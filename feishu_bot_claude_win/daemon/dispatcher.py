"""Op-name → handler-function routing."""

from __future__ import annotations

from typing import Awaitable, Callable

HandlerFn = Callable[[dict], Awaitable[object]]


class Dispatcher:
    """Registry mapping op names to async handler callables."""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, op: str, handler: HandlerFn) -> None:
        if op in self._handlers:
            raise ValueError(f"handler for {op!r} already registered")
        self._handlers[op] = handler

    def lookup(self, op: str) -> HandlerFn:
        try:
            return self._handlers[op]
        except KeyError:
            raise KeyError(f"no handler for op {op!r}") from None

    def registered_ops(self) -> list[str]:
        return list(self._handlers.keys())
