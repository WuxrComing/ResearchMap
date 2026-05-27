"""Session CRUD API routes."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, delete as sm_delete
from pydantic import BaseModel

from app.services.storage import get_session
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage

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
def update_session(session_id: str, body: SessionCreate,
                   db: Session = Depends(get_session)):
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
