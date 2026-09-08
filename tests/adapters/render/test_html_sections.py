# ABOUTME: Behaviour tests for the report's four data sections and the inline timeline SVG.
# ABOUTME: The template does no arithmetic: every coordinate here was computed in build_timeline.

import pytest
from markupsafe import escape

from tests.adapters.render.test_html import a_report, a_row
from tests.domain.report.test_build_frame import (
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    a_pull,
    a_run,
)
from tests.domain.report.test_build_observations import SUBJECT, a_finding, a_loaded
from wowperf.adapters.render.html import render
from wowperf.domain.report import build as build_module
from wowperf.domain.report.build import build_report, build_timeline
from wowperf.domain.report.model import (
    AvailabilityGroup,
    AvailabilityRow,
    Badge,
    DeathCard,
    PlayerCard,
    RecapRow,
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


def test_the_svg_carries_its_own_title_separate_from_a_blocks_title() -> None:
    # No `role="img"`: that would flatten the whole chart into one image for
    # assistive tech and hide every block's own <title> behind it, leaving pack
    # names reachable on hover only. The SVG's own first-child <title> names
    # the chart instead, as a distinct, earlier element from any block's own
    # <title> -- so a future edit cannot collapse the two back into one.
    html = render(a_report(timeline=a_timeline()))
    assert 'role="img"' not in html
    svg_open = html.index("<svg")
    chart_title_at = html.index("<title>Both runs on one elapsed-time axis</title>", svg_open)
    first_block_title_at = html.index("<title>", chart_title_at + 1)
    assert svg_open < chart_title_at < first_block_title_at
    assert html[first_block_title_at:].startswith("<title>Loa Speaker Nanea</title>")


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


def test_every_row_kind_and_every_availability_state_reaches_the_page_as_a_class() -> None:
    # The template maps a kind and a state to a class and to nothing else, so
    # the eight names below are the whole of what tells the rows apart on screen.
    card = DeathCard(
        player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
        killing_blow="Frigid Roar",
        timeline=tuple(
            RecapRow(seconds_before="1.0 s", kind=kind, ability=kind.title())
            for kind in ("hit", "absorb", "heal", "cast")
        ),
        availability=(
            AvailabilityGroup(title="Defensives", rows=tuple(
                AvailabilityRow(ability=state.title(), state=state)
                for state in ("pressed", "ready", "cooldown", "unseen")
            )),
        ),
    )

    html = render(a_report(deaths=(card,)))

    assert [kind for kind in ("hit", "absorb", "heal", "cast")
            if f'<tr class="{kind}">' not in html] == []
    assert [state for state in ("pressed", "ready", "cooldown", "unseen")
            if f'<li class="{state}">' not in html] == []


def test_a_death_card_with_no_timeline_prints_the_note_the_builder_wrote() -> None:
    # Deliberately not the builder's own wording: the template must print the
    # card's note rather than a sentence of its own.
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", timeline_note="Nothing reached this player.")

    html = render(a_report(deaths=(card,)))

    assert "Nothing reached this player." in html


def test_a_death_card_renders_its_recap() -> None:
    card = DeathCard(
        player="Stonewake",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
        timeline=(
            RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                     detail="82,410 to health", health="61%", health_percent=61),
        ),
        health_badge=Badge(label="derived", tint="badge-derived"),
        came_back="Released; first action against an enemy 34.2 s after death.",
        came_back_badge=Badge(label="derived", tint="badge-derived"),
        availability=(
            AvailabilityGroup(title="Defensives", rows=(
                AvailabilityRow(ability="Icebound Fortitude", state="cooldown",
                                detail="at most 14 s left"),
            ), badge=Badge(label="inferred", tint="badge-inferred")),
            AvailabilityGroup(title="Consumables", note="nothing judged"),
            AvailabilityGroup(title="Teammates' externals", rows=(
                AvailabilityRow(ability="Ironbark", owner="Leafy", state="ready"),
            ), badge=Badge(label="inferred", tint="badge-inferred")),
        ),
    )
    # Escaped on comparison: real ability names commonly carry an apostrophe
    # (e.g. "Nature's Wrath"), which autoescape would transform.
    html = render(a_report(deaths=(card,)))
    deaths = html[html.index('<h2 id="deaths">'):html.index('<h2 id="interrupts">')]
    assert str(escape("Frigid Roar")) in deaths
    assert '<tr class="hit">' in deaths and str(escape("Snowdrift")) in deaths
    assert 'style="width: 61%"' in deaths and "61%" in deaths
    assert "34.2 s after death" in deaths
    assert '<li class="cooldown">' in deaths and "at most 14 s left" in deaths
    assert "Leafy" in deaths and "nothing judged" in deaths
    assert deaths.count('href="#provenance"') >= 4  # health, return, two groups


