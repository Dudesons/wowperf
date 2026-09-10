# ABOUTME: Whole-page rules: offline, every finding once, sections in order, and one golden file.
# ABOUTME: The golden fixture is tiny on purpose — a 2000-line diff is a test nobody reads.

import re
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from markupsafe import escape

from tests.adapters.render.test_html import a_report
from tests.adapters.render.test_html_sections import FakeIcons
from tests.domain.report.test_build_frame import (
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    a_pull,
    a_run,
)
from tests.domain.report.test_build_timeline import a_member
from tests.domain.report.test_model import view_model_types
from wowperf.adapters.render.html import render
from wowperf.domain.comparison.sample import SpeedSample
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import (
    AvailabilityRow,
    CooldownRow,
    CurveGuide,
    CurvePoint,
    CurveReading,
    CurveTick,
    DamageBar,
    DamageTrack,
    DeathCard,
    Header,
    HealthCurve,
    LedgerRow,
    PlayerTimeline,
    Press,
    Provenance,
    RecapRow,
    ReferenceRecord,
    Span,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    DefensiveAbility,
    Defensives,
)

GOLDEN = Path(__file__).parent / "golden" / "minimal.html"

# The player being analysed, from our own roster -- never a reference run's top
# parser, which names a different character in a different log (item 1).
SUBJECT = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=680)

# "losses" renders only when a timed loss exists; the minimal fixture has two.
SECTION_ORDER = [
    "ledger", "losses", "timeline", "observations", "route", "deaths", "interrupts", "players",
    "provenance",
]


def minimal_loaded() -> LoadedRun:
    return LoadedRun(
        run=a_run(
            players=(
                Player(
                    actor_id=1,
                    name="Emberkin",
                    class_name="Mage",
                    spec="Arcane",
                    item_level=680,
                ),
            ),
            pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 200_000, encounter_id=12825)),
        ),
        casts=(CastEvent(actor_id=1, ability_id=1, ability_name="Arcane Blast",
                         timestamp_ms=10_000, pull_index=0),),
        deaths=(Death(player_name="Emberkin", actor_id=1, timestamp_ms=50_000,
                      killing_blow="Frigid Roar", pull_index=0),),
        damage_taken=(DamageTakenEvent(actor_id=1, ability_id=2, ability_name="Snowdrift",
                                       amount=82_410, health_damage=82_410,
                                       timestamp_ms=45_000, pull_index=0),),
    )


def minimal_findings() -> tuple[Finding, ...]:
    return (
        Finding(
            id="time.residual",
            title="Time outside pulls",
            detail="Travel, waiting and run-backs.",
            confidence=Confidence.MEASURED,
            seconds_lost=300.0,
        ),
        Finding(
            id="time.gap.0",
            title="A 41 second gap after pull 0",
            detail="Travel, not combat.",
            confidence=Confidence.MEASURED,
            seconds_lost=41.0,
            evidence=("next pull begins at Pack 1",),
        ),
        Finding(
            id="interrupts.summary",
            # Apostrophe and ampersand on purpose: Jinja's autoescape turns
            # apostrophes into &#39;, so the title must be escaped before
            # comparing against the rendered HTML.
            title="Wipsdk let Death's Advance & Ice Block go uninterrupted",
            detail="Grouped by spell.",
            confidence=Confidence.DERIVED,
        ),
        # A death-family finding, so the once-only and reaches-the-page
        # invariants below exercise the rows beneath the Deaths section.
        Finding(
            id="defensives.unused.0",
            title="Emberkin died with Ice Block available",
            detail="Cast earlier in the run, and its cooldown had elapsed by the killing blow.",
            confidence=Confidence.INFERRED,
        ),
    )


def minimal_html() -> str:
    return render(
        build_report(
            minimal_loaded(), minimal_findings(), None, None, SUBJECT, None, FETCHED,
            NO_DEFENSIVES,
        NO_CONSUMABLES,
        )
    )


# The golden fixture above deliberately has one player, no reference run, and so no
# Warcraft Logs link and no timeline SVG. The self-containment and href-scoping
# assertions need a page that actually contains both href kinds, the inline SVG,
# a withheld section and more than one player — otherwise they would pass by never
# exercising the thing they claim to check. This fixture, not the golden one, is
# what those tests render.


