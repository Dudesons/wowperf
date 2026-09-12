# ABOUTME: Behaviour tests for the report's four data sections and the inline timeline SVG.
# ABOUTME: The template does no arithmetic: every coordinate here was computed in build_timeline.

import re
from pathlib import Path

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
from tests.domain.report.test_build_timeline import a_member, a_sample
from wowperf.adapters.render.html import render
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report import player_timeline as player_timeline_module
from wowperf.domain.report import timeline as timeline_module
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import (
    AvailabilityGroup,
    AvailabilityRow,
    Badge,
    CooldownRow,
    CurveGuide,
    CurvePoint,
    CurveReading,
    CurveTick,
    DamageBar,
    DamageTrack,
    DeathCard,
    HealthCurve,
    LedgerRow,
    PlayerCard,
    PlayerTimeline,
    Press,
    RecapRow,
    Section,
    SectionState,
    Span,
    Timeline,
    TimelineBlock,
    TimelineTrack,
    Tooltip,
    TooltipLine,
)
from wowperf.domain.report.timeline import build_timeline

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
        legend=timeline_module.COMPARED_TIMELINE_LEGEND,
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


def test_a_lone_track_renders_its_own_legend_and_not_the_compared_one() -> None:
    """The legend is written in build.py, so the template prints whichever one it
    was given: a page with no reference track must not carry a legend explaining
    marks no block on it wears."""
    lone = a_timeline().model_copy(
        update={"theirs": None, "legend": timeline_module.LONE_TIMELINE_LEGEND}
    )

    html = render(a_report(timeline=lone))

    assert "no reference in the sample ran our keystone level" in html
    assert "reference run skipped" not in html


def test_changing_timeline_height_moves_the_tick_geometry_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No coordinate in the SVG is a template literal: it all comes from build_timeline,
    # so changing TIMELINE_HEIGHT there moves the tick line, its label, and nothing else,
    # together, without touching the template.
    monkeypatch.setattr(timeline_module, "TIMELINE_HEIGHT", 300.0)
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = timeline_module.build_timeline(run, a_sample(a_member(run, run)), PRESENT)
    assert timeline.height == 300.0
    assert timeline.tick_y2 == 300.0 - 32.0
    assert timeline.tick_label_y == 300.0 - 16.0

    html = render(a_report(timeline=timeline))
    assert f'y2="{timeline.tick_y2}"' in html
    assert f'y="{timeline.tick_label_y}"' in html
    assert f'height="{timeline.block_height}"' in html


def test_the_rendered_geometry_matches_what_build_timeline_computed() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_timeline(run, a_sample(a_member(run, run)), PRESENT)
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
            "defensives.unused.emberkin",
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


def test_each_player_gets_a_sub_tab_button_pointing_at_their_own_panel() -> None:
    # A local import: test_html_invariants imports FakeIcons from this module,
    # so a module-level import back would make the two modules circular and
    # fail to collect every test in this file.
    from tests.adapters.render.test_html_invariants import rich_html

    html = rich_html()
    navs = re.findall(r'data-tab-group="players".*?</nav>', html, flags=re.S)
    assert navs, "the players panel has no sub-tab nav"
    targets = re.findall(r'data-tab-for="(player-[^"]+)"', navs[0])
    # rich_loaded() has two players. Asserting the count rather than truthiness is
    # what stops this passing against a nav that rendered one button, or none.
    assert len(targets) == 2
    for target in targets:
        assert f'id="{target}"' in html
    assert html.count('data-tab-panel="players"') == len(targets)


def test_the_subjects_sub_tab_is_the_one_that_opens_first() -> None:
    # design section 3. `report.js.j2` activates the first `[data-tab-for]` in
    # each group, so "opens first" is "is drawn first" -- and the panels must
    # move with the buttons, or the nav and the cards disagree about order.
    # The subject is last on this roster on purpose: with them first, a page
    # that never ordered anything would pass.
    roster = (
        Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=680),
        Player(actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood",
               item_level=675),
    )
    subject = roster[1]
    loaded = LoadedRun(run=a_run(players=roster, pulls=(a_pull(0, 0, 60_000),)))
    html = render(build_report(loaded, (), None, None, subject, None, FETCHED,
                               NO_DEFENSIVES, NO_CONSUMABLES))
    nav = re.search(r'data-tab-group="players".*?</nav>', html, flags=re.S)
    assert nav is not None
    buttons = re.findall(r'data-tab-for="(player-[^"]+)"', nav.group(0))
    panels = re.findall(r'data-tab-panel="players" id="(player-[^"]+)"', html)
    assert buttons[0].startswith("player-stonewake")
    assert panels == buttons


def a_curve() -> HealthCurve:
    return HealthCurve(
        width=680.0,
        height=148.0,
        plot_x0=40.0,
        plot_x1=668.0,
        plot_y0=14.0,
        plot_y1=116.0,
        plot_height=102.0,
        label_x=34.0,
        tick_label_y=136.0,
        points=(CurvePoint(x=40.0, y=14.0), CurvePoint(x=668.0, y=116.0)),
        readings=(CurveReading(x=40.0, y=14.0, percent=100),),
        ticks=(CurveTick(x=40.0, label="10 s"), CurveTick(x=668.0, label="death")),
        guides=(CurveGuide(y=14.0, label="100%"), CurveGuide(y=116.0, label="0%")),
        reading_legend="A dot is a health reading the log stated.",
        line_legend="Between dots the line is arithmetic.",
        line_badge=Badge(label="derived", tint="badge-derived"),
        reading_badge=Badge(label="measured", tint="badge-measured"),
    )


def a_card(**changes: object) -> DeathCard:
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", timeline_summary="2 events",
                     timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                                        health="61%", health_percent=61),))
    return card.model_copy(update=changes)


def deaths_of(card: DeathCard) -> str:
    html = render(a_report(deaths=(card,)))
    return html[html.index('<h2 id="deaths">'):html.index('<h2 id="interrupts">')]


def test_a_death_card_draws_its_health_curve_as_inline_svg() -> None:
    deaths = deaths_of(a_card(health_curve=a_curve()))
    assert "40.0,14.0" in deaths and "668.0,116.0" in deaths
    assert '<circle' in deaths and 'cx="40.0"' in deaths
    # Anchored to their own elements: the slice starts at the Deaths heading, so a
    # bare "death" matches the section itself, and "0%" matches inside "100%".
    assert ">10 s</text>" in deaths and ">death</text>" in deaths
    assert ">100%</text>" in deaths and ">0%</text>" in deaths


def test_the_curve_prints_the_legend_and_both_badges_the_builder_wrote() -> None:
    deaths = deaths_of(a_card(health_curve=a_curve()))
    assert "A dot is a health reading the log stated." in deaths
    assert "Between dots the line is arithmetic." in deaths
    assert "measured" in deaths and "derived" in deaths


def test_the_health_curve_and_its_legends_share_a_pinned_wrapper() -> None:
    # A reader hovering a row 1400px down the table still needs the curve that
    # row lights, and the card stands 2007px against a 900px viewport. Nothing
    # inside the wrapper is itself a div, so the first closing tag after it is
    # the wrapper's own.
    html = render(a_report(deaths=(a_card(health_curve=a_curve()),)))
    start = html.index('<div class="hp-pinned">')
    pinned = html[start:html.index("</div>", start)]
    assert '<svg class="hp-curve"' in pinned
    assert pinned.count('<p class="legend">') == 2
    assert ".hp-pinned { position: sticky;" in html


