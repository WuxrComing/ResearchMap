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


def review_card(summary, correctness, score, action, issues=None):
    issue_lines = "\n".join(f"- {issue}" for issue in (issues or ["none"]))
    return (
        "[REVIEW]\n"
        f"summary: {summary}\n"
        f"correctness: {correctness}\n"
        f"score: {score}\n"
        "issues:\n"
        f"{issue_lines}\n"
        f"action: {action}\n"
        "[/REVIEW]"
    )


def create_review_target(runtime_engine, session_id, **kwargs):
    root = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", "Root request."),
    )
    target_kwargs = {
        "agent_name": "Paper Agent",
        "root_user_message_id": root.id,
        "trigger_message_id": root.id,
        "dispatch_depth": 2,
    }
    target_kwargs.update(kwargs)
    target = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-2",
            "assistant",
            "Paper answer.",
            **target_kwargs,
        ),
    )
    return root, target


def load_message(runtime_engine, message_id):
    with Session(runtime_engine) as session:
        return session.get(ChatMessage, message_id)


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


def test_user_message_with_only_fenced_code_mention_falls_back_to_topic(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    content = "```text\n@Paper Agent find papers.\n```"
    message = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", content),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert len(tasks) == 1
    assert tasks[0].target_agent == "Topic Agent"
    assert tasks[0].task_type == "user_request"
    assert tasks[0].instruction == content


def test_user_message_with_only_malformed_mention_falls_back_to_topic(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    content = "@Paper Agent2 find papers."
    message = save_message(
        runtime_engine,
        **message_kwargs(session_id, "msg-1", "user", content),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert len(tasks) == 1
    assert tasks[0].target_agent == "Topic Agent"
    assert tasks[0].task_type == "user_request"
    assert tasks[0].instruction == content


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


def test_topic_review_accept_updates_target_review_fields_and_creates_no_tasks(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Looks correct.", "pass", 5, "accept"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            trigger_message_id=target.id,
            target_message_id=target.id,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert tasks == []
    assert enqueued == []
    updated = load_message(runtime_engine, target.id)
    assert updated.review_status == "passed"
    assert updated.review_score == 5
    assert updated.review_summary == "Looks correct."


def test_topic_review_redo_creates_redo_task_for_original_target_agent(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Needs sources.", "fail", 2, "redo", ["Missing citations"]),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            trigger_message_id=target.id,
            target_message_id=target.id,
            dispatch_depth=4,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.target_agent == "Paper Agent"
    assert task.task_type == "redo"
    assert task.target_message_id == target.id
    assert task.trigger_message_id == review.id


def test_topic_review_redo_preserves_original_task_depth_and_increments_redo_count(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root, target = create_review_target(
        runtime_engine,
        session_id,
        dispatch_depth=3,
        redo_count=1,
    )
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Still incomplete.", "partial", 3, "redo"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
            dispatch_depth=5,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert len(tasks) == 1
    assert tasks[0].dispatch_depth == 3
    assert tasks[0].redo_count == 2
    updated = load_message(runtime_engine, target.id)
    assert updated.redo_count == 2
    assert updated.review_score == 3
    assert updated.review_summary == "Still incomplete."


def test_topic_review_redo_processed_twice_increments_redo_count_once(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id, redo_count=0)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Needs another pass.", "fail", 2, "redo"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
        ),
    )

    first_tasks = dispatcher.handle_message_saved(review.id)
    second_tasks = dispatcher.handle_message_saved(review.id)

    assert len(first_tasks) == 1
    assert second_tasks == []
    assert len(enqueued) == 1
    updated = load_message(runtime_engine, target.id)
    assert updated.redo_count == 1
    processed_review = load_message(runtime_engine, review.id)
    assert processed_review.dispatch_processed is True
    assert processed_review.review_status is None


def test_topic_review_redo_processed_by_new_dispatcher_does_not_repeat(
    runtime_engine,
    runtime_db_session,
    runtime_session_id,
):
    first_enqueued = []
    first_dispatcher = AgentDispatcher(runtime_engine, first_enqueued.append)
    root, target = create_review_target(runtime_engine, runtime_session_id, redo_count=0)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            runtime_session_id,
            "msg-3",
            "assistant",
            review_card("Needs another pass.", "fail", 2, "redo"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
        ),
    )

    first_tasks = first_dispatcher.handle_message_saved(review.id)

    second_enqueued = []
    second_dispatcher = AgentDispatcher(runtime_engine, second_enqueued.append)
    second_tasks = second_dispatcher.handle_message_saved(review.id)

    assert len(first_tasks) == 1
    assert second_tasks == []
    assert second_enqueued == []
    updated = load_message(runtime_engine, target.id)
    assert updated.redo_count == 1
    processed_review = load_message(runtime_engine, review.id)
    assert processed_review.dispatch_processed is True
    assert processed_review.review_status is None


def test_topic_review_redo_enqueue_failure_does_not_increment_redo_count_and_retry_enqueues(
    runtime_engine,
    runtime_session_id,
):
    enqueued = []
    should_raise = True

    def enqueue_task(task):
        nonlocal should_raise
        if should_raise:
            should_raise = False
            raise RuntimeError("enqueue failed")
        enqueued.append(task)

    dispatcher = AgentDispatcher(runtime_engine, enqueue_task)
    root, target = create_review_target(runtime_engine, runtime_session_id, redo_count=0)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            runtime_session_id,
            "msg-3",
            "assistant",
            review_card("Needs another pass.", "fail", 2, "redo"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
        ),
    )

    with pytest.raises(RuntimeError, match="enqueue failed"):
        dispatcher.handle_message_saved(review.id)

    after_failure = load_message(runtime_engine, target.id)
    assert after_failure.redo_count == 0

    retry_tasks = dispatcher.handle_message_saved(review.id)

    assert len(retry_tasks) == 1
    assert retry_tasks[0].redo_count == 1
    assert len(enqueued) == 1
    after_retry = load_message(runtime_engine, target.id)
    assert after_retry.redo_count == 1


def test_topic_review_redo_persistence_failure_rolls_back_processed_key_for_retry(
    runtime_engine,
    runtime_db_session,
    runtime_session_id,
    monkeypatch,
):
    enqueued = []
    dispatcher = AgentDispatcher(runtime_engine, enqueued.append)
    original_persist = dispatcher._persist_review_result
    should_raise = True

    def persist_review_result(*args, **kwargs):
        nonlocal should_raise
        if should_raise:
            should_raise = False
            raise RuntimeError("persist failed")
        return original_persist(*args, **kwargs)

    monkeypatch.setattr(dispatcher, "_persist_review_result", persist_review_result)
    root, target = create_review_target(runtime_engine, runtime_session_id, redo_count=0)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            runtime_session_id,
            "msg-3",
            "assistant",
            review_card("Needs another pass.", "fail", 2, "redo"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
        ),
    )

    with pytest.raises(RuntimeError, match="persist failed"):
        dispatcher.handle_message_saved(review.id)

    after_failure = load_message(runtime_engine, target.id)
    assert after_failure.redo_count == 0
    assert after_failure.review_status is None

    retry_tasks = dispatcher.handle_message_saved(review.id)

    assert len(retry_tasks) == 1
    assert len(enqueued) == 2
    after_retry = load_message(runtime_engine, target.id)
    assert after_retry.redo_count == 1
    assert after_retry.review_status == "failed"
    assert after_retry.review_score == 2
    assert after_retry.review_summary == "Needs another pass."


def test_topic_review_redo_at_max_rounds_creates_topic_fallback_task(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root, target = create_review_target(
        runtime_engine,
        session_id,
        dispatch_depth=2,
        redo_count=AgentDispatcher.MAX_REDO_ROUNDS,
    )
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Cannot fix.", "fail", 1, "redo"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.target_agent == "Topic Agent"
    assert task.task_type == "fallback"
    assert task.target_message_id == target.id
    assert task.dispatch_depth == 2
    assert task.instruction == (
        "子 Agent 多次重做仍未通过审查。请基于群聊上下文直接给出纠正后的回答。"
    )
    updated = load_message(runtime_engine, target.id)
    assert updated.redo_count == AgentDispatcher.MAX_REDO_ROUNDS


def test_topic_review_supplement_with_memory_mention_dispatches_memory_task(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Need memory context.", "partial", 3, "supplement")
            + "\n\n@Memory Agent recall user preferences.",
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
            dispatch_depth=1,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.target_agent == "Memory Agent"
    assert task.task_type == "dispatch"
    assert task.instruction == "recall user preferences."
    assert task.target_message_id == target.id


def test_topic_review_supplement_dispatch_increments_dispatch_depth_by_one(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id, dispatch_depth=1)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Ask memory.", "partial", 3, "supplement")
            + "\n\n@Memory Agent find context.",
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
            dispatch_depth=2,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert len(tasks) == 1
    assert tasks[0].dispatch_depth == 3


def test_topic_review_supplement_enqueue_failure_remains_retry_safe(
    runtime_engine,
    runtime_db_session,
    runtime_session_id,
):
    enqueued = []
    should_raise = True

    def enqueue_task(task):
        nonlocal should_raise
        if should_raise:
            should_raise = False
            raise RuntimeError("enqueue failed")
        enqueued.append(task)

    dispatcher = AgentDispatcher(runtime_engine, enqueue_task)
    root, target = create_review_target(runtime_engine, runtime_session_id)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            runtime_session_id,
            "msg-3",
            "assistant",
            review_card("Ask memory.", "partial", 3, "supplement")
            + "\n\n@Memory Agent find context.",
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
            dispatch_depth=2,
        ),
    )

    with pytest.raises(RuntimeError, match="enqueue failed"):
        dispatcher.handle_message_saved(review.id)

    after_failure = load_message(runtime_engine, target.id)
    assert after_failure.review_status is None
    assert after_failure.review_score is None
    assert after_failure.review_summary is None

    retry_tasks = dispatcher.handle_message_saved(review.id)

    assert len(retry_tasks) == 1
    assert retry_tasks[0].target_agent == "Memory Agent"
    assert len(enqueued) == 1
    after_retry = load_message(runtime_engine, target.id)
    assert after_retry.review_status == "supplemented"
    assert after_retry.review_score == 3
    assert after_retry.review_summary == "Ask memory."


def test_topic_review_supplement_dispatch_over_max_depth_is_rejected(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id, dispatch_depth=4)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Ask memory.", "partial", 3, "supplement")
            + "\n\n@Memory Agent find context.",
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
            target_message_id=target.id,
            dispatch_depth=AgentDispatcher.MAX_DISPATCH_DEPTH,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert tasks == []
    assert enqueued == []


def test_topic_review_without_target_message_id_creates_no_task_and_writes_no_target_update(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, enqueued, session_id = dispatcher_context
    root, target = create_review_target(runtime_engine, session_id)
    review = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-3",
            "assistant",
            review_card("Looks correct.", "pass", 5, "accept"),
            agent_name="Topic Agent",
            task_type="review",
            root_user_message_id=root.id,
        ),
    )

    tasks = dispatcher.handle_message_saved(review.id)

    assert tasks == []
    assert enqueued == []
    unchanged = load_message(runtime_engine, target.id)
    assert unchanged.review_status is None
    assert unchanged.review_score is None
    assert unchanged.review_summary is None


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


