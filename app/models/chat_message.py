import uuid
from datetime import datetime, UTC
from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
    )
    session_id: str = Field(foreign_key="sessions.id", index=True)
    role: str = Field(default="user")
    content: str = Field(default="")
    agent_name: str = Field(default="")
    node_id: str | None = Field(default=None, foreign_key="map_nodes.id")
    review_status: str | None = Field(default=None)       # null | "passed" | "failed" | "supplemented"
    review_score: int | None = Field(default=None)         # 1-5
    review_summary: str | None = Field(default=None)       # Topic Agent 审查摘要
    redo_count: int = Field(default=0)                     # 该消息重做次数
    task_id: str | None = Field(default=None, index=True)
    task_type: str | None = Field(default=None, index=True)
    root_user_message_id: str | None = Field(default=None, index=True)
    trigger_message_id: str | None = Field(default=None)
    target_message_id: str | None = Field(default=None, index=True)
    dispatch_depth: int = Field(default=0)
    dispatch_processed: bool = Field(default=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
