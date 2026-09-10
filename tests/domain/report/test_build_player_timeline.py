# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import NO_DEFENSIVES, a_pull, a_run
from wowperf.domain.model import LoadedRun
from wowperf.domain.report.model import PlayerTimeline, SectionState
from wowperf.domain.report.player_timeline import (
    FIRST_ROW_Y,
    PRECISION,
    ROW_HEIGHT,
    build_player_timeline,
)
from wowperf.domain.report.timeline import TRACK_X0, TRACK_X1, axis_scale, axis_ticks
from wowperf.domain.season import Defensives, ThroughputCooldowns

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


def a_timeline(
    loaded: LoadedRun,
    *,
    actor_id: int = 1,
    class_name: str = "DeathKnight",
    spec: str = "Blood",
    defensives: Defensives = NO_DEFENSIVES,
    throughput: ThroughputCooldowns = NO_THROUGHPUT,
) -> PlayerTimeline:
    return build_player_timeline(
        loaded,
        actor_id=actor_id,
        class_name=class_name,
        spec=spec,
        defensives=defensives,
        throughput=throughput,
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


def test_a_later_pulls_x_is_its_scaled_and_rounded_offset_from_the_first() -> None:
    # Pull 0 always lands on TRACK_X0 regardless of the scale, because its own
    # offset from the origin is zero -- this pull is the one whose x depends on
    # the scale actually being applied, and on the origin actually being the
    # first pull's start rather than pull 1's own.
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    timeline = a_timeline(LoadedRun(run=run))
    scale = axis_scale(180.0)  # last pull's end (180_000 ms) minus the origin (0)
    assert timeline.pulls[1].x == round(TRACK_X0 + 120.0 * scale, PRECISION)


def test_a_bands_width_is_its_scaled_and_rounded_duration() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    timeline = a_timeline(LoadedRun(run=run))
    scale = axis_scale(180.0)
    assert timeline.pulls[1].width == round(60.0 * scale, PRECISION)


def test_the_height_grows_with_the_rows_it_has_to_hold() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.height == FIRST_ROW_Y + len(timeline.cooldowns) * ROW_HEIGHT + 28.0


def test_the_measured_and_inferred_badges_are_not_interchangeable() -> None:
    # A test that only checked both badges exist would still pass with the two
    # swapped: `build_player_timeline` must put `measured` on the field the
    # damage bars and press marks read, and `inferred` on the one the dimming
    # reads, exactly as `HealthCurve.line_badge`/`reading_badge` do.
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.badge_measured is not None and timeline.badge_measured.label == "measured"
    assert timeline.badge_inferred is not None and timeline.badge_inferred.label == "inferred"
