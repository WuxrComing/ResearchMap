import pytest
from datetime import UTC, datetime, timedelta
from sqlmodel import Session, SQLModel, create_engine

from app.models.agent_config import AgentConfig
from app.models.chat_message import ChatMessage
from app.models.session import Session as ChatSession
from app.models.topic import Topic
from app.services.agent_runtime import (
    AgentDispatcher,
    find_mention_spans,
    split_mention_instructions,
)
from app.services.message_router import MessageRouter


@pytest.fixture
def runtime_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def runtime_db_session(runtime_engine):
    with Session(runtime_engine) as session:
        for agent in [
            AgentConfig(
                name="Topic Agent",
                role="assistant",
                system_prompt="Topic prompt",
                description="核心助手",
                model="",
                color="#07C160",
                enabled=True,
            ),
            AgentConfig(
                name="Paper Agent",
                role="paper",
                system_prompt="Paper prompt",
                description="论文检索",
                model="gpt-4",
                color="#F9A825",
                enabled=True,
            ),
            AgentConfig(
                name="Memory Agent",
                role="memory",
                system_prompt="Memory prompt",
                description="记忆管理",
                model="",
                color="#9E9E9E",
                enabled=True,
            ),
            AgentConfig(
                name="Transfer Agent",
                role="transfer",
                system_prompt="Transfer prompt",
                description="迁移判断",
                model="",
                color="#2196F3",
                enabled=False,
            ),
        ]:
            session.add(agent)
        session.commit()
        yield session


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
        session.commit()
    return "session-1"


@pytest.fixture
def dispatcher_context(runtime_engine, runtime_db_session, runtime_session_id):
    enqueued = []
    dispatcher = AgentDispatcher(runtime_engine, enqueued.append)
    return dispatcher, enqueued, runtime_session_id


def save_message(runtime_engine, **kwargs):
    with Session(runtime_engine) as session:
        message = ChatMessage(**kwargs)
        session.add(message)
        session.commit()
        session.refresh(message)
        return message


def message_kwargs(session_id, message_id, role, content, **kwargs):
    return {
        "id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC)
        + timedelta(minutes=int(message_id.split("-")[-1])),
        **kwargs,
    }


@pytest.fixture
def router(runtime_db_session):
    return MessageRouter(runtime_db_session)


def test_user_message_without_mention_creates_topic_user_request_task(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    message = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "Help me map this idea."),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert tasks == enqueued
    assert len(tasks) == 1
    task = tasks[0]
    assert task.target_agent == "Topic Agent"
    assert task.task_type == "user_request"
    assert task.root_user_message_id == message.id
    assert task.trigger_message_id == message.id
    assert task.target_message_id is None
    assert task.instruction == message.content


def test_user_message_with_paper_mention_creates_paper_user_request_task(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    message = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-1",
            "user",
            "@Paper Agent find related papers.",
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert len(tasks) == 1
    assert tasks[0].target_agent == "Paper Agent"
    assert tasks[0].task_type == "user_request"
    assert tasks[0].instruction == "find related papers."


def test_user_message_with_multiple_mentions_creates_only_mentioned_user_request_tasks(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    message = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-1",
            "user",
            "@Paper Agent find papers. @Memory Agent recall preferences.",
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert [task.target_agent for task in tasks] == ["Paper Agent", "Memory Agent"]
    assert {task.task_type for task in tasks} == {"user_request"}
    assert "Topic Agent" not in {task.target_agent for task in tasks}


def test_topic_message_with_paper_mention_creates_paper_dispatch_task(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "Root request."),
    )
    message = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-2",
            "assistant",
            "Checking. @Paper Agent: summarize newest papers.",
            agent_name="Topic Agent",
            root_user_message_id=root.id,
            trigger_message_id=root.id,
            dispatch_depth=1,
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.target_agent == "Paper Agent"
    assert task.task_type == "dispatch"
    assert task.instruction == "summarize newest papers."
    assert task.root_user_message_id == root.id
    assert task.trigger_message_id == message.id
    assert task.dispatch_depth == 2


def test_non_topic_assistant_message_creates_topic_review_task_with_target(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "Root request."),
    )
    message = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-2",
            "assistant",
            "Paper answer.",
            agent_name="Paper Agent",
            root_user_message_id=root.id,
            trigger_message_id=root.id,
            dispatch_depth=3,
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.target_agent == "Topic Agent"
    assert task.task_type == "review"
    assert task.target_message_id == message.id
    assert task.trigger_message_id == message.id
    assert task.root_user_message_id == root.id
    assert (
        task.instruction
        == "请审查 Paper Agent 的目标回复，只输出 [REVIEW]...[/REVIEW] 审查卡片。"
    )
    assert task.dispatch_depth == 3


