# ABOUTME: Behaviour tests for the four fields an Encounter gained for progression.
# ABOUTME: Each is absent-by-default, because a report is often silent about them.

from wowperf.domain.encounter import Encounter
from wowperf.domain.phases import PhaseTransition


def an_encounter(**overrides: object) -> Encounter:
    fields: dict[str, object] = dict(
        report_code="abc123",
        fight_id=30,
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        partition=1,
        size=20,
        kill=False,
        fight_percentage=16.49,
        start_ms=0,
        end_ms=480_000,
        players=(),
    )
    fields.update(overrides)
    return Encounter(**fields)  # type: ignore[arg-type]


def test_an_encounter_built_the_old_way_reports_every_new_field_as_absent() -> None:
    """Slice 2 constructs Encounters without these; none of them may break."""
    encounter = an_encounter()

    assert encounter.boss_percentage is None
    assert encounter.last_phase is None
    assert encounter.last_phase_is_intermission is False
    assert encounter.phase_transitions == ()


def test_an_encounter_carries_both_percentages_separately() -> None:
    """They diverge: one measured attempt read 51.12 against 3.76."""
    encounter = an_encounter(fight_percentage=51.12, boss_percentage=3.76)

    assert encounter.fight_percentage == 51.12
    assert encounter.boss_percentage == 3.76


def test_an_encounter_carries_the_phase_it_ended_in_and_how_it_got_there() -> None:
    encounter = an_encounter(
        last_phase=3,
        last_phase_is_intermission=True,
        phase_transitions=(
            PhaseTransition(id=1, start_ms=9518),
            PhaseTransition(id=2, start_ms=9682),
            PhaseTransition(id=3, start_ms=9827),
        ),
    )

    assert encounter.last_phase == 3
    assert encounter.last_phase_is_intermission is True
    assert [t.id for t in encounter.phase_transitions] == [1, 2, 3]
    assert encounter.phase_transitions[2].start_ms == 9827
