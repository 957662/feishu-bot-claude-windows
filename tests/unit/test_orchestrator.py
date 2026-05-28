"""Tests for Orchestrator — per-binding coroutine group lifecycle."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude_win.config.binding import BindingConfig, BindingStore
from feishu_bot_claude_win.daemon.feishu import FakeLarkCli
from feishu_bot_claude_win.daemon.orchestrator import Orchestrator
from feishu_bot_claude_win.daemon.zellij import FakeTmux


def _config(name="foo-bot", project_dir="/abs/foo") -> BindingConfig:
    return BindingConfig(
        name=name,
        project_dir=project_dir,
        tmux_session=f"claude-{name}",
        feishu_app_id=f"cli_{name}",
        secret_ref=f"feishu-bot-claude.{name}.app_secret",
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )


@pytest.fixture
def orch_setup(tmp_path):
    tmux = FakeTmux()
    lark = FakeLarkCli()
    store = BindingStore(tmp_path / "bindings.toml")
    orch = Orchestrator(
        store=store,
        tmux_factory=lambda binding_name: tmux,
        lark_factory=lambda binding: lark,
        data_dir=tmp_path,
    )
    return orch, tmux, lark, store, tmp_path


@pytest.mark.asyncio
async def test_start_binding_requires_existing_binding(orch_setup):
    orch, *_ = orch_setup
    with pytest.raises(KeyError, match="no binding for cwd"):
        await orch.start_binding(cwd="/abs/unknown")


@pytest.mark.asyncio
async def test_start_binding_requires_tmux_session(orch_setup):
    orch, tmux, lark, store, td = orch_setup
    project_dir = td / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    with pytest.raises(RuntimeError, match="zellij session.*not running"):
        await orch.start_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_start_binding_happy_path(orch_setup):
    orch, tmux, lark, store, td = orch_setup
    project_dir = td / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    tmux.set_session("claude-foo-bot", exists=True)

    await orch.start_binding(cwd=str(project_dir), jsonl_path=td / "session.jsonl")
    try:
        running = orch.get_running("foo-bot")
        assert running is not None
        assert running.config.name == "foo-bot"
    finally:
        await orch.stop_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_start_already_running_rejects(orch_setup):
    orch, tmux, lark, store, td = orch_setup
    project_dir = td / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    tmux.set_session("claude-foo-bot", exists=True)

    await orch.start_binding(cwd=str(project_dir), jsonl_path=td / "session.jsonl")
    try:
        with pytest.raises(RuntimeError, match="already running"):
            await orch.start_binding(cwd=str(project_dir), jsonl_path=td / "session.jsonl")
    finally:
        await orch.stop_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_stop_cancels_coroutines(orch_setup):
    orch, tmux, lark, store, td = orch_setup
    project_dir = td / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    tmux.set_session("claude-foo-bot", exists=True)

    await orch.start_binding(cwd=str(project_dir), jsonl_path=td / "session.jsonl")
    await orch.stop_binding(cwd=str(project_dir))
    assert orch.get_running("foo-bot") is None


@pytest.mark.asyncio
async def test_list_running_returns_names(orch_setup):
    orch, tmux, lark, store, td = orch_setup
    a = td / "a"; a.mkdir()
    b = td / "b"; b.mkdir()
    store.add(_config(project_dir=str(a), name="bot-a"))
    store.add(_config(project_dir=str(b), name="bot-b"))
    tmux.set_session("claude-bot-a", exists=True)
    tmux.set_session("claude-bot-b", exists=True)

    await orch.start_binding(cwd=str(a), jsonl_path=td / "a.jsonl")
    try:
        running = orch.list_running()
        assert running == ["bot-a"]
        await orch.start_binding(cwd=str(b), jsonl_path=td / "b.jsonl")
        assert set(orch.list_running()) == {"bot-a", "bot-b"}
    finally:
        await orch.stop_binding(cwd=str(a))
        await orch.stop_binding(cwd=str(b))
