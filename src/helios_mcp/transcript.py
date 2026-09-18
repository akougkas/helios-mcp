"""Parse Claude Code transcript JSONL into agent turns.

A transcript is an append-only JSONL file with one record per line. Assistant
messages are split into one record per content block that share a
``message.id``. User records carry typed prompts, tool results, interrupt
markers, slash-command wrappers, meta injections and background task
notifications. This module folds that stream into ``AgentTurn`` objects: the
input that started the turn, everything the agent did, and the first input
that followed it.

Only the main conversation is parsed. Sidechain records belong to subagents
and are skipped, as are compaction summaries and meta injections. Nothing
parsed here is persisted; callers derive labels and discard the text.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

UserKind = Literal["prompt", "notification", "command", "interrupt"]

_INTERRUPT_PREFIX = "[Request interrupted by user"
_DENIAL_FEEDBACK_MARKER = "the user said:\n"
_REJECTED_MARKER = "The user doesn't want to proceed with this tool use."
_NOT_DENIALS = frozenset({"AskUserQuestion"})

# Wrappers that mark user records produced by the harness rather than typed
# by a person. Slash commands are kept as "command" so a /clear still closes
# the preceding turn, but they carry no judgment about it.
_COMMAND_PREFIXES = ("<command-name>", "<command-message>", "<local-command-")
_NOTIFICATION_PREFIXES = (
    "<task-notification>",
    "<cross-session-message",
    "<scheduled-task",
)
_SKIP_PREFIXES = ("Base directory for this skill:", "Caveat: The messages below")


@dataclass(frozen=True)
class UserInput:
    """One input that starts or follows an agent turn."""

    kind: UserKind
    text: str
    timestamp: float
    uuid: str


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation and what came back."""

    tool_use_id: str
    name: str
    input: dict[str, Any]
    is_error: bool = False
    denied: bool = False
    denial_feedback: str | None = None
    answered: str | None = None  # AskUserQuestion answers text, when present


@dataclass
class AgentTurn:
    """Everything the agent did between two inputs."""

    turn_id: str
    session_id: str
    timestamp: float
    prompt: UserInput | None
    texts: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    steers: list[UserInput] = field(default_factory=list)
    interrupted: bool = False
    end_timestamp: float = 0.0
    next_input: UserInput | None = None
    opens_session: bool = False
    model: str | None = None  # first real model id that produced the turn

    @property
    def text(self) -> str:
        """Visible assistant prose for the whole turn."""
        return "\n\n".join(t for t in self.texts if t.strip())

    @property
    def final_text(self) -> str:
        """The last prose block, which is what the user reads at the end."""
        for t in reversed(self.texts):
            if t.strip():
                return t
        return ""

    @property
    def denials(self) -> list[ToolCall]:
        return [c for c in self.tool_calls if c.denied]


@dataclass
class Session:
    session_id: str
    turns: list[AgentTurn]


