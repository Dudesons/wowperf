# ABOUTME: Locating which phase of a boss fight an instant fell in.
# ABOUTME: Handles non-ladder transition sequences and data disagreements.

from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.phase_windows import dominant_phase_by_ability, phase_at
from wowperf.domain.phases import Phase, PhaseTransition

STAGE_ONE = Phase(id=1, name="Stage One")
STAGE_TWO = Phase(id=2, name="Stage Two", is_intermission=True)
PHASES = (STAGE_ONE, STAGE_TWO)
TRANSITIONS = (PhaseTransition(id=1, start_ms=0), PhaseTransition(id=2, start_ms=5000))


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


def _hit(ability_id: int, timestamp_ms: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=1,
        ability_id=ability_id,
        ability_name="Caustic Waves",
        amount=100,
        timestamp_ms=timestamp_ms,
    )


def test_an_ability_reports_the_phase_most_of_its_landings_fell_in() -> None:
    events = (_hit(11, 100), _hit(11, 6000), _hit(11, 7000), _hit(11, 8000))

    share = dominant_phase_by_ability(events, PHASES, TRANSITIONS)[11]

    assert share.phase == STAGE_TWO
    assert share.landings == 3
    assert share.total == 4


def test_the_share_counts_rather_than_assuming_the_last_phase() -> None:
    """Three landings in Stage One and one in Stage Two must read Stage One.

    An implementation returning the phase of the newest event passes the test
    above and fails this one.
    """
    events = (_hit(11, 100), _hit(11, 200), _hit(11, 300), _hit(11, 6000))

    share = dominant_phase_by_ability(events, PHASES, TRANSITIONS)[11]

    assert share.phase == STAGE_ONE
    assert share.landings == 3
    assert share.total == 4


def test_each_ability_is_counted_separately() -> None:
    events = (_hit(11, 100), _hit(22, 6000))

    shares = dominant_phase_by_ability(events, PHASES, TRANSITIONS)

    assert shares[11].phase == STAGE_ONE
    assert shares[22].phase == STAGE_TWO


def test_an_encounter_with_no_phases_yields_no_shares() -> None:
    assert dominant_phase_by_ability((_hit(11, 100),), (), TRANSITIONS) == {}


def test_an_ability_whose_landings_all_fall_outside_any_phase_is_absent() -> None:
    late = (PhaseTransition(id=1, start_ms=9000),)

    assert dominant_phase_by_ability((_hit(11, 100),), PHASES, late) == {}


def test_when_landings_tie_between_phases_the_lower_phase_id_wins() -> None:
    """Two landings in Stage One, two in Stage Two: must return Stage One.

    The tie-break sorts by `(pair[1], -pair[0])`, so equal counts favor the
    lower phase id. An implementation using `+pair[0]` or deleting the
    tie-break term entirely fails this test.
    """
    events = (_hit(11, 100), _hit(11, 200), _hit(11, 6000), _hit(11, 7000))

    share = dominant_phase_by_ability(events, PHASES, TRANSITIONS)[11]

    assert share.phase == STAGE_ONE
    assert share.landings == 2
    assert share.total == 4
