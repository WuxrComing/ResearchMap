import re
import threading
import uuid
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from PyQt6.QtCore import QObject, QThread, pyqtSignal
except ImportError:

    class QObject:  # type: ignore[no-redef]
        def __init__(self, parent=None):
            self._parent = parent

    class QThread:  # type: ignore[no-redef]
        pass

    class pyqtSignal:  # type: ignore[no-redef]
        def __init__(self, *args):
            pass

        def emit(self, *args):
            pass
from sqlmodel import Session, select

from app.models.agent_config import AgentConfig
from app.models.chat_message import ChatMessage
from app.services.llm import LLMService
from app.services.message_router import MessageRouter, parse_review_card


@dataclass
class ChatContextMessage:
    message_id: str
    role: str
    agent_name: str
    content: str
    created_at: datetime


@dataclass
class AgentTask:
    task_id: str
    session_id: str
    target_agent: str
    task_type: str
    instruction: str
    root_user_message_id: str
    trigger_message_id: str
    target_message_id: str | None
    context_snapshot: list[ChatContextMessage]
    dispatch_depth: int = 0
    redo_count: int = 0


@dataclass
class RuntimeStatusEntry:
    agent_name: str
    state: str
    task_type: str | None
    instruction_summary: str
    task_id: str | None
    root_user_message_id: str | None


def build_agent_user_prompt(task: AgentTask) -> str:
    lines = ["以下是当前群聊上下文，按时间顺序排列：", ""]
    for msg in task.context_snapshot:
        speaker = "User" if msg.role == "user" else (msg.agent_name or msg.role)
        lines.append(f"{speaker}:")
        lines.append(msg.content)
        lines.append("")
    lines.append("你的任务：")
    lines.append(task.instruction)
    return "\n".join(lines).strip()


