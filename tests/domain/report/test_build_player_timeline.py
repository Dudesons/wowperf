# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import NO_DEFENSIVES, a_pull, a_run
from wowperf.adapters.config.toml import load_defensives, load_throughput_cooldowns
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import CastEvent, DamageTakenEvent
from wowperf.domain.model import LoadedRun
from wowperf.domain.report.model import PlayerTimeline, SectionState
from wowperf.domain.report.player_timeline import (
    BADGE_INFERRED_CAPTION,
    BADGE_MEASURED_CAPTION,
    BUCKET_SECONDS,
    DAMAGE_HEIGHT,
    FIRST_ROW_Y,
    LABEL_UNITS_PER_CHARACTER,
    LABEL_X,
    LEGEND,
    NO_PULLS_RECORDED,
    NOTHING_TRACKED_OR_TAKEN,
    PRECISION,
    PRESS_WIDTH,
    ROW_HEIGHT,
    RUN_SPANS_NO_TIME,
    TRACK_ORIGIN_X,
    build_player_timeline,
)
from wowperf.domain.report.timeline import (
    MIN_BLOCK_WIDTH,
    TRACK_X0,
    TRACK_X1,
    axis_scale,
    axis_ticks,
)
from wowperf.domain.season import CooldownAbility, DefensiveAbility, Defensives, ThroughputCooldowns

NO_THROUGHPUT = ThroughputCooldowns(entries=())


def a_scale(seconds: float) -> float:
    """This drawing's own units per second.

    Not `axis_scale(seconds)`: the player timeline reserves a gutter for its
    row labels and starts its track after it, so the same run fits a narrower
    track here than on the run timeline.
    """
    return axis_scale(seconds, TRACK_ORIGIN_X)


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
    assert timeline.section.reason == NO_PULLS_RECORDED
    assert timeline.pulls == ()


def test_a_run_whose_pulls_span_no_time_is_withheld_with_its_own_reason() -> None:
    # A run with pulls recorded is not the same absence as a run with none: an
    # instantaneous pull leaves `run.pulls` non-empty while `run_seconds` is
    # still zero, and the reason given must not claim no pull was recorded.
    run = a_run(pulls=(a_pull(0, 0, 0),))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.section.state is SectionState.WITHHELD
    assert timeline.section.reason == RUN_SPANS_NO_TIME


def test_a_pull_band_starts_where_the_axis_starts_and_a_boss_is_marked() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    assert timeline.pulls[0].x == TRACK_ORIGIN_X
    assert timeline.pulls[1].is_boss
    assert "block-boss" in timeline.pulls[1].css_class


def test_a_later_pulls_x_is_its_scaled_and_rounded_offset_from_the_first() -> None:
    # Pull 0 always lands on TRACK_ORIGIN_X regardless of the scale, because its own
    # offset from the origin is zero -- this pull is the one whose x depends on
    # the scale actually being applied, and on the origin actually being the
    # first pull's start rather than pull 1's own.
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    scale = a_scale(180.0)  # last pull's end (180_000 ms) minus the origin (0)
    assert timeline.pulls[1].x == round(TRACK_ORIGIN_X + 120.0 * scale, PRECISION)


def test_a_bands_width_is_its_scaled_and_rounded_duration() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    scale = a_scale(180.0)
    assert timeline.pulls[1].width == round(60.0 * scale, PRECISION)


def test_a_boss_pull_takes_its_name_and_a_trash_pull_takes_its_index() -> None:
    # `Pull.name`, `Pull.is_boss` and `Pull.index` are already on the domain
    # model and the timeline used none of them. A reader looking at a press
    # should be able to say which pull it landed in. `a_pull` always names a
    # pull "Pack {index}", so the boss's label below is that generated name,
    # not a real encounter name -- what matters is that it is `pull.name`,
    # not `f"Pull {pull.index}"`.
    run = a_run(pulls=(a_pull(1, 0, 60_000), a_pull(2, 120_000, 180_000, encounter_id=2571)))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    assert [block.label for block in timeline.pulls] == ["Pull 1", "Pack 2"]


