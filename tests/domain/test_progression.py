# ABOUTME: Behaviour tests for selecting a night's attempts and ordering them.
# ABOUTME: The fixture's shape is the measured shape: the deepest attempt is not the last.

from collections.abc import Sequence

from wowperf.domain.encounter import Encounter
from wowperf.domain.phases import Phase
from wowperf.domain.progression import (
    MIN_ATTEMPT_SECONDS,
    build_progression,
    remaining_percent,
)


def an_attempt(fight_id: int, remaining: float, seconds: float, **overrides: object) -> Encounter:
    fields: dict[str, object] = dict(
        report_code="abc123",
        fight_id=fight_id,
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        partition=1,
        size=20,
        kill=False,
        fight_percentage=remaining,
        start_ms=fight_id * 1_000_000,
        end_ms=fight_id * 1_000_000 + int(seconds * 1000),
        players=(),
    )
    fields.update(overrides)
    return Encounter(**fields)  # type: ignore[arg-type]


def a_measured_night() -> Sequence[Encounter]:
    """The eight attempts measured 2026-09-16. The deepest is third, not last."""
    return [
        an_attempt(28, 64.81, 215.7),
        an_attempt(29, 85.80, 105.9),
        an_attempt(30, 16.49, 480.0),
        an_attempt(31, 85.40, 110.0),
        an_attempt(32, 87.65, 88.0),
        an_attempt(33, 53.30, 278.8),
        an_attempt(34, 55.65, 227.0),
        an_attempt(35, 100.0, 15.8),
    ]


def test_the_series_keeps_only_the_boss_and_difficulty_asked_for() -> None:
    mixed = [
        an_attempt(1, 50.0, 200.0),
        an_attempt(2, 50.0, 200.0, encounter_id=3445),
        an_attempt(3, 50.0, 200.0, difficulty=4),
    ]

    progression = build_progression(mixed, encounter_id=3492, difficulty=5)

    assert [a.fight_id for a in progression.attempts] == [1]


def test_attempts_are_ordered_by_when_they_were_pulled() -> None:
    shuffled = [an_attempt(34, 55.65, 227.0), an_attempt(28, 64.81, 215.7)]

    progression = build_progression(shuffled, encounter_id=3492, difficulty=5)

    assert [a.fight_id for a in progression.attempts] == [28, 34]


def test_a_reset_is_discarded_and_counted_rather_than_dropped_in_silence() -> None:
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    assert [a.fight_id for a in progression.discarded] == [35]
    assert 35 not in [a.fight_id for a in progression.attempts]
    assert all(a.duration_seconds >= MIN_ATTEMPT_SECONDS for a in progression.attempts)


def test_the_deepest_attempt_is_the_one_with_least_left_not_the_last_one() -> None:
    """The finding this whole design exists to get right."""
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    assert progression.deepest is not None
    assert progression.deepest.fight_id == 30
    assert progression.deepest.fight_id != progression.attempts[-1].fight_id


def test_a_kill_stays_in_the_series() -> None:
    with_kill = [
        an_attempt(25, 100.0, 60.0),
        an_attempt(26, 51.12, 271.3),
        an_attempt(27, 0.01, 453.6, kill=True),
    ]

    progression = build_progression(with_kill, encounter_id=3492, difficulty=5)

    assert progression.killed is True
    assert 27 in [a.fight_id for a in progression.attempts]


def test_a_night_with_no_kill_says_so() -> None:
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    assert progression.killed is False


def test_the_phase_table_and_its_guard_travel_with_the_series() -> None:
    progression = build_progression(
        a_measured_night(),
        encounter_id=3492,
        difficulty=5,
        phases=(Phase(id=1, name="Stage One"),),
        separates_wipes=True,
    )

    assert [p.name for p in progression.phases] == ["Stage One"]
    assert progression.separates_wipes is True


def test_remaining_reads_the_boss_figure_when_the_series_uses_boss_health() -> None:
    """bossPercentage is the boss's own health; fightPercentage is the encounter's.

    Which one a given attempt is read on is not this attempt's own choice --
    `uses_boss_health` is decided for the whole series and passed in.
    """
    attempt = an_attempt(1, 51.12, 200.0, boss_percentage=3.76)
    assert remaining_percent(attempt, uses_boss_health=True) == 3.76


def test_remaining_reads_the_fight_figure_when_the_series_does_not_use_boss_health() -> None:
    attempt = an_attempt(1, 51.12, 200.0, boss_percentage=3.76)
    assert remaining_percent(attempt, uses_boss_health=False) == 51.12


def test_an_attempt_the_report_says_nothing_about_has_no_depth() -> None:
    empty = an_attempt(1, 50.0, 200.0, fight_percentage=None)
    assert remaining_percent(empty, uses_boss_health=False) is None
    assert remaining_percent(empty, uses_boss_health=True) is None


def test_a_series_uses_boss_health_only_when_every_attempt_carries_one() -> None:
    """Finding: two incompatible percentages must never pool under one label.

    All three qualify: one series where every attempt carries both readings
    uses boss health throughout; one where even a single attempt lacks a
    boss reading falls the whole series back to encounter progress, not a
    per-attempt mix of the two; and an empty series is neither.
    """
    every_attempt_has_both = [
        an_attempt(1, 51.12, 200.0, boss_percentage=40.0),
        an_attempt(2, 60.0, 210.0, boss_percentage=25.0),
    ]
    only_some_have_boss_health = [
        an_attempt(1, 51.12, 200.0, boss_percentage=3.76),
        an_attempt(2, 60.0, 210.0),
    ]

    all_boss = build_progression(every_attempt_has_both, encounter_id=3492, difficulty=5)
    mixed = build_progression(only_some_have_boss_health, encounter_id=3492, difficulty=5)
    empty = build_progression([], encounter_id=3492, difficulty=5)

    assert all_boss.uses_boss_health is True
    assert mixed.uses_boss_health is False
    assert empty.uses_boss_health is False
