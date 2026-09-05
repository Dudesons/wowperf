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
    # A class that cannot exist, so this keeps testing the empty-result path
    # however complete the file becomes.
    assert defensives.for_spec("Bard", "Jazz") == ()


def test_the_defensive_list_carries_cooldowns_and_charges() -> None:
    # Structure, not values: a cooldown is whatever the game currently says, and
    # pinning one here would make a balance patch look like a code failure. The
    # file's `verified` date records when the numbers were last checked.
    from wowperf.adapters.config.toml import load_defensives

    defensives = load_defensives()

    icebound = next(
        a for a in defensives.for_spec("DeathKnight", "Blood") if a.ability_id == 48792
    )
    assert icebound.name == "Icebound Fortitude"
    assert icebound.cooldown_seconds > 0
    assert icebound.charges == 1

    # An ability whose charges are not the default, so the field is actually read
    # rather than defaulted past.
    instincts = next(
        a for a in defensives.for_spec("Druid", "Guardian") if a.ability_id == 61336
    )
    assert instincts.charges == 2


def test_every_listed_defensive_has_a_positive_cooldown() -> None:
    from wowperf.adapters.config.toml import load_defensives

    defensives = load_defensives()

    for _spec, abilities in defensives.entries:
        for ability in abilities:
            assert ability.cooldown_seconds > 0, f"{ability.name} has no usable cooldown"


# The class strings Warcraft Logs actually returns, read from `subType` on player
# actors in cached responses on 2026-09-05. They carry no spaces: a key written
# "Death Knight/Blood" or "Hunter/Beast Mastery" matches no player, silently, for
# as long as it goes unnoticed.
WCL_CLASS_NAMES = frozenset(
    {
        "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
        "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
    }
)


def test_every_spec_key_names_a_class_the_log_api_reports() -> None:
    from wowperf.adapters.config.toml import load_defensives

    unknown = []
    for key, _abilities in load_defensives().entries:
        class_name, _, spec = key.partition("/")
        if class_name not in WCL_CLASS_NAMES or not spec:
            unknown.append(key)
    assert unknown == [], f"spec keys that can never match a player: {unknown}"


def test_no_spec_lists_the_same_ability_twice() -> None:
    from wowperf.adapters.config.toml import load_defensives

    duplicated = []
    for key, abilities in load_defensives().entries:
        ids = [ability.ability_id for ability in abilities]
        if len(ids) != len(set(ids)):
            duplicated.append(key)
    assert duplicated == [], f"specs listing an ability more than once: {duplicated}"


def test_no_spec_is_listed_twice() -> None:
    # TOML itself rejects a duplicated table, but the entries are a tuple of pairs
    # rather than a dict, so a future loader change could let one through and
    # `for_spec` would silently return only the first.
    from wowperf.adapters.config.toml import load_defensives

    keys = [key for key, _ in load_defensives().entries]
    assert len(keys) == len(set(keys)), "a spec appears more than once"