def test_mutating_canceled_roots_after_dispatcher_construction_gates_tasks(
    runtime_engine,
    runtime_db_session,
    runtime_session_id,
):
    enqueued = []
    canceled_roots = set()
    dispatcher = AgentDispatcher(
        runtime_engine,
        enqueued.append,
        canceled_roots=canceled_roots,
    )
    message = save_message(
        runtime_engine,
        **message_kwargs(runtime_session_id, "msg-1", "user", "Cancel before run."),
    )
    canceled_roots.add(message.id)

    tasks = dispatcher.handle_message_saved(message.id)

    assert tasks == []
    assert enqueued == []


def test_topic_review_message_creates_no_dispatch_task(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    root = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "Root request."),
    )
    message = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-2",
            "assistant",
            "[REVIEW]\nsummary: mentions @Paper Agent\n[/REVIEW]",
            agent_name="Topic Agent",
            root_user_message_id=root.id,
            task_type="review",
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert tasks == []
    assert enqueued == []


def test_system_message_creates_no_task(runtime_engine, dispatcher_context):
    dispatcher, enqueued, session_id = dispatcher_context
    message = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "system", "Do not dispatch."),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert tasks == []
    assert enqueued == []


def test_task_context_includes_root_trigger_and_target_chronologically(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    target = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-1",
            "assistant",
            "Target reply.",
            agent_name="Paper Agent",
            root_user_message_id="msg-3",
            trigger_message_id="msg-2",
            dispatch_depth=2,
        ),
    )
    trigger = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-2",
            "assistant",
            "Trigger dispatch.",
            agent_name="Topic Agent",
            root_user_message_id="msg-3",
        ),
    )
    root = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-3", "user", "Root request."),
    )

    tasks = dispatcher.handle_message_saved(target.id)

    context_ids = [item.message_id for item in tasks[0].context_snapshot]
    assert context_ids == [target.id, trigger.id, root.id]


def test_duplicate_handle_message_saved_does_not_enqueue_duplicate_tasks(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    message = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "@Paper Agent find papers."),
    )

    first = dispatcher.handle_message_saved(message.id)
    second = dispatcher.handle_message_saved(message.id)

    assert len(first) == 1
    assert second == []
    assert len(enqueued) == 1


def test_dispatch_depth_at_max_allowed_but_child_beyond_max_rejected(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    root = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "Root request."),
    )
    allowed = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-4",
            "assistant",
            "@Paper Agent: allowed at max depth.",
            agent_name="Topic Agent",
            root_user_message_id=root.id,
            dispatch_depth=dispatcher.MAX_DISPATCH_DEPTH - 1,
        ),
    )
    rejected = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-5",
            "assistant",
            "@Paper Agent: too deep.",
            agent_name="Topic Agent",
            root_user_message_id=root.id,
            dispatch_depth=dispatcher.MAX_DISPATCH_DEPTH,
        ),
    )

    allowed_tasks = dispatcher.handle_message_saved(allowed.id)
    rejected_tasks = dispatcher.handle_message_saved(rejected.id)

    assert len(allowed_tasks) == 1
    assert allowed_tasks[0].dispatch_depth == dispatcher.MAX_DISPATCH_DEPTH
    assert rejected_tasks == []
    assert enqueued == allowed_tasks


