# ABOUTME: Integration test wiring client, cache and ingest into a RunRepository.
# ABOUTME: Confirms a second get is served from the cache rather than the network.

import json
from pathlib import Path
from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
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
