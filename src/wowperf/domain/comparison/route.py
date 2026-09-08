# ABOUTME: Turns a route alignment into findings: what a faster group skipped, and what we added.
# ABOUTME: Every second here is measured on our own clock, so a keystone gap cannot distort it.

from collections import Counter
from collections.abc import Mapping, Sequence

from wowperf.domain.comparison.alignment import MIN_ALIGNED_SHARE, Alignment
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample, too_few
from wowperf.domain.comparison.statistics import count_phrase, observed_range
from wowperf.domain.findings import Confidence, Finding, quantifier_for
from wowperf.domain.model import Pull, Run

MAX_PACKS_REPORTED = 5
"""Beyond five packs a reader stops reading and starts skimming."""


def _pull_by_index(run: Run, index: int) -> Pull | None:
    return next((pull for pull in run.pulls if pull.index == index), None)


def compare_route(
    ours: Run, theirs: Run, alignment: Alignment, forces: Mapping[int, int]
) -> list[Finding]:
    """What the two routes did differently, priced where we honestly can.

    `forces` is enemy forces per pull index of our run, summed from enemy deaths
    by `analysis.trash.forces_by_pull`, so the route and the trash findings
    price the same pull with the same number.
    """
    matched_trash = round(alignment.matched_share * alignment.our_trash_count)
    in_common = len({match.ours_index for match in alignment.matched})
    findings: list[Finding] = [
        Finding(
            id="compare.route.summary",
            title=(
                f"We pulled {len(ours.pulls)} "
                f"pack{'s' if len(ours.pulls) != 1 else ''}, "
                f"the reference pulled {len(theirs.pulls)}"
            ),
            detail=(
                f"{matched_trash} of {alignment.our_trash_count} trash "
                f"pull{'s' if alignment.our_trash_count != 1 else ''} found a counterpart. "
                "Packs are matched by which enemies they contain, not by when either group "
                "fought them, so this comparison holds across a keystone-level difference. A "
                "stretch fought without a break is one pull to Warcraft Logs, and it matches "
                "each of the separate pulls it covers."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"{in_common} pack{'s' if in_common != 1 else ''} in common",
                f"{len(alignment.only_ours)} only ours",
                f"{len(alignment.only_theirs)} only theirs",
                f"{len(alignment.out_of_order)} reordered",
            ),
        )
    ]

    if alignment.matched_share < MIN_ALIGNED_SHARE:
        findings.append(
            Finding(
                id="compare.route.unaligned",
                title=(
                    f"Only {matched_trash} of {alignment.our_trash_count} trash pulls could be "
                    "matched to the reference's"
                ),
                detail=(
                    "The two logs cut the route into pulls differently — a chain of packs "
                    "fought without a break is one pull to Warcraft Logs — so no pack is priced "
                    "as skipped or listed as extra. The timeline still shows both routes."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"{len(alignment.only_ours)} of our pulls without a counterpart",
                    f"{len(alignment.only_theirs)} of theirs without a counterpart",
                ),
            )
        )
        return findings

    # Only trash pulls can be skipped. A boss in only_ours means the reference
    # took a different route through the dungeon, not that anyone skipped a
    # boss, so bosses are excluded from the skipped findings entirely.
    skippable = [
        pull
        for index in alignment.only_ours
        if (pull := _pull_by_index(ours, index)) is not None and not pull.is_boss
    ]
    skippable.sort(key=lambda pull: pull.duration_seconds, reverse=True)

    for rank, pull in enumerate(skippable[:MAX_PACKS_REPORTED]):
        forces_awarded = forces.get(pull.index, 0)
        findings.append(
            Finding(
                id=f"compare.route.skipped.{rank}",
                title=f"The reference skipped the pack at pull {pull.index}",
                detail=(
                    f"We spent {pull.duration_seconds:.0f}s on a pack the faster group never "
                    f"pulled. It awarded {forces_awarded} enemy forces."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=pull.duration_seconds,
                evidence=(
                    pull.name,
                    f"{forces_awarded} enemy forces",
                    f"{len(pull.enemies)} enem{'y' if len(pull.enemies) == 1 else 'ies'}",
                ),
                pull_index=pull.index,
            )
        )

    # A pack only they killed carries no seconds: we have no clock for a pull
    # we never did, and pricing it with their duration would import a number
    # from the other side of a keystone gap. Bosses are excluded here too,
    # for the same routing reason as above.
    extra = [
        pull
        for index in alignment.only_theirs
        if (pull := _pull_by_index(theirs, index)) is not None and not pull.is_boss
    ]
    for rank, pull in enumerate(extra[:MAX_PACKS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.route.extra.{rank}",
                title=f"The reference pulled a pack we did not, at their pull {pull.index}",
                detail=(
                    "They killed a pack that is not on our route. No seconds are attached: we "
                    "have no clock for a pull we never did."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    pull.name,
                    f"{len(pull.enemies)} enem{'y' if len(pull.enemies) == 1 else 'ies'}",
                ),
            )
        )

    return findings


def compare_route_sample(
    ours: Run, sample: SpeedSample, forces: Mapping[int, int]
) -> list[Finding]:
    """What the sample's routes did differently from ours, priced on our own clock.

    Only route-eligible members are counted: a member whose pulls did not line
    up with ours cannot say whether a pack was skipped or merely cut
    differently, and counting it would put the largest wrong number on the page.
    """
    if not sample.members:
        # A wholly empty sample means there was nothing to compare against at
        # all. `service.compare()` already says so, once, as
        # `compare.speed.unavailable`; saying it again here would duplicate
        # that finding, and there is no member to fall back on for the
        # pairwise path below, so silence is the only answer that is not a
        # crash or a repeat.
        return []

    eligible = sample.route_eligible
    if not sample.can_aggregate(eligible):
        first = eligible[0] if eligible else sample.members[0]
        return too_few(compare_route(ours, first.run, first.alignment, forces), len(eligible))

    findings = [_summary(ours, eligible), *_skipped(ours, eligible, forces)]
    findings += _extra_from(eligible[0], ours)
    return findings


def _summary(ours: Run, eligible: Sequence[SpeedMember]) -> Finding:
    """Our pull count against the range the sample actually pulled.

    A pull count is a routing choice, not a measurement with sampling noise to
    average away, so the sample states its spread rather than a mean.
    """
    total = len(eligible)
    low, high = observed_range([float(len(member.run.pulls)) for member in eligible])
    return Finding(
        id="compare.route.summary",
        title=(
            f"We pulled {len(ours.pulls)} packs; the {total} fast runs pulled "
            f"{low:.0f} to {high:.0f}"
        ),
        detail=(
            "Pack counts are compared as a range, not averaged: how a route is cut into pulls "
            "is a routing choice, and a mean over routing choices is not a statistic a reader "
            "can act on."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"{total} fast runs compared",
            f"observed range {low:.0f} to {high:.0f} packs",
        ),
    )


def _skipped(
    ours: Run, eligible: Sequence[SpeedMember], forces: Mapping[int, int]
) -> list[Finding]:
    """Packs from our route that a route-eligible member's alignment left unmatched.

    A pull is tallied once per member whose alignment placed it in `only_ours`,
    so the count is how many of the sample agree the pack was skipped.
    """
    counts: Counter[int] = Counter()
    for member in eligible:
        counts.update(member.alignment.only_ours)

    skippable = [
        (pull, counts[pull.index])
        for index in counts
        if (pull := _pull_by_index(ours, index)) is not None and not pull.is_boss
    ]
    skippable.sort(key=lambda row: (row[1], row[0].duration_seconds), reverse=True)

    total = len(eligible)
    findings = []
    for rank, (pull, matching) in enumerate(skippable[:MAX_PACKS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.route.skipped.{rank}",
                title=(
                    f"{count_phrase(matching, total)} fast runs skipped the pack "
                    f"at pull {pull.index}"
                ),
                detail=(
                    f"We spent {pull.duration_seconds:.0f}s on it. It awarded "
                    f"{forces.get(pull.index, 0)} enemy forces. The seconds are our own: a "
                    "reference's clock never prices one of our packs."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=pull.duration_seconds,
                evidence=(
                    pull.name,
                    f"{forces.get(pull.index, 0)} enemy forces",
                    f"{total - matching} of {total} pulled it too",
                ),
                quantifier=quantifier_for(matching, total),
                pull_index=pull.index,
            )
        )
    return findings


def _extra_from(member: SpeedMember, ours: Run) -> list[Finding]:
    """Packs one route-eligible reference pulled that we did not.

    Pairwise against a single member, named in the finding rather than counted
    across the sample: `align_pulls` matches packs by containment, not by a
    shared signature, so grouping extra packs across members would need a
    clustering rule this comparison does not have.
    """
    theirs = member.run
    extra = [
        pull
        for index in member.alignment.only_theirs
        if (pull := _pull_by_index(theirs, index)) is not None and not pull.is_boss
    ]
    findings = []
    for rank, pull in enumerate(extra[:MAX_PACKS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.route.extra.{rank}",
                title=f"A fast run pulled a pack we did not, at their pull {pull.index}",
                detail=(
                    f"One fast run (report {member.row.report_code}, fight "
                    f"{member.row.fight_id}) killed a pack that is not on our route. No "
                    "seconds are attached: we have no clock for a pull we never did. This is "
                    "one reference from the sample, not a count across it: packs are matched "
                    "by containment, not a shared signature, so grouping extra packs across "
                    "references would need a clustering rule this comparison does not have."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    pull.name,
                    f"{len(pull.enemies)} enem{'y' if len(pull.enemies) == 1 else 'ies'}",
                ),
            )
        )
    return findings
