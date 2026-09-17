"""Regression tests for bootstrap wiring to the v2 taxonomy schema.

`BootstrapManager.bootstrap_installation()` must install the v2 default
profiles (species-level `base/identity.yaml` plus the `developer`,
`researcher`, and `writer` domain personas from `default_profiles/`) — not
the old non-v2-schema base config. These tests prove:

1. A fresh bootstrap creates a v2-schema identity.yaml plus the domain
   personas.
2. The created identity.yaml actually loads through the real
   profile/hierarchy loader and yields valid probability distributions
   over all four taxonomy dimensions.
3. A second bootstrap over the same directory is idempotent and does not
   clobber a user's existing edits.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from helios_mcp.bootstrap import BootstrapManager
from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.hierarchy import IdentityHierarchy
from helios_mcp.profile import BehavioralProfile
from helios_mcp.taxonomy import list_dimensions

_DOMAIN_PERSONAS = ("developer", "researcher", "writer")


def _bootstrap(helios_dir: Path) -> BootstrapManager:
    """Bootstrap a fresh installation without touching git."""
    manager = BootstrapManager(helios_dir, git_enabled=False)
    manager.bootstrap_installation()
    return manager


def test_fresh_bootstrap_creates_v2_identity_and_domain_personas(
    tmp_path: Path,
) -> None:
    """A fresh install must write the v2-schema identity.yaml and personas."""
    helios_dir = tmp_path / ".helios"

    _bootstrap(helios_dir)

    identity_file = helios_dir / "base" / "identity.yaml"
    assert identity_file.exists(), "base/identity.yaml was not created"

    identity_data = yaml.safe_load(identity_file.read_text(encoding="utf-8"))
    assert identity_data["schema_version"] == "2.0"
    assert identity_data["agent_id"] == "base"
    assert identity_data["level"] == "species"
    assert "behavioral_distributions" in identity_data
    assert set(identity_data["behavioral_distributions"]) == set(list_dimensions())

    personas_dir = helios_dir / "personas"
    assert personas_dir.exists()

    for name in _DOMAIN_PERSONAS:
        persona_file = personas_dir / f"{name}.yaml"
        assert persona_file.exists(), f"personas/{name}.yaml was not created"

        persona_data = yaml.safe_load(persona_file.read_text(encoding="utf-8"))
        assert persona_data["schema_version"] == "2.0"
        assert persona_data["agent_id"] == name
        assert persona_data["level"] == "domain"
        assert set(persona_data["behavioral_distributions"]) == set(list_dimensions())


def test_fresh_bootstrap_identity_loads_valid_distributions(tmp_path: Path) -> None:
    """The bootstrapped identity/persona files must load through the real
    profile and hierarchy loaders and yield valid distributions over all
    four taxonomy dimensions."""
    helios_dir = tmp_path / ".helios"

    _bootstrap(helios_dir)

    # Loading the raw species profile directly through BehavioralProfile.
    identity_file = helios_dir / "base" / "identity.yaml"
    species_profile = BehavioralProfile.load(identity_file)
    assert set(species_profile.distributions) == set(list_dimensions())
    for dim, dist in species_profile.distributions.items():
        assert isinstance(dist, BehavioralDistribution)
        assert dist.dimension == dim
        assert abs(sum(dist.probs) - 1.0) < 1e-6

    # Resolving through the real 4-level hierarchy for each domain persona.
    hierarchy = IdentityHierarchy(helios_dir)
    for name in _DOMAIN_PERSONAS:
        resolved = hierarchy.resolve(name)
        assert set(resolved.distributions) == set(list_dimensions())
        for dim, dist in resolved.distributions.items():
            assert isinstance(dist, BehavioralDistribution)
            assert abs(sum(dist.probs) - 1.0) < 1e-6

    # A persona with no domain file must still resolve via species fallback.
    fallback = hierarchy.resolve("does-not-exist")
    assert set(fallback.distributions) == set(list_dimensions())
    for dist in fallback.distributions.values():
        assert abs(sum(dist.probs) - 1.0) < 1e-6


def test_second_bootstrap_is_idempotent_and_preserves_user_edits(
    tmp_path: Path,
) -> None:
    """Bootstrapping twice over the same directory must not clobber
    existing (possibly user-edited) v2 profiles."""
    helios_dir = tmp_path / ".helios"

    _bootstrap(helios_dir)

    identity_file = helios_dir / "base" / "identity.yaml"
    developer_file = helios_dir / "personas" / "developer.yaml"

    # Simulate a user edit: keep the v2 schema marker (so it is recognized
    # as an existing v2 profile) but change values a fresh install would
    # never produce.
    identity_data = yaml.safe_load(identity_file.read_text(encoding="utf-8"))
    identity_data["description"] = "USER EDITED SPECIES PROFILE"
    identity_data["behavioral_distributions"]["epistemic_style"] = {
        "confident": 1.0,
        "hedging": 0.0,
        "admits_ignorance": 0.0,
        "speculating": 0.0,
    }
    identity_file.write_text(yaml.safe_dump(identity_data), encoding="utf-8")

    developer_data = yaml.safe_load(developer_file.read_text(encoding="utf-8"))
    developer_data["description"] = "USER EDITED DEVELOPER PERSONA"
    developer_file.write_text(yaml.safe_dump(developer_data), encoding="utf-8")

    # Bootstrapping again over the same directory must be a no-op for
    # already-present v2 profiles.
    _bootstrap(helios_dir)

    identity_after = yaml.safe_load(identity_file.read_text(encoding="utf-8"))
    assert identity_after["description"] == "USER EDITED SPECIES PROFILE"
    assert identity_after["behavioral_distributions"]["epistemic_style"] == {
        "confident": 1.0,
        "hedging": 0.0,
        "admits_ignorance": 0.0,
        "speculating": 0.0,
    }

    developer_after = yaml.safe_load(developer_file.read_text(encoding="utf-8"))
    assert developer_after["description"] == "USER EDITED DEVELOPER PERSONA"
