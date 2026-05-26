"""Decide whether a tool's output is inlined into the card or uploaded as a file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UploadDecision(Enum):
    INLINE = "inline"
    UPLOAD = "upload"


@dataclass(frozen=True)
class LongOutputPolicy:
    """Decide INLINE vs UPLOAD based on line count and byte size."""

    inline_lines_threshold: int = 50
    upload_bytes_threshold: int = 10_000  # 10 KB
    enabled: bool = True

    def decide(self, content: str) -> UploadDecision:
        if not self.enabled:
            return UploadDecision.INLINE
        line_count = content.count("\n") + (1 if content else 0)
        if line_count > self.inline_lines_threshold:
            return UploadDecision.UPLOAD
        if len(content.encode("utf-8")) > self.upload_bytes_threshold:
            return UploadDecision.UPLOAD
        return UploadDecision.INLINE
