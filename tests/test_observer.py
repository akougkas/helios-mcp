"""Tests for BehavioralObserver — the signal extraction and distribution engine."""

from __future__ import annotations

import pytest

from helios_mcp.observer import (
    BehavioralObserver,
    extract_decision_points,
    extract_semantic,
    extract_structural,
    extract_user_signals,
    signals_to_distributions,
)
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_messages(*pairs: tuple[str, str]) -> list[dict]:
    """Build a message list from (role, content) pairs."""
    return [{"role": role, "content": content} for role, content in pairs]


def assistant(content: str) -> dict:
    return {"role": "assistant", "content": content}


def user(content: str) -> dict:
    return {"role": "user", "content": content}


# ---------------------------------------------------------------------------
# extract_structural
# ---------------------------------------------------------------------------

class TestExtractStructural:
    def test_returns_all_expected_keys(self) -> None:
        msgs = [assistant("Hello world.")]
        result = extract_structural(msgs)
        expected_keys = {"avg_length", "list_rate", "question_rate", "hedge_rate", "code_rate", "caveat_rate"}
        assert set(result.keys()) == expected_keys

    def test_empty_messages_returns_zeros(self) -> None:
        result = extract_structural([])
        assert result["avg_length"] == 0.0
        assert result["list_rate"] == 0.0
        assert result["question_rate"] == 0.0

    def test_only_user_messages_returns_zeros(self) -> None:
        msgs = [user("what?"), user("explain please")]
        result = extract_structural(msgs)
        assert result["avg_length"] == 0.0

    def test_avg_length_counts_words(self) -> None:
        msgs = [assistant("one two three four five")]
        result = extract_structural(msgs)
        assert result["avg_length"] == 5.0

    def test_avg_length_averages_multiple_messages(self) -> None:
        msgs = [assistant("one two"), assistant("three four five six")]
        result = extract_structural(msgs)
        assert result["avg_length"] == pytest.approx(3.0)

    def test_list_rate_detects_bullet_points(self) -> None:
        msgs = [
            assistant("- item one\n- item two"),
            assistant("No bullets here."),
        ]
        result = extract_structural(msgs)
        assert result["list_rate"] == pytest.approx(0.5)

    def test_list_rate_detects_asterisk_bullets(self) -> None:
        msgs = [assistant("* item\n* another")]
        result = extract_structural(msgs)
        assert result["list_rate"] == pytest.approx(1.0)

    def test_question_rate_counts_questions(self) -> None:
        msgs = [
            assistant("Do you want me to proceed?"),
            assistant("Here is the answer."),
        ]
        result = extract_structural(msgs)
        assert result["question_rate"] == pytest.approx(0.5)

    def test_hedge_words_detected_correctly(self) -> None:
        msgs = [
            assistant("I think this might work."),
            assistant("This is definitely correct."),
        ]
        result = extract_structural(msgs)
        assert result["hedge_rate"] == pytest.approx(0.5)

    def test_hedge_rate_multiple_words(self) -> None:
        msgs = [assistant("Perhaps this could work, maybe.")]
        result = extract_structural(msgs)
        assert result["hedge_rate"] == pytest.approx(1.0)

    def test_code_rate_detects_backticks(self) -> None:
        msgs = [
            assistant("```python\nprint('hi')\n```"),
            assistant("Plain text here."),
        ]
        result = extract_structural(msgs)
        assert result["code_rate"] == pytest.approx(0.5)

    def test_code_rate_detects_indented_blocks(self) -> None:
        msgs = [assistant("    indented_code = True")]
        result = extract_structural(msgs)
        assert result["code_rate"] == pytest.approx(1.0)

    def test_caveat_rate_detects_caveat_phrases(self) -> None:
        msgs = [
            assistant("Note: this is important."),
            assistant("Here is the plain answer."),
        ]
        result = extract_structural(msgs)
        assert result["caveat_rate"] == pytest.approx(0.5)

    def test_all_rates_between_zero_and_one(self) -> None:
        msgs = [assistant("Hello."), assistant("How are you?"), assistant("I think perhaps.")]
        result = extract_structural(msgs)
        for key in ["list_rate", "question_rate", "hedge_rate", "code_rate", "caveat_rate"]:
            assert 0.0 <= result[key] <= 1.0


# ---------------------------------------------------------------------------
# extract_semantic
# ---------------------------------------------------------------------------

