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

# Mermaid fenced code block detector. Matches ``` or ~~~ fences with a
# `mermaid` language tag (case-insensitive). The body is captured lazily so
# multiple blocks in one message are matched independently.
_MERMAID_FENCE_RE = re.compile(
    r"(?P<fence>```|~~~)[ \t]*mermaid[ \t]*\n(?P<code>.*?)\n[ \t]*(?P=fence)",
    re.IGNORECASE | re.DOTALL,
)
# Marker we substitute for the mermaid source in the rendered markdown text.
# The actual diagram image is appended as a separate img element immediately
# after the markdown element holding this placeholder.
MERMAID_PLACEHOLDER = "[mermaid 图,见下方]"


def extract_mermaid_blocks(text: str) -> list[str]:
    """Return the source code of every ```mermaid``` block in `text`, in order.

    Used by the outbound pipeline to know what to render + upload BEFORE
    calling render_turn_to_card. Blocks are de-duplicated by content so that
    a turn repeating the same diagram doesn't trigger two uploads.
    """
    if not text or "mermaid" not in text.lower():
        return []
    seen: dict[str, None] = {}
    for m in _MERMAID_FENCE_RE.finditer(text):
        code = m.group("code").strip()
        if code:
            seen.setdefault(code, None)
    return list(seen.keys())


def collect_mermaid_blocks(turn: Turn) -> list[str]:
    """All mermaid source blocks referenced anywhere in this turn's text parts.

    Tool_result content is included too — sometimes the model echoes a
    diagram via a tool output (e.g. `cat diagram.mmd`).
    """
    seen: dict[str, None] = {}
    for event in turn.assistant_events:
        for part in event.content:
            ptype = part.get("type")
            if ptype == "text" and isinstance(part.get("text"), str):
                for code in extract_mermaid_blocks(part["text"]):
                    seen.setdefault(code, None)
            elif ptype == "tool_result":
                content = part.get("content", "")
                if isinstance(content, list):
                    content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                if isinstance(content, str):
                    for code in extract_mermaid_blocks(content):
                        seen.setdefault(code, None)
    return list(seen.keys())


def _split_text_by_mermaid(text: str) -> list[tuple[str, str]]:
    """Split text into a sequence of segments around mermaid fences.

    Yields a list of (kind, value) where kind ∈ {"text", "mermaid"}:
      - "text"    → markdown chunk (may be empty if mermaid blocks are adjacent)
      - "mermaid" → the source code of one fenced block, stripped

    The original document is reconstructible by concatenating the text values
    with the fenced blocks re-inserted at the mermaid slots.
    """
    if not text or "mermaid" not in text.lower():
        return [("text", text)]
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _MERMAID_FENCE_RE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        code = m.group("code").strip()
        out.append(("mermaid", code))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out

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

# Non-image, non-binary user-readable file extensions that we'll auto-upload
# to Feishu so the user can grab them from the bot chat. PNG/JPG/etc go
# through the IMAGE path. We deliberately skip very large binaries (.zip,
# .tar.gz, etc.) — they'd be too easy to spam.
_FILE_PATH_RE = re.compile(
    r"(?<![\w./])"  # path boundary on the left
    r"(?P<path>(?:/[\w./\-]+|[A-Za-z]:\\[\w.\\\- ]+)\."
    r"(?:pdf|txt|md|markdown|csv|tsv|json|yaml|yml|toml|xml|"
    r"py|js|ts|tsx|jsx|go|rs|java|kt|swift|c|h|cpp|hpp|cs|rb|php|"
    r"sh|bash|zsh|fish|sql|html|css|scss|log|conf|ini|cfg|"
    r"docx?|xlsx?|pptx?))"
    r"(?![\w])",
    re.IGNORECASE,
)


