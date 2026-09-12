# ABOUTME: One player's run on a single axis, in viewBox units the template only prints.
# ABOUTME: Pull bands behind, damage taken above, one row per cooldown the player owns.

from collections import defaultdict

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.events import CastEvent, DamageTakenEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Pull, Run
from wowperf.domain.report.cover import clipped_bands, resolve_aura
from wowperf.domain.report.frame import badge_for, format_seconds, run_seconds, run_start_ms
from wowperf.domain.report.model import (
    CooldownRow,
    DamageBar,
    DamageTrack,
    PlayerTimeline,
    Press,
    Section,
    SectionState,
    Span,
    TimelineBlock,
)
from wowperf.domain.report.timeline import (
    MIN_BLOCK_WIDTH,
    TIMELINE_WIDTH,
    TRACK_X1,
    axis_scale,
    axis_ticks,
)
from wowperf.domain.season import CooldownAbility, Defensives, ThroughputCooldowns

PRECISION = 1
"""Coordinates are rounded to a tenth of a viewBox unit.

A run's worth of damage buckets and cooldown presses is hundreds of numbers per
player. Unrounded binary fractions would fill the page, and its golden file,
with digits no reader and no reviewer can use.
"""

TRACK_ORIGIN_X = 130.0
"""Where this drawing's axis starts, and so how wide the gutter left of it is.

Not `timeline.TRACK_X0` (46). Every row here is named, and a name has to end
before the track begins: a label drawn over its own row strikes through the
not-judged stretch that row opens with, and an obscured abstention reads as an
ability that was ready -- the one direction the analysis never guesses in.

Sized against the data. The longest ability name across `data/defensives.toml`
and `data/throughput_cooldowns.toml` is "Incarnation: Avatar of Ashamane", 31
characters. Measured in Chromium against the report's own font stack at the
`.row-label` size of 8.5px, that name draws 121.6 units wide in Segoe UI,
122.7 in Arial and Helvetica, and 123.6 in Roboto; `-apple-system` could not
be measured on the machine that took the reading. `LABEL_X` at 126 clears the
widest of those by 2.4 units, and `LABEL_GAP` keeps the label off the track.

The 12px the run timeline's captions use would need 172 units for the same
name. That is why these labels take a size of their own: the track is what is
left of `TRACK_X1`, so every unit of gutter is a unit the run is not drawn on.
"""

LABEL_GAP = 4.0
"""Clear space between where a row's label ends and where its track begins."""

LABEL_X = TRACK_ORIGIN_X - LABEL_GAP
"""Where a row's ability name ends. The label is right-aligned to this x, so it
runs leftward into the gutter and never over the track it names."""

LABEL_UNITS_PER_CHARACTER = 4.0
"""A label's drawn width per character, at the `.row-label` size.

The measurement above divided by the name it measured: 123.6 units over 31
characters is 3.99, rounded up. Crude on purpose -- it exists so a test can
ask whether the longest name in the data files still fits the gutter, which
is a question about the data changing, not about kerning.
"""

AXIS_TOP = 22.0
"""Where the tick lines start, above the pull band."""

BAND_Y = 28.0
"""The pull band's top edge: a thin strip the rest of the drawing hangs under."""

PULL_LABEL_GAP = 3.0
"""Clear space between a boss pull's name and the column top it sits above."""

DAMAGE_BASELINE_Y = 76.0
"""The foot of the damage bars. They grow upward from here."""

DAMAGE_HEIGHT = 32.0
"""How tall the largest bucket is drawn. Every other bar is a fraction of it."""

