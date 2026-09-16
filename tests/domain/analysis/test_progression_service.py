# ABOUTME: Behaviour tests for what a night of attempts may and may not claim.
# ABOUTME: The central case is a night that moved nowhere -- silence is the right answer.

from tests.domain.test_progression import a_measured_night, an_attempt
from wowperf.domain.analysis.progression_service import (
    MIN_ATTEMPTS_FOR_MOVEMENT,
    analyse_progression,
)
from wowperf.domain.findings import Finding
from wowperf.domain.progression import build_progression


def ids(findings: list[Finding]) -> list[str]:
    return [f.id for f in findings]


def one(findings: list[Finding], finding_id: str) -> Finding:
    match = [f for f in findings if f.id == finding_id]
    assert len(match) == 1, f"expected exactly one {finding_id}, got {len(match)}"
    return match[0]


def test_the_best_finding_names_the_deepest_attempt_not_the_last() -> None:
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    best = one(analyse_progression(progression), "progression.best")

    assert "16.5" in best.title or "16.49" in best.title
    assert best.confidence == "measured"


def test_the_best_finding_says_which_percentage_it_means() -> None:
    """`a_measured_night` never sets `boss_percentage`, so the only correct
    label is "encounter progress". Asserting either word would pass even if
    the wrong scale were picked -- both labels contain one of the two words,
    so only pinning the exact label can catch a mislabelled series.
    """
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    best = one(analyse_progression(progression), "progression.best")

    assert "(encounter progress)" in best.title


def test_the_cluster_reports_a_median_and_a_range_never_a_mean() -> None:
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    cluster = one(analyse_progression(progression), "progression.cluster")

    assert "mean" not in (cluster.title + cluster.detail).lower()
    # Median of 64.81, 85.80, 16.49, 85.40, 87.65, 53.30, 55.65 is 64.81.
    assert "64.8" in cluster.title


def test_the_measured_night_reports_the_movement_its_halves_actually_show() -> None:
    """Computed from the fixture, not assumed about it.

    Qualifying depths in pull order are 64.81, 85.80, 16.49, 85.40, 87.65,
    53.30, 55.65. Seven values, so the halves are the first three and the last
    three: medians 64.81 and 55.65, a gap of 9.16 points. Remaining counts down,
    so the later half sat deeper.

    The deepest attempt is still the third of eight, and the tool still draws no
    slope. Stating a gap between two halves is not the forbidden claim.
    """
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    movement = one(analyse_progression(progression), "progression.movement")

    assert movement.confidence == "derived"
    assert "deeper" in movement.title.lower()
    assert "9.2" in movement.title
    assert "encounter" in movement.title.lower()


def test_a_night_whose_halves_barely_differ_says_no_movement() -> None:
    """Silence is a first-class result, so it must be reachable.

    Depths 70.0, 68.0, 72.0, 69.0, 71.0, 70.5: half medians 70.0 and 70.5, a gap
    of half a point. Nothing this tool will call a direction.
    """
    flat = [
        an_attempt(1, 70.0, 200.0),
        an_attempt(2, 68.0, 210.0),
        an_attempt(3, 72.0, 190.0),
        an_attempt(4, 69.0, 205.0),
        an_attempt(5, 71.0, 195.0),
        an_attempt(6, 70.5, 200.0),
    ]
    progression = build_progression(flat, encounter_id=3492, difficulty=5)

    movement = one(analyse_progression(progression), "progression.movement")

    assert movement.confidence == "derived"
    assert "no movement" in movement.title.lower()


def test_a_night_that_really_did_deepen_is_allowed_to_say_so() -> None:
    """Guards the mutation that would make the movement finding a constant."""
    deepening = [
        an_attempt(1, 90.0, 120.0), an_attempt(2, 88.0, 130.0), an_attempt(3, 86.0, 140.0),
        an_attempt(4, 40.0, 300.0), an_attempt(5, 35.0, 320.0), an_attempt(6, 30.0, 340.0),
    ]
    progression = build_progression(deepening, encounter_id=3492, difficulty=5)

    movement = one(analyse_progression(progression), "progression.movement")

    assert "no movement" not in movement.title.lower()
    assert "deep" in movement.title.lower()
    assert "encounter" in movement.title.lower()


def test_a_night_that_sat_shallower_later_prints_a_positive_gap() -> None:
    """Guards the sign of the shallower branch specifically.

    Earlier attempts sit deep (median 35.0), later ones sit shallow (median
    88.0): gap = early - late = -53.0. The branch negates that to print the
    positive figure a reader should see, 53.0. Printing the raw, still-negative
    gap instead would read "by -53.0 points" -- wrong, but every other test in
    this file would still pass, since none of them reaches this branch. The
    substring assertion below is chosen so that regression breaks it: "by
    53.0 points" is not a substring of "by -53.0 points of median".
    """
    shallowing = [
        an_attempt(1, 30.0, 300.0), an_attempt(2, 35.0, 320.0), an_attempt(3, 40.0, 340.0),
        an_attempt(4, 86.0, 140.0), an_attempt(5, 88.0, 130.0), an_attempt(6, 90.0, 120.0),
    ]
    progression = build_progression(shallowing, encounter_id=3492, difficulty=5)

    movement = one(analyse_progression(progression), "progression.movement")

    assert movement.confidence == "derived"
    assert "shallower" in movement.title.lower()
    assert "by 53.0 points" in movement.title
    assert "-53.0" not in movement.title
    assert "encounter" in movement.title.lower()


