# ABOUTME: Whole-page rules for the night report: the report invariant, held over many pulls.
# ABOUTME: Two dropdowns that only show and hide, and no element id shared between two pulls.

import re

from markupsafe import escape

from tests.adapters.render.test_html_invariants import FORBIDDEN_IN_SCRIPT, ICON_HOST
from tests.domain.progression_fixtures import a_loaded_attempt
from tests.domain.report.test_night_build import (
    BOSS_NAMES,
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    NO_FINDINGS,
    NO_ROLES,
    OWNER,
    REPORT_CODE,
    ROSTER,
    a_night,
)
from wowperf.adapters.render.html import render_night
from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.comparison.night_axis import NOT_DRAWN_ID
from wowperf.domain.night import LoadedNight, Night
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.deaths import TRIMMED_CARD_NOTE
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.night_model import NightReport

PULLS_PER_BOSS = (2, 3)
"""Two bosses, and deliberately not the same number of pulls under each.

Nearly every rule in this file is about *many* pulls -- ids that must not
collide, one pull control per boss, an icon map gathered past the first pull.
A fixture of one boss with one pull passes every one of them against an
implementation that handles only the first thing it is given, and two bosses
holding two pulls each passes a control that renders the first boss's count
twice. Two and three can be passed by neither.
"""

PANELS_PER_PULL = 7
"""Summary, Damage, Mechanics, Deaths, Interrupts, Players, Provenance.

The raid page's own seven, drawn once per pull because the night page composes
the raid partials rather than inventing a second set. Stated here so a pull that
lost a panel fails by count rather than by a reader noticing a missing tab.
"""

ABILITY_IDS = (445_566, 445_567, 445_568, 445_569, 445_570)
"""One ability id per pull, each different from every other.

The icon address map is gathered over every pull, and a walk that stopped at
the first pull -- or at the first boss -- would resolve one of these and draw
the rest as bare names. Five ids for five pulls is what makes that visible.
"""

ICON_FILES = {one: f"spell-{one}.jpg" for one in ABILITY_IDS}

TRIMMED_ON_THE_PAGE = str(escape(TRIMMED_CARD_NOTE))
"""The trimmed-card note as the page spells it, not as Python holds it.

The note names the flag that buys the card back -- `--deep <fight>` -- and
Jinja's autoescape turns those angle brackets into entities, so only the
escaped form is ever in the rendered page.
"""


def a_loaded_night(counts: tuple[int, ...] = PULLS_PER_BOSS) -> LoadedNight:
    """`a_night`'s shape, with a different ability hitting each pull.

    `a_night` next door gives every pull the same ability id, which is right
    for a builder test and useless for an icon walk: one resolved address would
    satisfy every pull at once. Built here rather than by widening that fixture,
    because the twelve builder tests that use it assert on grouping and tiers
    and would all have to change to buy nothing.
    """
    loaded: list[LoadedProgression] = []
    drawn = 0
    for index, count in enumerate(counts):
        boss_name = BOSS_NAMES[index]
        encounter_id = 3490 + index
        pulls = []
        for which in range(count):
            pulls.append(
                a_loaded_attempt(
                    (index + 1) * 10 + which,
                    players=ROSTER,
                    deaths_after_ms=(10_000,),
                    damage_after_ms=((9_000, ABILITY_IDS[drawn], None),),
                    boss_name=boss_name,
                    encounter_id=encounter_id,
                    owner_name=OWNER,
                )
            )
            drawn += 1
        loaded.append(
            LoadedProgression(
                progression=Progression(
                    report_code=REPORT_CODE,
                    encounter_id=encounter_id,
                    boss_name=boss_name,
                    difficulty=5,
                    size=20,
                    attempts=tuple(one.encounter for one in pulls),
                ),
                loaded=tuple(pulls),
            )
        )
    return LoadedNight(
        night=Night(
            report_code=REPORT_CODE, bosses=tuple(one.progression for one in loaded)
        ),
        loaded=tuple(loaded),
    )


def a_night_report(
    loaded: LoadedNight | None = None, *, deep_every_pull: bool = False
) -> NightReport:
    night = a_loaded_night() if loaded is None else loaded
    every = frozenset(
        attempt.encounter.fight_id
        for boss in night.loaded
        for attempt in boss.attempts_with_events
    )
    return build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=every if deep_every_pull else frozenset(),
        death_cards=True,
    )


def a_night_page() -> str:
    """The trimmed page: the tier every night is drawn at unless `--deep` names one."""
    return render_night(a_night_report())


def a_deep_night_page_with_icons() -> str:
    """Every pull deep, so every pull carries a timeline row naming its own ability.

    A trimmed card holds no timeline and this fixture's deaths carry no killing
    blow id, so the trimmed page resolves no icon at all -- the address rules
    below would pass over it while never meeting an address.
    """
    return render_night(a_night_report(deep_every_pull=True), CdnIcons(ICON_FILES))


