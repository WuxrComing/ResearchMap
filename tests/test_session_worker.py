"""Tests for review/redo utilities that remain after the runtime migration.

The old serial SessionWorker and QueuedMessage have been replaced by
SessionRuntimeManager, SessionRuntime, AgentDispatcher, and AgentWorker
(see tests/test_agent_runtime_*.py for the new runtime tests).
"""

import pytest


class TestReviewPipeline:
    """Tests for review card parsing, ReviewResult, and build_redo_message."""

    def test_review_card_detected(self):
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
        assert result.correctness == "pass"
        assert result.score == 4

    def test_save_message_with_review_fields(self):
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

    def test_parse_review_card_rejects_dispatch_block(self):
        """parse_review_card should not match >>DISPATCH>> blocks."""
        from app.services.message_router import parse_review_card
        assert parse_review_card("直接回答用户问题") is None
        assert parse_review_card("") is None
