"""Tests for the fast-path hook handler script.

Validates that hook-handler.py correctly writes JSONL observation records
without depending on the full helios-mcp CLI stack. This is the hot path
that Claude Code invokes on every tool call.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HANDLER = Path(__file__).parent.parent / "helios-plugin" / "hooks" / "hook-handler.py"


@pytest.fixture
def helios_dir(tmp_path):
    d = tmp_path / "helios"
    return d


def _run_handler(event_type: str, stdin_data: dict, helios_dir: Path) -> subprocess.CompletedProcess:
    """Run the hook handler script with the given event type and stdin data."""
    env = os.environ.copy()
    env["HELIOS_DIR"] = str(helios_dir)
    return subprocess.run(
        [sys.executable, str(HANDLER), event_type],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )


class TestHookHandlerBasics:
    def test_handler_script_exists(self):
        assert HANDLER.is_file()

    def test_exits_zero(self, helios_dir):
        result = _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        assert result.returncode == 0

    def test_creates_observation_file(self, helios_dir):
        _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        assert obs_file.exists()

    def test_writes_valid_jsonl(self, helios_dir):
        _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["event_type"] == "post-tool"
        assert isinstance(line["timestamp"], float)

    def test_preserves_common_fields(self, helios_dir):
        data = {
            "tool_name": "Edit",
            "session_id": "sess-42",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/home/user/project",
        }
        _run_handler("post-tool", data, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["session_id"] == "sess-42"
        assert line["transcript_path"] == "/tmp/transcript.jsonl"
        assert line["cwd"] == "/home/user/project"

    def test_stores_full_data(self, helios_dir):
        data = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        _run_handler("post-tool", data, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["data"]["tool_name"] == "Bash"
        assert line["data"]["tool_input"]["command"] == "ls"


class TestHookHandlerAllEventTypes:
    @pytest.mark.parametrize("event_type", [
        "post-tool", "post-tool-failure", "pre-tool",
        "subagent-start", "subagent-stop",
        "session-start", "session-end",
        "notification", "prompt-submit", "stop",
        "instructions-loaded", "permission-request",
        "teammate-idle", "task-completed",
        "config-change",
        "worktree-create", "worktree-remove",
        "pre-compact",
    ])
    def test_all_event_types_exit_zero(self, event_type, helios_dir):
        result = _run_handler(event_type, {}, helios_dir)
        assert result.returncode == 0

    @pytest.mark.parametrize("event_type", [
        "post-tool", "post-tool-failure",
        "subagent-start", "subagent-stop",
        "session-start", "session-end",
        "notification", "prompt-submit", "stop",
    ])
    def test_all_observation_events_write_records(self, event_type, helios_dir):
        _run_handler(event_type, {"session_id": "s1"}, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        assert obs_file.exists()
        line = json.loads(obs_file.read_text().strip())
        assert line["event_type"] == event_type


class TestHookHandlerEdgeCases:
    def test_empty_stdin(self, helios_dir):
        env = os.environ.copy()
        env["HELIOS_DIR"] = str(helios_dir)
        result = subprocess.run(
            [sys.executable, str(HANDLER), "post-tool"],
            input="",
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0

    def test_malformed_json(self, helios_dir):
        env = os.environ.copy()
        env["HELIOS_DIR"] = str(helios_dir)
        result = subprocess.run(
            [sys.executable, str(HANDLER), "post-tool"],
            input="not json at all",
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0

    def test_no_args_exits_zero(self, helios_dir):
        env = os.environ.copy()
        env["HELIOS_DIR"] = str(helios_dir)
        result = subprocess.run(
            [sys.executable, str(HANDLER)],
            input="{}",
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0

    def test_multiple_events_append(self, helios_dir):
        for i in range(5):
            _run_handler("post-tool", {"tool_name": f"Tool{i}"}, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        lines = obs_file.read_text().strip().splitlines()
        assert len(lines) == 5
        for i, line_str in enumerate(lines):
            record = json.loads(line_str)
            assert record["data"]["tool_name"] == f"Tool{i}"

    def test_missing_common_fields_default_to_empty(self, helios_dir):
        _run_handler("stop", {}, helios_dir)
        obs_file = helios_dir / "observations" / "hooks" / "default.jsonl"
        line = json.loads(obs_file.read_text().strip())
        assert line["session_id"] == ""
        assert line["transcript_path"] == ""
        assert line["cwd"] == ""


class TestHookHandlerPerformance:
    def test_latency_under_100ms(self, helios_dir):
        """Each hook invocation must complete in under 100ms."""
        times = []
        for _ in range(5):
            start = time.time()
            _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)
        avg = sum(times) / len(times)
        assert avg < 100, f"Average latency {avg:.0f}ms exceeds 100ms target"

    def test_latency_under_200ms_worst_case(self, helios_dir):
        """Even worst-case should be under 200ms."""
        times = []
        for _ in range(10):
            start = time.time()
            _run_handler("post-tool", {"tool_name": "Read", "session_id": "s1"}, helios_dir)
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)
        worst = max(times)
        assert worst < 200, f"Worst-case latency {worst:.0f}ms exceeds 200ms"
