"""Ingest: transcripts and messages into the observation ledger."""

from __future__ import annotations

from pathlib import Path

from helios_mcp.estimator import estimate
from helios_mcp.ingest import ingest_session, observations_from_messages
from helios_mcp.store import ObservationStore
from helios_mcp.transcript import parse_timestamp

from .transcript_fixtures import TranscriptBuilder

LONG = " ".join(["The change rewrites the parser loop and updates every caller."] * 40)


def _verbose_session_with_corrections(n: int = 6) -> TranscriptBuilder:
    b = TranscriptBuilder()
    b.prompt("start")
    for _ in range(n):
        b.tool("Read", {"file_path": "a.py"}, f"r{len(b.records)}")
        b.say(LONG)
        b.prompt("too long, be terse")
    b.say("Done.")
    return b


class FakeClient:
    def __init__(self, reply=None):
        self.reply = reply
        self.calls = 0

    def complete_json(self, system, prompt, schema):
        self.calls += 1
        return self.reply


def test_stop_ingest_is_idempotent_and_holds_back_the_open_turn(tmp_path: Path):
    b = _verbose_session_with_corrections(3)
    path = b.write(tmp_path / "s.jsonl")
    helios = tmp_path / "helios"
    client = FakeClient()

    first = ingest_session(helios, "dev", path, "s1", client=client)
    assert first == 3  # the last turn has no reply yet
    assert ingest_session(helios, "dev", path, "s1", client=client) == 0
    assert client.calls == 0  # Stop never calls the model

    assert ingest_session(helios, "dev", path, "s1", final=True, client=client) == 1
    rows = list(ObservationStore(helios).iter("dev"))
    assert [r.endorsement for r in rows] == [-1.0, -1.0, -1.0, None]
    assert all(r.correction_hint == {"communication_register": "terse"} for r in rows[:3])
    stamps = {parse_timestamp(rec["timestamp"]) for rec in b.records if rec.get("timestamp")}
    assert all(r.timestamp in stamps for r in rows)
    for r in rows:
        assert r.dim_confidence is not None
        assert set(r.dim_confidence) == set(r.labels)


def test_corrections_move_endorsed_register_toward_terse(tmp_path: Path):
    helios = tmp_path / "helios"
    path = _verbose_session_with_corrections().write(tmp_path / "s.jsonl")
    ingest_session(helios, "dev", path, "s1", final=True, client=FakeClient())
    evidence = estimate(ObservationStore(helios).iter("dev"))
    endorsed = evidence.endorsed["communication_register"]
    fingerprint = evidence.fingerprint["communication_register"]
    assert max(endorsed, key=endorsed.__getitem__) == "terse"
    assert fingerprint["thorough"] > fingerprint["terse"]


def test_final_ingest_adds_model_rows_with_transcript_facts_enforced(tmp_path: Path):
    b = TranscriptBuilder()
    b.prompt("deploy")
    b.tool("Bash", {"command": "make deploy"}, "t1")
    b.interrupt()
    b.prompt("use staging")
    b.say("Deployed to staging.")
    path = b.write(tmp_path / "s.jsonl")
    label = {"epistemic_style": {"confident": 1, "hedging": 0, "admits_ignorance": 0, "speculating": 0},
             "interaction_agency": None, "communication_register": None, "risk_caution": None,
             "confidence": 0.8, "endorsement": 1, "correction_hint": {}}
    reply = {"turns": [{"id": "0", **label}, {"id": "1", **label}]}
    helios = tmp_path / "helios"
    ingest_session(helios, "dev", path, "s1", final=True, client=FakeClient(reply))
    llm_rows = [r for r in ObservationStore(helios).iter("dev") if r.source == "llm"]
    assert [r.endorsement for r in llm_rows] == [-1.0, None]


def test_missing_or_truncated_transcripts(tmp_path: Path):
    helios = tmp_path / "helios"
    assert ingest_session(helios, "dev", tmp_path / "nope.jsonl", "s1", final=True) == 0
    b = TranscriptBuilder()
    b.prompt("hi")
    b.say("Hello. The repo builds and tests pass.")
    path = b.write(tmp_path / "s.jsonl")
    with path.open("a") as fh:
        fh.write('{"type": "user", "message": {"role": "us')
    assert ingest_session(helios, "dev", path, "s1", final=True) == 1


def test_message_path_is_idempotent_when_the_conversation_is_resent(tmp_path: Path):
    store = ObservationStore(tmp_path)
    short = [
        {"role": "user", "content": "explain the bug"},
        {"role": "assistant", "content": LONG},
    ]
    longer = [*short, {"role": "user", "content": "shorter please"},
              {"role": "assistant", "content": "Off-by-one in the loop."}]
    first = observations_from_messages(persona="dev", messages=short)
    assert store.append(first) == 1
    again = observations_from_messages(persona="dev", messages=longer)
    assert again[0].turn_id == first[0].turn_id
    assert again[0].correction_hint == {"communication_register": "terse"}
    assert store.append(again) == 1
    assert {o.source for o in again} == {"mcp"}
