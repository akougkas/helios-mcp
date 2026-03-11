"""Tests for replaying raw JSONL hook events through the observer.

Validates the bridge between the fast-path hook handler (writes JSONL)
and the behavioral observer (processes events into distributions).
"""

import json
import time
from pathlib import Path

import pytest

from helios_mcp.observer import BehavioralObserver
from helios_mcp.taxonomy import list_dimensions


def _write_raw_events(helios_dir: Path, persona: str, events: list[dict]) -> None:
    """Write raw hook events as JSONL (same format as hook-handler.py)."""
    obs_dir = helios_dir / "observations" / "hooks"
    obs_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = obs_dir / f"{persona}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")


class TestReplayRawHooks:
    def test_replay_returns_distributions(self, tmp_path):
        helios_dir = tmp_path / "helios"
        events = [
            {
                "event_type": "post-tool",
                "timestamp": time.time(),
                "session_id": "s1",
                "transcript_path": "",
                "cwd": "/tmp",
                "data": {"tool_name": "Read", "tool_input": {"file_path": "/test.py"}},
            },
            {
                "event_type": "post-tool",
                "timestamp": time.time(),
                "session_id": "s1",
                "transcript_path": "",
                "cwd": "/tmp",
                "data": {"tool_name": "Edit", "tool_input": {"file_path": "/test.py"}},
            },
        ]
        _write_raw_events(helios_dir, "default", events)

        observer = BehavioralObserver(helios_dir=helios_dir)
        dists = observer.replay_raw_hooks("default")
        assert dists is not None
        assert set(dists.keys()) == set(list_dimensions())

    def test_replay_increments_observation_count(self, tmp_path):
        helios_dir = tmp_path / "helios"
        events = [
            {
                "event_type": "post-tool",
                "timestamp": time.time(),
                "session_id": "s1",
                "transcript_path": "",
                "cwd": "/tmp",
                "data": {"tool_name": "Read"},
            },
        ]
        _write_raw_events(helios_dir, "dev", events)

        observer = BehavioralObserver(helios_dir=helios_dir)
        assert observer.get_observation_count("dev") == 0
        observer.replay_raw_hooks("dev")
        assert observer.get_observation_count("dev") == 1

    def test_replay_no_file_returns_none(self, tmp_path):
        helios_dir = tmp_path / "helios"
        observer = BehavioralObserver(helios_dir=helios_dir)
        result = observer.replay_raw_hooks("nonexistent")
        assert result is None

    def test_replay_empty_file_returns_none(self, tmp_path):
        helios_dir = tmp_path / "helios"
        obs_dir = helios_dir / "observations" / "hooks"
        obs_dir.mkdir(parents=True, exist_ok=True)
        (obs_dir / "empty.jsonl").write_text("")
        observer = BehavioralObserver(helios_dir=helios_dir)
        result = observer.replay_raw_hooks("empty")
        assert result is None

    def test_replay_skips_malformed_lines(self, tmp_path):
        helios_dir = tmp_path / "helios"
        obs_dir = helios_dir / "observations" / "hooks"
        obs_dir.mkdir(parents=True, exist_ok=True)
        content = (
            'not json\n'
            '{"event_type": "post-tool", "timestamp": 1.0, "session_id": "", '
            '"transcript_path": "", "cwd": "", '
            '"data": {"tool_name": "Read"}}\n'
            '{"bad": true}\n'
        )
        (obs_dir / "mixed.jsonl").write_text(content)
        observer = BehavioralObserver(helios_dir=helios_dir)
        dists = observer.replay_raw_hooks("mixed")
        assert dists is not None
        assert observer.get_observation_count("mixed") == 1

    def test_replay_realistic_session(self, tmp_path):
        helios_dir = tmp_path / "helios"
        ts = time.time()
        events = []
        # Simulate reads, edits, test runs
        for i, tool in enumerate(["Read"] * 5 + ["Grep"] * 2 + ["Edit"] * 2 + ["Bash"]):
            events.append({
                "event_type": "post-tool",
                "timestamp": ts + i,
                "session_id": "s1",
                "transcript_path": "/tmp/t.jsonl",
                "cwd": "/home/user/project",
                "data": {"tool_name": tool, "tool_input": {"file_path": f"f{i}.py"}},
            })
        # Add prompts
        for i in range(3):
            events.append({
                "event_type": "prompt-submit",
                "timestamp": ts + 20 + i,
                "session_id": "s1",
                "transcript_path": "/tmp/t.jsonl",
                "cwd": "/home/user/project",
                "data": {"prompt": f"Short prompt {i}"},
            })
        _write_raw_events(helios_dir, "dev", events)

        observer = BehavioralObserver(helios_dir=helios_dir)
        dists = observer.replay_raw_hooks("dev")
        assert dists is not None
        # Read-heavy pattern should show checks_before_acting
        assert dists["risk_caution"]["checks_before_acting"] > 0.1

    def test_replay_no_helios_dir_returns_none(self):
        observer = BehavioralObserver(helios_dir=None)
        result = observer.replay_raw_hooks("any")
        assert result is None

    def test_get_accumulated_after_replay(self, tmp_path):
        helios_dir = tmp_path / "helios"
        events = [
            {
                "event_type": "post-tool",
                "timestamp": time.time(),
                "session_id": "s1",
                "transcript_path": "",
                "cwd": "/tmp",
                "data": {"tool_name": "Read"},
            },
        ]
        _write_raw_events(helios_dir, "dev", events)

        observer = BehavioralObserver(helios_dir=helios_dir)
        observer.replay_raw_hooks("dev")
        accumulated = observer.get_accumulated_distributions("dev")
        assert accumulated is not None
        assert set(accumulated.keys()) == set(list_dimensions())