def rich_loaded() -> LoadedRun:
    return LoadedRun(
        run=a_run(
            players=(
                Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane",
                       item_level=680),
                Player(actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood",
                       item_level=675),
            ),
            pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 200_000, encounter_id=12825)),
        ),
    )


def rich_speed_sample() -> SpeedSample:
    # A reference run makes the timeline present (so it renders its SVG) and
    # gives provenance a Warcraft Logs link to the reference report. One member,
    # sharing our keystone level, so `build_timeline` draws both tracks.
    reference_run = a_run(
        report_code="ref001",
        fight_id=7,
        pulls=(a_pull(0, 0, 55_000), a_pull(1, 105_000, 190_000, encounter_id=12825)),
    )
    return SpeedSample(
        members=(a_member(rich_loaded().run, reference_run, level=16, code="ref001"),)
    )


def rich_reference_records() -> tuple[ReferenceRecord, ...]:
    return (
        ReferenceRecord(
            report_code="ref001", fight_id=7, keystone_level=16,
            url="https://www.warcraftlogs.com/reports/ref001?fight=7", axis="speed",
        ),
    )


def rich_findings() -> tuple[Finding, ...]:
    return (
        Finding(
            id="time.residual",
            title="Time outside pulls",
            detail="Travel, waiting and run-backs.",
            confidence=Confidence.MEASURED,
            seconds_lost=300.0,
        ),
        # Nests inside the finding above, by build.py's own NESTS_INSIDE table.
        Finding(
            id="time.gap.0",
            title="A 41 second gap after pull 0",
            detail="Travel, not combat.",
            confidence=Confidence.MEASURED,
            seconds_lost=41.0,
        ),
    )


def rich_html() -> str:
    # No parse sample is passed, so the spell-and-talent comparison on each
    # player card is withheld, giving the page a withheld section as well.
    return render(
        build_report(
            rich_loaded(), rich_findings(), rich_speed_sample(), None, SUBJECT, None, FETCHED,
            NO_DEFENSIVES, NO_CONSUMABLES,
            reference_records=rich_reference_records(),
        )
    )


def test_the_richer_fixture_actually_exercises_what_it_claims_to() -> None:
    # Guards the fixture above against ever drifting back to something vacuous:
    # the tests below are only meaningful if the page they render truly contains
    # every shape they assert about.
    html = rich_html()
    assert "<svg" in html
    assert html.count('class="player-head"') == 2
    assert "Already counted inside" in html
    assert 'class="withheld"' in html
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith("#") for href in hrefs)
    assert any(href.startswith("https://www.warcraftlogs.com/reports/") for href in hrefs)


FORBIDDEN_IN_SCRIPT = (
    "fetch",
    "XMLHttpRequest",
    "import(",
    "document.write",
    "innerHTML",
    "textContent",
    "localStorage",
    "sessionStorage",
    "eval",
    "WebSocket",
)
"""What the script may not contain: anything that fetches, writes text or reads storage."""


def test_the_page_executes_only_its_own_script() -> None:
    # A Warcraft Logs reference-run link and the SVG's own namespace attribute
    # both legitimately contain "http://" without fetching anything, so
    # self-containment is checked by what the page can *execute* or *load*,
    # not by whether the string appears at all. One inline script is allowed,
    # and only one: the tab toggle. Its text is checked for anything that could
    # reach past showing and hiding.
    html = rich_html()
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
    # Finding ids contain dots (e.g. "finding-time.gap.0"); querySelector("#" + id)
    # would parse the dot as a class selector, so the lookup must stay getElementById.
    assert "getElementById" in body


def test_the_page_loads_no_image_over_the_network() -> None:
    # The existing script test checks `src` attributes; an icon reaches the page
    # through a CSS url() instead, which that check never sees. A hotlinked icon
    # would leave the report blank the day Blizzard moved the file.
    html = render(a_report())
    assert "url(http" not in html
    assert "url(//" not in html


def test_a_resolved_icon_reaches_the_page_as_a_data_uri_never_a_hotlink() -> None:
    # The test above renders no icon at all, so a hotlinked `url(http...)` would
    # leave it passing exactly as it does today -- it never exercises the path a
    # real icon travels. This renders a page that actually resolves one and
    # checks what kind of url() it wrote.
    card = DeathCard(player="Stonewake", class_name="DeathKnight", when="12:04, pull 5",
                     killing_blow="Frigid Roar", killing_blow_id=7)
    html = render(a_report(deaths=(card,)), icons=FakeIcons({7: "data:image/jpeg;base64,AAA"}))
    assert "url(data:" in html
    assert "url(http" not in html
    assert "url(//" not in html