BUCKET_SECONDS = 5.0
"""How much of the run one damage bar covers.

Chosen against report 6Kx1P9GbNXrcLdHa fight 36 (five players, four deaths, 1,908.976
seconds first pull to last), by rendering that run at 2, 5 and 10 seconds and reading the
result three ways.

Rect count and file size move together but gently across that range: 3,266, 2,062 and
1,609 rects (721,206, 632,149 and 598,706 bytes) at 2, 5 and 10 seconds — a 1.20x spread
in bytes end to end. None of the three risks the report's openability, so file weight does
not decide.

Checked against the run's own four deaths — the share of each death's four-bucket
neighbourhood landing in its single largest bucket — no width wins across all four:
52%/47%/79%/100% at 2 seconds, 58%/91%/50%/100% at 5, 72%/50%/54%/71% at 10. This metric is
a weak arbiter besides: a four-bucket neighbourhood spans 8, 20 and 40 seconds at the three
widths, so a point spike's share of it falls simply because the window widened, biasing the
comparison toward narrow buckets on exactly the case it exists to settle. That even 2
seconds still loses on two of the four deaths despite that bias is the more telling reading
of the table.

What decides is geometry. The track spans `TRACK_X1 - TRACK_ORIGIN_X`, 526 units, over this
run's 1,908.976 seconds — `axis_scale` = 0.2755 units per second — so consecutive buckets sit
`BUCKET_SECONDS * scale` apart: 0.55, 1.38 and 2.76 units at 2, 5 and 10 seconds.
`MIN_BLOCK_WIDTH` (2.0) floors how narrow a drawn bar may get, and at 2 seconds that floor
draws every bar 3.6x wider than the gap between buckets — a lethal spike is not one bar, it
is smeared across its own slot and two and a half more, which is the "one lethal spike is one
bar" rule failing outright. At 5 seconds the floor still binds, but only to 1.45x, a bar
spilling lightly into its one right-hand neighbour. At 10 seconds the gap already exceeds
the floor, so nothing is drawn oversize.

Two seconds is ruled out on that ground alone. Between 5 and 10, neither the concentration
figures nor the geometry pick a clean winner: 10 draws every bucket at its true width, 5
accepts a mild, single-neighbour overdraw for half the seconds any one bar can blur
together. 5 is kept for the finer resolution at that modest cost.
"""

FIRST_ROW_Y = 96.0
"""The baseline of the first cooldown row."""

ROW_HEIGHT = 16.0

BOTTOM_MARGIN = 28.0
"""Gap between the last row and the viewBox's bottom edge, holding the tick labels."""

TICK_LABEL_MARGIN = 12.0

PRESS_WIDTH = 4.0
"""How wide the narrow mark at a press is drawn.

Narrow enough that two presses close together stay two marks, wide enough to
survive the page being screenshotted. The mark is centred on the instant, as
the icon behind it is, so its own width never displaces the moment it marks.
"""

TITLE = "One player's run on one elapsed-time axis"
"""The drawing's accessible name, read before any of its parts."""

NO_PULLS_RECORDED = (
    "The run recorded no pulls, so there is no axis to place this player's timeline against."
)

RUN_SPANS_NO_TIME = (
    "This run's pulls span no time, so there is no axis to place this player's timeline against."
)

NOTHING_TRACKED_OR_TAKEN = (
    "This player cast none of the cooldowns tracked for their specialisation and took no "
    "damage the log recorded, so there is nothing to draw."
)

LEGEND = (
    "A mark is a cast the log recorded. The stretch after it is the ability's cooldown, "
    "computed from its base length: talents shorten cooldowns and the log records no reset, "
    "so this shows an ability as unavailable at least as often as it truly was. The pale "
    "stretch at the start is not judged at all — a press before the timer began is invisible "
    "to a log fetched per fight. An open tick marks the earliest the ability could have come "
    "back, computed from that same base length: talents may have freed it sooner, and the log "
    "never says."
)

BADGE_MEASURED_CAPTION = "the damage bars, the press marks and the cover windows."
"""What the measured badge grades: the log itself reports all three directly -- casts
and hits as events, the aura's own bands as the intervals it was up for."""

BADGE_INFERRED_CAPTION = "the dimming and the ready tick that ends it."
"""What the inferred badge grades: a cooldown length assumed from its base value, since
talents shorten it and the log records no reset -- the same assumption the ready tick is
computed from, so it carries the same badge as the dimming it closes."""


def _track_x(elapsed_seconds: float, scale: float) -> float:
    """The x coordinate for a moment `elapsed_seconds` after the axis origin.

    Every mark on this chart -- a pull band, a damage bucket, a press, a
    cooldown span, a ready tick, a cover window -- places some instant on the
    same track, and every one of them has to translate that instant to an x
    the same way. Writing `TRACK_ORIGIN_X + elapsed_seconds * scale` by hand
    at each call site let a mark and the thing it sits on drift apart the
    moment one site's formula changed and another's did not; this is the one
    place that arithmetic happens. Unrounded: callers round to `PRECISION`
    themselves, since some do further arithmetic first (a press mark's x is
    offset half its own width before rounding).
    """
    return TRACK_ORIGIN_X + elapsed_seconds * scale


def _press_x(instant: float) -> float:
    """The left edge of a `PRESS_WIDTH`-wide mark centred on `instant`, rounded.

    Shared by a press's own mark and the ready tick that answers it: both are
    rects of the same width standing for a single moment, and `Press`'s own
    docstring is the reason either needs offsetting at all -- an SVG rect's
    `x` is its left edge, so a mark placed flush with the instant would sit
    wholly to its right. Writing the offset a second time at the tick's call
    site would let the two drift the way `_track_x` already exists to stop a
    mark and its track from drifting.
    """
    return round(instant - PRESS_WIDTH / 2, PRECISION)


