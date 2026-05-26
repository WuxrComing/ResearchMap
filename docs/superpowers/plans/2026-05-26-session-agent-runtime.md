# Session Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the serial `SessionWorker` collaboration pipeline with a session-scoped multi-agent runtime that dispatches by natural `@AgentName`, runs different agents concurrently, freezes context at task enqueue time, and renders every saved message immediately.

**Architecture:** Add a service-layer runtime under `app/services/agent_runtime.py` with `SessionRuntimeManager`, `SessionRuntime`, deterministic `Dispatcher`, and per-agent `AgentWorker` queues. Persist task lineage on `ChatMessage` so review/redo/cancellation can be routed after message save. Update `ChatView` to submit saved user messages to the runtime and refresh on `message_saved`.

**Tech Stack:** Python 3.13, PyQt6 `QObject`/`QThread`/signals, SQLModel, SQLite, pytest, existing `LLMService`, existing `MessageRouter`.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-05-26-session-agent-runtime-design.md`
- Current serial pipeline: `app/ui/worker.py`
- Current chat UI queue: `app/ui/chat_view.py`
- Routing helpers: `app/services/message_router.py`
- Message model: `app/models/chat_message.py`
- Storage migrations: `app/services/storage.py`

## File Structure

Create:

- `app/services/agent_runtime.py`  
  Owns task dataclasses, mention segment parsing, context snapshot building, `AgentDispatcher`, `AgentWorker`, `SessionRuntime`, and `SessionRuntimeManager`.

- `tests/test_agent_runtime_dispatcher.py`  
  Unit tests for natural `@mention` routing, segmentation, task lineage, review/redo handling, loop prevention, cancellation gates, and system-message ignores.

- `tests/test_agent_runtime_worker.py`  
  Tests for worker prompt construction, FIFO execution, cancellation checks, message saving metadata, and fake LLM execution.

- `tests/test_agent_runtime_manager.py`  
  Tests for session-scoped runtime creation, lazy worker start, cross-agent parallelism contract where feasible, runtime close policy, and signal emission behavior.

Modify:

- `app/models/chat_message.py`  
  Add persisted task lineage fields: `task_id`, `task_type`, `root_user_message_id`, `trigger_message_id`, `target_message_id`, `dispatch_depth`.

- `app/services/storage.py`  
  Add migration for the new `chat_messages` metadata columns.

- `app/services/message_router.py`  
  Remove `DispatchRequest` and `parse_dispatch_blocks`. Keep `ReviewResult`, `parse_review_card`, `build_redo_message`, `RoutedAgent`, and `MessageRouter`.

- `app/agents/definitions.py`  
  Update Topic Agent prompt to use natural `@AgentName` group-chat dispatch only. Remove `>>DISPATCH>>` instructions.

- `app/ui/chat_view.py`  
  Replace old queue/session-worker flow with `SessionRuntimeManager` submission, `message_saved` refresh, structured status updates, and cancellation by root user message.

- `app/ui/worker.py`  
  Remove or stop using `SessionWorker` for chat. Keep `TopicBuildWorker` in this file unless a later cleanup extracts it.

- Existing tests under `tests/test_session_worker.py`, `tests/test_message_router.py`, and `tests/test_chat_routing.py`  
  Remove or rewrite expectations for `>>DISPATCH>>` and serial worker behavior.

---

## Task 1: Persist Task Lineage on `ChatMessage`

**Files:**
- Modify: `app/models/chat_message.py`
- Modify: `app/services/storage.py`
- Test: `tests/test_models.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing model test**

Add a test to `tests/test_models.py`:

```python
def test_chat_message_accepts_runtime_lineage_fields():
    from app.models.chat_message import ChatMessage

    msg = ChatMessage(
        session_id="sess",
        role="assistant",
        content="reply",
        agent_name="Paper Agent",
        task_id="task_1",
        task_type="dispatch",
        root_user_message_id="root_1",
        trigger_message_id="trigger_1",
        target_message_id=None,
        dispatch_depth=2,
    )

    assert msg.task_id == "task_1"
    assert msg.task_type == "dispatch"
    assert msg.root_user_message_id == "root_1"
    assert msg.trigger_message_id == "trigger_1"
    assert msg.target_message_id is None
    assert msg.dispatch_depth == 2
```

