# ABOUTME: Behaviour tests for reading season constants off disk.
# ABOUTME: Also asserts the committed data file parses, so a typo in it fails here.

from pathlib import Path

import pytest

from wowperf.adapters.config.toml import DEFAULT_SEASON_PATH, load_season_data


def test_season_data_is_read_from_a_toml_file(tmp_path: Path) -> None:
    path = tmp_path / "season.toml"
    path.write_text(
        '[death_penalty]\n'
        'seconds = 4.0\n'
        'seconds_high_key = 14.0\n'
        'high_key_threshold = 10\n',
        encoding="utf-8",
    )
    season = load_season_data(path)
    assert season.death_penalty(9) == 4.0
    assert season.death_penalty(10) == 14.0


def test_the_committed_season_file_parses() -> None:
    season = load_season_data(DEFAULT_SEASON_PATH)
    assert season.death_penalty(2) == 5.0
    assert season.death_penalty(12) == 15.0


def test_a_missing_file_says_which_one(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nope.toml"):
        load_season_data(tmp_path / "nope.toml")


def test_the_committed_defensives_file_parses() -> None:
    from wowperf.adapters.config.toml import DEFAULT_DEFENSIVES_PATH, load_defensives

    defensives = load_defensives(DEFAULT_DEFENSIVES_PATH)
    arcane = defensives.for_spec("Mage", "Arcane")
    assert any(ability.name == "Ice Block" for ability in arcane)
    assert defensives.for_spec("Druid", "Feral") == ()


def test_the_defensive_list_carries_cooldowns_and_charges() -> None:
    from wowperf.adapters.config.toml import load_defensives

    defensives = load_defensives()
    blood = defensives.for_spec("DeathKnight", "Blood")

    icebound = next(a for a in blood if a.ability_id == 48792)
    assert icebound.cooldown_seconds == 180.0
    assert icebound.charges == 1


def test_every_listed_defensive_has_a_positive_cooldown() -> None:
    from wowperf.adapters.config.toml import load_defensives

    defensives = load_defensives()

    for _spec, abilities in defensives.entries:
        for ability in abilities:
            assert ability.cooldown_seconds > 0, f"{ability.name} has no usable cooldown"
