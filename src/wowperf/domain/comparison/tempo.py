# ABOUTME: Compares deaths, missed interrupts and downtime against a reference run or a sample.
# ABOUTME: Withholds every duration-shaped number when the keystone levels involved differ.

from collections.abc import Sequence

from wowperf.domain.analysis.interrupts import reconstruct_enemy_casts
from wowperf.domain.analysis.timeline import gaps_between_pulls
from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample, too_few
from wowperf.domain.comparison.statistics import median, observed_range
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun

DURATION_WITHHELD_REASON = (
    "Enemy health scales about 10% a keystone level and compounds, so pull durations and "
    "kill times mean different things at different keystone levels and are not shown."
)
"""The evergreen half of a withheld-duration explanation, quoted by `confounds.py` too.

`Comparability.withheld_because()` names one specific "+N" level gap, which
reads fine for a single reference. A sample draws references from a spread of
levels at once, so no single gap is the reason; this sentence states the
mechanism that holds regardless of which levels were involved, and the count
of affected references is reported alongside it, not folded into the string.
"""


def _downtime_seconds(loaded: LoadedRun | SpeedMember) -> float:
    """Seconds spent between pulls — walking, not fighting.

    Reuses the timeline analyser's definition so the report never carries two
    different numbers for the same idea.
    """
    return sum(gap.seconds for gap in gaps_between_pulls(loaded.run))


def _kick_counts(loaded: LoadedRun | SpeedMember) -> tuple[int, int]:
    """(kicked, landed) enemy casts, by the documented reconstruction rule."""
    casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)
    kicked = sum(1 for cast in casts if cast.was_kicked)
    landed = sum(1 for cast in casts if cast.landed)
    return kicked, landed


def compare_tempo(ours: LoadedRun, theirs: SpeedMember, rule: Comparability) -> list[Finding]:
    """The group-axis comparisons that are not about the route, against one reference.

    The below-floor fallback `compare_tempo_sample` delegates to when a sample
    has too few eligible members to state a statistic.
    """
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


def compare_tempo_sample(ours: LoadedRun, sample: SpeedSample) -> list[Finding]:
    """The group-axis comparisons that are not about the route, against a sample.

    Kick shares are the median of each run's own share, never the pooled ratio:
    pooling weights by run length, so a long reference would dominate a figure
    that is supposed to describe a group's discipline. One reference, one
    observation.
    """
    if not sample.members:
        # A wholly empty sample means there was nothing to compare against at
        # all. `service.compare()` already says so, once, as
        # `compare.speed.unavailable`; saying it again here would duplicate
        # that finding, and there is no member to fall back on for the
        # pairwise path below, so silence is the only answer that is not a
        # crash or a repeat.
        return []

    if not sample.can_aggregate(sample.members):
        first = sample.members[0]
        return too_few(compare_tempo(ours, first, first.comparability), len(sample.members))

    members = sample.members
    return [
        _downtime_finding(ours, members),
        _deaths_finding(ours, members),
        _interrupts_finding(ours, members),
        _duration_finding(ours, sample),
    ]


