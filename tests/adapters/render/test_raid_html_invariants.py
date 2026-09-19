# ABOUTME: Whole-page rules for the raid report: the Mythic+ invariants, against a raid page.
# ABOUTME: Seven panels in order, one script, every finding drawn once, and every icon an address.

import re
from pathlib import Path

import pytest
from markupsafe import escape

from tests.adapters.render.test_html_invariants import (
    FORBIDDEN_IN_SCRIPT,
    ICON_HOST,
    NUMBERS_THAT_ARE_NOT_TOTALS,
    is_a_bare_number,
)
from tests.domain.analysis.test_encounter_service import ARCANE_BLAST
from tests.domain.report.test_raid_build import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES, NO_ROLES
from tests.domain.report.test_raid_frame import an_encounter
from tests.domain.report.test_raid_model import raid_view_model_types
from wowperf.adapters.render.html import render_raid
from wowperf.adapters.render.icons import CdnIcons
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
)
from wowperf.domain.comparison.parse_axis import WITHHELD_DETAIL, ParseSubject
from wowperf.domain.comparison.raid_reference import (
    RaidParseRow,
    RankedPlayer,
    ReportRankings,
)
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.targets import TargetRow
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, EnemyCastRow
from wowperf.domain.findings import Confidence, Finding, FindingFact
from wowperf.domain.model import Player
from wowperf.domain.phases import Phase, PhaseTransition
from wowperf.domain.report.model import (
    Badge,
    LedgerRow,
    Provenance,
    ReferenceRecord,
    Section,
    SectionState,
)
from wowperf.domain.report.players import slugs_by_actor
from wowperf.domain.report.raid_build import build_raid_report
from wowperf.domain.report.raid_frame import RaidHeader
from wowperf.domain.report.raid_model import (
    GridCell,
    GridColumn,
    GridRow,
    RaidGrid,
    RaidReport,
    all_raid_ledger_rows,
)
from wowperf.domain.season import DefensiveAbility, Defensives

RAID_PANEL_ORDER = [
    "tab-summary",
    "tab-damage",
    "tab-mechanics",
    "tab-deaths",
    "tab-interrupts",
    "tab-players",
    "tab-provenance",
]
"""The exact seven top-level panel ids, in the order the page draws them.

Nothing in the templates or the renderer counts tabs -- the script matches a
button to a panel by string equality -- so this list is the only place the
count is stated, and a tab added without a line here is a tab no test sees.
"""


def a_raid_header(**overrides: object) -> RaidHeader:
    fields: dict[str, object] = {
        "boss": "Emberkin",
        "difficulty": "Mythic",
        "outcome": "Killed",
        "partition": "Partition 1",
        "size": 20,
    }
    fields.update(overrides)
    return RaidHeader(**fields)  # type: ignore[arg-type]


def a_ledger_row(**overrides: object) -> LedgerRow:
    fields: dict[str, object] = {
        "finding_id": "deaths.total",
        "title": "Two deaths cost the raid a wipe",
        "title_before": "Two deaths cost the raid a wipe",
        "detail": "Both deaths happened during the third intermission.",
        "badge": Badge(label="measured", tint="badge-measured"),
    }
    fields.update(overrides)
    return LedgerRow(**fields)  # type: ignore[arg-type]


def a_minimal_raid_report(**overrides: object) -> RaidReport:
    """The smallest raid report the template can render: every tab empty or withheld.

    A later task builds richer fixtures on top of this one -- see
    `a_raid_report_with_an_ability_only_in` below -- rather than replacing it,
    so keep new fields on top of these defaults instead of removing any.
    """
    fields: dict[str, object] = {
        "header": a_raid_header(),
        "ledger_decomposition": (),
        "damage": Section(state=SectionState.WITHHELD, reason="the attempt did not kill"),
        "deaths": (),
        "interrupts": (),
        "players": (),
        "observations": (),
        "provenance": Provenance(
            report_code="abc123", fight_id=2, fetched_at="2026-09-05 14:02",
        ),
    }
    fields.update(overrides)
    return RaidReport(**fields)  # type: ignore[arg-type]


def a_raid_report_with_an_ability_only_in(field: str, ability_id: int) -> RaidReport:
    """A raid report whose one resolvable ability id sits on a single named field.

    Named by field rather than by scenario, so a later task can reach for any
    of `all_raid_ledger_rows`' fields (or, for `damage_rows`, the tab it feeds)
    without a new fixture. `damage_rows` also needs its `Section` flipped to
    present, or the field would hold a row the Damage tab's own template never
    shows -- a fixture that renders nothing is not one this task's test can
    trust.
    """
    row = a_ledger_row(finding_id=f"finding-with-{field}", ability_id=ability_id)
    updates: dict[str, object] = {field: (row,)}
    if field == "damage_rows":
        updates["damage"] = Section(state=SectionState.PRESENT)
    return a_minimal_raid_report(**updates)


def test_a_raid_report_renders_its_seven_panels() -> None:
    html = render_raid(a_minimal_raid_report())

    assert html.count('<section class="panel"') == len(RAID_PANEL_ORDER)
    for panel in RAID_PANEL_ORDER:
        assert html.count(f'data-tab-for="{panel}"') == 1


def test_an_ability_a_damage_row_names_still_draws_its_icon() -> None:
    """The icon resolver walks the model, so a field it does not walk draws nothing.

    Every other icon failure is loud. This one is a missing picture on a page
    that otherwise renders, which is why the walk is asserted from a row in a
    field only the raid model has.
    """
    ability_id = 12345
    report = a_raid_report_with_an_ability_only_in(field="damage_rows", ability_id=ability_id)

    html = render_raid(report, CdnIcons({ability_id: "spell_holy_divineshield.jpg"}))

    assert f".i-{ability_id}" in html


# The fixture above renders every panel empty or withheld, which is what Task 9
# needed of it and is exactly the page most of the rules below would pass on
# while checking nothing: no finding to draw once, no pointer to resolve, no
# player card, no reference link. What follows is the other end -- a report the
# builder actually assembled out of findings, a death and a reference, the raid
# counterpart of `rich_report()` next door -- so the rules are asserted against
# the page a reader is handed.

EMBERKIN = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700)
STONEWAKE = Player(
    actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=690
)
BRIALA = Player(actor_id=3, name="Bríala", class_name="Priest", spec="Discipline", item_level=685)
A_RAID = (EMBERKIN, STONEWAKE, BRIALA)

EMBERKIN_SLUG = "emberkin-0"
STONEWAKE_SLUG = "stonewake-1"
BRIALA_SLUG = "briala-2"
"""The slugs `slugs_by_actor` mints for the roster above, in that order.

Written out rather than computed, because the comparison findings below spell
the same slugs into their ids and a fixture that derived both from one call
could not tell a card from the finding that is supposed to land on it.
"""

COMPARED = frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG})
"""Who the fixture's comparison was asked for: two of the three raiders.

Two, so two cards carry the same comparison families under a slug each and a
colliding element id between them is a page the uniqueness rule below can
actually see. The third is deliberately left out, so the same page also carries
a card in the not-requested state, which is the page's other `withheld` shape.
"""

KILLING_BLOW_ID = 1214628
"""The one ability id the fixture puts on the page, on the death's killing blow.

An id is what makes an icon resolvable at all, and `DeathCard.killing_blow_id`
is the first thing `_icon_addresses` walks -- so the icon rules below are proved
against art the page really drew rather than against a fixture that drew none.
"""

FIGHT_START_MS = 1_000_000
DEATH_MS = 1_150_000
FIGHT_END_MS = 1_300_000

A_REFERENCE = ReferenceRecord(
    report_code="ref001",
    fight_id=7,
    keystone_level=0,
    url="https://www.warcraftlogs.com/reports/ref001?fight=7",
    axis="parse",
    player_slug=EMBERKIN_SLUG,
    player_name="Emberkin",
)
"""One candidate, so the page carries a Warcraft Logs href at all.

Without it the href rule below would prove only that badge fragments start with
`#`, and a remote address drawn in the Provenance list would never be met.
`keystone_level` is zero and goes unread: `_raid_provenance.html.j2` prints no
per-row difficulty, because the rankings query already asked for one.
"""


def a_raid_fight(kill: bool = True) -> LoadedEncounter:
    """One boss fight with one death, on a log that begins well after zero.

    The start is not zero on purpose, the same reason `test_raid_build`'s own
    fixture gives: a death's elapsed time is measured from it, and a fixture
    starting at zero cannot tell a reading of the fight's start apart from a raw
    timestamp.
    """
    return LoadedEncounter(
        encounter=an_encounter(
            boss_name="The Twin Fangs",
            players=A_RAID,
            kill=kill,
            fight_percentage=0.0 if kill else 12.4,
            start_ms=FIGHT_START_MS,
            end_ms=FIGHT_END_MS,
        ),
        deaths=(
            Death(
                actor_id=2,
                player_name="Stonewake",
                timestamp_ms=DEATH_MS,
                killing_blow="Ravenous Feast",
                killing_blow_id=KILLING_BLOW_ID,
            ),
        ),
    )


