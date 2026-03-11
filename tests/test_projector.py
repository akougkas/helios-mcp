"""Tests for LLM-assisted projection (Task 2.2).

Covers prompt construction, response parsing, validation/normalization,
and the keyword fallback path.
"""

import json

import pytest

from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.projector import (
    build_projection_prompt,
    build_taxonomy_description,
    parse_projection_response,
    project_to_distributions,
    validate_and_normalize,
)
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestBuildTaxonomyDescription:
    def test_includes_all_dimensions(self):
        desc = build_taxonomy_description()
        for dim in list_dimensions():
            assert dim in desc

    def test_includes_all_states(self):
        desc = build_taxonomy_description()
        for dim in list_dimensions():
            for state in list_states(dim):
                assert state in desc


class TestBuildProjectionPrompt:
    def test_returns_system_and_user(self):
        system, user = build_projection_prompt(["Be direct."])
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 100
        assert "Be direct" in user

    def test_multiple_blocks_joined(self):
        system, user = build_projection_prompt(["Block 1", "Block 2"])
        assert "Block 1" in user
        assert "Block 2" in user

    def test_system_prompt_has_json_format(self):
        system, _ = build_projection_prompt(["test"])
        assert "epistemic_style" in system
        assert "interaction_agency" in system
        assert "JSON" in system


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _valid_response() -> str:
    """Generate a valid LLM response."""
    return json.dumps({
        "epistemic_style": {
            "confident": 0.60, "hedging": 0.20,
            "admits_ignorance": 0.10, "speculating": 0.10,
        },
        "interaction_agency": {
            "asks_first": 0.15, "assumes_and_acts": 0.40,
            "offers_options": 0.25, "decides_unilaterally": 0.10,
            "defers_to_user": 0.10,
        },
        "communication_register": {
            "terse": 0.35, "moderate": 0.30,
            "thorough": 0.15, "technical_dense": 0.15,
            "plain_accessible": 0.05,
        },
        "risk_caution": {
            "acts_immediately": 0.25, "checks_before_acting": 0.40,
            "warns_frequently": 0.25, "refuses_ambiguity": 0.10,
        },
    })


class TestParseProjectionResponse:
    def test_valid_json(self):
        raw = parse_projection_response(_valid_response())
        assert set(raw.keys()) == set(list_dimensions())

    def test_with_code_fences(self):
        fenced = f"```json\n{_valid_response()}\n```"
        raw = parse_projection_response(fenced)
        assert "epistemic_style" in raw

    def test_with_bare_fences(self):
        fenced = f"```\n{_valid_response()}\n```"
        raw = parse_projection_response(fenced)
        assert "epistemic_style" in raw

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_projection_response("not json at all")

    def test_missing_dimension_raises(self):
        partial = json.dumps({
            "epistemic_style": {
                "confident": 0.5, "hedging": 0.2,
                "admits_ignorance": 0.2, "speculating": 0.1,
            },
        })
        with pytest.raises(ValueError, match="Missing dimension"):
            parse_projection_response(partial)

    def test_missing_state_raises(self):
        data = json.loads(_valid_response())
        del data["epistemic_style"]["confident"]
        with pytest.raises(ValueError, match="Missing state"):
            parse_projection_response(json.dumps(data))

    def test_negative_value_raises(self):
        data = json.loads(_valid_response())
        data["epistemic_style"]["confident"] = -0.5
        with pytest.raises(ValueError, match="negative"):
            parse_projection_response(json.dumps(data))

    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="JSON object"):
            parse_projection_response("[1, 2, 3]")

    def test_non_dict_dimension_raises(self):
        data = json.loads(_valid_response())
        data["epistemic_style"] = "not a dict"
        with pytest.raises(ValueError, match="must be a dict"):
            parse_projection_response(json.dumps(data))

    def test_non_numeric_value_raises(self):
        data = json.loads(_valid_response())
        data["epistemic_style"]["confident"] = "high"
        with pytest.raises(ValueError, match="must be numeric"):
            parse_projection_response(json.dumps(data))


# ---------------------------------------------------------------------------
# Validation and normalization
# ---------------------------------------------------------------------------


class TestValidateAndNormalize:
    def test_valid_input(self):
        raw = json.loads(_valid_response())
        dists = validate_and_normalize(raw)
        assert set(dists.keys()) == set(list_dimensions())
        for dim, dist in dists.items():
            assert isinstance(dist, BehavioralDistribution)
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6

    def test_unnormalized_input_gets_normalized(self):
        raw = {
            "epistemic_style": {"confident": 5.0, "hedging": 3.0, "admits_ignorance": 1.0, "speculating": 1.0},
            "interaction_agency": {"asks_first": 2.0, "assumes_and_acts": 4.0, "offers_options": 2.0, "decides_unilaterally": 1.0, "defers_to_user": 1.0},
            "communication_register": {"terse": 3.0, "moderate": 3.0, "thorough": 2.0, "technical_dense": 1.0, "plain_accessible": 1.0},
            "risk_caution": {"acts_immediately": 1.0, "checks_before_acting": 4.0, "warns_frequently": 3.0, "refuses_ambiguity": 2.0},
        }
        dists = validate_and_normalize(raw)
        for dim, dist in dists.items():
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6

    def test_zero_values_get_floored(self):
        raw = {
            "epistemic_style": {"confident": 1.0, "hedging": 0.0, "admits_ignorance": 0.0, "speculating": 0.0},
            "interaction_agency": {"asks_first": 0.0, "assumes_and_acts": 1.0, "offers_options": 0.0, "decides_unilaterally": 0.0, "defers_to_user": 0.0},
            "communication_register": {"terse": 1.0, "moderate": 0.0, "thorough": 0.0, "technical_dense": 0.0, "plain_accessible": 0.0},
            "risk_caution": {"acts_immediately": 0.0, "checks_before_acting": 1.0, "warns_frequently": 0.0, "refuses_ambiguity": 0.0},
        }
        dists = validate_and_normalize(raw)
        # All states should have nonzero probability due to floor
        for dim in list_dimensions():
            for s in list_states(dim):
                assert dists[dim][s] > 0.0

    def test_missing_dimension_gets_uniform(self):
        raw = {}
        dists = validate_and_normalize(raw)
        for dim in list_dimensions():
            assert isinstance(dists[dim], BehavioralDistribution)


# ---------------------------------------------------------------------------
# project_to_distributions
# ---------------------------------------------------------------------------


class TestProjectToDistributions:
    def test_with_llm_response(self):
        dists = project_to_distributions(["Be direct."], llm_response=_valid_response())
        assert set(dists.keys()) == set(list_dimensions())
        assert dists["epistemic_style"]["confident"] > 0.5

    def test_keyword_fallback(self):
        dists = project_to_distributions(["Be direct and concise."])
        assert set(dists.keys()) == set(list_dimensions())
        for dim, dist in dists.items():
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6

    def test_llm_response_with_fences(self):
        fenced = f"```json\n{_valid_response()}\n```"
        dists = project_to_distributions(["test"], llm_response=fenced)
        assert "epistemic_style" in dists

    def test_invalid_llm_response_raises(self):
        with pytest.raises(ValueError):
            project_to_distributions(["test"], llm_response="garbage")

    def test_none_response_uses_fallback(self):
        dists = project_to_distributions(["Be thorough and comprehensive."], llm_response=None)
        assert dists["communication_register"]["thorough"] > 0.2
