"""Render a resolved profile as the context text injected at session start.

Each dimension is a distribution, so the text keeps its shape: the dominant
tendency, then any secondary tendency with real mass, each with a frequency
word and its share, plus how settled the dimension is overall. Rendering only
the argmax would tell the agent "always terse" when the profile says terse
half the time and thorough a third of it.

Models differ in how they drift from a user's preferences, so the text can
end with a block per model naming where that model's own fingerprint departs
credibly from the profile. When the caller does not know which model will
read the text, it gets a block for each of the most observed models that
have such departures, and each model applies the block with its own name.
"""

from __future__ import annotations

from collections.abc import Sequence

from .distribution import BehavioralDistribution
from .drift import DimensionDrift, DriftAssessment
from .profile import BehavioralProfile
from .taxonomy import get_state_label

_DIMENSION_HEADINGS: dict[str, str] = {
    "epistemic_style": "Epistemic style",
    "interaction_agency": "Interaction agency",
    "communication_register": "Communication register",
    "risk_caution": "Risk and caution",
    "structure": "Structure",
    "sycophancy": "Candor",
    "narration": "Narration",
    "specificity": "Specificity",
    "pushback": "Under pushback",
}

# A tendency below this share is noise at the resolution of prose.
_MIN_SHARE = 0.15
_MAX_TENDENCIES = 3
# Model blocks when the reader's model is unknown, and lines per block.
_MAX_MODELS = 2
_MAX_DEVIATIONS = 3


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


def _deviation_line(drift: DimensionDrift) -> str:
    gap = {s: drift.posterior_mean[s] - drift.declared[s] for s in drift.declared}
    over = max(gap, key=gap.__getitem__)
    under = min(gap, key=gap.__getitem__)
    heading = _DIMENSION_HEADINGS.get(drift.dimension, drift.dimension)
    return (f"- {heading}: you tend to {get_state_label(drift.dimension, over)} "
            f"(about {drift.posterior_mean[over]:.0%} of your turns; the profile "
            f"has {drift.declared[over]:.0%}). Lean toward: "
            f"{get_state_label(drift.dimension, under)}.")


def model_blocks(fingerprints: Sequence[tuple[str, DriftAssessment]],
                 model: str | None = None) -> list[str]:
    """Counter-tendency lines per model, given fingerprints most observed first.

    With ``model`` set, only that model's block; otherwise up to two models
    that have at least one credible departure.
    """
    lines: list[str] = []
    shown = 0
    for name, assessment in fingerprints:
        if model is not None and name != model:
            continue
        credible = [r for r in assessment.dimensions.values() if r.tier == "strong"]
        drifts = sorted(credible, key=lambda r: r.divergence,
                        reverse=True)[:_MAX_DEVIATIONS]
        if not drifts:
            continue
        lines.append(f"If you are {name}:")
        lines.extend(_deviation_line(r) for r in drifts)
        lines.append("")
        shown += 1
        if shown == _MAX_MODELS:
            break
    if not lines:
        return []
    header = ("Tendencies to counter, observed in your past sessions." if model
              else "Model-specific tendencies to counter, observed in past "
              "sessions. Apply only the block for the model you are.")
    return [header, "", *lines]


class BehavioralRenderer:
    def render(self, profile: BehavioralProfile, persona_name: str = "",
               fingerprints: Sequence[tuple[str, DriftAssessment]] = (),
               model: str | None = None) -> str:
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
        lines.extend(model_blocks(fingerprints, model))
        return "\n".join(lines).rstrip() + "\n"
