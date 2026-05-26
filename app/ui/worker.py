import uuid
from PyQt6.QtCore import QThread, pyqtSignal
from sqlmodel import Session, select
from app.services.storage import get_engine
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from app.agents.topic_builder import TopicBuilder
from collections import deque
from dataclasses import dataclass, field
from app.services.message_router import DispatchRequest, ReviewResult


@dataclass
class QueuedMessage:
    """A message waiting in a session's processing queue."""
    content: str
    mentioned_agents: list[str] = field(default_factory=list)
    status: str = "queued"  # "queued" | "thinking" | "done" | "cancelled"
    db_msg_id: str = ""


class SessionWorker(QThread):
    """Processes a single chat message via LLM, then signals done.
    Supports dispatch->review->redo pipeline when Topic Agent is Supervisor."""

    MAX_REDO_ROUNDS = 3

    thinking = pyqtSignal(str)           # session_id
    done = pyqtSignal(str, str)          # session_id, agent_name
    error = pyqtSignal(str, str)         # session_id, error_message

    def __init__(self, session_id: str, queued_message: QueuedMessage, parent=None):
        super().__init__(parent)
        self._session_id = session_id
        self._qm = queued_message
        self._cancel_current = False

    def cancel(self):
        self._cancel_current = True
        self._qm.status = "cancelled"

    def _call_agent_llm(self, agent_name: str, system_prompt: str, user_prompt: str, agent_model: str = "") -> str:
        """Call LLM for a specific agent and return the reply text."""
        from app.services.llm import LLMService
        llm = LLMService()
        if agent_model:
            llm.model = agent_model
        try:
            reply = llm.call_simple(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            if reply.startswith("LLM Error:"):
                self.error.emit(self._session_id, reply)
            return reply
        except Exception as e:
            self.error.emit(self._session_id, str(e))
            return f"抱歉，调用大模型时出错：{e}"

    def _save_message(self, engine, session_id: str, role: str, content: str,
                      agent_name: str = "", review_status: str | None = None,
                      review_score: int | None = None, review_summary: str | None = None,
                      redo_count: int = 0) -> str:
        """Save a message to DB and return its ID."""
        msg_id = uuid.uuid4().hex
        with Session(engine) as db:
            db.add(ChatMessage(
                id=msg_id, session_id=session_id, role=role,
                content=content, agent_name=agent_name,
                review_status=review_status, review_score=review_score,
                review_summary=review_summary, redo_count=redo_count,
            ))
            db.commit()
        return msg_id

    def _get_topic_agent_prompt(self) -> str:
        """Get Topic Agent's system prompt from DB."""
        engine = get_engine()
        with Session(engine) as db:
            from app.models.agent_config import AgentConfig
            from sqlmodel import select
            topic = db.exec(
                select(AgentConfig).where(AgentConfig.name == "Topic Agent")
            ).first()
            if topic:
                return topic.system_prompt
        return ""

    def _run_review(self, engine, session_id: str, target_agent_name: str,
                    target_reply: str, redo_count: int) -> tuple[str, ReviewResult | None, bool]:
        """Run Topic Agent review on target_reply.
        Returns (review_message, review_result, should_redo).
        """
        from app.services.message_router import parse_review_card

        review_text = self._call_agent_llm(
            agent_name="Topic Agent",
            system_prompt=self._get_topic_agent_prompt(),
            user_prompt=(
                f"请审查以下来自 {target_agent_name} 的回复。\n\n"
                f"--- {target_agent_name} 的回复 ---\n"
                f"{target_reply}\n"
                f"--- 回复结束 ---\n\n"
                f"请输出审查卡片 [REVIEW]...[/REVIEW]，必要时给出纠正指令。"
            ),
        )
        if review_text.startswith("抱歉"):
            return f"[审查跳过 — LLM 调用失败] {target_agent_name} 的回复未审查", None, False

        review = parse_review_card(review_text)
        if review is None:
            return review_text, None, False

        # Update the target's message with review status
        with Session(engine) as db:
            from sqlmodel import select as sql_select
            target_msg = db.exec(
                sql_select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .where(ChatMessage.agent_name == target_agent_name)
                .order_by(ChatMessage.created_at.desc())
            ).first()
            if target_msg:
                target_msg.review_status = "passed" if review.correctness == "pass" else "failed"
                target_msg.review_score = review.score
                target_msg.review_summary = review.summary
                if review.action == "redo":
                    target_msg.redo_count = redo_count + 1
                db.add(target_msg)
                db.commit()

        if review.action == "redo" and redo_count < self.MAX_REDO_ROUNDS:
            return review_text, review, True

        return review_text, review, False

    def run(self):
        if self._cancel_current:
            self.done.emit(self._session_id, "")
            return

        self._qm.status = "thinking"
        self.thinking.emit(self._session_id)
        engine = get_engine()

        # 1. Resolve target agents
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            router = MessageRouter(db)
            if self._qm.mentioned_agents:
                agents = router.resolve_agents(self._qm.mentioned_agents)
            else:
                agents = router.resolve_agents([])

        if not agents:
            self.done.emit(self._session_id, "System")
            return

        # 2. Build chat history once
        with Session(engine) as db:
            from sqlmodel import select as sql_select
            history = db.exec(
                sql_select(ChatMessage)
                .where(ChatMessage.session_id == self._session_id)
                .order_by(ChatMessage.created_at.asc())
            ).all()

        def _build_user_prompt(dispatch: DispatchRequest | None = None) -> str:
            lines = []
            for msg in history[-20:]:
                if msg.role == "assistant":
                    lines.append(f"{msg.agent_name or 'Assistant'}: {msg.content}")
                else:
                    lines.append(f"User: {msg.content}")
            if dispatch:
                lines.append("")
                lines.append(f"Topic Agent 公开指挥给 @{dispatch.target_agent} 的任务：")
                lines.append(dispatch.task)
            return "\n".join(lines)

        last_agent_name = agents[0].name if agents else "System"

        # 3. Process each target agent
        pending_agents: deque[tuple[object, DispatchRequest | None]] = deque(
            (agent, None) for agent in agents
        )
        called_dispatches: set[tuple[str, str]] = set()

        while pending_agents:
            if self._cancel_current:
                break

            routed, dispatch = pending_agents.popleft()
            agent_name = routed.name
            agent_model = routed.model

            with Session(engine) as db:
                router2 = MessageRouter(db)
                system_prompt = router2.build_system_prompt(routed)

            user_prompt = _build_user_prompt(dispatch)

            # 3a. Call the target agent
            reply = self._call_agent_llm(agent_name, system_prompt, user_prompt, agent_model)

            if self._cancel_current:
                break

            # 3b. Save the agent's reply
            self._save_message(engine, self._session_id, role="assistant",
                               content=reply, agent_name=agent_name)

            last_agent_name = agent_name

            # 3c. Topic Agent dispatches are public group-chat messages that
            # enqueue the requested agents; their replies remain separate.
            if agent_name == "Topic Agent":
                from app.services.message_router import MessageRouter, parse_dispatch_blocks

                dispatches = parse_dispatch_blocks(reply)
                if dispatches:
                    with Session(engine) as db:
                        router3 = MessageRouter(db)
                        name_map = {a.name: a for a in router3.resolve_agents(
                            [d.target_agent for d in dispatches]
                        )}
                    for child_dispatch in dispatches:
                        key = (child_dispatch.target_agent, child_dispatch.task)
                        routed_child = name_map.get(child_dispatch.target_agent)
                        if routed_child and child_dispatch.target_agent != "Topic Agent" and key not in called_dispatches:
                            called_dispatches.add(key)
                            pending_agents.append((routed_child, child_dispatch))
                continue

            # 3d. If target is NOT Topic Agent, run review
            if agent_name != "Topic Agent":
                redo_count = 0
                current_reply = reply
                redo_passed = False

                while redo_count <= self.MAX_REDO_ROUNDS:
                    if self._cancel_current:
                        break

                    review_text, review, should_redo = self._run_review(
                        engine, self._session_id, agent_name,
                        current_reply, redo_count,
                    )

                    # Save the review message
                    self._save_message(
                        engine, self._session_id, role="assistant",
                        content=review_text, agent_name="Topic Agent",
                        review_status="passed" if review and review.correctness == "pass" else "failed",
                        review_score=review.score if review else None,
                        review_summary=review.summary if review else None,
                    )

                    if not should_redo:
                        if review and review.correctness == "pass":
                            redo_passed = True
                        break

                    # Build redo prompt and send to original agent
                    redo_count += 1
                    redo_user_prompt = (
                        f"## 你的上一轮回复被 Topic Agent 审查为不通过\n\n"
                        f"审查反馈：{review.summary if review else '请改进'}\n\n"
                        f"请根据反馈重新回答用户的原始问题：\n{user_prompt}"
                    )
                    current_reply = self._call_agent_llm(
                        agent_name, system_prompt, redo_user_prompt, agent_model,
                    )
                    if self._cancel_current:
                        break
                    self._save_message(
                        engine, self._session_id, role="assistant",
                        content=current_reply, agent_name=agent_name,
                        redo_count=redo_count,
                    )
                    last_agent_name = agent_name

                # If max redo rounds reached without pass, Topic Agent handles it
                if not self._cancel_current and redo_count >= self.MAX_REDO_ROUNDS and not redo_passed:
                    ta_prompt = self._get_topic_agent_prompt()
                    ta_reply = self._call_agent_llm(
                        "Topic Agent", ta_prompt,
                        f"子 Agent ({agent_name}) 经过 {self.MAX_REDO_ROUNDS} 次重做仍未通过审查。"
                        f"请直接回答用户的原始问题：\n{user_prompt}",
                    )
                    if not self._cancel_current:
                        self._save_message(
                            engine, self._session_id, role="assistant",
                            content=ta_reply, agent_name="Topic Agent",
                        )
                        last_agent_name = "Topic Agent"

        # 4. Write cancellation notice if needed
        if self._cancel_current:
            with Session(engine) as db:
                db.add(ChatMessage(
                    id=uuid.uuid4().hex,
                    session_id=self._session_id,
                    role="system",
                    content="用户取消了此请求",
                ))
                db.commit()

        self._qm.status = "done" if not self._cancel_current else "cancelled"
        self.done.emit(self._session_id, last_agent_name)


class TopicBuildWorker(QThread):
    finished = pyqtSignal(str, str, int, int, list)  # topic_id, title, nodes, edges, errors
    progress = pyqtSignal(str)  # status message

    def __init__(self, title: str, description: str, parent=None,
                 topic_id: str = None, session_id: str = None):
        super().__init__(parent)
        self._title = title
        self._desc = description
        self._topic_id = topic_id
        self._session_id = session_id

    def run(self):
        self.progress.emit(f"正在为「{self._title}」生成思维导图...")

        engine = get_engine()
        topic_id = self._topic_id or uuid.uuid4().hex
        session_id = self._session_id or uuid.uuid4().hex

        if not self._topic_id:
            with Session(engine) as db:
                topic = Topic(id=topic_id, title=self._title, description=self._desc)
                db.add(topic)
                session = SessionModel(
                    id=session_id, workspace_id=topic_id, title="默认会话"
                )
                db.add(session)
                db.commit()

        builder = TopicBuilder()
        node_count, edge_count, errors = builder.build(
            topic_id, self._title, self._desc, session_id
        )

        if errors:
            error_text = "; ".join(errors)
            with Session(engine) as db:
                msg = ChatMessage(
                    id=uuid.uuid4().hex,
                    session_id=session_id,
                    role="system",
                    content=f"思维导图生成失败：{error_text}",
                )
                db.add(msg)
                db.commit()

        self.finished.emit(topic_id, self._title, node_count, edge_count, errors)

    @staticmethod
    def create_empty_workspace(title: str, description: str) -> tuple[str, str]:
        engine = get_engine()
        topic_id = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        with Session(engine) as db:
            topic = Topic(id=topic_id, title=title, description=description)
            db.add(topic)
            session = SessionModel(
                id=session_id, workspace_id=topic_id, title="默认会话"
            )
            db.add(session)

            msg = ChatMessage(
                id=uuid.uuid4().hex,
                session_id=session_id,
                role="system",
                content=f"课题「{title}」已创建。请点击「生成思维导图」或直接输入描述来初始化思维导图。",
            )
            db.add(msg)
            db.commit()
        return topic_id, session_id
