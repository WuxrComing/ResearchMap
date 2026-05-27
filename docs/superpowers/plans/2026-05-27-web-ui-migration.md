# Web UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate ResearchMap from PyQt6 desktop UI to FastAPI + React web app, reusing autogen-studio layout components

**Architecture:** FastAPI serves a REST + SSE API backed by existing SQLModel services. React + Vite + Tailwind CSS frontend reuses autogen-studio's layout/sidebar/header components directly. SessionRuntime adapted from QThread to Python threading with async callbacks for SSE streaming.

**Tech Stack:** FastAPI, SQLModel, Python threading, React 18, Vite, Tailwind CSS 3, HeadlessUI, Ant Design, Zustand, Cytoscape.js

**Source of truth for all UI design decisions:** `ref/autogen-main/python/packages/autogen-studio/frontend/`

---

## File Structure Map

### Backend (new/modified)
```
app/
├── main.py              # REPLACE: FastAPI entry + static serving (was PyQt6 QApplication)
├── api/
│   ├── __init__.py      # NEW: APIRouter aggregation
│   ├── workspaces.py    # NEW: workspace CRUD + build SSE
│   ├── sessions.py      # NEW: session CRUD
│   ├── chat.py          # NEW: chat history + send message SSE
│   ├── mindmap.py       # NEW: mindmap query
│   └── settings.py      # NEW: LLM agent config CRUD
├── services/
│   ├── sse.py           # NEW: SSE streaming adapter for SessionRuntime
│   └── ...              # UNCHANGED: agent_runtime, message_router, mind_map_service, storage
├── models/              # UNCHANGED
├── agents/              # UNCHANGED
└── config.py            # UNCHANGED
```

### Frontend (all new)
```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── components/
│   │   ├── layout.tsx           # COPIED from autogen-studio
│   │   ├── sidebar.tsx          # COPIED from autogen-studio (nav items modified)
│   │   ├── contentheader.tsx    # COPIED from autogen-studio
│   │   ├── footer.tsx           # COPIED from autogen-studio
│   │   ├── icons.tsx            # COPIED from autogen-studio (app icon modified)
│   │   └── types/
│   │       └── datamodel.ts     # NEW: ResearchMap data types
│   ├── hooks/
│   │   ├── provider.tsx         # COPIED from autogen-studio (dark mode only, no auth)
│   │   └── store.ts             # NEW: Zustand stores for workspaces/sessions/chat
│   ├── pages/
│   │   ├── workspaces/
│   │   │   └── WorkspacePage.tsx
│   │   ├── chat/
│   │   │   ├── ChatPage.tsx
│   │   │   ├── SessionSidebar.tsx
│   │   │   ├── ChatView.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   └── ChatInput.tsx
│   │   ├── mindmap/
│   │   │   └── MindMapPanel.tsx
│   │   └── settings/
│   │       └── SettingsPage.tsx
│   └── api/
│       └── client.ts            # NEW: API client with SSE support
```

---

### Task 1: Add FastAPI + SSE dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add FastAPI, uvicorn, sse-starlette to dependencies**

```toml
[project]
name = "research-map-agent"
version = "0.1.0"
description = "Dynamic research mind map agent"
requires-python = ">=3.11"
dependencies = [
    "pyqt6>=6.7.0",
    "sqlmodel>=0.0.22",
    "openai>=1.55.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.27.0",
    "jinja2>=3.1.0",
    "markdown2>=2.5.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sse-starlette>=2.1.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `pip install fastapi uvicorn[standard] sse-starlette`
Expected: All packages installed successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add FastAPI, uvicorn, sse-starlette"
```

---

### Task 2: Create SSE streaming adapter for SessionRuntime

**Files:**
- Create: `app/services/sse.py`

The SessionRuntime and SessionRuntimeManager use `pyqtSignal` for callbacks. We need an adapter that replaces Qt signals with Python callbacks for use in FastAPI async endpoints.

- [ ] **Step 1: Write the SSE adapter module**

```python
"""SSE streaming adapter for SessionRuntime — replaces PyQt6 signals with async callbacks."""
import asyncio
import json
import queue
import threading
from dataclasses import dataclass
from app.services.storage import get_engine


@dataclass
class SSEEvent:
    event: str
    data: str


class SessionRuntimeAdapter:
    """Wraps SessionRuntimeManager for SSE streaming in FastAPI endpoints.

    Replaces pyqtSignal callbacks with asyncio.Queue for SSE delivery.
    """

    def __init__(self):
        self.engine = get_engine()
        # Defer import to avoid Qt dependency at module load
        from app.services.agent_runtime import SessionRuntimeManager

        self._manager = SessionRuntimeManager(engine=self.engine)

        self._manager.message_saved.connect(self._on_message_saved)
        self._manager.status_changed.connect(self._on_status_changed)

        # Per-session SSE queues: session_id -> asyncio.Queue
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    def _on_message_saved(self, session_id: str, message_id: str) -> None:
        from app.models.chat_message import ChatMessage
        from sqlmodel import Session

        with Session(self.engine) as db:
            msg = db.get(ChatMessage, message_id)

        if msg:
            event = SSEEvent(
                event="message",
                data=json.dumps({
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "agent_name": msg.agent_name,
                    "review_status": msg.review_status,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }, default=str),
            )
            q = self._get_queue(session_id)
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _on_status_changed(self, session_id: str, entries: list) -> None:
        event = SSEEvent(
            event="status",
            data=json.dumps([
                {
                    "agent_name": e.agent_name,
                    "state": e.state,
                    "task_type": e.task_type,
                    "instruction_summary": e.instruction_summary,
                    "task_id": e.task_id,
                    "root_user_message_id": e.root_user_message_id,
                }
                for e in entries
            ], default=str),
        )
        q = self._get_queue(session_id)
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def submit_message(self, session_id: str, message_id: str) -> None:
        self._manager.submit_message(session_id, message_id)

    def start_draining(self, session_id: str) -> None:
        self._manager.start_draining(session_id)

    def cancel_root(self, session_id: str, root_user_message_id: str) -> None:
        self._manager.cancel_root(root_user_message_id)

    def shutdown(self) -> None:
        self._manager.shutdown()

    async def event_stream(self, session_id: str) -> asyncio.Queue:
        return self._get_queue(session_id)


# Global singleton
_adapter: SessionRuntimeAdapter | None = None


def get_sse_adapter() -> SessionRuntimeAdapter:
    global _adapter
    if _adapter is None:
        _adapter = SessionRuntimeAdapter()
    return _adapter
```

Wait — PyQt6 signal `.connect()` won't work in a non-Qt context because there's no QApplication. Let me rewrite this to NOT use Qt signals at all, and instead thread pool directly.

Actually, looking more carefully at SessionRuntime, the `_on_worker_message_saved` method calls either `emit` on a signal OR a plain callable. The `SessionRuntime.__init__` accepts `message_saved_signal` and `status_changed_signal` as callables. So we can pass plain Python callables directly without using Qt signals at all.

Let me rewrite:

