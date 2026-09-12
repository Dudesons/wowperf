# ABOUTME: One player's run on a single axis, in viewBox units the template only prints.
# ABOUTME: Pull bands behind, damage taken above, one row per cooldown the player owns.

from collections import defaultdict
from collections.abc import Iterable

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.events import CastEvent, DamageTakenEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import DamageDoneSeries, LoadedRun, Pull, Run
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
    StateKey,
    TimelineBlock,
    Tooltip,
    TooltipLine,
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

TRACK_ORIGIN_X = 150.0
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

The gutter holds the row's icon as well as its name, which is what 150 buys
over the 130 it was: `ICON_SIZE + LABEL_GAP` of it, leaving `LABEL_X` where it
already stood so the measurement above still holds. The track gives up 20 of
the 526 units it had for that, leaving 506, which is 3.8% of it.

The 12px the run timeline's captions use would need 172 units for the same
name. That is why these labels take a size of their own: the track is what is
left of `TRACK_X1`, so every unit of gutter is a unit the run is not drawn on.
"""

LABEL_GAP = 4.0
"""Clear space between where a row's label ends and where its track begins."""

ROW_HEIGHT = 16.0
"""How tall one cooldown row is drawn. Stated here rather than beside the other
vertical constants below because the gutter's width is derived from it: a row's
icon is square and as tall as its row, and `LABEL_X` is what is left over."""

ICON_SIZE = ROW_HEIGHT
"""A row's icon is as tall as its row, and square.

Drawn once, in the gutter. It was drawn at every press until 2026-09-12, at
this same size -- which is about seventeen seconds of a twenty-three minute
run, so any ability pressed oftener than that overlapped itself. Across five
players one report drew 281 of them and 67 overlapped a neighbour, and the
press mark was painted over each one, which is why they looked cut.
"""

ICON_X = TRACK_ORIGIN_X - LABEL_GAP - ICON_SIZE
"""Where the row's icon starts: immediately left of the track, clear of it by `LABEL_GAP`."""

LABEL_X = ICON_X - LABEL_GAP
"""Where a row's ability name ends. The label is right-aligned to this x, so it
runs leftward into the gutter and never over the icon or the track it names."""

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

DAMAGE_DONE_GAP = 8.0
"""Clear space between the damage taken bars' baseline and the done track's top."""

DAMAGE_DONE_BASELINE_Y = DAMAGE_BASELINE_Y + DAMAGE_DONE_GAP + DAMAGE_HEIGHT
"""The foot of the damage done bars, which also grow upward from it.

Below the damage taken track and immediately above the first cooldown row,
which is the placement the reader's eye path decides: a press mark is read
against the output that followed it, so the two sit together and nothing goes
between them.
"""

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

What decides is geometry. The track spans `TRACK_X1 - TRACK_ORIGIN_X`, 506 units, over this
run's 1,908.976 seconds — `axis_scale` = 0.2651 units per second — so consecutive buckets sit
`BUCKET_SECONDS * scale` apart: 0.53, 1.33 and 2.65 units at 2, 5 and 10 seconds.
`MIN_BLOCK_WIDTH` (2.0) floors how narrow a drawn bar may get, and at 2 seconds that floor
draws every bar 3.77x wider than the gap between buckets — a lethal spike is not one bar, it
is smeared across its own slot and nearly three more, which is the "one lethal spike is one
bar" rule failing outright. At 5 seconds the floor still binds, but only to 1.51x, a bar
spilling lightly into its one right-hand neighbour. At 10 seconds the gap already exceeds
the floor, so nothing is drawn oversize.

Two seconds is ruled out on that ground alone. Between 5 and 10, neither the concentration
figures nor the geometry pick a clean winner: 10 draws every bucket at its true width, 5
accepts a mild, single-neighbour overdraw for half the seconds any one bar can blur
together. 5 is kept for the finer resolution at that modest cost.
"""

FIRST_ROW_Y = 136.0
"""The baseline of the first cooldown row.

Forty units below the damage taken track rather than eight: the damage done
bars take the band between them, and a row left at the older figure would be
drawn straight through those bars. Every row's hover strip is placed as a
share of the chart's own height, so moving this moves all of them.
"""

BOTTOM_MARGIN = 28.0
"""Gap between the last row and the viewBox's bottom edge, holding the tick labels."""

