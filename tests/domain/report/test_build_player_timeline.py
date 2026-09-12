# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import NO_DEFENSIVES, a_pull, a_run
from wowperf.adapters.config.toml import load_defensives, load_throughput_cooldowns
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import CastEvent, DamageTakenEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import DamageDoneSeries, LoadedRun
from wowperf.domain.report.frame import badge_for
from wowperf.domain.report.model import (
    CooldownRow,
    PlayerTimeline,
    SectionState,
    Span,
    TooltipLine,
)
from wowperf.domain.report.player_timeline import (
    BADGE_DERIVED_CAPTION,
    BADGE_INFERRED_CAPTION,
    BADGE_MEASURED_CAPTION,
    BUCKET_SECONDS,
    DAMAGE_DONE_BASELINE_Y,
    DAMAGE_HEIGHT,
    FIRST_ROW_Y,
    LABEL_UNITS_PER_CHARACTER,
    LABEL_X,
    LEGEND,
    NO_AURA_DATA,
    NO_DAMAGE_DONE,
    NO_DAMAGE_TAKEN,
    NO_PULLS_RECORDED,
    NOTHING_TRACKED_OR_TAKEN,
    PRECISION,
    PRESS_WIDTH,
    ROW_HEIGHT,
    RUN_SPANS_NO_TIME,
    TRACK_ORIGIN_X,
    TRACK_WIDTH,
    _row_shares,
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
    timeline = a_complete_chart()
    assert timeline.badge_measured is not None and timeline.badge_measured.label == "measured"
    assert timeline.badge_inferred is not None and timeline.badge_inferred.label == "inferred"


def test_the_badge_captions_are_not_interchangeable() -> None:
    # Mirrors the test above: a caption is a claim about what its own badge
    # grades, so swapping the two would misdescribe both. A test only
    # checking that each caption is non-empty would not catch the swap; this
    # pins each caption's exact words against its own badge. The chart has to
    # draw every layer, or each caption is a shorter sentence than the
    # constant and the comparison says nothing about a swap.
    timeline = a_complete_chart()
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


def test_a_presss_mark_is_centred_on_the_instant_it_marks() -> None:
    # The mark is placed by its left edge and is wider than the moment it
    # stands for, so one placed flush with the instant would sit entirely to
    # its right -- several seconds late on a half-hour run.
    #
    # Until 2026-09-12 this also pinned a `Press.icon_x` centred on the same
    # instant. The icon left the track that day: at ROW_HEIGHT it covered
    # about seventeen seconds of a twenty-three minute run, so it overlapped
    # its neighbours and the press mark was painted over it. What replaces
    # that half is the gutter test below.
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    press = a_timeline(loaded, defensives=KIT).cooldowns[0].presses[0]
    instant = TRACK_ORIGIN_X + 300.0 * a_scale(600.0)
    assert press.x == round(instant - PRESS_WIDTH / 2, PRECISION)


def a_timeline_with_presses(count: int) -> PlayerTimeline:
    """One row pressed `count` times across a ten-minute run, the first at its origin."""
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    casts = tuple(
        a_cast(1, SHIELD.ability_id, index * (600_000 // count)) for index in range(count)
    )
    return a_timeline(LoadedRun(run=run, casts=casts), defensives=KIT)


def test_the_icon_sits_between_the_label_and_the_track() -> None:
    # One coordinate a row rather than one a press, and it lives in the
    # gutter: clear of the name to its left and of the track to its right.
    timeline = a_timeline_with_presses(count=1)
    assert timeline.row_icon_size == ROW_HEIGHT
    assert LABEL_X <= timeline.row_icon_x
    assert timeline.row_icon_x + timeline.row_icon_size <= TRACK_ORIGIN_X


def a_timeline_with_damage(amount: int, at_seconds: float, pull: str) -> PlayerTimeline:
    """A run of one boss pull, with one hit landing inside it."""
    boss = a_pull(0, 0, 1_200_000, encounter_id=1).model_copy(update={"name": pull})
    loaded = LoadedRun(
        run=a_run(pulls=(boss,)),
        damage_taken=(a_hit(1, int(at_seconds * 1000), amount),),
    )
    return a_timeline(loaded)


def test_a_damage_bucket_says_what_it_holds_and_where() -> None:
    # A spike is only a question until a reader knows which pull it fell in.
    timeline = a_timeline_with_damage(amount=11_418_755, at_seconds=875.0, pull="Atroxus")
    assert timeline.damage is not None
    assert timeline.damage.bars[0].hover == (
        "11,418,755 unmitigated in 5 s, at 14:35, during Atroxus"
    )


def test_a_damage_bucket_outside_every_pull_says_so_rather_than_naming_one() -> None:
    # The log records damage between pulls too, and the honest answer there is
    # that no pull holds it -- never the nearest one.
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 300_000, 400_000))),
        damage_taken=(a_hit(1, 120_000, 5_000),),
    )
    timeline = a_timeline(loaded)
    assert timeline.damage is not None
    assert timeline.damage.bars[0].hover.endswith(", between pulls")