def _band_label(pull: Pull) -> str:
    """What a band is called.

    A boss's name is worth the space; a trash pack's generated name is the
    first mob the log happened to see, which names nothing a reader can find
    again. The index is what the rest of the report calls it.
    """
    return pull.name if pull.is_boss else f"Pull {pull.index}"


def _band_hover(pull: Pull) -> str:
    """A band's name and how long it ran.

    "ran" is there to stop the figure reading as the pull's start: every other
    number on this axis is an elapsed time, and a band's own duration is the
    one quantity a reader cannot recover by eye from a chart this wide.
    """
    duration = format_seconds(pull.duration_seconds)
    assert duration is not None  # a float input always formats to a string
    return f"{_band_label(pull)} — ran {duration}"


def _pull_bands(run: Run, scale: float, origin_ms: int) -> tuple[TimelineBlock, ...]:
    """Every pull as a band behind the tracks, boss pulls outlined."""
    return tuple(
        TimelineBlock(
            label=_band_label(pull),
            hover=_band_hover(pull),
            x=round(_track_x((pull.start_ms - origin_ms) / 1000, scale), PRECISION),
            width=round(max(pull.duration_seconds * scale, MIN_BLOCK_WIDTH), PRECISION),
            is_boss=pull.is_boss,
            kind="band",
            css_class="pull-band block-boss" if pull.is_boss else "pull-band",
        )
        for pull in run.pulls
    )


def _damage_track(
    events: tuple[DamageTakenEvent, ...], actor_id: int, scale: float, origin_ms: int
) -> DamageTrack | None:
    """Damage this player took, bucketed, scaled to their own largest bucket.

    `amount` is the unmitigated figure — what the hit was worth before armour
    and absorbs — which is the same number the per-ability comparison reads, so
    the drawing and the findings cannot disagree about how hard something hit.

    Returns `None` when this player took nothing the log recorded -- no
    events, or every recorded hit fully avoided (a miss, dodge, or parry
    carries an unmitigated amount of zero): an empty track drawn at full
    height would read as a run of zero-damage buckets rather than as an
    absence.
    """
    ours = [event for event in events if event.actor_id == actor_id]
    if not ours:
        return None

    buckets: dict[int, int] = defaultdict(int)
    for event in ours:
        index = int((event.timestamp_ms - origin_ms) / 1000 // BUCKET_SECONDS)
        buckets[index] += event.amount

    peak = max(buckets.values())
    if peak == 0:
        return None

    width = round(BUCKET_SECONDS * scale, PRECISION)
    bars = tuple(
        DamageBar(
            x=round(_track_x(index * BUCKET_SECONDS, scale), PRECISION),
            width=max(width, MIN_BLOCK_WIDTH),
            y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT * amount / peak, PRECISION),
            height=round(DAMAGE_HEIGHT * amount / peak, PRECISION),
        )
        for index, amount in sorted(buckets.items())
    )
    return DamageTrack(
        baseline_y=DAMAGE_BASELINE_Y,
        # Centred on the band the bars grow through, so the name sits beside
        # what it names rather than on the line the bars stand on.
        label_y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT / 2, PRECISION),
        bars=bars,
        peak_label=(
            f"Tallest bar: {peak:,} unmitigated damage in {int(BUCKET_SECONDS)} seconds."
        ),
        axis_top_y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT, PRECISION),
        # The same origin the bars and every span on the chart already start
        # from, not the label gutter: every other track element leaves
        # LABEL_GAP between the two, and this line is not an exception.
        axis_x0=TRACK_ORIGIN_X,
        # The same end the bars and every span on the chart already stop at,
        # not the viewBox's own edge: `timeline.width` runs past TRACK_X1 into
        # the right margin, twenty-four units this drawing never places
        # anything else in.
        axis_x1=TRACK_X1,
        axis_top_label=f"{peak:,}",
        # Says what `peak_label` does not: that width is every bar's, not just
        # the tallest one's, and what the axis itself is scaled against. Says
        # nothing `peak_label` already said -- no repeated "unmitigated
        # damage" -- since the two sentences sit side by side on the page.
        bucket_caption=(
            f"Each bar is a {int(BUCKET_SECONDS)}-second bucket, and the axis runs from "
            f"nothing to this player's own tallest, never the group's."
        ),
    )


