"""Tests for menu push with file-write fallback."""

import json

import pytest

from feishu_bot_claude_win.daemon.menu import MenuPushResult, push_menu_with_fallback


class FakeLarkMenu:
    """Test double — simulates lark-cli menu push API."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls: list[dict] = []

    async def push_menu(self, app_id: str, menu_json: dict) -> None:
        self.calls.append({"app_id": app_id, "menu": menu_json})
        if not self.succeed:
            raise RuntimeError("API endpoint not supported")


@pytest.mark.asyncio
async def test_push_succeeds_via_api(tmp_path):
    fake = FakeLarkMenu(succeed=True)
    result = await push_menu_with_fallback(
        lark_menu=fake,
        app_id="cli_xxx",
        menu_json={"menu_items": []},
        fallback_dir=tmp_path,
        binding_name="foo-bot",
    )
    assert result.method == "api"
    assert result.fallback_path is None
    assert fake.calls[0]["app_id"] == "cli_xxx"


@pytest.mark.asyncio
async def test_push_falls_back_to_file_on_api_failure(tmp_path):
    fake = FakeLarkMenu(succeed=False)
    result = await push_menu_with_fallback(
        lark_menu=fake,
        app_id="cli_xxx",
        menu_json={"menu_items": [{"label": "x"}]},
        fallback_dir=tmp_path,
        binding_name="foo-bot",
    )
    assert result.method == "file"
    assert result.fallback_path is not None
    assert result.fallback_path.exists()
    contents = json.loads(result.fallback_path.read_text())
    assert contents == {"menu_items": [{"label": "x"}]}
