# ABOUTME: Our cumulative boss damage against the kills' band, drawn as one chart.
# ABOUTME: Reuses `alive_chart`'s frame so the two SVGs on the raid page share a viewBox.

import math

from wowperf.domain.comparison.pace_curve import PaceReading, final_behind_start
from wowperf.domain.findings import Confidence
from wowperf.domain.report.alive_chart import (
    BASELINE_Y,
    CHART_HEIGHT,
    CHART_WIDTH,
    PLOT_TOP,
    PLOT_X0,
    PLOT_X1,
    TICK_LABEL_X,
)
from wowperf.domain.report.frame import badge_for
from wowperf.domain.report.raid_model import ChartPoint, PaceChart

TOP_STEP = 0.25
"""The y axis tops out at a multiple of this share, never at the data's own peak.

An axis that hugged the highest point drawn would put a raid barely ahead of
the band at the very top of the plot, reading as far more dominant than it
was; rounding the top up to a quarter-share keeps some headroom above it.
"""

BAND_LEGEND = (
    "Damage to the boss since the pull, as a share of the kills' median total. The band runs "
    "from the kill that had dealt least by each second to the one that had dealt most; the "
    "thin line is their median; the heavy line is this raid."
)
SINGLE_LEGEND = (
    "Damage to the boss since the pull, as a share of the slowest reference kill's total. The "
    "thin line is that kill; the heavy line is this raid."
)
CUT_NOTE = " The band ends where fewer than three kills were still fighting."


def _top(reading: PaceReading) -> float:
    """The axis's own top, as a share of `reading.target`.

    The largest share any drawn line reaches -- a kill's high, our own line,
    or the median -- floored at one quarter and rounded up to the next one, so
    the axis never tops out below `TOP_STEP` and never lands between two
    labelled ticks.
    """
    shares = [
        value / reading.target
        for second in reading.seconds
        for value in (second.high, second.ours, second.median)
    ]
    raw = max(shares) if shares else 0.0
    # The epsilon keeps a share that lands exactly on a step (0.5000000001 from
    # float division) from rounding up to the next one it never actually needs.
    steps = math.ceil(raw / TOP_STEP - 1e-9)
    return max(TOP_STEP, steps * TOP_STEP)


def build_pace_chart(reading: PaceReading, duration_seconds: float) -> PaceChart | None:
    """Our curve against the kills', every coordinate computed so the template need not be.

    `None` where the reading has nothing to draw at all: an empty `seconds`
    (nothing was compared) or a `target` of zero, which would divide every
    share by nothing.
    """
    if not reading.seconds or reading.target <= 0:
        return None

    span = PLOT_X1 - PLOT_X0
    height = BASELINE_Y - PLOT_TOP
    top = _top(reading)

    def _x(second: int) -> float:
        return PLOT_X0 + (second / duration_seconds) * span

    def _y(share: float) -> float:
        return BASELINE_Y - (share / top) * height

    def _y_of(value: float) -> float:
        return _y(value / reading.target)

    highs = [ChartPoint(x=_x(one.second), y=_y_of(one.high)) for one in reading.seconds]
    lows = [ChartPoint(x=_x(one.second), y=_y_of(one.low)) for one in reversed(reading.seconds)]
    median = tuple(ChartPoint(x=_x(one.second), y=_y_of(one.median)) for one in reading.seconds)
    ours = tuple(ChartPoint(x=_x(one.second), y=_y_of(one.ours)) for one in reading.seconds)

    behind_start = final_behind_start(reading)
    behind_x = _x(behind_start) if behind_start is not None else None
    cut_x = _x(reading.seconds[-1].second) if reading.band_cut else None

    legend = SINGLE_LEGEND if reading.single else BAND_LEGEND
    if reading.band_cut and not reading.single:
        legend += CUT_NOTE

    return PaceChart(
        band=tuple(highs + lows),
        median=median,
        ours=ours,
        behind_x=behind_x,
        cut_x=cut_x,
        plot_top=PLOT_TOP,
        baseline_y=BASELINE_Y,
        ticks=(
            (_y(0.0), "0%"),
            (_y(top / 2), f"{round(100 * top / 2)}%"),
            (_y(top), f"{round(100 * top)}%"),
        ),
        legend=legend,
        badge=badge_for(Confidence.DERIVED),
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        tick_x1=PLOT_X0,
        tick_x2=PLOT_X1,
        tick_label_x=TICK_LABEL_X,
    )
