# ABOUTME: Builders for the boss-damage graph, the report's NPC actors, and one reference fight.
# ABOUTME: Also tests load_pace_sample end to end, against a MockTransport, never a real network.

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.ingest import build_boss_damage, build_npc_actors, build_reference_fight
from wowperf.adapters.wcl.pace import load_pace_sample
from wowperf.adapters.wcl.queries import operation_name
from wowperf.domain.comparison.mechanics import ReferenceKillRow
from wowperf.domain.comparison.pace import BOSS_IN_NO_REFERENCE, NO_SINGLE_BOSS
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.comparison.pace_curve import BossDamage
from wowperf.domain.encounter import Encounter

TOKEN = {"access_token": "t", "expires_in": 86400}
FIGHT_NAME = "The Test Colossus"
OUR_REPORT = "ourreport0000000A"
BOSS_GAME_ID = 900
OUR_BOSS_ACTOR_ID = 57


def test_the_total_series_becomes_boss_damage_converted_from_its_rate() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": 7, "name": "Emberkin", "pointStart": 5000, "pointInterval": 2000.0,
         "data": [10.0, 20.0]},
        {"id": "Total", "name": "Total", "pointStart": 5000, "pointInterval": 2000.0,
         "data": [15.0, 25.0, 5.0]},
    ]}}}}}
    damage = build_boss_damage(payload, fight_start_ms=5000)
    assert damage == BossDamage(interval_ms=2000.0, amounts=(30, 50, 10), lead_ms=0)


def test_a_graph_without_a_total_series_is_no_boss_damage() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": 7, "pointStart": 0, "pointInterval": 1000.0, "data": [1.0]},
    ]}}}}}
    assert build_boss_damage(payload, fight_start_ms=0) is None


def test_a_late_grid_keeps_its_lead() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": "Total", "pointStart": 6000, "pointInterval": 1000.0, "data": [1.0]},
    ]}}}}}
    damage = build_boss_damage(payload, fight_start_ms=5000)
    assert damage is not None and damage.lead_ms == 1000


def test_npc_actors_are_read_with_their_boss_flag() -> None:
    payload = {"reportData": {"report": {"masterData": {"actors": [
        {"id": 57, "gameID": 900, "name": "The Test Colossus", "subType": "Boss"},
        {"id": 60, "gameID": 903, "name": "The Test Colossus", "subType": "NPC"},
    ]}}}}
    assert build_npc_actors(payload) == (
        NpcActor(actor_id=57, game_id=900, name="The Test Colossus", sub_type="Boss"),
        NpcActor(actor_id=60, game_id=903, name="The Test Colossus", sub_type="NPC"),
    )


def test_a_reference_fight_carries_its_window_and_enemies() -> None:
    payload = {"reportData": {"report": {"fights": [
        {"id": 12, "startTime": 1000, "endTime": 481000,
         "enemyNPCs": [{"id": 31, "gameID": 900}, {"id": 32, "gameID": 901}]},
    ]}}}
    fight = build_reference_fight(payload)
    assert fight is not None
    assert (fight.start_ms, fight.end_ms) == (1000, 481000)
    assert [(one.actor_id, one.game_id) for one in fight.enemies] == [(31, 900), (32, 901)]


def test_a_missing_reference_fight_is_none() -> None:
    assert build_reference_fight({"reportData": {"report": {"fights": []}}}) is None


def _encounter(**overrides: Any) -> Encounter:
    fields: dict[str, Any] = dict(
        report_code=OUR_REPORT,
        fight_id=2,
        encounter_id=3001,
        boss_name=FIGHT_NAME,
        difficulty=4,
        partition=7,
        size=20,
        kill=False,
        start_ms=0,
        end_ms=300000,
        players=(),
    )
    fields.update(overrides)
    return Encounter(**fields)


def _client(handle: Callable[[httpx.Request], httpx.Response]) -> WclClient:
    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    return WclClient(TokenProvider("id", "secret", http), http)


