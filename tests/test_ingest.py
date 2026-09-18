"""Ingest: transcripts and messages into the observation ledger."""

from __future__ import annotations

from pathlib import Path

from helios_mcp.estimator import estimate
from helios_mcp.ingest import ingest_session, observations_from_messages
from helios_mcp.store import ObservationStore, base_turn_id
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
    rows = list(ObservationStore(helios).iter("dev"))
    llm_rows = [r for r in rows if r.source == "llm"]
    assert [r.endorsement for r in llm_rows] == [-1.0, None]
    # Both sources carry the transcript's model id, for per-model fingerprints.
    assert {r.source for r in rows} == {"heuristic", "llm"}
    assert {r.model for r in rows} == {"claude-test"}


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


def test_message_path_records_the_reply_when_the_conversation_is_resent(tmp_path: Path):
    store = ObservationStore(tmp_path)
    short = [
        {"role": "user", "content": "explain the bug"},
        {"role": "assistant", "content": LONG},
    ]
    corrected = [*short, {"role": "user", "content": "no, too long. be terse"}]
    longer = [*corrected, {"role": "assistant", "content": "Off-by-one in the loop."},
              {"role": "user", "content": "thanks"}]

    # The unanswered turn waits for its reply instead of being frozen without one.
    assert store.append(observations_from_messages(persona="dev", messages=short)) == 0
    assert store.append(observations_from_messages(persona="dev", messages=corrected)) == 1
    assert store.append(observations_from_messages(persona="dev", messages=longer)) == 1
    assert store.append(observations_from_messages(persona="dev", messages=longer)) == 0

    first, second = store.iter("dev")
    assert first.endorsement == -1.0
    assert first.correction_hint == {"communication_register": "terse"}
    assert second.endorsement == 1.0
    assert {first.source, second.source} == {"mcp"}


class CountingClient:
    """Labels every turn it is shown and records how many it saw."""

    def __init__(self):
        self.seen: list[int] = []

    def complete_json(self, system, prompt, schema):
        ids = [int(line.split()[2]) for line in prompt.splitlines() if line.startswith("### turn ")]
        self.seen.append(len(ids))
        label = {"epistemic_style": {"confident": 1, "hedging": 0, "admits_ignorance": 0, "speculating": 0},
                 "interaction_agency": None, "communication_register": None, "risk_caution": None,
                 "confidence": 0.8, "endorsement": 0.5, "correction_hint": {}}
        return {"turns": [{"id": str(i), **label} for i in ids]}


def test_reply_to_the_last_turn_lands_when_a_session_is_resumed(tmp_path: Path):
    helios = tmp_path / "helios"
    b = TranscriptBuilder()
    b.prompt("rename the module")
    b.tool("Bash", {"command": "git mv a.py b.py"}, "t1")
    b.result("t1")
    b.say("Renamed the module and updated every import that referenced it.")
    path = b.write(tmp_path / "s.jsonl")
    ingest_session(helios, "dev", path, "s1", final=True)
    b.prompt("no, too long. be terse")   # the session is resumed
    b.say("ok")
    b.write(path)
    ingest_session(helios, "dev", path, "s1")

    ev = estimate(ObservationStore(helios).iter("dev"))
    assert ev.turns == 1
    assert ev.endorsed["communication_register"]["terse"] > 0


def test_resumed_session_end_labels_only_new_turns(tmp_path: Path):
    helios = tmp_path / "helios"
    b = _verbose_session_with_corrections(2)
    path = b.write(tmp_path / "s.jsonl")
    client = CountingClient()
    ingest_session(helios, "dev", path, "s1", final=True, client=client)
    b.prompt("one more thing")
    b.say("Done again.")
    b.write(path)
    ingest_session(helios, "dev", path, "s1", final=True, client=client)
    ingest_session(helios, "dev", path, "s1", final=True, client=client)
    # The turn the first run ended on was open; its reply now exists, so it
    # goes back once with the new turn, and nothing goes back a third time.
    assert client.seen == [3, 2]
    llm_ids = [r.turn_id for r in ObservationStore(helios).iter("dev") if r.source == "llm"]
    assert len(llm_ids) == len(set(llm_ids)) == 5
    assert len({base_turn_id(t) for t in llm_ids}) == 4


def test_model_hints_need_a_human_reply_and_opener_hints_come_from_the_lexicon(tmp_path: Path):
    b = TranscriptBuilder()
    b.prompt("check with me before changing files. Read brief.md and execute it exactly.")
    b.say("Here is the plan. Shall I start?")
    b.prompt("yes")
    b.say("Started.")
    path = b.write(tmp_path / "s.jsonl")
    label = {"epistemic_style": None, "interaction_agency": None, "communication_register": None,
             "risk_caution": {"acts_immediately": 1, "checks_before_acting": 0, "warns_frequently": 0,
                              "refuses_ambiguity": 0},
             "confidence": 0.8, "endorsement": 0.5,
             "correction_hint": {"interaction_agency": "assumes_and_acts", "communication_register": "terse"}}
    reply = {"turns": [{"id": "0", **label}, {"id": "1", **label}]}
    helios = tmp_path / "helios"
    ingest_session(helios, "dev", path, "s1", final=True, client=FakeClient(reply))
    opener, last = [r for r in ObservationStore(helios).iter("dev") if r.source == "llm"]
    assert opener.correction_hint == {
        "interaction_agency": "assumes_and_acts",
        "communication_register": "terse",
        "risk_caution": "checks_before_acting",
    }
    assert last.correction_hint is None


def test_stop_classifies_only_turns_without_a_row(tmp_path: Path, monkeypatch):
    import helios_mcp.ingest as ingest_mod

    helios = tmp_path / "helios"
    b = _verbose_session_with_corrections(3)
    path = b.write(tmp_path / "s.jsonl")
    ingest_session(helios, "dev", path, "s1")
    classified: list[str] = []
    real = ingest_mod.classify_turn
    monkeypatch.setattr(ingest_mod, "classify_turn",
                        lambda t: (classified.append(t.turn_id), real(t))[1])
    b.prompt("next task")
    b.say("Done.")
    b.prompt("thanks")
    ingest_session(helios, "dev", b.write(path), "s1")
    assert len(classified) == 2   # the answered turn before, and the new one
