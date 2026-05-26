"""Test that daemon restart restores running bindings from disk state."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude_win.config.binding import BindingConfig, BindingStore
from feishu_bot_claude_win.daemon.feishu import FakeLarkCli
from feishu_bot_claude_win.daemon.orchestrator import Orchestrator
from feishu_bot_claude_win.daemon.state import BindingRuntimeState
from feishu_bot_claude_win.daemon.zellij import FakeTmux


@pytest.mark.asyncio
async def test_orchestrator_restores_bindings_from_disk(tmp_path):
    project_dir = tmp_path / "p"; project_dir.mkdir()
    jsonl = tmp_path / "p.jsonl"
    jsonl.write_text("")

    cfg = BindingConfig(
        name="bot-p", project_dir=str(project_dir),
        tmux_session="claude-bot-p", feishu_app_id="cli_x",
        secret_ref="x", created_at=datetime.now(timezone.utc),
    )
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(cfg)

    # Simulate that the binding was running before crash: state.json exists with offset
    state = BindingRuntimeState(binding_name="bot-p", jsonl_offset=42)
    state.save(tmp_path / "state-bot-p.json")
    # Write a "running" marker
    (tmp_path / "running-bot-p").write_text(json.dumps({"jsonl_path": str(jsonl)}))

    tmux = FakeTmux()
    tmux.set_session("claude-bot-p", exists=True)

    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: FakeLarkCli(),
        data_dir=tmp_path,
    )

    stale = await orch.restore_from_disk()
    try:
        assert "bot-p" in orch.list_running()
        running = orch.get_running("bot-p")
        assert running.state.jsonl_offset == 42
        assert stale == []
    finally:
        await orch.stop_all()


@pytest.mark.asyncio
async def test_restore_skips_bindings_with_missing_tmux(tmp_path):
    """If tmux session was killed during crash, restore should mark stale."""
    project_dir = tmp_path / "p"; project_dir.mkdir()
    cfg = BindingConfig(
        name="bot-p", project_dir=str(project_dir),
        tmux_session="claude-bot-p", feishu_app_id="cli_x",
        secret_ref="x", created_at=datetime.now(timezone.utc),
    )
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(cfg)
    (tmp_path / "running-bot-p").write_text("{}")

    tmux = FakeTmux()  # No session registered → stale

    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: FakeLarkCli(),
        data_dir=tmp_path,
    )

    stale = await orch.restore_from_disk()
    assert "bot-p" not in orch.list_running()
    assert "bot-p" in stale


@pytest.mark.asyncio
async def test_restore_with_no_markers_is_noop(tmp_path):
    """If no running-* markers exist, restore returns empty."""
    store = BindingStore(tmp_path / "bindings.toml")
    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: FakeTmux(),
        lark_factory=lambda c: FakeLarkCli(),
        data_dir=tmp_path,
    )
    stale = await orch.restore_from_disk()
    assert stale == []
    assert orch.list_running() == []
