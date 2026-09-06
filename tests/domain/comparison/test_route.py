# ABOUTME: Behaviour tests for turning a route alignment into findings a reader can act on.
# ABOUTME: The headline is what a faster group skipped, priced with our own clock.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.route import (
    MAX_PACKS_REPORTED,
    MIN_ALIGNED_SHARE,
    compare_route,
)
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import EnemyNpc, Pull, Run


def a_pull(
    index: int,
    game_ids: tuple[int, ...],
    seconds: float = 60.0,
    boss: bool = False,
    name: str | None = None,
) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name=name if name is not None else ("Boss" if boss else "Pack"),
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + int(seconds * 1000),
        killed=True,
        x=100 + index,
        y=200 + index,
        enemies=tuple(
            EnemyNpc(actor_id=100 + n, game_id=game_id) for n, game_id in enumerate(game_ids)
        ),
    )


def a_run(pulls: tuple[Pull, ...], counts: tuple[tuple[int, int], ...] = ()) -> Run:
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
        npc_counts=counts,
        players=(),
        pulls=pulls,
    )


def findings_by_prefix(findings: list[Finding], prefix: str) -> list[Finding]:
    return [finding for finding in findings if finding.id.startswith(prefix)]


def test_a_pack_they_skipped_is_priced_with_our_own_clock() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=45.0), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {1: 12})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert len(skipped) == 1
    assert skipped[0].seconds_lost == 45.0
    assert skipped[0].confidence is Confidence.MEASURED
    assert skipped[0].pull_index == 1
    assert any("12" in line for line in skipped[0].evidence)


def test_a_skipped_pack_is_priced_by_the_forces_its_deaths_awarded() -> None:
    # Two copies of one NPC type died in the skipped pull. Pricing by type would say 6.
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))
    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {1: 12})
    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert "12 enemy forces" in skipped.evidence
    assert "It awarded 12 enemy forces." in skipped.detail


def test_a_boss_is_never_reported_as_a_skipped_pack() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))
    theirs = a_run((a_pull(0, (1,)),))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})

    assert findings_by_prefix(findings, "compare.route.skipped.") == []


def test_a_boss_is_never_reported_as_an_extra_pack() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})

    assert findings_by_prefix(findings, "compare.route.extra.") == []


def test_a_pack_only_they_killed_carries_no_seconds() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=77.0)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert len(extra) == 1
    assert extra[0].seconds_lost is None


def test_the_extra_pack_evidence_carries_no_duration() -> None:
    """A cross-gap duration would import a number from the other side of a keystone
    gap; the pack's name and enemy count already identify it without one."""
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=77.0)))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    extra = findings_by_prefix(findings, "compare.route.extra.")[0]

    assert not any("77" in line or "lasted" in line for line in extra.evidence)


def test_the_extra_pack_detail_makes_no_claim_about_keystone_levels() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    extra = findings_by_prefix(findings, "compare.route.extra.")[0]

    assert "keystone" not in extra.detail.lower()
    assert "level" not in extra.detail.lower()


def test_the_evidence_names_the_pack_for_both_skipped_and_extra_findings() -> None:
    ours = a_run(
        (a_pull(0, (1,)), a_pull(1, (2,), name="Thornclaw Gatherer")),
        counts=((2, 12),),
    )
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,), name="Spirit of Hunger")))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert skipped[0].evidence[0] == "Thornclaw Gatherer"
    assert extra[0].evidence[0] == "Spirit of Hunger"


def test_the_summary_counts_both_routes() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run((a_pull(0, (1,)),))

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs), {}),
                                 "compare.route.summary")[0]

    assert "2" in summary.title
    assert "1" in summary.title
    assert summary.seconds_lost is None


def test_the_summary_evidence_accounts_for_every_pull_including_reordered_ones() -> None:
    """A swap leaves every pack matched, so the reordering is the only trace of it.

    `out_of_order` is a view of `matched`, not a fourth bucket: with nothing in
    `only_ours` or `only_theirs`, the reordered count is what tells the reader the
    two routes did the same packs in a different sequence."""
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,)), a_pull(2, (3,))))

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs), {}),
                                 "compare.route.summary")[0]

    assert any("reordered" in line for line in summary.evidence)
    assert not any(line.startswith("0 reordered") for line in summary.evidence)


