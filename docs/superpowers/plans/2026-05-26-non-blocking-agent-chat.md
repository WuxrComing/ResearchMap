# Non-Blocking Agent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agent chat non-blocking — users can freely operate the app while agents think, with per-session message queuing and cancellation.

**Architecture:** Replace one-shot ChatWorker with SessionWorker that processes a single message and signals completion. ChatView chains workers via per-session deques. UI never blocks: input stays enabled, sidebar stays enabled, new messages queue up. Cooperative cancellation via flag check.

**Tech Stack:** PyQt6 QThread, deque, existing LLMService/MessageRouter/Storage

---

## File Structure

| File | Responsibility |
|------|---------------|
| `app/ui/worker.py` | `QueuedMessage` dataclass, `SessionWorker(QThread)`, keep `TopicBuildWorker` |
| `app/ui/chat_view.py` | Per-session message queue, status indicator widget, cancel button, worker chaining |
| `app/ui/main_window.py` | Remove sidebar blocking during topic build |

---

### Task 1: Add `QueuedMessage` and `SessionWorker` to worker.py

**Files:**
- Modify: `app/ui/worker.py`

- [ ] **Step 1: Add `QueuedMessage` dataclass and `SessionWorker` class**

Add at the top of `app/ui/worker.py`, after existing imports:

```python
import uuid
from collections import deque
from dataclasses import dataclass, field
from PyQt6.QtCore import QThread, pyqtSignal
from sqlmodel import Session, select
from app.services.storage import get_engine
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from app.agents.topic_builder import TopicBuilder


@dataclass
class QueuedMessage:
    """A message waiting in a session's processing queue."""
    content: str
    mentioned_agents: list[str] = field(default_factory=list)
    status: str = "queued"  # "queued" | "thinking" | "done" | "cancelled"
    db_msg_id: str = ""


class SessionWorker(QThread):
    """Processes a single chat message via LLM, then signals done.
    Designed to be chained: ChatView creates a new one for each queued message."""

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

    def run(self):
        if self._cancel_current:
            self.done.emit(self._session_id, "")
            return

        self._qm.status = "thinking"
        self.thinking.emit(self._session_id)

        engine = get_engine()

        # Resolve agents via MessageRouter
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

        # Process each agent (for @multi-mention, one message spawns N replies)
        for routed in agents:
            if self._cancel_current:
                break
            agent_name = routed.name
            system_prompt = ""
            agent_model = routed.model

            with Session(engine) as db:
                router2 = MessageRouter(db)
                system_prompt = router2.build_system_prompt(routed)

            # Load chat history
            with Session(engine) as db:
                history = db.exec(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == self._session_id)
                    .order_by(ChatMessage.created_at.asc())
                ).all()

            messages = [{"role": "system", "content": system_prompt}]
            for msg in history[-20:]:
                if msg.role == "assistant":
                    label = f"{msg.agent_name}: " if msg.agent_name else ""
                    messages.append({
                        "role": "assistant",
                        "content": f"{label}{msg.content}",
                        "agent_name": msg.agent_name or "Assistant",
                    })
                else:
                    messages.append({"role": "user", "content": msg.content})

            try:
                from app.services.llm import LLMService
                llm = LLMService()
                if agent_model:
                    llm.model = agent_model
                reply = llm.call_simple(
                    system_prompt=messages[0]["content"],
                    user_prompt="\n".join(
                        f"{m.get('agent_name', 'Assistant')}: {m['content']}"
                        if m['role'] == 'assistant' else f"User: {m['content']}"
                        for m in messages[1:]
                    ),
                )
                if reply.startswith("LLM Error:"):
                    reply = f"抱歉，大模型调用失败：{reply}"
            except Exception as e:
                reply = f"抱歉，调用大模型时出错：{e}"

            if self._cancel_current:
                break

            # Write assistant reply to DB
            with Session(engine) as db:
                msg = ChatMessage(
                    id=uuid.uuid4().hex,
                    session_id=self._session_id,
                    role="assistant",
                    content=reply,
                    agent_name=agent_name,
                )
                db.add(msg)
                db.commit()

            # Write cancellation notice if needed
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
        self.done.emit(self._session_id, agents[0].name if agents else "System")
```

