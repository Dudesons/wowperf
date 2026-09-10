# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import NO_DEFENSIVES, a_pull, a_run
from wowperf.domain.events import CastEvent, DamageTakenEvent
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
from wowperf.domain.season import CooldownAbility, DefensiveAbility, Defensives, ThroughputCooldowns

NO_THROUGHPUT = ThroughputCooldowns(entries=())


def a_cast(actor_id: int, ability_id: int, at_ms: int) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name="Shield", timestamp_ms=at_ms
    )


def a_hit(actor_id: int, at_ms: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=9, ability_name="Cleave", amount=amount, timestamp_ms=at_ms
    )


SHIELD = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0)
BURST = CooldownAbility(ability_id=49028, name="Dancing Rune Weapon", cooldown_seconds=120.0)
KIT = Defensives(entries=(("DeathKnight/Blood", (SHIELD,)),))
BURSTS = ThroughputCooldowns(entries=(("DeathKnight/Blood", (BURST,)),))


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
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    assert timeline.pulls[0].x == TRACK_X0
    assert timeline.pulls[1].is_boss
    assert "block-boss" in timeline.pulls[1].css_class


def test_a_later_pulls_x_is_its_scaled_and_rounded_offset_from_the_first() -> None:
    # Pull 0 always lands on TRACK_X0 regardless of the scale, because its own
    # offset from the origin is zero -- this pull is the one whose x depends on
    # the scale actually being applied, and on the origin actually being the
    # first pull's start rather than pull 1's own.
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    scale = axis_scale(180.0)  # last pull's end (180_000 ms) minus the origin (0)
    assert timeline.pulls[1].x == round(TRACK_X0 + 120.0 * scale, PRECISION)


def test_a_bands_width_is_its_scaled_and_rounded_duration() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    scale = axis_scale(180.0)
    assert timeline.pulls[1].width == round(60.0 * scale, PRECISION)


def test_the_height_grows_with_the_rows_it_has_to_hold() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    timeline = a_timeline(loaded, defensives=KIT)
    assert timeline.cooldowns != ()
    assert timeline.height == FIRST_ROW_Y + len(timeline.cooldowns) * ROW_HEIGHT + 28.0


def test_the_measured_and_inferred_badges_are_not_interchangeable() -> None:
    # A test that only checked both badges exist would still pass with the two
    # swapped: `build_player_timeline` must put `measured` on the field the
    # damage bars and press marks read, and `inferred` on the one the dimming
    # reads, exactly as `HealthCurve.line_badge`/`reading_badge` do.
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    assert timeline.badge_measured is not None and timeline.badge_measured.label == "measured"
    assert timeline.badge_inferred is not None and timeline.badge_inferred.label == "inferred"


def test_an_ability_the_player_never_cast_gets_no_row_at_all() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=())
    assert a_timeline(loaded, defensives=KIT).cooldowns == ()


def test_an_ability_the_player_cast_once_gets_a_row_with_one_press() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    rows = a_timeline(loaded, defensives=KIT).cooldowns
    assert len(rows) == 1
    assert rows[0].label == "Icebound Fortitude"
    assert rows[0].ability_id == SHIELD.ability_id
    assert len(rows[0].presses) == 1


def test_another_players_cast_never_gives_this_player_a_row() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(2, SHIELD.ability_id, 300_000),))
    assert a_timeline(loaded, actor_id=1, defensives=KIT).cooldowns == ()


def test_a_press_dims_the_row_for_the_abilitys_own_cooldown() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    scale = axis_scale(600.0)
    span = next(s for s in row.unavailable if s.x == round(TRACK_X0 + 300.0 * scale, 1))
    assert span.width == round(180.0 * scale, 1)


def test_the_runs_opening_is_not_judged_for_as_long_as_the_cooldown_lasts() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.not_judged is not None
    assert row.not_judged.x == TRACK_X0
    assert row.not_judged.width == round(180.0 * axis_scale(600.0), 1)


def test_throughput_rows_come_before_defensive_rows() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, BURST.ability_id, 400_000)),
    )
    rows = a_timeline(loaded, defensives=KIT, throughput=BURSTS).cooldowns
    assert [row.label for row in rows] == ["Dancing Rune Weapon", "Icebound Fortitude"]


def test_each_row_sits_one_row_height_below_the_last() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, BURST.ability_id, 400_000)),
    )
    rows = a_timeline(loaded, defensives=KIT, throughput=BURSTS).cooldowns
    assert rows[1].baseline_y - rows[0].baseline_y == ROW_HEIGHT


def test_a_player_with_pulls_but_nothing_tracked_and_no_damage_is_withheld() -> None:
    # A positive-length run alone is not enough to draw: a player who cast
    # none of the cooldowns tracked for their specialisation and took no
    # damage the log recorded has nothing to put on the axis. A guard that
    # withheld only on `span <= 0` would draw this as `PRESENT` with an axis
    # and nothing on it -- the "empty SVG" the design's testing section says
    # must not happen.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=())
    timeline = a_timeline(loaded, defensives=KIT)
    assert timeline.section.state is SectionState.WITHHELD
    assert timeline.section.reason


def test_a_player_with_damage_but_nothing_tracked_still_draws() -> None:
    # The companion to the test above: a player with something worth drawing --
    # here, damage taken -- must not be withheld merely because they own no
    # tracked cooldown they ever pressed. A guard that withheld on "no rows"
    # alone, without also checking for a damage track, would fail this one.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(), damage_taken=(a_hit(1, 1_000, 100),))
    timeline = a_timeline(loaded, defensives=KIT)
    assert timeline.section.state is SectionState.PRESENT
    assert timeline.damage is not None
    assert timeline.cooldowns == ()


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


def test_a_far_larger_hit_on_a_different_actor_never_sets_this_players_scale() -> None:
    # The other actor's hit dwarfs this player's own, in a separate bucket so
    # no per-bucket summing could blend the two. If peak were read from the
    # unfiltered events rather than from `ours`, this player's lone bar would
    # be drawn far short of DAMAGE_HEIGHT and the label would name the other
    # actor's figure instead of this player's own.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 100), a_hit(2, 90_000, 100_000)))
    track = a_timeline(loaded, actor_id=1).damage
    assert track is not None
    assert len(track.bars) == 1
    assert track.bars[0].height == DAMAGE_HEIGHT
    assert track.peak_label == "Tallest bar: 100 damage in 5 seconds"


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
