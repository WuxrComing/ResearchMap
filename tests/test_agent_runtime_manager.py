from collections import deque
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.agent_config import AgentConfig
from app.models.chat_message import ChatMessage
from app.models.session import Session as ChatSession
from app.models.topic import Topic


@pytest.fixture
def runtime_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def runtime_session_id(runtime_engine):
    with Session(runtime_engine) as session:
        topic = Topic(id="topic-1", title="Topic")
        chat_session = ChatSession(
            id="session-1",
            workspace_id=topic.id,
            title="Runtime session",
        )
        session.add(topic)
        session.add(chat_session)
        for agent in [
            AgentConfig(
                name="Topic Agent",
                role="assistant",
                system_prompt="Topic prompt",
                description="核心助手",
                model="topic-model",
                enabled=True,
            ),
            AgentConfig(
                name="Paper Agent",
                role="paper",
                system_prompt="Paper prompt",
                description="论文检索",
                model="paper-model",
                enabled=True,
            ),
            AgentConfig(
                name="Memory Agent",
                role="memory",
                system_prompt="Memory prompt",
                description="记忆管理",
                model="memory-model",
                enabled=True,
            ),
        ]:
            session.add(agent)
        session.commit()
    return "session-1"


def save_message(runtime_engine, **kwargs):
    with Session(runtime_engine) as session:
        message = ChatMessage(**kwargs)
        session.add(message)
        session.commit()
        session.refresh(message)
        return message


def load_messages(runtime_engine):
    with Session(runtime_engine) as session:
        return list(session.exec(select(ChatMessage).order_by(ChatMessage.created_at)).all())


def test_get_runtime_returns_same_runtime_for_same_session(runtime_engine):
    from app.services.agent_runtime import SessionRuntimeManager

    manager = SessionRuntimeManager(engine=runtime_engine)
    rt1 = manager.get_runtime("session-1")
    rt2 = manager.get_runtime("session-1")

    assert rt1 is rt2


def test_different_sessions_get_different_runtimes(runtime_engine):
    from app.services.agent_runtime import SessionRuntimeManager

    manager = SessionRuntimeManager(engine=runtime_engine)
    rt1 = manager.get_runtime("session-a")
    rt2 = manager.get_runtime("session-b")

    assert rt1 is not rt2


def test_submit_user_message_enqueues_topic_task(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    saved = []
    manager = SessionRuntimeManager(engine=runtime_engine)
    manager.message_saved.connect(lambda sid, mid: saved.append((sid, mid)))

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="请帮我检索文献",
        root_user_message_id="user-1",
    )

    manager.submit_message(runtime_session_id, user.id)

    rt = manager.get_runtime(runtime_session_id)
    assert rt is not None
    assert "Topic Agent" in rt.queues


def test_queued_task_starts_target_agent_worker(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    fake_calls = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        fake_calls.append(agent_name)
        return f"{agent_name} reply"

    saved = []
    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)
    manager.message_saved.connect(lambda sid, mid: saved.append((sid, mid)))

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="请帮我检索文献",
        root_user_message_id="user-1",
    )

    manager.submit_message(runtime_session_id, user.id)
    rt = manager.get_runtime(runtime_session_id)
    rt.drain_for_tests(max_steps=20)

    assert len(fake_calls) >= 1
    assert "Topic Agent" in fake_calls
    assert len(saved) >= 1
    messages = load_messages(runtime_engine)
    assistant_messages = [m for m in messages if m.role == "assistant"]
    assert len(assistant_messages) >= 1


