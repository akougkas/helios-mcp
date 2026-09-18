"""Calibration reports aggregates only and skips lab and subagent transcripts."""

from __future__ import annotations

import json
from pathlib import Path

from helios_mcp.calibrate import agreement_report, heuristic_report, iter_transcripts
from helios_mcp.transcript import parse_transcript

from .transcript_fixtures import TranscriptBuilder

SECRET = "zebra-quartz-771"


def _corpus(root: Path) -> None:
    b = TranscriptBuilder()
    b.prompt(f"deploy {SECRET} now")
    b.say(f"Deployed {SECRET}. Tests pass.")
    b.prompt("too long, be terse")
    b.say("ok")
    for rel in ("-home-u-proj/s1.jsonl", "-tmp-helios-lab-run/s2.jsonl", "-home-u-proj/s1/subagents/a.jsonl"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        b.write(path)


def test_reports_carry_no_transcript_text(tmp_path: Path):
    _corpus(tmp_path)
    paths = list(iter_transcripts(tmp_path))
    assert [p.name for p in paths] == ["s1.jsonl"]

    report = heuristic_report(paths)
    assert report["sessions"] == 1
    assert report["correction_hints"] == {"communication_register.terse": 1}

    class Echo:
        def complete_json(self, system, prompt, schema):
            return {"turns": [{"id": "0", "confidence": 1, "endorsement": -1,
                               "correction_hint": {"risk_caution": SECRET}}]}

    agreement = agreement_report([parse_transcript(paths[0])], Echo(), workers=1)
    assert agreement["endorsement"]["sign_agree"] == 1
    assert SECRET not in json.dumps(report) + json.dumps(agreement)
