"""Tests for hook event data model (Task 1.1 + C1 compliance).

Covers event parsing, validation, edge cases, and the parse_hook_stdin
dispatcher for all 18 event types Helios consumes from Claude Code hooks.
"""

import time

import pytest

from helios_mcp.hook_events import (
    AnyHookEvent,
    ConfigChangeEvent,
    HookEvent,
    InstructionsLoadedEvent,
    NotificationEvent,
    PermissionRequestEvent,
    PreCompactEvent,
    SessionEvent,
    StopEvent,
    SubagentEvent,
    TaskCompletedEvent,
    TeammateIdleEvent,
    ToolUseEvent,
    UserPromptEvent,
    UserPromptSubmitEvent,
    WorktreeEvent,
    parse_hook_stdin,
)


# ---------------------------------------------------------------------------
# Base HookEvent common fields
# ---------------------------------------------------------------------------


class TestHookEventCommonFields:
    def test_common_fields_default_empty(self):
        evt = HookEvent()
        assert evt.session_id == ""
        assert evt.transcript_path == ""
        assert evt.cwd == ""
        assert evt.permission_mode == ""
        assert evt.hook_event_name == ""

    def test_common_fields_set(self):
        evt = HookEvent(
            session_id="abc123",
            transcript_path="/path/to/transcript.jsonl",
            cwd="/home/user/project",
            permission_mode="default",
            hook_event_name="PostToolUse",
        )
        assert evt.session_id == "abc123"
        assert evt.transcript_path == "/path/to/transcript.jsonl"
        assert evt.cwd == "/home/user/project"
        assert evt.permission_mode == "default"
        assert evt.hook_event_name == "PostToolUse"

    def test_common_fields_parsed_from_stdin(self):
        raw = {
            "session_id": "sess-42",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/home/user/project",
            "permission_mode": "plan",
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
        }
        evt = parse_hook_stdin(raw, "post-tool")
        assert evt.session_id == "sess-42"
        assert evt.transcript_path == "/tmp/transcript.jsonl"
        assert evt.cwd == "/home/user/project"
        assert evt.permission_mode == "plan"
        assert evt.hook_event_name == "PostToolUse"

    def test_common_fields_default_when_missing(self):
        raw = {"tool_name": "Edit"}
        evt = parse_hook_stdin(raw, "post-tool")
        assert evt.session_id == ""
        assert evt.transcript_path == ""
        assert evt.cwd == ""

    def test_common_fields_inherited_by_all_event_types(self):
        raw = {"session_id": "s1", "cwd": "/tmp"}
        for event_type in [
            "post-tool", "subagent-start", "session-start",
            "notification", "prompt-submit", "stop",
            "instructions-loaded", "permission-request",
            "teammate-idle", "task-completed", "config-change",
            "worktree-create", "pre-compact",
        ]:
            evt = parse_hook_stdin(raw, event_type)
            assert evt.session_id == "s1", f"{event_type} missing session_id"
            assert evt.cwd == "/tmp", f"{event_type} missing cwd"


# ---------------------------------------------------------------------------
# ToolUseEvent
# ---------------------------------------------------------------------------


class TestToolUseEvent:
    def test_basic_construction(self):
        evt = ToolUseEvent(
            tool_name="Read",
            tool_input_keys=("file_path",),
            duration_ms=42,
            success=True,
            phase="post",
        )
        assert evt.tool_name == "Read"
        assert evt.tool_input_keys == ("file_path",)
        assert evt.duration_ms == 42
        assert evt.success is True
        assert evt.phase == "post"

    def test_default_values(self):
        evt = ToolUseEvent()
        assert evt.tool_name == ""
        assert evt.tool_input_keys == ()
        assert evt.duration_ms == 0
        assert evt.success is True
        assert evt.phase == "post"

    def test_frozen(self):
        evt = ToolUseEvent(tool_name="Edit")
        with pytest.raises(AttributeError):
            evt.tool_name = "Write"  # type: ignore[misc]

    def test_timestamp_auto_generated(self):
        before = time.time()
        evt = ToolUseEvent(tool_name="Bash")
        after = time.time()
        assert before <= evt.timestamp <= after

    def test_is_hook_event(self):
        evt = ToolUseEvent(tool_name="Grep")
        assert isinstance(evt, HookEvent)

    def test_pre_phase(self):
        evt = ToolUseEvent(tool_name="Edit", phase="pre")
        assert evt.phase == "pre"
        assert evt.duration_ms == 0

    def test_post_failure_phase(self):
        evt = ToolUseEvent(tool_name="Bash", phase="post_failure", success=False)
        assert evt.phase == "post_failure"
        assert evt.success is False


