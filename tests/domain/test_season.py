# ABOUTME: Behaviour tests for the season constants the timer arithmetic depends on.
# ABOUTME: The threshold is a boundary, so both sides of it are pinned here.

from wowperf.domain.season import SeasonData


def a_season() -> SeasonData:
    return SeasonData(
        death_penalty_seconds=5.0,
        death_penalty_seconds_high_key=15.0,
        high_key_threshold=12,
    )


def test_a_low_key_uses_the_base_death_penalty() -> None:
    assert a_season().death_penalty(11) == 5.0


def test_the_threshold_itself_uses_the_high_penalty() -> None:
    assert a_season().death_penalty(12) == 15.0


def test_above_the_threshold_uses_the_high_penalty() -> None:
    assert a_season().death_penalty(20) == 15.0
