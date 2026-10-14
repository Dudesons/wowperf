# ABOUTME: Whole-page rules for the character report: four panels, one script, scoped links.
# ABOUTME: A run report beside the page is the one new link kind, and nothing else new is admitted.

import re

from markupsafe import escape

from tests.adapters.render.test_html_invariants import FORBIDDEN_IN_SCRIPT, ICON_HOST
from tests.domain.character.builders import a_finding, a_run, a_tempo
from tests.domain.report.test_character_build import a_report
from wowperf.adapters.render.html import render_character
from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.character.patterns import (
    CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE,
    DIRECTIONS_WITHHELD_ID,
)
from wowperf.domain.comparison.tempo import DURATION_WITHHELD_REASON
from wowperf.domain.findings import Confidence
from wowperf.domain.report.character_build import SELECTION_QUERIES

CHARACTER_PANEL_ORDER = ["tab-summary", "tab-group", "tab-runs", "tab-provenance"]
PANEL_ID = re.compile(r'<section class="panel"[^>]*\sid="([^"]+)"')
MAIN_NAV = re.compile(r'<nav class="tabs" data-tab-group="main"[^>]*>(.*?)</nav>', re.DOTALL)
TAB_TARGET = re.compile(r'data-tab-for="([^"]+)"')
RUN_FILE = re.compile(r"^[A-Za-z0-9]+-\d+\.html$")
ICON_ABILITY_ID = 433895
ICON_FILENAME = "spell_deathknight_bloodboil.jpg"
WITHHELD_TITLE = "Consistent directions are not stated: 2 runs loaded, 6 are needed"

FINDINGS = (
    # Its title names its ability exactly once, so `ledger_row` cuts it there and
    # hands the row an `ability_id`: the one row on this page an icon can resolve for.
    a_finding("character.direction.boss.433895", slug="", ability_id=ICON_ABILITY_ID,
              ability_name="Blood Boil",
              title="Top parses cast Blood Boil more often than you on bosses"),
    a_finding("character.repeat.compare.talents", slug="", title="Repeat title"),
    a_finding(DIRECTIONS_WITHHELD_ID, slug="", title=WITHHELD_TITLE,
              confidence=Confidence.MEASURED),
)


def a_page(icons: CdnIcons | None = None) -> str:
    return render_character(a_report(findings=FINDINGS), icons)


def panel(html: str, panel_id: str) -> str:
    """One panel's markup: from its own tag to the next panel's, or to the page's end."""
    return html.split(f'id="{panel_id}"', 1)[1].split('<section class="panel"', 1)[0]


def test_every_panel_appears_once_in_tab_order() -> None:
    html = a_page()
    assert PANEL_ID.findall(html) == CHARACTER_PANEL_ORDER
    assert html.count('<section class="panel"') == len(CHARACTER_PANEL_ORDER)


def test_the_tab_buttons_follow_panel_order() -> None:
    nav = MAIN_NAV.search(a_page())
    assert nav is not None
    assert TAB_TARGET.findall(nav.group(1)) == CHARACTER_PANEL_ORDER


def test_every_panel_has_exactly_one_tab_button() -> None:
    """Both directions: a panel with no button is unreachable, and a button naming
    a panel that does not exist is a click that does nothing."""
    html = a_page()
    for name in CHARACTER_PANEL_ORDER:
        assert html.count(f'data-tab-for="{name}"') == 1, name
    nav = MAIN_NAV.search(html)
    assert nav is not None
    assert set(TAB_TARGET.findall(nav.group(1))) == set(PANEL_ID.findall(html))


def test_the_root_class_the_script_adds_is_not_in_the_markup() -> None:
    # The script adds it at run time; rendering it would hide panels with no script.
    html = a_page()
    assert '<html lang="en">' in html
    assert 'class="js' not in html


