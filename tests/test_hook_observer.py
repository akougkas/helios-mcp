"""Tests for hook signal extraction (Tasks 1.2, 1.3 + C2 compliance).

Covers all six extractor functions, the merge utility,
and the signal-to-distribution conversion.
"""

import time

import pytest

from helios_mcp.hook_events import (
    ConfigChangeEvent,
    SubagentEvent,
    SessionEvent,
    ToolUseEvent,
    UserPromptEvent,
)
from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.hook_observer import (
    SignalResult,
    extract_config_signals,
    extract_failure_signals,
    extract_prompt_signals,
    extract_session_signals,
    extract_subagent_signals,
    extract_tool_signals,
    hook_signals_to_distributions,
    merge_signal_results,
)
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool(name: str, keys: tuple[str, ...] = (), success: bool = True,
          duration_ms: int = 50, phase: str = "post") -> ToolUseEvent:
    return ToolUseEvent(
        tool_name=name, tool_input_keys=keys,
        duration_ms=duration_ms, success=success, phase=phase,
    )


def _subagent(agent_type: str, event_type: str = "start",
              agent_id: str = "a1") -> SubagentEvent:
    return SubagentEvent(agent_type=agent_type, event_type=event_type,
                         agent_id=agent_id)


def _session(event_type: str, ts: float | None = None) -> SessionEvent:
    return SessionEvent(event_type=event_type,
                        timestamp=ts if ts is not None else time.time())


def _prompt(length: int, questions: int = 0) -> UserPromptEvent:
    return UserPromptEvent(length=length, question_count=questions)


def _has_nonzero(result: SignalResult, dim: str, state: str) -> bool:
    return result.get(dim, {}).get(state, 0.0) > 0.0


# ---------------------------------------------------------------------------
# extract_tool_signals
# ---------------------------------------------------------------------------


class TestExtractToolSignals:
    def test_empty_returns_empty(self):
        result = extract_tool_signals([])
        assert all(len(states) == 0 for states in result.values())

    def test_read_heavy_boosts_confident(self):
        events = [_tool("Read")] * 6 + [_tool("Edit")]
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "epistemic_style", "confident")

    def test_read_heavy_boosts_thorough(self):
        events = [_tool("Read")] * 6 + [_tool("Edit")]
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "communication_register", "thorough")

    def test_read_before_write_boosts_checks(self):
        events = [_tool("Read"), _tool("Grep"), _tool("Edit")]
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "risk_caution", "checks_before_acting")

    def test_agent_tool_boosts_offers_options(self):
        events = [_tool("Agent")] * 3 + [_tool("Read")] * 5
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "interaction_agency", "offers_options")

    def test_bash_heavy_boosts_assumes_and_acts(self):
        events = [_tool("Bash")] * 5 + [_tool("Read")] * 2
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "interaction_agency", "assumes_and_acts")

    def test_high_failure_rate_boosts_acts_immediately(self):
        events = [_tool("Bash", success=False)] * 4 + [_tool("Read")]
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "risk_caution", "acts_immediately")

    def test_no_search_tools_boosts_acts_immediately(self):
        events = [_tool("Edit")] * 5
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "risk_caution", "acts_immediately")

    def test_diverse_tools_boost_speculating(self):
        events = [
            _tool("Read"), _tool("Grep"), _tool("Edit"),
            _tool("Write"), _tool("Bash"), _tool("Agent"),
            _tool("Glob"), _tool("NotebookEdit"),
        ]
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "epistemic_style", "speculating")

    def test_write_heavy_boosts_terse(self):
        events = [_tool("Edit")] * 6 + [_tool("Write")] * 4 + [_tool("Read")]
        result = extract_tool_signals(events)
        assert _has_nonzero(result, "communication_register", "terse")

    def test_returns_all_four_dimensions(self):
        events = [_tool("Read"), _tool("Edit")]
        result = extract_tool_signals(events)
        assert set(result.keys()) == {
            "epistemic_style", "interaction_agency",
            "communication_register", "risk_caution",
        }


