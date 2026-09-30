# ABOUTME: The audit-data command end to end: committed data files against a test-written cache.
# ABOUTME: Offline by construction -- the command builds no client, so no request can be made.

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from wowperf.adapters.config.toml import load_defensives
from wowperf.cli import app

runner = CliRunner()


def a_page(directory: Path, name: str, report: dict[str, Any]) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"reportData": {"report": report}}), encoding="utf-8"
    )


def ice_block_id() -> int:
    [ice_block] = [one for one in load_defensives().for_spec("Mage", "Arcane")
                   if one.name == "Ice Block"]
    return ice_block.ability_id


def test_an_entry_the_logs_cast_under_another_id_is_named_with_that_id(tmp_path: Path) -> None:
    # A made-up id, so the case holds whatever Ice Block's committed id is.
    other = 999_001
    a_page(tmp_path, "abilities", {"masterData": {
        "actors": [{"id": 5, "name": "Emberkin", "server": "Somewhere", "subType": "Mage"}],
        "abilities": [{"gameID": ice_block_id(), "name": "Ice Block", "icon": "a.jpg"},
                      {"gameID": other, "name": "Ice Block", "icon": "a.jpg"}],
    }})
    a_page(tmp_path, "casts", {"events": {"data": [
        {"timestamp": 1_000, "type": "cast", "sourceID": 5, "abilityGameID": other, "fight": 1},
        {"timestamp": 9_000, "type": "cast", "sourceID": 5, "abilityGameID": other, "fight": 1},
    ], "nextPageTimestamp": None}})

    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (
        f"  Mage/Arcane  Ice Block  {ice_block_id()}: never cast; the logs cast it as {other} x2"
        in result.output.splitlines()
    )
    assert "Read 2 cached pages: 1 distinct ability ids cast." in result.output
    assert "Emberkin" not in result.output


def test_every_data_file_gets_its_heading(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path)])
    headings = [line.split(":")[0] for line in result.output.splitlines()
                if not line.startswith(" ") and "entries never cast" in line]
    assert headings == ["defensives", "externals", "throughput_cooldowns"]


def test_a_missing_cache_directory_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path / "absent")])
    assert result.exit_code == 1
    assert "No cache directory at" in result.output