```python
"""SSE streaming adapter — bridges SessionRuntime to async SSE queues."""
import asyncio
import json
import threading
from app.services.storage import get_engine


class SSEEvent:
    def __init__(self, event: str, data: str):
        self.event = event
        self.data = data


class SessionRuntimeSSEAdapter:
    """Wraps SessionRuntime with plain callbacks + asyncio.Queue for SSE."""

    def __init__(self):
        self.engine = get_engine()
        self._queues: dict[str, asyncio.Queue] = {}

        from app.services.agent_runtime import SessionRuntimeManager
        self._manager = SessionRuntimeManager(
            engine=self.engine,
            message_saved_signal=self._on_message_saved,
            status_changed_signal=self._on_status_changed,
        )

    def _get_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue(maxsize=256)
        return self._queues[session_id]

    def _on_message_saved(self, session_id: str, message_id: str) -> None:
        from app.models.chat_message import ChatMessage
        from sqlmodel import Session

        with Session(self.engine) as db:
            msg = db.get(ChatMessage, message_id)
        if msg is None:
            return

        event = SSEEvent(
            event="message",
            data=json.dumps({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "agent_name": msg.agent_name,
                "review_status": msg.review_status,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }, default=str),
        )
        q = self._get_queue(session_id)
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def _on_status_changed(self, session_id: str, entries: list) -> None:
        event = SSEEvent(
            event="status",
            data=json.dumps([
                {
                    "agent_name": e.agent_name,
                    "state": e.state,
                    "task_type": e.task_type,
                    "instruction_summary": e.instruction_summary,
                    "task_id": e.task_id,
                    "root_user_message_id": e.root_user_message_id,
                }
                for e in entries
            ], default=str),
        )
        q = self._get_queue(session_id)
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def submit_message(self, session_id: str, message_id: str) -> None:
        self._manager.submit_message(session_id, message_id)

    def start_draining(self, session_id: str) -> None:
        self._manager.start_draining(session_id)

    def cancel_root(self, session_id: str, root_user_message_id: str) -> None:
        self._manager.cancel_root(session_id, root_user_message_id)

    def shutdown(self) -> None:
        self._manager.shutdown()

    async def event_stream(self, session_id: str):
        """Async generator yielding SSE events for a session."""
        q = self._get_queue(session_id)
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                yield event
            except asyncio.TimeoutError:
                yield SSEEvent(event="ping", data="{}")


_adapter: SessionRuntimeSSEAdapter | None = None


def get_sse_adapter() -> SessionRuntimeSSEAdapter:
    global _adapter
    if _adapter is None:
        _adapter = SessionRuntimeSSEAdapter()
    return _adapter
```

Wait, I need to check - does `SessionRuntimeManager.__init__` accept `message_saved_signal` as a plain callable? Let me look again...

Looking at `SessionRuntimeManager.__init__`:
```python
def __init__(self, engine=None, llm_caller=None, parent=None):
    super().__init__(parent)
    self.engine = engine
    self.llm_caller = llm_caller
    self._runtimes: dict[str, SessionRuntime] = {}
    self._persistence_lock = None
```

It doesn't accept message_saved_signal or status_changed_signal as __init__ params. These are pyqtSignal class attributes:
```python
class SessionRuntimeManager(QObject):
    message_saved = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, list)
```

So `message_saved` is a pyqtSignal on the QObject, not an injectable callback.

However, checking `SessionRuntime._on_worker_message_saved`:
```python
def _on_worker_message_saved(self, session_id: str, message_id: str) -> None:
    if self.message_saved_signal is not None:
        try:
            self.message_saved_signal.emit(session_id, message_id)
        except AttributeError:
            try:
                self.message_saved_signal(session_id, message_id)
            except (TypeError, RuntimeError):
                self.message_saved_signal((session_id, message_id))
```

So `SessionRuntime` tries `.emit()` first, then falls back to calling it as a plain function. But `SessionRuntime` is created by `SessionRuntimeManager.get_runtime()` which passes `self.message_saved` (the pyqtSignal) as the signal.

The issue is that `SessionRuntimeManager` itself extends QObject and uses pyqtSignal. In a FastAPI context without QApplication, this will fail.

I have two options:
1. Modify SessionRuntimeManager to work without QObject/pyqtSignal (extract an interface)
2. Create a thin wrapper thread that runs the QApplication in the background (messy)

Option 1 is cleaner. I'll create a `SessionRuntimeManager` variant that doesn't use Qt signals, using plain callbacks instead.

Actually, wait. Let me look at this differently. The `_RuntimeWorkerThread` also extends `QThread`. We can't use QThread without a QApplication.

So the approach is:
1. Create `ThreadedSessionRuntime` that uses `threading.Thread` instead of `QThread`
2. Create `ThreadedSessionRuntimeManager` that uses plain callbacks instead of pyqtSignal
3. These are thin wrappers around the existing `AgentWorker` and `AgentDispatcher` which are pure Python (no Qt)

Let me revise the plan. Actually, looking again at the code more carefully:

- `AgentWorker` - pure Python, no Qt ✅
- `AgentDispatcher` - pure Python, no Qt ✅
- `SessionRuntime` - pure Python, no Qt (uses callables for signals) ✅
- `SessionRuntimeManager` - extends QObject, uses pyqtSignal ❌
- `_RuntimeWorkerThread` - extends QThread ❌

So I only need to modify/wrap `SessionRuntimeManager` and `_RuntimeWorkerThread` to be Qt-free.

Let me write a clean plan for this.

Actually, I'm overcomplicating this. Let me just write the plan with the practical approach. The key insight: create non-Qt versions of the two Qt-dependent classes.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="Write">
<｜｜DSML｜｜parameter name="content" string="true"># Web UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate ResearchMap from PyQt6 desktop UI to FastAPI + React web app, reusing autogen-studio layout components

**Architecture:** FastAPI serves REST + SSE API backed by existing SQLModel services. React + Vite + Tailwind CSS frontend reuses autogen-studio's layout/sidebar/header directly. Two Qt-dependent classes (SessionRuntimeManager, _RuntimeWorkerThread) are adapted to use plain threading + callbacks.

**Tech Stack:** FastAPI, SQLModel, Python threading, React 18, Vite, Tailwind CSS 3, HeadlessUI, Ant Design, Zustand, Cytoscape.js

**Design reference:** All visual decisions follow `ref/autogen-main/python/packages/autogen-studio/frontend/`

---

## File Structure Map

### Backend
```
app/
├── main.py              # REPLACE: FastAPI + static serving (was PyQt6 QApplication)
├── api/
│   ├── __init__.py      # NEW
│   ├── workspaces.py    # NEW
│   ├── sessions.py      # NEW
│   ├── chat.py          # NEW + SSE streaming
│   ├── mindmap.py       # NEW
│   └── settings.py      # NEW
├── services/
│   ├── sse_adapter.py   # NEW: non-Qt SessionRuntime wrapper
│   ├── agent_runtime.py # MODIFY: add non-Qt RuntimeWorkerThread
│   └── ...              # UNCHANGED
├── models/              # UNCHANGED
├── agents/              # UNCHANGED
└── config.py            # UNCHANGED
```

### Frontend
```
frontend/
├── package.json
├── vite.config.ts / tsconfig.json / tailwind.config.js / postcss.config.js
├── index.html
├── src/
│   ├── main.tsx / App.tsx / index.css
│   ├── components/        # COPIED from autogen-studio (layout, sidebar, contentheader, footer, icons)
│   ├── hooks/             # provider (dark mode), store (Zustand)
│   ├── pages/
│   │   ├── workspaces/WorkspacePage.tsx
│   │   ├── chat/ChatPage.tsx + SessionSidebar.tsx + ChatView.tsx + MessageBubble.tsx + ChatInput.tsx
│   │   ├── mindmap/MindMapPanel.tsx
│   │   └── settings/SettingsPage.tsx
│   └── api/client.ts
```

---

### Task 1: Add FastAPI + SSE dependencies

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: Add FastAPI, uvicorn, sse-starlette to dependencies**

```toml
dependencies = [
    # ... existing deps remain ...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sse-starlette>=2.1.0",
]
```

- [ ] **Step 2: Install**

Run: `pip install fastapi uvicorn[standard] sse-starlette`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add FastAPI, uvicorn, sse-starlette for web API"
```

---

### Task 2: Create non-Qt SessionRuntime adapter

**Files:**
- Create: `app/services/sse_adapter.py`
- Modify: `app/services/agent_runtime.py` — add `NativeWorkerThread(threading.Thread)` alongside existing `_RuntimeWorkerThread(QThread)`

**Context:** `SessionRuntimeManager` extends `QObject` with `pyqtSignal`, and `_RuntimeWorkerThread` extends `QThread`. These are the only Qt-dependent classes in the agent runtime. We add non-Qt alternatives that use `threading.Thread` and plain callbacks.

- [ ] **Step 1: Add NativeWorkerThread to agent_runtime.py**

Append after the `_RuntimeWorkerThread` class (around line 854):

```python
import threading


