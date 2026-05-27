import uuid
import pytest
from sqlmodel import Session, text
from app.services.storage import get_engine, init_db
from app.models.topic import Topic


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    import app.services.storage as storage

    if storage._engine is not None:
        storage._engine.dispose()
    storage._engine = None
    monkeypatch.setattr(storage.settings, "DATABASE_PATH", str(tmp_path / "test.db"))

    yield

    if storage._engine is not None:
        storage._engine.dispose()
    storage._engine = None


def test_fts5_tables_exist():
    init_db()
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'")
        )
        fts_tables = [row[0] for row in result.fetchall()]
        assert "topics_fts" in fts_tables
        assert "map_nodes_fts" in fts_tables
        assert "chat_messages_fts" in fts_tables


def test_chat_message_runtime_lineage_columns_exist():
    init_db()
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info('chat_messages')"))
        columns = {row[1] for row in result.fetchall()}

    assert "task_id" in columns
    assert "task_type" in columns
    assert "root_user_message_id" in columns
    assert "trigger_message_id" in columns
    assert "target_message_id" in columns
    assert "dispatch_depth" in columns
    assert "dispatch_processed" in columns


def test_chat_message_runtime_lineage_indexes_exist_on_migrated_table():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT,
                content TEXT,
                agent_name TEXT,
                node_id TEXT,
                review_status TEXT,
                review_score INTEGER,
                review_summary TEXT,
                redo_count INTEGER,
                created_at DATETIME
            )
        """))
        conn.commit()

    init_db()

    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA index_list('chat_messages')"))
        index_names = {row[1] for row in result.fetchall()}

    assert "ix_chat_messages_task_id" in index_names
    assert "ix_chat_messages_task_type" in index_names
    assert "ix_chat_messages_root_user_message_id" in index_names
    assert "ix_chat_messages_target_message_id" in index_names
    assert "ix_chat_messages_dispatch_processed" in index_names


def test_chat_message_dispatch_processed_migrates_existing_table_with_default():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT,
                content TEXT,
                agent_name TEXT,
                node_id TEXT,
                review_status TEXT,
                review_score INTEGER,
                review_summary TEXT,
                redo_count INTEGER,
                created_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO chat_messages (
                id, session_id, role, content, agent_name, redo_count
            ) VALUES (
                'msg-1', 'session-1', 'user', 'hello', '', 0
            )
        """))
        conn.commit()

    init_db()

    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info('chat_messages')"))
        columns = {row[1]: row for row in result.fetchall()}
        dispatch_processed = conn.execute(
            text("SELECT dispatch_processed FROM chat_messages WHERE id = 'msg-1'")
        ).scalar_one()

    assert "dispatch_processed" in columns
    assert dispatch_processed == 0


def test_fts5_insert_trigger():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(
            id=uuid.uuid4().hex,
            title="FTS Test Topic",
            description="Testing full-text search",
        )
        db.add(topic)
        db.commit()

        with engine.connect() as conn:
            topic_rowid = conn.execute(
                text("SELECT rowid FROM topics WHERE id = :topic_id"),
                {"topic_id": topic.id},
            ).scalar_one()
            result = conn.execute(
                text("SELECT rowid FROM topics_fts WHERE topics_fts MATCH 'Testing'")
            )
            rowids = [row[0] for row in result.fetchall()]

        assert topic_rowid in rowids