- [ ] **Step 2: Run model test and verify it fails**

Run: `pytest tests/test_models.py::test_chat_message_accepts_runtime_lineage_fields -v`

Expected: FAIL because `ChatMessage` has no lineage fields.

- [ ] **Step 3: Add lineage fields to `ChatMessage`**

In `app/models/chat_message.py`, add:

```python
    task_id: str | None = Field(default=None, index=True)
    task_type: str | None = Field(default=None, index=True)
    root_user_message_id: str | None = Field(default=None, index=True)
    trigger_message_id: str | None = Field(default=None)
    target_message_id: str | None = Field(default=None, index=True)
    dispatch_depth: int = Field(default=0)
```

- [ ] **Step 4: Run model test and verify it passes**

Run: `pytest tests/test_models.py::test_chat_message_accepts_runtime_lineage_fields -v`

Expected: PASS.

- [ ] **Step 5: Write failing storage migration test**

In `tests/test_storage.py`, add a test that calls `init_db()` and checks `PRAGMA table_info('chat_messages')` includes:

```python
{
    "task_id",
    "task_type",
    "root_user_message_id",
    "trigger_message_id",
    "target_message_id",
    "dispatch_depth",
}
```

- [ ] **Step 6: Run storage test and verify it fails**

Run: `pytest tests/test_storage.py::test_chat_message_runtime_lineage_columns_exist -v`

Expected: FAIL until migration is added.

- [ ] **Step 7: Add storage migration**

In `app/services/storage.py`, add `_migrate_chat_message_runtime_metadata(engine)` and call it from `init_db()` after table creation.

Use `PRAGMA table_info('chat_messages')`; for each missing column, run `ALTER TABLE`.

Column SQL:

```sql
ALTER TABLE chat_messages ADD COLUMN task_id TEXT;
ALTER TABLE chat_messages ADD COLUMN task_type TEXT;
ALTER TABLE chat_messages ADD COLUMN root_user_message_id TEXT;
ALTER TABLE chat_messages ADD COLUMN trigger_message_id TEXT;
ALTER TABLE chat_messages ADD COLUMN target_message_id TEXT;
ALTER TABLE chat_messages ADD COLUMN dispatch_depth INTEGER DEFAULT 0;
```

- [ ] **Step 8: Run storage tests**

Run: `pytest tests/test_storage.py tests/test_models.py -v`

Expected: PASS, except unrelated pre-existing failures must be documented if any appear.

- [ ] **Step 9: Commit**

```bash
git add app/models/chat_message.py app/services/storage.py tests/test_models.py tests/test_storage.py
git commit -m "Add chat message runtime metadata"
```

---

## Task 2: Replace Machine Dispatch with Natural Mention Parsing

**Files:**
- Modify: `app/agents/definitions.py`
- Test: `tests/test_message_router.py`
- Test: `tests/test_chat_routing.py`

- [ ] **Step 1: Write prompt test or assertion**

Add/update a test that reads `DEFAULT_AGENTS` and asserts Topic prompt:

```python
assert ">>DISPATCH>>" not in topic_prompt
assert ">>END_DISPATCH>>" not in topic_prompt
assert "@Paper Agent" in topic_prompt
assert "自然语言" in topic_prompt or "直接在群聊中 @" in topic_prompt
```

- [ ] **Step 2: Run prompt test and verify it fails if prompt still references dispatch blocks**

Run the targeted test.

Expected: FAIL until prompt is updated.

- [ ] **Step 3: Update Topic Agent prompt**

In `app/agents/definitions.py`, replace dispatch block instructions with:

```text
当你需要其他 Agent 协助时，直接在群聊中 @对应 Agent，并用自然语言说明任务。
你的 @ 消息就是公开指挥，不要私下调用，不要代替被 @ 的 Agent 回答。
```

Remove all `>>DISPATCH>>` wording from Topic prompt only. Do not delete `parse_dispatch_blocks` yet because the old `SessionWorker` still imports it until Task 9.

- [ ] **Step 4: Run routing and prompt tests**

Run: `pytest tests/test_message_router.py tests/test_chat_routing.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/definitions.py tests/test_message_router.py tests/test_chat_routing.py
git commit -m "Use natural mentions for agent dispatch"
```

---

## Task 3: Add Runtime Dataclasses and Mention Segment Parser