TICK_LABEL_MARGIN = 12.0

PRESS_WIDTH = 4.0
"""How wide the narrow mark at a press is drawn.

Narrow enough that two presses close together stay two marks, wide enough to
survive the page being screenshotted. The mark is centred on the instant, so
its own width never displaces the moment it marks.
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
    "This player cast none of the cooldowns tracked for their specialisation, and neither the "
    "log nor the run's graph carried any damage for them inside the window this chart draws, "
    "so there is nothing to draw."
)
"""Why the whole chart is withheld, naming both sources and the window.

Both, because the two tracks are read from different places and `NO_DAMAGE_DONE`
below turns on saying so; the window, because a stream can carry plenty and
have none of it land between the first pull and the last.
"""

NO_DAMAGE_TAKEN = (
    "No damage taken is drawn: the log recorded none for this player inside the window this "
    "axis draws. A flat track would read as a run of zero-damage buckets rather than as an "
    "absence."
)
"""Said where the damage taken track's caption would sit, when none is drawn.

The chart still renders on its other layers, so without this the blank is left
for a reader to explain, and the likeliest explanation -- that the player did
nothing -- is the one the absence does not support. The same abstention
`NO_AURA_DATA` makes for an ability whose cover cannot be drawn.

The claim is about the log rather than about the player, and deliberately so.
`_damage_track` abstains on three causes -- no events for this actor, every
recorded hit fully avoided, or every bucket falling outside the drawn window --
and "recorded none inside the window this axis draws" is true of all three
without having to tell them apart. The window clause is not decoration: a hit
before the first pull is real damage the log did record, and a sentence
blaming the log for it would be false.
"""

NO_DAMAGE_DONE = (
    "No damage done is drawn: the run's graph carried none for this player inside the window "
    "this axis draws. A flat track would read as a run of empty buckets, which is a claim "
    "nobody measured."
)
"""The mirror of `NO_DAMAGE_TAKEN`, and not the same claim as it.

Damage taken is read from an event stream, so its silence is a fact about the
player. This track is read from `graph`, a separate response that can carry no
series at all for a player who certainly dealt damage, so its silence is a fact
about the data. Naming the graph rather than the log is what keeps the two
apart on the page, and `_damage_done_track`'s other cause -- a series whose
every bucket is zero -- is covered by the same words.
"""

LEGEND = (
    "A mark is a cast the log recorded. The stretch after it is the ability's cooldown, "
    "computed from its base length: talents shorten cooldowns and the log records no reset, "
    "so this shows an ability as unavailable at least as often as it truly was. The pale "
    "stretch at the start is not judged at all — a press before the timer began is invisible "
    "to a log fetched per fight. An open tick marks the earliest the ability could have come "
    "back, computed from that same base length: talents may have freed it sooner, and the log "
    "never says."
)

STATE_KEY = (
    StateKey(label="a press", css_class="press"),
    StateKey(label="the buff up", css_class="cover"),
    StateKey(label="on cooldown", css_class="on-cooldown"),
    StateKey(label="not judged", css_class="not-judged"),
)
"""The four states the track paints, each named in the class it is painted with.

