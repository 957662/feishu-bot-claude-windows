"""OAuth bot-new flow wrapper: parses lark-cli output, emits qrcode/progress events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotCreationResult:
    app_id: str
    app_secret: str
    tenant_key: str | None = None


async def bot_new(
    runner,
    on_event,
):
    """Drive lark-cli's new-app flow, parsing QR + URL from real lark-cli output.

    The QR is a block of lines starting with ASCII block characters like █, ▀, ▄.
    The URL line starts with `https://open.feishu.cn/page/cli`.
    Process exit code 0 = user completed scan + profile saved.
    """
    qr_lines: list[str] = []
    qr_url: str = ""
    qr_emitted = False

    async def _emit(event):
        result = on_event(event)
        if asyncio.iscoroutine(result):
            await result

    def _is_qr_row(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        # QR rows are dense block characters
        block_chars = set("█▀▄▌▐ ")
        non_block = sum(1 for c in stripped if c not in block_chars)
        return non_block == 0 and len(stripped) >= 20

    async for line in runner:
        line = line.rstrip("\n")
        if _is_qr_row(line):
            qr_lines.append(line)
            continue
        # Non-QR line. If we've been accumulating QR rows, the QR block has ended.
        if "open.feishu.cn/page/cli" in line:
            qr_url = line.strip().split()[-1] if line.strip().split() else line.strip()
            if qr_lines and not qr_emitted:
                await _emit({"type": "qrcode", "ascii": "\n".join(qr_lines), "url": qr_url})
                qr_emitted = True
            continue
        if line.strip():
            await _emit({"type": "log", "level": "info", "msg": line})

    if not qr_emitted:
        raise RuntimeError("auth flow failed: did not see QR + URL in lark-cli output")

    # Process exited successfully (we only get here if the runner exhausted normally).
    # Return a result with placeholder app_id — handler will call config show separately.
    return BotCreationResult(app_id="", app_secret="", tenant_key=None)