def a_raids_findings() -> tuple[Finding, ...]:
    """One finding on each tab that holds them, plus one no placement claims.

    Every title differs from every other, which the once-only rule below needs:
    two findings that happened to share a sentence would render two identical
    headings, and a heading counted twice would read as a finding drawn twice.
    """
    return (
        Finding(
            id="deaths.total",
            title="Deaths cost the raid three minutes",
            detail="Every one of them inside the third intermission.",
            confidence=Confidence.MEASURED,
            seconds_lost=180.0,
        ),
        # Nests inside the finding above by `NESTS_INSIDE`, and carries a figure,
        # so it is also what the Summary points at.
        Finding(
            id="deaths.single.0",
            title="The death in the third intermission was the expensive one",
            detail="It came before the add wave was down.",
            confidence=Confidence.MEASURED,
            seconds_lost=95.0,
            evidence=("the raid was at full strength until it",),
        ),
        Finding(
            id="mechanics.ravenous-feast",
            title="Ravenous Feast reached the raid on every cast",
            detail="Nobody left the pool before the cast finished.",
            confidence=Confidence.DERIVED,
        ),
        Finding(
            id="interrupts.summary",
            # Apostrophe and ampersand on purpose: Jinja's autoescape turns an
            # apostrophe into `&#39;`, so only an escaped comparison can tell an
            # escaped heading from one a hypothetical `|safe` let through unchanged.
            title="The raid let Death's Advance & Ice Block go uninterrupted",
            detail="Grouped by spell.",
            confidence=Confidence.DERIVED,
        ),
        Finding(
            id=f"compare.damage.total.{EMBERKIN_SLUG}",
            title="The Mage's damage sits under the sample's median",
            detail="Against five kills of the same boss at the same difficulty.",
            confidence=Confidence.DERIVED,
            player_slug=EMBERKIN_SLUG,
        ),
        # Two raiders' comparison findings, in the same two families under a slug
        # each. Every id in these families is minted by appending the raider to a
        # family name the comparison modules share, so this pair is the shape a
        # lost suffix would collide in.
        Finding(
            id=f"compare.talents.{EMBERKIN_SLUG}",
            title="The Mage's talents differ from the sample's in two nodes",
            detail="Both differences sit in the class tree.",
            confidence=Confidence.DERIVED,
            player_slug=EMBERKIN_SLUG,
        ),
        Finding(
            id=f"compare.spells.missing.0.{EMBERKIN_SLUG}",
            title="The Mage cast no Combustion on the boss",
            detail="The sample cast it twice in the same window.",
            confidence=Confidence.MEASURED,
            player_slug=EMBERKIN_SLUG,
        ),
        Finding(
            id=f"compare.talents.{STONEWAKE_SLUG}",
            title="The Death Knight's talents differ from the sample's in one node",
            detail="The difference sits in the specialisation tree.",
            confidence=Confidence.DERIVED,
            player_slug=STONEWAKE_SLUG,
        ),
        Finding(
            id=f"compare.spells.missing.0.{STONEWAKE_SLUG}",
            title="The Death Knight cast no Dancing Rune Weapon on the boss",
            detail="The sample cast it once in the same window.",
            confidence=Confidence.MEASURED,
            player_slug=STONEWAKE_SLUG,
        ),
        # A family `RAID_PLACEMENTS` deliberately omits -- a boss fight has no
        # route -- so the Summary's catch-all has something to catch.
        Finding(
            id="compare.confound.difficulty",
            title="Two of the five references were fought at a lower difficulty",
            detail="Read the damage comparison with that in mind.",
            confidence=Confidence.INFERRED,
        ),
    )


def a_wipes_findings() -> tuple[Finding, ...]:
    """The same findings on an attempt that did not kill, which has no damage rows.

    `compare.parse.unavailable.<slug>` is what `compare_parse_axis` emits for
    each raider then, and it carries `WITHHELD_DETAIL` itself rather than a
    paraphrase: the reason the Damage tab prints has to be the comparison's own
    sentence, and a fixture that invented one could not tell whether the builder
    quoted it or wrote its own.
    """
    return (
        *(one for one in a_raids_findings() if not one.id.startswith("compare.damage.")),
        *(
            Finding(
                id=f"compare.parse.unavailable.{slug}",
                title=f"No comparison against other kills is available for {who}",
                detail=WITHHELD_DETAIL,
                confidence=Confidence.MEASURED,
                player_slug=slug,
            )
            for slug, who in ((EMBERKIN_SLUG, "the Mage"), (STONEWAKE_SLUG, "the Death Knight"))
        ),
    )


def a_built_raid_report(
    kill: bool = True,
    findings: tuple[Finding, ...] | None = None,
    compared: frozenset[str] | None = COMPARED,
) -> RaidReport:
    return build_raid_report(
        a_raid_fight(kill=kill),
        a_raids_findings() if findings is None else findings,
        EMBERKIN,
        compared,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        reference_records=(A_REFERENCE,),
    )


def a_raid_page() -> str:
    return render_raid(a_built_raid_report())


def a_raid_page_with_an_icon() -> str:
    """The same page with its one ability id resolved to an address.

    `a_raid_page()` is rendered with no `icons` argument at all, so it can never
    contain a resolved icon -- the address-scoping rules below would still pass
    over it even if a future edit drew a remote address, because nothing there
    renders one to catch. This fixture actually resolves one.
    """
    return render_raid(
        a_built_raid_report(), CdnIcons({KILLING_BLOW_ID: "spell_holy_divineshield.jpg"})
    )


def a_wiped_raid_page() -> str:
    return render_raid(a_built_raid_report(kill=False, findings=a_wipes_findings()))


A_VERDICT_FINDING = Finding(
    id="wipe.cause",
    title="This attempt failed on execution: the raid was taken apart",
    detail="12 of 20 died against a reference median.",
    confidence=Confidence.INFERRED,
)
"""The smallest real verdict `classify_attempt` could hand back, id and shape
both -- `a_wipes_findings` alone carries no `wipe.cause`, so nothing else in
this file already renders the block `_raid_summary.html.j2` guards on
`report.verdict`."""


def a_wiped_raid_page_with_a_verdict() -> str:
    return render_raid(
        a_built_raid_report(kill=False, findings=(*a_wipes_findings(), A_VERDICT_FINDING))
    )


MARKUP = re.compile(r"<[^>]*>")

FINDING_HEADING = re.compile(
    r'<div class="card" id="finding-[^"]*">\s*<div class="row-head">\s*<h3>(.*?)</h3>', re.DOTALL
)
"""One finding card's heading, scoped to finding cards alone.

A death card carries an `<h3>` too -- the killing blow and who it killed -- and
so does every player card, so an unscoped search for headings would count
shapes that are not findings at all. Read out of the markup rather than off the
view model, because whether a row reached the page is the question.
"""


def finding_headings(html: str) -> list[str]:
    """Every finding heading the page drew, with the icon markup taken back out.

    A heading that names an ability is rendered in three pieces around an
    `ability` span, so the tags come out before the heading is compared with the
    finding's own title. Escaped text survives: `&#39;` is not a tag.
    """
    return [MARKUP.sub("", heading).strip() for heading in FINDING_HEADING.findall(html)]


def test_the_built_fixture_actually_exercises_what_it_claims_to() -> None:
    """Guards every rule below against a fixture that quietly went empty.

    The rules that follow are only meaningful if the page they render truly
    contains every shape they assert about, and this repository's failure mode
    is a test that could never have failed. Each line here is the precondition
    of a test below, stated once so a fixture that drifts fails here by name
    rather than leaving four assertions green over nothing.
    """
    html = a_raid_page()
    assert html.count('class="player-head"') == len(A_RAID)
    assert 'class="pointer"' in html
    assert "Already counted inside" in html
    # The raider nobody asked for, whose card is the page's own `withheld` block.
    assert f'id="player-{BRIALA_SLUG}"' in html
    assert 'class="withheld"' in html
    assert finding_headings(html)

    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith("#") for href in hrefs)
    assert any(href.startswith("https://www.warcraftlogs.com/reports/") for href in hrefs)

    # Same guard for the icon fixture: proves it resolves an icon rather than
    # passing the scoping rules below by never drawing an address at all.
    icon_hrefs = re.findall(r'href="([^"]*)"', a_raid_page_with_an_icon())
    assert any(href.startswith(ICON_HOST) for href in icon_hrefs)

    # And for the wipe, whose Damage tab is the one section 13 names as a risk.
    assert WITHHELD_DETAIL in a_wiped_raid_page()


