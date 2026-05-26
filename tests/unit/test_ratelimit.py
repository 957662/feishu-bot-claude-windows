"""Tests for TokenBucket rate limiter."""

import asyncio
import time

import pytest

from feishu_bot_claude_win.daemon.ratelimit import TokenBucket


@pytest.mark.asyncio
async def test_acquire_immediate_when_tokens_available():
    bucket = TokenBucket(rate_per_sec=10, capacity=10)
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_acquire_blocks_when_empty():
    bucket = TokenBucket(rate_per_sec=10, capacity=2)
    await bucket.acquire()
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert 0.07 <= elapsed <= 0.30, f"expected ~0.1s, got {elapsed:.3f}"


@pytest.mark.asyncio
async def test_refill_over_time():
    bucket = TokenBucket(rate_per_sec=10, capacity=5)
    for _ in range(5):
        await bucket.acquire()
    await asyncio.sleep(0.25)
    start = time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, f"expected near-zero, got {elapsed:.3f}"


@pytest.mark.asyncio
async def test_try_acquire_returns_false_when_empty():
    bucket = TokenBucket(rate_per_sec=10, capacity=1)
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False
