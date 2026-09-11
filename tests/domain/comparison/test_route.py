# ABOUTME: Behaviour tests for turning a route alignment into findings a reader can act on.
# ABOUTME: The headline is what a faster group skipped, priced with our own clock.

from wowperf.domain.comparison.alignment import MIN_ALIGNED_SHARE, align_pulls
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.route import (
    MAX_PACKS_REPORTED,
    compare_route,
    compare_route_sample,
)
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample
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


# --- compare_route_sample -------------------------------------------------
#
# Eight trash pulls, indices 0..7, each fighting one enemy type it alone
# fights (game id = index + 1). Pull 7 runs 42s; every other pull runs the
# 60s default. A member is built by aligning one of these fixtures against
# OUR_RUN, so `only_ours` / `only_theirs` land on exactly the indices the
# fixture omits or adds.

OUR_RUN = a_run(tuple(a_pull(i, (i + 1,), seconds=42.0 if i == 7 else 60.0) for i in range(8)))


def a_speed_row(report_code: str = "REF1", fight_id: int = 1) -> SpeedRow:
    return SpeedRow(
        report_code=report_code,
        fight_id=fight_id,
        keystone_level=16,
        duration_ms=1_000_000,
        deaths=0,
    )


def member_missing(indices: tuple[int, ...], report_code: str = "REF1") -> SpeedMember:
    """A reference that fought every one of our packs except the ones named."""
    theirs = a_run(tuple(a_pull(i, (i + 1,)) for i in range(8) if i not in indices))
    return SpeedMember(
        row=a_speed_row(report_code=report_code),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=16),
        alignment=align_pulls(OUR_RUN, theirs),
    )


def member_missing_pull_7(report_code: str = "REF1") -> SpeedMember:
    return member_missing((7,), report_code=report_code)


def member_full(report_code: str = "REF1") -> SpeedMember:
    return member_missing((), report_code=report_code)


def member_with_extra_pack(report_code: str = "REF1") -> SpeedMember:
    """A reference that fought every one of our packs, plus one we never pulled."""
    theirs = a_run(
        (
            *tuple(a_pull(i, (i + 1,)) for i in range(8)),
            a_pull(8, (99,), name="Bonus Pack"),
        )
    )
    return SpeedMember(
        row=a_speed_row(report_code=report_code),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=16),
        alignment=align_pulls(OUR_RUN, theirs),
    )


def member_reordered(report_code: str = "REF1") -> SpeedMember:
    """A reference that fought every one of our packs, with pulls 0 and 1 swapped."""
    theirs = a_run(
        (
            a_pull(0, (2,)),
            a_pull(1, (1,)),
            *tuple(a_pull(i, (i + 1,)) for i in range(2, 8)),
        )
    )
    return SpeedMember(
        row=a_speed_row(report_code=report_code),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=16),
        alignment=align_pulls(OUR_RUN, theirs),
    )


def test_a_wholly_empty_sample_produces_no_findings() -> None:
    # `SpeedSample()` with no members at all is the type's own zero-argument
    # default. `service.compare()` already says "nothing to compare against"
    # once, as `compare.speed.unavailable`; this must not crash, and must not
    # say it again.
    findings = compare_route_sample(OUR_RUN, SpeedSample(), forces={})

    assert findings == []


def test_a_pack_every_reference_skipped_is_counted_in_the_title() -> None:
    sample = SpeedSample(
        members=(member_missing_pull_7(), member_missing_pull_7(), member_missing_pull_7())
    )

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.title == "3 of 3 fast runs skipped the pack at pull 7"
    assert skipped.quantifier == "every"
    assert skipped.confidence is Confidence.MEASURED


def test_the_price_of_a_skipped_pack_is_our_own_pull_duration() -> None:
    sample = SpeedSample(
        members=(member_missing_pull_7(), member_missing_pull_7(), member_missing_pull_7())
    )

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.seconds_lost == 42.0


def test_a_pack_only_some_references_skipped_says_so() -> None:
    # Two of five route-eligible members skipped pull 7. 2 of 3 would round up
    # to "most" under quantifier_for, so five members are used to land on the
    # "some" wording this test is about.
    sample = SpeedSample(
        members=(
            member_missing_pull_7(),
            member_missing_pull_7(),
            member_full(),
            member_full(),
            member_full(),
        )
    )

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.title == "2 of 5 fast runs skipped the pack at pull 7"
    assert skipped.quantifier == "some"


