# ABOUTME: Behaviour tests for the raid report's header: boss, difficulty, outcome, partition.
# ABOUTME: A sibling of the Mythic+ header tests -- a boss fight has no dungeon or keystone.

from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.model import Player
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

    header = build_raid_header(LoadedEncounter(encounter=encounter))

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

    header = build_raid_header(LoadedEncounter(encounter=encounter))

    assert header.outcome == "Wiped at 12.4% remaining"


def test_a_wipe_the_report_does_not_quantify_states_only_that_it_wiped() -> None:
    """`fight_percentage` is None where the report does not say (`encounter.py`).

    Formatting a missing figure is not an option this header has: no
    percentage, no "unknown", and never a zero standing in for the number the
    log never gave. `Encounter.outcome` draws the same line in the findings'
    own words -- its None branch reads "wiped", not "wiped at 0%".
    """
    encounter = an_encounter(kill=False, difficulty=5, fight_percentage=None, partition=1)

    header = build_raid_header(LoadedEncounter(encounter=encounter))

    assert header.outcome == "Wiped"


def test_a_difficulty_nobody_recorded_prints_the_number_rather_than_a_guess() -> None:
    """An unmapped difficulty says what it knows, and does not invent a name.

    The table is hand-maintained and dated. A number it does not carry means
    the table is stale, and a report that guessed `Heroic` for it would be
    confidently wrong -- which is the one thing the badges exist to prevent.
    """
    encounter = an_encounter(kill=True, difficulty=99, fight_percentage=0.0, partition=1)

    header = build_raid_header(LoadedEncounter(encounter=encounter))

    assert header.difficulty == "Difficulty 99"


FOUR = (
    Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=700),
    Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Arms", item_level=700),
    Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=700),
    Player(actor_id=4, name="Кириллица", class_name="Rogue", spec="Outlaw", item_level=700),
)


def a_pull_with_deaths(count: int, *, kill: bool) -> LoadedEncounter:
    """`count` roster deaths, one per raider in turn, ten seconds apart."""
    return LoadedEncounter(
        encounter=an_encounter(kill=kill, fight_percentage=0.0 if kill else 12.4, players=FOUR),
        deaths=tuple(
            Death(player_name=FOUR[index % 4].name, actor_id=FOUR[index % 4].actor_id,
                  timestamp_ms=(index + 1) * 10_000, killing_blow="Ravenous Feast")
            for index in range(count)
        ),
    )


def test_a_kill_with_four_deaths_reads_as_dirty_and_counts_them() -> None:
    assert build_raid_header(a_pull_with_deaths(4, kill=True)).outcome == "Killed — dirty, 4 deaths"
    assert build_raid_header(a_pull_with_deaths(5, kill=True)).outcome == "Killed — dirty, 5 deaths"


def test_a_kill_with_three_deaths_reads_as_a_kill() -> None:
    assert build_raid_header(a_pull_with_deaths(3, kill=True)).outcome == "Killed"


def test_a_wipe_past_the_call_still_states_how_far_the_raid_got() -> None:
    header = build_raid_header(a_pull_with_deaths(6, kill=False))
    assert header.outcome == "Wiped at 12.4% remaining"