def test_find_mention_spans_returns_positions_and_duplicates(router):
    text = "@Paper Agent first, @Memory Agent second, @Paper Agent again"

    spans = find_mention_spans(text, router)

    assert [(s.agent_name, s.start, s.end) for s in spans] == [
        ("Paper Agent", 0, len("@Paper Agent")),
        (
            "Memory Agent",
            text.index("@Memory Agent"),
            text.index("@Memory Agent") + len("@Memory Agent"),
        ),
        (
            "Paper Agent",
            text.rindex("@Paper Agent"),
            text.rindex("@Paper Agent") + len("@Paper Agent"),
        ),
    ]


def test_split_topic_mentions_into_agent_instructions(router):
    text = (
        "我先说明背景。"
        "@Paper Agent：检索 2024 年小目标检测论文。"
        "@Memory Agent, 查找用户之前的偏好。"
    )

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {
        "Paper Agent": "检索 2024 年小目标检测论文。",
        "Memory Agent": "查找用户之前的偏好。",
    }


def test_text_before_first_mention_ignored_for_instruction(router):
    text = "这段背景不该进入任务。@Paper Agent: 只分析这里"

    instructions = split_mention_instructions(text, router, source_agent="User")

    assert instructions == {"Paper Agent": "只分析这里"}


def test_duplicate_same_agent_mentions_concatenate_with_blank_line(router):
    text = "@Paper Agent: 第一项任务。 @Memory Agent: 记住设置。 @Paper Agent: 第二项任务。"

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions["Paper Agent"] == "第一项任务。\n\n第二项任务。"
    assert instructions["Memory Agent"] == "记住设置。"


def test_unknown_disabled_mentions_ignored(router):
    text = (
        "@Unknown Agent 忽略未知。"
        "@Transfer Agent 忽略禁用。"
        "@Paper Agent: 保留启用代理任务。"
    )

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {"Paper Agent": "保留启用代理任务。"}


def test_disabled_mention_after_enabled_does_not_leak_into_instruction(router):
    text = "@Paper Agent: keep. @Transfer Agent: ignore this disabled task."

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {"Paper Agent": "keep."}


def test_topic_agent_ignored_inside_topic_messages(router):
    text = "@Topic Agent: 不要派给自己。 @Paper Agent: 检索论文。"

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {"Paper Agent": "检索论文。"}


def test_topic_mention_after_enabled_does_not_leak_inside_topic_messages(router):
    text = "@Paper Agent: 检索论文。 @Topic Agent: 不要进入 Paper 任务。"

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {"Paper Agent": "检索论文。"}


def test_mentions_in_fenced_code_ignored(router):
    text = (
        "```text\n"
        "@Paper Agent: 这是代码示例，不应触发。\n"
        "```\n"
        "@Memory Agent: 记录真实任务。"
    )

    spans = find_mention_spans(text, router)
    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert [s.agent_name for s in spans] == ["Memory Agent"]
    assert instructions == {"Memory Agent": "记录真实任务。"}


def test_mentions_in_unterminated_fenced_code_ignored(router):
    text = (
        "```text\n"
        "@Paper Agent: 这是未闭合代码块，不应触发。\n"
        "@Memory Agent: 也不应触发。"
    )

    stripped = split_mention_instructions(text, router, source_agent="Topic Agent")
    spans = find_mention_spans(text, router)

    assert spans == []
    assert stripped == {}


def test_mention_suffix_rejects_ascii_letters_and_digits(router):
    text = "@Paper Agent2 ignore digits. @Paper Agentic ignore letters. @Memory Agent: keep."

    spans = find_mention_spans(text, router)
    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert [s.agent_name for s in spans] == ["Memory Agent"]
    assert instructions == {"Memory Agent": "keep."}


def test_mention_suffix_allows_cjk_adjacent_instruction(router):
    text = "@Paper Agent帮我检索小目标检测论文。"

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {"Paper Agent": "帮我检索小目标检测论文。"}


def test_adjacent_mentions_use_full_message_only_without_non_empty_segment(router):
    text = "@Paper Agent @Memory Agent @Paper Agent: 单独检索。"

    instructions = split_mention_instructions(text, router, source_agent="Topic Agent")

    assert instructions == {
        "Paper Agent": "单独检索。",
        "Memory Agent": text,
    }
