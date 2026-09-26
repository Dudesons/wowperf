# ABOUTME: Whole-page rules for the night report: the report invariant, held over many pulls.
# ABOUTME: Two dropdowns that only show and hide, and no element id shared between two pulls.

import re
from pathlib import Path

import pytest
from markupsafe import escape

from tests.adapters.render.test_html_invariants import FORBIDDEN_IN_SCRIPT, ICON_HOST
from tests.adapters.render.test_raid_html_invariants import a_minimal_raid_report
from tests.domain.progression_fixtures import a_loaded_attempt
from tests.domain.report.test_night_build import (
    BOSS_NAMES,
    FETCHED,
    NO_CONSUMABLES,
    NO_ROLES,
    OWNER,
    REPORT_CODE,
    ROSTER,
    a_night,
)
from wowperf.adapters.render.html import render_night, render_raid
from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.night_axis import NOT_DRAWN_ID
from wowperf.domain.events import CastEvent, HealthSample
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.night import LoadedNight, Night
from wowperf.domain.progression import LoadedProgression, Progression
from wowperf.domain.report.deaths import NO_CARDS_ASKED, TRIMMED_CARD_NOTE
from wowperf.domain.report.night_build import build_night_report
from wowperf.domain.report.night_model import NightReport
from wowperf.domain.season import DefensiveAbility, Defensives

PULLS_PER_BOSS = (1, 2, 3)
"""Three bosses at three different counts, the first pulled only once.

Nearly every rule in this file is about *many* pulls -- ids that must not
collide, one pull control per boss, an icon map gathered past the first pull.
A fixture of one boss with one pull passes every one of them against an
implementation that handles only the first thing it is given, and two bosses
holding two pulls each passes a control that renders the first boss's count
twice. The single-pull boss is what puts a boss with no summary on the page
beside two that carry one, so both shapes are drawn -- and still no two
bosses share a count.
"""

NIGHT_BOSS_NAMES = (*BOSS_NAMES, "Vorthal the Unmade")
"""`BOSS_NAMES` with a third boss for the third count.

Widened here rather than next door: the builder test that groups every pull
under its own boss compares against the whole of `BOSS_NAMES`.
"""

PANELS_PER_PULL = 7
"""Summary, Damage, Mechanics, Deaths, Interrupts, Players, Provenance.

The raid page's own seven, drawn once per pull because the night page composes
the raid partials rather than inventing a second set. Stated here so a pull that
lost a panel fails by count rather than by a reader noticing a missing tab.
"""

PANELS_PER_SUMMARY = 5
"""Summary, Attempts, Repeats, Best attempt, Provenance.

The progression page's own five, drawn once per boss summary for the same
reason the pulls draw the raid page's seven: the night composes the
progression partials rather than inventing a third set.
"""


def summaries_on(report: NightReport) -> int:
    """How many bosses on the page carry a summary, counted off the report itself."""
    return sum(1 for boss in report.bosses if boss.summary)


ABILITY_IDS = (445_566, 445_567, 445_568, 445_569, 445_570, 445_571)
"""One ability id per pull, each different from every other.

The icon address map is gathered over every pull, and a walk that stopped at
the first pull -- or at the first boss -- would resolve one of these and draw
the rest as bare names. Six ids for six pulls is what makes that visible.
"""

ROW_ABILITY_IDS = (700_101, 700_102, 700_103, 700_104, 700_105, 700_106)
"""One ability per pull, named by that pull's finding rather than by its death.

`_icon_addresses` walks ledger rows as well as death cards, and those are two
different arms of it: a fixture whose icons all arrive through a death card's
timeline leaves the row arm untested, and dropping it entirely then fails
nothing. Measured -- that is exactly what survived before these existed. One id
per pull for the same reason `ABILITY_IDS` has one: a walk that stopped at the
first pull would resolve one of them and leave five abilities drawn as bare
names.
"""

ICON_FILES = {
    one: f"spell-{one}.jpg" for one in (*ABILITY_IDS, *ROW_ABILITY_IDS)
}
"""Every ability the fixture puts on the page, resolvable.

Both arms of the walk: the death card's timeline names one per pull, and
that pull's own finding names another. An `ICON_FILES` covering only the
first would leave the row arm resolving nothing and drawing nothing, which
is indistinguishable from a walk that never reached it.
"""

