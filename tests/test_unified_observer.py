"""Tests for unified observation pipeline (Task 1.5).

Verifies that BehavioralObserver handles both text messages and hook
events, and correctly blends distributions from both sources.
"""

import json
import time
from pathlib import Path

import pytest

from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.hook_events import (
    SessionEvent,
    SubagentEvent,
    ToolUseEvent,
    UserPromptEvent,
)
from helios_mcp.observer import BehavioralObserver
from helios_mcp.taxonomy import list_dimensions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def observer(tmp_path):
    return BehavioralObserver(helios_dir=tmp_path)


@pytest.fixture
def messages():
    """Minimal conversation messages for text observation."""
    return [
        {"role": "user", "content": "Fix the bug in server.py"},
        {"role": "assistant", "content": "I'll look at the code and fix it."},
        {"role": "user", "content": "thanks"},
    ]


@pytest.fixture
def hook_events():
    """Minimal hook events for hook observation."""
    return [
        ToolUseEvent(tool_name="Read", tool_input_keys=("file_path",)),
        ToolUseEvent(tool_name="Grep", tool_input_keys=("pattern",)),
        ToolUseEvent(tool_name="Edit", tool_input_keys=("file_path", "old_string", "new_string")),
        UserPromptEvent(length=30, question_count=0),
    ]


# ---------------------------------------------------------------------------
# Text observation (backward compatibility)
# ---------------------------------------------------------------------------


class TestTextObservation:
    def test_observe_returns_distributions(self, observer, messages):
        dists = observer.observe("dev", messages)
        assert len(dists) == 4
        for dim in list_dimensions():
            assert dim in dists
            assert isinstance(dists[dim], BehavioralDistribution)

    def test_observe_persists(self, observer, messages):
        observer.observe("dev", messages)
        assert observer.get_text_observation_count("dev") == 1

    def test_multiple_text_observations(self, observer, messages):
        observer.observe("dev", messages)
        observer.observe("dev", messages)
        assert observer.get_text_observation_count("dev") == 2


# ---------------------------------------------------------------------------
# Hook observation
# ---------------------------------------------------------------------------


class TestHookObservation:
    def test_observe_hooks_returns_distributions(self, observer, hook_events):
        dists = observer.observe_hooks("dev", hook_events)
        assert len(dists) == 4
        for dim in list_dimensions():
            assert dim in dists
            assert isinstance(dists[dim], BehavioralDistribution)

    def test_observe_hooks_persists(self, observer, hook_events):
        observer.observe_hooks("dev", hook_events)
        assert observer.get_hook_observation_count("dev") == 1

    def test_multiple_hook_observations(self, observer, hook_events):
        observer.observe_hooks("dev", hook_events)
        observer.observe_hooks("dev", hook_events)
        assert observer.get_hook_observation_count("dev") == 2

    def test_empty_events(self, observer):
        dists = observer.observe_hooks("dev", [])
        assert len(dists) == 4

    def test_tool_only_events(self, observer):
        events = [
            ToolUseEvent(tool_name="Read"),
            ToolUseEvent(tool_name="Edit"),
        ]
        dists = observer.observe_hooks("dev", events)
        assert len(dists) == 4


# ---------------------------------------------------------------------------
# Unified observation count
# ---------------------------------------------------------------------------


class TestObservationCount:
    def test_text_only_count(self, observer, messages):
        observer.observe("dev", messages)
        assert observer.get_observation_count("dev") == 1
        assert observer.get_text_observation_count("dev") == 1
        assert observer.get_hook_observation_count("dev") == 0

    def test_hook_only_count(self, observer, hook_events):
        observer.observe_hooks("dev", hook_events)
        assert observer.get_observation_count("dev") == 1
        assert observer.get_text_observation_count("dev") == 0
        assert observer.get_hook_observation_count("dev") == 1

    def test_combined_count(self, observer, messages, hook_events):
        observer.observe("dev", messages)
        observer.observe_hooks("dev", hook_events)
        assert observer.get_observation_count("dev") == 2

    def test_no_observations(self, observer):
        assert observer.get_observation_count("dev") == 0


