"""Tests for the fast-path hook handler script.

Validates that hook-handler.py writes privacy-safe JSONL observation
records without depending on the full helios-mcp CLI stack. This is the
hot path that Claude Code invokes on every hook event, so every test here
runs the script as a real subprocess the way Claude Code does — not by
importing it, since it deliberately avoids being an importable module.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from helios_mcp.security import validate_persona_name as pkg_validate_persona_name

HANDLER = Path(__file__).parent.parent / "helios-plugin" / "hooks" / "hook-handler.py"


@pytest.fixture
def helios_dir(tmp_path):
    d = tmp_path / "helios"
    return d


def _run_handler(
    event_type: str,
    stdin_data: dict,
    helios_dir: Path,
    *,
    cwd: str | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run the hook handler script with the given event type and stdin data."""
    env = os.environ.copy()
    env["HELIOS_DIR"] = str(helios_dir)
    env.pop("HELIOS_PERSONA", None)
    env.pop("HELIOS_DISABLE", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HANDLER), event_type],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=5,
    )


def _record(helios_dir: Path, persona: str = "default") -> dict:
    obs_file = helios_dir / "observations" / "hooks" / f"{persona}.jsonl"
    return json.loads(obs_file.read_text().strip().splitlines()[-1])


class TestHookHandlerBasics:
    def test_handler_script_exists(self):
        assert HANDLER.is_file()

    def test_exits_zero(self, helios_dir):
        result = _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        assert result.returncode == 0

    def test_creates_observation_file(self, helios_dir):
        _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        assert (helios_dir / "observations" / "hooks" / "default.jsonl").exists()

    def test_writes_valid_jsonl(self, helios_dir):
        _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        line = _record(helios_dir)
        assert line["event_type"] == "post-tool"
        assert isinstance(line["timestamp"], float)

    def test_preserves_common_fields(self, helios_dir):
        data = {
            "tool_name": "Edit",
            "session_id": "sess-42",
            "transcript_path": "/tmp/transcript.jsonl",
            "cwd": "/home/user/project",
            "permission_mode": "acceptEdits",
        }
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert line["session_id"] == "sess-42"
        assert line["transcript_path"] == "/tmp/transcript.jsonl"
        assert line["cwd"] == "/home/user/project"
        assert line["permission_mode"] == "acceptEdits"


