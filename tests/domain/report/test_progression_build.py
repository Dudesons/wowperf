# ABOUTME: The progression page's builder: every judgement made here, none in the template.
# ABOUTME: No death cards and no references -- section 8 sends both elsewhere by design.

import pytest

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series, a_series
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression
from wowperf.domain.report.model import SectionState
from wowperf.domain.report.progression_build import build_progression_report


def a_finding(finding_id: str, title: str = "t") -> Finding:
    return Finding(id=finding_id, title=title, detail="d", confidence=Confidence.MEASURED)


def test_each_finding_lands_on_exactly_one_tab() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )
    findings = [
        a_finding("progression.best"),
        a_finding("progression.best.deaths"),
        a_finding("progression.cluster"),
        a_finding("progression.repeat.phase"),
        a_finding("progression.collapse"),
    ]

    report = build_progression_report(series, findings, fetched_at="2026-09-16 21:04")

    assert [row.finding_id for row in report.best_rows] == [
        "progression.best",
        "progression.best.deaths",
    ]
    assert [row.finding_id for row in report.attempt_rows] == ["progression.cluster"]
    assert [row.finding_id for row in report.repeat_rows] == [
        "progression.repeat.phase",
        "progression.collapse",
    ]
    assert report.observations == ()


def test_a_finding_no_table_places_reaches_the_summary_rather_than_vanishing() -> None:
    series = a_loaded_series(a_loaded_attempt(1, remaining=60.0))

    report = build_progression_report(
        series, [a_finding("progression.something.new", "New")], fetched_at="x"
    )

    assert [row.finding_id for row in report.observations] == ["progression.something.new"]


def test_the_best_tab_is_withheld_when_nothing_was_deepened() -> None:
    series = LoadedProgression(progression=a_series(), loaded=())

    report = build_progression_report(series, [], fetched_at="x")

    assert report.best.state is SectionState.WITHHELD
    assert report.best.reason
    assert any("Best attempt" in line for line in report.provenance.withheld)


def test_the_best_tab_is_present_when_something_was_deepened() -> None:
    series = a_loaded_series(a_loaded_attempt(1, remaining=60.0))

    report = build_progression_report(series, [], fetched_at="x")

    assert report.best.state is SectionState.PRESENT
    assert report.provenance.withheld == ()


def test_a_duplicate_finding_id_is_refused() -> None:
    series = a_loaded_series(a_loaded_attempt(1, remaining=60.0))

    with pytest.raises(ValueError):
        build_progression_report(
            series,
            [a_finding("progression.cluster"), a_finding("progression.cluster")],
            fetched_at="x",
        )


def test_the_provenance_counts_what_was_read_and_carries_no_reference_field() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )

    report = build_progression_report(series, [], fetched_at="2026-09-16 21:04")

    assert report.provenance.report_code == "abc123"
    assert report.provenance.encounter_id == 3492
    assert report.provenance.attempts_counted == 2
    assert report.provenance.attempts_deepened == 2
    assert report.provenance.fetched_at == "2026-09-16 21:04"
    # The type has nowhere to record another player's run, and that is the point.
    assert not hasattr(report.provenance, "references")