The class is carried rather than the colour so the key and the track cannot
disagree: a swatch takes the same rule as the rectangle it stands for.
`LEGEND` explains three of these four in prose and has never named the cover,
which is the one a reader is least able to guess.
"""

def _graded_caption(layers: tuple[str, ...]) -> str:
    """The layers a badge grades, as one sentence naming those and no others.

    A badge's caption is a claim about this page, not about the chart in
    general, and every layer below is optional: a player can take damage and
    press nothing, press something the aura tables know nothing about, or press
    it late enough that the cooldown outlasts the run. Naming a layer the chart
    did not draw grades something absent from it, which is the same defect as a
    badge over an absent track, one level finer.

    Given every layer, this reproduces the sentence each caption had when it was
    a constant, so a complete chart's wording does not move.
    """
    if not layers:
        return ""
    if len(layers) == 1:
        return f"{layers[0]}."
    return f"{', '.join(layers[:-1])} and {layers[-1]}."


MEASURED_DAMAGE_TAKEN = "the damage taken bars"
MEASURED_PRESS_MARKS = "the press marks"
MEASURED_COVER_WINDOWS = "the cover windows"
BADGE_MEASURED_CAPTION = _graded_caption(
    (MEASURED_DAMAGE_TAKEN, MEASURED_PRESS_MARKS, MEASURED_COVER_WINDOWS)
)
"""What the measured badge grades when a chart draws all three: the log itself reports
them directly -- casts and hits as events, the aura's own bands as the intervals it was
up for. A chart drawing fewer is captioned with fewer; see `_graded_caption`."""

BADGE_DERIVED_CAPTION = (
    "the damage done bars, rebuilt from the per-second figures the log's own graph reports."
)
"""What the derived badge grades: the graph states a rate, and the amount a bar draws is
that rate multiplied back up by the interval it covers. The reconstruction lands within
a percent of the figure the API reports for the whole run, and does not close exactly --
which is the difference between this and the measured bars above it."""

INFERRED_DIMMING = "the dimming"
INFERRED_READY_TICK = "the ready tick that ends it"
BADGE_INFERRED_CAPTION = _graded_caption((INFERRED_DIMMING, INFERRED_READY_TICK))
"""What the inferred badge grades: a cooldown length assumed from its base value, since
talents shorten it and the log records no reset -- the same assumption the ready tick is
computed from, so it carries the same badge as the dimming it closes.

