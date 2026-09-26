# ABOUTME: Whole-page rules for the progression report: five panels, one script, one golden file.
# ABOUTME: The fixture is a night that varies -- deepest attempt third of seven, one discarded.

import re
from pathlib import Path

import pytest
from markupsafe import escape

from tests.adapters.render.test_html_invariants import FORBIDDEN_IN_SCRIPT, ICON_HOST
from tests.domain.progression_fixtures import (
    _DEFAULT_PLAYER,
    PHASES,
    a_loaded_attempt,
    a_loaded_series,
)
from tests.domain.test_progression import an_attempt
from wowperf.adapters.render.html import PROGRESSION_TEMPLATE_NAME, _environment, render_progression
from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import Death
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

    The three fight ids `a_progression_series` deepens (28, 30, 33) carry
    `_DEFAULT_PLAYER` as their roster, so `roster_deaths` has someone to count
    a death against; the other five carry none, since they are never wrapped
    in a `LoadedEncounter` and nothing ever reads their roster.
    """
    return [
        an_attempt(28, 64.81, 215.7, boss_name=BOSS_NAME, last_phase=1, players=_DEFAULT_PLAYER),
        an_attempt(29, 85.80, 105.9, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(30, 16.49, 480.0, boss_name=BOSS_NAME, last_phase=3, players=_DEFAULT_PLAYER),
        an_attempt(31, 85.40, 110.0, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(32, 87.65, 88.0, boss_name=BOSS_NAME, last_phase=1),
        an_attempt(33, 53.30, 278.8, boss_name=BOSS_NAME, last_phase=2, players=_DEFAULT_PLAYER),
        an_attempt(34, 55.65, 227.0, boss_name=BOSS_NAME, last_phase=2),
        an_attempt(35, 100.0, 15.8, boss_name=BOSS_NAME),
    ]


def _loaded(encounter: Encounter, *, deaths_after_ms: tuple[int, ...] = ()) -> LoadedEncounter:
    """Wraps one of `_measured_attempts()`'s own encounters as a deepened attempt.

    `a_loaded_attempt` builds its own encounter from scratch -- its own
    default boss name, no `last_phase` -- so a loaded attempt built that way
    reads a different encounter than `progression.attempts` holds for the
    same fight id: harmless while only `loaded.deaths` is read off it, wrong
    the moment anything reads `loaded.encounter.last_phase`, `.kill` or
    `.duration_seconds` instead. Wrapping the very object `_measured_attempts()`
    returned keeps the two in agreement on every field, not only the one this
    fixture happens to exercise today.
    """
    deaths = tuple(
        Death(
            player_name="", actor_id=1, timestamp_ms=encounter.start_ms + offset,
            killing_blow="x",
        )
        for offset in deaths_after_ms
    )
    return LoadedEncounter(encounter=encounter, deaths=deaths, damage_taken=())


def a_progression_series() -> LoadedProgression:
    """A night that varies: the deepest attempt sits third of seven, one attempt
    was discarded below the duration floor, phases are separated, and nothing
    was killed.

    Only three of the seven kept attempts are deepened -- the first, the
    deepest, and one more -- so the fixture also carries the "no reading yet"
    state the Deaths column has for an attempt nobody fetched events for.
    """
    measured = _measured_attempts()
    progression = build_progression(
        measured, encounter_id=3492, difficulty=5, phases=PHASES,
        separates_wipes=True,
    )
    by_fight_id = {encounter.fight_id: encounter for encounter in measured}
    loaded = (
        _loaded(by_fight_id[28], deaths_after_ms=(180_000,)),
        _loaded(by_fight_id[30], deaths_after_ms=(400_000, 450_000)),
        _loaded(by_fight_id[33]),
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
            title="The deepest attempt took more roster deaths than the rest of the night",
            detail="Two roster deaths, against zero and one on the other attempts read.",
            confidence=Confidence.MEASURED,
        ),
        Finding(
            id="progression.repeat.killing_blow",
            title="Frigid Roar dealt the first death in 3 of 7 attempts",
            detail=(
                "Across the 7 attempts whose first death was a roster player: "
                "Frigid Roar dealt 3."
            ),
            confidence=Confidence.MEASURED,
            evidence=("Frigid Roar dealt the first death in 3 of 7 attempts",),
            ability_id=1_309_919,
            ability_name="Frigid Roar",
        ),
        Finding(
            id=UNROUTED_ID,
            title="The pull timer drifted across the night",
            detail="No section of this report claims this measurement yet.",
            confidence=Confidence.INFERRED,
        ),
    )


def test_the_first_death_killing_blow_is_drawn_on_the_repeats_tab() -> None:
    html = a_progression_page()
    repeats = html.split('id="tab-repeats"', 1)[1].split("</section>", 1)[0]
    assert "finding-progression.repeat.killing_blow" in repeats


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

    # Vacuous on this page today, on purpose kept rather than dropped: icons here
    # are addressed through a CSS url() and an SVG <image href>, never through
    # `src=`, so no fixture in this file makes this loop match anything. It is a
    # standing check against a future template that starts using `src=` for an
    # icon -- see `a_progression_page_with_an_icon` below for the coverage this
    # page's actual icon-resolution path needs, which this loop cannot give it.
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


ICON_ABILITY_ID = 445432
ICON_FILENAME = "inv_misc_food_wheatbread.jpg"


def a_progression_findings_with_an_ability() -> tuple[Finding, ...]:
    """One finding whose title names a single ability, so `ledger_row`'s title
    split can hand it an `ability_id`.

    `progression.repeat.ability` is the one finding family that names one --
    `render_progression`'s own docstring says so -- so this is the only shape a
    progression finding can take that an icon could ever resolve against.
    """
    return (
        Finding(
            id="progression.repeat.ability",
            title="Ravenous Feast kept landing as attempts fell apart",
            detail="It landed in three of the four attempts carrying a window.",
            confidence=Confidence.MEASURED,
            ability_id=ICON_ABILITY_ID,
            ability_name="Ravenous Feast",
        ),
    )


def a_progression_page_with_an_icon() -> str:
    """The one page in this file that actually resolves an icon.

    A fixture of its own rather than an `icons=` argument added to
    `a_progression_page()`: that one feeds the committed golden file, which
    pins the page a run with no `icons` argument produces -- the CLI may never
    pass one, and folding an icon into it would make the golden byte-diff turn
    on a CDN address instead of on the run itself. Every other fixture in this
    file renders with no `icons` argument at all, so the scoping rules below
    would still pass over a page that started drawing a wrongly-scoped address,
    because nothing there resolves one to catch. This is the fixture that does.
    """
    report = build_progression_report(
        a_progression_series(), a_progression_findings_with_an_ability(), FETCHED_AT
    )
    return render_progression(report, CdnIcons({ICON_ABILITY_ID: ICON_FILENAME}))


def test_every_image_address_the_page_draws_points_at_the_icon_host() -> None:
    # The self-containment loop above checks `src=` attributes; an icon reaches
    # this page through a CSS url() instead, which that loop cannot see since
    # nothing here ever draws one through `src=`. Icons are the only thing the
    # report may load, and one host is the only place it may load them from.
    html = a_progression_page_with_an_icon()
    drawn = re.findall(r"url\(([^)]*)\)", html)
    assert drawn, "the fixture resolved no icon, so this rule was never exercised"
    for address in drawn:
        assert address.startswith(ICON_HOST), address


def test_a_resolved_icon_reaches_the_page_as_an_address_never_as_embedded_bytes() -> None:
    # The page carries no image bytes of its own. Embedding would satisfy every
    # scoping rule above perfectly well, which is why it needs a check of its
    # own rather than following from the two around it.
    html = a_progression_page_with_an_icon()
    assert f"url({ICON_HOST}{ICON_FILENAME})" in html
    assert "data:image" not in html


def test_every_href_stays_scoped_even_when_an_icon_resolves() -> None:
    # `test_the_page_carries_no_reference_to_another_report` above is proved
    # against a page that resolves no icon at all. An SVG <image href> is the
    # one other shape an href may take on this page, and this applies the same
    # scoping -- a fragment, or the icon host -- to a page that draws one.
    html = a_progression_page_with_an_icon()
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith(ICON_HOST) for href in hrefs), (
        "the fixture resolved no icon href, so this rule was never exercised"
    )
    for href in hrefs:
        assert href.startswith("#") or href.startswith(ICON_HOST), href


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


SCOPE = "b9-"


def test_every_anchor_the_progression_partials_draw_takes_the_scope() -> None:
    """The night page draws these partials once per boss; an unprefixed id collides.

    Rendered through the real template with a scope handed in, which is exactly
    how the night page will reach them. Every family of anchor is checked, not
    only ids: a tab button whose `data-tab-for` stayed bare would open another
    boss's panel.
    """
    html = _environment().get_template(PROGRESSION_TEMPLATE_NAME).render(
        report=a_progression_report(), icons_by_id={}, scope=SCOPE
    )
    # Cut before the inline script as well as after <main>: report.js.j2 builds
    # its own selectors by string concatenation ('[data-tab-panel="' + group +
    # '"]'), and the naive regexes below would read that literal text as a bare
    # data-tab-panel value. It is JS source, not a drawn anchor, and no template
    # this task touches can change it -- test_night_html_invariants.py notes the
    # same script-text hazard for its own tab-bar count.
    body = html.split("<main>", 1)[1].split("<script", 1)[0]
    values = (
        re.findall(r'\sid="([^"]+)"', body)
        + re.findall(r'data-tab-panel="([^"]+)"', body)
        + re.findall(r'data-tab-for="([^"]+)"', body)
        + re.findall(r'href="#([^"]+)"', body)
    )
    assert values, "a page with no anchors would pass this vacuously"
    bare = sorted({value for value in values if not value.startswith(SCOPE)})
    assert bare == [], f"drawn without the scope: {bare}"