SHIELD_ID = 11426
SHIELD_NAME = "Ice Barrier"
"""One defensive the dying player pressed inside the run-up, on every pull.

A press with an aura band over it is the only thing that puts a cover
rectangle on a health curve, and the cover's element id is built from the
same `marker_id` as the marker beside it -- the same string on every pull.
Measured: with no press, unscoping the cover id fails nothing.
"""

A_DEFENSIVE = Defensives(
    entries=(
        ("Mage/Arcane", (DefensiveAbility(
            ability_id=SHIELD_ID, name=SHIELD_NAME, cooldown_seconds=25.0,
        ),)),
    )
)

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

    Each pull also carries two health readings before its death, which is what
    makes a deep card draw a health curve. The curve is the only thing that
    puts a marker and a cover on the page -- both keyed on the same
    `marker_id` that counts from zero inside each card, and so the same string
    on every pull. Measured: without the readings, unscoping either of those
    two ids fails nothing at all.
    """
    loaded: list[LoadedProgression] = []
    drawn = 0
    for index, count in enumerate(counts):
        boss_name = NIGHT_BOSS_NAMES[index]
        encounter_id = 3490 + index
        pulls = []
        for which in range(count):
            attempt = a_loaded_attempt(
                (index + 1) * 10 + which,
                players=ROSTER,
                deaths_after_ms=(10_000,),
                damage_after_ms=((9_000, ABILITY_IDS[drawn], None),),
                boss_name=boss_name,
                encounter_id=encounter_id,
                owner_name=OWNER,
            )
            start_ms = attempt.encounter.start_ms
            pulls.append(
                attempt.model_copy(
                    update={
                        "health_samples": tuple(
                            HealthSample(
                                actor_id=ROSTER[0].actor_id,
                                timestamp_ms=start_ms + offset,
                                hit_points=points,
                                max_hit_points=1_000_000,
                            )
                            # Two readings, at different health, so the curve is a
                            # line rather than the single point `build_health_curve`
                            # refuses to draw.
                            for offset, points in ((2_000, 1_000_000), (8_000, 400_000))
                        ),
                        "casts": (
                            CastEvent(
                                actor_id=ROSTER[0].actor_id,
                                ability_id=SHIELD_ID,
                                ability_name=SHIELD_NAME,
                                timestamp_ms=start_ms + 5_000,
                            ),
                        ),
                        "auras": (
                            PlayerAuras(
                                actor_id=ROSTER[0].actor_id,
                                on_self=(
                                    Aura(
                                        ability_id=SHIELD_ID,
                                        name=SHIELD_NAME,
                                        total_uptime_ms=4_000,
                                        uses=1,
                                        bands=(
                                            AuraBand(
                                                start_ms=start_ms + 5_000,
                                                end_ms=start_ms + 9_000,
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    }
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


REPEATED_FINDING_ID = "night.pull.repeated"
"""One finding id, handed to every pull, because that is the shape a real night has.

`night` runs the same analysers over every pull, so the id a finding carries on
pull one is the id it carries on pull five -- `all_night_ledger_rows` returns
duplicates by design. That is what makes the prefix necessary, and a fixture
that handed each pull no finding at all, or a differently named one, would draw
no colliding card and leave the whole of `_macros.html.j2`'s scoping untested.
Measured: with `NO_FINDINGS`, unscoping the finding card id fails nothing.

