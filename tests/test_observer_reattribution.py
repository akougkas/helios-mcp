"""Tests for BehavioralObserver.reattribute_hook_observations.

Covers the public re-attribution method that replaced cli.py's direct
reach into BehavioralObserver's private `_hook_observations` dict: the
fast-path hook handler writes raw events under "default" when it cannot
resolve the active persona, and callers like `negotiate` need those
observations counted against the requested persona instead.
"""

from __future__ import annotations

import pytest

from helios_mcp.hook_events import ToolUseEvent, UserPromptEvent
from helios_mcp.observer import BehavioralObserver

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def observer(tmp_path):
    return BehavioralObserver(helios_dir=tmp_path)


@pytest.fixture
def hook_events():
    """Minimal hook events for hook observation."""
    return [
        ToolUseEvent(tool_name="Read", tool_input_keys=("file_path",)),
        ToolUseEvent(tool_name="Grep", tool_input_keys=("pattern",)),
        UserPromptEvent(length=30, question_count=0),
    ]


# ---------------------------------------------------------------------------
# reattribute_hook_observations
# ---------------------------------------------------------------------------


class TestReattributeHookObservations:
    def test_reattributes_when_source_has_observations(
        self, observer, hook_events
    ) -> None:
        observer.observe_hooks("default", hook_events)

        moved = observer.reattribute_hook_observations("default", "developer")

        assert moved is True
        assert observer.get_hook_observation_count("developer") == 1

    def test_returns_false_when_source_has_no_observations(self, observer) -> None:
        moved = observer.reattribute_hook_observations("default", "developer")

        assert moved is False
        assert observer.get_hook_observation_count("developer") == 0

    def test_target_count_matches_source_after_multiple_observations(
        self, observer, hook_events
    ) -> None:
        observer.observe_hooks("default", hook_events)
        observer.observe_hooks("default", hook_events)

        moved = observer.reattribute_hook_observations("default", "developer")

        assert moved is True
        assert observer.get_hook_observation_count(
            "developer"
        ) == observer.get_hook_observation_count("default")
        assert observer.get_hook_observation_count("developer") == 2

    def test_reattributed_observations_feed_accumulated_distributions(
        self, observer, hook_events
    ) -> None:
        observer.observe_hooks("default", hook_events)
        observer.reattribute_hook_observations("default", "developer")

        dists = observer.get_accumulated_distributions("developer")

        assert observer.get_observation_count("developer") == 1
        for dist in dists.values():
            assert abs(sum(dist.probs) - 1.0) < 1e-6

    def test_reattribution_aliases_the_same_list_object(
        self, observer, hook_events
    ) -> None:
        observer.observe_hooks("default", hook_events)

        observer.reattribute_hook_observations("default", "developer")

        # Current behavior aliases the same underlying list rather than
        # copying it — appending further "default" hook observations is
        # visible on the re-attributed persona too. This is a change-
        # detector test that documents the existing aliasing semantics;
        # it must be preserved by the public method, not silently altered.
        observer.observe_hooks("default", hook_events)
        assert observer.get_hook_observation_count(
            "developer"
        ) == observer.get_hook_observation_count("default")

    def test_does_not_overwrite_existing_target_when_source_missing(
        self, observer, hook_events
    ) -> None:
        observer.observe_hooks("developer", hook_events)

        moved = observer.reattribute_hook_observations("default", "developer")

        assert moved is False
        assert observer.get_hook_observation_count("developer") == 1
