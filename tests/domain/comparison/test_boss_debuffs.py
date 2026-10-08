# ABOUTME: One player's debuffs on each boss: the boss alone, clipped to its pull, pets included.
# ABOUTME: Pins a council measured over its bosses' lives, a missing boss withheld, shares per boss.

import pytest

from wowperf.domain.comparison.boss_debuffs import (
    SHARED_OVERLAP_TOLERANCE_S,
    BossTarget,
    BossWindow,
    Withheld,
    boss_debuffs,
    boss_windows_of,
    encounter_share,
)
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.debuffs import DebuffEvent, DebuffLog
from wowperf.domain.model import EnemyNpc, Pull

BOSS_NAME = "The Test Colossus"
BOSS_ACTOR, BOSS_GAME = 50, 5000
ADD_ACTOR, ADD_GAME = 51, 5100
PLAYER, PET, OTHER, THIRD_PLAYER = 7, 8, 9, 10
RUN_PLAYERS = frozenset({PLAYER, OTHER, THIRD_PLAYER})
"""The players of our run, as the caller names them: a pet and an enemy are never among them."""
DOT = 55078
GAME_IDS = {BOSS_ACTOR: BOSS_GAME, ADD_ACTOR: ADD_GAME}


def a_pull(
    index: int,
    start_ms: int,
    end_ms: int,
    *,
    encounter_id: int = 0,
    name: str = "Pack",
    enemies: tuple[int, ...] = (BOSS_ACTOR, ADD_ACTOR),
) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name=name,
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=tuple(
            EnemyNpc(actor_id=actor, game_id=GAME_IDS.get(actor, actor * 100))
            for actor in enemies
        ),
    )


TRASH_PULL = a_pull(0, 0, 8_000)
BOSS_PULL = a_pull(1, 10_000, 70_000, encounter_id=2001, name=BOSS_NAME)
ACTORS = (
    NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name=BOSS_NAME, sub_type="Boss"),
    NpcActor(actor_id=ADD_ACTOR, game_id=ADD_GAME, name="Fixture Add", sub_type="NPC"),
)


def an_event(
    applied: bool, at: int, *, source: int = PLAYER, target: int = BOSS_ACTOR
) -> DebuffEvent:
    return DebuffEvent(
        applied=applied, timestamp_ms=at, source_id=source, target_id=target, ability_id=DOT
    )


def a_log(
    *events: DebuffEvent,
    actors: tuple[NpcActor, ...] = ACTORS,
    deaths: tuple[tuple[int, int], ...] = (),
) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=tuple(GAME_IDS.items()),
        npc_actors=actors,
        ability_names=((DOT, "Blood Plague"),),
        deaths=deaths,
        end_ms=80_000,
    )


def test_a_single_boss_is_measured_over_its_own_pull_and_trash_is_not() -> None:
    assert boss_windows_of((TRASH_PULL, BOSS_PULL), ACTORS) == (
        BossWindow(
            encounter_id=2001,
            name=BOSS_NAME,
            start_ms=10_000,
            end_ms=70_000,
            targets=(BossTarget(game_id=BOSS_GAME, start_ms=10_000, end_ms=70_000),),
        ),
    )


def test_only_the_debuff_on_the_boss_counts() -> None:
    mine = boss_debuffs(
        a_log(
            an_event(True, 20_000),
            an_event(False, 50_000),
            an_event(True, 10_000, target=ADD_ACTOR),
            an_event(False, 70_000, target=ADD_ACTOR),
        ),
        (TRASH_PULL, BOSS_PULL),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered == ((2001, DOT, 30_000),)
    assert mine.names == ((DOT, "Blood Plague"),)
    assert mine.seconds == 60.0


def test_an_interval_reaching_past_the_pull_is_clipped_to_it() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 5_000), an_event(False, 75_000)), (BOSS_PULL,), PLAYER, RUN_PLAYERS
    )

    assert mine.covered == ((2001, DOT, 60_000),)


