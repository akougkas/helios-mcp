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

``estimate_ledger`` keeps a checkpoint of the tallies next to the ledger so a
Stop hook that appends a few new turns costs milliseconds instead of a full
scan. The checkpoint only ever extends: a row for a turn it has already
counted (the session-end relabel, a model backfill) or any change to the
config, label policy or accept watermarks triggers one full rebuild, so the
result always equals ``estimate`` over the whole ledger.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Collection, Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .atomic_ops import atomic_write_text
from .drift import DEFAULT_CONFIG, DriftConfig
from .security import persona_path
from .store import (
    SOURCES,
    ObservationStore,
    Proposal,
    TurnObservation,
    is_open_turn,
)
from .taxonomy import list_states

logger = logging.getLogger(__name__)

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


def select_turns(observations: Iterable[TurnObservation], start_row: int = 0,
                 ) -> tuple[list[_Turn], int]:
    """One observation per turn, by source precedence. Returns turns and row count.

    A turn keeps the ledger position of its first row, so a later relabel from
    a higher-precedence source does not make an already absorbed turn look new.
    The exception is a settled row replacing an open one: the open row carried
    no reply, so nothing of it was absorbed, and the reply is as new as its row.
    Rows are numbered from ``start_row``, and the count returned includes it.
    """
    source_rank = {s: i for i, s in enumerate(SOURCES)}

    def rank(obs: TurnObservation) -> tuple[int, bool]:
        # Source first, so the label-source policy holds while a resumed turn
        # waits for its model relabel; then a settled row over an open one.
        return source_rank[obs.source], is_open_turn(obs.turn_id)

    chosen: dict[tuple[str, str], _Turn] = {}
    rows = start_row
    for row, obs in enumerate(observations, start_row):
        rows = row + 1
        key = obs.turn_key
        current = chosen.get(key)
        llm_row = row if obs.source == "llm" else None
        if current is None:
            chosen[key] = _Turn(row, obs, llm_row, obs.model)
        elif rank(obs) < rank(current.obs):
            settles = (is_open_turn(current.obs.turn_id)
                       and not is_open_turn(obs.turn_id))
            chosen[key] = _Turn(row if settles else current.first_row, obs,
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


@dataclass
class _Tally:
    """Evidence counts before rejection pseudo-counts, extendable turn by turn."""

    fingerprint: Counts = field(default_factory=dict)
    endorsed: Counts = field(default_factory=dict)
    by_model: dict[str, Counts] = field(default_factory=dict)
    model_turns: dict[str, int] = field(default_factory=dict)
    turns: int = 0
    endorsed_turns: int = 0

    def add(self, turns: Iterable[_Turn], marks: Mapping[str, int],
            config: DriftConfig, llm_labels: bool,
            explicit_only: Collection[str] = ()) -> None:
        def weight(obs: TurnObservation, dim: str) -> float:
            return float(obs.confidence_for(dim) ** config.confidence_exponent)

        fingerprint, endorsed = self.fingerprint, self.endorsed
        for turn in turns:
            self.turns += 1
            obs = turn.obs
            model_counts = None
            if turn.model is not None:
                model_counts = self.by_model.setdefault(turn.model, {})
                self.model_turns[turn.model] = self.model_turns.get(turn.model, 0) + 1
            for dim, label in obs.labels.items():
                _add(fingerprint, dim, label, weight(obs, dim))
                if model_counts is not None:
                    _add(model_counts, dim, label, weight(obs, dim))

            position = turn.first_row
            if llm_labels:
                if turn.llm_row is None:
                    continue
                position = turn.llm_row
            self.endorsed_turns += 1
            hints = obs.correction_hint or {}
            live = {
                dim for dim in {*obs.labels, *hints}
                if position >= marks.get(dim, 0)
            }
            corrected = obs.endorsement is not None and obs.endorsement <= CORRECTED
            if not corrected:
                # A hint on an uncorrected turn is a standing preference ("keep
                # it brief"): it speaks for its dimensions at reduced weight, and
                # the rest of the turn counts as uncorrected.
                for dim, state in hints.items():
                    if dim in live:
                        _add(endorsed, dim, {state: 1.0}, config.standing_hint_weight)
                grade = grade_weight(obs.endorsement, config)
                approved = (obs.endorsement is not None
                            and obs.endorsement >= _APPROVED)
                for dim in (live & obs.labels.keys()) - hints.keys():
                    if dim in explicit_only and not approved:
                        # The user declared this dimension, so a turn they
                        # merely moved on from says nothing new about it.
                        continue
                    _add(endorsed, dim, obs.labels[dim], grade * weight(obs, dim))
                continue

            strength = -(obs.endorsement or 0.0)
            if hints:
                # The correction names what it is about, so dimensions it does
                # not mention get no evidence from this turn either way.
                for dim, state in hints.items():
                    if dim in live:
                        _add(endorsed, dim, {state: 1.0}, strength)
            else:
                for dim in live & obs.labels.keys():
                    _add(endorsed, dim, _complement(dim, obs.labels[dim]),
                         strength * config.unhinted_correction_weight
                         * weight(obs, dim))

    def evidence(self, rows: int, proposals: Iterable[Proposal],
                 marks: Mapping[str, int], config: DriftConfig) -> Evidence:
        endorsed = {dim: dict(c) for dim, c in self.endorsed.items()}
        for p in proposals:
            if p.status != "rejected":
                continue
            for dim in p.decided_dimensions:
                if p.observation_count > marks.get(dim, 0) and dim in p.changes:
                    _add(endorsed, dim, p.changes[dim].declared,
                         config.rejection_strength)
        return Evidence(
            {dim: dict(c) for dim, c in self.fingerprint.items()}, endorsed,
            self.turns, rows, self.endorsed_turns,
            {m: {dim: dict(c) for dim, c in counts.items()}
             for m, counts in self.by_model.items()},
            dict(self.model_turns),
        )


def estimate(
    observations: Iterable[TurnObservation],
    proposals: Iterable[Proposal] = (),
    config: DriftConfig = DEFAULT_CONFIG,
    llm_labels: bool = False,
    explicit_only: Collection[str] = (),
) -> Evidence:
    """Fingerprint and endorsed counts.

    On ``explicit_only`` dimensions, the ones a declared artifact set, an
    uncorrected turn counts toward endorsed only when the user approved it;
    corrections, hints and rejections count as everywhere else.

    With ``llm_labels``, only turns that have a model label count toward the
    endorsed posterior, positioned at that label's ledger row; heuristic-only
    turns still feed the fingerprint. Otherwise the session-end relabel would
    swap one label distribution for another under the posterior with no change
    in behavior.
    """
    proposals = list(proposals)
    marks = accept_watermarks(proposals)
    turns, rows = select_turns(observations)
    tally = _Tally()
    tally.add(turns, marks, config, llm_labels, explicit_only)
    return tally.evidence(rows, proposals, marks, config)


_CHECKPOINT_VERSION = 1
_TAIL_BYTES = 256


def _tail_digest(store: ObservationStore, persona: str, offset: int) -> str:
    """Digest of the bytes just before ``offset``, to notice a rewritten ledger."""
    start = max(0, offset - _TAIL_BYTES)
    with store.path(persona).open("rb") as f:
        f.seek(start)
        return hashlib.sha256(f.read(offset - start)).hexdigest()


def _load_checkpoint(store: ObservationStore, persona: str,
                     stamp: dict[str, Any]) -> dict[str, Any] | None:
    path = persona_path(store.root, persona, ".evidence.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("stamp") != stamp:
            return None
        offset = data["offset"]
        size = store.path(persona).stat().st_size
        if not 0 < offset <= size or data["tail"] != _tail_digest(
                store, persona, offset):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def estimate_ledger(
    store: ObservationStore,
    persona: str,
    proposals: Iterable[Proposal] = (),
    config: DriftConfig = DEFAULT_CONFIG,
    llm_labels: bool = False,
    explicit_only: Collection[str] = (),
) -> Evidence:
    """``estimate`` over the persona's ledger, extending a saved checkpoint."""
    proposals = list(proposals)
    marks = accept_watermarks(proposals)
    explicit = sorted(set(explicit_only))
    stamp = {"version": _CHECKPOINT_VERSION, "config": asdict(config),
             "llm_labels": llm_labels, "marks": marks, "explicit_only": explicit}
    data = _load_checkpoint(store, persona, stamp)
    if data is not None:
        start, rows = data["offset"], data["rows"]
        seen = {(sid, tid) for sid, tid in data["turn_keys"]}
        tally = _Tally(data["fingerprint"], data["endorsed"], data["by_model"],
                       data["model_turns"], data["turns"], data["endorsed_turns"])
    else:
        start, rows, seen, tally = 0, 0, set(), _Tally()

    offset = start
    new: list[TurnObservation] = []
    for _, end, obs in store.scan(persona, start):
        offset = end
        if obs is not None:
            new.append(obs)
    if data is not None and any(o.turn_key in seen for o in new):
        # A new row for a turn already counted can change that turn's label,
        # model or position, which an append-only tally cannot express.
        return _rebuild(store, persona, proposals, marks, config, llm_labels,
                        explicit, stamp)

    turns, rows = select_turns(new, rows)
    tally.add(turns, marks, config, llm_labels, explicit)
    if offset != start:
        seen.update(t.obs.turn_key for t in turns)
        _save_checkpoint(store, persona, stamp, offset, rows, seen, tally)
    return tally.evidence(rows, proposals, marks, config)


def _rebuild(store: ObservationStore, persona: str, proposals: list[Proposal],
             marks: dict[str, int], config: DriftConfig, llm_labels: bool,
             explicit_only: list[str], stamp: dict[str, Any]) -> Evidence:
    offset = 0
    rows: list[TurnObservation] = []
    for _, end, obs in store.scan(persona):
        offset = end
        if obs is not None:
            rows.append(obs)
    turns, count = select_turns(rows)
    tally = _Tally()
    tally.add(turns, marks, config, llm_labels, explicit_only)
    if offset:
        seen = {t.obs.turn_key for t in turns}
        _save_checkpoint(store, persona, stamp, offset, count, seen, tally)
    return tally.evidence(count, proposals, marks, config)


def _save_checkpoint(store: ObservationStore, persona: str, stamp: dict[str, Any],
                     offset: int, rows: int, seen: set[tuple[str, str]],
                     tally: _Tally) -> None:
    data = {
        "stamp": stamp, "offset": offset, "rows": rows,
        "tail": _tail_digest(store, persona, offset),
        "turn_keys": sorted(seen),
        **asdict(tally),
    }
    try:
        atomic_write_text(persona_path(store.root, persona, ".evidence.json"),
                          json.dumps(data, separators=(",", ":")))
    except OSError as exc:
        # The checkpoint only saves time; the estimate itself is still right.
        logger.warning("could not save the evidence checkpoint: %s", exc)