class TestHookHandlerPrivacy:
    """The core P2 contract: derived features only, never raw content."""

    def test_no_raw_data_envelope(self, helios_dir):
        data = {"tool_name": "Bash", "tool_input": {"command": "ls -la /secret"}}
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert "data" not in line
        assert "tool_input" not in line

    def test_bash_command_text_never_written(self, helios_dir):
        secret_command = "curl https://internal.example.com/leak?token=abc123"
        data = {"tool_name": "Bash", "tool_input": {"command": secret_command}}
        _run_handler("post-tool", data, helios_dir)
        raw_line = (
            helios_dir / "observations" / "hooks" / "default.jsonl"
        ).read_text()
        assert secret_command not in raw_line
        assert "abc123" not in raw_line

    def test_prompt_text_never_written(self, helios_dir):
        secret_prompt = "my api key is sk-verysecret, please store it"
        _run_handler("prompt-submit", {"prompt": secret_prompt}, helios_dir)
        raw_line = (
            helios_dir / "observations" / "hooks" / "default.jsonl"
        ).read_text()
        assert secret_prompt not in raw_line
        assert "sk-verysecret" not in raw_line

    def test_prompt_derives_length_and_question_count(self, helios_dir):
        _run_handler(
            "prompt-submit", {"prompt": "why does this fail? and how?"}, helios_dir
        )
        line = _record(helios_dir)
        assert line["prompt_len"] == len("why does this fail? and how?")
        assert line["question_count"] == 2

    def test_edit_tool_input_values_never_written(self, helios_dir):
        data = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/home/user/.ssh/id_rsa",
                "old_string": "PRIVATE KEY CONTENT",
                "new_string": "still private",
            },
        }
        _run_handler("post-tool", data, helios_dir)
        raw_line = (
            helios_dir / "observations" / "hooks" / "default.jsonl"
        ).read_text()
        assert "PRIVATE KEY CONTENT" not in raw_line
        assert "id_rsa" not in raw_line

    def test_tool_response_content_never_written(self, helios_dir):
        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "tool_response": {"output": "super secret stdout content"},
        }
        _run_handler("post-tool", data, helios_dir)
        raw_line = (
            helios_dir / "observations" / "hooks" / "default.jsonl"
        ).read_text()
        assert "super secret stdout content" not in raw_line

    @pytest.mark.parametrize(
        ("command", "expected_kind", "expected_is_test"),
        [
            ("pytest tests/ -q", "test", True),
            ("npm test", "test", True),
            ("git commit -m 'x'", "git", False),
            ("pip install requests", "install", False),
            ("cargo build --release", "build", False),
            ("echo hello", "other", False),
        ],
    )
    def test_bash_command_classification(
        self, helios_dir, command, expected_kind, expected_is_test
    ):
        data = {"tool_name": "Bash", "tool_input": {"command": command}}
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert line["command_kind"] == expected_kind
        assert line["is_test_command"] is expected_is_test

    def test_non_bash_tool_has_no_command_kind_leak(self, helios_dir):
        data = {"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}}
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert line["command_kind"] == "n/a"
        assert line["is_test_command"] is False

    def test_post_tool_failure_marks_success_false(self, helios_dir):
        data = {"tool_name": "Bash", "tool_input": {"command": "false"}}
        _run_handler("post-tool-failure", data, helios_dir)
        line = _record(helios_dir)
        assert line["success"] is False


class TestHookHandlerPersonaResolution:
    def test_env_var_takes_priority(self, helios_dir, tmp_path):
        marker_dir = tmp_path / "proj"
        marker_dir.mkdir()
        (marker_dir / ".helios-persona").write_text("from-file\n")
        _run_handler(
            "post-tool",
            {"tool_name": "Read", "cwd": str(marker_dir)},
            helios_dir,
            extra_env={"HELIOS_PERSONA": "from-env"},
        )
        assert (helios_dir / "observations" / "hooks" / "from-env.jsonl").exists()

    def test_marker_file_in_cwd(self, helios_dir, tmp_path):
        marker_dir = tmp_path / "proj"
        marker_dir.mkdir()
        (marker_dir / ".helios-persona").write_text("coder\n")
        _run_handler(
            "post-tool",
            {"tool_name": "Read", "cwd": str(marker_dir)},
            helios_dir,
        )
        assert (helios_dir / "observations" / "hooks" / "coder.jsonl").exists()

    def test_marker_file_found_walking_up_from_cwd(self, helios_dir, tmp_path):
        root = tmp_path / "proj"
        nested = root / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (root / ".helios-persona").write_text("researcher\n")
        _run_handler(
            "post-tool",
            {"tool_name": "Read", "cwd": str(nested)},
            helios_dir,
        )
        assert (helios_dir / "observations" / "hooks" / "researcher.jsonl").exists()

    def test_helios_dir_default_persona_used_when_no_marker(self, helios_dir, tmp_path):
        helios_dir.mkdir(parents=True)
        (helios_dir / "default_persona").write_text("writer\n")
        cwd_no_marker = tmp_path / "elsewhere"
        cwd_no_marker.mkdir()
        _run_handler(
            "post-tool",
            {"tool_name": "Read", "cwd": str(cwd_no_marker)},
            helios_dir,
        )
        assert (helios_dir / "observations" / "hooks" / "writer.jsonl").exists()

    def test_falls_back_to_default(self, helios_dir):
        _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)
        assert (helios_dir / "observations" / "hooks" / "default.jsonl").exists()

    def test_malicious_marker_file_is_rejected(self, helios_dir, tmp_path):
        marker_dir = tmp_path / "proj"
        marker_dir.mkdir()
        (marker_dir / ".helios-persona").write_text("../../../etc/evil\n")
        _run_handler(
            "post-tool",
            {"tool_name": "Read", "cwd": str(marker_dir)},
            helios_dir,
        )
        # Falls through to "default" rather than writing outside helios_dir.
        assert (helios_dir / "observations" / "hooks" / "default.jsonl").exists()
        escaped = list(tmp_path.rglob("evil*"))
        assert escaped == []

    def test_malicious_env_persona_is_rejected(self, helios_dir):
        _run_handler(
            "post-tool",
            {"tool_name": "Read"},
            helios_dir,
            extra_env={"HELIOS_PERSONA": "../../etc/passwd"},
        )
        assert (helios_dir / "observations" / "hooks" / "default.jsonl").exists()

    @pytest.mark.parametrize(
        "name",
        [
            "developer", "dev_user", "coder-1", "a" * 50,
            "../../x", "..", ".", "a/b", "", "   ", " developer",
            "developer ", "a" * 51, "dev.user", "~root",
        ],
    )
    def test_local_validator_agrees_with_package_validator(self, name):
        """hook-handler.py duplicates helios_mcp.security's persona
        whitelist rather than importing it (stdlib-only hot path). This
        pins the two implementations to the same accept/reject decision
        for every case in P1's own test matrix."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("hook_handler", HANDLER)
        hook_handler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_handler)

        local_result = hook_handler._validate_persona_name(name)
        try:
            package_result = pkg_validate_persona_name(name)
        except Exception:
            package_result = None

        assert local_result == package_result


class TestHookHandlerDisable:
    def test_helios_disable_skips_all_writes(self, helios_dir):
        result = _run_handler(
            "post-tool",
            {"tool_name": "Read"},
            helios_dir,
            extra_env={"HELIOS_DISABLE": "1"},
        )
        assert result.returncode == 0
        assert not (helios_dir / "observations").exists()


class TestHookHandlerRotation:
    def test_rotates_when_over_size_threshold(self, helios_dir):
        obs_dir = helios_dir / "observations" / "hooks"
        obs_dir.mkdir(parents=True)
        obs_file = obs_dir / "default.jsonl"
        obs_file.write_text("x" * (5_000_000 + 1))

        _run_handler("post-tool", {"tool_name": "Read"}, helios_dir)

        assert (obs_dir / "default.jsonl.1").exists()
        assert obs_file.exists()
        new_content = obs_file.read_text().strip()
        assert new_content.count("\n") == 0  # only the new record


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
        line = _record(helios_dir)
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
            assert record["tool_name"] == f"Tool{i}"

    def test_missing_common_fields_default_to_empty(self, helios_dir):
        _run_handler("stop", {}, helios_dir)
        line = _record(helios_dir)
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
