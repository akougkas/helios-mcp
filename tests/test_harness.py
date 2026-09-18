"""BehavioralHarness over HeliosService."""

from pathlib import Path

import pytest

from helios_mcp.harness import BehavioralHarness


@pytest.fixture()
def helios_dir(tmp_path: Path) -> Path:
    return tmp_path / "helios"


def test_context_is_the_rendered_persona_profile(helios_dir):
    ctx = BehavioralHarness("developer", helios_dir).get_context()
    assert "'developer'" in ctx
    assert "Epistemic style" in ctx


def test_decorator_injects_system_and_preserves_metadata(helios_dir):
    captured: list[str] = []
    harness = BehavioralHarness("developer", helios_dir, observe_every=1000)

    @harness
    def agent(messages, system=""):
        """Doc."""
        captured.append(system)
        return 42

    assert agent([]) == 42
    assert agent.__name__ == "agent" and agent.__doc__ == "Doc."
    assert "Epistemic style" in captured[0]


def test_invalid_persona_is_rejected(helios_dir):
    from helios_mcp.security import SecurityError

    with pytest.raises(SecurityError):
        BehavioralHarness("../x", helios_dir)


def test_fresh_harness_does_not_recommend_negotiation(helios_dir):
    harness = BehavioralHarness("developer", helios_dir)
    assert harness.should_negotiate() is False
    assert harness.get_drift_summary() is None


def test_repeated_observe_of_a_growing_conversation_is_idempotent(helios_dir):
    pytest.importorskip("helios_mcp.ingest")
    harness = BehavioralHarness("developer", helios_dir)
    convo = [{"role": "user", "content": "Refactor this."},
             {"role": "assistant", "content": "Done. I used a comprehension."},
             {"role": "user", "content": "Thanks. Now add a test."}]
    first = harness.observe(convo)
    assert first["observations_added"] >= 1
    assert harness.observe(convo)["observations_added"] == 0