PANEL_ORDER = [
    "tab-summary", "tab-route", "tab-deaths", "tab-interrupts", "tab-players", "tab-provenance",
]


def test_the_page_hides_nothing_before_the_script_runs() -> None:
    # Without the script the root class is absent, so every hiding rule must be
    # scoped under it. The tab bar is the one thing hidden *without* the script,
    # by the bare `.tabs` rule, and that is checked by name.
    html = rich_html()
    assert not re.search(r"<[^>]*\shidden[\s>=]", html)
    assert not re.search(r'style="[^"]*display', html)
    style = html[html.index("<style>"):html.index("</style>")]
    for rule in re.finditer(r"([^{}]+)\{[^{}]*display:\s*none", style):
        selector = rule.group(1).strip().splitlines()[-1].strip()
        assert selector.startswith(".js ") or selector == ".tabs", selector


def test_every_panel_appears_once_in_tab_order() -> None:
    html = minimal_html()
    positions = [html.index(f'id="{name}"') for name in PANEL_ORDER]
    assert positions == sorted(positions)
    assert len(re.findall(r'<section class="panel"', html)) == len(PANEL_ORDER)


def test_every_panel_has_exactly_one_tab_button() -> None:
    html = minimal_html()
    for name in PANEL_ORDER:
        assert html.count(f'data-tab-for="{name}"') == 1, name


def test_the_tab_buttons_follow_panel_order() -> None:
    # The script opens the first button's panel by default, so button order is
    # the default tab; nothing else pins the order the buttons appear in.
    html = minimal_html()
    positions = [html.index(f'data-tab-for="{name}"') for name in PANEL_ORDER]
    assert positions == sorted(positions)


def test_the_root_class_the_script_adds_is_not_in_the_markup() -> None:
    # The script adds it at run time; rendering it would hide panels with no script.
    html = rich_html()
    assert '<html lang="en">' in html
    assert 'class="js' not in html


def test_every_href_is_a_fragment_a_report_link_or_an_embedded_icon() -> None:
    # A press-mark icon is drawn as an SVG <image href="data:…">, not a CSS
    # background: this is the one other shape an href is allowed to take,
    # because a data URI is bytes already in the file, not a fetch -- the
    # same reason icons are embedded rather than hotlinked everywhere else.
    html = rich_html()
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith("#") for href in hrefs)
    assert any(href.startswith("https://www.warcraftlogs.com/reports/") for href in hrefs)
    for href in hrefs:
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ) or href.startswith("data:image/"), href


def test_every_section_appears_in_the_order_the_design_fixes() -> None:
    html = minimal_html()
    positions = [html.index(f'id="{name}"') for name in SECTION_ORDER]
    assert positions == sorted(positions)


def test_a_report_without_a_narrative_renders_one_heading_per_section() -> None:
    # Header (h1) plus the always-present h2 sections in SECTION_ORDER.
    html = minimal_html()
    assert 'id="narrative"' not in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER)


def test_a_narrative_adds_exactly_one_heading() -> None:
    # Header (h1) plus the always-present h2 sections plus narrative.
    html = render(
        build_report(
            minimal_loaded(), minimal_findings(), None, None, SUBJECT, "A sentence.", FETCHED
        , NO_DEFENSIVES, NO_CONSUMABLES)
    )
    assert 'id="narrative"' in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER) + 1


def test_every_finding_reaches_the_page() -> None:
    # Compared against the escaped title: the template renders it through Jinja's
    # autoescape (markupsafe.escape), which turns an apostrophe into `&#39;`.
    html = minimal_html()
    for finding in minimal_findings():
        assert str(escape(finding.title)) in html, finding.id


def test_no_finding_reaches_the_page_twice() -> None:
    # Anchored to the row heading, not to the bare title text: a nested row
    # legitimately quotes its parent's title in "Already counted inside ...",
    # which is a cross-reference, not a second copy of the parent's own row.
    # Compared against the escaped title for the same reason as the test above.
    html = minimal_html()
    for finding in minimal_findings():
        assert html.count(f"<h3>{escape(finding.title)}</h3>") == 1, finding.id


