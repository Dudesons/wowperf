# ABOUTME: One death's health across the run-up, in viewBox units the template only prints.
# ABOUTME: A step between events, and the log's own readings drawn apart from that arithmetic.

from wowperf.domain.analysis.recap import RecapEvent, health_percent, window_start
from wowperf.domain.events import Death, HealthSample
from wowperf.domain.findings import Confidence
from wowperf.domain.report.frame import badge_for
from wowperf.domain.report.model import (
    CurveGuide,
    CurvePoint,
    CurveReading,
    CurveTick,
    HealthCurve,
)

CURVE_WIDTH = 680.0
CURVE_HEIGHT = 148.0
PLOT_X0 = 40.0
"""Where the plot's left edge sits, leaving the health labels room outside it."""
PLOT_X1 = 648.0
"""Where its right edge sits, short of the viewBox so the last time label fits.

That label is centred on the axis's end, so half its width hangs past this
point. A plot drawn to the viewBox's own edge clips the word "death".
"""
PLOT_TOP = 14.0
"""The y of full health. The gap above it keeps a line at 100% off the viewBox edge."""
PLOT_BOTTOM = 116.0
"""The y of no health, with the x labels below it."""
LABEL_X = 34.0
"""Where the health labels end, right-aligned into the margin left of the plot."""
TICK_LABEL_Y = 136.0
"""The baseline of the time labels, below the plot and inside the viewBox."""

PRECISION = 1
"""Coordinates are rounded to a tenth of a viewBox unit.

The run timeline emits a handful of coordinates and leaves them unrounded. A
death card emits one per event of the run-up, which reaches seventy on a long
one, so unrounded binary fractions would fill both the page and its golden file
with digits no reader and no reviewer can use. A tenth of a unit is a fifth of
a pixel at the width this is drawn.
"""

TICK_SECONDS = 2.0
"""One time label every two seconds of the run-up: five of them plus the death."""

READING_LEGEND = "A dot is a health reading the log stated."
"""What a dot is, said beside the dots rather than in the provenance section.

A line is the most trusted shape on a page and about six of every seven points
on this one are computed, so each half of the drawing is graded where a reader
meets it.
"""

LINE_LEGEND = (
    "Between dots the line is arithmetic: each hit subtracted, each heal added."
)
"""What joins the dots, and the claim the derived badge grades."""

UNANCHORED_LINE_LEGEND = (
    "The log stated this player's health at no moment this axis covers, so the whole "
    "line is arithmetic from the last reading before it."
)
"""Said instead of the two sentences above when the run-up carried no reading.

Naming dots that are not drawn would have a reader hunting the axis for a
measurement it does not hold.
"""

DEATH_TICK = "death"
"""The rightmost label. The axis counts down to the death, so its end is named, not zeroed:
"0 s" beside a line that stops there reads as a measurement rather than as the moment."""


def _x(timestamp_ms: int, start_ms: int, span_ms: int) -> float:
    return round(PLOT_X0 + (timestamp_ms - start_ms) / span_ms * (PLOT_X1 - PLOT_X0), PRECISION)


def curve_x(timestamp_ms: int, death: Death) -> float:
    """Where an instant of the run-up falls on the curve's axis.

    Exported so a recap row's marker and the curve's own points are placed by
    one piece of arithmetic. A row computing its own x would drift the first
    time the plot's margins changed.
    """
    start_ms = window_start(death)
    span_ms = death.timestamp_ms - start_ms
    return _x(timestamp_ms, start_ms, span_ms)


def _y(percent: int) -> float:
    return round(PLOT_BOTTOM - percent / 100 * (PLOT_BOTTOM - PLOT_TOP), PRECISION)


