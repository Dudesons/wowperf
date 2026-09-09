# ABOUTME: Integration test wiring client, cache and ingest into a RunRepository.
# ABOUTME: Confirms a second get is served from the cache rather than the network.

import itertools
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import IngestError
from wowperf.adapters.wcl.queries import ACTORS_QUERY, FIGHTS_QUERY
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
                    {"id": 693, "name": "Emberkin", "subType": "Mage", "server": "Hyjal"},
                ]
            },
        }
    }
}


def a_repository(
    handler: Callable[[httpx.Request], httpx.Response], tmp_path: Path
) -> WclRunRepository:
    """Wire a mock transport into one repository, cached under `tmp_path`."""
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRunRepository(client, DiskCache(tmp_path))


def operation_name(body: dict[str, Any]) -> str:
    """Pull the GraphQL operation name (e.g. "Fights") out of a request body.

    An operation takes variables or it does not, so the name ends at whichever
    of `(` or `{` follows it.
    """
    query: str = body["query"]
    return query.split("query ")[1].split("(")[0].split("{")[0].strip()


def recording_repository(
    calls: list[str],
    tmp_path: Path | None = None,
    deaths: list[dict[str, Any]] | None = None,
    affixes_payloads: list[dict[str, Any]] | None = None,
    abilities_rows: list[dict[str, Any]] | None = None,
) -> WclRunRepository:
    """Build one repository whose mock transport records every GraphQL operation name.

    The repository is backed by one cache directory that persists for its whole
    lifetime, as a real caller's would — so a `get` issued after a `load` on the
    same repository sees whatever `load` already cached, rather than starting cold.
    `tmp_path` is optional: the whole-load tests do not need a fresh directory
    injected by pytest, so one is created on demand. `deaths` replaces the single
    death row, for the tests that need two of them. `affixes_payloads` replaces
    the one well-formed affix table with a cycle of answers, for a test that
    needs the affix fetch itself to keep failing. `abilities_rows` replaces the
    empty ability dictionary, for the tests that need a real row with a `gameID`,
    `name` and `icon`.

    Each of the six event streams gets its own small, distinguishable payload —
    a real field swap in `repository.py` (e.g. assigning `interrupts` the
    `enemy_cast_rows` builder's result, or `damage_taken` the `deaths` builder's)
    must make a test built on this fixture fail.
    """
    abilities: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"abilities": abilities_rows or []}}}
    }
    # Deliberately short of the fixture's third affix, 147, so the fallback to
    # the bare id is exercised by every test built on this fixture.
    affixes: dict[str, Any] = {
        "gameData": {
            "affixes": [{"id": 9, "name": "Tyrannical"}, {"id": 10, "name": "Fortified"}]
        }
    }
    affixes_answers = (
        itertools.cycle(affixes_payloads) if affixes_payloads is not None else None
    )
    all_actors: dict[str, Any] = {
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
            [{"type": "cast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2000,
              "hitPoints": 61200, "maxHitPoints": 99000}]
        ),
        "Deaths": events_payload(
            deaths or [{"type": "death", "sourceID": -1, "targetID": 693, "timestamp": 5000}]
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
        "Healing": events_payload(
            [{"type": "heal", "abilityGameID": 774, "sourceID": 5, "targetID": 693,
              "amount": 9100, "timestamp": 4500}]
        ),
        "Resurrects": events_payload(
            [{"type": "resurrect", "abilityGameID": 61999, "sourceID": 7, "targetID": 693,
              "timestamp": 9000}]
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        name = operation_name(json.loads(request.content))
        calls.append(name)
        if name == "Fights":
            return httpx.Response(200, json={"data": FIGHTS_PAYLOAD})
        if name == "Abilities":
            return httpx.Response(200, json={"data": abilities})
        if name == "Actors":
            return httpx.Response(200, json={"data": all_actors})
        if name == "Affixes":
            answer = next(affixes_answers) if affixes_answers is not None else affixes
            return httpx.Response(200, json={"data": answer})
        if name == "Talents":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "reportData": {"report": {"fights": [{"id": 36, "a693": "C4DAAAAA"}]}}
                    }
                },
            )
        return httpx.Response(200, json={"data": event_payloads[name]})

    cache_dir = tmp_path if tmp_path is not None else Path(tempfile.mkdtemp())
    return a_repository(handler, cache_dir)


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
    assert get_calls == ["Fights", "Affixes"]

    load_calls: list[str] = []
    recording_repository(load_calls, tmp_path / "load").load("abc123", None)
    assert load_calls[0] == "Fights"
    assert set(load_calls) == {
        "Fights", "Affixes", "Abilities", "Casts", "Deaths",
        "EnemyCasts", "Interrupts", "EnemyDeaths", "DamageTaken", "Actors", "Talents",
        "Healing", "Resurrects",
    }


