#!/usr/bin/env python3
"""Fast-path hook handler for Helios plugin.

Called by Claude Code via hooks.json on every hook event. Reads JSON from
stdin, derives a small set of privacy-safe features, and appends one JSONL
record per event. Runs under the bare `python3` on PATH, not necessarily
inside the project's managed venv, so this file stays stdlib-only and
imports persona resolution from the sibling _persona.py module rather
than from helios_mcp.security. tests/test_hook_handler.py asserts
_persona.py agrees with the package's own validator.

Exit code 0 always (observe-only, never block, never raise past main()).

Privacy contract: never write prompt text, tool_input values, or
tool_response content to disk. Only derived, bounded features cross
into HELIOS_DIR: lengths, counts, and small closed-vocabulary categories.
"""

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _persona import resolve_persona  # noqa: E402

_INGEST_TRIGGER_EVENTS = ("stop", "session-end")
# Stop runs heuristic-only ingest and blocks this script for up to this
# long (Claude Code has no timeout cap on Stop hooks; default is 600s).
# session-end doesn't use this; see _trigger_ingest.
_INGEST_TIMEOUT_SECONDS = 300

_MAX_OBS_BYTES = 5_000_000
_MAX_LOG_BYTES = 2_000_000
_BACKUP_COUNT = 3

_TEST_MARKERS = (
    "pytest", "py.test", "npm test", "npm run test", "yarn test",
    "pnpm test", "go test", "cargo test", "make test", "jest",
    "mocha", "rspec", "phpunit", "python -m pytest", "python3 -m pytest",
    "tox", "ctest",
)
_GIT_MARKERS = ("git ", "gh ")
_BUILD_MARKERS = (
    "npm run build", "yarn build", "cargo build", "go build", "make",
    "tsc", "webpack", "vite build",
)
_INSTALL_MARKERS = (
    "pip install", "pip3 install", "npm install", "npm ci", "yarn add",
    "uv add", "uv sync", "uv pip install", "apt install", "apt-get install",
    "brew install", "cargo add",
)


def _classify_command(command: str) -> str:
    lowered = command.lower()
    if any(marker in lowered for marker in _TEST_MARKERS):
        return "test"
    if any(lowered.startswith(marker) for marker in _GIT_MARKERS):
        return "git"
    if any(marker in lowered for marker in _INSTALL_MARKERS):
        return "install"
    if any(marker in lowered for marker in _BUILD_MARKERS):
        return "build"
    return "other"


def _tool_derived_fields(raw_json: dict[str, Any]) -> dict[str, Any]:
    """Derive tool-call features without retaining tool_input/tool_response."""
    tool_name = raw_json.get("tool_name", "")
    tool_name = tool_name if isinstance(tool_name, str) else ""

    tool_input = raw_json.get("tool_input", {})
    command_kind = "n/a"
    if tool_name == "Bash" and isinstance(tool_input, dict):
        command = tool_input.get("command", "")
        if isinstance(command, str) and command:
            command_kind = _classify_command(command)

    return {
        "tool_name": tool_name,
        "command_kind": command_kind,
        "is_test_command": command_kind == "test",
    }


def _looks_denied(raw_json: dict[str, Any]) -> bool:
    """Best-effort permission-denial signal from explicit decision fields.

    A denial is the user or the permission system refusing to let a tool
    run. It is distinct from the tool running and failing, which is
    is_error below; conflating the two would feed a failed pytest run
    into the same signal as a rejected proposal. Only inspects
    permission-decision-shaped fields; never retains the value itself,
    only the derived boolean. Transcript parsing (observe's ingest
    pipeline) is the authoritative source for denials. This is only a
    lightweight corroborating signal.
    """
    for key in ("permission_decision", "decision"):
        value = raw_json.get(key)
        if isinstance(value, str) and value.lower() in ("deny", "block", "denied"):
            return True
    return False


def _looks_error(raw_json: dict[str, Any]) -> bool:
    """Best-effort tool-failure signal from the tool_response shape.

    Only inspects a small set of plausible keys for a truthy error-like
    value; never retains the value itself, only the derived boolean.
    """
    tool_response = raw_json.get("tool_response")
    if isinstance(tool_response, dict):
        for key in ("is_error", "isError", "error"):
            if tool_response.get(key):
                return True
    return False


