import re
from dataclasses import dataclass
from sqlmodel import Session, select
from app.models.agent_config import AgentConfig


@dataclass
class ReviewResult:
    summary: str
    correctness: str       # "pass" | "partial" | "fail"
    score: int             # 1-5
    issues: list[str]
    action: str            # "accept" | "redo" | "supplement"


@dataclass
class DispatchRequest:
    target_agent: str
    task: str


def parse_dispatch_blocks(text: str) -> list[DispatchRequest]:
    """Parse public Topic Agent dispatch blocks from a chat message."""
    if not text:
        return []

    dispatches = []
    pattern = r'>>DISPATCH>>\s*@([^\n]+?)\s*\n(.*?)\n\s*>>END_DISPATCH>>'
    for match in re.finditer(pattern, text, re.DOTALL):
        target_agent = match.group(1).strip()
        task = match.group(2).strip()
        if target_agent and task:
            dispatches.append(DispatchRequest(target_agent=target_agent, task=task))
    return dispatches


def parse_review_card(text: str) -> ReviewResult | None:
    """Parse [REVIEW]...[/REVIEW] card from Topic Agent output.
    Returns None if no valid review card is found."""
    m = re.search(r'\[REVIEW\]\s*\n(.*?)\n\s*\[/REVIEW\]', text, re.DOTALL)
    if not m:
        return None
    body = m.group(1)

    def _field(key: str) -> str | None:
        fm = re.search(rf'^{key}:\s*(.+)$', body, re.MULTILINE)
        return fm.group(1).strip() if fm else None

    def _list(key: str) -> list[str]:
        pattern = rf'^{key}:\s*\n((?:\s*-\s*.+\n?)*)'
        lm = re.search(pattern, body, re.MULTILINE)
        if not lm:
            return []
        items = re.findall(r'^\s*-\s*(.+)$', lm.group(1), re.MULTILINE)
        return [i.strip() for i in items]

    summary = _field("summary")
    correctness = _field("correctness")
    score_str = _field("score")
    action = _field("action")
    issues = _list("issues")

    if not all([summary, correctness, score_str, action]):
        return None

    try:
        score = int(score_str)
    except (ValueError, TypeError):
        return None

    if not 1 <= score <= 5:
        return None
    if correctness not in ("pass", "partial", "fail"):
        return None
    if action not in ("accept", "redo", "supplement"):
        return None

    return ReviewResult(
        summary=summary,
        correctness=correctness,
        score=score,
        issues=issues if issues else ["none"],
        action=action,
    )


def build_redo_message(
    target_agent: str,
    original_reply: str,
    review: ReviewResult,
) -> str:
    """Build a redo instruction message to send back to the original agent."""
    issues_text = "\n".join(f"  {i+1}. {issue}" for i, issue in enumerate(review.issues))
    return (
        f">>REDO>> @{target_agent}\n"
        f"你刚才的回复存在以下问题：\n"
        f"{issues_text}\n\n"
        f"原始回复摘要：{review.summary}\n\n"
        f"请重新回答，注意纠正以上问题。\n"
        f">>END_REDO>>"
    )


@dataclass
class RoutedAgent:
    name: str
    role: str
    system_prompt: str
    model: str


class MessageRouter:
    def __init__(self, db: Session):
        self._db = db
        self._agents: list[AgentConfig] = self._load_enabled_agents()

    def _load_enabled_agents(self) -> list[AgentConfig]:
        return list(
            self._db.exec(
                select(AgentConfig).where(AgentConfig.enabled == True)
            ).all()
        )

    def get_all_agent_names(self) -> list[str]:
        return [a.name for a in self._agents]

    def parse_mentions(self, text: str) -> list[str]:
        """Extract @AgentName mentions from text in order of appearance. Only returns enabled agents."""
        if not text:
            return []
        matches = []
        for agent in self._agents:
            m = re.search(rf'@{re.escape(agent.name)}', text)
            if m:
                matches.append((m.start(), agent.name))
        matches.sort(key=lambda x: x[0])
        return [name for _, name in matches]

    def resolve_agents(self, mentions: list[str]) -> list[RoutedAgent]:
        """Resolve mention names to RoutedAgent objects. Falls back to default if empty."""
        if not mentions:
            mentions = []
        name_map = {a.name: a for a in self._agents}
        result = []
        for name in mentions:
            agent = name_map.get(name)
            if agent:
                result.append(RoutedAgent(
                    name=agent.name, role=agent.role,
                    system_prompt=agent.system_prompt,
                    model=agent.model or "",
                ))
        if not result:
            default = next(
                (a for a in self._agents if a.role == "assistant"),
                self._agents[0] if self._agents else None,
            )
            if default:
                result.append(RoutedAgent(
                    name=default.name, role=default.role,
                    system_prompt=default.system_prompt,
                    model=default.model or "",
                ))
        return result

    def build_system_prompt(self, agent: RoutedAgent) -> str:
        """Build enhanced system prompt with available agents summary."""
        base = agent.system_prompt
        available = [
            f"- {a.name}: {a.description or 'No description'}"
            for a in self._agents
        ]
        if available:
            base += (
                "\n\n---\n"
                "可用的 Agent 角色（你可以通过 @Agent名称 调用他们协助你）：\n"
                + "\n".join(available)
                + "\n---"
            )
        return base
