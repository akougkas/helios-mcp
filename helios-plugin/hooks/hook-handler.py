#!/usr/bin/env python3
"""Fast-path hook handler for Helios plugin.

Called by Claude Code via hooks.json on every hook event. Reads JSON from
stdin, derives a small set of privacy-safe features, and appends one JSONL
record per event. Runs under the bare `python3` on PATH, not necessarily
inside the project's managed venv, so this file stays stdlib-only and
duplicates the persona-validation rules in helios_mcp.security rather than
importing that package. tests/test_hook_handler.py asserts the two agree.

Exit code 0 always (observe-only, never block, never raise past main()).

Privacy contract: never write prompt text, tool_input values, or
tool_response content to disk. Only derived, bounded features — lengths,
counts, and small closed-vocabulary categories — cross into HELIOS_DIR.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Mirrors helios_mcp.security.SAFE_PERSONA_NAME_PATTERN exactly. Kept in
# sync by tests/test_hook_handler.py, which imports both and fuzzes them
# against the same input set.
_SAFE_PERSONA_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")

_DEFAULT_PERSONA_FILENAME = "default_persona"
_PERSONA_MARKER_FILENAME = ".helios-persona"
_MAX_PERSONA_WALK_DEPTH = 64  # bound the upward directory walk

_MAX_OBS_BYTES = 5_000_000
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


def _validate_persona_name(name: str) -> str | None:
    """Return name if it passes the persona-name whitelist, else None.

    Never raises — this is the hot path and must never block a hook.
    """
    if not isinstance(name, str):
        return None
    if name != name.strip():
        return None
    if not _SAFE_PERSONA_NAME_PATTERN.match(name):
        return None
    return name


def _read_first_line(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    first_line = text.splitlines()[0] if text.splitlines() else ""
    return first_line.strip()


def _resolve_persona(cwd: str, helios_dir: Path) -> str:
    """HELIOS_PERSONA env > .helios-persona walking up from cwd > \
HELIOS_DIR/default_persona > "default"."""
    env_persona = _validate_persona_name(os.environ.get("HELIOS_PERSONA", ""))
    if env_persona:
        return env_persona

    if cwd:
        try:
            current = Path(cwd).resolve()
        except OSError:
            current = None
        if current is not None:
            for _ in range(_MAX_PERSONA_WALK_DEPTH):
                candidate = _read_first_line(current / _PERSONA_MARKER_FILENAME)
                if candidate:
                    validated = _validate_persona_name(candidate)
                    if validated:
                        return validated
                if current.parent == current:
                    break
                current = current.parent

    default_file_persona = _read_first_line(helios_dir / _DEFAULT_PERSONA_FILENAME)
    if default_file_persona:
        validated = _validate_persona_name(default_file_persona)
        if validated:
            return validated

    return "default"


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
    """Best-effort permission-denial signal from documented-shape fields.

    Only inspects a small set of plausible keys for a truthy/deny-like
    value; never retains the value itself, only the derived boolean.
    """
    for key in ("permission_decision", "decision"):
        value = raw_json.get(key)
        if isinstance(value, str) and value.lower() in ("deny", "block", "denied"):
            return True

    tool_response = raw_json.get("tool_response")
    if isinstance(tool_response, dict):
        for key in ("is_error", "isError", "error", "denied"):
            if tool_response.get(key):
                return True

    return False


def _event_derived_fields(event_type: str, raw_json: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    if event_type in ("post-tool", "post-tool-failure", "pre-tool"):
        fields.update(_tool_derived_fields(raw_json))
        fields["success"] = event_type != "post-tool-failure"
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


def _rotate_if_needed(obs_file: Path) -> None:
    """Size-based rotation: persona.jsonl -> .1 -> .2 -> .3, oldest dropped."""
    try:
        if not obs_file.exists() or obs_file.stat().st_size < _MAX_OBS_BYTES:
            return
        for i in range(_BACKUP_COUNT - 1, 0, -1):
            src = obs_file.with_name(f"{obs_file.name}.{i}")
            dst = obs_file.with_name(f"{obs_file.name}.{i + 1}")
            if src.exists():
                src.replace(dst)
        obs_file.replace(obs_file.with_name(f"{obs_file.name}.1"))
    except OSError:
        pass  # never block the hook on rotation failure


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

    persona = _resolve_persona(cwd, helios_dir)

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


if __name__ == "__main__":
    main()
