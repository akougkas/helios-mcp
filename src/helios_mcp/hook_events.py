"""Hook event data model for Helios v2.

Defines typed dataclasses for each Claude Code hook event that Helios
consumes. Events are parsed from JSON stdin provided by Claude Code's
hook system and dispatched to the observation engine.

Event types:
- ToolUseEvent: tool call observation (pre/post)
- SubagentEvent: subagent lifecycle (start/stop)
- SessionEvent: session boundaries (start/end)
- NotificationEvent: agent notifications
- UserPromptEvent: user prompt submissions
- StopEvent: agent stop signal
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Union


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HookEvent:
    """Base for all hook events. Every event carries a timestamp."""

    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Concrete event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolUseEvent(HookEvent):
    """A tool invocation observed via PreToolUse or PostToolUse hooks.

    Attributes:
        tool_name: The tool that was called (e.g., "Read", "Edit", "Bash").
        tool_input_keys: Top-level keys from the tool input dict.
            Captures what the agent specified without storing sensitive values.
        duration_ms: Elapsed time in milliseconds (PostToolUse only, 0 for pre).
        success: Whether the tool call succeeded (PostToolUse only, True for pre).
        phase: "pre" or "post" indicating which hook fired.
    """

    tool_name: str = ""
    tool_input_keys: tuple[str, ...] = ()
    duration_ms: int = 0
    success: bool = True
    phase: str = "post"


@dataclass(frozen=True)
class SubagentEvent(HookEvent):
    """A subagent lifecycle event (start or stop).

    Attributes:
        agent_type: The type of subagent (e.g., "Explore", "Plan").
        agent_id: Unique identifier for this subagent instance.
        event_type: "start" or "stop".
    """

    agent_type: str = ""
    agent_id: str = ""
    event_type: str = "start"

    def __post_init__(self) -> None:
        if self.event_type not in ("start", "stop"):
            object.__setattr__(
                self, "event_type",
                "start" if self.event_type not in ("start", "stop") else self.event_type,
            )


@dataclass(frozen=True)
class SessionEvent(HookEvent):
    """A session boundary event.

    Attributes:
        event_type: "start" or "end".
        session_id: Optional session identifier.
    """

    event_type: str = "start"
    session_id: str = ""


@dataclass(frozen=True)
class NotificationEvent(HookEvent):
    """An agent notification event.

    Attributes:
        length: Character length of the notification content.
    """

    length: int = 0


@dataclass(frozen=True)
class UserPromptEvent(HookEvent):
    """A user prompt submission event.

    Attributes:
        length: Character length of the prompt.
        question_count: Number of question marks in the prompt.
    """

    length: int = 0
    question_count: int = 0


@dataclass(frozen=True)
class StopEvent(HookEvent):
    """Agent stop signal. Marks the end of an agent turn.

    Attributes:
        reason: Why the agent stopped (e.g., "end_turn", "max_tokens").
    """

    reason: str = "end_turn"


# Union type for all concrete events
AnyHookEvent = Union[
    ToolUseEvent,
    SubagentEvent,
    SessionEvent,
    NotificationEvent,
    UserPromptEvent,
    StopEvent,
]

# Mapping from CLI event-type strings to hook event names
_EVENT_TYPE_MAP: dict[str, str] = {
    "pre-tool": "tool_use",
    "post-tool": "tool_use",
    "subagent-start": "subagent",
    "subagent-stop": "subagent",
    "session-start": "session",
    "session-end": "session",
    "notification": "notification",
    "prompt-submit": "user_prompt",
    "stop": "stop",
}


# ---------------------------------------------------------------------------
# Parser / dispatcher
# ---------------------------------------------------------------------------

def parse_hook_stdin(raw_json: dict, event_type: str | None = None) -> AnyHookEvent:
    """Parse raw JSON from Claude Code hook stdin into a typed HookEvent.

    Claude Code pipes JSON to hook commands via stdin. This function
    dispatches to the correct event constructor based on the event_type
    argument (from the CLI subcommand) or from a "type" key in the JSON.

    Args:
        raw_json: The parsed JSON dict from stdin.
        event_type: The CLI event type string (e.g., "post-tool",
            "subagent-stop"). If None, inferred from raw_json["type"].

    Returns:
        A typed HookEvent subclass instance.

    Raises:
        ValueError: If the event type is unknown or the JSON is malformed.
    """
    if event_type is None:
        event_type = raw_json.get("type", "")

    if not event_type:
        raise ValueError("Cannot determine event type: no 'type' in JSON and no event_type argument")

    ts = _extract_timestamp(raw_json)

    if event_type in ("pre-tool", "post-tool"):
        return _parse_tool_use(raw_json, event_type, ts)
    if event_type in ("subagent-start", "subagent-stop"):
        return _parse_subagent(raw_json, event_type, ts)
    if event_type in ("session-start", "session-end"):
        return _parse_session(raw_json, event_type, ts)
    if event_type == "notification":
        return _parse_notification(raw_json, ts)
    if event_type == "prompt-submit":
        return _parse_user_prompt(raw_json, ts)
    if event_type == "stop":
        return _parse_stop(raw_json, ts)

    raise ValueError(f"Unknown event type: {event_type!r}")


def _extract_timestamp(raw_json: dict) -> float:
    """Extract timestamp from raw JSON, falling back to current time."""
    ts = raw_json.get("timestamp")
    if ts is not None:
        try:
            return float(ts)
        except (TypeError, ValueError):
            pass
    return time.time()


def _parse_tool_use(raw_json: dict, event_type: str, ts: float) -> ToolUseEvent:
    tool_name = raw_json.get("tool_name", "") or raw_json.get("tool", {}).get("name", "")
    tool_input = raw_json.get("tool_input", {}) or raw_json.get("tool", {}).get("input", {})
    input_keys = tuple(sorted(tool_input.keys())) if isinstance(tool_input, dict) else ()
    duration_ms = int(raw_json.get("duration_ms", 0))
    success = raw_json.get("success", True)
    phase = "pre" if event_type == "pre-tool" else "post"

    return ToolUseEvent(
        timestamp=ts,
        tool_name=str(tool_name),
        tool_input_keys=input_keys,
        duration_ms=duration_ms,
        success=bool(success),
        phase=phase,
    )


def _parse_subagent(raw_json: dict, event_type: str, ts: float) -> SubagentEvent:
    agent_type = raw_json.get("agent_type", "") or raw_json.get("type_name", "")
    agent_id = raw_json.get("agent_id", "") or raw_json.get("id", "")
    sub_event = "start" if event_type == "subagent-start" else "stop"

    return SubagentEvent(
        timestamp=ts,
        agent_type=str(agent_type),
        agent_id=str(agent_id),
        event_type=sub_event,
    )


def _parse_session(raw_json: dict, event_type: str, ts: float) -> SessionEvent:
    sub_event = "start" if event_type == "session-start" else "end"
    session_id = raw_json.get("session_id", "")

    return SessionEvent(
        timestamp=ts,
        event_type=sub_event,
        session_id=str(session_id) if session_id else "",
    )


def _parse_notification(raw_json: dict, ts: float) -> NotificationEvent:
    content = raw_json.get("content", "") or raw_json.get("message", "")
    length = len(str(content)) if content else 0

    return NotificationEvent(timestamp=ts, length=length)


def _parse_user_prompt(raw_json: dict, ts: float) -> UserPromptEvent:
    content = raw_json.get("content", "") or raw_json.get("prompt", "")
    text = str(content) if content else ""
    length = len(text)
    question_count = text.count("?")

    return UserPromptEvent(timestamp=ts, length=length, question_count=question_count)


def _parse_stop(raw_json: dict, ts: float) -> StopEvent:
    reason = raw_json.get("reason", "end_turn")
    return StopEvent(timestamp=ts, reason=str(reason) if reason else "end_turn")