def test_the_curve_draws_arithmetic_dashed_and_a_stated_reading_as_a_ring() -> None:
    # The line is derived and the dots are measured, and the badges beneath say
    # so. Saying it in shape as well as in words means a reader who never reads
    # the legend still sees two different claims.
    curve = HealthCurve(
        width=680.0, height=148.0, plot_x0=40.0, plot_x1=648.0, plot_y0=14.0, plot_y1=116.0,
        plot_height=102.0,
        label_x=34.0,
        tick_label_y=136.0,
        points=(CurvePoint(x=40.0, y=14.0), CurvePoint(x=648.0, y=116.0)),
        readings=(CurveReading(x=40.0, y=14.0, percent=100),),
    )
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", health_curve=curve)
    html = render(a_report(deaths=(card,)))
    # The line is dashed: stroke-linejoin followed by stroke-dasharray appears
    # only in the .hp-line rule after this change.
    assert "stroke-linejoin: round; stroke-dasharray: 5 3;" in html
    # The reading is ringed: the rule now has both fill and stroke, a
    # combination that did not exist before.
    assert "fill: var(--badge-measured); stroke: var(--page); stroke-width: 1.5;" in html
    # The reading's radius is increased so the ring stroke is visible: assert
    # the whole opening tag rather than the bare radius, which could appear
    # on any circle.
    assert '<circle class="hp-reading" cx="40.0" cy="14.0" r="3.5">' in html


def test_a_curve_with_no_readings_draws_no_dots_and_claims_no_measurement() -> None:
    curve = a_curve().model_copy(
        update={"readings": (), "reading_badge": None, "reading_legend": ""}
    )
    deaths = deaths_of(a_card(health_curve=curve))
    assert "<circle" not in deaths
    assert "measured" not in deaths


def test_a_recap_row_with_a_marker_draws_a_hidden_line_on_the_curve() -> None:
    # The script test in test_html_invariants.py proves the CSS rule and the JS
    # handlers exist, but that string sits in the stylesheet regardless of
    # whether any card actually draws a marker. This proves the template
    # itself draws the hidden `<line>` a real row's marker_x asks for, tied
    # to the row's own id by the "-mark" suffix the script looks up.
    curve = a_curve()
    row = RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                   health="61%", health_percent=61, marker_id="death-0-e0", marker_x=50.0)
    deaths = deaths_of(a_card(health_curve=curve, timeline=(row,)))
    assert (
        '<line class="hp-marker" id="death-0-e0-mark"\n'
        f'        x1="50.0" y1="{curve.plot_y0}"\n'
        f'        x2="50.0" y2="{curve.plot_y1}"></line>'
    ) in deaths


def test_a_recap_row_with_no_marker_draws_no_line_on_the_curve() -> None:
    # The default RecapRow carries no marker_x, and a card can carry a curve
    # while one of its rows falls outside it (or before build_deaths ever ran).
    deaths = deaths_of(a_card(health_curve=a_curve()))
    assert "hp-marker" not in deaths


def test_a_pressed_row_with_a_cover_window_draws_a_hidden_rect_on_the_curve() -> None:
    # Same proof as the marker test above, for the window a press covered: the
    # template itself draws the hidden `<rect>` a real row's cover_x and
    # cover_width ask for, tied to the row's own id by the "-cover" suffix the
    # script looks up.
    curve = a_curve()
    row = RecapRow(seconds_before="5.0 s", kind="cast", ability="Icebound Fortitude",
                   marker_id="death-0-e0", cover_x=40.0, cover_width=12.0)
    deaths = deaths_of(a_card(health_curve=curve, timeline=(row,)))
    assert (
        '<rect class="hp-cover" id="death-0-e0-cover"\n'
        f'        x="40.0" y="{curve.plot_y0}"\n'
        f'        width="12.0" height="{curve.plot_height}"></rect>'
    ) in deaths


def test_a_recap_row_with_no_cover_window_draws_no_rect_on_the_curve() -> None:
    # A row that is not a press, or whose buff the aura table never recorded,
    # must render no cover element at all -- not an empty or zero-width one.
    deaths = deaths_of(a_card(health_curve=a_curve()))
    assert "hp-cover" not in deaths


def test_a_death_card_with_no_curve_emits_no_svg_at_all() -> None:
    assert "<polyline" not in deaths_of(a_card())


def test_the_recap_table_sits_behind_a_summary_naming_its_size() -> None:
    deaths = deaths_of(a_card(health_curve=a_curve()))
    assert "<details" in deaths and "<summary>2 events</summary>" in deaths


class FakeIcons:
    """Answers for the ids it was given and for no others."""

    def __init__(self, uris: dict[int, str]) -> None:
        self.uris = uris
        self.asked: list[int] = []

    def data_uri(self, ability_id: int) -> str | None:
        self.asked.append(ability_id)
        return self.uris.get(ability_id)


def test_an_icon_is_drawn_beside_the_ability_it_names() -> None:
    card = a_card(timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                                     ability_id=42),))
    html = render(a_report(deaths=(card,)), icons=FakeIcons({42: "data:image/jpeg;base64,AAA"}))
    assert ".i-42 { background-image: url(data:image/jpeg;base64,AAA); }" in html
    assert '<span class="icon i-42" aria-hidden="true"></span>' in html
    assert "Snowdrift" in html


def test_an_ability_with_no_icon_still_shows_its_name_and_emits_no_span() -> None:
    card = a_card(timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                                     ability_id=42),))
    html = render(a_report(deaths=(card,)), icons=FakeIcons({}))
    assert "Snowdrift" in html
    assert 'class="icon' not in html


def test_an_ability_drawn_many_times_is_embedded_once() -> None:
    rows = tuple(
        RecapRow(seconds_before=f"{n}.0 s", kind="hit", ability="Snowdrift", ability_id=42)
        for n in range(9)
    )
    html = render(a_report(deaths=(a_card(timeline=rows),)),
                  icons=FakeIcons({42: "data:image/jpeg;base64,AAA"}))
    assert html.count("background-image") == 1
    assert html.count('class="icon i-42"') == 9


def test_rendering_without_an_icon_source_is_the_page_as_it_was() -> None:
    # All three icon sites carry an id at once, against the same card with
    # every one of those ids left None. Nothing resolves either way -- there
    # is no IconSource at all -- so the two pages must render byte-identical:
    # an id nothing can turn into bytes is exactly as inert as no id.
    with_ids = a_card(
        killing_blow_id=77,
        timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                            ability_id=42),),
        availability=(
            AvailabilityGroup(title="Defensives", rows=(
                AvailabilityRow(ability="Icebound Fortitude", state="ready", ability_id=99),
            )),
        ),
    )
    without_ids = with_ids.model_copy(update={
        "killing_blow_id": None,
        "timeline": (RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                               ability_id=None),),
        "availability": (
            AvailabilityGroup(title="Defensives", rows=(
                AvailabilityRow(ability="Icebound Fortitude", state="ready", ability_id=None),
            )),
        ),
    })
    assert render(a_report(deaths=(with_ids,))) == render(a_report(deaths=(without_ids,)))
    assert "background-image" not in render(a_report(deaths=(with_ids,)))