The tick is the half that can be missing. Every press dims the track after it, but a
press whose cooldown outlasts the run gets no tick, because the log never says the
ability came back. A chart of only such presses is captioned for the dimming alone."""


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


def _bucket_pulls(run: Run, start_ms: int, end_ms: int) -> tuple[str, ...]:
    """Every pull this bucket's own span overlaps, in run order.

    Resolved from the pulls' own bounds rather than from the hits' recorded
    `pull_index`, so the sentence a reader hovers names the band they can see
    the bar standing on. The same discipline `_row_panel` states for its
    figures: the number and the rectangles behind it cannot disagree.

    More than one where a bucket straddles a boundary, which five seconds
    readily does. Both are named: choosing between them would be a judgement
    the log never made.
    """
    return tuple(
        _band_label(pull)
        for pull in run.pulls
        if pull.start_ms < end_ms and start_ms < pull.end_ms
    )


def _bucket_hover(amount: int, bucket_index: int, run: Run, origin_ms: int) -> str:
    """What one bar holds, how wide it is, when it fell, and which pull it fell in.

    A spike is only a question until a reader knows which pull it belongs to,
    and the chart draws forty bands behind the bars for them to find it by eye.
    """
    start_ms = origin_ms + int(bucket_index * BUCKET_SECONDS * 1000)
    at = format_seconds(bucket_index * BUCKET_SECONDS)
    assert at is not None  # a float input always formats to a string
    names = _bucket_pulls(run, start_ms, start_ms + int(BUCKET_SECONDS * 1000))
    where = f"during {' and '.join(names)}" if names else "between pulls"
    return f"{amount:,} unmitigated in {_bucket_width_text(BUCKET_SECONDS)} s, at {at}, {where}"


def _bucket_width_text(seconds: float) -> str:
    """A bucket width as a reader would write it: "5", and "6.4".

    The damage taken track buckets at a whole five seconds and the graph hands
    back 6.4117, so one formatter serves both without the first gaining a
    decimal it never had.
    """
    return f"{round(seconds, 1):g}"


def _done_bucket_hover(
    amount: int, at_seconds: float, bucket_seconds: float, run: Run, origin_ms: int
) -> str:
    """What one damage done bar holds, when it fell, and which pull it fell in.

    States an amount, never a rate. The response this is built from is in
    damage per second, and printing that would hand the reader the throughput
    figure the postmortem design's section 5.5 refuses to produce.
    """
    start_ms = origin_ms + int(at_seconds * 1000)
    at = format_seconds(at_seconds)
    assert at is not None  # a float input always formats to a string
    names = _bucket_pulls(run, start_ms, start_ms + int(bucket_seconds * 1000))
    where = f"during {' and '.join(names)}" if names else "between pulls"
    return f"{amount:,} damage done in {_bucket_width_text(bucket_seconds)} s, at {at}, {where}"


def _damage_done_track(
    series: tuple[DamageDoneSeries, ...],
    actor_id: int,
    run: Run,
    scale: float,
    origin_ms: int,
) -> DamageTrack | None:
    """This player's output, in the buckets the API chose, scaled to their own peak.

    Never to the group's, for the reason `_damage_track` states below: a shared
    scale across five players would rank them.

    Returns None where nothing is left to draw -- no series for this player,
    a series of nothing but zeros, or every bucket falling outside the window
    this axis covers -- so the absence is drawn as an absence. A track of
    zero-height bars would read as a run of empty buckets, which is a different
    claim and one nobody measured.
    """
    ours = next((one for one in series if one.actor_id == actor_id), None)
    if ours is None:
        return None

    bucket_seconds = ours.interval_ms / 1000
    offset_seconds = (ours.point_start_ms - origin_ms) / 1000
    span_seconds = run_seconds(run)
    # `graph` covers the fight and this axis covers the first pull to the last,
    # so a real series opens with a bucket or two before the origin.
    drawn = tuple(
        (at, amount)
        for at, amount in (
            (offset_seconds + index * bucket_seconds, amount)
            for index, amount in enumerate(ours.amounts)
        )
        if _bucket_is_drawn(at, span_seconds)
    )
    if not drawn:
        return None

    peak = max(amount for _at, amount in drawn)
    if peak == 0:
        return None

    width = max(round(bucket_seconds * scale, PRECISION), MIN_BLOCK_WIDTH)
    bars = tuple(
        DamageBar(
            x=(x := round(_track_x(at, scale), PRECISION)),
            width=_bar_width(x, width),
            y=round(DAMAGE_DONE_BASELINE_Y - DAMAGE_HEIGHT * amount / peak, PRECISION),
            height=round(DAMAGE_HEIGHT * amount / peak, PRECISION),
            hover=_done_bucket_hover(amount, at, bucket_seconds, run, origin_ms),
        )
        for at, amount in drawn
    )
    return DamageTrack(
        baseline_y=DAMAGE_DONE_BASELINE_Y,
        label_y=round(DAMAGE_DONE_BASELINE_Y - DAMAGE_HEIGHT / 2, PRECISION),
        bars=bars,
        peak_label=(
            f"Tallest bar: {peak:,} damage done in "
            f"{_bucket_width_text(bucket_seconds)} seconds."
        ),
        axis_top_y=round(DAMAGE_DONE_BASELINE_Y - DAMAGE_HEIGHT, PRECISION),
        axis_x0=TRACK_ORIGIN_X,
        axis_x1=TRACK_X1,
        axis_top_label=f"{peak:,}",
        bucket_caption=(
            f"Each bar is a {_bucket_width_text(bucket_seconds)}-second bucket, and the axis "
            f"runs from nothing to this player's own tallest, never the group's."
        ),
    )


def _bucket_is_drawn(start_seconds: float, span_seconds: float) -> bool:
    """Whether a bucket starting here falls inside the window this axis draws.

    The axis runs from the first pull to the last, and both bucket streams are
    wider than it: `graph` covers the whole fight, and a hit can land before the
    first pull or after the last one ends. A bucket outside has nowhere honest
    to go. Drawn at its true position it lands in the label gutter, where a row
    name is about to be written, and it carries a hover stating a time this
    axis has no origin for -- `format_seconds` floors, so ten seconds before
    the first pull reads as "-1:50" rather than as anything a reader can use.

    Moving it inside would be worse: it would place damage at a moment it did
    not happen, on a chart whose whole subject is when things happened.
    """
    return 0.0 <= start_seconds < span_seconds


def _bar_width(x: float, width: float) -> float:
    """A bar's drawn width, stopped at the axis's own end.

    The last bucket of a stream overhangs the window it covers -- 241 buckets of
    6.4117 s span 1545.2 s of a 1538.8 s fight. That overhang is real geometry,
    whatever else it was once blamed for: the wcl-api skill records that it
    cannot be the reason the rebuilt total lands under the API's, since it
    predicts the opposite sign. What it must not do is put marks past
    `TRACK_X1`, in the right margin the axis deliberately stops at.

    A bar clipped here can end up narrower than `MIN_BLOCK_WIDTH`. That floor
    keeps a bucket from vanishing mid-chart; at the boundary the axis wins.
    """
    return round(min(x + width, TRACK_X1) - x, PRECISION)


def _damage_track(
    events: tuple[DamageTakenEvent, ...], actor_id: int, run: Run, scale: float, origin_ms: int
) -> DamageTrack | None:
    """Damage this player took, bucketed, scaled to their own largest bucket.

    `amount` is the unmitigated figure — what the hit was worth before armour
    and absorbs — which is the same number the per-ability comparison reads, so
    the drawing and the findings cannot disagree about how hard something hit.

    Returns `None` when nothing is left to draw -- no events, every recorded
    hit fully avoided (a miss, dodge, or parry carries an unmitigated amount of
    zero), or every bucket falling outside the window this axis covers: an
    empty track drawn at full height would read as a run of zero-damage
    buckets rather than as an absence.
    """
    ours = [event for event in events if event.actor_id == actor_id]
    if not ours:
        return None

    buckets: dict[int, int] = defaultdict(int)
    for event in ours:
        index = int((event.timestamp_ms - origin_ms) / 1000 // BUCKET_SECONDS)
        buckets[index] += event.amount

    span_seconds = run_seconds(run)
    drawn = sorted(
        (index, amount)
        for index, amount in buckets.items()
        if _bucket_is_drawn(index * BUCKET_SECONDS, span_seconds)
    )
    if not drawn:
        return None

    # The tallest bucket on the chart, not the tallest in the stream: a bucket
    # the chart does not draw setting the axis top would label the track with a
    # figure no bar on it reaches, and squash every bar that is there.
    peak = max(amount for _index, amount in drawn)
    if peak == 0:
        return None

    width = max(round(BUCKET_SECONDS * scale, PRECISION), MIN_BLOCK_WIDTH)
    bars = tuple(
        DamageBar(
            x=(x := round(_track_x(index * BUCKET_SECONDS, scale), PRECISION)),
            width=_bar_width(x, width),
            y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT * amount / peak, PRECISION),
            height=round(DAMAGE_HEIGHT * amount / peak, PRECISION),
            hover=_bucket_hover(amount, index, run, origin_ms),
        )
        for index, amount in drawn
    )
    return DamageTrack(
        baseline_y=DAMAGE_BASELINE_Y,
        # Centred on the band the bars grow through, so the name sits beside
        # what it names rather than on the line the bars stand on.
        label_y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT / 2, PRECISION),
        bars=bars,
        peak_label=(
            f"Tallest bar: {peak:,} unmitigated damage in "
            f"{_bucket_width_text(BUCKET_SECONDS)} seconds."
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
            f"Each bar is a {_bucket_width_text(BUCKET_SECONDS)}-second bucket, and the "
            f"axis runs from "
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


TRACK_WIDTH = TRACK_X1 - TRACK_ORIGIN_X
"""How wide a row's track is drawn, and so what a share of the run is a share of."""


