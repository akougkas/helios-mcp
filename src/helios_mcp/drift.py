"""Drift detection: Dirichlet posterior over each dimension, scored by JS divergence.

For one dimension with declared distribution ``q`` (the resolved profile) and
evidence counts ``c`` (soft label mass accumulated from observed turns), the
posterior is ``Dirichlet(alpha)`` with ``alpha = s * q + c``. The prior strength
``s`` is how many turns' worth of evidence the declared profile is worth.

Two numbers describe drift on that dimension:

- ``divergence`` is ``JS(mean, q)`` with natural log, so it lies in [0, ln 2].
  JS stays finite when a state has zero mass on one side, unlike KL, which is
  what made the old score explode on unseen states.
- ``credibility`` is ``P(JS(p, q) > tau)`` for ``p ~ Dirichlet(alpha)``,
  estimated by seeded sampling. It is the posterior probability that the true
  behavior differs from the declared profile by more than ``tau``. With little
  evidence the posterior is wide but centered on ``q``, so this stays below the
  level until the counts actually pull the mean away. That replaces the fixed
  minimum-observation count.

A dimension is *drifted* when credibility reaches ``credibility_level``. A
dimension qualifies for *auto-accept* when the posterior is confidently close
to ``q`` (``P(JS < auto_accept_js) >= auto_accept_level``) yet has moved by a
measurable amount, so a silent update is both safe and non-trivial. The update
target in either case is the posterior mean.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .taxonomy import list_states

LN2 = math.log(2.0)


@dataclass(frozen=True)
class DriftConfig:
    """Every threshold the drift math uses, in one place so calibration can sweep it."""

    prior_strength: float = 20.0
    js_threshold: float = 0.02
    credibility_level: float = 0.95
    auto_accept_js: float = 0.01
    auto_accept_level: float = 0.9
    auto_accept_min_change: float = 0.0005
    rejection_strength: float = 10.0
    samples: int = 1000
    seed: int = 0
    min_prob: float = 0.005


DEFAULT_CONFIG = DriftConfig()


def js_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    """Jensen-Shannon divergence in nats. Symmetric, bounded by ln 2."""
    total = 0.0
    for pi, qi in zip(p, q, strict=True):
        # Written as logs of the sum rather than of the midpoint so a subnormal
        # probability cannot underflow the midpoint to zero.
        log_sum = math.log(pi + qi) if pi + qi > 0.0 else 0.0
        if pi > 0.0:
            total += 0.5 * pi * (LN2 + math.log(pi) - log_sum)
        if qi > 0.0:
            total += 0.5 * qi * (LN2 + math.log(qi) - log_sum)
    return min(LN2, max(0.0, total))


def smooth(probs: Sequence[float], floor: float) -> list[float]:
    """Lift every state to at least ``floor`` and renormalize.

    Profiles written to disk and priors fed to the Dirichlet must give every
    state positive mass: a zero prior makes ``alpha`` invalid, and a near-zero
    declared state turns any later observation of it into an outsized signal.
    """
    lifted = [max(p, floor) for p in probs]
    total = sum(lifted)
    return [p / total for p in lifted]


def sample_dirichlet(alpha: Sequence[float], rng: random.Random) -> list[float]:
    draws = [rng.gammavariate(a, 1.0) for a in alpha]
    total = sum(draws)
    if total <= 0.0:
        # Every draw underflowed, which only happens for tiny alphas; fall back
        # to the mean rather than divide by zero.
        s = sum(alpha)
        return [a / s for a in alpha]
    return [d / total for d in draws]


@dataclass(frozen=True)
class DimensionDrift:
    dimension: str
    declared: dict[str, float]
    posterior_mean: dict[str, float]
    evidence: float
    divergence: float
    credibility: float
    closeness: float
    drifted: bool
    auto_accept: bool


@dataclass(frozen=True)
class DriftAssessment:
    dimensions: dict[str, DimensionDrift] = field(default_factory=dict)

    @property
    def drifted_dimensions(self) -> list[str]:
        return [d for d, r in self.dimensions.items() if r.drifted]

    @property
    def auto_accept_dimensions(self) -> list[str]:
        return [d for d, r in self.dimensions.items() if r.auto_accept]

    @property
    def total_divergence(self) -> float:
        return sum(r.divergence for r in self.dimensions.values())

    @property
    def proposal_recommended(self) -> bool:
        return bool(self.drifted_dimensions)


def assess_dimension(
    dimension: str,
    declared: Mapping[str, float],
    counts: Mapping[str, float],
    config: DriftConfig = DEFAULT_CONFIG,
) -> DimensionDrift:
    """Posterior drift for one dimension. ``counts`` may omit states."""
    states = list_states(dimension)
    q = smooth([declared.get(s, 0.0) for s in states], config.min_prob)
    c = [max(0.0, counts.get(s, 0.0)) for s in states]
    alpha = [config.prior_strength * qi + ci for qi, ci in zip(q, c, strict=True)]
    concentration = sum(alpha)
    mean = [a / concentration for a in alpha]

    rng = random.Random(f"{config.seed}:{dimension}")
    above = below = 0
    for _ in range(config.samples):
        js = js_divergence(sample_dirichlet(alpha, rng), q)
        above += js > config.js_threshold
        below += js < config.auto_accept_js
    credibility = above / config.samples
    closeness = below / config.samples
    divergence = js_divergence(mean, q)

    drifted = credibility >= config.credibility_level
    auto_accept = (
        not drifted
        and closeness >= config.auto_accept_level
        and divergence >= config.auto_accept_min_change
    )
    return DimensionDrift(
        dimension=dimension,
        declared=dict(zip(states, q, strict=True)),
        posterior_mean=dict(zip(states, mean, strict=True)),
        evidence=sum(c),
        divergence=divergence,
        credibility=credibility,
        closeness=closeness,
        drifted=drifted,
        auto_accept=auto_accept,
    )


def assess(
    declared: Mapping[str, Mapping[str, float]],
    counts: Mapping[str, Mapping[str, float]],
    config: DriftConfig = DEFAULT_CONFIG,
) -> DriftAssessment:
    """Assess every declared dimension. Dimensions without counts get none."""
    return DriftAssessment({
        dim: assess_dimension(dim, dist, counts.get(dim, {}), config)
        for dim, dist in declared.items()
    })


# Legacy KL detector. Removed once server, cli and harness move to assess().
from datetime import UTC, datetime  # noqa: E402

from .distribution import BehavioralDistribution  # noqa: E402


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
    AUTO_ACCEPT_THRESHOLD: float = 0.05

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
        timestamp = datetime.now(UTC).isoformat()

        return DriftResult(
            total_drift=total,
            per_dimension=per_dim,
            exceeds_total_threshold=exceeds_total,
            dimensions_exceeding_threshold=dims_exceeding,
            observation_count=observation_count,
            sufficient_observations=sufficient,
            timestamp=timestamp,
        )

    def should_auto_accept(self, result: DriftResult) -> bool:
        """Return True if drift is small enough to auto-accept silently.

        Per-dimension KL < AUTO_ACCEPT_THRESHOLD means the observed behavior
        is close enough to the declared profile that updating it silently
        is safe. Requires sufficient observations to prevent premature
        auto-acceptance from sparse data.

        Args:
            result: A previously computed DriftResult.

        Returns:
            True if all per-dimension KL values are below the auto-accept
            threshold and there are sufficient observations.
        """
        if not result.sufficient_observations:
            return False
        return all(
            kl < self.AUTO_ACCEPT_THRESHOLD
            for kl in result.per_dimension.values()
        )

    def auto_accept_dimensions(self, result: DriftResult) -> list[str]:
        """Return dimension names where drift is small enough to auto-accept.

        Unlike should_auto_accept() which requires ALL dimensions to be below
        threshold, this returns the specific dimensions that qualify. Useful
        for partial auto-accept where some dimensions evolve silently while
        others require negotiation.

        Args:
            result: A previously computed DriftResult.

        Returns:
            List of dimension names with KL < AUTO_ACCEPT_THRESHOLD.
        """
        if not result.sufficient_observations:
            return []
        return [
            dim for dim, kl in result.per_dimension.items()
            if kl < self.AUTO_ACCEPT_THRESHOLD
        ]

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