- [ ] **Step 2: Remove old `ChatWorker` class**

Delete the entire `ChatWorker` class (lines 84-165 in the original file). Keep `TopicBuildWorker` unchanged.

- [ ] **Step 3: Run existing tests to verify nothing is broken**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add app/ui/worker.py
git commit -m "feat: add SessionWorker with QueuedMessage and cancellation support"
```

---

### Task 2: Update chat_view.py — queue, non-blocking UI, status indicators

**Files:**
- Modify: `app/ui/chat_view.py`

- [ ] **Step 1: Add queue and worker tracking to `ChatView.__init__`**

In `__init__`, after `self._active_workers: list = []` (line 234), add:

```python
        self._active_workers: list = []
        self._session_queues: dict = {}   # session_id → deque[QueuedMessage]
        self._session_worker_busy: dict = {}  # session_id → bool
        self._status_widgets: dict = {}   # queued_message db_msg_id → _StatusWidget
```

- [ ] **Step 2: Create `_StatusWidget` inner class at top of chat_view.py**

Add before the `ChatView` class (after `_MessageBubble`):

```python
class _StatusWidget(QFrame):
    """Shows agent thinking/queued status below a user message."""
    cancel_clicked = pyqtSignal()

    def __init__(self, agent_names: list[str], status: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._agent_names = agent_names
        self._status = status

        layout = QHBoxLayout(self)
        layout.setContentsMargins(56, 2, 12, 4)
        layout.setSpacing(8)

        if status == "thinking":
            text = "  ".join(f"⏳ {name} 思考中..." for name in agent_names)
        elif status == "queued":
            text = f"⏱ 排队中（{agent_names[0]}）"
        else:
            text = ""

        self._label = QLabel(text)
        self._label.setStyleSheet("color:#8A9890; font-style:italic; font-size:12px; background:transparent;")
        layout.addWidget(self._label)

        if status == "thinking":
            self._cancel_btn = QPushButton("✕ 取消")
            self._cancel_btn.setFixedHeight(20)
            self._cancel_btn.setStyleSheet(
                "QPushButton { color:#8A9890; background:transparent; border:none; "
                "font-size:11px; padding:0 4px; }"
                "QPushButton:hover { color:#FF5252; }"
            )
            self._cancel_btn.clicked.connect(self.cancel_clicked.emit)
            layout.addWidget(self._cancel_btn)
        else:
            self._cancel_btn = None

        layout.addStretch()

    def update_status(self, status: str, agent_names: list[str] = None):
        if agent_names:
            self._agent_names = agent_names
        self._status = status
        if status == "thinking":
            self._label.setText("  ".join(f"⏳ {name} 思考中..." for name in self._agent_names))
        elif status == "queued":
            self._label.setText(f"⏱ {agent_names[0] if agent_names else '排队中...'}")
        elif status == "done":
            self._label.setText("✓ 已完成")
```

- [ ] **Step 3: Rewrite `_send_message` to use queue**

Replace the existing `_send_message` method (lines 333-362):

```python
    def _send_message(self):
        content = self.input_edit.text().strip()
        if not content or not self._session_id:
            return

        sid = self._session_id
        engine = get_engine()

        # Parse @mentions
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            router = MessageRouter(db)
            mentioned = router.parse_mentions(content)

        # Write user message to DB immediately
        db_msg_id = uuid.uuid4().hex
        with Session(engine) as db:
            db.add(ChatMessage(id=db_msg_id, session_id=sid,
                               role="user", content=content))
            db.commit()

        self.input_edit.clear()

        # Reset auto-collaboration state for this user-initiated interaction
        self._auto_collab_round = 0
        self._called_agents = set()

        self._refresh()

        # Create queued message
        from app.ui.worker import QueuedMessage, SessionWorker
        qm = QueuedMessage(
            content=content,
            mentioned_agents=mentioned,
            status="queued",
            db_msg_id=db_msg_id,
        )

        # Initialize queue for this session if needed
        if sid not in self._session_queues:
            self._session_queues[sid] = deque()
        self._session_queues[sid].append(qm)

        # If worker is not busy for this session, start processing
        if sid not in self._session_worker_busy or not self._session_worker_busy[sid]:
            self._process_next_in_queue(sid)
        else:
            # Show queued status
            agent_names = mentioned or ["Agent"]
            self._add_status_widget(qm, "queued", agent_names)
```

- [ ] **Step 4: Add `_process_next_in_queue` method**

```python
    def _process_next_in_queue(self, session_id: str):
        """Start a SessionWorker for the next message in the session's queue."""
        queue = self._session_queues.get(session_id)
        if not queue:
            self._session_worker_busy[session_id] = False
            return

        qm = queue.popleft()
        if qm.status == "cancelled":
            self._process_next_in_queue(session_id)
            return

        self._session_worker_busy[session_id] = True

        # Resolve agents to get display names
        engine = get_engine()
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            router = MessageRouter(db)
            if qm.mentioned_agents:
                agents = router.resolve_agents(qm.mentioned_agents)
            else:
                agents = router.resolve_agents([])
        agent_names = [a.name for a in agents] if agents else ["Agent"]

        # Show thinking status
        self._add_status_widget(qm, "thinking", agent_names)

        worker = SessionWorker(session_id, qm)
        worker.thinking.connect(lambda sid: self._on_thinking(sid, qm))
        worker.done.connect(lambda sid, an: self._on_session_worker_done(sid, an, qm))
        self._active_workers.append(worker)
        worker.start()
```

- [ ] **Step 5: Add status widget management methods**

```python
    def _add_status_widget(self, qm: "QueuedMessage", status: str, agent_names: list[str]):
        """Add or update a status indicator in the chat view."""
        from app.ui.worker import QueuedMessage

        # Remove existing status widget for this message if any
        if qm.db_msg_id in self._status_widgets:
            existing = self._status_widgets[qm.db_msg_id]
            existing.update_status(status, agent_names)
            return

        widget = _StatusWidget(agent_names, status)
        widget.cancel_clicked.connect(lambda: self._cancel_message(qm))
        self._status_widgets[qm.db_msg_id] = widget
        # Insert after the last stretch
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, widget)

    def _remove_status_widget(self, qm: "QueuedMessage"):
        """Remove status indicator for a completed/cancelled message."""
        if qm.db_msg_id in self._status_widgets:
            widget = self._status_widgets.pop(qm.db_msg_id)
            widget.deleteLater()

    def _cancel_message(self, qm: "QueuedMessage"):
        """Cancel a queued or in-progress message."""
        qm.status = "cancelled"
        # Find and cancel the worker processing this message
        for w in self._active_workers:
            if hasattr(w, '_qm') and w._qm is qm:
                w.cancel()
                break
        self._remove_status_widget(qm)
