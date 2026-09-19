# ABOUTME: Players alive across one attempt, as a step function in viewBox units.
# ABOUTME: Its last point is the verdict's own alive count, by construction.

from wowperf.domain.analysis.attempt_shape import alive_over_time
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.findings import Confidence
from wowperf.domain.report.frame import badge_for
from wowperf.domain.report.raid_model import AliveChart, AliveStep

CHART_WIDTH = 680.0
CHART_HEIGHT = 200.0

PLOT_X0 = 46.0
"""Where the line starts: right of the headcount axis's labels."""

PLOT_X1 = 664.0
PLOT_TOP = 16.0
"""The y of the whole raid standing."""

BASELINE_Y = 170.0
"""The y of nobody standing."""

TICK_LABEL_X = 40.0

LEGEND = (
    "Players still standing, across the attempt. A battle resurrection steps the line "
    "back up. A player who released and ran back leaves no record, so this can only "
    "undercount how many were actually up."
)


def _ticks(size: int) -> tuple[tuple[float, str], ...]:
    """A gridline at nobody, half the raid, and everybody.

    Three lines rather than one per player: twenty gridlines on a 200-unit
    plot is a grey field, and the line's own shape is what a reader follows.
    """
    marks = (0, size // 2, size)
    return tuple(
        (BASELINE_Y - (count / size) * (BASELINE_Y - PLOT_TOP), f"{count}")
        for count in marks
    )


def build_alive_chart(
    size: int,
    deaths: tuple[Death, ...],
    resurrections: tuple[Resurrection, ...],
    duration_ms: int,
    boss_percentage: float | None,
) -> AliveChart | None:
    """The attempt's headcount as one drawing, or None where there is no axis.

    Reads `alive_over_time` rather than counting deaths itself, so this chart
    and the verdict's "N of 20 alive at the end" are one computation.

    Emits two points per event rather than one: `alive_over_time` reports the
    headcount at each instant it changed, and a `<polyline>` drawn straight
    through those points alone would slope steadily between them -- a claim
    that the raid was losing people continuously across the gap, which the
    data does not support. Every point after the first therefore steps in
    twice at its own x: once at the previous count, once at its own, so the
    polyline turns the corner instead of climbing it.
    """
    if duration_ms <= 0 or size <= 0:
        return None

    span = PLOT_X1 - PLOT_X0
    height = BASELINE_Y - PLOT_TOP

    def _x(timestamp_ms: int) -> float:
        return PLOT_X0 + min(1.0, timestamp_ms / duration_ms) * span

    def _y(alive: int) -> float:
        return BASELINE_Y - (alive / size) * height

    series = alive_over_time(size, deaths, resurrections)
    first = series[0]
    steps = [AliveStep(x=_x(first.timestamp_ms), y=_y(first.alive))]
    previous_y = steps[0].y
    for point in series[1:]:
        x = _x(point.timestamp_ms)
        y = _y(point.alive)
        steps.append(AliveStep(x=x, y=previous_y))
        steps.append(AliveStep(x=x, y=y))
        previous_y = y
    points = tuple(steps)

    boss_note = (
        f"The boss finished on {boss_percentage:.1f}% health."
        if boss_percentage is not None
        else "This report gives no boss health for this attempt."
    )

    return AliveChart(
        points=points,
        ticks=_ticks(size),
        legend=LEGEND,
        boss_note=boss_note,
        badge=badge_for(Confidence.DERIVED),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        tick_x1=PLOT_X0,
        tick_x2=PLOT_X1,
        tick_label_x=TICK_LABEL_X,
    )
