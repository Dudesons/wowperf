# ABOUTME: Behaviour tests for the trash-pack half of the individual comparison.
# ABOUTME: Only packs two routes shared are compared, and only their own seconds count.

from wowperf.domain.comparison.trash_spells import aligned_trash
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

OURS = Player(
    actor_id=693, name="Emberkin", class_name="DeathKnight", spec="Blood", item_level=318
)
THEIRS = Player(
    actor_id=11, name="Bríala", class_name="DeathKnight", spec="Blood", item_level=330
)


def a_pull(index: int, seconds: float, *game_ids: int, encounter_id: int = 0) -> Pull:
    """A pull holding one enemy actor per game id, so alignment can match on types."""
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack" if encounter_id == 0 else "Boss",
        encounter_id=encounter_id,
        start_ms=index * 400_000,
        end_ms=index * 400_000 + int(seconds * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=1000 + n, game_id=g) for n, g in enumerate(game_ids)),
    )


def a_run(player: Player, *pulls: Pull) -> Run:
    return Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(player,),
        pulls=pulls,
    )


def test_only_packs_both_routes_fought_are_counted() -> None:
    ours = a_run(OURS, a_pull(0, 60.0, 100, 101), a_pull(1, 40.0, 200))
    theirs = a_run(THEIRS, a_pull(0, 30.0, 100, 101))

    aligned = aligned_trash(ours, theirs)

    assert aligned.our_pulls == frozenset({0})
    assert aligned.our_seconds == 60.0
    assert aligned.their_seconds == 30.0
    assert aligned.pack_count == 1


def test_one_chain_pull_of_ours_counts_its_seconds_once() -> None:
    """align_pulls sweeps back over their unclaimed pulls and can name the same
    pull of ours twice. Summing per match would count our stretch twice, inflate
    our denominator and depress our own rate - an error that makes the player
    look worse than they were."""
    ours = a_run(OURS, a_pull(0, 90.0, 100, 101, 200, 201))
    theirs = a_run(THEIRS, a_pull(0, 30.0, 100, 101), a_pull(1, 25.0, 200, 201))

    aligned = aligned_trash(ours, theirs)

    # Both of their packs matched our single stretch.
    assert aligned.their_pulls == frozenset({0, 1})
    assert aligned.their_seconds == 55.0
    # Ours is one pull and counts once, however many of theirs it covered.
    assert aligned.our_pulls == frozenset({0})
    assert aligned.our_seconds == 90.0
    assert aligned.pack_count == 1


def test_boss_pulls_are_not_aligned_trash() -> None:
    """Bosses match by encounter id and are the other comparison's subject. Counting
    them here would put the same seconds in two denominators."""
    ours = a_run(OURS, a_pull(0, 60.0, 100, encounter_id=2607), a_pull(1, 40.0, 200))
    theirs = a_run(THEIRS, a_pull(0, 55.0, 100, encounter_id=2607), a_pull(1, 35.0, 200))

    aligned = aligned_trash(ours, theirs)

    assert aligned.our_pulls == frozenset({1})
    assert aligned.our_seconds == 40.0
