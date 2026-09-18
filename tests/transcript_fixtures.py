"""Synthetic Claude Code transcripts modeled on the real record schema."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

SESSION = "sess-0001"


class TranscriptBuilder:
    """Emits records in the shape Claude Code writes them."""

    def __init__(self, session_id: str = SESSION) -> None:
        self.session_id = session_id
        self.records: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._clock = itertools.count(0)
        self._parent: str | None = None

    def _base(self, rtype: str, **extra: Any) -> dict[str, Any]:
        n = next(self._ids)
        uuid = f"{rtype[:1]}-{n:04d}"
        sec = next(self._clock)
        rec = {
            "type": rtype,
            "uuid": uuid,
            "parentUuid": self._parent,
            "isSidechain": False,
            "sessionId": self.session_id,
            "timestamp": f"2026-09-01T10:{sec // 60:02d}:{sec % 60:02d}.000Z",
            "version": "2.1.250",
            **extra,
        }
        self._parent = uuid
        self.records.append(rec)
        return rec

    def prompt(self, text: str, **extra: Any) -> dict[str, Any]:
        return self._base(
            "user",
            message={"role": "user", "content": text},
            promptSource="typed",
            origin={"kind": "human"},
            **extra,
        )

    def notification(self, text: str = "<task-notification>done</task-notification>") -> dict[str, Any]:
        return self._base(
            "user",
            message={"role": "user", "content": text},
            promptSource="system",
            origin={"kind": "task-notification"},
        )

    def meta(self, text: str) -> dict[str, Any]:
        return self._base("user", message={"role": "user", "content": text}, isMeta=True)

    def say(self, text: str, msg_id: str | None = None, stop: str = "end_turn") -> dict[str, Any]:
        return self._base(
            "assistant",
            message={
                "id": msg_id or f"msg_{len(self.records)}",
                "role": "assistant",
                "model": "claude-test",
                "stop_reason": stop,
                "content": [{"type": "text", "text": text}],
            },
        )

    def think(self, text: str, msg_id: str = "msg_think") -> dict[str, Any]:
        return self._base(
            "assistant",
            message={"id": msg_id, "role": "assistant", "stop_reason": "tool_use",
                     "content": [{"type": "thinking", "thinking": text}]},
        )

    def tool(self, name: str, tool_input: dict[str, Any], tool_id: str, msg_id: str | None = None) -> dict[str, Any]:
        return self._base(
            "assistant",
            message={
                "id": msg_id or f"msg_{len(self.records)}",
                "role": "assistant",
                "model": "claude-test",
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}],
            },
        )

    def result(self, tool_id: str, content: str = "ok", is_error: bool = False, **extra: Any) -> dict[str, Any]:
        return self._base(
            "user",
            message={"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": content, "is_error": is_error}
            ]},
            **extra,
        )

    def deny(self, tool_id: str, feedback: str | None = None) -> dict[str, Any]:
        text = (
            "The user doesn't want to proceed with this tool use. The tool use was "
            "rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
        )
        if feedback:
            text += "To tell you how to proceed, the user said:\n" + feedback
        else:
            text += "STOP what you are doing and wait for the user to tell you how to proceed."
        return self.result(tool_id, text, is_error=True, toolDenialKind="user-rejected",
                           toolUseResult="User rejected tool use")

    def interrupt(self, for_tool: bool = False) -> dict[str, Any]:
        suffix = " for tool use" if for_tool else ""
        return self._base("user", message={"role": "user", "content": [
            {"type": "text", "text": f"[Request interrupted by user{suffix}]"}
        ]})

    def queued(self, prompt: str, mode: str = "prompt") -> dict[str, Any]:
        return self._base("attachment", attachment={"type": "queued_command", "prompt": prompt, "commandMode": mode})

    def sidechain_say(self, text: str) -> dict[str, Any]:
        rec = self.say(text)
        rec["isSidechain"] = True
        return rec

    def noise(self) -> None:
        self.records.append({"type": "last-prompt", "sessionId": self.session_id, "lastPrompt": "x"})
        self.records.append({"type": "system", "subtype": "turn_duration", "uuid": "sys", "sessionId": self.session_id})

    def write(self, path: Path) -> Path:
        path.write_text("\n".join(json.dumps(r) for r in self.records) + "\n", encoding="utf-8")
        return path
