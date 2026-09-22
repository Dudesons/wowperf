# ABOUTME: Whether burst cooldowns landed on the pulls that were worth spending them on.
# ABOUTME: A cooldown held for a trivial pack is correct play, so only the big pulls ask.

from wowperf.domain.analysis.throughput import (
    analyse_cooldown_alignment,
    pulls_worth_a_cooldown,
    ready_at,
)
from wowperf.domain.events import CastEvent, Death, EnemyDeath
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import CooldownAbility, ThroughputCooldowns

BURST = CooldownAbility(ability_id=31884, name="Avenging Wrath", cooldown_seconds=120.0)
SECOND = CooldownAbility(ability_id=343721, name="Final Reckoning", cooldown_seconds=60.0)
ABILITIES = (BURST, SECOND)
COOLDOWNS = ThroughputCooldowns(entries=(("Paladin/Retribution", ABILITIES),))


def a_cast(ability_id: int, at_ms: int, actor_id: int = 11) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name="x", timestamp_ms=at_ms
    )


def a_pull(index: int, start_ms: int, end_ms: int, encounter_id: int = 0) -> Pull:
    return Pull(
        index=index, pull_id=index + 1, name=f"Pack {index}", encounter_id=encounter_id,
        start_ms=start_ms, end_ms=end_ms, killed=True, x=0, y=0,
        enemies=(EnemyNpc(actor_id=1, game_id=100),),
    )


def a_death_of(game_id: int, at_ms: int, forces: int, pull_index: int) -> EnemyDeath:
    return EnemyDeath(
        game_id=game_id, actor_id=1, timestamp_ms=at_ms, forces=forces, pull_index=pull_index
    )


def a_run(pulls: tuple[Pull, ...]) -> Run:
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=1_800_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=11, name="Bob", class_name="Paladin", spec="Retribution",
                   item_level=318),
        ),
        pulls=pulls,
    )


def test_ready_requires_the_player_to_own_the_ability() -> None:
    # Throughput cooldowns are talent-gated too. A player who never cast one all
    # run may simply not have taken it, and must not be told they held it back.
    assert ready_at((), ABILITIES, 11, 600_000, visible_from_ms=0) == ()


def test_an_owned_ability_off_cooldown_is_ready() -> None:
    casts = (a_cast(31884, 10_000),)
    ready = ready_at(casts, ABILITIES, 11, 600_000, visible_from_ms=0)
    assert [ability.name for ability in ready] == ["Avenging Wrath"]


def test_an_ability_still_on_cooldown_is_not_ready() -> None:
    casts = (a_cast(31884, 10_000), a_cast(31884, 550_000))
    assert ready_at(casts, ABILITIES, 11, 600_000, visible_from_ms=0) == ()


def test_an_ability_whose_window_predates_the_log_is_not_judged() -> None:
    # Casts are fetched per fight, so a cooldown pressed before the timer began
    # is invisible. Claiming it was ready would be the accusing direction.
    casts = (a_cast(31884, 10_000),)
    assert ready_at(casts, ABILITIES, 11, 60_000, visible_from_ms=0) == ()


def test_the_biggest_trash_pulls_are_worth_a_cooldown() -> None:
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 100_000, 160_000), a_pull(2, 200_000, 260_000))
    deaths = (
        a_death_of(100, 30_000, 4, 0),
        a_death_of(100, 130_000, 40, 1),
        a_death_of(100, 230_000, 12, 2),
    )
    worth = pulls_worth_a_cooldown(a_run(pulls), deaths, most=2)
    assert [pull.index for pull in worth] == [1, 2]


def test_every_boss_pull_is_worth_a_cooldown_however_few_forces_it_gives() -> None:
    # A boss gives no forces at all, so ranking by forces alone would drop the
    # one pull nobody would argue about.
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 100_000, 160_000, encounter_id=12825))
    deaths = (a_death_of(100, 30_000, 40, 0),)
    worth = pulls_worth_a_cooldown(a_run(pulls), deaths, most=1)
    assert {pull.index for pull in worth} == {0, 1}


def test_a_cooldown_ready_and_unpressed_on_a_big_pull_is_a_finding() -> None:
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 400_000, 460_000))
    deaths = (a_death_of(100, 430_000, 40, 1),)
    # Owned early, so it is theirs, and long off cooldown by the big pull.
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    findings = analyse_cooldown_alignment(a_run(pulls), casts, COOLDOWNS, deaths, ())
    assert len(findings) == 1
    assert findings[0].id == "throughput.alignment.Bob"
    assert findings[0].confidence is Confidence.INFERRED
    assert findings[0].seconds_lost is None
    assert "Avenging Wrath" in " ".join(findings[0].evidence)


def test_a_cooldown_pressed_during_the_pull_is_not_reported() -> None:
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 400_000, 460_000))
    deaths = (a_death_of(100, 430_000, 40, 1),)
    casts = (
        a_cast(31884, 10_000),
        a_cast(343721, 10_000),
        a_cast(31884, 410_000),
        a_cast(343721, 410_000),
    )
    assert analyse_cooldown_alignment(a_run(pulls), casts, COOLDOWNS, deaths, ()) == []


def test_a_spec_the_data_file_does_not_cover_says_nothing() -> None:
    pulls = (a_pull(0, 400_000, 460_000),)
    deaths = (a_death_of(100, 430_000, 40, 0),)
    casts = (a_cast(31884, 10_000),)
    empty = ThroughputCooldowns(entries=())
    assert analyse_cooldown_alignment(a_run(pulls), casts, empty, deaths, ()) == []


