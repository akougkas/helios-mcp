"""Turn transcripts and message lists into ledger observations.

``ingest_session`` is what the Stop and SessionEnd hooks run. Each call parses
the whole transcript and appends one heuristic observation per turn. Appends
are idempotent on (persona, session, turn, source), so repeated calls add
only the turns that are new.

A turn's endorsement comes from what the user did next, which is unknown
until the next prompt arrives. Because the ledger never rewrites a row, the
newest turn is held back until something follows it, and is written with no
endorsement only when the session ends (``final=True``). The final call also
runs the model labeler over the whole session, adding ``llm`` rows that the
estimator prefers over heuristic ones for the same turn.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .classify import classify_turn
from .endorsement import judge_turn, opener_hints
from .llm import LLMClient, LLMTurnLabel, default_client, label_session
from .store import ObservationStore, TurnObservation
from .transcript import AgentTurn, UserInput, parse_transcript


def heuristic_observation(
    persona: str, session_id: str, turn: AgentTurn, source: str = "heuristic"
) -> TurnObservation | None:
    """Heuristic labels plus endorsement for one turn, or None if it carries nothing."""
    labels = classify_turn(turn)
    verdict = judge_turn(turn)
    if not labels.labels and verdict.correction_hint is None:
        return None
    return TurnObservation(
        persona=persona,
        session_id=session_id,
        turn_id=turn.turn_id,
        timestamp=turn.timestamp,
        source=source,
        labels=labels.labels,
        confidence=round(labels.overall_confidence, 4),
        endorsement=verdict.value,
        correction_hint=verdict.correction_hint,
        dim_confidence=dict(labels.confidence) or None,
    )


def llm_observation(
    persona: str, session_id: str, turn: AgentTurn, label: LLMTurnLabel
) -> TurnObservation:
    """Model labels for one turn, with hard transcript facts kept authoritative."""
    endorsement = label.endorsement
    if turn.interrupted or turn.denials:
        # An interrupt or a denied tool call is a recorded fact, not a reading.
        endorsement = -1.0
    elif endorsement is not None and turn.next_input is None and not turn.steers:
        endorsement = None
    # The model reads hints only from what the user said after the turn; a
    # hint on a turn nobody answered came from the task text itself. Opener
    # preferences come from the narrow heuristic lexicon instead.
    hint = dict(label.correction_hint or {}) if _human_followed(turn) else {}
    for dim, state in opener_hints(turn).items():
        hint.setdefault(dim, state)
    # A row is written even when the model found nothing, so a resumed
    # SessionEnd does not send the same turn back to it.
    return TurnObservation(
        persona=persona,
        session_id=session_id,
        turn_id=turn.turn_id,
        timestamp=turn.timestamp,
        source="llm",
        labels=label.labels,
        confidence=round(label.confidence, 4),
        endorsement=endorsement,
        correction_hint=hint or None,
    )


def _human_followed(turn: AgentTurn) -> bool:
    nxt = turn.next_input
    return bool(
        (nxt is not None and nxt.kind == "prompt")
        or turn.steers
        or any(c.denial_feedback for c in turn.denials)
    )


def _settled(turns: Sequence[AgentTurn], final: bool) -> list[AgentTurn]:
    """Turns whose endorsement can no longer change."""
    if final or not turns:
        return list(turns)
    if turns[-1].next_input is None:
        return list(turns[:-1])
    return list(turns)


def ingest_session(
    helios_dir: Path,
    persona: str,
    transcript_path: Path,
    session_id: str,
    *,
    final: bool = False,
    client: LLMClient | None = None,
) -> int:
    """Append observations for a session transcript. Returns the new row count.

    A missing transcript or a truncated last line is not an error. The model
    labeler runs only when ``final`` is set, using ``client`` or the default
    client when labeling is enabled.
    """
    session = parse_transcript(Path(transcript_path), session_id)
    turns = [t for t in _settled(session.turns, final) if t.turn_id]
    if not turns:
        return 0

    observations: list[TurnObservation] = []
    for turn in turns:
        obs = heuristic_observation(persona, session_id, turn)
        if obs is not None:
            observations.append(obs)

    store = ObservationStore(helios_dir)
    if final:
        # SessionEnd fires again when a session is resumed; only turns the
        # model has not labeled yet go back to it.
        done = {
            obs.turn_id for obs in store.iter(persona)
            if obs.source == "llm" and obs.session_id == session_id
        }
        pending = [t for t in turns if t.turn_id not in done]
        if pending and client is None:
            client = default_client(helios_dir)
        if pending and client is not None:
            labels = label_session(pending, client)
            for turn in pending:
                label = labels.get(turn.turn_id)
                if label is None:
                    continue
                observations.append(
                    llm_observation(persona, session_id, turn, label)
                )

    return store.append(observations)


# ---------------------------------------------------------------------------
# MCP text path
# ---------------------------------------------------------------------------


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", "")) for b in content
            if isinstance(b, dict) and b.get("type", "text") == "text"
        )
    return ""


def turns_from_messages(
    messages: Sequence[dict[str, Any]], session_id: str
) -> list[AgentTurn]:
    """Fold role/content messages into agent turns.

    Turn ids hash the conversation up to and including the assistant message,
    so re-sending a longer version of the same conversation maps the earlier
    turns to the same ids and the ledger ignores them.
    """
    now = time.time()
    digest = hashlib.sha256(session_id.encode())
    turns: list[AgentTurn] = []
    current: AgentTurn | None = None
    pending: UserInput | None = None
    for i, msg in enumerate(messages):
        role = msg.get("role")
        text = _content_text(msg.get("content"))
        digest.update(f"\x00{role}\x00{text}".encode())
        if role == "assistant":
            if current is None:
                current = AgentTurn(
                    turn_id="mcp-" + digest.hexdigest()[:24],
                    session_id=session_id,
                    timestamp=now,
                    prompt=pending,
                )
                pending = None
            current.texts.append(text)
        elif role == "user":
            user = UserInput("prompt", text, now, f"msg-{i}")
            if current is not None:
                current.next_input = user
                turns.append(current)
                current = None
            pending = user
    if current is not None:
        turns.append(current)
    return turns


def observations_from_messages(
    *, persona: str, messages: Sequence[dict[str, Any]], session_id: str | None = None
) -> list[TurnObservation]:
    """Observations for the ``observe_interaction`` tool, one per assistant turn."""
    sid = session_id or "mcp"
    out: list[TurnObservation] = []
    for turn in turns_from_messages(messages, sid):
        obs = heuristic_observation(persona, sid, turn, source="mcp")
        if obs is not None:
            out.append(obs)
    return out