def test_the_page_hides_nothing_before_the_script_runs() -> None:
    # Every hiding rule is scoped under the root class the script adds, except
    # `.tabs`, which the script un-hides, and `.tip`, which CSS alone reveals.
    html = a_page(CdnIcons({ICON_ABILITY_ID: ICON_FILENAME}))
    assert not re.search(r"<[^>]*\shidden[\s>=]", html)
    assert not re.search(r'style="[^"]*display', html)
    style = html[html.index("<style>"):html.index("</style>")]
    for rule in re.finditer(r"([^{}]+)\{[^{}]*display:\s*none", style):
        selector = rule.group(1).strip().splitlines()[-1].strip()
        assert selector.startswith(".js ") or selector in (".tabs", ".tip"), selector


def test_no_element_id_appears_twice() -> None:
    # A duplicate id is invalid HTML and sends a badge's link to whichever copy
    # the browser picks; rendered with an icon so the symbol ids are counted too.
    html = a_page(CdnIcons({ICON_ABILITY_ID: ICON_FILENAME}))
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicates == set()


def test_the_page_makes_no_request_but_its_icons() -> None:
    html = a_page(CdnIcons({ICON_ABILITY_ID: ICON_FILENAME}))
    assert "<link" not in html.lower()
    assert "@import" not in html.lower()
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.S | re.I)
    assert len(scripts) == 1
    attributes, body = scripts[0]
    assert "src=" not in attributes.lower()
    for forbidden in FORBIDDEN_IN_SCRIPT:
        assert forbidden not in body, forbidden
    # Vacuous today -- icons arrive through a CSS url() and an SVG <image href>,
    # never `src=` -- and kept as the standing check against a template that
    # starts loading anything through `src=` from anywhere but the icon host.
    for src in re.findall(r'src="([^"]*)"', html, flags=re.I):
        assert src.startswith(ICON_HOST), src
    drawn = re.findall(r"url\(([^)]*)\)", html)
    assert drawn, "the fixture resolved no icon, so the address rule was never exercised"
    for address in drawn:
        assert address.startswith(ICON_HOST), address
    assert f"url({ICON_HOST}{ICON_FILENAME})" in html
    assert "data:image" not in html


def test_every_finding_appears_exactly_once() -> None:
    ids = re.findall(r'id="finding-([^"]+)"', a_page())
    for finding_id in ("character.direction.boss.433895", "character.repeat.compare.talents",
                       "character.direction.withheld"):
        assert ids.count(finding_id) == 1, finding_id


def test_every_href_is_a_fragment_the_icon_host_or_a_run_report_beside_the_page() -> None:
    html = a_page(CdnIcons({ICON_ABILITY_ID: ICON_FILENAME}))
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(RUN_FILE.match(href) for href in hrefs), "no run report was linked"
    assert any(href.startswith(ICON_HOST) for href in hrefs), (
        "the fixture resolved no icon href, so the icon-host leg was never exercised"
    )
    for href in hrefs:
        assert href.startswith("#") or href.startswith(ICON_HOST) or RUN_FILE.match(href), href


def test_an_icon_is_drawn_beside_the_ability_its_row_names() -> None:
    html = a_page(CdnIcons({ICON_ABILITY_ID: ICON_FILENAME}))
    assert f'<span class="icon i-{ICON_ABILITY_ID}"' in panel(html, "tab-summary")


def test_without_an_icon_source_the_ability_is_named_and_no_art_is_drawn() -> None:
    html = a_page()
    assert "Blood Boil" in panel(html, "tab-summary")
    assert ICON_HOST not in html


def test_the_page_links_no_report_on_warcraft_logs() -> None:
    assert "warcraftlogs.com/reports/" not in a_page()


def test_the_narrative_and_the_warning_are_on_the_page() -> None:
    html = a_page()
    assert "Your losses are route, not rotation." in html
    assert str(escape(CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE)) in html
    assert "counted, never summed" in html


def directions_section(html: str) -> str:
    """The Summary's directions: from their heading to the repeats' heading."""
    return html.split('<h2 id="directions">', 1)[1].split('<h2 id="repeats">', 1)[0]


def test_withheld_directions_are_stated_under_the_directions_heading() -> None:
    """Withheld, nothing was tested: the empty state would claim a test that found nothing."""
    html = render_character(a_report(findings=(FINDINGS[2], FINDINGS[1])))
    section = directions_section(html)
    assert f'id="finding-{DIRECTIONS_WITHHELD_ID}"' in section
    assert "No measure sat" not in section


