"""Per-binding runtime state — what jsonl byte we're at, what card we're updating."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BindingRuntimeState:
    """Mutable per-binding state, persisted as JSON for crash recovery."""

    binding_name: str
    current_turn_card_id: str | None = None
    jsonl_offset: int = 0
    last_event_uuid: str | None = None
    chat_id: str = ""  # discovered from first inbound message; empty = bootstrap pending

    def set_current_turn_card(self, message_id: str) -> None:
        self.current_turn_card_id = message_id

    def reset_current_turn(self) -> None:
        self.current_turn_card_id = None

    def advance_offset(self, delta: int) -> None:
        self.jsonl_offset += delta

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "binding_name": self.binding_name,
            "current_turn_card_id": self.current_turn_card_id,
            "jsonl_offset": self.jsonl_offset,
            "last_event_uuid": self.last_event_uuid,
            "chat_id": self.chat_id,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp.replace(path)

    @classmethod
    def load(cls, binding_name: str, path: Path) -> "BindingRuntimeState":
        if not path.exists():
            return cls(binding_name=binding_name)
        data = json.loads(path.read_text())
        return cls(
            binding_name=binding_name,
            current_turn_card_id=data.get("current_turn_card_id"),
            jsonl_offset=data.get("jsonl_offset", 0),
            last_event_uuid=data.get("last_event_uuid"),
            chat_id=data.get("chat_id", ""),
        )
