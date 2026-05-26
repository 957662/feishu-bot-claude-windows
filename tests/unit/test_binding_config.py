"""Tests for BindingConfig dataclass."""

from datetime import datetime, timezone

import pytest

from feishu_bot_claude_win.config.binding import BindingConfig


def _example_config(**overrides) -> BindingConfig:
    defaults = dict(
        name="foo-bot",
        project_dir="/Users/me/project/foo",
        tmux_session="claude-foo",
        feishu_app_id="cli_xxxxxxxx",
        secret_ref="feishu-bot-claude.foo-bot.app_secret",
        render_style="rich",
        replay_on_start="all",
        mute_thinking=False,
        card_throttle_ms=300,
        domain="https://open.feishu.cn",
        api_timeout_ms=5000,
        upload_timeout_ms=60000,
        event_silent_threshold_ms=60000,
        event_dead_threshold_ms=120000,
        reconnect_grace_failures=3,
        created_at=datetime(2026, 5, 26, 18, 50, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return BindingConfig(**defaults)


def test_binding_config_accepts_valid_values():
    cfg = _example_config()
    assert cfg.name == "foo-bot"
    assert cfg.render_style == "rich"


def test_binding_config_rejects_invalid_render_style():
    with pytest.raises(ValueError, match="render_style"):
        _example_config(render_style="fancy")


def test_binding_config_rejects_invalid_replay_value():
    with pytest.raises(ValueError, match="replay_on_start"):
        _example_config(replay_on_start="2")
    with pytest.raises(ValueError, match="replay_on_start"):
        _example_config(replay_on_start="some")


def test_binding_config_rejects_negative_timeouts():
    with pytest.raises(ValueError, match="api_timeout_ms"):
        _example_config(api_timeout_ms=-1)


def test_binding_config_rejects_empty_name():
    with pytest.raises(ValueError, match="name"):
        _example_config(name="")


def test_binding_config_rejects_non_absolute_project_dir():
    with pytest.raises(ValueError, match="project_dir"):
        _example_config(project_dir="relative/path")


def test_binding_config_accepts_security_fields():
    cfg = _example_config(
        allow_users=["ou_xxx", "ou_yyy"],
        require_confirm_patterns=[r"rm\s+-rf"],
        max_message_length=4000,
        session_idle_timeout_seconds=1800,
    )
    assert cfg.allow_users == ["ou_xxx", "ou_yyy"]
    assert cfg.require_confirm_patterns == [r"rm\s+-rf"]
    assert cfg.max_message_length == 4000


def test_binding_config_defaults_security_empty():
    cfg = _example_config()
    assert cfg.allow_users == []
    assert cfg.require_confirm_patterns == []
    assert cfg.max_message_length == 8000  # default
    assert cfg.session_idle_timeout_seconds == 0  # disabled