The id is one no placement family claims, so it lands in the Summary's
catch-all and is drawn on every pull rather than only on the pulls whose tab
its family belongs to.
"""


def a_nights_findings(night: LoadedNight) -> dict[int, tuple[Finding, ...]]:
    """The same finding on every pull, under the one id every pull would mint.

    The id repeats and the ability does not, which is the honest shape: an
    analyser's id is the same on every pull, and what it found is not.
    """
    fights = [
        attempt.encounter.fight_id
        for boss in night.loaded
        for attempt in boss.attempts_with_events
    ]
    findings: dict[int, tuple[Finding, ...]] = {}
    for index, fight_id in enumerate(fights):
        name = f"Rite {index}"
        findings[fight_id] = (
            Finding(
                id=REPEATED_FINDING_ID,
                # The ability's name appears exactly once in the title, which is
                # what `_split_title` needs before it will put the id on the row
                # and let the card draw an icon beside its heading.
                title=f"{name} is what this pull earned a word about",
                ability_id=ROW_ABILITY_IDS[index],
                ability_name=name,
                detail="Drawn on every pull, under the id every pull mints.",
                confidence=Confidence.MEASURED,
                # A loss, so the Summary draws a pointer at the card as well as
                # the card itself. The pointer's href is the other place a
                # finding id becomes a fragment, and a finding with no loss
                # renders no pointer for it to be wrong in.
                seconds_lost=12.0,
            ),
        )
    return findings


FINDING_CARD = re.compile(r'<div class="card" id="[^"]*finding-' + REPEATED_FINDING_ID + '"')
POINTER_AT_IT = re.compile(r'<a class="pointer" href="#[^"]*finding-' + REPEATED_FINDING_ID + '"')
"""The two places one finding id becomes a string in the document: the card's
own element id, and the Summary pointer's fragment link at it. Matched with the
prefix left open, so each says only that the shape was drawn -- whether it was
scoped is the id rules' question, not this one's."""


def a_night_report(
    loaded: LoadedNight | None = None,
    *,
    deep_every_pull: bool = False,
    death_cards: bool = True,
) -> NightReport:
    night = a_loaded_night() if loaded is None else loaded
    every = frozenset(
        attempt.encounter.fight_id
        for boss in night.loaded
        for attempt in boss.attempts_with_events
    )
    return build_night_report(
        night,
        a_nights_findings(night),
        FETCHED,
        A_DEFENSIVE,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=every if deep_every_pull else frozenset(),
        death_cards=death_cards,
        findings_by_boss={
            boss.progression.encounter_id: tuple(analyse_progression(boss))
            for boss in night.loaded
        },
    )


def golden_night_html(deep_every_pull: bool = False) -> str:
    """The page the golden test and the byte-budget pair below pin.

    No icon resolver, matching `golden_raid_html` and `minimal_html`: neither
    of the other two goldens passes one either, so an ability reaches every
    golden page as a bare name rather than a resolved address. `deep_every_pull`
    is the only thing that varies -- the same fixture, read at whichever tier
    the caller needs.
    """
    return render_night(a_night_report(deep_every_pull=deep_every_pull))


def a_night_page() -> str:
    """The trimmed page: the tier every night is drawn at unless `--deep` names one."""
    return golden_night_html()


def a_deep_night_page_with_icons() -> str:
    """Every pull deep, so every pull carries a timeline row naming its own ability.

    A trimmed card holds no timeline and this fixture's deaths carry no killing
    blow id, so the trimmed page resolves no icon at all -- the address rules
    below would pass over it while never meeting an address.
    """
    return render_night(a_night_report(deep_every_pull=True), CdnIcons(ICON_FILES))


def a_night_page_with_no_cards() -> str:
    """The third tier, which no other fixture here draws.

    `--no-deaths` is the only tier whose Deaths tab is empty on a pull that may
    well have had deaths, so it is the only one where the tab's own empty-state
    sentence can be false.
    """
    return render_night(a_night_report(death_cards=False))


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
    assert summaries_on(report) == sum(1 for count in PULLS_PER_BOSS if count >= 2)
    assert html.count('<section class="panel"') == (
        PANELS_PER_PULL * report.total_pulls + PANELS_PER_SUMMARY * summaries_on(report)
    )
    assert TRIMMED_ON_THE_PAGE in html

    # The shapes the id rules below are about, each drawn once per pull and
    # each carrying a string that repeats across pulls: a finding card, the
    # pointer at it, a player slug, and a death card. A page missing any of
    # them would leave that scoping site untested while the rules stayed green.
    assert len(re.findall(FINDING_CARD, html)) == report.total_pulls
    assert len(re.findall(POINTER_AT_IT, html)) == report.total_pulls
    assert html.count('class="player-head"') == len(ROSTER) * report.total_pulls
    assert html.count('class="death-when"') == report.total_pulls

    # And the health curve, which is the only thing that draws a marker or a
    # cover at all: a trimmed card has neither, so the deep page is where those
    # two scoping sites are exercised. Read off the markup's own class names,
    # not off the strings "-mark" and "-cover", which `report.js.j2` also
    # contains -- a guard matching those would pass on the script alone.
    deep = a_deep_night_page_with_icons()
    assert deep.count('class="hp-marker"') >= report.total_pulls
    assert deep.count('class="hp-cover"') >= report.total_pulls


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
    """The other half: a control per boss is worth nothing if all list the night.

    Three bosses holding one, two and three pulls, so a control that offered
    every pull to every boss would read six three times, and one that offered
    the first boss's count to all would read one three times. A boss with a
    summary offers it as one more option beside its pulls.
    """
    report = a_night_report()
    html = render_night(report)

    offered = {
        int(index): body.count("<option") for index, body in PULL_CONTROL.findall(html)
    }
    assert offered == {
        index: count + (1 if boss.summary else 0)
        for index, (count, boss) in enumerate(zip(PULLS_PER_BOSS, report.bosses, strict=True))
    }


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
    assert len(groups) == (
        PANELS_PER_PULL * report.total_pulls + PANELS_PER_SUMMARY * summaries_on(report)
    )
    assert len(set(groups)) == report.total_pulls + summaries_on(report)

    # Every tab bar on the page, not only the seven-panel one. Each pull draws
    # two -- its own sections, and the per-player sub-tabs inside its Players
    # panel -- and a bar whose group name lost its prefix names a group whose
    # panels are still prefixed, so the script finds no button to highlight and
    # the sub-tabs silently stop marking which player is open. No id collides,
    # so the rule above cannot see it. Read off the `<nav>` itself rather than
    # by a bare attribute search, which `report.js.j2` would also answer: the
    # script builds that same attribute selector as a string, and a rule
    # counting those would be counting the script.
    # A summary draws one bar, its own five tabs: the progression page has no
    # per-player sub-tabs.
    bars = re.findall(r'<nav class="tabs[^"]*" data-tab-group="([^"]+)"', html)
    assert len(bars) == 2 * report.total_pulls + summaries_on(report)
    assert len(set(bars)) == len(bars)


def test_no_element_id_appears_twice_across_every_pull() -> None:
    """Finding ids repeat across pulls by design, and DOM ids may not.

    Every pull draws its findings from the same analysers, so the ids inside
    two pulls' reports are the same strings. That is harmless for a map keyed
    by ability id and fatal for an `id=` attribute: a duplicate is invalid HTML
    and sends the page's own links to whichever copy the browser reaches first.

    Both tiers, because they draw different ids. A trimmed card has no run-up
    timeline and no health curve, so the marker, cover and timeline-row ids come
    to the page only at the deep tier -- and every one of those is built from a
    `marker_id` that counts from zero inside each card, which is to say it is
    the same string on every pull.
    """
    for tier, html in (("trimmed", a_night_page()), ("deep", a_deep_night_page_with_icons())):
        element_ids = re.findall(r'\sid="([^"]+)"', html)
        assert element_ids, "a page with no element ids would pass this vacuously"
        duplicates = {value for value in element_ids if element_ids.count(value) > 1}
        assert duplicates == set(), tier


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


def pull_blocks(html: str) -> list[str]:
    """The page cut at its pull boundaries: one string per pull, in page order.

    Cut on the opening tags rather than matched as a balanced element, because
    a pull holds seven `<section>` panels of its own and every one of them
    closes at column zero exactly as the pull does.
    """
    starts = [one.start() for one in re.finditer(r'<section class="pull"', html)]
    assert starts, "the page drew no pull at all"
    ends = [*starts[1:], html.index('<section class="night-notes">')]
    return [html[start:end] for start, end in zip(starts, ends, strict=True)]


SUMMARY_ID = re.compile(r'<section class="pull" data-night-pull-panel id="(b\d+-summary)">')


def summary_blocks(html: str) -> dict[str, str]:
    """Each summary section's markup, keyed by its id, cut where `pull_blocks` cuts."""
    blocks: dict[str, str] = {}
    for block in pull_blocks(html):
        opened = SUMMARY_ID.match(block)
        if opened is not None:
            blocks[opened.group(1)] = block
    return blocks