def _cover_bands(
    ability_id: int,
    ability_name: str,
    auras: PlayerAuras | None,
    origin_ms: int,
    span_seconds: float,
) -> tuple[tuple[int, int], ...] | None:
    """Every stretch this ability's buff was up, in report milliseconds, clipped to the axis.

    None where no aura table was fetched for this player, or where the table
    holds nothing under this ability's id or name. An empty tuple is the
    different answer: a table that covers the ability and recorded no window
    inside the drawing. Nothing distinguishes the two on the chart, which
    draws no rectangle either way, so the distinction is carried here for the
    row's hover to state.

    `clipped_bands` -- the merged view -- is used rather than `band_holding`:
    this row describes the ability's total cover across the whole run, not the
    window one particular press earned.
    """
    if auras is None:
        return None
    aura = resolve_aura(auras, ability_id, ability_name)
    if aura is None:
        return None
    return clipped_bands(aura, origin_ms, origin_ms + int(span_seconds * 1000))


def _cover_spans(
    bands: tuple[tuple[int, int], ...] | None, scale: float, origin_ms: int
) -> tuple[Span, ...]:
    """The cover windows drawn at the axis's own scale.

    `MIN_BLOCK_WIDTH` is deliberately not applied. A pull is floored to that
    width because a pull that vanishes tells the reader nothing; a cover
    window's width *is* the claim, and widening a five-second buff on a
    thirty-three-minute axis from 1.4 units to 2 would overstate its duration by
    nearly half.
    """
    return tuple(
        Span(
            x=round(_track_x((start - origin_ms) / 1000, scale), PRECISION),
            width=round((end - start) / 1000 * scale, PRECISION),
        )
        for start, end in bands or ()
    )


NO_AURA_DATA = "No aura data for it, so its cover is not drawn."
"""Said on a row whose ability the run's aura tables say nothing about.

The alternative -- printing zero seconds of cover -- would state as a
measured figure a thing nobody measured, which is the one reading a hover
panel over an empty stretch of chart most invites.
"""


def _cooldown_hover(
    label: str, presses: int, bands: tuple[tuple[int, int], ...] | None
) -> str:
    """What one row's rectangles are worth, as the plain text a native title holds.

    Measured only, and deliberately so. The row also draws the stretches the
    ability was unavailable, but those are a base cooldown from `data/` laid
    over the presses rather than anything the log stated, and an SVG title
    carries no badge to grade such a figure with. So this states what was
    counted and leaves what was assumed to the drawing, where the timeline's
    own inferred badge and its caption already account for it.

    The cover figure is summed from the drawn windows and never from the aura
    table's own total, so a buff still up when the axis ends reports the part
    the chart shows: the number a reader hovers and the rectangles they are
    looking at cannot disagree.
    """
    counted = f"{presses} press{'es' if presses != 1 else ''}"
    if bands is None:
        return f"{label} — {counted}. {NO_AURA_DATA}"
    seconds = sum(end - start for start, end in bands) / 1000
    return f"{label} — {counted}, {seconds:.1f} s of cover"


