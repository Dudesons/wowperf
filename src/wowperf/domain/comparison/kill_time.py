# ABOUTME: A kill's duration against the reference kills' own durations, never a mean.
# ABOUTME: Median and observed range from three kills up; the slowest kill alone below that.

from statistics import median

from wowperf.domain.comparison.mechanics import MechanicsSample
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence, Finding

KILL_PREFIX = "compare.kill."
KILL_TIME_ID = "compare.kill.time"

KILL_TIME_DETAIL = (
    "Our kill's duration against the reference kills' own, read off the leaderboard rows the "
    "mechanics comparison draws: a median and an observed range, never an average, or the "
    "slowest kill alone when fewer than three were available. The kills are not adjusted for "
    "roster, item level or strategy. They are the execution leaderboard's, among the best "
    "kills of this boss, so a kill slower than theirs is the expected result rather than a "
    "fault; the damage pace beside this says where the time went."
)


def analyse_kill_time(encounter: Encounter, sample: MechanicsSample) -> list[Finding]:
    """`compare.kill.time` on a kill with any reference kill, or nothing.

    Below three kills the slowest stands alone, as the pace comparison's band
    does: it is the kinder reference, so "slower" against it can only
    understate. `seconds_lost` stays None: a raid kill is not a race against
    a timer, and the title carries both clocks.
    """
    if not encounter.kill or not sample.members:
        return []
    durations = sorted(member.row.duration_seconds for member in sample.members)
    ours = clock_text(encounter.duration_seconds)
    if len(durations) < MIN_SAMPLE_FOR_AGGREGATE:
        title = (
            f"The kill took {ours} against the slowest reference kill's "
            f"{clock_text(durations[-1])}"
        )
        evidence: tuple[str, ...] = (
            "Against the one reference kill of this raid size: fewer than three were available"
            if len(durations) == 1
            else f"Against the slowest of {len(durations)} reference kills of this raid size: "
            "fewer than three were available",
        )
    else:
        title = f"The kill took {ours} against the kills' median of {clock_text(median(durations))}"
        evidence = (
            f"Against {len(durations)} reference kills of this raid size",
            f"Their range: {clock_text(durations[0])} to {clock_text(durations[-1])}",
        )
    return [
        Finding(
            id=KILL_TIME_ID,
            title=title,
            detail=KILL_TIME_DETAIL,
            confidence=Confidence.MEASURED,
            evidence=evidence,
        )
    ]
