# ABOUTME: Integration tests for translating a Warcraft Logs report into the domain model.
# ABOUTME: Runs against a committed payload shaped like the real one; no network involved.

import json
from pathlib import Path
from typing import Any, cast

import pytest

from wowperf.adapters.wcl.ingest import IngestError, build_run, select_keystone_fight

FIXTURE = Path(__file__).parent / "fixtures" / "report_fights.json"


def report() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload["reportData"]["report"])


def _fight(fight_id: int, keystone_level: int | None, kill: bool | None) -> dict[str, Any]:
    """A minimal fight dict carrying only the fields select_keystone_fight reads."""
    return {"id": fight_id, "keystoneLevel": keystone_level, "kill": kill}


def test_the_keystone_fight_is_the_one_with_a_keystone_level() -> None:
    fight = select_keystone_fight(report()["fights"], None)
    assert fight["id"] == 2


def test_an_explicit_fight_id_selects_that_fight() -> None:
    fight = select_keystone_fight(report()["fights"], 2)
    assert fight["id"] == 2


def test_a_fight_id_that_is_not_a_keystone_run_is_rejected() -> None:
    with pytest.raises(IngestError, match="not a Mythic\\+ run"):
        select_keystone_fight(report()["fights"], 1)


def test_a_report_with_no_keystone_fight_is_rejected() -> None:
    with pytest.raises(IngestError, match="no Mythic\\+ run"):
        select_keystone_fight([{"id": 1, "keystoneLevel": None}], None)


def test_keystone_fights_with_none_completed_are_rejected() -> None:
    fights = [_fight(1, 10, False), _fight(2, 12, None)]
    with pytest.raises(IngestError) as exc_info:
        select_keystone_fight(fights, None)
    assert str(exc_info.value) == "This report contains no completed Mythic+ run"


def test_several_completed_keystone_fights_without_fight_id_are_rejected() -> None:
    fights = [_fight(1, 10, True), _fight(2, 12, True)]
    with pytest.raises(IngestError) as exc_info:
        select_keystone_fight(fights, None)
    assert str(exc_info.value) == "This report holds several Mythic+ runs (1, 2); pass --fight"


def test_a_fight_id_naming_an_uncompleted_keystone_fight_is_rejected() -> None:
    fights = [_fight(1, 10, False)]
    with pytest.raises(IngestError) as exc_info:
        select_keystone_fight(fights, 1)
    assert str(exc_info.value) == "Fight 1 is a Mythic+ run that was not completed"


def test_keystone_facts_are_carried_into_the_run() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.report_code == "abc123"
    assert run.fight_id == 2
    assert run.dungeon_name == "Murder Row"
    assert run.keystone_level == 12
    assert run.affix_ids == (9, 10)
    assert run.keystone_time_ms == 1_800_000
    assert run.keystone_bonus == 1
    assert (run.count_reached, run.count_required) == (820, 800)


def test_the_npc_count_map_keys_become_integers() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.npc_count_map == {5001: 4, 5002: 12}


def test_players_join_master_data_with_the_index_aligned_fight_arrays() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert [(p.name, p.class_name, p.spec, p.item_level) for p in run.players] == [
        ("Frostie", "Mage", "Frost", 301),
        ("Healbot", "Priest", "Holy", 299),
    ]


def test_pulls_keep_their_order_and_classify_bosses() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert [(p.index, p.is_boss) for p in run.pulls] == [(0, False), (1, True)]


def test_pull_enemies_carry_their_game_ids() -> None:
    run = build_run(report(), select_keystone_fight(report()["fights"], None))
    assert run.pulls[0].signature == (5001, 5002)
