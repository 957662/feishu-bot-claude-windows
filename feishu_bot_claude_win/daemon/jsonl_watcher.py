"""Async wrapper around watchfiles that yields a signal when the target file grows."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncIterator

import watchfiles

logger = logging.getLogger(__name__)


class JsonlWatcher:
    """Yield a signal whenever the watched file grows or is created.

    Watches the *parent directory* of `path` so file creation is also detected.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def changes(self, stop_after: int = 0) -> AsyncIterator[None]:
        """Yield None each time the file changes. stop_after=N exits after N signals; 0 = unlimited."""
        # Ensure parent exists so watchfiles can watch it
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Resolve symlinks once so the comparison works on macOS where
        # /var/folders is a symlink to /private/var/folders.
        resolved_path = self._path.resolve()
        emitted = 0
        async for changes in watchfiles.awatch(self._path.parent, recursive=False):
            relevant = any(Path(p).resolve() == resolved_path for _, p in changes)
            if relevant:
                yield None
                emitted += 1
                if stop_after and emitted >= stop_after:
                    return