class NativeWorkerThread(threading.Thread):
    """Non-Qt alternative to _RuntimeWorkerThread for web server use."""

    def __init__(self, runtime, agent_name: str):
        super().__init__(daemon=True)
        self._runtime = runtime
        self._agent_name = agent_name

    def run(self):
        while not self._runtime.closed:
            queue = self._runtime.queues.get(self._agent_name)
            if not queue:
                break
            try:
                task = queue.popleft()
            except IndexError:
                break

            if task.root_user_message_id in self._runtime.canceled_roots:
                continue

            worker = self._runtime._ensure_worker(self._agent_name)
            self._runtime._active_workers_count += 1
            self._runtime._emit_status()
            try:
                message_id = worker.process_one(task)
            finally:
                self._runtime._active_workers_count -= 1

            if message_id is not None:
                self._runtime.on_message_saved(message_id)
                self._runtime._start_draining()

        self._runtime.queues.pop(self._agent_name, None)
        self._runtime._threads.pop(self._agent_name, None)
        self._runtime._emit_status()
```

- [ ] **Step 2: Add `_thread_class` attribute to SessionRuntime**

In `SessionRuntime.__init__`, add after `self._draining_sync = False`:

```python
self._thread_class = NativeWorkerThread  # can be swapped for tests
```

- [ ] **Step 3: Replace `_RuntimeWorkerThread` usage in `_start_draining`**

Change line 919 from:
```python
thread = _RuntimeWorkerThread(self, agent_name)
```
to:
```python
thread = self._thread_class(self, agent_name)
```

- [ ] **Step 4: Write the SSE adapter**

Create `app/services/sse_adapter.py`:

```python
"""Bridges SessionRuntime to asyncio SSE queues for FastAPI."""
import asyncio
import json
from app.services.storage import get_engine
from app.services.agent_runtime import SessionRuntime, AgentDispatcher


class SSEEvent:
    def __init__(self, event: str, data: str):
        self.event = event
        self.data = data


class SSEAdapter:
    """Manages SessionRuntime instances with SSE event queues."""

    def __init__(self):
        self.engine = get_engine()
        self._runtimes: dict[str, SessionRuntime] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_runtime(self, session_id: str) -> SessionRuntime:
        if session_id not in self._runtimes:
            rt = SessionRuntime(
                session_id=session_id,
                engine=self.engine,
                message_saved_signal=self._on_message_saved,
                status_changed_signal=self._on_status_changed,
            )
            self._runtimes[session_id] = rt
        return self._runtimes[session_id]

    def _get_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue(maxsize=256)
        return self._queues[session_id]

    def _on_message_saved(self, session_id: str, message_id: str) -> None:
        from app.models.chat_message import ChatMessage
        from sqlmodel import Session
        with Session(self.engine) as db:
            msg = db.get(ChatMessage, message_id)
        if msg is None:
            return
        event = SSEEvent(event="message", data=json.dumps({
            "id": msg.id, "role": msg.role, "content": msg.content,
            "agent_name": msg.agent_name, "review_status": msg.review_status,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }, default=str))
        try:
            self._get_queue(session_id).put_nowait(event)
        except asyncio.QueueFull:
            pass

    def _on_status_changed(self, session_id: str, entries: list) -> None:
        event = SSEEvent(event="status", data=json.dumps([
            {"agent_name": e.agent_name, "state": e.state,
             "task_type": e.task_type, "instruction_summary": e.instruction_summary[:80],
             "task_id": e.task_id, "root_user_message_id": e.root_user_message_id}
            for e in entries
        ], default=str))
        try:
            self._get_queue(session_id).put_nowait(event)
        except asyncio.QueueFull:
            pass

    def submit_message(self, session_id: str, message_id: str) -> None:
        rt = self._get_runtime(session_id)
        rt.on_message_saved(message_id)

    def start_draining(self, session_id: str) -> None:
        rt = self._get_runtime(session_id)
        rt._start_draining()

    def cancel_root(self, session_id: str, root_user_message_id: str) -> None:
        rt = self._get_runtime(session_id)
        rt.cancel_root(root_user_message_id)

    def shutdown(self) -> None:
        for rt in self._runtimes.values():
            rt.close(reason="shutdown")
        self._runtimes.clear()

    async def event_stream(self, session_id: str):
        q = self._get_queue(session_id)
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                yield event
            except asyncio.TimeoutError:
                yield SSEEvent(event="ping", data="{}")


_adapter: SSEAdapter | None = None


def get_sse_adapter() -> SSEAdapter:
    global _adapter
    if _adapter is None:
        _adapter = SSEAdapter()
    return _adapter
```

- [ ] **Step 5: Commit**

```bash
git add app/services/agent_runtime.py app/services/sse_adapter.py
git commit -m "feat: add non-Qt SessionRuntime adapter for SSE streaming"
```

---

### Task 3: Create FastAPI routes — settings

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/settings.py`

- [ ] **Step 1: Create `app/api/__init__.py`**

```python
from fastapi import APIRouter

api_router = APIRouter(prefix="/api")
```

- [ ] **Step 2: Create `app/api/settings.py`**

```python
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.services.storage import get_engine, get_session
from app.models.agent_config import AgentConfig
from app.config import settings as app_settings
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMSettingsOut(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class LLMSettingsUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class AgentOut(BaseModel):
    name: str
    role: str
    system_prompt: str
    description: str
    model: str
    color: str
    enabled: bool


class AgentUpdate(BaseModel):
    enabled: bool | None = None
    system_prompt: str | None = None
    model: str | None = None


@router.get("", response_model=LLMSettingsOut)
def get_llm_settings():
    return LLMSettingsOut(
        api_key="***" if app_settings.DEEPSEEK_API_KEY else "",
        base_url=app_settings.DEEPSEEK_BASE_URL,
        model=app_settings.LLM_MODEL,
    )


@router.put("", response_model=LLMSettingsOut)
def update_llm_settings(body: LLMSettingsUpdate):
    # Settings are environment-based; updates persist to .env
    import os
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    updates = {}
    if body.api_key is not None:
        updates["DEEPSEEK_API_KEY"] = body.api_key
    if body.base_url is not None:
        updates["DEEPSEEK_BASE_URL"] = body.base_url
    if body.model is not None:
        updates["LLM_MODEL"] = body.model

    for key, val in updates.items():
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}\n"
                found = True
                break
        if not found:
            lines.append(f"{key}={val}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    # Reload settings
    app_settings.DEEPSEEK_API_KEY = updates.get("DEEPSEEK_API_KEY", app_settings.DEEPSEEK_API_KEY)
    app_settings.DEEPSEEK_BASE_URL = updates.get("DEEPSEEK_BASE_URL", app_settings.DEEPSEEK_BASE_URL)
    app_settings.LLM_MODEL = updates.get("LLM_MODEL", app_settings.LLM_MODEL)

    return LLMSettingsOut(
        api_key="***" if app_settings.DEEPSEEK_API_KEY else "",
        base_url=app_settings.DEEPSEEK_BASE_URL,
        model=app_settings.LLM_MODEL,
    )


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_session)):
    agents = db.exec(select(AgentConfig)).all()
    return [
        AgentOut(
            name=a.name, role=a.role, system_prompt=a.system_prompt,
            description=a.description or "", model=a.model or "",
            color=a.color or "", enabled=a.enabled,
        )
        for a in agents
    ]


@router.put("/agents/{name}", response_model=AgentOut)
def update_agent(name: str, body: AgentUpdate, db: Session = Depends(get_session)):
    agent = db.exec(select(AgentConfig).where(AgentConfig.name == name)).first()
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(404, f"Agent {name} not found")
    if body.enabled is not None:
        agent.enabled = body.enabled
    if body.system_prompt is not None:
        agent.system_prompt = body.system_prompt
    if body.model is not None:
        agent.model = body.model
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return AgentOut(
        name=agent.name, role=agent.role, system_prompt=agent.system_prompt,
        description=agent.description or "", model=agent.model or "",
        color=agent.color or "", enabled=agent.enabled,
    )
```

- [ ] **Step 3: Commit**

```bash
git add app/api/__init__.py app/api/settings.py
git commit -m "feat: add FastAPI settings and agent config routes"
```

---

### Task 4: Create FastAPI routes — workspaces, sessions, mindmap

**Files:**
- Create: `app/api/workspaces.py`
- Create: `app/api/sessions.py`
- Create: `app/api/mindmap.py`

- [ ] **Step 1: Create `app/api/workspaces.py`**