class TestToolUseParsing:
    def test_parse_post_tool(self):
        raw = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "duration_ms": 150,
            "success": True,
        }
        evt = parse_hook_stdin(raw, "post-tool")
        assert isinstance(evt, ToolUseEvent)
        assert evt.tool_name == "Read"
        assert evt.tool_input_keys == ("file_path",)
        assert evt.duration_ms == 150
        assert evt.success is True
        assert evt.phase == "post"

    def test_parse_pre_tool(self):
        raw = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/a.py", "old_string": "x", "new_string": "y"},
        }
        evt = parse_hook_stdin(raw, "pre-tool")
        assert isinstance(evt, ToolUseEvent)
        assert evt.tool_name == "Edit"
        assert evt.tool_input_keys == ("file_path", "new_string", "old_string")
        assert evt.phase == "pre"

    def test_parse_post_tool_failure(self):
        raw = {
            "tool_name": "Bash",
            "tool_input": {"command": "false"},
            "duration_ms": 10,
        }
        evt = parse_hook_stdin(raw, "post-tool-failure")
        assert isinstance(evt, ToolUseEvent)
        assert evt.tool_name == "Bash"
        assert evt.success is False
        assert evt.phase == "post_failure"

    def test_parse_tool_nested_format(self):
        raw = {
            "tool": {"name": "Bash", "input": {"command": "ls"}},
        }
        evt = parse_hook_stdin(raw, "post-tool")
        assert isinstance(evt, ToolUseEvent)
        assert evt.tool_name == "Bash"
        assert evt.tool_input_keys == ("command",)

    def test_parse_tool_failed(self):
        raw = {
            "tool_name": "Bash",
            "tool_input": {"command": "false"},
            "duration_ms": 10,
            "success": False,
        }
        evt = parse_hook_stdin(raw, "post-tool")
        assert evt.success is False

    def test_parse_tool_empty_input(self):
        raw = {"tool_name": "Read"}
        evt = parse_hook_stdin(raw, "post-tool")
        assert isinstance(evt, ToolUseEvent)
        assert evt.tool_input_keys == ()

    def test_parse_tool_missing_name(self):
        raw = {"tool_input": {"x": 1}}
        evt = parse_hook_stdin(raw, "post-tool")
        assert isinstance(evt, ToolUseEvent)
        assert evt.tool_name == ""


# ---------------------------------------------------------------------------
# SubagentEvent
# ---------------------------------------------------------------------------


class TestSubagentEvent:
    def test_basic_construction(self):
        evt = SubagentEvent(agent_type="Explore", agent_id="abc123", event_type="start")
        assert evt.agent_type == "Explore"
        assert evt.agent_id == "abc123"
        assert evt.event_type == "start"

    def test_stop_event(self):
        evt = SubagentEvent(agent_type="Plan", agent_id="xyz", event_type="stop")
        assert evt.event_type == "stop"

    def test_default_is_start(self):
        evt = SubagentEvent()
        assert evt.event_type == "start"