# ---------------------------------------------------------------------------
# extract_subagent_signals
# ---------------------------------------------------------------------------


class TestExtractSubagentSignals:
    def test_empty_returns_empty(self):
        result = extract_subagent_signals([])
        assert all(len(states) == 0 for states in result.values())

    def test_high_delegation_boosts_offers_options(self):
        events = [_subagent("Explore", "start")] * 5
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "interaction_agency", "offers_options")

    def test_high_delegation_boosts_defers(self):
        events = [_subagent("Explore", "start")] * 5
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "interaction_agency", "defers_to_user")

    def test_explore_agent_boosts_confident(self):
        events = [_subagent("Explore", "start")]
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "epistemic_style", "confident")

    def test_plan_agent_boosts_confident(self):
        events = [_subagent("Plan", "start")]
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "epistemic_style", "confident")

    def test_parallel_delegation_boosts_acts_immediately(self):
        # Multiple starts before stops suggests parallelization
        events = [
            _subagent("Explore", "start", "a1"),
            _subagent("Plan", "start", "a2"),
            _subagent("Explore", "start", "a3"),
            _subagent("Explore", "stop", "a1"),
            _subagent("Plan", "stop", "a2"),
            _subagent("Explore", "stop", "a3"),
        ]
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "risk_caution", "acts_immediately")

    def test_sequential_delegation_boosts_checks(self):
        events = [
            _subagent("Explore", "start", "a1"),
            _subagent("Explore", "stop", "a1"),
            _subagent("Plan", "start", "a2"),
            _subagent("Plan", "stop", "a2"),
        ]
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "risk_caution", "checks_before_acting")

    def test_heavy_delegation_boosts_thorough(self):
        events = [_subagent("Explore", "start")] * 4
        result = extract_subagent_signals(events)
        assert _has_nonzero(result, "communication_register", "thorough")

    def test_no_delegation_boosts_assumes(self):
        # Only stop events, no starts
        events = []
        result = extract_subagent_signals(events)
        assert all(len(states) == 0 for states in result.values())


# ---------------------------------------------------------------------------
# extract_session_signals
# ---------------------------------------------------------------------------


class TestExtractSessionSignals:
    def test_empty_returns_empty(self):
        result = extract_session_signals([])
        assert all(len(states) == 0 for states in result.values())

    def test_long_session_boosts_thorough(self):
        now = time.time()
        events = [
            _session("start", now),
            _session("end", now + 3600),  # 60 min session
        ]
        result = extract_session_signals(events)
        assert _has_nonzero(result, "communication_register", "thorough")

    def test_long_session_boosts_confident(self):
        now = time.time()
        events = [
            _session("start", now),
            _session("end", now + 3600),
        ]
        result = extract_session_signals(events)
        assert _has_nonzero(result, "epistemic_style", "confident")

    def test_short_session_boosts_terse(self):
        now = time.time()
        events = [
            _session("start", now),
            _session("end", now + 120),  # 2 min session
        ]
        result = extract_session_signals(events)
        assert _has_nonzero(result, "communication_register", "terse")

    def test_short_session_boosts_acts_immediately(self):
        now = time.time()
        events = [
            _session("start", now),
            _session("end", now + 120),
        ]
        result = extract_session_signals(events)
        assert _has_nonzero(result, "risk_caution", "acts_immediately")

    def test_many_sessions_boosts_checks(self):
        now = time.time()
        events = []
        for i in range(4):
            events.append(_session("start", now + i * 600))
            events.append(_session("end", now + i * 600 + 300))
        result = extract_session_signals(events)
        assert _has_nonzero(result, "risk_caution", "checks_before_acting")

    def test_unpaired_start_no_crash(self):
        events = [_session("start")]
        result = extract_session_signals(events)
        assert isinstance(result, dict)

    def test_unpaired_end_no_crash(self):
        events = [_session("end")]
        result = extract_session_signals(events)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# extract_prompt_signals
