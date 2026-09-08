# ABOUTME: The three statistics a sample of reference runs is allowed to state.
# ABOUTME: Median and range only — a mean would let one disaster run speak for the sample.

import statistics
from collections.abc import Sequence


def median(values: Sequence[float]) -> float:
    """The middle value, or the midpoint of the two middles.

    A median rather than a mean throughout: leaderboard tails are skewed, and
    one six-death disaster must not drag the figure the report compares against.
    """
    if not values:
        raise ValueError("a sample with no members has no median")
    return statistics.median(values)


def observed_range(values: Sequence[float]) -> tuple[float, float]:
    """The lowest and highest value seen.

    Every median the report prints states this beside it: a median of five with
    a 200-second spread and one with a 20-second spread must not read alike.
    """
    if not values:
        raise ValueError("a sample with no members has no range")
    return min(values), max(values)


def count_phrase(matching: int, total: int) -> str:
    """How many of the sample agreed, as the title must state it.

    Never a percentage: at these sample sizes a percentage invents precision
    the sample does not have.
    """
    return f"{matching} of {total}"
