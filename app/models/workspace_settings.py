import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class WorkspaceSettings(SQLModel, table=True):
    __tablename__ = "workspace_settings"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    workspace_id: str = Field(foreign_key="topics.id", unique=True, index=True)
    model: str = Field(default="")  # empty = use global default
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )


class WorkspaceAgentOverride(SQLModel, table=True):
    __tablename__ = "workspace_agent_overrides"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    workspace_id: str = Field(foreign_key="topics.id", index=True)
    agent_name: str = Field(index=True)
    role: str | None = Field(default=None)  # for custom agents; null = use global
    description: str | None = Field(default=None)  # for custom agents
    color: str | None = Field(default=None)  # for custom agents
    enabled: bool | None = Field(default=None)  # null = use global default
    system_prompt: str | None = Field(default=None)  # null = use global default
    model: str | None = Field(default=None)  # null = use global default
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