class TestSubagentParsing:
    def test_parse_subagent_start(self):
        raw = {"agent_type": "Explore", "agent_id": "sa-001"}
        evt = parse_hook_stdin(raw, "subagent-start")
        assert isinstance(evt, SubagentEvent)
        assert evt.agent_type == "Explore"
        assert evt.agent_id == "sa-001"
        assert evt.event_type == "start"

    def test_parse_subagent_stop(self):
        raw = {"agent_type": "Plan", "agent_id": "sa-002"}
        evt = parse_hook_stdin(raw, "subagent-stop")
        assert isinstance(evt, SubagentEvent)
        assert evt.event_type == "stop"

    def test_parse_subagent_alt_keys(self):
        raw = {"type_name": "general-purpose", "id": "abc"}
        evt = parse_hook_stdin(raw, "subagent-start")
        assert isinstance(evt, SubagentEvent)
        assert evt.agent_type == "general-purpose"
        assert evt.agent_id == "abc"

    def test_parse_subagent_empty(self):
        raw = {}
        evt = parse_hook_stdin(raw, "subagent-start")
        assert isinstance(evt, SubagentEvent)
        assert evt.agent_type == ""
        assert evt.agent_id == ""


# ---------------------------------------------------------------------------
# SessionEvent
# ---------------------------------------------------------------------------


class TestSessionEvent:
    def test_start(self):
        evt = SessionEvent(event_type="start", source="startup")
        assert evt.event_type == "start"
        assert evt.source == "startup"

    def test_end(self):
        evt = SessionEvent(event_type="end", reason="logout")
        assert evt.event_type == "end"
        assert evt.reason == "logout"

    def test_defaults(self):
        evt = SessionEvent()
        assert evt.source == ""
        assert evt.reason == ""


class TestSessionParsing:
    def test_parse_session_start(self):
        raw = {"session_id": "s123", "source": "startup"}
        evt = parse_hook_stdin(raw, "session-start")
        assert isinstance(evt, SessionEvent)
        assert evt.event_type == "start"
        assert evt.session_id == "s123"
        assert evt.source == "startup"

    def test_parse_session_end(self):
        raw = {"session_id": "s123", "reason": "logout"}
        evt = parse_hook_stdin(raw, "session-end")
        assert isinstance(evt, SessionEvent)
        assert evt.event_type == "end"
        assert evt.reason == "logout"

    def test_parse_session_no_id(self):
        raw = {}
        evt = parse_hook_stdin(raw, "session-start")
        assert isinstance(evt, SessionEvent)
        assert evt.session_id == ""


# ---------------------------------------------------------------------------
# NotificationEvent
# ---------------------------------------------------------------------------


class TestNotificationEvent:
    def test_basic(self):
        evt = NotificationEvent(length=42)
        assert evt.length == 42

    def test_default_length(self):
        evt = NotificationEvent()
        assert evt.length == 0

    def test_notification_type(self):
        evt = NotificationEvent(notification_type="info")
        assert evt.notification_type == "info"


class TestNotificationParsing:
    def test_parse_with_content(self):
        raw = {"content": "Build succeeded!"}
        evt = parse_hook_stdin(raw, "notification")
        assert isinstance(evt, NotificationEvent)
        assert evt.length == len("Build succeeded!")

    def test_parse_with_message_key(self):
        raw = {"message": "Done"}
        evt = parse_hook_stdin(raw, "notification")
        assert isinstance(evt, NotificationEvent)
        assert evt.length == len("Done")

    def test_parse_empty(self):
        raw = {}
        evt = parse_hook_stdin(raw, "notification")
        assert isinstance(evt, NotificationEvent)
        assert evt.length == 0

    def test_parse_with_notification_type(self):
        raw = {"content": "x", "notification_type": "warning"}
        evt = parse_hook_stdin(raw, "notification")
        assert evt.notification_type == "warning"


# ---------------------------------------------------------------------------
# UserPromptSubmitEvent
# ---------------------------------------------------------------------------


class TestUserPromptSubmitEvent:
    def test_basic(self):
        evt = UserPromptSubmitEvent(length=100, question_count=3)
        assert evt.length == 100
        assert evt.question_count == 3

    def test_defaults(self):
        evt = UserPromptSubmitEvent()
        assert evt.length == 0
        assert evt.question_count == 0

    def test_backward_compatible_alias(self):
        assert UserPromptEvent is UserPromptSubmitEvent
        evt = UserPromptEvent(length=50)
        assert isinstance(evt, UserPromptSubmitEvent)