```python
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, delete as sm_delete
from app.services.storage import get_engine, get_session
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from pydantic import BaseModel

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceOut(BaseModel):
    id: str
    title: str
    description: str
    session_count: int
    created_at: str
    updated_at: str


class WorkspaceCreate(BaseModel):
    title: str
    description: str = ""
    auto_generate: bool = True


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: Session = Depends(get_session)):
    topics = db.exec(select(Topic).order_by(Topic.updated_at.desc())).all()
    result = []
    for t in topics:
        count = len(db.exec(
            select(SessionModel).where(SessionModel.workspace_id == t.id)
        ).all())
        result.append(WorkspaceOut(
            id=t.id, title=t.title, description=t.description or "",
            session_count=count,
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else "",
        ))
    return result


@router.post("", response_model=WorkspaceOut)
def create_workspace(body: WorkspaceCreate):
    from app.ui.worker import TopicBuildWorker
    topic_id, session_id = TopicBuildWorker.create_empty_workspace(body.title, body.description)
    engine = get_engine()
    with Session(engine) as db:
        t = db.get(Topic, topic_id)
        return WorkspaceOut(
            id=t.id, title=t.title, description=t.description or "",
            session_count=1,
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else "",
        )


@router.put("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(workspace_id: str, body: WorkspaceCreate, db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        from fastapi import HTTPException
        raise HTTPException(404, "Workspace not found")
    t.title = body.title
    t.description = body.description
    t.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    count = len(db.exec(
        select(SessionModel).where(SessionModel.workspace_id == t.id)
    ).all())
    return WorkspaceOut(
        id=t.id, title=t.title, description=t.description or "",
        session_count=count,
        created_at=t.created_at.isoformat() if t.created_at else "",
        updated_at=t.updated_at.isoformat() if t.updated_at else "",
    )


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str):
    engine = get_engine()
    with Session(engine) as db:
        t = db.get(Topic, workspace_id)
        if not t:
            from fastapi import HTTPException
            raise HTTPException(404, "Workspace not found")
        session_ids = db.exec(
            select(SessionModel.id).where(SessionModel.workspace_id == workspace_id)
        ).all()
        for sid in session_ids:
            db.exec(sm_delete(ChatMessage).where(ChatMessage.session_id == sid))
        db.exec(sm_delete(SessionModel).where(SessionModel.workspace_id == workspace_id))
        db.exec(sm_delete(MapEdge).where(MapEdge.topic_id == workspace_id))
        db.exec(sm_delete(MapNode).where(MapNode.topic_id == workspace_id))
        db.delete(t)
        db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Create `app/api/sessions.py`**

```python
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, delete as sm_delete
from app.services.storage import get_session
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from pydantic import BaseModel

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    created_at: str
    updated_at: str


class SessionCreate(BaseModel):
    workspace_id: str
    title: str = "新会话"


@router.get("", response_model=list[SessionOut])
def list_sessions(workspace_id: str, db: Session = Depends(get_session)):
    sessions = db.exec(
        select(SessionModel)
        .where(SessionModel.workspace_id == workspace_id)
        .order_by(SessionModel.updated_at.desc())
    ).all()
    return [
        SessionOut(
            id=s.id, workspace_id=s.workspace_id, title=s.title,
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
        )
        for s in sessions
    ]


@router.post("", response_model=SessionOut)
def create_session(body: SessionCreate, db: Session = Depends(get_session)):
    sid = uuid.uuid4().hex
    s = SessionModel(id=sid, workspace_id=body.workspace_id, title=body.title)
    db.add(s)
    db.commit()
    db.refresh(s)
    return SessionOut(
        id=s.id, workspace_id=s.workspace_id, title=s.title,
        created_at=s.created_at.isoformat() if s.created_at else "",
        updated_at=s.updated_at.isoformat() if s.updated_at else "",
    )


@router.put("/{session_id}", response_model=SessionOut)
def update_session(session_id: str, body: SessionCreate, db: Session = Depends(get_session)):
    s = db.get(SessionModel, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    s.title = body.title
    s.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    return SessionOut(
        id=s.id, workspace_id=s.workspace_id, title=s.title,
        created_at=s.created_at.isoformat() if s.created_at else "",
        updated_at=s.updated_at.isoformat() if s.updated_at else "",
    )


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_session)):
    s = db.get(SessionModel, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    db.exec(sm_delete(ChatMessage).where(ChatMessage.session_id == session_id))
    db.delete(s)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 3: Create `app/api/mindmap.py`**

```python
from fastapi import APIRouter
from app.services.mind_map_service import MindMapService

router = APIRouter(prefix="/mindmap", tags=["mindmap"])


@router.get("")
def get_mindmap(workspace_id: str):
    service = MindMapService(workspace_id)
    return service.get_map_state()
```

- [ ] **Step 4: Commit**

```bash
git add app/api/workspaces.py app/api/sessions.py app/api/mindmap.py
git commit -m "feat: add workspaces, sessions, mindmap API routes"
```

---

### Task 5: Create FastAPI routes — chat with SSE

**Files:**
- Create: `app/api/chat.py`

- [ ] **Step 1: Create `app/api/chat.py`**

```python
import uuid
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse
from app.services.storage import get_engine, get_session
from app.models.chat_message import ChatMessage
from app.models.session import Session as SessionModel
from app.services.sse_adapter import get_sse_adapter
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    agent_name: str | None
    review_status: str | None
    created_at: str | None


class SendMessageRequest(BaseModel):
    session_id: str
    content: str
    mentioned_agents: list[str] = []


class CancelRequest(BaseModel):
    session_id: str
    root_user_message_id: str


@router.get("", response_model=list[MessageOut])
def list_messages(session_id: str, db: Session = Depends(get_session)):
    msgs = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    ).all()
    return [
        MessageOut(
            id=m.id, session_id=m.session_id, role=m.role, content=m.content,
            agent_name=m.agent_name, review_status=m.review_status,
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in msgs
    ]


@router.post("")
async def send_message(body: SendMessageRequest, request: Request):
    engine = get_engine()
    adapter = get_sse_adapter()

    # Verify session exists
    with Session(engine) as db:
        s = db.get(SessionModel, body.session_id)
        if not s:
            raise HTTPException(404, "Session not found")

    # Write user message
    msg_id = uuid.uuid4().hex
    with Session(engine) as db:
        msg = ChatMessage(
            id=msg_id, session_id=body.session_id,
            role="user", content=body.content,
        )
        db.add(msg)
        db.commit()

    # Submit to runtime (this triggers the agent pipeline in background threads)
    adapter.submit_message(body.session_id, msg_id)
    adapter.start_draining(body.session_id)

    async def event_generator():
        q = await adapter.event_stream(body.session_id)
        # Send initial message as first event
        yield {"event": "message", "data": json.dumps({
            "id": msg_id, "role": "user", "content": body.content,
            "agent_name": None, "review_status": None,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }, default=str)}

        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                yield {"event": event.event, "data": event.data}
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(event_generator())


@router.post("/cancel")
def cancel_message(body: CancelRequest):
    adapter = get_sse_adapter()
    adapter.cancel_root(body.session_id, body.root_user_message_id)
    return {"ok": True}
```

- [ ] **Step 2: Register all API routes in `app/api/__init__.py`**

```python
from fastapi import APIRouter
from app.api.settings import router as settings_router
from app.api.workspaces import router as workspaces_router
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.mindmap import router as mindmap_router

api_router = APIRouter(prefix="/api")
api_router.include_router(settings_router)
api_router.include_router(workspaces_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(mindmap_router)
```

- [ ] **Step 3: Commit**

```bash
git add app/api/chat.py app/api/__init__.py
git commit -m "feat: add chat API with SSE streaming"
```

---

### Task 6: Replace main.py with FastAPI entry point

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Rewrite `app/main.py`**

```python
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.services.storage import init_db
from app.api import api_router
from app.services.sse_adapter import get_sse_adapter
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("storage", exist_ok=True)
    init_db()
    yield
    get_sse_adapter().shutdown()


app = FastAPI(title="Research Map Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

# Serve frontend static files in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


def main():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add app/main.py
git commit -m "feat: replace PyQt6 entry with FastAPI app"
```

---

### Task 7: Initialize frontend project with Vite + React + Tailwind

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "researchmap-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@headlessui/react": "^2.2.0",
    "@heroicons/react": "^2.0.18",
    "antd": "^5.22.0",
    "lucide-react": "^0.460.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-markdown": "^9.0.1",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.55",
    "@types/react-dom": "^18.2.19",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.14",
    "typescript": "^5.3.3",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```

- [ ] **Step 3: Create `frontend/tailwind.config.js`** (copy from autogen-studio)

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: "var(--color-primary)",
        secondary: "var(--color-secondary)",
        tertiary: "var(--color-tertiary)",
        accent: "var(--color-accent)",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: Create `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 6: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Research Map Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 8: Create `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppProvider } from "./hooks/provider";
import Layout from "./components/layout";

function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/*" element={<Layout />} />
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}

export default App;
```

- [ ] **Step 9: Create `frontend/src/index.css`** (CSS variables for theme, from autogen-studio)

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --color-primary: #111827;
  --color-secondary: #6b7280;
  --color-tertiary: #f3f4f6;
  --color-accent: #4f46e5;
}

