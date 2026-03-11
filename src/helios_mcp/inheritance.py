"""KL-divergence based profile blending for Helios v2.

The core inheritance formula:
    weight = base_importance / (specialization_level ** 2)

Applied to probability distributions via KL-minimizing mixture:
    M(x) = weight * P_base(x) + (1 - weight) * P_persona(x)
"""

from __future__ import annotations

from typing import Any


def kl_blend_profiles(
    base_profile: Any,
    persona_profile: Any,
) -> Any:
    """Blend two BehavioralProfiles using KL-divergence minimizing mixture.

    weight = base_importance / (specialization_level ** 2), clamped to [0.01, 1.0]

    Args:
        base_profile: A BehavioralProfile acting as the parent/base.
        persona_profile: A BehavioralProfile acting as the child/persona.

    Returns:
        A new BehavioralProfile representing the blended identity.
    """
    from .profile import BehavioralProfile
    from .distribution import BehavioralDistribution
    from .taxonomy import list_dimensions

    _MIN_WEIGHT = 0.01
    _MAX_WEIGHT = 1.0

    raw_weight = base_profile.base_importance / (persona_profile.specialization_level ** 2)
    weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, raw_weight))

    blended_dists: dict[str, BehavioralDistribution] = {}
    for dim in list_dimensions():
        base_dist = base_profile.distributions.get(dim, BehavioralDistribution.uniform(dim))
        persona_dist = persona_profile.distributions.get(dim, BehavioralDistribution.uniform(dim))
        blended_dists[dim] = base_dist.kl_blend(persona_dist, weight)

    return BehavioralProfile(
        agent_id=persona_profile.agent_id,
        level=persona_profile.level,
        distributions=blended_dists,
        parent_id=base_profile.agent_id,
        specialization_level=persona_profile.specialization_level,
        base_importance=persona_profile.base_importance,
        description=persona_profile.description,
        observation_count=persona_profile.observation_count,
        last_negotiation=persona_profile.last_negotiation,
        created=persona_profile.created,
        schema_version=persona_profile.schema_version,
    )
