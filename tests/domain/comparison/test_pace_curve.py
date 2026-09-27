# ABOUTME: Cumulative boss damage per second and the kills' band around it.
# ABOUTME: Pins the interpolation, the band, its cut, the fallback and the behind stretches.

import pytest

from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReference,
    PaceState,
    behind_stretches,
    cumulative_at,
    earlier_behind,
    final_behind_start,
    read_pace,
)


def steady(per_second: int, seconds: int, *, interval_ms: float = 1000.0) -> BossDamage:
    """A constant rate, cut into buckets of `interval_ms`."""
    buckets = int(seconds * 1000 / interval_ms)
    return BossDamage(
        interval_ms=interval_ms,
        amounts=tuple(int(per_second * interval_ms / 1000) for _ in range(buckets)),
    )


def a_kill(per_second: int, seconds: int, *, interval_ms: float = 2000.0) -> PaceReference:
    return PaceReference(
        duration_seconds=float(seconds), damage=steady(per_second, seconds, interval_ms=interval_ms)
    )


def test_cumulative_takes_the_covered_fraction_of_the_straddling_bucket() -> None:
    series = BossDamage(interval_ms=2000.0, amounts=(100, 300, 500))
    assert cumulative_at(series, 0) == 0.0
    assert cumulative_at(series, 1) == pytest.approx(50.0)
    assert cumulative_at(series, 3) == pytest.approx(250.0)
    assert cumulative_at(series, 6) == pytest.approx(900.0)
    assert cumulative_at(series, 60) == pytest.approx(900.0)


def test_a_grid_starting_late_reads_nothing_before_its_start() -> None:
    series = BossDamage(lead_ms=1000, interval_ms=1000.0, amounts=(100, 100))
    assert cumulative_at(series, 1) == 0.0
    assert cumulative_at(series, 2) == pytest.approx(100.0)


def test_the_band_is_the_lowest_median_and_highest_of_the_kills() -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    at_ten = reading.seconds[9]
    assert at_ten.second == 10
    assert (at_ten.low, at_ten.median, at_ten.high) == pytest.approx((900.0, 1000.0, 1300.0))
    assert at_ten.ours == pytest.approx(1000.0)
    assert at_ten.state is PaceState.ON_PACE


@pytest.mark.parametrize(
    ("ours_per_second", "state"),
    [(80, PaceState.BEHIND), (100, PaceState.ON_PACE), (140, PaceState.AHEAD)],
)
def test_the_three_states(ours_per_second: int, state: PaceState) -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(ours_per_second, 30), kills, 30.0)
    assert reading is not None
    assert reading.seconds[-1].state is state


def test_the_band_stops_where_fewer_than_three_kills_are_still_fighting() -> None:
    """Two kills end at 20 s: from second 21 only two remain."""
    kills = (a_kill(100, 20), a_kill(100, 20), a_kill(100, 60), a_kill(100, 60))
    reading = read_pace(steady(100, 40), kills, 40.0)
    assert reading is not None
    assert reading.seconds[-1].second == 20
    assert reading.band_cut is True
    assert reading.single is False
    assert reading.references == 4


def test_a_wipe_shorter_than_every_kill_is_compared_to_its_end() -> None:
    kills = (a_kill(100, 60), a_kill(100, 60), a_kill(100, 60))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    assert reading.seconds[-1].second == 30
    assert reading.band_cut is False


def test_below_three_references_the_slowest_kill_stands_alone() -> None:
    """The slowest kill deals least per second, so it is the lenient comparison."""
    fast, slow = a_kill(200, 30), a_kill(100, 60)
    reading = read_pace(steady(150, 40), (fast, slow), 40.0)
    assert reading is not None
    assert reading.single is True
    assert reading.references == 2
    last = reading.seconds[-1]
    assert last.low == last.median == last.high == pytest.approx(4000.0)
    assert last.state is PaceState.AHEAD
    assert reading.target == pytest.approx(6000.0)


def test_the_single_kill_ending_first_cuts_the_comparison() -> None:
    reading = read_pace(steady(100, 40), (a_kill(100, 25),), 40.0)
    assert reading is not None
    assert reading.seconds[-1].second == 25
    assert reading.band_cut is True


def test_no_reference_reads_nothing() -> None:
    assert read_pace(steady(100, 30), (), 30.0) is None


def test_the_target_is_the_median_of_the_kills_totals_at_their_own_ends() -> None:
    kills = (a_kill(100, 50), a_kill(100, 60), a_kill(100, 70))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    assert reading.target == pytest.approx(6000.0)
    assert reading.reference_durations == (50.0, 60.0, 70.0)


def test_the_widest_bucket_is_the_coarsest_reference_grid() -> None:
    kills = (
        a_kill(100, 60, interval_ms=1000.0),
        a_kill(100, 60, interval_ms=3000.0),
        a_kill(100, 60, interval_ms=2000.0),
    )
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    assert reading.widest_bucket_seconds == pytest.approx(3.0)


def a_behind_pattern(pattern: str) -> tuple[BossDamage, tuple[PaceReference, ...]]:
    """Ours per second from a string, against three kills dealing 100 a second.

    'b' deals 0 (the gap to the band widens by 100), '.' deals 100 (the gap
    holds), '+' deals 300 (the gap closes by 200). The band is one line at
    100 per second, so a second is behind exactly when the running gap is
    negative -- and each stretch's bounds can be worked out on paper.
    """
    per_mark = {"b": 0, ".": 100, "+": 300}
    ours = BossDamage(interval_ms=1000.0, amounts=tuple(per_mark[mark] for mark in pattern))
    kills = tuple(a_kill(100, 100, interval_ms=1000.0) for _ in range(3))
    return ours, kills


def test_behind_stretches_are_read_as_inclusive_seconds() -> None:
    """Gap by second: -100 -200 0 +200, held to s10, then +100 0 -100 -200."""
    ours, kills = a_behind_pattern("bb++......bbbb")
    reading = read_pace(ours, kills, 14.0)
    assert reading is not None
    assert behind_stretches(reading) == ((1, 2), (13, 14))


def test_t_is_the_start_of_the_final_stretch_not_the_first() -> None:
    ours, kills = a_behind_pattern("bb++......bbbb")
    reading = read_pace(ours, kills, 14.0)
    assert reading is not None
    assert final_behind_start(reading) == 13


def test_no_t_when_the_raid_was_not_behind_at_the_end() -> None:
    """Ends 200 ahead: the early stretch is never mentioned."""
    ours, kills = a_behind_pattern("bb++......")
    reading = read_pace(ours, kills, 10.0)
    assert reading is not None
    assert final_behind_start(reading) is None
    assert earlier_behind(reading) == ()


def test_an_earlier_stretch_counts_only_when_longer_than_the_widest_bucket() -> None:
    """Gap by second: -100 +100 0 -100 -200 0 0 -100 -200.

    Stretches (1, 1), (4, 5) and the final (8, 9). With 1 s reference buckets
    the one-second stretch sits exactly on the bar and is left out; the
    two-second one outlasts it and is kept.
    """
    ours, kills = a_behind_pattern("b+bbb+.bb")
    reading = read_pace(ours, kills, 9.0)
    assert reading is not None
    assert behind_stretches(reading) == ((1, 1), (4, 5), (8, 9))
    assert final_behind_start(reading) == 8
    assert earlier_behind(reading) == ((4, 5),)