def test_non_topic_review_message_creates_no_review_task(
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
            "Review recursion should stop.",
            agent_name="Paper Agent",
            root_user_message_id=root.id,
            task_type="review",
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    assert tasks == []
    assert enqueued == []


def test_context_snapshot_does_not_include_required_ids_from_other_sessions(
    runtime_engine,
    dispatcher_context,
):
    dispatcher, _, session_id = dispatcher_context
    with Session(runtime_engine) as session:
        session.add(
            ChatSession(
                id="session-2",
                workspace_id="topic-1",
                title="Other session",
            )
        )
        session.commit()
    save_message(
        runtime_engine,
        **message_kwargs(
            "session-2",
            "msg-99",
            "user",
            "This cross-session message must not leak.",
        ),
    )
    message = save_message(
        runtime_engine,
        **message_kwargs(
            session_id,
            "msg-2",
            "assistant",
            "Paper answer.",
            agent_name="Paper Agent",
            root_user_message_id="msg-99",
        ),
    )

    tasks = dispatcher.handle_message_saved(message.id)

    context_ids = [item.message_id for item in tasks[0].context_snapshot]
    assert message.id in context_ids
    assert "msg-99" not in context_ids


def test_enqueue_failure_does_not_mark_task_processed(
    runtime_engine,
    runtime_db_session,
    runtime_session_id,
):
    enqueued = []

    def failing_enqueue(task):
        raise RuntimeError("queue unavailable")

    dispatcher = AgentDispatcher(runtime_engine, failing_enqueue)
    message = save_message(
        runtime_engine,
        **message_kwargs(runtime_session_id, "msg-1", "user", "@Paper Agent retry."),
    )

    with pytest.raises(RuntimeError, match="queue unavailable"):
        dispatcher.handle_message_saved(message.id)

    dispatcher.enqueue_task = enqueued.append
    tasks = dispatcher.handle_message_saved(message.id)

    assert len(tasks) == 1
    assert enqueued == tasks


def test_runtime_router_does_not_retain_db_session(runtime_engine, runtime_db_session):
    dispatcher = AgentDispatcher(runtime_engine, lambda task: None)

    router = dispatcher._router()

    assert getattr(router, "_db", None) is None
    assert router.parse_mentions("@Paper Agent retry.") == ["Paper Agent"]


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