def test_a_get_after_a_load_costs_nothing() -> None:
    """FIGHTS_QUERY is keyed on the report code alone, so a get sees load's cache entry."""
    calls: list[str] = []
    repository = recording_repository(calls)

    repository.load("abc123", 36)
    assert sorted(set(calls)) == [
        "Abilities", "Actors", "Affixes", "Casts", "DamageTaken", "Deaths",
        "EnemyCasts", "EnemyDeaths", "Fights", "Healing", "Interrupts", "Resurrects", "Talents",
    ]

    calls.clear()
    repository.get("abc123", 36)
    assert calls == []


def test_a_loaded_run_carries_each_abilitys_icon_file_name(tmp_path: Path) -> None:
    repository = recording_repository(
        [],
        tmp_path,
        abilities_rows=[{"gameID": 48792, "name": "Icebound Fortitude", "icon": "spell_x.jpg"}],
    )
    loaded = repository.load("CODE", 36)
    assert loaded.ability_icon_map[48792] == "spell_x.jpg"


def test_an_ability_with_no_icon_contributes_no_pair(tmp_path: Path) -> None:
    repository = recording_repository(
        [],
        tmp_path,
        abilities_rows=[{"gameID": 48792, "name": "Icebound Fortitude", "icon": None}],
    )
    loaded = repository.load("CODE", 36)
    assert dict(loaded.ability_icon_map) == {}


def test_a_loaded_run_carries_every_stream() -> None:
    loaded = recording_repository([]).load("abc123", 36)
    assert loaded.run.keystone_level == 16
    assert [cast.ability_id for cast in loaded.casts] == [100]
    assert [death.actor_id for death in loaded.deaths] == [693]
    assert [row.ability_id for row in loaded.enemy_cast_rows] == [200]
    assert [interrupt.interrupted_ability_id for interrupt in loaded.interrupts] == [400]
    assert [death.actor_id for death in loaded.enemy_deaths] == [702]
    assert [taken.amount for taken in loaded.damage_taken] == [1000]


def test_load_fetches_a_healing_window_per_death_and_the_fight_s_resurrections(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)
    loaded = repository.load("abc123", None)
    assert calls.count("Healing") == 1
    assert calls.count("Resurrects") == 1
    assert [(h.ability_id, h.amount) for h in loaded.healing] == [(774, 9100)]
    assert [(r.caster_id, r.actor_id) for r in loaded.resurrections] == [(7, 693)]


def test_a_speed_reference_fetches_only_the_streams_the_speed_comparisons_read(
    tmp_path: Path,
) -> None:
    """Route, tempo and confounds read a speed member's run, deaths, enemy casts and
    interrupts (`grep -rn "member\\.|theirs\\." src/wowperf/domain/comparison/`).
    Casts, talents, damage taken, enemy deaths, healing and resurrections exist for
    our own analysers and death cards or for the parse axis; fetching any of them
    for a speed reference spends points and cache on data nothing here reads.
    """
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)

    repository.load_speed_reference("abc123", None)

    assert sorted(set(calls)) == [
        "Abilities", "Affixes", "Deaths", "EnemyCasts", "Fights", "Interrupts"
    ]


