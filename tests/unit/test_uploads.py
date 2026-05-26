"""Tests for long-output upload decision policy."""

import pytest

from feishu_bot_claude_win.rendering.uploads import LongOutputPolicy, UploadDecision


def test_short_output_inlines():
    policy = LongOutputPolicy(inline_lines_threshold=50, upload_bytes_threshold=10_000)
    decision = policy.decide(content="line1\nline2")
    assert decision == UploadDecision.INLINE


def test_long_lines_uploads():
    policy = LongOutputPolicy(inline_lines_threshold=50, upload_bytes_threshold=10_000)
    content = "\n".join(["x"] * 100)
    decision = policy.decide(content=content)
    assert decision == UploadDecision.UPLOAD


def test_big_bytes_uploads():
    policy = LongOutputPolicy(inline_lines_threshold=10_000, upload_bytes_threshold=1024)
    content = "x" * 5000
    decision = policy.decide(content=content)
    assert decision == UploadDecision.UPLOAD


def test_disabled_policy_always_inlines():
    policy = LongOutputPolicy(inline_lines_threshold=50, upload_bytes_threshold=10_000, enabled=False)
    long = "\n".join(["x"] * 10_000)
    assert policy.decide(long) == UploadDecision.INLINE
