# ABOUTME: One player's debuffs on each boss: the boss alone, clipped to its pull, pets included.
# ABOUTME: Pins councils and missing bosses withheld, a shorter boss name, and per-boss shares.

import pytest

from wowperf.domain.auras import uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import (
    SHARED_OVERLAP_TOLERANCE_S,
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


def a_log(*events: DebuffEvent, actors: tuple[NpcActor, ...] = ACTORS) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=tuple(GAME_IDS.items()),
        npc_actors=actors,
        ability_names=((DOT, "Blood Plague"),),
        end_ms=80_000,
    )


def test_a_single_boss_is_measured_over_its_own_pull_and_trash_is_not() -> None:
    assert boss_windows_of((TRASH_PULL, BOSS_PULL), ACTORS) == (
        BossWindow(
            encounter_id=2001,
            name=BOSS_NAME,
            start_ms=10_000,
            end_ms=70_000,
            boss_game_id=BOSS_GAME,
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

    [aura] = mine.auras
    assert (aura.ability_id, aura.name, aura.total_uptime_ms) == (DOT, "Blood Plague", 30_000)
    assert [(band.start_ms, band.end_ms) for band in aura.bands] == [(20_000, 50_000)]
    assert mine.seconds == 60.0


def test_an_interval_reaching_past_the_pull_is_clipped_to_it() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 5_000), an_event(False, 75_000)), (BOSS_PULL,), PLAYER, RUN_PLAYERS
    )

    assert [(band.start_ms, band.end_ms) for band in mine.auras[0].bands] == [(10_000, 70_000)]


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

    [aura] = mine.auras
    assert uptime_seconds_in(aura, mine.measured) == 40.0
    assert aura.total_uptime_ms == 40_000


def test_another_players_debuff_is_not_this_players() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 20_000, source=OTHER), an_event(False, 50_000, source=OTHER)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.auras == ()


def test_a_council_is_withheld_and_counts_no_seconds() -> None:
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
        a_log(an_event(True, 20_000), an_event(False, 50_000), actors=council),
        (pull,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert [window.withheld for window in mine.windows] == [Withheld.COUNCIL]
    assert (mine.seconds, mine.auras) == (0.0, ())


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

    assert [window.boss_game_id for window in boss_windows_of((pull,), actors)] == [BOSS_GAME]


def test_the_pairing_tally_rides_along() -> None:
    mine = boss_debuffs(a_log(an_event(False, 30_000)), (BOSS_PULL,), PLAYER, RUN_PLAYERS)

    assert mine.tally.orphan_removes == 1


def test_a_share_is_read_per_boss_and_a_withheld_boss_says_why() -> None:
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
    assert encounter_share(mine, DOT, 2002) is Withheld.COUNCIL
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


def test_an_unflagged_enemy_named_after_the_pull_is_its_boss() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_a_name_match_beats_a_boss_flagged_add() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME),
        an_enemy(SECOND, SECOND_GAME, "Fixture Add", "Boss"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_an_unflagged_pair_named_for_both_is_a_council() -> None:
    window = the_window_of(
        "Alpha Fixture and Beta Fixture",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture"),
        an_enemy(SECOND, SECOND_GAME, "Beta Fixture"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (None, Withheld.COUNCIL)


def test_an_unflagged_enemy_whose_name_only_begins_the_pulls_is_its_boss() -> None:
    # The flag is absent, so only the opening-words half of the name step can
    # find this boss: the `find_bosses` fallback has no candidate to read.
    window = the_window_of(
        "Alpha Fixture the Tester",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_a_flagged_pair_whose_first_name_begins_the_pulls_is_a_council_not_that_boss() -> None:
    window = the_window_of(
        "Alpha Fixture and Beta Fixture",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(SECOND, SECOND_GAME, "Beta Fixture", "Boss"),
    )

    assert (window.boss_game_id, window.withheld) == (None, Withheld.COUNCIL)


def test_a_pull_named_for_two_bosses_with_one_in_it_is_still_a_council() -> None:
    window = the_window_of(
        "Alpha Fixture and Beta Fixture",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (None, Withheld.COUNCIL)


def test_one_boss_logged_under_two_actor_ids_is_one_boss() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME, "Boss"),
        an_enemy(THIRD, FIRST_GAME, BOSS_NAME, "Boss"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_one_flagged_boss_logged_under_two_actor_ids_is_one_boss_when_no_name_matches() -> None:
    window = the_window_of(
        "The Fixture Hall",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(THIRD, FIRST_GAME, "Alpha Fixture", "Boss"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_a_pull_named_for_no_enemy_reads_its_one_flagged_enemy() -> None:
    window = the_window_of(
        "The Fixture Hall",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_a_pull_named_for_no_enemy_reads_two_flagged_enemies_as_a_council() -> None:
    window = the_window_of(
        "Council o' Fixtures",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture", "Boss"),
        an_enemy(SECOND, SECOND_GAME, "Beta Fixture", "Boss"),
    )

    assert (window.boss_game_id, window.withheld) == (None, Withheld.COUNCIL)


def test_a_pull_named_for_no_enemy_and_holding_no_flagged_one_has_no_boss() -> None:
    window = the_window_of(
        "The Fixture Hall",
        an_enemy(FIRST, FIRST_GAME, "Fixture Add"),
        an_enemy(SECOND, SECOND_GAME, "Another Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (None, Withheld.NO_BOSS)


def test_a_comma_in_the_pulls_name_is_a_title_not_a_second_boss() -> None:
    window = the_window_of(
        "Alpha Fixture, The Tester",
        an_enemy(FIRST, FIRST_GAME, "Alpha Fixture, The Tester"),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add"),
    )

    assert (window.boss_game_id, window.withheld) == (FIRST_GAME, None)


def test_a_part_matched_by_two_game_ids_is_no_boss_and_does_not_fall_back_to_a_flag() -> None:
    window = the_window_of(
        BOSS_NAME,
        an_enemy(FIRST, FIRST_GAME, BOSS_NAME),
        an_enemy(SECOND, SECOND_GAME, BOSS_NAME),
        an_enemy(ADD_ACTOR, ADD_GAME, "Fixture Add", "Boss"),
    )

    assert (window.boss_game_id, window.withheld) == (None, Withheld.NO_BOSS)


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
    assert mine.auras[0].total_uptime_ms == 40_000


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

    assert mine.auras == ()
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