```

- [ ] **Step 6: Add `_on_thinking` and `_on_session_worker_done` handlers**

```python
    def _on_thinking(self, session_id: str, qm: "QueuedMessage"):
        """Called when a worker starts processing. Status widget already added by _process_next_in_queue."""
        qm.status = "thinking"
        # No _refresh() — it would destroy the status widget just added.

    def _on_session_worker_done(self, session_id: str, agent_name: str, qm: "QueuedMessage"):
        """Called when a worker finishes processing a message."""
        # Clean up worker reference
        for w in list(self._active_workers):
            if hasattr(w, '_qm') and w._qm is qm:
                self._active_workers.remove(w)
                break

        self._remove_status_widget(qm)

        if session_id == self._session_id:
            self._refresh()

        # Process next in queue
        self._process_next_in_queue(session_id)

        # Auto-collaboration check
        if self._auto_collab_enabled and self._auto_collab_round < 3 and qm.status != "cancelled":
            self._check_auto_collab(session_id, agent_name)
```

- [ ] **Step 7: Remove old blocking code**

Delete these methods (replaced by the above):
- `_on_agent_done` (lines 364-378)
- `_dispatch_workers` (lines 380-396)

Remove the `_collab_toggle` and related auto-collaboration wiring from `__init__` (lines 150-160) — keep the toggle but re-wire to work with the new flow. Actually, keep the toggle UI but update `_check_auto_collab` to work with the queue system.

In `_check_auto_collab` (lines 398-427), update to use the new queue mechanism instead of directly calling `_dispatch_workers`:

```python
    def _check_auto_collab(self, session_id: str, agent_name: str):
        """Check the latest reply from agent_name for @mentions to other agents."""
        engine = get_engine()
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            msg = db.exec(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.agent_name == agent_name,
                )
                .order_by(ChatMessage.created_at.desc())
            ).first()
            if not msg:
                return

            router = MessageRouter(db)
            mentions = router.parse_mentions(msg.content)
            new_mentions = [m for m in mentions if m not in self._called_agents]

            if new_mentions:
                self._auto_collab_round += 1
                for name in new_mentions:
                    self._called_agents.add(name)
                db.add(ChatMessage(
                    id=uuid.uuid4().hex,
                    session_id=session_id,
                    role="system",
                    content=f"[自动协作 第{self._auto_collab_round}轮] {agent_name} 调用了 {', '.join(f'@{n}' for n in new_mentions)}",
                ))
                db.commit()
                # Queue a new message for the mentioned agents
                from app.ui.worker import QueuedMessage
                qm = QueuedMessage(
                    content=msg.content,
                    mentioned_agents=new_mentions,
                    status="queued",
                    db_msg_id=uuid.uuid4().hex,
                )
                if session_id not in self._session_queues:
                    self._session_queues[session_id] = deque()
                self._session_queues[session_id].append(qm)