def test_a_pull_is_drawn_as_a_column_the_height_of_the_chart() -> None:
    # A press must land visibly inside the pull it happened during, so the
    # column runs from the band's own top down to where the axis ticks end,
    # not some independent fixed height.
    run = a_run(pulls=(a_pull(0, 0, 60_000, encounter_id=2571),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    assert timeline.column_height == timeline.tick_y2 - timeline.band_y
    assert timeline.band_y + timeline.column_height <= timeline.height


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


def test_the_badge_captions_are_not_interchangeable() -> None:
    # Mirrors the test above: a caption is a claim about what its own badge
    # grades, so swapping the two would misdescribe both. A test only
    # checking that each caption is non-empty would not catch the swap; this
    # pins each caption's exact words against its own badge.
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    assert timeline.badge_measured_caption == BADGE_MEASURED_CAPTION
    assert timeline.badge_inferred_caption == BADGE_INFERRED_CAPTION
    assert BADGE_MEASURED_CAPTION != BADGE_INFERRED_CAPTION


def test_the_legend_states_the_ready_tick_as_an_upper_bound_not_a_moment() -> None:
    # F4: the tick is computed from an ability's base cooldown, and the same
    # legend already admits, two sentences earlier, that this understates how
    # often an ability was really available. Naming the tick "the moment" the
    # ability came back contradicts the sentence right before it.
    assert "is the moment" not in LEGEND
    assert "earliest" in LEGEND


def test_the_inferred_badge_also_grades_the_ready_tick() -> None:
    # The tick is derived from the same base-cooldown assumption the dimming
    # already carries the inferred badge for, so the caption has to name both
    # -- a new mark on a badged drawing must not go ungraded.
    assert "tick" in BADGE_INFERRED_CAPTION
    # BADGE_MEASURED_CAPTION is untouched: the tick is not measured.
    assert "tick" not in BADGE_MEASURED_CAPTION


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
    scale = a_scale(600.0)
    span = next(s for s in row.unavailable if s.x == round(TRACK_ORIGIN_X + 300.0 * scale, 1))
    assert span.width == round(180.0 * scale, 1)


def test_the_runs_opening_is_not_judged_for_as_long_as_the_cooldown_lasts() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.not_judged is not None
    assert row.not_judged.x == TRACK_ORIGIN_X
    assert row.not_judged.width == round(180.0 * a_scale(600.0), 1)


def test_a_press_near_the_runs_end_is_clamped_to_the_axis_end_not_the_runs_length() -> None:
    # A press 50 seconds from the end of a 600-second run still carries a full
    # 180-second cooldown, but only 50 of those seconds are left to draw: the
    # span must stop at the axis end, never past it.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 550_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    scale = a_scale(600.0)
    span = row.unavailable[0]
    assert span.x == round(TRACK_ORIGIN_X + 550.0 * scale, PRECISION)
    assert span.width == round(50.0 * scale, PRECISION)
    assert round(span.x + span.width, PRECISION) == TRACK_X1


def test_a_cooldown_longer_than_the_run_leaves_the_whole_track_not_judged() -> None:
    # The design endorses overstating what the log cannot judge: a cooldown
    # that outlasts the run leaves `not_judged` covering the full track, and
    # the press's own span -- clamped to the time remaining, not to the
    # cooldown -- sits entirely inside that stretch.
    long_cooldown = DefensiveAbility(
        ability_id=SHIELD.ability_id, name=SHIELD.name, cooldown_seconds=900.0
    )
    kit = Defensives(entries=(("DeathKnight/Blood", (long_cooldown,)),))
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 100_000),))
    row = a_timeline(loaded, defensives=kit).cooldowns[0]
    scale = a_scale(600.0)
    assert row.not_judged is not None
    assert row.not_judged.x == TRACK_ORIGIN_X
    assert row.not_judged.width == round(TRACK_X1 - TRACK_ORIGIN_X, PRECISION)
    span = row.unavailable[0]
    assert span.x == round(TRACK_ORIGIN_X + 100.0 * scale, PRECISION)
    assert span.x > row.not_judged.x
    assert round(span.x + span.width, PRECISION) == TRACK_X1


