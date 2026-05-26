"""Group raw Claude jsonl events into Turns for rendering."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class JsonlEvent:
    """One line from Claude's session jsonl."""

    role: str
    uuid: str
    content: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> JsonlEvent:
        # Claude jsonl stores message events with `message.content` (Anthropic SDK
        # shape) OR with `content` at the top level (older / synthetic events).
        # content itself can be a plain string OR a list of {type,text|...} parts.
        # Normalize to list-of-dicts so downstream code can iterate safely.
        msg_obj = d.get("message")
        if isinstance(msg_obj, dict):
            raw_content = msg_obj.get("content", d.get("content", []))
            role = msg_obj.get("role", d.get("role", ""))
        else:
            raw_content = d.get("content", [])
            role = d.get("role", "")
        if isinstance(raw_content, str):
            normalized = [{"type": "text", "text": raw_content}]
        elif isinstance(raw_content, list):
            normalized = []
            for part in raw_content:
                if isinstance(part, dict):
                    normalized.append(part)
                elif isinstance(part, str):
                    normalized.append({"type": "text", "text": part})
                # else skip unknown shapes
        else:
            normalized = []
        return cls(
            role=role,
            uuid=d.get("uuid", ""),
            content=normalized,
            raw=d,
        )

    @classmethod
    def load_file(cls, path: Path) -> Iterator[JsonlEvent]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield cls.from_dict(json.loads(line))

    def text(self) -> str:
        return "".join(c.get("text", "") for c in self.content if c.get("type") == "text")

    def has_only_tool_results(self) -> bool:
        if not self.content:
            return False
        return all(c.get("type") == "tool_result" for c in self.content)


@dataclass
class Turn:
    """One conversation turn: a user message and the assistant response(s)."""

    user_event: JsonlEvent | None
    assistant_events: list[JsonlEvent] = field(default_factory=list)


def group_into_turns(events: Iterable[JsonlEvent]) -> list[Turn]:
    """Group an iterable of JsonlEvents into Turn list.

    A new Turn starts on a `user` event that contains at least one text part
    (i.e., a real user message, not just tool_result delivery).
    """
    turns: list[Turn] = []
    current: Turn | None = None

    for event in events:
        if event.role == "user" and not event.has_only_tool_results():
            current = Turn(user_event=event)
            turns.append(current)
        else:
            if current is None:
                current = Turn(user_event=None)
                turns.append(current)
            current.assistant_events.append(event)

    return turns


from feishu_bot_claude_win.rendering.card import build_card, build_header, build_image, build_markdown, build_note
from feishu_bot_claude_win.rendering.tools import render_tool_block

# Feishu card limits (see tools.py): cap individual markdown elements and
# total element count to stay under the per-message budget (~30KB / ~50 elements).
MARKDOWN_CHAR_LIMIT = 4000
MAX_ELEMENTS_PER_CARD = 40

# Regex to spot absolute image paths embedded in plain text. We support
# common formats Claude/Codex emit: bare paths, markdown `![alt](path)`,
# and the "Image: <path>" prefix our own inbound pipeline uses.
_IMAGE_PATH_RE = re.compile(
    r"(?:!?\[[^\]]*\]\()?(?P<path>(?:/[\w./\-]+|[A-Za-z]:\\[\w.\\\- ]+)\.(?:png|jpe?g|gif|webp|bmp))\)?",
    re.IGNORECASE,
)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…(截断 {len(text) - limit} 字符)…"


def collect_image_paths(turn: Turn) -> list[str]:
    """Scan a Turn for local image file paths that should be uploaded + shown.

    Returns absolute paths in encounter order, de-duplicated. Sources:
      - explicit `image` content parts (e.g. Claude's tool_result image blocks)
      - text containing absolute paths to .png/.jpg/.jpeg/.gif/.webp/.bmp
      - tool_result text containing the same
    """
    seen: dict[str, None] = {}  # ordered set
    for event in turn.assistant_events:
        for part in event.content:
            ptype = part.get("type")
            if ptype == "image":
                src = part.get("source") or {}
                if src.get("type") == "path" and src.get("path"):
                    p = src["path"]
                    seen.setdefault(p, None)
                # base64 images are skipped — handling those requires a
                # tempfile write; out of scope for v1.
            elif ptype == "text" and isinstance(part.get("text"), str):
                for m in _IMAGE_PATH_RE.finditer(part["text"]):
                    seen.setdefault(m.group("path"), None)
            elif ptype == "tool_result":
                content = part.get("content", "")
                if isinstance(content, list):
                    content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                if isinstance(content, str):
                    for m in _IMAGE_PATH_RE.finditer(content):
                        seen.setdefault(m.group("path"), None)
    return list(seen.keys())


def render_turn_to_card(
    turn: Turn,
    project_name: str = "project",
    render_style: str = "rich",
    image_keys: dict[str, str] | None = None,
) -> dict:
    """Render a Turn to a Feishu interactive card JSON.

    `image_keys` maps absolute local path → uploaded image_key. When provided,
    each known path gets an `img` element appended after the text/tool block
    that referenced it. Paths not in the map (upload failed or skipped) are
    left as text — no broken-image markers.
    """
    image_keys = image_keys or {}
    elements: list[dict] = []
    for event in turn.assistant_events:
        for part in event.content:
            if part.get("type") == "text" and part.get("text"):
                text = _truncate(part["text"], MARKDOWN_CHAR_LIMIT)
                elements.append(build_markdown(text))
                _append_inline_images(elements, part["text"], image_keys)
            elif part.get("type") == "image":
                src = part.get("source") or {}
                if src.get("type") == "path" and src.get("path") in image_keys:
                    elements.append(build_image(image_keys[src["path"]], alt=src.get("alt", "")))
            elif part.get("type") == "tool_use":
                tool_use = part
                tool_result = None
                for later in turn.assistant_events:
                    for p in later.content:
                        if p.get("type") == "tool_result" and p.get("tool_use_id") == tool_use.get("id"):
                            tool_result = p
                            break
                block = render_tool_block(tool_use, tool_result, render_style=render_style)
                if block is not None:
                    elements.append(block)
                if tool_result is not None:
                    content = tool_result.get("content", "")
                    if isinstance(content, list):
                        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                    if isinstance(content, str):
                        _append_inline_images(elements, content, image_keys)

    total_in = sum(e.raw.get("usage", {}).get("input_tokens", 0) for e in turn.assistant_events)
    total_out = sum(e.raw.get("usage", {}).get("output_tokens", 0) for e in turn.assistant_events)

    if len(elements) > MAX_ELEMENTS_PER_CARD - 2:
        dropped = len(elements) - (MAX_ELEMENTS_PER_CARD - 2)
        elements = elements[:MAX_ELEMENTS_PER_CARD - 2]
        elements.append(build_note(f"…省略 {dropped} 个工具调用/段落…"))

    if total_in or total_out:
        elements.append(build_note(f"{total_in}+{total_out} tokens"))

    header = build_header(title=f"🤖 Claude · {project_name}")
    return build_card(header=header, elements=elements)


def _append_inline_images(
    elements: list[dict],
    text: str,
    image_keys: dict[str, str],
) -> None:
    """For each known image path mentioned in `text`, append an img element."""
    if not image_keys:
        return
    seen: set[str] = set()
    for m in _IMAGE_PATH_RE.finditer(text):
        path = m.group("path")
        if path in seen:
            continue
        seen.add(path)
        if path in image_keys:
            elements.append(build_image(image_keys[path], alt=os.path.basename(path)))
