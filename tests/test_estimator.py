"""Invariants of turning the ledger into fingerprint and endorsed evidence."""

import math

from helios_mcp.drift import DEFAULT_CONFIG
from helios_mcp.estimator import estimate
from helios_mcp.store import Proposal, ProposedChange, TurnObservation

DIM = "communication_register"
TERSE = {"terse": 1.0}
THOROUGH = {"thorough": 1.0}


def turn(tid, source="heuristic", label=None, **kw):
    return TurnObservation(persona="dev", session_id="s", turn_id=tid,
                           timestamp=0.0, source=source,
                           labels={DIM: label or THOROUGH}, **kw)


def test_source_precedence_picks_llm_over_heuristic_per_turn():
    ev = estimate([turn("t1", "heuristic", THOROUGH), turn("t1", "llm", TERSE),
                   turn("t1", "mcp", THOROUGH)])
    assert ev.turns == 1
    assert ev.fingerprint[DIM] == {"terse": 1.0}


def test_uncorrected_turns_count_for_both_posteriors():
    ev = estimate([turn("t1", endorsement=None), turn("t2", endorsement=1.0),
                   turn("t3", endorsement=0.0, confidence=0.5)])
    assert ev.fingerprint[DIM]["thorough"] == 2.5
    assert ev.endorsed[DIM]["thorough"] == 2.5


def test_hinted_correction_moves_endorsed_mass_to_hinted_state_only():
    ev = estimate([TurnObservation(
        persona="dev", session_id="s", turn_id="t1", timestamp=0, source="llm",
        labels={DIM: THOROUGH, "risk_caution": {"acts_immediately": 1.0}},
        endorsement=-1.0, correction_hint={DIM: "terse"})])
    assert ev.endorsed == {DIM: {"terse": 1.0}}
    # The fingerprint still records what the agent actually did.
    assert ev.fingerprint[DIM] == {"thorough": 1.0}


def test_unhinted_correction_moves_mass_away_from_labeled_state():
    ev = estimate([turn("t1", endorsement=-1.0)])
    endorsed = ev.endorsed[DIM]
    assert endorsed["thorough"] == 0.0
    assert math.isclose(sum(endorsed.values()), 1.0)


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
    assert ev.endorsed["risk_caution"] == {"acts_immediately": 1.0}


def test_dim_confidence_overrides_turn_confidence_per_dimension():
    ev = estimate([TurnObservation(
        persona="dev", session_id="s", turn_id="t1", timestamp=0, source="heuristic",
        labels={DIM: THOROUGH, "risk_caution": {"acts_immediately": 1.0}},
        confidence=0.6, dim_confidence={DIM: 0.2})])
    assert ev.endorsed[DIM] == {"thorough": 0.2}
    assert ev.fingerprint["risk_caution"] == {"acts_immediately": 0.6}