def test_the_page_executes_only_its_own_script() -> None:
    # A Warcraft Logs reference link and the SVG's own namespace attribute both
    # legitimately contain "http://" without fetching anything, so
    # self-containment is checked by what the page can *execute* or *load*, not
    # by whether the string appears at all. One inline script is allowed, and
    # only one: the tab toggle. Its text is checked for anything that could
    # reach past showing and hiding. `FORBIDDEN_IN_SCRIPT` is imported rather
    # than retyped, so one tuple governs both pages.
    html = a_raid_page()
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
    # Finding ids contain dots (e.g. "finding-deaths.single.0"); querySelector("#" + id)
    # would parse the dot as a class selector, so the lookup must stay getElementById.
    assert "getElementById" in body


def test_every_href_is_a_fragment_a_report_link_or_an_icon_address() -> None:
    # A resolved icon is drawn as an SVG <image href>, not only as a CSS
    # background: this is the one other shape an href is allowed to take. The
    # page here resolves no icon, so the icon arm of the rule is proved by the
    # fixture that does -- see the scoping rule below.
    html = a_raid_page()
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith("#") for href in hrefs)
    assert any(href.startswith("https://www.warcraftlogs.com/reports/") for href in hrefs)
    for href in hrefs:
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ) or href.startswith(ICON_HOST), href


def test_every_href_stays_scoped_even_when_an_icon_resolves() -> None:
    # The three-prefix rule above is proved against a page that resolves no icon
    # at all, so a future edit drawing `<image href="https://…">` would pass it
    # silently. This applies the same rule to the page that actually resolves one.
    html = a_raid_page_with_an_icon()
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith(ICON_HOST) for href in hrefs)
    for href in hrefs:
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ) or href.startswith(ICON_HOST), href


def test_every_image_address_the_page_draws_points_at_the_icon_host() -> None:
    # The script rule checks `src` attributes; an icon reaches the page through a
    # CSS url() and an SVG <image href> instead, neither of which that check
    # sees. Icons are the only thing the report may load, and one host is the
    # only place it may load them from.
    html = a_raid_page_with_an_icon()
    drawn = re.findall(r"url\(([^)]*)\)", html)
    assert drawn, "the fixture resolved no icon, so this rule was never exercised"
    for address in drawn:
        assert address.startswith(ICON_HOST), address


def test_a_resolved_icon_reaches_the_page_as_an_address_never_as_embedded_bytes() -> None:
    # The page carries no image bytes of its own. Embedding is what turned a
    # report into a self-contained copy of Blizzard's art, and it is what this
    # asserts has not come back -- a regression no other rule here would see,
    # because embedded bytes satisfy every scoping rule above perfectly well.
    html = a_raid_page_with_an_icon()
    assert f"url({ICON_HOST}spell_holy_divineshield.jpg)" in html
    assert "data:image" not in html


def test_the_page_hides_nothing_before_the_script_runs() -> None:
    # Without the script the root class is absent, so every hiding rule must be
    # scoped under it. Two bare rules are hidden *without* the script: `.tabs`,
    # which the script un-hides by adding the root class, and `.tip`, which
    # needs no script at all -- a hover panel that CSS alone reveals on
    # `:hover`/`:focus-within` and hides the rest of the time.
    html = a_raid_page()
    assert not re.search(r"<[^>]*\shidden[\s>=]", html)
    assert not re.search(r'style="[^"]*display', html)
    style = html[html.index("<style>"):html.index("</style>")]
    hiding = list(re.finditer(r"([^{}]+)\{[^{}]*display:\s*none", style))
    assert hiding, "the stylesheet hides nothing at all, so this rule went unexercised"
    for rule in hiding:
        selector = rule.group(1).strip().splitlines()[-1].strip()
        assert selector.startswith(".js ") or selector in (".tabs", ".tip"), selector


PANEL_ID = re.compile(r'<section class="panel"[^>]*\sid="([^"]+)"')
"""Each top-level panel's own id, in the order the page draws them.

Read off the `<section>` itself rather than counted, and read as an id rather
than as a tag: a panel whose id was misspelled in its own partial still counts
as a section, still gets a nav button pointing at the name nobody renamed, and
clicks through to nothing. A tab is two hand-written halves matched only by
string equality, and this is the half that names the panel.
"""

MAIN_NAV = re.compile(r'<nav class="tabs" data-tab-group="main"[^>]*>(.*?)</nav>', re.DOTALL)
"""The page's top-level tab bar, and not the per-player one nested inside the
Players panel -- that one is `class="tabs subtabs"` and carries its own group."""

TAB_TARGET = re.compile(r'data-tab-for="([^"]+)"')


def main_tab_targets(html: str) -> list[str]:
    """What each top-level nav button claims to open, in the order drawn."""
    nav = MAIN_NAV.search(html)
    assert nav is not None, "the page drew no top-level tab bar at all"
    return TAB_TARGET.findall(nav.group(1))


def test_every_panel_appears_once_in_tab_order() -> None:
    """The seven panels, by the ids they actually render, in the order they render.

    Stronger than counting `<section class="panel"` on its own, which a panel
    with a misspelled id passes: the count is right, the order is right, and the
    button pointing at the name nobody renamed opens nothing. Compared as a list
    so a missing panel, a duplicated one, a renamed one and a reordered one are
    each a failure, and `RAID_PANEL_ORDER` stays the one place the count is stated.

    The count is kept beside the list rather than dropped for it, because the two
    cover different halves. `PANEL_ID` reads only sections that carry an id, so
    an eighth panel written without one is a section the list equality never
    sees: the ids it did find are still the right seven in the right order. The
    list says the ids are right; the count says there are no others.
    """
    html = a_raid_page()
    panels = PANEL_ID.findall(html)

    assert panels, "the page drew no panels at all"
    assert panels == RAID_PANEL_ORDER
    assert html.count('<section class="panel"') == len(RAID_PANEL_ORDER)


def test_every_panel_has_exactly_one_tab_button() -> None:
    """Both directions, because either alone leaves the other half unchecked.

    A panel with no button is unreachable; a button naming a panel that does not
    exist is a click that does nothing. Counting `data-tab-for` occurrences
    would see neither, since every count would be of the buttons themselves.
    """
    html = a_raid_page()
    panels = PANEL_ID.findall(html)
    assert panels, "the page drew no panels at all"

    for name in RAID_PANEL_ORDER:
        assert html.count(f'data-tab-for="{name}"') == 1, name
    assert set(main_tab_targets(html)) == set(panels)


def test_the_tab_buttons_follow_panel_order() -> None:
    # The script opens the first button's panel by default, so button order is
    # the default tab; nothing else pins the order the buttons appear in.
    assert main_tab_targets(a_raid_page()) == RAID_PANEL_ORDER


def test_the_root_class_the_script_adds_is_not_in_the_markup() -> None:
    # The script adds it at run time; rendering it would hide panels with no script.
    # This is the other half of the rule above it: `.tabs` is hidden until the
    # root class arrives, so a page that shipped the class already would hide
    # every panel but one for a reader whose browser runs no script -- and the
    # raid page inherits exactly that stylesheet.
    html = a_raid_page()
    assert '<html lang="en">' in html
    assert 'class="js' not in html


def test_no_element_id_appears_twice() -> None:
    # The companion to `test_no_finding_reaches_the_page_twice`, which compares
    # headings and so cannot see two findings that share an id. A duplicate
    # element id is invalid HTML and sends the page's own pointer to whichever
    # of the two the browser happens to pick.
    html = a_raid_page()
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicates == set()


def test_every_finding_reaches_the_page() -> None:
    # Compared against the escaped title: the template renders it through Jinja's
    # autoescape (markupsafe.escape), which turns an apostrophe into `&#39;`.
    headings = finding_headings(a_raid_page())
    assert headings, "the page drew no finding at all, so this proves nothing"
    for finding in a_raids_findings():
        assert str(escape(finding.title)) in headings, finding.id


def test_no_finding_reaches_the_page_twice() -> None:
    # Anchored to the row heading, not to the bare title text: a nested row
    # legitimately quotes its parent's title in "Already counted inside ...",
    # and a Summary pointer legitimately repeats it as a link, neither of which
    # is a second copy of the row.
    headings = finding_headings(a_raid_page())
    for finding in a_raids_findings():
        assert headings.count(str(escape(finding.title))) == 1, finding.id


