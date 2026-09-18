"""Shared, stdlib-only persona resolution for Helios plugin hook scripts.

hook-handler.py and session-start-context.py both need this and both run
under the bare `python3` on PATH, not necessarily inside the project's
managed venv, so this stays a plain sibling module (imported via a
sys.path insert of its own directory) rather than a helios_mcp import.

Mirrors helios_mcp.security.validate_persona_name's whitelist exactly.
tests/test_hook_handler.py asserts the two agree.
"""

import os
import re
from pathlib import Path

SAFE_PERSONA_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")

DEFAULT_PERSONA_FILENAME = "default_persona"
PERSONA_MARKER_FILENAME = ".helios-persona"
MAX_PERSONA_WALK_DEPTH = 64  # bound the upward directory walk


def validate_persona_name(name: str) -> str | None:
    """Return name if it passes the persona-name whitelist, else None.

    Never raises — callers are hot-path hooks that must never block.
    """
    if not isinstance(name, str):
        return None
    if name != name.strip():
        return None
    if not SAFE_PERSONA_NAME_PATTERN.match(name):
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


def resolve_persona(cwd: str, helios_dir: Path) -> str:
    """HELIOS_PERSONA env > .helios-persona walking up from cwd > \
HELIOS_DIR/default_persona > "default"."""
    env_persona = validate_persona_name(os.environ.get("HELIOS_PERSONA", ""))
    if env_persona:
        return env_persona

    if cwd:
        try:
            current: Path | None = Path(cwd).resolve()
        except OSError:
            current = None
        if current is not None:
            for _ in range(MAX_PERSONA_WALK_DEPTH):
                candidate = _read_first_line(current / PERSONA_MARKER_FILENAME)
                if candidate:
                    validated = validate_persona_name(candidate)
                    if validated:
                        return validated
                if current.parent == current:
                    break
                current = current.parent

    default_file_persona = _read_first_line(helios_dir / DEFAULT_PERSONA_FILENAME)
    if default_file_persona:
        validated = validate_persona_name(default_file_persona)
        if validated:
            return validated

    return "default"
