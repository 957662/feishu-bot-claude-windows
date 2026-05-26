"""CLI entry (Windows-native): TCP loopback client + Click commands.

Differences from the macOS edition:
- Connects to daemon via TCP loopback (port discovered from data_dir/control.port)
- `start <url>` (Windows) replaces `open` / `xdg-open` for auto-launching browser
- `shell` spawns zellij + claude in a new console window (no exec — Windows
  doesn't have execv-style PATH-based replacement that keeps the parent alive
  as a TUI; we Popen and exit).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import AsyncIterator

import click

from feishu_bot_claude_win.proto import (
    DoneEvent,
    LogEvent,
    ProgressEvent,
    QRCodeEvent,
    ResponseEvent,
    ResultEvent,
    parse_response_line,
    Request,
)

DEFAULT_DATA_DIR = Path(os.environ.get(
    "FEISHU_BOT_CLAUDE_DATA_DIR",
    Path.home() / ".feishu-bot-claude-win",
))


def _read_control_port(data_dir: Path) -> tuple[str, int]:
    """Read `data_dir/control.port` and return (host, port).

    Raises FileNotFoundError if the file is missing — that's a strong signal
    the daemon isn't running.
    """
    port_file = data_dir / "control.port"
    text = port_file.read_text(encoding="utf-8").strip()
    host, port_str = text.rsplit(":", 1)
    return host, int(port_str)


async def run_op(
    data_dir: Path,
    op: str,
    args: dict,
    request_id: str = "",
) -> AsyncIterator[ResponseEvent]:
    """Open the daemon TCP socket, send one Request, yield ResponseEvents."""
    host, port = _read_control_port(data_dir)
    reader, writer = await asyncio.open_connection(host, port)
    try:
        req = Request(op=op, args=args, request_id=request_id)
        writer.write((req.to_json_line() + "\n").encode())
        await writer.drain()

        while True:
            line = await reader.readline()
            if not line:
                break
            event = parse_response_line(line.decode().rstrip("\n"))
            yield event
            if isinstance(event, DoneEvent):
                break
    finally:
        writer.close()
        await writer.wait_closed()


def render_event(event: ResponseEvent) -> str:
    if isinstance(event, LogEvent):
        if event.level == "error":
            return f"ERROR: {event.msg}"
        if event.level == "warn":
            return f"WARN: {event.msg}"
        return event.msg
    if isinstance(event, QRCodeEvent):
        return f"{event.ascii}\n\nURL: {event.url}"
    if isinstance(event, ProgressEvent):
        pct = int(event.value * 100)
        return f"[{pct}%] {event.msg}"
    if isinstance(event, ResultEvent):
        if event.ok:
            payload = json.dumps(event.data, ensure_ascii=False, indent=2) if event.data else ""
            return f"OK\n{payload}" if payload else "OK"
        return f"FAILED: {event.error}"
    if isinstance(event, DoneEvent):
        return ""
    return repr(event)


def _open_url_in_browser(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    if os.environ.get("FEISHU_BOT_CLAUDE_NO_AUTO_OPEN"):
        return False
    try:
        if sys.platform == "win32":
            # `start` is a cmd builtin; needs shell=True. Use os.startfile for
            # native default-handler behavior (avoids cmd.exe quoting headaches).
            os.startfile(url)  # noqa: S606 — opening a known-good URL
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (FileNotFoundError, OSError):
        return False


def _print_events_sync(data_dir: Path, op: str, args: dict) -> int:
    final_ok = True

    async def _drive():
        nonlocal final_ok
        try:
            async for event in run_op(data_dir=data_dir, op=op, args=args):
                rendered = render_event(event)
                if rendered:
                    click.echo(rendered)
                if isinstance(event, QRCodeEvent):
                    if _open_url_in_browser(event.url):
                        click.echo("  (浏览器已自动打开;若没弹出请手动点击上方 URL)")
                if isinstance(event, ResultEvent) and not event.ok:
                    final_ok = False
        except FileNotFoundError:
            click.echo(
                f"ERROR: daemon not running (no control.port file in {data_dir})",
                err=True,
            )
            return 2
        except ConnectionRefusedError:
            click.echo(f"ERROR: daemon not running (connection refused)", err=True)
            return 2
        return 0 if final_ok else 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(_drive())


@click.group(help="feishu-bot-claude — Feishu bridge for Claude Code (Windows)")
@click.option("--data-dir", "data_dir", type=click.Path(path_type=Path), default=DEFAULT_DATA_DIR, show_default=True)
@click.pass_context
def main(ctx, data_dir):
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = data_dir


@main.command(help="Liveness check against the daemon")
@click.pass_context
def ping(ctx):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "ping", {}))


@main.command(name="list", help="List all bindings")
@click.pass_context
def list_cmd(ctx):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "list", {}))


@main.command(help="Show daemon status")
@click.pass_context
def status(ctx):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "status", {}))


@main.command(help="Bind current project to a new Feishu bot")
@click.argument("name")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.pass_context
def bind(ctx, name, cwd):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "bind", {"name": name, "cwd": str(cwd)}))


@main.command(help="Remove a binding")
@click.argument("name")
@click.pass_context
def unbind(ctx, name):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "unbind", {"name": name}))


@main.command(help="Start mirror for current project")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.pass_context
def start(ctx, cwd):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "start", {"cwd": str(cwd)}))


@main.command(help="Stop mirror for current project")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.pass_context
def stop(ctx, cwd):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "stop", {"cwd": str(cwd)}))


@main.command(help="Adjust binding parameters")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.argument("kv", nargs=-1)
@click.pass_context
def config(ctx, cwd, kv):
    sys.exit(_print_events_sync(ctx.obj["data_dir"], "config", {"cwd": str(cwd), "kv": list(kv)}))


def _resolve_session_name(data_dir: Path, cwd: Path) -> str:
    """Ask daemon for the session name bound to `cwd`.

    Falls back to `claude-<basename(cwd)>` if no binding exists or daemon
    is unreachable.
    """
    fallback = f"claude-{cwd.name}"
    cwd_resolved = str(cwd.resolve())

    async def _ask():
        try:
            async for event in run_op(data_dir=data_dir, op="list", args={}):
                if isinstance(event, ResultEvent) and event.ok and event.data:
                    for b in event.data.get("bindings", []):
                        if str(Path(b.get("project_dir", "")).resolve()) == cwd_resolved:
                            return b.get("tmux_session") or fallback
                if isinstance(event, DoneEvent):
                    break
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            pass
        return fallback

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(_ask())


@main.command(
    help="Start zellij + claude shell for current project (new console window). "
         "Extra args after options are forwarded to claude.",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--cwd", default=None, type=click.Path(path_type=Path))
@click.argument("claude_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def shell(ctx, cwd, claude_args):
    """Spawn `zellij --session <name> -- claude [args...]` in a NEW console.

    Unlike tmux's detached `new-session -d`, zellij combines create + attach in
    one command. We open a new console window for it so the user sees Claude's
    TUI directly. To leave the session alive while closing the window, use
    zellij's `Ctrl+P, D` (detach).
    """
    target = (cwd or Path(os.getcwd())).resolve()
    session_name = _resolve_session_name(ctx.obj["data_dir"], target)

    claude_cmd = ["claude", *claude_args]
    # zellij needs `--` to separate its own args from the inner command
    zellij_argv = ["zellij", "--session", session_name, "--", *claude_cmd]

    if sys.platform == "win32":
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(
            zellij_argv,
            cwd=str(target),
            creationflags=CREATE_NEW_CONSOLE,
            close_fds=True,
        )
        click.echo(f"Started zellij session {session_name!r} in a new console window.")
        click.echo("To detach without killing the session: Ctrl+P, then D.")
    else:
        # Dev fallback for testing on macOS / Linux without WSL.
        os.execvp("zellij", zellij_argv)
