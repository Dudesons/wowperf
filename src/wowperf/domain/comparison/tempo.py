# ABOUTME: Compares deaths, missed interrupts and downtime against a reference run.
# ABOUTME: Withholds every duration-shaped number when the two keystone levels differ.

from wowperf.domain.analysis.interrupts import reconstruct_enemy_casts
from wowperf.domain.analysis.timeline import gaps_between_pulls
from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun


def _downtime_seconds(loaded: LoadedRun) -> float:
    """Seconds spent between pulls — walking, not fighting.

    Reuses the timeline analyser's definition so the report never carries two
    different numbers for the same idea.
    """
    return sum(gap.seconds for gap in gaps_between_pulls(loaded.run))


def _kick_counts(loaded: LoadedRun) -> tuple[int, int]:
    """(kicked, landed) enemy casts, by the documented reconstruction rule."""
    casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)
    kicked = sum(1 for cast in casts if cast.was_kicked)
    landed = sum(1 for cast in casts if cast.landed)
    return kicked, landed


def compare_tempo(ours: LoadedRun, theirs: LoadedRun, rule: Comparability) -> list[Finding]:
    """The group-axis comparisons that are not about the route."""
    findings: list[Finding] = []

    our_downtime = _downtime_seconds(ours)
    their_downtime = _downtime_seconds(theirs)
    excess = our_downtime - their_downtime
    findings.append(
        Finding(
            id="compare.downtime",
            title=(
                f"We spent {our_downtime:.0f}s between packs, the reference spent "
                f"{their_downtime:.0f}s"
            ),
            detail=(
                "Time between pulls is travel, run-backs and waiting. It does not depend on how "
                "much health a mob had, so it compares cleanly even across a keystone-level gap."
            ),
            confidence=Confidence.MEASURED,
            # Only an excess is a loss. Beating the reference is not worth negative seconds.
            seconds_lost=excess if excess > 0 else None,
            evidence=(
                f"ours {our_downtime:.0f}s",
                f"theirs {their_downtime:.0f}s",
                f"{len(gaps_between_pulls(ours.run))} gaps on our route",
            ),
        )
    )

    findings.append(
        Finding(
            id="compare.deaths",
            title=f"We died {len(ours.deaths)} times, the reference died {len(theirs.deaths)}",
            detail=(
                "A death count compares across keystone levels; what a death costs does not "
                "need restating here."
            ),
            confidence=Confidence.MEASURED,
            # deaths.total already prices our deaths in seconds. Pricing them again
            # here would count the same loss twice in one report.
            seconds_lost=None,
            evidence=(
                f"ours {len(ours.deaths)}",
                f"theirs {len(theirs.deaths)}",
                "seconds for our own deaths are reported by deaths.total",
            ),
        )
    )

    our_kicked, our_landed = _kick_counts(ours)
    their_kicked, their_landed = _kick_counts(theirs)
    findings.append(
        Finding(
            id="compare.interrupts",
            title=(
                f"We kicked {our_kicked} of {our_kicked + our_landed} resolved casts, "
                f"the reference kicked {their_kicked} of {their_kicked + their_landed}"
            ),
            detail=(
                "Outcomes are reconstructed on both sides by the same documented rule, and "
                "casts the log does not resolve are excluded rather than counted as missed. "
                "Neither side's log records which casts could be interrupted at all."
            ),
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"ours {our_kicked} kicked, {our_landed} landed",
                f"theirs {their_kicked} kicked, {their_landed} landed",
            ),
        )
    )

    if rule.durations_comparable:
        our_time = ours.run.keystone_time_seconds
        their_time = theirs.run.keystone_time_seconds
        behind = our_time - their_time
        findings.append(
            Finding(
                id="compare.duration",
                title=f"We finished in {our_time:.0f}s, the reference in {their_time:.0f}s",
                detail=(
                    "Both runs are the same keystone level, so the official times mean the same "
                    "thing and can be compared directly."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=behind if behind > 0 else None,
                evidence=(f"ours {our_time:.0f}s", f"theirs {their_time:.0f}s"),
            )
        )
    else:
        findings.append(
            Finding(
                id="compare.duration",
                title="Completion times are not compared",
                detail=rule.withheld_because(),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"our key +{rule.our_level}",
                    f"reference key +{rule.their_level}",
                    "route, deaths, interrupts and downtime are still compared",
                ),
            )
        )

    return findings
