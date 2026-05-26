from sqlmodel import SQLModel, Session, create_engine
from app.config import settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            f"sqlite:///{settings.DATABASE_PATH}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def init_db():
    import app.models  # noqa: F401  ensure all models registered with SQLModel.metadata
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _migrate_agent_config_description(engine)
    _migrate_chat_message_runtime_metadata(engine)
    _init_fts5(engine)
    _seed_agents(engine)
    _refresh_builtin_agent_prompts(engine)


def _init_fts5(engine):
    import sqlalchemy

    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
                title, description, content='topics', content_rowid='rowid'
            )
        """))
        conn.execute(sqlalchemy.text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS map_nodes_fts USING fts5(
                name, summary, content='map_nodes', content_rowid='rowid'
            )
        """))
        conn.execute(sqlalchemy.text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(
                content, content='chat_messages', content_rowid='rowid'
            )
        """))

        _create_fts_triggers(conn, "topics", ["title", "description"])
        _create_fts_triggers(conn, "map_nodes", ["name", "summary"])
        _create_fts_triggers(conn, "chat_messages", ["content"])

        conn.commit()


def _migrate_agent_config_description(engine):
    """Add description column to agent_configs if it doesn't exist."""
    import sqlalchemy

    with engine.connect() as conn:
        result = conn.execute(
            sqlalchemy.text("PRAGMA table_info('agent_configs')")
        )
        columns = {row[1] for row in result.fetchall()}
        if "description" not in columns:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE agent_configs ADD COLUMN description TEXT DEFAULT ''"
                )
            )
            conn.commit()


def _migrate_chat_message_runtime_metadata(engine):
    """Add runtime lineage columns to chat_messages if they don't exist."""
    import sqlalchemy

    columns_to_add = {
        "task_id": "ALTER TABLE chat_messages ADD COLUMN task_id TEXT",
        "task_type": "ALTER TABLE chat_messages ADD COLUMN task_type TEXT",
        "root_user_message_id": (
            "ALTER TABLE chat_messages ADD COLUMN root_user_message_id TEXT"
        ),
        "trigger_message_id": (
            "ALTER TABLE chat_messages ADD COLUMN trigger_message_id TEXT"
        ),
        "target_message_id": (
            "ALTER TABLE chat_messages ADD COLUMN target_message_id TEXT"
        ),
        "dispatch_depth": (
            "ALTER TABLE chat_messages ADD COLUMN dispatch_depth INTEGER DEFAULT 0"
        ),
    }
    indexes_to_create = [
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_task_id "
        "ON chat_messages (task_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_task_type "
        "ON chat_messages (task_type)",
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_root_user_message_id "
        "ON chat_messages (root_user_message_id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_target_message_id "
        "ON chat_messages (target_message_id)",
    ]

    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text("PRAGMA table_info('chat_messages')"))
        existing_columns = {row[1] for row in result.fetchall()}
        for column, statement in columns_to_add.items():
            if column not in existing_columns:
                conn.execute(sqlalchemy.text(statement))
        for statement in indexes_to_create:
            conn.execute(sqlalchemy.text(statement))
        conn.commit()


def _seed_agents(engine):
    """Insert default agent configs if table is empty."""
    from sqlmodel import Session, select
    from app.models.agent_config import AgentConfig
    from app.agents.definitions import DEFAULT_AGENTS

    with Session(engine) as db:
        count = db.exec(select(AgentConfig)).first()
        if count is not None:
            return
        for a in DEFAULT_AGENTS:
            db.add(AgentConfig(
                name=a["name"], role=a["role"], system_prompt=a["system_prompt"],
                description=a.get("description", ""),
                model=a["model"], color=a["color"], enabled=a["enabled"],
            ))
        db.commit()


def _refresh_builtin_agent_prompts(engine):
    """Update old built-in prompts without clobbering customized agents."""
    from sqlmodel import Session, select
    from app.models.agent_config import AgentConfig
    from app.agents.definitions import DEFAULT_AGENTS

    default_by_name = {a["name"]: a for a in DEFAULT_AGENTS}
    old_topic_marker = "1. **直接回答**：当用户没有指定 Agent 时，你直接回答用户问题。"

    with Session(engine) as db:
        topic = db.exec(
            select(AgentConfig).where(AgentConfig.name == "Topic Agent")
        ).first()
        if topic and old_topic_marker in topic.system_prompt:
            default_topic = default_by_name["Topic Agent"]
            topic.system_prompt = default_topic["system_prompt"]
            topic.description = default_topic.get("description", topic.description)
            db.add(topic)
            db.commit()


def _create_fts_triggers(conn, table, columns):
    import sqlalchemy
    col_str = ", ".join(columns)

    conn.execute(sqlalchemy.text(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_fts_insert AFTER INSERT ON {table}
        BEGIN
            INSERT INTO {table}_fts(rowid, {col_str})
            VALUES (new.rowid, {', '.join(f'new.{c}' for c in columns)});
        END
    """))
    conn.execute(sqlalchemy.text(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_fts_delete AFTER DELETE ON {table}
        BEGIN
            INSERT INTO {table}_fts({table}_fts, rowid, {col_str})
            VALUES ('delete', old.rowid, {', '.join(f'old.{c}' for c in columns)});
        END
    """))
    conn.execute(sqlalchemy.text(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_fts_update AFTER UPDATE ON {table}
        BEGIN
            INSERT INTO {table}_fts({table}_fts, rowid, {col_str})
            VALUES ('delete', old.rowid, {', '.join(f'old.{c}' for c in columns)});
            INSERT INTO {table}_fts(rowid, {col_str})
            VALUES (new.rowid, {', '.join(f'new.{c}' for c in columns)});
        END
    """))


def get_session():
    engine = get_engine()
    with Session(engine) as session:
        yield session