class TestUserPromptParsing:
    def test_parse_prompt(self):
        raw = {"content": "How do I fix this? And what about tests?"}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptSubmitEvent)
        assert evt.length == len("How do I fix this? And what about tests?")
        assert evt.question_count == 2

    def test_parse_prompt_alt_key(self):
        raw = {"prompt": "Do this now"}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptSubmitEvent)
        assert evt.length == len("Do this now")
        assert evt.question_count == 0

    def test_parse_prompt_empty(self):
        raw = {}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptSubmitEvent)
        assert evt.length == 0
        assert evt.question_count == 0


# ---------------------------------------------------------------------------
# StopEvent
# ---------------------------------------------------------------------------


class TestStopEvent:
    def test_basic(self):
        evt = StopEvent(stop_hook_active=True)
        assert evt.stop_hook_active is True

    def test_default(self):
        evt = StopEvent()
        assert evt.stop_hook_active is False


class TestStopParsing:
    def test_parse_stop_active(self):
        raw = {"stop_hook_active": True}
        evt = parse_hook_stdin(raw, "stop")
        assert isinstance(evt, StopEvent)
        assert evt.stop_hook_active is True

    def test_parse_stop_default(self):
        raw = {}
        evt = parse_hook_stdin(raw, "stop")
        assert isinstance(evt, StopEvent)
        assert evt.stop_hook_active is False


# ---------------------------------------------------------------------------
# New event types (C1 compliance)
# ---------------------------------------------------------------------------


class TestInstructionsLoadedEvent:
    def test_construction(self):
        evt = InstructionsLoadedEvent()
        assert isinstance(evt, HookEvent)

    def test_parsing(self):
        raw = {"session_id": "s1"}
        evt = parse_hook_stdin(raw, "instructions-loaded")
        assert isinstance(evt, InstructionsLoadedEvent)
        assert evt.session_id == "s1"


class TestPermissionRequestEvent:
    def test_construction(self):
        evt = PermissionRequestEvent(tool_name="Bash")
        assert evt.tool_name == "Bash"

    def test_parsing(self):
        raw = {"tool_name": "Edit"}
        evt = parse_hook_stdin(raw, "permission-request")
        assert isinstance(evt, PermissionRequestEvent)
        assert evt.tool_name == "Edit"


class TestTeammateIdleEvent:
    def test_construction(self):
        evt = TeammateIdleEvent()
        assert isinstance(evt, HookEvent)

    def test_parsing(self):
        raw = {}
        evt = parse_hook_stdin(raw, "teammate-idle")
        assert isinstance(evt, TeammateIdleEvent)


class TestTaskCompletedEvent:
    def test_construction(self):
        evt = TaskCompletedEvent()
        assert isinstance(evt, HookEvent)

    def test_parsing(self):
        raw = {"session_id": "s1"}
        evt = parse_hook_stdin(raw, "task-completed")
        assert isinstance(evt, TaskCompletedEvent)
        assert evt.session_id == "s1"


class TestConfigChangeEvent:
    def test_construction(self):
        evt = ConfigChangeEvent(source="user", file_path="/home/.claude/settings.json")
        assert evt.source == "user"
        assert evt.file_path == "/home/.claude/settings.json"

    def test_parsing(self):
        raw = {"source": "plugin", "file_path": "/path/to/config.json"}
        evt = parse_hook_stdin(raw, "config-change")
        assert isinstance(evt, ConfigChangeEvent)
        assert evt.source == "plugin"
        assert evt.file_path == "/path/to/config.json"


class TestWorktreeEvent:
    def test_create(self):
        evt = WorktreeEvent(event_type="create")
        assert evt.event_type == "create"

    def test_remove(self):
        evt = WorktreeEvent(event_type="remove")
        assert evt.event_type == "remove"

    def test_parse_create(self):
        raw = {}
        evt = parse_hook_stdin(raw, "worktree-create")
        assert isinstance(evt, WorktreeEvent)
        assert evt.event_type == "create"

    def test_parse_remove(self):
        raw = {}
        evt = parse_hook_stdin(raw, "worktree-remove")
        assert isinstance(evt, WorktreeEvent)
        assert evt.event_type == "remove"


