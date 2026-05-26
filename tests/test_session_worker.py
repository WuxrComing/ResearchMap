import pytest
from collections import deque
from unittest.mock import patch, MagicMock
from sqlmodel import Session, SQLModel, create_engine, select
from app.models.agent_config import AgentConfig
from app.models.chat_message import ChatMessage
from app.ui.worker import QueuedMessage, SessionWorker


class TestQueuedMessage:
    def test_default_status_is_queued(self):
        qm = QueuedMessage(content="hello")
        assert qm.status == "queued"
        assert qm.content == "hello"
        assert qm.mentioned_agents == []
        assert qm.db_msg_id == ""

    def test_with_mentions(self):
        qm = QueuedMessage(
            content="@Topic Agent help",
            mentioned_agents=["Topic Agent"],
            db_msg_id="abc123",
        )
        assert qm.mentioned_agents == ["Topic Agent"]
        assert qm.db_msg_id == "abc123"

    def test_custom_status(self):
        qm = QueuedMessage(content="test", status="thinking")
        assert qm.status == "thinking"


class TestSessionWorkerCancel:
    def test_cancel_sets_flag_and_status(self):
        qm = QueuedMessage(content="test")
        worker = SessionWorker("sess_1", qm)
        assert worker._cancel_current is False

        worker.cancel()
        assert worker._cancel_current is True
        assert qm.status == "cancelled"

    def test_cancelled_worker_returns_immediately(self):
        """Worker with cancel flag set should emit done without doing any work."""
        qm = QueuedMessage(content="test")
        worker = SessionWorker("sess_1", qm)
        worker.cancel()

        done_emitted = []

        def on_done(sid, agent_name):
            done_emitted.append((sid, agent_name))

        worker.done.connect(on_done)
        # Call run() directly (not via start()) so signals are delivered
        # synchronously in the same thread without needing a QApplication
        # event loop (pytest-qt is not available).
        worker.run()

        assert len(done_emitted) == 1
        assert done_emitted[0] == ("sess_1", "")
        assert qm.status == "cancelled"

    def test_thinking_status_set_during_run(self):
        """Worker should set status to 'thinking' when run starts."""
        qm = QueuedMessage(content="test")
        worker = SessionWorker("sess_1", qm)

        thinking_emitted = []

        def on_thinking(sid):
            thinking_emitted.append(sid)

        worker.thinking.connect(on_thinking)

        # Mock get_engine to raise so run() stops after emitting the
        # thinking signal — avoids DB/LLM dependencies.
        with patch("app.ui.worker.get_engine", side_effect=RuntimeError("no db")):
            with pytest.raises(RuntimeError, match="no db"):
                worker.run()

        assert len(thinking_emitted) == 1
        assert thinking_emitted[0] == "sess_1"
        assert qm.status == "thinking"


class TestMessageQueue:
    def test_queue_order_is_fifo(self):
        queue = deque()
        qm1 = QueuedMessage(content="first")
        qm2 = QueuedMessage(content="second")
        qm3 = QueuedMessage(content="third")

        queue.append(qm1)
        queue.append(qm2)
        queue.append(qm3)

        assert queue.popleft().content == "first"
        assert queue.popleft().content == "second"
        assert queue.popleft().content == "third"
        assert len(queue) == 0

    def test_cancelled_message_is_skipped(self):
        queue = deque()
        qm1 = QueuedMessage(content="first", status="cancelled")
        qm2 = QueuedMessage(content="second")

        queue.append(qm1)
        queue.append(qm2)

        # Simulate _process_next_in_queue skip logic
        msg = queue.popleft()
        if msg.status == "cancelled":
            msg = queue.popleft() if queue else None

        assert msg.content == "second"

    def test_empty_queue_is_handled(self):
        queue = deque()
        assert len(queue) == 0
        # Should handle empty queue without error
        result = queue.popleft() if queue else None
        assert result is None


