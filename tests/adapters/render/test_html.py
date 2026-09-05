# ABOUTME: Behaviour tests for the HTML adapter: self-contained, escaped, every section present.
# ABOUTME: Self-containment is asserted rather than trusted — the file must work offline from disk.

import re

from wowperf.adapters.render.html import render
from wowperf.domain.report.model import (
    Badge,
    Header,
    LedgerRow,
    Provenance,
    Report,
    Section,
    SectionState,
    Timeline,
)


def a_row(finding_id: str = "time.gap.0", **overrides: object) -> LedgerRow:
    fields: dict[str, object] = {
        "finding_id": finding_id,
        "title": "A 41 second gap after pull 7",
        "detail": "Travel, not combat.",
        "badge": Badge(label="measured", tint="badge-measured"),
        "seconds": "0:41",
        "nests_inside": None,
        "evidence": ("next pull begins at Loa Speaker Nanea",),
    }
    fields.update(overrides)
    return LedgerRow(**fields)  # type: ignore[arg-type]


def a_report(**overrides: object) -> Report:
    fields: dict[str, object] = {
        "header": Header(
            dungeon="Den of Nalorakk",
            keystone_level=16,
            affixes=("Tyrannical",),
            result="Timed by 2:14",
        ),
        "narrative": None,
        "ledger_decomposition": (),
        "ledger_losses": (),
        "timeline": Timeline(section=Section(state=SectionState.WITHHELD, reason="no reference")),
        "deaths": (),
        "interrupts": (),
        "players": (),
        "observations": (),
        "provenance": Provenance(
            report_code="abc123", fight_id=36, fetched_at="2026-09-05 14:02"
        ),
    }
    fields.update(overrides)
    return Report(**fields)  # type: ignore[arg-type]


def test_the_document_is_html() -> None:
    assert render(a_report()).lstrip().lower().startswith("<!doctype html>")


def test_nothing_is_fetched_from_anywhere() -> None:
    html = render(a_report())
    assert "<script" not in html.lower()
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src


def test_every_href_is_a_fragment_or_a_report_link_the_reader_asked_for() -> None:
    html = render(
        a_report(
            ledger_losses=(a_row(),),
            provenance=Provenance(
                report_code="abc123",
                fight_id=36,
                fetched_at="2026-09-05 14:02",
                speed_reference_url="https://www.warcraftlogs.com/reports/xyz789?fight=12",
            ),
        )
    )
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert any(href.startswith("#") for href in hrefs)
    assert any(href.startswith("https://www.warcraftlogs.com/reports/") for href in hrefs)
    for href in hrefs:
        assert href.startswith("#") or href.startswith(
            "https://www.warcraftlogs.com/reports/"
        ), href


def test_the_header_is_rendered() -> None:
    html = render(a_report())
    assert "Den of Nalorakk" in html
    assert "Timed by 2:14" in html


def test_affixes_are_labeled_since_no_name_source_exists() -> None:
    # No affix-name source exists anywhere in this codebase, so the raw ids
    # are still shown -- but labeled, so a reader knows what the bare
    # integers are rather than reading "31:49 · 9, 10, 147".
    html = render(
        a_report(
            header=Header(
                dungeon="Den of Nalorakk",
                keystone_level=16,
                affixes=("9", "10", "147"),
                result="Timed in 31:49",
            )
        )
    )
    assert "Affixes 9, 10, 147" in html


def test_a_run_with_no_narrative_renders_no_narrative_section() -> None:
    assert "id=\"narrative\"" not in render(a_report())


def test_a_narrative_is_rendered_when_present() -> None:
    html = render(a_report(narrative="Both losses were travel, not damage."))
    assert "Both losses were travel, not damage." in html


def test_a_narrative_cannot_smuggle_markup_into_the_page() -> None:
    html = render(a_report(narrative="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_a_pack_name_from_the_api_cannot_smuggle_markup_either() -> None:
    html = render(a_report(ledger_losses=(a_row(title="<img onerror=x>"),)))
    assert "<img onerror=x>" not in html
    assert "&lt;img" in html


def test_a_ledger_row_shows_its_badge_as_a_word() -> None:
    html = render(a_report(ledger_losses=(a_row(),)))
    assert "measured" in html


def test_a_nested_row_says_what_contains_it() -> None:
    html = render(a_report(ledger_losses=(a_row(nests_inside="time.residual"),)))
    assert "time.residual" in html


def test_a_withheld_section_renders_its_heading_and_its_reason() -> None:
    html = render(a_report())
    assert "Aligned timeline" in html
    assert "no reference" in html


def test_provenance_names_the_report_and_when_it_was_fetched() -> None:
    html = render(a_report())
    assert "abc123" in html
    assert "2026-09-05 14:02" in html


def test_provenance_links_each_reference_run_when_its_url_is_present() -> None:
    html = render(
        a_report(
            provenance=Provenance(
                report_code="abc123",
                fight_id=36,
                fetched_at="2026-09-05 14:02",
                speed_reference_url="https://www.warcraftlogs.com/reports/speed1?fight=1",
                parse_reference_url="https://www.warcraftlogs.com/reports/parse1?fight=2",
            )
        )
    )
    assert 'href="https://www.warcraftlogs.com/reports/speed1?fight=1"' in html
    assert 'href="https://www.warcraftlogs.com/reports/parse1?fight=2"' in html


def test_provenance_renders_no_reference_link_when_the_url_is_absent() -> None:
    html = render(a_report())
    assert "reference run" not in html.lower()
    assert "warcraftlogs.com/reports/" not in html


def test_the_confidence_legend_explains_all_three_badges() -> None:
    html = render(a_report())
    for word in ("measured", "derived", "inferred"):
        assert word in html