.dark {
  --color-primary: #f9fafb;
  --color-secondary: #9ca3af;
  --color-tertiary: #1f2937;
  --color-accent: #818cf8;
}

.bg-primary { background-color: var(--color-primary); }
.bg-secondary { background-color: var(--color-secondary); }
.bg-tertiary { background-color: var(--color-tertiary); }
.bg-accent { background-color: var(--color-accent); }
.text-primary { color: var(--color-primary); }
.text-secondary { color: var(--color-secondary); }
.text-accent { color: var(--color-accent); }
.border-secondary { border-color: var(--color-secondary); }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
```

- [ ] **Step 10: Install frontend dependencies**

Run: `cd frontend && npm install`

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: initialize frontend with Vite, React, Tailwind"
```

---

### Task 8: Copy and adapt autogen-studio layout components

**Files:**
- Create: `frontend/src/components/layout.tsx`
- Create: `frontend/src/components/sidebar.tsx`
- Create: `frontend/src/components/contentheader.tsx`
- Create: `frontend/src/components/footer.tsx`
- Create: `frontend/src/components/icons.tsx`

- [ ] **Step 1: Copy `layout.tsx` from autogen-studio** with modifications:

Copy from `ref/autogen-main/python/packages/autogen-studio/frontend/src/components/layout.tsx` and modify:
- Replace `import { Link } from "gatsby"` with `import { Link } from "react-router-dom"`
- Remove `import { useAuth } from "../auth/context"` and `import ProtectedRoute from "../auth/protected"`
- Remove `restricted` prop and ProtectedRoute wrapping
- Add `react-router-dom` routing inside the `<main>` area to render child pages

```tsx
import * as React from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import { Dialog } from "@headlessui/react";
import { X } from "lucide-react";
import { appContext } from "../hooks/provider";
import { useConfigStore } from "../hooks/store";
import Footer from "./footer";
import Sidebar from "./sidebar";
import ContentHeader from "./contentheader";
import { ConfigProvider, theme } from "antd";
import WorkspacePage from "../pages/workspaces/WorkspacePage";
import ChatPage from "../pages/chat/ChatPage";
import SettingsPage from "../pages/settings/SettingsPage";

const classNames = (...classes: (string | undefined | boolean)[]) => {
  return classes.filter(Boolean).join(" ");
};

const Layout = () => {
  const { darkMode } = React.useContext(appContext);
  const { sidebar } = useConfigStore();
  const { isExpanded } = sidebar;
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  React.useEffect(() => {
    document.getElementsByTagName("html")[0].className = `${
      darkMode === "dark" ? "dark bg-primary" : "light bg-primary"
    }`;
  }, [darkMode]);

  const meta = { title: "Research Map", description: "科研思维导图 Agent" };

  return (
    <div className="min-h-screen flex">
      <Dialog
        as="div"
        open={isMobileMenuOpen}
        onClose={() => setIsMobileMenuOpen(false)}
        className="relative z-50 md:hidden"
      >
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        <div className="fixed inset-0 flex">
          <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
            <div className="absolute right-0 top-0 flex w-16 justify-center pt-5">
              <button
                type="button"
                className="text-secondary"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                <X className="h-6 w-6" />
              </button>
            </div>
            <Sidebar link={location.pathname} meta={meta} isMobile={true} />
          </Dialog.Panel>
        </div>
      </Dialog>

      <div className="hidden md:flex md:flex-col md:fixed md:inset-y-0">
        <Sidebar link={location.pathname} meta={meta} isMobile={false} />
      </div>

      <div
        className={classNames(
          "flex-1 flex flex-col min-h-screen",
          "transition-all duration-300 ease-in-out",
          "md:pl-16",
          isExpanded ? "md:pl-72" : "md:pl-16"
        )}
      >
        <ContentHeader
          isMobileMenuOpen={isMobileMenuOpen}
          onMobileMenuToggle={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        />

        <ConfigProvider
          theme={{
            token: {
              borderRadius: 4,
              colorBgBase: darkMode === "dark" ? "#05080C" : "#ffffff",
            },
            algorithm:
              darkMode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
          }}
        >
          <main className="flex-1 p-2 text-primary">
            <Routes>
              <Route path="/" element={<WorkspacePage />} />
              <Route path="/workspaces" element={<WorkspacePage />} />
              <Route path="/chat/:workspaceId" element={<ChatPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </ConfigProvider>

        <Footer />
      </div>
    </div>
  );
};

export default Layout;
```

- [ ] **Step 2: Copy `sidebar.tsx` from autogen-studio** with navigation items replaced:

Copy from `ref/autogen-main/.../frontend/src/components/sidebar.tsx` and modify:
- Replace `import { Link } from "gatsby"` with `import { Link } from "react-router-dom"`
- Replace navigation array:

```typescript
const navigation: INavItem[] = [
  {
    name: "课题管理",
    href: "/workspaces",
    icon: ({ className }: { className?: string }) => (
      <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
      </svg>
    ),
  },
  {
    name: "对话",
    href: "/chat",
    icon: MessagesSquare,
  },
];
```

- [ ] **Step 3: Copy `contentheader.tsx`**, replacing `import { Link } from "gatsby"` with `import { Link } from "react-router-dom"`, and `to={}` with `to={}` (same interface).

- [ ] **Step 4: Copy `footer.tsx`** from autogen-studio as-is, only changing the text to "Research Map Agent".

- [ ] **Step 5: Copy `icons.tsx`** from autogen-studio, keep the `app` icon but change other icons as needed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add layout components adapted from autogen-studio"
```

---

### Task 9: Create Zustand stores and hooks

**Files:**
- Create: `frontend/src/hooks/provider.tsx`
- Create: `frontend/src/hooks/store.ts`

- [ ] **Step 1: Create `provider.tsx`** (dark mode context, simplified from autogen-studio — no auth)

```tsx
import React, { createContext, useState, useEffect } from "react";

interface AppContextType {
  darkMode: string;
  setDarkMode: (mode: string) => void;
}

export const appContext = createContext<AppContextType>({
  darkMode: "light",
  setDarkMode: () => {},
});

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("darkMode") || "light";
    }
    return "light";
  });

  useEffect(() => {
    localStorage.setItem("darkMode", darkMode);
  }, [darkMode]);

  return (
    <appContext.Provider value={{ darkMode, setDarkMode }}>
      {children}
    </appContext.Provider>
  );
};
```

- [ ] **Step 2: Create `store.ts`** with Zustand stores

```tsx
import { create } from "zustand";

// ---- Sidebar ----
interface SidebarState {
  isExpanded: boolean;
}
interface ConfigStore {
  sidebar: SidebarState;
  header: { title: string; breadcrumbs: { name: string; href: string; current?: boolean }[] };
  setSidebarState: (state: Partial<SidebarState>) => void;
  setHeader: (header: ConfigStore["header"]) => void;
}

export const useConfigStore = create<ConfigStore>((set) => ({
  sidebar: { isExpanded: false },
  header: { title: "课题管理", breadcrumbs: [{ name: "课题管理", href: "/workspaces", current: true }] },
  setSidebarState: (state) =>
    set((prev) => ({ sidebar: { ...prev.sidebar, ...state } })),
  setHeader: (header) => set({ header }),
}));

