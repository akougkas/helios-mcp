"""Model-backed labeling through a headless ``claude -p`` child process.

One client serves two jobs: batch-labeling the turns of a finished session,
and projecting CLAUDE.md or soul.md text into distributions on import. The
child runs in safe mode with no tools, no MCP servers, no session persistence
and ``HELIOS_DISABLE=1`` in its environment, so it never loads this plugin or
fires Helios hooks recursively. Output is constrained by a JSON schema and
validated again here, because a label that fails validation must not reach
the ledger.

Opt out with ``HELIOS_LLM=0`` or ``llm: false`` in ``HELIOS_DIR/config.yaml``.
Every failure path returns None so callers fall back to heuristics.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from .endorsement import follow_texts
from .taxonomy import (
    DIMENSION_DESCRIPTIONS,
    STATE_LABELS,
    list_dimensions,
    list_states,
)
from .transcript import AgentTurn

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TIMEOUT = 180.0
# Spend cap per child call, passed to the CLI as --max-budget-usd.
DEFAULT_BUDGET_USD = 0.50
# Character budget for one batch prompt. A session larger than this is split
# into several calls, keeping each request well inside the model's context.
BATCH_CHAR_BUDGET = 60_000

_PROMPT_CHARS = 500
_TEXT_HEAD = 600
_TEXT_TAIL = 900
_NEXT_CHARS = 500
_MAX_TOOLS_LISTED = 12
_OFF_VALUES = {"0", "false", "no", "off"}
_TRAILING_INT = re.compile(r"(\d+)\s*$")
_APPROVAL_GRADE = 0.75
_MOVED_ON_GRADE = 0.5


class LLMClient(Protocol):
    def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any] | None: ...


def llm_enabled(helios_dir: Path | None = None) -> bool:
    """Whether model labeling may run in this process."""
    if os.environ.get("HELIOS_DISABLE") == "1":
        return False
    if os.environ.get("HELIOS_LLM", "").strip().lower() in _OFF_VALUES:
        return False
    if helios_dir is not None:
        cfg = helios_dir / "config.yaml"
        if cfg.is_file():
            try:
                data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                data = None
            if isinstance(data, dict) and data.get("llm") is False:
                return False
    return True


@dataclass
class ClaudeCLIClient:
    """Runs ``claude -p`` once per request and returns its structured output."""

    model: str = DEFAULT_MODEL
    timeout: float = DEFAULT_TIMEOUT
    budget_usd: float = DEFAULT_BUDGET_USD
    executable: str = "claude"

    def command(self, system: str, schema: dict[str, Any]) -> list[str]:
        return [
            self.executable, "-p",
            "--safe-mode",
            "--model", self.model,
            "--output-format", "json",
            "--no-session-persistence",
            "--tools", "",
            "--strict-mcp-config",
            "--max-budget-usd", f"{self.budget_usd:.2f}",
            "--system-prompt", system,
            "--json-schema", json.dumps(schema),
        ]

    def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        # Extended thinking made a 3-turn batch take 127s and cost 4x more with
        # no better labels, and pushed larger batches past the timeout.
        env = {
            **os.environ,
            "HELIOS_DISABLE": "1",
            "HELIOS_LLM": "0",
            "MAX_THINKING_TOKENS": "0",
        }
        with tempfile.TemporaryDirectory(prefix="helios-llm-") as cwd:
            try:
                proc = subprocess.run(
                    self.command(system, schema),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env,
                    cwd=cwd,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
        if proc.returncode != 0:
            return None
        return parse_cli_output(proc.stdout)


def parse_cli_output(stdout: str) -> dict[str, Any] | None:
    """Structured output from ``--output-format json``, in either CLI shape.

    Newer CLIs print an array of stream events ending in a ``result`` event;
    older ones print the ``result`` object alone.
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    events = data if isinstance(data, list) else [data]
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("type") != "result":
            continue
        if event.get("is_error"):
            return None
        structured = event.get("structured_output")
        if isinstance(structured, dict):
            return structured
        text = event.get("result")
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def default_client(helios_dir: Path | None = None) -> LLMClient | None:
    """The CLI client when labeling is enabled and ``claude`` is on PATH."""
    if not llm_enabled(helios_dir):
        return None
    exe = shutil.which("claude")
    if exe is None:
        return None
    return ClaudeCLIClient(executable=exe)


