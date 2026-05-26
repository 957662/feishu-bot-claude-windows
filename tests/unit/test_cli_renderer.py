"""Tests for CLI event renderer (pure, no I/O)."""

from feishu_bot_claude_win.cli import render_event
from feishu_bot_claude_win.proto import (
    DoneEvent,
    LogEvent,
    ProgressEvent,
    QRCodeEvent,
    ResultEvent,
)


def test_render_log_returns_plain_message():
    out = render_event(LogEvent(level="info", msg="hello"))
    assert out == "hello"


def test_render_log_error_includes_marker():
    out = render_event(LogEvent(level="error", msg="bad thing"))
    assert "error" in out.lower() or "ERROR" in out
    assert "bad thing" in out


def test_render_qrcode_includes_ascii_and_url():
    out = render_event(QRCodeEvent(ascii="█▀█\n▀ █", url="https://x/qr"))
    assert "█▀█" in out
    assert "https://x/qr" in out


def test_render_progress_percent():
    out = render_event(ProgressEvent(value=0.42, msg="working"))
    assert "42%" in out
    assert "working" in out


def test_render_result_ok_with_data():
    out = render_event(ResultEvent(ok=True, data={"x": 1}, error=None))
    assert "ok" in out.lower() or "success" in out.lower() or "✓" in out or "OK" in out


def test_render_result_failure_includes_error():
    out = render_event(ResultEvent(ok=False, data=None, error="boom"))
    assert "boom" in out


def test_render_done_returns_empty_string():
    out = render_event(DoneEvent())
    assert out == ""


from click.testing import CliRunner


def test_main_help_lists_subcommands():
    from feishu_bot_claude_win.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ["ping", "list", "bind", "start", "stop", "status", "unbind", "config"]:
        assert cmd in result.output, f"missing subcommand: {cmd}"
