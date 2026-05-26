import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.agents.definitions import DEFAULT_AGENTS
from app.models.agent_config import AgentConfig
from app.services.message_router import MessageRouter, RoutedAgent, parse_dispatch_blocks


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(AgentConfig(
            name="Topic Agent", role="assistant", system_prompt="Topic prompt",
            description="核心助手", model="", color="#07C160", enabled=True,
        ))
        session.add(AgentConfig(
            name="Paper Agent", role="paper", system_prompt="Paper prompt",
            description="论文检索", model="gpt-4", color="#F9A825", enabled=True,
        ))
        session.add(AgentConfig(
            name="Memory Agent", role="memory", system_prompt="Memory prompt",
            description="记忆管理", model="", color="#9E9E9E", enabled=False,
        ))
        session.commit()
        yield session


class TestParseMentions:
    def test_single_mention(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Topic Agent 帮我分析这个课题")
        assert mentions == ["Topic Agent"]

    def test_multiple_mentions(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Topic Agent 和 @Paper Agent 一起分析")
        assert mentions == ["Topic Agent", "Paper Agent"]

    def test_no_mention(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("帮我分析这个课题")
        assert mentions == []

    def test_mention_not_matching(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Unknown Agent 帮我分析")
        assert mentions == []

    def test_mention_disabled_agent(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Memory Agent 帮我回忆")
        assert mentions == []

    def test_mention_partial_name_no_match(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Papers review something")
        assert mentions == []  # Should NOT match "Paper Agent"

    def test_parse_none_text(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions(None)
        assert mentions == []

    def test_mention_with_cjk_after(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Topic Agent帮我分析这个课题")
        assert mentions == ["Topic Agent"]

    def test_mention_order_by_position(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Paper Agent 然后 @Topic Agent 分析")
        assert mentions == ["Paper Agent", "Topic Agent"]


class TestResolveAgents:
    def test_resolve_known_mentions(self, db_session):
        router = MessageRouter(db_session)
        agents = router.resolve_agents(["Topic Agent", "Paper Agent"])
        assert len(agents) == 2
        assert agents[0].name == "Topic Agent"
        assert agents[1].name == "Paper Agent"
        assert agents[1].model == "gpt-4"

    def test_resolve_empty_falls_back_to_default(self, db_session):
        router = MessageRouter(db_session)
        agents = router.resolve_agents([])
        assert len(agents) == 1
        assert agents[0].name == "Topic Agent"


class TestBuildSystemPrompt:
    def test_includes_available_agents(self, db_session):
        router = MessageRouter(db_session)
        agent = RoutedAgent(
            name="Paper Agent", role="paper",
            system_prompt="Paper prompt", model="",
        )
        prompt = router.build_system_prompt(agent)
        assert "Paper prompt" in prompt
        assert "可用的 Agent 角色" in prompt
        assert "Topic Agent: 核心助手" in prompt
        assert "Paper Agent: 论文检索" in prompt
        assert "Memory Agent" not in prompt  # disabled agent


class TestDefaultAgentPrompts:
    def test_topic_agent_uses_natural_mentions_for_dispatch(self):
        topic_prompt = next(
            agent["system_prompt"]
            for agent in DEFAULT_AGENTS
            if agent["name"] == "Topic Agent"
        )

        assert ">>DISPATCH>>" not in topic_prompt
        assert ">>END_DISPATCH>>" not in topic_prompt
        assert "@Paper Agent" in topic_prompt
        assert "自然语言" in topic_prompt or "直接在群聊中 @" in topic_prompt


class TestParseDispatchBlocks:
    def test_parse_single_dispatch_block(self):
        text = """我来安排检索。
>>DISPATCH>> @Paper Agent
请检索小目标检测领域 2023-2025 年最新代表性论文。
>>END_DISPATCH>>"""

        dispatches = parse_dispatch_blocks(text)

        assert len(dispatches) == 1
        assert dispatches[0].target_agent == "Paper Agent"
        assert "2023-2025" in dispatches[0].task

    def test_ignores_text_without_dispatch(self):
        assert parse_dispatch_blocks("直接回答用户问题") == []


class TestBuildRedoMessage:
    def test_build_redo_message(self):
        from app.services.message_router import build_redo_message, ReviewResult
        review = ReviewResult(
            summary="回复有误",
            correctness="fail",
            score=2,
            issues=["忽略了2024年论文", "混淆了概念"],
            action="redo",
        )
        msg = build_redo_message(
            target_agent="Paper Agent",
            original_reply="一些错误内容...",
            review=review,
        )
        assert "Paper Agent" in msg
        assert "忽略了2024年论文" in msg
        assert "混淆了概念" in msg
        assert ">>REDO>>" in msg
        assert ">>END_REDO>>" in msg

    def test_build_redo_includes_guidance(self):
        from app.services.message_router import build_redo_message, ReviewResult
        review = ReviewResult(
            summary="不完整",
            correctness="partial",
            score=3,
            issues=["遗漏了不确定性感知方法"],
            action="redo",
        )
        msg = build_redo_message(
            target_agent="Paper Agent",
            original_reply="之前的回答",
            review=review,
        )
        assert "遗漏了不确定性感知方法" in msg
        assert "重新回答" in msg
