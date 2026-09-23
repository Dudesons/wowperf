# ABOUTME: The night load reads one report once and keeps every boss instead of picking one.
# ABOUTME: Counting the operations and the bosses proves the read does not narrow or refuse.

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.adapters.wcl.test_repository import operation_name
from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.repository import WclRunRepository


def a_fight(
    fight_id: int, encounter_id: int, difficulty: int, left: float, seconds: float
) -> dict[str, Any]:
    start = fight_id * 1_000_000
    return {
        "id": fight_id,
        "name": "Emberkin",
        "encounterID": encounter_id,
        "difficulty": difficulty,
        "size": 20,
        "kill": False,
        "fightPercentage": left,
        "bossPercentage": left,
        "lastPhase": 2,
        "lastPhaseIsIntermission": False,
        "phaseTransitions": [{"id": 1, "startTime": float(start)}],
        "startTime": start,
        "endTime": start + int(seconds * 1000),
        "friendlyPlayers": [],
        "friendlySpecs": [],
        "friendlyItemLevels": [],
        "dungeonPulls": [],
    }


# Three bosses: 3492 with two qualifying attempts and one reset, 3429 with one
# qualifying attempt, 3388 with a single qualifying attempt at a different
# difficulty than the other two -- so difficulty resolution is exercised per
# boss, not just once for the whole report.
THREE_BOSS_NIGHT: dict[str, Any] = {
    "reportData": {
        "report": {
            "code": "abc123",
            "title": "Raid",
            "startTime": 0,
            "endTime": 40_000_000,
            "owner": {"name": "Emberkin"},
            "phases": [
                {
                    "encounterID": 3492,
                    "separatesWipes": True,
                    "phases": [
                        {"id": 1, "name": "Stage One", "isIntermission": False},
                    ],
                },
            ],
            "fights": [
                a_fight(28, 3492, 5, 64.81, 215.7),
                a_fight(29, 3492, 5, 85.80, 105.9),
                a_fight(35, 3492, 5, 100.0, 15.8),
                a_fight(26, 3429, 5, 51.12, 271.3),
                a_fight(41, 3388, 4, 12.30, 300.0),
            ],
            "masterData": {"actors": []},
        }
    }
}


def a_repository_counting_calls(
    tmp_path: Path, payload: dict[str, Any] = THREE_BOSS_NIGHT
) -> tuple[WclRunRepository, list[str]]:
    """One repository over a mock transport, plus the operations it sent."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        calls.append(operation_name(json.loads(request.content)))
        return httpx.Response(200, json={"data": payload})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path)), calls


def test_a_whole_night_costs_one_query(tmp_path: Path) -> None:
    repository, calls = a_repository_counting_calls(tmp_path)

    repository.load_night("abc123", None)

    assert calls == ["Fights"]


def test_every_boss_the_report_holds_comes_back_as_its_own_progression(
    tmp_path: Path,
) -> None:
    """The presence a naive grouping would collapse: three bosses, not one or a refusal.

    Where `load_progression` would raise ("several bosses; pass --boss"),
    `load_night` must return all three, each carrying only its own attempts.
    """
    repository, _ = a_repository_counting_calls(tmp_path)

    night = repository.load_night("abc123", None)

    assert [boss.encounter_id for boss in night.bosses] == [3492, 3429, 3388]
    by_id = {boss.encounter_id: boss for boss in night.bosses}
    assert len(by_id[3492].attempts) == 2, "fight 35 is a reset and stays discarded"
    assert [a.fight_id for a in by_id[3492].discarded] == [35]
    assert len(by_id[3429].attempts) == 1
    assert len(by_id[3388].attempts) == 1
    assert by_id[3388].difficulty == 4


def test_an_explicit_difficulty_applies_to_every_boss(tmp_path: Path) -> None:
    """`--difficulty` is a report-wide value here, applied to every boss in turn."""
    two_boss: dict[str, Any] = json.loads(json.dumps(THREE_BOSS_NIGHT))
    fights = two_boss["reportData"]["report"]["fights"]
    two_boss["reportData"]["report"]["fights"] = [f for f in fights if f["id"] != 41]
    repository, _ = a_repository_counting_calls(tmp_path, two_boss)

    night = repository.load_night("abc123", 5)

    assert [boss.encounter_id for boss in night.bosses] == [3492, 3429]
    assert all(boss.difficulty == 5 for boss in night.bosses)


def test_an_explicit_difficulty_absent_for_one_boss_says_so(tmp_path: Path) -> None:
    """`--difficulty` reuses `_pick_boss`'s own check, once per boss.

    THREE_BOSS_NIGHT only ever fights 3388 at difficulty 4, never 5. An
    explicit `--difficulty 5` must fail loudly, naming the boss that does not
    have it, exactly as `load_progression` fails on a boss fought only at a
    different difficulty than the one asked for.
    """
    repository, _ = a_repository_counting_calls(tmp_path)

    with pytest.raises(ValueError) as error:
        repository.load_night("abc123", 5)

    message = str(error.value)
    assert "3388" in message
    assert "5" in message


def test_a_report_with_no_boss_fight_is_an_empty_night_not_an_error(tmp_path: Path) -> None:
    empty: dict[str, Any] = json.loads(json.dumps(THREE_BOSS_NIGHT))
    empty["reportData"]["report"]["fights"] = []
    repository, _ = a_repository_counting_calls(tmp_path, empty)

    night = repository.load_night("abc123", None)

    assert night.bosses == ()
