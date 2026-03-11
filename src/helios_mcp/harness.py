"""Behavioral harness for Helios v2.

Wraps any Python callable as a behaviorally-aware agent.
The wrapped function receives behavioral context injected into its call,
and its outputs are automatically observed to update behavioral distributions.

Usage:
    from helios_mcp.harness import BehavioralHarness

    harness = BehavioralHarness(persona='developer')

    @harness
    def my_agent(messages: list[dict], system: str = "") -> str:
        # system= will be populated with behavioral context
        return call_llm(messages, system=system)

    # Or as a context manager for explicit session tracking:
    with BehavioralHarness(persona='developer') as h:
        context = h.get_context()
        response = call_llm(messages, system=context)
        h.observe(messages + [{"role": "assistant", "content": response}])
"""
from __future__ import annotations

import functools
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from .drift import DriftDetector
from .hierarchy import IdentityHierarchy
from .observer import BehavioralObserver
from .profile import BehavioralProfile
from .renderer import BehavioralRenderer

logger = logging.getLogger(__name__)


class BehavioralHarness:
    """Wraps any callable agent with behavioral context injection and observation."""

    def __init__(
        self,
        persona: str = "developer",
        helios_dir: Optional[Path] = None,
        drift_threshold: float = 0.30,
        observe_every: int = 1,
        negotiate_after: int = 20,
    ) -> None:
        """Initialise the harness.

        Args:
            persona: Name of the persona to load from the hierarchy.
            helios_dir: Path to the Helios configuration directory.
                        Defaults to ~/.helios.
            drift_threshold: KL-divergence total above which drift is flagged.
            observe_every: Observe after every N calls (1 = every call).
            negotiate_after: Suggest negotiation after this many observations.
        """
        self.persona = persona
        self.helios_dir = helios_dir or Path.home() / ".helios"
        self.drift_threshold = drift_threshold
        self.observe_every = observe_every
        self.negotiate_after = negotiate_after

        self._renderer = BehavioralRenderer()
        self._observer = BehavioralObserver()
        self._detector = DriftDetector()
        self._call_count: int = 0
        self._profile: Optional[BehavioralProfile] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_context(self) -> str:
        """Render the current behavioral profile as system prompt text.

        Returns:
            A multi-line string suitable for use as a system prompt section.
        """
        profile = self._load_profile()
        return self._renderer.render(profile, self.persona)

    def observe(self, messages: list[dict]) -> None:
        """Pass messages to the observer.

        Args:
            messages: Conversation messages with 'role' and 'content' keys.
        """
        self._observer.observe(self.persona, messages)

    def should_negotiate(self) -> bool:
        """Return True if sufficient observations exist and drift exceeds threshold.

        Returns:
            True if observation_count >= negotiate_after AND drift exceeds threshold.
        """
        count = self._observer.get_observation_count(self.persona)
        if count < self.negotiate_after:
            return False

        profile = self._load_profile()
        observed = self._observer.get_accumulated_distributions(self.persona)
        result = self._detector.compute_drift(
            profile.distributions, observed, count
        )
        return bool(result.total_drift >= self.drift_threshold)

    def get_drift_summary(self) -> Optional[str]:
        """Return None if no observations, else a brief one-line drift summary.

        Returns:
            None when there are no observations or drift is below threshold.
            A summary string when drift is detected.
        """
        count = self._observer.get_observation_count(self.persona)
        if count == 0:
            return None

        profile = self._load_profile()
        observed = self._observer.get_accumulated_distributions(self.persona)
        result = self._detector.compute_drift(
            profile.distributions, observed, count
        )

        if result.total_drift < self.drift_threshold:
            return None

        dims_exceeding = [
            dim for dim, kl in result.per_dimension.items()
            if kl >= self._detector.PER_DIM_THRESHOLD
        ]
        dims = ", ".join(dims_exceeding) if dims_exceeding else "multiple dimensions"
        return (
            f"Behavioral drift detected in {self.persona}: {dims} "
            f"(score: {result.total_drift:.2f}). Run negotiate() to review."
        )

    # ------------------------------------------------------------------
    # Decorator support
    # ------------------------------------------------------------------

    def __call__(self, func: Callable) -> Callable:
        """Decorator: wrap func with behavioral context injection and observation.

        If func has a 'system' parameter, injects the rendered behavioral context
        as a kwarg override. After calling func, if the return value is a string,
        creates an assistant message and calls observe().

        Args:
            func: The callable to wrap.

        Returns:
            The wrapped callable with functools.wraps applied.
        """
        sig = inspect.signature(func)
        has_system_param = "system" in sig.parameters

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self._call_count += 1
            should_observe = (self._call_count % self.observe_every) == 0

            if has_system_param:
                kwargs["system"] = self.get_context()

            result = func(*args, **kwargs)

            if should_observe and isinstance(result, str):
                # Build a minimal message list to record the output
                obs_messages: list[dict] = [
                    {"role": "assistant", "content": result}
                ]
                self._observer.observe(self.persona, obs_messages)

            return result

        return wrapper

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "BehavioralHarness":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_profile(self) -> BehavioralProfile:
        """Load the behavioral profile via IdentityHierarchy.resolve().

        Returns:
            The resolved BehavioralProfile for this persona.
        """
        if self._profile is None:
            hierarchy = IdentityHierarchy(self.helios_dir)
            self._profile = hierarchy.resolve(self.persona)
        return self._profile
