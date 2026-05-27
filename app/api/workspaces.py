"""Workspace (topic) CRUD API routes."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, delete as sm_delete
from pydantic import BaseModel

from app.services.storage import get_engine, get_session
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge

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
    result: list[WorkspaceOut] = []
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
    topic_id, session_id = TopicBuildWorker.create_empty_workspace(
        body.title, body.description
    )
    engine = get_engine()
    with Session(engine) as db:
        t = db.get(Topic, topic_id)
        if not t:
            raise HTTPException(500, "Workspace creation failed")
        return WorkspaceOut(
            id=t.id, title=t.title, description=t.description or "",
            session_count=1,
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else "",
        )


@router.put("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(workspace_id: str, body: WorkspaceCreate,
                     db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
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
            raise HTTPException(404, "Workspace not found")
        session_ids = db.exec(
            select(SessionModel.id).where(
                SessionModel.workspace_id == workspace_id
            )
        ).all()
        for sid in session_ids:
            db.exec(sm_delete(ChatMessage).where(
                ChatMessage.session_id == sid
            ))
        db.exec(sm_delete(SessionModel).where(
            SessionModel.workspace_id == workspace_id
        ))
        db.exec(sm_delete(MapEdge).where(
            MapEdge.topic_id == workspace_id
        ))
        db.exec(sm_delete(MapNode).where(
            MapNode.topic_id == workspace_id
        ))
        db.delete(t)
        db.commit()
    return {"ok": True}