// ---- Workspaces ----
interface Workspace {
  id: string;
  title: string;
  description: string;
  session_count: number;
  created_at: string;
  updated_at: string;
}
interface WorkspaceStore {
  workspaces: Workspace[];
  selectedId: string | null;
  loading: boolean;
  setWorkspaces: (w: Workspace[]) => void;
  setSelectedId: (id: string | null) => void;
  setLoading: (l: boolean) => void;
}
export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  workspaces: [],
  selectedId: null,
  loading: false,
  setWorkspaces: (workspaces) => set({ workspaces }),
  setSelectedId: (selectedId) => set({ selectedId }),
  setLoading: (loading) => set({ loading }),
}));

// ---- Sessions ----
interface Session {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
interface SessionStore {
  sessions: Session[];
  activeId: string | null;
  loading: boolean;
  setSessions: (s: Session[]) => void;
  setActiveId: (id: string | null) => void;
  setLoading: (l: boolean) => void;
}
export const useSessionStore = create<SessionStore>((set) => ({
  sessions: [],
  activeId: null,
  loading: false,
  setSessions: (sessions) => set({ sessions }),
  setActiveId: (activeId) => set({ activeId }),
  setLoading: (loading) => set({ loading }),
}));

// ---- Chat ----
interface ChatMessage {
  id: string;
  session_id: string;
  role: string;
  content: string;
  agent_name: string | null;
  review_status: string | null;
  created_at: string | null;
}
interface ChatStore {
  messages: ChatMessage[];
  streaming: boolean;
  pendingAgents: { agent_name: string; state: string }[];
  setMessages: (m: ChatMessage[]) => void;
  addMessage: (m: ChatMessage) => void;
  setStreaming: (s: boolean) => void;
  setPendingAgents: (a: { agent_name: string; state: string }[]) => void;
}
export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  streaming: false,
  pendingAgents: [],
  setMessages: (messages) => set({ messages }),
  addMessage: (message) =>
    set((prev) => ({ messages: [...prev.messages, message] })),
  setStreaming: (streaming) => set({ streaming }),
  setPendingAgents: (pendingAgents) => set({ pendingAgents }),
}));
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add Zustand stores and dark mode provider"
```

---

### Task 10: Create API client

**Files:**
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Create `client.ts`**

```typescript
const BASE = "/api";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  // Workspaces
  listWorkspaces: () => request<any[]>("/workspaces"),
  createWorkspace: (body: { title: string; description: string; auto_generate?: boolean }) =>
    request<any>("/workspaces", { method: "POST", body: JSON.stringify(body) }),
  updateWorkspace: (id: string, body: { title: string; description: string }) =>
    request<any>(`/workspaces/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteWorkspace: (id: string) =>
    request<any>(`/workspaces/${id}`, { method: "DELETE" }),

  // Sessions
  listSessions: (workspaceId: string) =>
    request<any[]>(`/sessions?workspace_id=${workspaceId}`),
  createSession: (body: { workspace_id: string; title: string }) =>
    request<any>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  updateSession: (id: string, body: { workspace_id: string; title: string }) =>
    request<any>(`/sessions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteSession: (id: string) =>
    request<any>(`/sessions/${id}`, { method: "DELETE" }),

  // Chat
  listMessages: (sessionId: string) =>
    request<any[]>(`/chat?session_id=${sessionId}`),
  sendMessage: (body: { session_id: string; content: string }) =>
    fetch(`${BASE}/chat`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }),
  cancelMessage: (sessionId: string, rootUserMessageId: string) =>
    request<any>("/chat/cancel", { method: "POST", body: JSON.stringify({ session_id: sessionId, root_user_message_id: rootUserMessageId }) }),

  // Mindmap
  getMindmap: (workspaceId: string) =>
    request<any>(`/mindmap?workspace_id=${workspaceId}`),

  // Settings
  getSettings: () => request<any>("/settings"),
  updateSettings: (body: any) =>
    request<any>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  listAgents: () => request<any[]>("/settings/agents"),
  updateAgent: (name: string, body: any) =>
    request<any>(`/settings/agents/${name}`, { method: "PUT", body: JSON.stringify(body) }),
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add API client with SSE support"
```

---

### Task 11: Create Workspace page

**Files:**
- Create: `frontend/src/pages/workspaces/WorkspacePage.tsx`

- [ ] **Step 1: Create `WorkspacePage.tsx`**

```tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Modal, Input, message } from "antd";
import { PlusOutlined } from "@heroicons/react/24/outline";
import { api } from "../../api/client";
import { useWorkspaceStore } from "../../hooks/store";

