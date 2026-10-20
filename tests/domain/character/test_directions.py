# ABOUTME: Behaviour tests for measures that sat on one side of the top parses in every run.
# ABOUTME: Unanimity over six runs and a gap floor; a run counts only where it judged the row.

from tests.domain.character.builders import (
    a_buff,
    a_debuff,
    a_rate,
    a_run,
    a_stat,
    measures_of,
)
from wowperf.domain.character.patterns import DIRECTIONS_WITHHELD_ID, consistent_directions
from wowperf.domain.comparison.measures import Stretch, Verdict
from wowperf.domain.findings import Confidence

STRIKE = 433895
PLAGUE = 55078
VISCERAL = 461130


def test_a_rate_below_the_median_in_six_runs_is_a_direction() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),))) for i in range(6)]

    [finding] = consistent_directions(runs)

    assert finding.id == f"character.direction.boss.{STRIKE}"
    assert finding.title == (
        "You cast Vampiric Strike less often than top parses on bosses, in every one of 6 runs")
    assert finding.quantifier == "every"
    assert finding.confidence is Confidence.DERIVED
    assert finding.ability_id == STRIKE
    assert finding.evidence[0] == "Altar of Fangs +18: 7.0 against 9.0 a minute"
    assert finding.evidence[-1] == "median gap 22%"


def test_five_judged_runs_are_not_enough() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),)) if i < 5
                  else measures_of()) for i in range(6)]
    assert consistent_directions(runs) == []


def test_one_dissent_breaks_it() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0 if i else 9.5, 9.0),)))
            for i in range(7)]
    assert consistent_directions(runs) == []


def test_one_tie_breaks_it() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0 if i else 9.0, 9.0),)))
            for i in range(7)]
    assert consistent_directions(runs) == []


def test_a_rate_gap_of_ten_percent_counts_and_nine_point_nine_does_not() -> None:
    at = [a_run(i, measures=measures_of(trash=(a_rate(STRIKE, 9.0, 10.0,
                                                      stretch=Stretch.TRASH),))) for i in range(6)]
    under = [a_run(i, measures=measures_of(trash=(a_rate(STRIKE, 9.01, 10.0,
                                                         stretch=Stretch.TRASH),)))
             for i in range(6)]
    assert [f.id for f in consistent_directions(at)] == [f"character.direction.trash.{STRIKE}"]
    assert consistent_directions(under) == []


def test_a_share_gap_of_five_points_counts_and_four_point_nine_does_not() -> None:
    at = [a_run(i, measures=measures_of(auras=(a_buff(VISCERAL, 0.50, 0.55),))) for i in range(6)]
    under = [a_run(i, measures=measures_of(auras=(a_buff(VISCERAL, 0.501, 0.55),)))
             for i in range(6)]
    [finding] = consistent_directions(at)
    assert finding.title == (
        "Visceral Strength was up less of the key for you than for top parses, "
        "in every one of 6 runs")
    assert finding.evidence[-1] == "median gap 5 points"
    assert consistent_directions(under) == []


def test_a_gap_on_the_floor_counts_however_its_subtraction_rounds() -> None:
    """0.60 - 0.55 is 0.04999... in floats and (3.0 - 2.7) / 3.0 is 0.09999...:
    both are on the floor, so both state a direction."""
    share = [a_run(i, measures=measures_of(auras=(a_buff(VISCERAL, 0.60, 0.55),)))
             for i in range(6)]
    rate = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 2.7, 3.0),))) for i in range(6)]
    assert [f.id for f in consistent_directions(share)] == [f"character.direction.buff.{VISCERAL}"]
    assert [f.id for f in consistent_directions(rate)] == [f"character.direction.boss.{STRIKE}"]


def test_debuff_coverage_is_a_direction_of_its_own() -> None:
    runs = [a_run(i, measures=measures_of(debuffs=(a_debuff(PLAGUE, 0.60, 0.80),)))
            for i in range(6)]
    [finding] = consistent_directions(runs)
    assert finding.id == f"character.direction.debuff.{PLAGUE}"
    assert finding.title == (
        "Your Blood Plague covered less of the enemies' lives than top parses', "
        "in every one of 6 runs")


def test_a_stat_share_direction_names_the_stat() -> None:
    runs = [a_run(i, measures=measures_of(stats=(a_stat("haste", 0.38, 0.30),)))
            for i in range(6)]
    [finding] = consistent_directions(runs)
    assert finding.id == "character.direction.stat.haste"
    assert finding.title == (
        "Your haste share of secondary rating sat above top parses', in every one of 6 runs")
    assert finding.ability_id is None


def test_rows_a_run_declined_to_judge_never_count() -> None:
    unjudged = [a_run(i, measures=measures_of(
        auras=(a_buff(VISCERAL, 0.0, 0.55, verdict=Verdict.UNJUDGED),),
        debuffs=(a_debuff(PLAGUE, 0.1, 0.8, verdict=Verdict.BOSSES_ONLY),
                 a_debuff(1, 0.1, 0.8, shared_with=(701,), name="Mortal Wounds")),
    )) for i in range(6)]
    assert consistent_directions(unjudged) == []


def test_a_run_with_no_parse_sample_contributes_nothing() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),)) if i < 5 else None)
            for i in range(7)]
    assert consistent_directions(runs) == []


def test_directions_are_ordered_by_runs_then_by_median_gap() -> None:
    runs = [a_run(i, measures=measures_of(
        trash=(a_rate(STRIKE, 9.0, 10.0, stretch=Stretch.TRASH),),
        debuffs=(a_debuff(PLAGUE, 0.60, 0.80),) if i < 6 else (),
        auras=(a_buff(VISCERAL, 0.48, 0.60),) if i < 6 else (),
    )) for i in range(7)]

    assert [f.id for f in consistent_directions(runs)] == [
        f"character.direction.trash.{STRIKE}",
        f"character.direction.debuff.{PLAGUE}",
        f"character.direction.buff.{VISCERAL}",
    ]


def test_fewer_than_six_loaded_runs_withholds_the_source_and_says_so() -> None:
    runs = [a_run(i, measures=measures_of(boss=(a_rate(STRIKE, 7.0, 9.0),))) for i in range(5)]

    [finding] = consistent_directions(runs)

    assert finding.id == DIRECTIONS_WITHHELD_ID
    assert finding.confidence is Confidence.MEASURED
    assert finding.title == "Consistent directions are not stated: 5 runs loaded, 6 are needed"


def test_one_loaded_run_is_counted_in_the_singular() -> None:
    [finding] = consistent_directions([a_run(0)])
    assert finding.title == "Consistent directions are not stated: 1 run loaded, 6 are needed"