def test_a_speed_reference_carries_its_streams_and_leaves_the_rest_empty(tmp_path: Path) -> None:
    loaded, _ = recording_repository([], tmp_path).load_speed_reference("abc123", None)

    assert [death.actor_id for death in loaded.deaths] == [693]
    assert [row.ability_id for row in loaded.enemy_cast_rows] == [200]
    assert [row.interrupted_ability_id for row in loaded.interrupts] == [400]
    assert loaded.casts == ()
    assert loaded.damage_taken == ()
    assert loaded.enemy_deaths == ()
    assert loaded.healing == ()
    assert loaded.resurrections == ()


def test_a_speed_reference_reports_whether_it_was_served_entirely_from_cache(
    tmp_path: Path,
) -> None:
    repository = recording_repository([], tmp_path)

    _, first = repository.load_speed_reference("abc123", None)
    assert first is False

    _, second = repository.load_speed_reference("abc123", None)
    assert second is True


def test_a_parse_reference_fetches_only_the_streams_the_parse_comparisons_read(
    tmp_path: Path,
) -> None:
    """spells and compare_talents read a parse member's run and casts; compare_talents
    reaches `top.run.players[...].talent_import_string`, which is why talents is
    fetched even though it names no field of its own on `ParseMember` — grepping
    `member\\.|theirs\\.` alone misses it, because the read goes through `top.run`,
    not a `member.` attribute. Deaths, enemy casts and interrupts are the speed
    axis's queries and are never fetched here.
    """
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)

    repository.load_parse_reference("abc123", None)

    assert sorted(set(calls)) == ["Abilities", "Affixes", "Casts", "Fights", "Talents"]


def test_a_parse_reference_carries_its_streams_and_leaves_the_rest_empty(tmp_path: Path) -> None:
    loaded, _ = recording_repository([], tmp_path).load_parse_reference("abc123", None)

    assert [cast.ability_id for cast in loaded.casts] == [100]
    assert loaded.deaths == ()
    assert loaded.enemy_cast_rows == ()
    assert loaded.interrupts == ()
    assert loaded.damage_taken == ()
    assert loaded.enemy_deaths == ()
    assert loaded.healing == ()
    assert loaded.resurrections == ()


def test_a_parse_reference_carries_each_abilitys_icon_file_name(tmp_path: Path) -> None:
    repository = recording_repository(
        [], tmp_path,
        abilities_rows=[{"gameID": 157997, "name": "Ice Nova", "icon": "spell_x.jpg"}],
    )
    loaded, _ = repository.load_parse_reference("abc123", None)
    assert loaded.ability_icon_map[157997] == "spell_x.jpg"


def test_a_parse_reference_reports_whether_it_was_served_entirely_from_cache(
    tmp_path: Path,
) -> None:
    repository = recording_repository([], tmp_path)

    _, first = repository.load_parse_reference("abc123", None)
    assert first is False

    _, second = repository.load_parse_reference("abc123", None)
    assert second is True


def test_from_cache_reflects_a_partial_hit_before_becoming_a_full_one(tmp_path: Path) -> None:
    """Fights, Affixes and Abilities are warmed by an earlier speed load, but Casts
    and Talents are still new to a first parse load of the same report. This proves
    the aggregate catches a mixed result, not only the all-hit or all-miss case a
    flag copied from the first or the last query would also get right by accident.
    """
    repository = recording_repository([], tmp_path)
    repository.load_speed_reference("abc123", None)

    _, first_parse_load = repository.load_parse_reference("abc123", None)
    assert first_parse_load is False

    _, second_parse_load = repository.load_parse_reference("abc123", None)
    assert second_parse_load is True


