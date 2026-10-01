# ABOUTME: One boss's wipes on the night page, each read by slice 1's own pace comparison.
# ABOUTME: Pins the count, every pull line's wording, the withheld pull, and the size line.

import re

from tests.domain.comparison.test_pace_curve import a_kill, steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import NO_BOSS, PaceSample
from wowperf.domain.comparison.pace_curve import PaceReference
from wowperf.domain.comparison.pace_night import NIGHT_PACE_ID, analyse_night_pace
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding

THREE_KILLS = (a_kill(100, 400), a_kill(110, 420), a_kill(120, 440))
"""Three kills fighting through 400 s: at every second the band is 100, 110 and 120 a second."""


def a_pull(
    fight_id: int, *, seconds: int = 200, kill: bool = False, size: int = 20
) -> LoadedEncounter:
    return LoadedEncounter(
        encounter=an_encounter(
            fight_id=fight_id, kill=kill, size=size, start_ms=0, end_ms=seconds * 1000,
            fight_percentage=0.0 if kill else 40.0,
        )
    )


def a_sample(
    per_second: int, seconds: int = 200, kills: tuple[PaceReference, ...] = THREE_KILLS
) -> PaceSample:
    return PaceSample(ours=steady(per_second, seconds), references=kills)


def the_line(
    pulls: list[LoadedEncounter], samples: dict[int, PaceSample]
) -> Finding | None:
    found = analyse_night_pace(pulls, samples)
    assert len(found) <= 1
    return found[0] if found else None


def test_each_wipe_gets_one_line_in_pull_order_and_the_title_counts_the_behind() -> None:
    pulls = [a_pull(12), a_pull(14), a_pull(15)]
    samples = {12: a_sample(80), 14: a_sample(110), 15: a_sample(130)}
    line = the_line(pulls, samples)
    assert line is not None
    assert line.id == NIGHT_PACE_ID
    assert line.confidence is Confidence.DERIVED
    assert line.title == "1 of 3 wipes ended behind the kills' pace"
    assert line.evidence == (
        "Fight 12: behind from 0:01 to the wipe at 3:20",
        "Fight 14: on pace through the wipe at 3:20",
        "Fight 15: ahead through the wipe at 3:20",
    )
    assert "no trend" in line.detail


def test_no_wipe_behind_reads_none_of() -> None:
    line = the_line([a_pull(12), a_pull(14)], {12: a_sample(110), 14: a_sample(130)})
    assert line is not None
    assert line.title == "None of 2 wipes ended behind the kills' pace"


def test_a_band_cut_says_where_the_kills_ran_out() -> None:
    line = the_line(
        [a_pull(12, seconds=430), a_pull(14)], {12: a_sample(80, 430), 14: a_sample(80)}
    )
    assert line is not None
    assert line.evidence[0] == (
        "Fight 12: behind from 0:01 to 6:40, where fewer than three kills were still fighting"
    )


def test_the_slowest_kill_fallback_is_named_on_its_line() -> None:
    single = (a_kill(100, 400),)
    line = the_line(
        [a_pull(12), a_pull(14)], {12: a_sample(80, kills=single), 14: a_sample(80)}
    )
    assert line is not None
    assert line.evidence[0] == (
        "Fight 12, against the slowest kill alone: behind from 0:01 to the wipe at 3:20"
    )


def test_a_withheld_wipe_is_listed_with_its_reason_and_not_counted() -> None:
    pulls = [a_pull(12), a_pull(13), a_pull(14)]
    samples = {12: a_sample(80), 13: PaceSample(unavailable=NO_BOSS), 14: a_sample(80)}
    line = the_line(pulls, samples)
    assert line is not None
    assert line.title == "2 of 2 wipes ended behind the kills' pace"
    assert line.evidence[1] == f"Fight 13: not compared. {NO_BOSS}"


def test_one_compared_wipe_draws_no_line() -> None:
    pulls = [a_pull(12), a_pull(13)]
    samples = {12: a_sample(80), 13: PaceSample(unavailable=NO_BOSS)}
    assert the_line(pulls, samples) is None


def test_a_kill_and_a_pull_with_no_sample_are_not_listed() -> None:
    """A kill is compared too, so it carries a sample, and a behind one here.

    The line counts wipes: the kill is neither listed nor counted among the
    wipes that ended behind, whatever its own pace reads.
    """
    pulls = [a_pull(12), a_pull(13, kill=True), a_pull(14), a_pull(15)]
    samples = {12: a_sample(80), 13: a_sample(80), 14: a_sample(110)}
    line = the_line(pulls, samples)
    assert line is not None
    assert [one.split(":")[0] for one in line.evidence] == ["Fight 12", "Fight 14"]
    assert line.title == "1 of 2 wipes ended behind the kills' pace"


def test_no_compare_draws_no_line() -> None:
    assert the_line([a_pull(12), a_pull(14)], {}) is None


def test_two_raid_sizes_are_named_on_one_line() -> None:
    pulls = [a_pull(12, size=20), a_pull(14, size=20), a_pull(15, size=18)]
    samples = {12: a_sample(80), 14: a_sample(80), 15: a_sample(80)}
    line = the_line(pulls, samples)
    assert line is not None
    assert line.evidence[-1] == (
        "Fights 12, 14 at 20 players; Fight 15 at 18 players: each against kills of its own size"
    )


def test_one_raid_size_draws_no_size_line() -> None:
    line = the_line([a_pull(12), a_pull(14)], {12: a_sample(80), 14: a_sample(80)})
    assert line is not None
    assert not any("players" in one for one in line.evidence)


def test_no_line_prints_a_raw_damage_figure() -> None:
    pulls = [a_pull(12), a_pull(14, seconds=430), a_pull(15)]
    samples = {12: a_sample(80), 14: a_sample(110, 430), 15: a_sample(130)}
    line = the_line(pulls, samples)
    assert line is not None
    for text in (line.title, line.detail, *line.evidence):
        assert not re.search(r"\d{4,}", text), text