def test_directions_tested_and_none_held_say_so() -> None:
    html = render_character(a_report(findings=(FINDINGS[1],)))
    assert "No measure sat on the same side of the top parses in every run." in (
        directions_section(html)
    )


def test_a_page_with_no_narrative_draws_no_narrative_heading() -> None:
    html = render_character(a_report(findings=FINDINGS, narrative=None))
    assert 'id="narrative"' not in html


def test_a_title_containing_markup_is_escaped() -> None:
    report = a_report(findings=[a_finding("character.repeat.compare.talents", slug="",
                                          title="<b>bold</b>")])
    html = render_character(report)
    assert "<b>bold</b>" not in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_every_run_links_its_own_report_on_the_runs_and_group_tabs() -> None:
    html = a_page()
    for panel_id in ("tab-group", "tab-runs"):
        hrefs = re.findall(r'href="([^"]*)"', panel(html, panel_id))
        assert hrefs == ["code000x-1.html", "code001x-2.html"], panel_id


def test_a_withheld_completion_time_says_why_beside_its_cell() -> None:
    report = a_report(findings=FINDINGS, runs=[a_run(0, tempo=a_tempo(their_time=None))])
    group = panel(render_character(report), "tab-group")
    cell = re.search(r"<td>1800s; not compared(.*?)</td>", group, re.S)
    assert cell is not None
    assert str(escape(DURATION_WITHHELD_REASON)) in cell.group(1)


def test_a_compared_completion_time_carries_no_note() -> None:
    group = panel(a_page(), "tab-group")
    assert "<td>1800s against 1700s</td>" in group
    assert str(escape(DURATION_WITHHELD_REASON)) not in group


def test_the_group_counts_sit_under_their_columns() -> None:
    group = panel(a_page(), "tab-group")
    footer = re.search(r"<tfoot>(.*?)</tfoot>", group, re.S)
    assert footer is not None
    header = re.search(r"<thead>(.*?)</thead>", group, re.S)
    assert header is not None
    data_columns = re.findall(r"<th>(.*?)</th>", header.group(1))[1:]
    counts = re.findall(r"<td>(.*?)</td>", footer.group(1))
    assert len(counts) == len(data_columns)
    assert counts == list(a_report().group_counts)


def test_the_group_tab_introduction_is_true_of_every_column() -> None:
    """Not every cell sets ours against a median: the run's own label and your
    deaths compare with nothing, and a run short of fast runs has no median."""
    intro = re.search(r'<h2 id="group">.*?</h2>\s*<p class="sub">(.*?)</p>',
                      panel(a_page(), "tab-group"), re.S)
    assert intro is not None
    text = intro.group(1).replace("&#39;", "'")
    assert "Each cell is ours" not in text
    assert "too few fast runs" in text
    assert "your own deaths" in text


def test_the_runs_tab_lists_the_runs_then_the_dungeons_left_out_then_the_failures() -> None:
    """Design section 6: every run, then the dungeons left out, then the runs that failed."""
    runs = panel(a_page(), "tab-runs")
    left_out = runs.index("Murder Row: no ranked run as Blood")
    failed = runs.index("Kings&#39; Rest +18 (report zzz999, fight 3)")
    assert runs.index("code001x-2.html") < left_out < failed


def test_the_provenance_names_the_selection_queries_and_points_at_each_runs_own() -> None:
    provenance = panel(a_page(), "tab-provenance")
    for name in SELECTION_QUERIES:
        assert name in provenance, name
    text = provenance.replace("&#39;", "'")
    assert "Each run's own report" in text
    # A run's Provenance lists every candidate, the unused ones marked so.
    assert "the reference runs it considered, and which it used" in text
    assert "compared against" not in text


def test_the_provenance_lists_what_was_withheld() -> None:
    provenance = panel(a_page(), "tab-provenance")
    assert f'<p class="withheld">{WITHHELD_TITLE}</p>' in provenance


def test_a_page_that_withheld_nothing_draws_no_withheld_line() -> None:
    html = render_character(a_report(findings=FINDINGS[:2]))
    assert 'class="withheld"' not in panel(html, "tab-provenance")