class AgentWorker:
    def __init__(
        self,
        engine,
        llm_caller=None,
        canceled_roots=None,
        persistence_lock=None,
        message_saved=None,
        is_canceled=None,
    ):
        self.engine = engine
        self.llm_caller = llm_caller
        self.canceled_roots = canceled_roots if canceled_roots is not None else set()
        self.persistence_lock = persistence_lock
        self.message_saved = message_saved
        self.is_canceled = is_canceled

    def process_one(self, task: AgentTask) -> str | None:
        if self._is_canceled(task):
            return None

        agent = self._resolve_agent(task.target_agent)
        system_prompt = self._build_system_prompt(agent)
        user_prompt = build_agent_user_prompt(task)

        try:
            content = self._call_llm(agent, system_prompt, user_prompt)
        except Exception as exc:
            if self._is_canceled(task):
                return None
            self._save_message(
                task,
                role="system",
                content=f"Agent execution failed: {exc}",
            )
            return None

        if self._is_canceled(task):
            return None

        return self._save_message(task, role="assistant", content=content)

    def _call_llm(self, agent, system_prompt: str, user_prompt: str) -> str:
        if self.llm_caller is not None:
            return self.llm_caller(
                agent.name,
                system_prompt,
                user_prompt,
                agent.model,
            )

        service = LLMService()
        if agent.model:
            service.model = agent.model
        return service.call_simple(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def _is_canceled(self, task: AgentTask) -> bool:
        if task.root_user_message_id in self.canceled_roots:
            return True
        if task.task_id in self.canceled_roots:
            return True
        if self.is_canceled is not None:
            return bool(self.is_canceled(task))
        return False

    def _resolve_agent(self, agent_name: str):
        with Session(self.engine) as session:
            router = MessageRouter(session)
            agents = router.resolve_agents([agent_name])
            for agent in agents:
                if agent.name == agent_name:
                    return agent
            return agents[0]

    def _build_system_prompt(self, agent) -> str:
        with Session(self.engine) as session:
            router = MessageRouter(session)
            return router.build_system_prompt(agent)

    def _save_message(self, task: AgentTask, role: str, content: str) -> str | None:
        lock = self.persistence_lock if self.persistence_lock is not None else nullcontext()
        with lock:
            if self._is_canceled(task):
                return None
            with Session(self.engine) as session:
                message = ChatMessage(
                    session_id=task.session_id,
                    role=role,
                    content=content,
                    agent_name=task.target_agent,
                    task_id=task.task_id,
                    task_type=task.task_type,
                    root_user_message_id=task.root_user_message_id,
                    trigger_message_id=task.trigger_message_id,
                    target_message_id=task.target_message_id,
                    dispatch_depth=task.dispatch_depth,
                    redo_count=task.redo_count,
                )
                session.add(message)
                session.commit()
                session.refresh(message)
                message_id = message.id

        self._emit_message_saved(task.session_id, message_id)
        return message_id

    def _emit_message_saved(self, session_id: str, message_id: str) -> None:
        if self.message_saved is None:
            return
        try:
            self.message_saved.emit(session_id, message_id)
        except AttributeError:
            try:
                self.message_saved(session_id, message_id)
            except (TypeError, RuntimeError):
                self.message_saved((session_id, message_id))


class AgentDispatcher:
    MAX_DISPATCH_DEPTH = 5
    MAX_REDO_ROUNDS = 3

    def __init__(
        self,
        engine,
        enqueue_task,
        canceled_roots=None,
        processed_keys=None,
    ):
        self.engine = engine
        self.enqueue_task = enqueue_task
        self.canceled_roots = canceled_roots if canceled_roots is not None else set()
        self.processed_keys = processed_keys if processed_keys is not None else set()

    def handle_message_saved(self, message_id: str) -> list[AgentTask]:
        message = self._load_message(message_id)
        if message is None or message.role == "system":
            return []
        if (
            message.role == "assistant"
            and message.task_type == "review"
            and message.agent_name != "Topic Agent"
        ):
            return []

        root_id = self._latest_root_for_message(message)
        if message.id in self.canceled_roots or root_id in self.canceled_roots:
            return []

        if message.role == "user":
            tasks = self._tasks_for_user_message(message, root_id)
        elif (
            message.role == "assistant"
            and message.agent_name == "Topic Agent"
            and message.task_type == "review"
        ):
            return self._handle_topic_review(message)
        elif message.role == "assistant" and message.agent_name == "Topic Agent":
            tasks = self._tasks_for_topic_message(message, root_id)
        elif message.role == "assistant":
            tasks = [self._make_review_task(message, root_id)]
        else:
            tasks = []

        enqueued: list[AgentTask] = []
        for task in tasks:
            if self._enqueue_once(task):
                enqueued.append(task)
        return enqueued

    def _tasks_for_user_message(
        self,
        message: ChatMessage,
        root_id: str,
    ) -> list[AgentTask]:
        router = self._router()
        instructions = split_mention_instructions(
            message.content,
            router,
            source_agent="User",
        )
        if not instructions:
            topic_agent = router.resolve_agents([])[0]
            return [
                self._make_task(
                    session_id=message.session_id,
                    target_agent=topic_agent.name,
                    task_type="user_request",
                    instruction=message.content,
                    root_id=root_id,
                    trigger_id=message.id,
                    dispatch_depth=0,
                )
            ]

        return [
            self._make_task(
                session_id=message.session_id,
                target_agent=agent_name,
                task_type="user_request",
                instruction=instructions.get(agent_name, message.content),
                root_id=root_id,
                trigger_id=message.id,
                dispatch_depth=0,
            )
            for agent_name in instructions
        ]

    def _tasks_for_topic_message(
        self,
        message: ChatMessage,
        root_id: str,
    ) -> list[AgentTask]:
        router = self._router()
        instructions = split_mention_instructions(
            message.content,
            router,
            source_agent="Topic Agent",
        )
        return [
            self._make_task(
                session_id=message.session_id,
                target_agent=agent_name,
                task_type="dispatch",
                instruction=instruction,
                root_id=root_id,
                trigger_id=message.id,
                dispatch_depth=(message.dispatch_depth or 0) + 1,
            )
            for agent_name, instruction in instructions.items()
            if agent_name != "Topic Agent"
        ]

    def _make_review_task(
        self,
        message: ChatMessage,
        root_id: str,
    ) -> AgentTask:
        router = self._router()
        topic_agent = router.resolve_agents([])[0]
        return self._make_task(
            session_id=message.session_id,
            target_agent=topic_agent.name,
            task_type="review",
            instruction=(
                f"请审查 {message.agent_name} 的目标回复，"
                "只输出 [REVIEW]...[/REVIEW] 审查卡片。"
            ),
            root_id=root_id,
            trigger_id=message.id,
            target_id=message.id,
            dispatch_depth=message.dispatch_depth or 0,
            redo_count=message.redo_count or 0,
        )

    def _handle_topic_review(self, message: ChatMessage) -> list[AgentTask]:
        review = parse_review_card(message.content)
        if review is None or not message.target_message_id:
            return []
        if self._review_message_processed(message):
            return []

        with Session(self.engine) as session:
            target = session.get(ChatMessage, message.target_message_id)
            if target is None or target.session_id != message.session_id:
                return []

            target_id = target.id
            target_agent = target.agent_name
            target_dispatch_depth = target.dispatch_depth or 0
            redo_count = target.redo_count or 0
            root_id = (
                message.root_user_message_id
                or target.root_user_message_id
                or self._latest_root_for_message(message)
            )
            redo_exhausted = (
                review.action == "redo" and redo_count >= self.MAX_REDO_ROUNDS
            )

        if review.action == "accept":
            self._persist_review_result(
                message.target_message_id,
                review,
                review_message_id=message.id,
            )
            return []
        elif review.action == "redo":
            task_redo_count = redo_count if redo_exhausted else redo_count + 1
            tasks = self._tasks_for_redo_review(
                message=message,
                review_summary=review.summary,
                root_id=root_id,
                target_id=target_id,
                target_agent=target_agent,
                dispatch_depth=target_dispatch_depth,
                redo_count=task_redo_count,
                redo_exhausted=redo_exhausted,
            )
        elif review.action == "supplement":
            tasks = self._tasks_for_supplement_review(
                message=message,
                root_id=root_id,
                target_id=target_id,
                target_dispatch_depth=target_dispatch_depth,
            )
        else:
            tasks = []

        def persist_review_result():
            self._persist_review_result(
                target_id,
                review,
                redo_count=task_redo_count if review.action == "redo" else None,
                review_message_id=message.id,
            )

        return self._enqueue_review_tasks(tasks, persist_review_result)

    def _review_message_processed(self, message: ChatMessage) -> bool:
        return message.dispatch_processed

    def _enqueue_review_tasks(
        self,
        tasks: list[AgentTask],
        persist_result,
    ) -> list[AgentTask]:
        enqueued: list[AgentTask] = []
        try:
            for task in tasks:
                if self._enqueue_once(task):
                    enqueued.append(task)
            if enqueued:
                persist_result()
            return enqueued
        except Exception:
            for task in enqueued:
                self.processed_keys.discard(self._processed_key(task))
            raise

    def _persist_review_result(
        self,
        target_id: str,
        review,
        redo_count: int | None = None,
        review_message_id: str | None = None,
    ) -> None:
        with Session(self.engine) as session:
            target = session.get(ChatMessage, target_id)
            if target is None:
                return

            target.review_status = self._review_status_for_action(review)
            target.review_score = review.score
            target.review_summary = review.summary
            if redo_count is not None:
                target.redo_count = redo_count

            session.add(target)
            if review_message_id:
                review_message = session.get(ChatMessage, review_message_id)
                if review_message:
                    review_message.dispatch_processed = True
                    session.add(review_message)
            session.commit()

    def _review_status_for_action(self, review) -> str:
        if review.action == "supplement":
            return "supplemented"
        if review.correctness == "pass":
            return "passed"
        return "failed"

    def _tasks_for_redo_review(
        self,
        message: ChatMessage,
        review_summary: str,
        root_id: str,
        target_id: str,
        target_agent: str,
        dispatch_depth: int,
        redo_count: int,
        redo_exhausted: bool,
    ) -> list[AgentTask]:
        if redo_exhausted:
            return [
                self._make_fallback_task(
                    message=message,
                    root_id=root_id,
                    target_id=target_id,
                    dispatch_depth=dispatch_depth,
                )
            ]

        return [
            self._make_task(
                session_id=message.session_id,
                target_agent=target_agent,
                task_type="redo",
                instruction=review_summary,
                root_id=root_id,
                trigger_id=message.id,
                target_id=target_id,
                dispatch_depth=dispatch_depth,
                redo_count=redo_count,
            )
        ]

    def _make_fallback_task(
        self,
        message: ChatMessage,
        root_id: str,
        target_id: str,
        dispatch_depth: int,
    ) -> AgentTask:
        return self._make_task(
            session_id=message.session_id,
            target_agent="Topic Agent",
            task_type="fallback",
            instruction="子 Agent 多次重做仍未通过审查。请基于群聊上下文直接给出纠正后的回答。",
            root_id=root_id,
            trigger_id=message.id,
            target_id=target_id,
            dispatch_depth=dispatch_depth,
        )

    def _tasks_for_supplement_review(
        self,
        message: ChatMessage,
        root_id: str,
        target_id: str,
        target_dispatch_depth: int,
    ) -> list[AgentTask]:
        router = self._router()
        instructions = split_mention_instructions(
            message.content,
            router,
            source_agent="Topic Agent",
        )
        source_depth = (
            message.dispatch_depth
            if message.dispatch_depth is not None
            else target_dispatch_depth
        )
        return [
            self._make_task(
                session_id=message.session_id,
                target_agent=agent_name,
                task_type="dispatch",
                instruction=instruction,
                root_id=root_id,
                trigger_id=message.id,
                target_id=target_id,
                dispatch_depth=source_depth + 1,
            )
            for agent_name, instruction in instructions.items()
            if agent_name != "Topic Agent"
        ]

    def _load_message(self, message_id: str) -> ChatMessage | None:
        with Session(self.engine) as session:
            return session.get(ChatMessage, message_id)

    def _latest_root_for_message(self, message: ChatMessage) -> str:
        if message.root_user_message_id:
            return message.root_user_message_id
        if message.role == "user":
            return message.id

        with Session(self.engine) as session:
            root = session.exec(
                select(ChatMessage)
                .where(ChatMessage.session_id == message.session_id)
                .where(ChatMessage.role == "user")
                .where(ChatMessage.created_at <= message.created_at)
                .order_by(ChatMessage.created_at.desc())
            ).first()
            return root.id if root else message.id

    def _build_context_snapshot(
        self,
        session_id: str,
        root_id: str,
        trigger_id: str,
        target_id: str | None = None,
        limit: int = 20,
    ) -> list[ChatContextMessage]:
        required_ids = {root_id, trigger_id}
        if target_id:
            required_ids.add(target_id)

        with Session(self.engine) as session:
            recent = session.exec(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            ).all()
            messages_by_id = {message.id: message for message in recent}

            missing_ids = required_ids - set(messages_by_id)
            if missing_ids:
                required_messages = session.exec(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .where(ChatMessage.id.in_(missing_ids))
                ).all()
                messages_by_id.update(
                    {message.id: message for message in required_messages}
                )

            messages = sorted(
                messages_by_id.values(),
                key=lambda message: (message.created_at, message.id),
            )
            return [
                ChatContextMessage(
                    message_id=message.id,
                    role=message.role,
                    agent_name=message.agent_name,
                    content=message.content,
                    created_at=message.created_at,
                )
                for message in messages
            ]

    def _make_task(
        self,
        session_id: str,
        target_agent: str,
        task_type: str,
        instruction: str,
        root_id: str,
        trigger_id: str,
        target_id: str | None = None,
        dispatch_depth: int = 0,
        redo_count: int = 0,
    ) -> AgentTask:
        return AgentTask(
            task_id=uuid.uuid4().hex,
            session_id=session_id,
            target_agent=target_agent,
            task_type=task_type,
            instruction=instruction,
            root_user_message_id=root_id,
            trigger_message_id=trigger_id,
            target_message_id=target_id,
            context_snapshot=self._build_context_snapshot(
                session_id,
                root_id,
                trigger_id,
                target_id=target_id,
            ),
            dispatch_depth=dispatch_depth,
            redo_count=redo_count,
        )

    def _enqueue_once(self, task: AgentTask) -> bool:
        if not self._can_enqueue_depth(task):
            return False

        key = self._processed_key(task)
        if key in self.processed_keys:
            return False

        self.enqueue_task(task)
        self.processed_keys.add(key)
        return True

    def _processed_key(self, task: AgentTask):
        return (
            task.session_id,
            task.trigger_message_id,
            task.task_type,
            task.target_agent,
            task.target_message_id,
        )

    def _can_enqueue_depth(self, task: AgentTask) -> bool:
        return task.dispatch_depth <= self.MAX_DISPATCH_DEPTH

    def _router(self) -> MessageRouter:
        with Session(self.engine) as session:
            router = MessageRouter(session)
            router._db = None
            return router


@dataclass
class MentionSpan:
    agent_name: str
    start: int
    end: int


_MENTION_SUFFIX_BOUNDARY = r"(?![A-Za-z0-9_])"


def strip_fenced_code(text: str) -> str:
    """Mask fenced code blocks while preserving string length and line positions."""
    if not text:
        return ""

    stripped_lines: list[str] = []
    in_fence = False

    for line in text.splitlines(keepends=True):
        starts_fence = line.lstrip().startswith("```")
        should_mask = in_fence or starts_fence

        if should_mask:
            stripped_lines.append(_mask_text_preserving_newlines(line))
        else:
            stripped_lines.append(line)

        if starts_fence:
            in_fence = not in_fence

    return "".join(stripped_lines)


def find_mention_spans(text: str, router) -> list[MentionSpan]:
    if not text:
        return []

    agent_names = router.get_all_agent_names()
    if not agent_names:
        return []

    return _find_named_mention_spans(text, agent_names)


def split_mention_instructions(text: str, router, source_agent: str) -> dict[str, str]:
    if not text:
        return {}

    dispatch_spans = find_mention_spans(text, router)
    boundary_spans = _find_boundary_mention_spans(text, router)
    if source_agent == "Topic Agent":
        dispatch_spans = [
            span for span in dispatch_spans if span.agent_name != "Topic Agent"
        ]

    dispatch_span_positions = {
        (span.start, span.end, span.agent_name) for span in dispatch_spans
    }
    spans = [
        (span, (span.start, span.end, span.agent_name) in dispatch_span_positions)
        for span in boundary_spans
    ]

    if not spans:
        return {}

    segments: dict[str, list[str]] = {}
    empty_only_agents: set[str] = set()

    for index, (span, should_dispatch) in enumerate(spans):
        next_start = spans[index + 1][0].start if index + 1 < len(spans) else len(text)
        if not should_dispatch:
            continue

        segment = _clean_instruction_segment(text[span.end:next_start])
        if segment:
            segments.setdefault(span.agent_name, []).append(segment)
            empty_only_agents.discard(span.agent_name)
        elif span.agent_name not in segments:
            empty_only_agents.add(span.agent_name)

    instructions = {
        agent_name: "\n\n".join(agent_segments)
        for agent_name, agent_segments in segments.items()
        if agent_segments
    }
    for agent_name in empty_only_agents:
        if agent_name not in instructions:
            instructions[agent_name] = text

    return instructions


def _clean_instruction_segment(segment: str) -> str:
    return segment.strip().lstrip("：:，,").strip()


def _mask_text_preserving_newlines(text: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in text)


def _find_named_mention_spans(text: str, agent_names: list[str]) -> list[MentionSpan]:
    if not text or not agent_names:
        return []

    names_pattern = "|".join(
        re.escape(name) for name in sorted(agent_names, key=len, reverse=True)
    )
    mention_pattern = re.compile(
        rf"@(?P<agent_name>{names_pattern}){_MENTION_SUFFIX_BOUNDARY}"
    )
    searchable_text = strip_fenced_code(text)
    spans = [
        MentionSpan(
            agent_name=match.group("agent_name"),
            start=match.start(),
            end=match.end(),
        )
        for match in mention_pattern.finditer(searchable_text)
    ]
    spans.sort(key=lambda span: span.start)
    return spans


def _find_boundary_mention_spans(text: str, router) -> list[MentionSpan]:
    configured_spans = _find_named_mention_spans(
        text,
        _get_configured_agent_names(router),
    )
    generic_spans = _find_generic_agent_mention_spans(text)

    spans_by_position: dict[tuple[int, int], MentionSpan] = {}
    for span in generic_spans + configured_spans:
        spans_by_position[(span.start, span.end)] = span

    spans = list(spans_by_position.values())
    spans.sort(key=lambda span: span.start)
    return spans


def _get_configured_agent_names(router) -> list[str]:
    db = getattr(router, "_db", None)
    if db is None:
        return list(router.get_all_agent_names())

    agents = db.exec(select(AgentConfig)).all()
    return [agent.name for agent in agents]


def _find_generic_agent_mention_spans(text: str) -> list[MentionSpan]:
    searchable_text = strip_fenced_code(text)
    pattern = re.compile(
        rf"@(?P<agent_name>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*)* Agent)"
        rf"{_MENTION_SUFFIX_BOUNDARY}"
    )
    spans = [
        MentionSpan(
            agent_name=match.group("agent_name"),
            start=match.start(),
            end=match.end(),
        )
        for match in pattern.finditer(searchable_text)
    ]
    spans.sort(key=lambda span: span.start)
    return spans


class _RuntimeWorkerThread(QThread):
    """Drains one agent's queue in a background thread."""

    def __init__(self, runtime, agent_name: str, parent=None):
        super().__init__(parent)
        self._runtime = runtime
        self._agent_name = agent_name

    def run(self):
        while not self._runtime.closed:
            queue = self._runtime.queues.get(self._agent_name)
            if not queue:
                break
            try:
                task = queue.popleft()
            except IndexError:
                break

            if task.root_user_message_id in self._runtime.canceled_roots:
                continue

            worker = self._runtime._ensure_worker(self._agent_name)
            self._runtime._active_workers_count += 1
            self._runtime._emit_status()
            try:
                message_id = worker.process_one(task)
            finally:
                self._runtime._active_workers_count -= 1

            if message_id is not None:
                self._runtime.on_message_saved(message_id)
                self._runtime._start_draining()

        self._runtime.queues.pop(self._agent_name, None)
        self._runtime._threads.pop(self._agent_name, None)
        self._runtime._emit_status()


class NativeWorkerThread(threading.Thread):
    """Non-Qt alternative to _RuntimeWorkerThread for web server use."""

    def __init__(self, runtime, agent_name: str):
        super().__init__(daemon=True)
        self._runtime = runtime
        self._agent_name = agent_name

    def isRunning(self) -> bool:
        return self.is_alive()

    def quit(self) -> None:
        pass  # Thread exits naturally when runtime is closed

    def wait(self, timeout: int = 3000) -> bool:
        self.join(timeout / 1000.0)
        return not self.is_alive()

    def run(self):
        while not self._runtime.closed:
            queue = self._runtime.queues.get(self._agent_name)
            if not queue:
                break
            try:
                task = queue.popleft()
            except IndexError:
                break

            if task.root_user_message_id in self._runtime.canceled_roots:
                continue

            worker = self._runtime._ensure_worker(self._agent_name)
            self._runtime._active_workers_count += 1
            self._runtime._emit_status()
            try:
                message_id = worker.process_one(task)
            finally:
                self._runtime._active_workers_count -= 1

            if message_id is not None:
                self._runtime.on_message_saved(message_id)
                self._runtime._start_draining()

        self._runtime.queues.pop(self._agent_name, None)
        self._runtime._threads.pop(self._agent_name, None)
        self._runtime._emit_status()


class SessionRuntime:
    def __init__(
        self,
        session_id: str,
        engine,
        llm_caller=None,
        persistence_lock=None,
        message_saved_signal=None,
        status_changed_signal=None,
    ):
        self.session_id = session_id
        self.engine = engine
        self.llm_caller = llm_caller
        self.persistence_lock = persistence_lock
        self.message_saved_signal = message_saved_signal
        self.status_changed_signal = status_changed_signal
        self.queues: dict[str, deque[AgentTask]] = {}
        self.workers: dict[str, AgentWorker] = {}
        self._threads: dict[str, threading.Thread | _RuntimeWorkerThread] = {}
        self._thread_class = NativeWorkerThread  # can be swapped for tests
        self.processed_keys: set[tuple] = set()
        self.canceled_roots: set[str] = set()
        self._closed = False
        self._active_workers_count = 0
        self._draining_sync = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _enqueue_task(self, task: AgentTask) -> None:
        if self._closed:
            return
        if task.root_user_message_id in self.canceled_roots:
            return
        queue = self.queues.setdefault(task.target_agent, deque())
        queue.append(task)
        self._emit_status()

    def _ensure_worker(self, agent_name: str) -> AgentWorker:
        if agent_name not in self.workers:
            worker = AgentWorker(
                self.engine,
                llm_caller=self.llm_caller,
                canceled_roots=self.canceled_roots,
                persistence_lock=self.persistence_lock,
                message_saved=self._on_worker_message_saved,
            )
            self.workers[agent_name] = worker
        return self.workers[agent_name]

    def _start_draining(self) -> None:
        """Launch worker threads for agents with queued tasks and no active thread."""
        if self._closed or self._draining_sync:
            return
        for agent_name in list(self.queues.keys()):
            if not self.queues[agent_name]:
                continue
            if agent_name in self._threads and self._threads[agent_name].isRunning():
                continue
            self._ensure_worker(agent_name)
            thread = self._thread_class(self, agent_name)
            self._threads[agent_name] = thread
            thread.start()

    def _emit_status(self) -> None:
        if self._draining_sync:
            return
        entries = self._build_status_entries()
        if self.status_changed_signal is not None:
            try:
                self.status_changed_signal.emit(self.session_id, entries)
            except AttributeError:
                try:
                    self.status_changed_signal(self.session_id, entries)
                except (TypeError, RuntimeError):
                    pass

    def _build_status_entries(self) -> list[RuntimeStatusEntry]:
        entries: list[RuntimeStatusEntry] = []
        for agent_name, queue in self.queues.items():
            if not queue:
                continue
            task = queue[0]
            state = "running" if (
                agent_name in self._threads
                and self._threads[agent_name].isRunning()
            ) else "queued"
            entries.append(RuntimeStatusEntry(
                agent_name=agent_name,
                state=state,
                task_type=task.task_type,
                instruction_summary=task.instruction[:50],
                task_id=task.task_id,
                root_user_message_id=task.root_user_message_id,
            ))
        return entries

    def _on_worker_message_saved(self, session_id: str, message_id: str) -> None:
        if self.message_saved_signal is not None:
            try:
                self.message_saved_signal.emit(session_id, message_id)
            except AttributeError:
                try:
                    self.message_saved_signal(session_id, message_id)
                except (TypeError, RuntimeError):
                    self.message_saved_signal((session_id, message_id))

    def _get_or_create_dispatcher(self) -> AgentDispatcher:
        return AgentDispatcher(
            self.engine,
            enqueue_task=self._enqueue_task,
            canceled_roots=self.canceled_roots,
            processed_keys=self.processed_keys,
        )

    def on_message_saved(self, message_id: str) -> None:
        if self._closed:
            return
        dispatcher = self._get_or_create_dispatcher()
        tasks = dispatcher.handle_message_saved(message_id)
        for task in tasks:
            self._ensure_worker(task.target_agent)

    def _drain_one(self) -> bool:
        """Process one task from any agent queue. Returns True if a task was processed."""
        for agent_name, queue in list(self.queues.items()):
            if not queue:
                continue
            task = queue.popleft()
            if not queue:
                del self.queues[agent_name]

            if task.root_user_message_id in self.canceled_roots:
                return True

            worker = self._ensure_worker(agent_name)
            self._active_workers_count += 1
            try:
                message_id = worker.process_one(task)
            finally:
                self._active_workers_count -= 1

            if message_id is not None:
                self.on_message_saved(message_id)
            return True
        return False

    def drain_for_tests(self, max_steps: int = 50) -> None:
        """Process all queued tasks synchronously. For tests only."""
        self._draining_sync = True
        try:
            for _ in range(max_steps):
                if not self._drain_one():
                    break
        finally:
            self._draining_sync = False

    def cancel_root(self, root_user_message_id: str) -> None:
        self.canceled_roots.add(root_user_message_id)
        for queue in self.queues.values():
            to_remove = [
                t for t in queue
                if t.root_user_message_id == root_user_message_id
            ]
            for task in to_remove:
                queue.remove(task)

    def close(self, reason: str = "") -> None:
        self._closed = True
        self.queues.clear()
        for thread in list(self._threads.values()):
            if thread.isRunning():
                thread.quit()
                thread.wait(3000)
        self._threads.clear()

    @property
    def has_pending_tasks(self) -> bool:
        return any(len(q) > 0 for q in self.queues.values()) or self._active_workers_count > 0


class SessionRuntimeManager(QObject):
    message_saved = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, list)
    error = pyqtSignal(str, str)

    def __init__(self, engine=None, llm_caller=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.llm_caller = llm_caller
        self._runtimes: dict[str, SessionRuntime] = {}
        self._persistence_lock = None

    def get_runtime(self, session_id: str) -> SessionRuntime:
        if session_id not in self._runtimes:
            self._runtimes[session_id] = SessionRuntime(
                session_id=session_id,
                engine=self.engine,
                llm_caller=self.llm_caller,
                persistence_lock=self._persistence_lock,
                message_saved_signal=self.message_saved,
                status_changed_signal=self.status_changed,
            )
        return self._runtimes[session_id]

    def submit_message(self, session_id: str, message_id: str) -> None:
        rt = self.get_runtime(session_id)
        rt.on_message_saved(message_id)

    def start_draining(self, session_id: str) -> None:
        """Start worker threads for any queued tasks in the session."""
        rt = self.get_runtime(session_id)
        rt._start_draining()

    def cancel_root(self, session_id: str, root_user_message_id: str) -> None:
        # Ensure the runtime exists so cancellation is recorded even before the
        # first submit_message call.
        rt = self.get_runtime(session_id)
        rt.cancel_root(root_user_message_id)

    def shutdown(self) -> None:
        for rt in list(self._runtimes.values()):
            rt.close(reason="shutdown")
        self._runtimes.clear()
