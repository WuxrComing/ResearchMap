import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class Topic(SQLModel, table=True):
    __tablename__ = "topics"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    title: str = Field(index=True)
    description: str = Field(default="")
    status: str = Field(default="active")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