def test_an_icon_is_drawn_beside_the_killing_blow_in_the_heading() -> None:
    # A distinct id from the recap-row test above: a guard copy-pasted from the
    # wrong site would still read the right id there and pass by accident.
    card = a_card(killing_blow_id=77)
    html = render(a_report(deaths=(card,)), icons=FakeIcons({77: "data:image/jpeg;base64,BBB"}))
    assert '<span class="icon i-77" aria-hidden="true"></span>' in html
    assert "Frigid Roar" in html


def test_an_icon_is_drawn_beside_an_availability_rows_ability() -> None:
    card = a_card(availability=(
        AvailabilityGroup(title="Defensives", rows=(
            AvailabilityRow(ability="Icebound Fortitude", state="ready", ability_id=99),
        )),
    ))
    html = render(a_report(deaths=(card,)), icons=FakeIcons({99: "data:image/jpeg;base64,CCC"}))
    assert '<span class="icon i-99" aria-hidden="true"></span>' in html
    assert "Icebound Fortitude" in html


def a_ledger_row(**changes: object) -> LedgerRow:
    row = LedgerRow(
        finding_id="time.gap.0",
        title="A 41 second gap after pull 7",
        title_before="A 41 second gap after pull 7",
        detail="Travel, not combat.",
        badge=Badge(label="measured", tint="badge-measured"),
    )
    return row.model_copy(update=changes)


def a_player_card(**changes: object) -> PlayerCard:
    card = PlayerCard(
        name="Bríala",
        class_name="Mage",
        spec="Frost",
        colour="class-mage",
        stats_line="182 casts in 31:49 of pulls · 1 death · 7 interrupts",
        spell_and_talent=Section(state=SectionState.PRESENT),
    )
    return card.model_copy(update=changes)


def a_drawn_timeline() -> PlayerTimeline:
    """A timeline with one of everything: a test checking each layer's own `class="..."`
    attribute fails, naming the layer, if a template drops it."""
    return PlayerTimeline(
        section=Section(state=SectionState.PRESENT),
        title=player_timeline_module.TITLE,
        width=680.0,
        height=140.0,
        pulls=(TimelineBlock(label="Pack 0", x=130.0, width=100.0, is_boss=False,
                             kind="band", css_class="pull-band",
                             hover="Pack 0 — ran 1:40"),),
        band_y=28.0,
        damage=DamageTrack(
            baseline_y=76.0,
            label_y=60.0,
            bars=(DamageBar(x=130.0, width=6.0, y=44.0, height=32.0),),
            peak_label="Tallest bar: 120,000 unmitigated damage in 5 seconds.",
        ),
        cooldowns=(CooldownRow(label="Ice Block", ability_id=45438,
                               # 96/140 of the chart's height, and 16/140 of it
                               # for `row_hit_height` below.
                               tooltip=Tooltip(lines=(
                                   TooltipLine(label="Presses", value="1"),
                                   TooltipLine(label="Not judged", value="30%",
                                               tier=Badge(label="inferred",
                                                          tint="badge-inferred")),
                                   TooltipLine(label="On cooldown", value="30%",
                                               tier=Badge(label="inferred",
                                                          tint="badge-inferred")),
                                   TooltipLine(label="Ready and unpressed", value="40%",
                                               tier=Badge(label="inferred",
                                                          tint="badge-inferred")),
                                   TooltipLine(label="Buff up", value="8.0 s (13%)",
                                               tier=Badge(label="derived",
                                                          tint="badge-derived")),
                               )),
                               hit_top=68.6,
                               baseline_y=96.0,
                               label_y=104.0,
                               presses=(Press(x=200.0),),
                               unavailable=(Span(x=200.0, width=90.0),),
                               not_judged=Span(x=130.0, width=90.0)),),
        row_icon_x=130.0,
        row_icon_size=16.0,
        row_hit_height=11.4,
        ticks=((130.0, "0:00"),),
        tick_y1=22.0,
        tick_y2=112.0,
        tick_label_y=128.0,
        label_x=126.0,
        row_height=16.0,
        press_width=4.0,
        state_key=player_timeline_module.STATE_KEY,
        legend="The pale stretch at the start is not judged at all.",
        badge_measured=Badge(label="measured", tint="badge-measured"),
        badge_measured_caption=player_timeline_module.BADGE_MEASURED_CAPTION,
        badge_inferred=Badge(label="inferred", tint="badge-inferred"),
        badge_inferred_caption=player_timeline_module.BADGE_INFERRED_CAPTION,
    )


def test_the_state_key_reaches_the_page_as_a_swatch_per_state() -> None:
    html = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),)))
    body = html.split("</style>")[1]
    assert body.count('<span class="state-swatch ') == len(player_timeline_module.STATE_KEY)
    for key in player_timeline_module.STATE_KEY:
        assert f'<span class="state-swatch {key.css_class}"></span>{key.label}' in body


def test_every_state_the_key_names_is_a_class_the_track_actually_paints() -> None:
    # The key carries a class rather than a colour so it cannot drift from the
    # track. That only holds if the class it carries is one the drawing really
    # paints and one the stylesheet gives the swatch a fill for. Neither can be
    # seen from a view model, so both are read off the files themselves.
    render_dir = Path(__file__).parents[3] / "src" / "wowperf" / "adapters" / "render"
    template = (render_dir / "_player_timeline.html.j2").read_text(encoding="utf-8")
    stylesheet = (render_dir / "report.css.j2").read_text(encoding="utf-8")
    # Stated rather than derived, so an emptied key makes the loop below
    # vacuous and this line fails instead of the whole test passing over it.
    assert len(player_timeline_module.STATE_KEY) == 4
    for key in player_timeline_module.STATE_KEY:
        assert f'<rect class="{key.css_class}"' in template, key.css_class
        assert f".state-swatch.{key.css_class} {{" in stylesheet, key.css_class


def test_every_layer_of_a_players_timeline_reaches_the_page() -> None:
    html = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),)))
    assert 'data-tab-panel="players"' in html
    assert 'class="player-timeline"' in html
    for layer in ("pull-band", "damage-bar", "not-judged", "on-cooldown", "press"):
        assert f'class="{layer}"' in html, layer
    assert "Ice Block" in html
    assert "not judged" in html
    # Which badge grades what is a claim the page makes, so it must be spoken
    # rather than left as two colours side by side: "measured" is captioned
    # to the damage taken bars, the press marks and the cover windows,
    # "inferred" to the dimming and the ready tick that ends it.
    assert "measured</a> — the damage taken bars, the press marks and the cover windows." in html
    assert "inferred</a> — the dimming and the ready tick that ends it." in html


def test_a_timelines_badges_link_to_provenance_like_every_other_badge() -> None:
    # The health curve's badges and every ledger row's are anchors to the
    # provenance section. These were the only badges on the page a reader
    # could not click through.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    assert '<a class="badge badge-measured" href="#provenance">measured</a>' in body
    assert '<a class="badge badge-inferred" href="#provenance">inferred</a>' in body


def test_a_timelines_captions_take_the_same_class_the_other_drawings_captions_do() -> None:
    # `.badges` matched no rule in the stylesheet, so that line rendered at
    # body size while every other caption on the page rendered at 13px.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    assert '<p class="legend"><a class="badge badge-measured"' in body
    assert 'class="badges"' not in body


