# ABOUTME: Behaviour tests for lining two pull sequences up by what each pack was made of.
# ABOUTME: The interesting cases are a skipped pack, an extra pack, and a reordered route.

from wowperf.domain.comparison.alignment import PullMatch, align_pulls
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


def test_matched_share_subtracts_matched_boss_pulls_from_the_numerator() -> None:
    # Two boss pulls, matched on both sides, plus four trash pulls of which two
    # match. Without subtracting the bosses from the numerator, matched_ours
    # would hold all six indices over four trash pulls and the share would
    # read 1.5, not 0.5.
    ours = a_run().model_copy(
        update={
            "pulls": (
                a_boss(0, 3207, (90,)),
                a_boss(1, 3208, (91,)),
                a_pull(2, (1,)),
                a_pull(3, (2,)),
                a_pull(4, (3,)),
                a_pull(5, (4,)),
            )
        }
    )
    theirs = a_run().model_copy(
        update={
            "pulls": (
                a_boss(0, 3207, (90,)),
                a_boss(1, 3208, (91,)),
                a_pull(2, (1,)),
                a_pull(3, (2,)),
            )
        }
    )
    alignment = align_pulls(ours, theirs)
    assert alignment.matched_share == 0.5


def test_an_enemy_less_trash_pull_counts_against_the_share_and_lands_in_only_ours() -> None:
    # One trash pull with enemies (matches), one with none recorded (matches
    # nothing but still counts in the denominator).
    ours = a_run().model_copy(
        update={
            "pulls": (
                a_pull(0, (1,)),
                Pull(
                    index=1,
                    pull_id=2,
                    name="Pack",
                    encounter_id=0,
                    start_ms=100_000,
                    end_ms=160_000,
                    killed=True,
                    x=0,
                    y=0,
                    enemies=(),
                ),
            )
        }
    )
    theirs = a_run((1,))
    alignment = align_pulls(ours, theirs)
    assert alignment.matched_share == 0.5
    assert 1 in alignment.only_ours


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
    counterparts of it — and both pairs name the same reference index, so neither
    had to move for the two orders to agree. Fighting a pack twice is not a
    resequencing of the route, and the run in the same order reports none.
    """
    alignment = align_pulls(a_run((1,), (2,), (2,)), a_run((1,), (2,)))

    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [
        (0, 0), (1, 1), (2, 1),
    ]
    assert alignment.out_of_order == ()
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()


def test_a_pack_we_pulled_twice_beside_a_swap_reports_only_the_swap() -> None:
    """The same duplicate, on a route that genuinely resequenced two packs.

    We took pack 1 before pack 2 and they took pack 2 first, which is a real
    swap and is reported. Our second pull of pack 2 shares its counterpart with
    the first and is not a second reordering on top of it.
    """
    alignment = align_pulls(a_run((1,), (2,), (2,)), a_run((2,), (1,)))

    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [
        (0, 1), (1, 0), (2, 0),
    ]
    assert [(m.ours_index, m.theirs_index) for m in alignment.out_of_order] == [(0, 1)]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()


def test_a_large_pull_pairs_with_their_large_one_and_a_small_with_their_small() -> None:
    """Shared fraction decides the pairing, not the order the routes list packs in.

    A small pack that both groups fought, and a long chain containing it. Whichever
    way round the two routes list the pair, the chain is the chain's counterpart and
    the small pack is the small pack's.
    """
    small, chain = (1, 2), (1, 2, 3, 4, 5, 6, 7)

    forwards = align_pulls(a_run(small, chain), a_run(chain, small))
    assert sorted((m.ours_index, m.theirs_index) for m in forwards.matched) == [(0, 1), (1, 0)]

    backwards = align_pulls(a_run(chain, small), a_run(small, chain))
    assert sorted((m.ours_index, m.theirs_index) for m in backwards.matched) == [(0, 1), (1, 0)]


def test_an_exact_counterpart_already_paired_still_beats_a_distant_unpaired_one() -> None:
    """The real-run defect in miniature: preferring an unpaired candidate stole a pairing.

    We fought the same small pack twice; they fought it once, and also fought a long
    chain that happens to contain it. Ranking "not yet paired" above shared fraction
    handed our second pull of the pack to the 5-type chain it shares two types with,
    instead of to their identical pull of it.
    """
    alignment = align_pulls(a_run((1, 2), (1, 2)), a_run((1, 2), (1, 2, 3, 4, 5)))

    pairs = {(m.ours_index, m.theirs_index) for m in alignment.matched}
    assert (1, 0) in pairs
    assert (1, 1) not in pairs


def test_several_of_our_pulls_matched_to_one_of_theirs_are_in_order() -> None:
    """Two of our pulls covered by one of theirs is segmentation, not resequencing.

    Their single pull of {1, 2, 3} is the counterpart of both our {1, 2} and our
    {3}. Both pairs name the same reference index, so neither had to move for the
    orders to agree.
    """
    alignment = align_pulls(a_run((1, 2), (3,), (4,)), a_run((1, 2, 3), (4,)))

    assert alignment.out_of_order == ()


def test_the_earliest_unpaired_candidate_wins_a_tie() -> None:
    # Three identical trash pulls of theirs, one of ours: pass 1 picks the
    # earliest of the tied, unpaired candidates for our pull 0, and the
    # sweep-back then pairs the other two of theirs with our pull 0 as well.
    alignment = align_pulls(a_run((1,),), a_run((1,), (1,), (1,)))

    assert sorted((m.ours_index, m.theirs_index) for m in alignment.matched) == [
        (0, 0), (0, 1), (0, 2),
    ]
    # Pass 1 appends before the sweep-back, so the first match recorded for
    # our pull 0 is the tie-break itself: their pull 0.
    assert alignment.matched[0] == PullMatch(ours_index=0, theirs_index=0)
