#!/usr/bin/env python3
"""Fast-path hook handler for Helios plugin.

Called by Claude Code via shim scripts. Reads JSON from stdin, appends
a JSONL observation record. Avoids importing the full helios-mcp CLI
stack to keep latency under 100ms.

Exit code 0 always (observe-only, never block).
"""

import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    event_type = sys.argv[1] if len(sys.argv) > 1 else ""
    if not event_type:
        sys.exit(0)

    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            raw_json = {}
        else:
            raw_json = json.loads(raw_input)
            if not isinstance(raw_json, dict):
                raw_json = {}
    except (json.JSONDecodeError, Exception):
        raw_json = {}

    helios_dir = Path(os.environ.get("HELIOS_DIR", Path.home() / ".helios"))
    obs_dir = helios_dir / "observations" / "hooks"
    obs_dir.mkdir(parents=True, exist_ok=True)

    # Resolve persona: env var > .helios-persona file in cwd > "default"
    cwd = raw_json.get("cwd", "")
    persona = os.environ.get("HELIOS_PERSONA", "")
    if not persona and cwd:
        persona_file = Path(cwd) / ".helios-persona"
        if persona_file.is_file():
            persona = persona_file.read_text().strip()
    if not persona:
        persona = "default"

    record = {
        "event_type": event_type,
        "timestamp": time.time(),
        "session_id": raw_json.get("session_id", ""),
        "transcript_path": raw_json.get("transcript_path", ""),
        "cwd": cwd,
        "persona": persona,
        "data": raw_json,
    }

    obs_file = obs_dir / f"{persona}.jsonl"
    with obs_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()