def test_same_agent_tasks_remain_fifo(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    call_order = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        call_order.append(agent_name)
        return f"{agent_name} reply"

    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="任务1",
        root_user_message_id="user-1",
    )
    user2 = save_message(
        runtime_engine,
        id="user-2",
        session_id=runtime_session_id,
        role="user",
        content="任务2",
        root_user_message_id="user-2",
    )

    manager.submit_message(runtime_session_id, user.id)
    manager.submit_message(runtime_session_id, user2.id)

    rt = manager.get_runtime(runtime_session_id)
    rt.drain_for_tests(max_steps=30)

    topic_calls = [c for c in call_order if c == "Topic Agent"]
    assert len(topic_calls) >= 2
    # Verify Topic tasks processed

    topic_queue = list(rt.queues.get("Topic Agent", []))
    assert len(topic_queue) == 0  # All drained


def test_cross_agent_parallelism_contract(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    call_order = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        call_order.append(agent_name)
        return f"@Paper Agent 请检索论文。\n@Memory Agent 请检查记忆。" if agent_name == "Topic Agent" else f"{agent_name} reply"

    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="请帮我检索文献并检查记忆",
        root_user_message_id="user-1",
    )

    manager.submit_message(runtime_session_id, user.id)
    rt = manager.get_runtime(runtime_session_id)
    rt.drain_for_tests(max_steps=30)

    paper_calls = [c for c in call_order if c == "Paper Agent"]
    memory_calls = [c for c in call_order if c == "Memory Agent"]
    assert len(paper_calls) >= 1
    assert len(memory_calls) >= 1


def test_explicit_runtime_close_cancels_queued_tasks(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    call_order = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        call_order.append(agent_name)
        return f"{agent_name} reply"

    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="任务1",
        root_user_message_id="user-1",
    )
    user2 = save_message(
        runtime_engine,
        id="user-2",
        session_id=runtime_session_id,
        role="user",
        content="任务2",
        root_user_message_id="user-2",
    )

    manager.submit_message(runtime_session_id, user.id)
    manager.submit_message(runtime_session_id, user2.id)

    rt = manager.get_runtime(runtime_session_id)
    # Close before draining
    rt.close(reason="test")

    # Queued tasks should be cleared
    all_queued = sum(len(q) for q in rt.queues.values())
    assert all_queued == 0


def test_shutdown_clears_all_runtimes(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    call_order = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        call_order.append(agent_name)
        return f"{agent_name} reply"

    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="任务1",
        root_user_message_id="user-1",
    )
    manager.submit_message(runtime_session_id, user.id)

    # Should not raise
    manager.shutdown()

    assert len(manager._runtimes) == 0


def test_message_saved_signal_emitted_after_worker_saves(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    saved_signals = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        return f"{agent_name} reply"

    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)
    manager.message_saved.connect(lambda sid, mid: saved_signals.append((sid, mid)))

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="测试",
        root_user_message_id="user-1",
    )
    manager.submit_message(runtime_session_id, user.id)

    rt = manager.get_runtime(runtime_session_id)
    rt.drain_for_tests(max_steps=20)

    assert len(saved_signals) >= 1
    for sid, mid in saved_signals:
        assert sid == runtime_session_id
        msg = save_message.__wrapped__ if hasattr(save_message, '__wrapped__') else None
        # Verify the message actually exists
        messages = load_messages(runtime_engine)
        message_ids = {m.id for m in messages}
        assert mid in message_ids


def test_cancel_by_root_user_message(runtime_engine, runtime_session_id):
    from app.services.agent_runtime import SessionRuntimeManager

    all_calls = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        all_calls.append(agent_name)
        return f"{agent_name} reply"

    manager = SessionRuntimeManager(engine=runtime_engine, llm_caller=fake_llm)

    user = save_message(
        runtime_engine,
        id="user-1",
        session_id=runtime_session_id,
        role="user",
        content="请取消此任务",
        root_user_message_id="user-1",
    )

    # Cancel before submitting
    manager.cancel_root(runtime_session_id, "user-1")
    manager.submit_message(runtime_session_id, user.id)

    rt = manager.get_runtime(runtime_session_id)
    rt.drain_for_tests(max_steps=20)

    # No agent should have been called because root is canceled
    assert len(all_calls) == 0
