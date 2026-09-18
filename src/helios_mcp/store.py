"""Persistent state for the observation ledger and negotiation proposals.

``ObservationStore`` is an append-only JSONL ledger per persona at
``HELIOS_DIR/observations/<persona>.jsonl``. Rows are keyed by
``(persona, session_id, turn_id, source)`` so re-ingesting a transcript is a
no-op. Corrupt lines are skipped on read rather than failing the whole ledger,
because a crash mid-append must not lose every earlier observation.

``ProposalStore`` keeps proposals per persona at
``HELIOS_DIR/proposals/<persona>.json``, rewritten atomically on every change.
Rejected proposals stay on disk: the estimator reads them as evidence toward the
declared profile, and they drive the per-dimension cooldown.
"""

from __future__ import annotations

import fcntl
import json
import logging
import math
import secrets
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from .atomic_ops import atomic_write_text
from .security import persona_path, validate_persona_name
from .taxonomy import BEHAVIORAL_TAXONOMY

logger = logging.getLogger(__name__)

SOURCES: tuple[str, ...] = ("llm", "heuristic", "mcp")
"""Label sources in precedence order: the first one present for a turn wins."""

_LABEL_SUM_TOLERANCE = 1e-3


def _validate_labels(labels: dict[str, dict[str, float]]) -> None:
    for dim, dist in labels.items():
        states = BEHAVIORAL_TAXONOMY.get(dim)
        if states is None:
            raise ValueError(f"unknown dimension {dim!r}")
        unknown = set(dist) - set(states)
        if unknown:
            raise ValueError(f"unknown states for {dim}: {sorted(unknown)}")
        if any(not math.isfinite(p) or p < 0 for p in dist.values()):
            raise ValueError(f"label for {dim} has negative or non-finite mass")
        total = sum(dist.values())
        if abs(total - 1.0) > _LABEL_SUM_TOLERANCE:
            raise ValueError(f"label for {dim} sums to {total:.4f}, not 1")


@dataclass(frozen=True)
class TurnObservation:
    """One labeled agent turn. Validated on construction."""

    persona: str
    session_id: str
    turn_id: str
    timestamp: float
    source: str
    labels: dict[str, dict[str, float]]
    confidence: float = 1.0
    endorsement: float | None = None
    correction_hint: dict[str, str] | None = None
    dim_confidence: dict[str, float] | None = None

    def __post_init__(self) -> None:
        validate_persona_name(self.persona)
        if not self.session_id or not self.turn_id:
            raise ValueError("session_id and turn_id must be non-empty")
        if self.source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {self.source!r}")
        if not math.isfinite(self.timestamp):
            raise ValueError("timestamp must be finite")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.endorsement is not None and not -1.0 <= self.endorsement <= 1.0:
            raise ValueError("endorsement must be in [-1, 1] or None")
        _validate_labels(self.labels)
        for dim, state in (self.correction_hint or {}).items():
            if state not in BEHAVIORAL_TAXONOMY.get(dim, ()):
                raise ValueError(f"correction_hint {dim}={state!r} is not a state")
        for dim, conf in (self.dim_confidence or {}).items():
            if dim not in BEHAVIORAL_TAXONOMY:
                raise ValueError(f"dim_confidence names unknown dimension {dim!r}")
            if not 0.0 <= conf <= 1.0:
                raise ValueError(f"dim_confidence for {dim} must be in [0, 1]")

    def confidence_for(self, dimension: str) -> float:
        """Per-dimension classifier confidence, falling back to ``confidence``."""
        if self.dim_confidence and dimension in self.dim_confidence:
            return self.dim_confidence[dimension]
        return self.confidence

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.persona, self.session_id, self.turn_id, self.source)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnObservation:
        return cls(
            persona=data["persona"],
            session_id=data["session_id"],
            turn_id=data["turn_id"],
            timestamp=float(data["timestamp"]),
            source=data["source"],
            labels=data["labels"],
            confidence=float(data.get("confidence", 1.0)),
            endorsement=data.get("endorsement"),
            correction_hint=data.get("correction_hint"),
            dim_confidence=data.get("dim_confidence"),
        )


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Serialize writers across processes (Stop and SessionEnd hooks can overlap)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class ObservationStore:
    """Append-only, idempotent per-persona observation ledger."""

    def __init__(self, helios_dir: Path) -> None:
        self.root = Path(helios_dir) / "observations"

    def path(self, persona: str) -> Path:
        return persona_path(self.root, persona, ".jsonl")

    def append(self, observations: Iterable[TurnObservation]) -> int:
        """Append observations not already in the ledger. Returns the new-row count.

        Keys already present, including duplicates within ``observations``,
        are skipped.
        """
        by_persona: dict[str, list[TurnObservation]] = {}
        for obs in observations:
            by_persona.setdefault(obs.persona, []).append(obs)

        added = 0
        for persona, batch in by_persona.items():
            path = self.path(persona)
            with _file_lock(path):
                seen = {obs.key for obs in self.iter(persona)}
                lines = []
                for obs in batch:
                    if obs.key in seen:
                        continue
                    seen.add(obs.key)
                    lines.append(obs.to_json() + "\n")
                if lines:
                    with path.open("a", encoding="utf-8") as f:
                        # A torn last line from an earlier crash would swallow
                        # the first new row, so start on a fresh line.
                        if f.tell() > 0 and not _ends_with_newline(path):
                            f.write("\n")
                        f.writelines(lines)
                added += len(lines)
        return added

    def iter(self, persona: str) -> Iterator[TurnObservation]:
        """Yield every valid row in ledger order, skipping corrupt lines."""
        path = self.path(persona)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    yield TurnObservation.from_dict(json.loads(line))
                except (ValueError, KeyError, TypeError) as exc:
                    logger.warning("skipping corrupt ledger line %s:%d: %s",
                                   path, lineno, exc)

    def count(self, persona: str) -> int:
        return sum(1 for _ in self.iter(persona))


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as f:
        f.seek(-1, 2)
        return f.read(1) == b"\n"


