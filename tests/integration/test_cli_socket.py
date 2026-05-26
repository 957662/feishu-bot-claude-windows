"""Integration test for the CLI TCP client against a real daemon."""

import pytest

from feishu_bot_claude_win.cli import run_op
from feishu_bot_claude_win.daemon import serve
from feishu_bot_claude_win.proto import DoneEvent, ResultEvent


@pytest.fixture
async def running_daemon(tmp_path):
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(
        host="127.0.0.1",
        port=0,
        bindings_path=bindings_path,
        data_dir=tmp_path,
    )
    yield tmp_path  # CLI looks up the port from data_dir/control.port
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_run_op_ping_returns_pong(running_daemon):
    """CLI client connects to daemon, sends ping, receives pong."""
    events = []
    async for ev in run_op(data_dir=running_daemon, op="ping", args={}):
        events.append(ev)
    assert len(events) == 2
    assert isinstance(events[0], ResultEvent)
    assert events[0].ok is True
    assert events[0].data == {"pong": True}
    assert isinstance(events[1], DoneEvent)


@pytest.mark.asyncio
async def test_run_op_status_returns_version(running_daemon):
    events = []
    async for ev in run_op(data_dir=running_daemon, op="status", args={}):
        events.append(ev)
    assert events[0].ok is True
    assert "version" in events[0].data
