# Session Agent Runtime Design

Date: 2026-05-26

## Goal

Replace the current serial `SessionWorker` multi-agent pipeline with a session-scoped runtime that supports natural group-chat dispatch, independent agent message bubbles, per-agent queues, parallel execution across agents, and immediate rendering after each saved message.

The user-facing behavior should feel like a group chat:

- Topic Agent publicly mentions another agent using natural `@AgentName` text.
- The mentioned agent replies in its own message bubble.
- Topic Agent reviews non-Topic agent replies in a separate review bubble.
- No agent contribution is merged or summarized into another agent's bubble.
- Each message renders as soon as it is saved, without waiting for the whole collaboration chain to finish.

## Current Problem

The current `SessionWorker` handles one user request as a single serial pipeline:

1. Resolve target agents.
2. Call Topic Agent.
3. Parse dispatch.
4. Call child agent.
5. Call Topic Agent review.
6. Save all messages during the worker run.
7. Refresh UI only when the worker emits `done`.

This causes two structural problems:

- Multiple agents cannot work concurrently because all calls run in one worker.
- The UI appears to wait until review finishes because message rendering is tied to worker completion rather than each message save.

## Design Summary

Introduce a service-layer `SessionRuntimeManager`.

```text
SessionRuntimeManager
  └─ SessionRuntime(session_id)
      ├─ Dispatcher
      ├─ Topic Agent queue + worker
      ├─ Paper Agent queue + worker
      ├─ Transfer Agent queue + worker
      └─ Memory Agent queue + worker
```

Each chat session owns its own runtime. A runtime owns deterministic dispatch logic, in-memory task queues, and lazily started workers for the agents used in that session.

Although tasks are in memory in the first version, messages created from tasks must persist enough task metadata on `ChatMessage` for later dispatch and review handling. See "Persistent Message Metadata".

## Runtime Scope

Use a session-scoped runtime.

- Each session has its own dispatcher.
- Each session has its own agent queues.
- Each session has its own workers.
- The same agent name in different sessions does not share a worker.

Example:

```text
session_A Paper Agent worker != session_B Paper Agent worker
```

This keeps group-chat context, cancellation, task order, and review chains isolated per session.

## Worker Concurrency

Within one session:

- Different agents may run concurrently.
- The same agent runs tasks serially in FIFO order.

Example:

```text
Paper Agent queue:    task 1 -> task 2 -> task 3
Transfer Agent queue: task A -> task B

Paper Agent and Transfer Agent may run at the same time.
Paper Agent task 2 cannot start before Paper Agent task 1 finishes.
```

This preserves each agent's local order while allowing real multi-agent parallelism.

## Worker Lifecycle

Use lazy start plus idle timeout.

### SessionRuntime Start

Create a `SessionRuntime` when a session is opened or receives its first submitted message. Creating a runtime only initializes lightweight state:

- Dispatcher
- Queue registry
- Processed task keys
- Signal bindings
- Runtime status

Do not start every agent worker when the session opens.

### AgentWorker Start

Start an agent worker only when the dispatcher first enqueues a task for that agent.

Example:

```text
User asks for literature
  -> Topic Agent worker starts
Topic mentions @Paper Agent
  -> Paper Agent worker starts
Paper replies
  -> Topic Agent worker is reused for review
```

### AgentWorker End

After finishing a task, a worker enters `idle` instead of exiting immediately.

A worker stops when:

- It has been idle longer than the configured timeout.
- The session runtime is closed.
- The application exits.
- The user cancels the current request chain and no remaining task should run.

Default idle timeout: 10 minutes.

## Dispatch Protocol

Use natural language `@AgentName` as the only dispatch protocol.

Do not support `>>DISPATCH>>` / `>>END_DISPATCH>>`.

Topic Agent should dispatch like this:

```text
@Paper Agent 请检索 2023-2025 年最新代表性论文。
```

The dispatcher parses enabled agent names from message content. A machine-readable dispatch block is unnecessary and makes the chat feel less natural.

