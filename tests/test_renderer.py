"""Tests for BehavioralRenderer (Phase 2)."""
from __future__ import annotations

import pytest

from helios_mcp.profile import BehavioralProfile
from helios_mcp.renderer import BehavioralRenderer
from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.taxonomy import list_dimensions, get_state_label


_ALL_DIMS = list_dimensions()

_EXPECTED_HEADINGS = [
    "EPISTEMIC STYLE",
    "INTERACTION AGENCY",
    "COMMUNICATION REGISTER",
    "RISK AND CAUTION",
]


class TestRenderBasics:
    def test_render_returns_nonempty_string(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_contains_all_dimension_headings(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile)
        for heading in _EXPECTED_HEADINGS:
            assert heading in result, f"Missing heading: {heading}"

    def test_render_with_persona_name_in_header(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile, persona_name="developer")
        assert "developer" in result

    def test_render_without_persona_name(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile)
        # Should still work without persona name
        assert "behavioral profile" in result.lower()

    def test_render_contains_trailing_instruction(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile)
        assert "behavioral patterns" in result.lower()


class TestRenderDominantState:
    def test_most_likely_state_label_appears_in_output(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile)

        # For default_species epistemic_style, dominant is "confident" (0.45)
        expected_label = get_state_label("epistemic_style", "confident")
        assert expected_label in result

    def test_all_dominant_state_labels_appear(self) -> None:
        renderer = BehavioralRenderer()
        profile = BehavioralProfile.default_species()
        result = renderer.render(profile)

        for dim in _ALL_DIMS:
            dist = profile.distributions[dim]
            dominant = dist.most_likely()
            label = get_state_label(dim, dominant)
            assert label in result, f"Missing label for {dim}/{dominant}: '{label}'"


class TestRenderHighEntropyNote:
    def test_high_entropy_note_present_for_uniform_distribution(self) -> None:
        renderer = BehavioralRenderer()
        # Uniform distribution has normalized_entropy = 1.0 > 0.6
        uniform_profile = BehavioralProfile(
            agent_id="test",
            level="domain",
            distributions={dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS},
        )
        result = renderer.render(uniform_profile)
        assert "high behavioral diversity" in result

    def test_no_high_entropy_note_for_point_mass_distribution(self) -> None:
        renderer = BehavioralRenderer()
        # Point mass has normalized_entropy = 0.0 < 0.3 — no note expected
        point_mass_profile = BehavioralProfile(
            agent_id="test",
            level="domain",
            distributions={
                dim: BehavioralDistribution.point_mass(dim, states[0])
                for dim, states in [
                    ("epistemic_style", ["confident"]),
                    ("interaction_agency", ["asks_first"]),
                    ("communication_register", ["moderate"]),
                    ("risk_caution", ["checks_before_acting"]),
                ]
            },
        )
        result = renderer.render(point_mass_profile)
        assert "high behavioral diversity" not in result

    def test_concentrated_distribution_does_not_trigger_high_entropy_note(self) -> None:
        renderer = BehavioralRenderer()
        # Build a profile with very concentrated (low-entropy) distributions
        from helios_mcp.taxonomy import list_dimensions, list_states
        dists: dict = {}
        for dim in list_dimensions():
            states = list_states(dim)
            # Put 0.97 on first state, rest share 0.03
            n_rest = len(states) - 1
            rest_prob = 0.03 / n_rest if n_rest > 0 else 0.0
            dists[dim] = BehavioralDistribution(dim, {s: (0.97 if i == 0 else rest_prob) for i, s in enumerate(states)})
        profile = BehavioralProfile(agent_id="concentrated", level="domain", distributions=dists)
        result = renderer.render(profile)
        assert "high behavioral diversity" not in result