```

- [ ] **Step 8: Run tests**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v
```

- [ ] **Step 9: Commit**

```bash
git add app/ui/chat_view.py
git commit -m "feat: add per-session message queue, status indicators, non-blocking chat"
```

---

### Task 3: Remove sidebar blocking in main_window.py

**Files:**
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: Remove `setEnabled` calls in `_on_build_requested`**

In `_on_build_requested` (lines 110-125), remove the two `setEnabled` calls:

```python
    def _on_build_requested(self, workspace_id, workspace_title, session_id):
        # REMOVED: self.workspace_list.setEnabled(False)
        Toast(self, "正在生成", f"正在为「{workspace_title}」生成思维导图...")

        worker = self.workspace_list.get_build_worker(workspace_id, workspace_title, session_id)
        if worker:
            def on_finished(wid, wtitle, nc, ec, errs):
                # REMOVED: self.workspace_list.setEnabled(True)
                if errs:
                    Toast(self, "生成失败", "; ".join(errs), is_error=True)
                else:
                    Toast(self, "生成完成", f"{nc} 个节点, {ec} 条连接")
                self.mind_map_tree.load_workspace(workspace_id)
                self.chat_view.load_session_by_workspace(workspace_id)
            worker.finished.connect(on_finished)
            worker.start()
```

- [ ] **Step 2: Run the app to verify sidebar is usable during topic build**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m app.main
```

Manual verification: create a new workspace, verify you can click other workspaces in the sidebar while the mind map is building.

- [ ] **Step 3: Run tests**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add app/ui/main_window.py
git commit -m "fix: remove sidebar blocking during topic building"
```

---

### Task 4: Write tests for SessionWorker and queue logic

**Files:**
- Create: `tests/test_session_worker.py`

- [ ] **Step 1: Write the test file**

```python
import pytest
from collections import deque
from unittest.mock import patch, MagicMock
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


class TestSessionWorkerCancel:
    def test_cancel_sets_flag_and_status(self):
        qm = QueuedMessage(content="test")
        worker = SessionWorker("sess_1", qm)
        assert worker._cancel_current is False

        worker.cancel()
        assert worker._cancel_current is True
        assert qm.status == "cancelled"

    def test_cancelled_worker_emits_done_without_llm_call(self, qtbot):
        qm = QueuedMessage(content="test")
        worker = SessionWorker("sess_1", qm)
        worker.cancel()

        with qtbot.waitSignal(worker.done, timeout=1000) as blocker:
            worker.start()

        assert blocker.signal_triggered
        assert qm.status == "cancelled"


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
```

- [ ] **Step 2: Run the new tests**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/test_session_worker.py -v
```

- [ ] **Step 3: Run all tests to confirm no regressions**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_session_worker.py
git commit -m "test: add SessionWorker and queue logic tests"
```
