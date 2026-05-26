"""Tests for BindingStore: TOML I/O, lookup, lifecycle."""

from datetime import datetime, timezone

import pytest

from feishu_bot_claude_win.config.binding import BindingConfig, BindingStore


def _make_config(name="foo-bot", project_dir="/abs/foo", **overrides) -> BindingConfig:
    defaults = dict(
        name=name,
        project_dir=project_dir,
        tmux_session=f"claude-{name}",
        feishu_app_id=f"cli_{name}",
        secret_ref=f"feishu-bot-claude.{name}.app_secret",
        created_at=datetime(2026, 5, 26, 18, 50, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return BindingConfig(**defaults)


def test_empty_store_returns_no_bindings(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    assert store.all() == []


def test_add_then_find_by_name(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    cfg = _make_config()
    store.add(cfg)
    assert store.find_by_name("foo-bot") == cfg


def test_find_by_name_returns_none_when_absent(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    assert store.find_by_name("nope") is None


def test_find_by_cwd_returns_matching_binding(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot", project_dir="/abs/foo"))
    store.add(_make_config(name="bar-bot", project_dir="/abs/bar"))
    found = store.find_by_cwd("/abs/foo")
    assert found is not None
    assert found.name == "foo-bot"


def test_find_by_cwd_returns_none_when_no_match(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot", project_dir="/abs/foo"))
    assert store.find_by_cwd("/abs/other") is None


def test_add_persists_to_disk(tmp_path):
    path = tmp_path / "bindings.toml"
    store1 = BindingStore(path)
    cfg = _make_config()
    store1.add(cfg)
    store2 = BindingStore(path)
    assert store2.find_by_name("foo-bot") == cfg


def test_remove_deletes_binding(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config())
    store.remove("foo-bot")
    assert store.find_by_name("foo-bot") is None
    assert store.all() == []


def test_remove_missing_raises(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    with pytest.raises(KeyError, match="foo-bot"):
        store.remove("foo-bot")


def test_add_duplicate_name_raises(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot"))
    with pytest.raises(ValueError, match="already exists"):
        store.add(_make_config(name="foo-bot", project_dir="/abs/different"))


def test_add_duplicate_project_dir_raises(tmp_path):
    """Hard invariant: one project dir ↔ one binding."""
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot", project_dir="/abs/foo"))
    with pytest.raises(ValueError, match="project_dir.*already bound"):
        store.add(_make_config(name="another-bot", project_dir="/abs/foo"))


def test_toml_file_has_secure_permissions(tmp_path):
    """bindings.toml must be 0600 after any write."""
    path = tmp_path / "bindings.toml"
    store = BindingStore(path)
    store.add(_make_config())
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


import threading


def test_concurrent_writes_do_not_corrupt(tmp_path):
    """Two threads adding different bindings should both succeed and produce
    a valid TOML file with both entries."""
    path = tmp_path / "bindings.toml"
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def add_one(name: str, dir_: str) -> None:
        try:
            barrier.wait()
            store = BindingStore(path)
            store.add(_make_config(name=name, project_dir=dir_))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=add_one, args=("alpha", "/abs/alpha"))
    t2 = threading.Thread(target=add_one, args=("beta", "/abs/beta"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    final = BindingStore(path).all()
    names = {b.name for b in final}
    assert not errors and names == {"alpha", "beta"}


from unittest.mock import patch, MagicMock


def test_add_rollback_on_save_failure(tmp_path):
    """When _save() fails, add() should restore the cache to its previous state."""
    path = tmp_path / "bindings.toml"
    store = BindingStore(path)
    cfg1 = _make_config(name="alpha", project_dir="/abs/alpha")
    store.add(cfg1)

    cfg2 = _make_config(name="beta", project_dir="/abs/beta")

    # Mock _save to raise an exception
    with patch.object(store, "_save", side_effect=IOError("disk full")):
        with pytest.raises(IOError, match="disk full"):
            store.add(cfg2)

    # Cache should still contain only cfg1
    assert store.all() == [cfg1]
    assert store.find_by_name("beta") is None


def test_remove_rollback_on_save_failure(tmp_path):
    """When _save() fails during remove(), the deleted binding should be restored."""
    path = tmp_path / "bindings.toml"
    store = BindingStore(path)
    cfg = _make_config(name="foo-bot", project_dir="/abs/foo")
    store.add(cfg)

    # Mock _save to raise an exception
    with patch.object(store, "_save", side_effect=IOError("disk full")):
        with pytest.raises(IOError, match="disk full"):
            store.remove("foo-bot")

    # The binding should still exist in cache
    assert store.find_by_name("foo-bot") == cfg


def test_remove_binding_in_middle_of_list(tmp_path):
    """Test removing a binding that's not first in the list.

    This ensures the loop condition in remove() exercises both the
    'found' and 'not found yet' branches.
    """
    path = tmp_path / "bindings.toml"
    store = BindingStore(path)
    store.add(_make_config(name="alpha", project_dir="/abs/alpha"))
    store.add(_make_config(name="beta", project_dir="/abs/beta"))
    store.add(_make_config(name="gamma", project_dir="/abs/gamma"))

    # Remove the middle one
    store.remove("beta")

    # Verify it's gone and others remain
    assert store.find_by_name("alpha") is not None
    assert store.find_by_name("beta") is None
    assert store.find_by_name("gamma") is not None


def test_merge_conflict_on_concurrent_modification(tmp_path):
    """When two stores modify the same binding name concurrently, _merge raises.

    This happens when:
    1. Store A loads file (no "conflict" entry)
    2. Store B loads file (no "conflict" entry)
    3. Store A adds "conflict" with content1 and saves
    4. Store B adds "conflict" with content2 and tries to save

    The conflict is detected because both stores tried to add the same name
    but with different content.
    """
    path = tmp_path / "bindings.toml"

    # Store 1: add a binding and save
    store1 = BindingStore(path)
    cfg1 = _make_config(name="conflict", project_dir="/abs/v1")
    store1.add(cfg1)

    # Store 2: load the file BEFORE Store 1 added the binding, so
    # "conflict" is unknown to store2's _known_names, but we'll
    # manually add a different version to its cache
    # This simulates the race condition where both stores added the same name
    store2 = BindingStore(path)
    # At this point, store2 knows about "conflict" from loading the file
    # So we need to clear that from _known_names to simulate the race
    store2._known_names.remove("conflict")  # Pretend we didn't see it

    # Now modify store2's cache to have a different content
    cfg2 = _make_config(name="conflict", project_dir="/abs/v2")
    store2._cache = [cfg2]

    # When store2 tries to save, it will merge with disk (which has cfg1 from store1)
    # Since cfg1 is not in _known_names, it's treated as a new entry
    # But cfg2 is also in cache, so the merge will detect the conflict
    with pytest.raises(ValueError, match="concurrent modification"):
        store2._save()
