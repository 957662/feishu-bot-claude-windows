"""Tests for JsonlWatcher — async file-change signal generator."""

import asyncio
from pathlib import Path

import pytest

from feishu_bot_claude_win.daemon.jsonl_watcher import JsonlWatcher


@pytest.mark.asyncio
async def test_watcher_yields_on_file_grow(tmp_path):
    """Appending to a watched file should yield a change signal."""
    path = tmp_path / "session.jsonl"
    path.write_text("initial\n")

    watcher = JsonlWatcher(path)
    received: list[None] = []

    async def listen():
        async for _ in watcher.changes(stop_after=1):
            received.append(None)

    listen_task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)  # let watcher initialize
    with path.open("a") as f:
        f.write("new line\n")
    await asyncio.wait_for(listen_task, timeout=3.0)
    assert len(received) >= 1


@pytest.mark.asyncio
async def test_watcher_handles_initial_missing_file(tmp_path):
    """If the file doesn't exist yet, watcher should wait for it to appear."""
    path = tmp_path / "later.jsonl"
    watcher = JsonlWatcher(path)
    received: list[None] = []

    async def listen():
        async for _ in watcher.changes(stop_after=1):
            received.append(None)

    listen_task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    path.write_text("hello\n")
    await asyncio.wait_for(listen_task, timeout=3.0)
    assert len(received) >= 1


@pytest.mark.asyncio
async def test_watcher_cancellable(tmp_path):
    """Cancelling the listen task should not leak the watchfiles task."""
    path = tmp_path / "session.jsonl"
    path.write_text("")

    watcher = JsonlWatcher(path)
    received: list[None] = []

    async def listen():
        async for _ in watcher.changes(stop_after=0):
            received.append(None)

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
