# ABOUTME: Behaviour tests for the report's four data sections and the inline timeline SVG.
# ABOUTME: The template does no arithmetic: every coordinate here was computed in build_timeline.

import pytest
from markupsafe import escape

from tests.adapters.render.test_html import a_report, a_row
from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.adapters.render.html import render
from wowperf.domain.report import build as build_module
from wowperf.domain.report.build import build_timeline
from wowperf.domain.report.model import (
    DamageRow,
    DeathCard,
    PlayerCard,
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)

PRESENT = Section(state=SectionState.PRESENT)


def a_timeline() -> Timeline:
    return Timeline(
        section=PRESENT,
        ours=TimelineTrack(
            caption="Ours — 31:48",
            baseline_y=58.0,
            blocks=(
                TimelineBlock(label="Loa Speaker Nanea", x=46.0, width=50.0, is_boss=True,
                              kind="matched", css_class="block block-boss"),
                TimelineBlock(label="Frostbound trio", x=120.0, width=20.0, is_boss=False,
                              kind="extra", css_class="block-extra"),
            ),
        ),
        theirs=TimelineTrack(
            caption="Reference — 27:30",
            baseline_y=132.0,
            blocks=(
                TimelineBlock(label="Shale Prowlers", x=60.0, width=15.0, is_boss=False,
                              kind="skipped", css_class="block-skipped"),
            ),
        ),
        ticks=((46.0, "0:00"), (240.0, "10:00")),
        width=680.0,
        height=208.0,
        tick_y1=46.0,
        tick_y2=176.0,
        tick_label_y=192.0,
        caption_x=46.0,
        caption_dy=-10.0,
        block_height=26.0,
    )


def test_the_timeline_renders_as_inline_svg() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<svg" in html
    assert 'viewBox="0 0 680.0 208.0"' in html


def test_a_withheld_timeline_emits_no_svg_at_all() -> None:
    # a_report()'s default timeline is withheld: the "no empty chart frame" rule.
    html = render(a_report())
    assert "<svg" not in html


def test_every_block_carries_its_pack_name_as_a_tooltip() -> None:
    # Escaped on comparison: real pack names commonly carry an apostrophe
    # (e.g. an NPC possessive), which autoescape would transform.
    html = render(a_report(timeline=a_timeline()))
    assert f"<title>{escape('Loa Speaker Nanea')}</title>" in html
    assert f"<title>{escape('Frostbound trio')}</title>" in html


def test_an_svg_title_escapes_hostile_input() -> None:
    timeline = Timeline(
        section=PRESENT,
        ours=TimelineTrack(
            caption="Ours",
            baseline_y=58.0,
            blocks=(
                TimelineBlock(
                    label="</title><img src=x onerror=alert(1)>",
                    x=46.0,
                    width=10.0,
                    is_boss=False,
                    kind="matched",
                    css_class="block",
                ),
            ),
        ),
        ticks=(),
        width=680.0,
        height=208.0,
        tick_y1=46.0,
        tick_y2=176.0,
        tick_label_y=192.0,
        caption_x=46.0,
        caption_dy=-10.0,
        block_height=26.0,
    )
    html = render(a_report(timeline=timeline))
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;/title&gt;&lt;img" in html


def test_a_boss_block_is_distinguishable_from_a_trash_block() -> None:
    html = render(a_report(timeline=a_timeline()))
    # The boss block's class carries block-boss; the non-boss block's does not.
    assert 'class="block block-boss"' in html
    assert 'class="block-extra"' in html
    assert "block-extra block-boss" not in html


def test_an_extra_pack_and_a_skipped_pack_are_marked_differently() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert 'class="block-extra"' in html
    assert 'class="block-skipped"' in html
    assert "block-extra block-skipped" not in html
    assert "block-skipped block-extra" not in html


def test_both_captions_are_rendered() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "Ours — 31:48" in html
    assert "Reference — 27:30" in html


def test_the_axis_ticks_are_rendered() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert ">10:00<" in html


def test_the_timeline_legend_names_all_three_marks() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "boss pull" in html
    assert "we pulled" in html and "reference run skipped" in html
    assert "reference run pulled" in html and "we skipped" in html


def test_changing_timeline_height_moves_the_tick_geometry_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No coordinate in the SVG is a template literal: it all comes from build_timeline,
    # so changing TIMELINE_HEIGHT there moves the tick line, its label, and nothing else,
    # together, without touching the template.
    monkeypatch.setattr(build_module, "TIMELINE_HEIGHT", 300.0)
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_module.build_timeline(run, run, PRESENT)
    assert timeline.height == 300.0
    assert timeline.tick_y2 == 300.0 - 32.0
    assert timeline.tick_label_y == 300.0 - 16.0

    html = render(a_report(timeline=timeline))
    assert f'y2="{timeline.tick_y2}"' in html
    assert f'y="{timeline.tick_label_y}"' in html
    assert f'height="{timeline.block_height}"' in html


def test_the_rendered_geometry_matches_what_build_timeline_computed() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_timeline(run, run, PRESENT)
    html = render(a_report(timeline=timeline))
    assert timeline.ours is not None
    assert f'y1="{timeline.tick_y1}"' in html
    assert f'y="{timeline.ours.baseline_y}"' in html


def test_a_death_card_shows_the_run_up() -> None:
    card = DeathCard(
        player="Dudesons",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
        last_ten_seconds=(
            DamageRow(seconds_before="5.8s before", ability="Snowdrift", amount="82,410"),
        ),
    )
    # Escaped on comparison: real ability names commonly carry an apostrophe
    # (e.g. "Nature's Wrath"), which autoescape would transform.
    html = render(a_report(deaths=(card,)))
    assert str(escape("Frigid Roar")) in html
    assert str(escape("Snowdrift")) in html
    assert "5.8s before" in html


def test_a_run_with_no_deaths_says_so_rather_than_showing_an_empty_heading() -> None:
    html = render(a_report(deaths=()))
    assert "No deaths" in html


def test_the_interrupts_section_renders_its_rows() -> None:
    # Escaped on comparison: the row title embeds a real ability name, which
    # can carry an apostrophe that autoescape would transform.
    title = "Snowdrift, 3 casts"
    html = render(a_report(interrupts=(a_row("interrupts.ability.0", title=title),)))
    assert str(escape(title)) in html


def test_a_player_card_prints_the_class_name_beside_the_colour() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        stats_line="182 casts in 31:49 of pulls · 1 death · 7 interrupts",
        spell_and_talent=Section(state=SectionState.WITHHELD, reason="no ranked parse"),
    )
    html = render(a_report(players=(card,)))
    assert "DeathKnight" in html
    assert "Blood" in html
    assert "class-deathknight" in html


def test_a_player_cards_withheld_comparison_states_its_reason() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        stats_line="182 casts in 31:49 of pulls · 0 deaths · 0 interrupts",
        spell_and_talent=Section(state=SectionState.WITHHELD, reason="no ranked parse was found"),
    )
    html = render(a_report(players=(card,)))
    assert "no ranked parse was found" in html


def test_a_run_with_no_players_says_so_rather_than_showing_an_empty_heading() -> None:
    html = render(a_report(players=()))
    assert "No players" in html
