"""Tests for per-tool block rendering."""

from feishu_bot_claude_win.rendering.tools import (
    TOOL_ICONS,
    render_tool_block,
    summarize_tool_result,
)


def test_tool_icon_for_read():
    assert TOOL_ICONS["Read"] == "📖"


def test_tool_icon_for_unknown_falls_back():
    assert TOOL_ICONS.get("UnknownTool", "🔧") == "🔧"


def test_render_read_block_rich():
    tool_use = {"name": "Read", "input": {"file_path": "/abs/auth.go"}}
    tool_result = {"content": "package auth\nfunc x() {}\n"}
    block = render_tool_block(tool_use, tool_result, render_style="rich")
    assert block["tag"] == "collapsible_panel"
    title = block["header"]["title"]["content"]
    assert "📖" in title
    assert "auth.go" in title
    assert "✓" in title
    body = block["elements"][0]["content"]
    assert "package auth" in body


def test_render_bash_long_output_truncates():
    tool_use = {"name": "Bash", "input": {"command": "ls -la"}}
    long = "\n".join([f"line {i}" for i in range(200)])
    tool_result = {"content": long}
    block = render_tool_block(tool_use, tool_result, render_style="rich", preview_lines=20)
    body = block["elements"][0]["content"]
    assert "line 0" in body
    assert "line 19" in body
    assert "line 199" not in body
    assert "省略" in body or "..." in body or "omitted" in body.lower()


def test_render_edit_block_shows_diff_summary():
    tool_use = {"name": "Edit", "input": {"file_path": "/x", "old_string": "a", "new_string": "b"}}
    tool_result = {"content": "ok"}
    block = render_tool_block(tool_use, tool_result, render_style="rich")
    title = block["header"]["title"]["content"]
    assert "✏️" in title


def test_render_failed_tool_uses_failure_marker():
    tool_use = {"name": "Bash", "input": {"command": "false"}}
    tool_result = {"content": "exit 1", "is_error": True}
    block = render_tool_block(tool_use, tool_result, render_style="rich")
    title = block["header"]["title"]["content"]
    assert "✗" in title or "❌" in title


def test_render_pending_tool_no_result_yet():
    """In-flight tool call (no result yet) shows hourglass."""
    tool_use = {"name": "Read", "input": {"file_path": "/x"}}
    block = render_tool_block(tool_use, tool_result=None, render_style="rich")
    title = block["header"]["title"]["content"]
    assert "⏳" in title


def test_summarize_tool_result_for_short():
    summary = summarize_tool_result({"content": "ok"})
    assert summary == "ok"


def test_summarize_tool_result_for_long():
    summary = summarize_tool_result({"content": "a\n" * 100})
    assert "lines" in summary


def test_render_minimal_style_omits_tool_blocks():
    """In minimal mode, render_tool_block returns None."""
    tool_use = {"name": "Read", "input": {"file_path": "/x"}}
    tool_result = {"content": "data"}
    assert render_tool_block(tool_use, tool_result, render_style="minimal") is None
