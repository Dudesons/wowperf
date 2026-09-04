# ABOUTME: Behaviour tests for lining two pull sequences up by what each pack was made of.
# ABOUTME: The interesting cases are a skipped pack, an extra pack, and a reordered route.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.model import EnemyNpc, Pull, Run


def a_pull(index: int, game_ids: tuple[int, ...]) -> Pull:
    enemies = tuple(
        EnemyNpc(actor_id=100 + n, game_id=game_id)
        for n, game_id in enumerate(game_ids)
    )
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack",
        encounter_id=0,
        start_ms=index * 100_000,
        end_ms=index * 100_000 + 60_000,
        killed=True,
        x=0,
        y=0,
        enemies=enemies,
    )


def a_run(*signatures: tuple[int, ...]) -> Run:
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
        players=(),
        pulls=tuple(a_pull(index, ids) for index, ids in enumerate(signatures)),
    )


def test_identical_routes_match_every_pull() -> None:
    alignment = align_pulls(a_run((1, 2), (3,)), a_run((1, 2), (3,)))

    assert [(m.ours_index, m.theirs_index) for m in alignment.matched] == [(0, 0), (1, 1)]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()


def test_a_pack_we_killed_and_they_skipped_lands_in_only_ours() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((1,), (3,)))

    assert alignment.only_ours == (1,)
    assert alignment.only_theirs == ()
    assert [(m.ours_index, m.theirs_index) for m in alignment.matched] == [(0, 0), (2, 1)]


def test_a_pack_only_they_killed_lands_in_only_theirs() -> None:
    alignment = align_pulls(a_run((1,), (3,)), a_run((1,), (2,), (3,)))

    assert alignment.only_ours == ()
    assert alignment.only_theirs == (1,)


def test_a_replaced_pack_counts_on_both_sides() -> None:
    alignment = align_pulls(a_run((1,), (2,)), a_run((1,), (9,)))

    assert alignment.only_ours == (1,)
    assert alignment.only_theirs == (1,)


def test_pack_composition_ignores_the_order_enemies_arrive_in() -> None:
    alignment = align_pulls(a_run((2, 1),), a_run((1, 2),))

    assert len(alignment.matched) == 1


def test_a_repeated_pack_is_matched_twice_not_folded_into_one() -> None:
    alignment = align_pulls(a_run((1,), (1,)), a_run((1,), (1,)))

    assert len(alignment.matched) == 2


def test_a_route_run_in_a_different_order_is_reported() -> None:
    ours = a_run((1,), (2,), (3,))
    theirs = a_run((2,), (1,), (3,))

    alignment = align_pulls(ours, theirs)
    reordered = [(m.ours_index, m.theirs_index) for m in alignment.out_of_order]

    assert reordered, "a route taken in a different order should be visible"


def test_a_route_in_the_same_order_reports_nothing_out_of_order() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((1,), (2,), (3,)))

    assert alignment.out_of_order == ()


def test_two_empty_routes_align_without_raising() -> None:
    alignment = align_pulls(a_run(), a_run())

    assert alignment.matched == ()


def test_a_skipped_pack_is_not_reported_as_reordering() -> None:
    """Index drift from an unequal-length route is not the same as reordering.

    Skipping pack 2 pushes every later match one slot back in their route
    (our pull 2 lines up with their pull 1, our pull 3 with their pull 2) but
    nothing was fought out of sequence.
    """
    alignment = align_pulls(a_run((1,), (2,), (3,), (4,)), a_run((1,), (3,), (4,)))

    assert alignment.out_of_order == ()
    assert alignment.only_ours == (1,)
    assert alignment.only_theirs == ()


def test_a_genuine_swap_is_reported_as_reordering_and_leaves_no_leftovers() -> None:
    """An adjacent swap is a pack signature stranded on both sides of the split.

    Pack 1 gets absorbed into a normal match (with drifted indices, same as a
    skip would cause), but pack 2 is left over on both sides and that is what
    `out_of_order` surfaces.
    """
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((2,), (1,), (3,)))

    assert [(m.ours_index, m.theirs_index) for m in alignment.out_of_order] == [(1, 0)]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()


def test_leftover_multiplicity_pairs_only_as_many_as_both_sides_share() -> None:
    """A signature left over twice on our side and once on theirs pairs once."""
    alignment = align_pulls(a_run((1,), (2,), (2,)), a_run((2,), (1,)))

    assert [(m.ours_index, m.theirs_index) for m in alignment.out_of_order] == [(1, 0)]
    assert alignment.only_ours == (2,)
    assert alignment.only_theirs == ()
