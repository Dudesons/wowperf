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


def a_boss(index: int, encounter_id: int, game_ids: tuple[int, ...]) -> Pull:
    return a_pull(index, game_ids).model_copy(update={"encounter_id": encounter_id})


def test_a_merged_pull_matches_each_separate_pull_it_covers() -> None:
    # We chain-pulled three packs; Warcraft Logs recorded one pull. They took them one by one.
    alignment = align_pulls(a_run((1, 2, 3, 4, 5)), a_run((1, 2), (3,), (4, 5)))
    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [
        (0, 0), (0, 1), (0, 2),
    ]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()
    assert alignment.matched_share == 1.0


def test_a_small_pull_matches_the_merged_pull_that_contains_it() -> None:
    alignment = align_pulls(a_run((1, 2), (3,)), a_run((1, 2, 3),))
    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [(0, 0), (1, 0)]
    assert alignment.only_theirs == ()


def test_packs_sharing_no_enemy_type_do_not_match() -> None:
    alignment = align_pulls(a_run((1, 2),), a_run((3, 4),))
    assert alignment.matched == ()
    assert alignment.only_ours == (0,)
    assert alignment.only_theirs == (0,)
    assert alignment.matched_share == 0.0


def test_overlap_without_containment_does_not_match() -> None:
    # {1, 2} and {2, 3} share a type but neither contains the other.
    alignment = align_pulls(a_run((1, 2),), a_run((2, 3),))
    assert alignment.matched == ()


def test_the_candidate_sharing_the_most_types_wins() -> None:
    # Their pull 1 is the closer match for our {1, 2, 3}; their pull 0 is only a subset.
    alignment = align_pulls(a_run((1, 2, 3),), a_run((1,), (1, 2, 3)))
    assert (0, 1) in {(m.ours_index, m.theirs_index) for m in alignment.matched}


def test_bosses_match_by_encounter_id_whatever_adds_were_present() -> None:
    ours = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9, 10)),)})
    theirs = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9,)),)})
    alignment = align_pulls(ours, theirs)
    assert [(m.ours_index, m.theirs_index) for m in alignment.matched] == [(0, 0)]


def test_a_boss_never_matches_a_trash_pull_with_the_same_enemies() -> None:
    ours = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9,)),)})
    alignment = align_pulls(ours, a_run((9,)))
    assert alignment.matched == ()


def test_matched_share_counts_our_trash_pulls_with_a_counterpart() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,), (4,)), a_run((1,), (2,)))
    assert alignment.matched_share == 0.5


def test_a_run_with_no_trash_pulls_has_a_full_matched_share() -> None:
    ours = a_run().model_copy(update={"pulls": (a_boss(0, 3207, (9,)),)})
    assert align_pulls(ours, ours).matched_share == 1.0


def test_pairs_that_break_the_reference_order_are_out_of_order() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((2,), (1,), (3,)))
    assert len(alignment.out_of_order) == 1
    assert alignment.only_ours == () and alignment.only_theirs == ()


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
    """An adjacent swap is one pair sitting outside the longest shared order.

    Both packs find their counterpart, so neither route has a leftover. Our
    pulls 0 and 2 line up with their pulls 1 and 2 in increasing order; our pull
    1 is the one that would have to move, and that is what `out_of_order`
    surfaces.
    """
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((2,), (1,), (3,)))

    assert [(m.ours_index, m.theirs_index) for m in alignment.out_of_order] == [(1, 0)]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()


def test_a_pack_we_pulled_twice_matches_their_single_pull_of_it_twice() -> None:
    """A pack fought twice on our route and once on theirs leaves nothing unmatched.

    Both of our pulls contain the same enemy types as theirs, so both are
    counterparts of it. Only the first of the two can follow their order, so the
    second is what reordering surfaces.
    """
    alignment = align_pulls(a_run((1,), (2,), (2,)), a_run((2,), (1,)))

    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [
        (0, 1), (1, 0), (2, 0),
    ]
    assert [(m.ours_index, m.theirs_index) for m in alignment.out_of_order] == [(1, 0), (2, 0)]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()