**Files:**
- Create: `app/services/agent_runtime.py`
- Test: `tests/test_agent_runtime_dispatcher.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_agent_runtime_dispatcher.py` with fixtures for enabled agents and tests:

```python
def test_split_topic_mentions_into_agent_instructions(populated_db):
    from app.services.agent_runtime import split_mention_instructions
    from app.services.message_router import MessageRouter

    router = MessageRouter(populated_db)
    result = split_mention_instructions(
        "@Paper Agent 请检索最新论文。\n@Memory Agent 请检查历史经验。",
        router,
        source_agent="Topic Agent",
    )

    assert result == {
        "Paper Agent": "请检索最新论文。",
        "Memory Agent": "请检查历史经验。",
    }
```

Also add tests for:

- text before first mention ignored for instruction
- duplicate same-agent mentions concatenate with blank line
- duplicate same-agent mentions are not lost; both occurrences contribute segments
- unknown/disabled mentions ignored
- `@Topic Agent` ignored inside Topic messages
- mentions in fenced code ignored
- adjacent mentions with no segment text use the full message only when that agent has no non-empty segment elsewhere

Add a lower-level span test:

```python
def test_find_mention_spans_returns_positions_and_duplicates(populated_db):
    from app.services.agent_runtime import find_mention_spans
    from app.services.message_router import MessageRouter

    router = MessageRouter(populated_db)
    spans = find_mention_spans("@Paper Agent first @Paper Agent second", router)

    assert [s.agent_name for s in spans] == ["Paper Agent", "Paper Agent"]
    assert spans[0].start < spans[1].start
```

- [ ] **Step 2: Run parser tests and verify they fail**

Run: `pytest tests/test_agent_runtime_dispatcher.py -v`

Expected: FAIL because `app.services.agent_runtime` does not exist.

- [ ] **Step 3: Add dataclasses and parser shell**

Create `app/services/agent_runtime.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
import re
import uuid

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
```

- [ ] **Step 4: Implement fenced-code stripping and mention segment splitting**

Implement:

```python
@dataclass
class MentionSpan:
    agent_name: str
    start: int
    end: int

def strip_fenced_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text or "", flags=re.DOTALL)

def find_mention_spans(text: str, router) -> list[MentionSpan]:
    ...

def split_mention_instructions(text: str, router, source_agent: str) -> dict[str, str]:
    ...
```

Rules:

- Do not use `router.parse_mentions()` for segmentation; it returns one occurrence per agent and loses positions.
- Build `find_mention_spans()` from enabled agent names and regex positions, preserving duplicate mentions.
- Work from valid mention positions in chronological order.
- Ignore disabled/unknown mentions because only enabled agent names are scanned.
- If `source_agent == "Topic Agent"`, ignore `Topic Agent`.
- Segment instruction from end of mention to start of next valid mention.
- Strip whitespace and leading punctuation like `：:，,`.
- Merge duplicate agent segments with `\n\n`.
- Empty segment does not create a task when that same agent has any non-empty segment.
- If an agent has only empty adjacent-mention segments, use the full source message as that agent's instruction.

- [ ] **Step 5: Run parser tests**

Run: `pytest tests/test_agent_runtime_dispatcher.py -v`

Expected: PASS for parser tests.

- [ ] **Step 6: Commit**

```bash
git add app/services/agent_runtime.py tests/test_agent_runtime_dispatcher.py
git commit -m "Add natural mention instruction parsing"
```

---

## Task 4: Implement Context Snapshot and Dispatcher Task Creation

**Files:**
- Modify: `app/services/agent_runtime.py`
- Test: `tests/test_agent_runtime_dispatcher.py`

- [ ] **Step 1: Write failing context snapshot tests**

Add tests for:

- user message without mention creates one Topic `user_request` task
- user message with `@Paper Agent` creates one Paper `user_request` task
- user message with `@Paper Agent` and `@Memory Agent` creates two `user_request` tasks and no default Topic task
- Topic message with `@Paper Agent` creates Paper `dispatch` task
- non-Topic message creates Topic `review` task
- system message creates no task
- task context includes root, trigger, and target where applicable
- duplicate `handle_message_saved(message_id)` does not enqueue duplicate tasks
- dispatch depth at `MAX_DISPATCH_DEPTH` is allowed, but a child dispatch beyond it is rejected

Example assertion:

```python
tasks = dispatcher.handle_message_saved(user_msg.id)
assert len(tasks) == 1
assert tasks[0].target_agent == "Topic Agent"
assert tasks[0].task_type == "user_request"
assert tasks[0].root_user_message_id == user_msg.id
```

- [ ] **Step 2: Run dispatcher tests and verify they fail**

Run: `pytest tests/test_agent_runtime_dispatcher.py -v`

Expected: FAIL because `AgentDispatcher` is not implemented.

- [ ] **Step 3: Implement `AgentDispatcher` constructor and helpers**

In `app/services/agent_runtime.py`, add:

```python
class AgentDispatcher:
    MAX_DISPATCH_DEPTH = 5
    MAX_REDO_ROUNDS = 3

    def __init__(self, engine, enqueue_task, canceled_roots=None, processed_keys=None):
        self.engine = engine
        self.enqueue_task = enqueue_task
        self.canceled_roots = canceled_roots if canceled_roots is not None else set()
        self.processed_keys = processed_keys if processed_keys is not None else set()
```

Add helpers:

- `_load_message(message_id)`
- `_latest_root_for_message(message)`
- `_build_context_snapshot(session_id, root_id, trigger_id, target_id=None, limit=20)`
- `_make_task(...)`
- `_enqueue_once(task)`
- `_processed_key(task)`
- `_can_enqueue_depth(task)`

- [ ] **Step 4: Implement user and Topic dispatch handling**

Implement:

```python
def handle_message_saved(self, message_id: str) -> list[AgentTask]:
    # load message
    # ignore system
    # cancellation gate
    # route by role/agent_name/task_type
```

For returned tasks, call `self.enqueue_task(task)` and return the created tasks for tests.

Enforce:

- cancellation gate before task creation
- processed-key check before enqueue
- dispatch-depth check before enqueue

- [ ] **Step 5: Implement non-Topic review task handling**

For assistant messages where `agent_name != "Topic Agent"` and `task_type != "review"`, create a Topic `review` task:

```python
instruction = f"请审查 {msg.agent_name} 的目标回复，只输出 [REVIEW]...[/REVIEW] 审查卡片。"
target_message_id = msg.id
```

- [ ] **Step 6: Run dispatcher creation tests**

Run: `pytest tests/test_agent_runtime_dispatcher.py -v`

Expected: PASS for task creation tests.

- [ ] **Step 7: Commit**

```bash
git add app/services/agent_runtime.py tests/test_agent_runtime_dispatcher.py
git commit -m "Add agent dispatcher task creation"
```

---

## Task 5: Implement Review Accept/Redo/Supplement Dispatch

**Files:**
- Modify: `app/services/agent_runtime.py`
- Test: `tests/test_agent_runtime_dispatcher.py`
- Possibly modify: `app/services/message_router.py`

- [ ] **Step 1: Write failing review handling tests**

Add tests:

- Topic review `accept` updates target `review_status = "passed"`, score, summary
- Topic review `redo` creates redo task for original agent
- review task preserves the target message's dispatch depth
- redo task preserves the original task depth and increments redo count
- max redo rounds creates Topic `fallback` task
- Topic review `supplement` with `@Memory Agent` dispatches Memory task
- supplement dispatch increments dispatch depth by one
- supplement dispatch over `MAX_DISPATCH_DEPTH` is rejected
- review message with no `target_message_id` creates no task and writes no target update

- [ ] **Step 2: Run review tests and verify they fail**

Run: `pytest tests/test_agent_runtime_dispatcher.py -v`

Expected: FAIL until review handling exists.

- [ ] **Step 3: Implement Topic review branch**

In `AgentDispatcher.handle_message_saved`, before normal Topic mention dispatch:

```python
if msg.agent_name == "Topic Agent" and msg.task_type == "review":
    return self._handle_topic_review(msg)
```

Use existing `parse_review_card(msg.content)`.

- [ ] **Step 4: Implement accept target update**

Load `target_message_id`; update:

```python
target.review_status = "passed" if review.correctness == "pass" else "failed"
target.review_score = review.score
target.review_summary = review.summary
```

Do not infer target by latest agent message.

- [ ] **Step 5: Implement redo task creation**

If `review.action == "redo"` and target `redo_count < MAX_REDO_ROUNDS`:

- increment target `redo_count`
- create `AgentTask(task_type="redo", target_agent=target.agent_name, target_message_id=target.id, redo_count=target.redo_count)`

- [ ] **Step 6: Implement fallback task creation**

If redo max reached, create Topic `fallback` task with instruction:

```text
子 Agent 多次重做仍未通过审查。请基于群聊上下文直接给出纠正后的回答。
```

- [ ] **Step 7: Implement supplement mention dispatch**

If `review.action == "supplement"`, parse Topic review content for mentions and dispatch to non-Topic agents using segmented instructions.

- [ ] **Step 8: Run review tests**

Run: `pytest tests/test_agent_runtime_dispatcher.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/services/agent_runtime.py tests/test_agent_runtime_dispatcher.py
git commit -m "Add review redo dispatch handling"
```

---

## Task 6: Implement AgentWorker Execution and Message Saving

**Files:**
- Modify: `app/services/agent_runtime.py`
- Test: `tests/test_agent_runtime_worker.py`

- [ ] **Step 1: Write failing prompt construction tests**

Create `tests/test_agent_runtime_worker.py` with a test for:

```python
from app.services.agent_runtime import build_agent_user_prompt, ChatContextMessage, AgentTask
```

Assert prompt contains:

- chronological group chat context
- `User:` line
- `Topic Agent:` line
- `你的任务：`
- task instruction

- [ ] **Step 2: Run test and verify it fails**

Run: `pytest tests/test_agent_runtime_worker.py -v`

Expected: FAIL because prompt builder does not exist.

- [ ] **Step 3: Implement prompt builder**

Add:

```python
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
```

- [ ] **Step 4: Run prompt test**

Run: `pytest tests/test_agent_runtime_worker.py::test_build_agent_user_prompt_includes_context_and_instruction -v`

Expected: PASS.

- [ ] **Step 5: Write failing worker save metadata test**

Use fake LLM callable returning `"Paper reply"`. Create an `AgentTask` and run a synchronous worker helper like:

```python
worker = AgentWorker(..., llm_caller=fake_call, run_threaded=False)
message_id = worker.process_one(task)
```

Assert saved `ChatMessage` has:

- `agent_name`
- `task_id`
- `task_type`
- `root_user_message_id`
- `trigger_message_id`
- `target_message_id`
- `dispatch_depth`

- [ ] **Step 6: Implement `AgentWorker.process_one` synchronous core**

Implement the core execution as a plain method first so tests do not require real threads:

```python
class AgentWorker(QObject):
    message_saved = pyqtSignal(str, str)
    status_changed = pyqtSignal()

    def process_one(self, task: AgentTask) -> str | None:
        ...
```

Rules:

- check cancellation before call
- resolve agent config with `MessageRouter`
- build system prompt
- build user prompt
- call injected `llm_caller` or `LLMService.call_simple`
- check cancellation after call
- save `ChatMessage` under persistence lock
- emit `message_saved`

- [ ] **Step 7: Run worker tests**

Run: `pytest tests/test_agent_runtime_worker.py -v`

Expected: PASS.

- [ ] **Step 8: Add cancellation tests**

Test:

- canceled before call does not call fake LLM and saves nothing
- canceled after call before save discards result

Use a `cancel_checker` injected into worker.

- [ ] **Step 9: Add failing LLM error handling tests**

Add tests for:

- normal agent LLM exception writes one system message with lineage metadata
- system error message emits `message_saved`
- failed normal call returns no assistant message id
- failed Topic review call writes a system message and does not update target review status

- [ ] **Step 10: Implement cancellation checks and LLM error handling**

Add `cancel_checker: Callable[[str], bool]` dependency to worker or runtime.

In `process_one`, wrap LLM call:

```python
try:
    reply = self.llm_caller(...)
except Exception as exc:
    return self._save_system_error(task, exc)
```

System error messages must have `role="system"`, copied lineage fields, and must emit `message_saved`.

- [ ] **Step 11: Run worker tests**

