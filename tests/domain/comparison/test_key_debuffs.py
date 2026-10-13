# ABOUTME: One player's debuffs over every enemy of a key: coverage and reach on each stretch.
# ABOUTME: Pins the summing over lives, adds in Overall only, the boss figure unmoved, sharing.

from tests.domain.comparison.test_boss_debuffs import (
    ALPHA,
    ALPHA_GAME,
    BETA,
    BETA_GAME,
    a_council_log,
    a_council_pull,
    on,
)
from tests.domain.comparison.test_enemy_lives import (
    BOSS_ACTOR,
    DOT,
    LASHER,
    OTHER,
    PET,
    PLAYER,
    PULLS,
    WHELP,
    a_log,
    applied,
    died,
    removed,
)
from wowperf.domain.comparison.boss_debuffs import BossDebuffs, BossTarget, BossWindow, Withheld
from wowperf.domain.comparison.key_debuffs import (
    KeyDebuffs,
    StretchCover,
    boss_debuffs,
    combined,
    key_debuffs,
)
from wowperf.domain.debuffs import DebuffEvent, DebuffLog

RUN_PLAYERS = frozenset({PLAYER, OTHER})
NOT_IN_THE_RUN = 99


def held_on(
    target: int, instance: int, start_ms: int, end_ms: int, *, source: int = PLAYER
) -> tuple[DebuffEvent, DebuffEvent]:
    """One application and its removal, by `source`, on one copy of one enemy."""
    return (
        applied(start_ms, target=target, instance=instance, source=source),
        removed(end_ms, target=target, instance=instance, source=source),
    )


def mine(log: DebuffLog, owner_id: int = PLAYER) -> KeyDebuffs:
    return key_debuffs(log, PULLS, owner_id, RUN_PLAYERS)


def test_trash_coverage_sums_debuff_time_over_summed_alive_time() -> None:
    # The first whelp lives 10-50s, opened by a teammate's application, and
    # carried ours 20-40s. The second lives 10-20s and carried ours 10-15s. The
    # lasher died undebuffed at 30s. That is 25s of 50s alive, on 2 lives of 3.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 50_000, source=OTHER),
            *held_on(WHELP, 1, 20_000, 40_000),
            *held_on(WHELP, 2, 10_000, 15_000),
            deaths=(
                died(50_000),
                died(20_000, instance=2),
                died(30_000, target=LASHER, instance=0),
            ),
        )
    )

    assert found.trash == StretchCover(
        lives=3, alive_ms=50_000, covered=((DOT, 25_000),), reached=((DOT, 2),)
    )
    assert found.trash.coverage(DOT) == 0.5
    assert found.trash.reach(DOT) == 2 / 3
    assert found.undebuffed_deaths == 1


def test_a_debuff_reaching_past_a_death_is_clipped_to_the_life() -> None:
    # Ours went on at 10s and its removal was logged at 60s, but the whelp died at
    # 40s: the life, and the debuff counted on it, end there.
    found = mine(a_log(*held_on(WHELP, 1, 10_000, 60_000), deaths=(died(40_000),)))

    assert found.trash == StretchCover(
        lives=1, alive_ms=30_000, covered=((DOT, 30_000),), reached=((DOT, 1),)
    )
    assert found.unmeasured_no_death == 0


def test_a_debuff_outliving_its_copys_death_counts_on_the_next_life_it_overlaps() -> None:
    # Ours went on whelp 1 at 10s and its removal was logged at 40s, though that
    # copy died at 20s. A teammate's application at 25s opens the copy's next
    # life, which dies at 50s. Ours is clipped to each life it overlaps: 10s on
    # the first and 15s on the second, nothing in the 5s between them. Measured
    # 2026-10-13 over 26 cached fights: 1,801 of 156,175 paired intervals outlived
    # a death of their copy, and the time past it was 0.38% of all interval time,
    # so this is pinned, not changed.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 40_000),
            *held_on(WHELP, 1, 25_000, 30_000, source=OTHER),
            deaths=(died(20_000), died(50_000)),
        )
    )

    assert found.trash == StretchCover(
        lives=2, alive_ms=35_000, covered=((DOT, 25_000),), reached=((DOT, 2),)
    )