def test_a_degraded_affix_fetch_counts_as_a_miss_in_the_from_cache_aggregate(
    tmp_path: Path,
) -> None:
    """A malformed affix table is never cached (see
    `test_a_malformed_affix_table_degrades_to_ids_and_caches_nothing`), so a
    reference whose affix fetch keeps failing must never report
    `from_cache=True` just because every other query it took happened to
    already be warm from an earlier load of the same report.
    """
    bad_affixes: dict[str, Any] = {"reportData": {}}
    repository = recording_repository([], tmp_path, affixes_payloads=[bad_affixes])

    repository.load_speed_reference("abc123", None)  # warms every query but Affixes
    _, from_cache = repository.load_speed_reference("abc123", None)

    assert from_cache is False


def test_load_reads_health_samples_off_the_casts(tmp_path: Path) -> None:
    loaded = recording_repository([], tmp_path).load("abc123", None)
    assert [(s.hit_points, s.max_hit_points) for s in loaded.health_samples] == [(61200, 99000)]


def test_the_healing_window_is_bounded_by_the_death_and_resurrects_span_the_fight(
    tmp_path: Path,
) -> None:
    """The healing window ends at the death; resurrections are asked for once, fight-wide."""
    from wowperf.adapters.wcl.queries import HEALING_QUERY, RESURRECTS_QUERY

    repository = recording_repository([], tmp_path)
    repository.load("abc123", None)
    healing_key = cache_key(
        HEALING_QUERY,
        {"code": "abc123", "fightId": 36, "actorId": 693,
         "startTime": 5000.0 - 10_000, "endTime": 5000.0},
    )
    resurrects_key = cache_key(
        RESURRECTS_QUERY,
        {"code": "abc123", "fightId": 36, "startTime": 0.0, "endTime": 1920000.0},
    )
    miss = {"miss": "the repository did not cache this window"}
    healing_payload, _ = repository.cache.get_or_fetch(healing_key, lambda: miss)
    resurrects_payload, _ = repository.cache.get_or_fetch(resurrects_key, lambda: miss)
    assert healing_payload != miss
    assert resurrects_payload != miss


def test_two_deaths_inside_one_run_up_share_a_single_healing_window(tmp_path: Path) -> None:
    """Overlapping run-ups are asked for once, so no heal reaches a card twice.

    A window per death would fetch the seconds the two share twice over, and
    both cards would then count every heal in them twice, health column and all.
    """
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path, deaths=two_deaths(5000, 8000))

    loaded = repository.load("abc123", None)

    assert [death.timestamp_ms for death in loaded.deaths] == [5000, 8000]
    assert calls.count("Healing") == 1
    assert [(heal.ability_id, heal.timestamp_ms) for heal in loaded.healing] == [(774, 4500)]


def test_two_deaths_further_apart_than_the_run_up_keep_their_own_windows(tmp_path: Path) -> None:
    """They share no second, so merging must not reach across the gap between them."""
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path, deaths=two_deaths(5000, 70_000))

    repository.load("abc123", None)

    assert calls.count("Healing") == 2


def two_deaths(first_ms: int, second_ms: int) -> list[dict[str, Any]]:
    """Two deaths of the fixture's one player, at the times the caller names."""
    return [
        {"type": "death", "sourceID": -1, "targetID": 693, "timestamp": first_ms},
        {"type": "death", "sourceID": -1, "targetID": 693, "timestamp": second_ms},
    ]


def test_the_casts_query_asks_for_the_casters_resources() -> None:
    from wowperf.adapters.wcl.queries import CASTS_QUERY

    assert "includeResources: true" in CASTS_QUERY


def test_a_run_carries_its_affix_names_from_game_data(tmp_path: Path) -> None:
    """An affix the game data does not list resolves to its id, never to nothing."""
    run = recording_repository([], tmp_path).get("abc123", None)

    assert run.affix_ids == (9, 10, 147)
    assert run.affix_names == ("Tyrannical", "Fortified", "147")