## Dispatcher Rules

The dispatcher is deterministic code. It does not call an LLM.

Its input is:

```text
on_message_saved(session_id, message_id)
```

It reads the saved message and applies the following rules.

System/runtime messages never dispatch and never trigger review.

### User Message

If the user message contains `@AgentName`, create a `user_request` task for each mentioned agent.

If the user message contains no mention, create a `user_request` task for Topic Agent.

### Topic Agent Message

If a Topic Agent message mentions non-Topic agents, split the message by mention segment and create one `dispatch` task per target agent.

Example:

```text
@Paper Agent 请检索最新论文。
@Memory Agent 请检查历史上是否试过这个方向。
```

Creates:

```text
Paper Agent instruction:
请检索最新论文。

Memory Agent instruction:
请检查历史上是否试过这个方向。
```

Both tasks receive the full Topic message in their context snapshot.

If a Topic Agent message has no mention, it is a normal Topic reply and no further dispatch occurs.

Exception: a Topic Agent message saved from a `review` task is identified by persisted message metadata, not by free-text heuristics. Review messages are handled by the Topic Review Message rule even when they contain no mentions.

### Non-Topic Agent Message

Every non-Topic agent reply creates an independent Topic Agent `review` task.

Review is per message, not batched. If Paper Agent and Transfer Agent finish independently, each reply gets its own review task as soon as it is saved.

### Topic Review Message

Topic review still uses the existing review card format:

```text
[REVIEW]
summary: ...
correctness: pass | partial | fail
score: 1-5
issues:
  - ...
action: accept | redo | supplement
[/REVIEW]
```

Dispatcher behavior:

- `accept`: update the target message's review fields and stop.
- `redo`: if `redo_count < MAX_REDO_ROUNDS`, enqueue a `redo` task for the original agent.
- `redo`: if max redo rounds are reached, enqueue a Topic fallback task.
- `supplement`: if the Topic message mentions another agent, dispatch by mention; otherwise stop.

The dispatcher must recover the reviewed target from the Topic review message's persisted `target_message_id`. It must not infer the target by "latest non-Topic message" because concurrent agent replies make that ambiguous.

### Dispatch Permissions

First version:

- User messages may dispatch to any enabled agent.
- Topic Agent messages may dispatch to non-Topic agents.
- Non-Topic agent mentions are plain text and do not dispatch.
- Topic Agent must not dispatch to Topic Agent.

This keeps Topic Agent as the supervisor and prevents uncontrolled collaboration loops.

## Agent Task Model

Tasks are in-memory objects. They are not persisted in the first version.

```python
@dataclass
class ChatContextMessage:
    message_id: str
    role: str              # user | assistant | system
    agent_name: str        # "" | Topic Agent | Paper Agent ...
    content: str
    created_at: datetime
```

```python
@dataclass
class AgentTask:
    task_id: str
    session_id: str
    target_agent: str
    task_type: str         # user_request | dispatch | review | redo | fallback
    instruction: str
    root_user_message_id: str
    trigger_message_id: str
    target_message_id: str | None
    context_snapshot: list[ChatContextMessage]
    dispatch_depth: int = 0
    redo_count: int = 0
```

Field meanings:

- `root_user_message_id`: original user message that started the collaboration chain.
- `trigger_message_id`: message that caused this task to be created.
- `target_message_id`: reviewed or redone message, only used by review/redo tasks.
- `context_snapshot`: frozen group-chat context captured when the task is enqueued.
- `dispatch_depth`: loop-prevention counter for chained dispatches.

Depth rules:

- User-originated `user_request` starts at `0`.
- Topic natural-language `dispatch` increments parent depth by `1`.
- Topic `supplement` dispatch also increments parent depth by `1`.
- `review` keeps the reviewed task's depth.
- `redo` keeps the original task's depth and increments `redo_count`.
- `fallback` keeps the original task's depth.

Do not enqueue a task whose `dispatch_depth` would exceed `MAX_DISPATCH_DEPTH`.