def test_a_life_reached_by_two_separate_applications_is_reached_once() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 20_000),
            *held_on(WHELP, 1, 30_000, 40_000),
            deaths=(died(50_000),),
        )
    )

    assert found.trash == StretchCover(
        lives=1, alive_ms=40_000, covered=((DOT, 20_000),), reached=((DOT, 1),)
    )


def test_a_players_and_their_pets_copies_on_one_life_count_once() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 1, 20_000, 40_000, source=PET),
            deaths=(died(50_000),),
        )
    )

    assert found.trash.covered == ((DOT, 30_000),)
    assert found.trash.alive_ms == 40_000


def test_an_add_counts_in_overall_and_not_in_trash() -> None:
    # Trash: a whelp alive 10-50s carried ours 10-30s. Boss: ours 100-130s of
    # its 60s pull. Add: a lasher alive 120-150s inside the boss pull carried
    # ours all of it. Overall is 80s of 130s.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(BOSS_ACTOR, 0, 100_000, 130_000),
            *held_on(LASHER, 3, 120_000, 150_000),
            deaths=(died(50_000), died(150_000, target=LASHER, instance=3)),
        )
    )

    assert found.trash == StretchCover(
        lives=1, alive_ms=40_000, covered=((DOT, 20_000),), reached=((DOT, 1),)
    )
    assert found.adds == StretchCover(
        lives=1, alive_ms=30_000, covered=((DOT, 30_000),), reached=((DOT, 1),)
    )
    assert found.on_bosses == StretchCover(
        lives=1, alive_ms=60_000, covered=((DOT, 30_000),), reached=((DOT, 1),)
    )
    assert found.overall.coverage(DOT) == 80_000 / 130_000
    assert found.overall.reach(DOT) == 1.0


def test_the_boss_figure_is_the_boss_rule_whatever_died_beside_it() -> None:
    alone = mine(a_log(*held_on(BOSS_ACTOR, 0, 100_000, 130_000)))
    beside = mine(
        a_log(
            *held_on(BOSS_ACTOR, 0, 100_000, 130_000),
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(LASHER, 3, 120_000, 150_000),
            deaths=(died(50_000), died(150_000, target=LASHER, instance=3)),
        )
    )

    assert beside.bosses == alone.bosses
    assert beside.bosses.covered == ((2001, DOT, 30_000),)
    assert beside.bosses.seconds == 60.0


def test_boss_debuffs_is_the_boss_half_of_the_key() -> None:
    log = a_log(
        *held_on(BOSS_ACTOR, 0, 100_000, 130_000),
        *held_on(WHELP, 1, 10_000, 30_000),
        deaths=(died(50_000),),
    )

    assert boss_debuffs(log, PULLS, PLAYER, RUN_PLAYERS) == mine(log).bosses


def test_a_boss_is_reached_once_however_often_it_carried_the_debuff() -> None:
    found = mine(
        a_log(
            *held_on(BOSS_ACTOR, 0, 100_000, 110_000),
            *held_on(BOSS_ACTOR, 0, 120_000, 130_000),
        )
    )

    assert found.bosses.reached == ((DOT, 1),)
    assert found.bosses.targets == 1


def test_two_players_who_swap_a_debuff_on_one_trash_life_share_it() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 1, 30_000, 50_000, source=OTHER),
            deaths=(died(50_000),),
        )
    )

    assert found.shared_with == ((DOT, (OTHER,)),)


def test_copies_that_coexist_on_one_trash_life_are_each_casters_own() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 40_000),
            *held_on(WHELP, 1, 20_000, 50_000, source=OTHER),
            deaths=(died(50_000),),
        )
    )

    assert found.shared_with == ()