def test_every_pointer_targets_an_anchor_that_exists() -> None:
    html = a_raid_page()
    targets = re.findall(r'class="pointer" href="#([^"]+)"', html)
    assert targets, "the fixture has a timed death, so the Summary must point at it"
    for target in targets:
        assert f'id="{target}"' in html, target


def test_a_pointer_is_a_link_not_a_second_card() -> None:
    # Once-only is anchored on the finding card's <h3>; a pointer that emitted
    # one would double every loss it points at.
    html = a_raid_page()
    pointers = re.findall(r'<a class="pointer"[^>]*>(.*?)</a>', html, flags=re.S)
    assert pointers
    for body in pointers:
        assert "<h3>" not in body
    headings = finding_headings(html)
    for finding in a_raids_findings():
        assert headings.count(str(escape(finding.title))) == 1, finding.id


def test_no_empty_findings_wrappers_render() -> None:
    # The .findings grid renders nothing when empty. Empty wrappers are dead
    # markup that prove unconditional wrappers exist where they should be
    # guarded. Both forms are covered: panel sections use 0 indent, the per-raider
    # blocks inside a card use 2.
    assert '<div class="findings">' in a_raid_page(), (
        "the fixture drew no findings grid at all, so this rule was never exercised"
    )
    for html in (a_raid_page(), a_wiped_raid_page(), render_raid(a_minimal_raid_report())):
        assert '<div class="findings">\n</div>' not in html
        assert re.search(r'  <div class="findings">\n  </div>', html) is None


def test_every_withheld_section_gives_a_reason() -> None:
    """A section that shows nothing has to say why, in the comparison's own words.

    Design section 13 names the empty Damage tab as a risk by itself: a reader
    who meets a blank panel concludes the tool measured nothing, when what
    happened is that Warcraft Logs ranks kills and this attempt was not one.
    """
    html = a_wiped_raid_page()
    panel = html[html.index('id="tab-damage"'):html.index('id="tab-mechanics"')]

    withheld = re.search(r'<p class="withheld">(.*?)</p>', panel, flags=re.S)
    assert withheld is not None, "the Damage tab was withheld and said nothing"
    assert withheld.group(1).strip() == str(escape(WITHHELD_DETAIL))


def test_a_raid_report_with_no_mechanics_rows_states_nothing_to_report() -> None:
    """`mechanics_rows` empties out for real: `--no-compare` guarantees no
    reference sample, and a fight with no damage outlier emits no row either.
    Every sibling panel that can empty out says so -- Route and Interrupts
    print "Nothing to report.", and the Damage tab has its own withheld
    branch -- so Mechanics must not go silent instead of joining them.
    """
    html = render_raid(a_minimal_raid_report())
    panel = html[html.index('id="tab-mechanics"'):html.index('id="tab-deaths"')]
    assert "Nothing to report." in panel


def test_a_deathless_kill_opens_the_summary_with_no_bare_decomposition_heading() -> None:
    """`RAID_DECOMPOSITION_IDS` is `("deaths.total",)` alone, so a boss killed
    with zero deaths -- the best possible raid outcome -- carries no
    `ledger_decomposition` at all. The heading and the "Not additive" caveat
    must not render over figures that are not there.
    """
    html = render_raid(a_minimal_raid_report())
    panel = html[html.index('id="tab-summary"'):html.index('id="tab-damage"')]
    assert "Figures that contain others" not in panel
    assert "Not additive" not in panel


def test_a_wipe_with_a_verdict_draws_it_as_the_summary_headline() -> None:
    """Design section 6's testing requirement, held at the render layer.

    `test_raid_build.py`'s verdict tests check `RaidReport.verdict` itself and
    never the HTML `_raid_summary.html.j2` draws from it, so a typo in
    `report.verdict`, a `ledger_row` call built with the wrong argument, or the
    `{% if report.verdict %}` guard being deleted outright would all still
    leave the whole suite green. `a_wiped_raid_page()` cannot stand in for this:
    `a_wipes_findings()` carries no `wipe.cause`, so its page never exercises
    the guard either -- see `a_wiped_raid_page_with_a_verdict` above.
    """
    html = a_wiped_raid_page_with_a_verdict()
    panel = html[html.index('id="tab-summary"'):html.index('id="tab-damage"')]

    assert "Why this attempt ended" in panel
    assert str(escape(A_VERDICT_FINDING.title)) in panel


def a_full_roster(size: int) -> tuple[Player, ...]:
    """A roster of `size` raiders, two of whom reduce to one slug on their own.

    The names are the sanctioned ones plus a roster index, except for the last
    pair: `Bríala` and `Briala`, the accent-stripped spelling CLAUDE.md sanctions
    for exactly this -- two distinct display names that `player_slug` reduces to
    `briala`. Without a pair like it nothing on the page would collide when the
    index `slugs_by_actor` appends goes missing, and the test below could not see
    it go. The indexed names must stay distinct from each other for the same
    reason in reverse: `display_names` rewrites any name two raiders share, which
    would pull them apart again before the slug is ever minted.
    """
    kit = (("Mage", "Arcane"), ("DeathKnight", "Blood"), ("Priest", "Discipline"),
           ("Druid", "Balance"))
    names = [f"Emberkin {index + 1}" for index in range(size - 2)]
    names.extend(("Bríala", "Briala"))
    return tuple(
        Player(
            actor_id=index + 1,
            name=name,
            class_name=kit[index % len(kit)][0],
            spec=kit[index % len(kit)][1],
            item_level=700,
        )
        for index, name in enumerate(names)
    )


def a_raid_report_with(raiders: int, compared: int) -> RaidReport:
    """A raid report of `raiders` cards, `compared` of them carrying rows.

    The comparison findings take their slugs from `slugs_by_actor` itself, which
    is how the analysis mints them: a fixture that spelled its own would still
    route rows to cards on a page where the two had stopped agreeing.
    """
    roster = a_full_roster(raiders)
    slugs = slugs_by_actor(roster)
    in_order = [slugs[player.actor_id] for player in roster]
    findings = tuple(
        Finding(
            id=f"compare.talents.{slug}",
            title=f"Raider {index + 1}'s talents differ from the sample's",
            detail="The difference sits in the class tree.",
            confidence=Confidence.DERIVED,
            player_slug=slug,
        )
        for index, slug in enumerate(in_order[:compared])
    )
    return build_raid_report(
        LoadedEncounter(
            encounter=an_encounter(
                boss_name="The Twin Fangs",
                players=roster,
                start_ms=FIGHT_START_MS,
                end_ms=FIGHT_END_MS,
            )
        ),
        findings,
        roster[0],
        frozenset(in_order[:compared]),
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
    )


def test_a_full_roster_collides_no_element_ids() -> None:
    """Twenty raiders is where a suffix that failed to distinguish anybody shows.

    Two would pass a suffix that appended a constant. The offline sibling of
    the e2e test that costs quota -- this one is free and runs on every push.

    A suffix lost from `slugs_by_actor` itself is caught one step earlier than
    this assertion, and on purpose: the fixture mints its finding ids from that
    same function, as the analysis does, so two raiders sharing a slug reach
    `_check_unique_finding_ids` before they reach the page. Measured, not
    assumed -- the mutation raises there rather than failing below. What proves
    the assertion itself can fail is a card id that stopped naming its raider,
    which the builder has no way to see.
    """
    report = a_raid_report_with(raiders=20, compared=20)

    html = render_raid(report)

    # Counted on the page and not on the model, the same guard the three-raider
    # fixture above states: twenty cards the builder made and the template never
    # drew would leave the assertion below passing over the panel ids alone, on
    # a page carrying none of the collisions this test exists to look for.
    assert html.count('class="player-head"') == 20, "the page drew fewer cards than that"
    element_ids = re.findall(r'\sid="([^"]+)"', html)
    assert element_ids, "a page with no element ids would pass this vacuously"
    duplicates = {value for value in element_ids if element_ids.count(value) > 1}
    assert duplicates == set()


def test_the_raid_report_carries_no_total_row() -> None:
    """No field on the raid view model is a bare number that could hold a total.

    The Mythic+ sibling of this rule walks `view_model_types()`, which
    enumerates the classes `report.model` defines and therefore cannot see the
    raid model at all -- so until this existed, a raid view model could grow a
    bare `int` and no test would notice. The allowlist is the same one, imported
    rather than copied: `(RaidHeader, "size")` already sits on it, and a raid
    entry belongs there for the same reason a Mythic+ one does.

    The template half of the Mythic+ rule is not repeated here. It globs every
    `*.j2` under the render directory, so the raid partials are already covered
    by it the day they exist.
    """
    types = raid_view_model_types()
    assert types, "the scan found no raid view model types, so this proves nothing"
    assert not any(field.startswith("total") for field in RaidReport.model_fields)

    for model_type in types:
        for field_name, field in model_type.model_fields.items():
            if is_a_bare_number(field.annotation):
                assert (model_type, field_name) in NUMBERS_THAT_ARE_NOT_TOTALS, (
                    f"{model_type.__name__}.{field_name} is a numeric field with no entry "
                    "on the allowlist explaining why it cannot hold a total"
                )


