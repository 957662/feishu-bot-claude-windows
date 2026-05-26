"""Unit tests for the daemon TCP server (Windows-native edition).

The macOS edition tested a Unix socket with 0600 perms; on Windows we use TCP
loopback and verify (1) round-trip handlers (ping, unknown op), (2) that the
server publishes its bound port to data_dir/control.port so the CLI can find it.
"""

import asyncio
import json

import pytest

from feishu_bot_claude_win.daemon.server import serve
from feishu_bot_claude_win.proto import Request


async def _start_server(tmp_path):
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(
        host="127.0.0.1",
        port=0,  # ephemeral
        bindings_path=bindings_path,
        data_dir=tmp_path,
    )
    port = server.sockets[0].getsockname()[1]
    return server, port


@pytest.mark.asyncio
async def test_server_responds_to_ping(tmp_path):
    server, port = await _start_server(tmp_path)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        req = Request(op="ping", args={}, request_id="t1")
        writer.write((req.to_json_line() + "\n").encode())
        await writer.drain()

        lines = []
        while True:
            line = await reader.readline()
            if not line:
                break
            lines.append(line.decode().rstrip("\n"))

        writer.close()
        await writer.wait_closed()

        events = [json.loads(line) for line in lines]
        assert events[0]["type"] == "result"
        assert events[0]["ok"] is True
        assert events[0]["data"]["pong"] is True
        assert events[-1]["type"] == "done"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_server_responds_to_unknown_op(tmp_path):
    server, port = await _start_server(tmp_path)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        req = Request(op="totally-unknown", args={}, request_id="t2")
        writer.write((req.to_json_line() + "\n").encode())
        await writer.drain()

        lines = []
        while True:
            line = await reader.readline()
            if not line:
                break
            lines.append(line.decode().rstrip("\n"))

        writer.close()
        await writer.wait_closed()

        events = [json.loads(line) for line in lines]
        assert events[0]["type"] == "result"
        assert events[0]["ok"] is False
        assert "unknown" in events[0]["error"].lower() or "no handler" in events[0]["error"].lower()
        assert events[-1]["type"] == "done"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_server_publishes_port_file(tmp_path):
    """The CLI discovers the daemon via data_dir/control.port — verify it's written."""
    server, port = await _start_server(tmp_path)
    try:
        port_file = tmp_path / "control.port"
        assert port_file.exists()
        host, port_str = port_file.read_text().strip().rsplit(":", 1)
        assert host == "127.0.0.1"
        assert int(port_str) == port
    finally:
        server.close()
        await server.wait_closed()
