# ABOUTME: One player's run on a single axis, in viewBox units the template only prints.
# ABOUTME: Pull bands behind, damage taken above, one row per cooldown the player owns.

from collections import defaultdict

from wowperf.domain.events import CastEvent, DamageTakenEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.frame import badge_for, run_seconds, run_start_ms
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
    TRACK_X0,
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

AXIS_TOP = 22.0
"""Where the tick lines start, above the pull band."""

BAND_Y = 28.0
"""The pull band's top edge: a thin strip the rest of the drawing hangs under."""

BAND_HEIGHT = 10.0

DAMAGE_BASELINE_Y = 76.0
"""The foot of the damage bars. They grow upward from here."""

DAMAGE_HEIGHT = 32.0
"""How tall the largest bucket is drawn. Every other bar is a fraction of it."""

BUCKET_SECONDS = 5.0
"""How much of the run one damage bar covers.

Narrow enough that a single lethal spike stays one bar rather than being
averaged into its neighbours, wide enough that a run does not emit thousands
of rectangles into a file that has to stay openable. Measured 2026-09-10
against report 6Kx1P9GbNXrcLdHa fight 36 (five players, four deaths):
re-rendering at 2, 5 and 10 seconds produced 3,266, 2,062 and 1,609 SVG
rects respectively (721,206, 632,149 and 598,706 bytes). Checked against
the four buckets surrounding each death, no width concentrated every
death's damage into one bar best: 5 seconds did for one death (91%,
against 47% at 2 seconds and 50% at 10), tied 2 seconds for a second
(100%, against 71% at 10), sat between the other two for a third (58%,
between 52% at 2 seconds and 72% at 10), and was the worst of the three
for the fourth (50%, against 79% at 2 seconds and 54% at 10). With spike
fidelity split across widths rather than favouring one, rect count
decides: 5 seconds holds well under 2 seconds' count for a comparable
spread of outcomes, at the cost of a few hundred more rects than 10
seconds would use.
"""

FIRST_ROW_Y = 96.0
"""The baseline of the first cooldown row."""

ROW_HEIGHT = 16.0

BOTTOM_MARGIN = 28.0
"""Gap between the last row and the viewBox's bottom edge, holding the tick labels."""

TICK_LABEL_MARGIN = 12.0

LABEL_X = 40.0
"""Where a row's ability name ends, right-aligned into the margin left of the axis."""

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
    "to a log fetched per fight."
)

BADGE_MEASURED_CAPTION = "the damage bars and the press marks."
"""What the measured badge grades: both are events the log itself emitted."""

BADGE_INFERRED_CAPTION = "the dimming."
"""What the inferred badge grades: a cooldown length assumed from its base value, since
talents shorten it and the log records no reset."""


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
            x=round(TRACK_X0 + index * BUCKET_SECONDS * scale, PRECISION),
            width=max(width, MIN_BLOCK_WIDTH),
            y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT * amount / peak, PRECISION),
            height=round(DAMAGE_HEIGHT * amount / peak, PRECISION),
        )
        for index, amount in sorted(buckets.items())
    )
    return DamageTrack(
        baseline_y=DAMAGE_BASELINE_Y,
        bars=bars,
        peak_label=f"Tallest bar: {peak:,} damage in {int(BUCKET_SECONDS)} seconds",
    )


def _cooldown_rows(
    casts: tuple[CastEvent, ...],
    abilities: tuple[CooldownAbility, ...],
    actor_id: int,
    scale: float,
    origin_ms: int,
    span_seconds: float,
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
        x = round(TRACK_X0 + (at - origin_ms) / 1000 * scale, PRECISION)
        return Press(x=x, icon_x=round(x - ROW_HEIGHT / 2, PRECISION))

    rows: list[CooldownRow] = []
    for ability in abilities:
        if ability.ability_id not in owned:
            continue
        presses = sorted(
            cast.timestamp_ms for cast in ours if cast.ability_id == ability.ability_id
        )
        not_judged_width = round(min(ability.cooldown_seconds, span_seconds) * scale, PRECISION)
        rows.append(
            CooldownRow(
                label=ability.name,
                ability_id=ability.ability_id,
                baseline_y=FIRST_ROW_Y + len(rows) * ROW_HEIGHT,
                presses=tuple(press_at(at) for at in presses),
                unavailable=tuple(
                    Span(
                        x=round(TRACK_X0 + (at - origin_ms) / 1000 * scale, PRECISION),
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
                not_judged=Span(x=TRACK_X0, width=not_judged_width),
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

    scale = axis_scale(span)
    origin = run_start_ms(run)
    rows = _cooldown_rows(
        loaded.casts,
        throughput.for_spec(class_name, spec) + defensives.for_spec(class_name, spec),
        actor_id,
        scale,
        origin,
        span,
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
        width=TIMELINE_WIDTH,
        height=height,
        pulls=_pull_bands(run, scale, origin),
        band_y=BAND_Y,
        band_height=BAND_HEIGHT,
        damage=damage,
        cooldowns=rows,
        ticks=axis_ticks(span, scale),
        tick_y1=AXIS_TOP,
        tick_y2=height - BOTTOM_MARGIN,
        tick_label_y=height - TICK_LABEL_MARGIN,
        label_x=LABEL_X,
        row_height=ROW_HEIGHT,
        legend=LEGEND,
        badge_measured=badge_for(Confidence.MEASURED),
        badge_measured_caption=BADGE_MEASURED_CAPTION,
        badge_inferred=badge_for(Confidence.INFERRED),
        badge_inferred_caption=BADGE_INFERRED_CAPTION,
    )
