"""Chat API routes with SSE streaming."""
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from app.services.storage import get_engine, get_session
from app.models.chat_message import ChatMessage
from app.models.session import Session as SessionModel
from app.services.sse_adapter import get_sse_adapter

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
    msg_created_at = None
    with Session(engine) as db:
        msg = ChatMessage(
            id=msg_id, session_id=body.session_id,
            role="user", content=body.content,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        msg_created_at = msg.created_at.isoformat() if msg.created_at else None

    # Submit to runtime (triggers agent pipeline in background threads)
    adapter.submit_message(body.session_id, msg_id)
    adapter.start_draining(body.session_id)

    async def event_generator():
        # Send the initial user message as first event
        yield {
            "event": "message",
            "data": json.dumps({
                "id": msg_id, "role": "user", "content": body.content,
                "agent_name": None, "review_status": None,
                "created_at": msg_created_at,
            }, default=str),
        }

        async for event in adapter.event_stream(body.session_id):
            if await request.is_disconnected():
                break
            yield {"event": event.event, "data": event.data}

    return EventSourceResponse(event_generator())


@router.post("/cancel")
def cancel_message(body: CancelRequest):
    adapter = get_sse_adapter()
    adapter.cancel_root(body.session_id, body.root_user_message_id)
    return {"ok": True}
