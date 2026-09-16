# ABOUTME: The progression load reads one report once and selects one boss's attempts.
# ABOUTME: Counting the operations proves the design's cost claim: one night, one query.

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
        "name": "Emberkin" if encounter_id == 3492 else "Stonewake",
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


NIGHT: dict[str, Any] = {
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
                        {"id": 2, "name": "Stage Two", "isIntermission": False},
                        {"id": 3, "name": "Intermission", "isIntermission": True},
                    ],
                },
                {"encounterID": 3429, "separatesWipes": False, "phases": []},
            ],
            "fights": [
                a_fight(28, 3492, 5, 64.81, 215.7),
                a_fight(29, 3492, 5, 85.80, 105.9),
                a_fight(30, 3492, 5, 16.49, 480.0),
                a_fight(35, 3492, 5, 100.0, 15.8),
                a_fight(26, 3429, 5, 51.12, 271.3),
                a_fight(40, 3492, 4, 70.00, 200.0),
            ],
            "masterData": {"actors": []},
        }
    }
}


def a_repository_counting_calls(
    tmp_path: Path, payload: dict[str, Any] = NIGHT
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
    """The design's central cost claim. A regression here is a cost regression."""
    repository, calls = a_repository_counting_calls(tmp_path)

    repository.load_progression("abc123", 3492, 5)

    assert calls == ["Fights"]


def test_only_the_asked_for_boss_and_difficulty_are_in_the_series(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)

    progression = repository.load_progression("abc123", 3492, 5)

    seen = [a.fight_id for a in progression.attempts + progression.discarded]
    assert sorted(seen) == [28, 29, 30, 35]
    assert 26 not in seen, "a different boss"
    assert 40 not in seen, "a different difficulty"


def test_the_reset_is_discarded_and_the_deepest_is_not_the_last(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)

    progression = repository.load_progression("abc123", 3492, 5)

    assert [a.fight_id for a in progression.discarded] == [35]
    assert [a.fight_id for a in progression.attempts] == [28, 29, 30]
    assert progression.deepest is not None
    assert progression.deepest.fight_id == 30


def test_the_phase_table_and_its_guard_come_from_the_report(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)

    progression = repository.load_progression("abc123", 3492, 5)

    assert [p.name for p in progression.phases] == [
        "Stage One",
        "Stage Two",
        "Intermission",
    ]
    assert progression.separates_wipes is True


def test_a_boss_the_report_lists_no_phases_for_gets_none(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)

    progression = repository.load_progression("abc123", 3429, 5)

    assert progression.phases == ()
    assert progression.separates_wipes is False


def test_a_report_holding_several_bosses_asks_which_one(tmp_path: Path) -> None:
    repository, _ = a_repository_counting_calls(tmp_path)

    with pytest.raises(ValueError) as error:
        repository.load_progression("abc123", None, None)

    message = str(error.value)
    assert "--boss" in message
    assert "3492" in message and "3429" in message


def test_a_report_holding_one_boss_needs_no_flag(tmp_path: Path) -> None:
    one_boss: dict[str, Any] = json.loads(json.dumps(NIGHT))
    fights = one_boss["reportData"]["report"]["fights"]
    one_boss["reportData"]["report"]["fights"] = [
        f for f in fights if f["encounterID"] == 3492 and f["difficulty"] == 5
    ]
    repository, _ = a_repository_counting_calls(tmp_path, one_boss)

    progression = repository.load_progression("abc123", None, None)

    assert progression.encounter_id == 3492
    assert progression.difficulty == 5


def test_a_report_with_no_boss_fight_says_so(tmp_path: Path) -> None:
    empty: dict[str, Any] = json.loads(json.dumps(NIGHT))
    empty["reportData"]["report"]["fights"] = []
    repository, _ = a_repository_counting_calls(tmp_path, empty)

    with pytest.raises(ValueError, match="no boss fight"):
        repository.load_progression("abc123", None, None)
