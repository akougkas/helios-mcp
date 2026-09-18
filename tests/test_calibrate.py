"""Calibration reports aggregates only and skips lab and subagent transcripts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helios_mcp.calibrate import (
    CORPUS_PERSONA,
    agreement_report,
    heuristic_report,
    iter_transcripts,
    label_corpus,
    ledger_report,
)
from helios_mcp.store import ObservationStore, TurnObservation
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


def test_label_corpus_is_resumable(tmp_path: Path):
    _corpus(tmp_path / "projects")
    paths = list(iter_transcripts(tmp_path / "projects"))
    out = tmp_path / "ledger"

    class Flaky:
        def __init__(self, reply):
            self.reply = reply
            self.calls = 0

        def complete_json(self, system, prompt, schema):
            self.calls += 1
            return self.reply

    label = {"epistemic_style": None, "interaction_agency": None, "communication_register": None,
             "risk_caution": None, "confidence": 0.5, "endorsement": -1,
             "correction_hint": {"communication_register": "terse"}}
    down = Flaky(None)
    first = label_corpus(paths, out, down, workers=2)
    assert first["sessions_done"] == 1 and down.calls == 1
    up = Flaky({"turns": [{"id": "0", **label}, {"id": "1", **label}]})
    label_corpus(paths, out, up, workers=2)
    label_corpus(paths, out, up, workers=2)
    assert up.calls == 1  # the third pass finds nothing left to label
    status = json.loads((out / "status.json").read_text())
    assert status["finished"] is not None
    assert SECRET not in (out / "observations" / "corpus.jsonl").read_text()


def _obs(turn: str, source: str, label: dict[str, float], hint=None) -> TurnObservation:
    return TurnObservation(
        persona=CORPUS_PERSONA, session_id="s", turn_id=turn, timestamp=1.0,
        source=source, labels={"structure": label}, endorsement=0.5,
        correction_hint=hint,
    )


PROSE = {"prose": 0.8, "light_structure": 0.1, "heavy_structure": 0.1}
HEAVY = {"prose": 0.1, "light_structure": 0.1, "heavy_structure": 0.8}


def test_ledger_report_pairs_rows_and_maps_heuristic_to_model_space(tmp_path: Path):
    # The heuristic calls every turn prose; the model says half are heavy.
    rows = []
    for i in range(4):
        rows.append(_obs(f"t{i}", "heuristic", PROSE, {"structure": "prose"}))
        rows.append(_obs(f"t{i}", "llm", PROSE if i % 2 else HEAVY,
                         {"structure": "prose"} if i == 0 else None))
    rows.append(_obs("unpaired", "heuristic", PROSE))
    ObservationStore(tmp_path).append(rows)

    report = ledger_report(tmp_path)
    assert report["paired_turns"] == 4
    assert report["heuristic_hint_precision"]["structure.prose"]["precision"] == 0.25
    assert report["argmax_agreement"]["structure"] == 0.5

    bias = report["bias_map"]["structure"]
    for row in bias.values():
        assert sum(row.values()) == pytest.approx(1.0, abs=1e-3)
    assert bias["prose"]["heavy_structure"] > 0.3
    # Too little heuristic mass on the other states to estimate, so identity.
    assert bias["light_structure"] == {
        "prose": 0.0, "light_structure": 1.0, "heavy_structure": 0.0,
    }
