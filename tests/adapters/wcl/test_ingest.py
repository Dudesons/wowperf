# ABOUTME: Integration tests for translating a Warcraft Logs report into the domain model.
# ABOUTME: Runs against a committed payload shaped like the real one; no network involved.

import json
from pathlib import Path
from typing import Any, cast

import pytest

from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_casts,
    build_encounter,
    build_run,
    select_keystone_fight,
    select_raid_fight,
)
from wowperf.adapters.wcl.queries import talents_query

FIXTURE = Path(__file__).parent / "fixtures" / "report_fights.json"


def report() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload["reportData"]["report"])


def _fight(fight_id: int, keystone_level: int | None, kill: bool | None) -> dict[str, Any]:
    """A minimal fight dict carrying only the fields select_keystone_fight reads."""
    return {"id": fight_id, "keystoneLevel": keystone_level, "kill": kill}


def test_the_keystone_fight_is_the_one_with_a_keystone_level() -> None:
    fight = select_keystone_fight(report()["fights"], None)
    assert fight["id"] == 2


def test_an_explicit_fight_id_selects_that_fight() -> None:
    fight = select_keystone_fight(report()["fights"], 2)
    assert fight["id"] == 2


def test_a_fight_id_that_is_not_a_keystone_run_is_rejected() -> None:
    with pytest.raises(IngestError, match="not a Mythic\\+ run"):
        select_keystone_fight(report()["fights"], 1)


def test_a_report_with_no_keystone_fight_is_rejected() -> None:
    with pytest.raises(IngestError, match="no Mythic\\+ run"):
        select_keystone_fight([{"id": 1, "keystoneLevel": None}], None)


def test_keystone_fights_with_none_completed_are_rejected() -> None:
    fights = [_fight(1, 10, False), _fight(2, 12, None)]
    with pytest.raises(IngestError) as exc_info:
        select_keystone_fight(fights, None)
    assert str(exc_info.value) == "This report contains no completed Mythic+ run"


def test_several_completed_keystone_fights_without_fight_id_are_rejected() -> None:
    fights = [_fight(1, 10, True), _fight(2, 12, True)]
    with pytest.raises(IngestError) as exc_info:
        select_keystone_fight(fights, None)
    assert str(exc_info.value) == "This report holds several Mythic+ runs (1, 2); pass --fight"


def test_a_fight_id_naming_an_uncompleted_keystone_fight_is_rejected() -> None:
    fights = [_fight(1, 10, False)]
    with pytest.raises(IngestError) as exc_info:
        select_keystone_fight(fights, 1)
    assert str(exc_info.value) == "Fight 1 is a Mythic+ run that was not completed"


def test_keystone_facts_are_carried_into_the_run() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.report_code == "abc123"
    assert run.fight_id == 2
    assert run.dungeon_name == "Murder Row"
    assert run.keystone_level == 12
    assert run.affix_ids == (9, 10)
    assert run.keystone_time_ms == 1_800_000
    assert run.keystone_bonus == 1
    assert (run.count_reached, run.count_required) == (820, 800)


def test_the_npc_count_map_keys_become_integers() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.npc_count_map == {5001: 4, 5002: 12}


def test_players_join_master_data_with_the_index_aligned_fight_arrays() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert [(p.name, p.class_name, p.spec, p.item_level) for p in run.players] == [
        ("Frostie", "Mage", "Frost", 301),
        ("Healbot", "Priest", "Holy", 299),
    ]


def test_pulls_keep_their_order_and_classify_bosses() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert [(p.index, p.is_boss) for p in run.pulls] == [(0, False), (1, True)]


def test_pull_enemies_carry_their_game_ids() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.pulls[0].signature == (5001, 5002)


def raid_fights() -> list[dict[str, Any]]:
    """Shaped after a real raid report: trash carries encounterID 0."""
    return [
        {"id": 1, "name": "Venomfang Juggernaut", "encounterID": 0, "kill": None,
         "keystoneLevel": None},
        {"id": 22, "name": "The Twin Fangs", "encounterID": 3421, "kill": True,
         "keystoneLevel": None},
        {"id": 28, "name": "Ula'tek", "encounterID": 3492, "kill": False,
         "keystoneLevel": None},
        {"id": 30, "name": "Ula'tek", "encounterID": 3492, "kill": False,
         "keystoneLevel": None},
    ]