def test_the_provenance_lists_the_methods_the_builder_named() -> None:
    report = a_report()
    provenance = report.provenance.model_copy(update={"methods": ("Health is reconstructed.",)})
    html = render(report.model_copy(update={"provenance": provenance}))
    assert "Health is reconstructed." in html[html.index('<h2 id="provenance">'):]


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
        name="Stonewake",
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
        name="Stonewake",
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


def test_death_findings_render_inside_the_deaths_section() -> None:
    html = render(build_report(a_loaded(), (
        a_finding(
            "defensives.unused.Emberkin",
            title="Emberkin died once with a defensive available",
        ),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    deaths_start = html.index('<h2 id="deaths">')
    interrupts_start = html.index('<h2 id="interrupts">')
    title_at = html.index("Emberkin died once with a defensive available")
    assert deaths_start < title_at < interrupts_start


def test_route_rows_render_inside_the_route_section() -> None:
    html = render(build_report(a_loaded(), (
        a_finding("time.gap.0", seconds=41.0, title="A 41 second gap after pull 0"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    route_start = html.index('<h2 id="route">')
    deaths_start = html.index('<h2 id="deaths">')
    # The card's own heading, not the Summary's pointer to it: the pointer
    # repeats the same title as a link, earlier on the page, under "losses".
    title_at = html.index("<h3>A 41 second gap after pull 0</h3>")
    assert route_start < title_at < deaths_start


def test_a_withheld_route_states_its_reason_and_still_shows_the_gaps() -> None:
    # Without a speed reference the comparison is withheld, but a gap between our
    # own pulls needs no reference and must not disappear with it.
    html = render(build_report(a_loaded(), (
        a_finding("time.gap.0", seconds=41.0, title="A 41 second gap after pull 0"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    route = html[html.index('<h2 id="route">'):html.index('<h2 id="deaths">')]
    assert 'class="withheld"' in route
    assert "A 41 second gap after pull 0" in route


def test_the_narrative_renders_inside_the_summary_panel() -> None:
    # The panel-hiding rule only touches `.panel` elements, so anything that
    # renders outside a panel shows on every tab. The narrative belongs to
    # Summary and must sit between the panel's opening tag and the next
    # <section> tag, not ahead of the panel altogether.
    narrative = "Both losses were travel, not damage."
    html = render(a_report(narrative=narrative))
    summary_open = html.index('<section class="panel" data-tab-panel="main" id="tab-summary">')
    next_section = html.index("<section ", summary_open + 1)
    narrative_at = html.index('<h2 id="narrative">')
    assert summary_open < narrative_at < next_section


def test_group_rows_render_inside_the_players_section() -> None:
    # Observations sits in the Summary panel, ahead of Players, so the section
    # that follows Players in document order is Provenance.
    html = render(build_report(a_loaded(), (
        a_finding("throughput.alignment.1", title="Emberkin had a cooldown ready and unpressed"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    players_start = html.index('<h2 id="players">')
    provenance_start = html.index('<h2 id="provenance">')
    title_at = html.index("Emberkin had a cooldown ready and unpressed")
    assert players_start < title_at < provenance_start
