"""Behavioral probability distribution for Helios v2.

A BehavioralDistribution represents an agent's behavioral tendencies on one
dimension as a proper probability distribution over discrete named states.

Scientific foundation:
- KL-divergence: D_KL(P||Q) = sum_x P(x) * log(P(x) / Q(x))
  Measures information lost when Q is used to approximate P.
  Always >= 0; equals 0 iff P == Q.

- KL-minimizing blend of P (base) and Q (persona) with weight w:
  M(x) = w * P(x) + (1 - w) * Q(x)
  This weighted mixture IS the KL-minimizing convex combination
  (Proposition from mixture model theory).

- Entropy: H(P) = -sum_x P(x) * log(P(x))
  Measures behavioral uncertainty. High entropy = spread across many states.
  Low entropy = concentrated on one dominant behavior.
"""

from __future__ import annotations

import math
import random
from typing import Any

from .taxonomy import (
    list_states,
    validate_dimension,
    validate_state,
)

# Numerical stability constant for log(0) avoidance
_EPSILON: float = 1e-10
# Tolerance for distribution sum validation
_SUM_TOLERANCE: float = 1e-6


class BehavioralDistribution:
    """A probability distribution over the discrete states of one behavioral dimension.

    Represents an agent's behavioral tendency as a proper probability
    distribution — not a label, not a scalar, but a full distribution
    capturing the likelihood of each behavioral state.

    Attributes:
        dimension: The behavioral dimension this distribution describes.
        states: Ordered list of state names for this dimension.
        probs: Probability for each state (parallel to states, sums to 1.0).
    """

    def __init__(self, dimension: str, states_dict: dict[str, float]) -> None:
        """Create a BehavioralDistribution.

        Args:
            dimension: The behavioral dimension (must be in taxonomy).
            states_dict: Mapping from state name to probability. Must include
                all states for the dimension and sum to 1.0 within tolerance.

        Raises:
            ValueError: If dimension is unknown, states are invalid, or
                        probabilities do not form a valid distribution.
        """
        validate_dimension(dimension)
        self.dimension: str = dimension

        valid_states = list_states(dimension)

        # Validate all required states are present
        missing = set(valid_states) - set(states_dict.keys())
        if missing:
            raise ValueError(
                f"Distribution for '{dimension}' is missing states: {missing}. "
                f"All states must be specified: {valid_states}"
            )

        # Validate no extra states
        extra = set(states_dict.keys()) - set(valid_states)
        if extra:
            raise ValueError(
                f"Distribution for '{dimension}' has unknown states: {extra}. "
                f"Valid states: {valid_states}"
            )

        # Validate all probabilities are non-negative
        for state, prob in states_dict.items():
            if prob < 0.0:
                raise ValueError(
                    f"Probability for state '{state}' in dimension '{dimension}' "
                    f"is negative: {prob}. All probabilities must be >= 0."
                )

        # Validate sum to 1.0
        total = sum(states_dict.values())
        if abs(total - 1.0) > _SUM_TOLERANCE:
            raise ValueError(
                f"Probabilities for dimension '{dimension}' sum to {total:.8f}, "
                f"not 1.0 (tolerance: {_SUM_TOLERANCE}). Normalize before creating."
            )

        # Store in canonical taxonomy order for consistent operations
        self.states: list[str] = valid_states
        self.probs: list[float] = [states_dict[s] for s in valid_states]

    # ------------------------------------------------------------------
    # Core scientific operations
    # ------------------------------------------------------------------

    def kl_divergence(self, other: "BehavioralDistribution") -> float:
        """Compute KL-divergence D_KL(self || other).

        D_KL(P || Q) = sum_x P(x) * log(P(x) / Q(x))

        Measures information lost when other (Q) is used to approximate
        self (P). Result is always >= 0; equals 0 iff distributions are identical.

        In the context of drift detection:
        - self = observed distribution (what the agent actually does)
        - other = declared distribution (what the profile says it should do)
        - High KL = large drift from declared behavior

        Args:
            other: The distribution to compare against (Q in the formula).

        Returns:
            Non-negative float. 0.0 means identical distributions.

        Raises:
            ValueError: If distributions are for different dimensions.
        """
        self._assert_same_dimension(other)

        result = 0.0
        for p, q in zip(self.probs, other.probs):
            if p < _EPSILON:
                # P(x) = 0 contributes 0 to KL (limit of x*log(x) as x→0 is 0)
                continue
            # Avoid log(0) with epsilon floor on Q
            q_safe = max(q, _EPSILON)
            result += p * math.log(p / q_safe)

        return result

    def kl_blend(self, other: "BehavioralDistribution", weight: float) -> "BehavioralDistribution":
        """Compute the KL-divergence minimizing mixture of self and other.

        M(x) = weight * self(x) + (1 - weight) * other(x)

        This weighted mixture is the KL-minimizing convex combination
        over the set of all mixture distributions.

        In the inheritance context:
        - self = base (species-level) distribution
        - other = persona distribution
        - weight = inheritance weight (base_importance / specialization_level²)
        - High weight → result closer to base
        - Low weight → result closer to persona

        Args:
            other: The persona distribution to blend with.
            weight: Blend weight for self (base). Must be in [0.0, 1.0].
                   (1 - weight) is applied to other (persona).

        Returns:
            New BehavioralDistribution representing the merged profile.

        Raises:
            ValueError: If weight is out of range or dimensions differ.
        """
        if not 0.0 <= weight <= 1.0:
            raise ValueError(
                f"Blend weight must be in [0.0, 1.0], got {weight}"
            )
        self._assert_same_dimension(other)

        persona_weight = 1.0 - weight
        blended: dict[str, float] = {}

        for state, p_base, p_persona in zip(self.states, self.probs, other.probs):
            blended[state] = weight * p_base + persona_weight * p_persona

        # Renormalize to correct any floating point drift
        blended = _normalize(blended)

        return BehavioralDistribution(self.dimension, blended)

    def entropy(self) -> float:
        """Compute Shannon entropy H(P) = -sum_x P(x) * log(P(x)).

        Measures behavioral uncertainty / spread of this distribution.
        - Maximum entropy: uniform distribution (all states equally likely)
        - Minimum entropy (0): point mass on a single state (certain behavior)

        Returns:
            Non-negative float. Higher = more uncertain/diverse behavior.
        """
        result = 0.0
        for p in self.probs:
            if p > _EPSILON:
                result -= p * math.log(p)
        return result

    def max_entropy(self) -> float:
        """Return the maximum possible entropy for this dimension.

        Equal to log(n_states) — the entropy of the uniform distribution.

        Returns:
            Float representing maximum entropy for this dimension.
        """
        return math.log(len(self.states))

    def normalized_entropy(self) -> float:
        """Return entropy normalized to [0, 1] relative to maximum entropy.

        0.0 = maximally certain (point mass)
        1.0 = maximally uncertain (uniform)

        Returns:
            Float in [0.0, 1.0].
        """
        max_h = self.max_entropy()
        if max_h < _EPSILON:
            return 0.0
        return self.entropy() / max_h

    def most_likely(self) -> str:
        """Return the state with the highest probability.

        Used when rendering behavioral profiles into system prompt text —
        the dominant state drives the primary behavioral instruction.

        Returns:
            Name of the highest-probability state.
        """
        return self.states[self.probs.index(max(self.probs))]

    def sample(self) -> str:
        """Draw a state from this distribution using weighted random sampling.

        Useful for stochastic behavioral simulation and testing.

        Returns:
            A state name drawn proportional to its probability.
        """
        r = random.random()
        cumulative = 0.0
        for state, prob in zip(self.states, self.probs):
            cumulative += prob
            if r <= cumulative:
                return state
        return self.states[-1]  # fallback for floating point edge case

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, float]:
        """Serialize to a plain dict mapping state → probability.

        Returns:
            Dict suitable for YAML serialization.
        """
        return dict(zip(self.states, self.probs))

    @classmethod
    def from_dict(cls, dimension: str, data: dict[str, float]) -> "BehavioralDistribution":
        """Deserialize from a plain dict.

        Args:
            dimension: The behavioral dimension.
            data: Mapping from state name to probability.

        Returns:
            BehavioralDistribution instance.

        Raises:
            ValueError: If the data is invalid for this dimension.
        """
        return cls(dimension, data)

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def uniform(cls, dimension: str) -> "BehavioralDistribution":
        """Create a uniform (maximum entropy) distribution.

        Args:
            dimension: The behavioral dimension.

        Returns:
            Distribution with equal probability on all states.
        """
        states = list_states(dimension)
        prob = 1.0 / len(states)
        return cls(dimension, {s: prob for s in states})

    @classmethod
    def point_mass(cls, dimension: str, state: str) -> "BehavioralDistribution":
        """Create a point-mass distribution concentrated on one state.

        Args:
            dimension: The behavioral dimension.
            state: The state to place full probability mass on.

        Returns:
            Distribution with P(state)=1.0, P(others)=0.0.
        """
        validate_state(dimension, state)
        states = list_states(dimension)
        probs = {s: (1.0 if s == state else 0.0) for s in states}
        return cls(dimension, probs)

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BehavioralDistribution):
            return NotImplemented
        if self.dimension != other.dimension:
            return False
        return all(
            abs(a - b) < _SUM_TOLERANCE
            for a, b in zip(self.probs, other.probs)
        )

    def __repr__(self) -> str:
        top = self.most_likely()
        top_prob = max(self.probs)
        h = self.normalized_entropy()
        return (
            f"BehavioralDistribution({self.dimension!r}, "
            f"dominant={top!r}@{top_prob:.2f}, entropy={h:.2f})"
        )

    def __getitem__(self, state: str) -> float:
        """Get probability of a specific state.

        Args:
            state: State name.

        Returns:
            Probability of that state.

        Raises:
            KeyError: If state is not in this dimension.
        """
        try:
            idx = self.states.index(state)
            return self.probs[idx]
        except ValueError:
            raise KeyError(f"State '{state}' not in dimension '{self.dimension}'")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_same_dimension(self, other: "BehavioralDistribution") -> None:
        if self.dimension != other.dimension:
            raise ValueError(
                f"Cannot operate on distributions from different dimensions: "
                f"'{self.dimension}' vs '{other.dimension}'"
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _normalize(probs: dict[str, float]) -> dict[str, float]:
    """Normalize a probability dict to sum to exactly 1.0.

    Args:
        probs: Dict mapping state → raw probability (non-negative).

    Returns:
        Normalized dict summing to 1.0.

    Raises:
        ValueError: If all probabilities are zero.
    """
    total = sum(probs.values())
    if total < _EPSILON:
        raise ValueError("Cannot normalize: all probabilities are zero.")
    return {k: v / total for k, v in probs.items()}


def total_kl_divergence(
    observed: dict[str, "BehavioralDistribution"],
    declared: dict[str, "BehavioralDistribution"],
) -> float:
    """Compute total KL-divergence across all behavioral dimensions.

    Used by the drift detector to compute the overall divergence score
    between an observed behavioral fingerprint and a declared profile.

    D_total = sum over dimensions of D_KL(observed_dim || declared_dim)

    Args:
        observed: Dict mapping dimension → observed distribution.
        declared: Dict mapping dimension → declared distribution.

    Returns:
        Total KL-divergence across all shared dimensions.
    """
    total = 0.0
    for dimension in observed:
        if dimension in declared:
            total += observed[dimension].kl_divergence(declared[dimension])
    return total
