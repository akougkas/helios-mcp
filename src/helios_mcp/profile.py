"""Behavioral profile — a complete v2 behavioral identity across all 4 dimensions."""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .distribution import BehavioralDistribution
from .taxonomy import list_dimensions

SCHEMA_VERSION = "2.0"


@dataclass
class BehavioralProfile:
    """A complete behavioral identity: one distribution per dimension."""

    agent_id: str
    level: str  # "species" | "domain" | "user" | "session"
    distributions: dict[str, BehavioralDistribution]
    parent_id: Optional[str] = None
    specialization_level: int = 1
    base_importance: float = 0.7
    description: str = ""
    observation_count: int = 0
    last_negotiation: Optional[str] = None
    created: str = field(default_factory=lambda: datetime.date.today().isoformat())
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def default_species(cls) -> "BehavioralProfile":
        """Balanced species-level base profile."""
        return cls(
            agent_id="base",
            level="species",
            distributions={
                "epistemic_style": BehavioralDistribution("epistemic_style", {
                    "confident": 0.45,
                    "hedging": 0.25,
                    "admits_ignorance": 0.20,
                    "speculating": 0.10,
                }),
                "interaction_agency": BehavioralDistribution("interaction_agency", {
                    "asks_first": 0.35,
                    "assumes_and_acts": 0.20,
                    "offers_options": 0.30,
                    "decides_unilaterally": 0.05,
                    "defers_to_user": 0.10,
                }),
                "communication_register": BehavioralDistribution("communication_register", {
                    "terse": 0.20,
                    "moderate": 0.45,
                    "thorough": 0.20,
                    "technical_dense": 0.10,
                    "plain_accessible": 0.05,
                }),
                "risk_caution": BehavioralDistribution("risk_caution", {
                    "acts_immediately": 0.15,
                    "checks_before_acting": 0.45,
                    "warns_frequently": 0.30,
                    "refuses_ambiguity": 0.10,
                }),
            },
            base_importance=0.7,
            specialization_level=1,
            description="Species-level base behavioral profile for all agents",
        )

    def to_yaml_dict(self) -> dict:
        """Serialize to a YAML-serializable dict."""
        d: dict = {
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
        return d

    @classmethod
    def from_yaml_dict(cls, data: dict) -> "BehavioralProfile":
        """Deserialize from a loaded YAML dict."""
        raw_dists = data.get("behavioral_distributions", {})
        distributions: dict[str, BehavioralDistribution] = {}
        for dim in list_dimensions():
            if dim in raw_dists:
                distributions[dim] = BehavioralDistribution.from_dict(dim, raw_dists[dim])
            else:
                distributions[dim] = BehavioralDistribution.uniform(dim)
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
        )

    @classmethod
    def load(cls, path: Path) -> "BehavioralProfile":
        """Load a BehavioralProfile from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_yaml_dict(data)

    def save(self, path: Path) -> None:
        """Atomically save this profile to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.dump(self.to_yaml_dict(), f, default_flow_style=False, allow_unicode=True)
        os.replace(tmp, path)
