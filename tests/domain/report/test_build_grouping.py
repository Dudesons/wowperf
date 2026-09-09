# ABOUTME: Tests that a run of findings sharing one explanation states it once, above the run.
# ABOUTME: Four cards each repeating the same paragraph is the page telling a reader to skip it.

from tests.domain.report.test_build_frame import (
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    a_loaded,
    a_player,
)
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.report.build import build_report
from wowperf.domain.report.ledger import collapse_repeated_details
from wowperf.domain.report.model import Badge, LedgerRow

BADGE = Badge(label="measured", tint="measured")


def a_row(finding_id: str, detail: str) -> LedgerRow:
    return LedgerRow(finding_id=finding_id, title=finding_id, detail=detail, badge=BADGE)


def notes_and_details(rows: tuple[LedgerRow, ...]) -> list[tuple[str, str]]:
    return [(row.group_note, row.detail) for row in rows]


def test_a_run_sharing_one_explanation_states_it_once_above_the_run() -> None:
    """The whole point: three cards, one paragraph, hoisted off the first row."""
    rows = (a_row("a", "shared"), a_row("b", "shared"), a_row("c", "shared"))

    assert notes_and_details(collapse_repeated_details(rows)) == [
        ("shared", ""),
        ("", ""),
        ("", ""),
    ]


def test_two_adjacent_rows_are_already_a_run() -> None:
    rows = (a_row("a", "shared"), a_row("b", "shared"))

    assert notes_and_details(collapse_repeated_details(rows)) == [("shared", ""), ("", "")]


def test_rows_that_explain_themselves_differently_are_left_alone() -> None:
    rows = (a_row("a", "one"), a_row("b", "two"), a_row("c", "three"))

    assert notes_and_details(collapse_repeated_details(rows)) == [
        ("", "one"),
        ("", "two"),
        ("", "three"),
    ]


def test_a_lone_row_keeps_its_own_detail() -> None:
    """A note above a single card would be the same sentence moved, not one saved."""
    rows = (a_row("a", "only"),)

    assert notes_and_details(collapse_repeated_details(rows)) == [("", "only")]


def test_a_repeat_that_is_not_adjacent_is_not_a_run() -> None:
    """Hoisting across an unrelated row would attach the note to that row too.

    Order here is the ranking `rank_findings` already decided, so grouping
    must never reorder to bring equal details together.
    """
    rows = (a_row("a", "shared"), a_row("b", "other"), a_row("c", "shared"))

    assert notes_and_details(collapse_repeated_details(rows)) == [
        ("", "shared"),
        ("", "other"),
        ("", "shared"),
    ]


def test_rows_carrying_no_detail_gain_no_note() -> None:
    """Empty details match each other, and hoisting emptiness would emit a blank note."""
    rows = (a_row("a", ""), a_row("b", ""))

    assert notes_and_details(collapse_repeated_details(rows)) == [("", ""), ("", "")]


def test_two_runs_in_one_tuple_each_get_their_own_note() -> None:
    rows = (
        a_row("a", "first"),
        a_row("b", "first"),
        a_row("c", "second"),
        a_row("d", "second"),
    )

    assert notes_and_details(collapse_repeated_details(rows)) == [
        ("first", ""),
        ("", ""),
        ("second", ""),
        ("", ""),
    ]


def test_grouping_changes_nothing_else_about_a_row() -> None:
    """Only the explanation moves: the id a deep link uses must survive."""
    rows = (a_row("time.gap.0", "shared"), a_row("time.gap.1", "shared"))

    collapsed = collapse_repeated_details(rows)

    assert [row.finding_id for row in collapsed] == ["time.gap.0", "time.gap.1"]
    assert [row.title for row in collapsed] == ["time.gap.0", "time.gap.1"]


def a_finding(finding_id: str, detail: str) -> Finding:
    return Finding(
        id=finding_id,
        title=finding_id,
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=1.0,
    )


def test_a_built_report_states_a_repeated_explanation_once() -> None:
    """Proves the collapse is wired into the tab, not merely available to it."""
    report = build_report(
        a_loaded(),
        (
            a_finding("time.gap.0", "same reason"),
            a_finding("time.gap.1", "same reason"),
            a_finding("time.gap.2", "same reason"),
        ),
        None,
        None,
        a_player(),
        None,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )

    assert notes_and_details(report.route_rows) == [
        ("same reason", ""),
        ("", ""),
        ("", ""),
    ]
