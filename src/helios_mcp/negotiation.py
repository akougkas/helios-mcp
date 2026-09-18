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

from .atomic_ops import git_commit
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
from .estimator import Evidence, estimate
from .hierarchy import IdentityHierarchy
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

    def assess(self, persona: str) -> tuple[DriftAssessment, DriftAssessment, Evidence]:
        """Endorsed and fingerprint assessments with the evidence behind them."""
        evidence = estimate(self.ledger.iter(persona), self.proposals.all(persona),
                            self.config)
        declared = self.declared(persona)
        return (
            assess(declared, evidence.endorsed, self.config),
            assess(declared, evidence.fingerprint, self.config),
            evidence,
        )

    def evaluate(self, persona: str, auto_accept: bool = True,
                 now: float | None = None) -> Evaluation:
        """Assess drift, apply auto-accepts, and reconcile the pending proposal."""
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
        decided = self.proposals.decide(persona, proposal_id, "accepted", dimensions)
        path, sha = self._apply(persona, decided, list(decided.decided_dimensions))
        return Decision(decided, sha, path)

    def reject(self, persona: str, proposal_id: str, reason: str = "",
               dimensions: list[str] | None = None) -> Decision:
        decided = self.proposals.decide(persona, proposal_id, "rejected", dimensions,
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
        )

    @staticmethod
    def _same(pending: Proposal, changes: dict[str, ProposedChange]) -> bool:
        if set(pending.changes) != set(changes):
            return False
        for dim, change in changes.items():
            states = list_states(dim)
            old = [pending.changes[dim].target[s] for s in states]
            new = [change.target[s] for s in states]
            if js_divergence(old, new) > _SAME_TARGET_JS:
                return False
        return True

    def _apply(self, persona: str, proposal: Proposal,
               dimensions: list[str]) -> tuple[Path, str | None]:
        """Write targets to the user level and commit."""
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


def describe(evaluation: Evaluation) -> tuple[str, dict[str, str]]:
    """Plain-language summary of endorsed drift, plus one line per dimension."""
    per_dim: dict[str, str] = {}
    for dim, r in evaluation.endorsed.dimensions.items():
        declared = max(r.declared, key=r.declared.__getitem__)
        observed = max(r.posterior_mean, key=r.posterior_mean.__getitem__)
        if r.drifted:
            per_dim[dim] = (
                f"Drifted: your preferred '{observed}' is now at "
                f"{r.posterior_mean[observed]:.0%}, the profile says '{declared}' "
                f"at {r.declared[declared]:.0%} ({r.credibility:.0%} credible)."
            )
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

    lines = [
        f"Your preferences for '{evaluation.persona}' have moved away from its "
        f"profile over {evaluation.evidence.turns} observed turns.",
        "",
    ]
    for dim in proposal.changes:
        lines.append(f"- {DIMENSION_DESCRIPTIONS[dim]}: {per_dim[dim]}")
    lines += [
        "",
        f"Proposal {proposal.id} updates these dimensions to the observed "
        "preference. Accept or reject it; either way the decision is recorded.",
    ]
    return "\n".join(lines), per_dim


# Legacy engine. Removed once server and cli move to Negotiator.
import subprocess  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import TypedDict  # noqa: E402

from .drift import DriftDetector, DriftResult  # noqa: E402
from .observer import BehavioralObserver  # noqa: E402
from .taxonomy import list_dimensions  # noqa: E402


@dataclass
class NegotiationProposal:
    """A proposed behavioral profile update after drift is detected.

    Attributes:
        persona_name: Name of the persona being negotiated.
        summary: Natural language paragraph explaining the drift.
        per_dimension_summary: One-sentence explanation per dimension.
        proposed_distributions: Proposed new distributions (dim -> state -> prob).
        drift_result: The DriftResult that triggered this proposal.
        proposed_at: ISO-8601 timestamp of when this proposal was generated.
    """

    persona_name: str
    summary: str
    per_dimension_summary: dict[str, str]
    proposed_distributions: dict[str, dict[str, float]]
    drift_result: DriftResult
    proposed_at: str


