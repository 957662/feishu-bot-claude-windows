"""Tests for atomic card JSON builders."""

from feishu_bot_claude_win.rendering.card import (
    build_card,
    build_header,
    build_markdown,
    build_divider,
    build_note,
    build_collapsible,
    build_action_buttons,
)


def test_header_basic():
    h = build_header(title="🤖 Claude · foo · opus-4-7")
    assert h == {
        "template": "purple",
        "title": {"tag": "plain_text", "content": "🤖 Claude · foo · opus-4-7"},
    }


def test_header_custom_template():
    h = build_header(title="x", template="green")
    assert h["template"] == "green"


def test_markdown_element():
    m = build_markdown("hello *world*")
    assert m == {"tag": "markdown", "content": "hello *world*"}


def test_divider_element():
    assert build_divider() == {"tag": "hr"}


def test_note_element():
    # Schema 2.0 dropped "note"; we now render notes as small/grey markdown.
    n = build_note("1.2K tokens · 4.3s")
    assert n["tag"] == "markdown"
    assert "1.2K tokens · 4.3s" in n["content"]


def test_collapsible_element():
    c = build_collapsible(
        summary="📖 Read auth.go  ✓ 50 lines",
        body_markdown="```\npackage auth\n```",
    )
    assert c["tag"] == "collapsible_panel"
    assert c["header"]["title"]["content"] == "📖 Read auth.go  ✓ 50 lines"
    body_elements = c["elements"]
    assert len(body_elements) == 1
    assert body_elements[0]["tag"] == "markdown"
    assert "package auth" in body_elements[0]["content"]


def test_action_buttons_two():
    buttons = build_action_buttons([
        ("confirm_yes", "确认", "primary"),
        ("confirm_no", "取消", "default"),
    ])
    assert buttons["tag"] == "action"
    actions = buttons["actions"]
    assert len(actions) == 2
    assert actions[0]["text"]["content"] == "确认"
    assert actions[0]["type"] == "primary"
    assert actions[0]["value"] == {"event_key": "confirm_yes"}


def test_build_card_combines_elements():
    card = build_card(
        header=build_header(title="t"),
        elements=[build_markdown("hi"), build_divider(), build_note("done")],
    )
    assert card["header"]["title"]["content"] == "t"
    elements = card["body"]["elements"]  # schema 2.0 nests under body
    assert len(elements) == 3
    assert elements[0]["tag"] == "markdown"
    assert elements[1]["tag"] == "hr"
    assert elements[2]["tag"] == "markdown"  # build_note → markdown under schema 2.0