def test_an_explicit_fight_id_selects_that_boss_fight() -> None:
    assert select_raid_fight(raid_fights(), 22)["id"] == 22


def test_a_wipe_is_selected_rather_than_refused() -> None:
    # The whole reason slice 2 does not reuse select_keystone_fight: a
    # progression attempt is exactly the log worth reading.
    assert select_raid_fight(raid_fights(), 30)["id"] == 30


def test_trash_is_not_a_boss_fight() -> None:
    with pytest.raises(IngestError, match="not a boss fight"):
        select_raid_fight(raid_fights(), 1)


def test_a_fight_id_absent_from_the_report_is_refused() -> None:
    with pytest.raises(IngestError, match="no fight 99"):
        select_raid_fight(raid_fights(), 99)


def test_several_boss_fights_and_no_choice_is_refused_rather_than_guessed() -> None:
    # Picking "the last one" or "the only kill" would silently analyse a fight
    # the reader did not ask for, on a report that holds a whole night.
    with pytest.raises(IngestError, match="--fight"):
        select_raid_fight(raid_fights(), None)


def test_one_boss_fight_needs_no_choice() -> None:
    only = [
        {"id": 1, "name": "Trash", "encounterID": 0, "kill": None},
        {"id": 22, "name": "The Twin Fangs", "encounterID": 3421, "kill": True},
    ]
    assert select_raid_fight(only, None)["id"] == 22


def test_a_report_with_no_boss_fight_says_so() -> None:
    with pytest.raises(IngestError, match="no boss fight"):
        select_raid_fight(
            [{"id": 1, "name": "Trash", "encounterID": 0, "kill": None,
              "keystoneLevel": None}],
            None,
        )


def test_a_keystone_is_not_a_raid_boss_fight() -> None:
    """A Mythic+ fight carries an encounterID too -- the dungeon's.

    Selecting on encounterID alone would let `raid` analyse a key as if it were
    a boss, producing a report with no route and no timer and never saying why.
    The discriminator is the absence of a keystoneLevel, not the presence of an
    encounter id.
    """
    keys = [{"id": 36, "name": "Den of Nalorakk", "encounterID": 12825, "kill": True,
             "keystoneLevel": 16}]

    with pytest.raises(IngestError, match="analyze"):
        select_raid_fight(keys, 36)
    # With no --fight given at all, the report as a whole is still a Mythic+
    # run, and the message has to say so just as plainly as the explicit-id
    # case above -- a reader who omitted --fight is not asking a harder
    # question than one who guessed wrong.
    with pytest.raises(IngestError, match="no boss fight") as excinfo:
        select_raid_fight(keys, None)
    assert "analyze" in str(excinfo.value)


@pytest.mark.parametrize("field", ["keystoneTime", "countReached", "countRequired"])
def test_a_missing_load_bearing_keystone_number_is_rejected_not_defaulted(field: str) -> None:
    payload = report()
    fight = select_keystone_fight(payload["fights"], None)
    fight[field] = None

    with pytest.raises(IngestError) as exc_info:
        build_run(payload, fight)
    assert str(exc_info.value) == f"Fight 2 is a completed Mythic+ run but carries no {field}"


def test_a_roster_member_with_no_matching_actor_is_rejected_not_dropped() -> None:
    payload = report()
    fight = select_keystone_fight(payload["fights"], None)
    fight["friendlyPlayers"] = [11, 12, 99]
    fight["friendlySpecs"] = ["Frost", "Holy", "Fury"]
    fight["friendlyItemLevels"] = [301, 299, 300]

    with pytest.raises(IngestError) as exc_info:
        build_run(payload, fight)
    assert str(exc_info.value) == (
        "Fight 2 lists player actor 99, which is absent from the report's master data"
    )