def test_the_summary_pluralises_a_single_pack_correctly() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = ours

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs), {}),
                                 "compare.route.summary")[0]

    assert "1 pack," in summary.title
    assert "1 packs" not in summary.title
    assert "1 of 1 trash pull found a counterpart" in summary.detail
    assert "1 pack in common" in " ".join(summary.evidence)


def test_a_single_enemy_pack_is_singular_in_skipped_evidence() -> None:
    # More than half our trash pulls must align for any pack to be priced. Three
    # of four align here, clear of the threshold by a full pull, so the pack
    # under test is skipped beside the ones both routes share.
    ours = a_run(
        (a_pull(0, (9,)), a_pull(1, (1,)), a_pull(2, (8,)), a_pull(3, (7,))),
        counts=((1, 5),),
    )
    theirs = a_run((a_pull(0, (9,)), a_pull(1, (8,)), a_pull(2, (7,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")[0]

    assert "1 enemy" in skipped.evidence
    assert "1 enemies" not in skipped.evidence


def test_a_single_reordered_pack_is_singular_and_uses_was() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,))))

    order = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs), {}),
                               "compare.route.order")[0]

    assert order.title == "1 pack was taken in a different order"


def test_only_the_worst_packs_are_reported() -> None:
    # Eight packs they skipped, each one second shorter than the last, beside
    # ten both routes share — one full pull clear of the threshold this test
    # is not about.
    shared_pulls = tuple(a_pull(index, (index + 1,)) for index in range(10))
    skipped_pulls = tuple(
        a_pull(index, (index + 30,), seconds=float(60 - index)) for index in range(10, 18)
    )
    ours = a_run((*shared_pulls, *skipped_pulls))
    theirs = a_run(shared_pulls)

    skipped = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs), {}),
                                 "compare.route.skipped.")

    assert len(skipped) == MAX_PACKS_REPORTED
    seconds = [finding.seconds_lost for finding in skipped]

    def as_sortable(value: float | None) -> float:
        return value if value is not None else float("-inf")

    assert seconds == sorted(seconds, key=as_sortable, reverse=True)


def test_a_reordered_route_is_reported_once() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,)), a_pull(2, (3,))))

    order = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs), {}),
                               "compare.route.order")

    assert len(order) <= 1


def test_identical_routes_report_only_the_summary() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, ours, align_pulls(ours, ours), {})

    assert [finding.id for finding in findings] == ["compare.route.summary"]


def test_no_finding_prints_a_map_position() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=45.0), a_pull(2, (3,))),
                 counts=((2, 12),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    for finding in findings:
        for line in finding.evidence:
            assert "map position" not in line, finding.id


def test_the_summary_states_how_many_trash_pulls_found_a_counterpart() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,)), a_pull(3, (4,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    summary = compare_route(ours, theirs, align_pulls(ours, theirs), {})[0]

    assert summary.id == "compare.route.summary"
    assert "2 of 4 trash pulls found a counterpart" in summary.detail


def test_below_the_aligned_share_no_pack_is_priced_as_skipped() -> None:
    # One of five trash pulls aligned: the two logs cut the route differently.
    ours = a_run(
        (a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,)), a_pull(3, (4,)), a_pull(4, (5,)))
    )
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (6,)), a_pull(2, (7,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {1: 10})
    ids = [f.id for f in findings]

    assert "compare.route.unaligned" in ids
    assert not any(i.startswith("compare.route.skipped.") for i in ids)
    assert not any(i.startswith("compare.route.extra.") for i in ids)
    assert "compare.route.order" not in ids
    unaligned = next(f for f in findings if f.id == "compare.route.unaligned")
    assert unaligned.seconds_lost is None
    assert unaligned.confidence is Confidence.MEASURED
    assert "1 of 5" in unaligned.title


def test_at_the_aligned_share_packs_are_priced() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,)), a_pull(3, (4,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})

    assert any(f.id.startswith("compare.route.skipped.") for f in findings)
    assert MIN_ALIGNED_SHARE == 0.5


def test_every_finding_id_is_unique() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (4,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    ids = [finding.id for finding in compare_route(ours, theirs, align_pulls(ours, theirs), {})]

    assert len(ids) == len(set(ids))
