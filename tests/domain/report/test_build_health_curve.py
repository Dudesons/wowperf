# ABOUTME: Behaviour tests for the death card's health curve: time on the x axis, a step between
# ABOUTME: events, and the log's own readings drawn apart from the arithmetic that joins them.

from tests.domain.analysis.test_recap_timeline import a_death, a_sample
from wowperf.domain.analysis.recap import HIT, RecapEvent
from wowperf.domain.report.health_curve import (
    DEATH_TICK,
    LINE_LEGEND,
    PLOT_BOTTOM,
    PLOT_TOP,
    PLOT_X0,
    PLOT_X1,
    READING_LEGEND,
    UNANCHORED_LINE_LEGEND,
    build_health_curve,
)
from wowperf.domain.report.model import HealthCurve


def an_event(at_ms: int, percent: int | None, kind: str = HIT) -> RecapEvent:
    return RecapEvent(
        kind=kind, timestamp_ms=at_ms, ability_name="Snowdrift", health_percent=percent
    )


def test_the_curve_places_x_by_time_and_not_by_row_index() -> None:
    # One second into the ten-second window and one second before its end. Spaced
    # by index the two would sit at the axis's extremes; spaced by time they sit a
    # tenth in from each.
    curve = build_health_curve((an_event(51_000, 90), an_event(59_000, 10)), (), a_death())
    assert curve is not None
    span = PLOT_X1 - PLOT_X0
    assert [point.x for point in curve.points][:2] == [
        round(PLOT_X0 + span * 0.1, 1),
        round(PLOT_X0 + span * 0.9, 1),
    ]


def test_there_is_no_curve_when_no_event_carries_health() -> None:
    assert build_health_curve((an_event(51_000, None),), (), a_death()) is None


def test_a_reading_is_drawn_at_the_value_the_log_stated() -> None:
    # The line says 10% because a hit landed; the reading says 40% because that is
    # what the log carried. The dot must follow the log, not the arithmetic.
    curve = build_health_curve(
        (an_event(55_000, 10),), (a_sample(55_000, 40_000, maximum=100_000),), a_death()
    )
    assert curve is not None
    assert [reading.percent for reading in curve.readings] == [40]


def x_at(fraction: float) -> float:
    """Where a moment that far through the run-up sits, as the test's own arithmetic."""
    return round(PLOT_X0 + (PLOT_X1 - PLOT_X0) * fraction, 1)


def y_at(percent: int) -> float:
    return round(PLOT_BOTTOM - (PLOT_BOTTOM - PLOT_TOP) * percent / 100, 1)


def corners(curve: HealthCurve) -> list[tuple[float, float]]:
    return [(point.x, point.y) for point in curve.points]


def test_the_line_holds_its_value_until_the_next_event() -> None:
    # Level to the second event's moment, and only there down to its value: a
    # slope between them would claim a drain that nothing in the log measured.
    curve = build_health_curve((an_event(51_000, 90), an_event(59_000, 10)), (), a_death())
    assert curve is not None
    assert corners(curve)[:3] == [
        (x_at(0.1), y_at(90)),
        (x_at(0.9), y_at(90)),
        (x_at(0.9), y_at(10)),
    ]


def test_events_sharing_a_moment_add_no_level_run() -> None:
    curve = build_health_curve((an_event(55_000, 90), an_event(55_000, 30)), (), a_death())
    assert curve is not None
    assert corners(curve)[:2] == [(x_at(0.5), y_at(90)), (x_at(0.5), y_at(30))]


def test_the_line_runs_on_to_the_death_at_its_last_value() -> None:
    curve = build_health_curve((an_event(55_000, 30),), (), a_death())
    assert curve is not None
    assert corners(curve)[-1] == (PLOT_X1, y_at(30))


def test_events_before_the_first_reading_are_not_drawn() -> None:
    curve = build_health_curve((an_event(51_000, None), an_event(55_000, 30)), (), a_death())
    assert curve is not None
    assert corners(curve)[0] == (x_at(0.5), y_at(30))


def test_the_axis_counts_down_to_the_death() -> None:
    curve = build_health_curve((an_event(55_000, 30),), (), a_death())
    assert curve is not None
    assert [tick.label for tick in curve.ticks] == ["10 s", "8 s", "6 s", "4 s", "2 s", "death"]
    assert [curve.ticks[0].x, curve.ticks[-1].x] == [PLOT_X0, PLOT_X1]


def test_the_guides_name_full_health_and_none() -> None:
    curve = build_health_curve((an_event(55_000, 30),), (), a_death())
    assert curve is not None
    assert [(guide.label, guide.y) for guide in curve.guides] == [
        ("100%", PLOT_TOP),
        ("0%", PLOT_BOTTOM),
    ]


def test_the_readings_and_the_line_carry_their_own_badges() -> None:
    curve = build_health_curve((an_event(55_000, 30),), (a_sample(55_000, 30_000),), a_death())
    assert curve is not None
    assert curve.line_badge is not None and curve.line_badge.label == "derived"
    assert curve.reading_badge is not None and curve.reading_badge.label == "measured"
    assert (curve.reading_legend, curve.line_legend) == (READING_LEGEND, LINE_LEGEND)


def test_a_curve_with_no_reading_of_its_own_claims_no_measurement() -> None:
    # Health here came from an anchor before the axis opens, so every point on
    # the line is arithmetic and nothing on the drawing was measured.
    curve = build_health_curve((an_event(55_000, 30),), (), a_death())
    assert curve is not None
    assert curve.reading_badge is None
    assert curve.reading_legend == ""
    assert curve.line_legend == UNANCHORED_LINE_LEGEND


def test_the_axis_labels_sit_clear_of_the_plot() -> None:
    # The template is handed these extents rather than the module's constants, and
    # a label placed inside the plot would cross the line it is there to label.
    curve = build_health_curve((an_event(55_000, 30),), (), a_death())
    assert curve is not None
    assert curve.label_x < curve.plot_x0 < curve.plot_x1
    assert curve.tick_label_y > curve.guides[-1].y


def test_the_time_labels_fit_inside_the_viewbox() -> None:
    # The rightmost label is centred on the axis's end, so half of it hangs past
    # that point and a plot drawn to the viewBox's edge clips the word "death".
    # The margin asked for here is a whole label wide rather than half of one, so
    # the last label is clear of the edge rather than touching it.
    curve = build_health_curve((an_event(55_000, 30),), (), a_death())
    assert curve is not None
    assert curve.width - curve.plot_x1 >= len(DEATH_TICK) * 5