Run: `pytest tests/test_agent_runtime_worker.py -v`

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add app/services/agent_runtime.py tests/test_agent_runtime_worker.py
git commit -m "Add agent worker execution core"
```

---

## Task 7: Implement SessionRuntime and Runtime Manager

**Files:**
- Modify: `app/services/agent_runtime.py`
- Test: `tests/test_agent_runtime_manager.py`

- [ ] **Step 1: Write failing manager tests**

Create `tests/test_agent_runtime_manager.py` with tests:

- `get_runtime(session_id)` returns same runtime for same session
- different sessions get different runtimes
- submitting a user message calls dispatcher
- queued task starts only the target agent worker
- same agent tasks remain FIFO
- `message_saved` emitted after worker saves message
- inactive close does not close runtime with queued or active tasks
- explicit runtime close cancels queued tasks
- explicit runtime close marks active task as cancelling
- late result from active task after close is discarded
- shutdown waits up to a bounded timeout and then releases runtime references

- [ ] **Step 2: Run manager tests and verify they fail**

Run: `pytest tests/test_agent_runtime_manager.py -v`

Expected: FAIL because manager/runtime are not implemented.

- [ ] **Step 3: Implement `SessionRuntimeManager`**

Add:

```python
class SessionRuntimeManager(QObject):
    message_saved = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, list)
    error = pyqtSignal(str, str)

    def __init__(self, engine=None, parent=None):
        ...

    def get_runtime(self, session_id: str) -> SessionRuntime:
        ...

    def submit_message(self, session_id: str, message_id: str):
        self.get_runtime(session_id).on_message_saved(message_id)

    def cancel_root(self, session_id: str, root_user_message_id: str):
        ...

    def shutdown(self):
        ...
```

- [ ] **Step 4: Implement `SessionRuntime` in-memory queues**

Add:

- `self.queues: dict[str, deque[AgentTask]]`
- `self.workers: dict[str, AgentWorker]`
- `self.processed_keys: set[tuple]`
- `self.canceled_roots: set[str]`
- `enqueue_task(task)`
- `on_message_saved(message_id)`
- `cancel_root(root_id)`
- `close(reason)`

- [ ] **Step 5: Implement lazy worker creation**

When `enqueue_task` receives a target agent:

- append to that agent queue
- if no worker exists or worker stopped, create worker
- if worker idle, start/drain queue

For first testable implementation, the queue drain can run synchronously under test through an injectable executor. Threaded start can be added after synchronous tests pass.

- [ ] **Step 6: Add QThread-backed draining**

Implement worker execution in a QThread or keep `AgentWorker` as `QThread` with a queue loop. Keep the synchronous core from Task 6.

Required behavior:

- one worker per agent per session
- worker drains FIFO queue
- emits status updates
- enters idle when queue empty

- [ ] **Step 7: Add idle timeout behavior**

Use `QTimer` or runtime-managed timestamp checks. For tests, make idle timeout configurable and use a small timeout.

- [ ] **Step 8: Run manager tests**

Run: `pytest tests/test_agent_runtime_manager.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/services/agent_runtime.py tests/test_agent_runtime_manager.py
git commit -m "Add session agent runtime manager"
```

---

## Task 8: Wire Runtime into ChatView

**Files:**
- Modify: `app/ui/chat_view.py`
- Modify: `app/ui/main_window.py` if shutdown wiring is needed
- Test: `tests/test_session_worker.py` may be retired/rewritten
- Test: add or update UI tests as feasible

- [ ] **Step 1: Write failing ChatView integration test**

Add a test that creates a `ChatView`, injects a fake runtime manager, sends a user message, and asserts:

- user message is saved immediately
- fake manager receives `submit_message(session_id, user_message_id)`
- no `SessionWorker` is created

If direct widget testing is too brittle, factor `_save_user_message` and `_submit_to_runtime` helpers and test them.

- [ ] **Step 2: Run test and verify it fails**

Run targeted UI test.

Expected: FAIL while `ChatView` still uses `SessionWorker`.

- [ ] **Step 3: Add runtime manager dependency to `ChatView`**

In `ChatView.__init__`, create or accept:

```python
from app.services.agent_runtime import SessionRuntimeManager
self._runtime_manager = runtime_manager or SessionRuntimeManager()
self._runtime_manager.message_saved.connect(self._on_runtime_message_saved)
self._runtime_manager.status_changed.connect(self._on_runtime_status_changed)
```

- [ ] **Step 4: Replace `_send_message` queue path**

New behavior:

```python
db_msg_id = uuid.uuid4().hex
save ChatMessage(
    id=db_msg_id,
    role="user",
    content=content,
    root_user_message_id=db_msg_id,
)
self._refresh()
self._runtime_manager.submit_message(sid, db_msg_id)
```

Remove local parsing of mentions from `_send_message`; dispatcher owns it.

- [ ] **Step 5: Add runtime message refresh handler**

Implement:

```python
def _on_runtime_message_saved(self, session_id: str, message_id: str):
    if session_id == self._session_id:
        self._refresh()
