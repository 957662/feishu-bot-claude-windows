"""Push bot menu config to Feishu, with file fallback if API unsupported."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class MenuPusher(Protocol):
    async def push_menu(self, app_id: str, menu_json: dict) -> None: ...


@dataclass(frozen=True)
class MenuPushResult:
    method: str  # "api" | "file"
    fallback_path: Path | None = None


async def push_menu_with_fallback(
    lark_menu: MenuPusher,
    app_id: str,
    menu_json: dict,
    fallback_dir: Path,
    binding_name: str,
) -> MenuPushResult:
    """Try API push; on any error, write JSON to fallback file and return."""
    try:
        await lark_menu.push_menu(app_id=app_id, menu_json=menu_json)
        return MenuPushResult(method="api")
    except Exception as e:  # noqa: BLE001
        logger.warning("menu API push failed (%s); writing fallback file", e)
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / f"{binding_name}.menu.json"
        path.write_text(json.dumps(menu_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return MenuPushResult(method="file", fallback_path=path)
