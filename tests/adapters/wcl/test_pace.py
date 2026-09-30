# ABOUTME: Builders for the boss-damage graph, the report's NPC actors, and one reference fight.
# ABOUTME: Also tests load_pace_sample end to end, against a MockTransport, never a real network.

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.ingest import (
    IngestError,
    RosterEntry,
    build_boss_damage,
    build_first_deaths,
    build_npc_actors,
    build_player_boss_damage,
    build_reference_fight,
)
from wowperf.adapters.wcl.pace import (
    BOSS_APPEARS_TWICE,
    BOSS_NOT_AMONG_ENEMIES,
    FIGHT_NOT_IN_REPORT,
    load_pace_sample,
)
from wowperf.adapters.wcl.queries import operation_name
from wowperf.domain.comparison.mechanics import ReferenceKillRow
from wowperf.domain.comparison.pace import (
    BOSS_IN_NO_REFERENCE,
    GRIDS_DIFFER,
    NO_BOSS,
    NO_REFERENCE_KILL,
)
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.comparison.pace_curve import BossDamage, PlayerSeries
from wowperf.domain.comparison.sample import SAMPLE_SIZE
from wowperf.domain.encounter import Encounter
from wowperf.domain.model import EnemyNpc, Player

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


def test_a_reference_fight_missing_endtime_raises_ingest_error() -> None:
    payload = {"reportData": {"report": {"fights": [
        {"id": 12, "startTime": 1000, "enemyNPCs": []},
    ]}}}
    with pytest.raises(IngestError):
        build_reference_fight(payload)


def test_a_reference_fight_carries_its_roster_by_class_and_spec() -> None:
    payload = {"reportData": {"report": {
        "fights": [{"id": 12, "startTime": 1000, "endTime": 481000,
                    "enemyNPCs": [{"id": 31, "gameID": 900}],
                    "friendlyPlayers": [5, 6, 7, 8],
                    "friendlySpecs": ["Frost", "Blood", None, "Frost"]}],
        "masterData": {"actors": [
            {"id": 5, "subType": "Mage"}, {"id": 6, "subType": "DeathKnight"},
            {"id": 7, "subType": "Priest"}, {"id": 99, "subType": "Rogue"},
        ]},
    }}}
    fight = build_reference_fight(payload)
    assert fight is not None
    # 7 has no spec and 8 no class: neither is pooled, rather than guessed at.
    assert fight.roster == (
        RosterEntry(actor_id=5, class_name="Mage", spec="Frost"),
        RosterEntry(actor_id=6, class_name="DeathKnight", spec="Blood"),
    )


def test_a_reference_fight_without_roster_fields_has_an_empty_roster() -> None:
    payload = {"reportData": {"report": {"fights": [
        {"id": 12, "startTime": 1000, "endTime": 481000, "enemyNPCs": []},
    ]}}}
    fight = build_reference_fight(payload)
    assert fight is not None and fight.roster == ()


def test_every_player_series_becomes_boss_damage_and_total_is_left_out() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": 7, "pointStart": 5000, "pointInterval": 2000.0, "data": [10.0, 20.0]},
        {"id": 8, "pointStart": 5000, "pointInterval": 2000.0, "data": [5.0]},
        {"id": "Total", "pointStart": 5000, "pointInterval": 2000.0, "data": [15.0, 20.0]},
    ]}}}}}
    assert build_player_boss_damage(payload, fight_start_ms=5000) == {
        7: BossDamage(interval_ms=2000.0, amounts=(20, 40)),
        8: BossDamage(interval_ms=2000.0, amounts=(10,)),
    }


