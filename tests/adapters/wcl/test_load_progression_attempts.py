# ABOUTME: load_progression_attempts deepens only qualifying attempts with two streams each.
# ABOUTME: Counting operations proves the narrower claim: no casts, no rankings, one ability call.

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from tests.adapters.wcl.test_load_progression import a_fight
from tests.adapters.wcl.test_repository import operation_name
from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.repository import WclRunRepository
from wowperf.domain.progression import Progression

# Three fights at one boss: two above MIN_ATTEMPT_SECONDS (44.0), one a 20s
# reset that build_progression discards. Only the two kept attempts should
# ever be deepened.
NIGHT: dict[str, Any] = {
    "reportData": {
        "report": {
            "code": "abc123",
            "title": "Raid",
            "startTime": 0,
            "endTime": 40_000_000,
            "owner": {"name": "Emberkin"},
            "phases": [],
            "fights": [
                a_fight(1, 3492, 5, 60.0, 200.0),
                a_fight(2, 3492, 5, 55.0, 210.0),
                a_fight(3, 3492, 5, 99.9, 20.0),
            ],
            "masterData": {"actors": []},
        }
    }
}


def _events_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"reportData": {"report": {"events": {"data": rows, "nextPageTimestamp": None}}}}


ABILITIES_PAYLOAD: dict[str, Any] = {
    "reportData": {"report": {"masterData": {"abilities": []}}}
}
DEATHS_PAYLOAD: dict[str, Any] = _events_payload(
    [{"type": "death", "sourceID": -1, "targetID": 11, "timestamp": 5000}]
)
DAMAGE_TAKEN_PAYLOAD: dict[str, Any] = _events_payload(
    [
        {
            "type": "damage",
            "abilityGameID": 12345,
            "sourceID": 249,
            "targetID": 11,
            "amount": 1000,
            "timestamp": 4000,
        }
    ]
)


class _UncachedDiskCache(DiskCache):
    """A `DiskCache` that never serves a stored answer, so every call reaches the network.

    Used only by the "once per command" assertion below. The ordinary,
    persistent `DiskCache` every other test in this file uses keys
    `_ability_dictionary` by report code alone, so it would silently absorb a
    second call for the same report -- exactly the mistake that assertion
    exists to catch -- into a cache hit that never reaches the mock transport.
    Proving the call happens once needs a cache that cannot hide a repeat call
    behind a hit.
    """

    def get_or_fetch(
        self, key: str, fetch: Callable[[], dict[str, Any]]
    ) -> tuple[dict[str, Any], bool]:
        return fetch(), False


def a_repository_counting_calls(
    tmp_path: Path, *, cache: DiskCache | None = None
) -> tuple[WclRunRepository, list[str]]:
    """One repository over a mock transport, plus the operations it sent, in order."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        name = operation_name(json.loads(request.content))
        calls.append(name)
        if name == "Fights":
            return httpx.Response(200, json={"data": NIGHT})
        if name == "Abilities":
            return httpx.Response(200, json={"data": ABILITIES_PAYLOAD})
        if name == "Deaths":
            return httpx.Response(200, json={"data": DEATHS_PAYLOAD})
        if name == "DamageTaken":
            return httpx.Response(200, json={"data": DAMAGE_TAKEN_PAYLOAD})
        raise AssertionError(f"unexpected operation {name!r} in load_progression_attempts test")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, cache if cache is not None else DiskCache(tmp_path)), calls


def test_deepens_every_qualifying_attempt_and_no_discarded_one(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)
    series = repository.load_progression("abc123", 3492, 5)

    deep = repository.load_progression_attempts(series)

    assert [one.encounter.fight_id for one in deep.attempts_with_events] == [1, 2]
    assert len(series.discarded) == 1


def test_sends_only_deaths_and_damage_taken_per_attempt(tmp_path: Path) -> None:
    # An uncached repository: `_ability_dictionary` keys its query on the
    # report code alone, so an ordinary `DiskCache` would absorb a second,
    # wrongly-per-attempt call into a hit before it ever became an
    # "Abilities" operation. This cache cannot hide that mistake.
    repository, operations = a_repository_counting_calls(
        tmp_path, cache=_UncachedDiskCache(tmp_path)
    )
    series = repository.load_progression("abc123", 3492, 5)
    operations.clear()  # drop the "Fights" call load_progression made above

    repository.load_progression_attempts(series)

    assert operations.count("Deaths") == 2
    assert operations.count("DamageTaken") == 2
    assert "Casts" not in operations
    assert "Debuffs" not in operations
    assert "Healing" not in operations
    assert operations.count("Abilities") == 1  # once for the command, not once per attempt


def test_returns_empty_and_fetches_nothing_when_no_attempt_qualifies(tmp_path: Path) -> None:
    """A night where every attempt falls under `MIN_ATTEMPT_SECONDS` leaves
    `progression.attempts` empty. `load_progression_attempts` must return
    before spending a point on an ability dictionary nothing would read.
    """
    repository, operations = a_repository_counting_calls(tmp_path)
    empty = Progression(
        report_code="abc123", encounter_id=3492, boss_name="Boss", difficulty=5, size=20,
    )

    deep = repository.load_progression_attempts(empty)

    assert deep.loaded == ()
    assert operations == []


def test_carries_the_deaths_and_damage_the_streams_returned(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)
    series = repository.load_progression("abc123", 3492, 5)

    deep = repository.load_progression_attempts(series)

    first = deep.attempts_with_events[0]
    assert [death.actor_id for death in first.deaths] == [11]
    assert [hit.ability_id for hit in first.damage_taken] == [12345]
    assert first.damage_taken[0].source_id == 249
