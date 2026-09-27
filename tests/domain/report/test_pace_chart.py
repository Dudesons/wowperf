# ABOUTME: Behaviour tests for the pace chart: every coordinate, tick and mark it draws.
# ABOUTME: Built from Task 1's `read_pace` readings, never a hand-typed chart shape.

import re

import pytest

from tests.domain.comparison.test_pace_curve import a_kill, steady
from wowperf.domain.comparison.pace_curve import read_pace
from wowperf.domain.report.alive_chart import PLOT_X0, PLOT_X1
from wowperf.domain.report.pace_chart import build_pace_chart

TICK_LABEL = re.compile(r"^\d+%$")


def test_the_band_polygon_is_the_highs_then_the_lows_reversed() -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None

    chart = build_pace_chart(reading, 30.0)

    assert chart is not None
    assert len(chart.band) == 2 * len(reading.seconds)
    # The polygon closes: its first point (the first second's high) and its
    # last point (the same second's low, reached by walking the lows
    # backwards) share an x, and the high sits above the low on the page.
    assert chart.band[0].x == pytest.approx(chart.band[-1].x)
    assert chart.band[0].y <= chart.band[-1].y


def test_a_behind_reading_ends_below_the_bands_own_low_edge() -> None:
    """"Below" on the page is a larger y: this raid dealt less than the kill
    that had dealt least, so its line sits under the band's own floor."""
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(80, 30), kills, 30.0)
    assert reading is not None
    assert reading.seconds[-1].state.value == "behind"

    chart = build_pace_chart(reading, 30.0)

    assert chart is not None
    last_low = chart.band[len(reading.seconds)]  # the lows walk back from the last second
    assert chart.ours[-1].y > last_low.y


def test_behind_x_is_where_the_final_stretch_began() -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(80, 30), kills, 30.0)
    assert reading is not None

    chart = build_pace_chart(reading, 30.0)

    assert chart is not None
    expected = PLOT_X0 + (1 / 30.0) * (PLOT_X1 - PLOT_X0)
    assert chart.behind_x == pytest.approx(expected)


def test_cut_x_is_set_only_when_the_band_was_cut() -> None:
    cut_kills = (a_kill(100, 20), a_kill(100, 20), a_kill(100, 60), a_kill(100, 60))
    cut_reading = read_pace(steady(100, 40), cut_kills, 40.0)
    assert cut_reading is not None
    assert cut_reading.band_cut is True

    cut_chart = build_pace_chart(cut_reading, 40.0)
    assert cut_chart is not None
    expected = PLOT_X0 + (20 / 40.0) * (PLOT_X1 - PLOT_X0)
    assert cut_chart.cut_x == pytest.approx(expected)
    assert "fewer than three kills" in cut_chart.legend

    whole_kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    whole_reading = read_pace(steady(100, 30), whole_kills, 30.0)
    assert whole_reading is not None
    assert whole_reading.band_cut is False

    whole_chart = build_pace_chart(whole_reading, 30.0)
    assert whole_chart is not None
    assert whole_chart.cut_x is None


def test_every_tick_label_is_a_bare_percentage() -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None

    chart = build_pace_chart(reading, 30.0)

    assert chart is not None
    assert chart.ticks
    for _, label in chart.ticks:
        assert TICK_LABEL.match(label), label


def test_the_fallback_legend_names_the_slowest_kill() -> None:
    fast, slow = a_kill(200, 30), a_kill(100, 60)
    reading = read_pace(steady(150, 40), (fast, slow), 40.0)
    assert reading is not None
    assert reading.single is True

    chart = build_pace_chart(reading, 40.0)

    assert chart is not None
    assert "slowest reference kill" in chart.legend


def test_none_on_a_reading_with_nothing_compared() -> None:
    assert read_pace(steady(100, 30), (), 30.0) is None
    kills = (a_kill(100, 20), a_kill(100, 20), a_kill(100, 20))
    reading = read_pace(steady(100, 10), kills, 0.0)
    assert reading is not None
    assert reading.seconds == ()

    assert build_pace_chart(reading, 10.0) is None
