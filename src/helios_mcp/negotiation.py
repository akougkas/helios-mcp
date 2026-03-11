"""Negotiation engine for Helios v2.

When behavioral drift crosses the threshold, the NegotiationEngine:
1. Generates a natural language summary of what changed and why it matters
2. Proposes a specific profile update (the observed distributions as the new declared)
3. Applies accepted changes with a semantic git commit
4. Rejects and logs if the human says no

The negotiation is always human-in-the-loop. Helios proposes, the human decides.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .distribution import BehavioralDistribution
from .drift import DriftDetector, DriftResult
from .observer import BehavioralObserver
from .profile import BehavioralProfile
from .taxonomy import DIMENSION_DESCRIPTIONS, list_dimensions


# ---------------------------------------------------------------------------
# NegotiationProposal dataclass
# ---------------------------------------------------------------------------


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
            f"Your '{persona_name}' behavioral profile has drifted from its declared state.",
            (
                f"Over {obs_count} observed interactions, your agent's actual behavior"
                f" diverged significantly from its profile (drift score: {total_drift:.2f},"
                f" threshold: 0.30)."
            ),
            "",
            "The most significant changes:",
        ]

        if dims_exceeding:
            for dim in dims_exceeding:
                dim_desc = DIMENSION_DESCRIPTIONS.get(dim, dim)
                declared_dist = declared_profile.distributions.get(dim)
                observed_dist = observed_dists.get(dim)
                declared_most = declared_dist.most_likely() if declared_dist else "unknown"
                observed_most = observed_dist.most_likely() if observed_dist else "unknown"
                lines.append(
                    f"- {dim_desc}: the agent was observed behaving as"
                    f" '{observed_most}' more than its declared '{declared_most}'"
                    f" profile suggests."
                )
        else:
            lines.append(
                "  Multiple dimensions show moderate drift that together exceed the threshold."
            )

        lines.extend([
            "",
            "Do you want to update the declared profile to match observed behavior?",
            "Accepting this update will commit the changes to your behavioral biography.",
        ])

        summary = "\n".join(lines)

        # Build proposed distributions dict
        proposed_distributions: dict[str, dict[str, float]] = {
            dim: dist.to_dict()
            for dim, dist in observed_dists.items()
        }

        proposed_at = datetime.now(timezone.utc).isoformat()

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
        dim: str,
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
        accepted_dimensions: Optional[list[str]] = None,
    ) -> dict:
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
                new_dist = BehavioralDistribution(dim, proposal.proposed_distributions[dim])
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
        helios_dir: Path,
    ) -> dict:
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
) -> Optional[NegotiationProposal]:
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
