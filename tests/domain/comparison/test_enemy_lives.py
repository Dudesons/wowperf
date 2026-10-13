# ABOUTME: Every enemy of a key cut into lives, from the first debuff anyone applied to its death.
# ABOUTME: Pins the cuts, a reused instance, one creature under two actor ids, and what is left out.

from wowperf.domain.comparison.enemy_lives import EnemyLife, EnemyLives, LifeStretch, enemy_lives
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.debuffs import DebuffEvent, DebuffLog, EnemyDeathRow
from wowperf.domain.model import EnemyNpc, Pull

PLAYER, PET, OTHER = 7, 8, 9
WHELP, WHELP_TWIN, LASHER, TOMB, BOSS_ACTOR, NAMELESS = 30, 31, 32, 33, 50, 77
WHELP_GAME, LASHER_GAME, TOMB_GAME, BOSS_GAME, PET_GAME = 3000, 3200, 3300, 5000, 900
BOSS_NAME = "The Test Colossus"
DOT = 55078
GAME_IDS = {
    # Players carry game id 0 in a real report's actors, so a player is only
    # kept out by being named a player, never by a missing game id.
    PLAYER: 0,
    OTHER: 0,
    PET: PET_GAME,
    WHELP: WHELP_GAME,
    WHELP_TWIN: WHELP_GAME,
    LASHER: LASHER_GAME,
    TOMB: TOMB_GAME,
    BOSS_ACTOR: BOSS_GAME,
}


def a_pull(
    index: int,
    start_ms: int,
    end_ms: int,
    *,
    encounter_id: int = 0,
    name: str = "Pack",
    enemies: tuple[int, ...] = (),
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
        enemies=tuple(EnemyNpc(actor_id=actor, game_id=GAME_IDS[actor]) for actor in enemies),
    )


TRASH = a_pull(0, 0, 60_000, enemies=(WHELP, LASHER))
BOSS = a_pull(1, 100_000, 160_000, encounter_id=2001, name=BOSS_NAME, enemies=(BOSS_ACTOR,))
PULLS = (TRASH, BOSS)
NPC_ACTORS = (
    NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name=BOSS_NAME, sub_type="Boss"),
    NpcActor(actor_id=WHELP, game_id=WHELP_GAME, name="Fixture Whelp", sub_type="NPC"),
    NpcActor(actor_id=WHELP_TWIN, game_id=WHELP_GAME, name="Fixture Whelp", sub_type="NPC"),
    NpcActor(actor_id=LASHER, game_id=LASHER_GAME, name="Fixture Lasher", sub_type="NPC"),
)


def applied(
    at: int, *, target: int = WHELP, instance: int = 1, source: int = PLAYER
) -> DebuffEvent:
    return DebuffEvent(
        applied=True,
        timestamp_ms=at,
        source_id=source,
        target_id=target,
        target_instance=instance,
        ability_id=DOT,
    )


def removed(
    at: int, *, target: int = WHELP, instance: int = 1, source: int = PLAYER
) -> DebuffEvent:
    return DebuffEvent(
        applied=False,
        timestamp_ms=at,
        source_id=source,
        target_id=target,
        target_instance=instance,
        ability_id=DOT,
    )


def died(at: int, *, target: int = WHELP, instance: int = 1) -> EnemyDeathRow:
    return EnemyDeathRow(target_id=target, target_instance=instance, timestamp_ms=at)


def a_log(*events: DebuffEvent, deaths: tuple[EnemyDeathRow, ...] = ()) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER), (TOMB, PLAYER)),
        game_ids=tuple(GAME_IDS.items()),
        npc_actors=NPC_ACTORS,
        ability_names=((DOT, "Blood Plague"),),
        death_rows=deaths,
        player_ids=(PLAYER, OTHER),
        end_ms=200_000,
    )


def lives_of(log: DebuffLog, bosses: frozenset[int] = frozenset({BOSS_GAME})) -> EnemyLives:
    return enemy_lives(log, PULLS, bosses)


def a_life(
    start_ms: int,
    end_ms: int,
    *,
    game_id: int = WHELP_GAME,
    instance: int = 1,
    stretch: LifeStretch = LifeStretch.TRASH,
) -> EnemyLife:
    return EnemyLife(
        game_id=game_id, instance=instance, start_ms=start_ms, end_ms=end_ms, stretch=stretch
    )


def test_a_life_runs_from_the_first_application_by_anyone_to_the_death() -> None:
    found = lives_of(a_log(applied(10_000, source=OTHER), applied(20_000), deaths=(died(40_000),)))

    assert found == EnemyLives(lives=(a_life(10_000, 40_000),))


def test_an_enemy_is_cut_into_a_life_at_each_of_its_deaths() -> None:
    # The log reuses copy numbers inside one pull: one copy number, two mobs.
    found = lives_of(a_log(applied(5_000), applied(30_000), deaths=(died(20_000), died(50_000))))

    assert found.lives == (a_life(5_000, 20_000), a_life(30_000, 50_000))


def test_a_removal_logged_just_after_a_death_opens_no_life() -> None:
    found = lives_of(a_log(applied(5_000), removed(20_050), deaths=(died(20_000),)))

    assert found == EnemyLives(lives=(a_life(5_000, 20_000),))


def test_one_creature_under_two_actor_ids_is_one_enemy() -> None:
    found = lives_of(a_log(applied(5_000, target=WHELP), deaths=(died(20_000, target=WHELP_TWIN),)))

    assert found.lives == (a_life(5_000, 20_000),)


