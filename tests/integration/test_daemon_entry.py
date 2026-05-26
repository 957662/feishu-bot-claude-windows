"""End-to-end: spawn daemon subprocess on TCP loopback, run CLI against it.

The daemon writes its bound port to <data_dir>/control.port. The CLI reads
that file to discover the daemon. Both pieces are driven by the
FEISHU_BOT_CLAUDE_DATA_DIR env var.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _wait_for_port_file(port_file: Path, timeout: float = 5.0) -> None:
    """Poll until the daemon publishes its control.port file."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_file.exists() and port_file.read_text().strip():
            return
        time.sleep(0.05)
    raise AssertionError(f"daemon did not write {port_file} within {timeout}s")


def _spawn_daemon(data_dir: Path, bindings_path: Path) -> tuple[subprocess.Popen, dict]:
    env = os.environ.copy()
    env["FEISHU_BOT_CLAUDE_DATA_DIR"] = str(data_dir)
    env["FEISHU_BOT_CLAUDE_BINDINGS"] = str(bindings_path)
    proc = subprocess.Popen(
        [sys.executable, "-m", "feishu_bot_claude_win", "daemon"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc, env


@pytest.mark.asyncio
async def test_daemon_subprocess_responds_to_cli(tmp_path):
    bindings_path = tmp_path / "bindings.toml"
    port_file = tmp_path / "control.port"
    daemon, env = _spawn_daemon(tmp_path, bindings_path)
    try:
        _wait_for_port_file(port_file)
        result = subprocess.run(
            [sys.executable, "-m", "feishu_bot_claude_win", "--data-dir", str(tmp_path), "ping"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
        assert "pong" in result.stdout.lower() or "OK" in result.stdout
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon.kill()


@pytest.mark.asyncio
async def test_daemon_list_empty(tmp_path):
    """A fresh daemon with no bindings returns an empty list."""
    bindings_path = tmp_path / "bindings.toml"
    port_file = tmp_path / "control.port"
    daemon, env = _spawn_daemon(tmp_path, bindings_path)
    try:
        _wait_for_port_file(port_file)
        result = subprocess.run(
            [sys.executable, "-m", "feishu_bot_claude_win", "--data-dir", str(tmp_path), "list"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "bindings" in result.stdout
        assert "[]" in result.stdout or '"bindings": []' in result.stdout
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon.kill()
