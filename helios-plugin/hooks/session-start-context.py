#!/usr/bin/env python3
"""Sync SessionStart hook for Helios plugin.

Injects HELIOS_DIR/rendered/<persona>.md into the new session's context,
written by the MCP server's renderer whenever a profile changes. Runs
synchronously (hooks.json has no "async" on this entry) because Claude
Code only reads a SessionStart hook's stdout as context if it waits for
the hook to finish.

Per current Claude Code docs, a SessionStart hook's stdout is added to
context as plain text — unlike UserPromptSubmit, which documents a
structured `{"hookSpecificOutput": {...}}` stdout envelope, SessionStart
is only documented to consume raw stdout text. So this prints the
rendered markdown directly rather than wrapping it in that envelope.

Silent no-op (no stdout, exit 0) whenever there's nothing to inject —
fresh install, unrendered persona, or a read failure — so a session
start is never delayed or polluted by a missing file. Must stay fast:
this hook blocks session start, stdlib-only, no subprocess, one file
read.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _persona import resolve_persona  # noqa: E402


def main() -> None:
    if os.environ.get("HELIOS_DISABLE") == "1":
        sys.exit(0)

    try:
        raw_input = sys.stdin.read()
        raw_json = json.loads(raw_input) if raw_input.strip() else {}
        if not isinstance(raw_json, dict):
            raw_json = {}
    except json.JSONDecodeError:
        raw_json = {}

    cwd = raw_json.get("cwd", "")
    cwd = cwd if isinstance(cwd, str) else ""

    helios_dir = Path(os.environ.get("HELIOS_DIR", str(Path.home() / ".helios")))
    persona = resolve_persona(cwd, helios_dir)

    rendered_path = helios_dir / "rendered" / f"{persona}.md"
    try:
        if not rendered_path.is_file():
            sys.exit(0)
        content = rendered_path.read_text(encoding="utf-8").strip()
    except OSError:
        sys.exit(0)

    if not content:
        sys.exit(0)

    print(content)


if __name__ == "__main__":
    main()
