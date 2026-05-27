from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.agent_config import AgentConfig
from app.models.chat_message import ChatMessage
from app.models.session import Session as ChatSession
from app.models.topic import Topic
import app.services.agent_runtime as agent_runtime
from app.services.agent_runtime import (
    AgentTask,
    ChatContextMessage,
)


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
        ]:
            session.add(agent)
        session.commit()
    return "session-1"


def make_context(message_id, role, content, agent_name=""):
    minute = int(message_id.split("-")[-1])
    return ChatContextMessage(
        message_id=message_id,
        role=role,
        agent_name=agent_name,
        content=content,
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute),
    )


def make_task(session_id, **kwargs):
    values = {
        "task_id": "task-1",
        "session_id": session_id,
        "target_agent": "Paper Agent",
        "task_type": "dispatch",
        "instruction": "请检索相关论文。",
        "root_user_message_id": "msg-1",
        "trigger_message_id": "msg-2",
        "target_message_id": None,
        "context_snapshot": [
            make_context("msg-1", "user", "用户问题"),
            make_context("msg-2", "assistant", "Topic 分派", "Topic Agent"),
        ],
        "dispatch_depth": 2,
        "redo_count": 1,
    }
    values.update(kwargs)
    return AgentTask(**values)


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


def load_message(runtime_engine, message_id):
    with Session(runtime_engine) as session:
        return session.get(ChatMessage, message_id)


def test_prompt_builder_includes_context_and_instruction(runtime_session_id):
    task = make_task(
        runtime_session_id,
        context_snapshot=[
            make_context("msg-1", "user", "第一条用户消息"),
            make_context("msg-2", "assistant", "Topic 回复", "Topic Agent"),
            make_context("msg-3", "paper", "Paper 回复", "Paper Agent"),
            make_context("msg-4", "system", "系统提示"),
        ],
        instruction="完成最终任务",
    )

    prompt = agent_runtime.build_agent_user_prompt(task)

    assert "以下是当前群聊上下文，按时间顺序排列：" in prompt
    assert "User:\n第一条用户消息" in prompt
    assert "Topic Agent:\nTopic 回复" in prompt
    assert "Paper Agent:\nPaper 回复" in prompt
    assert "system:\n系统提示" in prompt
    assert prompt.endswith("你的任务：\n完成最终任务")


def test_worker_saves_assistant_message_with_lineage_metadata(
    runtime_engine,
    runtime_session_id,
):
    calls = []
    saved = []

    def fake_llm(agent_name, system_prompt, user_prompt, agent_model):
        calls.append((agent_name, system_prompt, user_prompt, agent_model))
        return "Paper answer"

    task = make_task(runtime_session_id)
    worker = agent_runtime.AgentWorker(runtime_engine, fake_llm, message_saved=saved.append)

    message_id = worker.process_one(task)

    assert message_id is not None
    messages = load_messages(runtime_engine)
    assert len(messages) == 1
    message = messages[0]
    assert message.id == message_id
    assert message.session_id == runtime_session_id
    assert message.role == "assistant"
    assert message.content == "Paper answer"
    assert message.agent_name == "Paper Agent"
    assert message.task_id == "task-1"
    assert message.task_type == "dispatch"
    assert message.root_user_message_id == "msg-1"
    assert message.trigger_message_id == "msg-2"
    assert message.target_message_id is None
    assert message.dispatch_depth == 2
    assert message.redo_count == 1
    assert saved == [(runtime_session_id, message_id)]
    assert calls[0][0] == "Paper Agent"
    assert "Paper prompt" in calls[0][1]
    assert "请检索相关论文。" in calls[0][2]
    assert calls[0][3] == "paper-model"


def test_worker_canceled_before_call_does_not_call_llm_or_save(
    runtime_engine,
    runtime_session_id,
):
    calls = []
    canceled_roots = {"msg-1"}
    task = make_task(runtime_session_id)
    worker = agent_runtime.AgentWorker(
        runtime_engine,
        lambda *args: calls.append(args) or "unused",
        canceled_roots=canceled_roots,
        message_saved=lambda *_: None,
    )

    result = worker.process_one(task)

    assert result is None
    assert calls == []
    assert load_messages(runtime_engine) == []


