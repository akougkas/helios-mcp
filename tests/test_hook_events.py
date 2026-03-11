"""Tests for hook event data model (Task 1.1).

Covers event parsing, validation, edge cases, and the parse_hook_stdin
dispatcher for all event types Helios consumes from Claude Code hooks.
"""

import time

import pytest

from helios_mcp.hook_events import (
    AnyHookEvent,
    HookEvent,
    NotificationEvent,
    SessionEvent,
    StopEvent,
    SubagentEvent,
    ToolUseEvent,
    UserPromptEvent,
    parse_hook_stdin,
)


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
        evt = SessionEvent(event_type="start", session_id="sess-1")
        assert evt.event_type == "start"
        assert evt.session_id == "sess-1"

    def test_end(self):
        evt = SessionEvent(event_type="end")
        assert evt.event_type == "end"


class TestSessionParsing:
    def test_parse_session_start(self):
        raw = {"session_id": "s123"}
        evt = parse_hook_stdin(raw, "session-start")
        assert isinstance(evt, SessionEvent)
        assert evt.event_type == "start"
        assert evt.session_id == "s123"

    def test_parse_session_end(self):
        raw = {"session_id": "s123"}
        evt = parse_hook_stdin(raw, "session-end")
        assert isinstance(evt, SessionEvent)
        assert evt.event_type == "end"

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


# ---------------------------------------------------------------------------
# UserPromptEvent
# ---------------------------------------------------------------------------


class TestUserPromptEvent:
    def test_basic(self):
        evt = UserPromptEvent(length=100, question_count=3)
        assert evt.length == 100
        assert evt.question_count == 3

    def test_defaults(self):
        evt = UserPromptEvent()
        assert evt.length == 0
        assert evt.question_count == 0


class TestUserPromptParsing:
    def test_parse_prompt(self):
        raw = {"content": "How do I fix this? And what about tests?"}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptEvent)
        assert evt.length == len("How do I fix this? And what about tests?")
        assert evt.question_count == 2

    def test_parse_prompt_alt_key(self):
        raw = {"prompt": "Do this now"}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptEvent)
        assert evt.length == len("Do this now")
        assert evt.question_count == 0

    def test_parse_prompt_empty(self):
        raw = {}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptEvent)
        assert evt.length == 0
        assert evt.question_count == 0


# ---------------------------------------------------------------------------
# StopEvent
# ---------------------------------------------------------------------------


class TestStopEvent:
    def test_basic(self):
        evt = StopEvent(reason="max_tokens")
        assert evt.reason == "max_tokens"

    def test_default_reason(self):
        evt = StopEvent()
        assert evt.reason == "end_turn"


class TestStopParsing:
    def test_parse_stop(self):
        raw = {"reason": "max_tokens"}
        evt = parse_hook_stdin(raw, "stop")
        assert isinstance(evt, StopEvent)
        assert evt.reason == "max_tokens"

    def test_parse_stop_default(self):
        raw = {}
        evt = parse_hook_stdin(raw, "stop")
        assert isinstance(evt, StopEvent)
        assert evt.reason == "end_turn"


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
        raw = {"type": "stop", "reason": "end_turn"}
        evt = parse_hook_stdin(raw)
        assert isinstance(evt, StopEvent)

    def test_explicit_type_overrides_json_type(self):
        raw = {"type": "stop", "content": "hello?"}
        evt = parse_hook_stdin(raw, "prompt-submit")
        assert isinstance(evt, UserPromptEvent)

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

    def test_all_event_types_dispatch(self):
        """Every supported event type string produces the correct class."""
        cases = [
            ("pre-tool", {"tool_name": "X"}, ToolUseEvent),
            ("post-tool", {"tool_name": "X"}, ToolUseEvent),
            ("subagent-start", {}, SubagentEvent),
            ("subagent-stop", {}, SubagentEvent),
            ("session-start", {}, SessionEvent),
            ("session-end", {}, SessionEvent),
            ("notification", {}, NotificationEvent),
            ("prompt-submit", {}, UserPromptEvent),
            ("stop", {}, StopEvent),
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
            ("subagent-start", {}),
            ("session-end", {}),
            ("notification", {}),
            ("prompt-submit", {}),
            ("stop", {}),
        ]
        for event_type, raw in types_and_raws:
            evt = parse_hook_stdin(raw, event_type)
            assert isinstance(evt, HookEvent)
