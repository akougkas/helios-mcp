"""Transcript parsing: turn boundaries and the user signals attached to them."""

from __future__ import annotations

from pathlib import Path

from helios_mcp.transcript import parse_records, parse_timestamp, parse_transcript

from .transcript_fixtures import TranscriptBuilder


def test_split_assistant_records_fold_into_one_turn_per_prompt(tmp_path: Path):
    b = TranscriptBuilder()
    b.meta("<local-command-caveat>Caveat</local-command-caveat>")
    b.prompt("fix the bug")
    b.think("hmm", msg_id="m1")
    b.tool("Bash", {"command": "pytest -q"}, "t1", msg_id="m1")
    b.noise()
    b.result("t1", "1 failed")
    b.say("Fixed it.", msg_id="m2")
    b.prompt("thanks, now add a test")
    b.say("Added.")
    b.sidechain_say("subagent chatter")
    session = parse_transcript(b.write(tmp_path / "s.jsonl"))

    assert session.session_id == "sess-0001"
    first, second = session.turns
    assert first.prompt is not None and first.prompt.text == "fix the bug"
    assert [c.name for c in first.tool_calls] == ["Bash"]
    assert first.text == "Fixed it."
    assert first.next_input is not None and first.next_input.text.startswith("thanks")
    assert second.text == "Added."  # sidechain text excluded
    assert second.next_input is None
    assert first.turn_id != second.turn_id
    assert first.timestamp == parse_timestamp(b.records[2]["timestamp"])
    assert first.model == "claude-test"


def test_turn_ids_are_stable_across_reparses(tmp_path: Path):
    b = TranscriptBuilder()
    b.prompt("a")
    b.say("one")
    path = b.write(tmp_path / "s.jsonl")
    before = [t.turn_id for t in parse_transcript(path).turns]
    b.prompt("b")
    b.say("two")
    after = [t.turn_id for t in parse_transcript(b.write(path)).turns]
    assert after[: len(before)] == before


def test_interrupt_marks_turn_and_next_prompt_follows_it():
    b = TranscriptBuilder()
    b.prompt("deploy it")
    b.tool("Bash", {"command": "make deploy"}, "t1")
    b.interrupt(for_tool=True)
    b.prompt("stop, use staging")
    b.say("ok")
    turns = parse_records(b.records).turns
    assert turns[0].interrupted
    assert turns[0].next_input is not None
    assert turns[0].next_input.text == "stop, use staging"
    assert not turns[1].interrupted


def test_denial_with_feedback_is_captured():
    b = TranscriptBuilder()
    b.prompt("clean up")
    b.tool("Bash", {"command": "rm -rf build"}, "t1")
    b.deny("t1", feedback="ask me before deleting anything")
    b.tool("Bash", {"command": "ls"}, "t2")
    b.deny("t2")
    turn = parse_records(b.records).turns[0]
    denials = turn.denials
    assert [c.tool_use_id for c in denials] == ["t1", "t2"]
    assert denials[0].denial_feedback == "ask me before deleting anything"
    assert denials[1].denial_feedback is None


def test_non_human_inputs_are_classified():
    b = TranscriptBuilder()
    b.prompt("watch the job")
    b.say("watching")
    b.notification()
    b.say("job finished")
    b.prompt("<command-name>/clear</command-name>")
    turns = parse_records(b.records).turns
    assert turns[0].next_input is not None and turns[0].next_input.kind == "notification"
    assert turns[1].prompt is not None and turns[1].prompt.kind == "notification"
    assert turns[1].next_input is not None and turns[1].next_input.kind == "command"


def test_queued_human_prompt_is_a_steer_but_notifications_are_not():
    b = TranscriptBuilder()
    b.prompt("refactor")
    b.tool("Edit", {"file_path": "a.py"}, "t1")
    b.queued("<task-notification>x</task-notification>", mode="task-notification")
    b.queued("shorter please")
    b.result("t1")
    b.say("done")
    turn = parse_records(b.records).turns[0]
    assert [s.text for s in turn.steers] == ["shorter please"]


def test_corrupt_lines_and_missing_file_are_tolerated(tmp_path: Path):
    b = TranscriptBuilder()
    b.prompt("hi")
    b.say("hello")
    path = b.write(tmp_path / "s.jsonl")
    with path.open("a") as fh:
        fh.write('{"type": "user", "trunc')
    assert len(parse_transcript(path).turns) == 1
    assert parse_transcript(tmp_path / "missing.jsonl", "x").turns == []


def test_declined_question_and_auto_mode_block_are_not_user_denials():
    b = TranscriptBuilder()
    b.prompt("plan the migration")
    b.tool("AskUserQuestion", {"questions": []}, "q1")
    b.deny("q1", feedback="The user wants to clarify these questions.")
    b.tool("Bash", {"command": "rm -rf /data"}, "t1")
    b.result("t1", "Permission for this action was denied by the auto mode classifier.",
             is_error=True, toolDenialKind="automode-blocked")
    b.tool("ExitPlanMode", {}, "p1")
    b.deny("p1", feedback="no, keep the old schema")
    turn = parse_records(b.records).turns[0]
    assert [c.tool_use_id for c in turn.denials] == ["p1"]
    assert turn.denials[0].denial_feedback == "no, keep the old schema"


def test_denial_in_a_headless_session_is_not_the_person_refusing():
    b = TranscriptBuilder()
    b.prompt("clean up", entrypoint="sdk-cli")
    b.tool("Bash", {"command": "rm -rf build"}, "t1")
    b.deny("t1")["entrypoint"] = "sdk-cli"
    assert parse_records(b.records).turns[0].denials == []