def parse_timestamp(value: Any) -> float:
    """ISO-8601 transcript timestamp to epoch seconds, 0.0 when absent."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def iter_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSON records from a transcript, skipping corrupt or partial lines."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield rec


def _content_blocks(message: Any) -> list[dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", "")) for b in content if isinstance(b, dict)
        )
    return ""


def classify_user_text(text: str, record: dict[str, Any]) -> UserKind | None:
    """Kind of a user text record, or None when it should be ignored."""
    stripped = text.lstrip()
    if stripped.startswith(_INTERRUPT_PREFIX):
        return "interrupt"
    origin = record.get("origin")
    origin_kind = origin.get("kind") if isinstance(origin, dict) else None
    if (
        record.get("promptSource") == "system"
        or origin_kind in {"task-notification", "peer"}
        or stripped.startswith(_NOTIFICATION_PREFIXES)
    ):
        return "notification"
    if stripped.startswith(_COMMAND_PREFIXES):
        return "command"
    if stripped.startswith(_SKIP_PREFIXES):
        return None
    return "prompt"


def _skip_record(rec: dict[str, Any]) -> bool:
    return bool(
        rec.get("isSidechain")
        or rec.get("isMeta")
        or rec.get("isCompactSummary")
        or rec.get("isVisibleInTranscriptOnly")
        or rec.get("isApiErrorMessage")
    )


class _Builder:
    """Folds records into turns in file order."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.turns: list[AgentTurn] = []
        self.current: AgentTurn | None = None
        self.pending_prompt: UserInput | None = None
        self.calls: dict[str, int] = {}  # tool_use_id -> index in current turn

    def _close(self, following: UserInput | None) -> None:
        if self.current is not None:
            self.current.next_input = following
            self.turns.append(self.current)
            self.current = None
            self.calls = {}

    def user_input(self, ui: UserInput) -> None:
        if ui.kind == "interrupt":
            if self.current is not None:
                self.current.interrupted = True
            return
        self._close(ui)
        self.pending_prompt = ui

    def steer(self, ui: UserInput) -> None:
        if self.current is not None:
            self.current.steers.append(ui)
        else:
            self.user_input(ui)

    def assistant(self, rec: dict[str, Any], ts: float) -> None:
        if self.current is None:
            self.current = AgentTurn(
                turn_id=str(rec.get("uuid", "")),
                session_id=self.session_id,
                timestamp=ts,
                prompt=self.pending_prompt,
                opens_session=not self.turns,
            )
            self.pending_prompt = None
        turn = self.current
        turn.end_timestamp = max(turn.end_timestamp, ts)
        message = rec.get("message")
        model = message.get("model") if isinstance(message, dict) else None
        if turn.model is None and isinstance(model, str) and model != "<synthetic>":
            turn.model = model
        for block in _content_blocks(rec.get("message")):
            btype = block.get("type")
            if btype == "text":
                turn.texts.append(str(block.get("text", "")))
            elif btype == "tool_use":
                raw_input = block.get("input")
                call = ToolCall(
                    tool_use_id=str(block.get("id", "")),
                    name=str(block.get("name", "")),
                    input=raw_input if isinstance(raw_input, dict) else {},
                )
                self.calls[call.tool_use_id] = len(turn.tool_calls)
                turn.tool_calls.append(call)

    def tool_result(self, rec: dict[str, Any], block: dict[str, Any]) -> None:
        if self.current is None:
            return
        idx = self.calls.get(str(block.get("tool_use_id", "")))
        if idx is None:
            return
        call = self.current.tool_calls[idx]
        text = _result_text(block)
        is_error = bool(block.get("is_error"))
        denial_kind = rec.get("toolDenialKind")
        # toolDenialKind is authoritative where the CLI writes it; older
        # transcripts only have the rejection text. Declining a question the
        # agent asked is the user answering in chat, not refusing an action,
        # and auto-mode blocks are a classifier's decision, not the user's.
        denied = call.name not in _NOT_DENIALS and (
            denial_kind == "user-rejected"
            or (denial_kind is None and is_error and text.startswith(_REJECTED_MARKER))
        )
        feedback = None
        if denied and _DENIAL_FEEDBACK_MARKER in text:
            feedback = text.split(_DENIAL_FEEDBACK_MARKER, 1)[1].strip() or None
        answered = None
        tur = rec.get("toolUseResult")
        if isinstance(tur, dict) and isinstance(tur.get("answers"), dict):
            answered = "; ".join(str(v) for v in tur["answers"].values())
        self.current.tool_calls[idx] = ToolCall(
            tool_use_id=call.tool_use_id,
            name=call.name,
            input=call.input,
            is_error=is_error,
            denied=denied,
            denial_feedback=feedback,
            answered=answered,
        )

    def finish(self) -> list[AgentTurn]:
        self._close(None)
        return self.turns


def parse_records(
    records: Iterable[dict[str, Any]], session_id: str | None = None
) -> Session:
    """Fold transcript records into a Session of agent turns."""
    builder: _Builder | None = None
    sid = session_id

    for rec in records:
        rtype = rec.get("type")
        if rtype not in {"user", "assistant", "attachment"}:
            continue
        if sid is None:
            found = rec.get("sessionId")
            if isinstance(found, str):
                sid = found
        if builder is None:
            builder = _Builder(sid or "")
        if _skip_record(rec):
            continue
        ts = parse_timestamp(rec.get("timestamp"))
        uuid = str(rec.get("uuid", ""))

        if rtype == "assistant":
            builder.assistant(rec, ts)
            continue

        if rtype == "attachment":
            att = rec.get("attachment")
            if isinstance(att, dict) and att.get("type") == "queued_command":
                prompt = str(att.get("prompt", ""))
                kind = classify_user_text(prompt, rec)
                if att.get("commandMode") == "task-notification":
                    kind = "notification"
                if kind == "prompt":
                    builder.steer(UserInput("prompt", prompt, ts, uuid))
            continue

        # user record
        for block in _content_blocks(rec.get("message")):
            btype = block.get("type")
            if btype == "tool_result":
                builder.tool_result(rec, block)
            elif btype == "text":
                text = str(block.get("text", ""))
                kind = classify_user_text(text, rec)
                if kind is not None:
                    builder.user_input(UserInput(kind, text, ts, uuid))
                    if kind != "interrupt":
                        break  # one input per record; later blocks are attachments

    if builder is None:
        return Session(session_id=sid or "", turns=[])
    return Session(session_id=builder.session_id, turns=builder.finish())


def parse_transcript(path: Path, session_id: str | None = None) -> Session:
    """Parse one transcript file. Missing files yield an empty session."""
    if not path.is_file():
        return Session(session_id=session_id or "", turns=[])
    return parse_records(iter_records(path), session_id)
