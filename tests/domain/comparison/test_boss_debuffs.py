# ABOUTME: One player's debuffs on each boss: the boss alone, clipped to its pull, pets included.
# ABOUTME: Pins councils and missing bosses withheld, a shorter boss name, and per-boss shares.

from wowperf.domain.auras import uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import (
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
PLAYER, PET, OTHER = 7, 8, 9
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
    )

    [aura] = mine.auras
    assert (aura.ability_id, aura.name, aura.total_uptime_ms) == (DOT, "Blood Plague", 30_000)
    assert [(band.start_ms, band.end_ms) for band in aura.bands] == [(20_000, 50_000)]
    assert mine.seconds == 60.0


def test_an_interval_reaching_past_the_pull_is_clipped_to_it() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 5_000), an_event(False, 75_000)), (BOSS_PULL,), PLAYER
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
    )

    [aura] = mine.auras
    assert uptime_seconds_in(aura, mine.measured) == 40.0
    assert aura.total_uptime_ms == 40_000


def test_another_players_debuff_is_not_this_players() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 20_000, source=OTHER), an_event(False, 50_000, source=OTHER)),
        (BOSS_PULL,),
        PLAYER,
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
    )

    assert [window.withheld for window in mine.windows] == [Withheld.COUNCIL]
    assert (mine.seconds, mine.auras) == (0.0, ())


def test_a_boss_pull_with_no_boss_flagged_enemy_is_withheld() -> None:
    unflagged = tuple(actor.model_copy(update={"sub_type": "NPC"}) for actor in ACTORS)

    assert [window.withheld for window in boss_windows_of((BOSS_PULL,), unflagged)] == [
        Withheld.NO_BOSS
    ]


def test_a_boss_whose_name_only_begins_the_pulls_is_still_the_boss() -> None:
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name="Vashnik the Malignant")
    actors = (NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name="Vashnik", sub_type="Boss"),)

    assert [window.boss_game_id for window in boss_windows_of((pull,), actors)] == [BOSS_GAME]


def test_the_pairing_tally_rides_along() -> None:
    mine = boss_debuffs(a_log(an_event(False, 30_000)), (BOSS_PULL,), PLAYER)

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
    )

    assert encounter_share(mine, DOT, 2001) == 0.5
    assert encounter_share(mine, DOT, 2002) is Withheld.COUNCIL
    assert encounter_share(mine, DOT, 9999) is None