def test_a_row_label_is_drawn_in_the_gutter_and_on_its_own_rows_middle() -> None:
    # The coordinates come from the domain and the alignment from one rule in
    # the stylesheet: without `text-anchor: end` an x of 126 is where the
    # label *starts*, and it runs rightward over the track it names.
    html = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),)))
    stylesheet, body = html.split("</style>")
    assert '<text class="track-label row-label" x="126.0" y="104.0">Ice Block</text>' in body
    assert '<text class="track-label row-label" x="126.0" y="60.0">Damage taken</text>' in body
    assert "text-anchor: end" in stylesheet.split(".row-label {")[1].split("}")[0]


def test_a_timeline_names_itself_rather_than_claiming_to_be_an_unnamed_image() -> None:
    # `role="img"` with no accessible name gives assistive tech an unnamed
    # image and drops the pull bands' own titles out of the tree with it.
    # Both other drawings on the page open with a <title> and carry no role.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    svg = body[body.index('<svg class="player-timeline"'):body.index("</svg>")]
    # Escaped on comparison: the title embeds an apostrophe, which autoescape
    # turns into "&#39;".
    assert f"<title>{escape(player_timeline_module.TITLE)}</title>" in svg
    assert "role=" not in svg
    assert "<title>Pack 0 — ran 1:40</title>" in svg


def test_a_boss_pulls_column_reaches_column_height_and_only_it_is_named() -> None:
    # The band used to float at a fixed height above the tracks; it now runs the
    # full column height so a press reads as landing inside the pull it happened
    # during. Only the boss pull's name is drawn on the chart -- a run's forty
    # trash names would overlap into a smear -- so the trash pull's index
    # reaches a reader only through its own <title>, never as on-chart text.
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT),
        title=player_timeline_module.TITLE,
        width=680.0,
        height=140.0,
        pulls=(
            TimelineBlock(label="Pull 7", x=130.0, width=50.0, is_boss=False,
                          kind="band", css_class="pull-band",
                          hover="Pull 7 — ran 0:50"),
            TimelineBlock(label="Nalorakk", x=200.0, width=60.0, is_boss=True,
                          kind="band", css_class="pull-band block-boss"),
        ),
        band_y=28.0,
        column_height=84.0,
        pull_label_y=25.0,
    )
    html = render(a_report(players=(a_player_card(timeline=timeline),)))
    body = html.split("</style>")[1]

    # The boss pull's <rect> carries height equal to the timeline's column_height.
    assert (
        '<rect class="pull-band block-boss" x="200.0" y="28.0"\n'
        '        width="60.0" height="84.0">'
    ) in body
    # The boss pull's name is drawn as text at pull_label_y.
    assert '<text class="pull-name" x="200.0" y="25.0">Nalorakk</text>' in body
    # The trash pull's index label reaches the page as a <title> only -- no
    # on-chart <text> is drawn for it.
    assert "<title>Pull 7 — ran 0:50</title>" in body
    assert '<text class="pull-name" x="130.0" y="25.0">Pull 7</text>' not in body


def a_drawn_body() -> str:
    return render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]


# Restates test_a_cooldown_rows_measured_facts_reach_the_page_as_its_groups_title,
# which held that the facts rode on a native <title> wrapping the row. They now
# ride on a strip laid over it, which is a hover target the whole width of the
# row rather than only the parts of it something was painted on.
def test_a_cooldown_rows_facts_reach_the_page_as_the_pages_own_panel() -> None:
    body = a_drawn_body()
    assert '<div class="row-hit" tabindex="0" aria-label="Ice Block"' in body
    assert 'style="top: 68.6%; height: 11.4%"' in body
    assert '<span class="tip-head">Ice Block</span>' in body
    assert '<span class="tip-label">Presses</span><span class="tip-value">1</span>' in body
    # The row still draws what the panel describes: the old test held this of
    # the same <g>, and the rects did not move when the title did.
    group = body[body.index('<rect class="on-cooldown"'):]
    group = group[:group.index("</g>")]
    assert '<rect class="press"' in group
    assert 'class="track-label row-label"' in group


def test_a_cooldown_row_carries_no_native_title_beside_its_panel() -> None:
    # Design section 5.2: one key beneath the chart, one panel on the row. A
    # <title> on the group would win the pointer for about a second and then
    # answer in the operating system's styling, beside the panel that had
    # already appeared.
    body = a_drawn_body()
    svg = body[body.index('<svg class="player-timeline"'):]
    svg = svg[:svg.index("</svg>")]
    assert "<g><title>" not in svg
    assert "1 press, 8.0 s of cover" not in svg


def test_the_strips_are_siblings_of_the_chart_and_never_children_of_it() -> None:
    # A strip inside the <svg> positions against nothing: CSS positioning does
    # not apply to the children of an SVG, so the panel would render at the
    # chart's origin for every row, silently and identically.
    body = a_drawn_body()
    wrap = body[body.index('<div class="timeline-wrap">'):]
    assert wrap.index("</svg>") < wrap.index('<div class="row-hit"')


def test_a_strips_percentage_is_the_one_the_builder_computed() -> None:
    """The other strip tests hand-write `hit_top`, so they would all still pass if
    `build_player_timeline` stamped the wrong number. This one renders a timeline
    the builder actually made, and reads the emitted percentage back against the
    row's own figure -- the only test that joins the two halves on a page."""
    from tests.domain.report.test_build_player_timeline import BURST as A_BURST
    from tests.domain.report.test_build_player_timeline import (
        BURSTS,
        KIT,
        SHIELD,
        a_cast,
        a_timeline,
    )

    timeline = a_timeline(
        LoadedRun(
            run=a_run(pulls=(a_pull(0, 0, 600_000),)),
            casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, A_BURST.ability_id, 120_000)),
        ),
        defensives=KIT,
        throughput=BURSTS,
    )
    body = render(a_report(players=(a_player_card(timeline=timeline),))).split("</style>")[1]

    assert len(timeline.cooldowns) == 2
    for row in timeline.cooldowns:
        emitted = f'aria-label="{row.label}" style="top: {row.hit_top}%; '
        assert emitted in body, emitted
        # The viewBox number must not be what reached the page: a strip placed at
        # `baseline_y` per cent sits nowhere near the row it describes.
        assert f'style="top: {row.baseline_y}%' not in body


def test_a_row_panels_heading_carries_the_abilitys_icon() -> None:
    # The panel can open a long way from the row it describes, and the art is
    # how a reader finds that row again among near-identical grey bars. The
    # `ability()` macro has paired the two since it was written, for the reason
    # its own comment gives: the art and the word are one object to a reader.
    body = render(
        a_report(players=(a_player_card(timeline=a_drawn_timeline()),)),
        icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}),
    ).split("</style>")[1]
    assert ('<span class="tip-head"><span class="icon i-45438" aria-hidden="true"></span>'
            "Ice Block</span>") in body


def test_a_row_panels_heading_is_just_the_name_when_no_icon_resolved() -> None:
    # No empty icon box where nothing resolved: the silent fallback every other
    # missing icon on the page already takes.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    assert '<span class="tip-head">Ice Block</span>' in body
    assert 'class="icon i-None"' not in body


