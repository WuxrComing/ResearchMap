import uuid
from datetime import datetime
from sqlmodel import Field, SQLModel


class AgentConfig(SQLModel, table=True):
    __tablename__ = "agent_configs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str = Field(index=True)
    role: str = Field(default="assistant")  # assistant / paper / transfer / memory
    system_prompt: str = Field(default="")
    description: str = Field(default="")
    model: str = Field(default="")  # empty = use default model
    color: str = Field(default="#07C160")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow,
                                  sa_column_kwargs={"onupdate": lambda: datetime.utcnow()})