def test_a_bucket_straddling_two_pulls_names_both_rather_than_picking_one() -> None:
    # A five-second bucket can hold the end of one pull and the start of the
    # next. Naming one of them would be a choice the log did not make.
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 61_000), a_pull(1, 62_000, 120_000))),
        damage_taken=(a_hit(1, 60_500, 100), a_hit(1, 62_500, 100)),
    )
    timeline = a_timeline(loaded)
    assert timeline.damage is not None
    assert timeline.damage.bars[0].hover.endswith(", during Pull 0 and Pull 1")


def test_the_key_names_every_state_the_track_draws() -> None:
    # Green was never named anywhere near the chart: LEGEND covers the mark,
    # the cooldown stretch, the pale opening and the ready tick, and stops.
    # The class is carried rather than the colour so the key and the track
    # cannot disagree -- a swatch takes the same rule as the rectangle it
    # stands for.
    timeline = a_timeline_with_presses(count=3)
    assert [key.css_class for key in timeline.state_key] == [
        "press", "cover", "on-cooldown", "not-judged",
    ]
    assert [key.label for key in timeline.state_key] == [
        "a press", "the buff up", "on cooldown", "not judged",
    ]


def test_the_legend_still_leaves_the_cover_to_the_key() -> None:
    # The one state LEGEND has never named is the one the key exists for. If
    # LEGEND ever grows a sentence about it, this fails and the key is
    # redundant rather than silently duplicated.
    assert "cover" not in LEGEND and "buff" not in LEGEND


def test_a_rows_icon_clears_even_a_press_at_the_very_origin() -> None:
    # The worst case the gutter has to survive: 31 presses is what one real
    # player's Prismatic Barrier row carried, and the first of them lands on
    # the axis origin, where a press mark reaches half its own width left of
    # TRACK_ORIGIN_X. The icon must still end before it.
    timeline = a_timeline_with_presses(count=31)
    assert timeline.row_icon_x + timeline.row_icon_size <= timeline.cooldowns[0].presses[0].x


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


def a_panel_line(row: CooldownRow, label: str) -> TooltipLine:
    """The one line of a row's panel with this label, or a clear failure."""
    assert row.tooltip is not None
    matches = [line for line in row.tooltip.lines if line.label == label]
    assert len(matches) == 1, f"{label} appears {len(matches)} times"
    return matches[0]


# Restates test_a_cooldown_rows_hover_states_its_presses_and_its_cover, which held
# the same two figures as one line of plain text on a native SVG title.
def test_a_cooldown_rows_panel_states_its_presses_and_its_cover() -> None:
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Presses").value == "1"
    assert a_panel_line(row, "Buff up").value == "8.0 s (1%)"