## Persistent Message Metadata

Add task lineage metadata to `ChatMessage` so that saved messages can be routed safely after persistence:

```python
task_id: str | None
task_type: str | None          # user_request | dispatch | review | redo | fallback
root_user_message_id: str | None
trigger_message_id: str | None
target_message_id: str | None
dispatch_depth: int = 0
```

These fields are separate from review fields. They identify why a message was produced and what message it refers to.

Rules:

- User messages set `root_user_message_id` to their own id.
- Agent replies copy lineage from the `AgentTask` that produced them.
- Review messages must set `task_type = "review"` and `target_message_id` to the reviewed non-Topic message.
- Redo replies must set `task_type = "redo"` and `target_message_id` to the previous reply being corrected.
- System/runtime error messages may set lineage fields, but dispatcher must ignore `role = "system"`.

This metadata is required because Topic review messages can be interleaved with other agent replies.

## Context Snapshot

Freeze context at enqueue time.

Workers must not query the latest group-chat messages when they begin execution. They only use `AgentTask.context_snapshot`.

Snapshot creation rules:

1. Include recent session messages, default `N = 20`.
2. Always include `root_user_message`.
3. Always include `trigger_message`.
4. Review tasks always include `target_message`.
5. Redo tasks include `target_message` and the review message that requested redo.
6. Sort the final snapshot chronologically.

This makes concurrent behavior stable. A worker sees the group-chat state from the moment its task was created, not whatever messages happen to exist when the worker later starts.

## Prompt Construction

`AgentWorker` builds prompts from:

- Agent system prompt from `AgentConfig`.
- Available agent summary, as currently done by `MessageRouter.build_system_prompt`.
- Frozen `context_snapshot`.
- Task instruction.
- Task-specific framing.

Example dispatch task prompt body:

```text
以下是当前群聊上下文，按时间顺序排列：

User:
帮我检索本领域最新文献

Topic Agent:
@Paper Agent 请检索本领域 2023-2025 年最新代表性论文。

你的任务：
请检索本领域 2023-2025 年最新代表性论文。
```

Example review task prompt body:

```text
以下是当前群聊上下文，按时间顺序排列：
...

你的任务：
请审查 Paper Agent 的目标回复，只输出 [REVIEW]...[/REVIEW] 审查卡片。
```

## UI Rendering

Rendering is driven by message saves, not worker completion.

```text
AgentWorker saves ChatMessage
  -> SessionRuntime emits message_saved(session_id, message_id) for UI rendering
  -> SessionRuntime schedules Dispatcher.on_message_saved(session_id, message_id)
  -> Dispatcher checks cancellation and processed gates
  -> Dispatcher may enqueue follow-up tasks
```

First implementation may call the existing `_refresh()` on every `message_saved`. A later optimization can append only the saved message by `message_id`.

The UI render signal and dispatcher handling are both triggered by the save event, but the dispatcher must apply cancellation gates before creating any follow-up task. Rendering a saved message does not imply that downstream dispatch is allowed.

## Status Display

Replace the single request-level worker status with runtime status.

Runtime should emit:

```text
status_changed(session_id, entries)
```

Where each entry is structured:

```python
@dataclass
class RuntimeStatusEntry:
    agent_name: str
    state: str                  # queued | running | idle | cancelling
    task_type: str | None
    instruction_summary: str
    task_id: str | None
    root_user_message_id: str | None
```

The UI can show:

```text
正在处理：
- Paper Agent：检索最新论文
- Transfer Agent：等待执行
- Topic Agent：正在审查 Paper Agent 的回复
```

First version can keep the existing status widget but feed it from runtime status instead of `SessionWorker`.

## Cancellation

Use soft cancellation.

Cancellation levels for the first version:

1. Cancel the current request chain by `root_user_message_id`.
2. Close a session runtime.

Rules:

- If a task is canceled before LLM call starts, do not execute it.
- If canceled during LLM call, wait for the call to return, then discard the result and do not write a message.
- If a message has already been written, keep it, but do not trigger downstream dispatch.
- Do not forcibly kill worker threads during an LLM call.

