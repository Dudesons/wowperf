# ABOUTME: Integration test wiring client, cache and ingest into a RunRepository.
# ABOUTME: Confirms a second get is served from the cache rather than the network.

import json
import tempfile
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

# The same "Den of Nalorakk" run test_ingest_streams.py builds by hand, so the
# whole slice tells one consistent fixture story: report abc123, fight 36.
FIGHTS_PAYLOAD: dict[str, Any] = {
    "reportData": {
        "report": {
            "code": "abc123",
            "title": "Keys",
            "startTime": 0,
            "endTime": 1920000,
            "fights": [
                {
                    "id": 36,
                    "name": "Den of Nalorakk",
                    "encounterID": 12660,
                    "startTime": 0,
                    "endTime": 1920000,
                    "kill": True,
                    "keystoneLevel": 16,
                    "keystoneAffixes": [9, 10, 147],
                    "keystoneTime": 1909000,
                    "keystoneBonus": 1,
                    "countReached": 744,
                    "countRequired": 729,
                    "npcCountMap": {"241874": 5, "244889": 35},
                    "friendlyPlayers": [693],
                    "friendlySpecs": ["Arcane"],
                    "friendlyItemLevels": [318],
                    "dungeonPulls": [
                        {
                            "id": 1,
                            "name": "Trash",
                            "encounterID": 0,
                            "startTime": 1000,
                            "endTime": 5000,
                            "kill": True,
                            "x": 10,
                            "y": 20,
                            "enemyNPCs": [{"id": 699, "gameID": 241874}],
                        },
                        {
                            "id": 2,
                            "name": "Boss",
                            "encounterID": 99001,
                            "startTime": 9000,
                            "endTime": 20000,
                            "kill": True,
                            "x": 30,
                            "y": 40,
                            "enemyNPCs": [{"id": 702, "gameID": 244889}],
                        },
                    ],
                }
            ],
            "masterData": {
                "actors": [
                    {"id": 693, "name": "Uglymage", "subType": "Mage", "server": "Hyjal"},
                ]
            },
        }
    }
}


def recording_repository(calls: list[str], tmp_path: Path | None = None) -> WclRunRepository:
    """Build one repository whose mock transport records every GraphQL operation name.

    The repository is backed by one cache directory that persists for its whole
    lifetime, as a real caller's would — so a `get` issued after a `load` on the
    same repository sees whatever `load` already cached, rather than starting cold.
    `tmp_path` is optional: the whole-load tests do not need a fresh directory
    injected by pytest, so one is created on demand.

    Each of the six event streams gets its own small, distinguishable payload —
    a real field swap in `repository.py` (e.g. assigning `interrupts` the
    `enemy_cast_rows` builder's result, or `damage_taken` the `deaths` builder's)
    must make a test built on this fixture fail.
    """
    abilities: dict[str, Any] = {"reportData": {"report": {"masterData": {"abilities": []}}}}
    npc_actors: dict[str, Any] = {
        "reportData": {
            "report": {
                "masterData": {
                    "actors": [
                        {"id": 699, "gameID": 241874},
                        {"id": 702, "gameID": 244889},
                    ]
                }
            }
        }
    }

    def events_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"reportData": {"report": {"events": {"data": rows, "nextPageTimestamp": None}}}}

    event_payloads: dict[str, dict[str, Any]] = {
        "Casts": events_payload(
            [{"type": "cast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2000}]
        ),
        "Deaths": events_payload(
            [{"type": "death", "sourceID": -1, "targetID": 693, "timestamp": 5000}]
        ),
        "EnemyCasts": events_payload(
            [{"type": "cast", "sourceID": 699, "abilityGameID": 200, "timestamp": 3000}]
        ),
        "Interrupts": events_payload(
            [
                {
                    "type": "interrupt", "abilityGameID": 300, "extraAbilityGameID": 400,
                    "sourceID": 693, "targetID": 702, "targetInstance": 1, "timestamp": 6000,
                }
            ]
        ),
        "EnemyDeaths": events_payload(
            [{"type": "death", "targetID": 702, "timestamp": 15000}]
        ),
        "DamageTaken": events_payload(
            [{"type": "damage", "abilityGameID": 500, "targetID": 693, "amount": 1000,
              "timestamp": 4000}]
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        query = json.loads(request.content)["query"]
        name = query.split("query ")[1].split("(")[0].strip()
        calls.append(name)
        if name == "Fights":
            return httpx.Response(200, json={"data": FIGHTS_PAYLOAD})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities})
        if name == "NpcActors":
            return httpx.Response(200, json={"data": npc_actors})
        return httpx.Response(200, json={"data": event_payloads[name]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    cache_dir = tmp_path if tmp_path is not None else Path(tempfile.mkdtemp())
    return WclRunRepository(client, DiskCache(cache_dir))


def test_the_repository_builds_a_run_from_the_api(tmp_path: Path) -> None:
    repository: RunRepository = recording_repository([], tmp_path)
    run = repository.get("abc123", None)
    assert (run.dungeon_name, run.keystone_level, len(run.pulls)) == ("Den of Nalorakk", 16, 2)


def test_a_second_get_makes_no_further_calls(tmp_path: Path) -> None:
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)
    repository.get("abc123", None)
    first_call_count = len(calls)
    repository.get("abc123", None)
    assert len(calls) == first_call_count


def test_get_fetches_only_the_fights_query_while_load_fetches_the_events(tmp_path: Path) -> None:
    """get returns a Run, so it must not pay for the paginated cast and death streams."""
    get_calls: list[str] = []
    recording_repository(get_calls, tmp_path / "get").get("abc123", None)
    assert get_calls == ["Fights"]

    load_calls: list[str] = []
    recording_repository(load_calls, tmp_path / "load").load("abc123", None)
    assert load_calls[0] == "Fights"
    assert set(load_calls) == {
        "Fights", "Abilities", "Casts", "Deaths",
        "EnemyCasts", "Interrupts", "EnemyDeaths", "DamageTaken", "NpcActors",
    }


def test_a_get_after_a_load_costs_nothing() -> None:
    """FIGHTS_QUERY is keyed on the report code alone, so a get sees load's cache entry."""
    calls: list[str] = []
    repository = recording_repository(calls)

    repository.load("abc123", 36)
    assert sorted(set(calls)) == [
        "Abilities", "Casts", "DamageTaken", "Deaths",
        "EnemyCasts", "EnemyDeaths", "Fights", "Interrupts", "NpcActors",
    ]

    calls.clear()
    repository.get("abc123", 36)
    assert calls == []


def test_a_loaded_run_carries_every_stream() -> None:
    loaded = recording_repository([]).load("abc123", 36)
    assert loaded.run.keystone_level == 16
    assert [cast.ability_id for cast in loaded.casts] == [100]
    assert [death.actor_id for death in loaded.deaths] == [693]
    assert [row.ability_id for row in loaded.enemy_cast_rows] == [200]
    assert [interrupt.interrupted_ability_id for interrupt in loaded.interrupts] == [400]
    assert [death.actor_id for death in loaded.enemy_deaths] == [702]
    assert [taken.amount for taken in loaded.damage_taken] == [1000]


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