def test_the_chart_keeps_the_aspect_ratio_the_strips_percentages_assume() -> None:
    # The strips are placed at baseline_y over the chart's height. That is only
    # the right place while the rendered height stays width x H/680 -- which a
    # height attribute or a preserveAspectRatio override would end, moving every
    # panel off its row with no test to notice.
    body = a_drawn_body()
    opening = body[body.index('<svg class="player-timeline"'):][:200]
    assert "preserveAspectRatio" not in opening
    assert "height=" not in opening


def test_a_timelines_tick_labels_are_centred_the_way_the_run_timelines_are() -> None:
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    assert '<text class="tick-label" x="130.0" y="128.0" text-anchor="middle">0:00</text>' in body


def test_the_press_marks_width_comes_from_the_domain_not_the_template() -> None:
    # The mark's width decides where its centre falls, so a number written in
    # the template would put the mark and its icon on different instants.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    assert '<rect class="press" x="200.0" y="96.0" width="4.0" height="16.0"/>' in body


def test_a_pressed_abilitys_icon_is_both_embedded_and_drawn_on_the_timeline() -> None:
    html = render(
        a_report(players=(a_player_card(timeline=a_drawn_timeline()),)),
        icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}),
    )
    assert ".i-45438 { background-image: url(data:image/jpeg;base64,AAA); }" in html
    # The rule alone proves the resolver ran, not that anything was drawn: split the
    # stylesheet off and require both the embedded payload and the element that
    # draws it from there, in the body. The coordinate is pinned too -- matching
    # only `'<use href="#icon-45438"'` would stay green even if the template
    # printed the press's own x rather than the row's gutter column.
    body = html.split("</style>")[1]
    assert ('<symbol id="icon-45438" viewBox="0 0 1 1">'
            '<image href="data:image/jpeg;base64,AAA"') in body
    assert '<use href="#icon-45438" x="130.0"' in body


def test_an_icon_that_resolves_is_drawn_clear_of_the_marks_on_the_track() -> None:
    # Was `test_a_press_whose_icon_resolves_still_draws_its_plain_mark_too`,
    # which required the mark to be painted after the icon because the icon
    # sat on the track, opaque and several times wider, and would otherwise
    # cover it. That is the defect itself: painted in that order the icon is
    # what looked cut. The icon is now drawn in the gutter, so the two cannot
    # overlap at all -- and the mark is still drawn whether or not an icon
    # resolved, never replaced by one.
    html = render(
        a_report(players=(a_player_card(timeline=a_drawn_timeline()),)),
        icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}),
    )
    body = html.split("</style>")[1]
    assert '<rect class="press" x="200.0"' in body
    icon = re.search(r'<use href="#icon-45438" x="([\d.]+)"[^>]*width="([\d.]+)"', body)
    assert icon is not None
    assert float(icon.group(1)) + float(icon.group(2)) <= 200.0


def test_a_press_whose_icon_never_resolves_still_draws_its_mark() -> None:
    html = render(
        a_report(players=(a_player_card(timeline=a_drawn_timeline()),)),
        icons=FakeIcons({}),
    )
    assert "background-image" not in html
    body = html.split("</style>")[1]
    assert 'class="press"' in body
    # Stronger than the line above: nothing resolved, so no icon element of
    # any kind -- embedded or drawn -- may appear either.
    assert "<use" not in body


def test_a_cooldowns_ability_is_asked_about_once_no_matter_how_many_presses_it_has() -> None:
    # The id lives on the row, not the press: two presses of the same ability
    # must cost one call, not two, the same guarantee the death-card walk
    # already gives the ids it meets more than once.
    row = CooldownRow(label="Ice Block", ability_id=45438, baseline_y=96.0,
                      presses=(Press(x=200.0), Press(x=210.0)))
    timeline = PlayerTimeline(section=Section(state=SectionState.PRESENT), width=680.0,
                              height=140.0, cooldowns=(row,))
    icons = FakeIcons({})
    render(a_report(players=(a_player_card(timeline=timeline),)), icons=icons)
    assert icons.asked == [45438]


def test_a_row_draws_one_icon_however_many_presses_it_has() -> None:
    # Was `test_two_presses_of_the_same_ability_share_one_copy_of_the_icon`,
    # which pinned that the payload is not copied once per press. The `<use>`
    # was: at ROW_HEIGHT an icon covers about seventeen seconds of a
    # twenty-three minute run, so one real report drew 281 of them across five
    # players and 67 overlapped a neighbour. The payload claim is kept in the
    # first assertion; the second is the one that changed, and the third keeps
    # it from passing because the presses themselves disappeared.
    row = CooldownRow(label="Ice Block", ability_id=45438, baseline_y=96.0,
                      presses=(Press(x=200.0), Press(x=210.0)))
    timeline = PlayerTimeline(section=Section(state=SectionState.PRESENT), width=680.0,
                              height=140.0, cooldowns=(row,), row_icon_x=126.0,
                              row_icon_size=16.0)
    html = render(a_report(players=(a_player_card(timeline=timeline),)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    body = html.split("</style>")[1]
    assert body.count("data:image/jpeg;base64,AAA") == 1
    assert body.count('<use href="#icon-45438"') == 1
    assert body.count('<rect class="press"') == 2


def test_a_press_on_a_row_with_no_ability_id_asks_nothing_and_draws_plain() -> None:
    # `CooldownRow.ability_id` is `int | None`. `None in {}` and `None in
    # {45438: ...}` are both `False`, but only the second dict can tell the
    # template's real guard apart from one that would happen to pass no matter
    # what it tested -- and a player with one identified row beside one
    # unidentified one is the case that actually occurs, so `icons_by_id` is
    # given a resolving id here rather than left empty.
    unidentified = CooldownRow(label="Unknown", ability_id=None, baseline_y=96.0,
                               presses=(Press(x=200.0),))
    identified = CooldownRow(label="Ice Block", ability_id=45438, baseline_y=112.0,
                             presses=(Press(x=210.0),))
    timeline = PlayerTimeline(section=Section(state=SectionState.PRESENT), width=680.0,
                              height=140.0, cooldowns=(unidentified, identified))
    icons = FakeIcons({45438: "data:image/jpeg;base64,AAA"})
    html = render(a_report(players=(a_player_card(timeline=timeline),)), icons=icons)
    assert icons.asked == [45438]
    body = html.split("</style>")[1]
    assert body.count('<rect class="press"') == 2
    assert '<use href="#icon-45438"' in body


def test_two_players_pressing_the_same_ability_share_one_copy_of_the_icon() -> None:
    # The prior test proves one row's own presses share one copy inside one
    # player's own <svg>. This is the shape the ruling actually worried about:
    # two different players, each with their own player-timeline <svg>,
    # pressing the same ability. A per-player <defs> would duplicate the id
    # (invalid HTML) and, the day `timeline.row_height` stops being one shared
    # module constant, silently draw the first player's own geometry under the
    # second player's <use>. A document-level <symbol> makes both structurally
    # impossible: there is exactly one element bearing this id anywhere on the
    # page, and both players' presses resolve against it.
    row = CooldownRow(label="Ice Block", ability_id=45438, baseline_y=96.0,
                      presses=(Press(x=200.0),))
    timeline = PlayerTimeline(section=Section(state=SectionState.PRESENT), width=680.0,
                              height=140.0, cooldowns=(row,))
    html = render(
        a_report(players=(
            a_player_card(name="Bríala", slug="briala-1", timeline=timeline),
            a_player_card(name="Stonewake", slug="stonewake-2", timeline=timeline),
        )),
        icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}),
    )
    body = html.split("</style>")[1]
    assert body.count("data:image/jpeg;base64,AAA") == 1
    assert body.count('id="icon-45438"') == 1
    assert body.count('<use href="#icon-45438"') == 2


