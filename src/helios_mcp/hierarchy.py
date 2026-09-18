"""4-level identity hierarchy for Helios v2.

Hierarchy levels (outermost to most specific):
  species  -> base identity applying to all agents
  domain   -> task-type persona (developer, researcher, writer)
  user     -> person-specific adaptation
  session  -> temporary context override

Each level blends with its parent as a mixture. Missing levels are skipped,
and dimensions a level does not declare pass through from its parent.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .distribution import BehavioralDistribution
from .profile import BehavioralProfile
from .security import validate_persona_name
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

    def resolve(
        self, persona_name: str, include_session: bool = True
    ) -> BehavioralProfile:
        """Load and blend the full inheritance chain for a persona.

        Chain:
          1. species  (base/identity.yaml)           — always required
          2. domain   (personas/{persona_name}.yaml) — blended if present
          3. user     (personas/{persona_name}_user.yaml) — blended if present
          4. session  (temporary/{persona_name}.yaml) — blended if present

        Returns the final merged BehavioralProfile. Negotiation passes
        ``include_session=False``: a temporary session override is not the
        baseline that long-term learning should be judged against.
        """
        validate_persona_name(persona_name)
        # Level 1: species — always required
        species_path = self.base_path / "identity.yaml"
        species = self._load_level(species_path)
        default = BehavioralProfile.default_species()
        if species is None:
            logger.warning("Species profile missing, using the built-in default")
            species = default
        for dim, dist in default.distributions.items():
            species.distributions.setdefault(dim, dist)

        resolved = species

        # Level 2: domain persona
        domain_path = self.personas_path / f"{persona_name}.yaml"
        domain = self._load_level(domain_path)
        if domain is not None:
            resolved = self._blend_profiles(resolved, domain)
        else:
            logger.debug(
                f"No domain persona found for '{persona_name}' — using species only"
            )

        # Level 3: user adaptation
        user_path = self.personas_path / f"{persona_name}_user.yaml"
        user = self._load_level(user_path)
        if user is not None:
            resolved = self._blend_profiles(resolved, user)

        # Level 4: session override
        session_path = self.temporary_path / f"{persona_name}.yaml"
        session = self._load_level(session_path) if include_session else None
        if session is not None:
            resolved = self._blend_profiles(resolved, session)

        return resolved

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_level(self, path: Path) -> BehavioralProfile | None:
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
        """Blend ``child`` over ``parent`` as ``w * parent + (1 - w) * child``.

        ``w`` is the child's ``inherit_weight`` when set, otherwise
        ``parent.base_importance / child.specialization_level**2`` clamped to
        [0.01, 1.0]. High weight keeps the result close to the parent.
        """
        if child.inherit_weight is not None:
            raw_weight = weight = max(0.0, min(_MAX_WEIGHT, child.inherit_weight))
        else:
            raw_weight = parent.base_importance / (child.specialization_level ** 2)
            weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, raw_weight))

        logger.debug(
            f"Blending '{parent.agent_id}' + '{child.agent_id}': "
            f"raw_weight={raw_weight:.4f}, clamped={weight:.4f}"
        )

        blended_dists: dict[str, BehavioralDistribution] = {}
        for dim in list_dimensions():
            parent_dist = parent.distributions[dim]
            child_dist = child.distributions.get(dim)
            blended_dists[dim] = (
                parent_dist if child_dist is None
                else parent_dist.kl_blend(child_dist, weight)
            )

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