def test_a_second_press_inside_the_first_covers_still_draws_its_own_mark() -> None:
    # Design §10: a press at t produces an unavailable span covering
    # t + cooldown, and a second press inside that span still draws its mark.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, SHIELD.ability_id, 350_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    scale = a_scale(600.0)
    assert [press.x for press in row.presses] == [
        round(TRACK_ORIGIN_X + 300.0 * scale - PRESS_WIDTH / 2, PRECISION),
        round(TRACK_ORIGIN_X + 350.0 * scale - PRESS_WIDTH / 2, PRECISION),
    ]
    assert [span.x for span in row.unavailable] == [
        round(TRACK_ORIGIN_X + 300.0 * scale, PRECISION),
        round(TRACK_ORIGIN_X + 350.0 * scale, PRECISION),
    ]
    assert row.unavailable[0].width == round(180.0 * scale, PRECISION)
    assert row.unavailable[1].width == round(180.0 * scale, PRECISION)
    # The first press's span is still open when the second press lands.
    assert row.unavailable[0].x + row.unavailable[0].width > row.unavailable[1].x


def test_a_presss_mark_and_icon_are_both_centred_on_the_instant_they_mark() -> None:
    # Both elements are placed by their own left edge, and both are wider than
    # the moment they stand for: the mark by `PRESS_WIDTH`, the icon by a whole
    # row height. Either one placed flush with the instant would sit entirely
    # to the right of it -- several seconds late on a half-hour run -- and the
    # two would then disagree about where the press happened.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    press = a_timeline(loaded, defensives=KIT).cooldowns[0].presses[0]
    instant = TRACK_ORIGIN_X + 300.0 * a_scale(600.0)
    assert press.x == round(instant - PRESS_WIDTH / 2, PRECISION)
    assert press.icon_x == round(instant - ROW_HEIGHT / 2, PRECISION)
    # Same centre, to within the rounding both coordinates carry.
    assert abs((press.x + PRESS_WIDTH / 2) - (press.icon_x + ROW_HEIGHT / 2)) <= 0.1


def test_every_tick_coordinate_is_rounded_like_every_other_coordinate() -> None:
    # design section 7: this drawing rounds every coordinate it emits, because
    # it emits hundreds of them. The ticks come from a helper the run timeline
    # shares and which does not round -- three attributes per tick, on every
    # player's drawing, at full binary precision.
    span_ms = 1_908_976
    span = span_ms / 1000
    run = a_run(pulls=(a_pull(0, 0, span_ms),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1),))
    timeline = a_timeline(loaded)
    raw = axis_ticks(span, a_scale(span), TRACK_ORIGIN_X)
    # The run has to produce a coordinate that rounding actually changes, or
    # the comparison below would hold with the rounding taken back out.
    assert any(x != round(x, PRECISION) for x, _ in raw)
    assert timeline.ticks == tuple((round(x, PRECISION), label) for x, label in raw)


def test_a_row_label_ends_in_the_gutter_and_sits_on_its_own_rows_middle() -> None:
    # Two claims, and the drawing is wrong without either. Horizontally the
    # label has to end before the track begins, or it is drawn across the row
    # it names -- over the not-judged stretch every row opens with, which
    # obscured reads as an ability that was ready. Vertically its baseline has
    # to be the row's middle, not the row's top edge, which is where every
    # rect on the row hangs from: a baseline on the top edge puts the glyphs
    # over the row above.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    timeline = a_timeline(loaded, defensives=KIT)
    row = timeline.cooldowns[0]
    assert timeline.label_x == LABEL_X
    assert timeline.label_x < TRACK_ORIGIN_X
    assert row.label_y == row.baseline_y + ROW_HEIGHT / 2


