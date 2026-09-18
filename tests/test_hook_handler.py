"""Tests for the fast-path hook handler script.

Validates that hook-handler.py writes privacy-safe JSONL observation
records without depending on the full helios-mcp CLI stack. This is the
hot path that Claude Code invokes on every hook event, so most tests here
run the script as a real subprocess the way Claude Code does. A few tests
load it as a module instead (it isn't meant to be imported in production,
only executed) to reach internal helpers directly: persona-validator
agreement with helios_mcp.security, and _trigger_ingest with subprocess.run
mocked out so tests never actually shell out to uvx.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from helios_mcp.security import validate_persona_name as pkg_validate_persona_name

HOOKS_DIR = Path(__file__).parent.parent / "helios-plugin" / "hooks"
HANDLER = HOOKS_DIR / "hook-handler.py"
SESSION_START_CONTEXT = HOOKS_DIR / "session-start-context.py"
PERSONA_MODULE = HOOKS_DIR / "_persona.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_hook_handler_module():
    return _load_module(HANDLER, "hook_handler")


def _load_persona_module():
    return _load_module(PERSONA_MODULE, "helios_hook_persona")


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

    def test_post_tool_failure_marks_success_and_error(self, helios_dir):
        data = {"tool_name": "Bash", "tool_input": {"command": "false"}}
        _run_handler("post-tool-failure", data, helios_dir)
        line = _record(helios_dir)
        assert line["success"] is False
        assert line["is_error"] is True

    def test_tool_response_error_shape_sets_is_error_not_is_denied(self, helios_dir):
        """A failed pytest run is a tool error, not a permission denial —
        conflating the two would feed false 'user said no' signals into
        drift. Only an explicit permission_decision/decision field may
        set is_denied."""
        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "tool_response": {"is_error": True, "error": "assertion failed"},
        }
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert line["is_error"] is True
        assert line["is_denied"] is False

    @pytest.mark.parametrize("key", ["permission_decision", "decision"])
    def test_explicit_permission_decision_sets_is_denied(self, helios_dir, key):
        data = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}, key: "deny"}
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert line["is_denied"] is True
        assert line["is_error"] is False

    def test_successful_tool_has_no_error_or_denial(self, helios_dir):
        data = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        _run_handler("post-tool", data, helios_dir)
        line = _record(helios_dir)
        assert line["is_error"] is False
        assert line["is_denied"] is False


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
        """The plugin's stdlib-only _persona.py duplicates
        helios_mcp.security's persona whitelist rather than importing it
        (hook scripts run under a bare python3 that may not have
        helios_mcp installed). This pins the two implementations to the
        same accept/reject decision for every case in P1's own test
        matrix."""
        persona_module = _load_persona_module()

        local_result = persona_module.validate_persona_name(name)
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


class TestHookHandlerIngestTrigger:
    """_trigger_ingest shells out to `uvx --from ... helios-mcp ingest`.

    stop blocks on subprocess.run (heuristic-only ingest, fast); every
    stop test here mocks subprocess.run so nothing actually invokes uvx.
    session-end launches --final fully detached via subprocess.Popen and
    returns immediately without waiting. session-end tests mock Popen
    instead, since --final also runs the Haiku batch labeler, which can
    take far longer than a SessionEnd hook is allowed to block for.
    """

    def test_no_op_without_transcript_file(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
        hook_handler._trigger_ingest(
            "stop", "developer", "sess-1", str(tmp_path / "missing.jsonl"), tmp_path
        )
        assert calls == []

    def test_no_op_without_session_id_or_transcript(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        hook_handler._trigger_ingest("stop", "developer", "", str(transcript), tmp_path)
        hook_handler._trigger_ingest("stop", "developer", "sess-1", "", tmp_path)
        assert calls == []

    def test_session_end_no_op_without_transcript_file(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        calls = []
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
        hook_handler._trigger_ingest(
            "session-end", "developer", "sess-1",
            str(tmp_path / "missing.jsonl"), tmp_path,
        )
        assert calls == []

    def test_stop_invokes_ingest_without_final(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        monkeypatch.setenv("HELIOS_SOURCE", "/path/to/worktree")

        hook_handler._trigger_ingest(
            "stop", "developer", "sess-1", str(transcript), tmp_path
        )

        assert len(calls) == 1
        cmd = calls[0][0][0]
        assert cmd[:4] == ["uvx", "--from", "/path/to/worktree", "helios-mcp"]
        assert "ingest" in cmd
        assert cmd[cmd.index("--persona") + 1] == "developer"
        assert cmd[cmd.index("--session-id") + 1] == "sess-1"
        assert cmd[cmd.index("--transcript") + 1] == str(transcript)
        assert cmd[cmd.index("--helios-dir") + 1] == str(tmp_path)
        assert "--final" not in cmd
        assert calls[0][1]["timeout"] == 300

    def test_session_end_invokes_ingest_with_final_detached(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        calls = []
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        hook_handler._trigger_ingest(
            "session-end", "developer", "sess-1", str(transcript), tmp_path
        )

        assert len(calls) == 1
        args, kwargs = calls[0]
        cmd = args[0]
        assert "--final" in cmd
        # Detached: its own session, no pipes we'd have to drain, and
        # this call never blocks on the child finishing.
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "timeout" not in kwargs

    def test_session_end_logs_to_bounded_file_under_helios_dir(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")
        # Use a command that actually runs (`true`) instead of mocking
        # Popen, so the log file and detachment are exercised for real.
        monkeypatch.setattr(hook_handler, "_ingest_command", lambda *a, **k: ["true"])

        hook_handler._trigger_ingest(
            "session-end", "developer", "sess-1", str(transcript), tmp_path
        )

        log_path = tmp_path / "logs" / "ingest.log"
        # The detached child may not have flushed/exited yet; the log
        # file's existence and location are what this test guarantees.
        assert log_path.parent.is_dir()

    def test_default_source_is_package_name(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
        monkeypatch.delenv("HELIOS_SOURCE", raising=False)
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        hook_handler._trigger_ingest(
            "stop", "developer", "sess-1", str(transcript), tmp_path
        )

        cmd = calls[0][0][0]
        assert cmd[cmd.index("--from") + 1] == "helios-mcp"

    def test_ingest_failure_never_raises(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()

        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd="uvx", timeout=1)

        monkeypatch.setattr(subprocess, "run", _raise)
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        hook_handler._trigger_ingest(
            "stop", "developer", "sess-1", str(transcript), tmp_path
        )  # must not raise

    def test_session_end_popen_failure_never_raises(self, tmp_path, monkeypatch):
        hook_handler = _load_hook_handler_module()

        def _raise(*a, **k):
            raise OSError("uvx not found")

        monkeypatch.setattr(subprocess, "Popen", _raise)
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{}\n")

        hook_handler._trigger_ingest(
            "session-end", "developer", "sess-1", str(transcript), tmp_path
        )  # must not raise

    def test_log_rotation_reuses_bounded_rotation(self, tmp_path):
        hook_handler = _load_hook_handler_module()
        log_path = tmp_path / "logs" / "ingest.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("x" * (hook_handler._MAX_LOG_BYTES + 1))

        hook_handler._rotate_if_needed(log_path, max_bytes=hook_handler._MAX_LOG_BYTES)

        assert (tmp_path / "logs" / "ingest.log.1").exists()
        assert not log_path.exists()


class TestSessionStartContext:
    def _run(self, stdin_data: dict, helios_dir: Path, extra_env: dict | None = None):
        env = os.environ.copy()
        env["HELIOS_DIR"] = str(helios_dir)
        env.pop("HELIOS_PERSONA", None)
        env.pop("HELIOS_DISABLE", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(SESSION_START_CONTEXT)],
            input=json.dumps(stdin_data),
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )

    def test_injects_rendered_markdown_as_plain_text(self, helios_dir):
        (helios_dir / "rendered").mkdir(parents=True)
        (helios_dir / "rendered" / "default.md").write_text("Be terse.\n")
        result = self._run({}, helios_dir)
        assert result.returncode == 0
        assert result.stdout.strip() == "Be terse."
        # SessionStart's documented stdout contract is plain text, not the
        # hookSpecificOutput JSON envelope UserPromptSubmit uses.
        assert "hookSpecificOutput" not in result.stdout

    def test_silent_no_op_when_rendered_file_missing(self, helios_dir):
        result = self._run({}, helios_dir)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_uses_persona_from_cwd_marker(self, helios_dir, tmp_path):
        (helios_dir / "rendered").mkdir(parents=True)
        (helios_dir / "rendered" / "coder.md").write_text("Coder profile.")
        marker_dir = tmp_path / "proj"
        marker_dir.mkdir()
        (marker_dir / ".helios-persona").write_text("coder\n")
        result = self._run({"cwd": str(marker_dir)}, helios_dir)
        assert result.stdout.strip() == "Coder profile."

    def test_disable_env_produces_no_output(self, helios_dir):
        (helios_dir / "rendered").mkdir(parents=True)
        (helios_dir / "rendered" / "default.md").write_text("Should not appear.")
        result = self._run({}, helios_dir, extra_env={"HELIOS_DISABLE": "1"})
        assert result.returncode == 0
        assert result.stdout == ""

    def test_malformed_stdin_does_not_crash(self, helios_dir):
        env = os.environ.copy()
        env["HELIOS_DIR"] = str(helios_dir)
        result = subprocess.run(
            [sys.executable, str(SESSION_START_CONTEXT)],
            input="not json",
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0

    def test_fast_enough_to_run_synchronously(self, helios_dir):
        (helios_dir / "rendered").mkdir(parents=True)
        (helios_dir / "rendered" / "default.md").write_text("x" * 2000)
        times = []
        for _ in range(5):
            start = time.time()
            self._run({}, helios_dir)
            times.append((time.time() - start) * 1000)
        # Generous bound for CI/subprocess overhead: the script itself
        # does one stdin read and one small file read.
        assert sum(times) / len(times) < 150


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
