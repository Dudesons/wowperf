# ABOUTME: Behaviour tests for cutting a finding's title at the ability it names.
# ABOUTME: A row keeps its whole title and draws no icon whenever the cut cannot be made cleanly.

from tests.domain.report.test_build_frame import (
    FETCHED,
    NO_CONSUMABLES,
    NO_DEFENSIVES,
    a_loaded,
    a_player,
)
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.report.build import build_report
from wowperf.domain.report.ledger import ledger_row
from wowperf.domain.report.model import LedgerRow, Report, all_ledger_rows


def a_finding(**changes: object) -> Finding:
    finding = Finding(
        id="deaths.single.0",
        title="Stonewake pressed nothing",
        detail="",
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )
    return finding.model_copy(update=changes)


def test_a_title_is_cut_at_the_ability_it_names() -> None:
    row = ledger_row(
        a_finding(title="Emberkin used Ice Block 1 of a possible 7 times",
                  ability_id=45438, ability_name="Ice Block"),
        {},
    )
    assert (row.title_before, row.title_ability, row.title_after) == (
        "Emberkin used ", "Ice Block", " 1 of a possible 7 times"
    )
    assert row.ability_id == 45438


def test_a_title_whose_ability_is_not_in_it_is_left_whole() -> None:
    row = ledger_row(
        a_finding(title="Emberkin pressed nothing",
                  ability_id=45438, ability_name="Ice Block"),
        {},
    )
    assert (row.title_before, row.title_ability, row.title_after) == (
        "Emberkin pressed nothing", "", ""
    )
    assert row.ability_id is None


def test_a_title_naming_its_ability_twice_is_left_whole() -> None:
    # Two occurrences and no way to say which one the reader means, so the row
    # keeps its whole title and draws no icon.
    row = ledger_row(
        a_finding(title="Ice Block was ready; Emberkin used Ice Block 1 of a possible 7 times",
                  ability_id=45438, ability_name="Ice Block"),
        {},
    )
    assert row.title_ability == ""
    assert row.ability_id is None


def test_a_finding_that_names_no_ability_is_left_whole() -> None:
    row = ledger_row(a_finding(title="4 deaths cost 64s of play"), {})
    assert row.title_before == "4 deaths cost 64s of play"
    assert row.ability_id is None


def a_full_report() -> Report:
    """A populated `Report` built from findings that really do name an ability.

    Spread across every row-bearing field, so the concatenation invariant
    below walks more than one shape of row; one finding's ability name
    appears exactly once in its own title, so at least one row is actually
    cut and the invariant is not proved against rows that were never split.
    """
    findings = (
        Finding(id="time.residual", title="Time spent outside pulls", detail="d",
                confidence=Confidence.MEASURED, seconds_lost=300.0),
        Finding(id="deaths.single.0", title="Stonewake used Ice Block 1 of a possible 7 times",
                detail="d",
                confidence=Confidence.MEASURED, seconds_lost=12.0,
                ability_id=45438, ability_name="Ice Block"),
        Finding(id="interrupts.missed.0", title="Emberkin missed an interrupt", detail="d",
                confidence=Confidence.MEASURED, seconds_lost=5.0),
        Finding(id="throughput.readiness.0", title="Bríala had a cooldown ready and unpressed",
                detail="d", confidence=Confidence.MEASURED, seconds_lost=None),
        Finding(id="trash.overage", title="Trash pulled too slow", detail="d",
                confidence=Confidence.MEASURED, seconds_lost=20.0),
        Finding(id="misc.note", title="Кириллица did something unusual", detail="d",
                confidence=Confidence.DERIVED, seconds_lost=None),
    )
    return build_report(
        a_loaded(), findings, None, None, a_player(), None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )


def test_every_row_of_a_real_report_can_be_reassembled_from_its_parts() -> None:
    # Two representations of one sentence would drift apart on their own; this
    # is what keeps them one sentence, checked over every row-bearing field
    # `all_ledger_rows` reaches.
    report = a_full_report()
    rows: list[LedgerRow] = list(all_ledger_rows(report))
    assert rows, "a report with no findings would make this vacuous"
    assert any(row.title_ability for row in rows), (
        "no row was actually cut, so the concatenation check below would hold vacuously"
    )
    for row in rows:
        assert row.title_before + row.title_ability + row.title_after == row.title