def test_a_withheld_timeline_says_why_instead_of_drawing_an_empty_axis() -> None:
    # The reason is the domain's own withheld string, not one invented for this
    # test: proving the template prints whatever reason it is given is the
    # point, and a hand-rolled sentence the domain never produces would prove
    # nothing about that. Escaped on comparison: the reason embeds an
    # apostrophe that autoescape turns into "&#39;".
    withheld = PlayerTimeline(
        section=Section(state=SectionState.WITHHELD,
                        reason=player_timeline_module.NO_PULLS_RECORDED),
    )
    html = render(a_report(players=(a_player_card(timeline=withheld),)))
    assert str(escape(player_timeline_module.NO_PULLS_RECORDED)) in html
    assert 'class="player-timeline"' not in html


def test_a_cooldown_that_outlasts_the_run_still_shows_its_dashed_border() -> None:
    # design section 6: when an ability's own cooldown exceeds the run, the
    # not-judged stretch and the press's unavailable span cover the exact same
    # rectangle. Painted in the wrong order the dashed border would sit under
    # the filled span and vanish; this proves it paints on top instead.
    row = CooldownRow(
        label="Ice Block", ability_id=45438, baseline_y=96.0,
        presses=(Press(x=46.0),),
        unavailable=(Span(x=46.0, width=600.0),),
        not_judged=Span(x=46.0, width=600.0),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        cooldowns=(row,),
    )
    html = render(a_report(players=(a_player_card(timeline=timeline),)))
    on_cooldown_at = html.index('class="on-cooldown"')
    not_judged_at = html.index('class="not-judged"')
    assert on_cooldown_at < not_judged_at


def test_a_cooldown_row_with_a_ready_tick_draws_the_open_mark() -> None:
    # The full opening tag is pinned, not just the class name: the tick's own
    # x and the row's baseline_y both have to reach the page, the same way a
    # press's own coordinates do.
    row = CooldownRow(
        label="Ice Block", ability_id=45438, baseline_y=96.0,
        presses=(Press(x=46.0),),
        unavailable=(Span(x=46.0, width=90.0),),
        ready_ticks=(136.0,),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        row_height=16.0, press_width=4.0, cooldowns=(row,),
    )
    body = render(a_report(players=(a_player_card(timeline=timeline),)))
    assert (
        '<rect class="ready-again" x="136.0" y="96.0"\n'
        '        width="4.0" height="16.0"/>'
    ) in body


def test_a_cooldown_row_with_a_cover_window_draws_it_at_true_scale() -> None:
    # The full opening tag is pinned, not just the class name: the span's own x
    # and width, and the row's baseline_y, all have to reach the page -- the
    # same proof every other mark on this row already carries. The width here
    # (1.4) is deliberately narrower than MIN_BLOCK_WIDTH (2.0): the builder
    # never floors a cover window, so the template must not either.
    row = CooldownRow(
        label="Ice Block", ability_id=45438, baseline_y=96.0,
        presses=(Press(x=46.0),),
        unavailable=(Span(x=46.0, width=90.0),),
        cover=(Span(x=46.0, width=1.4),),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        row_height=16.0, press_width=4.0, cooldowns=(row,),
    )
    body = render(a_report(players=(a_player_card(timeline=timeline),)))
    assert (
        '<rect class="cover" x="46.0" y="96.0"\n'
        '        width="1.4" height="16.0"/>'
    ) in body


def test_a_cooldown_row_with_no_cover_window_draws_no_cover_rect() -> None:
    # The half that catches an unconditional element: a row with a press but
    # no cover window -- an ability whose buff the aura table never recorded,
    # or a player with no aura table fetched at all -- must not render a
    # "cover" element anywhere. Scoped to the body: the stylesheet always
    # defines ".cover", so checking the whole page would pass even if the
    # template drew the element unconditionally.
    row = CooldownRow(
        label="Ice Block", ability_id=45438, baseline_y=96.0,
        presses=(Press(x=46.0),),
        unavailable=(Span(x=46.0, width=90.0),),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        row_height=16.0, press_width=4.0, cooldowns=(row,),
    )
    body = render(a_report(players=(a_player_card(timeline=timeline),))).split(
        "</style>"
    )[1]
    assert 'class="cover"' not in body


def test_a_cooldown_row_with_no_ready_ticks_draws_no_ready_again_mark() -> None:
    # The half that catches an unconditional element: a row with a press but
    # no ready tick -- the ordinary case for a cooldown still running when the
    # run ends -- must not render a "ready-again" element anywhere at all.
    row = CooldownRow(
        label="Ice Block", ability_id=45438, baseline_y=96.0,
        presses=(Press(x=46.0),),
        unavailable=(Span(x=46.0, width=600.0),),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        row_height=16.0, press_width=4.0, cooldowns=(row,),
    )
    # Scoped to the body: the stylesheet always defines ".ready-again", so
    # checking the whole page would pass even if the template drew the
    # element unconditionally.
    body = render(a_report(players=(a_player_card(timeline=timeline),))).split(
        "</style>"
    )[1]
    assert "ready-again" not in body


def test_the_damage_row_draws_its_own_axis_line() -> None:
    # The full opening tag is pinned: the line has to start at the track's own
    # origin -- the same one the bars sit on -- and not at label_x, which is
    # the label gutter every other track element leaves a LABEL_GAP clear of.
    # And it must end at the track's own end (F9), not at the viewBox's width,
    # which runs past TRACK_X1 into a margin nothing else on this chart uses.
    damage = DamageTrack(
        baseline_y=76.0, label_y=60.0,
        bars=(DamageBar(x=130.0, width=6.0, y=44.0, height=32.0),),
        peak_label="Tallest bar: 120,000 unmitigated damage in 5 seconds.",
        axis_top_y=44.0,
        axis_x0=130.0,
        axis_x1=timeline_module.TRACK_X1,
        axis_top_label="120,000",
        bucket_caption=(
            "Each bar is a 5-second bucket, and the axis runs from nothing to this "
            "player's own tallest, never the group's."
        ),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        label_x=126.0, damage=damage,
    )
    body = render(a_report(players=(a_player_card(timeline=timeline),)))
    assert (
        '<line class="damage-axis" x1="130.0" y1="44.0"\n'
        f'        x2="{timeline_module.TRACK_X1}" y2="44.0"/>'
    ) in body


def test_the_damage_rows_axis_label_and_bucket_caption_reach_the_page() -> None:
    damage = DamageTrack(
        baseline_y=76.0, label_y=60.0,
        bars=(DamageBar(x=130.0, width=6.0, y=44.0, height=32.0),),
        peak_label="Tallest bar: 120,000 unmitigated damage in 5 seconds.",
        axis_top_y=44.0,
        axis_x0=130.0,
        axis_top_label="120,000",
        bucket_caption=(
            "Each bar is a 5-second bucket, and the axis runs from nothing to this "
            "player's own tallest, never the group's."
        ),
    )
    timeline = PlayerTimeline(
        section=Section(state=SectionState.PRESENT), width=680.0, height=140.0,
        label_x=126.0, damage=damage,
    )
    html = render(a_report(players=(a_player_card(timeline=timeline),)))
    assert "120,000" in html
    # Escaped on comparison: the caption embeds two apostrophes, which
    # autoescape turns into "&#39;".
    assert str(escape(damage.bucket_caption)) in html