def _downtime_finding(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding:
    """Time between pulls, ours against the median of the sample's own downtimes."""
    our_downtime = _downtime_seconds(ours)
    theirs = [_downtime_seconds(member) for member in members]
    their_median = median(theirs)
    low, high = observed_range(theirs)
    excess = our_downtime - their_median
    return Finding(
        id="compare.downtime",
        title=(
            f"We spent {our_downtime:.0f}s between packs; the median of {len(members)} fast "
            f"runs is {their_median:.0f}s"
        ),
        detail=(
            "Time between pulls is travel, run-backs and waiting. It does not depend on how "
            "much health a mob had, so it compares cleanly even across a keystone-level gap."
        ),
        confidence=Confidence.DERIVED,
        # Only an excess over the median is a loss. Beating the sample is not worth
        # negative seconds.
        seconds_lost=excess if excess > 0 else None,
        evidence=(
            f"ours {our_downtime:.0f}s",
            f"range {low:.0f}s to {high:.0f}s",
            f"{len(gaps_between_pulls(ours.run))} gaps on our route",
        ),
    )


def _deaths_finding(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding:
    """Death counts, ours against the median of the sample's own death counts."""
    our_deaths = len(ours.deaths)
    theirs = [float(len(member.deaths)) for member in members]
    their_median = median(theirs)
    low, high = observed_range(theirs)
    return Finding(
        id="compare.deaths",
        title=(
            f"We died {our_deaths} times; the median of {len(members)} fast runs died "
            f"{their_median:.0f} times"
        ),
        detail=(
            "A death count compares across keystone levels; what a death costs does not "
            "need restating here."
        ),
        confidence=Confidence.DERIVED,
        # deaths.total already prices our deaths in seconds. Pricing them again
        # here would count the same loss twice in one report.
        seconds_lost=None,
        evidence=(
            f"ours {our_deaths}",
            f"range {low:.0f} to {high:.0f}",
            "seconds for our own deaths are reported by deaths.total",
        ),
    )


def _interrupts_finding(ours: LoadedRun, members: Sequence[SpeedMember]) -> Finding:
    """Kick share, ours against the median of each member's own share.

    A member with no resolved casts at all contributes a share of 0.0 rather
    than being dropped from the sample: dropping it would let the title's
    denominator drift from the number of members the median was drawn from.
    """
    our_kicked, our_landed = _kick_counts(ours)
    shares: list[float] = []
    for member in members:
        kicked, landed = _kick_counts(member)
        resolved = kicked + landed
        shares.append(kicked / resolved if resolved > 0 else 0.0)
    their_median = median(shares)
    low, high = observed_range(shares)
    return Finding(
        id="compare.interrupts",
        title=(
            f"We kicked {our_kicked} of {our_kicked + our_landed} resolved casts against a "
            f"median {their_median:.0%} kick share over {len(members)} fast runs"
        ),
        detail=(
            "Outcomes are reconstructed on both sides by the same documented rule, and casts "
            "the log does not resolve are excluded rather than counted as missed. Each "
            "reference contributes its own kicked share; the sample states the median of "
            "those shares, never a ratio pooled across every reference's casts, which would "
            "let a long reference's cast count dominate a figure about a group's discipline."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"ours {our_kicked} kicked, {our_landed} landed",
            f"median kick share {their_median:.0%}",
            f"range {low:.0%} to {high:.0%}",
        ),
    )


def _duration_finding(ours: LoadedRun, sample: SpeedSample) -> Finding:
    """Completion time, against the median of only the members at our keystone level.

    A duration means something different at a different keystone level, so a
    member off our level is excluded rather than counted at a misleading value.
    """
    eligible = sample.duration_eligible
    total_members = len(sample.members)
    if not sample.can_aggregate(eligible):
        off_level = total_members - len(eligible)
        return Finding(
            id="compare.duration",
            title="Completion times are not compared",
            detail=DURATION_WITHHELD_REASON,
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"{off_level} of {total_members} references were at a different keystone level",
                "route, deaths, interrupts and downtime are still compared",
            ),
        )

    our_time = ours.run.keystone_time_seconds
    theirs = [member.run.keystone_time_seconds for member in eligible]
    their_median = median(theirs)
    low, high = observed_range(theirs)
    behind = our_time - their_median
    total = len(eligible)
    return Finding(
        id="compare.duration",
        title=(
            f"We finished in {our_time:.0f}s; the median of {total} fast runs "
            f"is {their_median:.0f}s"
        ),
        detail=(
            "Every member compared here shares our keystone level, so the official times "
            "mean the same thing and can be compared directly."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=behind if behind > 0 else None,
        evidence=(
            f"ours {our_time:.0f}s",
            f"median {their_median:.0f}s",
            f"range {low:.0f}s to {high:.0f}s",
            f"{total} of {total_members} references shared our keystone level",
        ),
    )
