"""Drift detection for Helios v2.

Detects when observed behavioral distributions diverge from declared profiles.
Uses KL-divergence as the scientific measure of behavioral drift.

Drift thresholds (scientifically grounded):
- Total drift threshold: 0.30 (sum of KL across all 4 dimensions)
- Per-dimension threshold: 0.10 (flag individual dimension drift early)
- Minimum observations: 20 (prevents spurious drift signals from sparse data)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .distribution import BehavioralDistribution


# ---------------------------------------------------------------------------
# DriftResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class DriftResult:
    """Encapsulates the result of a single drift computation.

    Attributes:
        total_drift: Sum of KL-divergences across all dimensions.
        per_dimension: KL-divergence value keyed by dimension name.
        exceeds_total_threshold: True if total_drift >= TOTAL_THRESHOLD.
        dimensions_exceeding_threshold: Dimension names where KL >= PER_DIM_THRESHOLD.
        observation_count: Number of conversations observed for this computation.
        sufficient_observations: True if observation_count >= MIN_OBSERVATIONS.
        timestamp: ISO-8601 UTC timestamp of when this result was computed.
    """
    total_drift: float
    per_dimension: dict[str, float]
    exceeds_total_threshold: bool
    dimensions_exceeding_threshold: list[str]
    observation_count: int
    sufficient_observations: bool
    timestamp: str


# ---------------------------------------------------------------------------
# DriftDetector class
# ---------------------------------------------------------------------------

class DriftDetector:
    """Detects behavioral drift between declared and observed distributions."""

    TOTAL_THRESHOLD: float = 0.30
    PER_DIM_THRESHOLD: float = 0.10
    MIN_OBSERVATIONS: int = 20

    def __init__(self) -> None:
        self._history: dict[str, list[DriftResult]] = {}

    def per_dimension_drift(
        self,
        declared: dict[str, BehavioralDistribution],
        observed: dict[str, BehavioralDistribution],
    ) -> dict[str, float]:
        """Compute KL-divergence per behavioral dimension.

        D_KL(observed || declared) for each shared dimension.

        Args:
            declared: Declared behavioral distributions (the target profile).
            observed: Observed behavioral distributions (what actually happened).

        Returns:
            Dict mapping dimension name → KL-divergence value.
        """
        result: dict[str, float] = {}
        for dim in observed:
            if dim in declared:
                result[dim] = observed[dim].kl_divergence(declared[dim])
        return result

    def compute_drift(
        self,
        declared: dict[str, BehavioralDistribution],
        observed: dict[str, BehavioralDistribution],
        observation_count: int,
    ) -> DriftResult:
        """Compute a full drift assessment between declared and observed profiles.

        Args:
            declared: The declared behavioral distributions (the target profile).
            observed: The observed behavioral distributions (empirically extracted).
            observation_count: Number of conversations this observation covers.

        Returns:
            DriftResult with all computed fields populated.
        """
        per_dim = self.per_dimension_drift(declared, observed)
        total = sum(per_dim.values())
        sufficient = observation_count >= self.MIN_OBSERVATIONS
        exceeds_total = total >= self.TOTAL_THRESHOLD
        dims_exceeding = [
            dim for dim, kl in per_dim.items()
            if kl >= self.PER_DIM_THRESHOLD
        ]
        timestamp = datetime.now(timezone.utc).isoformat()

        return DriftResult(
            total_drift=total,
            per_dimension=per_dim,
            exceeds_total_threshold=exceeds_total,
            dimensions_exceeding_threshold=dims_exceeding,
            observation_count=observation_count,
            sufficient_observations=sufficient,
            timestamp=timestamp,
        )

    def exceeds_threshold(self, result: DriftResult) -> bool:
        """Return True if drift is actionable.

        Drift is only considered actionable when there are sufficient
        observations AND the total drift exceeds the threshold. This prevents
        spurious alerts from sparse data.

        Args:
            result: A previously computed DriftResult.

        Returns:
            True if sufficient_observations AND exceeds_total_threshold.
        """
        return result.sufficient_observations and result.exceeds_total_threshold

    def record(self, persona_name: str, result: DriftResult) -> None:
        """Append a DriftResult to the history for a persona.

        Args:
            persona_name: Name of the persona.
            result: The drift result to record.
        """
        if persona_name not in self._history:
            self._history[persona_name] = []
        self._history[persona_name].append(result)

    def get_history(self, persona_name: str) -> list[DriftResult]:
        """Return all recorded drift results for a persona.

        Args:
            persona_name: Name of the persona.

        Returns:
            List of DriftResult in recording order. Empty list if none.
        """
        return list(self._history.get(persona_name, []))

    def get_trend(self, persona_name: str) -> str:
        """Characterize the drift trend for a persona based on recent history.

        Uses the last 3 recorded drift results to determine whether drift
        is stable, increasing (drifting), or decreasing (stabilizing).

        Args:
            persona_name: Name of the persona.

        Returns:
            "stable" | "drifting" | "stabilizing"
            Returns "stable" if fewer than 2 recorded results exist.
        """
        history = self._history.get(persona_name, [])
        if len(history) < 2:
            return "stable"

        recent = history[-3:]  # up to last 3 entries
        drifts = [r.total_drift for r in recent]

        if len(drifts) < 2:
            return "stable"

        # Compare first and last in the window
        if drifts[-1] > drifts[0]:
            return "drifting"
        elif drifts[-1] < drifts[0]:
            return "stabilizing"
        else:
            return "stable"