# ---------------------------------------------------------------------------


class TestExtractPromptSignals:
    def test_empty_returns_empty(self):
        result = extract_prompt_signals([])
        assert all(len(states) == 0 for states in result.values())

    def test_short_prompts_boost_terse(self):
        events = [_prompt(20), _prompt(30), _prompt(15)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "communication_register", "terse")

    def test_long_prompts_boost_thorough(self):
        events = [_prompt(250), _prompt(300), _prompt(220)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "communication_register", "thorough")

    def test_medium_prompts_boost_moderate(self):
        events = [_prompt(80), _prompt(100), _prompt(90)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "communication_register", "moderate")

    def test_high_question_rate_boosts_hedging(self):
        events = [_prompt(50, 2), _prompt(60, 3), _prompt(40, 1)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "epistemic_style", "hedging")

    def test_low_question_long_boosts_confident(self):
        events = [_prompt(150, 0), _prompt(200, 0), _prompt(180, 0)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "epistemic_style", "confident")

    def test_many_questions_boosts_asks_first(self):
        events = [_prompt(100, 3), _prompt(80, 2)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "interaction_agency", "asks_first")

    def test_short_directive_boosts_assumes(self):
        events = [_prompt(20, 0), _prompt(15, 0), _prompt(25, 0)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "interaction_agency", "assumes_and_acts")

    def test_question_heavy_boosts_checks(self):
        events = [_prompt(50, 2), _prompt(60, 1), _prompt(40, 3)]
        result = extract_prompt_signals(events)
        assert _has_nonzero(result, "risk_caution", "checks_before_acting")


# ---------------------------------------------------------------------------
# merge_signal_results
# ---------------------------------------------------------------------------


