# ABOUTME: Turns a route alignment into findings: what a faster group skipped, and what we added.
# ABOUTME: Every second here is measured on our own clock, so a keystone gap cannot distort it.

from wowperf.domain.comparison.alignment import Alignment
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Pull, Run

MAX_PACKS_REPORTED = 5
"""Beyond five packs a reader stops reading and starts skimming."""


def _forces(run: Run, pull: Pull) -> int:
    """Enemy forces the pack awarded, priced by our own run's map.

    The reference's map may differ if the season retuned between the two runs;
    ours is the one that actually counted towards our key.
    """
    counts = run.npc_count_map
    return sum(counts.get(enemy.game_id, 0) for enemy in pull.enemies)


def _pull_by_index(run: Run, index: int) -> Pull | None:
    return next((pull for pull in run.pulls if pull.index == index), None)


def compare_route(ours: Run, theirs: Run, alignment: Alignment) -> list[Finding]:
    """What the two routes did differently, priced where we honestly can."""
    findings: list[Finding] = [
        Finding(
            id="compare.route.summary",
            title=(
                f"We pulled {len(ours.pulls)} packs, the reference pulled {len(theirs.pulls)}"
            ),
            detail=(
                f"{len(alignment.matched)} packs matched on composition. Packs are matched by "
                "which enemies they contain, not by when either group fought them, so this "
                "comparison holds across a keystone-level difference."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"{len(alignment.matched)} packs in common",
                f"{len(alignment.only_ours)} only ours",
                f"{len(alignment.only_theirs)} only theirs",
            ),
        )
    ]

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
        forces = _forces(ours, pull)
        findings.append(
            Finding(
                id=f"compare.route.skipped.{rank}",
                title=f"The reference skipped the pack at pull {pull.index}",
                detail=(
                    f"We spent {pull.duration_seconds:.0f}s on a pack the faster group never "
                    f"pulled. It awarded {forces} enemy forces."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=pull.duration_seconds,
                evidence=(
                    f"{forces} enemy forces",
                    f"{len(pull.enemies)} enemies",
                    f"map position x={pull.x}, y={pull.y}",
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
                    "have no clock for a pull we never did, and theirs was run at a different "
                    "keystone level."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"{len(pull.enemies)} enemies",
                    f"their pull lasted {pull.duration_seconds:.0f}s",
                ),
            )
        )

    drifted = alignment.out_of_order
    if drifted:
        findings.append(
            Finding(
                id="compare.route.order",
                title=f"{len(drifted)} packs were taken in a different order",
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
