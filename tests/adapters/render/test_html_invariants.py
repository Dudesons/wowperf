# ABOUTME: Whole-page rules: offline, every finding once, sections in order, and one golden file.
# ABOUTME: The golden fixture is tiny on purpose — a 2000-line diff is a test nobody reads.

import re
from pathlib import Path

import pytest

from tests.domain.report.test_build_frame import FETCHED, a_pull, a_run
from wowperf.adapters.render.html import render
from wowperf.domain.comparison.reference import SpeedReference, SpeedRow
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_report

GOLDEN = Path(__file__).parent / "golden" / "minimal.html"

SECTION_ORDER = ["ledger", "timeline", "deaths", "interrupts", "players", "provenance"]


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
            title="Three enemy casts went uninterrupted",
            detail="Grouped by spell.",
            confidence=Confidence.DERIVED,
        ),
    )


def minimal_html() -> str:
    return render(build_report(minimal_loaded(), minimal_findings(), None, None, None, FETCHED))


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
        build_report(rich_loaded(), rich_findings(), rich_speed_reference(), None, None, FETCHED)
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


def test_a_report_without_a_narrative_renders_seven_sections_not_eight() -> None:
    html = minimal_html()
    assert 'id="narrative"' not in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER)


def test_a_report_with_a_narrative_renders_all_eight() -> None:
    html = render(
        build_report(minimal_loaded(), minimal_findings(), None, None, "A sentence.", FETCHED)
    )
    assert 'id="narrative"' in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER) + 1


def test_every_finding_reaches_the_page() -> None:
    html = minimal_html()
    for finding in minimal_findings():
        assert finding.title in html, finding.id


def test_no_finding_reaches_the_page_twice() -> None:
    # Anchored to the row heading, not to the bare title text: a nested row
    # legitimately quotes its parent's title in "Already counted inside ...",
    # which is a cross-reference, not a second copy of the parent's own row.
    html = minimal_html()
    for finding in minimal_findings():
        assert html.count(f"<h3>{finding.title}</h3>") == 1, finding.id


def test_every_withheld_section_gives_a_reason() -> None:
    html = minimal_html()
    # The timeline is withheld here: no speed reference was passed.
    heading = html.index('id="timeline"')
    deaths = html.index('id="deaths"')
    assert 'class="withheld"' in html[heading:deaths]


def test_the_report_carries_no_total_row() -> None:
    report = build_report(minimal_loaded(), minimal_findings(), None, None, None, FETCHED)
    assert not any(field.startswith("total") for field in type(report).model_fields)
    template = (
        Path(__file__).parents[3] / "src" / "wowperf" / "adapters" / "render" / "report.html.j2"
    ).read_text(encoding="utf-8")
    assert "|sum" not in template
    assert "sum(" not in template


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
