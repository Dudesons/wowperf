# ABOUTME: Whole-page rules for the progression report: five panels, one script, one golden file.
# ABOUTME: The fixture is a night that varies -- deepest attempt third of seven, one discarded.

import re
from pathlib import Path

import pytest
from markupsafe import escape

from tests.adapters.render.test_html_invariants import FORBIDDEN_IN_SCRIPT, ICON_HOST
from tests.domain.progression_fixtures import PHASES, a_loaded_attempt, a_loaded_series
from tests.domain.test_progression import an_attempt
from wowperf.adapters.render.html import render_progression
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression, build_progression
from wowperf.domain.report.progression_build import build_progression_report
from wowperf.domain.report.progression_model import ProgressionReport

PROGRESSION_PANEL_ORDER = [
    "tab-summary", "tab-attempts", "tab-repeats", "tab-best", "tab-provenance",
]
"""The exact five top-level panel ids, in the order the page draws them.

Nothing in the templates or the renderer counts tabs -- the script matches a
button to a panel by string equality -- so this list is the only place the
count is stated, and a tab added without a line here is a tab no test sees.
"""

FETCHED_AT = "2026-09-16 08:14"

BOSS_NAME = "The Hollow Choir"
"""Deliberately not `an_attempt`'s own default ("Emberkin"): that default is also
the name on `progression_fixtures._DEFAULT_PLAYER`'s one roster member, and the
golden file below is read by eye for "no player name appears anywhere". Naming
the boss something else keeps that reading unambiguous -- every "Emberkin" a
regression could introduce would be a raider's name and nothing else.
"""