def test_the_ceiling_fires_only_on_near_total_neglect() -> None:
    from wowperf.domain.analysis.throughput import analyse_cooldown_ceiling

    # The floor is the fraction's own arithmetic: a press count is a positive
    # integer, so one press cannot clear `uses < ceiling * CEILING_USE_FRACTION`
    # until the ceiling passes 1 / 0.2 = 5. Both sides of that boundary, because
    # an emptiness assertion alone would pass even if the branch never ran.
    casts = (a_cast(31884, 10_000),)

    # 600s of pulls fits Avenging Wrath's 120s cooldown exactly 5 times.
    at_the_floor = (a_pull(0, 0, 600_000),)
    assert analyse_cooldown_ceiling(a_run(at_the_floor), casts, COOLDOWNS, ()) == []

    # 720s fits it 6 times, and the same single press is then a finding.
    above_the_floor = (a_pull(0, 0, 720_000),)
    assert analyse_cooldown_ceiling(a_run(above_the_floor), casts, COOLDOWNS, ()) != []


def test_a_cooldown_pressed_far_below_its_ceiling_is_a_finding() -> None:
    from wowperf.domain.analysis.throughput import analyse_cooldown_ceiling

    # Half an hour of pulls fits Avenging Wrath fifteen times; pressing it once
    # is the near-neglect case the fraction is set to catch.
    pulls = (a_pull(0, 0, 1_800_000),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    findings = analyse_cooldown_ceiling(a_run(pulls), casts, COOLDOWNS, ())
    assert findings, "a single press against a ceiling of fifteen should be reported"
    assert findings[0].id.startswith("throughput.ceiling.Bob")
    assert findings[0].confidence is Confidence.INFERRED


def test_an_ability_never_cast_has_no_ceiling_claim() -> None:
    # Never cast is the talent-gated case, which this analyser must not touch.
    from wowperf.domain.analysis.throughput import analyse_cooldown_ceiling

    pulls = (a_pull(0, 0, 1_800_000),)
    assert analyse_cooldown_ceiling(a_run(pulls), (), COOLDOWNS, ()) == []


def test_a_throughput_ceiling_finding_names_the_cooldown_it_judged() -> None:
    from wowperf.domain.analysis.throughput import analyse_cooldown_ceiling

    pulls = (a_pull(0, 0, 1_800_000),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    findings = analyse_cooldown_ceiling(a_run(pulls), casts, COOLDOWNS, ())
    ceiling = next(f for f in findings if f.id.startswith("throughput.ceiling."))
    assert ceiling.ability_id == BURST.ability_id
    assert ceiling.ability_name == "Avenging Wrath"
    assert ceiling.ability_name in ceiling.title


def a_player_death(at_ms: int, until_next: float | None = 20.0) -> Death:
    return Death(
        player_name="Bob", actor_id=11, timestamp_ms=at_ms, killing_blow="Shadow Bolt",
        pull_index=1, seconds_until_next_action=until_next,
    )


def test_a_pull_the_player_spent_dead_is_not_asked_about() -> None:
    # A corpse presses nothing. Reporting it would be telling someone they failed
    # to use a cooldown they could not reach, which is the worst thing this tool
    # can do — and big pulls are exactly where deaths happen.
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 400_000, 460_000))
    enemies = (a_death_of(100, 430_000, 40, 1),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    deaths = (a_player_death(405_000),)
    assert analyse_cooldown_alignment(a_run(pulls), casts, COOLDOWNS, enemies, deaths) == []


def test_a_death_whose_cost_cannot_be_measured_stops_the_claim_entirely() -> None:
    # `seconds_until_next_action` of None means the player never acted again, so
    # there is no honest dead span to subtract — and so no honest claim to make.
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 400_000, 460_000))
    enemies = (a_death_of(100, 430_000, 40, 1),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    deaths = (a_player_death(1_000_000, until_next=None),)
    assert analyse_cooldown_alignment(a_run(pulls), casts, COOLDOWNS, enemies, deaths) == []


def test_a_death_outside_the_pull_does_not_stop_the_claim() -> None:
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 400_000, 460_000))
    enemies = (a_death_of(100, 430_000, 40, 1),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    deaths = (a_player_death(20_000),)
    assert analyse_cooldown_alignment(a_run(pulls), casts, COOLDOWNS, enemies, deaths)


def test_a_pull_that_gave_up_no_forces_is_not_one_of_the_largest() -> None:
    # With no forces recorded every pull ties at zero, and a stable sort would
    # hand back the first three in log order while the finding calls them the
    # largest. Silence is the honest answer.
    pulls = (a_pull(0, 0, 60_000), a_pull(1, 100_000, 160_000))
    assert pulls_worth_a_cooldown(a_run(pulls), (), most=2) == ()


def test_the_evidence_names_each_pull_so_two_bosses_can_be_told_apart() -> None:
    # Every other analyser names a pull by its name. Calling them all "the boss"
    # produced three identical lines in a three-boss dungeon.
    pulls = (
        a_pull(0, 0, 60_000),
        a_pull(1, 400_000, 460_000, encounter_id=12825),
        a_pull(2, 500_000, 560_000, encounter_id=12826),
    )
    enemies = (a_death_of(100, 30_000, 40, 0),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    evidence = analyse_cooldown_alignment(a_run(pulls), casts, COOLDOWNS, enemies, ())[0].evidence
    named = [line for line in evidence if line.startswith("Pack ")]
    assert len(named) == len(set(named)), f"indistinguishable lines: {named}"
    assert any(line.startswith("Pack 1") for line in named)
    assert any(line.startswith("Pack 2") for line in named)