def test_a_boss_pulled_more_than_once_opens_on_its_summary() -> None:
    """The summary is the first option, so a fresh page, and a boss not yet visited, opens on it."""
    html = a_night_page()
    for index, count in enumerate(PULLS_PER_BOSS):
        control = re.search(
            rf'<select id="night-pull-b{index}" data-night-pull>(.*?)</select>', html, re.S
        )
        assert control is not None
        first = re.search(r'<option value="([^"]+)"', control.group(1))
        assert first is not None
        if count >= 2:
            assert first.group(1) == f"b{index}-summary"
        else:
            assert first.group(1).endswith("-pull"), "a single-pull boss opens on its pull"


def test_exactly_the_bosses_pulled_more_than_once_carry_a_summary_section() -> None:
    html = a_night_page()
    expected = {f"b{i}-summary" for i, count in enumerate(PULLS_PER_BOSS) if count >= 2}
    assert set(summary_blocks(html)) == expected


def test_a_summary_draws_the_progression_tabs_under_its_own_scope() -> None:
    """Five tabs, each button naming a panel inside the same summary."""
    blocks = summary_blocks(a_night_page())
    assert blocks, "the page drew no summary, so this rule was never exercised"
    for scope_id, block in blocks.items():
        scope = scope_id.removesuffix("summary")
        buttons = re.findall(r'data-tab-for="([^"]+)"', block)
        panels = re.findall(r'<section class="panel" data-tab-panel="[^"]+" id="([^"]+)"', block)
        assert buttons == [f"{scope}tab-{name}" for name in
                           ("summary", "attempts", "repeats", "best", "provenance")]
        assert buttons == panels


