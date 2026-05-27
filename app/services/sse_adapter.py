"""Bridges SessionRuntime to asyncio SSE queues for FastAPI."""
import asyncio
import json

from app.services.storage import get_engine
from app.services.agent_runtime import SessionRuntime


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
