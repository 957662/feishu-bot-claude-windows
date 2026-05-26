"""Tests for FakeTmux — records calls, replays canned responses."""

import pytest

from feishu_bot_claude_win.daemon.zellij import FakeTmux, Tmux


def test_fake_records_new_session():
    tmux: Tmux = FakeTmux()
    tmux.new_session(name="claude-foo", cwd="/abs/foo", command="claude")
    assert tmux.calls == [
        ("new_session", {"name": "claude-foo", "cwd": "/abs/foo", "command": "claude"}),
    ]


def test_fake_has_session_returns_configured_value():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    assert tmux.has_session("claude-foo") is True
    assert tmux.has_session("claude-other") is False


def test_fake_send_keys_records():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    tmux.send_keys(session="claude-foo", keys="/compact\n")
    assert tmux.calls[-1] == ("send_keys", {"session": "claude-foo", "keys": "/compact\n"})


def test_fake_send_keys_raises_if_session_missing():
    tmux = FakeTmux()
    with pytest.raises(RuntimeError, match="no session"):
        tmux.send_keys(session="claude-foo", keys="x")


def test_fake_kill_session_records():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    tmux.kill_session("claude-foo")
    assert ("kill_session", {"name": "claude-foo"}) in tmux.calls
    assert tmux.has_session("claude-foo") is False


def test_fake_new_session_idempotent_with_attach_existing():
    """new_session(attach_if_exists=True) on an existing session is a no-op."""
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    tmux.new_session(name="claude-foo", cwd="/abs/foo", command="claude", attach_if_exists=True)
    last = tmux.calls[-1]
    assert last[0] in ("attach_session", "no_op_session_exists")
