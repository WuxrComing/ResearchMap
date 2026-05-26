# Topic Agent Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Topic Agent from a peer assistant to a Supervisor that distributes tasks, reviews all agent replies with structured review cards, and automatically triggers redo on failure.

**Architecture:** Refactor SessionWorker's message processing loop to support a dispatch→review→redo pipeline. Topic Agent gets a rewritten system prompt with DISPATCH/REDO internal commands and [REVIEW] structured output. MessageRouter gains review card parsing. ChatMessage gains review tracking fields.

**Tech Stack:** Python 3.11+, PyQt6, SQLModel, OpenAI-compatible LLM, Pydantic

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/models/chat_message.py` | Modify | Add review_status, review_score, review_summary, redo_count columns |
| `app/services/message_router.py` | Modify | Add ReviewResult dataclass, parse_review_card(), build_redo_message() |
| `app/agents/definitions.py` | Modify | Rewrite Topic Agent system prompt with Supervisor role |
| `app/ui/worker.py` | Modify | Refactor run() with dispatch→review→redo pipeline |
| `app/ui/chat_view.py` | Modify | Style review card messages |
| `tests/test_review_card.py` | Create | Test ReviewResult parsing from LLM-like output |
| `tests/test_message_router.py` | Modify | Add tests for new MessageRouter functions |

---

### Task 1: Add review fields to ChatMessage model

**Files:**
- Modify: `app/models/chat_message.py`

- [ ] **Step 1: Add review tracking fields**

In `app/models/chat_message.py`, add four nullable columns to the ChatMessage class after `node_id`:

```python
import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    session_id: str = Field(foreign_key="sessions.id", index=True)
    role: str = Field(default="user")
    content: str = Field(default="")
    agent_name: str = Field(default="")
    node_id: str | None = Field(default=None, foreign_key="map_nodes.id")
    review_status: str | None = Field(default=None)    # null | "passed" | "failed" | "supplemented"
    review_score: int | None = Field(default=None)      # 1-5
    review_summary: str | None = Field(default=None)    # Topic Agent 审查摘要
    redo_count: int = Field(default=0)                  # 该消息重做次数
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
```

- [ ] **Step 2: Verify tests still pass after model change**

Run: `pytest tests/test_storage.py -v`
Expected: Tests pass (model is auto-created in SQLite :memory:)

- [ ] **Step 3: Commit**

```bash
git add app/models/chat_message.py
git commit -m "feat: add review tracking fields to ChatMessage model"
```

---

### Task 2: Add ReviewResult dataclass and parser to MessageRouter

**Files:**
- Modify: `app/services/message_router.py`
- Create: `tests/test_review_card.py`

- [ ] **Step 1: Write failing tests for review card parsing**

Create `tests/test_review_card.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_review_card.py -v`
Expected: ImportError or all FAIL

- [ ] **Step 3: Implement ReviewResult and parse_review_card in MessageRouter**

Add to `app/services/message_router.py`, after the existing imports:

```python
import re
from dataclasses import dataclass
from sqlmodel import Session, select
from app.models.agent_config import AgentConfig


@dataclass
class ReviewResult:
    summary: str
    correctness: str       # "pass" | "partial" | "fail"
    score: int             # 1-5
    issues: list[str]
    action: str            # "accept" | "redo" | "supplement"