def test_every_withheld_section_gives_a_reason() -> None:
    html = minimal_html()
    # The timeline is withheld here: no speed reference was passed.
    heading = html.index('id="timeline"')
    deaths = html.index('id="deaths"')
    assert 'class="withheld"' in html[heading:deaths]


# Every numeric field any view model type carries, together with why it is not
# a duration a total could be built from: an id, a difficulty tier, or a
# coordinate the SVG needs. A field added to this allowlist should not also be
# a count of seconds -- if it is, it belongs on `LedgerRow.seconds` instead,
# pre-formatted as a string, the way every other seconds-lost figure already is.
NUMBERS_THAT_ARE_NOT_TOTALS = {
    (Header, "keystone_level"),  # a difficulty tier, not a duration
    (Provenance, "fight_id"),  # an id, not a duration
    (ReferenceRecord, "fight_id"),  # an id, not a duration
    (ReferenceRecord, "keystone_level"),  # a difficulty tier, not a duration
    (Timeline, "width"),
    (Timeline, "height"),
    (Timeline, "tick_y1"),
    (Timeline, "tick_y2"),
    (Timeline, "tick_label_y"),
    (Timeline, "caption_x"),
    (Timeline, "caption_dy"),
    (Timeline, "block_height"),
    (TimelineBlock, "x"),
    (TimelineBlock, "width"),
    (TimelineTrack, "baseline_y"),
    (RecapRow, "health_percent"),  # a share of the player's own health, not a duration
    (RecapRow, "ability_id"),  # a spell's identity, not a duration
    (AvailabilityRow, "ability_id"),  # a spell's identity, not a duration
    (DeathCard, "killing_blow_id"),  # a spell's identity, not a duration
    (LedgerRow, "ability_id"),  # a spell's identity, not a duration
    # The health curve's geometry. Every one of these is a viewBox coordinate
    # computed in `health_curve.py`: a position on a fixed axis rather than a
    # quantity, so a column of them summed would mean nothing a reader could
    # misread as a total.
    (HealthCurve, "width"),
    (HealthCurve, "height"),
    (HealthCurve, "plot_x0"),
    (HealthCurve, "plot_x1"),
    (HealthCurve, "label_x"),
    (HealthCurve, "tick_label_y"),
    (CurvePoint, "x"),
    (CurvePoint, "y"),
    (CurveReading, "x"),
    (CurveReading, "y"),
    (CurveTick, "x"),
    (CurveGuide, "y"),
    (CurveReading, "percent"),  # a share of the player's own health, not a duration
    # The player timeline's geometry. Every one of these is a viewBox coordinate
    # computed in `player_timeline.py`: a position on a fixed axis rather than a
    # quantity, so a column of them summed would mean nothing a reader could
    # misread as a total.
    (DamageBar, "x"),
    (DamageBar, "width"),
    (DamageBar, "y"),
    (DamageBar, "height"),
    (DamageTrack, "baseline_y"),
    (Press, "x"),
    (Span, "x"),
    (Span, "width"),
    (CooldownRow, "ability_id"),  # a spell's identity, not a duration
    (CooldownRow, "baseline_y"),
    (PlayerTimeline, "width"),
    (PlayerTimeline, "height"),
    (PlayerTimeline, "band_y"),
    (PlayerTimeline, "band_height"),
    (PlayerTimeline, "tick_y1"),
    (PlayerTimeline, "tick_y2"),
    (PlayerTimeline, "tick_label_y"),
    (PlayerTimeline, "label_x"),
    (PlayerTimeline, "row_height"),
}


