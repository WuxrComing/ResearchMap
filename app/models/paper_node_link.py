import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class PaperNodeLink(SQLModel, table=True):
    __tablename__ = "paper_node_links"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    paper_id: str = Field(foreign_key="papers.id", index=True)
    node_id: str = Field(foreign_key="map_nodes.id", index=True)
    relation: str = Field(default="belongs_to")
    confidence: float = Field(default=1.0)
    reason: str = Field(default="")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