def _intervals(spans: Iterable[Span]) -> tuple[tuple[float, float], ...]:
    return tuple((span.x, span.x + span.width) for span in spans)


def _merged(intervals: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """The same stretches with every overlap collapsed.

    A press landing inside a running cooldown is the normal case on a busy row,
    so the drawn spans overlap routinely and summing their widths would report
    more track than the row has.
    """
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def _without(
    intervals: tuple[tuple[float, float], ...], holes: tuple[tuple[float, float], ...]
) -> tuple[tuple[float, float], ...]:
    """`intervals` with every part lying inside `holes` removed. `holes` must be merged."""
    kept: list[tuple[float, float]] = []
    for start, end in intervals:
        cursor = start
        for hole_start, hole_end in holes:
            if hole_end <= cursor or hole_start >= end:
                continue
            if hole_start > cursor:
                kept.append((cursor, hole_start))
            cursor = max(cursor, hole_end)
        if cursor < end:
            kept.append((cursor, end))
    return tuple(kept)


def _length(intervals: Iterable[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _apportion(lengths: tuple[float, float, float]) -> tuple[int, int, int]:
    """Three lengths as whole percentages of the track that sum to 100.

    By largest remainder: floor each, then give the leftover points to the
    largest fractions. Rounding the three independently sums to 99 or 101 often
    enough to reach a reader, and a panel whose own column does not add up
    invites the one doubt this page cannot afford.
    """
    exact = [length / TRACK_WIDTH * 100 for length in lengths]
    shares = [int(part) for part in exact]
    by_remainder = sorted(range(3), key=lambda index: exact[index] - shares[index], reverse=True)
    for index in by_remainder[: 100 - sum(shares)]:
        shares[index] += 1
    return shares[0], shares[1], shares[2]


def _row_shares(not_judged: Span | None, unavailable: tuple[Span, ...]) -> tuple[int, int, int]:
    """What share of the run this row was unjudged, on cooldown, and ready but unpressed.

    These three cover the track exactly once, which is why the drawing's fourth
    state is not among them: cover overlaps the cooldown almost always, because
    the buff is up while the cooldown runs, and four shares of one run would sum
    past 100. Design section 2.1 records the measurement that settled it.

    Read from the drawn spans and not from the milliseconds behind them, for the
    reason the cover figure already states: the panel's claim is about what the
    reader is looking at, so the number and the rectangles cannot disagree.
    """
    opening = _merged(_intervals([not_judged] if not_judged is not None else []))
    cooldown = _without(_merged(_intervals(unavailable)), opening)
    opening_length = _length(opening)
    cooldown_length = _length(cooldown)
    # Clamped against float error only: every span is already clipped to the
    # axis, so the complement cannot truly be negative.
    ready = max(0.0, TRACK_WIDTH - opening_length - cooldown_length)
    return _apportion((opening_length, cooldown_length, ready))


NO_AURA_DATA = "No aura data for it, so its cover is not drawn."
"""Said on a row whose ability the run's aura tables say nothing about.

The alternative -- printing zero seconds of cover -- would state as a
measured figure a thing nobody measured, which is the one reading a hover
panel over an empty stretch of chart most invites.
"""


def _chart_height(row_count: int) -> float:
    """The viewBox's own height, and so what a row's strip is a percentage of."""
    return FIRST_ROW_Y + row_count * ROW_HEIGHT + BOTTOM_MARGIN


def _row_panel(
    presses: int,
    bands: tuple[tuple[int, int], ...] | None,
    shares: tuple[int, int, int],
    span_seconds: float,
) -> Tooltip:
    """What one row's rectangles are worth, as the page's own panel.

    The press count carries no tier, which is this panel's way of saying
    measured. The three shares carry `inferred`, because the cooldown they
    divide by is a base value from `data/` that talents shorten and the log
    never records a reset -- the same claim `BADGE_INFERRED_CAPTION` grades on
    the chart.

    The cover line carries `derived`, and states its share on the same line as
    its seconds. Both figures come from the aura table and both are clipped to
    the drawn axis rather than to the fight, and that window is a choice: it is
    why this figure sits a fraction below the uptime Warcraft Logs reports for
    the same aura over the whole fight. `comparison/uptime.py` grades an aura's
    share of a chosen window the same way. Dividing by the axis is still the
    only reading that agrees with the rectangles, which is the discipline
    `_row_shares` keeps for the same reason. The share rides on the seconds
    rather than taking a line of its own because the three lines above it
    partition the track and sum to 100 -- a fourth percentage in that column
    would read as a partition that does not add up, which is the measurement
    design section 2.1 records.

    `bands` of None is not an empty tuple: the first says no aura table covers
    this ability, the second that a table covered it and recorded no window.
    The row draws nothing either way, so the note is the only place a reader
    can tell them apart, and printing zero seconds for the first would state as
    measured a thing nobody measured.
    """
    not_judged, on_cooldown, ready = shares
    inferred = badge_for(Confidence.INFERRED)
    lines = [
        TooltipLine(label="Presses", value=str(presses)),
        TooltipLine(label="Not judged", value=f"{not_judged}%", tier=inferred),
        TooltipLine(label="On cooldown", value=f"{on_cooldown}%", tier=inferred),
        TooltipLine(label="Ready and unpressed", value=f"{ready}%", tier=inferred),
    ]
    if bands is not None:
        seconds = sum(end - start for start, end in bands) / 1000
        share = round(seconds / span_seconds * 100)
        lines.append(
            TooltipLine(
                label="Buff up",
                value=f"{seconds:.1f} s ({share}%)",
                tier=badge_for(Confidence.DERIVED),
            )
        )
    return Tooltip(lines=tuple(lines), note="" if bands is not None else NO_AURA_DATA)


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
        return Press(x=_press_x(_track_x((at - origin_ms) / 1000, scale)))

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
        unavailable = tuple(
            Span(
                x=round(_track_x((at - origin_ms) / 1000, scale), PRECISION),
                # Clamped to the time remaining in the run after this press, not
                # to the run's whole length: the ability can only be judged
                # unavailable up to the axis end, never past it.
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
        )
        not_judged = Span(x=TRACK_ORIGIN_X, width=not_judged_width)
        rows.append(
            CooldownRow(
                label=ability.name,
                ability_id=ability.ability_id,
                tooltip=_row_panel(
                    len(presses),
                    bands,
                    _row_shares(not_judged, unavailable),
                    span_seconds,
                ),
                baseline_y=FIRST_ROW_Y + len(rows) * ROW_HEIGHT,
                # The label sits on the row's own middle, not on its top edge:
                # a baseline at the top would draw the glyphs over the row above.
                label_y=round(FIRST_ROW_Y + len(rows) * ROW_HEIGHT + ROW_HEIGHT / 2, PRECISION),
                presses=tuple(press_at(at) for at in presses),
                unavailable=unavailable,
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
                not_judged=not_judged,
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
    damage = _damage_track(loaded.damage_taken, actor_id, run, scale, origin)
    damage_done = _damage_done_track(loaded.damage_done, actor_id, run, scale, origin)

    if not rows and damage is None and damage_done is None:
        return PlayerTimeline(
            section=Section(state=SectionState.WITHHELD, reason=NOTHING_TRACKED_OR_TAKEN),
            width=TIMELINE_WIDTH,
        )

    # What the page actually drew, which is all either badge may claim. Every
    # one of these is optional on its own: a player can take damage and press
    # nothing, press an ability the aura tables know nothing about, or press it
    # late enough that the cooldown is still running when the run ends.
    measured_layers = tuple(
        layer
        for layer, drawn in (
            (MEASURED_DAMAGE_TAKEN, damage is not None),
            (MEASURED_PRESS_MARKS, bool(rows)),
            (MEASURED_COVER_WINDOWS, any(row.cover for row in rows)),
        )
        if drawn
    )
    inferred_layers = tuple(
        layer
        for layer, drawn in (
            # Every press dims the track after it, so the dimming stands or
            # falls with the rows themselves.
            (INFERRED_DIMMING, bool(rows)),
            (INFERRED_READY_TICK, any(row.ready_ticks for row in rows)),
        )
        if drawn
    )

    height = _chart_height(len(rows))
    # Stamped once the chart's height is known, which it is not while the rows
    # are being built: the height depends on how many of them there turned out
    # to be.
    rows = tuple(
        row.model_copy(update={"hit_top": round(row.baseline_y / height * 100, PRECISION)})
        for row in rows
    )

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
        damage_done=damage_done,
        damage_abstention="" if damage else NO_DAMAGE_TAKEN,
        damage_done_abstention="" if damage_done else NO_DAMAGE_DONE,
        cooldowns=rows,
        ticks=tuple(
            (round(x, PRECISION), label) for x, label in axis_ticks(span, scale, TRACK_ORIGIN_X)
        ),
        tick_y1=AXIS_TOP,
        tick_y2=height - BOTTOM_MARGIN,
        tick_label_y=height - TICK_LABEL_MARGIN,
        label_x=LABEL_X,
        row_icon_x=ICON_X,
        row_icon_size=ICON_SIZE,
        row_hit_height=round(ROW_HEIGHT / height * 100, PRECISION),
        row_height=ROW_HEIGHT,
        press_width=PRESS_WIDTH,
        state_key=STATE_KEY,
        legend=LEGEND,
        # Each badge is shown only where it has something to grade, and says
        # which layers those are. A grade on something absent from the page is
        # a claim about nothing, and a caption listing layers the chart did not
        # draw is the same claim in smaller print -- which is why the badge and
        # its caption are decided together, from one list.
        badge_measured=badge_for(Confidence.MEASURED) if measured_layers else None,
        badge_measured_caption=_graded_caption(measured_layers),
        # Derived grades one layer, so its caption never varies.
        badge_derived=badge_for(Confidence.DERIVED) if damage_done else None,
        badge_derived_caption=BADGE_DERIVED_CAPTION if damage_done else "",
        badge_inferred=badge_for(Confidence.INFERRED) if inferred_layers else None,
        badge_inferred_caption=_graded_caption(inferred_layers),
    )
