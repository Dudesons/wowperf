# ABOUTME: The two pace findings and the notice, from one fight and its reference kills.
# ABOUTME: Pins the titles, evidence, badges and every withhold the design names.

import re

from tests.domain.comparison.test_pace_curve import a_behind_pattern, a_kill, steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import (
    BOSS_DETAIL,
    BOSS_IN_NO_REFERENCE,
    KILL_DETAIL,
    NO_BOSS,
    NO_REFERENCE_KILL,
    NOTHING_TO_COMPARE,
    PACE_ID,
    PACE_NOT_FETCHED,
    PROJECTION_ID,
    UNAVAILABLE_ID,
    PaceSample,
    analyse_pace,
    not_fetched,
    pace_reading,
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


def test_the_single_reference_wording_names_the_one_kill_and_its_cut() -> None:
    """One reference, ending before the wipe: hand arithmetic below.

    `a_kill(100, 200)` deals 100 a second for 200 s; against a 300 s wipe the
    band has fewer than `MIN_SAMPLE_FOR_AGGREGATE` (3) references throughout,
    so `reading.single` is True and the comparison stops at second 200, where
    the one kill ended -- band_cut is True, and `reading.references == 1`
    reaches the branch `test_the_fallback_names_the_slowest_kill_and_gives_no_range`
    (two references) cannot.
    """
    kill = a_kill(100, 200)
    found = by_id(
        analyse_pace(a_wipe(300), PaceSample(ours=steady(80, 300), references=(kill,)))
    )
    pace = found[PACE_ID]
    assert pace.evidence[0] == (
        "Against the one reference kill of this raid size: fewer than three were available"
    )
    assert "Compared through 3:20, when the reference kill ended" in pace.evidence


def test_the_single_reference_projection_times_its_own_total() -> None:
    """Hand arithmetic: target is the one kill's total at its own end, 200 s *
    100/s = 20000; our rate is 24000 (300 s * 80/s) / 300 s = 80/s; projected =
    20000 / 80 = 250 s = 4:10.
    """
    kill = a_kill(100, 200)
    found = by_id(
        analyse_pace(a_wipe(300), PaceSample(ours=steady(80, 300), references=(kill,)))
    )
    projection = found[PROJECTION_ID]
    assert projection.title == (
        "At its average pace this raid would have dealt the slowest kill's boss damage "
        "by about 4:10"
    )
    assert projection.evidence == ("The reference kill took 3:20",)


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


KILL_SAMPLE = PaceSample(
    ours=steady(10, 200),
    references=tuple(a_kill(amount, 300) for amount in (18, 20, 22)),
)
"""Our kill at 10 a second over 200 s against three kills at 18, 20 and 22 over 300 s.

The references outlast our kill, so the band is never cut and the comparison runs through
our own last second; 20 is the median and neither end, so the share names the median."""


def a_kill_fight(seconds: int) -> Encounter:
    return an_encounter(kill=True, start_ms=0, end_ms=seconds * 1000)


def test_a_kill_is_compared_through_its_last_second_with_the_kill_wording() -> None:
    [finding] = analyse_pace(a_kill_fight(200), KILL_SAMPLE)
    assert finding.id == PACE_ID
    assert finding.title == "Behind the kills' pace: 50% of their median boss damage by 3:20"
    assert finding.confidence is Confidence.DERIVED
    assert "Compared through the kill at 3:20" in finding.evidence
    assert finding.detail == KILL_DETAIL


def test_a_kill_that_outlasts_the_kills_says_where_the_band_was_cut() -> None:
    """Our kill runs 200 s; two of the four references end at 100 s.

    From 1:41 fewer than three kills are still fighting, so the comparison
    stops at 1:40, before our own last second: the line says where the kills
    ran out, and names neither the kill's end nor a wipe.
    """
    kills = (a_kill(100, 100), a_kill(100, 100), a_kill(100, 400), a_kill(100, 400))
    [finding] = analyse_pace(a_kill_fight(200), PaceSample(ours=steady(100, 200), references=kills))
    assert (
        "Compared through 1:40, after which fewer than three kills were still fighting"
        in finding.evidence
    )
    assert not any("wipe" in line for line in finding.evidence)
    assert not any(line.startswith("Compared through the kill") for line in finding.evidence)


def test_a_kill_that_outlasts_the_one_reference_says_when_that_kill_ended() -> None:
    """Our kill runs 300 s against one reference kill of 200 s: cut where it ended."""
    [finding] = analyse_pace(
        a_kill_fight(300), PaceSample(ours=steady(80, 300), references=(a_kill(100, 200),))
    )
    assert "Compared through 3:20, when the reference kill ended" in finding.evidence
    assert not any("wipe" in line for line in finding.evidence)
    assert not any(line.startswith("Compared through the kill") for line in finding.evidence)


def test_a_kill_draws_no_projection() -> None:
    ids = [one.id for one in analyse_pace(a_kill_fight(200), KILL_SAMPLE)]
    assert ids == [PACE_ID]
    assert PROJECTION_ID not in ids


def test_a_wipe_keeps_the_wipe_wording_and_its_projection() -> None:
    findings = analyse_pace(a_wipe(200), KILL_SAMPLE)
    assert [one.id for one in findings] == [PACE_ID, PROJECTION_ID]
    assert "Compared through the wipe at 3:20" in findings[0].evidence
    assert findings[0].detail == BOSS_DETAIL


def test_a_kill_with_nothing_to_compare_against_gets_the_notice() -> None:
    [notice] = analyse_pace(
        a_kill_fight(200), PaceSample(ours=steady(10, 200), unavailable=NO_REFERENCE_KILL)
    )
    assert notice.id == UNAVAILABLE_ID
    assert notice.detail == NO_REFERENCE_KILL


def test_pace_reading_reads_a_kill() -> None:
    assert pace_reading(a_kill_fight(200), KILL_SAMPLE) is not None


def test_each_withhold_is_one_notice_carrying_its_reason() -> None:
    for sample, reason in (
        (PaceSample(unavailable=NO_BOSS), NO_BOSS),
        (PaceSample(ours=steady(80, 200), unavailable=BOSS_IN_NO_REFERENCE), BOSS_IN_NO_REFERENCE),
        (PaceSample(ours=steady(80, 200)), NO_REFERENCE_KILL),
        # The shape `load_pace_sample` now returns with no references at all:
        # `ours` was never fetched, so it stays unset alongside the reason.
        (PaceSample(unavailable=NO_REFERENCE_KILL), NO_REFERENCE_KILL),
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


def test_no_comparable_seconds_yields_a_notice() -> None:
    """Reference kills that dealt zero damage (e.g. three a_kill(0, 400)) mean reading.seconds
    is empty or the last second has zero median; both cannot be compared.
    """
    kills = (a_kill(0, 400), a_kill(0, 400), a_kill(0, 400))
    [notice] = analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=kills))
    assert notice.id == UNAVAILABLE_ID
    assert notice.detail == NOTHING_TO_COMPARE


def test_a_reason_for_data_that_never_arrived_keeps_the_errors_first_line() -> None:
    """The error's own words say what failed; its later lines are a pointer to docs
    or a stack of context no reader of the page can act on."""
    reason = not_fetched("Server error '500 Internal Server Error'\nFor more information check")
    assert reason == f"{PACE_NOT_FETCHED}: Server error '500 Internal Server Error'."


def test_a_reason_for_data_that_never_arrived_ends_on_one_period() -> None:
    assert not_fetched("The report is private.") == f"{PACE_NOT_FETCHED}: The report is private."


def test_a_withheld_wipe_carries_the_not_fetched_reason_verbatim() -> None:
    encounter = an_encounter(kill=False, fight_percentage=40.0)
    reason = not_fetched("timed out")
    [notice] = analyse_pace(encounter, PaceSample(unavailable=reason))
    assert (notice.id, notice.detail) == (UNAVAILABLE_ID, reason)
