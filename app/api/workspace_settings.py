"""Per-workspace settings API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.services.storage import get_session
from app.models.workspace_settings import WorkspaceSettings, WorkspaceAgentOverride
from app.models.agent_config import AgentConfig
from app.models.topic import Topic
from app.config import settings as app_settings

router = APIRouter(prefix="/workspaces", tags=["workspace-settings"])


# --- schemas ---

class WSLlmSettings(BaseModel):
    model: str = ""


class AgentWithOverrides(BaseModel):
    name: str
    role: str
    system_prompt: str
    description: str
    model: str
    color: str
    enabled: bool


class AgentOverrideUpdate(BaseModel):
    enabled: bool | None = None
    system_prompt: str | None = None
    model: str | None = None


# --- helpers ---

def _get_ws_settings(db: Session, workspace_id: str) -> WorkspaceSettings:
    ws = db.exec(
        select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id)
    ).first()
    if ws is None:
        ws = WorkspaceSettings(workspace_id=workspace_id)
        db.add(ws)
        db.commit()
        db.refresh(ws)
    return ws


def _get_merged_model(db: Session, workspace_id: str) -> str:
    ws = _get_ws_settings(db, workspace_id)
    return ws.model or app_settings.LLM_MODEL


def _get_merged_agents(db: Session, workspace_id: str) -> list[AgentWithOverrides]:
    agents = db.exec(select(AgentConfig)).all()
    overrides = db.exec(
        select(WorkspaceAgentOverride).where(
            WorkspaceAgentOverride.workspace_id == workspace_id
        )
    ).all()
    override_map: dict[str, WorkspaceAgentOverride] = {}
    for o in overrides:
        override_map[o.agent_name] = o

    result: list[AgentWithOverrides] = []
    for a in agents:
        o = override_map.get(a.name)
        result.append(AgentWithOverrides(
            name=a.name,
            role=a.role,
            system_prompt=o.system_prompt if (o and o.system_prompt is not None) else a.system_prompt,
            description=a.description or "",
            model=o.model if (o and o.model is not None) else (a.model or ""),
            color=a.color or "",
            enabled=o.enabled if (o and o.enabled is not None) else a.enabled,
        ))
    return result


# --- routes ---

@router.get("/{workspace_id}/settings", response_model=WSLlmSettings)
def get_settings(workspace_id: str, db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")
    return WSLlmSettings(model=_get_merged_model(db, workspace_id))


@router.put("/{workspace_id}/settings", response_model=WSLlmSettings)
def update_settings(workspace_id: str, body: WSLlmSettings, db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")
    ws = _get_ws_settings(db, workspace_id)
    ws.model = body.model
    db.add(ws)
    db.commit()
    return WSLlmSettings(model=body.model)


@router.get("/{workspace_id}/settings/agents", response_model=list[AgentWithOverrides])
def list_agents(workspace_id: str, db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")
    return _get_merged_agents(db, workspace_id)


@router.put("/{workspace_id}/settings/agents/{name}", response_model=AgentWithOverrides)
def update_agent(workspace_id: str, name: str, body: AgentOverrideUpdate,
                 db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")

    global_agent = db.exec(
        select(AgentConfig).where(AgentConfig.name == name)
    ).first()
    if not global_agent:
        raise HTTPException(404, f"Agent {name} not found")

    override = db.exec(
        select(WorkspaceAgentOverride).where(
            WorkspaceAgentOverride.workspace_id == workspace_id,
            WorkspaceAgentOverride.agent_name == name,
        )
    ).first()

    if override is None:
        override = WorkspaceAgentOverride(workspace_id=workspace_id, agent_name=name)
        db.add(override)

    if body.enabled is not None:
        override.enabled = body.enabled
    if body.system_prompt is not None:
        override.system_prompt = body.system_prompt
    if body.model is not None:
        override.model = body.model

    db.commit()
    db.refresh(override)

    return AgentWithOverrides(
        name=global_agent.name,
        role=global_agent.role,
        system_prompt=override.system_prompt if override.system_prompt is not None else global_agent.system_prompt,
        description=global_agent.description or "",
        model=override.model if override.model is not None else (global_agent.model or ""),
        color=global_agent.color or "",
        enabled=override.enabled if override.enabled is not None else global_agent.enabled,
    )
