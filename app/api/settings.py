"""Settings and agent configuration API routes."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from pydantic import BaseModel

from app.services.storage import get_session
from app.models.agent_config import AgentConfig
from app.config import settings as app_settings

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
    import os

    env_path = ".env"
    lines: list[str] = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    if body.api_key is not None:
        _upsert_env_line(lines, "DEEPSEEK_API_KEY", body.api_key)
        app_settings.DEEPSEEK_API_KEY = body.api_key
    if body.base_url is not None:
        _upsert_env_line(lines, "DEEPSEEK_BASE_URL", body.base_url)
        app_settings.DEEPSEEK_BASE_URL = body.base_url
    if body.model is not None:
        _upsert_env_line(lines, "LLM_MODEL", body.model)
        app_settings.LLM_MODEL = body.model

    with open(env_path, "w") as f:
        f.writelines(lines)

    return LLMSettingsOut(
        api_key="***" if app_settings.DEEPSEEK_API_KEY else "",
        base_url=app_settings.DEEPSEEK_BASE_URL,
        model=app_settings.LLM_MODEL,
    )


def _upsert_env_line(lines: list[str], key: str, value: str) -> None:
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            return
    lines.append(f"{key}={value}\n")


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
