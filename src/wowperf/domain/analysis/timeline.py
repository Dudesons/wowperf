# ABOUTME: Splits a keystone time into pull time, death penalties and everything else.
# ABOUTME: The residual is travel, run-backs and hesitation, which is where routes improve.

from wowperf.domain.base import Frozen
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import SeasonData

GAP_FLOOR_SECONDS = 15.0
"""Below this a gap is a loading screen or a drink, not a routing problem."""

MAX_GAPS_REPORTED = 5


class Gap(Frozen):
    """Silence between two consecutive pulls, located on the map."""

    after_pull_index: int
    seconds: float
    x: int
    y: int


def gaps_between_pulls(run: Run) -> list[Gap]:
    """The stretches where nothing was being fought, worst first."""
    gaps = [
        Gap(
            after_pull_index=earlier.index,
            seconds=(later.start_ms - earlier.end_ms) / 1000,
            x=later.x,
            y=later.y,
        )
        for earlier, later in zip(run.pulls, run.pulls[1:], strict=False)
    ]
    return sorted(gaps, key=lambda gap: -gap.seconds)


def decompose_time(run: Run, deaths: tuple[Death, ...], season: SeasonData) -> list[Finding]:
    """Account for every second of the keystone timer."""
    penalty_each = season.death_penalty(run.keystone_level)
    penalty_total = penalty_each * len(deaths)
    residual = run.keystone_time_seconds - run.total_pull_seconds - penalty_total

    if residual < 0:
        residual_detail = (
            f"Fighting ({run.total_pull_seconds:.0f}s) and the death penalty "
            f"({penalty_total:.0f}s) together exceed the {run.keystone_time_seconds:.0f}s "
            f"timer, so there is no measurable residual."
        )
        residual_seconds_lost = None
    else:
        residual_detail = (
            f"{residual:.0f}s of the {run.keystone_time_seconds:.0f}s timer was neither "
            f"fighting nor the death penalty. That is travel, run-backs and waiting."
        )
        residual_seconds_lost = residual

    findings = [
        Finding(
            id="time.residual",
            title="Time spent outside pulls",
            detail=residual_detail,
            confidence=Confidence.MEASURED,
            seconds_lost=residual_seconds_lost,
            evidence=(
                f"keystone time {run.keystone_time_seconds:.0f}s",
                f"pull time {run.total_pull_seconds:.0f}s across {len(run.pulls)} pulls",
                f"{len(deaths)} deaths at {penalty_each:.0f}s = {penalty_total:.0f}s",
            ),
        )
    ]

    for rank, gap in enumerate(gaps_between_pulls(run)[:MAX_GAPS_REPORTED]):
        if gap.seconds < GAP_FLOOR_SECONDS:
            break
        next_pull = run.pulls[gap.after_pull_index + 1]
        findings.append(
            Finding(
                id=f"time.gap.{rank}",
                title=f"{gap.seconds:.0f}s between pulls {gap.after_pull_index} and "
                      f"{gap.after_pull_index + 1}",
                detail=(
                    f"The group fought nothing for {gap.seconds:.0f}s after pull "
                    f"{gap.after_pull_index}."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=gap.seconds,
                evidence=(
                    next_pull.name,
                    f"next pull begins at map position x={gap.x}, y={gap.y}",
                ),
                pull_index=gap.after_pull_index + 1,
            )
        )
    return findings
