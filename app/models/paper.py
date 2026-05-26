import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class Paper(SQLModel, table=True):
    __tablename__ = "papers"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    topic_id: str = Field(foreign_key="topics.id", index=True)
    title: str = Field(index=True)
    authors: str = Field(default="[]")
    year: int | None = Field(default=None)
    source: str = Field(default="")
    url: str = Field(default="")
    abstract: str = Field(default="")
    summary: str = Field(default="")
    core_idea: str = Field(default="")
    design_philosophy: str = Field(default="")
    mechanism: str = Field(default="")
    evidence_quality: str = Field(default="")
    transfer_potential: str = Field(default="")
    risk_level: str = Field(default="")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