class TestExtractSemantic:
    def test_confident_no_hedges(self) -> None:
        msgs = [assistant("The answer is 42.")]
        result = extract_semantic(msgs)
        assert result == ["confident"]

    def test_hedging_with_hedge_word(self) -> None:
        msgs = [assistant("I think this might be correct.")]
        result = extract_semantic(msgs)
        assert result == ["hedging"]

    def test_admits_ignorance(self) -> None:
        msgs = [assistant("I don't know the answer to that.")]
        result = extract_semantic(msgs)
        assert result == ["admits_ignorance"]

    def test_admits_ignorance_i_cannot(self) -> None:
        msgs = [assistant("I cannot help with that.")]
        result = extract_semantic(msgs)
        assert result == ["admits_ignorance"]

    def test_speculating(self) -> None:
        msgs = [assistant("What if we tried a different approach?")]
        result = extract_semantic(msgs)
        assert result == ["speculating"]

    def test_one_per_assistant_message(self) -> None:
        msgs = [
            assistant("This is confident."),
            user("Thanks."),
            assistant("I think it might work."),
        ]
        result = extract_semantic(msgs)
        assert len(result) == 2

    def test_user_messages_excluded(self) -> None:
        msgs = [user("I think you're wrong.")]
        result = extract_semantic(msgs)
        assert result == []

    def test_admits_ignorance_takes_priority_over_speculating(self) -> None:
        msgs = [assistant("I don't know, perhaps it could be something.")]
        result = extract_semantic(msgs)
        assert result == ["admits_ignorance"]


# ---------------------------------------------------------------------------
# extract_decision_points
# ---------------------------------------------------------------------------

class TestExtractDecisionPoints:
    def test_asks_first_ending_question(self) -> None:
        msgs = [assistant("What would you like me to do?")]
        result = extract_decision_points(msgs)
        assert result == ["asks_first"]

    def test_assumes_and_acts_default(self) -> None:
        msgs = [assistant("Here is the implementation you requested.")]
        result = extract_decision_points(msgs)
        assert result == ["assumes_and_acts"]

    def test_offers_options_with_keyword(self) -> None:
        msgs = [assistant("You could use option A or option B.")]
        result = extract_decision_points(msgs)
        assert result == ["offers_options"]

    def test_offers_options_numbered_list(self) -> None:
        msgs = [assistant("1. First choice\n2. Second choice")]
        result = extract_decision_points(msgs)
        assert result == ["offers_options"]

    def test_decides_unilaterally(self) -> None:
        msgs = [assistant("I will handle this for you.")]
        result = extract_decision_points(msgs)
        assert result == ["decides_unilaterally"]

    def test_defers_to_user(self) -> None:
        msgs = [assistant("It's up to you which path to take.")]
        result = extract_decision_points(msgs)
        assert result == ["defers_to_user"]

    def test_one_per_assistant_message(self) -> None:
        msgs = [
            assistant("I will do this."),
            user("ok"),
            assistant("Your call on the next step."),
        ]
        result = extract_decision_points(msgs)
        assert len(result) == 2

    def test_user_messages_excluded(self) -> None:
        msgs = [user("What should I do?")]
        result = extract_decision_points(msgs)
        assert result == []


# ---------------------------------------------------------------------------
# extract_user_signals
# ---------------------------------------------------------------------------

class TestExtractUserSignals:
    def test_correction_no_prefix(self) -> None:
        msgs = [assistant("The answer is 5."), user("No, that's wrong.")]
        result = extract_user_signals(msgs)
        assert result == ["correction"]

    def test_actually_correction(self) -> None:
        msgs = [assistant("Paris is the capital."), user("Actually, I asked about Germany.")]
        result = extract_user_signals(msgs)
        assert result == ["correction"]

    def test_acceptance_thanks(self) -> None:
        msgs = [assistant("Here is your answer."), user("Thanks, perfect!")]
        result = extract_user_signals(msgs)
        assert result == ["acceptance"]

    def test_elaboration_request(self) -> None:
        msgs = [assistant("The system works."), user("Can you tell me more detail about it?")]
        result = extract_user_signals(msgs)
        assert result == ["elaboration_request"]

    def test_user_message_not_after_assistant_excluded(self) -> None:
        msgs = [user("Hello"), assistant("Hi there"), user("Thanks")]
        result = extract_user_signals(msgs)
        # Only the user message after assistant should be captured
        assert len(result) == 1
        assert result[0] == "acceptance"

    def test_empty_messages(self) -> None:
        result = extract_user_signals([])
        assert result == []

    def test_only_assistant_messages(self) -> None:
        msgs = [assistant("Hello."), assistant("Goodbye.")]
        result = extract_user_signals(msgs)
        assert result == []


# ---------------------------------------------------------------------------
# signals_to_distributions
# ---------------------------------------------------------------------------

