"""Hook event data model for Helios v2.

Defines typed dataclasses for each Claude Code hook event that Helios
consumes. Events are parsed from JSON stdin provided by Claude Code's
hook system and dispatched to the observation engine.

Claude Code provides 18 hook event types. All events share common fields
(session_id, transcript_path, cwd, permission_mode, hook_event_name).
Helios consumes all 18 for observation.

Event types:
- ToolUseEvent: tool call observation (PreToolUse/PostToolUse/PostToolUseFailure)
- SubagentEvent: subagent lifecycle (SubagentStart/SubagentStop)
- SessionEvent: session boundaries (SessionStart/SessionEnd)
- NotificationEvent: agent notifications (Notification)
- UserPromptSubmitEvent: user prompt submissions (UserPromptSubmit)
- StopEvent: agent stop signal (Stop)
- InstructionsLoadedEvent: CLAUDE.md rules loaded (InstructionsLoaded)
- PermissionRequestEvent: permission dialog (PermissionRequest)
- TeammateIdleEvent: teammate goes idle (TeammateIdle)
- TaskCompletedEvent: task marked completed (TaskCompleted)
- ConfigChangeEvent: config file changed (ConfigChange)
- WorktreeEvent: worktree lifecycle (WorktreeCreate/WorktreeRemove)
- PreCompactEvent: before context compaction (PreCompact)
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
    """Base for all hook events.

    Every event carries a timestamp and the common fields that Claude Code
    provides on stdin for all hook invocations.
    """

    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    transcript_path: str = ""
    cwd: str = ""
    permission_mode: str = ""
    hook_event_name: str = ""


# ---------------------------------------------------------------------------
# Concrete event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolUseEvent(HookEvent):
    """A tool invocation observed via PreToolUse, PostToolUse, or PostToolUseFailure hooks.

    Attributes:
        tool_name: The tool that was called (e.g., "Read", "Edit", "Bash").
        tool_input_keys: Top-level keys from the tool input dict.
            Captures what the agent specified without storing sensitive values.
        duration_ms: Elapsed time in milliseconds (PostToolUse only, 0 for pre).
        success: Whether the tool call succeeded (False for PostToolUseFailure).
        phase: "pre", "post", or "post_failure" indicating which hook fired.
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
        source: For SessionStart, how the session began (startup/resume/clear/compact).
        reason: For SessionEnd, why the session ended (clear/logout/prompt_input_exit/other).
    """

    event_type: str = "start"
    source: str = ""
    reason: str = ""


@dataclass(frozen=True)
class NotificationEvent(HookEvent):
    """An agent notification event.

    Attributes:
        length: Character length of the notification content.
        notification_type: The notification_type field from the event.
    """

    length: int = 0
    notification_type: str = ""


@dataclass(frozen=True)
class UserPromptSubmitEvent(HookEvent):
    """A user prompt submission event (UserPromptSubmit).

    Attributes:
        length: Character length of the prompt.
        question_count: Number of question marks in the prompt.
    """

    length: int = 0
    question_count: int = 0


# Keep backward-compatible alias
UserPromptEvent = UserPromptSubmitEvent


@dataclass(frozen=True)
class StopEvent(HookEvent):
    """Agent stop signal. Marks the end of an agent turn.

    Attributes:
        stop_hook_active: Whether the stop hook is currently active.
    """

    stop_hook_active: bool = False


@dataclass(frozen=True)
class InstructionsLoadedEvent(HookEvent):
    """Fired when CLAUDE.md or .claude/rules files are loaded."""
    pass


@dataclass(frozen=True)
class PermissionRequestEvent(HookEvent):
    """Fired when a permission dialog appears.

    Attributes:
        tool_name: The tool requesting permission.
    """

    tool_name: str = ""


@dataclass(frozen=True)
class TeammateIdleEvent(HookEvent):
    """Fired when a teammate goes idle."""
    pass


@dataclass(frozen=True)
class TaskCompletedEvent(HookEvent):
    """Fired when a task is marked completed."""
    pass


@dataclass(frozen=True)
class ConfigChangeEvent(HookEvent):
    """Fired when a config file changes.

    Attributes:
        source: What triggered the change.
        file_path: Path to the changed config file.
    """

    source: str = ""
    file_path: str = ""


@dataclass(frozen=True)
class WorktreeEvent(HookEvent):
    """A worktree lifecycle event (create or remove).

    Attributes:
        event_type: "create" or "remove".
    """

    event_type: str = "create"


@dataclass(frozen=True)
class PreCompactEvent(HookEvent):
    """Fired before context compaction."""
    pass


# Union type for all concrete events
AnyHookEvent = Union[
    ToolUseEvent,
    SubagentEvent,
    SessionEvent,
    NotificationEvent,
    UserPromptSubmitEvent,
    StopEvent,
    InstructionsLoadedEvent,
    PermissionRequestEvent,
    TeammateIdleEvent,
    TaskCompletedEvent,
    ConfigChangeEvent,
    WorktreeEvent,
    PreCompactEvent,
]

# Mapping from CLI event-type strings to hook event names
_EVENT_TYPE_MAP: dict[str, str] = {
    "pre-tool": "tool_use",
    "post-tool": "tool_use",
    "post-tool-failure": "tool_use",
    "subagent-start": "subagent",
    "subagent-stop": "subagent",
    "session-start": "session",
    "session-end": "session",
    "notification": "notification",
    "prompt-submit": "user_prompt",
    "stop": "stop",
    "instructions-loaded": "instructions_loaded",
    "permission-request": "permission_request",
    "teammate-idle": "teammate_idle",
    "task-completed": "task_completed",
    "config-change": "config_change",
    "worktree-create": "worktree",
    "worktree-remove": "worktree",
    "pre-compact": "pre_compact",
}


# ---------------------------------------------------------------------------
# Parser / dispatcher
# ---------------------------------------------------------------------------

def _extract_common_fields(raw_json: dict) -> dict:
    """Extract common fields shared by all Claude Code hook events."""
    return {
        "session_id": str(raw_json.get("session_id", "") or ""),
        "transcript_path": str(raw_json.get("transcript_path", "") or ""),
        "cwd": str(raw_json.get("cwd", "") or ""),
        "permission_mode": str(raw_json.get("permission_mode", "") or ""),
        "hook_event_name": str(raw_json.get("hook_event_name", "") or ""),
    }


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
    common = _extract_common_fields(raw_json)

    if event_type in ("pre-tool", "post-tool", "post-tool-failure"):
        return _parse_tool_use(raw_json, event_type, ts, common)
    if event_type in ("subagent-start", "subagent-stop"):
        return _parse_subagent(raw_json, event_type, ts, common)
    if event_type in ("session-start", "session-end"):
        return _parse_session(raw_json, event_type, ts, common)
    if event_type == "notification":
        return _parse_notification(raw_json, ts, common)
    if event_type == "prompt-submit":
        return _parse_user_prompt(raw_json, ts, common)
    if event_type == "stop":
        return _parse_stop(raw_json, ts, common)
    if event_type == "instructions-loaded":
        return InstructionsLoadedEvent(timestamp=ts, **common)
    if event_type == "permission-request":
        return _parse_permission_request(raw_json, ts, common)
    if event_type == "teammate-idle":
        return TeammateIdleEvent(timestamp=ts, **common)
    if event_type == "task-completed":
        return TaskCompletedEvent(timestamp=ts, **common)
    if event_type == "config-change":
        return _parse_config_change(raw_json, ts, common)
    if event_type in ("worktree-create", "worktree-remove"):
        return _parse_worktree(raw_json, event_type, ts, common)
    if event_type == "pre-compact":
        return PreCompactEvent(timestamp=ts, **common)

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


def _parse_tool_use(raw_json: dict, event_type: str, ts: float, common: dict) -> ToolUseEvent:
    tool_name = raw_json.get("tool_name", "") or raw_json.get("tool", {}).get("name", "")
    tool_input = raw_json.get("tool_input", {}) or raw_json.get("tool", {}).get("input", {})
    input_keys = tuple(sorted(tool_input.keys())) if isinstance(tool_input, dict) else ()
    duration_ms = int(raw_json.get("duration_ms", 0))

    if event_type == "post-tool-failure":
        success = False
        phase = "post_failure"
    elif event_type == "pre-tool":
        success = raw_json.get("success", True)
        phase = "pre"
    else:
        success = raw_json.get("success", True)
        phase = "post"

    return ToolUseEvent(
        timestamp=ts,
        tool_name=str(tool_name),
        tool_input_keys=input_keys,
        duration_ms=duration_ms,
        success=bool(success),
        phase=phase,
        **common,
    )


def _parse_subagent(raw_json: dict, event_type: str, ts: float, common: dict) -> SubagentEvent:
    agent_type = raw_json.get("agent_type", "") or raw_json.get("type_name", "")
    agent_id = raw_json.get("agent_id", "") or raw_json.get("id", "")
    sub_event = "start" if event_type == "subagent-start" else "stop"

    return SubagentEvent(
        timestamp=ts,
        agent_type=str(agent_type),
        agent_id=str(agent_id),
        event_type=sub_event,
        **common,
    )


def _parse_session(raw_json: dict, event_type: str, ts: float, common: dict) -> SessionEvent:
    sub_event = "start" if event_type == "session-start" else "end"
    source = str(raw_json.get("source", "") or "")
    reason = str(raw_json.get("reason", "") or "")

    return SessionEvent(
        timestamp=ts,
        event_type=sub_event,
        source=source,
        reason=reason,
        **common,
    )


def _parse_notification(raw_json: dict, ts: float, common: dict) -> NotificationEvent:
    content = raw_json.get("content", "") or raw_json.get("message", "")
    length = len(str(content)) if content else 0
    notification_type = str(raw_json.get("notification_type", "") or "")

    return NotificationEvent(timestamp=ts, length=length, notification_type=notification_type, **common)


def _parse_user_prompt(raw_json: dict, ts: float, common: dict) -> UserPromptSubmitEvent:
    content = raw_json.get("content", "") or raw_json.get("prompt", "")
    text = str(content) if content else ""
    length = len(text)
    question_count = text.count("?")

    return UserPromptSubmitEvent(timestamp=ts, length=length, question_count=question_count, **common)


def _parse_stop(raw_json: dict, ts: float, common: dict) -> StopEvent:
    stop_hook_active = bool(raw_json.get("stop_hook_active", False))
    return StopEvent(timestamp=ts, stop_hook_active=stop_hook_active, **common)


def _parse_permission_request(raw_json: dict, ts: float, common: dict) -> PermissionRequestEvent:
    tool_name = str(raw_json.get("tool_name", "") or "")
    return PermissionRequestEvent(timestamp=ts, tool_name=tool_name, **common)


def _parse_config_change(raw_json: dict, ts: float, common: dict) -> ConfigChangeEvent:
    source = str(raw_json.get("source", "") or "")
    file_path = str(raw_json.get("file_path", "") or "")
    return ConfigChangeEvent(timestamp=ts, source=source, file_path=file_path, **common)


def _parse_worktree(raw_json: dict, event_type: str, ts: float, common: dict) -> WorktreeEvent:
    wt_event = "create" if event_type == "worktree-create" else "remove"
    return WorktreeEvent(timestamp=ts, event_type=wt_event, **common)
