# ABOUTME: Behaviour tests for the content-addressed response cache.
# ABOUTME: The cache is load-bearing: point cost is unknown, so a second fetch must not happen.

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from wowperf.adapters.cache.disk import DiskCache, cache_key


def test_the_same_query_and_variables_produce_the_same_key() -> None:
    assert cache_key("query {}", {"b": 2, "a": 1}) == cache_key("query {}", {"a": 1, "b": 2})


def test_different_variables_produce_different_keys() -> None:
    assert cache_key("query {}", {"a": 1}) != cache_key("query {}", {"a": 2})


def test_a_second_call_is_served_from_disk_without_fetching(tmp_path: Path) -> None:
    calls: list[int] = []

    def fetch() -> dict[str, object]:
        calls.append(1)
        return {"value": 42}

    cache = DiskCache(tmp_path)
    assert cache.get_or_fetch("k", fetch) == ({"value": 42}, False)
    assert cache.get_or_fetch("k", fetch) == ({"value": 42}, True)
    assert len(calls) == 1


def test_a_fresh_cache_over_the_same_directory_still_hits(tmp_path: Path) -> None:
    DiskCache(tmp_path).get_or_fetch("k", lambda: {"value": 42})

    def fail() -> dict[str, object]:
        raise AssertionError("should have been served from disk")

    assert DiskCache(tmp_path).get_or_fetch("k", fail) == ({"value": 42}, True)


def test_a_written_entry_is_complete_and_leaves_no_temporary_behind(tmp_path: Path) -> None:
    DiskCache(tmp_path).get_or_fetch("k", lambda: {"value": 42})

    assert [p.name for p in tmp_path.iterdir()] == ["k.json"]
    assert json.loads((tmp_path / "k.json").read_text(encoding="utf-8")) == {"value": 42}


def test_an_entry_older_than_max_age_is_fetched_again(tmp_path: Path) -> None:
    clock = [1_000.0]
    calls: list[int] = []

    def fetch() -> dict[str, object]:
        calls.append(1)
        return {"at": clock[0]}

    cache = DiskCache(tmp_path, max_age_seconds=60, now=lambda: clock[0])
    assert cache.get_or_fetch("k", fetch) == ({"at": 1_000.0}, False)
    clock[0] = 1_030.0
    assert cache.get_or_fetch("k", fetch) == ({"at": 1_000.0}, True)
    clock[0] = 1_060.0
    assert cache.get_or_fetch("k", fetch) == ({"at": 1_000.0}, True)
    assert len(calls) == 1
    clock[0] = 1_061.0
    assert cache.get_or_fetch("k", fetch) == ({"at": 1_061.0}, False)
    assert len(calls) == 2


def test_opening_a_cache_purges_its_expired_entries(tmp_path: Path) -> None:
    clock = [1_000.0]
    DiskCache(tmp_path, max_age_seconds=60, now=lambda: clock[0]).get_or_fetch(
        "old", lambda: {"v": 1}
    )
    clock[0] = 1_100.0
    DiskCache(tmp_path, max_age_seconds=60, now=lambda: clock[0]).get_or_fetch(
        "fresh", lambda: {"v": 2}
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fresh.json"]


def test_purge_expired_ignores_a_file_removed_between_glob_and_stat(tmp_path: Path) -> None:
    """Another process sharing the cache directory may delete an entry between
    purge_expired's glob and this entry's stat; that must not raise. `_expired`
    calls `now()` before it stats the path, so a `now` that deletes the file is
    the simplest way to land inside that window.
    """
    DiskCache(tmp_path, max_age_seconds=60, now=lambda: 1_000.0).get_or_fetch(
        "k", lambda: {"v": 1}
    )

    def now_and_remove() -> float:
        (tmp_path / "k.json").unlink(missing_ok=True)
        return 1_100.0

    DiskCache(tmp_path, max_age_seconds=60, now=now_and_remove)


def test_get_or_fetch_refetches_an_entry_removed_between_exists_and_stat(tmp_path: Path) -> None:
    """The same race as above, on the read path: `get_or_fetch` checks that the
    file exists and then stats it through `_expired`, and another process may
    delete it in between. A vanished entry is a miss, not an exception. `_expired`
    calls `now()` before it stats the path, so a `now` that deletes the file once
    is the simplest way to land inside that window.
    """
    remove_next = [False]

    def now_and_remove_once() -> float:
        if remove_next[0]:
            remove_next[0] = False
            (tmp_path / "k.json").unlink(missing_ok=True)
        return 1_000.0

    cache = DiskCache(tmp_path, max_age_seconds=60, now=now_and_remove_once)
    assert cache.get_or_fetch("k", lambda: {"v": 1}) == ({"v": 1}, False)

    remove_next[0] = True
    assert cache.get_or_fetch("k", lambda: {"v": 2}) == ({"v": 2}, False)


def test_a_cache_without_a_max_age_keeps_everything(tmp_path: Path) -> None:
    clock = [0.0]
    cache = DiskCache(tmp_path, now=lambda: clock[0])
    cache.get_or_fetch("k", lambda: {"v": 1})
    clock[0] = 10**9
    assert DiskCache(tmp_path, now=lambda: clock[0]).get_or_fetch(
        "k", lambda: {"v": 2}
    ) == ({"v": 1}, True)


def test_an_interrupted_write_never_becomes_a_cache_entry(tmp_path: Path) -> None:
    """Content reaches the key only through the rename, so a torn write cannot be read.

    A process killed mid-write cannot be staged from inside the process. This
    drives the same seam instead: the rename fails, and nothing observable is
    left behind under the key nor as a stray temporary.
    """
    cache = DiskCache(tmp_path)

    with mock.patch.object(os, "replace", side_effect=OSError("interrupted")):
        with pytest.raises(OSError, match="interrupted"):
            cache.get_or_fetch("k", lambda: {"value": 42})

    assert list(tmp_path.iterdir()) == []
