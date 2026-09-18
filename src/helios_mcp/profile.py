"""Behavioral profile — a complete v2 behavioral identity across all 4 dimensions."""
from __future__ import annotations

import copy
import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .atomic_ops import atomic_write_yaml
from .distribution import BehavioralDistribution
from .drift import DEFAULT_CONFIG, smooth
from .taxonomy import list_dimensions

SCHEMA_VERSION = "2.0"


_PARSED: dict[str, tuple[tuple[int, int, int], dict[str, Any]]] = {}


@dataclass
class BehavioralProfile:
    """A behavioral identity: one distribution per dimension it declares.

    A level in the hierarchy may declare only some dimensions; the rest pass
    through from its parent unchanged. ``inherit_weight``, when set, replaces
    the ``base_importance / specialization_level**2`` formula for this level's
    blend with its parent; ``0.0`` makes the level authoritative for every
    dimension it declares.
    """

    agent_id: str
    level: str  # "species" | "domain" | "user" | "session"
    distributions: dict[str, BehavioralDistribution]
    parent_id: str | None = None
    specialization_level: int = 1
    base_importance: float = 0.7
    description: str = ""
    observation_count: int = 0
    last_negotiation: str | None = None
    created: str = field(default_factory=lambda: datetime.date.today().isoformat())
    schema_version: str = SCHEMA_VERSION
    inherit_weight: float | None = None

    @classmethod
    def default_species(cls) -> BehavioralProfile:
        """The packaged species-level base profile, covering every dimension."""
        return cls.load(Path(__file__).parent / "default_profiles" / "identity.yaml")

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialize to a YAML-serializable dict."""
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "level": self.level,
            "base_importance": self.base_importance,
            "specialization_level": self.specialization_level,
            "description": self.description,
            "observation_count": self.observation_count,
            "created": self.created,
            "behavioral_distributions": {
                dim: dist.to_dict()
                for dim, dist in self.distributions.items()
            },
        }
        if self.parent_id:
            d["parent_id"] = self.parent_id
        if self.last_negotiation:
            d["last_negotiation"] = self.last_negotiation
        if self.inherit_weight is not None:
            d["inherit_weight"] = self.inherit_weight
        return d

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> BehavioralProfile:
        """Deserialize from a loaded YAML dict."""
        raw_dists = data.get("behavioral_distributions", {})
        distributions = {
            dim: BehavioralDistribution.from_dict(dim, raw_dists[dim])
            for dim in list_dimensions()
            if dim in raw_dists
        }
        weight = data.get("inherit_weight")
        return cls(
            agent_id=data.get("agent_id", "unknown"),
            level=data.get("level", "domain"),
            distributions=distributions,
            parent_id=data.get("parent_id"),
            specialization_level=int(data.get("specialization_level", 1)),
            base_importance=float(data.get("base_importance", 0.7)),
            description=data.get("description", ""),
            observation_count=int(data.get("observation_count", 0)),
            last_negotiation=data.get("last_negotiation"),
            created=data.get("created", datetime.date.today().isoformat()),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            inherit_weight=None if weight is None else float(weight),
        )

    @classmethod
    def load(cls, path: Path) -> BehavioralProfile:
        """Load a BehavioralProfile from a YAML file.

        Every tool call resolves the hierarchy, and YAML parsing dominated it,
        so parsed files are cached by identity and mtime. Each call still
        builds a fresh profile, because callers mutate what they load.
        """
        st = os.stat(path)
        stamp = (st.st_ino, st.st_size, st.st_mtime_ns)
        key = str(Path(path).resolve())
        cached = _PARSED.get(key)
        if cached is None or cached[0] != stamp:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _PARSED[key] = cached = (stamp, data)
        return cls.from_yaml_dict(copy.deepcopy(cached[1]))

    def save(self, path: Path) -> None:
        """Atomically write this profile as YAML.

        Every distribution is smoothed to the probability floor first, so no
        state on disk is degenerate. Smoothing is a no-op for distributions
        already at or above the floor.
        """
        for dim, dist in list(self.distributions.items()):
            lifted = smooth(dist.probs, DEFAULT_CONFIG.min_prob)
            self.distributions[dim] = BehavioralDistribution(
                dim, dict(zip(dist.states, lifted, strict=True))
            )
        atomic_write_yaml(path, self.to_yaml_dict())
