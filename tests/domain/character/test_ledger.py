# ABOUTME: Behaviour tests for the group ledger: four comparisons every run carries, counted.
# ABOUTME: Counts sides of the fast runs' median and states no verdict; a withheld time stays out.

from tests.domain.character.builders import a_run, a_tempo
from wowperf.domain.character.ledger import GroupColumn, group_ledger
from wowperf.domain.comparison.tempo import DURATION_WITHHELD_REASON


def test_each_column_counts_the_runs_above_below_and_on_the_median() -> None:
    runs = [a_run(0, tempo=a_tempo()), a_run(1, tempo=a_tempo(time=1600.0, deaths=0)),
            a_run(2, tempo=a_tempo(downtime=100.0, kick=0.5))]

    ledger = group_ledger(runs)

    assert ledger.time == GroupColumn(above=2, below=1, level=0, compared=3)
    assert ledger.deaths == GroupColumn(above=2, below=1, level=0, compared=3)
    assert ledger.downtime == GroupColumn(above=0, below=2, level=1, compared=3)
    assert ledger.kick_share == GroupColumn(above=1, below=0, level=2, compared=3)


def test_a_withheld_time_and_a_missing_share_are_left_out_of_their_columns() -> None:
    runs = [a_run(0, tempo=a_tempo(their_time=None, kick=None)), a_run(1, tempo=a_tempo())]

    ledger = group_ledger(runs)

    assert ledger.time.compared == 1
    assert ledger.kick_share.compared == 1


def test_a_withheld_time_carries_the_reason_the_tempo_findings_give() -> None:
    ledger = group_ledger([a_run(0, tempo=a_tempo(their_time=None)), a_run(1, tempo=a_tempo())])
    assert ledger.time_withheld_reason == DURATION_WITHHELD_REASON


def test_no_reason_is_carried_when_every_time_was_compared() -> None:
    ledger = group_ledger([a_run(0, tempo=a_tempo()), a_run(1, tempo=a_tempo())])
    assert ledger.time_withheld_reason is None


def test_a_run_below_the_speed_floor_is_in_no_column() -> None:
    ledger = group_ledger([a_run(0), a_run(1, tempo=a_tempo())])
    assert ledger.deaths.compared == 1


def test_a_run_below_the_speed_floor_withholds_no_time() -> None:
    ledger = group_ledger([a_run(0), a_run(1, tempo=a_tempo())])
    assert ledger.time_withheld_reason is None


def test_the_characters_own_deaths_are_counted_by_run() -> None:
    ledger = group_ledger([a_run(0, subject_deaths=2), a_run(1), a_run(2, subject_deaths=1)])
    assert ledger.subject_died_in == 2
