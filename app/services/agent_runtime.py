import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChatContextMessage:
    message_id: str
    role: str
    agent_name: str
    content: str
    created_at: datetime


@dataclass
class AgentTask:
    task_id: str
    session_id: str
    target_agent: str
    task_type: str
    instruction: str
    root_user_message_id: str
    trigger_message_id: str
    target_message_id: str | None
    context_snapshot: list[ChatContextMessage]
    dispatch_depth: int = 0
    redo_count: int = 0


@dataclass
class RuntimeStatusEntry:
    agent_name: str
    state: str
    task_type: str | None
    instruction_summary: str
    task_id: str | None
    root_user_message_id: str | None


@dataclass
class MentionSpan:
    agent_name: str
    start: int
    end: int


def strip_fenced_code(text: str) -> str:
    """Mask fenced code blocks while preserving string length and line positions."""
    if not text:
        return ""

    def _mask(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return re.sub(r"```.*?```", _mask, text, flags=re.DOTALL)


def find_mention_spans(text: str, router) -> list[MentionSpan]:
    if not text:
        return []

    agent_names = router.get_all_agent_names()
    if not agent_names:
        return []

    names_pattern = "|".join(
        re.escape(name) for name in sorted(agent_names, key=len, reverse=True)
    )
    mention_pattern = re.compile(rf"@(?P<agent_name>{names_pattern})")
    searchable_text = strip_fenced_code(text)

    spans = [
        MentionSpan(
            agent_name=match.group("agent_name"),
            start=match.start(),
            end=match.end(),
        )
        for match in mention_pattern.finditer(searchable_text)
    ]
    spans.sort(key=lambda span: span.start)
    return spans


def split_mention_instructions(text: str, router, source_agent: str) -> dict[str, str]:
    if not text:
        return {}

    spans = find_mention_spans(text, router)
    if source_agent == "Topic Agent":
        spans = [span for span in spans if span.agent_name != "Topic Agent"]

    if not spans:
        return {}

    segments: dict[str, list[str]] = {}
    empty_only_agents: set[str] = set()

    for index, span in enumerate(spans):
        next_start = spans[index + 1].start if index + 1 < len(spans) else len(text)
        segment = _clean_instruction_segment(text[span.end:next_start])
        if segment:
            segments.setdefault(span.agent_name, []).append(segment)
            empty_only_agents.discard(span.agent_name)
        elif span.agent_name not in segments:
            empty_only_agents.add(span.agent_name)

    instructions = {
        agent_name: "\n\n".join(agent_segments)
        for agent_name, agent_segments in segments.items()
        if agent_segments
    }
    for agent_name in empty_only_agents:
        if agent_name not in instructions:
            instructions[agent_name] = text

    return instructions


def _clean_instruction_segment(segment: str) -> str:
    return segment.strip().lstrip("：:，,").strip()
