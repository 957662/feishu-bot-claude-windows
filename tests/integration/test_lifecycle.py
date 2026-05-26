"""End-to-end lifecycle test with fake adapters."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude_win.config.binding import BindingConfig, BindingStore
from feishu_bot_claude_win.daemon.feishu import FakeLarkCli
from feishu_bot_claude_win.daemon.orchestrator import Orchestrator
from feishu_bot_claude_win.daemon.zellij import FakeTmux


@pytest.mark.asyncio
async def test_full_lifecycle_with_fakes(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text("")

    cfg = BindingConfig(
        name="myproject-bot",
        project_dir=str(project_dir),
        tmux_session="claude-myproject-bot",
        feishu_app_id="cli_x",
        secret_ref="x",
        created_at=datetime.now(timezone.utc),
    )
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(cfg)

    tmux = FakeTmux()
    tmux.set_session("claude-myproject-bot", exists=True)
    lark = FakeLarkCli()

    orchestrator = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: lark,
        data_dir=tmp_path,
    )
    # Outbound only sends cards once a chat_id is known (set by the bootstrap
    # message in real flow). Inject one here so the test exercises sends.
    orchestrator.set_chat_id("myproject-bot", "oc_test_chat")

    # Start
    await orchestrator.start_binding(cwd=str(project_dir), jsonl_path=jsonl)
    assert "myproject-bot" in orchestrator.list_running()

    # Simulate Claude writing a turn to the jsonl
    events = [
        {"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "hello"}]},
    ]
    with jsonl.open("a") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Give the outbound loop a moment to react to the file change
    await asyncio.sleep(0.8)

    # The mock LarkCli should have at least one send call
    assert any(c["kind"] == "card" for c in lark.send_calls), \
        f"expected card send; got: {lark.send_calls}"

    # Stop
    await orchestrator.stop_binding(cwd=str(project_dir))
    assert "myproject-bot" not in orchestrator.list_running()
