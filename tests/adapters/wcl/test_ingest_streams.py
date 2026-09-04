# ABOUTME: Integration tests turning the four new event payloads into domain events.
# ABOUTME: Payload shapes are copied from real API responses, not imagined.

from typing import Any

from wowperf.adapters.wcl.ingest import (
    build_damage_taken,
    build_enemy_cast_rows,
    build_enemy_deaths,
    build_interrupts,
)
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

ABILITY_NAMES = {1238440: "Molten Scar", 1241214: "Searing Wave", 47528: "Kick"}
PLAYERS = {693: "Uglymage"}


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=1000, end_ms=5000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=699, game_id=241874),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=9000,
             end_ms=20000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=702, game_id=244889),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(9, 10, 147), keystone_time_ms=1_909_000,
        keystone_bonus=1, count_reached=744, count_required=729,
        npc_counts=((241874, 5), (244889, 35)),
        players=(Player(actor_id=693, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


def test_a_begincast_and_a_cast_become_two_rows_flagged_differently() -> None:
    events: list[dict[str, Any]] = [
        {"type": "begincast", "abilityGameID": 1238440, "sourceID": 699, "timestamp": 2000},
        {"type": "cast", "abilityGameID": 1238440, "sourceID": 699, "timestamp": 3500},
    ]
    rows = build_enemy_cast_rows(events, a_run(), ABILITY_NAMES)
    assert [row.is_start for row in rows] == [True, False]
    assert rows[0].ability_name == "Molten Scar"
    assert rows[0].pull_index == 0


def test_a_missing_source_instance_reads_as_zero() -> None:
    events: list[dict[str, Any]] = [
        {"type": "begincast", "abilityGameID": 1238440, "sourceID": 699, "timestamp": 2000},
        {"type": "begincast", "abilityGameID": 1238440, "sourceID": 699,
         "sourceInstance": 3, "timestamp": 2100},
    ]
    rows = build_enemy_cast_rows(events, a_run(), ABILITY_NAMES)
    assert [row.source_instance for row in rows] == [0, 3]


def test_only_interrupt_rows_become_interrupts() -> None:
    events: list[dict[str, Any]] = [
        {"type": "applydebuff", "abilityGameID": 118, "sourceID": 693, "targetID": 699,
         "timestamp": 2000},
        {"type": "interrupt", "abilityGameID": 47528, "extraAbilityGameID": 1241214,
         "sourceID": 693, "targetID": 702, "targetInstance": 1, "timestamp": 12000},
    ]
    interrupts = build_interrupts(events, a_run(), PLAYERS)
    assert len(interrupts) == 1
    assert interrupts[0].player_name == "Uglymage"
    assert interrupts[0].interrupted_ability_id == 1241214
    assert interrupts[0].target_instance == 1
    assert interrupts[0].pull_index == 1


def test_an_enemy_death_carries_the_forces_its_kill_awarded() -> None:
    events: list[dict[str, Any]] = [
        {"type": "death", "targetID": 699, "timestamp": 4000},
        {"type": "death", "targetID": 702, "timestamp": 15000},
    ]
    deaths = build_enemy_deaths(
        events, a_run(), {699: 241874, 702: 244889}, {241874: 5, 244889: 35}
    )
    assert [death.forces for death in deaths] == [5, 35]
    assert [death.pull_index for death in deaths] == [0, 1]


def test_an_enemy_with_no_forces_entry_counts_zero() -> None:
    events: list[dict[str, Any]] = [{"type": "death", "targetID": 999, "timestamp": 4000}]
    deaths = build_enemy_deaths(events, a_run(), {999: 555}, {241874: 5})
    assert deaths[0].forces == 0


def test_damage_taken_uses_the_unmitigated_amount() -> None:
    events: list[dict[str, Any]] = [
        {"type": "damage", "abilityGameID": 1238440, "targetID": 693, "amount": 0,
         "absorbed": 123570, "unmitigatedAmount": 132788, "timestamp": 2500},
    ]
    taken = build_damage_taken(events, a_run(), ABILITY_NAMES)
    assert taken[0].amount == 132788
    assert taken[0].ability_name == "Molten Scar"
    assert taken[0].actor_id == 693


def test_damage_taken_falls_back_to_amount_when_unmitigated_is_absent() -> None:
    events: list[dict[str, Any]] = [
        {"type": "damage", "abilityGameID": 1238440, "targetID": 693, "amount": 900,
         "timestamp": 2500},
    ]
    assert build_damage_taken(events, a_run(), ABILITY_NAMES)[0].amount == 900