def parse_review_card(text: str) -> ReviewResult | None:
    """Parse [REVIEW]...[/REVIEW] card from Topic Agent output.
    Returns None if no valid review card is found."""
    m = re.search(r'\[REVIEW\]\s*\n(.*?)\n\s*\[/REVIEW\]', text, re.DOTALL)
    if not m:
        return None
    body = m.group(1)

    def _field(key: str) -> str | None:
        fm = re.search(rf'^{key}:\s*(.+)$', body, re.MULTILINE)
        return fm.group(1).strip() if fm else None

    def _list(key: str) -> list[str]:
        # Match lines like "  - item" after the key line
        pattern = rf'^{key}:\s*\n((?:\s*-\s*.+\n?)*)'
        lm = re.search(pattern, body, re.MULTILINE)
        if not lm:
            return []
        items = re.findall(r'^\s*-\s*(.+)$', lm.group(1), re.MULTILINE)
        return [i.strip() for i in items]

    summary = _field("summary")
    correctness = _field("correctness")
    score_str = _field("score")
    action = _field("action")
    issues = _list("issues")

    if not all([summary, correctness, score_str, action]):
        return None

    try:
        score = int(score_str)
    except (ValueError, TypeError):
        return None

    if correctness not in ("pass", "partial", "fail"):
        return None
    if action not in ("accept", "redo", "supplement"):
        return None

    return ReviewResult(
        summary=summary,
        correctness=correctness,
        score=score,
        issues=issues if issues else ["none"],
        action=action,
    )
```

Keep all existing `MessageRouter` class and `RoutedAgent` code below this addition.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_review_card.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/message_router.py tests/test_review_card.py
git commit -m "feat: add ReviewResult dataclass and review card parser"
```

---

### Task 3: Add build_redo_message helper to MessageRouter

**Files:**
- Modify: `app/services/message_router.py`
- Modify: `tests/test_message_router.py`

- [ ] **Step 1: Write failing test for build_redo_message**

Add to `tests/test_message_router.py` after the existing tests:

```python
class TestBuildRedoMessage:
    def test_build_redo_message(self):
        from app.services.message_router import build_redo_message, ReviewResult
        review = ReviewResult(
            summary="回复有误",
            correctness="fail",
            score=2,
            issues=["忽略了2024年论文", "混淆了概念"],
            action="redo",
        )
        msg = build_redo_message(
            target_agent="Paper Agent",
            original_reply="一些错误内容...",
            review=review,
        )
        assert "Paper Agent" in msg
        assert "忽略了2024年论文" in msg
        assert "混淆了概念" in msg
        assert ">>REDO>>" in msg
        assert ">>END_REDO>>" in msg

    def test_build_redo_includes_guidance(self):
        from app.services.message_router import build_redo_message, ReviewResult
        review = ReviewResult(
            summary="不完整",
            correctness="partial",
            score=3,
            issues=["遗漏了不确定性感知方法"],
            action="redo",
        )
        msg = build_redo_message(
            target_agent="Paper Agent",
            original_reply="之前的回答",
            review=review,
        )
        assert "遗漏了不确定性感知方法" in msg
        assert "重新回答" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_message_router.py::TestBuildRedoMessage -v`
Expected: ImportError or FAIL

- [ ] **Step 3: Implement build_redo_message**

Add to `app/services/message_router.py`, after `parse_review_card`:

```python
def build_redo_message(
    target_agent: str,
    original_reply: str,
    review: ReviewResult,
) -> str:
    """Build a redo instruction message to send back to the original agent."""
    issues_text = "\n".join(f"  {i+1}. {issue}" for i, issue in enumerate(review.issues))
    return (
        f">>REDO>> @{target_agent}\n"
        f"你刚才的回复存在以下问题：\n"
        f"{issues_text}\n\n"
        f"原始回复摘要：{review.summary}\n\n"
        f"请重新回答，注意纠正以上问题。\n"
        f">>END_REDO>>"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_message_router.py::TestBuildRedoMessage -v`
Expected: 2 PASS

- [ ] **Step 5: Run all message_router tests to check no regressions**

Run: `pytest tests/test_message_router.py tests/test_chat_routing.py -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/message_router.py tests/test_message_router.py
git commit -m "feat: add build_redo_message helper to MessageRouter"
```

---

### Task 4: Rewrite Topic Agent system prompt

**Files:**
- Modify: `app/agents/definitions.py`

- [ ] **Step 1: Replace Topic Agent definition with Supervisor prompt**

In `app/agents/definitions.py`, replace the Topic Agent entry (lines 5-17) in DEFAULT_AGENTS:

```python
DEFAULT_AGENTS = [
    {
        "name": "Topic Agent",
        "role": "assistant",
        "system_prompt": (
            "你是 Research Map 的 Topic Agent，担任 Agent Team 的监督者（Supervisor）。\n"
            "\n"
            "## 你的核心职责\n"
            "\n"
            "1. **直接回答**：当用户没有指定 Agent 时，你直接回答用户问题。\n"
            "2. **智能分发**：判断任务是否更适合其他 Agent 处理，如果是则分发。\n"
            "3. **审查回复**：审查所有其他 Agent 的回复，输出结构化审查卡片。\n"
            "4. **纠正指导**：发现问题时给出具体纠正指令，触发重做。\n"
            "\n"
            "## 分发能力\n"
            "\n"
            "你可以调用以下 Agent：\n"
            "- @Paper Agent：论文检索、阅读、分析\n"
            "- @Transfer Agent：算法迁移判断、实验想法生成\n"
            "- @Memory Agent：记忆管理、负面经验查询\n"
            "\n"
            "分发时使用格式：\n"
            ">>DISPATCH>> @Agent名称\n"
            "具体任务描述\n"
            ">>END_DISPATCH>>\n"
            "\n"
            "## 审查输出格式\n"
            "\n"
            "每次审查其他 Agent 的回复时，必须在你的回复开头输出审查卡片：\n"
            "\n"
            "[REVIEW]\n"
            "summary: <1-2句摘要>\n"
            "correctness: pass | partial | fail\n"
            "score: 1-5\n"
            "issues:\n"
            "  - <具体问题1，无则写 none>\n"
            "  - <具体问题2>\n"
            "action: accept | redo | supplement\n"
            "[/REVIEW]\n"
            "\n"
            "- correctness=pass → action=accept，直接展示\n"
            "- correctness=partial → action=supplement 或 redo\n"
            "- correctness=fail → action=redo，给出纠正指令\n"
            "\n"
            "## 重做指令格式\n"
            "\n"
            "当需要其他 Agent 重做时：\n"
            ">>REDO>> @Agent名称\n"
            "你刚才的回复存在以下问题：\n"
            "1. <具体问题>\n"
            "2. <具体问题>\n"
            "请重新回答，注意：<改进方向>\n"
            ">>END_REDO>>\n"
            "\n"
            "## 原则\n"
            "- 审查必须具体，不能只说\"不对\"，必须指出哪里不对\n"
            "- 重做最多 3 次，超过后你直接给出正确回答\n"
            "- 对用户的最终回复中，去掉内部 DISPATCH/REDO 指令，只保留自然语言\n"
        ),
        "description": "Agent Team 监督者，负责分发任务、审查回复和纠正指导",
        "model": "",
        "color": "#07C160",
        "enabled": True,
    },
    # ... Paper Agent, Transfer Agent, Memory Agent remain unchanged
```

- [ ] **Step 2: Verify tests still pass**

Run: `pytest tests/test_topic_builder.py -v`
Expected: PASS (TopicBuilder does not depend on agent definitions)

- [ ] **Step 3: Commit**

```bash
git add app/agents/definitions.py
git commit -m "feat: rewrite Topic Agent system prompt as Supervisor"
```

---

### Task 5: Refactor SessionWorker with review pipeline

**Files:**
- Modify: `app/ui/worker.py`

This is the core change. The `SessionWorker.run()` method gets refactored to support the dispatch→review→redo loop.

- [ ] **Step 1: Add helper methods to SessionWorker**

In `app/ui/worker.py`, add to the `SessionWorker` class before `run()`:

```python
MAX_REDO_ROUNDS = 3

def _call_agent_llm(self, agent_name: str, system_prompt: str, user_prompt: str, agent_model: str = "") -> str:
    """Call LLM for a specific agent and return the reply text."""
    from app.services.llm import LLMService
    llm = LLMService()
    if agent_model:
        llm.model = agent_model
    try:
        return llm.call_simple(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as e:
        return f"抱歉，调用大模型时出错：{e}"

def _save_message(self, engine, session_id: str, role: str, content: str,
                  agent_name: str = "", review_status: str | None = None,
                  review_score: int | None = None, review_summary: str | None = None,
                  redo_count: int = 0) -> str:
    """Save a message to DB and return its ID."""
    from app.models.chat_message import ChatMessage
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

def _run_review(self, engine, session_id: str, target_agent_name: str,
                target_reply: str, redo_count: int) -> tuple[str, bool]:
    """Run Topic Agent review on target_reply.
    Returns (review_message, should_redo).
    should_redo=True means review found issues and redo is needed.
    """
    from app.services.message_router import parse_review_card

    # Call Topic Agent to review
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
        # LLM call failed — pass through
        return f"[审查跳过 — LLM 调用失败] {target_agent_name} 的回复未审查", False

    review = parse_review_card(review_text)
    if review is None:
        # No valid review card — Topic Agent chose to reply directly
        return review_text, False

    # Save review as a ChatMessage
    self._save_message(
        engine, session_id, role="assistant",
        content=review_text, agent_name="Topic Agent",
        review_status=review.correctness if review.correctness == "pass" else "failed",
        review_score=review.score,
        review_summary=review.summary,
    )

    # Update the target's message with review status
    with Session(engine) as db:
        from app.services.message_router import MessageRouter
        from sqlmodel import select
        from app.models.chat_message import ChatMessage
        target_msg = db.exec(
            select(ChatMessage)
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
        return review_text, True
    else:
        return review_text, False

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
```

- [ ] **Step 2: Rewrite SessionWorker.run()**

Replace the current `run()` method (lines 42-144) with the pipeline version:

```python
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
            # No @mention → Topic Agent handles by default
            agents = router.resolve_agents([])

    if not agents:
        self.done.emit(self._session_id, "System")
        return

    # 2. Build chat history once
    with Session(engine) as db:
        from sqlmodel import select
        from app.models.chat_message import ChatMessage
        history = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == self._session_id)
            .order_by(ChatMessage.created_at.asc())
        ).all()

    def _build_user_prompt(target_name: str) -> str:
        """Build user prompt with chat history, scoped to a specific agent."""
        lines = []
        for msg in history[-20:]:
            if msg.role == "assistant":
                lines.append(f"{msg.agent_name or 'Assistant'}: {msg.content}")
            else:
                lines.append(f"User: {msg.content}")
        return "\n".join(lines)

    last_agent_name = agents[0].name if agents else "System"

    # 3. Process each target agent
    for routed in agents:
        if self._cancel_current:
            break

        agent_name = routed.name
        agent_model = routed.model

        with Session(engine) as db:
            router2 = MessageRouter(db)
            system_prompt = router2.build_system_prompt(routed)

        user_prompt = _build_user_prompt(agent_name)

        # 3a. Call the target agent
        reply = self._call_agent_llm(agent_name, system_prompt, user_prompt, agent_model)

        if self._cancel_current:
            break

        # 3b. Save the agent's reply
        self._save_message(engine, self._session_id, role="assistant",
                           content=reply, agent_name=agent_name)

        last_agent_name = agent_name

        # 3c. If target is NOT Topic Agent, run review
        if agent_name != "Topic Agent":
            redo_count = 0
            current_reply = reply

            while redo_count <= self.MAX_REDO_ROUNDS:
                if self._cancel_current:
                    break

                review_text, should_redo = self._run_review(
                    engine, self._session_id, agent_name,
                    current_reply, redo_count,
                )

                if not should_redo:
                    break

                # Build redo message and send to original agent
                from app.services.message_router import parse_review_card
                review = parse_review_card(review_text)
                redo_count += 1
                redo_prompt = (
                    f"## 你的上一轮回复被 Topic Agent 审查为不通过\n\n"
                    f"审查反馈：{review.summary if review else '请改进'}\n\n"
                    f"请根据反馈重新回答用户的原始问题：\n{user_prompt}"
                )
                current_reply = self._call_agent_llm(
                    agent_name, system_prompt, redo_prompt, agent_model,
                )
                if self._cancel_current:
                    break
                self._save_message(
                    engine, self._session_id, role="assistant",
                    content=current_reply, agent_name=agent_name,
                    redo_count=redo_count,
                )
                last_agent_name = agent_name

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
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `pytest tests/test_session_worker.py -v`
Expected: PASS or minor adjustment needed for the new run() behavior

- [ ] **Step 4: Commit**

```bash
git add app/ui/worker.py
git commit -m "feat: refactor SessionWorker with dispatch-review-redo pipeline"
```

---

### Task 6: Style review card messages in ChatView

**Files:**
- Modify: `app/ui/chat_view.py`

- [ ] **Step 1: Add review card rendering to _MessageBubble**

In `app/ui/chat_view.py`, modify the `_MessageBubble.__init__` to detect review card messages and style them differently. Add after the existing `_make_system` / `_make_bubble` split (around line 40):

```python
class _MessageBubble(QFrame):
    def __init__(self, role, content, agent_name="", review_status=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)

        if role == "system":
            self._make_system(content)
        elif review_status:
            self._make_review_card(content, agent_name, review_status)
        else:
            self._make_bubble(role, content, agent_name)

    def _make_review_card(self, content, agent_name, review_status):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        avatar = QLabel("T")
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_color = "#07C160" if review_status == "passed" else "#FF5252"
        avatar.setStyleSheet(
            f"background:{status_color};color:white;"
            f"border-radius:14px;font-size:12px;font-weight:bold;"
        )

        status_text = "审查通过" if review_status == "passed" else "审查不通过"
        review_label = QLabel(f"{agent_name} [{status_text}]")
        review_label.setStyleSheet(f"color:{status_color};font-size:11px;font-weight:bold;")

        body = QLabel(content)
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:12px;padding:4px 0;")

        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(review_label)
        col.addWidget(body)

        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(col)
        layout.addStretch()
```

- [ ] **Step 2: Update _MessageBubble instantiation in _refresh**

In `ChatView._refresh()`, pass review_status when creating message bubbles. Find the line (approximately line 394):

```python
self.msg_layout.addWidget(
    _MessageBubble(msg.role, msg.content, msg.agent_name)
)
```

Replace with:

```python
self.msg_layout.addWidget(
    _MessageBubble(
        msg.role, msg.content, msg.agent_name,
        review_status=msg.review_status,
    )
)
```

- [ ] **Step 3: Verify the app launches without import errors**

Run: `python -c "from app.ui.chat_view import ChatView; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add app/ui/chat_view.py
git commit -m "feat: add review card styling to ChatView messages"
```

---

### Task 7: Integration test and smoke test

**Files:**
- Modify: `tests/test_session_worker.py`

- [ ] **Step 1: Add integration test for review pipeline**

Append to `tests/test_session_worker.py`:

```python
class TestReviewPipeline:
    """Integration tests for the dispatch→review→redo pipeline."""

    def test_review_card_detected_on_non_topic_reply(self):
        """When a non-Topic agent replies, parse_review_card should be called."""
        from app.services.message_router import parse_review_card
        # Simulate a Topic Agent review of Paper Agent's reply
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
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_session_worker.py
git commit -m "test: add integration tests for review pipeline"
```

---

## Summary

7 tasks, each producing a commit. Task order is dependency-aware:
1. Model fields (foundation for all other changes)
2. ReviewResult + parser (no dependencies)
3. build_redo_message (depends on Task 2)
4. Topic Agent prompt (no dependencies)
5. SessionWorker pipeline (depends on Tasks 1-4)
6. ChatView styling (depends on Task 1, independent of Task 5)
7. Integration tests (depends on all above)
