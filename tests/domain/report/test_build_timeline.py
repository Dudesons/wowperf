# ABOUTME: Behaviour tests for timeline geometry: shared axis, marked packs, no leftover arithmetic.
# ABOUTME: The gaps between blocks are travel, which is the reason this layout was chosen.

from tests.domain.report.test_build_frame import (
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    a_loaded,
    a_player,
    a_pull,
    a_run,
)
from wowperf.domain.comparison.alignment import Alignment, align_pulls
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.sample import SpeedMember, SpeedSample
from wowperf.domain.model import Run
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import Section, SectionState
from wowperf.domain.report.timeline import (
    COMPARED_TIMELINE_LEGEND,
    LONE_TIMELINE_LEGEND,
    TRACK_X0,
    TRACK_X1,
    build_timeline,
)

PRESENT = Section(state=SectionState.PRESENT)
WITHHELD = Section(state=SectionState.WITHHELD, reason="no faster run was available")


def a_member(ours: Run, theirs: Run, level: int = 16, code: str = "ref1") -> SpeedMember:
    """A speed member wrapping `theirs`, with the comparability and alignment `_samples`
    computes once against `ours` at sample-build time, and `build_timeline` must reuse."""
    return SpeedMember(
        row=SpeedRow(report_code=code, fight_id=1, keystone_level=level, duration_ms=0, deaths=0),
        run=theirs,
        comparability=Comparability(our_level=ours.keystone_level, their_level=level),
        alignment=align_pulls(ours, theirs),
    )


def a_sample(*members: SpeedMember) -> SpeedSample:
    return SpeedSample(members=members)


def test_a_withheld_timeline_has_no_tracks_at_all() -> None:
    timeline = build_timeline(a_run(), None, WITHHELD)
    assert timeline.ours is None
    assert timeline.theirs is None
    assert timeline.section.state is SectionState.WITHHELD


def test_our_first_block_starts_where_the_axis_starts() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000)))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].x == TRACK_X0


def test_the_axis_is_scaled_to_the_longer_run_so_both_fit() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 100_000),))
    theirs = a_run(pulls=(a_pull(0, 0, 200_000),))
    timeline = build_timeline(ours, a_sample(a_member(ours, theirs)), PRESENT)
    assert timeline.theirs is not None
    # Theirs is the longer run, so its last block ends at the axis's right edge.
    last = timeline.theirs.blocks[-1]
    assert round(last.x + last.width, 6) == TRACK_X1
    # Ours ran half as long, so it ends halfway along.
    assert timeline.ours is not None
    ours_last = timeline.ours.blocks[-1]
    assert round(ours_last.x + ours_last.width) == round(TRACK_X0 + (TRACK_X1 - TRACK_X0) / 2)


def test_the_space_between_blocks_is_travel_and_is_preserved() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 50_000), a_pull(1, 150_000, 200_000)))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ours is not None
    first, second = timeline.ours.blocks
    assert second.x > first.x + first.width


def test_a_boss_pull_is_marked_as_one() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, encounter_id=12825),))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].is_boss is True


def test_a_pack_only_we_pulled_is_marked_as_extra() -> None:
    ours = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    theirs = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    timeline = build_timeline(ours, a_sample(a_member(ours, theirs)), PRESENT)
    assert timeline.ours is not None
    assert [block.kind for block in timeline.ours.blocks] == ["matched", "extra"]


def test_a_pack_only_they_pulled_is_marked_as_skipped() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    theirs = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    timeline = build_timeline(ours, a_sample(a_member(ours, theirs)), PRESENT)
    assert timeline.theirs is not None
    assert [block.kind for block in timeline.theirs.blocks] == ["matched", "skipped"]


def test_an_extra_boss_pull_carries_both_marks() -> None:
    # A pull can be both a boss and one only we pulled (an optional add-on boss
    # the reference run skipped). Its css_class must carry both classes, so the
    # stylesheet's rule order — not the template — decides which stroke wins.
    ours = a_run(pulls=(a_pull(0, 0, 60_000, encounter_id=12825, enemies=(1,)),))
    theirs = a_run(pulls=())
    timeline = build_timeline(ours, a_sample(a_member(ours, theirs)), PRESENT)
    assert timeline.ours is not None
    block = timeline.ours.blocks[0]
    assert block.kind == "extra"
    assert block.is_boss is True
    assert block.css_class == "block-extra block-boss"


def test_every_block_carries_its_pack_name_for_the_tooltip() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].label == "Pack 0"


def test_a_very_short_pull_still_has_a_visible_width() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 100), a_pull(1, 500_000, 900_000)))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].width >= 2.0


def test_a_run_with_no_pulls_yields_no_blocks_and_does_not_divide_by_zero() -> None:
    empty = a_run(pulls=())
    timeline = build_timeline(empty, a_sample(a_member(empty, empty)), PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks == ()


def test_the_axis_carries_ticks_a_reader_can_read() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 1_200_000),))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ticks
    assert all(":" in label for _x, label in timeline.ticks)


def test_the_caption_names_the_run_and_the_span_it_measures() -> None:
    # `run_seconds` spans first-pull-start to last-pull-end, not the run's
    # completion time from `keystone_time_seconds` — the header states that
    # other, longer figure. The caption must say which one this is, so a
    # reader never takes the two different numbers on the page as a
    # contradiction.
    ours = a_run(pulls=(a_pull(0, 0, 600_000),))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.caption == "Ours — 10:00 from first pull to last"
    assert timeline.theirs is not None
    assert timeline.theirs.caption == (
        "Reference — 10:00 from first pull to last, one of 1 fast runs"
    )


def test_without_a_speed_reference_build_report_leaves_the_tracks_empty() -> None:
    report = build_report(a_loaded(), (), None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES)
    assert report.timeline.ours is None


def test_no_reference_track_is_drawn_when_no_member_shares_our_keystone_level() -> None:
    # `compare.duration` already refuses to print a number across a keystone gap,
    # and drawing that member's pull lengths anyway would contradict it. Our own
    # track survives: it is measured on our own log and says the same thing
    # whether or not anyone comparable ran the dungeon.
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    theirs = a_run(pulls=(a_pull(0, 0, 60_000),))
    sample = a_sample(a_member(ours, theirs, level=15))
    timeline = build_timeline(ours, sample, PRESENT)
    assert timeline.theirs is None
    assert timeline.ours is not None
    assert timeline.ours.blocks


def test_a_lone_track_says_why_there_is_nothing_to_compare_it_against() -> None:
    # A PRESENT section with no reference track once drew a heading, a legend
    # describing reference blocks, and an empty box. The legend now states the
    # keystone-level reason instead, and never describes a mark no block wears.
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    theirs = a_run(pulls=(a_pull(0, 0, 60_000),))
    sample = a_sample(a_member(ours, theirs, level=15))

    timeline = build_timeline(ours, sample, PRESENT)

    assert timeline.legend == LONE_TIMELINE_LEGEND
    assert "keystone level" in timeline.legend
    assert "skipped" not in timeline.legend


def test_a_compared_timeline_keeps_the_legend_that_describes_both_tracks() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_timeline(ours, a_sample(a_member(ours, ours)), PRESENT)

    assert timeline.legend == COMPARED_TIMELINE_LEGEND


def test_a_withheld_timeline_offers_no_legend_to_render() -> None:
    timeline = build_timeline(a_run(), None, WITHHELD)

    assert timeline.legend == ""


def test_a_single_duration_eligible_member_among_off_level_ones_is_still_drawn() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    off_level = a_run(pulls=(a_pull(0, 0, 60_000),))
    on_level = a_run(pulls=(a_pull(0, 0, 60_000),))
    sample = a_sample(
        a_member(ours, off_level, level=15, code="off"),
        a_member(ours, on_level, level=16, code="on"),
    )
    timeline = build_timeline(ours, sample, PRESENT)
    assert timeline.theirs is not None


def test_the_timeline_track_names_the_member_it_drew_and_the_sample_size() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 600_000),))
    sample = a_sample(
        *(
            a_member(ours, a_run(pulls=(a_pull(0, 0, 600_000),)), code=f"ref{i}")
            for i in range(5)
        )
    )
    timeline = build_timeline(ours, sample, PRESENT)
    assert timeline.theirs is not None
    assert timeline.theirs.caption.endswith("one of 5 fast runs")


def test_among_several_duration_eligible_members_the_best_aligned_one_is_drawn() -> None:
    ours = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    # Shares our level but aligns only one of our two pulls.
    poorly_aligned = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    # Shares our level and aligns both.
    well_aligned = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    sample = a_sample(
        a_member(ours, poorly_aligned, code="poor"),
        a_member(ours, well_aligned, code="good"),
    )
    timeline = build_timeline(ours, sample, PRESENT)
    assert timeline.theirs is not None
    assert len(timeline.theirs.blocks) == 2


def test_the_timeline_draws_the_members_own_alignment_not_a_recomputed_one() -> None:
    # align_pulls(ours, theirs) would match this single shared pull on both sides.
    # The member below carries a deliberately different, hand-built alignment
    # instead — the only way this test passes is if build_timeline draws that
    # stored alignment rather than calling align_pulls a second time.
    ours = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    theirs = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    member = SpeedMember(
        row=SpeedRow(report_code="ref1", fight_id=1, keystone_level=16, duration_ms=0, deaths=0),
        run=theirs,
        comparability=Comparability(our_level=16, their_level=16),
        alignment=Alignment(only_ours=(0,), only_theirs=(0,)),
    )
    timeline = build_timeline(ours, a_sample(member), PRESENT)
    assert timeline.ours is not None
    assert timeline.theirs is not None
    assert timeline.ours.blocks[0].kind == "extra"
    assert timeline.theirs.blocks[0].kind == "skipped"


def test_an_artefact_pull_is_not_outlined_as_a_pack_the_reference_skipped() -> None:
    # The legend calls the heavier outline a pack we pulled and the reference did
    # not. A pull Warcraft Logs cut out of the middle of an engagement is not one,
    # and `compare_route` will not name it, so the picture must not claim it either.
    ours = a_run(
        pulls=(
            a_pull(0, 0, 60_000, enemies=(1,)),
            a_pull(1, 90_000, 90_048, enemies=(7,)),
            a_pull(2, 100_000, 160_000, enemies=()),
            a_pull(3, 200_000, 260_000, enemies=(8,)),
        )
    )
    theirs = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))

    timeline = build_timeline(ours, a_sample(a_member(ours, theirs)), PRESENT)

    assert timeline.ours is not None
    assert [block.kind for block in timeline.ours.blocks] == [
        "matched",
        "matched",
        "matched",
        "extra",
    ]


def test_a_reference_artefact_pull_is_not_drawn_as_a_pack_we_skipped() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    theirs = a_run(
        pulls=(
            a_pull(0, 0, 60_000, enemies=(1,)),
            a_pull(1, 90_000, 90_048, enemies=(7,)),
            a_pull(2, 100_000, 160_000, enemies=()),
            a_pull(3, 200_000, 260_000, enemies=(8,)),
        )
    )

    timeline = build_timeline(ours, a_sample(a_member(ours, theirs)), PRESENT)

    assert timeline.theirs is not None
    assert [block.kind for block in timeline.theirs.blocks] == [
        "matched",
        "matched",
        "matched",
        "skipped",
    ]
