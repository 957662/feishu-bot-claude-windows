"""Tests for auth.bot_new — parses real lark-cli output."""

import asyncio

import pytest

from feishu_bot_claude_win.daemon.auth import BotCreationResult, bot_new


async def _async_lines(lines):
    for line in lines:
        await asyncio.sleep(0)
        yield line + "\n"


@pytest.mark.asyncio
async def test_bot_new_parses_real_larkcli_output():
    """Real lark-cli output: ASCII QR block followed by URL line."""
    fake_output = [
        "█████████████████████████████████████████████",
        "█████████████████████████████████████████████",
        "████ ▄▄▄▄▄ █▄ ▄▀ ▀▀█ ▀ ▀▀█▄▄▄▀▀▄██ ▄▄▄▄▄ ████",
        "████ █   █ █▀▀█  █ ▀▄▄ ▄▀▄█▄▄▀ █▀█ █   █ ████",
        "▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
        "",
        "打开以下链接配置应用:",
        "",
        "  https://open.feishu.cn/page/cli?user_code=ABCD-EFGH&lpv=1.0.41",
        "",
        "等待配置应用...",
    ]
    progress_events = []

    async def on_progress(event):
        progress_events.append(event)

    result = await bot_new(runner=_async_lines(fake_output), on_event=on_progress)

    assert isinstance(result, BotCreationResult)
    qr_events = [e for e in progress_events if e["type"] == "qrcode"]
    assert len(qr_events) == 1
    assert "█" in qr_events[0]["ascii"]
    assert qr_events[0]["url"].startswith("https://open.feishu.cn/page/cli")


@pytest.mark.asyncio
async def test_bot_new_no_qr_raises():
    """If no QR is seen, raise."""
    with pytest.raises(RuntimeError, match="did not see QR"):
        await bot_new(runner=_async_lines(["some unrelated text"]), on_event=lambda e: None)