# ---------------------------------------------------------------------------
# Result TypedDicts
#
# apply_update and reject_update each return exactly one key set on every
# call — neither has an error/short-circuit branch that returns a different
# shape, so both are modeled as total (all-required) TypedDicts.
# ---------------------------------------------------------------------------


class ApplyUpdateResult(TypedDict):
    """Return shape of NegotiationEngine.apply_update."""

    status: str
    updated_dimensions: list[str]
    commit_message: str


class RejectUpdateResult(TypedDict):
    """Return shape of NegotiationEngine.reject_update."""

    status: str
    persona: str
    reason: str


# ---------------------------------------------------------------------------
# NegotiationEngine class
# ---------------------------------------------------------------------------


class NegotiationEngine:
    """Generates drift summaries and manages the negotiation lifecycle."""

    def generate_summary(
        self,
        persona_name: str,
        declared_profile: BehavioralProfile,
        observed_dists: dict[str, BehavioralDistribution],
        drift_result: DriftResult,
    ) -> NegotiationProposal:
        """Build a NegotiationProposal from drift data.

        Args:
            persona_name: Name of the persona.
            declared_profile: The current declared BehavioralProfile.
            observed_dists: Observed distributions from the observer.
            drift_result: The computed DriftResult for this drift event.

        Returns:
            NegotiationProposal with natural language summary and proposed update.
        """
        obs_count = drift_result.observation_count
        total_drift = drift_result.total_drift
        dims_exceeding = drift_result.dimensions_exceeding_threshold

        # Build per-dimension summaries
        per_dim_summary: dict[str, str] = {}
        for dim in list_dimensions():
            declared_dist = declared_profile.distributions.get(dim)
            observed_dist = observed_dists.get(dim)
            kl = drift_result.per_dimension.get(dim, 0.0)
            if declared_dist is not None and observed_dist is not None:
                per_dim_summary[dim] = self.generate_per_dimension_summary(
                    dim, declared_dist, observed_dist, kl
                )
            else:
                per_dim_summary[dim] = "No data available for this dimension."

        # Build the main summary paragraph
        lines: list[str] = [
            (
                f"Your '{persona_name}' behavioral profile has drifted from its "
                "declared state."
            ),
            (
                f"Over {obs_count} observed interactions, your agent's actual behavior"
                f" diverged significantly from its profile"
                f" (drift score: {total_drift:.2f}, threshold: 0.30)."
            ),
            "",
            "The most significant changes:",
        ]

        if dims_exceeding:
            for dim in dims_exceeding:
                dim_desc = DIMENSION_DESCRIPTIONS.get(dim, dim)
                declared_dist = declared_profile.distributions.get(dim)
                observed_dist = observed_dists.get(dim)
                declared_most = (
                    declared_dist.most_likely() if declared_dist else "unknown"
                )
                observed_most = (
                    observed_dist.most_likely() if observed_dist else "unknown"
                )
                lines.append(
                    f"- {dim_desc}: the agent was observed behaving as"
                    f" '{observed_most}' more than its declared '{declared_most}'"
                    f" profile suggests."
                )
        else:
            lines.append(
                "  Multiple dimensions show moderate drift that together exceed"
                " the threshold."
            )

        lines.extend([
            "",
            "Do you want to update the declared profile to match observed behavior?",
            (
                "Accepting this update will commit the changes to your behavioral"
                " biography."
            ),
        ])

        summary = "\n".join(lines)

        # Build proposed distributions dict
        proposed_distributions: dict[str, dict[str, float]] = {
            dim: dist.to_dict()
            for dim, dist in observed_dists.items()
        }

        proposed_at = datetime.now(UTC).isoformat()

        return NegotiationProposal(
            persona_name=persona_name,
            summary=summary,
            per_dimension_summary=per_dim_summary,
            proposed_distributions=proposed_distributions,
            drift_result=drift_result,
            proposed_at=proposed_at,
        )

    def generate_per_dimension_summary(
        self,
        dim: str,  # noqa: ARG002 - kept for symmetry with generate_summary's call site
        declared_dist: BehavioralDistribution,
        observed_dist: BehavioralDistribution,
        kl: float,
    ) -> str:
        """Generate a one-sentence summary for a single dimension.

        Args:
            dim: Dimension name.
            declared_dist: The declared distribution for this dimension.
            observed_dist: The observed distribution for this dimension.
            kl: KL-divergence between observed and declared.

        Returns:
            One sentence describing the drift level for this dimension.
        """
        observed_most = observed_dist.most_likely()
        declared_most = declared_dist.most_likely()

        if kl < 0.05:
            return "Stable — declared and observed are well-aligned."
        elif kl < 0.10:
            return (
                f"Minor drift — observed '{observed_most}' slightly more than declared."
            )
        else:
            observed_prob = observed_dist[observed_most]
            declared_prob = declared_dist[declared_most]
            return (
                f"Significant drift — agent behaved as '{observed_most}'"
                f" ({observed_prob:.0%}) but profile declares '{declared_most}'"
                f" ({declared_prob:.0%})."
            )

    def apply_update(
        self,
        persona_name: str,
        proposal: NegotiationProposal,
        helios_dir: Path,
        accepted_dimensions: list[str] | None = None,
    ) -> ApplyUpdateResult:
        """Apply an accepted negotiation proposal to the persona's profile.

        Args:
            persona_name: Name of the persona to update.
            proposal: The NegotiationProposal to apply.
            helios_dir: Root helios directory (contains personas/).
            accepted_dimensions: If None, accept all proposed dimensions.
                Otherwise, only update the listed dimensions.

        Returns:
            Dict with status, updated_dimensions, and commit_message.
        """
        profile_path = helios_dir / "personas" / f"{persona_name}.yaml"
        profile = BehavioralProfile.load(profile_path)

        dims_to_update = (
            accepted_dimensions
            if accepted_dimensions is not None
            else list(proposal.proposed_distributions.keys())
        )

        updated: list[str] = []
        for dim in dims_to_update:
            if dim in proposal.proposed_distributions:
                new_dist = BehavioralDistribution(
                    dim, proposal.proposed_distributions[dim]
                )
                profile.distributions[dim] = new_dist
                updated.append(dim)

        profile.save(profile_path)

        obs_count = proposal.drift_result.observation_count
        n = len(updated)
        commit_message = (
            f"Behavioral evolution: {persona_name} — "
            f"{n} dimensions updated after {obs_count} observations"
        )

        subprocess.run(
            ["git", "-C", str(helios_dir), "add", str(profile_path)],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(helios_dir), "commit", "-m", commit_message],
            check=False,
            capture_output=True,
        )

        return {
            "status": "applied",
            "updated_dimensions": updated,
            "commit_message": commit_message,
        }

    def reject_update(
        self,
        persona_name: str,
        reason: str,
        helios_dir: Path,  # noqa: ARG002 - symmetry with apply_update
    ) -> RejectUpdateResult:
        """Reject a negotiation proposal and log the rejection.

        Args:
            persona_name: Name of the persona.
            reason: Human-provided reason for rejection.
            helios_dir: Root helios directory.

        Returns:
            Dict with status, persona, and reason.
        """
        return {
            "status": "rejected",
            "persona": persona_name,
            "reason": reason,
        }


def create_proposal_from_observer(
    persona_name: str,
    helios_dir: Path,
    observer: BehavioralObserver,
    drift_detector: DriftDetector,
) -> NegotiationProposal | None:
    """Convenience function: check drift and return a proposal if threshold exceeded.

    Args:
        persona_name: Name of the persona.
        helios_dir: Root helios directory.
        observer: The BehavioralObserver that has been accumulating observations.
        drift_detector: The DriftDetector to use for computing drift.

    Returns:
        NegotiationProposal if drift exceeds the threshold, else None.
    """
    observed_dists = observer.get_accumulated_distributions(persona_name)
    obs_count = observer.get_observation_count(persona_name)

    profile_path = helios_dir / "personas" / f"{persona_name}.yaml"
    declared_profile = BehavioralProfile.load(profile_path)

    drift_result = drift_detector.compute_drift(
        declared=declared_profile.distributions,
        observed=observed_dists,
        observation_count=obs_count,
    )

    if not drift_detector.exceeds_threshold(drift_result):
        return None

    engine = NegotiationEngine()
    return engine.generate_summary(
        persona_name=persona_name,
        declared_profile=declared_profile,
        observed_dists=observed_dists,
        drift_result=drift_result,
    )