# ---------------------------------------------------------------------------
# Schemas and validation shared by both jobs
# ---------------------------------------------------------------------------


def _distribution_schema(dim: str) -> dict[str, Any]:
    states = list_states(dim)
    return {
        "type": "object",
        "properties": {s: {"type": "number", "minimum": 0} for s in states},
        "required": states,
        "additionalProperties": False,
    }


def normalize_label(dim: str, raw: Any) -> dict[str, float] | None:
    """A validated distribution over ``dim``'s states, or None if unusable."""
    if not isinstance(raw, dict):
        return None
    states = list_states(dim)
    weights: dict[str, float] = {}
    for s in states:
        v = raw.get(s, 0.0)
        if isinstance(v, bool) or not isinstance(v, int | float) or v != v:
            return None
        weights[s] = max(float(v), 0.0)
    total = sum(weights.values())
    if total <= 0:
        return None
    return {s: w / total for s, w in weights.items()}


def _hint_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            d: {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "enum": list_states(d)},
                    "quote": {"type": "string"},
                },
                "required": ["state", "quote"],
                "additionalProperties": False,
            }
            for d in list_dimensions()
        },
        "additionalProperties": False,
    }


_QUOTE_TRIM = " \t\n\"'`.,;:!?()[]"
# A shorter quote ("ok", "no") matches almost any reply and grounds nothing.
_MIN_QUOTE = 4


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def grounded(quote: Any, texts: Sequence[str]) -> bool:
    """Whether ``quote`` appears verbatim, up to case and spacing, in ``texts``."""
    if not isinstance(quote, str):
        return False
    q = _norm(quote).strip(_QUOTE_TRIM)
    return len(q) >= _MIN_QUOTE and any(q in _norm(t) for t in texts)


# ---------------------------------------------------------------------------
# Session labeling
# ---------------------------------------------------------------------------

_LABEL_SYSTEM = """\
You annotate an AI coding agent's behavior for a preference-learning system.
You receive the turns of one session. Each turn shows the user's input, what
the agent did (tool calls) and said, and what the user did next.

For every turn produce:
1. A probability distribution over the states of each dimension that the turn
   gives evidence for, describing the agent's behavior in that turn. Use null
   for a dimension the turn says nothing about. Spread mass when uncertain;
   put more than 0.8 on one state only for unambiguous evidence.
   Judge structure, narration and sycophancy from the prose the agent wrote,
   not from tool calls. Inline code, paths and bold words inside sentences are
   not structure; plain paragraphs are prose. A closing report of what changed
   and how it was verified is not a recap; a recap restates what the turn
   already said, like a summary section. Label sycophancy only when the turn
   praises or validates the user, or had something to dispute or flag;
   otherwise it is null. Label pushback only when the turn's input disputed
   something the agent said or did; otherwise pushback is null.
2. confidence in [0, 1]: how much evidence the turn carries overall.
3. endorsement in [-1, 1], judged only from what the user did next:
   1 explicit approval of the turn, wherever it sits in the reply: "thanks",
   "perfect", "good catch", "your fix is accepted", "agreed, go ahead", even
   when the same message goes on to the next task. Put the approving words,
   copied exactly, in approval_quote. A reply that just gives the next task
   is not approval, however polite; 0.5 the user moved on without
   praising or objecting; 0 no human
   response or a response unrelated to the agent's behavior; -0.5 the outcome
   was wrong but not the behavior; -1 correction, frustration, interrupt or
   denied tool call. null when nothing followed.
   A style request that contradicts what the agent just did ("ask me before
   deleting" right after a deletion) is a correction, -1. The same request
   when the agent already behaved that way is a standing preference, 0.
4. correction_hint: only from what the user said after the turn (the next
   input, a mid-turn interjection, or feedback on a denied tool call), never
   from the turn's own input. For each dimension the user explicitly
   addressed, the state they asked for: "shorter" means
   communication_register terse, "stop asking, just do it" means
   interaction_agency assumes_and_acts, "check with me before changing files"
   means interaction_agency asks_first and risk_caution checks_before_acting.
   Every dimension can be addressed: "too many bullets" or "write it as
   prose" means structure prose; "don't flatter me" or "be honest" means
   sycophancy candid; "stop narrating" or "skip the recap" means narration
   silent_action, and "what are you doing? give me an update" means
   brief_signposting; "be specific, cite the file" means specificity
   concrete; "don't just agree with me" means pushback holds_position;
   "stop hedging, pick one" means epistemic_style confident; "did you make
   that up?" means admits_ignorance. A standing preference stated mid-session
   ("from now on keep replies short", "always run the tests first") is a
   hint too, with the endorsement set by the rest of the reply.
   A hint needs the user to comment on how the agent works or talks.
   Directives for the next step are not hints: "stand down", "is it done?",
   "fix exactly those four tests", "reply 'done'", "reply in one line" for a
   single report, scope rules, and requests about the product being built.
   For each hint give the state and the quote: the user's exact words that
   ask for it, copied verbatim from what they said after the turn. If you
   cannot quote words about how the agent works or talks, there is no hint.
   Most turns have no hint; use an empty object when in doubt.
5. approval_quote: the approving words for an endorsement of 1, else null.

Dimensions and states:
{taxonomy}
"""


