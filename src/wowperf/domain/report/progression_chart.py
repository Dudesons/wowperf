# ABOUTME: The night's shape as one bar per attempt, in viewBox units the template prints.
# ABOUTME: Depth counts down and the chart counts up, so every height here is an inversion.

from wowperf.domain.progression import LoadedProgression, remaining_percent
from wowperf.domain.report.model import Section, SectionState
from wowperf.domain.report.progression_frame import depth_label
from wowperf.domain.report.progression_model import AttemptBar, AttemptsChart

CHART_WIDTH = 680.0
CHART_HEIGHT = 220.0

PLOT_X0 = 46.0
"""Where the bars start: right of the depth axis's labels."""

PLOT_X1 = 664.0
"""Where the bars end."""

PLOT_TOP = 16.0
"""The y of 100% reached -- the top of a bar that killed the boss."""

BASELINE_Y = 186.0
"""The y every bar stands on: 0% reached, the floor of the drawing."""

BAR_GAP = 6.0
"""The gap between one attempt's slot and the next."""

MIN_BAR_HEIGHT = 2.0
"""An attempt that moved the boss almost not at all still draws something.

Zero height renders nothing, and a slot with nothing in it reads as an attempt
the tool failed to measure rather than one that made no progress.
"""

TICK_PERCENTS = (0, 25, 50, 75, 100)
"""One gridline every quarter: enough to place a bar, few enough to stay legible."""

TICK_LABEL_X = 40.0
"""Where a gridline's label sits, right-aligned against the plot's left edge."""


def _legend(label: str) -> str:
    """The chart's caption, naming the one thing its axis never spells out on its own.

    Every tick reads a bare percentage -- `0%` through `100%` -- and means
    depth *reached*, the opposite of the scale every other percentage on this
    page prints (`remaining_percent`, the table's `Depth left` column, and this
    same bar's own hover text). `label` is read from `depth_label`, the one
    place that decides whether a night is on boss health or encounter
    progress, so the axis and the header can never name two different scales.
    """
    return (
        f"One bar an attempt, in pull order. Height is depth reached ({label}): a taller "
        "bar got further into the encounter. The outlined bar is the attempt that went "
        "deepest."
    )


NO_READING_REASON = (
    "This series has no depth reading on any attempt, so there is no shape to draw. "
    "The attempts table below still lists every one of them."
)


def build_attempts_chart(series: LoadedProgression) -> AttemptsChart:
    """One bar per qualifying attempt, depth reached upward from the baseline.

    Depth counts down -- `fightPercentage` and `bossPercentage` both report
    what was *left* -- and the chart draws what was *reached*, so every height
    is `100 - remaining` scaled to the plot. Drawing `remaining` directly would
    put the worst attempt of the night at the top of the page and look entirely
    plausible doing it.

    Slots are laid out by an attempt's position in pull order, not by its
    position among the attempts that carry a reading: an attempt the report
    gave no percentage for leaves its slot empty rather than closing the gap,
    so the bars stay aligned with the table's row numbers.
    """
    progression = series.progression
    attempts = progression.attempts
    uses_boss_health = progression.uses_boss_health
    deepest = progression.deepest
    label = depth_label(uses_boss_health)

    blank = AttemptsChart(section=Section(state=SectionState.WITHHELD, reason=NO_READING_REASON))
    if not attempts:
        return blank

    span = BASELINE_Y - PLOT_TOP
    ticks = tuple(
        (BASELINE_Y - (percent / 100.0) * span, f"{percent}%") for percent in TICK_PERCENTS
    )
    slot = (PLOT_X1 - PLOT_X0) / len(attempts)
    width = max(slot - BAR_GAP, 1.0)

    bars: list[AttemptBar] = []
    missing = 0
    for index, attempt in enumerate(attempts):
        left = remaining_percent(attempt, uses_boss_health=uses_boss_health)
        if left is None:
            missing += 1
            continue
        reached = max(0.0, min(100.0, 100.0 - left))
        height = max(MIN_BAR_HEIGHT, (reached / 100.0) * span)
        classes = ["attempt-bar"]
        if deepest is not None and attempt.fight_id == deepest.fight_id:
            classes.append("attempt-best")
        if attempt.kill:
            classes.append("attempt-kill")
        bars.append(
            AttemptBar(
                x=PLOT_X0 + index * slot,
                y=BASELINE_Y - height,
                width=width,
                height=height,
                css_class=" ".join(classes),
                hover=(
                    f"Attempt {index + 1}: {left:.1f}% left ({label}), "
                    f"{attempt.duration_seconds:.0f} seconds"
                ),
            )
        )

    if not bars:
        return blank

    legend = _legend(label)
    if missing:
        legend = (
            f"{legend} {missing} attempt{'' if missing == 1 else 's'} "
            f"carr{'ies' if missing == 1 else 'y'} no depth reading and draw"
            f"{'s' if missing == 1 else ''} no bar."
        )
    return AttemptsChart(
        section=Section(state=SectionState.PRESENT),
        bars=tuple(bars),
        ticks=ticks,
        legend=legend,
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        tick_x1=PLOT_X0,
        tick_x2=PLOT_X1,
        tick_label_x=TICK_LABEL_X,
        baseline_y=BASELINE_Y,
    )
