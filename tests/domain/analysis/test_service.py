# ABOUTME: Behaviour tests for running every analyser over one run and ranking the result.
# ABOUTME: Guards the two invariants a reader depends on: every badge set, worst finding first.

from wowperf.domain.analysis.service import analyse
from wowperf.domain.events import CastEvent, Death, EnemyCastRow, EnemyDeath
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    CooldownAbility,
    DefensiveAbility,
    Defensives,
    SeasonData,
    ThroughputCooldowns,
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


def a_loaded_run_owning_its_cooldown() -> LoadedRun:
    """The shared run, plus one Arcane Surge cast so the player demonstrably has it.

    Ownership is what the throughput analysers require before saying anything: a
    talent never taken looks exactly like a button never pressed, and must not be
    held against anyone.
    """
    loaded = a_loaded_run()
    return loaded.model_copy(
        update={
            "casts": loaded.casts
            + (
                CastEvent(actor_id=11, ability_id=365350, ability_name="Arcane Surge",
                          timestamp_ms=5_000, pull_index=0),
            )
        }
    )


def test_every_finding_carries_a_confidence_badge() -> None:
    findings = analyse(
        a_loaded_run(), SEASON, DEFENSIVES, Consumables(), ThroughputCooldowns()
    )
    assert findings
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_findings_are_ranked_worst_first_with_untimed_ones_last() -> None:
    findings = analyse(
        a_loaded_run(), SEASON, DEFENSIVES, Consumables(), ThroughputCooldowns()
    )
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)
    first_untimed = next(
        (index for index, f in enumerate(findings) if f.seconds_lost is None), len(findings)
    )
    assert all(f.seconds_lost is None for f in findings[first_untimed:])


def test_finding_ids_are_unique() -> None:
    ids = [
        finding.id
        for finding in analyse(
            a_loaded_run(), SEASON, DEFENSIVES, Consumables(), ThroughputCooldowns()
        )
    ]
    assert len(ids) == len(set(ids))


def test_every_analyser_contributes() -> None:
    ids = {
        finding.id.split(".")[0]
        for finding in analyse(
            a_loaded_run_owning_its_cooldown(), SEASON, DEFENSIVES, CONSUMABLES, THROUGHPUT
        )
    }
    assert {
        "time", "deaths", "interrupts", "trash", "defensives", "consumables", "throughput",
    } <= ids


def test_an_empty_run_analyses_without_raising() -> None:
    loaded = a_loaded_run()
    bare = LoadedRun(run=loaded.run)
    findings = analyse(
        bare, SEASON, DEFENSIVES, Consumables(), ThroughputCooldowns()
    )
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_a_death_with_a_defensive_available_reaches_the_ranked_list() -> None:
    # Uglymage casts Ice Block at 40s, which proves it is talented, and dies at
    # 30s with it off cooldown. The availability analyser must contribute
    # alongside the never-pressed one it sits beside.
    ids = {
        finding.id
        for finding in analyse(
            a_loaded_run(), SEASON, DEFENSIVES, Consumables(), ThroughputCooldowns()
        )
    }
    assert "defensives.unused.Uglymage" in ids


CONSUMABLES = Consumables(
    categories=(
        ConsumableCategory(
            # Short on purpose: the fixture death is 30s in, and a category
            # whose window reaches before the run starts is deliberately not
            # claimed at all.
            name="health potion", cooldown_seconds=20.0, ability_ids=(1234768,)
        ),
    )
)


def test_a_death_with_a_consumable_available_reaches_the_ranked_list() -> None:
    # Uglymage drinks nothing all run and dies, so the consumable analyser must
    # contribute alongside the defensive ones.
    # Drunk once early, so the category is one the tool may speak about at all.
    loaded = a_loaded_run()
    drank = loaded.casts + (
        CastEvent(actor_id=11, ability_id=1234768, ability_name="Health Potion",
                  timestamp_ms=50_000, pull_index=0),
    )
    findings = analyse(
        loaded.model_copy(update={"casts": drank}),
        SEASON, DEFENSIVES, CONSUMABLES, ThroughputCooldowns(),
    )
    assert "consumables.unused.Uglymage" in {finding.id for finding in findings}


def test_the_alignment_analyser_reaches_the_ranked_list() -> None:
    # The boss pull is judgeable and Arcane Surge is owned but never pressed on
    # it, so the default half of the throughput pair must contribute.
    findings = analyse(
        a_loaded_run_owning_its_cooldown(), SEASON, DEFENSIVES, Consumables(), THROUGHPUT
    )
    assert any(f.id.startswith("throughput.alignment.") for f in findings)


THROUGHPUT = ThroughputCooldowns(
    entries=(
        (
            "Mage/Arcane",
            (CooldownAbility(ability_id=365350, name="Arcane Surge", cooldown_seconds=90.0),),
        ),
    )
)


def a_run_the_ceiling_can_judge() -> LoadedRun:
    """Long enough to have a ceiling, with the ability pressed once so it is owned.

    Both matter. A short run makes the ceiling too small to argue from, and an
    ability never cast is the talent-gated case no analyser here touches — so
    without either, the ceiling returns nothing whatever the flag says and a test
    of the flag proves nothing. An earlier version of these two tests did exactly
    that.
    """
    loaded = a_loaded_run()
    long_run = loaded.run.model_copy(
        update={"pulls": (loaded.run.pulls[0].model_copy(update={"end_ms": 1_800_000}),)}
    )
    once = loaded.casts + (
        CastEvent(actor_id=11, ability_id=365350, ability_name="Arcane Surge",
                  timestamp_ms=5_000, pull_index=0),
    )
    return loaded.model_copy(update={"run": long_run, "casts": once})


def test_the_throughput_ceiling_is_off_unless_it_is_asked_for() -> None:
    # The noisier of the two throughput claims: a keystone's route decides how
    # many packs are worth a burst cooldown, so a low count is often right. This
    # is the same run the test below gets a ceiling finding out of.
    findings = analyse(
        a_run_the_ceiling_can_judge(), SEASON, DEFENSIVES, Consumables(), THROUGHPUT
    )
    assert not any(f.id.startswith("throughput.ceiling.") for f in findings)


def test_asking_for_the_throughput_ceiling_turns_it_on() -> None:
    findings = analyse(
        a_run_the_ceiling_can_judge(),
        SEASON,
        DEFENSIVES,
        Consumables(),
        THROUGHPUT,
        include_cooldown_ceiling=True,
    )
    assert any(f.id.startswith("throughput.ceiling.") for f in findings)
