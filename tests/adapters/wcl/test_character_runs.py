# ABOUTME: Behaviour tests for reading a zone's dungeons and a character's ranked runs.
# ABOUTME: A rank with no public report is kept, marked, so selection can say why it was skipped.

from typing import Any

import pytest

from wowperf.adapters.wcl.character_runs import build_ranked_runs, build_zone
from wowperf.domain.character.model import Dungeon, RankedRun, Zone

DUNGEONS = (Dungeon(encounter_id=101, name="Den of Nalorakk"),
            Dungeon(encounter_id=102, name="Murder Row"))


def a_rank(level: int, code: str, fight: int | None, start: int) -> dict[str, Any]:
    # A rank with no public log carries a null report start (wcl-api skill, "A
    # character's ranked runs"). A logged one carries the report's own start, which
    # differs from the rank's: the run is a fight inside the report.
    return {
        "report": {"code": code, "fightID": fight, "startTime": start - 500 if code else None},
        "bracketData": level,
        "spec": "Protection",
        "startTime": start,
        "duration": 1_700_000,
        "medal": "bronze",
    }


def test_a_zone_names_its_dungeons_and_difficulties() -> None:
    payload = {
        "worldData": {
            "zone": {
                "id": 55,
                "name": "Mythic+ Season 2",
                "difficulties": [{"id": 10, "name": "Dungeon"}],
                "encounters": [{"id": 101, "name": "Den of Nalorakk"},
                               {"id": 102, "name": "Murder Row"}],
            }
        }
    }

    assert build_zone(payload) == Zone(
        zone_id=55, name="Mythic+ Season 2", difficulty_ids=(10,), dungeons=DUNGEONS
    )


def test_an_unknown_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="no zone"):
        build_zone({"worldData": {"zone": None}})


def test_each_rank_becomes_a_ranked_run_of_its_dungeon() -> None:
    payload = {
        "characterData": {
            "character": {
                "id": 1,
                "hidden": False,
                "e101": {"ranks": [a_rank(18, "aBc123XyZ", 7, 2000)]},
                "e102": {"ranks": [a_rank(17, "", None, 1000)]},
            }
        }
    }

    assert build_ranked_runs(payload, DUNGEONS) == (
        RankedRun(encounter_id=101, keystone_level=18, spec="Protection", start_time_ms=2000,
                  report_code="aBc123XyZ", fight_id=7),
        RankedRun(encounter_id=102, keystone_level=17, spec="Protection", start_time_ms=1000),
    )


def test_a_dungeon_with_no_ranks_contributes_nothing() -> None:
    payload = {
        "characterData": {"character": {"id": 1, "hidden": False, "e101": None, "e102": None}}
    }
    assert build_ranked_runs(payload, DUNGEONS) == ()


def test_a_missing_character_is_refused() -> None:
    with pytest.raises(ValueError, match="no such character"):
        build_ranked_runs({"characterData": {"character": None}}, DUNGEONS)


def test_a_character_with_hidden_rankings_is_refused() -> None:
    with pytest.raises(ValueError, match="hidden"):
        build_ranked_runs({"characterData": {"character": {"id": 1, "hidden": True}}}, DUNGEONS)


def test_a_logged_run_starts_when_its_rank_says_not_when_its_report_does() -> None:
    rank = a_rank(18, "aBc123XyZ", 7, 2000)
    assert rank["report"]["startTime"] != rank["startTime"]
    payload = {"characterData": {"character": {
        "id": 1, "hidden": False, "e101": {"ranks": [rank]}, "e102": None}}}

    assert [run.start_time_ms for run in build_ranked_runs(payload, DUNGEONS)] == [2000]


def test_a_dungeon_the_character_block_does_not_answer_is_refused() -> None:
    # The rankings field "can change without notice": a missing alias is a changed
    # shape, not a dungeon with no runs (that one answers null).
    payload = {"characterData": {"character": {"id": 1, "hidden": False, "e101": None}}}

    with pytest.raises(ValueError, match="102"):
        build_ranked_runs(payload, DUNGEONS)


def test_a_ranking_block_without_ranks_is_refused() -> None:
    payload = {"characterData": {"character": {
        "id": 1, "hidden": False, "e101": {"runs": []}, "e102": None}}}

    with pytest.raises(ValueError, match="101"):
        build_ranked_runs(payload, DUNGEONS)


def test_a_rank_without_a_report_is_refused() -> None:
    rank = a_rank(18, "aBc123XyZ", 7, 2000)
    del rank["report"]
    payload = {"characterData": {"character": {
        "id": 1, "hidden": False, "e101": {"ranks": [rank]}, "e102": None}}}

    with pytest.raises(ValueError, match="101"):
        build_ranked_runs(payload, DUNGEONS)


@pytest.mark.parametrize("code", ["../../evil", "ab/cd12", "ab\\cd12", "abc 123"])
def test_a_report_code_that_could_not_name_a_file_is_refused(code: str) -> None:
    """A run's code becomes part of its two file names beside the character page."""
    payload = {"characterData": {"character": {
        "id": 1, "hidden": False, "e101": {"ranks": [a_rank(18, code, 7, 2000)]}, "e102": None}}}

    with pytest.raises(ValueError, match="101"):
        build_ranked_runs(payload, DUNGEONS)
