import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class NegativeMemory(SQLModel, table=True):
    __tablename__ = "negative_memories"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    topic_id: str = Field(foreign_key="topics.id", index=True)
    title: str = Field(index=True)
    description: str = Field(default="")
    failed_reason: str = Field(default="")
    avoid_rule: str = Field(default="")
    related_nodes: str = Field(default="[]")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
