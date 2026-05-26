"""Per-tool block rendering — jsonl tool_use + tool_result → Feishu card block."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from feishu_bot_claude_win.rendering.card import build_collapsible


RenderStyle = Literal["minimal", "full", "rich"]


TOOL_ICONS: dict[str, str] = {
    "Read": "📖",
    "Write": "📝",
    "Edit": "✏️",
    "MultiEdit": "✏️",
    "Bash": "💻",
    "Grep": "🔍",
    "Glob": "📁",
    "WebFetch": "🌐",
    "WebSearch": "🌐",
    "Task": "🤖",
    "TodoWrite": "✅",
    "NotebookEdit": "📓",
}


def _icon(tool_name: str) -> str:
    return TOOL_ICONS.get(tool_name, "🔧")


def _format_title(tool_use: dict, tool_result: dict | None) -> str:
    name = tool_use.get("name", "?")
    icon = _icon(name)
    target = _tool_target(tool_use)
    status = _status_marker(tool_result)
    detail = _tool_detail(tool_use, tool_result)
    parts = [f"{icon} {name}"]
    if target:
        parts.append(target)
    parts.append(status)
    if detail:
        parts.append(detail)
    return "  ".join(parts)


def _tool_target(tool_use: dict) -> str:
    name = tool_use.get("name", "")
    args = tool_use.get("input", {}) or {}
    if name in {"Read", "Write", "Edit", "MultiEdit"}:
        path = args.get("file_path", "")
        return Path(path).name if path else ""
    if name == "Bash":
        cmd = args.get("command", "")
        return (cmd[:40] + "…") if len(cmd) > 40 else cmd
    if name == "Grep":
        return args.get("pattern", "")
    if name == "Glob":
        return args.get("pattern", "")
    if name == "WebFetch":
        return args.get("url", "")[:40]
    if name == "Task":
        return args.get("subagent_type", "")
    return ""


def _status_marker(tool_result: dict | None) -> str:
    if tool_result is None:
        return "⏳"
    if tool_result.get("is_error"):
        return "✗"
    return "✓"


def _tool_detail(tool_use: dict, tool_result: dict | None) -> str:
    if tool_result is None:
        return ""
    content = tool_result.get("content", "")
    if isinstance(content, str):
        lines = content.count("\n") + (1 if content else 0)
        if lines > 1:
            return f"{lines} lines"
    return ""


# Feishu interactive card limits (per testing 2026-05):
#   - Total message body ≤ 30KB (code 230025 if exceeded)
#   - Single element body cannot exceed ~8KB (code 11310 "element exceeds the limit")
#   - Total elements per card cannot exceed ~50 (code 11310 "element/table number over limit")
# We cap each tool block to keep individual elements small AND keep total chars bounded.
TOOL_BLOCK_CHAR_LIMIT = 4000  # safe under 8KB even with multibyte chars


def render_tool_block(
    tool_use: dict,
    tool_result: dict | None,
    render_style: RenderStyle,
    preview_lines: int = 60,
) -> dict | None:
    """Return a collapsible card block for one tool call, or None if minimal."""
    if render_style == "minimal":
        return None

    title = _format_title(tool_use, tool_result)
    body = _build_body(tool_use, tool_result, render_style, preview_lines)
    return build_collapsible(summary=title, body_markdown=body, expanded=False)


def _truncate_to_chars(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit]
    return head + f"\n…(截断 {len(text) - limit} 字符)…"


def _build_body(tool_use: dict, tool_result: dict | None, render_style: RenderStyle, preview_lines: int) -> str:
    parts = []
    if render_style == "full":
        args = tool_use.get("input", {})
        if args:
            import json
            parts.append("**Input:**\n```json\n" + json.dumps(args, ensure_ascii=False, indent=2) + "\n```")
    if tool_result is None:
        parts.append("_pending..._")
        return "\n\n".join(parts)
    content = tool_result.get("content", "")
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    if not isinstance(content, str):
        content = str(content)
    lines = content.splitlines()
    if len(lines) > preview_lines:
        head = "\n".join(lines[:preview_lines])
        parts.append(f"```\n{head}\n```\n_...省略 {len(lines) - preview_lines} 行..._")
    elif content:
        parts.append(f"```\n{content}\n```")
    body = "\n\n".join(parts) if parts else "_(empty)_"
    return _truncate_to_chars(body, TOOL_BLOCK_CHAR_LIMIT)


def summarize_tool_result(tool_result: dict | None) -> str:
    if tool_result is None:
        return "(pending)"
    content = tool_result.get("content", "")
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    if not isinstance(content, str):
        content = str(content)
    lines = content.count("\n") + (1 if content else 0)
    if lines > 1:
        return f"{lines} lines"
    return content[:80]