def test_worker_canceled_after_call_before_save_discards_result(
    runtime_engine,
    runtime_session_id,
):
    canceled_roots = set()
    saved = []

    def fake_llm(*_args):
        canceled_roots.add("msg-1")
        return "Paper answer"

    task = make_task(runtime_session_id)
    worker = agent_runtime.AgentWorker(
        runtime_engine,
        fake_llm,
        canceled_roots=canceled_roots,
        message_saved=saved.append,
    )

    result = worker.process_one(task)

    assert result is None
    assert saved == []
    assert load_messages(runtime_engine) == []


def test_normal_llm_exception_writes_system_message_and_emits_saved_callback(
    runtime_engine,
    runtime_session_id,
):
    saved = []

    def failing_llm(*_args):
        raise RuntimeError("provider unavailable")

    task = make_task(runtime_session_id)
    worker = agent_runtime.AgentWorker(runtime_engine, failing_llm, message_saved=saved.append)

    result = worker.process_one(task)

    assert result is None
    messages = load_messages(runtime_engine)
    assert len(messages) == 1
    message = messages[0]
    assert message.role == "system"
    assert "provider unavailable" in message.content
    assert message.agent_name == "Paper Agent"
    assert message.task_id == "task-1"
    assert message.task_type == "dispatch"
    assert message.root_user_message_id == "msg-1"
    assert message.trigger_message_id == "msg-2"
    assert message.target_message_id is None
    assert message.dispatch_depth == 2
    assert message.redo_count == 1
    assert saved == [(runtime_session_id, message.id)]


def test_failing_llm_canceled_before_exception_save_writes_nothing(
    runtime_engine,
    runtime_session_id,
):
    canceled_roots = set()
    saved = []

    def failing_llm(*_args):
        canceled_roots.add("msg-1")
        raise RuntimeError("provider unavailable")

    task = make_task(runtime_session_id)
    worker = agent_runtime.AgentWorker(
        runtime_engine,
        failing_llm,
        canceled_roots=canceled_roots,
        message_saved=saved.append,
    )

    result = worker.process_one(task)

    assert result is None
    assert saved == []
    assert load_messages(runtime_engine) == []


def test_worker_without_injected_llm_uses_llm_service_fallback(
    monkeypatch,
    runtime_engine,
    runtime_session_id,
):
    calls = []
    saved = []

    class FakeLLMService:
        def __init__(self):
            self.model = "default-model"

        def call_simple(self, system_prompt, user_prompt):
            calls.append((self.model, system_prompt, user_prompt))
            return "Fallback answer"

    monkeypatch.setattr(agent_runtime, "LLMService", FakeLLMService)

    task = make_task(runtime_session_id)
    worker = agent_runtime.AgentWorker(runtime_engine, message_saved=saved.append)

    message_id = worker.process_one(task)

    assert message_id is not None
    messages = load_messages(runtime_engine)
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "Fallback answer"
    assert messages[0].agent_name == "Paper Agent"
    assert saved == [(runtime_session_id, message_id)]
    assert len(calls) == 1
    assert calls[0][0] == "paper-model"
    assert "Paper prompt" in calls[0][1]
    assert "请检索相关论文。" in calls[0][2]


def test_failed_topic_review_writes_system_message_without_updating_target_status(
    runtime_engine,
    runtime_session_id,
):
    target = save_message(
        runtime_engine,
        id="target-1",
        session_id=runtime_session_id,
        role="assistant",
        content="Draft answer",
        agent_name="Paper Agent",
        root_user_message_id="msg-1",
        trigger_message_id="msg-1",
        dispatch_depth=1,
    )
    saved = []

    def failing_llm(*_args):
        raise RuntimeError("review failed")

    task = make_task(
        runtime_session_id,
        task_id="review-task",
        target_agent="Topic Agent",
        task_type="review",
        instruction="请审查 Paper Agent 的回复。",
        target_message_id=target.id,
        dispatch_depth=1,
        redo_count=0,
    )
    worker = agent_runtime.AgentWorker(runtime_engine, failing_llm, message_saved=saved.append)

    result = worker.process_one(task)

    assert result is None
    messages = load_messages(runtime_engine)
    system_messages = [message for message in messages if message.role == "system"]
    assert len(system_messages) == 1
    system_message = system_messages[0]
    assert "review failed" in system_message.content
    assert system_message.agent_name == "Topic Agent"
    assert system_message.task_id == "review-task"
    assert system_message.task_type == "review"
    assert system_message.target_message_id == target.id
    assert saved == [(runtime_session_id, system_message.id)]
    assert load_message(runtime_engine, target.id).review_status is None