def test_a_null_spec_leaves_the_player_on_the_roster_with_no_spec() -> None:
    """Real reports carry nulls in `friendlySpecs`.

    Observed in cached responses on 2026-09-05, e.g.
    `['Retribution', None, 'Balance', ...]`. Dropping the player would shrink the
    roster and skew every per-player metric computed from it, exactly as an
    unmatched actor would; raising would refuse to analyse a run over a field
    nothing depends on. An unknown spec is reported as unknown instead.
    """
    report_payload = {
        "code": "abc123",
        "masterData": {
            "actors": [
                {"id": 693, "name": "Emberkin", "subType": "Mage"},
                {"id": 7, "name": "Stonewake", "subType": "DeathKnight"},
            ]
        },
    }
    fight = a_minimal_fight()
    fight["friendlyPlayers"] = [693, 7]
    fight["friendlySpecs"] = ["Arcane", None]
    fight["friendlyItemLevels"] = [318, 320]

    run = build_run(report_payload, fight)

    by_name = {player.name: player for player in run.players}
    assert set(by_name) == {"Emberkin", "Stonewake"}
    assert by_name["Stonewake"].spec == ""
    assert by_name["Stonewake"].class_name == "DeathKnight"
    # The neighbouring player must be unaffected: the arrays are index-aligned,
    # so a null must not shift what anyone else is read as.
    assert by_name["Emberkin"].spec == "Arcane"


def test_a_null_item_level_leaves_the_player_on_the_roster() -> None:
    # Same array, same nullability, same reasoning.
    report_payload = {
        "code": "abc123",
        "masterData": {"actors": [{"id": 693, "name": "Emberkin", "subType": "Mage"}]},
    }
    fight = a_minimal_fight()
    fight["friendlyPlayers"] = [693]
    fight["friendlySpecs"] = ["Arcane"]
    fight["friendlyItemLevels"] = [None]

    assert build_run(report_payload, fight).players[0].item_level == 0


def a_minimal_fight() -> dict[str, object]:
    return {
        "id": 36,
        "name": "Den of Nalorakk",
        "encounterID": 12825,
        "keystoneLevel": 16,
        "keystoneAffixes": [9, 10, 147],
        "keystoneTime": 1_909_000,
        "keystoneBonus": 1,
        "countReached": 744,
        "countRequired": 729,
        "npcCountMap": {},
        "friendlyPlayers": [],
        "friendlySpecs": [],
        "friendlyItemLevels": [],
        "dungeonPulls": [],
    }


def test_build_run_reads_the_encounter_and_the_owner_off_the_report() -> None:
    report = {
        "code": "abc123",
        "owner": {"name": "stonewake"},
        "masterData": {"actors": []},
    }

    run = build_run(report, a_minimal_fight())

    assert run.encounter_id == 12825
    assert run.owner_name == "stonewake"


def test_build_run_survives_a_report_with_no_owner() -> None:
    report = {"code": "abc123", "masterData": {"actors": []}}

    assert build_run(report, a_minimal_fight()).owner_name is None


def test_a_fight_with_no_encounter_id_fails_loudly() -> None:
    fight = a_minimal_fight()
    del fight["encounterID"]

    with pytest.raises(IngestError, match="encounterID"):
        build_run({"code": "abc123", "masterData": {"actors": []}}, fight)


def test_a_player_has_no_talent_string_until_one_is_fetched() -> None:
    report = {
        "code": "abc123",
        "masterData": {"actors": [{"id": 693, "name": "Emberkin", "subType": "Mage"}]},
    }
    fight = a_minimal_fight()
    fight["friendlyPlayers"] = [693]
    fight["friendlySpecs"] = ["Arcane"]
    fight["friendlyItemLevels"] = [318]

    assert build_run(report, fight).players[0].talent_import_string is None


def test_a_talent_string_reaches_the_player_it_belongs_to() -> None:
    report = {
        "code": "abc123",
        "masterData": {
            "actors": [
                {"id": 693, "name": "Emberkin", "subType": "Mage"},
                {"id": 7, "name": "Stonewake", "subType": "DeathKnight"},
            ]
        },
    }
    fight = a_minimal_fight()
    fight["friendlyPlayers"] = [693, 7]
    fight["friendlySpecs"] = ["Arcane", "Blood"]
    fight["friendlyItemLevels"] = [318, 320]

    run = build_run(report, fight, talents={693: "C4DAAAAA", 7: "CoPAAAAA"})

    by_name = {player.name: player for player in run.players}
    assert by_name["Emberkin"].talent_import_string == "C4DAAAAA"
    assert by_name["Stonewake"].talent_import_string == "CoPAAAAA"


