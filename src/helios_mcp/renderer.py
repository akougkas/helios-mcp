"""Render a resolved profile as the context text injected at session start.

Each dimension is a distribution, so the text keeps its shape: the dominant
tendency, then any secondary tendency with real mass, each with a frequency
word and its share, plus how settled the dimension is overall. Rendering only
the argmax would tell the agent "always terse" when the profile says terse
half the time and thorough a third of it.
"""

from __future__ import annotations

from .distribution import BehavioralDistribution
from .profile import BehavioralProfile
from .taxonomy import get_state_label

_DIMENSION_HEADINGS: dict[str, str] = {
    "epistemic_style": "Epistemic style",
    "interaction_agency": "Interaction agency",
    "communication_register": "Communication register",
    "risk_caution": "Risk and caution",
}

# A tendency below this share is noise at the resolution of prose.
_MIN_SHARE = 0.15
_MAX_TENDENCIES = 3


def _frequency(p: float) -> str:
    if p >= 0.6:
        return "Usually"
    if p >= 0.35:
        return "Often"
    return "Sometimes"


def _settledness(normalized_entropy: float) -> str:
    if normalized_entropy < 0.3:
        return "settled"
    if normalized_entropy <= 0.6:
        return "mixed"
    return "varied; adapt to context"


def tendencies(dist: BehavioralDistribution) -> list[tuple[str, float]]:
    """States worth mentioning, most likely first. Always includes the dominant."""
    ranked = sorted(zip(dist.states, dist.probs, strict=True),
                    key=lambda sp: sp[1], reverse=True)
    kept = [ranked[0]] + [sp for sp in ranked[1:] if sp[1] >= _MIN_SHARE]
    return kept[:_MAX_TENDENCIES]


class BehavioralRenderer:
    def render(self, profile: BehavioralProfile, persona_name: str = "") -> str:
        subject = f" for the '{persona_name}' persona" if persona_name else ""
        lines = [
            f"Behavioral profile{subject}, learned from the user's feedback. "
            "Treat it as defaults; explicit instructions in the conversation win.",
            "",
        ]
        for dim, heading in _DIMENSION_HEADINGS.items():
            dist = profile.distributions.get(dim)
            if dist is None:
                continue
            lines.append(f"{heading} ({_settledness(dist.normalized_entropy())}):")
            for state, p in tendencies(dist):
                lines.append(f"- {_frequency(p)} ({p:.0%}): "
                             f"{get_state_label(dim, state)}.")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