def _measured_attempts() -> list[Encounter]:
    """The eight attempts `test_progression.a_measured_night` measured 2026-09-16,
    each given a `last_phase` this fixture adds on top: that night's own cache
    carried no phase-transition reading, and without one the "Ended in" column
    this task exists to pin would read empty regardless of `separates_wipes`.

    The shape itself is not invented. Attempt 30 is the deepest at 16.49% left,
    third of the eight pulled and third of the seven `build_progression` keeps --
    neither the first row nor the last, which is the one behaviour a monotonic
    fixture could never exercise. Attempt 35, at 15.8 seconds, is the one
    `build_progression` discards below `MIN_ATTEMPT_SECONDS`.
    """
    return [
        an_attempt(28, 64.81, 215.7, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(29, 85.80, 105.9, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(30, 16.49, 480.0, boss_name=BOSS_NAME, last_phase=3),
        an_attempt(31, 85.40, 110.0, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(32, 87.65, 88.0, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(33, 53.30, 278.8, boss_name=BOSS_NAME, last_phase=2),
        an_attempt(34, 55.65, 227.0, boss_name=BOSS_NAME, last_phase=2),
        an_attempt(35, 100.0, 15.8, boss_name=BOSS_NAME),
    ]


def a_progression_series() -> LoadedProgression:
    """A night that varies: the deepest attempt sits third of seven, one attempt
    was discarded below the duration floor, phases are separated, and nothing
    was killed.

    Only three of the seven kept attempts are deepened -- the first, the
    deepest, and one more -- so the fixture also carries the "no reading yet"
    state the Deaths column has for an attempt nobody fetched events for.
    """
    progression = build_progression(
        _measured_attempts(), encounter_id=3492, difficulty=5, phases=PHASES,
        separates_wipes=True,
    )
    loaded = (
        a_loaded_attempt(28, remaining=64.81, seconds=215.7, deaths_after_ms=(180_000,)),
        a_loaded_attempt(
            30, remaining=16.49, seconds=480.0, deaths_after_ms=(400_000, 450_000)
        ),
        a_loaded_attempt(33, remaining=53.30, seconds=278.8),
    )
    return LoadedProgression(progression=progression, loaded=loaded)


UNROUTED_ID = "progression.unplaced.example"
"""No prefix in `PROGRESSION_PLACEMENTS` starts a family this way. Every real
finding id the analysers emit today already has a placement there (checked
against `progression_service.py`, `progression_best.py` and
`progression_repeats.py`, 2026-09-16), so this id stands in for a family the
table has not been taught to place yet -- which is exactly the shape
`build_observations` exists to catch instead of dropping silently.
"""


def a_progression_findings() -> tuple[Finding, ...]:
    """One finding per row field the page has, plus one none of them claim.

    Every title differs from every other, which the once-only rule below
    needs: two findings sharing a sentence would draw two identical headings,
    and a heading counted twice would read as a finding drawn twice.
    """
    return (
        Finding(
            id="progression.cluster",
            title="The attempts split into a short cluster and a long one",
            detail="Four ran under two minutes; three ran past three and a half.",
            confidence=Confidence.DERIVED,
        ),
        Finding(
            id="progression.repeat.phase",
            title="Most wipes ended in the same phase",
            detail="Four of the seven kept attempts never left the opening phase.",
            confidence=Confidence.MEASURED,
        ),
        Finding(
            id="progression.best.deaths",
            title="The deepest attempt lost more players than the rest of the night",
            detail="Two roster deaths, against zero and one on the other attempts read.",
            confidence=Confidence.MEASURED,
        ),
        Finding(
            id=UNROUTED_ID,
            title="The pull timer drifted across the night",
            detail="No section of this report claims this measurement yet.",
            confidence=Confidence.INFERRED,
        ),
    )


def a_progression_report() -> ProgressionReport:
    return build_progression_report(a_progression_series(), a_progression_findings(), FETCHED_AT)


def a_progression_page() -> str:
    return render_progression(a_progression_report())


PANEL_ID = re.compile(r'<section class="panel"[^>]*\sid="([^"]+)"')
"""Each top-level panel's own id, in the order the page draws them.

Read off the `<section>` itself rather than counted, and read as an id rather
than as a tag: a panel whose id was misspelled in its own partial still counts
as a section, still gets a nav button pointing at the name nobody renamed, and
clicks through to nothing. A tab is two hand-written halves matched only by
string equality, and this is the half that names the panel.
"""

MAIN_NAV = re.compile(r'<nav class="tabs" data-tab-group="main"[^>]*>(.*?)</nav>', re.DOTALL)
TAB_TARGET = re.compile(r'data-tab-for="([^"]+)"')


def main_tab_targets(html: str) -> list[str]:
    """What each top-level nav button claims to open, in the order drawn."""
    nav = MAIN_NAV.search(html)
    assert nav is not None, "the page drew no top-level tab bar at all"
    return TAB_TARGET.findall(nav.group(1))


def test_every_panel_appears_once_in_tab_order() -> None:
    """The five panels, by the ids they actually render, in the order they render.

    Stronger than counting `<section class="panel"` on its own, which a panel
    with a misspelled id passes: the count is right, the order is right, and
    the button pointing at the name nobody renamed opens nothing. Compared as
    a list so a missing panel, a duplicated one, a renamed one and a reordered
    one are each a failure, and `PROGRESSION_PANEL_ORDER` stays the one place
    the count is stated. The count is kept beside the list rather than dropped
    for it, because `PANEL_ID` only reads sections that carry an id: a sixth
    panel written without one is a section the list equality never sees.
    """
    html = a_progression_page()
    panels = PANEL_ID.findall(html)

    assert panels, "the page drew no panels at all"
    assert panels == PROGRESSION_PANEL_ORDER
    assert html.count('<section class="panel"') == len(PROGRESSION_PANEL_ORDER)


def test_every_panel_has_exactly_one_tab_button() -> None:
    """Both directions, because either alone leaves the other half unchecked.

    A panel with no button is unreachable; a button naming a panel that does
    not exist is a click that does nothing.
    """
    html = a_progression_page()
    panels = PANEL_ID.findall(html)
    assert panels, "the page drew no panels at all"

    for name in PROGRESSION_PANEL_ORDER:
        assert html.count(f'data-tab-for="{name}"') == 1, name
    assert set(main_tab_targets(html)) == set(panels)


def test_the_tab_buttons_follow_panel_order() -> None:
    # The script opens the first button's panel by default, so button order is
    # the default tab; nothing else pins the order the buttons appear in.
    assert main_tab_targets(a_progression_page()) == PROGRESSION_PANEL_ORDER


def test_the_root_class_the_script_adds_is_not_in_the_markup() -> None:
    # The script adds it at run time; rendering it would hide panels with no
    # script. `.tabs` is hidden until the root class arrives, so a page that
    # shipped the class already would hide every panel but one for a reader
    # whose browser runs no script.
    html = a_progression_page()
    assert '<html lang="en">' in html
    assert 'class="js' not in html


def test_the_page_makes_no_request_but_its_icons() -> None:
    """One inline script, none of it fetching anything, no stylesheet link, no
    `@import`, and no `src=` pointed anywhere but the one host the report may
    load art from.

    `FORBIDDEN_IN_SCRIPT` and `ICON_HOST` are imported rather than retyped, so
    one tuple and one host govern every report page.
    """
    html = a_progression_page()
    assert "<link" not in html.lower()
    assert "@import" not in html.lower()

    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.S | re.I)
    assert len(scripts) == 1
    attributes, body = scripts[0]
    assert "src=" not in attributes.lower()
    for forbidden in FORBIDDEN_IN_SCRIPT:
        assert forbidden not in body, forbidden

    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert src.startswith(ICON_HOST), src


FINDING_ID = re.compile(r'id="finding-([^"]+)"')


def test_every_finding_appears_exactly_once() -> None:
    html = a_progression_page()
    ids = FINDING_ID.findall(html)
    assert ids, "the page drew no finding cards at all"
    for finding in a_progression_findings():
        assert ids.count(finding.id) == 1, finding.id


def test_a_title_containing_markup_is_escaped() -> None:
    # Autoescaping is the only thing standing between an API-sourced string --
    # a boss name or a phase name Warcraft Logs supplied -- and the reader's
    # browser. Compared against the escaped form too, so a title stripped
    # instead of escaped could not pass this by accident of being blank.
    evil_title = "<script>alert(1)</script>"
    findings = (
        Finding(
            id="progression.cluster", title=evil_title, detail="",
            confidence=Confidence.MEASURED,
        ),
    )
    report = build_progression_report(a_progression_series(), findings, FETCHED_AT)

    html = render_progression(report)

    assert evil_title not in html
    assert str(escape(evil_title)) in html


def test_the_page_never_draws_one_attempts_anatomy() -> None:
    """Section 8: the anatomy is `wowperf raid --fight N`'s work, and keeping the
    two pages from becoming duplicate templates is a prohibition, not a taste.

    Asserted against the class names the death recap owns, because that is the
    one part of the raid page a progression page would plausibly grow into.
    """
    html = a_progression_page()

    for owned_by_the_raid_page in ('class="recap"', 'class="hp-curve"', 'class="avail"'):
        assert owned_by_the_raid_page not in html


def test_the_page_carries_no_reference_to_another_report() -> None:
    """RPGLogs terms section 5d: never accumulate a corpus of other players' logs.

    The provenance type has no field for one, so this asserts what a reader can
    check: the page links to no report at all.
    """
    assert "warcraftlogs.com/reports/" not in a_progression_page()


ATTEMPT_ROW_CELLS = re.compile(
    r"<tr[^>]*>\s*<td>[^<]*</td><td>[^<]*</td><td>[^<]*</td><td>([^<]*)</td><td>[^<]*</td>",
)


def attempts_phase_column(html: str) -> list[str]:
    """Every attempt row's "Ended in" cell (the fourth column), in table order.

    The attempts table is the only `<table>` a progression page draws, so
    matching `<tr>` across the whole page needs no scoping to find it.
    """
    cells = ATTEMPT_ROW_CELLS.findall(html)
    assert cells, "the page drew no attempt rows at all"
    return cells


def a_progression_page_without_phase_separation() -> str:
    """The other gate state: `separates_wipes=False`, on attempts that do carry
    a phase reading.

    Both attempts here are given a `last_phase`. Without one, an empty "Ended
    in" column would prove nothing about the flag -- it would read empty for
    lack of data regardless of what the flag said.
    """
    series = a_loaded_series(
        a_loaded_attempt(60, remaining=70.0, seconds=180.0, last_phase=1),
        a_loaded_attempt(61, remaining=40.0, seconds=260.0, last_phase=2),
        separates_wipes=False,
        phases=PHASES,
    )
    report = build_progression_report(series, (), FETCHED_AT)
    return render_progression(report)


def test_the_ended_in_column_is_empty_when_the_series_does_not_separate_wipes() -> None:
    html = a_progression_page_without_phase_separation()
    for cell in attempts_phase_column(html):
        assert cell == ""


PROGRESSION_GOLDEN = Path(__file__).parent / "golden" / "progression.html"


def test_the_rendered_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = a_progression_page()
    if pytestconfig.getoption("--golden-update"):
        PROGRESSION_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSION_GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == PROGRESSION_GOLDEN.read_text(encoding="utf-8"), (
        "The rendered progression report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_progression_html_invariants.py "
        "--golden-update`."
    )
