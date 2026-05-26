import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models.agent_config import AgentConfig
from app.services.message_router import MessageRouter


@pytest.fixture
def populated_db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for a in [
            AgentConfig(name="Topic Agent", role="assistant",
                        system_prompt="Topic prompt", description="核心助手",
                        model="", color="#07C160", enabled=True),
            AgentConfig(name="Paper Agent", role="paper",
                        system_prompt="Paper prompt", description="论文检索",
                        model="gpt-4", color="#F9A825", enabled=True),
            AgentConfig(name="Transfer Agent", role="transfer",
                        system_prompt="Transfer prompt", description="迁移判断",
                        model="", color="#2196F3", enabled=True),
        ]:
            session.add(a)
        session.commit()
        yield session


class TestMessageRouting:
    def test_parse_all_mentions(self, populated_db):
        router = MessageRouter(populated_db)
        text = "@Topic Agent 分析后，@Paper Agent 找论文，@Transfer Agent 判断"
        assert router.parse_mentions(text) == [
            "Topic Agent", "Paper Agent", "Transfer Agent"
        ]

    def test_resolve_returns_correct_order(self, populated_db):
        router = MessageRouter(populated_db)
        agents = router.resolve_agents(["Paper Agent", "Transfer Agent"])
        assert [a.name for a in agents] == ["Paper Agent", "Transfer Agent"]

    def test_ignore_unknown_mention(self, populated_db):
        router = MessageRouter(populated_db)
        agents = router.resolve_agents(["Unknown Agent"])
        assert len(agents) == 1
        assert agents[0].name == "Topic Agent"

    def test_auto_collab_dedup(self, populated_db):
        """Already-called agents are not re-called."""
        router = MessageRouter(populated_db)
        mentions = router.parse_mentions("@Topic Agent @Paper Agent")
        called = {"Topic Agent"}
        new = [m for m in mentions if m not in called]
        assert new == ["Paper Agent"]