This avoids partial DB writes and inconsistent UI state.

Dispatcher cancellation gates:

- Maintain `canceled_roots: set[str]` in `SessionRuntime`.
- Before dispatching from any saved message, read `root_user_message_id`.
- If the root is canceled, mark the message as terminal for dispatch purposes and do not enqueue follow-up tasks.
- Before a worker starts a task, check whether its root is canceled.
- After an LLM call returns and before saving, check cancellation again; if canceled, discard the result and write nothing.

Runtime close policy:

- Inactive idle cleanup may close a runtime only when it has no active tasks and no queued tasks.
- Explicit session close or app exit cancels queued tasks, marks active tasks as cancelling, waits for workers up to a bounded timeout, then releases the runtime.
- If an in-flight LLM call outlives the close timeout, the worker result must be discarded when it returns.

## Error Handling

LLM errors must not crash the runtime.

On agent execution failure:

1. Catch the exception.
2. Write a system message.
3. Emit `message_saved`.
4. Mark the task failed.
5. Do not trigger review for that failed task.

Example:

```text
System:
Paper Agent 调用失败：<错误摘要>
```

If Topic review fails, keep the target agent reply. Leave review fields empty in the first version unless a later schema change adds `review_failed`.

System/runtime error messages are terminal. Dispatcher must ignore `role = "system"` regardless of mentions or lineage metadata.

## Loop Prevention

Use hard limits:

- `MAX_REDO_ROUNDS = 3`
- `MAX_DISPATCH_DEPTH = 5`
- Same `(session_id, trigger_message_id, task_type, target_agent, target_message_id)` dispatch key only runs once.
- Topic Agent cannot dispatch to Topic Agent.
- Non-Topic agent mentions do not dispatch in the first version.

Processed keys should be checked after cancellation gates and before task enqueue.

## Mention Parsing

Use enabled agent names from `MessageRouter`.

Parsing rules for natural-language dispatch:

- Parse mentions in chronological order.
- Ignore unknown or disabled agent names.
- Ignore `@Topic Agent` inside Topic Agent messages.
- For Topic Agent dispatch, one instruction segment runs from an agent mention to the next valid agent mention.
- Text before the first valid mention is not part of any instruction, but remains visible in the context snapshot.
- If the same agent is mentioned multiple times in one message, create one task for that agent and concatenate its segments in message order separated by blank lines.
- Adjacent mentions with no instruction text produce no task for the empty segment unless there is no other text for that agent; in that fallback case, use the full message as instruction.
- Mentions inside fenced code blocks are ignored.
- Mentions inside normal quotes or prose are still parsed in the first version.

The full source message is always present in `context_snapshot`, even when each target agent receives a segmented instruction.

## Threading and Persistence

Use Qt queued signals for all worker-to-UI communication.

Persistence rules:

- Never share a SQLModel `Session` across threads.
- Each DB operation opens its own short-lived `Session`.
- Use the existing SQLite engine with `check_same_thread=False`.
- Guard writes through a runtime/global persistence lock in the first version to avoid concurrent SQLite write conflicts.
- Commit the `ChatMessage` before emitting `message_saved`.
- Emit signals from workers/runtime using Qt's queued connection semantics so UI updates run on the UI thread.

The first version may let workers perform DB writes directly under the persistence lock. A later version can centralize persistence behind a dedicated runtime persistence service if needed.

## Components

### `SessionRuntimeManager`

Responsibilities:

- Create and cache `SessionRuntime` by `session_id`.
- Submit user messages to the correct runtime.
- Close runtimes for inactive sessions.
- Stop all runtimes on app exit.
- Expose Qt signals for UI integration.
- Maintain a global persistence lock or provide access to one shared by runtimes.

### `SessionRuntime`

Responsibilities:

- Own dispatcher, queues, workers, and processed keys for one session.
- Receive `on_message_saved`.
- Emit `message_saved` and `status_changed`.
- Manage cancellation by root user message.
- Stop workers on close.
- Close from inactivity only when no queued or active tasks exist.