class TestMergeSignalResults:
    def test_merge_empty(self):
        result = merge_signal_results()
        assert all(len(states) == 0 for states in result.values())

    def test_merge_single(self):
        r1: SignalResult = {
            "epistemic_style": {"confident": 2.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        result = merge_signal_results(r1)
        assert result["epistemic_style"]["confident"] == 2.0

    def test_merge_sums_weights(self):
        r1: SignalResult = {
            "epistemic_style": {"confident": 2.0, "hedging": 1.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        r2: SignalResult = {
            "epistemic_style": {"confident": 1.0},
            "interaction_agency": {"asks_first": 1.5},
            "communication_register": {},
            "risk_caution": {},
        }
        result = merge_signal_results(r1, r2)
        assert result["epistemic_style"]["confident"] == 3.0
        assert result["epistemic_style"]["hedging"] == 1.0
        assert result["interaction_agency"]["asks_first"] == 1.5

    def test_merge_three_results(self):
        r1: SignalResult = {
            "epistemic_style": {"confident": 1.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {"acts_immediately": 1.0},
        }
        r2: SignalResult = {
            "epistemic_style": {"confident": 1.0},
            "interaction_agency": {},
            "communication_register": {"terse": 2.0},
            "risk_caution": {},
        }
        r3: SignalResult = {
            "epistemic_style": {},
            "interaction_agency": {"assumes_and_acts": 3.0},
            "communication_register": {"terse": 1.0},
            "risk_caution": {"acts_immediately": 2.0},
        }
        result = merge_signal_results(r1, r2, r3)
        assert result["epistemic_style"]["confident"] == 2.0
        assert result["communication_register"]["terse"] == 3.0
        assert result["risk_caution"]["acts_immediately"] == 3.0
        assert result["interaction_agency"]["assumes_and_acts"] == 3.0

    def test_merge_preserves_all_dimensions(self):
        result = merge_signal_results(
            {"epistemic_style": {}, "interaction_agency": {},
             "communication_register": {}, "risk_caution": {}},
        )
        assert set(result.keys()) == {
            "epistemic_style", "interaction_agency",
            "communication_register", "risk_caution",
        }


# ---------------------------------------------------------------------------
# hook_signals_to_distributions (Task 1.3)
# ---------------------------------------------------------------------------


class TestHookSignalsToDistributions:
    def test_empty_signals_produce_near_uniform(self):
        """With no signal weights, result should be approximately uniform."""
        signals: SignalResult = {
            "epistemic_style": {},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        dists = hook_signals_to_distributions(signals)
        for dim in list_dimensions():
            assert dim in dists
            dist = dists[dim]
            assert isinstance(dist, BehavioralDistribution)
            # All states should have roughly equal probability
            states = list_states(dim)
            expected = 1.0 / len(states)
            for s in states:
                assert abs(dist[s] - expected) < 0.01

    def test_returns_all_four_dimensions(self):
        signals: SignalResult = {
            "epistemic_style": {"confident": 5.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        dists = hook_signals_to_distributions(signals)
        assert set(dists.keys()) == set(list_dimensions())

    def test_strong_signal_dominates(self):
        """A strong signal weight should produce a distribution favoring that state."""
        signals: SignalResult = {
            "epistemic_style": {"confident": 10.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        dists = hook_signals_to_distributions(signals)
        ep = dists["epistemic_style"]
        assert ep.most_likely() == "confident"
        assert ep["confident"] > 0.5

    def test_all_distributions_are_valid(self):
        """Every returned distribution should sum to 1.0."""
        signals: SignalResult = {
            "epistemic_style": {"hedging": 2.0, "confident": 1.0},
            "interaction_agency": {"asks_first": 3.0},
            "communication_register": {"terse": 5.0},
            "risk_caution": {"checks_before_acting": 4.0, "warns_frequently": 1.0},
        }
        dists = hook_signals_to_distributions(signals)
        for dim, dist in dists.items():
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6, f"{dim} sums to {total}"

    def test_no_zero_mass_states(self):
        """Even states with no signal should have nonzero probability (prior)."""
        signals: SignalResult = {
            "epistemic_style": {"confident": 10.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        dists = hook_signals_to_distributions(signals)
        for dim in list_dimensions():
            for s in list_states(dim):
                assert dists[dim][s] > 0.0, f"{dim}.{s} has zero mass"

    def test_multiple_signals_blend(self):
        """Multiple signals in one dimension should blend proportionally."""
        signals: SignalResult = {
            "epistemic_style": {"confident": 3.0, "hedging": 3.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        dists = hook_signals_to_distributions(signals)
        ep = dists["epistemic_style"]
        # confident and hedging should have equal weight (plus equal priors)
        assert abs(ep["confident"] - ep["hedging"]) < 0.01

    def test_end_to_end_with_extractors(self):
        """Full pipeline: events → extract → merge → distributions."""
        tool_events = [_tool("Read")] * 6 + [_tool("Edit")]
        prompt_events = [_prompt(20, 0), _prompt(15, 0)]

        tool_sig = extract_tool_signals(tool_events)
        prompt_sig = extract_prompt_signals(prompt_events)
        merged = merge_signal_results(tool_sig, prompt_sig)
        dists = hook_signals_to_distributions(merged)

        assert len(dists) == 4
        for dim, dist in dists.items():
            assert isinstance(dist, BehavioralDistribution)
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6

    def test_proportional_to_weights(self):
        """State with 2x the weight should have roughly 2x probability (minus prior)."""
        signals: SignalResult = {
            "epistemic_style": {"confident": 4.0, "hedging": 2.0},
            "interaction_agency": {},
            "communication_register": {},
            "risk_caution": {},
        }
        dists = hook_signals_to_distributions(signals)
        ep = dists["epistemic_style"]
        # confident got 4.0 + 0.1 prior = 4.1, hedging got 2.0 + 0.1 = 2.1
        # Others got 0.1 each (2 others = 0.2)
        # Total = 4.1 + 2.1 + 0.1 + 0.1 = 6.4
        # confident should be roughly 4.1/6.4 ≈ 0.64
        assert ep["confident"] > ep["hedging"]
        assert ep["confident"] > 0.5


# ---------------------------------------------------------------------------
# extract_failure_signals (C2 compliance)
# ---------------------------------------------------------------------------


def _failure_tool(name: str, keys: tuple[str, ...] = ()) -> ToolUseEvent:
    return ToolUseEvent(
        tool_name=name, tool_input_keys=keys,
        success=False, phase="post_failure",
    )


class TestExtractFailureSignals:
    def test_empty_returns_empty(self):
        result = extract_failure_signals([])
        assert all(len(states) == 0 for states in result.values())

    def test_repeated_same_tool_failures_boost_acts_immediately(self):
        events = [_failure_tool("Bash")] * 4
        result = extract_failure_signals(events)
        assert _has_nonzero(result, "risk_caution", "acts_immediately")

    def test_repeated_same_tool_failures_boost_confident(self):
        events = [_failure_tool("Bash")] * 3
        result = extract_failure_signals(events)
        assert _has_nonzero(result, "epistemic_style", "confident")

    def test_diverse_tool_failures_boost_speculating(self):
        events = [
            _failure_tool("Bash"),
            _failure_tool("Edit"),
            _failure_tool("Write"),
        ]
        result = extract_failure_signals(events)
        assert _has_nonzero(result, "epistemic_style", "speculating")

    def test_multiple_failures_boost_warns_frequently(self):
        events = [_failure_tool("Bash"), _failure_tool("Edit")]
        result = extract_failure_signals(events)
        assert _has_nonzero(result, "risk_caution", "warns_frequently")

    def test_many_failures_boost_assumes_and_acts(self):
        events = [_failure_tool("Bash")] * 5
        result = extract_failure_signals(events)
        assert _has_nonzero(result, "interaction_agency", "assumes_and_acts")

    def test_single_failure_minimal_signals(self):
        events = [_failure_tool("Bash")]
        result = extract_failure_signals(events)
        # Single failure should not trigger heavy signals
        assert not _has_nonzero(result, "risk_caution", "acts_immediately")
        assert not _has_nonzero(result, "interaction_agency", "assumes_and_acts")

    def test_returns_all_four_dimensions(self):
        events = [_failure_tool("Bash")]
        result = extract_failure_signals(events)
        assert set(result.keys()) == {
            "epistemic_style", "interaction_agency",
            "communication_register", "risk_caution",
        }


# ---------------------------------------------------------------------------
# extract_config_signals (C2 compliance)
# ---------------------------------------------------------------------------


def _config_change(source: str = "user", file_path: str = "") -> ConfigChangeEvent:
    return ConfigChangeEvent(source=source, file_path=file_path)


class TestExtractConfigSignals:
    def test_empty_returns_empty(self):
        result = extract_config_signals([])
        assert all(len(states) == 0 for states in result.values())

    def test_frequent_changes_boost_speculating(self):
        events = [_config_change()] * 3
        result = extract_config_signals(events)
        assert _has_nonzero(result, "epistemic_style", "speculating")

    def test_frequent_changes_boost_assumes_and_acts(self):
        events = [_config_change()] * 3
        result = extract_config_signals(events)
        assert _has_nonzero(result, "interaction_agency", "assumes_and_acts")

    def test_any_change_boosts_checks(self):
        events = [_config_change()]
        result = extract_config_signals(events)
        assert _has_nonzero(result, "risk_caution", "checks_before_acting")

    def test_returns_all_four_dimensions(self):
        events = [_config_change()]
        result = extract_config_signals(events)
        assert set(result.keys()) == {
            "epistemic_style", "interaction_agency",
            "communication_register", "risk_caution",
        }