def test_the_report_carries_no_total_row() -> None:
    # This proves two things, and no more than these two:
    # (1) no field on `Report` or any view model it nests is a bare number that
    #     could hold a total -- every seconds-lost figure reaches the page
    #     already formatted as a string on `LedgerRow.seconds`, so the only
    #     numeric fields left are an id, a difficulty tier and a handful of SVG
    #     coordinates, all named on the allowlist above; and
    # (2) no template holds a Jinja `{% set %}` accumulator that could total
    #     figures on its own, whether spelled as an obvious `|sum`/`sum(` call
    #     or a hand-rolled running total in a loop variable. Every template in
    #     the render directory is read, so a partial is covered the moment it
    #     exists rather than when someone remembers to name it here.
    # It does NOT prove no total is computed anywhere in the codebase -- only
    # that the report's own view model and templates have nowhere to hold or
    # build one.
    report = build_report(
        minimal_loaded(), minimal_findings(), None, None, SUBJECT, None, FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    assert not any(field.startswith("total") for field in type(report).model_fields)

    for model_type in view_model_types():
        for field_name, field in model_type.model_fields.items():
            # Check bare numeric types (int, float) and optional variants (int | None, etc).
            is_numeric = field.annotation in (int, float)
            if not is_numeric:
                origin = get_origin(field.annotation)
                # Handle both typing.Union and types.UnionType (Python 3.10+ int | None).
                if origin is Union or isinstance(field.annotation, UnionType):
                    args = get_args(field.annotation)
                    # Check if one arg is numeric and the other is None (optional type).
                    numeric_args = [arg for arg in args if arg in (int, float)]
                    is_numeric = len(numeric_args) == 1 and len(args) == 2
            if is_numeric:
                assert (model_type, field_name) in NUMBERS_THAT_ARE_NOT_TOTALS, (
                    f"{model_type.__name__}.{field_name} is a numeric field with no entry "
                    "on the allowlist explaining why it cannot hold a total"
                )

    render_dir = Path(__file__).parents[3] / "src" / "wowperf" / "adapters" / "render"
    templates = sorted(render_dir.glob("*.j2"))
    # A glob that matched nothing would let every assertion below pass without
    # reading a line of markup, so the count is checked before the content is.
    assert len(templates) >= 2, f"only {len(templates)} template(s) under {render_dir}"
    for path in templates:
        source = path.read_text(encoding="utf-8")
        assert "|sum" not in source, path.name
        assert "sum(" not in source, path.name
        assert "{% set" not in source, path.name


def test_the_rendered_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = minimal_html()
    if pytestconfig.getoption("--golden-update"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == GOLDEN.read_text(encoding="utf-8"), (
        "The rendered report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_html_invariants.py --golden-update`."
    )


POTIONS = Consumables(
    categories=(
        ConsumableCategory(
            name="health potion", cooldown_seconds=300.0, ability_ids=(1234768,)
        ),
    )
)

ARCANE = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(
                    ability_id=235450, name="Prismatic Barrier", cooldown_seconds=25.0
                ),
            ),
        ),
    )
)


def a_page(defensives: Defensives) -> str:
    return render(
        build_report(
            minimal_loaded(), minimal_findings(), None, None, SUBJECT, None, FETCHED,
            defensives, NO_CONSUMABLES,
        )
    )


def deaths_section(html: str) -> str:
    """Just the deaths section. Ability names recur across sections — the fixture's
    own interrupt findings name Ice Block — so an unscoped search proves nothing."""
    start = html.index('<h2 id="deaths">')
    return html[start : html.index('<h2 id="interrupts">', start)]


def owns_barrier(at_ms: int) -> CastEvent:
    return CastEvent(actor_id=1, ability_id=235450, ability_name="Prismatic Barrier",
                     timestamp_ms=at_ms, pull_index=0)


def a_page_with(cast: CastEvent) -> str:
    loaded = minimal_loaded()
    return render(
        build_report(
            loaded.model_copy(update={"casts": loaded.casts + (cast,)}), minimal_findings(),
            None, None, SUBJECT, None, FETCHED, ARCANE, NO_CONSUMABLES,
        )
    )


AVAILABILITY_ROW = r'<li class="(pressed|ready|cooldown|unseen)">'
"""One row of an availability group. An evidence bullet is also an `<li>` and carries no
class, so matching on the class is what tells a judged tool from a finding's evidence."""


def test_a_death_card_names_the_defensives_it_judged() -> None:
    # Cast at 10s, its 25s cooldown elapsed before the window opens at 40s.
    section = deaths_section(a_page_with(owns_barrier(10_000)))
    assert "Prismatic Barrier" in section
    assert '<li class="ready">' in section


def test_a_defensive_pressed_inside_the_run_up_reads_as_pressed() -> None:
    # Cast at 45s, inside the window that ends at the death at 50s.
    section = deaths_section(a_page_with(owns_barrier(45_000)))
    assert '<li class="pressed">' in section
    assert "5.0 s before death" in section


