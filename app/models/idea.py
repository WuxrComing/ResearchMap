import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class Idea(SQLModel, table=True):
    __tablename__ = "ideas"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    topic_id: str = Field(foreign_key="topics.id", index=True)
    node_id: str | None = Field(default=None, foreign_key="map_nodes.id")
    name: str = Field(index=True)
    description: str = Field(default="")
    origin_paper_ids: str = Field(default="[]")
    target_module: str = Field(default="")
    expected_gain: str = Field(default="[]")
    implementation_cost: str = Field(default="")
    risk: str = Field(default="")
    priority: str = Field(default="medium")
    status: str = Field(default="candidate")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