def _npc_actors_response(actors: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(
        200, json={"data": {"reportData": {"report": {"masterData": {"actors": actors}}}}}
    )


def _graph_response(total: list[float], *, point_start: int, interval: float) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "reportData": {
                    "report": {
                        "graph": {
                            "data": {
                                "series": [
                                    {
                                        "id": "Total",
                                        "pointStart": point_start,
                                        "pointInterval": interval,
                                        "data": total,
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        },
    )


def _reference_fight_response(
    start_ms: int, end_ms: int, enemies: list[dict[str, int]]
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "reportData": {
                    "report": {
                        "fights": [
                            {
                                "id": 1,
                                "startTime": start_ms,
                                "endTime": end_ms,
                                "enemyNPCs": enemies,
                            }
                        ]
                    }
                }
            }
        },
    )


def _our_boss_actors() -> list[dict[str, object]]:
    return [
        {"id": OUR_BOSS_ACTOR_ID, "gameID": BOSS_GAME_ID, "name": FIGHT_NAME, "subType": "Boss"}
    ]


def test_a_council_report_finds_no_single_boss_and_asks_for_no_graph(tmp_path: Path) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        calls.append(name)
        if name == "NpcActors":
            return _npc_actors_response(
                [
                    {"id": 10, "gameID": 900, "name": "First Warden", "subType": "Boss"},
                    {"id": 11, "gameID": 901, "name": "Second Warden", "subType": "Boss"},
                ]
            )
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter(boss_name="The Wardens")

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, ())

    assert sample.unavailable == NO_SINGLE_BOSS
    assert records == ()
    assert "BossDamageGraph" not in calls


def test_three_references_load_as_pace_references_with_their_leaderboard_durations(
    tmp_path: Path,
) -> None:
    captured_graph_variables: dict[str, dict[str, object]] = {}

    references = tuple(
        ReferenceKillRow(
            report_code=f"refreport00000{i}A",
            fight_id=10 + i,
            size=20,
            duration_ms=200000 + i * 10000,
        )
        for i in range(3)
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body["variables"]
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        if name == "BossDamageGraph" and variables["code"] == OUR_REPORT:
            return _graph_response([10.0], point_start=0, interval=1000.0)
        if name == "ReferenceFight":
            return _reference_fight_response(
                1000, 211000, [{"id": 40, "gameID": BOSS_GAME_ID}]
            )
        if name == "BossDamageGraph":
            captured_graph_variables[variables["code"]] = variables
            return _graph_response([5.0], point_start=1000, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert sample.unavailable == ""
    assert len(sample.references) == 3
    assert sorted(one.duration_seconds for one in sample.references) == [200.0, 210.0, 220.0]
    assert len([one for one in records if one.loaded]) == 3
    assert all(one.axis == "pace" for one in records)

    # The reference graph was asked for that reference fight's own boss actor
    # id and window, not ours: fixture returns enemy actor id 40 and window
    # 1000..211000 for every reference.
    for row in references:
        variables = captured_graph_variables[row.report_code]
        assert variables["targetId"] == 40
        assert (variables["startTime"], variables["endTime"]) == (1000.0, 211000.0)


def test_one_reference_lacking_the_boss_and_two_that_load(tmp_path: Path) -> None:
    references = (
        ReferenceKillRow(report_code="refnoboss00000A", fight_id=20, size=20, duration_ms=200000),
        ReferenceKillRow(report_code="refloadsA0000A1", fight_id=21, size=20, duration_ms=210000),
        ReferenceKillRow(report_code="refloadsA0000A2", fight_id=22, size=20, duration_ms=220000),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body["variables"]
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        if name == "BossDamageGraph" and variables["code"] == OUR_REPORT:
            return _graph_response([10.0], point_start=0, interval=1000.0)
        if name == "ReferenceFight" and variables["code"] == "refnoboss00000A":
            return _reference_fight_response(1000, 201000, [{"id": 40, "gameID": 999}])
        if name == "ReferenceFight":
            return _reference_fight_response(1000, 211000, [{"id": 40, "gameID": BOSS_GAME_ID}])
        if name == "BossDamageGraph":
            return _graph_response([5.0], point_start=1000, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert len(sample.references) == 2
    absent = [one for one in records if not one.loaded]
    assert len(absent) == 1
    assert "not among" in absent[0].reason


def test_every_reference_lacking_the_boss_withholds_with_its_own_reason(tmp_path: Path) -> None:
    references = (
        ReferenceKillRow(report_code="refnoboss00000A", fight_id=20, size=20, duration_ms=200000),
        ReferenceKillRow(report_code="refnoboss00000B", fight_id=21, size=20, duration_ms=210000),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body["variables"]
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        if name == "BossDamageGraph" and variables["code"] == OUR_REPORT:
            return _graph_response([10.0], point_start=0, interval=1000.0)
        if name == "ReferenceFight":
            return _reference_fight_response(1000, 201000, [{"id": 40, "gameID": 999}])
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert sample.unavailable == BOSS_IN_NO_REFERENCE
    assert len(records) == 2
    assert all(not one.loaded for one in records)


def test_a_reference_answering_with_an_http_error_is_recorded_not_raised(tmp_path: Path) -> None:
    references = (
        ReferenceKillRow(report_code="reffails000000A", fight_id=30, size=20, duration_ms=200000),
        ReferenceKillRow(report_code="refloads0000000B", fight_id=31, size=20, duration_ms=210000),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body["variables"]
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        if name == "BossDamageGraph" and variables["code"] == OUR_REPORT:
            return _graph_response([10.0], point_start=0, interval=1000.0)
        if name == "ReferenceFight" and variables["code"] == "reffails000000A":
            return httpx.Response(500)
        if name == "ReferenceFight":
            return _reference_fight_response(1000, 211000, [{"id": 40, "gameID": BOSS_GAME_ID}])
        if name == "BossDamageGraph":
            return _graph_response([5.0], point_start=1000, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert len(sample.references) == 1
    failed = [one for one in records if not one.loaded]
    assert len(failed) == 1
    assert failed[0].report_code == "reffails000000A"


def test_our_responses_use_the_own_cache_and_references_the_reference_cache(
    tmp_path: Path,
) -> None:
    # Two references, not one: two own-cache calls against four reference-cache
    # calls (a fight and a graph apiece) is a count no cache swap could pass by
    # coincidence, unlike a one-reference fixture where both sides read two.
    references = (
        ReferenceKillRow(report_code="refloads0000000C", fight_id=40, size=20, duration_ms=200000),
        ReferenceKillRow(report_code="refloads0000000D", fight_id=41, size=20, duration_ms=210000),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body["variables"]
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        if name == "BossDamageGraph" and variables["code"] == OUR_REPORT:
            return _graph_response([10.0], point_start=0, interval=1000.0)
        if name == "ReferenceFight":
            return _reference_fight_response(1000, 211000, [{"id": 40, "gameID": BOSS_GAME_ID}])
        if name == "BossDamageGraph":
            return _graph_response([5.0], point_start=1000, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_dir = tmp_path / "own"
    reference_dir = tmp_path / "reference"
    own_cache = DiskCache(own_dir)
    reference_cache = DiskCache(reference_dir)
    encounter = _encounter()

    load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert len(list(own_dir.glob("*.json"))) == 2
    assert len(list(reference_dir.glob("*.json"))) == 4
