"""Turn the observation ledger into evidence counts for the drift posterior.

Two sets of counts come out, one per posterior:

- ``fingerprint`` is what the agent did: every selected turn contributes its
  soft label weighted by ``confidence ** confidence_exponent``. The soft label
  already spreads mass by the classifier's uncertainty, so the full confidence
  would discount the same doubt twice; on the founder's corpus the square root
  cut time to the first plausible proposal from 19 sessions to 8 with no
  stationary false positives. Diagnostics only.
- ``endorsed`` is what the user endorses. A turn the user did not correct
  counts toward what the agent did, weighted by how the user responded: an
  explicit approval at ``approval_weight``, moving on without comment at
  ``moved_on_weight``, and no response at ``neutral_weight``. Passive
  acceptance is weak evidence because users tolerate styles they would not
  choose; the founder's long accepted reports were fatigue, not approval.
  Only a grade at or below ``CORRECTED`` is a behavior correction. The model
  labeler grades "the outcome was wrong but the behavior was fine" at -0.5,
  which says nothing about style. A corrected turn with a ``correction_hint``
  puts its weight on the hinted state instead. A corrected turn without a hint
  spreads ``unhinted_correction_weight`` of its weight over every state except
  the labeled one, in proportion to ``1 - label``, which moves mass away from
  what the agent did without inventing a direction. The weight is low because
  on real sessions corrected turns look stylistically like all other turns:
  most corrections are about content, and at full weight they pull every
  dimension toward uniform. A hint on an uncorrected turn is a standing
  preference and adds ``standing_hint_weight`` toward the hinted state in
  place of that dimension's label. Rejected proposals add ``rejection_strength``
  pseudo-counts of the profile that was declared when the user said no.

Accepting a proposal absorbs the evidence it was computed from into the
declared profile. Counting that evidence again against the new profile would
pull the posterior past the accepted target and re-trigger drift, so each
dimension ignores turns first seen before its latest accept watermark.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from .drift import DEFAULT_CONFIG, DriftConfig
from .store import SOURCES, Proposal, TurnObservation
from .taxonomy import list_states

Counts = dict[str, dict[str, float]]

CORRECTED = -0.75
_APPROVED = 0.75
_MOVED_ON = 0.25


def grade_weight(endorsement: float | None, config: DriftConfig) -> float:
    """Weight of an uncorrected turn's label, by what the user did next."""
    if endorsement is None:
        return config.neutral_weight
    if endorsement >= _APPROVED:
        return config.approval_weight
    if endorsement >= _MOVED_ON:
        return config.moved_on_weight
    return config.neutral_weight


@dataclass(frozen=True)
class Evidence:
    fingerprint: Counts = field(default_factory=dict)
    endorsed: Counts = field(default_factory=dict)
    turns: int = 0
    ledger_rows: int = 0
    endorsed_turns: int = 0
    # Fingerprint counts and turn counts per model, for turns whose model is known.
    fingerprint_by_model: dict[str, Counts] = field(default_factory=dict)
    model_turns: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _Turn:
    first_row: int
    obs: TurnObservation
    llm_row: int | None = None
    model: str | None = None


def select_turns(observations: Iterable[TurnObservation]) -> tuple[list[_Turn], int]:
    """One observation per turn, by source precedence. Returns turns and row count.

    A turn keeps the ledger position of its first row, so a later relabel from
    a higher-precedence source does not make an already absorbed turn look new.
    """
    rank = {s: i for i, s in enumerate(SOURCES)}
    chosen: dict[tuple[str, str], _Turn] = {}
    rows = 0
    for row, obs in enumerate(observations):
        rows = row + 1
        key = (obs.session_id, obs.turn_id)
        current = chosen.get(key)
        llm_row = row if obs.source == "llm" else None
        if current is None:
            chosen[key] = _Turn(row, obs, llm_row, obs.model)
        elif rank[obs.source] < rank[current.obs.source]:
            chosen[key] = _Turn(current.first_row, obs,
                                current.llm_row if llm_row is None else llm_row,
                                current.model or obs.model)
        elif current.model is None and obs.model is not None:
            chosen[key] = replace(current, model=obs.model)
    return sorted(chosen.values(), key=lambda t: t.first_row), rows