def test_a_life_with_no_death_is_left_out_and_counted() -> None:
    found = lives_of(a_log(applied(5_000), applied(30_000), deaths=(died(20_000),)))

    assert found == EnemyLives(lives=(a_life(5_000, 20_000),), unmeasured_no_death=1)


def test_an_enemy_debuffed_and_never_killed_is_counted_once() -> None:
    found = lives_of(a_log(applied(5_000), applied(10_000, source=OTHER)))

    assert found == EnemyLives(unmeasured_no_death=1)


def test_a_death_nobody_debuffed_is_a_life_of_no_length_and_counted() -> None:
    found = lives_of(a_log(deaths=(died(20_000, target=LASHER, instance=0),)))

    assert found == EnemyLives(
        lives=(a_life(20_000, 20_000, game_id=LASHER_GAME, instance=0),),
        undebuffed_deaths=1,
    )


def test_a_death_the_log_writes_twice_is_one_death() -> None:
    found = lives_of(a_log(applied(5_000), deaths=(died(20_000), died(20_000))))

    assert found == EnemyLives(lives=(a_life(5_000, 20_000),))


def test_a_player_and_a_pet_a_player_owns_are_never_enemies() -> None:
    # Glacial Tomb and A Knot of Snakes are logged as hostile pets of a player.
    found = lives_of(
        a_log(
            applied(5_000, target=TOMB, instance=0),
            applied(5_000, target=PET, instance=0),
            applied(5_000, target=OTHER, instance=0),
            deaths=(
                died(20_000, target=TOMB, instance=0),
                died(20_000, target=PET, instance=0),
                died(20_000, target=OTHER, instance=0),
            ),
        )
    )

    assert found == EnemyLives()


def test_a_life_belongs_to_the_pull_holding_its_death() -> None:
    # The first lasher dies after the trash pull closed and before the boss pull
    # opened, so the trash pull still holds it. The second dies inside the boss
    # pull: an add.
    found = lives_of(
        a_log(
            applied(50_000, target=LASHER, instance=1),
            applied(120_000, target=LASHER, instance=2),
            deaths=(
                died(61_000, target=LASHER, instance=1),
                died(150_000, target=LASHER, instance=2),
            ),
        )
    )

    assert found.lives == (
        a_life(50_000, 61_000, game_id=LASHER_GAME, instance=1),
        a_life(120_000, 150_000, game_id=LASHER_GAME, instance=2, stretch=LifeStretch.ADDS),
    )


def test_a_measured_boss_is_left_to_the_boss_rule() -> None:
    # A wipe: the boss carried a debuff and never died. As a life it would read
    # as an enemy with no death; the boss rule measures it instead.
    found = lives_of(a_log(applied(110_000, target=BOSS_ACTOR, instance=0)))

    assert found == EnemyLives()


def test_a_boss_no_window_measured_is_an_add() -> None:
    found = lives_of(
        a_log(
            applied(110_000, target=BOSS_ACTOR, instance=0),
            deaths=(died(150_000, target=BOSS_ACTOR, instance=0),),
        ),
        bosses=frozenset(),
    )

    assert found.lives == (
        a_life(110_000, 150_000, game_id=BOSS_GAME, instance=0, stretch=LifeStretch.ADDS),
    )


def test_an_actor_with_no_game_id_is_no_enemy() -> None:
    found = lives_of(
        a_log(applied(5_000, target=NAMELESS), deaths=(died(20_000, target=NAMELESS),))
    )

    assert found == EnemyLives()


def test_a_fight_with_no_pulls_holds_no_life() -> None:
    log = a_log(applied(5_000), deaths=(died(20_000),))

    assert enemy_lives(log, (), frozenset()) == EnemyLives()


def test_a_life_is_keyed_by_its_enemy_and_its_death() -> None:
    assert a_life(5_000, 20_000).key == (WHELP_GAME, 1, 20_000)


def test_an_application_after_a_death_is_no_part_of_that_death() -> None:
    # The only application comes after the copy's only death: a life with no death
    # to close it, and a death nobody debuffed before it.
    found = lives_of(a_log(applied(30_000), deaths=(died(20_000),)))

    assert found == EnemyLives(
        lives=(a_life(20_000, 20_000),), unmeasured_no_death=1, undebuffed_deaths=1
    )


def test_a_death_stamped_just_after_a_boss_pull_closed_is_still_an_add() -> None:
    found = lives_of(
        a_log(
            applied(120_000, target=LASHER, instance=2),
            deaths=(died(160_050, target=LASHER, instance=2),),
        )
    )

    assert found.lives == (
        a_life(120_000, 160_050, game_id=LASHER_GAME, instance=2, stretch=LifeStretch.ADDS),
    )


def test_a_death_before_every_pull_belongs_to_the_first_pull() -> None:
    # The first pull is the boss's; a later trash pull must not take the death.
    pulls = (BOSS, a_pull(2, 200_000, 260_000, enemies=(WHELP,)))
    log = a_log(applied(5_000), deaths=(died(20_000),))

    assert enemy_lives(log, pulls, frozenset()).lives == (
        a_life(5_000, 20_000, stretch=LifeStretch.ADDS),
    )


def test_an_application_in_the_same_millisecond_as_a_death_belongs_to_that_life() -> None:
    # The cut is "after the previous death", strictly: a debuff stamped at a death's
    # own millisecond is that life's last, not the next life's first.
    found = lives_of(a_log(applied(5_000), applied(20_000), deaths=(died(20_000), died(50_000))))

    assert found == EnemyLives(
        lives=(a_life(5_000, 20_000), a_life(50_000, 50_000)), undebuffed_deaths=1
    )
