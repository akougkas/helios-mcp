"""Negotiation: turn endorsed drift into persisted proposals and apply decisions.

``Negotiator.evaluate`` reads the ledger, estimates evidence, assesses drift
against the durable resolved profile (session overrides excluded), applies
auto-accepts, and keeps at most one pending proposal per persona. ``accept``
writes the user level (``personas/<p>_user.yaml``) as authoritative for the
accepted dimensions so the resolved profile equals the proposal target, then
commits. ``reject`` records the decision, which starts the cooldown and feeds
the estimator's pseudo-counts toward the declared profile.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .atomic_ops import git_commit, helios_lock
from .distribution import BehavioralDistribution
from .drift import (
    DEFAULT_CONFIG,
    DimensionDrift,
    DriftAssessment,
    DriftConfig,
    assess,
    js_divergence,
    smooth,
)
from .estimator import Evidence, estimate_ledger
from .hierarchy import IdentityHierarchy
from .llm import llm_enabled
from .profile import BehavioralProfile
from .security import persona_path
from .store import ObservationStore, Proposal, ProposalStore, ProposedChange
from .taxonomy import DIMENSION_DESCRIPTIONS, list_states

logger = logging.getLogger(__name__)

# A pending proposal is kept, id and all, while its targets move less than this.
# Otherwise every ingested turn would mint a new id under a reviewing user.
_SAME_TARGET_JS = 1e-3


@dataclass(frozen=True)
class Evaluation:
    persona: str
    endorsed: DriftAssessment
    fingerprint: DriftAssessment
    evidence: Evidence
    proposal: Proposal | None
    auto_accepted: list[str] = field(default_factory=list)
    cooling_down: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    proposal: Proposal
    commit: str | None
    profile_path: Path | None = None


def _target(drift: DimensionDrift, config: DriftConfig) -> dict[str, float]:
    states = list_states(drift.dimension)
    lifted = smooth([drift.posterior_mean[s] for s in states], config.min_prob)
    return dict(zip(states, lifted, strict=True))


class Negotiator:
    def __init__(self, helios_dir: Path, config: DriftConfig = DEFAULT_CONFIG,
                 cooldown_seconds: float | None = None) -> None:
        self.helios_dir = helios_dir
        self.config = config
        self.hierarchy = IdentityHierarchy(helios_dir)
        self.ledger = ObservationStore(helios_dir)
        self.proposals = (
            ProposalStore(helios_dir) if cooldown_seconds is None
            else ProposalStore(helios_dir, cooldown_seconds=cooldown_seconds)
        )

    def declared(self, persona: str) -> dict[str, dict[str, float]]:
        profile = self.hierarchy.resolve(persona, include_session=False)
        return {dim: d.to_dict() for dim, d in profile.distributions.items()}

    def evidence(self, persona: str) -> Evidence:
        return estimate_ledger(self.ledger, persona, self.proposals.all(persona),
                               self.config, llm_labels=llm_enabled(self.helios_dir))

    def assess(self, persona: str) -> tuple[DriftAssessment, DriftAssessment, Evidence]:
        """Endorsed and fingerprint assessments with the evidence behind them."""
        evidence = self.evidence(persona)
        declared = self.declared(persona)
        return (
            assess(declared, evidence.endorsed, self.config),
            assess(declared, evidence.fingerprint, self.config),
            evidence,
        )

    def model_fingerprints(self, persona: str, evidence: Evidence | None = None,
                           ) -> list[tuple[str, int, DriftAssessment]]:
        """Each known model's fingerprint against the declared profile.

        Returns ``(model, turns, assessment)`` with the most observed model
        first. A model's credible deviations are what the rendered context
        asks it to counter.
        """
        if evidence is None:
            evidence = self.evidence(persona)
        declared = self.declared(persona)
        ranked = sorted(evidence.model_turns.items(), key=lambda mt: (-mt[1], mt[0]))
        return [(model, turns,
                 assess(declared, evidence.fingerprint_by_model[model], self.config))
                for model, turns in ranked]

    def evaluate(self, persona: str, auto_accept: bool = True,
                 now: float | None = None) -> Evaluation:
        """Assess drift, apply auto-accepts, and reconcile the pending proposal."""
        # Under the lock, an auto-accept is decided on the evidence and profile
        # it is written over, and cannot interleave with a user's decision.
        with helios_lock(self.helios_dir):
            return self._evaluate(persona, auto_accept, now)

    def _evaluate(self, persona: str, auto_accept: bool,
                  now: float | None) -> Evaluation:
        now = time.time() if now is None else now
        endorsed, fingerprint, evidence = self.assess(persona)

        auto: list[str] = []
        if auto_accept and endorsed.auto_accept_dimensions:
            auto = endorsed.auto_accept_dimensions
            changes = {d: self._change(endorsed.dimensions[d]) for d in auto}
            silent = self.proposals.create_decided(
                persona, changes, evidence.ledger_rows, "auto_accepted", now=now)
            self._apply(persona, silent, auto)
            endorsed, fingerprint, evidence = self.assess(persona)

        cooling = [d for d in endorsed.drifted_dimensions
                   if self.proposals.in_cooldown(persona, d, now)]
        drifted = [d for d in endorsed.drifted_dimensions if d not in cooling]
        pending = self.proposals.pending(persona)
        proposal: Proposal | None = None
        if drifted:
            changes = {d: self._change(endorsed.dimensions[d]) for d in drifted}
            if pending is not None and self._same(pending, changes):
                proposal = pending
            else:
                proposal = self.proposals.create(
                    persona, changes, evidence.ledger_rows, now=now)
        elif pending is not None:
            self.proposals.decide(persona, pending.id, "superseded",
                                  reason="drift no longer credible", now=now)

        return Evaluation(persona, endorsed, fingerprint, evidence, proposal,
                          auto, cooling)

    def accept(self, persona: str, proposal_id: str,
               dimensions: list[str] | None = None) -> Decision:
        with helios_lock(self.helios_dir):
            decided = self.proposals.decide(persona, proposal_id, "accepted",
                                            dimensions)
            path, sha = self._apply(persona, decided,
                                    list(decided.decided_dimensions))
        return Decision(decided, sha, path)

    def reject(self, persona: str, proposal_id: str, reason: str = "",
               dimensions: list[str] | None = None) -> Decision:
        with helios_lock(self.helios_dir):
            decided = self.proposals.decide(persona, proposal_id, "rejected",
                                            dimensions,
                                            reason=reason or "rejected by user")
            sha = git_commit(
                self.helios_dir, [self.proposals.path(persona)],
                f"{persona}: rejected {', '.join(decided.decided_dimensions)} "
                f"(proposal {decided.id})"
                + (f"\n\n{decided.reason}" if decided.reason else ""),
            )
        return Decision(decided, sha)

    # ------------------------------------------------------------------

    def _change(self, drift: DimensionDrift) -> ProposedChange:
        return ProposedChange(
            declared=drift.declared,
            target=_target(drift, self.config),
            divergence=drift.divergence,
            credibility=drift.credibility,
            tier=drift.tier or "strong",
        )

    @staticmethod
    def _same(pending: Proposal, changes: dict[str, ProposedChange]) -> bool:
        if set(pending.changes) != set(changes):
            return False
        for dim, change in changes.items():
            if pending.changes[dim].tier != change.tier:
                return False
            states = list_states(dim)
            old = [pending.changes[dim].target[s] for s in states]
            new = [change.target[s] for s in states]
            if js_divergence(old, new) > _SAME_TARGET_JS:
                return False
        return True

    def _apply(self, persona: str, proposal: Proposal,
               dimensions: list[str]) -> tuple[Path, str | None]:
        """Write targets to the user level and commit."""
        with helios_lock(self.helios_dir):
            return self._apply_locked(persona, proposal, dimensions)

    def _apply_locked(self, persona: str, proposal: Proposal,
                      dimensions: list[str]) -> tuple[Path, str | None]:
        path = persona_path(self.helios_dir / "personas", persona, "_user.yaml")
        if path.exists():
            user = BehavioralProfile.load(path)
        else:
            user = BehavioralProfile(
                agent_id=f"{persona}_user", level="user", distributions={},
                parent_id=persona, specialization_level=3,
                description=f"Learned preferences for {persona}",
            )
        if user.inherit_weight != 0.0 and user.distributions:
            # Switching an existing user level to authoritative would change
            # what its other dimensions resolve to, so freeze them at their
            # current resolved values first.
            current = self.hierarchy.resolve(persona, include_session=False)
            for dim in user.distributions:
                user.distributions[dim] = current.distributions[dim]
        user.inherit_weight = 0.0
        for dim in dimensions:
            user.distributions[dim] = BehavioralDistribution(
                dim, proposal.changes[dim].target)
        user.observation_count = proposal.observation_count
        user.last_negotiation = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        user.save(path)

        verb = "auto-accepted" if proposal.status == "auto_accepted" else "accepted"
        sha = git_commit(
            self.helios_dir, [path, self.proposals.path(persona)],
            f"{persona}: {verb} {', '.join(dimensions)} "
            f"(proposal {proposal.id}, {proposal.observation_count} ledger rows)",
        )
        return path, sha


def _shift(r: DimensionDrift) -> str:
    """What moved, in words: the new leading state, or, when the lead held,
    the state that gained the most mass."""
    declared = max(r.declared, key=r.declared.__getitem__)
    observed = max(r.posterior_mean, key=r.posterior_mean.__getitem__)
    if observed != declared:
        return (f"you seem to prefer '{observed}' ({r.posterior_mean[observed]:.0%}) "
                f"over the profile's '{declared}' ({r.declared[declared]:.0%})")
    gained = max(r.posterior_mean,
                 key=lambda s: r.posterior_mean[s] - r.declared.get(s, 0.0))
    return (f"'{gained}' has grown from {r.declared.get(gained, 0.0):.0%} in the "
            f"profile to {r.posterior_mean[gained]:.0%}, while '{declared}' still "
            f"leads at {r.posterior_mean[declared]:.0%} "
            f"(the profile has {r.declared[declared]:.0%})")


def describe(evaluation: Evaluation) -> tuple[str, dict[str, str]]:
    """Plain-language summary of endorsed drift, plus one line per dimension."""
    per_dim: dict[str, str] = {}
    for dim, r in evaluation.endorsed.dimensions.items():
        if r.tier == "strong":
            per_dim[dim] = f"Drifted: {_shift(r)}; {r.credibility:.0%} credible."
        elif r.tier == "suggestion":
            per_dim[dim] = (f"Possibly shifting: {_shift(r)}; "
                            f"{r.credibility:.0%} credible so far.")
        elif r.evidence == 0:
            per_dim[dim] = "No evidence yet."
        else:
            per_dim[dim] = f"Consistent with the profile ({r.evidence:.0f} turns)."

    proposal = evaluation.proposal
    if proposal is None:
        lines = [f"No credible drift for '{evaluation.persona}' "
                 f"over {evaluation.evidence.turns} observed turns."]
        if evaluation.cooling_down:
            lines.append("Recently rejected and cooling down: "
                         + ", ".join(evaluation.cooling_down) + ".")
        return "\n".join(lines), per_dim

    if proposal.tier == "strong":
        opening = (f"Your preferences for '{evaluation.persona}' have moved away "
                   f"from its profile over {evaluation.evidence.turns} observed turns.")
        closing = (f"Proposal {proposal.id} updates these dimensions to the observed "
                   "preference. Accept or reject it; either way the decision is "
                   "recorded.")
    else:
        opening = (f"A suggestion for '{evaluation.persona}', based on "
                   f"{evaluation.evidence.turns} observed turns. The evidence is "
                   "early, so it may be wrong.")
        closing = (f"Suggestion {proposal.id} would update these dimensions. A quick "
                   "no is fine and also teaches Helios something.")
    lines = [opening, ""]
    for dim in proposal.changes:
        lines.append(f"- {DIMENSION_DESCRIPTIONS[dim]}: {per_dim[dim]}")
    lines += ["", closing]
    return "\n".join(lines), per_dim

