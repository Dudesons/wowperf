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


def test_the_summary_points_at_the_three_repeats_in_their_order() -> None:
    """Killing blow, first death, ability -- whatever order the findings came in.

    Each pointer is the Repeats card itself, so a pointer can never say something
    its card does not, and the findings that are not one of the three (the
    phase, a pooled readiness line) are never pointed at.
    """
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )
    findings = [
        a_finding("progression.repeat.ability", "An ability kept landing"),
        a_finding("progression.repeat.phase", "A phase kept ending it"),
        a_finding("progression.repeat.ready.emberkin", "A cooldown was ready"),
        a_finding("progression.repeat.killing_blow", "A killing blow kept repeating"),
        a_finding("progression.repeat.first_death", "A player fell first"),
    ]

    report = build_progression_report(series, findings, fetched_at="x")

    assert [row.finding_id for row in report.repeat_pointers] == [
        "progression.repeat.killing_blow",
        "progression.repeat.first_death",
        "progression.repeat.ability",
    ]
    cards = {row.finding_id: row for row in report.repeat_rows}
    for pointer in report.repeat_pointers:
        assert pointer == cards[pointer.finding_id]


def test_a_summary_with_no_repeat_carries_no_pointer() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )

    only_the_phase = build_progression_report(
        series, [a_finding("progression.repeat.phase")], fetched_at="x"
    )
    nothing = build_progression_report(series, [], fetched_at="x")

    assert only_the_phase.repeat_pointers == ()
    assert nothing.repeat_pointers == ()


def test_a_pointer_names_only_the_repeats_present() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )

    report = build_progression_report(
        series,
        [a_finding("progression.repeat.ability"), a_finding("progression.repeat.first_death")],
        fetched_at="x",
    )

    assert [row.finding_id for row in report.repeat_pointers] == [
        "progression.repeat.first_death",
        "progression.repeat.ability",
    ]


def test_the_summary_header_leads_with_the_headline() -> None:
    series = a_loaded_series(
        a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)
    )

    report = build_progression_report(series, [], fetched_at="x")

    assert report.header.headline == (
        "No kill in 2 attempts; the deepest left 20.0% encounter progress"
    )


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


def test_the_provenance_states_what_was_read_and_deepened_in_the_right_number() -> None:
    once = build_progression_report(
        a_loaded_series(a_loaded_attempt(1, remaining=60.0)), [], fetched_at="x"
    )
    twice = build_progression_report(
        a_loaded_series(a_loaded_attempt(1, remaining=60.0), a_loaded_attempt(2, remaining=20.0)),
        [],
        fetched_at="x",
    )

    assert once.provenance.read_line == "1 attempt read and 1 deepened"
    assert twice.provenance.read_line == "2 attempts read and 2 deepened"


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
