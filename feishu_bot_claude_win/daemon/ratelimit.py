"""Rate limiting: TokenBucket and exponential backoff for Feishu 11232 throttle."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


class TokenBucket:
    """Async token bucket. capacity tokens, refills at rate_per_sec."""

    def __init__(self, rate_per_sec: float, capacity: int) -> None:
        self._rate = rate_per_sec
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """Block until one token is available, then consume it."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait_seconds = deficit / self._rate
            await asyncio.sleep(wait_seconds + 0.001)

    def try_acquire(self) -> bool:
        """Non-blocking: return True if a token was consumed, False otherwise."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


@dataclass(frozen=True)
class BackoffPolicy:
    """Exponential backoff for Feishu 11232 throttle and similar transient errors."""

    initial_sec: float = 1.0
    multiplier: float = 2.0
    max_sec: float = 30.0
    max_attempts: int = 7

    def delay_for(self, attempt: int) -> float:
        """Return the sleep duration after `attempt` failures (1-based)."""
        delay = self.initial_sec * (self.multiplier ** (attempt - 1))
        return min(delay, self.max_sec)
