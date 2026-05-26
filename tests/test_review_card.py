import pytest
from app.services.message_router import parse_review_card, ReviewResult


class TestParseReviewCard:
    def test_parse_pass_review(self):
        text = """[REVIEW]
summary: Paper Agent找到了3篇相关论文，覆盖了高斯监督方向
correctness: pass
score: 4
issues:
  - none
action: accept
[/REVIEW]"""
        result = parse_review_card(text)
        assert result is not None
        assert result.correctness == "pass"
        assert result.score == 4
        assert result.action == "accept"
        assert "高斯监督" in result.summary
        assert result.issues == ["none"]

    def test_parse_fail_review(self):
        text = """[REVIEW]
summary: 回复混淆了QGLS与传统标签平滑
correctness: fail
score: 2
issues:
  - 忽略了2023-2024年的最新进展
  - 混淆了QGLS和传统标签平滑的概念
action: redo
[/REVIEW]"""
        result = parse_review_card(text)
        assert result is not None
        assert result.correctness == "fail"
        assert result.score == 2
        assert result.action == "redo"
        assert len(result.issues) == 2
        assert "最新进展" in result.issues[0]

    def test_parse_partial_review(self):
        text = """[REVIEW]
summary: 回答基本正确但遗漏了不确定性感知方向
correctness: partial
score: 3
issues:
  - 未覆盖不确定性感知分配方向
action: supplement
[/REVIEW]"""
        result = parse_review_card(text)
        assert result is not None
        assert result.correctness == "partial"
        assert result.action == "supplement"

    def test_no_review_card_returns_none(self):
        text = "这是一段普通的回复，没有审查卡片。"
        result = parse_review_card(text)
        assert result is None

    def test_malformed_review_returns_none(self):
        text = "[REVIEW]\nsome broken content\nwithout proper structure"
        result = parse_review_card(text)
        assert result is None

    def test_review_with_markdown_around(self):
        text = """一些前置文字...
[REVIEW]
summary: 测试摘要
correctness: pass
score: 5
issues:
  - none
action: accept
[/REVIEW]
后续文字..."""
        result = parse_review_card(text)
        assert result is not None
        assert result.correctness == "pass"
        assert result.score == 5

    def test_review_card_single_issue(self):
        text = """[REVIEW]
summary: 回答准确
correctness: pass
score: 4
issues:
  - 可以补充更多引用
action: accept
[/REVIEW]"""
        result = parse_review_card(text)
        assert result is not None
        assert len(result.issues) == 1