def test_an_unchecked_spec_makes_no_claim_either_way() -> None:
    # The silence a reader must not mistake for "nothing was up": the group
    # states why it is empty instead of listing an ability in any state.
    section = deaths_section(a_page(NO_DEFENSIVES))
    assert "No data file covers Mage Arcane." in section
    assert not re.search(AVAILABILITY_ROW, section)


def test_the_defensives_group_carries_its_confidence_badge() -> None:
    # The only inferred claim on a card whose other facts are all measured. Without
    # a badge a reader has no way to tell it is reconstructed rather than logged.
    # Scoped to the group's own heading: the finding card in the same section
    # carries an inferred badge too, and would answer for a missing one here.
    section = deaths_section(a_page_with(owns_barrier(10_000)))
    heading = re.search(r'<p class="avail-title">Defensives.*?</p>', section, re.S)
    assert heading is not None
    assert "badge-inferred" in heading.group()
    assert 'href="#provenance"' in heading.group()


def a_page_with_consumables(cast: CastEvent | None = None) -> str:
    loaded = minimal_loaded()
    casts = loaded.casts + ((cast,) if cast else ())
    # Late enough that the health-potion window fits inside the run; an earlier
    # death is one the log cannot see far enough back for, and is not claimed.
    late = tuple(d.model_copy(update={"timestamp_ms": 400_000}) for d in loaded.deaths)
    return render(
        build_report(
            loaded.model_copy(update={"casts": casts, "deaths": late}), minimal_findings(),
            None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, POTIONS,
        )
    )


def test_a_death_card_names_a_consumable_whose_cooldown_was_clear() -> None:
    # A potion drunk at 10s: proof the category is theirs, and outside the
    # window, which opens at 100s for a death at 400s given the 300s cooldown.
    drunk_early = CastEvent(actor_id=1, ability_id=1234768, ability_name="Health Potion",
                            timestamp_ms=10_000, pull_index=0)
    section = deaths_section(a_page_with_consumables(drunk_early))
    assert "health potion" in section
    assert '<li class="ready">' in section


def test_the_consumable_group_carries_its_caveat_beside_it() -> None:
    # It looks identical to the defensive group beside it and is a weaker claim:
    # a defensive is only named once the player demonstrably cast it, while a
    # consumable never proves it was carried. Without the caveat next to it, a
    # reader concludes the player had a potion and did not drink it.
    section = deaths_section(a_page_with_consumables())
    assert "not that one was carried" in section


def test_a_consumable_still_on_cooldown_shows_its_upper_bound() -> None:
    # Drunk at 200s with a 300s cooldown: a charge is free at 500s, so 100 s is
    # a ceiling the log cannot better, never a remaining time.
    drunk = CastEvent(actor_id=1, ability_id=1234768, ability_name="Health Potion",
                      timestamp_ms=200_000, pull_index=0)
    section = deaths_section(a_page_with_consumables(drunk))
    assert '<li class="cooldown">' in section
    assert "at most 100 s left" in section


def test_a_page_with_no_consumable_data_names_no_consumable() -> None:
    section = deaths_section(a_page(NO_DEFENSIVES))
    assert "health potion" not in section
    assert not re.search(AVAILABILITY_ROW, section)


def test_every_pointer_targets_an_anchor_that_exists() -> None:
    html = minimal_html()
    targets = re.findall(r'class="pointer" href="#([^"]+)"', html)
    assert targets, "the minimal fixture has a timed loss, so the Summary must point at it"
    for target in targets:
        assert f'id="{target}"' in html, target


def test_a_pointer_is_a_link_not_a_second_card() -> None:
    # Once-only is anchored on <h3>; a pointer that emitted one would double every loss.
    html = minimal_html()
    pointers = re.findall(r'<a class="pointer"[^>]*>(.*?)</a>', html, flags=re.S)
    assert pointers
    for body in pointers:
        assert "<h3>" not in body
    # Every finding still appears exactly once as a heading, pointers notwithstanding.
    for finding in minimal_findings():
        assert html.count(f"<h3>{escape(finding.title)}</h3>") == 1, finding.id


def test_the_losses_heading_is_absent_when_nothing_was_timed() -> None:
    untimed = tuple(f for f in minimal_findings() if f.seconds_lost is None)
    html = render(
        build_report(
            minimal_loaded(), untimed, None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES,
            NO_CONSUMABLES,
        )
    )
    assert 'id="losses"' not in html