def test_below_the_floor_the_pairwise_wording_is_used() -> None:
    sample = SpeedSample(members=(member_missing_pull_7(),))

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.title == "The reference skipped the pack at pull 7"
    assert any("below the floor of" in line for line in skipped.evidence)


def test_below_the_floor_one_eligible_member_reads_as_singular_english() -> None:
    # eligible == 1 must read "1 of the sample was comparable", not "were" — and
    # not as "one reference ... 1 of the sample", which restates the same count twice.
    sample = SpeedSample(members=(member_missing_pull_7(),))

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert any("1 of the sample was comparable" in line for line in skipped.evidence)


def test_no_finding_reports_a_different_pull_order() -> None:
    sample = SpeedSample(members=(member_reordered(), member_reordered(), member_reordered()))

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    assert not any(f.id == "compare.route.order" for f in findings)


def test_the_summary_states_our_count_against_the_samples_observed_range() -> None:
    sample = SpeedSample(members=(member_missing((7,)), member_missing((6, 7)), member_full()))

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    summary = next(f for f in findings if f.id == "compare.route.summary")
    assert summary.title == "We pulled 8 packs; the 3 fast runs pulled 6 to 8"
    assert summary.confidence is Confidence.MEASURED
    assert "3 of 3 references aligned well enough to price a skip" in summary.evidence


def test_the_summary_discloses_how_many_of_the_sample_could_price_a_skip() -> None:
    """A member whose route did not line up is dropped from every skipped-pack
    count and raises no finding of its own, so the summary is the only place a
    reader can learn why route rows carry a smaller denominator than tempo rows
    on the same page."""
    stranger = member_missing((3, 4, 5, 6, 7), report_code="ODD")
    sample = SpeedSample(
        members=(
            member_missing_pull_7(),
            member_missing_pull_7(),
            member_missing_pull_7(),
            stranger,
            stranger,
        )
    )
    # The fixture's own premise: two of the five matched 3 of our 8 trash pulls.
    assert len(sample.route_eligible) == 3

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    summary = next(f for f in findings if f.id == "compare.route.summary")
    assert "3 of 5 references aligned well enough to price a skip" in summary.evidence
    # The count is over the eligible three, not the whole five, even though the
    # two dropped members also never pulled pack 7.
    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.title == "3 of 3 fast runs skipped the pack at pull 7"
    assert not any(f.id == "compare.route.unaligned" for f in findings)


def test_extra_packs_are_reported_pairwise_against_the_first_eligible_member_only() -> None:
    # Two members share the same extra pack. If it were counted across the
    # sample this would read "2 of 3"; instead it stays one finding, named to
    # the first eligible member alone.
    sample = SpeedSample(
        members=(
            member_with_extra_pack(report_code="EXTRA1"),
            member_with_extra_pack(report_code="EXTRA2"),
            member_full(),
        )
    )

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    extra = findings_by_prefix(findings, "compare.route.extra.")
    assert len(extra) == 1
    assert "EXTRA1" in extra[0].detail
    assert "EXTRA2" not in extra[0].detail


def test_the_extra_finding_names_a_run_not_a_report_code_as_the_subject() -> None:
    # A report code is not a player identity, but it should not be the
    # grammatical subject of "killed" either -- a run does the killing, and
    # the identifiers stay available to a reader in parentheses. Matches the
    # wording `compare_route`'s own pairwise block uses ("They killed a
    # pack...").
    sample = SpeedSample(
        members=(member_with_extra_pack(report_code="REF1"), member_full(), member_full())
    )

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    extra = findings_by_prefix(findings, "compare.route.extra.")[0]
    assert extra.detail.startswith("One fast run (report REF1, fight 1) killed a pack")


# --- pulls that cannot honestly be priced ---------------------------------
#
# Warcraft Logs closes and reopens a pull mid-engagement, leaving a pull of a
# few milliseconds whose enemies are a subset of the one before it, and it
# records pulls with no enemies at all. Neither is a pack anybody skipped.

ARTEFACT_RUN = a_run(
    (
        *tuple(a_pull(i, (i + 1,)) for i in range(6)),
        a_pull(6, (90,), seconds=93.0, name="Real Pack"),
        a_pull(7, (91,), seconds=0.048, name="Tail"),
    )
)