# Every fixture above renders from `Finding` literals, which is right for rules
# about markup and wrong for a file that pins sentences: a hand-written title is
# only ever pinned to itself. The Mythic+ golden fixture is exactly that -- it
# passes `None` for its speed sample and writes its comparison rows out by hand,
# so no `compare.*` family reaches the page it renders and a wording mutation
# inside one of those sentences leaves the Mythic+ golden test green. That was
# found by mutation during plan 3a, after the file had been cited as proof in
# three separate review briefs.
#
# What follows is the other thing. `a_real_raid_comparison` calls
# `analyse_encounter` -- the real service, the real comparison modules, the real
# per-raider minting -- against two compared raiders, a five-member parse sample
# and two leaderboards each, so every comparison sentence in `raid.html` was
# written by the code the golden file is supposed to pin.

RAID_GOLDEN = Path(__file__).parent / "golden" / "raid.html"

COMBUSTION = 190319
DEATH_STRIKE = 49998
DANCING_RUNE_WEAPON = 49028
ARCANE_INTELLECT = 1459
BONE_SHIELD = 195181
VOID_BOLT = 451288
"""Ability ids the fixture's casts, auras and enemy casts are keyed on.

Named rather than inlined because each is spelled on both sides of a comparison
-- ours and the reference's -- and a comparison joins two streams on the same
id. A typo in one of two literals would quietly become a spell the reference
cast and we never did.
"""

REFERENCE_SECONDS = 240.0
"""Every reference kill's own boss time, which its rates are stated over.

Shorter than this fight's 300 seconds on purpose: a rate is casts per minute on
both sides, and two sides sharing a denominator could not tell a rate apart from
a count.
"""

ARCANE_BUILD = "CQUAmqWgLuBtT1EJyqZrqqIn6Jzs5AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
BLOOD_BUILD = "C4PAj7pKoDmTBWCX9ppIkB0MjZmZmZMzMzMYmZmZmZGmZmZmZMzMzMzAAAAAAAA"
REFERENCE_ARCANE_BUILD = "CQUAmqWgLuBtT1EJyqZrqqIn6Jzs5AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB"
REFERENCE_BLOOD_BUILD = "C4PAj7pKoDmTBWCX9ppIkB0MjZmZmZMzMzMYmZmZmZGmZmZmZMzMzMzAAAAAAAB"
"""Four opaque talent strings, each differing from its counterpart in one place.

`compare_talents` compares the two strings and never reads either, so what
matters is that ours and theirs differ -- which is what makes the finding say
the builds differ rather than that one of the two reports carries no string.
"""

GOLDEN_ROSTER = (
    EMBERKIN.model_copy(update={"talent_import_string": ARCANE_BUILD}),
    STONEWAKE.model_copy(update={"talent_import_string": BLOOD_BUILD}),
    BRIALA,
)
"""`A_RAID` with a build on the two raiders a comparison is asked for.

Copied rather than added to `A_RAID` itself, which every fixture above renders
and none of which compares a build. Bríala carries none because nobody asked to
compare her, which is the same reason her card is the page's `withheld` block.
"""


def _casts(
    actor_id: int, ability_id: int, name: str, count: int, first_ms: int
) -> tuple[CastEvent, ...]:
    """`count` casts of one ability, two seconds apart, from `first_ms`.

    The spacing is read by nothing -- every raid rate counts the whole stream
    and divides by the fight -- so it exists only to keep two casts of one
    ability from sharing a timestamp.
    """
    return tuple(
        CastEvent(
            actor_id=actor_id,
            ability_id=ability_id,
            ability_name=name,
            timestamp_ms=first_ms + one * 2_000,
        )
        for one in range(count)
    )


ARCANE_BLASTS = (12, 13, 14, 15, 16)
ARCANE_INTELLECT_MS = (190_000, 195_000, 200_000, 205_000, 210_000)
DEATH_STRIKES = (22, 23, 24, 25, 26)
BONE_SHIELD_MS = (210_000, 215_000, 220_000, 225_000, 230_000)
"""One value per reference, so no sample the page states a median of is flat.

Five identical references produce a median that equals the minimum, the maximum
and every member, so a bug returning any of those instead of the middle would
leave every sentence on the page unchanged -- and the golden file would go on
being cited as proof the medians are right. That is the Mythic+ golden's defect
one level down, and it is why every one of these is a spread rather than a
constant. Each is centred on the value the sentences already stated, so the
medians the page prints are unchanged and only the ranges stop being degenerate.
"""


def an_arcane_reference(index: int) -> ParseMember:
    """One reference parse for the Mage: two abilities and one buff.

    Arcane Blast is cast by both sides at rates far enough apart to report;
    Combustion is cast by every reference and by our Mage never, which is the
    other verdict `compare_spells_sample` can reach. The buff is up over most of
    the reference's boss time and a fifth of ours, which is the gap
    `compare_uptime_sample` reports.

    Combustion alone is held at the same count across the five: the verdict it
    produces counts how many references cast it at all, states no rate and no
    range, and there is nothing for a spread to make visible.
    """
    them = Player(
        actor_id=90, name="Кириллица", class_name="Mage", spec="Arcane",
        item_level=710, talent_import_string=REFERENCE_ARCANE_BUILD,
    )
    uptime_ms = ARCANE_INTELLECT_MS[index]
    return ParseMember(
        character_name="Кириллица",
        report_code=f"ARC{index}",
        fight_id=index + 1,
        boss_seconds=REFERENCE_SECONDS,
        players=(them,),
        casts=(
            *_casts(90, ARCANE_BLAST, "Arcane Blast", ARCANE_BLASTS[index], 0),
            *_casts(90, COMBUSTION, "Combustion", 4, 40_000),
        ),
        auras=PlayerAuras(
            actor_id=90,
            on_self=(
                Aura(
                    ability_id=ARCANE_INTELLECT, name="Arcane Intellect",
                    total_uptime_ms=uptime_ms, uses=1,
                    bands=(AuraBand(start_ms=0, end_ms=uptime_ms),),
                ),
            ),
        ),
    )


def a_blood_reference(index: int) -> ParseMember:
    """One reference parse for the Death Knight, shaped like the Mage's.

    Death Strike is cast at the same rate on both sides, so the only spell
    verdict this raider draws is the ability the references press and she does
    not. Her own Bone Shield sits inside the gap threshold of theirs, so her
    card carries no uptime row -- two raiders whose comparisons differ is what
    the page is for.
    """
    them = Player(
        actor_id=91, name="Кириллица", class_name="DeathKnight", spec="Blood",
        item_level=705, talent_import_string=REFERENCE_BLOOD_BUILD,
    )
    uptime_ms = BONE_SHIELD_MS[index]
    return ParseMember(
        character_name="Кириллица",
        report_code=f"BLD{index}",
        fight_id=index + 1,
        boss_seconds=REFERENCE_SECONDS,
        players=(them,),
        casts=(
            *_casts(91, DEATH_STRIKE, "Death Strike", DEATH_STRIKES[index], 0),
            *_casts(91, DANCING_RUNE_WEAPON, "Dancing Rune Weapon", 4, 60_000),
        ),
        auras=PlayerAuras(
            actor_id=91,
            on_self=(
                Aura(
                    ability_id=BONE_SHIELD, name="Bone Shield",
                    total_uptime_ms=uptime_ms, uses=1,
                    bands=(AuraBand(start_ms=0, end_ms=uptime_ms),),
                ),
            ),
        ),
    )


def a_board(spec: str, amounts: tuple[float, ...]) -> tuple[RaidParseRow, ...]:
    """One leaderboard, `amounts` long. `amount` is a per-second rate already."""
    return tuple(
        RaidParseRow(
            report_code=f"BOARD{one}", fight_id=one + 1, duration_ms=240_000,
            character_name="Кириллица",
            class_name="Mage" if spec == "Arcane" else "DeathKnight",
            spec=spec, amount=amount,
        )
        for one, amount in enumerate(amounts)
    )


def a_rankings_row(name: str, spec: str, role: str, amount: float, percent: int) -> RankedPlayer:
    return RankedPlayer(
        character_name=name,
        class_name="Mage" if spec == "Arcane" else "DeathKnight",
        spec=spec, role=role, amount=amount, rank="~1200", best="~900",
        rank_percent=percent, bracket_percent=percent, total_parses=4_100,
    )


