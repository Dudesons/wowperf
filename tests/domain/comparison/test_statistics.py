# ABOUTME: Behaviour tests for the three statistics a sample of reference runs may state.
# ABOUTME: Median and range only, and each refuses an empty sample in its own words.

import pytest

from wowperf.domain.comparison.statistics import count_phrase, median, observed_range


def test_the_median_of_an_odd_count_is_the_middle_value() -> None:
    assert median([30.0, 10.0, 20.0]) == 20.0


def test_the_median_of_an_even_count_is_the_midpoint_of_the_two_middles() -> None:
    assert median([10.0, 20.0, 30.0, 40.0]) == 25.0


def test_an_empty_sample_has_no_median() -> None:
    # Matched on the guard's own words, not on the type: statistics.median([])
    # raises StatisticsError, a ValueError subclass, so a bare pytest.raises
    # would pass with the guard deleted and prove nothing about it.
    with pytest.raises(ValueError, match="a sample with no members has no median"):
        median([])


def test_an_empty_sample_has_no_range() -> None:
    # min([]) raises ValueError too, so this matches the guard's own words for
    # the same reason the median test above does.
    with pytest.raises(ValueError, match="a sample with no members has no range"):
        observed_range([])


def test_the_observed_range_is_the_lowest_and_the_highest() -> None:
    assert observed_range([30.0, 10.0, 20.0]) == (10.0, 30.0)


def test_the_range_of_one_value_is_that_value_twice() -> None:
    assert observed_range([7.0]) == (7.0, 7.0)


def test_the_count_phrase_carries_both_numbers() -> None:
    assert count_phrase(4, 5) == "4 of 5"