def artefact_member(missing: tuple[int, ...], report_code: str = "REF1") -> SpeedMember:
    """A reference that fought every pull of ARTEFACT_RUN except the ones named."""
    theirs = a_run(tuple(pull for pull in ARTEFACT_RUN.pulls if pull.index not in missing))
    return SpeedMember(
        row=a_speed_row(report_code=report_code),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=16),
        alignment=align_pulls(ARTEFACT_RUN, theirs),
    )


def test_a_sub_second_pull_is_not_priced_as_a_pack_the_reference_skipped() -> None:
    ours = a_run(
        (
            a_pull(0, (1,)),
            a_pull(1, (2,)),
            a_pull(2, (3,)),
            a_pull(3, (4,), seconds=0.048, name="Tail"),
            a_pull(4, (5,), seconds=93.0, name="Real Pack"),
        )
    )
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert [finding.pull_index for finding in skipped] == [4]
    assert skipped[0].seconds_lost == 93.0


def test_a_pull_with_no_recorded_enemies_is_not_priced_as_a_pack_the_reference_skipped() -> None:
    # `align_pulls` never offers a counterpart to a pull with no enemies, so it
    # always lands in `only_ours`. That says nothing about the reference's route.
    ours = a_run(
        (
            a_pull(0, (1,)),
            a_pull(1, (2,)),
            a_pull(2, (3,)),
            a_pull(3, ()),
            a_pull(4, (5,), seconds=93.0, name="Real Pack"),
        )
    )
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert [finding.pull_index for finding in skipped] == [4]


def test_a_pack_one_second_long_is_still_priced_as_skipped() -> None:
    # The floor is the resolution of the finding's own claim, not a judgement
    # about small packs: at one second it can still say what it cost.
    ours = a_run(
        (a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,)), a_pull(3, (4,), seconds=1.0))
    )
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert [finding.pull_index for finding in skipped] == [3]
    assert skipped[0].seconds_lost == 1.0


def test_a_reference_artefact_pull_is_not_reported_as_a_pack_we_did_not_pull() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run(
        (
            a_pull(0, (1,)),
            a_pull(1, (2,)),
            a_pull(2, (98,), seconds=0.03, name="Their Tail"),
            a_pull(3, (99,), name="Bonus Pack"),
        )
    )

    findings = compare_route(ours, theirs, align_pulls(ours, theirs), {})
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert [finding.evidence[0] for finding in extra] == ["Bonus Pack"]


def test_an_artefact_pull_does_not_outrank_the_pack_the_sample_really_skipped() -> None:
    # Agreement sorts before price here, and no reference ever pulls a pack that
    # existed for 48ms, so an artefact draws unanimous agreement by construction
    # and takes the top row from a pack that really was skipped.
    sample = SpeedSample(
        members=(
            artefact_member((7,), report_code="REF1"),
            artefact_member((7,), report_code="REF2"),
            artefact_member((6, 7), report_code="REF3"),
        )
    )

    findings = compare_route_sample(ARTEFACT_RUN, sample, forces={})
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert [finding.pull_index for finding in skipped] == [6]
    assert skipped[0].title == "1 of 3 fast runs skipped the pack at pull 6"


def test_the_sampled_summary_states_how_well_the_pulls_matched() -> None:
    # The pairwise summary states this and the sampled one did not, so a reader
    # could not tell whether the rows below rested on a whole route lining up or
    # on the bare minimum.
    sample = SpeedSample(members=(member_full(), member_missing_pull_7(), member_missing((5, 6))))

    findings = compare_route_sample(OUR_RUN, sample, forces={})
    summary = next(f for f in findings if f.id == "compare.route.summary")

    assert "6 to 8 of our 8 trash pulls matched" in summary.evidence


def test_a_reference_artefact_pull_is_not_reported_as_extra_on_the_sampled_path() -> None:
    theirs = a_run(
        (
            *tuple(a_pull(i, (i + 1,)) for i in range(8)),
            a_pull(8, (98,), seconds=0.03, name="Their Tail"),
            a_pull(9, (99,), name="Bonus Pack"),
        )
    )
    member = SpeedMember(
        row=a_speed_row(),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=16),
        alignment=align_pulls(OUR_RUN, theirs),
    )
    sample = SpeedSample(members=(member, member_full("REF2"), member_full("REF3")))

    findings = compare_route_sample(OUR_RUN, sample, forces={})
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert [finding.evidence[0] for finding in extra] == ["Bonus Pack"]
