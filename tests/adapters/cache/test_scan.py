# ABOUTME: Reading cached pages for cast ids and ability names, on pages written for the test.
# ABOUTME: The pages mimic the API's shapes; every id and name in them is made up.

import json
from pathlib import Path
from typing import Any

from wowperf.adapters.cache.scan import scan_cache


def a_cast(ability_id: int, at: int, source: int = 5, fight: int = 1) -> dict[str, Any]:
    return {"timestamp": at, "type": "cast", "sourceID": source, "targetID": -1,
            "abilityGameID": ability_id, "fight": fight}


def events_page(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"reportData": {"report": {"events": {"data": list(rows), "nextPageTimestamp": None}}}}


def abilities_page(*pairs: tuple[int, str], actors: tuple[str, ...] = ()) -> dict[str, Any]:
    # A real cached actor carries `id`, `name`, `server` and `subType` (checked 2026-09-30).
    return {"reportData": {"report": {"masterData": {
        "actors": [{"id": index, "name": name, "server": "Somewhere", "subType": "Mage"}
                   for index, name in enumerate(actors)],
        "abilities": [{"gameID": game_id, "name": name, "icon": "x.jpg"}
                      for game_id, name in pairs],
    }}}}


def write(directory: Path, *pages: dict[str, Any]) -> Path:
    for index, page in enumerate(pages):
        (directory / f"{index:04d}.json").write_text(json.dumps(page), encoding="utf-8")
    return directory


def test_cast_rows_are_counted_by_ability_id(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, events_page(a_cast(200, 1_000), a_cast(200, 5_000),
                                                  a_cast(300, 9_000))))
    assert (scan.pages, scan.casts) == (1, {200: 2, 300: 1})


def test_a_row_that_is_not_a_cast_is_not_counted(tmp_path: Path) -> None:
    damage = {**a_cast(200, 1_000), "type": "damage"}
    assert scan_cache(write(tmp_path, events_page(damage))).casts == {}


def test_a_row_two_overlapping_pages_both_hold_is_counted_once(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, events_page(a_cast(200, 1_000)),
                            events_page(a_cast(200, 1_000), a_cast(200, 2_000))))
    assert scan.casts == {200: 2}


def test_ability_tables_give_every_id_a_name_has_folded_to_one_case(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, abilities_page((100, "Ice Shield")),
                            abilities_page((200, "ICE SHIELD"), (300, "Burst"))))
    assert scan.named == {"ice shield": frozenset({100, 200}), "burst": frozenset({300})}


def test_no_actor_name_is_read(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, abilities_page((100, "Ice Shield"), actors=("Emberkin",))))
    assert "emberkin" not in scan.named


def test_a_named_id_outside_an_ability_table_is_not_read(tmp_path: Path) -> None:
    page = {"reportData": {"report": {"fights": [{"gameID": 777, "name": "Grand Enemy"}]}}}
    assert scan_cache(write(tmp_path, page)).named == {}


def test_a_page_in_a_subdirectory_is_read(tmp_path: Path) -> None:
    # Reference runs are cached a level down, in their own tier.
    nested = tmp_path / "references"
    nested.mkdir()
    write(tmp_path, events_page(a_cast(200, 1_000)))
    write(nested, events_page(a_cast(300, 1_000)))
    scan = scan_cache(tmp_path)
    assert (scan.pages, scan.casts) == (2, {200: 1, 300: 1})


def test_two_casters_pressing_at_the_same_moment_are_two_casts(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, events_page(a_cast(200, 1_000, source=5),
                                                  a_cast(200, 1_000, source=6))))
    assert scan.casts == {200: 2}


def test_one_caster_at_the_same_moment_in_two_fights_is_two_casts(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, events_page(a_cast(200, 1_000, fight=1),
                                                  a_cast(200, 1_000, fight=2))))
    assert scan.casts == {200: 2}


def test_a_page_holding_neither_reads_as_nothing(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, {"rateLimitData": {"pointsSpentThisHour": 3}}))
    assert (scan.pages, scan.casts, scan.named) == (1, {}, {})
