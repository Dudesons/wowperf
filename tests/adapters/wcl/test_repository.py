# ABOUTME: Integration test wiring client, cache and ingest into a RunRepository.
# ABOUTME: Confirms a second get is served from the cache rather than the network.

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.queries import FIGHTS_QUERY
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.ports import RunRepository

FIXTURE = Path(__file__).parent / "fixtures" / "report_fights.json"


def build_repository(tmp_path: Path, calls: list[str]) -> WclRunRepository:
    fights = json.loads(FIXTURE.read_text(encoding="utf-8"))
    empty_events: dict[str, Any] = {
        "reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}
    }
    abilities: dict[str, Any] = {"reportData": {"report": {"masterData": {"abilities": []}}}}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        query = json.loads(request.content)["query"]
        name = query.split("query ")[1].split("(")[0].strip()
        calls.append(name)
        if name == "Fights":
            return httpx.Response(200, json={"data": fights})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities})
        return httpx.Response(200, json={"data": empty_events})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path))


def test_the_repository_builds_a_run_from_the_api(tmp_path: Path) -> None:
    repository: RunRepository = build_repository(tmp_path, [])
    run = repository.get("abc123", None)
    assert (run.dungeon_name, run.keystone_level, len(run.pulls)) == ("Murder Row", 12, 2)


def test_a_second_get_makes_no_further_calls(tmp_path: Path) -> None:
    calls: list[str] = []
    repository = build_repository(tmp_path, calls)
    repository.get("abc123", None)
    first_call_count = len(calls)
    repository.get("abc123", None)
    assert len(calls) == first_call_count


def test_get_fetches_only_the_fights_query_while_load_fetches_the_events(tmp_path: Path) -> None:
    """get returns a Run, so it must not pay for the paginated cast and death streams."""
    get_calls: list[str] = []
    build_repository(tmp_path / "get", get_calls).get("abc123", None)
    assert get_calls == ["Fights"]

    load_calls: list[str] = []
    build_repository(tmp_path / "load", load_calls).load("abc123", None)
    assert load_calls[0] == "Fights"
    assert set(load_calls) == {"Fights", "Abilities", "Casts", "Deaths"}


def build_null_report_repository(tmp_path: Path, calls: list[str]) -> WclRunRepository:
    """A repository whose API answers HTTP 200 with a null report and no errors.

    This is what Warcraft Logs returns for an unlisted or unknown report code.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        calls.append(str(request.url))
        return httpx.Response(200, json={"data": {"reportData": {"report": None}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path))


def test_a_null_report_raises_an_ingest_error_naming_the_code(tmp_path: Path) -> None:
    repository = build_null_report_repository(tmp_path, [])
    with pytest.raises(IngestError, match="Report abc123 was not found"):
        repository.get("abc123", None)


def test_a_null_report_is_never_written_to_the_cache(tmp_path: Path) -> None:
    """A cached null would be permanent: get_or_fetch short-circuits on the file existing."""
    cache_dir = tmp_path / "cache"
    calls: list[str] = []
    repository = build_null_report_repository(cache_dir, calls)

    with pytest.raises(IngestError):
        repository.get("abc123", None)
    assert list(cache_dir.iterdir()) == []

    # The report being made public later must be reachable, so the second attempt
    # has to hit the network rather than a poisoned cache entry.
    with pytest.raises(IngestError):
        repository.get("abc123", None)
    assert len(calls) == 2


def test_a_null_report_cached_by_an_older_build_reports_the_problem(tmp_path: Path) -> None:
    """Caches written before the write-side check exists must not crash on a null."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    poisoned = cache_dir / f"{cache_key(FIGHTS_QUERY, {'code': 'abc123'})}.json"
    poisoned.write_text(json.dumps({"reportData": {"report": None}}), encoding="utf-8")

    repository = build_null_report_repository(cache_dir, [])
    with pytest.raises(IngestError, match="Report abc123 was not found"):
        repository.get("abc123", None)
