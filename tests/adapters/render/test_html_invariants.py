# ABOUTME: Whole-page rules: offline, every finding once, sections in order, and one golden file.
# ABOUTME: The golden fixture is tiny on purpose — a 2000-line diff is a test nobody reads.

import re
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from markupsafe import escape

from tests.domain.report.test_build_frame import FETCHED, NO_DEFENSIVES, a_pull, a_run
from tests.domain.report.test_model import view_model_types
from wowperf.adapters.render.html import render
from wowperf.domain.comparison.reference import SpeedReference, SpeedRow
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import Header, Provenance, Timeline, TimelineBlock, TimelineTrack
from wowperf.domain.season import DefensiveAbility, Defensives

GOLDEN = Path(__file__).parent / "golden" / "minimal.html"

# The player being analysed, from our own roster -- never a reference run's top
# parser, which names a different character in a different log (item 1).
SUBJECT = Player(actor_id=1, name="Uglymage", class_name="Mage", spec="Arcane", item_level=680)

SECTION_ORDER = [
    "ledger", "timeline", "deaths", "interrupts", "players", "observations", "provenance",
]


def minimal_loaded() -> LoadedRun:
    return LoadedRun(
        run=a_run(
            players=(
                Player(
                    actor_id=1,
                    name="Uglymage",
                    class_name="Mage",
                    spec="Arcane",
                    item_level=680,
                ),
            ),
            pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 200_000, encounter_id=12825)),
        ),
        casts=(CastEvent(actor_id=1, ability_id=1, ability_name="Arcane Blast",
                         timestamp_ms=10_000, pull_index=0),),
        deaths=(Death(player_name="Uglymage", actor_id=1, timestamp_ms=50_000,
                      killing_blow="Frigid Roar", pull_index=0),),
        damage_taken=(DamageTakenEvent(actor_id=1, ability_id=2, ability_name="Snowdrift",
                                       amount=82_410, timestamp_ms=45_000, pull_index=0),),
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
    )


def minimal_html() -> str:
    return render(
        build_report(
            minimal_loaded(), minimal_findings(), None, None, SUBJECT, None, FETCHED,
            NO_DEFENSIVES,
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
                Player(actor_id=1, name="Uglymage", class_name="Mage", spec="Arcane",
                       item_level=680),
                Player(actor_id=2, name="Dudesons", class_name="DeathKnight", spec="Blood",
                       item_level=675),
            ),
            pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 200_000, encounter_id=12825)),
        ),
    )


def rich_speed_reference() -> SpeedReference:
    # A reference run makes the timeline present (so it renders its SVG) and
    # gives provenance a Warcraft Logs link to the reference report.
    reference_run = a_run(
        report_code="ref001",
        fight_id=7,
        pulls=(a_pull(0, 0, 55_000), a_pull(1, 105_000, 190_000, encounter_id=12825)),
    )
    return SpeedReference(
        row=SpeedRow(
            report_code="ref001", fight_id=7, keystone_level=16, duration_ms=190_000, deaths=0
        ),
        loaded=LoadedRun(run=reference_run),
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
    # No ParseReference is passed, so the spell-and-talent comparison on each
    # player card is withheld, giving the page a withheld section as well.
    return render(
        build_report(
            rich_loaded(), rich_findings(), rich_speed_reference(), None, SUBJECT, None, FETCHED
        , NO_DEFENSIVES)
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


def test_the_page_fetches_nothing_at_all() -> None:
    # A Warcraft Logs reference-run link and the SVG's own namespace attribute
    # both legitimately contain "http://" without fetching anything, so
    # self-containment is checked by what the page can *execute* or *load*,
    # not by whether the string appears at all.
    html = rich_html()
    assert "<script" not in html.lower()
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src


def test_every_href_is_a_fragment_or_a_report_link_the_reader_asked_for() -> None:
    html = rich_html()
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith("#") for href in hrefs)
    assert any(href.startswith("https://www.warcraftlogs.com/reports/") for href in hrefs)
    for href in hrefs:
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ), href


def test_every_section_appears_in_the_order_the_design_fixes() -> None:
    html = minimal_html()
    positions = [html.index(f'id="{name}"') for name in SECTION_ORDER]
    assert positions == sorted(positions)


def test_a_report_without_a_narrative_renders_eight_sections_not_nine() -> None:
    # Header (h1) plus the seven always-present h2 sections in SECTION_ORDER.
    html = minimal_html()
    assert 'id="narrative"' not in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER)


def test_a_report_with_a_narrative_renders_nine_sections_not_eight() -> None:
    # Header (h1) plus the seven always-present h2 sections plus narrative.
    html = render(
        build_report(
            minimal_loaded(), minimal_findings(), None, None, SUBJECT, "A sentence.", FETCHED
        , NO_DEFENSIVES)
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
}


def test_the_report_carries_no_total_row() -> None:
    # This proves two things, and no more than these two:
    # (1) no field on `Report` or any view model it nests is a bare number that
    #     could hold a total -- every seconds-lost figure reaches the page
    #     already formatted as a string on `LedgerRow.seconds`, so the only
    #     numeric fields left are an id, a difficulty tier and a handful of SVG
    #     coordinates, all named on the allowlist above; and
    # (2) the template holds no Jinja `{% set %}` accumulator that could total
    #     figures on its own, whether spelled as an obvious `|sum`/`sum(` call
    #     or a hand-rolled running total in a loop variable.
    # It does NOT prove no total is computed anywhere in the codebase -- only
    # that the report's own view model and template have nowhere to hold or
    # build one.
    report = build_report(
        minimal_loaded(), minimal_findings(), None, None, SUBJECT, None, FETCHED,
        NO_DEFENSIVES,
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

    template = (
        Path(__file__).parents[3] / "src" / "wowperf" / "adapters" / "render" / "report.html.j2"
    ).read_text(encoding="utf-8")
    assert "|sum" not in template
    assert "sum(" not in template
    assert "{% set" not in template


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
            minimal_loaded(), minimal_findings(), None, None, SUBJECT, None, FETCHED, defensives
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
            None, None, SUBJECT, None, FETCHED, ARCANE,
        )
    )


def test_a_death_card_names_the_defensives_that_were_available() -> None:
    # Cast at 10s, outside the window that opens at 15s for a 25s cooldown.
    section = deaths_section(a_page_with(owns_barrier(10_000)))
    assert "Defensives off cooldown: Prismatic Barrier" in section


def test_a_death_card_says_so_when_nothing_was_off_cooldown() -> None:
    # Cast at 45s, inside the window that ends at the death at 50s.
    section = deaths_section(a_page_with(owns_barrier(45_000)))
    assert "Defensives off cooldown: none" in section
    assert "Prismatic Barrier" not in section


def test_an_unchecked_spec_makes_no_claim_either_way() -> None:
    # The silence a reader must not mistake for "nothing was up".
    section = deaths_section(a_page(NO_DEFENSIVES))
    assert "Defensives off cooldown" not in section
    assert "off cooldown" not in section


def test_the_defensives_line_carries_its_confidence_badge() -> None:
    # The only inferred claim on a card whose other facts are all measured. Without
    # a badge a reader has no way to tell it is reconstructed rather than logged.
    section = deaths_section(a_page_with(owns_barrier(10_000)))
    assert "badge-inferred" in section
    assert 'href="#provenance"' in section
