# ABOUTME: A kill's duration against the reference kills' own: median and range, or the slowest.
# ABOUTME: Pins the wording, the fallback below three kills, and silence on a wipe.

from wowperf.domain.comparison.kill_time import KILL_TIME_DETAIL, KILL_TIME_ID, analyse_kill_time
from wowperf.domain.comparison.mechanics import MechanicsMember, MechanicsSample, ReferenceKillRow
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence


def _encounter(*, kill: bool = True, seconds: float = 397.0) -> Encounter:
    return Encounter(
        report_code="ourreport0000000A", fight_id=4, encounter_id=3001,
        boss_name="The Test Colossus", difficulty=5, partition=1, size=20, kill=kill,
        start_ms=0, end_ms=int(seconds * 1000), players=(),
    )


def _sample(*seconds: int) -> MechanicsSample:
    return MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code=f"ref{index}", fight_id=1, size=20, duration_ms=one * 1000
                ),
                abilities=(),
            )
            for index, one in enumerate(seconds)
        )
    )


def test_a_kill_is_read_against_the_kills_median_and_range() -> None:
    # Leaderboard order, not sorted: 300 s is the median, 320 s the mean, and
    # neither end of the range, so each figure can only come from its own rule.
    [finding] = analyse_kill_time(_encounter(), _sample(310, 240, 500, 300, 250))
    assert finding.id == KILL_TIME_ID
    assert finding.confidence is Confidence.MEASURED
    assert finding.title == "The kill took 6:37 against the kills' median of 5:00"
    assert finding.evidence == ("Against 5 reference kills", "Their range: 4:00 to 8:20")
    assert finding.detail == KILL_TIME_DETAIL


def test_below_three_kills_the_slowest_stands_alone() -> None:
    [finding] = analyse_kill_time(_encounter(), _sample(250, 300))
    assert finding.title == "The kill took 6:37 against the slowest reference kill's 5:00"
    assert finding.evidence == (
        "Against the slowest of 2 reference kills: fewer than three were available",
    )


def test_one_kill_is_named_as_the_one_reference() -> None:
    [finding] = analyse_kill_time(_encounter(), _sample(250))
    assert finding.title == "The kill took 6:37 against the slowest reference kill's 4:10"
    assert finding.evidence == (
        "Against the one reference kill of this raid size: fewer than three were available",
    )


def test_a_wipe_has_no_kill_time() -> None:
    assert analyse_kill_time(_encounter(kill=False), _sample(310, 240, 500)) == []


def test_no_reference_kill_is_no_kill_time() -> None:
    assert analyse_kill_time(_encounter(), MechanicsSample()) == []