def _add(counts: Counts, dim: str, dist: Mapping[str, float], weight: float) -> None:
    if weight <= 0.0:
        return
    bucket = counts.setdefault(dim, {})
    for state, p in dist.items():
        bucket[state] = bucket.get(state, 0.0) + weight * p


def _complement(dim: str, label: Mapping[str, float]) -> dict[str, float]:
    away = {s: 1.0 - label.get(s, 0.0) for s in list_states(dim)}
    total = sum(away.values())
    return {s: v / total for s, v in away.items()}


def accept_watermarks(proposals: Iterable[Proposal]) -> dict[str, int]:
    """Per dimension, the ledger row count absorbed by the latest accept."""
    marks: dict[str, int] = {}
    for p in proposals:
        if p.status in ("accepted", "auto_accepted"):
            for dim in p.decided_dimensions:
                marks[dim] = max(marks.get(dim, 0), p.observation_count)
    return marks


def estimate(
    observations: Iterable[TurnObservation],
    proposals: Iterable[Proposal] = (),
    config: DriftConfig = DEFAULT_CONFIG,
    llm_labels: bool = False,
) -> Evidence:
    """Fingerprint and endorsed counts.

    With ``llm_labels``, only turns that have a model label count toward the
    endorsed posterior, positioned at that label's ledger row; heuristic-only
    turns still feed the fingerprint. Otherwise the session-end relabel would
    swap one label distribution for another under the posterior with no change
    in behavior.
    """
    proposals = list(proposals)
    marks = accept_watermarks(proposals)
    turns, rows = select_turns(observations)

    fingerprint: Counts = {}
    endorsed: Counts = {}
    by_model: dict[str, Counts] = {}
    model_turns: dict[str, int] = {}
    def weight(obs: TurnObservation, dim: str) -> float:
        return float(obs.confidence_for(dim) ** config.confidence_exponent)

    endorsed_turns = 0
    for turn in turns:
        obs = turn.obs
        model_counts = None
        if turn.model is not None:
            model_counts = by_model.setdefault(turn.model, {})
            model_turns[turn.model] = model_turns.get(turn.model, 0) + 1
        for dim, label in obs.labels.items():
            _add(fingerprint, dim, label, weight(obs, dim))
            if model_counts is not None:
                _add(model_counts, dim, label, weight(obs, dim))

        position = turn.first_row
        if llm_labels:
            if turn.llm_row is None:
                continue
            position = turn.llm_row
        endorsed_turns += 1
        hints = obs.correction_hint or {}
        live = {
            dim for dim in {*obs.labels, *hints}
            if position >= marks.get(dim, 0)
        }
        corrected = obs.endorsement is not None and obs.endorsement <= CORRECTED
        if not corrected:
            # A hint on an uncorrected turn is a standing preference ("keep it
            # brief"): it speaks for its dimensions at reduced weight, and the
            # rest of the turn counts as uncorrected.
            for dim, state in hints.items():
                if dim in live:
                    _add(endorsed, dim, {state: 1.0}, config.standing_hint_weight)
            grade = grade_weight(obs.endorsement, config)
            for dim in (live & obs.labels.keys()) - hints.keys():
                _add(endorsed, dim, obs.labels[dim], grade * weight(obs, dim))
            continue

        strength = -(obs.endorsement or 0.0)
        if hints:
            # The correction names what it is about, so dimensions it does not
            # mention get no evidence from this turn either way.
            for dim, state in hints.items():
                if dim in live:
                    _add(endorsed, dim, {state: 1.0}, strength)
        else:
            for dim in live & obs.labels.keys():
                _add(endorsed, dim, _complement(dim, obs.labels[dim]),
                     strength * config.unhinted_correction_weight * weight(obs, dim))

    for p in proposals:
        if p.status != "rejected":
            continue
        for dim in p.decided_dimensions:
            if p.observation_count > marks.get(dim, 0) and dim in p.changes:
                _add(endorsed, dim, p.changes[dim].declared, config.rejection_strength)

    return Evidence(fingerprint, endorsed, len(turns), rows, endorsed_turns,
                    by_model, model_turns)
