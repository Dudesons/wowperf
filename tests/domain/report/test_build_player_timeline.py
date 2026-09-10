# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import NO_DEFENSIVES, a_pull, a_run
from wowperf.domain.model import LoadedRun
from wowperf.domain.report.model import PlayerTimeline, SectionState
from wowperf.domain.report.player_timeline import (
    FIRST_ROW_Y,
    ROW_HEIGHT,
    build_player_timeline,
)
from wowperf.domain.report.timeline import TRACK_X0, TRACK_X1, axis_scale, axis_ticks
from wowperf.domain.season import ThroughputCooldowns

NO_THROUGHPUT = ThroughputCooldowns(entries=())


def test_the_axis_scale_fills_the_track_width() -> None:
    scale = axis_scale(100.0)
    assert TRACK_X0 + 100.0 * scale == TRACK_X1


def test_a_run_of_no_length_scales_to_zero_rather_than_dividing_by_it() -> None:
    assert axis_scale(0.0) == 0.0


def test_the_first_tick_sits_at_the_axis_origin() -> None:
    ticks = axis_ticks(1200.0, axis_scale(1200.0))
    assert ticks[0][0] == TRACK_X0
    assert ticks[0][1] == "0:00"


def a_timeline(loaded: LoadedRun, **kwargs: object) -> PlayerTimeline:
    return build_player_timeline(
        loaded,
        actor_id=int(kwargs.get("actor_id", 1)),  # type: ignore[call-overload]
        class_name=str(kwargs.get("class_name", "DeathKnight")),
        spec=str(kwargs.get("spec", "Blood")),
        defensives=kwargs.get("defensives", NO_DEFENSIVES),  # type: ignore[arg-type]
        throughput=kwargs.get("throughput", NO_THROUGHPUT),  # type: ignore[arg-type]
    )


def test_a_player_with_nothing_to_draw_gets_a_withheld_section_and_no_bands() -> None:
    timeline = a_timeline(LoadedRun(run=a_run(pulls=())))
    assert timeline.section.state is SectionState.WITHHELD
    assert timeline.section.reason
    assert timeline.pulls == ()


def test_a_pull_band_starts_where_the_axis_starts_and_a_boss_is_marked() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.pulls[0].x == TRACK_X0
    assert timeline.pulls[1].is_boss
    assert "block-boss" in timeline.pulls[1].css_class


def test_the_height_grows_with_the_rows_it_has_to_hold() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.height == FIRST_ROW_Y + len(timeline.cooldowns) * ROW_HEIGHT + 28.0
