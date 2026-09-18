"""Wrap any Python callable as a behaviorally aware agent.

The wrapped function receives the rendered behavioral context through its
``system`` parameter, and string results are recorded as agent turns.

Usage:
    from helios_mcp.harness import BehavioralHarness

    harness = BehavioralHarness(persona="developer")

    @harness
    def my_agent(messages: list[dict], system: str = "") -> str:
        return call_llm(messages, system=system)

    with BehavioralHarness(persona="developer") as h:
        response = call_llm(messages, system=h.get_context())
        h.observe(messages + [{"role": "assistant", "content": response}])
"""

from __future__ import annotations

import functools
import inspect
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .service import HeliosService, ObserveReport


class BehavioralHarness:
    """Context injection and observation for one persona over HeliosService."""

    def __init__(
        self,
        persona: str = "developer",
        helios_dir: Path | None = None,
        observe_every: int = 1,
        session_id: str | None = None,
    ) -> None:
        self.service = HeliosService(helios_dir or Path.home() / ".helios")
        self.persona = self.service.persona(persona)
        self.observe_every = observe_every
        # One harness is one conversation, so repeated observe() calls with a
        # growing message list do not count earlier turns twice.
        self.session_id = session_id or f"harness-{uuid.uuid4().hex}"
        self._call_count = 0

    def get_context(self) -> str:
        return str(self.service.context(self.persona)["behavioral_context"])

    def observe(self, messages: list[dict[str, Any]]) -> ObserveReport:
        return self.service.observe_messages(self.persona, messages, self.session_id)

    def should_negotiate(self) -> bool:
        return self.service.drift_report(self.persona)["negotiation_recommended"]

    def get_drift_summary(self) -> str | None:
        """The drift summary when a proposal is pending, else None."""
        report = self.service.drift_report(self.persona)
        return report["summary"] if report["negotiation_recommended"] else None

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Inject context into ``system`` if the function takes it; observe output."""
        has_system_param = "system" in inspect.signature(func).parameters

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self._call_count += 1
            if has_system_param:
                kwargs["system"] = self.get_context()
            result = func(*args, **kwargs)
            if self._call_count % self.observe_every == 0 and isinstance(result, str):
                messages = [*kwargs.get("messages", args[0] if args else []),
                            {"role": "assistant", "content": result}]
                self.observe(messages)
            return result

        return wrapper

    def __enter__(self) -> BehavioralHarness:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass
