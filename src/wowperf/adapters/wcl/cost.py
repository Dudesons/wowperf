# ABOUTME: What each Warcraft Logs query cost, derived from the quota reading every query carries.
# ABOUTME: A reading reports the spend before its own query is billed, so costs shift by one.

from wowperf.domain.base import Frozen


class QueryCost(Frozen):
    operation: str
    points: float


class OperationCost(Frozen):
    operation: str
    calls: int
    points: float


class CostLedger:
    """Readings in the order they were taken, and the per-query costs they imply.

    A query's `rateLimitData` reports the points spent *before* that query is
    billed. Measured 2026-09-08: an aliased Fights query reported 8.01, exactly
    the spend the queries before it had left behind, and the gap to the next
    reading was Fights' own 2.01. So a query costs the next reading minus its
    own, and the most recent query stays unpriced until another one runs.

    Sequential requests are what make that hold. Nothing here enforces it, and
    concurrent fetches would interleave the readings and misattribute every cost
    after the first.
    """

    def __init__(self) -> None:
        self._readings: list[tuple[str, float]] = []

    def record(self, operation: str, points_spent_this_hour: float) -> None:
        self._readings.append((operation, points_spent_this_hour))

    def pending(self) -> str | None:
        """The operation whose cost the next reading would reveal, if one comes."""
        return self._readings[-1][0] if self._readings else None

    def costs(self) -> list[QueryCost]:
        priced: list[QueryCost] = []
        pairs = zip(self._readings, self._readings[1:], strict=False)
        for (operation, spent), (_, following) in pairs:
            if following < spent:
                # Points reset on a fixed one-hour cycle. This pair straddles a
                # reset, so its difference is not a cost of anything.
                continue
            priced.append(QueryCost(operation=operation, points=round(following - spent, 2)))
        return priced

    def by_operation(self) -> list[OperationCost]:
        """One row per operation, dearest first, so a reader starts at what to cut."""
        calls: dict[str, int] = {}
        points: dict[str, float] = {}
        for cost in self.costs():
            calls[cost.operation] = calls.get(cost.operation, 0) + 1
            points[cost.operation] = points.get(cost.operation, 0.0) + cost.points

        return sorted(
            (
                OperationCost(operation=name, calls=count, points=round(points[name], 2))
                for name, count in calls.items()
            ),
            key=lambda entry: (-entry.points, entry.operation),
        )
