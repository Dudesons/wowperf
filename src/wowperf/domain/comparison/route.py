# ABOUTME: Turns a route alignment into findings: what a faster group skipped, and what we added.
# ABOUTME: Every second here is measured on our own clock, so a keystone gap cannot distort it.

from collections.abc import Mapping

from wowperf.domain.comparison.alignment import Alignment
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Pull, Run

MAX_PACKS_REPORTED = 5
"""Beyond five packs a reader stops reading and starts skimming."""

MIN_ALIGNED_SHARE = 0.5
"""Below this share of our trash pulls with a counterpart, no pack is priced as skipped.

When the two logs cut the route into pulls differently, an unmatched pull is not
a skipped pack; it is a segmentation difference, and pricing it would put the
largest wrong number on the page at the top of the ledger.
"""


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

    drifted = alignment.out_of_order
    if drifted:
        findings.append(
            Finding(
                id="compare.route.order",
                title=(
                    f"{len(drifted)} pack{'s' if len(drifted) != 1 else ''} "
                    f"{'was' if len(drifted) == 1 else 'were'} taken in a different order"
                ),
                detail=(
                    "The same packs appear on both routes but in a different sequence. That is "
                    "usually a different path through the dungeon rather than a mistake, and it "
                    "is worth looking at next to the skipped packs above."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=tuple(
                    f"our pull {match.ours_index} is their pull {match.theirs_index}"
                    for match in drifted[:MAX_PACKS_REPORTED]
                ),
            )
        )

    return findings
