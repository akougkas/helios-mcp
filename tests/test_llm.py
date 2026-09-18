"""Model labeling: the child process contract, output parsing and validation."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from helios_mcp.llm import (
    ClaudeCLIClient,
    batches,
    default_client,
    label_session,
    llm_enabled,
    parse_cli_output,
)
from helios_mcp.transcript import parse_records

from .transcript_fixtures import TranscriptBuilder

RESULT = {"type": "result", "subtype": "success", "is_error": False,
          "structured_output": {"ok": True}, "result": '{"ok": true}'}


def _fake_cli(tmp_path: Path, body: str) -> str:
    script = tmp_path / "claude"
    script.write_text("#!/usr/bin/env python3\nimport json, os, sys, time\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_child_runs_lean_and_hook_free(tmp_path: Path):
    record = tmp_path / "record.json"
    exe = _fake_cli(tmp_path, f"""
json.dump({{"argv": sys.argv[1:], "stdin": sys.stdin.read(),
           "disable": os.environ.get("HELIOS_DISABLE"), "llm": os.environ.get("HELIOS_LLM"),
           "thinking": os.environ.get("MAX_THINKING_TOKENS")}},
          open({str(record)!r}, "w"))
print(json.dumps([{{"type": "system"}}, {RESULT!r}]))
""")
    out = ClaudeCLIClient(executable=exe).complete_json("sys", "the prompt", {"type": "object"})
    assert out == {"ok": True}
    seen = json.loads(record.read_text())
    assert seen["disable"] == "1"
    assert seen["llm"] == "0"
    assert seen["thinking"] == "0"
    assert seen["stdin"] == "the prompt"
    argv = seen["argv"]
    for flag in ("-p", "--safe-mode", "--no-session-persistence", "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--output-format") + 1] == "json"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == {"type": "object"}


def test_timeout_and_failure_return_none(tmp_path: Path):
    slow = _fake_cli(tmp_path, "time.sleep(5)\n")
    assert ClaudeCLIClient(executable=slow, timeout=0.3).complete_json("s", "p", {}) is None
    failing = _fake_cli(tmp_path, "sys.exit(2)\n")
    assert ClaudeCLIClient(executable=failing).complete_json("s", "p", {}) is None


def test_parse_cli_output_shapes():
    assert parse_cli_output(json.dumps(RESULT)) == {"ok": True}
    no_structured = {**RESULT, "structured_output": None}
    assert parse_cli_output(json.dumps([no_structured])) == {"ok": True}
    assert parse_cli_output(json.dumps([{**RESULT, "is_error": True}])) is None
    assert parse_cli_output("not json") is None


def test_opt_out_switches(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HELIOS_LLM", "1")
    assert llm_enabled(tmp_path)
    (tmp_path / "config.yaml").write_text("llm: false\n")
    assert not llm_enabled(tmp_path)
    assert llm_enabled(None)
    monkeypatch.setenv("HELIOS_DISABLE", "1")
    assert not llm_enabled(None)
    monkeypatch.delenv("HELIOS_DISABLE")
    monkeypatch.setenv("HELIOS_LLM", "0")
    assert default_client() is None


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else None


def _session():
    b = TranscriptBuilder()
    b.prompt("fix it")
    b.say("Fixed the loop bound.")
    b.prompt("too long, be terse")
    b.say("ok")
    return parse_records(b.records).turns


def test_label_session_validates_and_keys_by_turn_id():
    turns = _session()
    reply = {"turns": [
        {"id": "turn 0", "epistemic_style": {"confident": 3, "hedging": 1, "admits_ignorance": 0, "speculating": 0},
         "interaction_agency": None, "communication_register": None, "risk_caution": None,
         "confidence": 1.7, "endorsement": -1,
         "correction_hint": {"communication_register": {"state": "terse", "quote": "Too long"},
                             "risk_caution": {"state": "bogus", "quote": "be terse"}}},
        {"id": "1", "epistemic_style": {"confident": "high"}, "interaction_agency": None,
         "communication_register": None, "risk_caution": None,
         "confidence": 0.4, "endorsement": None, "correction_hint": {}},
        {"id": "7", "epistemic_style": None, "confidence": 1, "endorsement": 1},
    ]}
    client = FakeClient([reply])
    out = label_session(turns, client)
    assert set(out) == {turns[0].turn_id, turns[1].turn_id}
    assert out[turns[1].turn_id].labels == {}
    assert out[turns[1].turn_id].endorsement is None
    first = out[turns[0].turn_id]
    assert first.labels["epistemic_style"]["confident"] == pytest.approx(0.75)
    assert first.confidence == 1.0
    assert first.endorsement == -1.0
    assert first.correction_hint == {"communication_register": "terse"}
    assert "too long, be terse" in client.prompts[0]


def test_hints_and_approvals_must_quote_the_user():
    turns = _session()
    hint = {"interaction_agency": {"state": "asks_first", "quote": "check with me first"},
            "communication_register": {"state": "terse", "quote": "be   TERSE."},
            "risk_caution": {"state": "acts_immediately", "quote": "too long"}}
    reply = {"turns": [
        {"id": "0", "confidence": 1, "endorsement": 1, "approval_quote": "perfect, thanks",
         "correction_hint": hint},
        {"id": "1", "confidence": 1, "endorsement": 1, "approval_quote": None,
         "correction_hint": {}},
    ]}
    b = TranscriptBuilder()
    b.prompt("fix it")
    b.say("Fixed the loop bound.")
    b.prompt("Perfect, thanks. Now the docs")
    b.say("Docs updated.")
    b.prompt("update the changelog")
    b.say("Done.")
    approved = parse_records(b.records).turns
    out = label_session(turns, FakeClient([reply]))
    # Only a quote found in the user's reply that names its dimension's style
    # survives ("too long" is said, but says nothing about risk). "perfect, thanks"
    # was never said after turn 0, so its approval falls back to moving on.
    assert out[turns[0].turn_id].correction_hint == {"communication_register": "terse"}
    assert out[turns[0].turn_id].endorsement == 0.5
    out = label_session(approved, FakeClient([reply]))
    assert out[approved[0].turn_id].endorsement == 1.0
    assert out[approved[1].turn_id].endorsement == 0.5


def test_failed_call_labels_nothing():
    assert label_session(_session(), FakeClient([None])) == {}


def test_large_sessions_are_split_into_batches():
    turns = _session() * 20
    groups = batches(turns, budget=400)
    assert len(groups) > 1
    assert sorted(i for g in groups for i in g) == list(range(len(turns)))


@pytest.mark.skipif(os.environ.get("HELIOS_LIVE_LLM") != "1", reason="live model call")
def test_live_label_session(monkeypatch):
    monkeypatch.setenv("HELIOS_LLM", "1")
    client = default_client()
    assert client is not None
    out = label_session(_session(), client)
    assert out
