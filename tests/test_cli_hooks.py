"""Tests for CLI hook handlers (Task 1.4 + C3 compliance).

Tests the `helios-mcp hook <event-type>` subcommand that reads JSON
from stdin and persists observations. Covers all 18 event types.
"""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from helios_mcp.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def helios_dir(tmp_path):
    return tmp_path / "helios"


class TestHookCommand:
    def test_post_tool_event(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/test.py"}})
        result = runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        assert obs_file.exists()
        line = json.loads(obs_file.read_text().strip())
        assert line["event_type"] == "post-tool"
        assert line["data"]["tool_name"] == "Read"

    def test_pre_tool_event(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Edit"})
        result = runner.invoke(
            main, ["hook", "pre-tool", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_post_tool_failure_event(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Bash", "tool_input": {"command": "false"}})
        result = runner.invoke(
            main, ["hook", "post-tool-failure", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["event_type"] == "post-tool-failure"

    def test_subagent_start(self, runner, helios_dir):
        raw = json.dumps({"agent_type": "Explore", "agent_id": "a1"})
        result = runner.invoke(
            main, ["hook", "subagent-start", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_subagent_stop(self, runner, helios_dir):
        raw = json.dumps({"agent_type": "Plan", "agent_id": "a2"})
        result = runner.invoke(
            main, ["hook", "subagent-stop", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_session_start(self, runner, helios_dir):
        raw = json.dumps({"session_id": "s1", "source": "startup"})
        result = runner.invoke(
            main, ["hook", "session-start", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_session_end(self, runner, helios_dir):
        raw = json.dumps({"session_id": "s1", "reason": "logout"})
        result = runner.invoke(
            main, ["hook", "session-end", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_notification(self, runner, helios_dir):
        raw = json.dumps({"content": "Build succeeded"})
        result = runner.invoke(
            main, ["hook", "notification", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_prompt_submit(self, runner, helios_dir):
        raw = json.dumps({"content": "How do I fix this?"})
        result = runner.invoke(
            main, ["hook", "prompt-submit", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_stop_event(self, runner, helios_dir):
        raw = json.dumps({"stop_hook_active": False})
        result = runner.invoke(
            main, ["hook", "stop", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_instructions_loaded(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "instructions-loaded", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_permission_request(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Bash"})
        result = runner.invoke(
            main, ["hook", "permission-request", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_teammate_idle(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "teammate-idle", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_task_completed(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "task-completed", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_config_change(self, runner, helios_dir):
        raw = json.dumps({"source": "user", "file_path": "/path/config.json"})
        result = runner.invoke(
            main, ["hook", "config-change", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        assert result.exit_code == 0

    def test_worktree_create(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "worktree-create", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_worktree_remove(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "worktree-remove", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_pre_compact(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "pre-compact", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_invalid_event_type_rejected(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "bogus-event", "--helios-dir", str(helios_dir)],
            input="{}",
        )
        # Click rejects invalid choices before the handler runs
        assert result.exit_code != 0

    def test_empty_stdin(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
            input="",
        )
        assert result.exit_code == 0

    def test_malformed_json(self, runner, helios_dir):
        result = runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
            input="not json at all",
        )
        # Should not crash. Exit 0.
        assert result.exit_code == 0

    def test_custom_persona(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Bash"})
        result = runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir),
                   "--persona", "developer"],
            input=raw,
        )
        assert result.exit_code == 0
        obs_file = helios_dir / "observations" / "hooks" / "developer.jsonl"
        assert obs_file.exists()

    def test_multiple_events_append(self, runner, helios_dir):
        for i in range(3):
            raw = json.dumps({"tool_name": f"Tool{i}"})
            result = runner.invoke(
                main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
                input=raw,
            )
            assert result.exit_code == 0

        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        lines = obs_file.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_all_18_event_types_work(self, runner, helios_dir):
        """Every valid event type should exit 0 with minimal input."""
        event_types = [
            "pre-tool", "post-tool", "post-tool-failure",
            "subagent-start", "subagent-stop",
            "session-start", "session-end",
            "notification", "prompt-submit", "stop",
            "instructions-loaded", "permission-request",
            "teammate-idle", "task-completed",
            "config-change",
            "worktree-create", "worktree-remove",
            "pre-compact",
        ]
        for et in event_types:
            result = runner.invoke(
                main, ["hook", et, "--helios-dir", str(helios_dir)],
                input="{}",
            )
            assert result.exit_code == 0, f"Event type {et} failed with exit code {result.exit_code}"

    def test_observation_contains_timestamp(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Read"})
        runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert "timestamp" in line
        assert isinstance(line["timestamp"], float)

    def test_observation_contains_common_fields(self, runner, helios_dir):
        raw = json.dumps({
            "tool_name": "Read",
            "session_id": "sess-42",
            "transcript_path": "/tmp/t.jsonl",
            "cwd": "/home/user/project",
        })
        runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["session_id"] == "sess-42"
        assert line["transcript_path"] == "/tmp/t.jsonl"
        assert line["cwd"] == "/home/user/project"

    def test_common_fields_empty_when_missing(self, runner, helios_dir):
        raw = json.dumps({"tool_name": "Edit"})
        runner.invoke(
            main, ["hook", "post-tool", "--helios-dir", str(helios_dir)],
            input=raw,
        )
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["session_id"] == ""
        assert line["transcript_path"] == ""
        assert line["cwd"] == ""