def test_the_first_death_of_each_listed_player_is_read_in_seconds_from_the_pull() -> None:
    events = [
        {"type": "death", "targetID": 5, "timestamp": 61_000},
        {"type": "death", "targetID": 5, "timestamp": 90_000},
        {"type": "death", "targetID": 42, "timestamp": 30_000},
        {"type": "cast", "targetID": 6, "timestamp": 20_000},
    ]
    assert build_first_deaths(events, frozenset({5, 6}), fight_start_ms=1_000) == {5: 60.0}


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
        enemies=(EnemyNpc(actor_id=OUR_BOSS_ACTOR_ID, game_id=BOSS_GAME_ID),),
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
    start_ms: int,
    end_ms: int,
    enemies: list[dict[str, int]],
    *,
    friendly_players: list[int] | None = None,
    friendly_specs: list[str | None] | None = None,
    player_actors: list[dict[str, object]] | None = None,
) -> httpx.Response:
    fight: dict[str, object] = {
        "id": 1,
        "startTime": start_ms,
        "endTime": end_ms,
        "enemyNPCs": enemies,
    }
    if friendly_players is not None:
        fight["friendlyPlayers"] = friendly_players
    if friendly_specs is not None:
        fight["friendlySpecs"] = friendly_specs
    report: dict[str, object] = {"fights": [fight]}
    if player_actors is not None:
        report["masterData"] = {"actors": player_actors}
    return httpx.Response(200, json={"data": {"reportData": {"report": report}}})


def _player_graph_response(
    series: dict[int, list[float]], total: list[float], *, point_start: int, interval: float
) -> httpx.Response:
    rows = [
        {"id": actor_id, "pointStart": point_start, "pointInterval": interval, "data": data}
        for actor_id, data in series.items()
    ]
    rows.append(
        {"id": "Total", "pointStart": point_start, "pointInterval": interval, "data": total}
    )
    return httpx.Response(
        200,
        json={
            "data": {
                "reportData": {"report": {"graph": {"data": {"series": rows}}}}
            }
        },
    )


def _deaths_response(events: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "reportData": {
                    "report": {"events": {"data": events, "nextPageTimestamp": None}}
                }
            }
        },
    )


def _our_boss_actors() -> list[dict[str, object]]:
    return [
        {"id": OUR_BOSS_ACTOR_ID, "gameID": BOSS_GAME_ID, "name": FIGHT_NAME, "subType": "Boss"}
    ]


def test_a_fight_with_no_boss_among_its_enemies_asks_for_no_graph(tmp_path: Path) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        name = operation_name(json.loads(request.content)["query"]) or ""
        calls.append(name)
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        raise AssertionError(f"unexpected operation: {name}")

    encounter = _encounter(enemies=(EnemyNpc(actor_id=99, game_id=999),))
    sample, records = load_pace_sample(
        _client(handle), DiskCache(tmp_path / "own"), DiskCache(tmp_path / "ref"),
        encounter,
        (ReferenceKillRow(report_code="ref1", fight_id=1, size=20, duration_ms=300_000),),
    )

    assert sample.unavailable == NO_BOSS
    assert records == ()
    assert "BossDamageGraph" not in calls


_COUNCIL_ACTORS: list[dict[str, object]] = [
    {"id": 10, "gameID": 900, "name": "First Warden", "subType": "Boss"},
    {"id": 11, "gameID": 901, "name": "Second Warden", "subType": "Boss"},
]


def _council_encounter() -> Encounter:
    return _encounter(
        boss_name="The Wardens",
        enemies=(EnemyNpc(actor_id=10, game_id=900), EnemyNpc(actor_id=11, game_id=901)),
    )