def collect_file_paths(turn: Turn) -> list[str]:
    """Like collect_image_paths but for non-image text files.

    Sources mirror image collection: text parts, tool_result content. Returned
    paths are absolute (matched by regex) and deduplicated in encounter order.
    """
    seen: dict[str, None] = {}
    for event in turn.assistant_events:
        for part in event.content:
            ptype = part.get("type")
            if ptype == "text" and isinstance(part.get("text"), str):
                for m in _FILE_PATH_RE.finditer(part["text"]):
                    seen.setdefault(m.group("path"), None)
            elif ptype == "tool_result":
                content = part.get("content", "")
                if isinstance(content, list):
                    content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                if isinstance(content, str):
                    for m in _FILE_PATH_RE.finditer(content):
                        seen.setdefault(m.group("path"), None)
    return list(seen.keys())


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
    mermaid_keys: dict[str, str] | None = None,
    in_progress: bool = False,
) -> dict:
    """Render a Turn to a Feishu interactive card JSON.

    `image_keys` maps absolute local path → uploaded image_key. When provided,
    each known path gets an `img` element appended after the text/tool block
    that referenced it. Paths not in the map (upload failed or skipped) are
    left as text — no broken-image markers.

    `mermaid_keys` maps mermaid source code (whitespace-stripped) → uploaded
    image_key. For each ```mermaid``` fence we find in the rendered text, we
    replace the source with a "[mermaid 图,见下方]" placeholder and append an
    img element right after. Blocks with no entry in the dict (mmdc + ink
    both failed) are left untouched so the user still sees the raw source.

    `in_progress=True` (the current turn is still being written) appends a
    "思考中…" pacer at the bottom. Subsequent updates rewrite the card with
    fresh content, giving the user a live-feedback feeling — flush after
    flush, as the watcher polls the jsonl every 2s.
    """
    image_keys = image_keys or {}
    mermaid_keys = mermaid_keys or {}
    elements: list[dict] = []
    for event in turn.assistant_events:
        for part in event.content:
            if part.get("type") == "text" and part.get("text"):
                _append_text_with_mermaid(elements, part["text"], image_keys, mermaid_keys)
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

    if in_progress:
        # Typewriter cursor — attach a blinking ▌ to the LAST markdown element
        # so the cursor appears at the end of the generated text. Falls back
        # to a standalone note if there's no markdown to anchor to (e.g. turn
        # is purely tool calls so far).
        import time
        # 0.5s blink: cursor visible on even half-seconds, dim on odd
        tick = int(time.time() * 2) % 4
        cursors = ["▌", "▍", "▎", "▏"]
        cursor = cursors[tick]
        anchored = False
        for el in reversed(elements):
            if el.get("tag") == "markdown" and isinstance(el.get("content"), str):
                # Append cursor inline (avoid second \n that breaks the visual
                # flow). Guard against the cursor lingering from a prior render.
                base = el["content"].rstrip("▌▍▎▏ \n")
                el["content"] = base + " " + cursor
                anchored = True
                break
        # Footer: spinner + elapsed + token count (signals progress even when
        # the cursor is on a long tool block that won't repaint).
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][int(time.time() * 8) % 10]
        # Elapsed: take first event's timestamp if present
        started = None
        for e in turn.assistant_events:
            ts = e.raw.get("timestamp")
            if isinstance(ts, str) and ts:
                started = ts
                break
        elapsed = ""
        if started:
            try:
                import datetime
                t0 = datetime.datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp()
                secs = int(time.time() - t0)
                if secs >= 0 and secs < 7200:  # sanity cap
                    elapsed = f"  ·  ⏱ {secs}s"
            except Exception:
                pass
        tk = f"  ·  {total_in + total_out:,} tokens" if (total_in or total_out) else ""
        if not anchored:
            elements.append(build_markdown(cursor))
        elements.append(build_note(f"{spinner} 生成中{elapsed}{tk}"))

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


def _append_text_with_mermaid(
    elements: list[dict],
    text: str,
    image_keys: dict[str, str],
    mermaid_keys: dict[str, str],
) -> None:
    """Append a text part as one or more markdown + img elements.

    Splits on ```mermaid``` fences:
      - text segments are emitted as build_markdown (truncated to fit card limit)
      - mermaid segments WITH an entry in mermaid_keys → placeholder note +
        build_image (img element)
      - mermaid segments WITHOUT a key (render failed) → keep original fence
        text so the user can still copy the source
    Inline image paths inside text segments are handled via _append_inline_images.
    """
    segments = _split_text_by_mermaid(text)
    for kind, value in segments:
        if kind == "text":
            if not value:
                continue
            chunk = _truncate(value, MARKDOWN_CHAR_LIMIT)
            elements.append(build_markdown(chunk))
            _append_inline_images(elements, value, image_keys)
        else:  # "mermaid"
            key = mermaid_keys.get(value)
            if key:
                # Marker so the surrounding text reads naturally even when
                # the image is far enough down the card to need scrolling.
                elements.append(build_markdown(MERMAID_PLACEHOLDER))
                elements.append(build_image(key, alt="mermaid diagram"))
            else:
                # Render failed — preserve the fenced source verbatim so the
                # user can copy it elsewhere instead of seeing a broken block.
                fallback = f"```mermaid\n{value}\n```"
                elements.append(build_markdown(_truncate(fallback, MARKDOWN_CHAR_LIMIT)))
