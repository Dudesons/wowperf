# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import NO_DEFENSIVES, a_pull, a_run
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.model import LoadedRun
from wowperf.domain.report.model import PlayerTimeline, SectionState
from wowperf.domain.report.player_timeline import (
    BUCKET_SECONDS,
    DAMAGE_HEIGHT,
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


def a_hit(actor_id: int, at_ms: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=9, ability_name="Cleave", amount=amount, timestamp_ms=at_ms
    )


def test_the_tallest_bar_fills_the_damage_track_and_a_half_sized_hit_is_half_of_it() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(
        run=run, damage_taken=(a_hit(1, 1_000, 2000), a_hit(1, 50_000, 1000))
    )
    track = a_timeline(loaded).damage
    assert track is not None
    tallest = max(bar.height for bar in track.bars)
    shortest = min(bar.height for bar in track.bars)
    assert tallest == DAMAGE_HEIGHT
    assert shortest == DAMAGE_HEIGHT / 2
    # This player's own tallest bucket only -- never a group figure, which
    # would still pass this assertion's shape but say something dishonest.
    assert track.peak_label == "Tallest bar: 2,000 damage in 5 seconds"


def test_another_players_damage_never_reaches_this_players_track() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(2, 1_000, 9999),))
    assert a_timeline(loaded, actor_id=1).damage is None


def test_two_hits_inside_one_bucket_are_one_bar_of_their_sum() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    both = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 400), a_hit(1, 2_000, 600)))
    one = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1000),))
    assert len(a_timeline(both).damage.bars) == 1  # type: ignore[union-attr]
    assert a_timeline(both).damage == a_timeline(one).damage


def test_a_bucket_with_no_damage_draws_no_bar() -> None:
    # Two hits five seconds apart straddle a bucket boundary, leaving the
    # bucket between them empty. A bar count of two, at bucket 0 and bucket 2
    # rather than bucket 0 and bucket 1, is only possible if the empty bucket
    # was skipped rather than drawn at zero height or folded out of the index.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 100), a_hit(1, 11_000, 100)))
    track = a_timeline(loaded).damage
    assert track is not None
    assert len(track.bars) == 2
    scale = axis_scale(100.0)
    assert track.bars[1].x == round(TRACK_X0 + 2 * BUCKET_SECONDS * scale, PRECISION)


def test_a_player_whose_every_hit_was_fully_avoided_gets_no_damage_track() -> None:
    # A miss, dodge, or parry carries no unmitigatedAmount and an amount of 0,
    # so ingest.py builds DamageTakenEvent(amount=0, ...) for it -- a real
    # construction, not a hypothetical. `ours` is non-empty here, so this
    # takes the path past the "no events" guard, into buckets that sum to
    # zero everywhere.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 0), a_hit(1, 50_000, 0)))
    assert a_timeline(loaded).damage is None
