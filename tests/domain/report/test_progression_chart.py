# ABOUTME: The attempts chart's geometry: a taller bar is a deeper attempt, not a worse one.
# ABOUTME: Depth counts down, so every height here is an inversion a test must be able to catch.

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series
from wowperf.domain.report.model import SectionState
from wowperf.domain.report.progression_chart import (
    CHART_HEIGHT,
    CHART_WIDTH,
    build_attempts_chart,
)


def test_a_deeper_attempt_draws_a_taller_bar() -> None:
    """The whole chart in one assertion: depth counts down and height counts up.

    Delete the inversion in `build_attempts_chart` and this fails, because the
    16.5% attempt would then draw the shortest bar on the page instead of the
    tallest.
    """
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=64.8),
        a_loaded_attempt(2, remaining=16.5),
        a_loaded_attempt(3, remaining=85.8),
    )

    chart = build_attempts_chart(series)

    heights = [bar.height for bar in chart.bars]
    assert heights[1] > heights[0] > heights[2]


def test_the_bars_stand_on_the_baseline_and_stay_inside_the_drawing() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=0.01),
        a_loaded_attempt(2, remaining=100.0),
    )

    chart = build_attempts_chart(series)

    assert chart.width == CHART_WIDTH
    assert chart.height == CHART_HEIGHT
    for bar in chart.bars:
        assert bar.y >= 0.0
        assert bar.y + bar.height <= chart.baseline_y + 0.001
        assert bar.x >= 0.0
        assert bar.x + bar.width <= chart.width


def test_the_deepest_attempt_carries_its_own_class() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=20.0),
        a_loaded_attempt(3, remaining=70.0),
    )

    chart = build_attempts_chart(series)

    assert [("attempt-best" in bar.css_class) for bar in chart.bars] == [False, True, False]


def test_a_kill_carries_its_own_class_too() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=0.01, kill=True),
    )

    chart = build_attempts_chart(series)

    assert "attempt-kill" in chart.bars[1].css_class
    assert "attempt-kill" not in chart.bars[0].css_class


def test_an_attempt_with_no_reading_leaves_its_slot_empty() -> None:
    """Its slot, not its place in the row: a missing bar must not shift the
    attempts after it, or bar 3 would sit where a reader reads bar 2."""
    with_gap = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
        a_loaded_attempt(3, remaining=40.0),
    )
    without_gap = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0),
        a_loaded_attempt(2, remaining=50.0),
        a_loaded_attempt(3, remaining=40.0),
    )

    gapped = build_attempts_chart(with_gap)
    whole = build_attempts_chart(without_gap)

    assert len(gapped.bars) == 2
    assert len(whole.bars) == 3
    assert gapped.bars[1].x == whole.bars[2].x
    assert "1 attempt carries no depth reading" in gapped.legend


def test_a_night_with_no_reading_at_all_withholds_the_chart() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=50.0, fight_percentage=None),
        a_loaded_attempt(2, remaining=50.0, fight_percentage=None),
    )

    chart = build_attempts_chart(series)

    assert chart.section.state is SectionState.WITHHELD
    assert chart.bars == ()
    assert "no depth reading" in chart.section.reason


def test_every_tick_label_names_a_depth_the_axis_reaches() -> None:
    chart = build_attempts_chart(
        a_loaded_series(a_loaded_attempt(1, remaining=50.0), a_loaded_attempt(2, remaining=40.0))
    )

    assert [label for _, label in chart.ticks] == ["0%", "25%", "50%", "75%", "100%"]
    ys = [y for y, _ in chart.ticks]
    assert ys[0] == chart.baseline_y
    assert ys == sorted(ys, reverse=True)
    assert chart.tick_x1 < chart.tick_x2


def test_the_legend_names_the_depth_scale_the_bars_are_on() -> None:
    """Section 2.4's Global Constraint: every printed percentage names which one
    it is. The bars' own height is a percentage read upward -- depth reached --
    the one figure on this page with no naming of its own on the axis itself,
    so the legend sentence above the chart is where it has to say so, and it
    has to read the same word `depth_label` gives the header and the table.
    """
    on_boss_health = build_attempts_chart(
        a_loaded_series(
            a_loaded_attempt(1, remaining=50.0, boss_percentage=30.0),
            a_loaded_attempt(2, remaining=60.0, boss_percentage=40.0),
        )
    )
    assert "depth reached (boss health)" in on_boss_health.legend

    on_progress = build_attempts_chart(
        a_loaded_series(
            a_loaded_attempt(1, remaining=50.0),
            a_loaded_attempt(2, remaining=60.0),
        )
    )
    assert "depth reached (encounter progress)" in on_progress.legend


def test_a_bars_hover_text_names_the_depth_scale_too() -> None:
    """The legend names the scale once; a reader hovering one bar, without
    having read the legend first, gets the same naming again."""
    chart = build_attempts_chart(
        a_loaded_series(
            a_loaded_attempt(1, remaining=50.0, boss_percentage=30.0),
            a_loaded_attempt(2, remaining=60.0, boss_percentage=40.0),
        )
    )
    assert all("(boss health)" in bar.hover for bar in chart.bars)
