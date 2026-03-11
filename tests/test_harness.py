"""Tests for BehavioralHarness (Phase 6)."""
from __future__ import annotations

from pathlib import Path

import pytest

from helios_mcp.harness import BehavioralHarness
from helios_mcp.profile import BehavioralProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_helios_dir(tmp_path: Path) -> Path:
    """Build a minimal helios directory with identity.yaml and developer.yaml."""
    helios = tmp_path / ".helios"
    (helios / "base").mkdir(parents=True, exist_ok=True)
    (helios / "personas").mkdir(parents=True, exist_ok=True)
    (helios / "temporary").mkdir(parents=True, exist_ok=True)
    (helios / "learned").mkdir(parents=True, exist_ok=True)

    # Write species-level base profile
    species = BehavioralProfile.default_species()
    species.save(helios / "base" / "identity.yaml")

    # Write a minimal developer persona
    from helios_mcp.distribution import BehavioralDistribution
    from helios_mcp.taxonomy import list_dimensions

    developer = BehavioralProfile(
        agent_id="developer",
        level="domain",
        distributions={
            dim: BehavioralDistribution.uniform(dim) for dim in list_dimensions()
        },
        specialization_level=2,
        base_importance=0.7,
        description="Developer persona for testing",
    )
    developer.save(helios / "personas" / "developer.yaml")

    return helios


