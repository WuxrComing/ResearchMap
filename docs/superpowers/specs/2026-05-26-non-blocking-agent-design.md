# Non-Blocking Agent Chat Design

## Problem

When an agent is thinking (LLM API call with DeepSeek `thinking: enabled` + `reasoning_effort: high`), the UI intentionally blocks all user interaction:

- `main_window.py:111`: `workspace_list.setEnabled(False)` — sidebar disabled during topic building
- `chat_view.py:354`: `input_edit.setEnabled(False)` — input field disabled during chat
- `chat_view.py:337-338`: `if self._pending_workers > 0: return` — new messages rejected

The API call can take 30s to several minutes. User must wait idly.

## Goal

User can operate the app freely at all times: switch sessions/workspaces, browse mind maps, send new messages. Messages queue per session and process sequentially. Ongoing work can be cancelled.

## Design

### Data Model (unchanged)

```
Topic (workspace)
  ├── Session  (FK: workspace_id → topics.id)
  │     └── ChatMessage  (FK: session_id → sessions.id)
  ├── MapNode  (FK: topic_id → topics.id)
  └── MapEdge  (FK: topic_id → topics.id)
```

Worker binds to `session_id` at creation. Switching UI sessions does not affect running workers — each writes to its own session in DB.

### Architecture Change

**Before:** One-shot workers. UI disabled during flight.

**After:** Per-session message queue with persistent worker.

```
User sends message
  → Write ChatMessage(role="user") to DB immediately
  → Push QueuedMessage to _session_queues[session_id]
  → If session has no running worker → start SessionWorker
  → If worker already running → message waits in queue
  → Worker processes, emits status signals, auto-advances to next
```

### Per-Session Message Queue

```python
_session_queues: dict[str, deque[QueuedMessage]]

QueuedMessage:
  content: str
  mentioned_agents: list[str]
  status: "queued" | "thinking" | "done" | "cancelled"
  db_msg_id: str  # ChatMessage.id already written to DB
```

### SessionWorker (replaces ChatWorker + TopicBuildWorker)

Persistent, long-lived worker per session. Loops: pop queue → process → emit → next.

- `thinking(session_id, queued_message_id)` — emitted when processing begins
- `done(session_id, agent_name)` — emitted when reply is written to DB
- `queue_advanced(session_id)` — emitted when worker moves to next queued message
- Cancellation via `_cancel_current` flag (cooperative, not `terminate()`)

Worker exits when its session queue is drained and no new messages arrive within 5 minutes. Timer resets on each new message. Exiting is a resource optimization, not a correctness requirement — a worker that stays alive is harmless.

### Status Indicator UI

Position: below the user message bubble, left-aligned with agent bubbles (56px indent).

```
[我]  @Topic Agent @Paper Agent 帮我分析...
⏳ Topic Agent 思考中...
⏳ Paper Agent 思考中...              [✕ 全部取消]

[我]  上一个问题的补充...
⏱ 排队中（第 2 位）
```

- One line per agent in the current batch
- Single cancel button cancels all agents for that queued message
- Styling: `color: #8A9890; font-style: italic; font-size: 12px`
- Cancelled messages get a system note "用户取消了此请求"

### Cancel Mechanism

Cooperative (not `QThread.terminate()`):

1. User clicks cancel → `QueuedMessage.status = "cancelled"`, `worker._cancel_current = True`
2. Worker finishes LLM call → checks flag → skips DB write → emits done → advances queue
3. System message written: "用户取消了此请求"

### What Gets Removed

- All `setEnabled(False)` / `setEnabled(True)` pairs on UI widgets during agent work
- `if self._pending_workers > 0: return` guard in `_send_message`
- `TopicBuildWorker` class stays but its caller no longer disables the workspace list

### Files Changed

| File | Change |
|------|--------|
| `app/ui/chat_view.py` | Add queue, status indicators, cancel button; remove blocking |
| `app/ui/worker.py` | New `SessionWorker` replacing `ChatWorker` + `TopicBuildWorker` |
| `app/ui/main_window.py` | Remove `setEnabled` calls; wire new signals |

### Scope Boundaries

- Same-session messages are serial (queue order). This is correct — parallel replies to sequential messages would be confusing.
- Different sessions run independently in parallel (already true with QThread).
- Topic building (mind map generation) keeps its own `TopicBuildWorker` QThread but no longer calls `workspace_list.setEnabled(False)` while it runs. The user can continue using the app during generation.
- No changes to `LLMService`, `MessageRouter`, or data models.
