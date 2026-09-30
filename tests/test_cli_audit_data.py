# ABOUTME: The audit-data command end to end: committed data files against a test-written cache.
# ABOUTME: Offline by construction -- the command builds no client, so no request can be made.

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from wowperf.adapters.config.toml import (
    load_defensives,
    load_externals,
    load_throughput_cooldowns,
)
from wowperf.cli import app

runner = CliRunner()


def a_page(directory: Path, name: str, report: dict[str, Any]) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"reportData": {"report": report}}), encoding="utf-8"
    )


def ice_block_id(spec: str) -> int:
    [ice_block] = [one for one in load_defensives().for_spec("Mage", spec)
                   if one.name == "Ice Block"]
    return ice_block.ability_id


def test_an_entry_the_logs_cast_under_another_id_is_named_with_that_id(tmp_path: Path) -> None:
    # A made-up id, so the case holds whatever Ice Block's committed id is.
    other = 999_001
    a_page(tmp_path, "abilities", {"masterData": {
        "actors": [{"id": 5, "name": "Emberkin", "server": "Somewhere", "subType": "Mage"}],
        "abilities": [{"gameID": ice_block_id("Arcane"), "name": "Ice Block", "icon": "a.jpg"},
                      {"gameID": other, "name": "Ice Block", "icon": "a.jpg"},
                      # Named but never cast, so the cache holds two names and one cast id.
                      {"gameID": 999_002, "name": "Made-up Ward", "icon": "a.jpg"}],
    }})
    a_page(tmp_path, "casts", {"events": {"data": [
        {"timestamp": 1_000, "type": "cast", "sourceID": 5, "abilityGameID": other, "fight": 1},
        {"timestamp": 9_000, "type": "cast", "sourceID": 5, "abilityGameID": other, "fight": 1},
    ], "nextPageTimestamp": None}})

    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    arcane = (f"  Mage/Arcane  Ice Block  {ice_block_id('Arcane')}: never cast; "
              f"the logs cast it as {other} x2")
    frost = (f"  Mage/Frost  Ice Block  {ice_block_id('Frost')}: never cast; "
             f"the logs cast it as {other} x2")
    assert lines.count(arcane) == 1
    assert lines.count(frost) == 1
    assert "Read 2 cached pages: 1 distinct ability ids cast." in lines
    assert "Emberkin" not in result.output


def test_every_data_file_gets_its_heading_with_its_own_count(tmp_path: Path) -> None:
    # An empty cache casts nothing, so every entry of each file is never cast.
    counts = {
        file: sum(len(abilities) for _spec, abilities in collection)
        for file, collection in (
            ("defensives", load_defensives().entries),
            ("externals", load_externals().entries),
            ("throughput_cooldowns", load_throughput_cooldowns().entries),
        )
    }
    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path)])
    headings = [line for line in result.output.splitlines()
                if not line.startswith(" ") and "entries never cast" in line]
    assert headings == [f"{file}: {n} of {n} entries never cast" for file, n in counts.items()]


def test_a_missing_cache_directory_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path / "absent")])
    assert result.exit_code == 1
    assert "No cache directory at" in result.output
