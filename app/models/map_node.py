import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class MapNode(SQLModel, table=True):
    __tablename__ = "map_nodes"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    topic_id: str = Field(foreign_key="topics.id", index=True)
    name: str = Field(index=True)
    node_type: str = Field(default="root")
    summary: str = Field(default="")
    heat: str = Field(default="medium")
    maturity: str = Field(default="emerging")
    evidence_strength: str = Field(default="weak")
    paper_count: int = Field(default=0)
    position_x: float | None = Field(default=None)
    position_y: float | None = Field(default=None)
    status: str = Field(default="active")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