def test_a_council_sums_its_bosses_on_both_sides(tmp_path: Path) -> None:
    """Two boss-flagged enemies, neither named after the fight: one graph each, summed.

    Our bosses deal 3 and 4 a second, so a sum reads 7 and either boss alone
    reads 3 or 4. The reference's two bosses sit at actor ids 31 and 32, not
    ours, so a lookup that reused our actor ids would ask for the wrong graphs.
    """
    graphs: list[tuple[str, int]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body.get("variables") or {}
        if name == "NpcActors":
            return _npc_actors_response(_COUNCIL_ACTORS)
        if name == "ReferenceFight":
            return _reference_fight_response(
                0, 300_000, [{"id": 31, "gameID": 900}, {"id": 32, "gameID": 901}]
            )
        if name == "BossDamageGraph":
            target = int(variables["targetId"])
            graphs.append((str(variables["code"]), target))
            per_second = {10: 3.0, 11: 4.0, 31: 30.0, 32: 40.0}[target]
            return _graph_response([per_second] * 300, point_start=0, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    row = ReferenceKillRow(report_code="ref1", fight_id=1, size=20, duration_ms=300_000)
    sample, records = load_pace_sample(
        _client(handle), DiskCache(tmp_path / "own"), DiskCache(tmp_path / "ref"),
        _council_encounter(), (row,),
    )

    assert sample.unavailable == ""
    assert sample.ours is not None and sample.ours.amounts[:2] == (7, 7)
    [reference] = sample.references
    assert reference.damage.amounts[:2] == (70, 70)
    assert sorted(graphs) == [(OUR_REPORT, 10), (OUR_REPORT, 11), ("ref1", 31), ("ref1", 32)]
    assert [one.loaded for one in records] == [True]


def test_a_reference_missing_one_of_the_councils_bosses_is_dropped(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        name = operation_name(json.loads(request.content)["query"]) or ""
        if name == "NpcActors":
            return _npc_actors_response(_COUNCIL_ACTORS)
        if name == "BossDamageGraph":
            return _graph_response([3.0] * 300, point_start=0, interval=1000.0)
        if name == "ReferenceFight":
            return _reference_fight_response(0, 300_000, [{"id": 31, "gameID": 900}])
        raise AssertionError(f"unexpected operation: {name}")

    row = ReferenceKillRow(report_code="ref1", fight_id=1, size=20, duration_ms=300_000)
    sample, records = load_pace_sample(
        _client(handle), DiskCache(tmp_path / "own"), DiskCache(tmp_path / "ref"),
        _council_encounter(), (row,),
    )

    [record] = records
    assert record.loaded is False
    assert record.reason == BOSS_NOT_AMONG_ENEMIES
    assert sample.unavailable == BOSS_IN_NO_REFERENCE


def test_our_councils_graphs_on_different_grids_withhold_with_that_reason(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        if name == "NpcActors":
            return _npc_actors_response(_COUNCIL_ACTORS)
        if name == "BossDamageGraph":
            interval = 1000.0 if int(body["variables"]["targetId"]) == 10 else 950.0
            return _graph_response([3.0] * 300, point_start=0, interval=interval)
        raise AssertionError(f"unexpected operation: {name}")

    row = ReferenceKillRow(report_code="ref1", fight_id=1, size=20, duration_ms=300_000)
    sample, records = load_pace_sample(
        _client(handle), DiskCache(tmp_path / "own"), DiskCache(tmp_path / "ref"),
        _council_encounter(), (row,),
    )

    assert sample.unavailable == GRIDS_DIFFER
    assert records == ()


def test_no_references_asks_for_no_boss_damage_graph_at_all(tmp_path: Path) -> None:
    """`load_pace_sample` must not spend our own graph's quota when there is
    nothing to compare it against: no references, no `BossDamageGraph` call,
    and `ours` stays unset since it was never fetched.
    """
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        calls.append(name)
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, ())

    assert sample.unavailable == NO_REFERENCE_KILL
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


def test_a_reference_whose_fight_is_missing_from_its_report_is_recorded(tmp_path: Path) -> None:
    references = (
        ReferenceKillRow(report_code="refnofight0000A", fight_id=20, size=20, duration_ms=200000),
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
            return httpx.Response(
                200, json={"data": {"reportData": {"report": {"fights": []}}}}
            )
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert sample.references == ()
    assert len(records) == 1
    assert records[0].loaded is False
    assert records[0].reason == FIGHT_NOT_IN_REPORT


def test_a_reference_whose_fight_lists_the_boss_under_two_actors_is_recorded(
    tmp_path: Path,
) -> None:
    references = (
        ReferenceKillRow(report_code="reftwice00000A", fight_id=20, size=20, duration_ms=200000),
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
                1000, 211000,
                [{"id": 40, "gameID": BOSS_GAME_ID}, {"id": 41, "gameID": BOSS_GAME_ID}],
            )
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert sample.references == ()
    assert len(records) == 1
    assert records[0].loaded is False
    assert records[0].reason == BOSS_APPEARS_TWICE


def test_a_reference_with_a_malformed_fight_is_recorded_while_others_load(
    tmp_path: Path,
) -> None:
    references = (
        ReferenceKillRow(report_code="refmalformed00A", fight_id=20, size=20, duration_ms=200000),
        ReferenceKillRow(report_code="refloads0000000B", fight_id=21, size=20, duration_ms=210000),
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
        if name == "ReferenceFight" and variables["code"] == "refmalformed00A":
            # `endTime` is missing: `build_reference_fight` must turn that into
            # `IngestError`, which is what proves it lands in the loader's own
            # `except` tuple instead of crashing the command.
            return httpx.Response(
                200,
                json={
                    "data": {
                        "reportData": {
                            "report": {
                                "fights": [
                                    {"id": 1, "startTime": 1000, "enemyNPCs": []}
                                ]
                            }
                        }
                    }
                },
            )
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
    assert failed[0].report_code == "refmalformed00A"


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


def _candidates(count: int) -> tuple[ReferenceKillRow, ...]:
    return tuple(
        ReferenceKillRow(
            report_code=f"refcandidate{i:03d}A", fight_id=40 + i, size=20, duration_ms=200000
        )
        for i in range(count)
    )


def _answering(
    fights_asked: list[str], *, failing: frozenset[str] = frozenset()
) -> Callable[[httpx.Request], httpx.Response]:
    """Every reference loads but the `failing` ones, which answer a 500."""

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
            fights_asked.append(variables["code"])
            if variables["code"] in failing:
                return httpx.Response(500)
            return _reference_fight_response(1000, 201000, [{"id": 40, "gameID": BOSS_GAME_ID}])
        if name == "BossDamageGraph":
            return _graph_response([5.0], point_start=1000, interval=1000.0)
        raise AssertionError(f"unexpected operation: {name}")

    return handle


def test_a_reference_that_fails_is_replaced_by_the_next_candidate(tmp_path: Path) -> None:
    """Handed more candidates than a sample holds, the loop refills a failed
    reference from the rows behind it rather than comparing against fewer."""
    candidates = _candidates(SAMPLE_SIZE + 2)
    failing = frozenset(one.report_code for one in candidates[:2])
    asked: list[str] = []

    sample, records = load_pace_sample(
        _client(_answering(asked, failing=failing)),
        DiskCache(tmp_path / "own"),
        DiskCache(tmp_path / "reference"),
        _encounter(),
        candidates,
    )

    assert len(sample.references) == SAMPLE_SIZE
    assert [one.report_code for one in records if not one.loaded] == [
        one.report_code for one in candidates[:2]
    ]
    assert asked == [one.report_code for one in candidates]


def test_no_candidate_past_a_full_sample_is_fetched(tmp_path: Path) -> None:
    """The sample stops at `SAMPLE_SIZE` loaded references: a candidate behind
    a full sample costs no request and leaves no record."""
    candidates = _candidates(SAMPLE_SIZE + 2)
    asked: list[str] = []

    sample, records = load_pace_sample(
        _client(_answering(asked)),
        DiskCache(tmp_path / "own"),
        DiskCache(tmp_path / "reference"),
        _encounter(),
        candidates,
    )

    assert len(sample.references) == SAMPLE_SIZE
    assert asked == [one.report_code for one in candidates[:SAMPLE_SIZE]]
    assert len(records) == SAMPLE_SIZE


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


def test_three_references_split_their_boss_graph_by_player_and_our_players_too(
    tmp_path: Path,
) -> None:
    references = tuple(
        ReferenceKillRow(
            report_code=f"refroster0000{i}A", fight_id=50 + i, size=20, duration_ms=210000
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
            return _player_graph_response(
                {7: [5.0], 8: [3.0]}, [8.0], point_start=0, interval=1000.0
            )
        if name == "ReferenceFight":
            return _reference_fight_response(
                1000,
                211000,
                [{"id": 100, "gameID": BOSS_GAME_ID}],
                friendly_players=[40, 41],
                friendly_specs=["Frost", "Fury"],
                player_actors=[{"id": 40, "subType": "Mage"}, {"id": 41, "subType": "Warrior"}],
            )
        if name == "BossDamageGraph":
            return _player_graph_response(
                {40: [4.0], 41: [1.0]}, [5.0], point_start=1000, interval=1000.0
            )
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter(
        players=(
            Player(actor_id=7, name="Emberkin", class_name="Mage", spec="Frost", item_level=0),
            Player(actor_id=8, name="Stonewake", class_name="Warrior", spec="Fury", item_level=0),
        )
    )

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert sample.our_players == (
        PlayerSeries(
            actor_id=7,
            class_name="Mage",
            spec="Frost",
            damage=BossDamage(interval_ms=1000.0, amounts=(5,)),
        ),
        PlayerSeries(
            actor_id=8,
            class_name="Warrior",
            spec="Fury",
            damage=BossDamage(interval_ms=1000.0, amounts=(3,)),
        ),
    )
    assert len(sample.references) == 3
    for reference in sample.references:
        assert reference.players == (
            PlayerSeries(
                actor_id=40,
                class_name="Mage",
                spec="Frost",
                damage=BossDamage(interval_ms=1000.0, amounts=(4,)),
            ),
            PlayerSeries(
                actor_id=41,
                class_name="Warrior",
                spec="Fury",
                damage=BossDamage(interval_ms=1000.0, amounts=(1,)),
            ),
        )


def test_a_reference_kills_deaths_are_read_only_when_someone_died(tmp_path: Path) -> None:
    references = (
        ReferenceKillRow(
            report_code="refnodeath0000A", fight_id=60, size=20, duration_ms=210000, deaths=0
        ),
        ReferenceKillRow(
            report_code="refonedeath000A", fight_id=61, size=20, duration_ms=210000, deaths=1
        ),
    )
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        name = operation_name(body["query"]) or ""
        variables = body["variables"]
        calls.append(name)
        if name == "NpcActors":
            return _npc_actors_response(_our_boss_actors())
        if name == "BossDamageGraph" and variables["code"] == OUR_REPORT:
            return _graph_response([10.0], point_start=0, interval=1000.0)
        if name == "ReferenceFight":
            return _reference_fight_response(
                1000,
                211000,
                [{"id": 100, "gameID": BOSS_GAME_ID}],
                friendly_players=[40, 41],
                friendly_specs=["Frost", "Fury"],
                player_actors=[{"id": 40, "subType": "Mage"}, {"id": 41, "subType": "Warrior"}],
            )
        if name == "BossDamageGraph":
            return _player_graph_response(
                {40: [4.0], 41: [1.0]}, [5.0], point_start=1000, interval=1000.0
            )
        if name == "Deaths" and variables["code"] == "refonedeath000A":
            return _deaths_response([{"type": "death", "targetID": 41, "timestamp": 61000}])
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_dir = tmp_path / "reference"
    reference_cache = DiskCache(reference_dir)
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert calls.count("Deaths") == 1
    no_death_reference = next(
        one for one in sample.references if one.duration_seconds == 210.0
        and all(player.until_seconds is None for player in one.players)
    )
    assert no_death_reference is not None
    dying_reference = next(
        one for one in sample.references
        if any(player.until_seconds is not None for player in one.players)
    )
    dying_player = next(p for p in dying_reference.players if p.actor_id == 41)
    assert dying_player.until_seconds == 60.0
    survivor = next(p for p in dying_reference.players if p.actor_id == 40)
    assert survivor.until_seconds is None
    # The Deaths request rode through the reference cache, never own_cache: the
    # own cache never expires and a reference kill's events must not linger there.
    assert len(list(reference_dir.glob("*.json"))) == 2 * 2 + 1


def test_a_roster_entry_missing_from_the_graph_is_left_out_and_an_extra_series_ignored(
    tmp_path: Path,
) -> None:
    references = (
        ReferenceKillRow(report_code="refmismatch000A", fight_id=70, size=20, duration_ms=210000),
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
            # Roster carries actors 40 and 41; the graph only carries 40 and an
            # unrelated actor 99 with no roster entry.
            return _reference_fight_response(
                1000,
                211000,
                [{"id": 100, "gameID": BOSS_GAME_ID}],
                friendly_players=[40, 41],
                friendly_specs=["Frost", "Fury"],
                player_actors=[{"id": 40, "subType": "Mage"}, {"id": 41, "subType": "Warrior"}],
            )
        if name == "BossDamageGraph":
            return _player_graph_response(
                {40: [4.0], 99: [2.0]}, [6.0], point_start=1000, interval=1000.0
            )
        raise AssertionError(f"unexpected operation: {name}")

    client = _client(handle)
    own_cache = DiskCache(tmp_path / "own")
    reference_cache = DiskCache(tmp_path / "reference")
    encounter = _encounter()

    sample, records = load_pace_sample(client, own_cache, reference_cache, encounter, references)

    assert len(sample.references) == 1
    players = sample.references[0].players
    assert [p.actor_id for p in players] == [40]