```

- [ ] **Step 6: Replace cancellation path**

Track current root user message ids in status widget metadata. On cancel:

```python
self._runtime_manager.cancel_root(self._session_id, root_user_message_id)
```

First version can cancel the latest submitted root for the active status widget.

- [ ] **Step 7: Remove old queue usage**

Remove or stop using:

- `_session_queues`
- `_session_worker_busy`
- `_active_workers` for chat workers
- `_process_next_in_queue`
- `_on_session_worker_done`
- `_check_auto_collab`

Keep shutdown behavior but route to `self._runtime_manager.shutdown()`.

- [ ] **Step 8: Update status widget integration**

Map `RuntimeStatusEntry` list to `_StatusWidget` labels. If this is too large for first pass, show a simple joined list:

```text
Paper Agent: running
Topic Agent: queued
```

- [ ] **Step 9: Run ChatView/UI tests**

Run:

```bash
pytest tests/test_chat_bubble_layout.py tests/test_session_worker.py -v
```

Expected: existing chat bubble tests pass; obsolete session worker tests should be rewritten or removed as part of this task.

- [ ] **Step 10: Commit**

```bash
git add app/ui/chat_view.py app/ui/main_window.py tests/test_session_worker.py tests/test_chat_bubble_layout.py
git commit -m "Wire chat view to session runtime"
```

---

## Task 9: Remove Serial SessionWorker Chat Pipeline

**Files:**
- Modify: `app/ui/worker.py`
- Modify: tests that import `SessionWorker`
- Test: full targeted suite

- [ ] **Step 1: Identify remaining `SessionWorker` references**

Run: `rg -n "SessionWorker|QueuedMessage|parse_dispatch_blocks|auto_collab|_session_worker_busy|_session_queues" app tests`

Expected: only obsolete references remain.

- [ ] **Step 2: Remove dispatch block API**

In `app/services/message_router.py`, delete:

- `DispatchRequest`
- `parse_dispatch_blocks`

Add/update a test:

```python
def test_message_router_has_no_dispatch_block_parser():
    import app.services.message_router as router_module

    assert not hasattr(router_module, "parse_dispatch_blocks")
```

- [ ] **Step 3: Remove chat `SessionWorker` and `QueuedMessage`**

In `app/ui/worker.py`, delete chat worker code. Keep `TopicBuildWorker`.

If imports need compatibility temporarily, do not leave dead classes that can be accidentally used.

- [ ] **Step 4: Rewrite session worker tests**

Replace `tests/test_session_worker.py` with runtime-focused tests or delete obsolete tests if coverage exists in:

- `tests/test_agent_runtime_dispatcher.py`
- `tests/test_agent_runtime_worker.py`
- `tests/test_agent_runtime_manager.py`

- [ ] **Step 5: Remove dispatch block tests**

Ensure no tests expect `>>DISPATCH>>`.

- [ ] **Step 6: Run reference search again**

Run: `rg -n "SessionWorker|QueuedMessage|parse_dispatch_blocks|>>DISPATCH>>|auto_collab|_session_worker_busy|_session_queues" app tests`

Expected: no production references; only spec/plan references are acceptable if search includes docs.

- [ ] **Step 7: Run targeted suite**

Run:

```bash
pytest tests/test_message_router.py \
       tests/test_chat_routing.py \
       tests/test_agent_runtime_dispatcher.py \
       tests/test_agent_runtime_worker.py \
       tests/test_agent_runtime_manager.py \
       tests/test_chat_bubble_layout.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/services/message_router.py app/ui/worker.py app/ui/chat_view.py tests
