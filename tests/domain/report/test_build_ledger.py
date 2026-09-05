# ABOUTME: Behaviour tests for the seconds ledger: two parts, nesting stated, never a total.
# ABOUTME: The nesting lines are what stop a reader adding figures that already contain each other.

from tests.domain.report.test_build_frame import FETCHED, a_loaded, a_player
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.report.build import build_report, parent_of
from wowperf.domain.report.model import LedgerRow


def a_finding(finding_id: str, seconds: float | None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.MEASURED,
        seconds_lost=seconds,
    )


def ids(rows: tuple[LedgerRow, ...]) -> list[str]:
    return [row.finding_id for row in rows]


def test_a_top_level_figure_goes_to_the_decomposition() -> None:
    report = build_report(
        a_loaded(), (a_finding("time.residual", 300.0),), None, None, a_player(), None, FETCHED
    )
    assert ids(report.ledger_decomposition) == ["time.residual"]
    assert ids(report.ledger_losses) == []


def test_a_ranked_loss_goes_to_the_losses() -> None:
    report = build_report(
        a_loaded(), (a_finding("time.gap.0", 41.0),), None, None, a_player(), None, FETCHED
    )
    assert ids(report.ledger_losses) == ["time.gap.0"]
    assert ids(report.ledger_decomposition) == []


def test_a_loss_that_nests_says_what_contains_it() -> None:
    # Title copied from analysis/timeline.py's `time.residual` finding, not the id:
    # a reader must see a sentence, never a dotted internal identifier.
    report = build_report(
        a_loaded(),
        (
            a_finding("time.residual", 300.0, title="Time spent outside pulls"),
            a_finding("time.gap.0", 41.0),
        ),
        None,
        None,
        a_player(),
        None,
        FETCHED,
    )
    assert report.ledger_losses[0].nests_inside == "Time spent outside pulls"


def test_a_loss_whose_parent_is_absent_from_this_run_says_nothing() -> None:
    # `time.gap.0` nests inside `time.residual`, but that finding never arrived
    # in this run's findings; pointing at a row that is not on the page would be
    # worse than staying silent, so `nests_inside` must not fall back to the id.
    report = build_report(
        a_loaded(), (a_finding("time.gap.0", 41.0),), None, None, a_player(), None, FETCHED
    )
    assert report.ledger_losses[0].nests_inside is None


def test_a_loss_that_nests_in_nothing_says_nothing() -> None:
    report = build_report(
        a_loaded(), (a_finding("trash.overage", 55.0),), None, None, a_player(), None, FETCHED
    )
    assert report.ledger_losses[0].nests_inside is None


def test_a_finding_with_no_seconds_never_reaches_the_ledger() -> None:
    report = build_report(
        a_loaded(), (a_finding("players.damage.0", None),), None, None, a_player(), None, FETCHED
    )
    assert ids(report.ledger_decomposition) == []
    assert ids(report.ledger_losses) == []


def test_losses_keep_the_order_they_arrived_in() -> None:
    # `rank_findings` has already ordered them; the ledger must not re-sort.
    report = build_report(
        a_loaded(),
        (a_finding("time.gap.0", 90.0), a_finding("compare.downtime", 40.0)),
        None,
        None,
        a_player(),
        None,
        FETCHED,
    )
    assert ids(report.ledger_losses) == ["time.gap.0", "compare.downtime"]


def test_seconds_reach_the_row_already_formatted() -> None:
    report = build_report(
        a_loaded(), (a_finding("time.gap.0", 252.0),), None, None, a_player(), None, FETCHED
    )
    assert report.ledger_losses[0].seconds == "4:12"


def test_the_badge_carries_a_word_not_only_a_tint() -> None:
    report = build_report(
        a_loaded(), (a_finding("time.gap.0", 12.0),), None, None, a_player(), None, FETCHED
    )
    assert report.ledger_losses[0].badge.label == "measured"


def test_every_nesting_relationship_the_findings_file_declares() -> None:
    assert parent_of("time.gap.3") == "time.residual"
    assert parent_of("compare.downtime") == "time.residual"
    assert parent_of("deaths.single.0") == "deaths.total"
    assert parent_of("deaths.chain.1") == "deaths.total"
    assert parent_of("compare.route.skipped.2") == "trash.overage"
    assert parent_of("trash.overage") is None
    assert parent_of("compare.duration") is None
