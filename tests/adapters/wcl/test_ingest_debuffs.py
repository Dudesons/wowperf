# ABOUTME: Turns the raw enemy-debuff stream and the report's actors into one DebuffLog.
# ABOUTME: Row shapes are the ones measured live on 2026-10-07; absent keys read as zero or empty.

from typing import Any

from wowperf.adapters.wcl.ingest import build_debuff_log
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.debuffs import EnemyDeathRow

ACTORS: list[dict[str, Any]] = [
    {"id": 171, "gameID": 0, "type": "Player", "subType": "DeathKnight", "name": "Stonewake"},
    {"id": 172, "gameID": 27893, "type": "Pet", "subType": "Pet", "name": "Rune Weapon",
     "petOwner": 171},
    {"id": 261, "gameID": 189893, "type": "NPC", "subType": "NPC", "name": "Fixture Whelp"},
    {"id": 279, "gameID": 999, "type": "NPC", "subType": "Boss", "name": "Fixture Boss"},
    {"id": 280, "gameID": 998, "type": "NPC"},
]

EVENTS: list[dict[str, Any]] = [
    {"timestamp": 1000, "type": "applydebuff", "sourceID": 171, "targetID": 261,
     "targetInstance": 1, "abilityGameID": 55078, "fight": 9, "sourceMarker": 6},
    {"timestamp": 1500, "type": "refreshdebuff", "sourceID": 171, "targetID": 261,
     "targetInstance": 1, "abilityGameID": 55078, "fight": 9},
    {"timestamp": 1600, "type": "applydebuffstack", "sourceID": 171, "targetID": 261,
     "targetInstance": 1, "abilityGameID": 55078, "fight": 9, "stack": 2},
    {"timestamp": 2000, "type": "removedebuff", "sourceID": 172, "sourceInstance": 122,
     "targetID": 279, "abilityGameID": 55078, "fight": 9},
]


def a_log() -> Any:
    return build_debuff_log(EVENTS, ACTORS, {55078: "Blood Plague"}, 9000)


def test_only_applications_and_removals_are_kept() -> None:
    assert [(event.applied, event.timestamp_ms) for event in a_log().events] == [
        (True, 1000),
        (False, 2000),
    ]


def test_an_absent_instance_reads_as_the_first_copy() -> None:
    applied, removed = a_log().events
    assert (applied.source_instance, applied.target_instance) == (0, 1)
    assert (removed.source_instance, removed.target_instance) == (122, 0)


def test_pets_resolve_to_their_owners_and_every_actor_to_its_game_id() -> None:
    log = a_log()
    assert log.pet_owners == ((172, 171),)
    assert (261, 189893) in log.game_ids
    assert (172, 27893) in log.game_ids


def test_only_npcs_are_offered_to_the_boss_finder_and_missing_names_read_empty() -> None:
    assert a_log().npc_actors == (
        NpcActor(actor_id=261, game_id=189893, name="Fixture Whelp", sub_type="NPC"),
        NpcActor(actor_id=279, game_id=999, name="Fixture Boss", sub_type="Boss"),
        NpcActor(actor_id=280, game_id=998, name="", sub_type=""),
    )


def test_names_and_the_fight_end_ride_along() -> None:
    log = a_log()
    assert (log.ability_names, log.end_ms) == (((55078, "Blood Plague"),), 9000)


def test_enemy_deaths_ride_along_by_game_id_and_unknown_actors_are_skipped() -> None:
    log = build_debuff_log(
        EVENTS,
        ACTORS,
        {55078: "Blood Plague"},
        9000,
        death_events=[
            {"type": "death", "targetID": 279, "timestamp": 8000},
            {"type": "death", "targetID": 12345, "timestamp": 8100},
            {"type": "resurrect", "targetID": 279, "timestamp": 8200},
        ],
    )

    assert log.deaths == ((999, 8000),)


def test_no_death_events_mean_no_deaths() -> None:
    assert a_log().deaths == ()


def test_each_enemy_death_keeps_its_actor_and_its_copy() -> None:
    log = build_debuff_log(
        EVENTS,
        ACTORS,
        {55078: "Blood Plague"},
        9000,
        death_events=[
            {"type": "death", "targetID": 261, "targetInstance": 3, "timestamp": 7000},
            {"type": "death", "targetID": 279, "timestamp": 8000},
            {"type": "death", "targetID": 12345, "timestamp": 8100},
            {"type": "resurrect", "targetID": 279, "timestamp": 8200},
        ],
    )

    # Every death row, even one on an actor with no game id: the domain decides
    # what an enemy is, and an absent copy number is the actor's only copy.
    assert log.death_rows == (
        EnemyDeathRow(target_id=261, target_instance=3, timestamp_ms=7000),
        EnemyDeathRow(target_id=279, target_instance=0, timestamp_ms=8000),
        EnemyDeathRow(target_id=12345, target_instance=0, timestamp_ms=8100),
    )
    # The council rule's own reading is unchanged beside it.
    assert log.deaths == ((189893, 7000), (999, 8000))


def test_the_reports_players_ride_along() -> None:
    assert a_log().player_ids == (171,)