# ---------------------------------------------------------------------------
# Blended distributions
# ---------------------------------------------------------------------------


class TestBlendedDistributions:
    def test_text_only_accumulated(self, observer, messages):
        observer.observe("dev", messages)
        dists = observer.get_accumulated_distributions("dev")
        assert len(dists) == 4
        for dim in list_dimensions():
            total = sum(dists[dim].probs)
            assert abs(total - 1.0) < 1e-6

    def test_hook_only_accumulated(self, observer, hook_events):
        observer.observe_hooks("dev", hook_events)
        dists = observer.get_accumulated_distributions("dev")
        assert len(dists) == 4
        for dim in list_dimensions():
            total = sum(dists[dim].probs)
            assert abs(total - 1.0) < 1e-6

    def test_blended_accumulated(self, observer, messages, hook_events):
        observer.observe("dev", messages)
        observer.observe_hooks("dev", hook_events)
        dists = observer.get_accumulated_distributions("dev")
        assert len(dists) == 4
        for dim in list_dimensions():
            total = sum(dists[dim].probs)
            assert abs(total - 1.0) < 1e-6

    def test_no_observations_returns_uniform(self, observer):
        dists = observer.get_accumulated_distributions("dev")
        for dim in list_dimensions():
            assert dists[dim].normalized_entropy() > 0.99

    def test_blended_differs_from_either_source(self, observer, messages, hook_events):
        """Blended distributions should not be identical to either source alone."""
        observer.observe("dev", messages)
        text_dists = observer.get_accumulated_distributions("dev")

        observer.observe_hooks("dev", hook_events)
        blended_dists = observer.get_accumulated_distributions("dev")

        # At least one dimension should differ between text-only and blended
        any_different = False
        for dim in list_dimensions():
            if text_dists[dim] != blended_dists[dim]:
                any_different = True
                break
        assert any_different

    def test_configurable_weights(self, observer, messages, hook_events):
        """Changing weights should change the blended result."""
        observer.observe("dev", messages)
        observer.observe_hooks("dev", hook_events)

        observer.TEXT_WEIGHT = 0.8
        observer.HOOK_WEIGHT = 0.2
        dists_text_heavy = observer.get_accumulated_distributions("dev")

        observer.TEXT_WEIGHT = 0.2
        observer.HOOK_WEIGHT = 0.8
        dists_hook_heavy = observer.get_accumulated_distributions("dev")

        # At least one dimension should differ
        any_different = False
        for dim in list_dimensions():
            if dists_text_heavy[dim] != dists_hook_heavy[dim]:
                any_different = True
                break
        assert any_different


# ---------------------------------------------------------------------------
# Persistence across instances
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_text_persists_across_instances(self, tmp_path, messages):
        obs1 = BehavioralObserver(helios_dir=tmp_path)
        obs1.observe("dev", messages)

        obs2 = BehavioralObserver(helios_dir=tmp_path)
        assert obs2.get_text_observation_count("dev") == 1

    def test_hooks_persist_across_instances(self, tmp_path, hook_events):
        obs1 = BehavioralObserver(helios_dir=tmp_path)
        obs1.observe_hooks("dev", hook_events)

        obs2 = BehavioralObserver(helios_dir=tmp_path)
        assert obs2.get_hook_observation_count("dev") == 1

    def test_both_persist_across_instances(self, tmp_path, messages, hook_events):
        obs1 = BehavioralObserver(helios_dir=tmp_path)
        obs1.observe("dev", messages)
        obs1.observe_hooks("dev", hook_events)

        obs2 = BehavioralObserver(helios_dir=tmp_path)
        assert obs2.get_observation_count("dev") == 2
        dists = obs2.get_accumulated_distributions("dev")
        assert len(dists) == 4

    def test_no_helios_dir_works_in_memory(self, messages, hook_events):
        obs = BehavioralObserver(helios_dir=None)
        obs.observe("dev", messages)
        obs.observe_hooks("dev", hook_events)
        assert obs.get_observation_count("dev") == 2
        dists = obs.get_accumulated_distributions("dev")
        assert len(dists) == 4
