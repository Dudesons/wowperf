# ABOUTME: Behaviour tests for the phase a night's attempts most often ended in.
# ABOUTME: Every guard -- separatesWipes, an empty phase table, phase zero -- gets its own case.

from tests.domain.progression_fixtures import a_loaded_attempt, a_loaded_series
from tests.domain.progression_fixtures import a_series as series
from tests.domain.test_progression import an_attempt
from wowperf.domain.analysis.progression_repeats import collapse, collapse_seconds, repeat_phase
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


def test_collapse_seconds_is_first_death_to_the_end_of_the_attempt() -> None:
    one = a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(70_000, 90_000))
    assert collapse_seconds(one) == 30.0


def test_collapse_seconds_is_none_without_a_death() -> None:
    assert collapse_seconds(a_loaded_attempt(1, seconds=100.0, deaths_after_ms=())) is None


def test_collapse_reports_a_median_and_a_range_never_a_mean() -> None:
    finding = collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),   # 10.0s
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=(80_000,)),   # 20.0s
        a_loaded_attempt(3, seconds=100.0, deaths_after_ms=(10_000,)),   # 90.0s
    ))
    assert finding is not None
    assert "20" in finding.title              # the median, not the 40.0 mean
    assert "40" not in finding.title
    assert "10" in " ".join(finding.evidence)
    assert "90" in " ".join(finding.evidence)


def test_collapse_is_withheld_below_two_attempts_with_a_death() -> None:
    assert collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=()),
    )) is None


def test_collapse_counts_only_attempts_that_had_one() -> None:
    finding = collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=(80_000,)),
        a_loaded_attempt(3, seconds=100.0, deaths_after_ms=()),
    ))
    assert finding is not None
    assert "2 attempts" in finding.detail