ProposalStatus = Literal["pending", "accepted", "rejected", "auto_accepted",
                         "superseded"]


@dataclass(frozen=True)
class ProposedChange:
    """Proposed update for one dimension."""

    declared: dict[str, float]
    target: dict[str, float]
    divergence: float
    credibility: float


@dataclass(frozen=True)
class Proposal:
    id: str
    persona: str
    created_at: float
    changes: dict[str, ProposedChange]
    observation_count: int
    status: ProposalStatus = "pending"
    decided_at: float | None = None
    decided_dimensions: tuple[str, ...] = ()
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decided_dimensions"] = list(self.decided_dimensions)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Proposal:
        return cls(
            id=data["id"],
            persona=data["persona"],
            created_at=float(data["created_at"]),
            changes={d: ProposedChange(**c) for d, c in data["changes"].items()},
            observation_count=int(data["observation_count"]),
            status=data["status"],
            decided_at=data.get("decided_at"),
            decided_dimensions=tuple(data.get("decided_dimensions", ())),
            reason=data.get("reason"),
        )


@dataclass
class ProposalStore:
    """Persisted proposals with ids, decisions and a per-dimension cooldown.

    ``cooldown_seconds`` is how long a rejected dimension stays out of new
    proposals.
    """

    helios_dir: Path
    cooldown_seconds: float = 3 * 24 * 3600
    root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.helios_dir) / "proposals"

    def path(self, persona: str) -> Path:
        return persona_path(self.root, persona, ".json")

    def all(self, persona: str) -> list[Proposal]:
        """Every proposal for ``persona``, oldest first."""
        path = self.path(persona)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [Proposal.from_dict(p) for p in raw]
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("unreadable proposal file %s: %s", path, exc)
            return []

    def get(self, persona: str, proposal_id: str) -> Proposal | None:
        return next((p for p in self.all(persona) if p.id == proposal_id), None)

    def pending(self, persona: str) -> Proposal | None:
        return next(
            (p for p in reversed(self.all(persona)) if p.status == "pending"), None
        )

    def rejections(self, persona: str) -> list[Proposal]:
        return [p for p in self.all(persona) if p.status == "rejected"]

    def in_cooldown(self, persona: str, dimension: str,
                    now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return any(
            dimension in p.decided_dimensions
            and p.decided_at is not None
            and now - p.decided_at < self.cooldown_seconds
            for p in self.rejections(persona)
        )

    def create(self, persona: str, changes: dict[str, ProposedChange],
               observation_count: int, now: float | None = None) -> Proposal:
        """Persist a new pending proposal, superseding any earlier pending one."""
        now = time.time() if now is None else now
        proposal = Proposal(
            id=secrets.token_hex(6),
            persona=validate_persona_name(persona),
            created_at=now,
            changes=changes,
            observation_count=observation_count,
        )
        with _file_lock(self.path(persona)):
            existing = [
                replace(p, status="superseded", decided_at=now)
                if p.status == "pending" else p
                for p in self.all(persona)
            ]
            self._write(persona, [*existing, proposal])
        return proposal

    def create_decided(self, persona: str, changes: dict[str, ProposedChange],
                       observation_count: int, status: ProposalStatus,
                       reason: str | None = None,
                       now: float | None = None) -> Proposal:
        """Persist a proposal that was decided without review, like an auto-accept.

        Unlike ``create``, this leaves any pending proposal alone.
        """
        now = time.time() if now is None else now
        proposal = Proposal(
            id=secrets.token_hex(6),
            persona=validate_persona_name(persona),
            created_at=now,
            changes=changes,
            observation_count=observation_count,
            status=status,
            decided_at=now,
            decided_dimensions=tuple(changes),
            reason=reason,
        )
        with _file_lock(self.path(persona)):
            self._write(persona, [*self.all(persona), proposal])
        return proposal

    def decide(self, persona: str, proposal_id: str, status: ProposalStatus,
               dimensions: Iterable[str] | None = None,
               reason: str | None = None, now: float | None = None) -> Proposal:
        """Record a decision on a pending proposal.

        ``dimensions`` defaults to every dimension in the proposal.

        Raises:
            KeyError: No proposal with that id.
            ValueError: The proposal is not pending, or a dimension is not in it.
        """
        now = time.time() if now is None else now
        with _file_lock(self.path(persona)):
            proposals = self.all(persona)
            idx = next((i for i, p in enumerate(proposals) if p.id == proposal_id),
                       None)
            if idx is None:
                raise KeyError(proposal_id)
            current = proposals[idx]
            if current.status != "pending":
                raise ValueError(f"proposal {proposal_id} is {current.status}")
            dims = tuple(current.changes if dimensions is None else dimensions)
            unknown = set(dims) - set(current.changes)
            if unknown:
                raise ValueError(f"dimensions not in proposal: {sorted(unknown)}")
            decided = replace(current, status=status, decided_at=now,
                               decided_dimensions=dims, reason=reason)
            proposals[idx] = decided
            self._write(persona, proposals)
        return decided

    def _write(self, persona: str, proposals: list[Proposal]) -> None:
        atomic_write_text(
            self.path(persona),
            json.dumps([p.to_dict() for p in proposals], indent=2) + "\n",
        )

