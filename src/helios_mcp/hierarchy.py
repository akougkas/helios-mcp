"""4-level identity hierarchy for Helios v2.

Hierarchy levels (outermost to most specific):
  species  -> base identity applying to all agents
  domain   -> task-type persona (developer, researcher, writer)
  user     -> person-specific adaptation
  session  -> temporary context override

Each level inherits from its parent using KL-divergence minimizing blend.
Missing levels are gracefully skipped (use parent's resolved profile).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .profile import BehavioralProfile
from .distribution import BehavioralDistribution
from .taxonomy import list_dimensions

logger = logging.getLogger(__name__)

_MIN_WEIGHT: float = 0.01
_MAX_WEIGHT: float = 1.0


class IdentityHierarchy:
    """Resolves a fully blended BehavioralProfile by walking the 4-level chain."""

    def __init__(self, helios_dir: Path) -> None:
        self.helios_dir = helios_dir
        self.base_path = helios_dir / "base"
        self.personas_path = helios_dir / "personas"
        self.temporary_path = helios_dir / "temporary"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, persona_name: str) -> BehavioralProfile:
        """Load and blend the full inheritance chain for a persona.

        Chain:
          1. species  (base/identity.yaml)           — always required
          2. domain   (personas/{persona_name}.yaml) — blended if present
          3. user     (personas/{persona_name}_user.yaml) — blended if present
          4. session  (temporary/{persona_name}.yaml) — blended if present

        Returns the final merged BehavioralProfile.
        """
        # Level 1: species — always required
        species_path = self.base_path / "identity.yaml"
        species = self._load_level(species_path)
        if species is None:
            logger.warning("Species profile missing — using default_species() fallback")
            species = BehavioralProfile.default_species()

        resolved = species

        # Level 2: domain persona
        domain_path = self.personas_path / f"{persona_name}.yaml"
        domain = self._load_level(domain_path)
        if domain is not None:
            resolved = self._blend_profiles(resolved, domain)
        else:
            logger.debug(f"No domain persona found for '{persona_name}' — using species only")

        # Level 3: user adaptation
        user_path = self.personas_path / f"{persona_name}_user.yaml"
        user = self._load_level(user_path)
        if user is not None:
            resolved = self._blend_profiles(resolved, user)

        # Level 4: session override
        session_path = self.temporary_path / f"{persona_name}.yaml"
        session = self._load_level(session_path)
        if session is not None:
            resolved = self._blend_profiles(resolved, session)

        return resolved

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_level(self, path: Path) -> Optional[BehavioralProfile]:
        """Load a BehavioralProfile from a YAML file, returning None if missing."""
        if not path.exists():
            return None
        try:
            return BehavioralProfile.load(path)
        except Exception as exc:
            logger.warning(f"Failed to load profile from {path}: {exc}")
            return None

    def _blend_profiles(
        self,
        parent: BehavioralProfile,
        child: BehavioralProfile,
    ) -> BehavioralProfile:
        """Blend parent and child profiles using KL-divergence minimizing mixture.

        weight = parent.base_importance / (child.specialization_level ** 2)
        Clamped to [0.01, 1.0].

        High weight -> result closer to parent (strong inheritance).
        Low weight  -> result closer to child (high specialization).
        """
        raw_weight = parent.base_importance / (child.specialization_level ** 2)
        weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, raw_weight))

        logger.debug(
            f"Blending '{parent.agent_id}' + '{child.agent_id}': "
            f"raw_weight={raw_weight:.4f}, clamped={weight:.4f}"
        )

        blended_dists: dict[str, BehavioralDistribution] = {}
        for dim in list_dimensions():
            parent_dist = parent.distributions.get(dim, BehavioralDistribution.uniform(dim))
            child_dist = child.distributions.get(dim, BehavioralDistribution.uniform(dim))
            blended_dists[dim] = parent_dist.kl_blend(child_dist, weight)

        return BehavioralProfile(
            agent_id=child.agent_id,
            level=child.level,
            distributions=blended_dists,
            parent_id=parent.agent_id,
            specialization_level=child.specialization_level,
            base_importance=child.base_importance,
            description=child.description,
            observation_count=child.observation_count,
            last_negotiation=child.last_negotiation,
            created=child.created,
            schema_version=child.schema_version,
        )
