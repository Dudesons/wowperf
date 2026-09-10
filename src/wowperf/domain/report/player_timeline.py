# ABOUTME: One player's run on a single axis, in viewBox units the template only prints.
# ABOUTME: Pull bands behind, damage taken above, one row per cooldown the player owns.

from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.frame import badge_for, run_seconds, run_start_ms
from wowperf.domain.report.model import (
    CooldownRow,
    PlayerTimeline,
    Section,
    SectionState,
    TimelineBlock,
)
from wowperf.domain.report.timeline import (
    MIN_BLOCK_WIDTH,
    TIMELINE_WIDTH,
    TRACK_X0,
    axis_scale,
    axis_ticks,
)
from wowperf.domain.season import Defensives, ThroughputCooldowns

PRECISION = 1
"""Coordinates are rounded to a tenth of a viewBox unit.

A run's worth of damage buckets and cooldown presses is hundreds of numbers per
player. Unrounded binary fractions would fill the page, and its golden file,
with digits no reader and no reviewer can use.
"""

AXIS_TOP = 22.0
"""Where the tick lines start, above the pull band."""

BAND_Y = 28.0
"""The pull band's top edge: a thin strip the rest of the drawing hangs under."""

BAND_HEIGHT = 10.0

DAMAGE_BASELINE_Y = 76.0
"""The foot of the damage bars. They grow upward from here."""

DAMAGE_HEIGHT = 32.0
"""How tall the largest bucket is drawn. Every other bar is a fraction of it."""

FIRST_ROW_Y = 96.0
"""The baseline of the first cooldown row."""

ROW_HEIGHT = 16.0

BOTTOM_MARGIN = 28.0
"""Gap between the last row and the viewBox's bottom edge, holding the tick labels."""

TICK_LABEL_MARGIN = 12.0

LABEL_X = 40.0
"""Where a row's ability name ends, right-aligned into the margin left of the axis."""

NOTHING_TO_DRAW = (
    "This player cast none of the cooldowns tracked for their specialisation, and the run "
    "recorded no pulls to place them against, so there is no timeline to draw."
)

LEGEND = (
    "A mark is a cast the log recorded. The stretch after it is the ability's cooldown, "
    "computed from its base length: talents shorten cooldowns and the log records no reset, "
    "so this shows an ability as unavailable at least as often as it truly was. The pale "
    "stretch at the start is not judged at all — a press before the timer began is invisible "
    "to a log fetched per fight."
)


def _pull_bands(run: Run, scale: float, origin_ms: int) -> tuple[TimelineBlock, ...]:
    """Every pull as a band behind the tracks, boss pulls outlined."""
    return tuple(
        TimelineBlock(
            label=pull.name,
            x=round(TRACK_X0 + (pull.start_ms - origin_ms) / 1000 * scale, PRECISION),
            width=round(max(pull.duration_seconds * scale, MIN_BLOCK_WIDTH), PRECISION),
            is_boss=pull.is_boss,
            kind="band",
            css_class="pull-band block-boss" if pull.is_boss else "pull-band",
        )
        for pull in run.pulls
    )


def build_player_timeline(
    loaded: LoadedRun,
    actor_id: int,
    class_name: str,
    spec: str,
    defensives: Defensives,
    throughput: ThroughputCooldowns,
) -> PlayerTimeline:
    """One player's run, drawn on the span from the first pull's start to the last pull's end.

    Not the run timeline's scale: that one fits the longer of our run and its
    reference into the width, so a pull sits at a different x there whenever a
    reference ran longer. Every player timeline in one report shares this scale
    instead, which is what lets five of them be read against each other.
    """
    run = loaded.run
    span = run_seconds(run)
    rows: tuple[CooldownRow, ...] = ()

    if span <= 0:
        return PlayerTimeline(
            section=Section(state=SectionState.WITHHELD, reason=NOTHING_TO_DRAW),
            width=TIMELINE_WIDTH,
        )

    scale = axis_scale(span)
    origin = run_start_ms(run)
    height = FIRST_ROW_Y + len(rows) * ROW_HEIGHT + BOTTOM_MARGIN

    return PlayerTimeline(
        section=Section(state=SectionState.PRESENT),
        width=TIMELINE_WIDTH,
        height=height,
        pulls=_pull_bands(run, scale, origin),
        band_y=BAND_Y,
        band_height=BAND_HEIGHT,
        damage=None,
        cooldowns=rows,
        ticks=axis_ticks(span, scale),
        tick_y1=AXIS_TOP,
        tick_y2=height - BOTTOM_MARGIN,
        tick_label_y=height - TICK_LABEL_MARGIN,
        label_x=LABEL_X,
        row_height=ROW_HEIGHT,
        legend=LEGEND,
        badge_measured=badge_for(Confidence.MEASURED),
        badge_inferred=badge_for(Confidence.INFERRED),
    )