GOLDEN_STANDING = ReportRankings(
    fight_id=2, difficulty=5, partition=1, size=20, kill=True,
    players=(
        a_rankings_row("Emberkin", "Arcane", "dps", 1_450_000.0, 62),
        a_rankings_row("Stonewake", "Blood", "tank", 760_000.0, 81),
    ),
)

GOLDEN_BOSS_STANDING = ReportRankings(
    fight_id=2, difficulty=5, partition=1, size=20, kill=True,
    players=(
        a_rankings_row("Emberkin", "Arcane", "dps", 1_180_000.0, 48),
        a_rankings_row("Stonewake", "Blood", "tank", 690_000.0, 81),
    ),
)
"""This report's own rankings on both metrics, for the two compared raiders.

The two take different branches of both throughput comparisons on purpose. The
Mage's two percentiles differ, so `compare_rank` states them separately; the
tank's are equal, so it states one. The Mage sits below both medians, so
`compare_damage_total` says so in one clause; the tank sits above one and below
the other, which is the split sentence that comparison exists to write. Bríala
is in neither row: nobody asked for her comparison, and a rankings row she does
not appear in is how that reads on the page.
"""


def a_parse_subject(player: Player, sample: ParseSample, **overrides: object) -> ParseSubject:
    """One raider as the adapter hands them over: their sample, boards and targets.

    The slug comes from `slugs_by_actor`, which is how `cli.py` mints one, and
    never from the display name -- two names can reduce to one slug and the
    roster index is what keeps them apart.
    """
    fields: dict[str, object] = {
        "player": player,
        "slug": slugs_by_actor(GOLDEN_ROSTER)[player.actor_id],
        "display_name": player.name,
        "sample": sample,
    }
    fields.update(overrides)
    return ParseSubject(**fields)  # type: ignore[arg-type]


def golden_subjects() -> tuple[ParseSubject, ...]:
    """The two raiders a comparison was asked for, each against their own board."""
    return (
        a_parse_subject(
            GOLDEN_ROSTER[0],
            ParseSample(members=tuple(an_arcane_reference(one) for one in range(5))),
            our_auras=PlayerAuras(
                actor_id=1,
                on_self=(
                    Aura(
                        ability_id=ARCANE_INTELLECT, name="Arcane Intellect",
                        total_uptime_ms=60_000, uses=1,
                        bands=(AuraBand(start_ms=0, end_ms=60_000),),
                    ),
                ),
            ),
            board=a_board(
                "Arcane", (1_600_000.0, 1_720_000.0, 1_540_000.0, 1_880_000.0, 1_490_000.0)
            ),
            boss_board=a_board(
                "Arcane", (1_310_000.0, 1_402_000.0, 1_255_000.0, 1_520_000.0, 1_190_000.0)
            ),
            our_targets=(
                TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=880_000_000),
                TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=120_000_000),
            ),
            their_targets=tuple(
                (
                    TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=boss),
                    TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=adds),
                )
                for boss, adds in (
                    (450_000_000, 34_000_000),
                    (460_000_000, 32_000_000),
                    (470_000_000, 30_000_000),
                    (480_000_000, 28_000_000),
                    (490_000_000, 26_000_000),
                )
            ),
        ),
        a_parse_subject(
            GOLDEN_ROSTER[1],
            ParseSample(members=tuple(a_blood_reference(one) for one in range(5))),
            our_auras=PlayerAuras(
                actor_id=2,
                on_self=(
                    Aura(
                        ability_id=BONE_SHIELD, name="Bone Shield",
                        total_uptime_ms=270_000, uses=1,
                        bands=(AuraBand(start_ms=0, end_ms=270_000),),
                    ),
                ),
            ),
            board=a_board("Blood", (700_000.0, 740_000.0, 690_000.0, 810_000.0, 720_000.0)),
            boss_board=a_board("Blood", (720_000.0, 760_000.0, 700_000.0, 790_000.0, 730_000.0)),
            our_targets=(
                TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=300_000_000),
                TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=60_000_000),
            ),
            their_targets=tuple(
                (
                    TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=boss),
                    TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=adds),
                )
                for boss, adds in (
                    (320_000_000, 24_000_000),
                    (330_000_000, 22_000_000),
                    (340_000_000, 20_000_000),
                    (350_000_000, 18_000_000),
                    (360_000_000, 16_000_000),
                )
            ),
        ),
    )


GOLDEN_MECHANICS = MechanicsSample(
    members=tuple(
        MechanicsMember(
            row=ReferenceKillRow(
                report_code=f"KILL{one}", fight_id=one + 1, size=20,
                duration_ms=duration_ms, deaths=one,
            ),
            abilities=(
                AbilityTakenRow(
                    ability_id=KILLING_BLOW_ID, ability_name="Ravenous Feast",
                    hit_count=hits, source_types=("Boss",),
                ),
            ),
        )
        for one, (duration_ms, hits) in enumerate(
            ((252_000, 5), (260_000, 6), (268_000, 7))
        )
    )
)
"""Three reference kills, so the mechanics row is a median and not one kill.

`MIN_SAMPLE_FOR_AGGREGATE` is three, and below it `compare_mechanics` falls back
to a pairwise sentence naming one report -- a different sentence, which the
golden file would then pin instead of the aggregate one a real analysis writes.

Three kills of one boss that ran to the same millisecond and took the same
mechanic the same number of times are the flat sample the constants above were
spread to avoid: the median would equal the range's ends, and the sentence
stating it would read the same whichever of the three the code returned.
"""

GOLDEN_ABILITIES_TAKEN = (
    AbilityTakenRow(
        ability_id=KILLING_BLOW_ID, ability_name="Ravenous Feast",
        hit_count=14, source_types=("Boss",),
    ),
)


def a_compared_raid_fight() -> LoadedEncounter:
    """`a_raid_fight`'s fight with everything a real comparison reads attached.

    The same roster, the same single death and the same killing blow, plus the
    streams the comparison modules join against: our own casts, this report's
    own rankings rows on both metrics, an enemy cast that landed, and the damage
    the raid took. Kept beside `a_raid_fight` rather than folded into it,
    because every rule above renders that one and a fixture that grew a rankings
    row would change fifteen pages to pin one.
    """
    return LoadedEncounter(
        encounter=an_encounter(
            boss_name="The Twin Fangs",
            players=GOLDEN_ROSTER,
            kill=True,
            fight_percentage=0.0,
            start_ms=FIGHT_START_MS,
            end_ms=FIGHT_END_MS,
        ),
        casts=(
            *_casts(1, ARCANE_BLAST, "Arcane Blast", 10, FIGHT_START_MS + 5_000),
            *_casts(2, DEATH_STRIKE, "Death Strike", 30, FIGHT_START_MS + 4_000),
        ),
        deaths=(
            Death(
                actor_id=2,
                player_name="Stonewake",
                timestamp_ms=DEATH_MS,
                killing_blow="Ravenous Feast",
                killing_blow_id=KILLING_BLOW_ID,
                # Timed, unlike `a_raid_fight`'s: a death nobody came back from
                # costs no seconds, and a finding with no seconds reaches
                # neither the decomposition nor a Summary pointer -- which
                # would leave the golden page pinning an empty Summary tab.
                seconds_until_next_action=42.0,
            ),
        ),
        enemy_cast_rows=(
            EnemyCastRow(source_id=500, source_instance=1, ability_id=VOID_BOLT,
                         ability_name="Void Bolt", timestamp_ms=FIGHT_START_MS + 60_000,
                         is_start=True),
            EnemyCastRow(source_id=500, source_instance=1, ability_id=VOID_BOLT,
                         ability_name="Void Bolt", timestamp_ms=FIGHT_START_MS + 61_500,
                         is_start=False),
        ),
        damage_taken=(
            # The Mage takes four times what the other two take of the same
            # ability, which is the outlier `analyse_damage_outliers` reports
            # against their shared median.
            DamageTakenEvent(actor_id=1, ability_id=KILLING_BLOW_ID,
                             ability_name="Ravenous Feast", amount=420_000,
                             timestamp_ms=FIGHT_START_MS + 40_000),
            DamageTakenEvent(actor_id=2, ability_id=KILLING_BLOW_ID,
                             ability_name="Ravenous Feast", amount=110_000,
                             timestamp_ms=FIGHT_START_MS + 40_000),
            DamageTakenEvent(actor_id=3, ability_id=KILLING_BLOW_ID,
                             ability_name="Ravenous Feast", amount=105_000,
                             timestamp_ms=FIGHT_START_MS + 40_000),
            # Lands inside the enemy cast's own follow window above, which is
            # what makes it an uninterrupted cast rather than a stray hit.
            DamageTakenEvent(actor_id=2, ability_id=VOID_BOLT, ability_name="Void Bolt",
                             amount=98_000, timestamp_ms=FIGHT_START_MS + 61_600),
        ),
        standing=GOLDEN_STANDING,
        boss_standing=GOLDEN_BOSS_STANDING,
    )


