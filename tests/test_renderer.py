"""The rendered context keeps each distribution's shape."""

from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.profile import BehavioralProfile
from helios_mcp.renderer import BehavioralRenderer, tendencies
from helios_mcp.taxonomy import get_state_label

DIM = "communication_register"


def profile_with(probs):
    return BehavioralProfile(agent_id="p", level="domain", distributions={
        DIM: BehavioralDistribution(DIM, probs)})


def test_secondary_tendencies_are_rendered_with_their_weights():
    text = BehavioralRenderer().render(profile_with({
        "terse": 0.5, "moderate": 0.05, "thorough": 0.3,
        "technical_dense": 0.1, "plain_accessible": 0.05}), "dev")
    assert f"Often (50%): {get_state_label(DIM, 'terse')}" in text
    assert f"Sometimes (30%): {get_state_label(DIM, 'thorough')}" in text
    assert get_state_label(DIM, "technical_dense") not in text
    assert "'dev'" in text


def test_concentrated_dimension_renders_one_settled_tendency():
    dist = BehavioralDistribution(DIM, {
        "terse": 0.9, "moderate": 0.025, "thorough": 0.025,
        "technical_dense": 0.025, "plain_accessible": 0.025})
    assert tendencies(dist) == [("terse", 0.9)]
    assert "(settled)" in BehavioralRenderer().render(profile_with(dist.to_dict()))


def test_uniform_dimension_is_flagged_as_varied():
    text = BehavioralRenderer().render(
        profile_with(BehavioralDistribution.uniform(DIM).to_dict()))
    assert "varied" in text


def test_full_species_profile_renders_every_dimension():
    text = BehavioralRenderer().render(BehavioralProfile.default_species())
    for heading in ("Epistemic style", "Interaction agency",
                    "Communication register", "Risk and caution"):
        assert heading in text