def test_movement_is_withheld_when_too_few_attempts_qualify() -> None:
    few = [an_attempt(i, 80.0 - i, 200.0) for i in range(1, MIN_ATTEMPTS_FOR_MOVEMENT)]
    progression = build_progression(few, encounter_id=3492, difficulty=5)

    findings = analyse_progression(progression)
    movement = one(findings, "progression.movement")

    assert "not compared" in movement.title.lower() or "too few" in movement.title.lower()
    assert movement.seconds_lost is None


def test_discarded_attempts_are_reported_with_their_count() -> None:
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    discarded = one(analyse_progression(progression), "progression.attempts.discarded")

    assert "1" in discarded.title


def test_nothing_is_reported_about_discards_when_there_were_none() -> None:
    clean = [an_attempt(i, 80.0 - i, 200.0) for i in range(1, 8)]
    progression = build_progression(clean, encounter_id=3492, difficulty=5)

    assert "progression.attempts.discarded" not in ids(analyse_progression(progression))


def test_every_finding_carries_a_confidence_badge() -> None:
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    for finding in analyse_progression(progression):
        assert finding.confidence in ("measured", "derived", "inferred")


def test_no_finding_claims_a_rate_or_a_slope() -> None:
    """Design section 2.3. The tool never extrapolates."""
    progression = build_progression(a_measured_night(), encounter_id=3492, difficulty=5)

    for finding in analyse_progression(progression):
        text = (finding.title + finding.detail).lower()
        for banned in ("per pull", "trend", "on track", "at this rate", "projected"):
            assert banned not in text, f"{finding.id} says '{banned}'"


def test_an_empty_night_produces_no_findings_rather_than_raising() -> None:
    progression = build_progression([], encounter_id=3492, difficulty=5)

    assert analyse_progression(progression) == []


def test_a_night_of_only_discards_still_reports_the_discard() -> None:
    """A night where nothing qualifies must still say so.

    Two attempts under `MIN_ATTEMPT_SECONDS` (20s and 30s) leave `attempts`
    empty and `discarded` holding both. The old `if not depths: return
    findings` returned before the discarded block was ever reached, so a
    night that excluded everything reported nothing at all -- the one case
    where the exclusion finding is the whole story. A reimplementation of
    that early return would make this list empty again instead of holding
    exactly one finding.
    """
    only_resets = [an_attempt(1, 90.0, 20.0), an_attempt(2, 80.0, 30.0)]
    progression = build_progression(only_resets, encounter_id=3492, difficulty=5)

    findings = analyse_progression(progression)

    assert ids(findings) == ["progression.attempts.discarded"]
    assert "2" in findings[0].title


def test_a_night_where_every_attempt_carries_boss_health_uses_it_throughout() -> None:
    """All three qualifying attempts carry a boss reading, so the series reads
    entirely on boss health -- label and median must agree on that scale.
    """
    boss_health_night = [
        an_attempt(1, 51.12, 200.0, boss_percentage=3.76),
        an_attempt(2, 60.0, 210.0, boss_percentage=40.0),
        an_attempt(3, 70.0, 220.0, boss_percentage=20.0),
    ]
    progression = build_progression(boss_health_night, encounter_id=3492, difficulty=5)

    cluster = one(analyse_progression(progression), "progression.cluster")

    assert "(boss health)" in cluster.title
    # median of 3.76, 40.0, 20.0 is 20.0 -- the boss-health figures.
    assert "20.0" in cluster.title


def test_a_night_where_only_some_attempts_carry_boss_health_reads_as_encounter_progress() -> None:
    """Reproduces the bug directly: pooling (fight 51.12, boss 3.76) with
    (fight 60.0, boss absent) used to print a median of 31.9% -- the median
    of 3.76 and 60.0, two different scales -- labelled "boss health", true
    of only one of the two figures. One attempt without a boss reading must
    pull the WHOLE series back to fightPercentage instead.
    """
    mixed_night = [
        an_attempt(1, 51.12, 200.0, boss_percentage=3.76),
        an_attempt(2, 60.0, 210.0),
    ]
    progression = build_progression(mixed_night, encounter_id=3492, difficulty=5)

    cluster = one(analyse_progression(progression), "progression.cluster")

    assert "(encounter progress)" in cluster.title
    # median of 51.12, 60.0 (both read as fightPercentage) is 55.56.
    assert "55.6" in cluster.title
    assert "31.9" not in cluster.title
