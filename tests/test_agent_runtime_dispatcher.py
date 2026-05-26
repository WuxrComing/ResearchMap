import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.agent_config import AgentConfig
from app.services.agent_runtime import find_mention_spans, split_mention_instructions
from app.services.message_router import MessageRouter


@pytest.fixture
def runtime_db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
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
def router(runtime_db_session):
    return MessageRouter(runtime_db_session)


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