# Restates test_a_cooldown_rows_hover_counts_every_press.
def test_a_cooldown_rows_panel_counts_every_press() -> None:
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=tuple(a_cast(1, SHIELD.ability_id, at) for at in (100_000, 300_000, 500_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Presses").value == "3"


# Restates test_a_cooldown_rows_hover_sums_every_window_the_buff_was_up.
def test_a_cooldown_rows_panel_sums_every_window_the_buff_was_up() -> None:
    loaded = a_covered_run(
        bands=(
            AuraBand(start_ms=100_000, end_ms=108_000),
            AuraBand(start_ms=300_000, end_ms=302_500),
        ),
        casts=tuple(a_cast(1, SHIELD.ability_id, at) for at in (100_000, 300_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "10.5 s (2%)"


# Restates test_a_cooldown_rows_hover_counts_only_the_cover_the_drawing_shows.
def test_a_cooldown_rows_panel_counts_only_the_cover_the_drawing_shows() -> None:
    """The figure is the drawn windows, never the aura table's own total.

    A buff still up when the axis ends is clipped where the drawing clips it,
    so the number a reader hovers and the rectangles they are looking at
    cannot disagree. `total_uptime_ms` here is 15s and the axis sees 5, which
    the share separates too: the table's own total would read 2% of the run.
    """
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=595_000, end_ms=610_000),),
        casts=(a_cast(1, SHIELD.ability_id, 595_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "5.0 s (1%)"


# Restates test_a_cooldown_row_with_no_aura_for_its_ability_says_so_rather_than_no_cover,
# which held the same distinction as the tail of a native title's one line.
def test_a_cooldown_row_with_no_aura_for_its_ability_says_so_rather_than_no_cover() -> None:
    """An absence of aura data is not a buff that was never up.

    The row draws no cover in either case, so the panel is the only place the
    two can be told apart, and reporting the missing table as zero seconds
    would state as measured a fact nobody measured.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.tooltip is not None
    assert row.tooltip.note == NO_AURA_DATA
    assert [line.label for line in row.tooltip.lines if line.label == "Buff up"] == []


# Restates test_a_cooldown_row_whose_aura_was_never_up_reports_no_seconds_of_cover.
def test_a_cooldown_row_whose_aura_was_never_up_reports_no_seconds_of_cover() -> None:
    loaded = a_covered_run(bands=(), casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "0.0 s (0%)"
    assert row.tooltip is not None
    assert row.tooltip.note == ""


def test_a_cooldown_rows_panel_states_the_buffs_share_of_the_drawn_run() -> None:
    """Seconds alone cannot be read against the share Warcraft Logs prints for
    the same aura, so the line carries both. The denominator is the run the row
    is drawn on -- 150s of this 600s axis is a quarter of it -- which is the
    same span the three partition lines above it divide by."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=450_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "150.0 s (25%)"


def test_a_cooldown_rows_panel_grades_each_line_by_what_it_rests_on() -> None:
    """`TooltipLine.tier` means measured when it is None, so an ungraded share
    would badge an assumed cooldown as something read from the log. The three
    shares rest on a base cooldown from `data/` that talents shorten and the log
    never records, which is the claim the chart's own inferred badge grades.

    The cover line is graded too, and derived rather than inferred: both its
    figures come from the aura table, but both are clipped to the drawn axis,
    and that window is a choice. It is the choice that puts our seconds a
    fraction below the uptime Warcraft Logs reports over the whole fight.
    `comparison/uptime.py` grades the same quantity the same way."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    inferred = badge_for(Confidence.INFERRED)
    assert a_panel_line(row, "Presses").tier is None
    assert a_panel_line(row, "Buff up").tier == badge_for(Confidence.DERIVED)
    for label in ("Not judged", "On cooldown", "Ready and unpressed"):
        assert a_panel_line(row, label).tier == inferred


def test_a_cooldown_rows_panel_reports_the_share_the_partition_computed() -> None:
    """One press at 300s of a 600s run, on a 180s cooldown: 30% unjudged,
    30% on cooldown, and 40% of the run ready and never pressed."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Not judged").value == "30%"
    assert a_panel_line(row, "On cooldown").value == "30%"
    assert a_panel_line(row, "Ready and unpressed").value == "40%"


def test_a_pull_bands_hover_names_the_pull_and_how_long_it_ran() -> None:
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 47_000), a_pull(1, 60_000, 600_000))),
        damage_taken=(a_hit(1, 1_000, 1),),
    )
    bands = a_timeline(loaded).pulls
    assert bands[0].hover == "Pull 0 — ran 0:47"
    assert bands[0].label == "Pull 0"


