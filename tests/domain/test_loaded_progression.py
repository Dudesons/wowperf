# ABOUTME: Behaviour tests for LoadedProgression's derived views over deepened attempts.
# ABOUTME: The fixture builds `loaded` in reverse so pull-order and fight-id matching are exercised.

from tests.domain.progression_fixtures import a_series
from tests.domain.test_progression import an_attempt
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.progression import LoadedProgression


def loaded(*fight_ids: int, boss_percentages: dict[int, float] | None = None) -> LoadedProgression:
    """A series whose `loaded` tuple is deliberately in the reverse of pull order.

    `fight_percentage` is forced to `None` alongside `boss_percentage`: when no
    fight in the series carries a boss reading, `uses_boss_health` is `False`
    and `Progression.deepest` falls back to `fight_percentage`. Leaving that at
    `an_attempt`'s default (50.0, tied across every attempt) would still give
    `deepest` a value to return, so a test asserting no reading exists at all
    needs both fields empty, not just the one this fixture varies per fight.
    """
    attempts = tuple(
        an_attempt(
            f,
            50.0,
            200.0,
            fight_percentage=None,
            boss_percentage=(boss_percentages or {}).get(f),
        )
        for f in fight_ids
    )
    return LoadedProgression(
        progression=a_series(*attempts),
        loaded=tuple(LoadedEncounter(encounter=a) for a in reversed(attempts)),
    )


def test_attempts_with_events_are_in_pull_order_however_they_were_loaded() -> None:
    series = loaded(1, 2, 3)
    assert [one.encounter.fight_id for one in series.attempts_with_events] == [1, 2, 3]


def test_deepest_loaded_is_the_attempt_that_got_furthest_not_the_last() -> None:
    series = loaded(1, 2, 3, boss_percentages={1: 60.0, 2: 12.5, 3: 55.0})
    deepest = series.deepest_loaded
    assert deepest is not None
    assert deepest.encounter.fight_id == 2


def test_deepest_loaded_is_none_when_no_attempt_carries_a_reading() -> None:
    assert loaded(1, 2).deepest_loaded is None


def test_deepest_loaded_follows_progression_deepest_not_load_order() -> None:
    # `loaded` is built in reverse, so a lookup that returns loaded[0] would
    # answer fight 3 here while progression.deepest names fight 2.
    series = loaded(1, 2, 3, boss_percentages={1: 60.0, 2: 12.5, 3: 55.0})
    deepest = series.deepest_loaded
    assert deepest is not None
    assert series.loaded[0].encounter.fight_id == 3
    assert series.progression.deepest is not None
    assert deepest.encounter.fight_id == series.progression.deepest.fight_id == 2
