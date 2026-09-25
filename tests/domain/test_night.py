# ABOUTME: Behaviour tests for the Night container: a report's bosses, each as a Progression.
# ABOUTME: The empty report is the case a naive implementation gets wrong, so it is pinned.

from wowperf.domain.night import Night
from wowperf.domain.progression import Progression


def a_boss(encounter_id: int, name: str) -> Progression:
    return Progression(
        report_code="TESTCODE00000000",
        encounter_id=encounter_id,
        boss_name=name,
        difficulty=5,
        size=20,
        phases=(),
        separates_wipes=True,
        attempts=(),
        discarded=(),
    )


def test_a_night_carries_its_bosses_in_the_order_given() -> None:
    night = Night(
        report_code="TESTCODE00000000",
        bosses=(a_boss(3492, "Ula'tek"), a_boss(3420, "Nek'zali")),
    )
    assert tuple(boss.encounter_id for boss in night.bosses) == (3492, 3420)


def test_a_report_with_no_boss_fights_is_an_empty_night_not_an_error() -> None:
    # The command refuses an empty report itself, with a message naming the report.
    # The container stays a container: a type that cannot represent nothing is a
    # type that forces the refusal into the wrong layer.
    night = Night(report_code="TESTCODE00000000", bosses=())
    assert night.bosses == ()
