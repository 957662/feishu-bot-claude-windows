"""Tests for Dispatcher: register handlers, look them up by op name."""

import pytest

from feishu_bot_claude_win.daemon.dispatcher import Dispatcher


async def _example_handler(args):
    return {"got": args}


def test_register_then_lookup():
    d = Dispatcher()
    d.register("ping", _example_handler)
    assert d.lookup("ping") is _example_handler


def test_lookup_missing_raises():
    d = Dispatcher()
    with pytest.raises(KeyError, match="no handler for op 'unknown'"):
        d.lookup("unknown")


def test_register_duplicate_raises():
    d = Dispatcher()
    d.register("ping", _example_handler)
    with pytest.raises(ValueError, match="handler for 'ping' already registered"):
        d.register("ping", _example_handler)


def test_registered_ops_lists_all():
    d = Dispatcher()
    d.register("a", _example_handler)
    d.register("b", _example_handler)
    assert sorted(d.registered_ops()) == ["a", "b"]