def test_the_damage_tracks_label_ends_in_the_same_gutter_the_rows_use() -> None:
    # One gutter, or the drawing has two left edges. The damage label is
    # centred on the band its bars grow through rather than on the foot they
    # stand on, so it reads level with what it names.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 2000),))
    timeline = a_timeline(loaded)
    assert timeline.damage is not None
    assert timeline.label_x == LABEL_X
    assert timeline.damage.label_y == timeline.damage.baseline_y - DAMAGE_HEIGHT / 2


def test_the_gutter_still_fits_the_longest_ability_name_in_the_data_files() -> None:
    # The gutter was sized against the widest name the shipped data files
    # carry. Adding a wider one is a legitimate thing to do to those files and
    # nothing else in the suite would notice it; this fails when it happens,
    # and equally if the gutter is ever narrowed under the names it holds.
    names = [
        ability.name
        for entries in (load_defensives().entries, load_throughput_cooldowns().entries)
        for _, abilities in entries
        for ability in abilities
    ]
    longest = max(names, key=len)
    assert len(longest) * LABEL_UNITS_PER_CHARACTER <= LABEL_X, longest


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
    assert timeline.section.reason == NOTHING_TRACKED_OR_TAKEN


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
    assert track.peak_label == "Tallest bar: 2,000 unmitigated damage in 5 seconds."


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
    assert track.peak_label == "Tallest bar: 100 unmitigated damage in 5 seconds."


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
    scale = a_scale(100.0)
    assert track.bars[1].x == round(TRACK_ORIGIN_X + 2 * BUCKET_SECONDS * scale, PRECISION)


def test_a_player_whose_every_hit_was_fully_avoided_gets_no_damage_track() -> None:
    # A miss, dodge, or parry carries no unmitigatedAmount and an amount of 0,
    # so ingest.py builds DamageTakenEvent(amount=0, ...) for it -- a real
    # construction, not a hypothetical. `ours` is non-empty here, so this
    # takes the path past the "no events" guard, into buckets that sum to
    # zero everywhere.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 0), a_hit(1, 50_000, 0)))
    assert a_timeline(loaded).damage is None


def test_a_cooldown_that_finishes_inside_the_run_is_marked_ready_again() -> None:
    # The stretch after a press is the cooldown; its end is the instant the
    # ability came back, and an unmarked end reads as an absence rather than
    # as an event. The press lands at 10s and SHIELD's cooldown is 180s, so
    # the ability comes back at 190s into the run. The tick is centred on
    # that instant the same way a press is centred on its own -- left-edged
    # half a mark's width before it, per `Press`'s own docstring -- so this
    # pins the anchored x, not the raw unoffset one.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 10_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    scale = a_scale(600.0)
    assert row.ready_ticks == (
        round(TRACK_ORIGIN_X + 190.0 * scale - PRESS_WIDTH / 2, PRECISION),
    )


def test_a_ready_tick_is_anchored_the_same_way_its_press_is() -> None:
    # F8: a `Press` centres its mark on the instant, left-edged half the
    # mark's own width before it (`Press`'s own docstring). The ready tick is
    # a mark of the same width answering that same press, so it has to use
    # the same anchoring rule -- not the raw, unoffset x -- or the two read at
    # different times on the same row despite marking the same cooldown.
    # Tolerance mirrors `test_a_presss_mark_and_icon_are_both_centred_on_the_instant_they_mark`:
    # both x's are independently rounded to PRECISION, so an exact comparison
    # of the two offsets would fail on rounding noise smaller than a pixel.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 10_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    press_offset = row.presses[0].x - (TRACK_ORIGIN_X + 10.0 * a_scale(600.0))
    tick_offset = row.ready_ticks[0] - (TRACK_ORIGIN_X + 190.0 * a_scale(600.0))
    assert abs(tick_offset - press_offset) <= 0.1
    assert abs(press_offset - (-PRESS_WIDTH / 2)) <= 0.1