class TestPreCompactEvent:
    def test_construction(self):
        evt = PreCompactEvent()
        assert isinstance(evt, HookEvent)

    def test_parsing(self):
        raw = {"session_id": "s1"}
        evt = parse_hook_stdin(raw, "pre-compact")
        assert isinstance(evt, PreCompactEvent)
        assert evt.session_id == "s1"


# ---------------------------------------------------------------------------
# parse_hook_stdin dispatcher
# ---------------------------------------------------------------------------


class TestParseHookStdin:
    def test_unknown_event_type_raises(self):
        with pytest.raises(ValueError, match="Unknown event type"):
            parse_hook_stdin({}, "unknown-event")

    def test_no_event_type_no_json_type_raises(self):
        with pytest.raises(ValueError, match="Cannot determine event type"):
            parse_hook_stdin({})

    def test_infer_type_from_json(self):
        raw = {"type": "stop", "stop_hook_active": False}
        evt = parse_hook_stdin(raw)
        assert isinstance(evt, StopEvent)

    def test_explicit_type_overrides_json_type(self):
        raw = {"type": "stop", "content": "hello?"}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptSubmitEvent)

    def test_custom_timestamp_preserved(self):
        ts = 1700000000.0
        raw = {"timestamp": ts, "tool_name": "Read"}
        evt = parse_hook_stdin(raw, "post-tool")
        assert evt.timestamp == ts

    def test_invalid_timestamp_falls_back(self):
        raw = {"timestamp": "not-a-number", "tool_name": "Read"}
        before = time.time()
        evt = parse_hook_stdin(raw, "post-tool")
        after = time.time()
        assert before <= evt.timestamp <= after

    def test_all_18_event_types_dispatch(self):
        """Every supported event type string produces the correct class."""
        cases = [
            ("pre-tool", {"tool_name": "X"}, ToolUseEvent),
            ("post-tool", {"tool_name": "X"}, ToolUseEvent),
            ("post-tool-failure", {"tool_name": "X"}, ToolUseEvent),
            ("subagent-start", {}, SubagentEvent),
            ("subagent-stop", {}, SubagentEvent),
            ("session-start", {}, SessionEvent),
            ("session-end", {}, SessionEvent),
            ("notification", {}, NotificationEvent),
            ("prompt-submit", {}, UserPromptSubmitEvent),
            ("stop", {}, StopEvent),
            ("instructions-loaded", {}, InstructionsLoadedEvent),
            ("permission-request", {}, PermissionRequestEvent),
            ("teammate-idle", {}, TeammateIdleEvent),
            ("task-completed", {}, TaskCompletedEvent),
            ("config-change", {}, ConfigChangeEvent),
            ("worktree-create", {}, WorktreeEvent),
            ("worktree-remove", {}, WorktreeEvent),
            ("pre-compact", {}, PreCompactEvent),
        ]
        for event_type, raw, expected_cls in cases:
            evt = parse_hook_stdin(raw, event_type)
            assert isinstance(evt, expected_cls), (
                f"event_type={event_type!r} should produce {expected_cls.__name__}, "
                f"got {type(evt).__name__}"
            )

    def test_all_events_are_hook_events(self):
        """Every parsed event is a HookEvent subclass."""
        types_and_raws = [
            ("post-tool", {"tool_name": "X"}),
            ("post-tool-failure", {"tool_name": "X"}),
            ("subagent-start", {}),
            ("session-end", {}),
            ("notification", {}),
            ("prompt-submit", {}),
            ("stop", {}),
            ("instructions-loaded", {}),
            ("permission-request", {}),
            ("teammate-idle", {}),
            ("task-completed", {}),
            ("config-change", {}),
            ("worktree-create", {}),
            ("pre-compact", {}),
        ]
        for event_type, raw in types_and_raws:
            evt = parse_hook_stdin(raw, event_type)
            assert isinstance(evt, HookEvent)
