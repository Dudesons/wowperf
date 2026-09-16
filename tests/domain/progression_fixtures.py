# ABOUTME: Shared builders for progression tests: one attempt, one deepened attempt, one series.
# ABOUTME: Timestamps are offsets from the attempt's own start, because an_attempt offsets by id.

from wowperf.domain.encounter import Encounter
from wowperf.domain.phases import Phase
from wowperf.domain.progression import Progression

PHASES = (
    Phase(id=1, name="The Gathering"),
    Phase(id=2, name="Intermission: Tide", is_intermission=True),
    Phase(id=3, name="The Drowning"),
)


def a_series(
    *attempts: Encounter,
    separates_wipes: bool = True,
    phases: tuple[Phase, ...] = PHASES,
) -> Progression:
    """A `Progression` around already-built attempts, with nothing discarded."""
    return Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        phases=phases,
        separates_wipes=separates_wipes,
        attempts=attempts,
    )
