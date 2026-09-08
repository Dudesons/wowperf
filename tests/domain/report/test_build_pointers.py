# ABOUTME: Behaviour tests for the Summary's pointers: the biggest timed losses, in the order
# ABOUTME: rank_findings already gave them, never a decomposition row, never re-sorted.

from collections.abc import Sequence

from tests.domain.report.test_build_frame import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES, a_run
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import POINTER_COUNT, build_report
from wowperf.domain.report.model import LedgerRow, Report

SUBJECT = Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=680)


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.MEASURED,
        seconds_lost=seconds,
    )


def a_report_of(*findings: Finding) -> Report:
    return build_report(
        LoadedRun(run=a_run(players=(SUBJECT,))), findings, None, None, SUBJECT, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )


def ids(rows: Sequence[LedgerRow]) -> list[str]:
    return [row.finding_id for row in rows]


def test_pointers_are_the_timed_findings_in_the_order_they_arrived() -> None:
    report = a_report_of(a_finding("time.gap.0", 90.0), a_finding("compare.downtime", 40.0))
    assert ids(report.summary_pointers) == ["time.gap.0", "compare.downtime"]


def test_pointers_stop_at_the_count_the_builder_fixes() -> None:
    findings = tuple(a_finding(f"time.gap.{i}", 100.0 - i) for i in range(POINTER_COUNT + 2))
    report = a_report_of(*findings)
    assert len(report.summary_pointers) == POINTER_COUNT
    assert ids(report.summary_pointers) == [f"time.gap.{i}" for i in range(POINTER_COUNT)]


def test_a_decomposition_row_is_never_a_pointer() -> None:
    # It already heads the ledger on the same tab; pointing at it would say it twice.
    report = a_report_of(a_finding("time.residual", 300.0), a_finding("time.gap.0", 41.0))
    assert ids(report.summary_pointers) == ["time.gap.0"]


def test_an_untimed_finding_is_never_a_pointer() -> None:
    report = a_report_of(a_finding("interrupts.summary"), a_finding("time.gap.0", 41.0))
    assert ids(report.summary_pointers) == ["time.gap.0"]


def test_no_timed_loss_means_no_pointers() -> None:
    report = a_report_of(a_finding("interrupts.summary"))
    assert report.summary_pointers == ()


def test_a_pointer_equals_the_card_it_points_at() -> None:
    # Same title, seconds and badge, by construction from the same finding.
    report = a_report_of(a_finding("time.gap.0", 41.0, title="A 41 second gap"))
    assert report.summary_pointers == (report.route_rows[0],)