def a_real_raid_comparison() -> tuple[Finding, ...]:
    """The golden page's findings, from the service rather than from this file.

    Every `compare.*` sentence the golden file holds was written by a comparison
    module and minted per raider by `analyse_encounter`, so a wording change
    anywhere along that path reaches `raid.html` and has to be approved.

    `mechanics` and `parse_subjects` are passed by name because
    `analyse_encounter` marks them keyword-only, so a call that tried to splat
    them positionally raises `TypeError` here and now. That marker is what makes
    the failure loud: without it the same call would bind each argument one slot
    to the left, and an earlier task on this plan lost time to a call that meant
    to supply these two and did not. A fixture that stopped supplying them would
    go quietly back to being the thing this one was written to replace.
    """
    return tuple(
        analyse_encounter(
            a_compared_raid_fight(),
            NO_DEFENSIVES,
            NO_CONSUMABLES,
            mechanics=GOLDEN_MECHANICS,
            our_abilities=GOLDEN_ABILITIES_TAKEN,
            parse_subjects=golden_subjects(),
        )
    )


GOLDEN_REFERENCES = (
    ReferenceRecord(
        report_code="ARC0", fight_id=1, keystone_level=0,
        url="https://www.warcraftlogs.com/reports/ARC0?fight=1", axis="parse",
    ),
    ReferenceRecord(
        report_code="BLD0", fight_id=1, keystone_level=0,
        url="https://www.warcraftlogs.com/reports/BLD0?fight=1", axis="parse",
    ),
)
"""One candidate per sample, naming the report its top parse came from.

`player_slug` and `player_name` stay at their empty defaults, which is what
`cli._parse_record` writes and why: a raid parse sample is drawn once per
class-and-specialisation pair and shared by every subject of that pair, so no
raid candidate was ever weighed for one particular player. The builder would
pass a name straight through, and a golden page carrying one would freeze a
Provenance line the real raid path cannot produce -- and teach the next reader
re-approving this file that it is the normal shape.
"""


def a_golden_raid_report() -> RaidReport:
    return build_raid_report(
        a_compared_raid_fight(),
        a_real_raid_comparison(),
        GOLDEN_ROSTER[0],
        COMPARED,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        reference_records=GOLDEN_REFERENCES,
    )


def golden_raid_html() -> str:
    return render_raid(a_golden_raid_report())


def test_the_golden_fixture_actually_carries_a_comparison() -> None:
    """The guard the Mythic+ golden file does not have.

    Its fixture carries no reference sample, so no comparison family reaches
    the page it renders, and a mutation to any comparison sentence leaves it
    green -- discovered by mutation during plan 3a, after the file had been
    cited as proof in three review briefs. A fixture that stops comparing must
    fail here rather than quietly stop testing.
    """
    findings = a_real_raid_comparison()

    families = {f.id.rsplit(".", 1)[0] for f in findings if f.id.startswith("compare.")}
    assert families >= {
        "compare.damage.total", "compare.rank", "compare.talents",
    }, sorted(families)


def test_the_golden_page_draws_every_comparison_sentence_once_per_raider() -> None:
    """The other half of the guard above: what the page did with the comparison.

    The guard proves the service compared and the golden file pins whatever was
    then rendered, so between them a page could pin a comparison stripped of
    everything that makes it one raider's. Three things are held here that the
    byte comparison states without asserting: both raiders are on the page under
    their own slug, which is what Task 2's minting buys; each compared finding
    draws exactly one card, so no raider's row is shown twice; and the sentence
    on the card is the comparison module's own, not one the builder rewrote.

    `title_before` rather than `title` because a title naming an ability is
    rendered in three pieces around an icon span, and the piece before the span
    is what the page carries as one string. For every other row it is the whole
    sentence.
    """
    report = a_golden_raid_report()
    html = render_raid(report)
    rows = {row.finding_id: row for row in all_raid_ledger_rows(report)}

    compared = [
        finding for finding in a_real_raid_comparison() if finding.id.startswith("compare.")
    ]
    assert compared, "the fixture produced no comparison findings at all"
    assert {finding.player_slug for finding in compared} == {EMBERKIN_SLUG, STONEWAKE_SLUG}
    for finding in compared:
        row = rows.get(finding.id)
        assert row is not None, f"{finding.id} reached no row at all"
        assert row.title == finding.title, finding.id
        assert html.count(f'id="finding-{finding.id}"') == 1, finding.id
        assert str(escape(row.title_before)) in html, finding.id


# Design section 12.5 asks for the two comparisons that cannot honestly be made
# to be held as a page-level invariant rather than inside two analysers, because
# "a rule living only in a docstring is a rule that gets broken" and a
# function-scoped test sees only the function it was written for. What follows
# is that rule, over every finding a real raid analysis produces.
#
# It is written per *fact*, never per finding. A `mechanics.ability.*` finding
# legitimately carries a reference rate and a phase label at once -- design
# section 6 asks for exactly that, one on each side of the same card -- and an
# invariant written per finding would fail on correct code the day a phased
# encounter reached it.

PHASE_ONE = Phase(id=1, name="Stage One: The Fangs Close")
PHASE_TWO = Phase(id=2, name="Stage Two: The Venom Rises")
"""Two named phases, spelled distinctly enough to be searched for in a string.

Phase names come from the API and never from a table of ours, so these are
invented as any encounter's would read -- what matters is that a fact quoting
one is recognisable as quoting one.
"""


def a_phased_raid_fight() -> LoadedEncounter:
    """The golden fight with phases on its encounter and nothing else changed.

    Its Ravenous Feast hits all fall before the second transition and its Void
    Bolt after, so `dominant_phase_by_ability` has a real choice to make and the
    comparison that names the killing blow picks up a phase label beside its
    reference rate -- the pair of facts this rule exists to keep apart.
    """
    fight = a_compared_raid_fight()
    return fight.model_copy(
        update={
            "encounter": fight.encounter.model_copy(
                update={
                    "phases": (PHASE_ONE, PHASE_TWO),
                    "phase_transitions": (
                        PhaseTransition(id=1, start_ms=FIGHT_START_MS),
                        PhaseTransition(id=2, start_ms=FIGHT_START_MS + 50_000),
                    ),
                }
            )
        }
    )


def a_phased_raids_findings() -> tuple[Finding, ...]:
    """Everything the raid service emits for that fight, comparison and all."""
    return tuple(
        analyse_encounter(
            a_phased_raid_fight(),
            NO_DEFENSIVES,
            NO_CONSUMABLES,
            mechanics=GOLDEN_MECHANICS,
            our_abilities=GOLDEN_ABILITIES_TAKEN,
            parse_subjects=golden_subjects(),
        )
    )


def states_a_phase(fact: FindingFact) -> bool:
    return any(phase.name in fact.label or phase.name in fact.value
               for phase in (PHASE_ONE, PHASE_TWO))


def states_a_reference(fact: FindingFact) -> bool:
    """Whether a fact carries a figure drawn from the reference side.

    Matched on the word rather than on a list of labels: the rule has to hold
    for a family nobody has written yet, and every reference figure this
    project prints names itself -- "Reference median", "3 reference kills",
    "1 reference kill".
    """
    return "reference" in fact.label.lower() or "reference" in fact.value.lower()


def test_no_one_fact_states_a_phase_and_a_reference_figure_together() -> None:
    """Section 9's rule, held over the whole page rather than one comparison.

    A reference kill's ability table carries no timestamps at all, so its
    landings cannot be split by time at any price -- which makes a fact reading
    "Stage Two, against a reference median of 1.4" a claim no reader could
    check and no query could support.
    """
    findings = a_phased_raids_findings()
    facts = [(finding, fact) for finding in findings for fact in finding.facts]
    assert facts, "the analysis produced no facts at all, so this rule was never exercised"

    assert any(
        any(states_a_phase(fact) for fact in finding.facts)
        and any(states_a_reference(fact) for fact in finding.facts)
        for finding in findings
    ), (
        "no finding carries a phase label and a reference figure at once, so this rule "
        "held over a page that never risked breaking it"
    )

    for finding, fact in facts:
        assert not (states_a_phase(fact) and states_a_reference(fact)), (
            f"{finding.id} states a phase and a reference figure in one fact: "
            f"{fact.label} = {fact.value}"
        )