git commit -m "Remove serial chat session worker"
```

---

## Task 10: End-to-End Runtime Flow with Fake LLM

**Files:**
- Modify: `tests/test_agent_runtime_manager.py`
- Possibly modify: `app/services/agent_runtime.py`

- [ ] **Step 1: Write failing end-to-end test**

Create a fake LLM sequence:

```python
def fake_llm(agent_name, system_prompt, user_prompt):
    if agent_name == "Topic Agent" and "审查" not in user_prompt:
        return "@Paper Agent 请检索最新论文。"
    if agent_name == "Paper Agent":
        return "Paper Agent 检索结果。"
    if agent_name == "Topic Agent" and "审查" in user_prompt:
        return """[REVIEW]
summary: Paper Agent 已完成检索。
correctness: pass
score: 5
issues:
  - none
action: accept
[/REVIEW]"""
```

Test flow:

1. Save user message.
2. Submit to runtime.
3. Drain runtime until idle.
4. Assert DB messages ordered by created_at:
   - User
   - Topic natural `@Paper Agent`
   - Paper reply
   - Topic review
5. Assert `message_saved` emitted for each assistant message.

- [ ] **Step 2: Run E2E test and verify it fails**

Run: `pytest tests/test_agent_runtime_manager.py::test_user_topic_paper_review_flow_renders_each_message -v`

Expected: FAIL until runtime drains full chain correctly.

- [ ] **Step 3: Add test drain helper**

Add runtime test helper:

```python
runtime.drain_for_tests(max_steps=20)
```

This should process queued tasks deterministically without sleeping.

- [ ] **Step 4: Fix runtime chain until E2E passes**

Ensure:

- Topic message triggers Paper dispatch
- Paper reply triggers Topic review
- review accept updates Paper review metadata
- all assistant messages emit `message_saved`

- [ ] **Step 5: Add parallel-dispatch E2E test**

Topic returns:

```text
@Paper Agent 请检索论文。
@Memory Agent 请检查历史经验。
```

Assert two target workers/queues receive tasks. If true threading is hard to assert deterministically, assert tasks are in distinct agent queues and same-agent FIFO remains intact.

- [ ] **Step 6: Run E2E runtime tests**

Run: `pytest tests/test_agent_runtime_manager.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/agent_runtime.py tests/test_agent_runtime_manager.py
git commit -m "Verify session runtime collaboration flow"
```

---

## Task 11: Full Regression and Cleanup

**Files:**
- All touched files

- [ ] **Step 1: Run full test suite**

Run: `pytest`

Expected: PASS. If existing unrelated `test_topic_builder.py` failures remain, document them and run the full relevant runtime/chat suite separately.

- [ ] **Step 2: Run search for removed protocol**

Run:

```bash
rg -n ">>DISPATCH>>|parse_dispatch_blocks|DispatchRequest|SessionWorker|QueuedMessage|auto_collab|_check_auto_collab" app tests
```

Expected: no matches in production/test code for removed protocol and old chat pipeline. Mentions in docs/spec/plans are acceptable only when describing removal.

- [ ] **Step 3: Manual smoke test**

Start the app using the project’s normal command. In a chat session, send:

```text
帮我检索本领域的最新文献
```

Expected visible sequence:

```text
User bubble
Topic Agent bubble with @Paper Agent natural instruction
Paper Agent bubble with result
Topic Agent review bubble
```

Each bubble should appear as soon as that agent finishes, not all at the end.

- [ ] **Step 4: Manual multi-agent smoke test**

Send:

```text
@Paper Agent 请检索最新论文。
@Memory Agent 请检查历史经验。
```

Expected:

- Paper and Memory tasks can be active at the same time.
- Each reply appears independently.
- Topic reviews each non-Topic reply independently.

- [ ] **Step 5: Manual cancellation smoke test**

Start a long request, click cancel.

Expected:

- queued downstream tasks do not execute
- in-flight result is discarded if cancellation occurs before save
- already saved messages remain visible

- [ ] **Step 6: Commit cleanup**

```bash
git add app tests
git commit -m "Clean up session runtime migration"
```

---

## Execution Notes

- Use TDD for every behavior change. Do not write runtime production code before the failing test exists.
- Keep commits small and task-aligned.
- Prefer synchronous core methods for deterministic tests, then wrap them in Qt threading.
- Do not use live LLM calls in tests. Inject fake LLM callables.
- Do not share SQLModel `Session` objects across threads.
- Do not reintroduce `>>DISPATCH>>`.
- Do not let non-Topic agent mentions trigger dispatch in the first version.
- If SQLite write contention appears, add or tighten the global persistence lock before expanding threaded tests.
