"""Per-workspace settings API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, delete as sm_delete
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
    is_custom: bool = False  # True if this agent only exists in this workspace


class AgentUpdate(BaseModel):
    enabled: bool | None = None
    system_prompt: str | None = None
    model: str | None = None
    description: str | None = None


class AgentCreate(BaseModel):
    name: str
    role: str = "assistant"
    system_prompt: str = ""
    description: str = ""
    color: str = "#07C160"


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
    global_agents = db.exec(select(AgentConfig)).all()
    overrides = db.exec(
        select(WorkspaceAgentOverride).where(
            WorkspaceAgentOverride.workspace_id == workspace_id
        )
    ).all()
    override_map: dict[str, WorkspaceAgentOverride] = {}
    custom_agents: list[WorkspaceAgentOverride] = []
    for o in overrides:
        # Check if this is a custom agent (no matching global)
        global_match = next((a for a in global_agents if a.name == o.agent_name), None)
        if global_match is None:
            custom_agents.append(o)
        else:
            override_map[o.agent_name] = o

    result: list[AgentWithOverrides] = []
    for a in global_agents:
        o = override_map.get(a.name)
        result.append(AgentWithOverrides(
            name=a.name,
            role=a.role,
            system_prompt=o.system_prompt if (o and o.system_prompt is not None) else a.system_prompt,
            description=o.description if (o and o.description is not None) else (a.description or ""),
            model=o.model if (o and o.model is not None) else (a.model or ""),
            color=o.color if (o and o.color is not None) else (a.color or ""),
            enabled=o.enabled if (o and o.enabled is not None) else a.enabled,
            is_custom=False,
        ))

    for o in custom_agents:
        result.append(AgentWithOverrides(
            name=o.agent_name,
            role=o.role or "assistant",
            system_prompt=o.system_prompt or "",
            description=o.description or "",
            model=o.model or "",
            color=o.color or "#07C160",
            enabled=o.enabled if o.enabled is not None else True,
            is_custom=True,
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


@router.post("/{workspace_id}/settings/agents", response_model=AgentWithOverrides)
def create_agent(workspace_id: str, body: AgentCreate, db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")

    # Check name collision with global agents + workspace overrides
    global_agent = db.exec(
        select(AgentConfig).where(AgentConfig.name == body.name)
    ).first()
    existing_override = db.exec(
        select(WorkspaceAgentOverride).where(
            WorkspaceAgentOverride.workspace_id == workspace_id,
            WorkspaceAgentOverride.agent_name == body.name,
        )
    ).first()
    if global_agent or existing_override:
        raise HTTPException(400, f"Agent '{body.name}' already exists")

    agent = WorkspaceAgentOverride(
        workspace_id=workspace_id,
        agent_name=body.name,
        role=body.role,
        description=body.description,
        color=body.color,
        system_prompt=body.system_prompt,
        enabled=True,
        model="",
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    return AgentWithOverrides(
        name=agent.agent_name,
        role=agent.role or "assistant",
        system_prompt=agent.system_prompt or "",
        description=agent.description or "",
        model=agent.model or "",
        color=agent.color or "#07C160",
        enabled=True,
        is_custom=True,
    )


@router.put("/{workspace_id}/settings/agents/{name}", response_model=AgentWithOverrides)
def update_agent(workspace_id: str, name: str, body: AgentUpdate,
                 db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")

    override = db.exec(
        select(WorkspaceAgentOverride).where(
            WorkspaceAgentOverride.workspace_id == workspace_id,
            WorkspaceAgentOverride.agent_name == name,
        )
    ).first()

    if override is None:
        global_agent = db.exec(
            select(AgentConfig).where(AgentConfig.name == name)
        ).first()
        if not global_agent:
            raise HTTPException(404, f"Agent {name} not found")
        override = WorkspaceAgentOverride(workspace_id=workspace_id, agent_name=name)
        db.add(override)

    if body.enabled is not None:
        override.enabled = body.enabled
    if body.system_prompt is not None:
        override.system_prompt = body.system_prompt
    if body.model is not None:
        override.model = body.model
    if body.description is not None:
        override.description = body.description

    db.commit()
    db.refresh(override)

    # Determine merged values
    is_custom = override.role is not None
    global_agent = db.exec(
        select(AgentConfig).where(AgentConfig.name == name)
    ).first()
    return AgentWithOverrides(
        name=override.agent_name,
        role=override.role or (global_agent.role if global_agent else "assistant"),
        system_prompt=override.system_prompt if override.system_prompt is not None else (global_agent.system_prompt if global_agent else ""),
        description=override.description if override.description is not None else (global_agent.description if global_agent else ""),
        model=override.model if override.model is not None else (global_agent.model if global_agent else ""),
        color=override.color or (global_agent.color if global_agent else "#07C160"),
        enabled=override.enabled if override.enabled is not None else (global_agent.enabled if global_agent else True),
        is_custom=is_custom,
    )


@router.delete("/{workspace_id}/settings/agents/{name}")
def delete_agent(workspace_id: str, name: str, db: Session = Depends(get_session)):
    t = db.get(Topic, workspace_id)
    if not t:
        raise HTTPException(404, "Workspace not found")

    result = db.exec(
        sm_delete(WorkspaceAgentOverride).where(
            WorkspaceAgentOverride.workspace_id == workspace_id,
            WorkspaceAgentOverride.agent_name == name,
        )
    )
    db.commit()

    global_agent = db.exec(
        select(AgentConfig).where(AgentConfig.name == name)
    ).first()
    if global_agent:
        return {"ok": True, "note": "Workspace override removed; global agent still exists"}

    if result.rowcount == 0:
        raise HTTPException(404, f"Agent {name} not found in this workspace")
    return {"ok": True}