def test_the_affix_table_is_fetched_once_for_two_runs(tmp_path: Path) -> None:
    """It is game-wide and argument-free, so one cached response serves every run."""
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)

    repository.load("abc123", 36)
    repository.get("abc123", 36)

    assert calls.count("Affixes") == 1


def repository_with_affix_answers(
    affix_payloads: list[dict[str, Any]], tmp_path: Path
) -> tuple[WclRunRepository, list[str]]:
    """Build a repository whose Affixes query answers from `affix_payloads` in order,
    cycling once exhausted (so a single bad payload can answer every call, and a
    bad-then-good pair answers the first call badly and every later one well).
    Every other query answers as the fixture fight does, so `get` still builds a
    real run regardless of what the affix table says.
    """
    calls: list[str] = []
    answers = itertools.cycle(affix_payloads)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        name = operation_name(json.loads(request.content))
        calls.append(name)
        if name == "Fights":
            return httpx.Response(200, json={"data": FIGHTS_PAYLOAD})
        assert name == "Affixes"
        return httpx.Response(200, json={"data": next(answers)})

    return a_repository(handler, tmp_path), calls


def test_a_malformed_affix_table_degrades_to_ids_and_caches_nothing(tmp_path: Path) -> None:
    """A payload with no gameData.affixes must not be cached, so a later get retries it."""
    bad_payload: dict[str, Any] = {"reportData": {}}
    repository, calls = repository_with_affix_answers([bad_payload], tmp_path)

    run = repository.get("abc123", None)
    assert run.affix_names == ("9", "10", "147")

    calls.clear()
    repository.get("abc123", None)
    assert calls.count("Affixes") == 1


def test_a_good_affix_table_after_a_bad_one_is_read_and_cached(tmp_path: Path) -> None:
    """Nothing unusable is cached, so a later, well-formed answer is read normally."""
    bad_payload: dict[str, Any] = {"reportData": {}}
    good_payload: dict[str, Any] = {
        "gameData": {
            "affixes": [
                {"id": 9, "name": "Tyrannical"},
                {"id": 10, "name": "Fortified"},
                {"id": 147, "name": "Xal'atath's Guile"},
            ]
        }
    }
    repository, calls = repository_with_affix_answers([bad_payload, good_payload], tmp_path)

    first = repository.get("abc123", None)
    assert first.affix_names == ("9", "10", "147")

    second = repository.get("abc123", None)
    assert second.affix_names == ("Tyrannical", "Fortified", "Xal'atath's Guile")


