"""Tests for daemon handlers (with mocked BindingStore)."""

import pytest

from feishu_bot_claude_win.daemon.handlers import handle_ping
from feishu_bot_claude_win.proto import DoneEvent, ResultEvent


@pytest.mark.asyncio
async def test_ping_emits_result_then_done():
    """ping yields a ResultEvent(ok=True, data={pong: True}) then DoneEvent."""
    events = []
    async for ev in handle_ping(args={}):
        events.append(ev)
    assert events == [
        ResultEvent(ok=True, data={"pong": True}, error=None),
        DoneEvent(),
    ]


from datetime import datetime, timezone
from pathlib import Path

from feishu_bot_claude_win.config.binding import BindingConfig, BindingStore
from feishu_bot_claude_win.daemon.handlers import handle_list


def _example_config(name="foo-bot", project_dir="/abs/foo") -> BindingConfig:
    return BindingConfig(
        name=name,
        project_dir=project_dir,
        tmux_session=f"claude-{name}",
        feishu_app_id=f"cli_{name}",
        secret_ref=f"feishu-bot-claude.{name}.app_secret",
        created_at=datetime(2026, 5, 26, 18, 50, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_list_returns_all_bindings(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_example_config(name="foo-bot", project_dir="/abs/foo"))
    store.add(_example_config(name="bar-bot", project_dir="/abs/bar"))

    events = []
    async for ev in handle_list(args={}, store=store):
        events.append(ev)

    assert len(events) == 2  # ResultEvent + DoneEvent
    result = events[0]
    assert result.ok is True
    assert {b["name"] for b in result.data["bindings"]} == {"foo-bot", "bar-bot"}
    assert events[-1] == DoneEvent()


@pytest.mark.asyncio
async def test_list_empty_store(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    events = []
    async for ev in handle_list(args={}, store=store):
        events.append(ev)
    assert events[0].data == {"bindings": []}


from feishu_bot_claude_win.daemon.handlers import (
    handle_bind,
    handle_unbind,
    handle_start,
    handle_stop,
    handle_config,
    handle_status,
    handle_shell,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [handle_bind, handle_unbind, handle_start, handle_stop, handle_config, handle_shell])
async def test_stub_handlers_return_not_implemented(handler):
    """Each stub handler returns ok=False with 'not yet implemented'."""
    events = []
    async for ev in handler(args={}):
        events.append(ev)
    assert events[0].ok is False
    assert "not yet implemented" in events[0].error.lower()
    assert events[-1] == DoneEvent()


@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    """status returns ok=True with daemon version + uptime."""
    events = []
    async for ev in handle_status(args={}):
        events.append(ev)
    assert events[0].ok is True
    assert "version" in events[0].data
    assert events[-1] == DoneEvent()


from feishu_bot_claude_win.daemon.handlers import (
    handle_start_with_orchestrator,
    handle_stop_with_orchestrator,
)
from feishu_bot_claude_win.daemon.orchestrator import Orchestrator
from feishu_bot_claude_win.daemon.zellij import FakeTmux
from feishu_bot_claude_win.daemon.feishu import FakeLarkCli


@pytest.mark.asyncio
async def test_handle_start_succeeds(tmp_path):
    tmux = FakeTmux()
    lark = FakeLarkCli()
    store = BindingStore(tmp_path / "bindings.toml")
    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: lark,
        data_dir=tmp_path,
    )
    project_dir = tmp_path / "p"
    project_dir.mkdir()
    cfg = _example_config(name="bot-p", project_dir=str(project_dir))
    store.add(cfg)
    tmux.set_session("claude-bot-p", exists=True)

    events = []
    async for ev in handle_start_with_orchestrator(
        args={"cwd": str(project_dir), "jsonl_path": str(tmp_path / "session.jsonl")},
        orchestrator=orch,
    ):
        events.append(ev)
    assert events[0].ok is True
    assert "bot-p" in events[0].data.get("name", "")
    await orch.stop_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_handle_start_unknown_cwd_fails(tmp_path):
    tmux = FakeTmux()
    lark = FakeLarkCli()
    store = BindingStore(tmp_path / "bindings.toml")
    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: lark,
        data_dir=tmp_path,
    )
    events = []
    async for ev in handle_start_with_orchestrator(
        args={"cwd": "/abs/nowhere"}, orchestrator=orch,
    ):
        events.append(ev)
    assert events[0].ok is False
    assert "no binding" in events[0].error.lower()


from feishu_bot_claude_win.daemon.handlers import (
    handle_bind_with_orchestrator,
    handle_unbind_with_orchestrator,
)
from feishu_bot_claude_win.config.keychain import InMemoryKeychainStore


async def _fake_auth_runner(name):
    for line in [
        "█████████████████████████████████████████████",
        "████ ▄▄▄▄▄ █▄ ▄▀ ▀▀█ ▀ ▀▀█▄▄▄▀▀▄██ ▄▄▄▄▄ ████",
        "▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
        "",
        "  https://open.feishu.cn/page/cli?user_code=ABCD-EFGH",
        "等待配置应用...",
    ]:
        yield line + "\n"


@pytest.mark.asyncio
async def test_handle_bind_creates_binding(tmp_path, monkeypatch):
    import asyncio
    from feishu_bot_claude_win.daemon import handlers as handlers_module
    # In test env, lark-cli isn't really invoked — stub the extractor.
    monkeypatch.setattr(handlers_module, "_extract_app_id_from_larkcli", lambda n: f"cli_test_{n}")

    store = BindingStore(tmp_path / "bindings.toml")
    keychain = InMemoryKeychainStore()

    class FakeOrchestrator:
        def __init__(self):
            self.pending_binds = {}
    orch = FakeOrchestrator()

    events = []
    async for ev in handle_bind_with_orchestrator(
        args={"name": "foo-bot", "cwd": str(tmp_path / "proj")},
        store=store,
        keychain=keychain,
        auth_runner_factory=lambda name: _fake_auth_runner(name),
        menu_pusher=None,
        data_dir=tmp_path,
        orchestrator=orch,
    ):
        events.append(ev)

    # Handler should yield immediately after the QR appears
    assert any(e.__class__.__name__ == "QRCodeEvent" for e in events)
    result = next(e for e in events if e.__class__.__name__ == "ResultEvent")
    assert result.ok is True
    assert "awaiting_scan" in result.data.get("status", "")

    # Background task should still be running OR just completed
    # Wait for it to finish (the fake auth runner exits quickly after emitting QR)
    if "foo-bot" in orch.pending_binds:
        await orch.pending_binds["foo-bot"]

    # Give any remaining async tasks a chance to complete
    await asyncio.sleep(0)

    binding = store.find_by_name("foo-bot")
    assert binding is not None
    # app_id will be "larkcli-profile:foo-bot" since no real lark-cli config exists in test env
    assert binding.feishu_app_id is not None
    # secret_ref key was stored (empty string since lark-cli manages the real secret)
    assert keychain.get(binding.secret_ref) is not None


@pytest.mark.asyncio
async def test_handle_unbind_removes_binding_and_secret(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    keychain = InMemoryKeychainStore()
    cfg = _example_config(name="foo-bot")
    store.add(cfg)
    keychain.put(cfg.secret_ref, "the-secret")

    events = []
    async for ev in handle_unbind_with_orchestrator(
        args={"name": "foo-bot"},
        store=store,
        keychain=keychain,
    ):
        events.append(ev)

    result = next(e for e in events if e.__class__.__name__ == "ResultEvent")
    assert result.ok is True
    assert store.find_by_name("foo-bot") is None
    assert keychain.get(cfg.secret_ref) is None
