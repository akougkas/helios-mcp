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
    """Every threshold the drift math uses, in one place so calibration can sweep it.

    Defaults come from simulating hard labels drawn from the four default
    profiles, evaluating after every turn: stationary behavior proposes on any
    dimension in under 1% of 200-turn runs (under 0.3% within the first 30
    turns), and a 0.3-mass shift is detected at a median of 26 to 30 turns
    (80th percentile 38 to 44, depending on which states the mass moves
    between). ``auto_accept_js`` equals ``js_threshold`` so a real shift
    below the proposal threshold is eventually absorbed silently instead of
    sitting in a dead zone; ``auto_accept_min_change`` keeps stationary noise to
    about one silent update per dimension per 800 turns.
    """

    prior_strength: float = 25.0
    js_threshold: float = 0.0125
    credibility_level: float = 0.95
    auto_accept_js: float = 0.0125
    auto_accept_level: float = 0.9
    auto_accept_min_change: float = 0.004
    rejection_strength: float = 10.0
    standing_hint_weight: float = 1.0
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