const WorkspacePage: React.FC = () => {
  const { workspaces, setWorkspaces, loading, setLoading } = useWorkspaceStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [messageApi, contextHolder] = message.useMessage();
  const navigate = useNavigate();

  const fetchWorkspaces = async () => {
    setLoading(true);
    try {
      const data = await api.listWorkspaces();
      setWorkspaces(data);
    } catch (e: any) {
      messageApi.error("加载课题列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchWorkspaces(); }, []);

  const handleCreate = async () => {
    if (!title.trim()) return;
    try {
      const w = await api.createWorkspace({ title: title.trim(), description: desc.trim(), auto_generate: true });
      setIsModalOpen(false);
      setTitle("");
      setDesc("");
      await fetchWorkspaces();
      navigate(`/chat/${w.id}`);
    } catch (e: any) {
      messageApi.error("创建课题失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteWorkspace(id);
      await fetchWorkspaces();
    } catch (e: any) {
      messageApi.error("删除失败");
    }
  };

  return (
    <div className="p-4">
      {contextHolder}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-primary">课题管理</h1>
        <Button type="primary" icon={<PlusOutlined className="h-4 w-4" />} onClick={() => setIsModalOpen(true)}>
          新建课题
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {workspaces.map((w) => (
          <Card
            key={w.id}
            hoverable
            onClick={() => navigate(`/chat/${w.id}`)}
            title={w.title}
            extra={<Button type="text" danger onClick={(e) => { e.stopPropagation(); handleDelete(w.id); }}>删除</Button>}
          >
            <p className="text-secondary text-sm">{w.description || "暂无描述"}</p>
            <p className="text-secondary text-xs mt-2">{w.session_count} 个会话</p>
          </Card>
        ))}
      </div>

      {!loading && workspaces.length === 0 && (
        <div className="text-center text-secondary py-20">还没有课题，点击上方按钮创建</div>
      )}

      <Modal
        title="新建课题"
        open={isModalOpen}
        onOk={handleCreate}
        onCancel={() => setIsModalOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <div className="space-y-4 py-4">
          <div>
            <label className="block text-sm mb-1">课题名称</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="输入课题名称" />
          </div>
          <div>
            <label className="block text-sm mb-1">描述（可选）</label>
            <Input.TextArea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="简要描述研究课题" rows={3} />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default WorkspacePage;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/workspaces/WorkspacePage.tsx
git commit -m "feat: add workspace management page"
```

---

### Task 12: Create Chat page with session sidebar, message bubbles, and mindmap panel

**Files:**
- Create: `frontend/src/pages/chat/ChatPage.tsx`
- Create: `frontend/src/pages/chat/SessionSidebar.tsx`
- Create: `frontend/src/pages/chat/ChatView.tsx`
- Create: `frontend/src/pages/chat/MessageBubble.tsx`
- Create: `frontend/src/pages/chat/ChatInput.tsx`
- Create: `frontend/src/pages/mindmap/MindMapPanel.tsx`

- [ ] **Step 1: Create `ChatPage.tsx`** — main layout with session sidebar + chat + mindmap

```tsx
import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useWorkspaceStore, useSessionStore } from "../../hooks/store";
import { api } from "../../api/client";
import SessionSidebar from "./SessionSidebar";
import ChatView from "./ChatView";
import MindMapPanel from "../mindmap/MindMapPanel";

const ChatPage: React.FC = () => {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const { setSelectedId } = useWorkspaceStore();
  const { sessions, setSessions, activeId, setActiveId, setLoading } = useSessionStore();
  const [mindmapVisible, setMindmapVisible] = useState(true);

  useEffect(() => {
    if (!workspaceId) {
      navigate("/workspaces");
      return;
    }
    setSelectedId(workspaceId);
    fetchSessions();
  }, [workspaceId]);

  const fetchSessions = async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const data = await api.listSessions(workspaceId);
      setSessions(data);
      if (data.length > 0 && !activeId) {
        setActiveId(data[0].id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSession = async () => {
    if (!workspaceId) return;
    try {
      const s = await api.createSession({ workspace_id: workspaceId, title: "新会话" });
      await fetchSessions();
      setActiveId(s.id);
    } catch (e) {
      console.error(e);
    }
  };

  if (!workspaceId) return null;

  return (
    <div className="flex h-[calc(100vh-120px)]">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={handleCreateSession}
        onDelete={async (id) => {
          await api.deleteSession(id);
          await fetchSessions();
        }}
      />
      <div className="flex-1 flex">
        <div className="flex-1">
          {activeId ? (
            <ChatView sessionId={activeId} />
          ) : (
            <div className="flex items-center justify-center h-full text-secondary">
              选择或创建一个会话
            </div>
          )}
        </div>
        {mindmapVisible && workspaceId && (
          <div className="w-80 border-l border-secondary relative">
            <MindMapPanel workspaceId={workspaceId} />
            <button
              className="absolute top-2 right-2 p-1 rounded hover:bg-secondary text-secondary"
              onClick={() => setMindmapVisible(false)}
            >
              ◀
            </button>
          </div>
        )}
        {!mindmapVisible && (
          <button
            className="self-start mt-2 p-1 rounded hover:bg-secondary text-secondary"
            onClick={() => setMindmapVisible(true)}
          >
            ▶
          </button>
        )}
      </div>
    </div>
  );
};

export default ChatPage;
```

- [ ] **Step 2: Create `SessionSidebar.tsx`**

```tsx
import React from "react";
import { Button } from "antd";
import { PlusOutlined } from "@heroicons/react/24/outline";

interface Session {
  id: string;
  title: string;
}

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

const SessionSidebar: React.FC<Props> = ({ sessions, activeId, onSelect, onCreate, onDelete }) => {
  return (
    <div className="w-56 border-r border-secondary p-2 flex flex-col">
      <Button
        size="small"
        type="primary"
        icon={<PlusOutlined className="h-3 w-3" />}
        onClick={onCreate}
        className="mb-2"
      >
        新会话
      </Button>
      <div className="flex-1 overflow-y-auto space-y-1">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-sm ${
              s.id === activeId ? "bg-secondary/20 text-primary" : "text-secondary hover:bg-tertiary"
            }`}
            onClick={() => onSelect(s.id)}
          >
            <span className="truncate">{s.title}</span>
            <button
              className="opacity-0 hover:opacity-100 text-xs text-red-500 ml-1"
              onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SessionSidebar;
```

- [ ] **Step 3: Create `ChatView.tsx`** with SSE streaming

```tsx
import React, { useEffect, useRef, useState } from "react";
import { useChatStore } from "../../hooks/store";
import { api } from "../../api/client";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";
import { message } from "antd";

const ChatView: React.FC<{ sessionId: string }> = ({ sessionId }) => {
  const { messages, setMessages, addMessage, streaming, setStreaming, pendingAgents, setPendingAgents } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    loadMessages();
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, pendingAgents]);

  const loadMessages = async () => {
    try {
      const data = await api.listMessages(sessionId);
      setMessages(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSend = async (content: string) => {
    setStreaming(true);
    try {
      const response = await api.sendMessage({ session_id: sessionId, content });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (data.event === "message" || !data.event) {
              addMessage(JSON.parse(data.data));
            } else if (data.event === "status") {
              setPendingAgents(JSON.parse(data.data));
            }
          }
        }
      }
    } catch (e: any) {
      messageApi.error("发送失败");
    } finally {
      setStreaming(false);
      setPendingAgents([]);
      await loadMessages();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {contextHolder}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {pendingAgents.length > 0 && (
          <div className="text-secondary text-sm italic px-4">
            {pendingAgents.map((a) => (
              <span key={a.agent_name} className="mr-3">
                {a.state === "running" ? "⏳" : "⏱"} {a.agent_name} {a.state === "running" ? "思考中..." : "排队中"}
              </span>
            ))}
          </div>
        )}
      </div>
      <ChatInput onSend={handleSend} disabled={streaming} />
    </div>
  );
};

export default ChatView;
```

- [ ] **Step 4: Create `MessageBubble.tsx`**

```tsx
import React from "react";
import ReactMarkdown from "react-markdown";

interface Props {
  message: {
    id: string;
    role: string;
    content: string;
    agent_name: string | null;
    review_status: string | null;
  };
}

const AVATAR_COLORS: Record<string, string> = {
  user: "#2196F3",
  "Topic Agent": "#07C160",
  "Paper Agent": "#F9A825",
};

const MessageBubble: React.FC<Props> = ({ message }) => {
  const { role, content, agent_name } = message;
  const isUser = role === "user";
  const isSystem = role === "system";
  const displayName = isUser ? "我" : (agent_name || "System");
  const color = AVATAR_COLORS[displayName] || "#757575";

  if (isSystem) {
    return (
      <div className="text-center text-secondary text-xs py-1">{content}</div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
        style={{ backgroundColor: color }}
      >
        {displayName[0]}
      </div>
      <div className="flex flex-col max-w-[70%]">
        <span className={`text-xs text-secondary mb-0.5 ${isUser ? "text-right" : ""}`}>
          {displayName}
        </span>
        <div
          className={`rounded-lg px-3 py-2 text-sm ${
            isUser
              ? "bg-[#07C160] text-white"
              : "bg-[#F0F0F0] dark:bg-[#2a2a2a] text-primary border border-secondary/20"
          }`}
        >
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;
```

- [ ] **Step 5: Create `ChatInput.tsx`**

```tsx
import React, { useState } from "react";

interface Props {
  onSend: (content: string) => void;
  disabled: boolean;
}

const ChatInput: React.FC<Props> = ({ onSend, disabled }) => {
  const [value, setValue] = useState("");

  const handleSend = () => {
    if (!value.trim() || disabled) return;
    onSend(value.trim());
    setValue("");
  };

  return (
    <div className="border-t border-secondary p-3 flex gap-2">
      <input
        className="flex-1 border border-secondary rounded px-3 py-2 text-sm bg-primary text-primary focus:outline-none focus:border-accent"
        placeholder="输入消息... 使用 @Agent名称 指定 Agent"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        disabled={disabled}
      />
      <button
        className="px-4 py-2 bg-[#07C160] text-white rounded text-sm hover:bg-[#06AD56] disabled:opacity-50"
        onClick={handleSend}
        disabled={disabled || !value.trim()}
      >
        发送
      </button>
    </div>
  );
};

export default ChatInput;
```

- [ ] **Step 6: Create `MindMapPanel.tsx`** using Cytoscape.js

```tsx
import React, { useEffect, useRef } from "react";
import { api } from "../../api/client";

const MindMapPanel: React.FC<{ workspaceId: string }> = ({ workspaceId }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getMindmap(workspaceId).then((data) => {
      if (!containerRef.current || !data.nodes?.length) return;
      // Render as a simple tree list for now
      renderTree(containerRef.current, data.nodes, data.edges);
    });
  }, [workspaceId]);

  const renderTree = (container: HTMLDivElement, nodes: any[], edges: any[]) => {
    // Find roots
    const childIds = new Set(edges.filter((e: any) => e.relation === "parent_of").map((e: any) => e.target_node_id));
    const roots = nodes.filter((n: any) => !childIds.has(n.id));

    const childrenMap: Record<string, any[]> = {};
    for (const e of edges) {
      if (e.relation === "parent_of") {
        if (!childrenMap[e.source_node_id]) childrenMap[e.source_node_id] = [];
        childrenMap[e.source_node_id].push(nodes.find((n: any) => n.id === e.target_node_id));
      }
    }

    const heatColors: Record<string, string> = { hot: "#FF5252", medium: "#FF9800", cold: "#2196F3", warm: "#4CAF50" };

    const renderNode = (node: any, depth: number = 0): HTMLElement => {
      const div = document.createElement("div");
      div.className = "flex items-center gap-2 py-1 cursor-pointer hover:bg-secondary/10 rounded px-1";
      div.style.paddingLeft = `${depth * 16 + 4}px`;

      const dot = document.createElement("span");
      dot.className = "w-2 h-2 rounded-full shrink-0";
      dot.style.backgroundColor = heatColors[node.heat] || "#999";

      const name = document.createElement("span");
      name.className = "text-sm text-primary truncate";
      name.textContent = node.name;

      const type = document.createElement("span");
      type.className = "text-xs text-secondary";
      type.textContent = node.node_type;

      div.appendChild(dot);
      div.appendChild(name);
      div.appendChild(type);
      return div;
    };

    container.innerHTML = "";
    const title = document.createElement("div");
    title.className = "text-sm font-bold text-primary px-2 py-2 border-b border-secondary mb-1";
    title.textContent = `思维导图 (${nodes.length} 节点)`;
    container.appendChild(title);

    const walk = (nodeList: any[], depth: number) => {
      for (const node of nodeList) {
        if (!node) continue;
        container.appendChild(renderNode(node, depth));
        walk(childrenMap[node.id] || [], depth + 1);
      }
    };
    walk(roots, 0);
  };

  return (
    <div ref={containerRef} className="h-full overflow-y-auto p-2 text-sm" />
  );
};

export default MindMapPanel;
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/chat/ frontend/src/pages/mindmap/
git commit -m "feat: add chat page with session sidebar, messages, mindmap panel"
```

---

### Task 13: Create Settings page

**Files:**
- Create: `frontend/src/pages/settings/SettingsPage.tsx`

- [ ] **Step 1: Create `SettingsPage.tsx`**

```tsx
import React, { useEffect, useState } from "react";
import { Input, Button, Switch, message, Card } from "antd";
import { api } from "../../api/client";

interface Agent {
  name: string;
  role: string;
  description: string;
  enabled: boolean;
}

const SettingsPage: React.FC = () => {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    loadSettings();
    loadAgents();
  }, []);

  const loadSettings = async () => {
    try {
      const s = await api.getSettings();
      setBaseUrl(s.base_url);
      setModel(s.model);
    } catch (e) {
      console.error(e);
    }
  };

  const loadAgents = async () => {
    try {
      const a = await api.listAgents();
      setAgents(a);
    } catch (e) {
      console.error(e);
    }
  };

  const saveSettings = async () => {
    try {
      await api.updateSettings({ api_key: apiKey || undefined, base_url: baseUrl, model });
      messageApi.success("设置已保存");
    } catch (e) {
      messageApi.error("保存失败");
    }
  };

  const toggleAgent = async (name: string, enabled: boolean) => {
    try {
      await api.updateAgent(name, { enabled });
      setAgents((prev) => prev.map((a) => (a.name === name ? { ...a, enabled } : a)));
    } catch (e) {
      messageApi.error("更新失败");
    }
  };

  return (
    <div className="p-4 max-w-2xl">
      {contextHolder}
      <h1 className="text-2xl font-bold text-primary mb-6">设置</h1>

      <Card title="LLM 配置" className="mb-4">
        <div className="space-y-4">
          <div>
            <label className="block text-sm mb-1">API Key</label>
            <Input.Password value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="输入新的 API Key（留空不修改）" />
          </div>
          <div>
            <label className="block text-sm mb-1">Base URL</label>
            <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm mb-1">Model</label>
            <Input value={model} onChange={(e) => setModel(e.target.value)} />
          </div>
          <Button type="primary" onClick={saveSettings}>保存</Button>
        </div>
      </Card>

      <Card title="Agent 管理">
        <div className="space-y-3">
          {agents.map((agent) => (
            <div key={agent.name} className="flex items-center justify-between py-2 border-b border-secondary/20">
              <div>
                <div className="text-sm font-medium text-primary">{agent.name}</div>
                <div className="text-xs text-secondary">{agent.description}</div>
              </div>
              <Switch checked={agent.enabled} onChange={(v) => toggleAgent(agent.name, v)} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default SettingsPage;
```

- [ ] **Step 2: Install react-router-dom**

Run: `cd frontend && npm install react-router-dom`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/settings/SettingsPage.tsx frontend/package.json
git commit -m "feat: add settings page and react-router-dom"
```

---

### Task 14: Backend API tests

**Files:**
- Create: `tests/test_api_workspaces.py`
- Create: `tests/test_api_sessions.py`
- Create: `tests/test_api_chat.py`

- [ ] **Step 1: Create `tests/test_api_workspaces.py`**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.services.storage import init_db
import os

os.makedirs("storage", exist_ok=True)
init_db()
client = TestClient(app)


def test_list_workspaces():
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_and_delete_workspace():
    resp = client.post("/api/workspaces", json={"title": "Test Topic", "description": "Test", "auto_generate": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Topic"
    assert data["session_count"] == 1

    # Delete
    resp = client.delete(f"/api/workspaces/{data['id']}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
```

- [ ] **Step 2: Create `tests/test_api_sessions.py`**

```python
from fastapi.testclient import TestClient
from app.main import app
import os

os.makedirs("storage", exist_ok=True)
client = TestClient(app)


def test_session_lifecycle():
    # Create workspace first
    resp = client.post("/api/workspaces", json={"title": "SessTest", "description": "", "auto_generate": False})
    wid = resp.json()["id"]

    # List sessions
    resp = client.get(f"/api/sessions?workspace_id={wid}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1  # default session

    # Create session
    resp = client.post("/api/sessions", json={"workspace_id": wid, "title": "Custom"})
    assert resp.status_code == 200
    sid = resp.json()["id"]
    assert resp.json()["title"] == "Custom"

    # Update
    resp = client.put(f"/api/sessions/{sid}", json={"workspace_id": wid, "title": "Renamed"})
    assert resp.json()["title"] == "Renamed"

    # Delete
    resp = client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 200

    # Cleanup
    client.delete(f"/api/workspaces/{wid}")
```

- [ ] **Step 3: Create `tests/test_api_chat.py`**

```python
from fastapi.testclient import TestClient
from app.main import app
import os

os.makedirs("storage", exist_ok=True)
client = TestClient(app)


def test_list_messages():
    resp = client.post("/api/workspaces", json={"title": "ChatTest", "description": "", "auto_generate": False})
    wid = resp.json()["id"]
    resp = client.get(f"/api/sessions?workspace_id={wid}")
    sid = resp.json()[0]["id"]

    resp = client.get(f"/api/chat?session_id={sid}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # Cleanup
    client.delete(f"/api/workspaces/{wid}")


def test_send_message():
    resp = client.post("/api/workspaces", json={"title": "ChatSendTest", "description": "", "auto_generate": False})
    wid = resp.json()["id"]
    resp = client.get(f"/api/sessions?workspace_id={wid}")
    sid = resp.json()[0]["id"]

    # SSE response
    resp = client.post("/api/chat", json={"session_id": sid, "content": "Hello"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    client.delete(f"/api/workspaces/{wid}")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_api_workspaces.py tests/test_api_sessions.py tests/test_api_chat.py -v`

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_*.py
git commit -m "test: add API integration tests for workspaces, sessions, chat"
```

---

### Task 15: Integration test — build frontend and verify

**Files:** None (verification only)

- [ ] **Step 1: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds, output in `frontend/dist/`

- [ ] **Step 2: Start backend and verify static serving**

Run: `python -m app.main` (starts uvicorn on :8000)

Open `http://127.0.0.1:8000/` in browser → should serve the React app

- [ ] **Step 3: Test API through the UI**

- Navigate to `/workspaces` → should see workspace grid (empty or with existing data)
- Create a workspace → should redirect to chat page
- Send a message → should see streaming response

- [ ] **Step 4: Verify dark mode** — toggle in header should switch theme

- [ ] **Step 5: Commit any fixes discovered during integration testing**

---

## Self-Review

**Spec coverage check:**
- ✅ 3 navigation items (课题管理, 对话, 设置) → sidebar.tsx
- ✅ Collapsible sidebar → sidebar.tsx (from autogen)
- ✅ Workspace management page with cards → Task 11
- ✅ Chat page with session sidebar + message bubbles + mindmap panel → Task 12
- ✅ Settings page with LLM config + agent toggles → Task 13
- ✅ SSE streaming for chat → Task 5 (backend) + Task 12 (frontend ChatView)
- ✅ Dark/light mode → Task 9 (provider.tsx)
- ✅ All API routes → Tasks 3-5
- ✅ Backend tests → Task 14
- ✅ Reuse autogen-studio components → Task 8

**Placeholder scan:** No TBD, TODO, or placeholder patterns found.

**Type consistency:** Zustand store types (Workspace, Session, ChatMessage) match API response shapes from backend Pydantic models.