def test_a_pet_counts_for_its_owner_and_an_overlap_counts_once() -> None:
    mine = boss_debuffs(
        a_log(
            an_event(True, 20_000),
            an_event(False, 50_000),
            an_event(True, 40_000, source=PET),
            an_event(False, 60_000, source=PET),
        ),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered_seconds(DOT) == 40.0


def test_another_players_debuff_is_not_this_players() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 20_000, source=OTHER), an_event(False, 50_000, source=OTHER)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered == ()


def test_a_council_is_measured_over_its_bosses_lives() -> None:
    council = (
        NpcActor(
            actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name="Blood of the Twins", sub_type="Boss"
        ),
        NpcActor(
            actor_id=ADD_ACTOR, game_id=ADD_GAME, name="Breath of the Twins", sub_type="Boss"
        ),
    )
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name="The Twin Council")

    mine = boss_debuffs(
        a_log(
            an_event(True, 20_000),
            an_event(False, 50_000),
            actors=council,
            deaths=((BOSS_GAME, 40_000), (ADD_GAME, 70_000)),
        ),
        (pull,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert [window.withheld for window in mine.windows] == [None]
    assert mine.seconds == 30.0 + 60.0
    # The 20-50s on the first boss is clipped to that boss's death at 40s.
    assert mine.covered == ((2001, DOT, 20_000),)


def test_a_boss_pull_with_no_boss_flagged_enemy_is_withheld() -> None:
    # The pull is named for no enemy, because an unflagged enemy named after the
    # pull is the boss (the name-first rule).
    unflagged = tuple(actor.model_copy(update={"sub_type": "NPC"}) for actor in ACTORS)
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name="The Fixture Hall")

    assert [window.withheld for window in boss_windows_of((pull,), unflagged)] == [
        Withheld.NO_BOSS
    ]


def test_a_boss_whose_name_only_begins_the_pulls_is_still_the_boss() -> None:
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name="Vashnik the Malignant")
    actors = (NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name="Vashnik", sub_type="Boss"),)

    assert [boss_ids(window) for window in boss_windows_of((pull,), actors)] == [(BOSS_GAME,)]


def test_the_pairing_tally_rides_along() -> None:
    mine = boss_debuffs(a_log(an_event(False, 30_000)), (BOSS_PULL,), PLAYER, RUN_PLAYERS)

    assert mine.tally.orphan_removes == 1


def test_a_share_is_read_per_boss() -> None:
    second = a_pull(2, 100_000, 200_000, encounter_id=2002, name="The Twin Council")
    council = (
        *ACTORS,
        NpcActor(actor_id=60, game_id=6000, name="Blood of the Twins", sub_type="Boss"),
        NpcActor(actor_id=61, game_id=6100, name="Breath of the Twins", sub_type="Boss"),
    )
    second = second.model_copy(
        update={
            "enemies": (
                EnemyNpc(actor_id=60, game_id=6000),
                EnemyNpc(actor_id=61, game_id=6100),
            )
        }
    )
    mine = boss_debuffs(
        a_log(an_event(True, 10_000), an_event(False, 40_000), actors=council),
        (BOSS_PULL, second),
        PLAYER,
        RUN_PLAYERS,
    )

    assert encounter_share(mine, DOT, 2001) == 0.5
    # Nothing was on the council's bosses, and they were measured.
    assert encounter_share(mine, DOT, 2002) == 0.0
    assert encounter_share(mine, DOT, 9999) is None


def test_a_boss_fought_twice_is_summed_over_both_measured_pulls() -> None:
    # A wipe, then the kill: two windows, one encounter. The shares differ, so a
    # mean of the two, or either one alone, cannot reach the summed figure:
    # 30s of 60s, then 10s of 40s, is 40s of 100s.
    wipe = BOSS_PULL
    kill = a_pull(2, 100_000, 140_000, encounter_id=2001, name=BOSS_NAME)
    mine = boss_debuffs(
        a_log(
            an_event(True, 20_000),
            an_event(False, 50_000),
            an_event(True, 100_000),
            an_event(False, 110_000),
        ),
        (wipe, kill),
        PLAYER,
        RUN_PLAYERS,
    )

    assert [window.encounter_id for window in mine.windows] == [2001, 2001]
    assert mine.seconds == 100.0
    assert encounter_share(mine, DOT, 2001) == 0.4


FIRST, SECOND, THIRD = 60, 61, 62
FIRST_GAME, SECOND_GAME = 6000, 6100


