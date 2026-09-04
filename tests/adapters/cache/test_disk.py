# ABOUTME: Behaviour tests for the content-addressed response cache.
# ABOUTME: The cache is load-bearing: point cost is unknown, so a second fetch must not happen.

from pathlib import Path

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
    assert cache.get_or_fetch("k", fetch) == {"value": 42}
    assert cache.get_or_fetch("k", fetch) == {"value": 42}
    assert len(calls) == 1


def test_a_fresh_cache_over_the_same_directory_still_hits(tmp_path: Path) -> None:
    DiskCache(tmp_path).get_or_fetch("k", lambda: {"value": 42})

    def fail() -> dict[str, object]:
        raise AssertionError("should have been served from disk")

    assert DiskCache(tmp_path).get_or_fetch("k", fail) == {"value": 42}