def test_a_cooldown_still_running_when_the_run_ends_is_not_marked_ready() -> None:
    # Marking a tick at the axis end would claim the ability came back at the
    # moment the run finished, which the log never says.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 590_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.ready_ticks == ()


def test_the_damage_row_states_its_own_scale_and_bucket_width() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 2000),))
    timeline = a_timeline(loaded)
    assert timeline.damage is not None
    assert timeline.damage.axis_top_label != ""
    assert f"{int(BUCKET_SECONDS)}-second" in timeline.damage.bucket_caption


def test_the_damage_axis_starts_at_the_same_origin_the_bars_do() -> None:
    # Every other element on this chart -- the bars, the pull bands, the
    # cooldown spans -- starts at the track's own origin and leaves the
    # label gutter to the row names. The axis line must not be the one
    # exception, or it reads as a mistake to anyone reading the drawing.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 2000),))
    timeline = a_timeline(loaded)
    assert timeline.damage is not None
    assert timeline.damage.axis_x0 == TRACK_ORIGIN_X


def test_the_damage_axis_ends_where_the_track_does_not_past_it() -> None:
    # F9: the same defect the axis's `x1` already had fixed for it, at the
    # other end of the same line. Every bar, span and mark on this chart ends
    # at TRACK_X1; an axis line reaching `timeline.width` instead overruns
    # the last instant the track can hold and runs into the right margin.
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 2000),))
    timeline = a_timeline(loaded)
    assert timeline.damage is not None
    assert timeline.damage.axis_x1 == TRACK_X1
    assert timeline.damage.axis_x1 != timeline.width


def a_player_auras(actor_id: int, aura: Aura) -> PlayerAuras:
    return PlayerAuras(actor_id=actor_id, on_self=(aura,))


def test_a_cooldown_row_carries_the_windows_its_buff_actually_covered() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        auras=(
            a_player_auras(
                1,
                Aura(
                    ability_id=SHIELD.ability_id,
                    name=SHIELD.name,
                    total_uptime_ms=8_000,
                    uses=1,
                    bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
                ),
            ),
        ),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.cover != ()


def test_a_cover_window_is_never_widened_to_make_it_visible() -> None:
    # The guard the spec asks for. MIN_BLOCK_WIDTH floors a pull so it does not
    # vanish; a cover window has no such floor, because its width IS the claim.
    # A five-second buff on a thirty-three-minute (1980-second) axis draws at
    # about 1.3 units, and that sliver is what must be drawn -- not widened to
    # clear MIN_BLOCK_WIDTH (2.0).
    run = a_run(pulls=(a_pull(0, 0, 1_980_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        auras=(
            a_player_auras(
                1,
                Aura(
                    ability_id=SHIELD.ability_id,
                    name=SHIELD.name,
                    total_uptime_ms=5_000,
                    uses=1,
                    bands=(AuraBand(start_ms=300_000, end_ms=305_000),),
                ),
            ),
        ),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    span = row.cover[0]
    assert span.width < MIN_BLOCK_WIDTH


def test_a_player_with_no_aura_table_gets_no_cover_windows() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.cover == ()


def test_a_cast_id_that_differs_from_its_auras_id_still_gets_a_cover_window() -> None:
    # The regression `resolve_aura` fixes, proven through a throughput cooldown
    # rather than a defensive: `_cooldown_rows` builds both kinds of row
    # through the same `_cover_spans` call, so the id/name bridge covers
    # throughput cooldowns by construction, not by a second implementation.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, BURST.ability_id, 300_000),),
        auras=(
            a_player_auras(
                1,
                Aura(
                    ability_id=999_111,  # deliberately not BURST.ability_id
                    name=BURST.name,
                    total_uptime_ms=8_000,
                    uses=1,
                    bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
                ),
            ),
        ),
    )
    row = a_timeline(loaded, throughput=BURSTS).cooldowns[0]
    assert row.cover != ()


def test_an_aura_table_with_no_band_for_this_ability_gives_no_cover_windows() -> None:
    # A player's own aura table can be present while saying nothing about this
    # particular ability -- distinct from no table at all, and the branch
    # `test_a_player_with_no_aura_table_gets_no_cover_windows` does not exercise.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        auras=(
            a_player_auras(
                1,
                Aura(ability_id=999_999, name="Unrelated Buff", total_uptime_ms=0, uses=0),
            ),
        ),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.cover == ()


def a_covered_run(bands: tuple[AuraBand, ...], casts: tuple[CastEvent, ...]) -> LoadedRun:
    """A ten-minute run whose player owns the shield and has an aura table for it."""
    return LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=casts,
        auras=(
            a_player_auras(
                1,
                Aura(
                    ability_id=SHIELD.ability_id,
                    name=SHIELD.name,
                    total_uptime_ms=sum(band.end_ms - band.start_ms for band in bands),
                    uses=len(bands),
                    bands=bands,
                ),
            ),
        ),
    )


