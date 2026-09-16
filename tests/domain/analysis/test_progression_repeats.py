# ABOUTME: Behaviour tests for the phase a night's attempts most often ended in.
# ABOUTME: Every guard -- separatesWipes, an empty phase table, phase zero -- gets its own case.

from tests.domain.progression_fixtures import a_series as series
from tests.domain.test_progression import an_attempt
from wowperf.domain.analysis.progression_repeats import repeat_phase
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence


def attempt(fight_id: int, *, last_phase: int | None = None) -> Encounter:
    """One qualifying attempt, 200 seconds long, at a stated ending phase."""
    return an_attempt(fight_id, 50.0, 200.0, last_phase=last_phase)


def test_names_the_phase_most_attempts_ended_in() -> None:
    finding = repeat_phase(
        series(
            attempt(1, last_phase=2),
            attempt(2, last_phase=2),
            attempt(3, last_phase=3),
        )
    )
    assert finding is not None
    assert "Intermission: Tide" in finding.title
    assert "2 of 3" in finding.title
    assert finding.confidence is Confidence.MEASURED


def test_is_silent_when_the_api_says_phases_do_not_separate_wipes() -> None:
    assert (
        repeat_phase(
            series(attempt(1, last_phase=2), attempt(2, last_phase=2), separates_wipes=False)
        )
        is None
    )


def test_is_silent_when_the_boss_has_no_phase_table() -> None:
    finding = repeat_phase(
        series(attempt(1, last_phase=2), attempt(2, last_phase=2), phases=())
    )
    assert finding is None


def test_treats_phase_zero_as_a_boss_without_phases_not_a_reading() -> None:
    assert repeat_phase(series(attempt(1, last_phase=0), attempt(2, last_phase=0))) is None


def test_is_silent_below_two_attempts_with_a_phase() -> None:
    assert repeat_phase(series(attempt(1, last_phase=2), attempt(2, last_phase=None))) is None


def test_names_an_unmatched_phase_id_by_number_rather_than_inventing_one() -> None:
    finding = repeat_phase(series(attempt(1, last_phase=9), attempt(2, last_phase=9)))
    assert finding is not None
    assert "phase 9" in finding.title


def test_says_nothing_about_failure() -> None:
    finding = repeat_phase(series(attempt(1, last_phase=3), attempt(2, last_phase=3)))
    assert finding is not None
    text = f"{finding.title} {finding.detail}".lower()
    for banned in ("fail", "failed", "missed", "mistake", "wrong"):
        assert banned not in text
