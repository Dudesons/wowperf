# ABOUTME: Both runs on one elapsed-time axis, in viewBox units the template only prints.
# ABOUTME: Every coordinate is computed here, so the SVG on the page decides nothing.

from wowperf.domain.comparison.sample import SpeedSample
from wowperf.domain.model import Run
from wowperf.domain.report.frame import format_seconds, run_seconds, run_start_ms
from wowperf.domain.report.model import (
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)

TIMELINE_WIDTH = 680.0
TIMELINE_HEIGHT = 208.0
TRACK_X0 = 46.0
TRACK_X1 = 656.0
MIN_BLOCK_WIDTH = 2.0
"""A pull narrower than this reads as nothing at all, so it is drawn at this width."""

TICK_SECONDS = 600
"""One axis label every ten minutes: enough to place a pull, few enough to stay legible."""

AXIS_TOP = 46.0
"""Where the tick lines start: just above the top track's caption."""

AXIS_BOTTOM_MARGIN = 32.0
"""Gap between the tick lines' foot and the viewBox's bottom edge."""

TICK_LABEL_MARGIN = 16.0
"""Gap between the tick labels' baseline and the viewBox's bottom edge."""

CAPTION_DY = -10.0
"""How far above its track's baseline a caption's text sits."""

BLOCK_HEIGHT = 26.0
"""Every block's height, shared by both tracks."""

OURS_BASELINE_Y = 58.0
"""The y at which our track's blocks and caption sit."""

THEIRS_BASELINE_Y = 132.0
"""The y at which the reference track's blocks and caption sit."""

COMPARED_TIMELINE_LEGEND = (
    "A thin outline marks a boss pull. A heavier outline marks a pack we pulled that the "
    "reference run skipped. A dashed, unfilled block is a pack the reference run pulled that "
    "we skipped."
)
"""What the marks mean when a reference track is drawn beside ours."""

LONE_TIMELINE_LEGEND = (
    "A thin outline marks a boss pull. Only this run is drawn: no reference in the sample ran "
    "our keystone level, and a pull lasts a different length of time at every level, so there "
    "is nothing here to compare against."
)
"""Why the second track is missing, said where a reader would look for it.

The marks that describe a reference — the heavier and dashed outlines — are
left out rather than explained, because no block on the page carries one.
"""


def _block_css_class(kind: str, is_boss: bool, track_class: str) -> str:
    """The whole class attribute for one block.

    `extra` gets its own tan fill but also a heavier outline, so the mark
    that matters most on this chart survives a colour-blind or greyscale
    reading rather than resting on hue alone. `skipped` is already
    unfilled and dashed, which is a shape difference and needs no help.
    """
    if kind == "extra":
        classes = ["block-extra"]
    elif kind == "skipped":
        classes = ["block-skipped"]
    else:
        classes = ["block", track_class] if track_class else ["block"]
    if is_boss:
        classes.append("block-boss")
    return " ".join(classes)


def _blocks(
    run: Run, kinds: dict[int, str], scale: float, origin_ms: int, track_class: str = ""
) -> tuple[TimelineBlock, ...]:
    blocks = []
    for pull in run.pulls:
        kind = kinds.get(pull.index, "matched")
        blocks.append(
            TimelineBlock(
                label=pull.name,
                x=TRACK_X0 + (pull.start_ms - origin_ms) / 1000 * scale,
                width=max(pull.duration_seconds * scale, MIN_BLOCK_WIDTH),
                is_boss=pull.is_boss,
                kind=kind,
                css_class=_block_css_class(kind, pull.is_boss, track_class),
            )
        )
    return tuple(blocks)


def axis_scale(seconds: float) -> float:
    """viewBox units per second for a drawing that fills the track width.

    A span of no length scales to zero rather than dividing by it: a run with
    one instantaneous pull is degenerate, not an error, and every coordinate
    derived from a zero scale collapses onto the axis origin where a reader can
    see there is nothing to read.
    """
    return (TRACK_X1 - TRACK_X0) / seconds if seconds > 0 else 0.0


def axis_ticks(longest: float, scale: float) -> tuple[tuple[float, str], ...]:
    """One labelled mark every `TICK_SECONDS`, from the origin to `longest`."""
    marks = []
    second = 0
    while second <= longest:
        label = format_seconds(float(second))
        assert label is not None  # a float input always formats to a string
        marks.append((TRACK_X0 + second * scale, label))
        second += TICK_SECONDS
    return tuple(marks)


def _timeline_caption(label: str, seconds: float, suffix: str = "") -> str:
    """State which span this caption measures, not just its length.

    `seconds` spans the first pull's start to the last pull's end. The
    header states a different, longer figure — `keystone_time_seconds`,
    which also counts the trip to the first pack and Blizzard's death
    penalties. Naming the span here keeps a reader from seeing two numbers
    for the same run and assuming one of them is wrong. `suffix`, when
    given, names the sample size a reference track was drawn from, so a
    reader never mistakes one picture for the whole sample.
    """
    formatted = format_seconds(seconds)
    assert formatted is not None  # a float input always formats to a string
    base = f"{label} — {formatted} from first pull to last"
    return f"{base}, {suffix}" if suffix else base


def build_timeline(ours: Run, sample: SpeedSample | None, section: Section) -> Timeline:
    """Both runs on one elapsed-time axis, scaled so the longer one fills the width.

    The space between blocks is travel. That is why this layout exists: a
    per-pull table compares durations, and durations are rarely where a
    Mythic+ run loses its time.

    The reference track is drawn from `sample.duration_eligible`'s best-aligned
    member — highest `Alignment.matched_share`, compared pairwise and never
    averaged — and from no one else: a member outside that subset sits at a
    different keystone level, where `compare.duration` already refuses to print
    a number, and a picture of its pull lengths would draw exactly what that
    finding withheld. The member's `Alignment` was computed once, when the
    sample was built, and is used as-is here rather than recomputed.

    Our own track is drawn either way. Its blocks and the travel between them
    are measured on our own log and mean the same thing whether or not anyone
    else ran this keystone level; withholding them because no reference was
    comparable would hide a fact to protect a comparison that was never needed
    to state it. `legend` then says why the second track is missing.
    """
    if section.state is SectionState.WITHHELD:
        return Timeline(section=section, width=TIMELINE_WIDTH, height=TIMELINE_HEIGHT)

    eligible = sample.duration_eligible if sample is not None else ()
    member = (
        max(eligible, key=lambda candidate: candidate.alignment.matched_share)
        if eligible
        else None
    )

    our_seconds = run_seconds(ours)
    their_seconds = run_seconds(member.run) if member is not None else 0.0
    longest = max(our_seconds, their_seconds)
    scale = axis_scale(longest)

    our_kinds = {index: "extra" for index in member.alignment.only_ours} if member else {}

    theirs_track = None
    if member is not None and sample is not None:
        theirs_track = TimelineTrack(
            caption=_timeline_caption(
                "Reference", their_seconds, suffix=f"one of {len(sample.members)} fast runs"
            ),
            baseline_y=THEIRS_BASELINE_Y,
            blocks=_blocks(
                member.run,
                {index: "skipped" for index in member.alignment.only_theirs},
                scale,
                run_start_ms(member.run),
                track_class="block-theirs",
            ),
        )

    return Timeline(
        section=section,
        ours=TimelineTrack(
            caption=_timeline_caption("Ours", our_seconds),
            baseline_y=OURS_BASELINE_Y,
            blocks=_blocks(ours, our_kinds, scale, run_start_ms(ours)),
        ),
        theirs=theirs_track,
        legend=COMPARED_TIMELINE_LEGEND if theirs_track else LONE_TIMELINE_LEGEND,
        ticks=axis_ticks(longest, scale),
        width=TIMELINE_WIDTH,
        height=TIMELINE_HEIGHT,
        tick_y1=AXIS_TOP,
        tick_y2=TIMELINE_HEIGHT - AXIS_BOTTOM_MARGIN,
        tick_label_y=TIMELINE_HEIGHT - TICK_LABEL_MARGIN,
        caption_x=TRACK_X0,
        caption_dy=CAPTION_DY,
        block_height=BLOCK_HEIGHT,
    )
