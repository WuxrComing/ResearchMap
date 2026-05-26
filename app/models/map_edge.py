import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class MapEdge(SQLModel, table=True):
    __tablename__ = "map_edges"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    topic_id: str = Field(foreign_key="topics.id", index=True)
    source_node_id: str = Field(foreign_key="map_nodes.id")
    target_node_id: str = Field(foreign_key="map_nodes.id")
    relation: str = Field(default="parent_of")
    weight: float = Field(default=1.0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