def _label_schema() -> dict[str, Any]:
    turn_props: dict[str, Any] = {"id": {"type": "string"}}
    for dim in list_dimensions():
        turn_props[dim] = {"anyOf": [_distribution_schema(dim), {"type": "null"}]}
    turn_props["confidence"] = {"type": "number", "minimum": 0, "maximum": 1}
    turn_props["endorsement"] = {
        "anyOf": [{"type": "number", "minimum": -1, "maximum": 1}, {"type": "null"}]
    }
    turn_props["correction_hint"] = _hint_schema()
    turn_props["approval_quote"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object",
        "properties": {
            "turns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": turn_props,
                    "required": list(turn_props),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["turns"],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class LLMTurnLabel:
    labels: dict[str, dict[str, float]]
    confidence: float
    endorsement: float | None
    correction_hint: dict[str, str] | None


def _clip(text: str, head: int, tail: int = 0) -> str:
    text = text.strip()
    if len(text) <= head + tail:
        return text
    if tail == 0:
        return text[:head] + " [...]"
    return text[:head] + " [...] " + text[-tail:]


def _tool_summary(turn: AgentTurn) -> list[str]:
    lines: list[str] = []
    for call in turn.tool_calls[:_MAX_TOOLS_LISTED]:
        detail = ""
        for key in ("command", "file_path", "pattern", "description"):
            val = call.input.get(key)
            if isinstance(val, str) and val:
                detail = _clip(val.replace("\n", " "), 100)
                break
        status = " DENIED" if call.denied else (" error" if call.is_error else "")
        head = f"  - {call.name}{status}"
        lines.append(f"{head}: {detail}" if detail else head)
        if call.denial_feedback:
            lines.append(f"    user said: {_clip(call.denial_feedback, 300)}")
    extra = len(turn.tool_calls) - _MAX_TOOLS_LISTED
    if extra > 0:
        lines.append(f"  - ... {extra} more tool calls")
    return lines


def render_turn(turn: AgentTurn, index: int) -> str:
    """Compact text rendering of one turn for the labeling prompt."""
    parts = [f"### turn {index}"]
    if turn.prompt is not None:
        prompt = _clip(turn.prompt.text, _PROMPT_CHARS)
        parts.append(f"input ({turn.prompt.kind}): {prompt}")
    tools = _tool_summary(turn)
    if tools:
        parts.append("tool calls:")
        parts.extend(tools)
    said = _clip(turn.text, _TEXT_HEAD, _TEXT_TAIL) or "(nothing)"
    parts.append(f"agent said: {said}")
    for steer in turn.steers:
        parts.append(f"user interjected mid-turn: {_clip(steer.text, 300)}")
    if turn.interrupted:
        parts.append("user INTERRUPTED this turn")
    nxt = turn.next_input
    if nxt is None:
        parts.append("next: (nothing yet)")
    else:
        parts.append(f"next ({nxt.kind}): {_clip(nxt.text, _NEXT_CHARS)}")
    return "\n".join(parts)


def batches(
    turns: Sequence[AgentTurn], budget: int = BATCH_CHAR_BUDGET
) -> list[list[int]]:
    """Group turn indices into batches whose rendered size fits the budget."""
    out: list[list[int]] = []
    current: list[int] = []
    size = 0
    for i, turn in enumerate(turns):
        n = len(render_turn(turn, i))
        if current and size + n > budget:
            out.append(current)
            current, size = [], 0
        current.append(i)
        size += n
    if current:
        out.append(current)
    return out


def _parse_turn(
    item: Any, turns: Sequence[AgentTurn]
) -> tuple[int, LLMTurnLabel] | None:
    if not isinstance(item, dict):
        return None
    # Models echo the id as "3", 3 or "turn 3"; the trailing integer is the id.
    match = _TRAILING_INT.search(str(item.get("id", "")))
    if match is None:
        return None
    index = int(match.group(1))
    if not 0 <= index < len(turns):
        return None
    said = follow_texts(turns[index])
    labels: dict[str, dict[str, float]] = {}
    for dim in list_dimensions():
        label = normalize_label(dim, item.get(dim))
        if label is not None:
            labels[dim] = label
    conf = item.get("confidence")
    confidence = (
        min(max(float(conf), 0.0), 1.0) if isinstance(conf, int | float) else 0.5
    )
    end = item.get("endorsement")
    endorsement = (
        min(max(float(end), -1.0), 1.0)
        if isinstance(end, int | float) and not isinstance(end, bool)
        else None
    )
    # Hints and approvals must quote the user. Unquoted ones were mostly task
    # directives read as style requests, and they drive the endorsed posterior.
    if (endorsement is not None and endorsement >= _APPROVAL_GRADE
            and not grounded(item.get("approval_quote"), said)):
        endorsement = _MOVED_ON_GRADE
    raw_hint = item.get("correction_hint")
    hint: dict[str, str] = {}
    for d, h in raw_hint.items() if isinstance(raw_hint, dict) else []:
        if not isinstance(h, dict) or d not in list_dimensions():
            continue
        state = h.get("state")
        if state in list_states(d) and grounded(h.get("quote"), said):
            hint[d] = state
    return index, LLMTurnLabel(labels, confidence, endorsement, hint or None)


def label_session(
    turns: Sequence[AgentTurn], client: LLMClient
) -> dict[str, LLMTurnLabel]:
    """Label every turn of a session, keyed by turn_id. Missing turns failed."""
    system = _LABEL_SYSTEM.format(taxonomy=build_taxonomy_description())
    schema = _label_schema()
    results: dict[str, LLMTurnLabel] = {}
    for batch in batches(turns):
        prompt = (
            "Label each turn below. Use the number after 'turn' as the id, "
            "for example \"3\".\n\n"
            + "\n\n".join(render_turn(turns[i], i) for i in batch)
        )
        data = client.complete_json(system, prompt, schema)
        if not data or not isinstance(data.get("turns"), list):
            continue
        wanted = set(batch)
        for item in data["turns"]:
            parsed = _parse_turn(item, turns)
            if parsed is None or parsed[0] not in wanted:
                continue
            index, label = parsed
            if label.labels or label.endorsement is not None:
                results[turns[index].turn_id] = label
    return results


def build_taxonomy_description() -> str:
    """Human-readable taxonomy used in both prompts."""
    lines: list[str] = []
    for dim in list_dimensions():
        lines.append(f"\n**{dim}**: {DIMENSION_DESCRIPTIONS[dim]}")
        for state in list_states(dim):
            lines.append(f"  - {state}: {STATE_LABELS[dim][state]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Import projection
# ---------------------------------------------------------------------------


def projection_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {d: _distribution_schema(d) for d in list_dimensions()},
        "required": list_dimensions(),
        "additionalProperties": False,
    }
