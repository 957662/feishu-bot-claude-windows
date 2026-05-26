"""Tests for the keychain abstraction.

Covers:
- InMemoryKeychainStore (used in unit tests across the codebase) for CRUD.
- WindowsCredentialStore with a mocked `win32cred` — pure-logic check so the
  suite runs cross-platform without pywin32 installed.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from feishu_bot_claude_win.config.keychain import (
    InMemoryKeychainStore,
    WindowsCredentialStore,
)


# ------------------- InMemoryKeychainStore -------------------

def test_in_memory_put_get():
    store = InMemoryKeychainStore()
    store.put("alice", "s3cret")
    assert store.get("alice") == "s3cret"


def test_in_memory_get_missing_returns_none():
    store = InMemoryKeychainStore()
    assert store.get("missing") is None


def test_in_memory_delete():
    store = InMemoryKeychainStore()
    store.put("alice", "x")
    store.delete("alice")
    assert store.get("alice") is None


def test_in_memory_delete_missing_is_noop():
    store = InMemoryKeychainStore()
    store.delete("nope")  # must not raise


# ------------------- WindowsCredentialStore -------------------

@pytest.fixture
def fake_win32cred(monkeypatch):
    """Install a fake `win32cred` module so the tests run on macOS / Linux."""
    fake = types.ModuleType("win32cred")
    fake.CRED_TYPE_GENERIC = 1
    fake.CRED_PERSIST_LOCAL_MACHINE = 2
    fake.CredWrite = MagicMock()
    fake.CredRead = MagicMock()
    fake.CredDelete = MagicMock()
    monkeypatch.setitem(sys.modules, "win32cred", fake)
    return fake


def test_windows_put_calls_credwrite(fake_win32cred):
    store = WindowsCredentialStore()
    store.put("mybot", "topsecret")
    fake_win32cred.CredWrite.assert_called_once()
    cred = fake_win32cred.CredWrite.call_args[0][0]
    assert cred["TargetName"] == "feishu-bot-claude-win:mybot"
    assert cred["CredentialBlob"] == "topsecret"


def test_windows_get_decodes_utf16le_bytes(fake_win32cred):
    fake_win32cred.CredRead.return_value = {
        "CredentialBlob": "hello".encode("utf-16-le"),
    }
    store = WindowsCredentialStore()
    assert store.get("mybot") == "hello"


def test_windows_get_returns_none_when_missing(fake_win32cred):
    class _NotFound(Exception):
        winerror = 1168
    fake_win32cred.CredRead.side_effect = _NotFound()
    store = WindowsCredentialStore()
    assert store.get("mybot") is None


def test_windows_delete_calls_creddelete(fake_win32cred):
    store = WindowsCredentialStore()
    store.delete("mybot")
    fake_win32cred.CredDelete.assert_called_once()
    kwargs = fake_win32cred.CredDelete.call_args.kwargs
    assert kwargs["TargetName"] == "feishu-bot-claude-win:mybot"


def test_windows_delete_swallows_not_found(fake_win32cred):
    class _NotFound(Exception):
        winerror = 1168
    fake_win32cred.CredDelete.side_effect = _NotFound()
    store = WindowsCredentialStore()
    store.delete("mybot")  # must not raise