### `Dispatcher`

Responsibilities:

- Parse mentions.
- Split natural-language mention segments.
- Create task context snapshots.
- Enqueue tasks.
- Parse review cards.
- Update review metadata.
- Enforce loop prevention.
- Apply cancellation gates before enqueueing follow-up tasks.

### `AgentWorker`

Responsibilities:

- Own one agent queue within one session runtime.
- Process tasks FIFO.
- Lazily start when a task is first queued.
- Build prompt from frozen task context.
- Call LLM.
- Save replies.
- Emit saved message events.
- Enter idle after task completion.
- Exit after idle timeout.
- Check cancellation before call, after call, and before saving.

### `ChatView`

Responsibilities:

- Save user message immediately.
- Submit saved message to `SessionRuntimeManager`.
- Listen for `message_saved` and refresh or append.
- Listen for runtime status updates.
- Request cancellation through runtime manager.

ChatView should no longer own `session_worker_busy`, `session_queues`, or the old auto-collab chain.

## Migration Plan

Remove or replace:

- Serial `SessionWorker` dispatch/review/redo pipeline.
- `parse_dispatch_blocks`.
- `>>DISPATCH>>` prompt instructions and tests.
- `ChatView` session queue and busy state.
- Auto-collab mechanism, because Dispatcher now owns natural `@mention` dispatch.

Keep and adapt:

- `parse_review_card`.
- `ReviewResult`.
- `MessageRouter.parse_mentions`.
- `MessageRouter.resolve_agents`.
- `MessageRouter.build_system_prompt`.
- Existing `ChatMessage` review fields.
- Existing review card UI.

## Testing Plan

### Dispatcher Unit Tests

Cover:

- User without mention creates Topic task.
- User with `@Paper Agent` creates Paper task.
- Topic with `@Paper Agent` creates Paper dispatch task.
- Topic with multiple mentions creates multiple tasks with segmented instructions.
- Non-Topic reply creates Topic review task.
- Topic review accept updates target review status.
- Topic review redo creates redo task.
- Non-Topic mentions do not dispatch.
- Duplicate `message_saved` events do not duplicate tasks.
- Topic cannot dispatch to Topic.
- System messages never dispatch or trigger review.
- Unknown and disabled mentions are ignored.
- Duplicate same-agent mentions are merged into one task.
- Mentions inside fenced code blocks are ignored.
- Dispatch depth over `MAX_DISPATCH_DEPTH` is rejected.
- Canceled root messages do not produce downstream tasks.

### Runtime Tests

Use fake LLM responses.

Cover:

- User -> Topic -> Paper -> Topic review message order.
- Each saved message emits `message_saved`.
- Paper and Memory workers can run concurrently.
- Same agent tasks execute FIFO.
- Worker lazy start.
- Worker idle timeout exit.
- Runtime inactivity cleanup does not close runtimes with active or queued tasks.
- Explicit runtime close cancels queued tasks and discards late in-flight results.
- Soft cancellation before call prevents execution.
- Soft cancellation during call discards result.
- Topic supplement with a valid mention creates a dispatch task.
- Max redo rounds creates Topic fallback instead of another redo.
- System error messages emit `message_saved` but do not dispatch.

### UI Tests

Cover:

- `message_saved` triggers immediate refresh.
- Runtime status displays active and queued agents.
- Cancel stops pending downstream tasks.
- Existing review card rendering still works.

## Non-Goals

- No persisted `agent_tasks` table in the first version.
- No cross-process worker system.
- No semantic dependency DAG for statements like "Transfer Agent waits for Paper result".
- No automatic dispatch from non-Topic agent mentions.
- No hard interruption of in-flight LLM calls.

## Open Defaults

The following defaults are accepted for the first version:

- Context message window: 20 messages.
- Worker idle timeout: 10 minutes.
- Max redo rounds: 3.
- Max dispatch depth: 5.