def test_the_three_shares_of_a_row_always_sum_to_a_hundred() -> None:
    """Rounded independently these are 26 + 41 + 34 = 101, which reads as a broken
    panel. Largest remainder gives the leftover points to the largest fractions,
    so the column a reader adds up comes to 100 whatever the spans were."""
    shares = _row_shares(
        Span(x=150.0, width=0.257 * TRACK_WIDTH),
        (Span(x=300.0, width=0.406 * TRACK_WIDTH),),
    )
    assert shares == (26, 40, 34)
    assert sum(shares) == 100


def test_overlapping_cooldowns_are_unioned_and_never_summed() -> None:
    """Two presses inside one cooldown cover 194 units of track, not 303.6. A run
    of presses closer together than the cooldown is the normal case, not the edge
    one, so summing the widths would overstate every busy row."""
    not_judged = Span(x=150.0, width=151.8)
    unavailable = (Span(x=403.0, width=151.8), Span(x=445.2, width=151.8))
    assert _row_shares(not_judged, unavailable) == (30, 38, 32)


def test_a_cooldown_running_under_the_unjudged_opening_is_not_counted_twice() -> None:
    """The opening is not judged whatever else is true of it, so a cooldown lying
    under it belongs to neither total twice. Here the press at the origin is
    covered entirely by the opening, so on-cooldown counts only the two later ones."""
    not_judged = Span(x=150.0, width=151.8)
    unavailable = tuple(Span(x=x, width=151.8) for x in (150.0, 318.7, 487.3))
    assert _row_shares(not_judged, unavailable) == (30, 60, 10)


def test_a_row_with_no_presses_is_ready_for_everything_it_was_judged_on() -> None:
    assert _row_shares(Span(x=150.0, width=151.8), ()) == (30, 0, 70)


def test_a_rows_strip_is_a_percentage_of_the_chart_and_never_a_viewbox_unit() -> None:
    """The strip is HTML laid over an SVG, so it is positioned in the rendered
    box and not in the drawing's own units. The viewBox fixes the aspect ratio,
    which is what makes the percentage exact at every window size -- and is why
    no script has to measure the page to find a row."""
    timeline = a_timeline_with_presses(count=1)
    row = timeline.cooldowns[0]
    assert row.hit_top == round(row.baseline_y / timeline.height * 100, PRECISION)
    assert timeline.row_hit_height == round(ROW_HEIGHT / timeline.height * 100, PRECISION)
    # A percentage, so it can never be the viewBox number it was derived from.
    assert row.hit_top != row.baseline_y


def test_every_rows_strip_sits_below_the_one_above_it_and_inside_the_chart() -> None:
    timeline = a_timeline(
        LoadedRun(
            run=a_run(pulls=(a_pull(0, 0, 600_000),)),
            casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, BURST.ability_id, 200_000)),
        ),
        defensives=KIT,
        throughput=BURSTS,
    )
    tops = [row.hit_top for row in timeline.cooldowns]
    assert len(tops) == 2
    assert tops == sorted(tops)
    # The epsilon is binary representation, not slack: two strips may abut
    # exactly, and 69.4 + 8.2 is 77.60000000000001 in a float.
    assert tops[0] + timeline.row_hit_height - tops[1] <= 1e-9
    assert tops[-1] + timeline.row_hit_height <= 100.0


