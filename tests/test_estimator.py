"""Invariants of turning the ledger into fingerprint and endorsed evidence."""

import math

from helios_mcp.drift import DEFAULT_CONFIG, DriftConfig
from helios_mcp.estimator import estimate
from helios_mcp.store import Proposal, ProposedChange, TurnObservation

DIM = "communication_register"
# Linear in confidence, full-weight corrections: the bookkeeping is easy to read.
LINEAR = DriftConfig(confidence_exponent=1.0, unhinted_correction_weight=1.0)
TERSE = {"terse": 1.0}
THOROUGH = {"thorough": 1.0}


def turn(tid, source="heuristic", label=None, **kw):
    kw.setdefault("endorsement", 1.0)
    return TurnObservation(persona="dev", session_id="s", turn_id=tid,
                           timestamp=0.0, source=source,
                           labels={DIM: label or THOROUGH}, **kw)


def test_source_precedence_picks_llm_over_heuristic_per_turn():
    ev = estimate([turn("t1", "heuristic", THOROUGH), turn("t1", "llm", TERSE),
                   turn("t1", "mcp", THOROUGH)])
    assert ev.turns == 1
    assert ev.fingerprint[DIM] == {"terse": 1.0}


def test_uncorrected_turns_are_endorsed_by_how_the_user_responded():
    obs = [turn("t1", endorsement=None), turn("t2", endorsement=1.0),
           turn("t3", endorsement=0.5), turn("t4", endorsement=0.0),
           turn("t5", endorsement=-0.5)]
    ev = estimate(obs, config=LINEAR)
    # The fingerprint counts every turn; endorsed counts an approval in full,
    # moving on weakly, and silence or an outcome complaint not at all.
    assert ev.fingerprint[DIM]["thorough"] == 5.0
    assert math.isclose(ev.endorsed[DIM]["thorough"],
                        DEFAULT_CONFIG.approval_weight + DEFAULT_CONFIG.moved_on_weight)
    assert set(ev.endorsed[DIM]) == {"thorough"}


def test_hinted_correction_moves_endorsed_mass_to_hinted_state_only():
    ev = estimate([TurnObservation(
        persona="dev", session_id="s", turn_id="t1", timestamp=0, source="llm",
        labels={DIM: THOROUGH, "risk_caution": {"acts_immediately": 1.0}},
        endorsement=-1.0, correction_hint={DIM: "terse"})])
    assert ev.endorsed == {DIM: {"terse": 1.0}}
    # The fingerprint still records what the agent actually did.
    assert ev.fingerprint[DIM] == {"thorough": 1.0}


def test_unhinted_correction_moves_down_weighted_mass_away_from_labeled_state():
    ev = estimate([turn("t1", endorsement=-1.0)])
    endorsed = ev.endorsed[DIM]
    assert endorsed["thorough"] == 0.0
    assert math.isclose(sum(endorsed.values()),
                        DEFAULT_CONFIG.unhinted_correction_weight)


def test_fingerprint_is_split_by_model_and_a_relabel_keeps_the_model():
    ev = estimate([turn("t1", model="m-a"), turn("t1", "llm", TERSE),
                   turn("t2", model="m-b"), turn("t3")], config=LINEAR)
    assert ev.model_turns == {"m-a": 1, "m-b": 1}
    # t1's llm row carries no model; the turn keeps the one its heuristic row saw.
    assert ev.fingerprint_by_model["m-a"] == {DIM: {"terse": 1.0}}
    assert ev.fingerprint_by_model["m-b"] == {DIM: {"thorough": 1.0}}


def test_confidence_exponent_softens_the_confidence_discount():
    obs = [turn("t1", confidence=0.25)]
    assert estimate(obs, config=LINEAR).endorsed[DIM]["thorough"] == 0.25
    assert estimate(obs, config=DriftConfig(confidence_exponent=0.5)
                    ).endorsed[DIM]["thorough"] == 0.5


def proposal(status, count, dims=(DIM,), declared=None):
    change = ProposedChange(declared=declared or {"moderate": 1.0},
                            target={"terse": 1.0}, divergence=0.1, credibility=1.0)
    return Proposal(id=status, persona="dev", created_at=0,
                    changes={DIM: change}, observation_count=count,
                    status=status, decided_at=0, decided_dimensions=dims)


def test_accept_absorbs_evidence_seen_before_its_watermark():
    ledger = [turn("t1"), turn("t2"), turn("t3"), turn("t2", source="llm")]
    ev = estimate(ledger, [proposal("accepted", 2)])
    # t1 and t2 were absorbed; the later llm relabel of t2 must not revive it.
    assert ev.endorsed[DIM]["thorough"] == 1.0
    assert ev.fingerprint[DIM]["thorough"] == 3.0


def test_rejection_adds_pseudo_counts_toward_declared_until_a_later_accept():
    ev = estimate([turn("t1")], [proposal("rejected", 1)])
    assert ev.endorsed[DIM]["moderate"] > 0
    ev = estimate([turn("t1")], [proposal("rejected", 1), proposal("accepted", 1)])
    assert "moderate" not in ev.endorsed.get(DIM, {})


def test_standing_preference_counts_toward_hint_in_place_of_label():
    ev = estimate([TurnObservation(
        persona="dev", session_id="s", turn_id="t1", timestamp=0, source="llm",
        labels={DIM: THOROUGH, "risk_caution": {"acts_immediately": 1.0}},
        endorsement=0.5, correction_hint={DIM: "terse"})])
    assert ev.endorsed[DIM] == {"terse": DEFAULT_CONFIG.standing_hint_weight}
    assert ev.endorsed["risk_caution"] == {
        "acts_immediately": DEFAULT_CONFIG.moved_on_weight}


def test_dim_confidence_overrides_turn_confidence_per_dimension():
    ev = estimate([TurnObservation(
        persona="dev", session_id="s", turn_id="t1", timestamp=0, source="heuristic",
        labels={DIM: THOROUGH, "risk_caution": {"acts_immediately": 1.0}},
        confidence=0.6, dim_confidence={DIM: 0.2}, endorsement=1.0)], config=LINEAR)
    assert ev.endorsed[DIM] == {"thorough": 0.2}
    assert ev.fingerprint["risk_caution"] == {"acts_immediately": 0.6}


def test_with_model_labels_only_model_labeled_turns_are_endorsed():
    ledger = [turn("t1", "heuristic", TERSE), turn("t2", "heuristic", TERSE),
              turn("t2", "llm", THOROUGH)]
    ev = estimate(ledger, config=LINEAR, llm_labels=True)
    assert ev.endorsed[DIM] == {"thorough": 1.0}
    assert ev.endorsed_turns == 1
    # The fingerprint still previews the heuristic-only turn.
    assert ev.fingerprint[DIM] == {"terse": 1.0, "thorough": 1.0}


def test_model_label_after_an_accept_counts_from_its_own_row():
    # t1 had only a heuristic row when the proposal was accepted at row 1; its
    # model label arrives later and was never absorbed.
    ledger = [turn("t1", "heuristic", TERSE), turn("t1", "llm", THOROUGH)]
    ev = estimate(ledger, [proposal("accepted", 1)], config=LINEAR, llm_labels=True)
    assert ev.endorsed[DIM] == {"thorough": 1.0}
