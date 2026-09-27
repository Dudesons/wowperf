# ABOUTME: The two pace findings and the notice, from one wipe and its reference kills.
# ABOUTME: Pins the titles, evidence, badges and every withhold the design names.

import re

from tests.domain.comparison.test_pace_curve import a_behind_pattern, a_kill, steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import (
    BOSS_IN_NO_REFERENCE,
    NO_REFERENCE_KILL,
    NO_SINGLE_BOSS,
    PACE_ID,
    PROJECTION_ID,
    UNAVAILABLE_ID,
    PaceSample,
    analyse_pace,
)
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence, Finding

THREE_KILLS = (a_kill(100, 400), a_kill(110, 420), a_kill(120, 440))


def a_wipe(seconds: int) -> Encounter:
    return an_encounter(kill=False, start_ms=0, end_ms=seconds * 1000, fight_percentage=40.0)


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_raid_behind_the_band_is_told_so_with_its_share_and_t() -> None:
    found = by_id(
        analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=THREE_KILLS))
    )
    pace = found[PACE_ID]
    assert pace.title == "Behind the kills' pace: 73% of their median boss damage by 3:20"
    assert pace.confidence is Confidence.DERIVED
    assert pace.evidence[0] == "Against 3 reference kills of this raid size"
    assert pace.evidence[1] == "Their range at 3:20: 91% to 109% of their median"
    assert "Compared through the wipe at 3:20" in pace.evidence
    assert "Behind from 0:01 to 3:20" in pace.evidence


def test_on_pace_and_ahead_carry_no_behind_line() -> None:
    on = by_id(
        analyse_pace(a_wipe(200), PaceSample(ours=steady(110, 200), references=THREE_KILLS))
    )
    ahead = by_id(
        analyse_pace(a_wipe(200), PaceSample(ours=steady(150, 200), references=THREE_KILLS))
    )
    assert on[PACE_ID].title.startswith("On the kills' pace: 100% ")
    assert ahead[PACE_ID].title.startswith("Ahead of the kills' pace: 136% ")
    for finding in (on[PACE_ID], ahead[PACE_ID]):
        assert not any(line.startswith("Behind from") for line in finding.evidence)


def test_the_band_cut_is_stated() -> None:
    kills = (a_kill(100, 100), a_kill(100, 100), a_kill(100, 400), a_kill(100, 400))
    found = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(100, 200), references=kills)))
    assert (
        "Compared through 1:40, after which fewer than three kills were still fighting"
        in found[PACE_ID].evidence
    )


def test_the_fallback_names_the_slowest_kill_and_gives_no_range() -> None:
    kills = (a_kill(200, 300), a_kill(100, 400))
    found = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=kills)))
    pace = found[PACE_ID]
    assert pace.title == "Behind the slowest kill's pace: 80% of its boss damage by 3:20"
    assert pace.evidence[0] == (
        "Against the slowest of 2 reference kills of this raid size: "
        "fewer than three were available"
    )
    assert not any(line.startswith("Their range") for line in pace.evidence)


def test_the_projection_times_the_kills_total_at_our_average_pace() -> None:
    """Target 46200 (median of 40000, 46200, 52800); 80 a second reaches it at 577.5 s."""
    found = by_id(
        analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=THREE_KILLS))
    )
    projection = found[PROJECTION_ID]
    assert projection.confidence is Confidence.INFERRED
    assert projection.title == (
        "At its average pace this raid would have dealt the kills' boss damage by about 9:38"
    )
    assert projection.evidence == ("The kills took 6:40 to 7:20, median 7:00",)
    assert "enrage" in projection.detail


def test_a_short_wipe_gets_no_projection_and_says_so() -> None:
    found = by_id(analyse_pace(a_wipe(40), PaceSample(ours=steady(80, 40), references=THREE_KILLS)))
    assert PROJECTION_ID not in found
    assert "No projection: the attempt lasted under 44 seconds" in found[PACE_ID].evidence


def test_zero_boss_damage_gets_no_projection() -> None:
    found = by_id(
        analyse_pace(a_wipe(100), PaceSample(ours=steady(0, 100), references=THREE_KILLS))
    )
    assert PROJECTION_ID not in found
    assert found[PACE_ID].title.startswith("Behind the kills' pace: 0% ")
    assert "No projection: the raid dealt the boss no damage" in found[PACE_ID].evidence


def test_a_kill_is_never_compared() -> None:
    kill = an_encounter(kill=True, start_ms=0, end_ms=200_000)
    assert analyse_pace(kill, PaceSample(ours=steady(80, 200), references=THREE_KILLS)) == []


def test_each_withhold_is_one_notice_carrying_its_reason() -> None:
    for sample, reason in (
        (PaceSample(unavailable=NO_SINGLE_BOSS), NO_SINGLE_BOSS),
        (PaceSample(ours=steady(80, 200), unavailable=BOSS_IN_NO_REFERENCE), BOSS_IN_NO_REFERENCE),
        (PaceSample(ours=steady(80, 200)), NO_REFERENCE_KILL),
    ):
        [notice] = analyse_pace(a_wipe(200), sample)
        assert notice.id == UNAVAILABLE_ID
        assert notice.detail == reason


def test_no_finding_prints_a_raw_damage_figure() -> None:
    """Shares and times only: no run of four or more digits anywhere."""
    found = analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=THREE_KILLS))
    for finding in found:
        for text in (finding.title, finding.detail, *finding.evidence):
            assert not re.search(r"\d{4,}", text), text


def test_an_earlier_behind_stretch_longer_than_the_widest_bucket_is_mentioned() -> None:
    """Pattern 'b+bbb+.bb' with 1s buckets: early stretch at (4,5) is 2 seconds, longer than bar.

    Hand arithmetic: stretches at (1,1), (4,5), (8,9). Final is (8,9). Early (4,5) outlasts
    the 1s widest bucket, so it is mentioned with 'Also behind between 0:04 and 0:05'.
    """
    ours, kills = a_behind_pattern("b+bbb+.bb")
    found = by_id(analyse_pace(a_wipe(9), PaceSample(ours=ours, references=kills)))
    pace = found[PACE_ID]
    assert "Also behind between 0:04 and 0:05" in pace.evidence