@pytest.fixture()
def helios_dir(tmp_path: Path) -> Path:
    return _make_helios_dir(tmp_path)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestBehavioralHarnessInit:
    def test_instantiates_without_error(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        assert harness is not None

    def test_default_persona_is_developer(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(helios_dir=helios_dir)
        assert harness.persona == "developer"

    def test_custom_persona_name(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="researcher", helios_dir=helios_dir)
        assert harness.persona == "researcher"

    def test_custom_drift_threshold(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(
            persona="developer", helios_dir=helios_dir, drift_threshold=0.50
        )
        assert harness.drift_threshold == 0.50

    def test_custom_negotiate_after(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(
            persona="developer", helios_dir=helios_dir, negotiate_after=5
        )
        assert harness.negotiate_after == 5


# ---------------------------------------------------------------------------
# get_context()
# ---------------------------------------------------------------------------


class TestGetContext:
    def test_returns_nonempty_string(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        ctx = harness.get_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_context_mentions_persona(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        ctx = harness.get_context()
        assert "developer" in ctx

    def test_context_contains_behavioral_dimensions(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        ctx = harness.get_context()
        # Renderer always emits dimension headings
        assert "EPISTEMIC STYLE" in ctx
        assert "INTERACTION AGENCY" in ctx


# ---------------------------------------------------------------------------
# observe()
# ---------------------------------------------------------------------------


class TestObserve:
    def test_observe_increments_observation_count(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        assert harness._observer.get_observation_count("developer") == 0

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        harness.observe(messages)
        assert harness._observer.get_observation_count("developer") == 1

    def test_multiple_observations_accumulate(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        messages = [{"role": "assistant", "content": "Response text."}]
        harness.observe(messages)
        harness.observe(messages)
        harness.observe(messages)
        assert harness._observer.get_observation_count("developer") == 3


# ---------------------------------------------------------------------------
# should_negotiate()
# ---------------------------------------------------------------------------


class TestShouldNegotiate:
    def test_returns_false_when_below_negotiate_after_threshold(
        self, helios_dir: Path
    ) -> None:
        harness = BehavioralHarness(
            persona="developer",
            helios_dir=helios_dir,
            negotiate_after=20,
        )
        # No observations — should not negotiate
        assert harness.should_negotiate() is False

    def test_returns_false_with_few_observations(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(
            persona="developer",
            helios_dir=helios_dir,
            negotiate_after=20,
        )
        messages = [{"role": "assistant", "content": "Short reply."}]
        for _ in range(5):
            harness.observe(messages)
        # 5 < 20 — below threshold
        assert harness.should_negotiate() is False

    def test_returns_false_below_count_even_with_low_threshold(
        self, helios_dir: Path
    ) -> None:
        harness = BehavioralHarness(
            persona="developer",
            helios_dir=helios_dir,
            drift_threshold=0.0,  # any drift would trigger
            negotiate_after=100,  # but count is always < 100 in this test
        )
        messages = [{"role": "assistant", "content": "A reply."}]
        harness.observe(messages)
        assert harness.should_negotiate() is False


# ---------------------------------------------------------------------------
# Decorator support
# ---------------------------------------------------------------------------


class TestDecoratorWrapping:
    def test_decorator_preserves_function_name(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)

        @harness
        def my_special_agent(messages: list[dict], system: str = "") -> str:
            return "hello"

        assert my_special_agent.__name__ == "my_special_agent"

    def test_decorator_preserves_docstring(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)

        @harness
        def my_agent(messages: list[dict], system: str = "") -> str:
            """My agent docstring."""
            return "hello"

        assert my_agent.__doc__ == "My agent docstring."

    def test_decorator_injects_system_kwarg(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        captured: list[str] = []

        @harness
        def recording_agent(messages: list[dict], system: str = "") -> str:
            captured.append(system)
            return "done"

        recording_agent([{"role": "user", "content": "hi"}])
        assert len(captured) == 1
        assert len(captured[0]) > 0  # behavioral context was injected

    def test_decorator_does_not_inject_system_if_no_param(
        self, helios_dir: Path
    ) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)

        @harness
        def simple_agent(messages: list[dict]) -> str:
            return "no system param"

        # Should not raise even without 'system' parameter
        result = simple_agent([{"role": "user", "content": "hi"}])
        assert result == "no system param"

    def test_decorator_calls_wrapped_function(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        call_count = [0]

        @harness
        def counted_agent(messages: list[dict], system: str = "") -> str:
            call_count[0] += 1
            return "response"

        counted_agent([])
        counted_agent([])
        assert call_count[0] == 2


# ---------------------------------------------------------------------------
# Context manager support
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_self(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        with harness as h:
            assert h is harness

    def test_context_manager_get_context_works(self, helios_dir: Path) -> None:
        with BehavioralHarness(persona="developer", helios_dir=helios_dir) as h:
            ctx = h.get_context()
            assert isinstance(ctx, str)
            assert len(ctx) > 0

    def test_context_manager_observe_works(self, helios_dir: Path) -> None:
        with BehavioralHarness(persona="developer", helios_dir=helios_dir) as h:
            h.observe([{"role": "assistant", "content": "A response."}])
            assert h._observer.get_observation_count("developer") == 1

    def test_context_manager_exits_cleanly_on_exception(
        self, helios_dir: Path
    ) -> None:
        try:
            with BehavioralHarness(persona="developer", helios_dir=helios_dir) as h:
                h.observe([{"role": "assistant", "content": "Before error."}])
                raise ValueError("simulated error")
        except ValueError:
            pass  # Exit should not suppress or re-raise differently


# ---------------------------------------------------------------------------
# get_drift_summary()
# ---------------------------------------------------------------------------


class TestGetDriftSummary:
    def test_returns_none_when_no_observations(self, helios_dir: Path) -> None:
        harness = BehavioralHarness(persona="developer", helios_dir=helios_dir)
        assert harness.get_drift_summary() is None

    def test_returns_none_below_drift_threshold(self, helios_dir: Path) -> None:
        # Use an impossibly high threshold so no drift can ever exceed it
        # KL divergence across 4 dimensions can easily reach 5-10, so use 1000.0
        harness = BehavioralHarness(
            persona="developer",
            helios_dir=helios_dir,
            drift_threshold=1000.0,
        )
        messages = [{"role": "assistant", "content": "A short reply."}]
        for _ in range(5):
            harness.observe(messages)
        summary = harness.get_drift_summary()
        assert summary is None

    def test_returns_string_when_drift_detected(self, helios_dir: Path) -> None:
        # Set an impossibly low drift threshold so drift is always detected
        harness = BehavioralHarness(
            persona="developer",
            helios_dir=helios_dir,
            drift_threshold=0.0,  # everything exceeds 0.0
        )
        messages = [{"role": "assistant", "content": "I'm not sure, perhaps maybe."}]
        harness.observe(messages)

        summary = harness.get_drift_summary()
        # With threshold=0.0 and any observation, drift is detected
        assert summary is not None
        assert isinstance(summary, str)
        assert "developer" in summary
