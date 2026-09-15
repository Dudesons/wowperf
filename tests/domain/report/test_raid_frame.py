# ABOUTME: Behaviour tests for the raid report's header: boss, difficulty, outcome, partition.
# ABOUTME: A sibling of the Mythic+ header tests -- a boss fight has no dungeon or keystone.

from wowperf.domain.encounter import Encounter
from wowperf.domain.report.raid_frame import build_raid_header


def an_encounter(**overrides: object) -> Encounter:
    fields: dict[str, object] = dict(
        report_code="abc123",
        fight_id=2,
        encounter_id=3470,
        boss_name="Emberkin",
        difficulty=5,
        partition=1,
        size=20,
        kill=True,
        fight_percentage=0.0,
        start_ms=0,
        end_ms=300_000,
        players=(),
    )
    fields.update(overrides)
    return Encounter(**fields)  # type: ignore[arg-type]


def test_a_kill_reads_as_a_kill_and_names_its_difficulty() -> None:
    encounter = an_encounter(kill=True, difficulty=5, fight_percentage=0.0, partition=1)

    header = build_raid_header(encounter)

    assert header.boss == "Emberkin"
    assert header.difficulty == "Mythic"
    assert header.outcome == "Killed"
    assert header.partition == "Partition 1"


def test_a_wipe_states_how_far_the_raid_got() -> None:
    """A wipe's headline is the best percentage, because there is no kill to state.

    `fight_percentage` is the boss's remaining health at the end of the
    attempt, so the figure a reader wants is what is left, stated as such
    rather than subtracted into a progress number the log never recorded.
    """
    encounter = an_encounter(kill=False, difficulty=5, fight_percentage=12.4, partition=1)

    header = build_raid_header(encounter)

    assert header.outcome == "Wiped at 12.4% remaining"


def test_a_difficulty_nobody_recorded_prints_the_number_rather_than_a_guess() -> None:
    """An unmapped difficulty says what it knows, and does not invent a name.

    The table is hand-maintained and dated. A number it does not carry means
    the table is stale, and a report that guessed `Heroic` for it would be
    confidently wrong -- which is the one thing the badges exist to prevent.
    """
    encounter = an_encounter(kill=True, difficulty=99, fight_percentage=0.0, partition=1)

    header = build_raid_header(encounter)

    assert header.difficulty == "Difficulty 99"
