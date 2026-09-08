# ABOUTME: Tests the per-query cost ledger, whose whole difficulty is the off-by-one attribution.
# ABOUTME: A query's quota reading is taken before its own cost is charged, measured 2026-09-08.

from wowperf.adapters.wcl.cost import CostLedger, OperationCost, QueryCost


def test_one_reading_prices_nothing() -> None:
    """A query's cost is the next reading minus its own, so the last one waits."""
    ledger = CostLedger()
    ledger.record("Fights", 3.00)

    assert ledger.costs() == []


def test_a_cost_is_charged_to_the_earlier_query_not_the_later_one() -> None:
    """The whole point. A reading reports spend BEFORE its own query is billed.

    Fights cost 2.01 and Affixes 1.00 when measured live on 2026-09-08. Shifting
    the attribution by one would report those two figures the other way round.
    """
    ledger = CostLedger()
    ledger.record("Fights", 3.00)
    ledger.record("Affixes", 5.01)
    ledger.record("RateLimit", 6.01)

    assert ledger.costs() == [
        QueryCost(operation="Fights", points=2.01),
        QueryCost(operation="Affixes", points=1.00),
    ]


def test_repeated_operations_are_summed_and_counted() -> None:
    ledger = CostLedger()
    ledger.record("Casts", 0.00)
    ledger.record("Casts", 2.00)
    ledger.record("Fights", 4.50)
    ledger.record("RateLimit", 5.50)

    assert ledger.by_operation() == [
        OperationCost(operation="Casts", calls=2, points=4.50),
        OperationCost(operation="Fights", calls=1, points=1.00),
    ]


def test_the_costliest_operation_is_reported_first() -> None:
    ledger = CostLedger()
    ledger.record("Cheap", 0.00)
    ledger.record("Dear", 1.00)
    ledger.record("RateLimit", 9.00)

    assert [entry.operation for entry in ledger.by_operation()] == ["Dear", "Cheap"]


def test_an_hour_rollover_drops_the_pair_rather_than_recording_a_negative_cost() -> None:
    """Points reset on a fixed one-hour cycle, so a reading can fall below the last."""
    ledger = CostLedger()
    ledger.record("Fights", 3590.00)
    ledger.record("Affixes", 1.00)
    ledger.record("RateLimit", 2.00)

    assert ledger.costs() == [QueryCost(operation="Affixes", points=1.00)]


def test_the_trailing_operation_is_named_as_the_one_still_unpriced() -> None:
    """So a report can say what its total leaves out instead of assuming."""
    ledger = CostLedger()
    assert ledger.pending() is None

    ledger.record("Fights", 3.00)
    assert ledger.pending() == "Fights"

    ledger.record("RateLimit", 5.01)
    assert ledger.pending() == "RateLimit"
