# ABOUTME: Behaviour tests for compare_targets -- shares per target, never totals.
# ABOUTME: The interesting cases are one target, a share gap, and the "read off itself" trap.

from wowperf.domain.comparison.targets import TargetRow, compare_targets


def a_reference(boss: int, adds: int) -> tuple[TargetRow, ...]:
    """One reference kill's own per-target rows, as a boss share of a round total."""
    return (
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=boss),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=adds),
    )


def test_the_sample_figure_is_the_median_of_distinct_shares_and_not_a_mean() -> None:
    """The headline number of this family is a sample median, and a median
    flanked by equal values is every other statistic as well.

    Four references at 40%, 50%, 62% and 92% put the median at 56% -- a value
    none of them holds, and not the mean of 61% either. So `max`, `min`, "the
    first reference" and "the average" each produce a different figure here,
    where a sample of identical references produces the same one for all five.
    The range is asserted at both ends for the same reason: a swap of the two
    is invisible while the lowest and the highest share are the same number.
    """
    ours = a_reference(880_000_000, 120_000_000)
    theirs = [
        a_reference(400_000_000, 600_000_000),
        a_reference(500_000_000, 500_000_000),
        a_reference(620_000_000, 380_000_000),
        a_reference(920_000_000, 80_000_000),
    ]

    findings = compare_targets(ours, theirs, "Emberkin")

    assert findings[0].title == (
        "Emberkin sent 88.0% of their damage into The Twin Fangs, against 56.0% for the "
        "sample"
    )
    assert list(findings[0].evidence) == [
        "ours 88.0% into The Twin Fangs",
        "sample 56.0%, range 40.0% to 92.0% over 4 references",
    ]
    assert [(fact.label, fact.value) for fact in findings[0].facts] == [
        ("This raid", "88.0% into The Twin Fangs"),
        ("Sample", "56.0%"),
    ]


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