def test_a_summary_draws_every_progression_finding_its_boss_earned() -> None:
    night = a_loaded_night()
    html = a_night_page()
    blocks = summary_blocks(html)
    for index, boss in enumerate(night.loaded):
        if len(boss.attempts_with_events) < 2:
            continue
        ids = {finding.id for finding in analyse_progression(boss)}
        assert ids, "a fixture boss with no progression finding pins nothing"
        drawn = set(re.findall(rf'id="b{index}-finding-([^"]+)"', blocks[f"b{index}-summary"]))
        assert drawn == ids


def test_a_fragment_link_inside_a_pull_lands_inside_that_same_pull() -> None:
    """Resolving somewhere is not the same as resolving to the right pull.

    Every pull carries a Provenance heading, and so does the night itself, so a
    badge that lost its prefix still points at an anchor that exists -- the
    rule above passes over it -- while sending a reader from pull five's death
    card to a provenance block describing something else. The same goes for a
    Summary pointer, which is a finding id turned into a fragment and would
    open pull one's card from pull five's tab.

    The deep page, because it draws the badges only a health curve and a
    timeline put on a card.

    `#icon-<id>` is the one fragment that legitimately leaves the pull: those
    are the shared SVG symbols in the page's own icon table, defined once for
    every pull to draw from, which is the whole point of a symbol.
    """
    blocks = pull_blocks(a_deep_night_page_with_icons())
    assert len(blocks) == sum(PULLS_PER_BOSS) + summaries_on(a_night_report(deep_every_pull=True))

    checked = 0
    for index, block in enumerate(blocks):
        inside = set(re.findall(r'\sid="([^"]+)"', block))
        targets = [
            href[1:]
            for href in re.findall(r'href="([^"]*)"', block)
            if href.startswith("#") and not href.startswith("#icon-")
        ]
        assert targets, f"pull {index} drew no fragment link, so it proves nothing"
        checked += len(targets)
        for target in targets:
            assert target in inside, f"pull {index} links out to {target}"
    assert checked


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

    Each pull is hit by its own ability and each names another in its own
    finding, so a walk that stopped at the first pull, or at the first boss,
    resolves one or two of these and draws the rest as bare names -- a missing
    picture on a page that otherwise renders, which is the one icon failure
    nothing else here would see.

    Both arms of `_icon_addresses`, and not one: `ABILITY_IDS` reach it through
    a death card's timeline and `ROW_ABILITY_IDS` through a ledger row, which
    are separate loops over separate arguments. Measured -- with only the first,
    handing the row walk an empty tuple failed nothing at all.
    """
    html = a_deep_night_page_with_icons()

    for ability_id in (*ABILITY_IDS, *ROW_ABILITY_IDS):
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
    # The first boss's two drawn pulls earn it a summary, a third option.
    assert report.bosses[0].summary is not None
    assert offered == {0: 3, 1: 1}
    # Guarded like every other loop here: an empty `withheld` would leave the
    # lines below asserting over nothing, on the one fixture whose whole point
    # is that two pulls failed and the page has to say so.
    assert report.provenance.withheld
    for line in report.provenance.withheld:
        assert line in html


def test_the_summary_option_counts_deepened_pulls_not_attempts() -> None:
    """Three attempts, one failed: counted 3, deepened 2, and the label reads the smaller figure.

    `night.html.j2` reads `attempts_deepened` for the option text. Both figures
    live on the same `provenance` object, so a swap to `attempts_counted` would
    still render a page -- just the wrong number on it, one no other test here
    reads closely enough to catch.
    """
    report = a_night_report(a_night(bosses=(3,), failed=(12,)))
    html = render_night(report)

    assert report.bosses[0].summary is not None
    assert report.bosses[0].summary.provenance.attempts_counted == 3
    assert report.bosses[0].summary.provenance.attempts_deepened == 2

    control = re.search(
        r'<select id="night-pull-b0" data-night-pull>(.*?)</select>', html, re.S
    )
    assert control is not None
    first = re.search(r'<option value="([^"]+)">([^<]*)</option>', control.group(1))
    assert first is not None
    assert first.group(2) == "Summary: 2 pulls"


BOSS_OPTION = re.compile(r'<select id="night-boss"[^>]*>(.*?)</select>', re.DOTALL)
OPTION_VALUE = re.compile(r'<option value="([^"]+)"')


def test_each_boss_option_names_a_pull_control_that_exists() -> None:
    """The boss dropdown's other half: what its values are matched against.

    `night.html.j2` writes the option's value and the control's `data-night-for`
    at two separate sites, from two separate `loop.index0` reads, and the script
    compares them by string equality. Swapping either for `loop.index` leaves
    every id unique, every count right and every fragment intact -- and every
    boss the reader picks showing nothing at all.
    """
    html = a_night_page()

    inside = BOSS_OPTION.search(html)
    assert inside is not None, "the page drew no boss control"
    chosen = OPTION_VALUE.findall(inside.group(1))
    controls = re.findall(r'data-night-for="([^"]+)"', html)

    assert len(chosen) == len(PULLS_PER_BOSS)
    assert chosen == controls


def test_each_pull_option_names_a_pull_section_that_exists() -> None:
    """The pull dropdowns' other half, per boss and in order.

    An option's value and the section's id are written at two separate sites
    from one shared prefix, with the literal `pull` appended at each. Dropping
    that literal from either breaks every pull dropdown on the page while
    leaving all the id, count, fragment and script rules green -- there is no
    duplicate, nothing miscounted and no link broken, just a `getElementById`
    that finds nothing.

    Per boss rather than over the page, so a control offering the right number
    of the wrong boss's pulls is a failure too.
    """
    report = a_night_report()
    html = render_night(report)

    drawn = re.findall(r'<section class="pull"[^>]*\sid="([^"]+)"', html)
    assert len(drawn) == report.total_pulls + summaries_on(report)

    offered: list[str] = []
    for index, body in PULL_CONTROL.findall(html):
        values = OPTION_VALUE.findall(body)
        boss = report.bosses[int(index)]
        assert len(values) == PULLS_PER_BOSS[int(index)] + (1 if boss.summary else 0), index
        offered.extend(values)

    # Compared as a list: the sections are drawn in the same boss-then-pull
    # order the controls are, so an option routed to another boss's pull is a
    # failure even though both strings are on the page.
    assert offered == drawn


def test_every_pull_names_its_own_fight_and_the_tier_it_was_drawn_at() -> None:
    """Which pull a reader is looking at, and how deep it was read.

    `night_model.py` argues the tier is what stops a reader comparing a trimmed
    pull with a deep one as though the difference between them were the raid's
    rather than the run's. Deleting the whole sub-line would otherwise fail
    nothing at all.

    Both tiers in one test, from one report each, so a page that printed a
    constant instead of each pull's own tier fails on the mixed expectation.
    """
    for deep in (False, True):
        report = a_night_report(deep_every_pull=deep)
        html = render_night(report)
        every = pull_blocks(html)
        assert len(every) == report.total_pulls + summaries_on(report)
        # A summary names no fight and no tier, so only the pulls' own blocks are read.
        blocks = [block for block in every if SUMMARY_ID.match(block) is None]
        assert len(blocks) == report.total_pulls

        pulls = [pull for boss in report.bosses for pull in boss.pulls]
        for block, pull in zip(blocks, pulls, strict=True):
            # Compared escaped: the fixture's boss names carry an apostrophe,
            # which Jinja's autoescape writes as `&#39;`, so only the escaped
            # form is ever on the page.
            heading = block[block.index("<h2>"):block.index("</p>")]
            assert str(escape(pull.report.header.boss)) in heading
            assert str(escape(pull.report.header.difficulty)) in heading
            assert str(escape(pull.report.header.outcome)) in heading
            assert f"fight {pull.report.provenance.fight_id}" in heading
            assert f"death cards: {pull.tier}" in heading
            assert pull.tier == ("deep" if deep else "trimmed")


def test_a_pull_drawn_with_no_cards_says_so_rather_than_claiming_no_deaths() -> None:
    """"No deaths." is a reading of the log. At this tier it would be a lie.

    A pull built with cards off has an empty `deaths` tuple whether or not
    anybody died, and the death-cost ledger drawn a few lines below it on the
    same tab may be listing what those very deaths cost -- so the page would
    contradict itself on one screen. This is the same family as
    `TRIMMED_CARD_NOTE` and `WITHHELD_DETAIL`: a sentence blaming the log for
    something the run decided.
    """
    report = a_night_report(death_cards=False)
    html = render_night(report)

    assert all(pull.tier == "none" for boss in report.bosses for pull in boss.pulls)
    assert all(
        pull.report.deaths == () for boss in report.bosses for pull in boss.pulls
    )
    assert "No deaths." not in html
    assert html.count(str(escape(NO_CARDS_ASKED))) == report.total_pulls


def test_the_raid_page_still_says_no_deaths_when_the_log_reported_none() -> None:
    """The other half: the sentence is right where it was right, and still drawn.

    `deaths_note` defaults to empty, so a raid page -- and a night pull built
    with cards on that simply had no death -- keeps the reading of the log it
    always had. Without this, emptying the branch entirely would pass the rule
    above.
    """
    html = render_raid(a_minimal_raid_report())

    assert "No deaths." in html
    assert NO_CARDS_ASKED not in html


NIGHT_GOLDEN = Path(__file__).parent / "golden" / "night.html"


def test_the_rendered_night_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = golden_night_html()
    if pytestconfig.getoption("--golden-update"):
        NIGHT_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        NIGHT_GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == NIGHT_GOLDEN.read_text(encoding="utf-8"), (
        "The rendered night report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_night_html_invariants.py --golden-update`."
    )


TRIMMED_NIGHT_BUDGET_BYTES = 95_000
"""Measured 91,642 bytes from `golden_night_html()` on 2026-09-26 -- three bosses,
six pulls, one death apiece, all trimmed, and two boss summaries -- rounded up by
roughly 4%. The same fixture read deep is 116,987 bytes, well past this budget: a
budget with room to spare is a test that cannot fail until the damage is done, so
this one sits close enough to the real figure that a card regaining a field it
lost, or a tier check that stopped trimming, moves it.
"""


def test_a_trimmed_night_stays_inside_its_byte_budget() -> None:
    # Three bosses, six pulls, one death apiece. The budget is deliberately
    # close to the real figure: a budget with room to spare is a test that
    # cannot fail until the damage is done.
    html = golden_night_html()
    assert len(html.encode("utf-8")) < TRIMMED_NIGHT_BUDGET_BYTES


def test_the_budget_would_catch_a_full_card_regression() -> None:
    # The same fixture at the deep tier must exceed the trimmed budget.
    # Without this, a builder that quietly ignores the tier passes the budget
    # test by rendering a small page for the wrong reason.
    html = golden_night_html(deep_every_pull=True)
    assert len(html.encode("utf-8")) > TRIMMED_NIGHT_BUDGET_BYTES