def test_a_cooldown_rows_hover_states_its_presses_and_its_cover() -> None:
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.hover == "Icebound Fortitude — 1 press, 8.0 s of cover"


def test_a_cooldown_rows_hover_counts_every_press() -> None:
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=tuple(a_cast(1, SHIELD.ability_id, at) for at in (100_000, 300_000, 500_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.hover == "Icebound Fortitude — 3 presses, 8.0 s of cover"


def test_a_cooldown_rows_hover_sums_every_window_the_buff_was_up() -> None:
    loaded = a_covered_run(
        bands=(
            AuraBand(start_ms=100_000, end_ms=108_000),
            AuraBand(start_ms=300_000, end_ms=302_500),
        ),
        casts=tuple(a_cast(1, SHIELD.ability_id, at) for at in (100_000, 300_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.hover == "Icebound Fortitude — 2 presses, 10.5 s of cover"


def test_a_cooldown_rows_hover_counts_only_the_cover_the_drawing_shows() -> None:
    """The figure is the drawn windows, never the aura table's own total.

    A buff still up when the axis ends is clipped where the drawing clips it,
    so the number a reader hovers and the rectangles they are looking at
    cannot disagree. `total_uptime_ms` here is 15s and the axis sees 5.
    """
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=595_000, end_ms=610_000),),
        casts=(a_cast(1, SHIELD.ability_id, 595_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.hover == "Icebound Fortitude — 1 press, 5.0 s of cover"


def test_a_cooldown_row_with_no_aura_for_its_ability_says_so_rather_than_no_cover() -> None:
    """An absence of aura data is not a buff that was never up.

    The row draws no cover in either case, so the hover is the only place the
    two can be told apart, and reporting the missing table as zero seconds
    would state as measured a fact nobody measured.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.hover == (
        "Icebound Fortitude — 1 press. No aura data for it, so its cover is not drawn."
    )
    assert "0.0 s of cover" not in row.hover


def test_a_cooldown_row_whose_aura_was_never_up_reports_no_seconds_of_cover() -> None:
    loaded = a_covered_run(bands=(), casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.hover == "Icebound Fortitude — 1 press, 0.0 s of cover"


def test_a_pull_bands_hover_names_the_pull_and_how_long_it_ran() -> None:
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 47_000), a_pull(1, 60_000, 600_000))),
        damage_taken=(a_hit(1, 1_000, 1),),
    )
    bands = a_timeline(loaded).pulls
    assert bands[0].hover == "Pull 0 — ran 0:47"
    assert bands[0].label == "Pull 0"
