"""Tests for grouping jsonl events into Turns."""

import json

import pytest

from feishu_bot_claude_win.rendering.turn import JsonlEvent, Turn, group_into_turns


def _evt(role: str, **extra) -> dict:
    base = {"role": role, "uuid": f"u-{role}-{extra.get('idx', 0)}"}
    base.update(extra)
    return base


def test_single_user_message_creates_one_turn():
    events = [JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "hi"}]))]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert turns[0].user_event is not None
    assert turns[0].assistant_events == []


def test_user_then_assistant_groups_into_one_turn():
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "hi"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "hello"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert len(turns[0].assistant_events) == 1


def test_assistant_with_tool_use_and_result_in_same_turn():
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "read"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/x"}}])),
        JsonlEvent.from_dict(_evt("user", content=[{"type": "tool_result", "tool_use_id": "t1", "content": "data"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "done"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert len(turns[0].assistant_events) == 3


def test_two_user_messages_create_two_turns():
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "first"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "a"}])),
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "second"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "b"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 2
    assert turns[0].user_event.text() == "first"
    assert turns[1].user_event.text() == "second"


def test_load_jsonl_file(tmp_path):
    path = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "hi"}]}),
        json.dumps({"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "hello"}]}),
    ]
    path.write_text("\n".join(lines) + "\n")

    events = list(JsonlEvent.load_file(path))
    assert len(events) == 2
    assert events[0].role == "user"
    assert events[1].role == "assistant"


def test_jsonl_event_skips_blank_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        '{"role": "user", "uuid": "u1", "content": []}\n'
        '\n'
        '   \n'
        '{"role": "assistant", "uuid": "a1", "content": []}\n'
    )
    events = list(JsonlEvent.load_file(path))
    assert len(events) == 2


def test_jsonl_event_text_method():
    e = JsonlEvent.from_dict({"role": "user", "uuid": "u1",
                              "content": [{"type": "text", "text": "first"}, {"type": "text", "text": " more"}]})
    assert e.text() == "first more"


def test_tool_use_only_user_event_belongs_to_previous_turn():
    """A user message whose content is ONLY tool_result(s) (no text) belongs to the previous turn."""
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "go"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}])),
        JsonlEvent.from_dict(_evt("user", content=[{"type": "tool_result", "tool_use_id": "t1", "content": "x"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert turns[0].user_event.text() == "go"
