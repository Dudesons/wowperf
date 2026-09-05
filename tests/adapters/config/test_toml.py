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


def test_the_committed_consumables_file_parses() -> None:
    from wowperf.adapters.config.toml import DEFAULT_CONSUMABLES_PATH, load_consumables

    consumables = load_consumables(DEFAULT_CONSUMABLES_PATH)
    names = {category.name for category in consumables.categories}
    assert names == {"health potion", "healthstone"}


def test_a_category_carries_its_cooldown_and_every_id_that_shares_it() -> None:
    from wowperf.adapters.config.toml import load_consumables

    stone = next(c for c in load_consumables().categories if c.name == "healthstone")
    assert stone.cooldown_seconds == 60.0
    # Soulburn: Healthstone consumes one without being drunk itself, so it has to
    # block the category like any other id in it.
    assert 387636 in stone.ability_ids


def test_every_consumable_category_has_a_positive_cooldown_and_some_ids() -> None:
    from wowperf.adapters.config.toml import load_consumables

    for category in load_consumables().categories:
        assert category.cooldown_seconds > 0, f"{category.name} has no usable cooldown"
        assert category.ability_ids, f"{category.name} lists no abilities"


def test_no_ability_belongs_to_two_categories() -> None:
    # An id in two categories would make availability depend on which category
    # was consulted first, which is not a question with an answer.
    from wowperf.adapters.config.toml import load_consumables

    seen: set[int] = set()
    for category in load_consumables().categories:
        overlap = seen & set(category.ability_ids)
        assert not overlap, f"{category.name} repeats ids from another category: {overlap}"
        seen |= set(category.ability_ids)


def test_the_committed_offensive_file_parses() -> None:
    from wowperf.adapters.config.toml import DEFAULT_OFFENSIVE_PATH, load_offensive_cooldowns

    cooldowns = load_offensive_cooldowns(DEFAULT_OFFENSIVE_PATH)
    assert cooldowns.for_spec("Mage", "Frost"), "Frost Mage has no offensive cooldowns listed"
    assert cooldowns.for_spec("Bard", "Jazz") == ()


def test_every_offensive_cooldown_is_long_enough_to_be_one() -> None:
    # The data file's own criterion. A 30s rotational ability is not a cooldown
    # anyone plans a pull around, and listing one would make the alignment claim
    # fire on abilities nobody holds.
    from wowperf.adapters.config.toml import load_offensive_cooldowns

    for spec, abilities in load_offensive_cooldowns().entries:
        for ability in abilities:
            assert ability.cooldown_seconds >= 45.0, f"{spec}: {ability.name} is too short"


def test_every_offensive_spec_key_names_a_class_the_log_api_reports() -> None:
    from wowperf.adapters.config.toml import load_offensive_cooldowns

    unknown = []
    for key, _abilities in load_offensive_cooldowns().entries:
        class_name, _, spec = key.partition("/")
        if class_name not in WCL_CLASS_NAMES or not spec:
            unknown.append(key)
    assert unknown == [], f"spec keys that can never match a player: {unknown}"


def test_no_ability_is_both_a_defensive_and_an_offensive_cooldown_for_one_spec() -> None:
    """The two files ask opposite questions, so an ability in both answers neither.

    Several abilities are genuinely dual-purpose — a tank cooldown that also
    raises damage — and the judgement of which file owns one belongs in the data,
    made once, rather than being made twice and disagreeing.
    """
    from wowperf.adapters.config.toml import load_defensives, load_offensive_cooldowns

    defensive = {key: {a.ability_id for a in abilities}
                 for key, abilities in load_defensives().entries}
    clashes = []
    for key, abilities in load_offensive_cooldowns().entries:
        overlap = defensive.get(key, set()) & {ability.ability_id for ability in abilities}
        if overlap:
            clashes.append((key, sorted(overlap)))
    assert clashes == [], f"listed as both defensive and offensive: {clashes}"