def test_no_one_fact_states_our_own_damage_and_a_reference_figure_together() -> None:
    """Section 12.5's other half, and ruling 4.5's reason for it.

    Our figure is unmitigated and a reference table's is mitigated, measured
    4.61x apart on a real fight, and nothing reconciles them. Cross-raid
    comparison is landings per minute or death counts; a damage figure stays on
    our own side of the page. Every one of ours says `unmitigated` in the fact
    that prints it, which is what makes this searchable.
    """
    findings = a_phased_raids_findings()
    facts = [(finding, fact) for finding in findings for fact in finding.facts]

    assert any("unmitigated" in fact.value.lower() for _finding, fact in facts), (
        "no fact states a damage figure of ours at all, so this rule was never exercised"
    )
    assert any(states_a_reference(fact) for _finding, fact in facts), (
        "no fact states a reference figure at all, so this rule was never exercised"
    )

    for finding, fact in facts:
        assert not ("unmitigated" in fact.value.lower() and states_a_reference(fact)), (
            f"{finding.id} puts our unmitigated figure beside a reference one: "
            f"{fact.label} = {fact.value}"
        )


def test_the_rendered_raid_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = golden_raid_html()
    if pytestconfig.getoption("--golden-update"):
        RAID_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        RAID_GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == RAID_GOLDEN.read_text(encoding="utf-8"), (
        "The rendered raid report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update`."
    )


def test_the_mechanics_panel_draws_the_damage_grid() -> None:
    """The brief for this task quoted design 7.3 as "It does not mean a mistake" --
    but that literal sentence never reached `raid_grid.CAPTION`. Task 3's own
    caption test, `test_the_caption_refuses_to_call_a_tint_a_mistake`, bans the
    word "mistake" from the caption outright, so a caption stating that sentence
    verbatim could never have passed. The phrase below is the wording Task 3
    settled on instead, and it carries the same fact: a tint means "took far
    more than their raid did", stated on the page rather than only in the
    design document.
    """
    html = golden_raid_html()

    assert 'class="damage-grid"' in html
    assert "A highlighted cell means that player took far more of it than their raid did" in html


def test_a_grid_tint_is_a_class_not_a_colour_word() -> None:
    """A reader who cannot separate two tints, or who printed the page, needs the number.

    The same rule `ComparisonRow` already follows: a tint carries no meaning
    alone.
    """
    html = golden_raid_html()

    assert 'class="cell tinted"' in html


def test_a_grid_column_whose_ability_id_appears_nowhere_else_still_draws_its_icon() -> None:
    """`_icon_addresses` must walk the grid on its own, not lean on a ledger row.

    `ledger_row` only copies `ability_id` onto a `LedgerRow` when
    `_split_title` can cut the finding's title at its own ability name --
    exactly once, no more, no fewer (`ledger.py::_split_title`). `_columns` in
    `raid_grid.py` carries no such gate: it reads `Finding.ability_id`
    unconditionally. So a `mechanics.ability.*` finding whose title does not
    name its ability exactly once still earns a grid column, while its
    `LedgerRow.ability_id` is `None` everywhere `all_raid_ledger_rows` walks.

    Proved here with a grid built directly, holding an ability id nowhere else
    on the report -- `all_raid_ledger_rows` cannot see it at all, so a page
    that still draws its icon proves the grid itself was walked, not a row
    that happened to carry the same id.
    """
    ability_id = 54321
    grid = RaidGrid(
        columns=(GridColumn(ability_id=ability_id, ability_name="Caustic Waves"),),
        rows=(
            GridRow(
                player_name="Emberkin",
                cells=(
                    GridCell(ability_id=ability_id, amount="1,000", multiple="", tinted=False),
                ),
            ),
        ),
        caption="test caption",
    )
    report = a_minimal_raid_report(grid=grid)

    html = render_raid(report, CdnIcons({ability_id: "spell_holy_divineshield.jpg"}))

    assert f".i-{ability_id}" in html


def test_a_report_with_no_grid_draws_none_of_it() -> None:
    """A `None` grid renders nothing at all, not an empty table with headings.

    Checks all three pieces the `{% if report.grid %}` guard wraps -- the
    heading, the caption and the table -- so an edit that moved the
    `{% endif %}` to cover only the `<table>`, leaving the heading and caption
    printed unconditionally, would still be caught here.
    """
    report = a_golden_raid_report().model_copy(update={"grid": None})

    html = render_raid(report)

    assert 'id="grid"' not in html
    assert 'class="damage-grid"' not in html
    assert (
        "A highlighted cell means that player took far more of it than their raid did"
        not in html
    )


def test_the_summary_draws_the_alive_chart() -> None:
    html = golden_raid_html()

    assert 'class="alive-chart"' in html
    assert "Players still standing" in html


def test_the_alive_chart_is_inline_svg_and_fetches_nothing() -> None:
    """The report is one file. The only outbound addresses are ability icons."""
    html = golden_raid_html()

    start = html.index('class="alive-chart"')
    chart = html[start : html.index("</svg>", start)]
    for forbidden in ("<image", "href=", "url("):
        assert forbidden not in chart, f"the chart reaches outside the page: {forbidden}"


def test_a_report_with_no_alive_chart_draws_none_of_it() -> None:
    """A `None` alive_chart renders nothing at all, not an empty SVG frame with axes.

    Mirrors `test_a_report_with_no_grid_draws_none_of_it`: the guard is
    `{% if report.alive_chart %}` around the heading, the legend and the SVG
    together, and only a fixture that actually flips the field to `None` can
    catch an edit that narrowed the guard to cover only one of the three.
    """
    report = a_golden_raid_report().model_copy(update={"alive_chart": None})

    html = render_raid(report)

    assert 'class="alive-chart"' not in html
    assert "Players still standing" not in html
    assert "How the attempt went" not in html


def a_death_page_where(
    pressed_at_ms: int, band: tuple[int, int], death_at_ms: int, ability: str
) -> str:
    """Render a raid page with one death: the dying player pressed their own
    defensive once, and the aura table gives it exactly one band.

    Goes through the real pipeline -- `build_raid_report` down through
    `build_deaths` and `render_raid` -- rather than hand-building an
    `AbilityState`, so a wiring mistake at the `availability_at` call site
    shows up here, not only in `state_of`'s own tests.

    `pressed_at_ms`, `band` and `death_at_ms` share
    `test_recap_availability.py`'s clock -- a fight window of `(0, 10_000)` --
    so the two levels agree on what "held" and "faded" mean for the same
    numbers.
    """
    ability_id = 22812  # Barkskin's id; only the id has to match, not the name.
    player = Player(
        actor_id=1, name="Кириллица",
        class_name="Druid", spec="Guardian", item_level=680,
    )
    defensives = Defensives(
        entries=(
            (
                "Druid/Guardian",
                (DefensiveAbility(ability_id=ability_id, name=ability, cooldown_seconds=45.0),),
            ),
        ),
    )
    auras = PlayerAuras(
        actor_id=1,
        on_self=(
            Aura(
                ability_id=ability_id, name=ability, total_uptime_ms=band[1] - band[0], uses=1,
                bands=(AuraBand(start_ms=band[0], end_ms=band[1]),),
            ),
        ),
    )
    loaded = LoadedEncounter(
        encounter=an_encounter(
            boss_name="The Twin Fangs", players=(player,), kill=False,
            fight_percentage=12.4, start_ms=0, end_ms=10_000,
        ),
        deaths=(
            Death(
                actor_id=1, player_name=player.name, timestamp_ms=death_at_ms,
                killing_blow="Ravenous Feast",
            ),
        ),
        casts=(
            CastEvent(
                actor_id=1, ability_id=ability_id, ability_name=ability,
                timestamp_ms=pressed_at_ms,
            ),
        ),
        auras=(auras,),
    )
    report = build_raid_report(
        loaded, (), player, None, FETCHED, defensives, NO_CONSUMABLES, NO_ROLES,
    )
    return render_raid(report)


def test_a_defensive_that_lapsed_says_so_on_the_card() -> None:
    """The overstatement this branch exists to correct, as a reader meets it."""
    html = a_death_page_where(
        pressed_at_ms=2000, band=(1000, 3000), death_at_ms=5000, ability="Barkskin"
    )

    assert "over by then" in html
    assert '<li class="faded">' in html


def test_a_defensive_still_covering_says_that_instead() -> None:
    html = a_death_page_where(
        pressed_at_ms=2000, band=(1000, 9000), death_at_ms=5000, ability="Barkskin"
    )

    assert '<span class="avail-detail">3.0 s before death, still up</span>' in html
    assert "over by then" not in html
    assert '<li class="held">' in html