def a_done_series(
    actor_id: int,
    amounts: tuple[int, ...],
    interval_ms: float = 6000.0,
    point_start_ms: int = 0,
) -> DamageDoneSeries:
    return DamageDoneSeries(
        actor_id=actor_id,
        point_start_ms=point_start_ms,
        interval_ms=interval_ms,
        amounts=amounts,
    )


def test_a_players_damage_done_track_is_scaled_to_their_own_tallest_bucket() -> None:
    """Never to the group's. Two players an order of magnitude apart both draw
    a full-height bar at their own peak, which is the postmortem design's
    section 5.5 expressed as a drawing: a shared scale would rank them."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (100, 50)), a_done_series(2, (10_000, 5_000))),
    )
    small = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    large = a_timeline(loaded, actor_id=2, defensives=KIT).damage_done
    assert small is not None and large is not None
    assert small.bars[0].height == large.bars[0].height
    assert small.bars[1].height == small.bars[0].height / 2


def test_a_damage_done_bar_sits_where_its_bucket_falls_on_the_axis() -> None:
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (100, 100, 100)),),
    )
    track = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    assert track is not None
    # One bucket's width in drawn units, which is what consecutive bars must
    # sit apart. Every x is rounded to a tenth before it reaches the view
    # model, so two gaps over the same step can differ by that tenth -- which
    # is why this pins the step itself rather than asserting the gaps are
    # equal to each other.
    step = 6.0 * a_scale(600.0)
    gaps = [track.bars[i + 1].x - track.bars[i].x for i in range(len(track.bars) - 1)]
    assert len(gaps) == 2
    assert all(abs(gap - step) <= 0.1 for gap in gaps), (gaps, step)
    assert step > 0


def test_a_player_with_no_series_draws_no_damage_done_track() -> None:
    """Absence, not a flat line: a track of zero-height bars reads as a run of
    empty buckets rather than as a figure nobody measured."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(2, (100,)),),
    )
    assert a_timeline(loaded, actor_id=1, defensives=KIT).damage_done is None


def test_a_damage_done_hover_states_an_amount_and_never_a_rate() -> None:
    """The response gives damage per second natively and printing it would
    cost one line. It is the figure section 5.5 refuses to produce."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (600,)),),
    )
    track = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    assert track is not None
    hover = track.bars[0].hover
    assert "600 damage done" in hover
    assert "6 s" in hover
    for forbidden in ("per second", "a second", "DPS", "dps"):
        assert forbidden not in hover


def test_the_damage_done_caption_keeps_a_fractional_bucket_width() -> None:
    """The API's interval is not a whole number of seconds. Rounding it to one
    would claim 6-second buckets for 6.4-second bars."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (600,), interval_ms=6411.7),),
    )
    track = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    assert track is not None
    assert "6.4-second bucket" in track.bucket_caption


def test_the_damage_taken_caption_still_reads_as_a_whole_number() -> None:
    """The shared formatter must not turn the existing track's 5 into 5.0."""
    timeline = a_timeline_with_damage(amount=1000, at_seconds=10.0, pull="Atroxus")
    assert timeline.damage is not None
    assert "5-second bucket" in timeline.damage.bucket_caption


def test_the_chart_leaves_room_for_the_damage_done_track() -> None:
    """The done bars grow upward from their own baseline, and rows are drawn
    downward from theirs, so a first row left where it was would be struck
    through by the new track.

    The constants are asserted against each other rather than a row against
    the formula that placed it: the latter agrees with itself wherever the
    rows sit, and would pass just as happily with the track drawn over them.
    Every strip is then placed as a share of the chart's own height, so the
    move has to reach them too.
    """
    assert DAMAGE_DONE_BASELINE_Y <= FIRST_ROW_Y
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    row = timeline.cooldowns[0]
    assert row.baseline_y == FIRST_ROW_Y
    # A literal, not the formula that produced it: restating
    # `hit_top = baseline_y / height * 100` agrees with itself wherever the row
    # sits, which is the same weakness this test was rewritten to escape one
    # assertion earlier. 136 of a 180-unit chart.
    assert (timeline.height, row.hit_top) == (180.0, 75.6)


