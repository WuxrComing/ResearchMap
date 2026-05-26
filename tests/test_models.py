import uuid
import pytest
from sqlmodel import Session
from app.services.storage import get_engine, init_db
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from app.models.paper import Paper
from app.models.paper_node_link import PaperNodeLink
from app.models.idea import Idea
from app.models.negative_memory import NegativeMemory
from app.models.chat_message import ChatMessage


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


def test_create_topic():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(
            id=uuid.uuid4().hex,
            title="Test Topic",
            description="Test description",
        )
        db.add(topic)
        db.commit()
        assert topic.id is not None
        assert topic.title == "Test Topic"


def test_create_session():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(
            id=uuid.uuid4().hex,
            title="Test Topic",
        )
        db.add(topic)
        db.commit()

        session = SessionModel(
            id=uuid.uuid4().hex,
            workspace_id=topic.id,
            title="Test Session",
        )
        db.add(session)
        db.commit()
        assert session.id is not None
        assert session.workspace_id == topic.id


def test_create_map_node():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(id=uuid.uuid4().hex, title="Test")
        db.add(topic)
        db.commit()

        node = MapNode(
            id=uuid.uuid4().hex,
            topic_id=topic.id,
            name="Core Problem",
            node_type="problem",
            summary="A test problem node",
        )
        db.add(node)
        db.commit()
        assert node.name == "Core Problem"


def test_create_map_edge():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(id=uuid.uuid4().hex, title="Test")
        db.add(topic)
        db.commit()

        root = MapNode(
            id=uuid.uuid4().hex, topic_id=topic.id, name="Root", node_type="root"
        )
        child = MapNode(
            id=uuid.uuid4().hex,
            topic_id=topic.id,
            name="Child",
            node_type="problem",
        )
        db.add_all([root, child])
        db.commit()

        edge = MapEdge(
            id=uuid.uuid4().hex,
            topic_id=topic.id,
            source_node_id=root.id,
            target_node_id=child.id,
            relation="parent_of",
        )
        db.add(edge)
        db.commit()
        assert edge.source_node_id == root.id


def test_create_paper():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(id=uuid.uuid4().hex, title="Test")
        db.add(topic)
        db.commit()

        paper = Paper(
            id=uuid.uuid4().hex,
            topic_id=topic.id,
            title="Test Paper",
            source="arXiv",
        )
        db.add(paper)
        db.commit()
        assert paper.title == "Test Paper"


def test_create_chat_message():
    init_db()
    engine = get_engine()
    with Session(engine) as db:
        topic = Topic(id=uuid.uuid4().hex, title="Test")
        db.add(topic)
        db.commit()

        session = SessionModel(
            id=uuid.uuid4().hex, workspace_id=topic.id, title="Chat"
        )
        db.add(session)
        db.commit()

        msg = ChatMessage(
            id=uuid.uuid4().hex,
            session_id=session.id,
            role="user",
            content="Hello",
        )
        db.add(msg)
        db.commit()
        assert msg.content == "Hello"


def test_chat_message_accepts_runtime_lineage_fields():
    from app.models.chat_message import ChatMessage

    msg = ChatMessage(
        session_id="sess",
        role="assistant",
        content="reply",
        agent_name="Paper Agent",
        task_id="task_1",
        task_type="dispatch",
        root_user_message_id="root_1",
        trigger_message_id="trigger_1",
        target_message_id=None,
        dispatch_depth=2,
    )

    assert msg.task_id == "task_1"
    assert msg.task_type == "dispatch"
    assert msg.root_user_message_id == "root_1"
    assert msg.trigger_message_id == "trigger_1"
    assert msg.target_message_id is None
    assert msg.dispatch_depth == 2


def test_all_tables_created():
    init_db()
    engine = get_engine()
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected = [
        "topics",
        "sessions",
        "map_nodes",
        "map_edges",
        "papers",
        "paper_node_links",
        "ideas",
        "negative_memories",
        "chat_messages",
    ]
    for table in expected:
        assert table in tables, f"Table {table} not found in {tables}"
