import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, select

from app.models.agent_config import AgentConfig
from app.models.chat_message import ChatMessage
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

        with Session(self.engine) as session:
            target = session.get(ChatMessage, message.target_message_id)
            if target is None or target.session_id != message.session_id:
                return []

            target.review_status = self._review_status_for_action(review)
            target.review_score = review.score
            target.review_summary = review.summary

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
            if review.action == "redo" and not redo_exhausted:
                redo_count += 1
                target.redo_count = redo_count

            session.add(target)
            session.commit()

        if review.action == "accept":
            tasks = []
        elif review.action == "redo":
            tasks = self._tasks_for_redo_review(
                message=message,
                review_summary=review.summary,
                root_id=root_id,
                target_id=target_id,
                target_agent=target_agent,
                dispatch_depth=target_dispatch_depth,
                redo_count=redo_count,
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

        enqueued: list[AgentTask] = []
        for task in tasks:
            if self._enqueue_once(task):
                enqueued.append(task)
        return enqueued

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
