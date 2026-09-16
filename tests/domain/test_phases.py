# ABOUTME: Behaviour tests for the phase vocabulary read from Warcraft Logs.
# ABOUTME: These types encode no boss knowledge -- they carry what the API names.

import pytest
from pydantic import ValidationError

from wowperf.domain.phases import Phase, PhaseTransition


def test_a_phase_carries_the_name_the_api_gave_it() -> None:
    phase = Phase(id=3, name="Intermission: The Shattering", is_intermission=True)

    assert phase.id == 3
    assert phase.name == "Intermission: The Shattering"
    assert phase.is_intermission is True


def test_a_phase_is_an_ordinary_stage_unless_told_otherwise() -> None:
    assert Phase(id=1, name="Stage One").is_intermission is False


def test_a_transition_says_when_the_attempt_entered_the_phase() -> None:
    transition = PhaseTransition(id=2, start_ms=9004)

    assert transition.id == 2
    assert transition.start_ms == 9004


def test_both_types_are_frozen() -> None:
    phase = Phase(id=1, name="Stage One")
    transition = PhaseTransition(id=1, start_ms=0)

    with pytest.raises(ValidationError):
        phase.name = "something else"
    with pytest.raises(ValidationError):
        transition.start_ms = 5