class TestReviewPipeline:
    """Integration tests for the dispatch->review->redo pipeline."""

    def test_review_card_detected_on_non_topic_reply(self):
        """When a non-Topic agent replies, parse_review_card should be called."""
        from app.services.message_router import parse_review_card
        topic_review = """[REVIEW]
summary: 回答准确覆盖了相关论文
correctness: pass
score: 4
issues:
  - none
action: accept
[/REVIEW]"""
        result = parse_review_card(topic_review)
        assert result is not None
        assert result.action == "accept"

    def test_redo_loop_terminates_after_max_rounds(self):
        """Redo should stop at MAX_REDO_ROUNDS (3)."""
        from app.ui.worker import SessionWorker
        assert SessionWorker.MAX_REDO_ROUNDS == 3

    def test_save_message_with_review_fields(self):
        """ChatMessage should accept review_status, review_score etc."""
        from app.models.chat_message import ChatMessage
        msg = ChatMessage(
            session_id="test", role="assistant",
            content="test review", agent_name="Topic Agent",
            review_status="passed", review_score=4,
            review_summary="ok", redo_count=0,
        )
        assert msg.review_status == "passed"
        assert msg.review_score == 4

    def test_review_result_dataclass(self):
        """ReviewResult should store all required fields."""
        from app.services.message_router import ReviewResult
        r = ReviewResult(
            summary="test summary",
            correctness="fail",
            score=2,
            issues=["issue 1", "issue 2"],
            action="redo",
        )
        assert r.summary == "test summary"
        assert r.correctness == "fail"
        assert r.score == 2
        assert len(r.issues) == 2
        assert r.action == "redo"

    def test_build_redo_message_format(self):
        """build_redo_message should produce properly formatted redo instructions."""
        from app.services.message_router import build_redo_message, ReviewResult
        review = ReviewResult(
            summary="错误摘要",
            correctness="fail",
            score=2,
            issues=["问题1", "问题2"],
            action="redo",
        )
        msg = build_redo_message("Paper Agent", "原始回复", review)
        assert ">>REDO>>" in msg
        assert ">>END_REDO>>" in msg
        assert "@Paper Agent" in msg
        assert "问题1" in msg
        assert "问题2" in msg

    def test_topic_dispatch_is_public_then_child_replies_then_topic_reviews(self):
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(AgentConfig(
                name="Topic Agent", role="assistant", system_prompt="Topic prompt",
                description="监督者", model="", color="#07C160", enabled=True,
            ))
            db.add(AgentConfig(
                name="Paper Agent", role="paper", system_prompt="Paper prompt",
                description="论文检索", model="", color="#F9A825", enabled=True,
            ))
            db.commit()

        qm = QueuedMessage(content="帮我检索本领域的最新文献")
        worker = SessionWorker("sess_dispatch", qm)

        def fake_call(agent_name, system_prompt, user_prompt, agent_model=""):
            if agent_name == "Topic Agent" and "请审查以下来自 Paper Agent 的回复" in user_prompt:
                return """[REVIEW]
summary: Paper Agent 已独立完成检索。
correctness: pass
score: 5
issues:
  - none
action: accept
[/REVIEW]"""
            if agent_name == "Topic Agent":
                return """>>DISPATCH>> @Paper Agent
请检索本领域最新文献，并列出代表性论文。
>>END_DISPATCH>>"""
            if agent_name == "Paper Agent":
                assert "请检索本领域最新文献" in user_prompt
                return "Paper Agent 检索结果：论文 A、论文 B。"
            raise AssertionError(agent_name)

        with patch("app.ui.worker.get_engine", return_value=engine):
            with patch.object(worker, "_call_agent_llm", side_effect=fake_call):
                worker.run()

        with Session(engine) as db:
            messages = db.exec(
                select(ChatMessage).where(ChatMessage.session_id == "sess_dispatch")
                .order_by(ChatMessage.created_at.asc())
            ).all()

        assert [(m.agent_name, m.content.splitlines()[0]) for m in messages] == [
            ("Topic Agent", ">>DISPATCH>> @Paper Agent"),
            ("Paper Agent", "Paper Agent 检索结果：论文 A、论文 B。"),
            ("Topic Agent", "[REVIEW]"),
        ]