def build_null_report_repository(tmp_path: Path, calls: list[str]) -> WclRunRepository:
    """A repository whose API answers HTTP 200 with a null report and no errors.

    This is what Warcraft Logs returns for an unlisted or unknown report code.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        calls.append(str(request.url))
        return httpx.Response(200, json={"data": {"reportData": {"report": None}}})

    return a_repository(handler, tmp_path)


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


def test_load_fetches_talents_and_get_does_not() -> None:
    calls: list[str] = []
    subject = recording_repository(calls)

    subject.load("abc123", 36)
    assert "Talents" in calls

    calls.clear()
    subject.get("abc123", 36)
    assert "Talents" not in calls


def test_actors_query_carries_no_type_filter() -> None:
    """Verify ACTORS_QUERY has no type argument on actors selection.

    A report's death stream contains pets, dungeon mechanics, and other non-NPC actors
    that Warcraft Logs models as hostile. If ACTORS_QUERY filters to `actors(type: "NPC")`
    only, those actors cannot resolve: the ingest fails with a missing actor error.
    This test catches any reintroduction of the type filter and prevents silent regression.
    """
    assert 'actors(type:' not in ACTORS_QUERY
    assert 'actors { id gameID }' in ACTORS_QUERY


def an_aura_payload() -> dict[str, object]:
    return {
        "data": {
            "reportData": {
                "report": {
                    "onSelf": {
                        "data": {
                            "auras": [
                                {
                                    "name": "Coagulopathy",
                                    "guid": 391477,
                                    "totalUptime": 5000,
                                    "totalUses": 1,
                                    "bands": [{"startTime": 0, "endTime": 5000}],
                                }
                            ],
                            "totalTime": 5000,
                        }
                    },
                    "onTargets": {"data": {"auras": [], "totalTime": 5000}},
                }
            }
        }
    }


def test_auras_come_back_for_the_actor_that_was_asked_for(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        body = json.loads(request.content)
        calls.append(operation_name(body))
        return httpx.Response(200, json=an_aura_payload())

    repository = a_repository(handler, tmp_path)
    auras = repository.auras("abc123", 36, 7)

    assert calls == ["AuraTable"]
    assert auras.actor_id == 7
    assert [a.name for a in auras.on_self] == ["Coagulopathy"]
    assert auras.on_targets == ()


def test_a_second_lookup_for_the_same_actor_is_served_from_the_cache(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        body = json.loads(request.content)
        calls.append(operation_name(body))
        return httpx.Response(200, json=an_aura_payload())

    repository = a_repository(handler, tmp_path)
    repository.auras("abc123", 36, 7)
    repository.auras("abc123", 36, 7)

    assert calls == ["AuraTable"], "the second lookup should not reach the network"


def test_a_null_data_block_raises_a_wcl_error_naming_the_code(tmp_path: Path) -> None:
    """A GraphQL response can carry a null `data` block itself, not only a null
    nested report: the aura table query hits this for a fight the API cannot
    resolve. `WclClient.execute` now raises `WclError` for a null `data` block
    itself, before this repository's `_require_report` guard is ever reached —
    so a null `data` block never reaches `_fetch` as a bare `None` to subscript."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"data": None})

    repository = a_repository(handler, tmp_path)
    with pytest.raises(WclError, match="null 'data' block.*abc123"):
        repository.auras("abc123", 36, 7)


def test_two_different_actors_do_not_collide_in_the_cache(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        body = json.loads(request.content)
        calls.append(operation_name(body))
        return httpx.Response(200, json=an_aura_payload())

    repository = a_repository(handler, tmp_path)
    repository.auras("abc123", 36, 7)
    repository.auras("abc123", 36, 8)

    assert len(calls) == 2, "a different actor is a different query"


def _quota_carrying_repository(tmp_path: Path) -> WclRunRepository:
    """A repository whose every response carries a quota block, as the live API's do."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        body = json.loads(request.content)
        # A degraded affix table caches nothing and so is refetched every time,
        # which would make the second run below look like a miss for the wrong
        # reason. This one parses.
        if operation_name(body) == "Affixes":
            payload: dict[str, Any] = {"gameData": {"affixes": [{"id": 9, "name": "Tyrannical"}]}}
        else:
            payload = dict(FIGHTS_PAYLOAD)
        payload["rateLimitData"] = {
            "limitPerHour": 3600,
            "pointsSpentThisHour": 5.0,
            "pointsResetIn": 900,
        }
        return httpx.Response(200, json={"data": payload})

    return a_repository(handler, tmp_path)


def test_the_cache_never_stores_the_quota_block(tmp_path: Path) -> None:
    """An entry lives for a day or forever, so a counter stored in one goes stale
    and would then be handed back as though it were current."""
    _quota_carrying_repository(tmp_path).get("abc123", None)

    entries = list(tmp_path.glob("*.json"))
    assert entries, "nothing was cached, so the assertion below would prove nothing"
    for entry in entries:
        assert "rateLimitData" not in entry.read_text(encoding="utf-8")


def test_a_cache_hit_records_no_reading_because_it_spent_no_points(tmp_path: Path) -> None:
    repository = _quota_carrying_repository(tmp_path)
    repository.get("abc123", None)
    after_first_run = len(repository.client.costs.costs())

    repository.get("abc123", None)

    assert len(repository.client.costs.costs()) == after_first_run
