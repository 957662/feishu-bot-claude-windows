"""Module entry: `python -m feishu_bot_claude_win {daemon|<cli-op>}`.

Windows-native port of feishu-bot-claude. Differences from the macOS edition:
- session multiplexer: zellij (instead of tmux)
- IPC: TCP localhost (instead of Unix domain socket)
- credentials: Windows Credential Manager (instead of macOS Keychain)
- service install: NSSM / Task Scheduler (instead of launchd)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from feishu_bot_claude_win.daemon import serve

_DEFAULT_DATA_DIR = Path.home() / ".feishu-bot-claude-win"


async def _run_daemon() -> None:
    # Default to TCP loopback. Port 0 = ephemeral; written to data_dir/control.port
    # so the CLI can discover it. Override via FEISHU_BOT_CLAUDE_HOST/PORT.
    host = os.environ.get("FEISHU_BOT_CLAUDE_HOST", "127.0.0.1")
    port = int(os.environ.get("FEISHU_BOT_CLAUDE_PORT", "0"))
    bindings_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_BINDINGS",
        _DEFAULT_DATA_DIR / "bindings.toml",
    ))
    data_dir = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_DATA_DIR",
        _DEFAULT_DATA_DIR,
    ))
    data_dir.mkdir(parents=True, exist_ok=True)

    from feishu_bot_claude_win.config.binding import BindingStore
    from feishu_bot_claude_win.daemon.orchestrator import Orchestrator
    from feishu_bot_claude_win.daemon.zellij import RealZellij
    from feishu_bot_claude_win.daemon.feishu import RealLarkCli
    from feishu_bot_claude_win.config.keychain import WindowsCredentialStore

    store = BindingStore(bindings_path)
    keychain = WindowsCredentialStore()

    def _lark_for_binding(cfg) -> RealLarkCli:
        """RealLarkCli with WS event source for menu_v6 + card.action.trigger."""
        secret = keychain.get(cfg.secret_ref) if cfg.secret_ref else None
        return RealLarkCli(
            ws_app_id=cfg.feishu_app_id,
            ws_app_secret=secret,
            ws_domain=cfg.domain or "https://open.feishu.cn",
        )

    orchestrator = Orchestrator(
        store=store,
        tmux_factory=lambda name: RealZellij(),
        lark_factory=_lark_for_binding,
        data_dir=data_dir,
    )

    real_lark = RealLarkCli()

    server = await serve(
        host=host,
        port=port,
        bindings_path=bindings_path,
        orchestrator=orchestrator,
        keychain=keychain,
        auth_runner_factory=lambda name: real_lark.auth_bot_new_stream(name),
        menu_pusher=real_lark,
        data_dir=data_dir,
    )
    try:
        stale = await orchestrator.restore_from_disk()
        if stale:
            logging.getLogger(__name__).warning("Stale bindings (zellij session missing): %s", stale)
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        await orchestrator.stop_all()


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "daemon":
        # Windows asyncio: ProactorEventLoop is the default on Py3.8+; required
        # for subprocess pipe semantics we rely on (lark-cli event consume).
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
        try:
            asyncio.run(_run_daemon())
        except KeyboardInterrupt:
            pass
        return 0
    from feishu_bot_claude_win.cli import main as click_main
    click_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
