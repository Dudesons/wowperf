# ABOUTME: Behaviour tests for compare_targets -- shares per target, never totals.
# ABOUTME: The interesting cases are one target, a share gap, and the "read off itself" trap.

from wowperf.domain.comparison.targets import TargetRow, compare_targets


def test_a_single_target_fight_draws_no_comparison_and_says_why() -> None:
    ours = (TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=500_000_000),)
    findings = compare_targets(ours, [ours], "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.damage.targets.unavailable"
    assert "one target" in findings[0].detail


def test_a_share_is_reported_and_a_total_is_not() -> None:
    """Design 6.2: totals confound target focus with fight length and gear."""
    ours = (
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=880_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=120_000_000),
    )
    theirs = [(
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=470_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=30_000_000),
    )]
    findings = compare_targets(ours, theirs, "Emberkin")
    text = findings[0].title + findings[0].detail + " ".join(findings[0].evidence)
    assert "88" in text and "94" in text      # our 88.0% against their 94.0%
    assert "880000000" not in text and "470000000" not in text


def test_our_share_and_theirs_are_not_read_off_the_same_object() -> None:
    """Shape 4 of the five: an assertion reading its expected value off the
    thing it checks is true for every input. Ours and theirs differ here."""
    ours = (
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=500_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=500_000_000),
    )
    theirs = [(
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=900_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=100_000_000),
    )]
    findings = compare_targets(ours, theirs, "Emberkin")
    text = findings[0].title + " ".join(findings[0].evidence)
    assert "50" in text and "90" in text
