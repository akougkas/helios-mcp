"""End-to-end invariants of the observe, drift, negotiate, commit cycle."""

import subprocess

import pytest

from helios_mcp.bootstrap import BootstrapManager
from helios_mcp.drift import js_divergence
from helios_mcp.negotiation import Negotiator, describe
from helios_mcp.store import ObservationStore, TurnObservation

DIM = "communication_register"


@pytest.fixture
def helios(tmp_path):
    BootstrapManager(tmp_path).bootstrap_installation()
    return tmp_path


def feed(helios, label, n, persona="developer", start=0, **kw):
    kw.setdefault("endorsement", 1.0)
    ObservationStore(helios).append(
        TurnObservation(persona=persona, session_id="s", turn_id=f"t{start + i}",
                        timestamp=float(i), source="heuristic",
                        labels={DIM: label}, **kw)
        for i in range(n))


TERSE = {"terse": 0.8, "moderate": 0.2}


def commits(helios):
    out = subprocess.run(["git", "-C", str(helios), "log", "--format=%s"],
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def test_accept_converges_on_the_same_ledger(helios):
    feed(helios, TERSE, 60)
    neg = Negotiator(helios)
    first = neg.evaluate("developer")
    assert first.proposal is not None
    assert DIM in first.proposal.changes

    decision = neg.accept("developer", first.proposal.id)
    assert decision.commit is not None

    resolved = neg.declared("developer")[DIM]
    target = first.proposal.changes[DIM].target
    assert all(abs(resolved[s] - p) < 1e-9 for s, p in target.items())

    again = neg.evaluate("developer")
    assert again.proposal is None
    assert not again.endorsed.drifted_dimensions
    assert "accepted" in commits(helios)[0]


def test_evaluate_keeps_the_pending_proposal_id_while_the_target_holds(helios):
    feed(helios, TERSE, 60)
    neg = Negotiator(helios)
    first = neg.evaluate("developer").proposal
    assert first is not None
    assert neg.evaluate("developer").proposal == first


def test_evidence_surfaces_a_suggestion_before_a_strong_proposal(helios):
    neg = Negotiator(helios)
    first = None
    for n in range(1, 80):
        feed(helios, TERSE, 1, start=n)
        evaluation = neg.evaluate("developer", auto_accept=False)
        if evaluation.proposal is not None:
            first = evaluation
            break
    assert first is not None and first.proposal is not None
    assert first.proposal.tier == "suggestion"
    assert first.proposal.changes[DIM].credibility < neg.config.credibility_level
    assert "Suggestion" in describe(first)[0]

    feed(helios, TERSE, 60, start=100)
    strong = neg.evaluate("developer", auto_accept=False).proposal
    assert strong is not None and strong.tier == "strong"
    assert strong.id != first.proposal.id


def test_reject_is_persisted_committed_and_cools_down(helios):
    feed(helios, TERSE, 60)
    neg = Negotiator(helios, cooldown_seconds=100)
    proposal = neg.evaluate("developer", now=0).proposal
    assert proposal is not None
    neg.reject("developer", proposal.id, "I like it wordy", )
    assert "rejected" in commits(helios)[0]

    during = neg.evaluate("developer", now=proposal.created_at + 10)
    assert during.proposal is None and DIM in during.cooling_down
    with pytest.raises(ValueError):
        neg.accept("developer", proposal.id)


def test_rejection_pulls_endorsed_evidence_toward_declared(helios):
    feed(helios, TERSE, 60)
    neg = Negotiator(helios)
    before = neg.evaluate("developer").endorsed.dimensions[DIM]
    neg.reject("developer", neg.proposals.pending("developer").id)  # type: ignore[union-attr]
    after, _, _ = neg.assess("developer")
    assert after.dimensions[DIM].divergence < before.divergence


def test_corrections_toward_declared_drive_drift_the_other_way(helios):
    declared = Negotiator(helios).declared("developer")[DIM]
    feed(helios, TERSE, 60, endorsement=-1.0, correction_hint={DIM: "thorough"})
    ev = Negotiator(helios).evaluate("developer")
    assert ev.proposal is not None
    assert ev.proposal.changes[DIM].target["thorough"] > declared["thorough"]
    # The fingerprint still says the agent was terse.
    fp = ev.fingerprint.dimensions[DIM].posterior_mean
    assert fp["terse"] > declared["terse"]


def test_small_well_supported_move_auto_accepts_and_commits(helios):
    neg = Negotiator(helios)
    declared = neg.declared("developer")[DIM]
    nudged = dict(declared)
    nudged["terse"] += 0.1
    nudged["moderate"] -= 0.1
    feed(helios, nudged, 2000)
    ev = neg.evaluate("developer")
    assert ev.auto_accepted == [DIM]
    assert ev.proposal is None
    assert "auto-accepted" in commits(helios)[0]
    assert js_divergence(list(neg.declared("developer")[DIM].values()),
                         list(nudged.values())) < js_divergence(
        list(declared.values()), list(nudged.values()))


def test_session_override_is_not_the_negotiation_baseline(helios):
    from helios_mcp.distribution import BehavioralDistribution
    from helios_mcp.profile import BehavioralProfile

    neg = Negotiator(helios)
    before = neg.declared("developer")
    BehavioralProfile(
        agent_id="developer", level="session", inherit_weight=0.0,
        distributions={DIM: BehavioralDistribution.point_mass(DIM, "terse")},
    ).save(helios / "temporary" / "developer.yaml")
    assert neg.declared("developer") == before
