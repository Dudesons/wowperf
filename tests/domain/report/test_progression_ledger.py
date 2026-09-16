# ABOUTME: Which tab each progression finding family lands on, and that none can fall off.
# ABOUTME: A family with no placement reaches Observations, which is the page's catch-all.

import pytest

from wowperf.domain.report.progression_ledger import (
    PROGRESSION_PLACEMENTS,
    progression_field_for,
)


@pytest.mark.parametrize(
    ("finding_id", "field"),
    [
        ("progression.best", "best_rows"),
        ("progression.best.deaths", "best_rows"),
        ("progression.best.survived", "best_rows"),
        ("progression.cluster", "attempt_rows"),
        ("progression.movement", "attempt_rows"),
        ("progression.attempts.discarded", "attempt_rows"),
        ("progression.repeat.phase", "repeat_rows"),
        ("progression.repeat.first_death", "repeat_rows"),
        ("progression.repeat.ability", "repeat_rows"),
        ("progression.collapse", "repeat_rows"),
    ],
)
def test_every_shipped_progression_finding_has_a_tab(finding_id: str, field: str) -> None:
    assert progression_field_for(finding_id) == field


def test_a_family_nothing_places_falls_through_to_observations() -> None:
    """None, not a default tab. `build_observations` is what catches it, and a
    default here would hide a new family on a tab nobody chose for it."""
    assert progression_field_for("progression.something.new") is None
    assert progression_field_for("deaths.total") is None


def test_the_narrow_prefix_is_written_first() -> None:
    """`progression.best.` precedes `progression.best`, and the first match wins.

    Both name the same field today, so this asserts the order is stated rather
    than that the order changes an answer -- the day a Layer 3 finding wants a
    tab of its own, an unordered table sends it to the wrong one silently.
    """
    prefixes = [prefix for prefix, _ in PROGRESSION_PLACEMENTS]
    assert prefixes.index("progression.best.") < prefixes.index("progression.best")