def test_a_timeline_with_no_damage_done_track_carries_no_derived_badge() -> None:
    """A badge is a grade on something the page drew.

    All three take the same guard, each on the layer it names, because any one
    of the three can be the only layer a chart draws. Here the chart draws a
    press and its cover window and no damage done at all, so the two badges
    that grade those survive and the one that grades the missing track does
    not.
    """
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    assert timeline.damage_done is None
    assert timeline.badge_derived is None
    assert timeline.badge_derived_caption == ""
    # The two layers this chart does draw are still graded.
    assert timeline.badge_measured is not None
    assert timeline.badge_inferred is not None


def test_a_timeline_that_draws_the_track_does_grade_it() -> None:
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (600,)),),
    )
    timeline = a_timeline(loaded, actor_id=1, defensives=KIT)
    assert timeline.damage_done is not None
    assert timeline.badge_derived == badge_for(Confidence.DERIVED)
    assert timeline.badge_derived_caption == BADGE_DERIVED_CAPTION


def a_complete_chart() -> PlayerTimeline:
    """A chart drawing every layer the three badges grade.

    Damage taken bars, a press with its cover window, the dimming after it, and
    a ready tick -- the press is early enough in the run that its cooldown ends
    before the axis does -- plus a damage done series.
    """
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    ).model_copy(
        update={
            "damage_taken": (a_hit(1, 100_000, 500),),
            "damage_done": (a_done_series(1, (600,)),),
        }
    )
    return a_timeline(loaded, defensives=KIT)


def test_a_chart_drawing_every_layer_reads_as_the_whole_sentence() -> None:
    """Composing a caption from the layers drawn must reproduce the full one.

    Otherwise every page that draws all of them changes wording for no reason,
    and the two captions stop matching the constants the swap-guards pin.
    """
    timeline = a_complete_chart()
    assert timeline.damage is not None
    row = timeline.cooldowns[0]
    assert row.presses and row.cover and row.unavailable and row.ready_ticks

    # Literals, not the two constants. Both are built by `_graded_caption`
    # themselves, so comparing a composed caption against one asks the function
    # whether it agrees with itself: joining every layer with a comma and no
    # "and" changes both sides together and passes.
    assert timeline.badge_measured_caption == (
        "the damage taken bars, the press marks and the cover windows."
    )
    assert timeline.badge_inferred_caption == "the dimming and the ready tick that ends it."
    # And the constants still say what a complete chart says, since the page's
    # other captions and the swap-guards are pinned against them.
    assert timeline.badge_measured_caption == BADGE_MEASURED_CAPTION
    assert timeline.badge_inferred_caption == BADGE_INFERRED_CAPTION


def test_the_measured_caption_names_only_the_layers_the_chart_drew() -> None:
    """The caption is the badge's claim about this page, not about the chart in
    general. Naming the press marks and the cover windows over a chart that
    drew neither grades two things absent from it -- the same defect as a badge
    on an absent track, one level finer."""
    timeline = a_timeline_with_damage(amount=500_000, at_seconds=100.0, pull="Atroxus")
    assert timeline.damage is not None and timeline.cooldowns == ()
    assert timeline.badge_measured_caption == "the damage taken bars."


