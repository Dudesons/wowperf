# ABOUTME: Behaviour tests for timeline geometry: shared axis, marked packs, no leftover arithmetic.
# ABOUTME: The gaps between blocks are travel, which is the reason this layout was chosen.

from tests.domain.report.test_build_frame import FETCHED, a_loaded, a_pull, a_run
from wowperf.domain.report.build import TRACK_X0, TRACK_X1, build_report, build_timeline
from wowperf.domain.report.model import Section, SectionState

PRESENT = Section(state=SectionState.PRESENT)
WITHHELD = Section(state=SectionState.WITHHELD, reason="no faster run was available")


def test_a_withheld_timeline_has_no_tracks_at_all() -> None:
    timeline = build_timeline(a_run(), None, WITHHELD)
    assert timeline.ours is None
    assert timeline.theirs is None
    assert timeline.section.state is SectionState.WITHHELD


def test_our_first_block_starts_where_the_axis_starts() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000)))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].x == TRACK_X0


def test_the_axis_is_scaled_to_the_longer_run_so_both_fit() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 100_000),))
    theirs = a_run(pulls=(a_pull(0, 0, 200_000),))
    timeline = build_timeline(ours, theirs, PRESENT)
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
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    first, second = timeline.ours.blocks
    assert second.x > first.x + first.width


def test_a_boss_pull_is_marked_as_one() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, encounter_id=12825),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].is_boss is True


def test_a_pack_only_we_pulled_is_marked_as_extra() -> None:
    ours = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    theirs = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    timeline = build_timeline(ours, theirs, PRESENT)
    assert timeline.ours is not None
    assert [block.kind for block in timeline.ours.blocks] == ["matched", "extra"]


def test_a_pack_only_they_pulled_is_marked_as_skipped() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    theirs = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    timeline = build_timeline(ours, theirs, PRESENT)
    assert timeline.theirs is not None
    assert [block.kind for block in timeline.theirs.blocks] == ["matched", "skipped"]


def test_an_extra_boss_pull_carries_both_marks() -> None:
    # A pull can be both a boss and one only we pulled (an optional add-on boss
    # the reference run skipped). Its css_class must carry both classes, so the
    # stylesheet's rule order — not the template — decides which stroke wins.
    ours = a_run(pulls=(a_pull(0, 0, 60_000, encounter_id=12825, enemies=(1,)),))
    theirs = a_run(pulls=())
    timeline = build_timeline(ours, theirs, PRESENT)
    assert timeline.ours is not None
    block = timeline.ours.blocks[0]
    assert block.kind == "extra"
    assert block.is_boss is True
    assert block.css_class == "block-extra block-boss"


def test_every_block_carries_its_pack_name_for_the_tooltip() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].label == "Pack 0"


def test_a_very_short_pull_still_has_a_visible_width() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 100), a_pull(1, 500_000, 900_000)))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].width >= 2.0


def test_a_run_with_no_pulls_yields_no_blocks_and_does_not_divide_by_zero() -> None:
    empty = a_run(pulls=())
    timeline = build_timeline(empty, empty, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks == ()


def test_the_axis_carries_ticks_a_reader_can_read() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 1_200_000),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ticks
    assert all(":" in label for _x, label in timeline.ticks)


def test_the_caption_names_the_run_and_the_span_it_measures() -> None:
    # `_run_seconds` spans first-pull-start to last-pull-end, not the run's
    # completion time from `keystone_time_seconds` — the header states that
    # other, longer figure. The caption must say which one this is, so a
    # reader never takes the two different numbers on the page as a
    # contradiction.
    ours = a_run(pulls=(a_pull(0, 0, 600_000),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.caption == "Ours — 10:00 from first pull to last"
    assert timeline.theirs is not None
    assert timeline.theirs.caption == "Reference — 10:00 from first pull to last"


def test_without_a_speed_reference_build_report_leaves_the_tracks_empty() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.timeline.ours is None
