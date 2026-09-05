# ABOUTME: Behaviour tests for running every analyser over one run and ranking the result.
# ABOUTME: Guards the two invariants a reader depends on: every badge set, worst finding first.

from wowperf.domain.analysis.service import analyse
from wowperf.domain.events import CastEvent, Death, EnemyCastRow, EnemyDeath
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    DefensiveAbility,
    Defensives,
    SeasonData,
)

SEASON = SeasonData(death_penalty_seconds=5.0, death_penalty_seconds_high_key=15.0,
                    high_key_threshold=12)
DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(
                    ability_id=45438, name="Ice Block", cooldown_seconds=240.0
                ),
            ),
        ),
    )
)


def a_loaded_run() -> LoadedRun:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=150_000,
             end_ms=200_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
    )
    run = Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=120, count_required=100, npc_counts=((100, 60),),
        players=(Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )
    return LoadedRun(
        run=run,
        casts=(
            CastEvent(actor_id=11, ability_id=1, ability_name="Frostbolt",
                      timestamp_ms=1_000, pull_index=0),
            # After the death at 30s, so it proves the talent is taken without
            # putting the ability on cooldown before it.
            CastEvent(actor_id=11, ability_id=45438, ability_name="Ice Block",
                      timestamp_ms=40_000, pull_index=0),
        ),
        deaths=(Death(player_name="Uglymage", actor_id=11, timestamp_ms=30_000,
                      killing_blow="Molten Scar", pull_index=0,
                      seconds_until_next_action=22.0),),
        enemy_cast_rows=(
            EnemyCastRow(source_id=1, source_instance=0, ability_id=900,
                         ability_name="Searing Wave", timestamp_ms=10_000, is_start=True,
                         pull_index=0),
            EnemyCastRow(source_id=1, source_instance=0, ability_id=900,
                         ability_name="Searing Wave", timestamp_ms=12_000, is_start=False,
                         pull_index=0),
        ),
        enemy_deaths=(EnemyDeath(game_id=100, actor_id=1, timestamp_ms=50_000, forces=120,
                                 pull_index=0),),
    )


def test_every_finding_carries_a_confidence_badge() -> None:
    findings = analyse(a_loaded_run(), SEASON, DEFENSIVES, Consumables())
    assert findings
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_findings_are_ranked_worst_first_with_untimed_ones_last() -> None:
    findings = analyse(a_loaded_run(), SEASON, DEFENSIVES, Consumables())
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)
    first_untimed = next(
        (index for index, f in enumerate(findings) if f.seconds_lost is None), len(findings)
    )
    assert all(f.seconds_lost is None for f in findings[first_untimed:])


def test_finding_ids_are_unique() -> None:
    ids = [finding.id for finding in analyse(a_loaded_run(), SEASON, DEFENSIVES, Consumables())]
    assert len(ids) == len(set(ids))


def test_every_analyser_contributes() -> None:
    ids = {
        finding.id.split(".")[0]
        for finding in analyse(a_loaded_run(), SEASON, DEFENSIVES, Consumables())
    }
    assert {"time", "deaths", "interrupts", "trash", "defensives"} <= ids


def test_an_empty_run_analyses_without_raising() -> None:
    loaded = a_loaded_run()
    bare = LoadedRun(run=loaded.run)
    findings = analyse(bare, SEASON, DEFENSIVES, Consumables())
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_a_death_with_a_defensive_available_reaches_the_ranked_list() -> None:
    # Uglymage casts Ice Block at 40s, which proves it is talented, and dies at
    # 30s with it off cooldown. The availability analyser must contribute
    # alongside the never-pressed one it sits beside.
    ids = {finding.id for finding in analyse(a_loaded_run(), SEASON, DEFENSIVES, Consumables())}
    assert "defensives.unused.Uglymage" in ids


CONSUMABLES = Consumables(
    categories=(
        ConsumableCategory(
            name="health potion", cooldown_seconds=300.0, ability_ids=(1234768,)
        ),
    )
)


def test_a_death_with_a_consumable_available_reaches_the_ranked_list() -> None:
    # Uglymage drinks nothing all run and dies, so the consumable analyser must
    # contribute alongside the defensive ones.
    findings = analyse(a_loaded_run(), SEASON, DEFENSIVES, CONSUMABLES)
    assert "consumables.unused.Uglymage" in {finding.id for finding in findings}