class TestSignalsToDistributions:
    def _get_all_signals(self) -> tuple:
        msgs = [
            assistant("The answer is 42."),
            user("Thanks!"),
            assistant("I think this might work."),
            user("Great, perfect."),
        ]
        structural = extract_structural(msgs)
        semantic = extract_semantic(msgs)
        decisions = extract_decision_points(msgs)
        user_sigs = extract_user_signals(msgs)
        return structural, semantic, decisions, user_sigs

    def test_returns_all_four_dimensions(self) -> None:
        s, sem, dec, usr = self._get_all_signals()
        result = signals_to_distributions(s, sem, dec, usr)
        expected_dims = set(list_dimensions())
        assert set(result.keys()) == expected_dims

    def test_all_distributions_sum_to_one(self) -> None:
        s, sem, dec, usr = self._get_all_signals()
        result = signals_to_distributions(s, sem, dec, usr)
        for dim, dist in result.items():
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6, f"Dimension {dim} sums to {total}"

    def test_empty_signals_still_valid(self) -> None:
        structural = {
            "avg_length": 0.0, "list_rate": 0.0, "question_rate": 0.0,
            "hedge_rate": 0.0, "code_rate": 0.0, "caveat_rate": 0.0,
        }
        result = signals_to_distributions(structural, [], [], [])
        for dim in list_dimensions():
            assert dim in result
            assert abs(sum(result[dim].probs) - 1.0) < 1e-6

    def test_high_hedge_rate_favors_hedging(self) -> None:
        structural = {
            "avg_length": 100.0, "list_rate": 0.0, "question_rate": 0.0,
            "hedge_rate": 1.0, "code_rate": 0.0, "caveat_rate": 0.0,
        }
        semantic = ["hedging", "hedging", "hedging"]
        result = signals_to_distributions(structural, semantic, [], [])
        ep_dist = result["epistemic_style"]
        assert ep_dist["hedging"] > ep_dist["confident"]

    def test_long_responses_favor_thorough(self) -> None:
        structural = {
            "avg_length": 300.0, "list_rate": 0.0, "question_rate": 0.0,
            "hedge_rate": 0.0, "code_rate": 0.0, "caveat_rate": 0.0,
        }
        result = signals_to_distributions(structural, [], [], [])
        reg_dist = result["communication_register"]
        assert reg_dist["thorough"] > reg_dist["terse"]

    def test_short_responses_favor_terse(self) -> None:
        structural = {
            "avg_length": 20.0, "list_rate": 0.0, "question_rate": 0.0,
            "hedge_rate": 0.0, "code_rate": 0.0, "caveat_rate": 0.0,
        }
        result = signals_to_distributions(structural, [], [], [])
        reg_dist = result["communication_register"]
        assert reg_dist["terse"] > reg_dist["thorough"]

    def test_high_caveat_rate_favors_warns_frequently(self) -> None:
        structural = {
            "avg_length": 100.0, "list_rate": 0.0, "question_rate": 0.0,
            "hedge_rate": 0.0, "code_rate": 0.0, "caveat_rate": 0.8,
        }
        result = signals_to_distributions(structural, [], [], [])
        rc_dist = result["risk_caution"]
        assert rc_dist["warns_frequently"] > rc_dist["acts_immediately"]


# ---------------------------------------------------------------------------
# BehavioralObserver
# ---------------------------------------------------------------------------

class TestBehavioralObserver:
    def _make_observer(self) -> BehavioralObserver:
        return BehavioralObserver()

    def _sample_messages(self) -> list[dict]:
        return [
            assistant("The answer is 42."),
            user("Thanks!"),
            assistant("I'll proceed with the implementation."),
            user("Great."),
        ]

    def test_observe_returns_distributions_for_all_dimensions(self) -> None:
        obs = self._make_observer()
        result = obs.observe("developer", self._sample_messages())
        assert set(result.keys()) == set(list_dimensions())

    def test_observe_increments_count(self) -> None:
        obs = self._make_observer()
        assert obs.get_observation_count("developer") == 0
        obs.observe("developer", self._sample_messages())
        assert obs.get_observation_count("developer") == 1
        obs.observe("developer", self._sample_messages())
        assert obs.get_observation_count("developer") == 2

    def test_different_personas_tracked_separately(self) -> None:
        obs = self._make_observer()
        obs.observe("developer", self._sample_messages())
        obs.observe("writer", self._sample_messages())
        assert obs.get_observation_count("developer") == 1
        assert obs.get_observation_count("writer") == 1

    def test_unobserved_persona_count_is_zero(self) -> None:
        obs = self._make_observer()
        assert obs.get_observation_count("nonexistent") == 0

    def test_empty_message_list_handled_gracefully(self) -> None:
        obs = self._make_observer()
        result = obs.observe("developer", [])
        assert set(result.keys()) == set(list_dimensions())
        for dim, dist in result.items():
            assert abs(sum(dist.probs) - 1.0) < 1e-6

    def test_accumulated_distributions_returns_all_dimensions(self) -> None:
        obs = self._make_observer()
        obs.observe("developer", self._sample_messages())
        result = obs.get_accumulated_distributions("developer")
        assert set(result.keys()) == set(list_dimensions())

    def test_accumulated_distributions_no_observations_is_uniform(self) -> None:
        obs = self._make_observer()
        result = obs.get_accumulated_distributions("nobody")
        for dim in list_dimensions():
            assert dim in result
            n = len(list_states(dim))
            expected = 1.0 / n
            for prob in result[dim].probs:
                assert abs(prob - expected) < 1e-6

    def test_accumulated_distributions_sum_to_one(self) -> None:
        obs = self._make_observer()
        for _ in range(3):
            obs.observe("developer", self._sample_messages())
        result = obs.get_accumulated_distributions("developer")
        for dim, dist in result.items():
            assert abs(sum(dist.probs) - 1.0) < 1e-6
