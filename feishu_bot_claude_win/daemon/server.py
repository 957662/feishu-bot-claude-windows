"""Asyncio TCP-loopback server (Windows-native).

Listens on 127.0.0.1:<ephemeral>; the chosen port is written to
data_dir/control.port so the CLI can discover it. One Request →
many ResponseEvents → DoneEvent → close (same protocol as the macOS edition).

Security model: bind to 127.0.0.1 only (no external access). Windows enforces
loopback-only at the network stack; per-user isolation on multi-user hosts is
NOT provided — if you share a workstation with another local user, switch to
Named Pipes with explicit ACLs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from feishu_bot_claude_win.config.binding import BindingStore
from feishu_bot_claude_win.daemon.dispatcher import Dispatcher
from feishu_bot_claude_win.daemon.handlers import (
    handle_bind,
    handle_config,
    handle_list,
    handle_ping,
    handle_shell,
    handle_start,
    handle_status,
    handle_stop,
    handle_unbind,
)
from feishu_bot_claude_win.proto import DoneEvent, Request, ResultEvent

logger = logging.getLogger(__name__)


def _build_dispatcher(
    store: BindingStore,
    orchestrator=None,
    keychain=None,
    auth_runner_factory=None,
    menu_pusher=None,
    data_dir=None,
) -> Dispatcher:
    d = Dispatcher()
    d.register("ping", handle_ping)
    d.register("status", handle_status)

    async def _list_with_store(args):
        async for ev in handle_list(args, store=store):
            yield ev
    d.register("list", _list_with_store)

    if orchestrator is not None:
        async def _start_with_orch(args):
            from feishu_bot_claude_win.daemon.handlers import handle_start_with_orchestrator
            async for ev in handle_start_with_orchestrator(args, orchestrator=orchestrator):
                yield ev
        async def _stop_with_orch(args):
            from feishu_bot_claude_win.daemon.handlers import handle_stop_with_orchestrator
            async for ev in handle_stop_with_orchestrator(args, orchestrator=orchestrator):
                yield ev
        d.register("start", _start_with_orch)
        d.register("stop", _stop_with_orch)
    else:
        d.register("start", handle_start)
        d.register("stop", handle_stop)

    if orchestrator is not None and keychain is not None and auth_runner_factory is not None:
        async def _bind_with_orch(args):
            from feishu_bot_claude_win.daemon.handlers import handle_bind_with_orchestrator
            async for ev in handle_bind_with_orchestrator(
                args, store=store, keychain=keychain,
                auth_runner_factory=auth_runner_factory,
                menu_pusher=menu_pusher, data_dir=data_dir,
                orchestrator=orchestrator,
            ):
                yield ev
        async def _unbind_with_orch(args):
            from feishu_bot_claude_win.daemon.handlers import handle_unbind_with_orchestrator
            async for ev in handle_unbind_with_orchestrator(args, store=store, keychain=keychain):
                yield ev
        d.register("bind", _bind_with_orch)
        d.register("unbind", _unbind_with_orch)
    else:
        d.register("bind", handle_bind)
        d.register("unbind", handle_unbind)

    d.register("config", handle_config)
    d.register("shell", handle_shell)
    return d


async def _handle_client(reader, writer, dispatcher: Dispatcher) -> None:
    try:
        line = await reader.readline()
        if not line:
            return
        try:
            req = Request.from_json_line(line.decode().rstrip("\n"))
            req.validate()
        except (json.JSONDecodeError, ValueError) as e:
            await _write_event(writer, ResultEvent(ok=False, data=None, error=f"bad request: {e}"))
            await _write_event(writer, DoneEvent())
            return

        try:
            handler = dispatcher.lookup(req.op)
        except KeyError as e:
            await _write_event(writer, ResultEvent(ok=False, data=None, error=str(e)))
            await _write_event(writer, DoneEvent())
            return

        async for event in handler(req.args):
            await _write_event(writer, event)
    except Exception as e:  # noqa: BLE001
        logger.exception("client handler crashed")
        try:
            await _write_event(writer, ResultEvent(ok=False, data=None, error=f"server crash: {e}"))
            await _write_event(writer, DoneEvent())
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _write_event(writer, event) -> None:
    writer.write((event.to_json_line() + "\n").encode())
    await writer.drain()


async def serve(
    host: str = "127.0.0.1",
    port: int = 0,
    bindings_path: Path | None = None,
    orchestrator=None,
    keychain=None,
    auth_runner_factory=None,
    menu_pusher=None,
    data_dir: Path | None = None,
) -> asyncio.AbstractServer:
    """Start the daemon server on TCP loopback. Returns the running server.

    port=0 → ephemeral. Chosen port is written to `data_dir/control.port`
    so the CLI can discover it.
    """
    if data_dir is None:
        raise ValueError("data_dir is required (port discovery file is written there)")
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    store = orchestrator._store if orchestrator is not None else BindingStore(bindings_path)
    dispatcher = _build_dispatcher(
        store,
        orchestrator=orchestrator,
        keychain=keychain,
        auth_runner_factory=auth_runner_factory,
        menu_pusher=menu_pusher,
        data_dir=data_dir,
    )

    async def _on_client(reader, writer):
        await _handle_client(reader, writer, dispatcher)

    server = await asyncio.start_server(_on_client, host=host, port=port)

    # Pull the actual bound port for ephemeral selection and publish it.
    actual_port = server.sockets[0].getsockname()[1]
    port_file = data_dir / "control.port"
    port_file.write_text(f"{host}:{actual_port}\n", encoding="utf-8")
    logger.info("daemon listening on %s:%d (port written to %s)", host, actual_port, port_file)
    return server