def test_an_icon_is_drawn_at_the_ability_inside_a_findings_sentence() -> None:
    # The death card's killing blow forces id 45438 into `icons_by_id` through
    # the path that already resolves it, so this test populates `icons_by_id`
    # independently of `report.interrupts` and isolates what this macro owns:
    # drawing the span wherever `row.ability_id` happens to match an id
    # already resolved, rather than the resolver's own coverage.
    row = a_ledger_row(
        title="Emberkin never cast Ice Block",
        title_before="Emberkin never cast ",
        title_ability="Ice Block",
        ability_id=45438,
    )
    html = render(a_report(interrupts=(row,), deaths=(a_card(killing_blow_id=45438),)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    expected = (
        'Emberkin never cast <span class="ability">'
        '<span class="icon i-45438" aria-hidden="true"></span>'
        '<span class="ability-name">Ice Block</span></span>'
    )
    assert expected in html


def test_a_finding_whose_ability_has_no_icon_still_reads_as_a_sentence() -> None:
    row = a_ledger_row(
        title="Emberkin never cast Ice Block",
        title_before="Emberkin never cast ",
        title_ability="Ice Block",
        ability_id=45438,
    )
    html = render(a_report(interrupts=(row,)), icons=FakeIcons({}))
    expected = (
        'Emberkin never cast <span class="ability">'
        '<span class="ability-name">Ice Block</span></span>'
    )
    assert expected in html
    assert 'class="icon' not in html


def test_a_summary_pointer_names_the_finding_without_an_icon() -> None:
    # A pointer is a one-line cross-reference into another section; the icon
    # belongs at the finding itself, not at every mention of it. The death
    # card's killing blow forces id 45438 into `icons_by_id` through the path
    # that already resolves it, so the assertion below proves the `pointer`
    # macro withholds the span even though the id is genuinely resolved --
    # not merely because nothing resolved at all.
    row = a_ledger_row(
        title="Emberkin never cast Ice Block",
        title_before="Emberkin never cast ",
        title_ability="Ice Block",
        ability_id=45438,
    )
    html = render(a_report(summary_pointers=(row,), deaths=(a_card(killing_blow_id=45438),)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    assert "pointer-title" in html
    assert 'class="icon i-45438"' not in html.split('class="pointer-title"')[1][:200]


def test_an_id_that_never_resolves_is_still_asked_about_only_once() -> None:
    # `resolved` only gains an entry once `data_uri` returns a URI, so a naive
    # dedup keyed on that dict would ask again about an id that resolves to
    # None every time it recurs -- on a card with 181 rows, every later one.
    # Two cards naming the same never-resolving ability prove the guard
    # remembers the id itself, not just the ones that produced a URI.
    card_a = a_card(killing_blow_id=5)
    card_b = a_card(killing_blow_id=5)
    icons = FakeIcons({})
    render(a_report(deaths=(card_a, card_b)), icons=icons)
    assert icons.asked == [5]


def test_an_ability_named_only_by_a_finding_is_embedded() -> None:
    row = a_ledger_row(title="Emberkin never cast Ice Block",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Block", ability_id=45438)
    icons = FakeIcons({45438: "data:image/jpeg;base64,AAA"})
    html = render(a_report(interrupts=(row,)), icons=icons)
    assert ".i-45438 { background-image: url(data:image/jpeg;base64,AAA); }" in html


def test_an_ability_named_only_inside_a_player_card_is_embedded() -> None:
    # spell_and_talent_rows is nested one level down, which is where the
    # comparison findings land.
    row = a_ledger_row(title="Emberkin never cast Ice Nova",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Nova", ability_id=157997)
    card = a_player_card().model_copy(update={"spell_and_talent_rows": (row,)})
    html = render(a_report(players=(card,)),
                  icons=FakeIcons({157997: "data:image/jpeg;base64,BBB"}))
    assert ".i-157997 { background-image: url(data:image/jpeg;base64,BBB); }" in html


# `ledger_row` is imported `with context` in five templates, because it reads
# `icons_by_id` off the caller's own template context rather than an argument:
# without that import, `row.ability_id in icons_by_id` silently evaluates false
# inside the macro instead of raising, and no span draws anywhere on that tab.
# `test_an_icon_is_drawn_at_the_ability_inside_a_findings_sentence` above is
# the only test proving a span (not merely the CSS rule `_icon_uris` emits in
# Python, which needs no template at all) is actually drawn for a finding row,
# and it only exercises `_interrupts.html.j2`. The four tests below do the same
# proof for the other four templates that import the macro `with context`.


def test_an_icon_is_drawn_at_the_ability_a_death_row_names() -> None:
    row = a_ledger_row(title="Emberkin never cast Ice Block",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Block", ability_id=45438)
    html = render(a_report(death_rows=(row,)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    expected = (
        'Emberkin never cast <span class="ability">'
        '<span class="icon i-45438" aria-hidden="true"></span>'
        '<span class="ability-name">Ice Block</span></span>'
    )
    assert expected in html


def test_an_icon_is_drawn_at_the_ability_a_group_row_names() -> None:
    row = a_ledger_row(title="Emberkin never cast Ice Block",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Block", ability_id=45438)
    html = render(a_report(group_rows=(row,)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    expected = (
        'Emberkin never cast <span class="ability">'
        '<span class="icon i-45438" aria-hidden="true"></span>'
        '<span class="ability-name">Ice Block</span></span>'
    )
    assert expected in html


def test_an_icon_is_drawn_at_the_ability_a_route_row_names() -> None:
    row = a_ledger_row(title="Emberkin never cast Ice Block",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Block", ability_id=45438)
    html = render(a_report(route_rows=(row,)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    expected = (
        'Emberkin never cast <span class="ability">'
        '<span class="icon i-45438" aria-hidden="true"></span>'
        '<span class="ability-name">Ice Block</span></span>'
    )
    assert expected in html


def test_an_icon_is_drawn_at_the_ability_a_summary_ledger_row_names() -> None:
    row = a_ledger_row(title="Emberkin never cast Ice Block",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Block", ability_id=45438)
    html = render(a_report(ledger_decomposition=(row,)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    expected = (
        'Emberkin never cast <span class="ability">'
        '<span class="icon i-45438" aria-hidden="true"></span>'
        '<span class="ability-name">Ice Block</span></span>'
    )
    assert expected in html


def test_a_findings_ability_icon_survives_finding_through_build_report_to_render() -> None:
    """No other test takes a `Finding` all the way through `ledger_row` ->
    `build_report` -> `render`: the view-model tests in `test_ledger.py` stop at
    `LedgerRow`, and every render test above starts from a hand-written
    `LedgerRow`, with a hand-typed seam between the two halves. This is the one
    test that walks the whole path: a `Finding` naming an ability in, its icon
    span in the rendered HTML out."""
    finding = a_finding(
        "interrupts.missed.0", title="Emberkin missed an Ice Block interrupt"
    ).model_copy(update={"ability_id": 45438, "ability_name": "Ice Block"})
    report = build_report(a_loaded(), (finding,), None, None, SUBJECT, None, FETCHED,
                           NO_DEFENSIVES, NO_CONSUMABLES)

    html = render(report, icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))

    assert '<span class="icon i-45438" aria-hidden="true"></span>' in html


def test_ledger_rows_render_inside_a_findings_wrapper() -> None:
    # The CSS grid for dense content applies to .findings containers.
    # Without them, the grid rule selects nothing and content does not flow
    # into columns. This test verifies the wrappers actually render and contain cards.
    finding = a_finding("time.residual", title="Time outside pulls")
    report = build_report(a_loaded(), (finding,), None, None, SUBJECT, None, FETCHED,
                          NO_DEFENSIVES, NO_CONSUMABLES)
    html = render(report)

    # Assert that a wrapper opening tag is immediately followed by a card opening tag,
    # proving adjacency and containment. The wrapper's first child is a card.
    assert '<div class="findings">\n<div class="card"' in html, \
        "Findings wrapper must immediately contain a card"


def test_an_icon_and_its_ability_name_render_as_one_element() -> None:
    # Two adjacent spans read as two things. A reader scanning a recap table
    # for "which ability was that" should meet one object with one hover
    # target, which is also what a tooltip later attaches to.
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", killing_blow_id=7)
    html = render(a_report(deaths=(card,)), icons=FakeIcons({7: "data:image/jpeg;base64,AAA"}))
    assert '<span class="ability">' in html
    assert '<span class="ability-name">Frigid Roar</span>' in html


def test_an_unresolved_icon_still_renders_the_ability_as_one_element() -> None:
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", killing_blow_id=7)
    html = render(a_report(deaths=(card,)), icons=FakeIcons({}))
    assert '<span class="ability">' in html
    assert '<span class="ability-name">Frigid Roar</span>' in html
    assert 'class="icon i-7"' not in html


def test_an_ability_with_a_tooltip_is_a_focusable_span() -> None:
    # Spec 4.6: the icon and name become "a single hoverable, focusable unit".
    # A bare <span> takes no keyboard focus at all, so the tooltip's
    # `:focus-within` half can only ever fire once the span carries a tabindex.
    tooltip = Tooltip(lines=(TooltipLine(label="Struck for", value="1"),))
    card = DeathCard(
        player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
        killing_blow="Frigid Roar",
        timeline=(RecapRow(seconds_before="5.0 s", kind="hit", ability="Snowdrift",
                           tooltip=tooltip),),
    )
    html = render(a_report(deaths=(card,)))
    assert '<span class="ability" tabindex="0">' in html


def test_an_ability_with_no_tooltip_is_not_a_tab_stop() -> None:
    # The real report embeds dozens of ability icons. Making every one of them
    # a tab stop would wreck keyboard navigation through the page to buy
    # nothing: an ability with no tooltip has no panel for focus to reveal.
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar")
    html = render(a_report(deaths=(card,)))
    assert '<span class="ability">' in html
    assert 'class="ability" tabindex' not in html


def _li(html: str, state: str) -> str:
    """The one `<li>` of this state, isolated from the rest of the page.

    Task 8 already put `class="tip"` on the page for death-event tooltips, so a
    bare substring check for it proves nothing about the availability rows this
    task adds it to -- the check has to be scoped to this one list item.
    """
    start = html.index(f'<li class="{state}">')
    return html[start:html.index("</li>", start)]


def test_an_availability_row_with_a_tooltip_renders_it_inside_the_row() -> None:
    tooltip = Tooltip(
        lines=(TooltipLine(label="Base cooldown", value="120 s"),),
        note="suggestive, not attributable",
    )
    card = a_card(availability=(
        AvailabilityGroup(title="Defensives", rows=(
            AvailabilityRow(ability="Icebound Fortitude", state="ready", tooltip=tooltip),
        )),
    ))
    row = _li(render(a_report(deaths=(card,))), "ready")
    assert 'class="tip"' in row
    assert "Base cooldown" in row and "120 s" in row
    assert "suggestive, not attributable" in row


def test_an_availability_row_with_no_tooltip_renders_no_tooltip_element() -> None:
    card = a_card(availability=(
        AvailabilityGroup(title="Defensives", rows=(
            AvailabilityRow(ability="Icebound Fortitude", state="ready"),
        )),
    ))
    row = _li(render(a_report(deaths=(card,))), "ready")
    assert 'class="tip"' not in row


def test_a_tooltip_line_with_a_tier_renders_a_badge_beside_its_label() -> None:
    # F2/spec 4.5: a tooltip that mixes measured, derived and inferred figures
    # has to mark which is which, the same discipline the rest of the page
    # already carries. Styled like the page's other badges but a <span>, not
    # a link -- a tooltip line is not a finding with its own row in
    # Provenance for it to point to.
    tooltip = Tooltip(
        lines=(TooltipLine(label="Base cooldown", value="120 s",
                           tier=Badge(label="inferred", tint="badge-inferred")),),
    )
    card = a_card(availability=(
        AvailabilityGroup(title="Defensives", rows=(
            AvailabilityRow(ability="Icebound Fortitude", state="ready", tooltip=tooltip),
        )),
    ))
    row = _li(render(a_report(deaths=(card,))), "ready")
    assert '<span class="badge badge-inferred">inferred</span>' in row
    assert '<a class="badge badge-inferred"' not in row


def test_a_tooltip_line_with_no_tier_renders_no_badge() -> None:
    tooltip = Tooltip(lines=(TooltipLine(label="Presses", value="1"),))
    card = a_card(availability=(
        AvailabilityGroup(title="Defensives", rows=(
            AvailabilityRow(ability="Icebound Fortitude", state="ready", tooltip=tooltip),
        )),
    ))
    row = _li(render(a_report(deaths=(card,))), "ready")
    assert "badge" not in row


def test_a_panel_can_carry_a_heading_for_a_surface_that_is_not_its_own_label() -> None:
    # A ledger card's panel hangs off the ability's name, so it needs no
    # heading. A timeline row's panel is laid over a drawing and can open a
    # long way from the label it belongs to, so it names its subject itself.
    from wowperf.adapters.render.html import _environment

    macros = _environment().get_template("_macros.html.j2").module
    panel = str(macros.tip(  # type: ignore[attr-defined]
        Tooltip(lines=(TooltipLine(label="Presses", value="4"),)), "Ice Block"
    ))
    assert '<span class="tip-head">Ice Block</span>' in panel
    assert '<span class="tip-label">Presses</span><span class="tip-value">4</span>' in panel


def test_a_ledger_cards_panel_still_names_nothing_above_its_figures() -> None:
    # The other half of the refactor: `ability()` passes no heading, so the
    # ledger's panels must render exactly as they did. The golden file is the
    # byte-level check; this states the rule in one place a reader will find.
    # Read past the stylesheet: `.tip-head`'s own rule is in it, and a check
    # over the whole document would answer about the CSS and never the markup.
    row = a_row(
        "defensives.ceiling.stonewake.48792",
        title_before="Stonewake used ",
        title_ability="Icebound Fortitude",
        title_after=" 2 of a possible 9 times",
        ability_id=48792,
        tooltip=Tooltip(lines=(TooltipLine(label="Presses", value="2"),)),
    )
    body = render(a_report(ledger_decomposition=(row,))).split("</style>")[1]
    assert '<span class="tip" role="note"><span class="tip-line">' in body
    assert "tip-head" not in body