def test_a_row_with_no_aura_data_is_not_credited_with_cover_windows() -> None:
    # The row draws a press and its dimming, and nothing for its cover: the
    # run's aura tables say nothing about the ability, which is the abstention
    # `NO_AURA_DATA` states on the row's own panel.
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        damage_taken=(a_hit(1, 100_000, 500),),
        casts=(a_cast(1, SHIELD.ability_id, 100_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    assert timeline.cooldowns and not any(row.cover for row in timeline.cooldowns)
    assert timeline.badge_measured_caption == "the damage taken bars and the press marks."


def test_a_press_whose_cooldown_outlasts_the_run_grades_no_ready_tick() -> None:
    """The tick is drawn only where the ability came back before the axis ended.

    A press late enough that its cooldown is still running at the last pull
    gets none, because the log never says it came back -- so the inferred badge
    must stop naming one.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 500_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    row = timeline.cooldowns[0]
    assert row.unavailable and row.ready_ticks == ()

    assert timeline.badge_inferred_caption == "the dimming."
    assert timeline.badge_measured_caption == "the press marks."


def test_a_chart_that_draws_neither_track_says_why_for_each_of_them() -> None:
    """Absence stated, so the blank is not read as a run of nothing.

    This is the abstention `NO_AURA_DATA` already makes for cover. A chart that
    simply omits a track leaves a reader to supply their own reason, and the
    likeliest one -- "they did nothing" -- is the reading neither track's
    absence supports.
    """
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    # The chart renders on its rows alone; neither track has anything to draw.
    assert timeline.section.state is SectionState.PRESENT
    assert timeline.damage is None and timeline.damage_done is None

    assert timeline.damage_abstention == NO_DAMAGE_TAKEN
    assert timeline.damage_done_abstention == NO_DAMAGE_DONE


def test_the_two_abstentions_are_not_interchangeable() -> None:
    """Each names the source that came up empty, and they are not the same source.

    The log records damage taken as events, so its silence is a measured fact
    about the player. The graph is a separate response, and its silence is a
    fact about the data -- it can carry no series for a player who certainly
    dealt damage. Swapping the two would state each as the other's kind of
    claim, and a test that only checked both were non-empty would not notice.
    """
    assert NO_DAMAGE_TAKEN != NO_DAMAGE_DONE
    assert "log" in NO_DAMAGE_TAKEN and "graph" not in NO_DAMAGE_TAKEN
    assert "graph" in NO_DAMAGE_DONE
    # Neither says the player did nothing, which is the reading they exist to
    # prevent: the absence is attributed to what was read, not to the player.
    for sentence in (NO_DAMAGE_TAKEN, NO_DAMAGE_DONE):
        for forbidden in ("did nothing", "dealt nothing", "took nothing", "you did"):
            assert forbidden not in sentence.lower(), sentence


def test_a_drawn_track_states_no_abstention_for_itself() -> None:
    """The two must not appear together: a caption and an abstention about one
    track say opposite things, and only one of them can be about the page."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        damage_taken=(a_hit(1, 100_000, 500),),
        damage_done=(a_done_series(1, (600,)),),
    )
    timeline = a_timeline(loaded, actor_id=1)
    assert timeline.damage is not None and timeline.damage_done is not None
    assert timeline.damage_abstention == ""
    assert timeline.damage_done_abstention == ""


def test_one_track_drawn_leaves_only_the_other_ones_abstention() -> None:
    # The two are decided separately, so a fixture with both absent or both
    # present cannot tell a pair of independent guards from one shared guard.
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        damage_done=(a_done_series(1, (600,)),),
    )
    timeline = a_timeline(loaded, actor_id=1)
    assert timeline.damage is None and timeline.damage_done is not None
    assert timeline.damage_abstention == NO_DAMAGE_TAKEN
    assert timeline.damage_done_abstention == ""


