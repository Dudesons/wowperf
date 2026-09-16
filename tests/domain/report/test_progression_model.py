# ABOUTME: Behaviour tests for the progression report view model and its row walker.
# ABOUTME: The walker is checked against the model's own fields, not a hand-kept list.

from wowperf.domain.report.model import Badge, LedgerRow, Section, SectionState
from wowperf.domain.report.progression_model import (
    AttemptsChart,
    ProgressionHeader,
    ProgressionProvenance,
    ProgressionReport,
    all_progression_ledger_rows,
)


def a_section(state: SectionState = SectionState.PRESENT, reason: str = "") -> Section:
    return Section(state=state, reason=reason)


def a_ledger_row(**changes: object) -> LedgerRow:
    row = LedgerRow(
        finding_id="progression.cluster",
        title="The attempts split into a short cluster and a long one",
        title_before="The attempts split into a short cluster and a long one",
        detail="Four ran under two minutes; three ran past three and a half.",
        badge=Badge(label="derived", tint="badge-derived"),
    )
    return row.model_copy(update=changes)


def a_progression_header(**changes: object) -> ProgressionHeader:
    header = ProgressionHeader(
        boss="The Hollow Choir",
        difficulty="Mythic",
        size=20,
        outcome="No kill in 7 attempts",
        attempts_counted=7,
        attempts_discarded=1,
        depth_label="encounter progress",
    )
    return header.model_copy(update=changes)


def a_progression_provenance(**changes: object) -> ProgressionProvenance:
    provenance = ProgressionProvenance(
        report_code="abc123",
        encounter_id=3492,
        attempts_counted=7,
        attempts_deepened=3,
        fetched_at="2026-09-16 08:14",
    )
    return provenance.model_copy(update=changes)


def a_progression_report(**changes: object) -> ProgressionReport:
    report = ProgressionReport(
        header=a_progression_header(),
        chart=AttemptsChart(section=a_section()),
        attempts=(),
        attempt_rows=(),
        repeat_rows=(),
        best_rows=(),
        best=a_section(),
        observations=(),
        provenance=a_progression_provenance(),
    )
    return report.model_copy(update=changes)


def a_progression_report_with_one_row_in_every_field(row_fields: set[str]) -> ProgressionReport:
    updates = {name: (a_ledger_row(finding_id=f"finding-in-{name}"),) for name in row_fields}
    return a_progression_report(**updates)


def test_every_field_holding_rows_is_walked() -> None:
    """The walker is the icon resolver's only map of the page.

    A row whose ability reaches the page without reaching the resolver draws
    nothing and reports nothing -- the failure is a missing picture, which no
    other test would see. So the walker is checked against the model's own
    fields rather than against a list somebody kept in step by hand: a sixth
    row-bearing field added later shows up here automatically, tagged and
    walked, with no line in this test to remember to update.
    """
    row_fields = {
        name
        for name, field in ProgressionReport.model_fields.items()
        if field.annotation == tuple[LedgerRow, ...]
    }
    assert row_fields, "no field on the model holds rows at all"

    report = a_progression_report_with_one_row_in_every_field(row_fields)
    walked = {row.finding_id for row in all_progression_ledger_rows(report)}

    assert walked == {f"finding-in-{name}" for name in row_fields}
