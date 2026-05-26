"""Tests for BindingRuntimeState — per-binding live state."""

import pytest

from feishu_bot_claude_win.daemon.state import BindingRuntimeState


def test_initial_state_empty():
    s = BindingRuntimeState(binding_name="foo-bot")
    assert s.current_turn_card_id is None
    assert s.jsonl_offset == 0
    assert s.last_event_uuid is None


def test_set_current_turn_card():
    s = BindingRuntimeState(binding_name="foo-bot")
    s.set_current_turn_card("om_xxx")
    assert s.current_turn_card_id == "om_xxx"


def test_reset_clears_card_keeps_offset():
    s = BindingRuntimeState(binding_name="foo-bot")
    s.set_current_turn_card("om_xxx")
    s.advance_offset(100)
    s.reset_current_turn()
    assert s.current_turn_card_id is None
    assert s.jsonl_offset == 100


def test_persist_and_restore(tmp_path):
    path = tmp_path / "state.json"
    s = BindingRuntimeState(binding_name="foo-bot")
    s.set_current_turn_card("om_xxx")
    s.advance_offset(42)
    s.last_event_uuid = "e-99"
    s.save(path)

    restored = BindingRuntimeState.load("foo-bot", path)
    assert restored.current_turn_card_id == "om_xxx"
    assert restored.jsonl_offset == 42
    assert restored.last_event_uuid == "e-99"


def test_load_missing_file_returns_fresh_state(tmp_path):
    state = BindingRuntimeState.load("missing-bot", tmp_path / "nope.json")
    assert state.binding_name == "missing-bot"
    assert state.current_turn_card_id is None
