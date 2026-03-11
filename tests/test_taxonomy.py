"""Tests for behavioral taxonomy — the scientific foundation of Helios v2."""

import pytest
from helios_mcp.taxonomy import (
    BEHAVIORAL_TAXONOMY,
    DIMENSION_DESCRIPTIONS,
    STATE_LABELS,
    list_dimensions,
    list_states,
    validate_dimension,
    validate_state,
    get_dimension_description,
    get_state_label,
    uniform_distribution,
)


# ---------------------------------------------------------------------------
# Taxonomy completeness and structure
# ---------------------------------------------------------------------------

class TestTaxonomyStructure:
    def test_four_dimensions_exist(self) -> None:
        dims = list_dimensions()
        assert len(dims) == 4

    def test_required_dimensions_present(self) -> None:
        dims = set(list_dimensions())
        assert "epistemic_style" in dims
        assert "interaction_agency" in dims
        assert "communication_register" in dims
        assert "risk_caution" in dims

    def test_epistemic_style_states(self) -> None:
        states = list_states("epistemic_style")
        assert "confident" in states
        assert "hedging" in states
        assert "admits_ignorance" in states
        assert "speculating" in states

    def test_interaction_agency_states(self) -> None:
        states = list_states("interaction_agency")
        assert "asks_first" in states
        assert "assumes_and_acts" in states
        assert "offers_options" in states
        assert "decides_unilaterally" in states
        assert "defers_to_user" in states

    def test_communication_register_states(self) -> None:
        states = list_states("communication_register")
        assert "terse" in states
        assert "moderate" in states
        assert "thorough" in states
        assert "technical_dense" in states
        assert "plain_accessible" in states

    def test_risk_caution_states(self) -> None:
        states = list_states("risk_caution")
        assert "acts_immediately" in states
        assert "checks_before_acting" in states
        assert "warns_frequently" in states
        assert "refuses_ambiguity" in states

    def test_every_dimension_has_description(self) -> None:
        for dim in list_dimensions():
            assert dim in DIMENSION_DESCRIPTIONS
            assert len(DIMENSION_DESCRIPTIONS[dim]) > 10

    def test_every_state_has_label(self) -> None:
        for dim, states in BEHAVIORAL_TAXONOMY.items():
            assert dim in STATE_LABELS, f"Missing STATE_LABELS entry for '{dim}'"
            for state in states:
                assert state in STATE_LABELS[dim], (
                    f"Missing STATE_LABELS['{dim}']['{state}']"
                )
                assert len(STATE_LABELS[dim][state]) > 5

    def test_all_dimensions_have_at_least_two_states(self) -> None:
        for dim in list_dimensions():
            assert len(list_states(dim)) >= 2


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

class TestValidation:
    def test_validate_dimension_valid(self) -> None:
        for dim in list_dimensions():
            assert validate_dimension(dim) == dim

    def test_validate_dimension_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unknown behavioral dimension"):
            validate_dimension("nonexistent_dimension")

    def test_validate_state_valid(self) -> None:
        assert validate_state("epistemic_style", "confident") == "confident"
        assert validate_state("risk_caution", "acts_immediately") == "acts_immediately"

    def test_validate_state_invalid_state(self) -> None:
        with pytest.raises(ValueError, match="Unknown state"):
            validate_state("epistemic_style", "totally_wrong_state")

    def test_validate_state_invalid_dimension(self) -> None:
        with pytest.raises(ValueError, match="Unknown behavioral dimension"):
            validate_state("bad_dimension", "confident")

    def test_validate_state_wrong_dimension_for_state(self) -> None:
        # 'terse' is communication_register, not epistemic_style
        with pytest.raises(ValueError, match="Unknown state"):
            validate_state("epistemic_style", "terse")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestUtilities:
    def test_get_dimension_description_returns_string(self) -> None:
        desc = get_dimension_description("epistemic_style")
        assert isinstance(desc, str)
        assert len(desc) > 20

    def test_get_dimension_description_invalid(self) -> None:
        with pytest.raises(ValueError):
            get_dimension_description("bad_dim")

    def test_get_state_label_returns_string(self) -> None:
        label = get_state_label("communication_register", "terse")
        assert isinstance(label, str)
        assert len(label) > 5

    def test_get_state_label_invalid_state(self) -> None:
        with pytest.raises(ValueError):
            get_state_label("communication_register", "nonexistent")

    def test_uniform_distribution_sums_to_one(self) -> None:
        for dim in list_dimensions():
            dist = uniform_distribution(dim)
            total = sum(dist.values())
            assert abs(total - 1.0) < 1e-9, (
                f"Uniform distribution for '{dim}' sums to {total}, not 1.0"
            )

    def test_uniform_distribution_all_states_covered(self) -> None:
        for dim in list_dimensions():
            dist = uniform_distribution(dim)
            expected_states = set(list_states(dim))
            assert set(dist.keys()) == expected_states

    def test_uniform_distribution_equal_probabilities(self) -> None:
        for dim in list_dimensions():
            states = list_states(dim)
            dist = uniform_distribution(dim)
            expected_prob = 1.0 / len(states)
            for state, prob in dist.items():
                assert abs(prob - expected_prob) < 1e-9

    def test_list_states_returns_copy(self) -> None:
        # Modifying the returned list should not affect the taxonomy
        states = list_states("epistemic_style")
        original_len = len(BEHAVIORAL_TAXONOMY["epistemic_style"])
        states.append("injected_state")
        assert len(BEHAVIORAL_TAXONOMY["epistemic_style"]) == original_len
