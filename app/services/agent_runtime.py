import re
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select

from app.models.agent_config import AgentConfig


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


_MENTION_SUFFIX_BOUNDARY = r"(?![A-Za-z0-9_])"


def strip_fenced_code(text: str) -> str:
    """Mask fenced code blocks while preserving string length and line positions."""
    if not text:
        return ""

    stripped_lines: list[str] = []
    in_fence = False

    for line in text.splitlines(keepends=True):
        starts_fence = line.lstrip().startswith("```")
        should_mask = in_fence or starts_fence

        if should_mask:
            stripped_lines.append(_mask_text_preserving_newlines(line))
        else:
            stripped_lines.append(line)

        if starts_fence:
            in_fence = not in_fence

    return "".join(stripped_lines)


def find_mention_spans(text: str, router) -> list[MentionSpan]:
    if not text:
        return []

    agent_names = router.get_all_agent_names()
    if not agent_names:
        return []

    return _find_named_mention_spans(text, agent_names)


def split_mention_instructions(text: str, router, source_agent: str) -> dict[str, str]:
    if not text:
        return {}

    dispatch_spans = find_mention_spans(text, router)
    boundary_spans = _find_boundary_mention_spans(text, router)
    if source_agent == "Topic Agent":
        dispatch_spans = [
            span for span in dispatch_spans if span.agent_name != "Topic Agent"
        ]

    dispatch_span_positions = {
        (span.start, span.end, span.agent_name) for span in dispatch_spans
    }
    spans = [
        (span, (span.start, span.end, span.agent_name) in dispatch_span_positions)
        for span in boundary_spans
    ]

    if not spans:
        return {}

    segments: dict[str, list[str]] = {}
    empty_only_agents: set[str] = set()

    for index, (span, should_dispatch) in enumerate(spans):
        next_start = spans[index + 1][0].start if index + 1 < len(spans) else len(text)
        if not should_dispatch:
            continue

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


def _mask_text_preserving_newlines(text: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in text)


def _find_named_mention_spans(text: str, agent_names: list[str]) -> list[MentionSpan]:
    if not text or not agent_names:
        return []

    names_pattern = "|".join(
        re.escape(name) for name in sorted(agent_names, key=len, reverse=True)
    )
    mention_pattern = re.compile(
        rf"@(?P<agent_name>{names_pattern}){_MENTION_SUFFIX_BOUNDARY}"
    )
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


def _find_boundary_mention_spans(text: str, router) -> list[MentionSpan]:
    configured_spans = _find_named_mention_spans(
        text,
        _get_configured_agent_names(router),
    )
    generic_spans = _find_generic_agent_mention_spans(text)

    spans_by_position: dict[tuple[int, int], MentionSpan] = {}
    for span in generic_spans + configured_spans:
        spans_by_position[(span.start, span.end)] = span

    spans = list(spans_by_position.values())
    spans.sort(key=lambda span: span.start)
    return spans


def _get_configured_agent_names(router) -> list[str]:
    db = getattr(router, "_db", None)
    if db is None:
        return list(router.get_all_agent_names())

    agents = db.exec(select(AgentConfig)).all()
    return [agent.name for agent in agents]


def _find_generic_agent_mention_spans(text: str) -> list[MentionSpan]:
    searchable_text = strip_fenced_code(text)
    pattern = re.compile(
        rf"@(?P<agent_name>[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*)* Agent)"
        rf"{_MENTION_SUFFIX_BOUNDARY}"
    )
    spans = [
        MentionSpan(
            agent_name=match.group("agent_name"),
            start=match.start(),
            end=match.end(),
        )
        for match in pattern.finditer(searchable_text)
    ]
    spans.sort(key=lambda span: span.start)
    return spans