def the_window_of(name: str, *actors: NpcActor) -> BossWindow:
    """The one window of a boss pull named `name`, holding exactly these enemies."""
    pull = a_pull(
        1,
        10_000,
        70_000,
        encounter_id=2001,
        name=name,
        enemies=tuple(actor.actor_id for actor in actors),
    )
    [window] = boss_windows_of((pull,), actors)
    return window


def an_enemy(actor_id: int, game_id: int, name: str, sub_type: str = "NPC") -> NpcActor:
    return NpcActor(actor_id=actor_id, game_id=game_id, name=name, sub_type=sub_type)


def boss_ids(window: BossWindow) -> tuple[int, ...]:
    """The game ids a window is measured on, in order."""
    return tuple(target.game_id for target in window.targets)


def test_an_unflagged_enemy_named_after_the_pull_is_its_boss() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_a_name_match_beats_a_boss_flagged_add() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME),
        an_enemy(SECOND, SECOND_GAME, "Fixture Add", "Boss"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_an_unflagged_pair_named_for_both_is_a_council() -> None:
    window = the_window_of(
        "Alpha Fixture and Beta Fixture",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture"),
        an_enemy(SECOND, SECOND_GAME, "Beta Fixture"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME, SECOND_GAME), None)


def test_an_unflagged_enemy_whose_name_only_begins_the_pulls_is_its_boss() -> None:
    # The flag is absent, so only the opening-words half of the name step can
    # find this boss: the `find_bosses` fallback has no candidate to read.
    window = the_window_of(
        "Alpha Fixture the Tester",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_a_flagged_pair_whose_first_name_begins_the_pulls_is_a_council_not_that_boss() -> None:
    window = the_window_of(
        "Alpha Fixture and Beta Fixture",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(SECOND, SECOND_GAME, "Beta Fixture", "Boss"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME, SECOND_GAME), None)


def test_a_pull_named_for_two_bosses_with_one_in_it_measures_that_one() -> None:
    window = the_window_of(
        "Alpha Fixture and Beta Fixture",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_one_boss_logged_under_two_actor_ids_is_one_boss() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME, "Boss"),
        an_enemy(THIRD, FIRST_GAME, BOSS_NAME, "Boss"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_one_flagged_boss_logged_under_two_actor_ids_is_one_boss_when_no_name_matches() -> None:
    window = the_window_of(
        "The Fixture Hall",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(THIRD, FIRST_GAME, "Alpha Fixture", "Boss"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_a_pull_named_for_no_enemy_reads_its_one_flagged_enemy() -> None:
    window = the_window_of(
        "The Fixture Hall",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_a_pull_named_for_no_enemy_reads_two_flagged_enemies_as_a_council() -> None:
    window = the_window_of(
        "Council o' Fixtures",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(SECOND, SECOND_GAME, "Beta Fixture", "Boss"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME, SECOND_GAME), None)


def test_a_pull_named_for_no_enemy_and_holding_no_flagged_one_has_no_boss() -> None:
    window = the_window_of(
        "The Fixture Hall",
        an_enemy(FIRST, FIRST_GAME, "Fixture Add"),
        an_enemy(SECOND, SECOND_GAME, "Another Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((), Withheld.NO_BOSS)


def test_a_comma_in_the_pulls_name_is_a_title_not_a_second_boss() -> None:
    window = the_window_of(
        "Alpha Fixture, The Tester",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture, The Tester"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (boss_ids(window), window.withheld) == ((FIRST_GAME,), None)


def test_a_part_matched_by_two_game_ids_is_no_boss_and_does_not_fall_back_to_a_flag() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME),
        an_enemy(SECOND, SECOND_GAME, BOSS_NAME),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add", "Boss"),
    )

    assert (boss_ids(window), window.withheld) == ((), Withheld.NO_BOSS)


def held(source: int, start_ms: int, end_ms: int) -> tuple[DebuffEvent, DebuffEvent]:
    """One application and its removal, by `source`, on the boss."""
    return an_event(True, start_ms, source=source), an_event(False, end_ms, source=source)


def test_a_debuff_one_teammates_application_replaces_is_shared_with_them() -> None:
    # The two never overlap: each application took the debuff over from the
    # other's, which is the shape of a debuff only one of which sits on a target.
    log = a_log(
        *held(PLAYER, 10_000, 30_000),
        *held(OTHER, 30_000, 50_000),
        *held(PLAYER, 50_000, 70_000),
    )

    mine = boss_debuffs(log, (BOSS_PULL,), PLAYER, RUN_PLAYERS)
    theirs = boss_debuffs(log, (BOSS_PULL,), OTHER, RUN_PLAYERS)

    assert mine.shared_with == ((DOT, (OTHER,)),)
    assert theirs.shared_with == ((DOT, (PLAYER,)),)
    # Shared changes no figure: our own seconds are still ours alone.
    assert mine.covered_seconds(DOT) == 40.0


def test_copies_of_one_debuff_that_coexist_are_each_casters_own() -> None:
    # Ten seconds of overlap: both copies sat on the boss at once, so a teammate
    # applying the same debuff did not take ours away.
    mine = boss_debuffs(
        a_log(*held(PLAYER, 10_000, 40_000), *held(OTHER, 30_000, 60_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


@pytest.mark.parametrize(
    ("our_end_ms", "shared"),
    [(31_000, True), (31_001, False)],
    ids=["exactly-the-tolerance", "a-millisecond-over"],
)
def test_an_overlap_up_to_the_tolerance_is_still_exclusive(our_end_ms: int, shared: bool) -> None:
    mine = boss_debuffs(
        a_log(*held(PLAYER, 10_000, our_end_ms), *held(OTHER, 30_000, 50_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert SHARED_OVERLAP_TOLERANCE_S == 1.0
    assert (mine.shared_with == ((DOT, (OTHER,)),)) is shared


def test_an_overlap_is_summed_across_every_stretch_the_two_held_it() -> None:
    # Two overlaps of 0.6s each: neither alone passes the tolerance, together they do.
    mine = boss_debuffs(
        a_log(
            *held(PLAYER, 10_000, 20_600),
            *held(OTHER, 20_000, 40_000),
            *held(PLAYER, 39_400, 50_000),
        ),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


def test_an_overlap_outside_the_boss_pull_does_not_count() -> None:
    # Both held it before the pull began, at once; on the boss pull they never
    # overlapped. Only the measured window is read.
    mine = boss_debuffs(
        a_log(*held(PLAYER, 0, 30_000), *held(OTHER, 0, 9_000), *held(OTHER, 30_000, 50_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ((DOT, (OTHER,)),)


def test_our_zero_is_shared_when_two_teammates_took_the_debuff_over_from_each_other() -> None:
    mine = boss_debuffs(
        a_log(*held(OTHER, 10_000, 30_000), *held(THIRD_PLAYER, 30_000, 50_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered == ()
    assert mine.shared_with == ((DOT, (OTHER, THIRD_PLAYER)),)


def test_our_zero_beside_one_teammate_says_nothing_about_sharing() -> None:
    # One holder alone cannot show that copies never coexist.
    mine = boss_debuffs(
        a_log(*held(OTHER, 10_000, 30_000)), (BOSS_PULL,), PLAYER, RUN_PLAYERS
    )

    assert mine.shared_with == ()


def test_a_player_and_their_own_pet_never_share() -> None:
    mine = boss_debuffs(
        a_log(*held(PLAYER, 10_000, 30_000), *held(PET, 30_000, 50_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


TEAMMATES_PET = 11


def test_a_teammates_pet_taking_the_debuff_over_shares_it_with_that_teammate() -> None:
    # The pet is no player, so this is shared only if the pet is folded into its
    # owner before the owner is checked against the run's players.
    log = a_log(*held(PLAYER, 10_000, 30_000), *held(TEAMMATES_PET, 30_000, 50_000))
    log = log.model_copy(update={"pet_owners": (*log.pet_owners, (TEAMMATES_PET, OTHER))})

    mine = boss_debuffs(log, (BOSS_PULL,), PLAYER, RUN_PLAYERS)

    assert mine.shared_with == ((DOT, (OTHER,)),)


def test_an_enemy_applying_the_same_debuff_does_not_make_it_shared() -> None:
    mine = boss_debuffs(
        a_log(*held(PLAYER, 10_000, 30_000), *held(ADD_ACTOR, 30_000, 50_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


def test_without_the_runs_players_nothing_is_shared() -> None:
    # A reference's debuffs are read with no players named, and sharing is
    # never computed for one.
    mine = boss_debuffs(
        a_log(*held(PLAYER, 10_000, 30_000), *held(OTHER, 30_000, 50_000)),
        (BOSS_PULL,),
        PLAYER,
        frozenset(),
    )

    assert mine.shared_with == ()


def test_covered_seconds_merge_a_players_and_their_pets_copies_on_one_boss() -> None:
    # Ours 20-50s, our pet 40-60s, ours again 65-80s (clipped to the pull's 70s):
    # 20-60 merged is 40s, plus 65-70 is 5s. A sum of the parts would read 65s.
    mine = boss_debuffs(
        a_log(
            *held(PLAYER, 20_000, 50_000),
            *held(PET, 40_000, 60_000),
            *held(PLAYER, 65_000, 80_000),
        ),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered == ((2001, DOT, 45_000),)
    assert mine.covered_seconds(DOT, 2001) == 45.0
    assert mine.covered_seconds(DOT, 9999) == 0.0


ALPHA, BETA = 63, 64
ALPHA_GAME, BETA_GAME = 6300, 6400
COUNCIL_NAME = "Alpha Fixture and Beta Fixture"
COUNCIL_ACTORS = (
    an_enemy(ALPHA, ALPHA_GAME, "Alpha Fixture"),
    an_enemy(BETA, BETA_GAME, "Beta Fixture"),
)


def a_council_pull(*, killed: bool = True) -> Pull:
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name=COUNCIL_NAME, enemies=(ALPHA, BETA))
    return pull.model_copy(
        update={
            "killed": killed,
            "enemies": (
                EnemyNpc(actor_id=ALPHA, game_id=ALPHA_GAME),
                EnemyNpc(actor_id=BETA, game_id=BETA_GAME),
            ),
        }
    )


def a_council_log(*events: DebuffEvent, deaths: tuple[tuple[int, int], ...] = ()) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=((ALPHA, ALPHA_GAME), (BETA, BETA_GAME), (THIRD, ALPHA_GAME)),
        npc_actors=COUNCIL_ACTORS,
        ability_names=((DOT, "Blood Plague"),),
        deaths=deaths,
        end_ms=80_000,
    )


def on(target: int, source: int, start_ms: int, end_ms: int) -> tuple[DebuffEvent, DebuffEvent]:
    """One application and its removal, by `source`, on `target`."""
    return (
        an_event(True, start_ms, source=source, target=target),
        an_event(False, end_ms, source=source, target=target),
    )


def test_a_councils_coverage_sums_each_boss_over_its_own_life() -> None:
    # Alpha dies at 40s, Beta at 70s: 30s and 60s alive. Ours covered Alpha for
    # 30s (all of it) and Beta for 30s: 60s of 90s. A pull-length reading would
    # be 60s over 60s, and a merged timeline 30s over 60s.
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 40_000),
            *on(BETA, PLAYER, 10_000, 40_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    [window] = mine.windows
    assert window.targets == (
        BossTarget(game_id=ALPHA_GAME, start_ms=10_000, end_ms=40_000),
        BossTarget(game_id=BETA_GAME, start_ms=10_000, end_ms=70_000),
    )
    assert mine.seconds == 90.0
    assert mine.covered_seconds(DOT) == 60.0
    assert encounter_share(mine, DOT, 2001) == 60.0 / 90.0


def test_a_wiped_council_runs_each_boss_to_the_pulls_end_and_counts_no_missing_death() -> None:
    [window] = boss_windows_of((a_council_pull(killed=False),), COUNCIL_ACTORS)

    assert [target.end_ms for target in window.targets] == [70_000, 70_000]
    assert window.deathless == 0


def test_a_killed_council_boss_with_no_death_runs_to_the_pulls_end_and_is_counted() -> None:
    [window] = boss_windows_of((a_council_pull(),), COUNCIL_ACTORS, ((ALPHA_GAME, 40_000),))

    assert [target.end_ms for target in window.targets] == [40_000, 70_000]
    assert window.deathless == 1


def test_a_boss_that_dies_twice_lives_until_its_last_death() -> None:
    [window] = boss_windows_of(
        (a_council_pull(),),
        COUNCIL_ACTORS,
        ((ALPHA_GAME, 30_000), (ALPHA_GAME, 50_000), (BETA_GAME, 60_000)),
    )

    assert [target.end_ms for target in window.targets] == [50_000, 60_000]


def test_a_death_before_the_pull_is_ignored_and_one_after_it_with_no_next_pull_counts() -> None:
    # Alpha's death at 5s precedes the pull: it is not this pull's. Its death at
    # 75s follows the pull's end and no pull comes after: it is Alpha's death, and
    # bounds the boss at the pull's end rather than past it.
    [window] = boss_windows_of(
        (a_council_pull(),),
        COUNCIL_ACTORS,
        ((ALPHA_GAME, 5_000), (ALPHA_GAME, 75_000), (BETA_GAME, 60_000)),
    )

    assert [target.end_ms for target in window.targets] == [70_000, 60_000]
    assert window.deathless == 0


def test_a_death_before_the_pull_alone_leaves_the_boss_deathless() -> None:
    [window] = boss_windows_of(
        (a_council_pull(),), COUNCIL_ACTORS, ((ALPHA_GAME, 5_000), (BETA_GAME, 60_000))
    )

    assert [target.end_ms for target in window.targets] == [70_000, 60_000]
    assert window.deathless == 1


def test_a_death_logged_just_after_the_pull_closed_is_still_that_bosss() -> None:
    [window] = boss_windows_of(
        (a_council_pull(),), COUNCIL_ACTORS, ((ALPHA_GAME, 40_000), (BETA_GAME, 70_036))
    )

    assert [target.end_ms for target in window.targets] == [40_000, 70_000]
    assert window.deathless == 0


def test_a_killed_pull_does_not_borrow_a_boss_death_from_the_next_pull() -> None:
    # Beta has no death in the first pull; the one at 130s belongs to the second.
    first = a_council_pull()
    second = a_council_pull().model_copy(
        update={"index": 2, "pull_id": 3, "start_ms": 100_000, "end_ms": 160_000}
    )

    one, two = boss_windows_of(
        (first, second), COUNCIL_ACTORS, ((ALPHA_GAME, 40_000), (BETA_GAME, 130_000))
    )

    assert one.deathless == 1
    assert two.deathless == 1


def test_a_wipe_runs_to_its_end_and_the_kill_after_it_takes_its_own_deaths() -> None:
    # The wipe is capped at its own end whatever the horizon says, so this pins the
    # kill's spans, not the horizon: `test_a_killed_pull_does_not_borrow_a_boss_death_
    # from_the_next_pull` pins that.
    wipe = a_council_pull(killed=False)
    kill = a_council_pull().model_copy(
        update={"index": 2, "pull_id": 3, "start_ms": 100_000, "end_ms": 160_000}
    )

    wiped, killed = boss_windows_of(
        (wipe, kill), COUNCIL_ACTORS, ((ALPHA_GAME, 130_000), (BETA_GAME, 150_000))
    )

    assert [target.end_ms for target in wiped.targets] == [70_000, 70_000]
    assert [target.end_ms for target in killed.targets] == [130_000, 150_000]
    assert wiped.deathless == 0
    assert killed.deathless == 0


def test_a_single_boss_runs_the_whole_pull_whatever_the_deaths_say() -> None:
    [window] = boss_windows_of((BOSS_PULL,), ACTORS, ((BOSS_GAME, 50_000),))

    assert window.targets == (BossTarget(game_id=BOSS_GAME, start_ms=10_000, end_ms=70_000),)


def test_a_council_boss_logged_under_a_second_actor_id_is_still_that_boss() -> None:
    # Actor THIRD is a second id of Alpha's game id: what sat on it, sat on Alpha.
    mine = boss_debuffs(
        a_council_log(*on(THIRD, PLAYER, 10_000, 40_000), deaths=((ALPHA_GAME, 40_000),)),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered_seconds(DOT) == 30.0


def test_two_players_on_different_council_bosses_do_not_share() -> None:
    # Ours only ever on Alpha, theirs only ever on Beta: the copies never met on
    # one boss, which says nothing about whether they could coexist.
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 40_000),
            *on(BETA, OTHER, 10_000, 40_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


def test_a_debuff_two_players_swap_on_each_council_boss_is_shared() -> None:
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 25_000),
            *on(ALPHA, OTHER, 25_000, 40_000),
            *on(BETA, OTHER, 10_000, 40_000),
            *on(BETA, PLAYER, 40_000, 70_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ((DOT, (OTHER,)),)


def test_copies_that_coexist_on_one_council_boss_are_per_caster() -> None:
    # They swap on Alpha but sit together on Beta for 20s: per caster after all.
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 25_000),
            *on(ALPHA, OTHER, 25_000, 40_000),
            *on(BETA, PLAYER, 10_000, 50_000),
            *on(BETA, OTHER, 30_000, 70_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


def a_listed_twice(pull: Pull) -> tuple[Pull, Pull]:
    """The pull, then its exact duplicate, as `dungeonPulls` lists some wipes."""
    return pull, pull.model_copy(update={"index": pull.index + 1, "pull_id": pull.pull_id + 1})


def test_a_boss_pull_listed_twice_is_measured_once() -> None:
    # 30s of a 60s pull is half. Counted twice, the seconds double and so does the
    # covered time (0.5 over 120s), or the denominator doubles alone (0.25).
    mine = boss_debuffs(
        a_log(*held(PLAYER, 20_000, 50_000)), a_listed_twice(BOSS_PULL), PLAYER, RUN_PLAYERS
    )

    assert len(mine.windows) == 1
    assert mine.seconds == 60.0
    assert encounter_share(mine, DOT, 2001) == 0.5


def test_a_council_kill_listed_twice_is_one_window_ending_at_its_deaths() -> None:
    # The first copy's next pull is its own duplicate, which starts where it does:
    # no death would be admitted there.
    [window] = boss_windows_of(
        a_listed_twice(a_council_pull()),
        COUNCIL_ACTORS,
        ((ALPHA_GAME, 40_000), (BETA_GAME, 60_000)),
    )

    assert [target.end_ms for target in window.targets] == [40_000, 60_000]
    assert window.deathless == 0


def test_a_duplicate_of_a_pull_is_not_the_next_pull_for_a_trash_pull_either() -> None:
    # A duplicate of the boss pull listed as a non-boss pull still starts where it does.
    boss = a_council_pull()
    twin = a_pull(2, boss.start_ms, boss.end_ms)

    [window] = boss_windows_of(
        (boss, twin), COUNCIL_ACTORS, ((ALPHA_GAME, 40_000), (BETA_GAME, 60_000))
    )

    assert [target.end_ms for target in window.targets] == [40_000, 60_000]
    assert window.deathless == 0


def test_a_next_pull_starting_inside_this_one_does_not_hide_a_death_inside_it() -> None:
    # The next pull opens at 50s, before this one closes at 70s. Alpha's death at
    # 60s is inside this pull's own span, so it is this pull's whatever comes next.
    overlapping = a_council_pull().model_copy(
        update={"index": 2, "pull_id": 3, "start_ms": 50_000, "end_ms": 160_000}
    )

    [window, _] = boss_windows_of(
        (a_council_pull(), overlapping),
        COUNCIL_ACTORS,
        ((ALPHA_GAME, 60_000), (BETA_GAME, 65_000)),
    )

    assert [target.end_ms for target in window.targets] == [60_000, 65_000]
    assert window.deathless == 0


def test_a_boss_fought_twice_shares_a_debuff_only_within_one_pull() -> None:
    # Ours only in the wipe, theirs only in the kill: the two copies never sat on
    # one boss in one pull, so nothing shows that they replace each other.
    wipe = BOSS_PULL
    kill = a_pull(2, 100_000, 160_000, encounter_id=2001, name=BOSS_NAME)

    mine = boss_debuffs(
        a_log(*held(PLAYER, 20_000, 50_000), *held(OTHER, 110_000, 140_000)),
        (wipe, kill),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()