def test_the_talents_query_asks_for_one_alias_per_actor() -> None:
    query = talents_query([693, 7])

    assert "a693: talentImportCode(actorID: 693)" in query
    assert "a7: talentImportCode(actorID: 7)" in query
    assert "allowUnlisted: true" in query


def test_the_talents_query_coerces_its_actor_ids() -> None:
    # The ids come from the API as integers; coercing makes that explicit rather
    # than interpolating whatever a caller happened to hold.
    assert "a693: talentImportCode(actorID: 693)" in talents_query(["693"])  # type: ignore[list-item]


def test_the_talents_query_is_deterministic_regardless_of_input_order() -> None:
    # The cache key is derived from the query text, so a document whose field
    # order tracked the caller's order would miss the cache on every run.
    assert talents_query([693, 7, 42]) == talents_query([42, 693, 7]) == talents_query([7, 42, 693])


def a_raid_report() -> dict[str, Any]:
    return {
        "code": "cW38jmwdnZfbHVL4",
        "owner": {"name": "Emberkin"},
        "masterData": {
            "actors": [
                {"id": 11, "name": "Emberkin", "subType": "Mage"},
                {"id": 12, "name": "Stonewake", "subType": "Warrior"},
            ]
        },
    }


def a_raid_fight(**overrides: Any) -> dict[str, Any]:
    fight: dict[str, Any] = {
        "id": 22,
        "name": "The Twin Fangs",
        "encounterID": 3421,
        "difficulty": 4,
        "size": 20,
        "kill": True,
        "fightPercentage": 0.01,
        "startTime": 1_000,
        "endTime": 375_000,
        "friendlyPlayers": [11, 12],
        "friendlySpecs": ["Arcane", "Protection"],
        "friendlyItemLevels": [700, 702],
    }
    fight.update(overrides)
    return fight


def test_an_encounter_carries_the_fight_and_the_roster() -> None:
    encounter = build_encounter(a_raid_report(), a_raid_fight(), partition=1)

    assert encounter.report_code == "cW38jmwdnZfbHVL4"
    assert encounter.fight_id == 22
    assert encounter.encounter_id == 3421
    assert encounter.boss_name == "The Twin Fangs"
    assert encounter.difficulty == 4
    assert encounter.partition == 1
    assert encounter.size == 20
    assert encounter.kill is True
    assert encounter.duration_seconds == 374.0
    assert [player.name for player in encounter.players] == ["Emberkin", "Stonewake"]


def test_a_wipe_keeps_the_percentage_it_ended_at() -> None:
    encounter = build_encounter(
        a_raid_report(), a_raid_fight(kill=False, fightPercentage=16.49), partition=1
    )
    assert encounter.kill is False
    assert encounter.fight_percentage == pytest.approx(16.49)
    assert encounter.outcome == "wiped at 16.5%"


def test_a_missing_difficulty_is_refused_rather_than_defaulted() -> None:
    # Difficulty selects the ranking sample. Defaulting it would compare a
    # Heroic pull against Mythic parses and never say so.
    with pytest.raises(IngestError, match="difficulty"):
        build_encounter(a_raid_report(), a_raid_fight(difficulty=None), partition=1)


def test_a_size_the_report_omits_falls_back_to_the_roster() -> None:
    encounter = build_encounter(a_raid_report(), a_raid_fight(size=None), partition=1)
    assert encounter.size == 2


def test_a_boss_fights_casts_carry_no_pull_index() -> None:
    """A boss fight has no pulls to be inside or outside of, unlike a keystone.

    `build_casts` (and its four siblings) locate an event by pull through
    `pull_index_at(pulls, timestamp)`. An `Encounter` carries no `pulls` tuple
    at all -- that is its whole point -- so `load_encounter` passes `()`, and
    every event it produces must read as "no pull" rather than one: an empty
    sequence can never claim a timestamp falls inside it.
    """
    casts = build_casts(
        [{"type": "cast", "sourceID": 11, "abilityGameID": 900, "timestamp": 2_000}],
        (),
        {900: "Venom Bolt"},
    )
    assert casts[0].pull_index is None