def test_the_fixture_draws_more_than_one_pull_and_more_than_one_boss() -> None:
    """The precondition every rule below rests on, stated once so it fails by name.

    This repository's failure mode is a test that could not have failed. A night
    fixture that quietly collapsed to one boss, or to one pull, would leave the
    id, control-count and icon rules green over a page that never exercised them.
    """
    report = a_night_report()

    assert tuple(len(boss.pulls) for boss in report.bosses) == PULLS_PER_BOSS
    assert report.total_pulls == sum(PULLS_PER_BOSS)
    assert len(ABILITY_IDS) == report.total_pulls

    html = a_night_page()
    assert html.count('<section class="panel"') == PANELS_PER_PULL * report.total_pulls
    assert TRIMMED_ON_THE_PAGE in html


def test_the_page_executes_only_its_own_script() -> None:
    # One inline script and only one, whatever the pull count: the night page
    # composes the same partials the raid page does and must not have grown a
    # second. `FORBIDDEN_IN_SCRIPT` is imported rather than retyped, so one
    # tuple governs every page.
    html = a_night_page()
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.S | re.I)
    assert len(scripts) == 1
    attributes, body = scripts[0]
    assert "src=" not in attributes.lower()
    for forbidden in FORBIDDEN_IN_SCRIPT:
        assert forbidden not in body, forbidden
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src
    # Ids here contain dots, from the finding ids inside them; querySelector("#" + id)
    # would read a dot as a class selector, so the lookup must stay getElementById.
    assert "getElementById" in body


def test_the_script_never_reaches_for_an_option_element() -> None:
    """What pins the two-control design in code rather than in a document.

    Spec section 3 settled one boss control and one pull control per boss,
    against a single pull control whose options are hidden or disabled as the
    boss changes. These three strings are how that rejected implementation
    would give itself away: it cannot be written without building, rewriting or
    disabling an `<option>`, and each of those reaches past showing and hiding,
    which is the whole of what the report invariant lets this script do.
    """
    body = re.findall(r"<script\b[^>]*>(.*?)</script>", a_night_page(), flags=re.S | re.I)[0]

    assert "createElement" not in body
    assert "innerHTML" not in body
    assert "disabled" not in body


SELECT_TAG = re.compile(r"<select\b[^>]*>")
PULL_CONTROL = re.compile(r'<select id="night-pull-b(\d+)"[^>]*>(.*?)</select>', re.DOTALL)


def test_one_boss_control_and_exactly_one_pull_control_for_each_boss() -> None:
    """A count, because a count is what fails when a loop is wrong.

    Asserting that a boss control and a pull control exist would pass against a
    page that drew one pull control for the whole night, which is the rejected
    design, and against one that drew a pull control per *pull*, which is five
    controls for five pulls.
    """
    report = a_night_report()
    html = render_night(report)

    selects = SELECT_TAG.findall(html)
    assert len(selects) == 1 + len(report.bosses)
    assert sum("data-night-boss" in one for one in selects) == 1
    assert sum("data-night-pull" in one for one in selects) == len(report.bosses)


def test_each_pull_control_offers_its_own_bosss_pulls_and_no_others() -> None:
    """The other half: a control per boss is worth nothing if both list the night.

    Two bosses holding two and three pulls, so a control that offered every
    pull to every boss would read five twice, and one that offered the first
    boss's count to both would read two twice.
    """
    report = a_night_report()
    html = render_night(report)

    offered = {
        int(index): body.count("<option") for index, body in PULL_CONTROL.findall(html)
    }
    assert offered == {0: PULLS_PER_BOSS[0], 1: PULLS_PER_BOSS[1]}


def test_every_pull_is_its_own_tab_group() -> None:
    """Seven panels per pull, and no two pulls sharing a group name.

    The script matches a tab button to a panel by string equality and toggles
    every panel in the button's group. Two pulls sharing a group would hide
    each other's tabs; two pulls sharing a panel id would send every button on
    the page to whichever of the two the browser picked first.
    """
    report = a_night_report()
    html = render_night(report)

    groups = re.findall(r'<section class="panel" data-tab-panel="([^"]+)"', html)
    assert len(groups) == PANELS_PER_PULL * report.total_pulls
    assert len(set(groups)) == report.total_pulls


def test_no_element_id_appears_twice_across_five_pulls() -> None:
    """Finding ids repeat across pulls by design, and DOM ids may not.

    Every pull draws its findings from the same analysers, so the ids inside
    two pulls' reports are the same strings. That is harmless for a map keyed
    by ability id and fatal for an `id=` attribute: a duplicate is invalid HTML
    and sends the page's own links to whichever copy the browser reaches first.
    """
    html = a_night_page()

    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicates == set()