def _event_derived_fields(event_type: str, raw_json: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    if event_type in ("post-tool", "post-tool-failure", "pre-tool"):
        fields.update(_tool_derived_fields(raw_json))
        fields["success"] = event_type != "post-tool-failure"
        fields["is_error"] = (not fields["success"]) or _looks_error(raw_json)
        fields["is_denied"] = _looks_denied(raw_json)

    elif event_type == "prompt-submit":
        prompt = raw_json.get("prompt", "")
        prompt = prompt if isinstance(prompt, str) else ""
        fields["prompt_len"] = len(prompt)
        fields["question_count"] = prompt.count("?")

    elif event_type in ("stop", "subagent-stop"):
        fields["stop_hook_active"] = bool(raw_json.get("stop_hook_active", False))

    elif event_type == "permission-request":
        fields["is_denied"] = _looks_denied(raw_json)

    elif event_type == "notification":
        content = raw_json.get("message", "")
        content = content if isinstance(content, str) else ""
        fields["length"] = len(content)
        notification_type = raw_json.get("notification_type", "")
        fields["notification_type"] = (
            notification_type if isinstance(notification_type, str) else ""
        )

    return fields


def _rotate_if_needed(path: Path, max_bytes: int = _MAX_OBS_BYTES) -> None:
    """Size-based rotation: path -> .1 -> .2 -> .3, oldest dropped."""
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        for i in range(_BACKUP_COUNT - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            dst = path.with_name(f"{path.name}.{i + 1}")
            if src.exists():
                src.replace(dst)
        path.replace(path.with_name(f"{path.name}.1"))
    except OSError:
        pass  # never block the hook on rotation failure


def _ingest_command(
    persona: str, session_id: str, transcript_path: str, helios_dir: Path
) -> list[str]:
    source = os.environ.get("HELIOS_SOURCE", "helios-mcp")
    return [
        "uvx", "--from", source, "helios-mcp", "ingest",
        "--persona", persona,
        "--session-id", session_id,
        "--transcript", transcript_path,
        "--helios-dir", str(helios_dir),
    ]


def _trigger_ingest(
    event_type: str,
    persona: str,
    session_id: str,
    transcript_path: str,
    helios_dir: Path,
) -> None:
    """Fire-and-forget `helios-mcp ingest` for a finished turn/session.

    Runs via `uvx --from ${HELIOS_SOURCE:-helios-mcp}` so a local checkout
    works during development and a published PyPI release works later
    (see .mcp.json). Only fires when there is an actual transcript file to
    ingest. That also keeps hook-handler.py's own tests fast, since none
    of them point transcript_path at a real file.

    Stop runs heuristic-only ingest and is fast, so it blocks this script
    (which Claude Code already treats as async at the hook level) with a
    bounded wait. session-end passes --final, which additionally runs the
    Haiku batch labeler over the whole session, observed at 25-55s
    against ingest's own 180s internal timeout, well past what a
    SessionEnd hook is allowed to block for (Claude Code caps SessionEnd
    hooks at 60s regardless of configuration). So --final is launched
    fully detached (its own session, stdio to a bounded log file under
    HELIOS_DIR/logs/) and this script returns immediately without
    waiting on it; the labeler finishes on its own time.
    """
    if not session_id or not transcript_path:
        return
    try:
        if not Path(transcript_path).is_file():
            return
    except OSError:
        return

    cmd = _ingest_command(persona, session_id, transcript_path, helios_dir)

    if event_type == "session-end":
        cmd.append("--final")
        log_path = helios_dir / "logs" / "ingest.log"
        with contextlib.suppress(OSError):
            log_path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(log_path, max_bytes=_MAX_LOG_BYTES)
            with log_path.open("a", encoding="utf-8") as log_file:
                subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        return

    # observe-only: ingest failing must never surface to the user
    with contextlib.suppress(
        OSError, subprocess.TimeoutExpired, subprocess.SubprocessError
    ):
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=_INGEST_TIMEOUT_SECONDS,
            check=False,
        )


def main() -> None:
    if os.environ.get("HELIOS_DISABLE") == "1":
        sys.exit(0)

    event_type = sys.argv[1] if len(sys.argv) > 1 else ""
    if not event_type:
        sys.exit(0)

    try:
        raw_input = sys.stdin.read()
        raw_json = json.loads(raw_input) if raw_input.strip() else {}
        if not isinstance(raw_json, dict):
            raw_json = {}
    except json.JSONDecodeError:
        raw_json = {}

    helios_dir = Path(os.environ.get("HELIOS_DIR", str(Path.home() / ".helios")))
    obs_dir = helios_dir / "observations" / "hooks"

    cwd = raw_json.get("cwd", "")
    cwd = cwd if isinstance(cwd, str) else ""
    session_id = raw_json.get("session_id", "")
    session_id = session_id if isinstance(session_id, str) else ""
    transcript_path = raw_json.get("transcript_path", "")
    transcript_path = transcript_path if isinstance(transcript_path, str) else ""
    permission_mode = raw_json.get("permission_mode", "")
    permission_mode = permission_mode if isinstance(permission_mode, str) else ""

    persona = resolve_persona(cwd, helios_dir)

    record: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": time.time(),
        "session_id": session_id,
        "transcript_path": transcript_path,
        "cwd": cwd,
        "persona": persona,
        "permission_mode": permission_mode,
        **_event_derived_fields(event_type, raw_json),
    }

    try:
        obs_dir.mkdir(parents=True, exist_ok=True)
        obs_file = obs_dir / f"{persona}.jsonl"
        _rotate_if_needed(obs_file)
        with obs_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # observe-only: a write failure must never surface to the user

    if event_type in _INGEST_TRIGGER_EVENTS:
        _trigger_ingest(event_type, persona, session_id, transcript_path, helios_dir)


if __name__ == "__main__":
    main()