def _step(plotted: list[tuple[int, int]], start_ms: int, span_ms: int) -> tuple[CurvePoint, ...]:
    """Corners of a line that holds its value until an event moves it.

    Health does not drift between events under this reconstruction: it changes
    when something lands and holds otherwise. So the line runs level to the next
    event's moment and only there to its value, and a slope — which would claim
    a gradual drain nothing measured — never appears. Events sharing a moment
    add the drop alone, having no time between them to run level for. The last
    value carries on to the death for the same reason every other one is held.

    Only a change earns a corner. Most events of a run-up move nothing — a cast,
    a hit a shield swallowed whole — and a vertex apiece would land in the page
    for each of them without moving the drawn shape by a pixel.
    """
    points: list[CurvePoint] = []
    for timestamp_ms, percent in plotted:
        x, y = _x(timestamp_ms, start_ms, span_ms), _y(percent)
        if not points:
            points.append(CurvePoint(x=x, y=y))
            continue
        if y == points[-1].y:
            continue
        if x != points[-1].x:
            points.append(CurvePoint(x=x, y=points[-1].y))
        points.append(CurvePoint(x=x, y=y))
    if points[-1].x != PLOT_X1:
        points.append(CurvePoint(x=PLOT_X1, y=points[-1].y))
    return tuple(points)


def _ticks(span_ms: int) -> tuple[CurveTick, ...]:
    """Time labels counting down to the death, which is named rather than numbered."""
    total = span_ms / 1000
    marks = []
    before = total
    while before > 0:
        marks.append(
            CurveTick(
                x=round(PLOT_X0 + (total - before) / total * (PLOT_X1 - PLOT_X0), PRECISION),
                label=f"{before:g} s",
            )
        )
        before -= TICK_SECONDS
    marks.append(CurveTick(x=PLOT_X1, label=DEATH_TICK))
    return tuple(marks)


def _guides() -> tuple[CurveGuide, ...]:
    """Full health and none, so a line's height is read against something."""
    return (CurveGuide(y=PLOT_TOP, label="100%"), CurveGuide(y=PLOT_BOTTOM, label="0%"))


def build_health_curve(
    events: tuple[RecapEvent, ...],
    readings: tuple[HealthSample, ...],
    death: Death,
) -> HealthCurve | None:
    """The run-up's health as a drawing, or None when the log reported none of it.

    The x axis is the whole run-up on every card, so two deaths are read against
    the same scale. The line begins at the first event carrying health rather
    than at the axis's edge: before that there is no reading to anchor the
    arithmetic, and a line drawn there would be invention.

    A line of one point is no line: a polyline paints nothing for it, and the
    legend beside it would grade a mark that is not on the page. That card gets
    None and falls back to its table, the same as one the log reported nothing
    for.
    """
    start_ms = window_start(death)
    span_ms = death.timestamp_ms - start_ms
    plotted = [
        (event.timestamp_ms, event.health_percent)
        for event in events
        if event.health_percent is not None
    ]
    if not plotted:
        return None
    dots = []
    for sample in readings:
        percent = health_percent(sample.hit_points, sample.max_hit_points)
        if percent is None:
            continue
        dots.append(
            CurveReading(
                x=_x(sample.timestamp_ms, start_ms, span_ms), y=_y(percent), percent=percent
            )
        )
    points = _step(plotted, start_ms, span_ms)
    if len(points) < 2:
        return None
    return HealthCurve(
        width=CURVE_WIDTH,
        height=CURVE_HEIGHT,
        plot_x0=PLOT_X0,
        plot_x1=PLOT_X1,
        plot_y0=PLOT_TOP,
        plot_y1=PLOT_BOTTOM,
        plot_height=PLOT_BOTTOM - PLOT_TOP,
        label_x=LABEL_X,
        tick_label_y=TICK_LABEL_Y,
        points=points,
        readings=tuple(dots),
        ticks=_ticks(span_ms),
        guides=_guides(),
        reading_legend=READING_LEGEND if dots else "",
        line_legend=LINE_LEGEND if dots else UNANCHORED_LINE_LEGEND,
        line_badge=badge_for(Confidence.DERIVED),
        reading_badge=badge_for(Confidence.MEASURED) if dots else None,
    )
