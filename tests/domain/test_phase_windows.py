# ABOUTME: Locating which phase of a boss fight an instant fell in.
# ABOUTME: Handles non-ladder transition sequences and data disagreements.

from wowperf.domain.phase_windows import phase_at
from wowperf.domain.phases import Phase, PhaseTransition

STAGE_ONE = Phase(id=1, name="Stage One")
STAGE_TWO = Phase(id=2, name="Stage Two", is_intermission=True)
PHASES = (STAGE_ONE, STAGE_TWO)


def test_an_instant_takes_the_phase_of_the_transition_before_it() -> None:
    transitions = (PhaseTransition(id=1, start_ms=0), PhaseTransition(id=2, start_ms=5000))

    assert phase_at(PHASES, transitions, 4999) == STAGE_ONE
    assert phase_at(PHASES, transitions, 5000) == STAGE_TWO
    assert phase_at(PHASES, transitions, 9999) == STAGE_TWO


def test_a_fight_that_returned_to_an_earlier_phase_reads_as_that_phase() -> None:
    """The list is not a ladder: 1, 2, 1 was measured on a real attempt.

    The highest id reached is not where the fight was. An implementation
    taking `max` over the ids passed so far returns Stage Two here.
    """
    transitions = (
        PhaseTransition(id=1, start_ms=0),
        PhaseTransition(id=2, start_ms=5000),
        PhaseTransition(id=1, start_ms=9000),
    )

    assert phase_at(PHASES, transitions, 9500) == STAGE_ONE


def test_transitions_out_of_order_are_read_by_time_not_by_position() -> None:
    transitions = (PhaseTransition(id=2, start_ms=5000), PhaseTransition(id=1, start_ms=0))

    assert phase_at(PHASES, transitions, 1000) == STAGE_ONE


def test_an_encounter_with_no_phases_places_nothing() -> None:
    assert phase_at((), (PhaseTransition(id=1, start_ms=0),), 10) is None


def test_an_encounter_with_no_transitions_places_nothing() -> None:
    assert phase_at(PHASES, (), 10) is None


def test_a_transition_naming_an_unlisted_phase_places_nothing() -> None:
    """Encounter 3470 reported `lastPhase: 2` against transitions ending in 3.

    The two vocabularies can disagree, so an id with no `Phase` behind it is
    answered with None rather than with a guess.
    """
    transitions = (PhaseTransition(id=7, start_ms=0),)

    assert phase_at(PHASES, transitions, 10) is None


def test_an_instant_before_the_first_transition_places_nothing() -> None:
    """Measured 2026-09-18: 104 of 104 fights began at their first transition.

    So this case does not arise inside a fight, and the function answers None
    rather than assuming the first listed phase covers the gap.
    """
    transitions = (PhaseTransition(id=1, start_ms=5000),)

    assert phase_at(PHASES, transitions, 4999) is None
