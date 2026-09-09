# ABOUTME: Integration tests for turning event payloads into deaths and casts.
# ABOUTME: Covers pull attribution and the measured cost of a death in seconds not played.

from typing import Any

from wowperf.adapters.wcl.ingest import build_casts, build_deaths, pull_index_at
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

ABILITY_NAMES = {700: "Frostbolt", 900: "Void Bolt"}


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=1000, end_ms=5000,
             killed=True, x=0, y=0, enemies=(EnemyNpc(actor_id=1, game_id=5001),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=9000, end_ms=20000,
             killed=True, x=0, y=0, enemies=(EnemyNpc(actor_id=2, game_id=6001),)),
    )
    return Run(
        report_code="abc123", fight_id=2, dungeon_name="Murder Row", encounter_id=12825,
        keystone_level=12,
        affix_ids=(), keystone_time_ms=1_800_000, keystone_bonus=1,
        count_reached=800, count_required=800, npc_counts=(),
        players=(Player(actor_id=11, name="Frostie", class_name="Mage", spec="Frost",
                        item_level=300),),
        pulls=pulls,
    )


def test_a_timestamp_inside_a_pull_resolves_to_its_index() -> None:
    assert pull_index_at(a_run(), 3000) == 0
    assert pull_index_at(a_run(), 12000) == 1


def test_a_timestamp_between_pulls_belongs_to_no_pull() -> None:
    assert pull_index_at(a_run(), 7000) is None


def test_casts_are_named_and_attributed_to_a_pull() -> None:
    events: list[dict[str, Any]] = [
        {"type": "cast", "sourceID": 11, "abilityGameID": 700, "timestamp": 3000}
    ]
    casts = build_casts(events, a_run(), ABILITY_NAMES)
    assert (casts[0].ability_name, casts[0].pull_index) == ("Frostbolt", 0)


def test_an_unknown_ability_id_falls_back_to_its_number() -> None:
    events: list[dict[str, Any]] = [
        {"type": "cast", "sourceID": 11, "abilityGameID": 12345, "timestamp": 3000}
    ]
    assert build_casts(events, a_run(), ABILITY_NAMES)[0].ability_name == "Unknown ability 12345"


def test_a_death_records_its_killing_blow_and_pull() -> None:
    # Real death events carry no killingBlow object: the killing ability lives in
    # killingAbilityGameID, sitting alongside abilityGameID (always 0 on a death),
    # sourceID (always -1), fight, killerID, killerInstance, targetID and timestamp.
    events: list[dict[str, Any]] = [
        {
            "abilityGameID": 0,
            "fight": 2,
            "killerID": 999,
            "killingAbilityGameID": 900,
            "sourceID": -1,
            "targetID": 11,
            "timestamp": 12000,
            "type": "death",
        }
    ]
    death = build_deaths(events, a_run(), (), ABILITY_NAMES)[0]
    assert (death.player_name, death.killing_blow, death.pull_index) == (
        "Frostie",
        "Void Bolt",
        1,
    )


def test_a_death_keeps_the_id_of_the_ability_that_killed_it() -> None:
    events: list[dict[str, Any]] = [
        {"type": "death", "targetID": 11, "timestamp": 12000, "killingAbilityGameID": 900}
    ]
    death = build_deaths(events, a_run(), (), ABILITY_NAMES)[0]
    assert death.killing_blow_id == 900


def test_a_death_with_no_killing_ability_falls_back_to_unknown() -> None:
    events: list[dict[str, Any]] = [
        {
            "abilityGameID": 0,
            "fight": 2,
            "killerID": 999,
            "killingAbilityGameID": 54321,
            "sourceID": -1,
            "targetID": 11,
            "timestamp": 12000,
            "type": "death",
        }
    ]
    death = build_deaths(events, a_run(), (), ABILITY_NAMES)[0]
    assert death.killing_blow == "Unknown ability 54321"


def test_a_cast_carries_its_target_and_none_for_an_untargeted_one() -> None:
    casts = build_casts(
        [
            {"type": "cast", "sourceID": 11, "targetID": 501, "abilityGameID": 700,
             "timestamp": 11000},
            {"type": "cast", "sourceID": 11, "targetID": -1, "abilityGameID": 701,
             "timestamp": 12000},
            {"type": "cast", "sourceID": 11, "abilityGameID": 702, "timestamp": 13000},
        ],
        a_run(),
        ABILITY_NAMES,
    )
    assert [cast.target_id for cast in casts] == [501, None, None]


def test_the_cost_of_a_death_runs_until_the_player_cast_at_another_actor() -> None:
    # Respawned at the entrance, the player pops a self-only sprint at 15s and a
    # self-buff at 20s while running back, then heals an ally at 45s. Only the
    # heal is the fight resuming.
    casts = build_casts(
        [
            {"type": "cast", "sourceID": 11, "targetID": -1, "abilityGameID": 700,
             "timestamp": 15000},
            {"type": "cast", "sourceID": 11, "targetID": 11, "abilityGameID": 701,
             "timestamp": 20000},
            {"type": "cast", "sourceID": 11, "targetID": 12, "abilityGameID": 702,
             "timestamp": 45000},
        ],
        a_run(),
        ABILITY_NAMES,
    )
    events: list[dict[str, Any]] = [
        {"abilityGameID": 0, "fight": 2, "killerID": 999, "killingAbilityGameID": 900,
         "sourceID": -1, "targetID": 11, "timestamp": 12000, "type": "death"},
    ]
    death = build_deaths(events, a_run(), casts, ABILITY_NAMES)[0]
    assert death.seconds_until_next_action == 33.0


def test_a_death_followed_only_by_self_casts_has_no_measured_cost() -> None:
    casts = build_casts(
        [{"type": "cast", "sourceID": 11, "targetID": -1, "abilityGameID": 700,
          "timestamp": 15000}],
        a_run(),
        ABILITY_NAMES,
    )
    events: list[dict[str, Any]] = [
        {"abilityGameID": 0, "fight": 2, "killerID": 999, "killingAbilityGameID": 900,
         "sourceID": -1, "targetID": 11, "timestamp": 12000, "type": "death"},
    ]
    assert build_deaths(events, a_run(), casts, ABILITY_NAMES)[0].seconds_until_next_action is None


def test_a_death_with_no_later_cast_has_no_measured_cost() -> None:
    events: list[dict[str, Any]] = [
        {
            "abilityGameID": 0,
            "fight": 2,
            "killerID": 999,
            "killingAbilityGameID": 900,
            "sourceID": -1,
            "targetID": 11,
            "timestamp": 12000,
            "type": "death",
        }
    ]
    assert build_deaths(events, a_run(), (), ABILITY_NAMES)[0].seconds_until_next_action is None
