"""Invariants of the observation ledger and proposal store."""

import pytest

from helios_mcp.security import InvalidInputError
from helios_mcp.store import (
    ObservationStore,
    ProposalStore,
    ProposedChange,
    TurnObservation,
)


def obs(turn: str, source: str = "heuristic", persona: str = "dev",
        **kw: object) -> TurnObservation:
    return TurnObservation(
        persona=persona, session_id="s1", turn_id=turn, timestamp=1000.0,
        source=source,
        labels={"communication_register": {"terse": 0.7, "moderate": 0.3}},
        **kw,  # type: ignore[arg-type]
    )


def test_append_is_idempotent_across_calls_and_within_batch(tmp_path):
    store = ObservationStore(tmp_path)
    assert store.append([obs("t1"), obs("t2"), obs("t1")]) == 2
    assert store.append([obs("t1"), obs("t2")]) == 0
    # Same turn from a different source is a distinct row.
    assert store.append([obs("t1", source="llm")]) == 1
    assert [o.turn_id for o in store.iter("dev")] == ["t1", "t2", "t1"]


def test_roundtrip_preserves_fields(tmp_path):
    store = ObservationStore(tmp_path)
    original = obs("t1", endorsement=-1.0, confidence=0.4,
                   correction_hint={"communication_register": "terse"},
                   dim_confidence={"communication_register": 0.9},
                   model="claude-opus-5")
    store.append([original])
    assert list(store.iter("dev")) == [original]


def test_rows_written_before_the_model_field_still_load(tmp_path):
    store = ObservationStore(tmp_path)
    store.path("dev").parent.mkdir(parents=True, exist_ok=True)
    store.path("dev").write_text(
        '{"persona":"dev","session_id":"s","turn_id":"t","timestamp":1.0,'
        '"source":"heuristic","labels":{}}\n')
    assert [o.model for o in store.iter("dev")] == [None]


def test_corrupt_and_torn_lines_are_skipped(tmp_path):
    store = ObservationStore(tmp_path)
    store.append([obs("t1")])
    with store.path("dev").open("a") as f:
        f.write('{"garbage": true}\nnot json\n{"persona": "dev", "sess')
    assert store.append([obs("t2")]) == 1
    assert [o.turn_id for o in store.iter("dev")] == ["t1", "t2"]


@pytest.mark.parametrize("bad", [
    {"labels": {"nope": {"terse": 1.0}}},
    {"labels": {"communication_register": {"shouty": 1.0}}},
    {"labels": {"communication_register": {"terse": 0.5}}},
    {"source": "guess"},
    {"endorsement": 2.0},
    {"confidence": -0.1},
    {"correction_hint": {"communication_register": "loud"}},
    {"dim_confidence": {"communication_register": 1.5}},
    {"dim_confidence": {"nope": 0.5}},
])
def test_invalid_observations_rejected(bad):
    fields: dict[str, object] = {"persona": "dev", "session_id": "s", "turn_id": "t",
                                 "timestamp": 1.0, "source": "mcp", "labels": {}}
    fields.update(bad)
    with pytest.raises(ValueError):
        TurnObservation(**fields)  # type: ignore[arg-type]


def test_persona_traversal_rejected(tmp_path):
    with pytest.raises(InvalidInputError):
        ObservationStore(tmp_path).path("../../x")
    with pytest.raises(InvalidInputError):
        obs("t1", persona="../x")


def change() -> dict[str, ProposedChange]:
    return {"communication_register": ProposedChange(
        declared={"terse": 0.5, "moderate": 0.5},
        target={"terse": 0.8, "moderate": 0.2}, divergence=0.05, credibility=0.97)}


def test_proposal_lifecycle_and_cooldown(tmp_path):
    store = ProposalStore(tmp_path, cooldown_seconds=100)
    first = store.create("dev", change(), observation_count=40, now=0)
    second = store.create("dev", change(), observation_count=50, now=1)
    assert store.get("dev", first.id).status == "superseded"  # type: ignore[union-attr]
    assert store.pending("dev") == second

    rejected = store.decide("dev", second.id, "rejected", reason="no", now=10)
    assert rejected.decided_dimensions == ("communication_register",)
    assert store.pending("dev") is None
    assert store.in_cooldown("dev", "communication_register", now=50)
    assert not store.in_cooldown("dev", "communication_register", now=200)
    assert not store.in_cooldown("dev", "risk_caution", now=50)

    # Survives a fresh instance reading from disk.
    assert ProposalStore(tmp_path).rejections("dev") == [rejected]


def test_decide_refuses_non_pending_and_unknown(tmp_path):
    store = ProposalStore(tmp_path)
    p = store.create("dev", change(), observation_count=1)
    with pytest.raises(ValueError):
        store.decide("dev", p.id, "accepted", dimensions=["risk_caution"])
    store.decide("dev", p.id, "accepted")
    with pytest.raises(ValueError):
        store.decide("dev", p.id, "rejected")
    with pytest.raises(KeyError):
        store.decide("dev", "missing", "accepted")


def test_an_unreadable_proposal_file_is_moved_aside_not_overwritten(tmp_path):
    store = ProposalStore(tmp_path)
    store.path("dev").parent.mkdir(parents=True)
    store.path("dev").write_text("garbage")
    assert store.all("dev") == []  # reads degrade to empty
    fresh = store.create("dev", change(), observation_count=1)
    assert store.all("dev") == [fresh]
    aside = list(store.path("dev").parent.glob("dev.json.corrupt-*"))
    assert [a.read_text() for a in aside] == ["garbage"]


def test_key_index_survives_rows_written_behind_its_back(tmp_path):
    store = ObservationStore(tmp_path)
    store.append([obs("t1")])
    # Another writer, or a crash between the ledger and index writes, leaves
    # the index behind the ledger; the next append must still see every key.
    with store.path("dev").open("a") as f:
        f.write(obs("t2").to_json() + "\n")
    assert store.append([obs("t2"), obs("t3")]) == 1
    store.index_path("dev").write_text('[12, [["s1"')  # torn index line
    assert store.append([obs("t1"), obs("t3")]) == 0
    assert store.count("dev") == 3