def _cooldown_rows(
    casts: tuple[CastEvent, ...],
    abilities: tuple[CooldownAbility, ...],
    actor_id: int,
    scale: float,
    origin_ms: int,
    span_seconds: float,
    auras: PlayerAuras | None,
) -> tuple[CooldownRow, ...]:
    """One row per ability in `abilities` this player cast at least once.

    Ownership is the whole rule. The data files list what a specialisation can
    take, not what this player took, and `analysis/defensives.py` already
    refuses to read silence as availability because "reporting silence as
    availability would accuse someone of not pressing a button they do not
    own". Drawn, that accusation is worse than written: an empty row across a
    whole run reads as a run of missed presses.

    The row's opening is marked not-judged for the ability's own cooldown, for
    the reason `analysis/throughput.py:ready_at` refuses to judge a window
    reaching back past the run's start — casts are fetched per fight, so a
    press before the timer began leaves no record, and calling that stretch
    ready would guess in the one direction this project never guesses in.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    owned = {cast.ability_id for cast in ours}

    def press_at(at: int) -> Press:
        instant = _track_x((at - origin_ms) / 1000, scale)
        return Press(
            x=_press_x(instant),
            icon_x=round(instant - ROW_HEIGHT / 2, PRECISION),
        )

    rows: list[CooldownRow] = []
    for ability in abilities:
        if ability.ability_id not in owned:
            continue
        presses = sorted(
            cast.timestamp_ms for cast in ours if cast.ability_id == ability.ability_id
        )
        not_judged_width = round(min(ability.cooldown_seconds, span_seconds) * scale, PRECISION)
        bands = _cover_bands(
            ability.ability_id, ability.name, auras, origin_ms, span_seconds
        )
        rows.append(
            CooldownRow(
                label=ability.name,
                ability_id=ability.ability_id,
                hover=_cooldown_hover(ability.name, len(presses), bands),
                baseline_y=FIRST_ROW_Y + len(rows) * ROW_HEIGHT,
                # The label sits on the row's own middle, not on its top edge:
                # a baseline at the top would draw the glyphs over the row above.
                label_y=round(FIRST_ROW_Y + len(rows) * ROW_HEIGHT + ROW_HEIGHT / 2, PRECISION),
                presses=tuple(press_at(at) for at in presses),
                unavailable=tuple(
                    Span(
                        x=round(_track_x((at - origin_ms) / 1000, scale), PRECISION),
                        # Clamped to the time remaining in the run after this
                        # press, not to the run's whole length: the ability can
                        # only be judged unavailable up to the axis end, never
                        # past it.
                        width=round(
                            min(
                                ability.cooldown_seconds,
                                max(0.0, span_seconds - (at - origin_ms) / 1000),
                            )
                            * scale,
                            PRECISION,
                        ),
                    )
                    for at in presses
                ),
                # A cooldown's own end is the moment the ability came back --
                # marked only when that moment falls before the axis does. A
                # cooldown still running when the run ends would need a tick
                # at the axis end, which claims the ability came back at the
                # moment the run finished; the log never says that. Anchored
                # through `_press_x`, the same offsetting the press it
                # answers already uses -- see that helper for why either
                # mark needs offsetting at all.
                ready_ticks=tuple(
                    _press_x(_track_x(end, scale))
                    for end in (
                        (at - origin_ms) / 1000 + ability.cooldown_seconds for at in presses
                    )
                    if end < span_seconds
                ),
                not_judged=Span(x=TRACK_ORIGIN_X, width=not_judged_width),
                cover=_cover_spans(bands, scale, origin_ms),
            )
        )
    return tuple(rows)


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

    if not run.pulls:
        return PlayerTimeline(
            section=Section(state=SectionState.WITHHELD, reason=NO_PULLS_RECORDED),
            width=TIMELINE_WIDTH,
        )

    if span <= 0:
        return PlayerTimeline(
            section=Section(state=SectionState.WITHHELD, reason=RUN_SPANS_NO_TIME),
            width=TIMELINE_WIDTH,
        )

    scale = axis_scale(span, TRACK_ORIGIN_X)
    origin = run_start_ms(run)
    rows = _cooldown_rows(
        loaded.casts,
        throughput.for_spec(class_name, spec) + defensives.for_spec(class_name, spec),
        actor_id,
        scale,
        origin,
        span,
        loaded.auras_by_actor.get(actor_id),
    )
    damage = _damage_track(loaded.damage_taken, actor_id, scale, origin)

    if not rows and damage is None:
        return PlayerTimeline(
            section=Section(state=SectionState.WITHHELD, reason=NOTHING_TRACKED_OR_TAKEN),
            width=TIMELINE_WIDTH,
        )

    height = FIRST_ROW_Y + len(rows) * ROW_HEIGHT + BOTTOM_MARGIN

    return PlayerTimeline(
        section=Section(state=SectionState.PRESENT),
        title=TITLE,
        width=TIMELINE_WIDTH,
        height=height,
        pulls=_pull_bands(run, scale, origin),
        band_y=BAND_Y,
        column_height=height - BAND_Y - BOTTOM_MARGIN,
        pull_label_y=BAND_Y - PULL_LABEL_GAP,
        damage=damage,
        cooldowns=rows,
        ticks=tuple(
            (round(x, PRECISION), label) for x, label in axis_ticks(span, scale, TRACK_ORIGIN_X)
        ),
        tick_y1=AXIS_TOP,
        tick_y2=height - BOTTOM_MARGIN,
        tick_label_y=height - TICK_LABEL_MARGIN,
        label_x=LABEL_X,
        row_height=ROW_HEIGHT,
        press_width=PRESS_WIDTH,
        legend=LEGEND,
        badge_measured=badge_for(Confidence.MEASURED),
        badge_measured_caption=BADGE_MEASURED_CAPTION,
        badge_inferred=badge_for(Confidence.INFERRED),
        badge_inferred_caption=BADGE_INFERRED_CAPTION,
    )
