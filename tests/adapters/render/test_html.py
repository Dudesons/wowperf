# ABOUTME: Behaviour tests for the HTML adapter: self-contained, escaped, every section present.
# ABOUTME: Self-containment is asserted rather than trusted — the file must work offline from disk.

from markupsafe import escape

from wowperf.adapters.render.html import render
from wowperf.domain.report.model import (
    Badge,
    Header,
    LedgerRow,
    Provenance,
    ReferenceRecord,
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
        "summary_pointers": (),
        "timeline": Timeline(section=Section(state=SectionState.WITHHELD, reason="no reference")),
        "route": Section(state=SectionState.PRESENT),
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


def test_the_header_is_rendered() -> None:
    # Escaped on comparison: real dungeon names can carry an apostrophe
    # (Atal'Dazar was a Mythic+ dungeon), and autoescape would turn it into `&#39;`.
    html = render(a_report())
    assert str(escape("Den of Nalorakk")) in html
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
    # Escaped on comparison: a hand-written narrative is free text and can
    # carry an apostrophe or ampersand, which autoescape would transform.
    narrative = "Both losses were travel, not damage."
    html = render(a_report(narrative=narrative))
    assert str(escape(narrative)) in html


def test_a_narrative_cannot_smuggle_markup_into_the_page() -> None:
    html = render(a_report(narrative="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_a_pack_name_from_the_api_cannot_smuggle_markup_either() -> None:
    html = render(a_report(route_rows=(a_row(title="<img onerror=x>"),)))
    assert "<img onerror=x>" not in html
    assert "&lt;img" in html


def test_a_ledger_row_shows_its_badge_as_a_word() -> None:
    html = render(a_report(route_rows=(a_row(),)))
    assert "measured" in html


def test_a_nested_row_says_what_contains_it() -> None:
    # Checked against the wrapping phrase, not the bare value: a row whose
    # `nests_inside` happened to appear elsewhere on the page for an unrelated
    # reason would still satisfy a plain substring check, so this pins the
    # value to the sentence the template is supposed to wrap it in.
    html = render(a_report(route_rows=(a_row(nests_inside="Time spent outside pulls"),)))
    assert "Already counted inside Time spent outside pulls." in html


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
                references=(
                    ReferenceRecord(
                        report_code="speed1", fight_id=1, keystone_level=16,
                        url="https://www.warcraftlogs.com/reports/speed1?fight=1", axis="speed",
                    ),
                    ReferenceRecord(
                        report_code="parse1", fight_id=2, keystone_level=16,
                        url="https://www.warcraftlogs.com/reports/parse1?fight=2", axis="parse",
                    ),
                ),
            )
        )
    )
    assert 'href="https://www.warcraftlogs.com/reports/speed1?fight=1"' in html
    assert 'href="https://www.warcraftlogs.com/reports/parse1?fight=2"' in html


def test_provenance_says_which_references_were_reused_from_cache() -> None:
    """The reference cache is shared across analyses, so a reference may not have
    been fetched for this report at all. A page that discloses every candidate it
    weighed must disclose that too, or the reuse stays invisible."""
    html = render(
        a_report(
            provenance=Provenance(
                report_code="abc123",
                fight_id=36,
                fetched_at="2026-09-05 14:02",
                references=(
                    ReferenceRecord(
                        report_code="cached", fight_id=1, keystone_level=16,
                        url="https://www.warcraftlogs.com/reports/cached?fight=1", axis="speed",
                        from_cache=True,
                    ),
                    ReferenceRecord(
                        report_code="fresh", fight_id=2, keystone_level=16,
                        url="https://www.warcraftlogs.com/reports/fresh?fight=2", axis="speed",
                    ),
                ),
            )
        )
    )
    cached, fresh = html.split("reports/cached?fight=1")[1].split("reports/fresh?fight=2")[:2]

    assert "reused from cache" in cached
    assert "reused from cache" not in fresh


def test_provenance_states_why_a_candidate_was_not_used() -> None:
    html = render(
        a_report(
            provenance=Provenance(
                report_code="abc123",
                fight_id=36,
                fetched_at="2026-09-05 14:02",
                references=(
                    ReferenceRecord(
                        report_code="speed1", fight_id=1, keystone_level=16,
                        url="https://www.warcraftlogs.com/reports/speed1?fight=1", axis="speed",
                        loaded=False, reason="this is the run under analysis",
                    ),
                ),
            )
        )
    )
    assert "this is the run under analysis" in html


def test_a_reference_records_reason_cannot_smuggle_markup() -> None:
    html = render(
        a_report(
            provenance=Provenance(
                report_code="abc123",
                fight_id=36,
                fetched_at="2026-09-05 14:02",
                references=(
                    ReferenceRecord(
                        report_code="speed1", fight_id=1, keystone_level=16,
                        url="https://www.warcraftlogs.com/reports/speed1?fight=1", axis="speed",
                        loaded=False, reason="<img onerror=x>",
                    ),
                ),
            )
        )
    )
    assert "<img onerror=x>" not in html
    assert "&lt;img" in html


def test_provenance_renders_no_reference_link_when_none_were_considered() -> None:
    html = render(a_report())
    assert "reference run" not in html.lower()
    assert "warcraftlogs.com/reports/" not in html


def test_the_confidence_legend_explains_all_three_badges() -> None:
    # Anchored to the badge span and the sentence that follows it, not the
    # bare word: "measured", "derived" and "inferred" already appear as a
    # ledger row's own badge label, so a loose substring check would still
    # pass with one or more explanations missing from the legend itself.
    html = render(a_report())
    legend = html[html.index('<p class="legend">', html.index('id="provenance"')) :]
    assert '<span class="badge badge-measured">measured</span> read from the log' in legend
    assert (
        '<span class="badge badge-derived">derived</span> reconstructed by a documented rule'
        in legend
    )
    assert (
        '<span class="badge badge-inferred">inferred</span> requires an assumption'
        in legend
    )