def test_every_fragment_link_lands_on_an_anchor_that_exists() -> None:
    """Scoping ids is only half of it: the links into them have to be scoped too.

    A badge inside pull four pointing at `#provenance` would jump a reader to
    the night's own provenance, or to pull one's, with nothing on the page
    saying the figures belonged to another attempt.
    """
    html = a_night_page()

    targets = [href[1:] for href in re.findall(r'href="([^"]*)"', html) if href.startswith("#")]
    assert targets, "the page drew no fragment link at all, so this proves nothing"
    present = set(re.findall(r'\sid="([^"]+)"', html))
    for target in targets:
        assert target in present, target


def test_a_trimmed_card_says_it_was_trimmed_instead_of_claiming_no_events() -> None:
    """`_deaths.html.j2` guards its timeline block on the timeline being there.

    A trimmed card's `timeline_summary` reads "0 events" and its
    `timeline_note` explains that the run-up was never built. Composing the
    partial in a way that dropped the guard would print the label beside the
    note -- a page claiming the log was quiet in the seconds before a death it
    never read.
    """
    html = a_night_page()

    assert TRIMMED_ON_THE_PAGE in html
    assert "0 events" not in html


def test_every_pull_contributes_its_own_ability_to_the_icon_map() -> None:
    """The address map is gathered over every pull, not over the first one.

    Each pull is hit by its own ability, so a walk that stopped at the first
    pull, or at the first boss, resolves one or two of these and draws the rest
    as bare names -- a missing picture on a page that otherwise renders, which
    is the one icon failure nothing else here would see.
    """
    html = a_deep_night_page_with_icons()

    for ability_id in ABILITY_IDS:
        assert f".i-{ability_id}" in html, ability_id


def test_every_image_address_the_page_draws_points_at_the_icon_host() -> None:
    # Icons are the only thing the report may load, and one host is the only
    # place it may load them from. An icon reaches the page through a CSS url()
    # and an SVG <image href>, neither of which the `src` rule above sees.
    html = a_deep_night_page_with_icons()

    drawn = re.findall(r"url\(([^)]*)\)", html)
    assert drawn, "the fixture resolved no icon, so this rule was never exercised"
    for address in drawn:
        assert address.startswith(ICON_HOST), address
    assert "data:image" not in html


def test_the_page_hides_nothing_before_the_script_runs() -> None:
    # Two dropdowns that hide four pulls out of five are the whole point of the
    # page, and a reader whose browser runs no script must still see all five.
    # Every hiding rule is therefore scoped under the root class the script
    # adds, with the same two exceptions the other pages carry: `.tabs`, which
    # the script un-hides, and `.tip`, which CSS alone reveals on hover.
    html = a_night_page()
    assert not re.search(r"<[^>]*\shidden[\s>=]", html)
    assert not re.search(r'style="[^"]*display', html)

    style = html[html.index("<style>"):html.index("</style>")]
    hiding = list(re.finditer(r"([^{}]+)\{[^{}]*display:\s*none", style))
    assert hiding, "the stylesheet hides nothing at all, so this rule went unexercised"
    for rule in hiding:
        selector = rule.group(1).strip().splitlines()[-1].strip()
        assert selector.startswith(".js ") or selector in (".tabs", ".tip"), selector


def test_the_root_class_the_script_adds_is_not_in_the_markup() -> None:
    # Rendering it would hide every pull but one for a reader whose browser runs
    # no script, and there is no control they could use to get the others back.
    html = a_night_page()
    assert '<html lang="en">' in html
    assert 'class="js' not in html


def test_the_absent_axis_disclosure_is_drawn_once_for_the_page() -> None:
    """The night's own finding, not one pull's, so it is stated once and not five times."""
    html = a_night_page()

    assert html.count(f'id="finding-{NOT_DRAWN_ID}"') == 1


def test_a_boss_whose_every_pull_failed_still_gets_a_control_and_says_so() -> None:
    """A boss the report pulled is on the page even when nothing could be drawn.

    `BossSection` keeps it, and a page that dropped its control would leave the
    boss list and the pull controls disagreeing about what the night held.
    """
    report = a_night_report(a_night(bosses=(2, 2), failed=(20, 21)))
    html = render_night(report)

    assert len(report.bosses) == 2
    assert report.bosses[1].pulls == ()
    assert len(SELECT_TAG.findall(html)) == 1 + len(report.bosses)
    offered = {int(index): body.count("<option") for index, body in PULL_CONTROL.findall(html)}
    assert offered == {0: 2, 1: 1}
    for line in report.provenance.withheld:
        assert line in html