def test_the_overlap_of_two_players_is_summed_over_every_life_they_met_on() -> None:
    # Ours and theirs overlap for 0.6s on each of two whelps: each alone is inside
    # the tolerance, the 1.2s together is not, so the copies coexisted.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 20_600),
            *held_on(WHELP, 1, 20_000, 30_000, source=OTHER),
            *held_on(WHELP, 2, 10_000, 20_600),
            *held_on(WHELP, 2, 20_000, 30_000, source=OTHER),
            deaths=(died(40_000), died(40_000, instance=2)),
        )
    )

    assert found.shared_with == ()


def test_a_debuff_from_someone_outside_the_run_is_never_compared() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 1, 30_000, 50_000, source=NOT_IN_THE_RUN),
            deaths=(died(50_000),),
        )
    )

    assert found.shared_with == ()


def test_two_players_on_different_lives_are_never_compared() -> None:
    # Ours only ever on one whelp, theirs only on the other: the copies never met.
    # Ours on whelp 1 from 10s to 30s and theirs on whelp 2 from 30s to 50s, so
    # the two never overlap in time either. Keyed by copy there is no common
    # target to compare them on. Keyed by game id alone, theirs would land on
    # whelp 1's 10-50s life beside ours, overlap it for 0s, and read as shared.
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            *held_on(WHELP, 2, 30_000, 50_000, source=OTHER),
            deaths=(died(50_000), died(50_000, instance=2)),
        )
    )

    assert found.shared_with == ()


def test_a_debuff_seen_only_on_trash_is_named() -> None:
    found = mine(a_log(*held_on(WHELP, 1, 10_000, 30_000), deaths=(died(50_000),)))

    assert found.names == ((DOT, "Blood Plague"),)
    assert found.bosses.names == ()


def test_what_could_not_be_measured_rides_along() -> None:
    found = mine(
        a_log(
            *held_on(WHELP, 1, 10_000, 30_000),
            deaths=(died(40_000, target=LASHER, instance=0),),
        )
    )

    assert (found.unmeasured_no_death, found.undebuffed_deaths) == (1, 1)


def test_a_councils_bosses_are_each_a_life_over_their_own_span() -> None:
    # Alpha dies at 40s, Beta at 70s, in a pull that opens at 10s: 30s and 60s
    # alive, not the pull's 60s twice. Ours covered Alpha for 30s and Beta for 30s.
    found = key_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 40_000),
            *on(BETA, PLAYER, 10_000, 40_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert found.on_bosses == StretchCover(
        lives=2, alive_ms=90_000, covered=((DOT, 60_000),), reached=((DOT, 2),)
    )


def test_a_withheld_boss_pull_has_no_lives_in_the_bosses_stretch() -> None:
    withheld = BossWindow(
        encounter_id=2001,
        name="Nameless",
        start_ms=0,
        end_ms=10_000,
        targets=(BossTarget(game_id=1, start_ms=0, end_ms=10_000),),
        withheld=Withheld.NO_BOSS,
    )
    key = KeyDebuffs(bosses=BossDebuffs(windows=(withheld,)))

    assert key.on_bosses == StretchCover()
    assert key.bosses.targets == 0


def test_a_stretch_with_nothing_measured_has_no_share() -> None:
    assert StretchCover().coverage(DOT) is None
    assert StretchCover().reach(DOT) is None
    assert StretchCover(lives=1).coverage(DOT) is None
    assert StretchCover(lives=1).reach(DOT) == 0.0


def test_stretches_combine_by_summing() -> None:
    first = StretchCover(lives=2, alive_ms=10_000, covered=((DOT, 4_000),), reached=((DOT, 1),))
    second = StretchCover(
        lives=1,
        alive_ms=5_000,
        covered=((DOT, 5_000), (DOT + 1, 1_000)),
        reached=((DOT, 1), (DOT + 1, 1)),
    )

    assert combined(first, second) == StretchCover(
        lives=3,
        alive_ms=15_000,
        covered=((DOT, 9_000), (DOT + 1, 1_000)),
        reached=((DOT, 2), (DOT + 1, 1)),
    )
