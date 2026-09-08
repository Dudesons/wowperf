# ABOUTME: Behaviour tests for fetching leaderboards, against a mock transport and a real cache.
# ABOUTME: Covers the level fallback, the bracket assertion, and that a page is fetched once.

import json
from pathlib import Path

import httpx
import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl import ranking_repository
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import BracketMismatch, WclError
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository

TOKEN = {"access_token": "t", "expires_in": 86400}


def speed_row(level: int, code: str = "aaa111") -> dict[str, object]:
    return {
        "duration": 1379452,
        "report": {"code": code, "fightID": 28, "startTime": 1},
        "deaths": 0,
        "bracketData": level,
        "affixes": [9, 10, 147],
        "team": [{"class": "Warrior", "spec": "Protection"}],
        "medal": "silver",
        "score": 435.5,
    }


def parse_row(level: int) -> dict[str, object]:
    return {
        "name": "Bríala",
        "class": "Mage",
        "spec": "Arcane",
        "duration": 1399143,
        "report": {"code": "bbb222", "fightID": 16, "startTime": 1},
        "bracketData": level,
        "affixes": [9, 10, 147],
        "medal": "silver",
        "score": 435.1,
    }


def repository(
    tmp_path: Path, by_bracket: dict[int, list[dict[str, object]]], calls: list[int]
) -> WclRankingRepository:
    """A repository whose transport answers from `by_bracket` and records each bracket asked."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        bracket = body["variables"]["bracket"]
        calls.append(bracket)
        rows = by_bracket.get(bracket, [])
        field = "characterRankings" if "className" in body["variables"] else "fightRankings"
        return httpx.Response(
            200,
            json={
                "data": {
                    "worldData": {
                        "encounter": {
                            "id": 12825,
                            "name": "Den of Nalorakk",
                            field: {"page": 1, "hasMorePages": False, "rankings": rows},
                        }
                    }
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRankingRepository(client, DiskCache(tmp_path))


def test_the_fastest_runs_come_back_as_speed_rows(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {15: [speed_row(16)]}, calls).fastest_runs(12825, 16)

    assert calls == [15]
    assert len(rows) == 1
    assert rows[0].report_code == "aaa111"
    assert rows[0].keystone_level == 16


def test_an_empty_bracket_falls_back_one_level_down_then_up(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {16: [speed_row(17)]}, calls).fastest_runs(12825, 16)

    # 15 is +16, 14 is +15, 16 is +17: our level first, then one below, then one above.
    assert calls == [15, 14, 16]
    assert rows[0].keystone_level == 17


def test_no_reference_at_any_accepted_level_returns_nothing(tmp_path: Path) -> None:
    calls: list[int] = []
    assert repository(tmp_path, {}, calls).fastest_runs(12825, 16) == ()
    assert calls == [15, 14, 16]


def test_a_bracket_that_lies_stops_the_run(tmp_path: Path) -> None:
    with pytest.raises(BracketMismatch):
        repository(tmp_path, {15: [speed_row(11)]}, []).fastest_runs(12825, 16)


def test_a_minimum_above_the_first_bracket_s_count_widens_to_the_next_one(
    tmp_path: Path,
) -> None:
    calls: list[int] = []
    rows = repository(
        tmp_path, {15: [speed_row(16, "aaa111")], 14: [speed_row(15, "bbb222")]}, calls
    ).fastest_runs(12825, 16, minimum=2)

    assert calls == [15, 14]
    assert [row.report_code for row in rows] == ["aaa111", "bbb222"]


def test_a_bracket_that_already_meets_the_minimum_does_not_widen(tmp_path: Path) -> None:
    calls: list[int] = []
    repository(
        tmp_path, {15: [speed_row(16, "aaa111"), speed_row(16, "ccc333")]}, calls
    ).fastest_runs(12825, 16, minimum=2)

    assert calls == [15]


def test_the_default_minimum_is_one_row(tmp_path: Path) -> None:
    calls: list[int] = []
    repository(tmp_path, {15: [speed_row(16)]}, calls).fastest_runs(12825, 16)

    assert calls == [15]


def test_widening_stops_once_every_level_has_been_tried_even_short_of_the_minimum(
    tmp_path: Path,
) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {15: [speed_row(16)]}, calls).fastest_runs(12825, 16, minimum=5)

    assert calls == [15, 14, 16]
    assert len(rows) == 1


def test_top_parses_also_takes_a_minimum(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(
        tmp_path, {15: [parse_row(16)], 14: [parse_row(15)]}, calls
    ).top_parses(12825, 16, "Mage", "Arcane", minimum=2)

    assert calls == [15, 14]
    assert len(rows) == 2


def test_top_parses_pass_the_class_and_spec_through(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {15: [parse_row(16)]}, calls).top_parses(
        12825, 16, "Mage", "Arcane"
    )

    assert calls == [15]
    assert rows[0].character_name == "Bríala"
    assert rows[0].spec == "Arcane"


def test_a_null_data_block_on_a_rankings_query_raises_a_named_error(tmp_path: Path) -> None:
    """{"data": null} reaches `rankings_block(payload)` as `payload.get(...)` on `None`,
    a raw `AttributeError` — not in `analyze`'s caught exception tuple — before this
    call site had any guard of its own. Guarding in `WclClient.execute` fixes it here too.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        return httpx.Response(200, json={"data": None})

    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    client = WclClient(TokenProvider("id", "secret", http), http)
    repository = WclRankingRepository(client, DiskCache(tmp_path))

    with pytest.raises(WclError, match="null 'data' block"):
        repository.fastest_runs(12825, 16)


def test_a_repeated_lookup_is_served_from_the_cache(tmp_path: Path) -> None:
    calls: list[int] = []
    subject = repository(tmp_path, {15: [speed_row(16)]}, calls)
    subject.fastest_runs(12825, 16)
    subject.fastest_runs(12825, 16)

    assert calls == [15]


def test_the_levels_tried_come_from_the_gap_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ranking_repository, "MAX_LEVEL_GAP", 2)

    assert WclRankingRepository._levels_to_try(16) == (16, 15, 17, 14, 18)


def test_one_gap_reproduces_our_level_then_one_either_side() -> None:
    assert WclRankingRepository._levels_to_try(16) == (16, 15, 17)