def test_the_damage_done_track_is_drawn_clear_of_the_track_above_it() -> None:
    """Where the track sits, pinned against its neighbours rather than its own formula.

    Nothing else asserts this. Swapping either the track's baseline or its
    bars' feet to `DAMAGE_BASELINE_Y` draws this player's output straight over
    the damage they took, in a second colour on the same pixels, and every
    other test in this file and the golden file all stay green.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        damage_taken=(a_hit(1, 100_000, 500),),
        casts=(a_cast(1, SHIELD.ability_id, 100_000),),
        damage_done=(a_done_series(1, (300, 600)),),
    )
    timeline = a_timeline(loaded, actor_id=1, defensives=KIT)
    taken, done = timeline.damage, timeline.damage_done
    assert taken is not None and done is not None

    # Lower on the page than the bars it sits under, and clear of their feet:
    # the two tracks share an axis and must not share pixels.
    assert done.baseline_y > taken.baseline_y
    assert min(bar.y for bar in done.bars) >= taken.baseline_y
    # And above the first row, whose baseline is that row's top edge.
    assert done.baseline_y <= timeline.cooldowns[0].baseline_y
    # Every bar grows from this track's own foot, not from the one above.
    for bar in done.bars:
        assert bar.y + bar.height == done.baseline_y


def test_a_series_that_starts_after_the_first_pull_is_drawn_where_it_starts() -> None:
    """The graph's window and the drawing's origin are two different moments.

    The API reports the fight, and this axis begins at the first pull, so the
    series carries an offset that is zero in no real run. Every other fixture
    here starts both at zero, which makes that subtraction vanish and lets it
    be deleted outright without a test noticing.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        damage_done=(a_done_series(1, (600,), point_start_ms=60_000),),
    )
    timeline = a_timeline(loaded, actor_id=1)
    track = timeline.damage_done
    assert track is not None
    assert track.bars[0].x > TRACK_ORIGIN_X
    assert track.bars[0].x == round(TRACK_ORIGIN_X + 60.0 * a_scale(600.0), PRECISION)
    assert "at 1:00" in track.bars[0].hover


def test_a_chart_of_damage_done_alone_grades_nothing_else() -> None:
    """The state this chart can now reach, and the three claims it must not make.

    Adding damage done to the withholding condition opened a chart that draws
    only that track: a player the graph carried a series for, whose log
    recorded no damage taken and none of whose tracked cooldowns were pressed.
    The measured caption names bars, presses and cover windows and the
    inferred caption names a dimming, and in this chart none of the five is
    drawn. A grade on something absent from the page is a claim about nothing,
    which is the property the derived badge was guarded to keep.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        damage_done=(a_done_series(1, (600,)),),
    )
    timeline = a_timeline(loaded, actor_id=1, defensives=KIT)
    # The chart renders, which is what makes the badges reachable at all.
    assert timeline.section.state is SectionState.PRESENT
    assert timeline.damage_done is not None
    assert timeline.cooldowns == ()
    assert timeline.damage is None

    assert timeline.badge_measured is None
    assert timeline.badge_measured_caption == ""
    assert timeline.badge_inferred is None
    assert timeline.badge_inferred_caption == ""
    # The one layer that is drawn is still graded.
    assert timeline.badge_derived == badge_for(Confidence.DERIVED)


def test_damage_taken_alone_grades_the_bars_and_not_the_dimming() -> None:
    """The two guards are not the same guard, and this is where they part.

    The measured badge grades the damage taken bars as well as the presses, so
    a chart with bars and no rows keeps it. The inferred badge grades only a
    dimming a row draws, so the same chart must lose that one. Guarding both
    on the rows alone would pass every other test in this file and drop a
    grade on bars that are plainly on the page.
    """
    timeline = a_timeline_with_damage(amount=500_000, at_seconds=100.0, pull="Atroxus")
    assert timeline.damage is not None
    assert timeline.cooldowns == ()

    assert timeline.badge_measured == badge_for(Confidence.MEASURED)
    # And the caption names that one layer alone, not the two absent ones the
    # full sentence would also have claimed.
    assert timeline.badge_measured_caption == "the damage taken bars."
    assert timeline.badge_inferred is None
    assert timeline.badge_inferred_caption == ""
