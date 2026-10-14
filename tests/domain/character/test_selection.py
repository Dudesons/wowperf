# ABOUTME: Behaviour tests for choosing one recent high key per dungeon for one specialisation.
# ABOUTME: Covers the level window, recency, missing logs, left-out dungeons and the spec rule.

import pytest

from wowperf.domain.character.model import ChosenRun, Dungeon, LeftOut, RankedRun, Zone
from wowperf.domain.character.selection import (
    choose_spec,
    require_mythic_plus,
    select_runs,
)

DEN = Dungeon(encounter_id=101, name="Den of Nalorakk")
ROW = Dungeon(encounter_id=102, name="Murder Row")
ZONE = Zone(zone_id=55, name="Mythic+ Season 2", difficulty_ids=(10,), dungeons=(DEN, ROW))


def a_run(encounter_id: int, level: int, start: int, *, code: str | None = "aBc123XyZ",
          fight: int | None = 1, spec: str = "Blood") -> RankedRun:
    return RankedRun(encounter_id=encounter_id, keystone_level=level, spec=spec,
                     start_time_ms=start, report_code=code,
                     fight_id=fight if code is not None else None)


def test_the_most_recent_run_at_the_top_level_or_one_below_is_chosen() -> None:
    runs = [
        a_run(101, 18, 100, fight=1),
        a_run(101, 17, 300, fight=2),
        a_run(101, 16, 500, fight=3),
    ]

    selection = select_runs(ZONE, runs)

    assert selection.chosen == (
        ChosenRun(dungeon="Den of Nalorakk", encounter_id=101, keystone_level=17,
                  start_time_ms=300, report_code="aBc123XyZ", fight_id=2),
    )


def test_two_below_the_top_is_never_chosen() -> None:
    runs = [a_run(101, 18, 100, code=None), a_run(101, 16, 500)]

    selection = select_runs(ZONE, runs)

    assert selection.chosen == ()
    assert LeftOut(dungeon="Den of Nalorakk",
                   reason="no run at +18 or +17 has a public report") in selection.left_out


def test_a_run_with_no_public_log_is_passed_over_for_one_with_a_log() -> None:
    runs = [a_run(101, 18, 900, code=None), a_run(101, 18, 100, fight=4)]
    assert select_runs(ZONE, runs).chosen[0].fight_id == 4


def test_a_dungeon_never_run_as_the_spec_is_left_out_with_the_reason() -> None:
    selection = select_runs(ZONE, [a_run(101, 18, 100)])
    assert selection.left_out == (LeftOut(dungeon="Murder Row", reason="no ranked run as Blood"),)


def test_the_spec_with_the_most_ranked_runs_is_read() -> None:
    runs = [a_run(101, 18, 1, spec="Blood"), a_run(102, 18, 2, spec="Blood"),
            a_run(101, 18, 3, spec="Frost")]
    assert choose_spec(runs, None) == "Blood"


def test_a_tie_between_specs_goes_to_the_one_played_most_recently() -> None:
    runs = [a_run(101, 18, 1, spec="Blood"), a_run(101, 18, 9, spec="Frost")]
    assert choose_spec(runs, None) == "Frost"


def test_a_requested_spec_is_matched_ignoring_case() -> None:
    assert choose_spec([a_run(101, 18, 1, spec="Blood")], "blood") == "Blood"


def test_a_spec_the_character_never_ran_is_refused_naming_the_ones_it_did() -> None:
    with pytest.raises(ValueError, match="ranked as: Blood"):
        choose_spec([a_run(101, 18, 1, spec="Blood")], "Frost")


def test_no_ranked_run_at_all_is_refused() -> None:
    with pytest.raises(ValueError, match="no ranked Mythic"):
        select_runs(ZONE, [])


def test_a_raid_zone_is_refused() -> None:
    with pytest.raises(ValueError, match=r"not a Mythic\+ zone"):
        require_mythic_plus(Zone(zone_id=42, name="Some Raid", difficulty_ids=(3, 4, 5)))
    require_mythic_plus(ZONE)


def test_another_spec_neither_raises_the_floor_nor_is_chosen() -> None:
    runs = [
        a_run(101, 18, 100, code="bloodCode", fight=5, spec="Blood"),
        a_run(101, 20, 900, code="frostCode", fight=6, spec="Frost"),
    ]

    selection = select_runs(ZONE, runs, "Blood")

    assert selection.spec == "Blood"
    assert selection.chosen == (
        ChosenRun(dungeon="Den of Nalorakk", encounter_id=101, keystone_level=18,
                  start_time_ms=100, report_code="bloodCode", fight_id=5),
    )


def test_a_run_with_a_report_but_no_fight_is_never_chosen() -> None:
    run = RankedRun(encounter_id=101, keystone_level=18, spec="Blood",
                    start_time_ms=100, report_code="x", fight_id=None)

    selection = select_runs(ZONE, [run])

    assert selection.chosen == ()
    assert LeftOut(dungeon="Den of Nalorakk",
                   reason="no run at +18 or +17 has a public report") in selection.left_out
