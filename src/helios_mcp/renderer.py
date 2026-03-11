"""Behavioral profile renderer — converts a BehavioralProfile into system prompt text."""
from __future__ import annotations

from .profile import BehavioralProfile
from .taxonomy import get_state_label

_DIMENSION_HEADINGS: dict[str, str] = {
    "epistemic_style": "EPISTEMIC STYLE",
    "interaction_agency": "INTERACTION AGENCY",
    "communication_register": "COMMUNICATION REGISTER",
    "risk_caution": "RISK AND CAUTION",
}

_ENTROPY_HIGH_NOTE = (
    "Note: this dimension shows high behavioral diversity — adapt to context."
)


def _entropy_label(normalized_entropy: float) -> str:
    """Map normalized entropy to a human-readable confidence label."""
    if normalized_entropy < 0.3:
        return "high"
    if normalized_entropy <= 0.6:
        return "moderate"
    return "uncertain"


class BehavioralRenderer:
    """Renders a BehavioralProfile as system prompt text."""

    def render(self, profile: BehavioralProfile, persona_name: str = "") -> str:
        """Return system prompt text describing the behavioral profile.

        Args:
            profile: The behavioral profile to render.
            persona_name: Optional name used in the header line.

        Returns:
            A multi-line string suitable for use as a system prompt section.
        """
        if persona_name:
            header = (
                f"You are operating with the following behavioral profile "
                f"for the '{persona_name}' persona."
            )
        else:
            header = "You are operating with the following behavioral profile."

        lines: list[str] = [header, ""]

        for dim, heading in _DIMENSION_HEADINGS.items():
            dist = profile.distributions.get(dim)
            if dist is None:
                continue

            ne = dist.normalized_entropy()
            label = _entropy_label(ne)
            dominant_state = dist.most_likely()
            state_label = get_state_label(dim, dominant_state)

            lines.append(f"{heading} (confidence: {label}):")
            lines.append(state_label)
            if ne > 0.6:
                lines.append(_ENTROPY_HIGH_NOTE)
            lines.append("")

        lines.append(
            "These behavioral patterns reflect accumulated preferences. "
            "Follow them as defaults, adapting to explicit user instructions when given."
        )

        return "\n".join(lines)
