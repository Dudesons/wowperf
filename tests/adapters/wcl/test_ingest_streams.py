# ABOUTME: Integration tests turning the four new event payloads into domain events.
# ABOUTME: Payload shapes are copied from real API responses, not imagined.

from typing import Any

import pytest

from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_damage_taken,
    build_enemy_cast_rows,
    build_enemy_deaths,
    build_healing,
    build_health_samples,
    build_interrupts,
    build_resurrections,
)
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

ABILITY_NAMES = {1238440: "Molten Scar", 1241214: "Searing Wave", 47528: "Kick"}
PLAYERS = {693: "Emberkin"}
RECAP_NAMES = {1238440: "Molten Scar", 17: "Power Word: Shield", 774: "Rejuvenation",
               61999: "Raise Ally"}


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=1000, end_ms=5000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=699, game_id=241874),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=9000,
             end_ms=20000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=702, game_id=244889),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(9, 10, 147), keystone_time_ms=1_909_000,
        keystone_bonus=1, count_reached=744, count_required=729,
        npc_counts=((241874, 5), (244889, 35)),
        players=(Player(actor_id=693, name="Emberkin", class_name="Mage", spec="Arcane",
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
    assert interrupts[0].player_name == "Emberkin"
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


def test_an_actor_id_absent_from_actor_game_ids_raises() -> None:
    events: list[dict[str, Any]] = [{"type": "death", "targetID": 999, "timestamp": 4000}]
    with pytest.raises(IngestError, match="999"):
        build_enemy_deaths(events, a_run(), {}, {241874: 5})


def test_a_pet_death_with_no_forces_entry_awards_zero_instead_of_raising() -> None:
    """Glacial Tomb (game id 246591) is a dungeon mechanic that encases a player;
    Warcraft Logs models it as a hostile pet owned by that player. It resolves
    through the actor map like any other enemy, and simply carries no forces
    entry of its own, so the honest answer is zero forces, not an IngestError.
    """
    events: list[dict[str, Any]] = [{"type": "death", "targetID": 730, "timestamp": 4000}]
    deaths = build_enemy_deaths(events, a_run(), {730: 246591}, {241874: 5, 244889: 35})
    assert deaths[0].game_id == 246591
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


def test_damage_taken_keeps_the_health_damage_and_the_absorbed_share() -> None:
    events: list[dict[str, Any]] = [
        {"type": "damage", "abilityGameID": 1238440, "targetID": 693, "amount": 9_218,
         "absorbed": 123_570, "unmitigatedAmount": 132_788, "timestamp": 2500},
    ]
    hit = build_damage_taken(events, a_run(), RECAP_NAMES)[0]
    assert (hit.amount, hit.health_damage, hit.absorbed) == (132_788, 9_218, 123_570)


def test_a_cast_carrying_hit_points_becomes_a_health_sample() -> None:
    events: list[dict[str, Any]] = [
        {"type": "cast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2000,
         "hitPoints": 61_200, "maxHitPoints": 99_000},
        {"type": "cast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2600},
        {"type": "begincast", "sourceID": 693, "abilityGameID": 100, "timestamp": 2900,
         "hitPoints": 50_000, "maxHitPoints": 99_000},
    ]
    samples = build_health_samples(events)
    # The bare cast carries no reading and must not become a zero; a begincast
    # is not a cast and is not a sample either.
    assert [(s.timestamp_ms, s.hit_points, s.max_hit_points) for s in samples] == [
        (2000, 61_200, 99_000)
    ]


def test_a_heal_and_an_absorb_become_healing_events_and_a_removebuff_does_not() -> None:
    events: list[dict[str, Any]] = [
        {"type": "heal", "abilityGameID": 774, "sourceID": 5, "targetID": 693, "amount": 9_100,
         "timestamp": 3000},
        {"type": "absorbed", "abilityGameID": 17, "extraAbilityGameID": 1238440, "sourceID": 5,
         "attackerID": 699, "targetID": 693, "amount": 12_000, "timestamp": 3100},
        {"type": "removebuff", "abilityGameID": 17, "sourceID": 5, "targetID": 693,
         "timestamp": 3200},
    ]
    healing = build_healing(events, RECAP_NAMES)
    assert [(h.ability_name, h.amount, h.absorbed, h.source_id) for h in healing] == [
        ("Rejuvenation", 9_100, False, 5),
        ("Power Word: Shield", 12_000, True, 5),
    ]
    assert all(h.actor_id == 693 for h in healing)


def test_a_resurrect_event_names_the_caster_and_the_spell() -> None:
    events: list[dict[str, Any]] = [
        {"type": "resurrect", "abilityGameID": 61999, "sourceID": 7, "targetID": 693,
         "timestamp": 9000},
        {"type": "applydebuff", "abilityGameID": 1, "sourceID": 7, "targetID": 693,
         "timestamp": 9000},
    ]
    back = build_resurrections(events, RECAP_NAMES)
    assert [(r.actor_id, r.caster_id, r.ability_name, r.timestamp_ms) for r in back] == [
        (693, 7, "Raise Ally", 9000)
    ]
