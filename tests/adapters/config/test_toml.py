# ABOUTME: Behaviour tests for reading season constants off disk.
# ABOUTME: Also asserts the committed data file parses, so a typo in it fails here.

from pathlib import Path

import pytest

from wowperf.adapters.config.toml import (
    DEFAULT_SEASON_PATH,
    load_raid_partition,
    load_season_data,
)


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


def test_the_raid_partition_is_read_from_the_file_not_assumed(tmp_path: Path) -> None:
    # 7, never the 1 the committed file currently carries: a loader that
    # returned the old hardcoded literal instead of reading the file would
    # pass against 1 and fail here.
    path = tmp_path / "season.toml"
    path.write_text('[raid]\npartition = 7\n', encoding="utf-8")
    assert load_raid_partition(path) == 7


def test_the_committed_season_file_carries_a_raid_partition() -> None:
    # A typo in the committed block fails here rather than at the first live
    # raid query. The value is not pinned: a partition is whatever the current
    # tier's is, and pinning one would make a new tier look like a code failure.
    assert load_raid_partition(DEFAULT_SEASON_PATH) >= 1


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
    assert names == {"health potion", "healthstone", "combat potion"}


def test_the_combat_potion_category_is_excluded_from_survival_categories() -> None:
    # A damage potion shares no cooldown with a health potion in the sense the
    # death-gated survival analysis cares about, so `survival = false` in the
    # data file must keep it out of `for_survival()` while `categories` (read
    # above) still carries it for the comparison half.
    from wowperf.adapters.config.toml import load_consumables

    consumables = load_consumables()
    survival_names = {category.name for category in consumables.for_survival()}
    assert "combat potion" not in survival_names
    assert {"health potion", "healthstone"} <= survival_names


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


def test_the_committed_throughput_file_parses() -> None:
    from wowperf.adapters.config.toml import DEFAULT_THROUGHPUT_PATH, load_throughput_cooldowns

    cooldowns = load_throughput_cooldowns(DEFAULT_THROUGHPUT_PATH)
    assert cooldowns.for_spec("Mage", "Frost"), "Frost Mage has no throughput cooldowns listed"
    assert cooldowns.for_spec("Bard", "Jazz") == ()


def test_every_throughput_cooldown_is_long_enough_to_be_one() -> None:
    # The data file's own criterion. A 30s rotational ability is not a cooldown
    # anyone plans a pull around, and listing one would make the alignment claim
    # fire on abilities nobody holds.
    from wowperf.adapters.config.toml import load_throughput_cooldowns

    for spec, abilities in load_throughput_cooldowns().entries:
        for ability in abilities:
            assert ability.cooldown_seconds >= 45.0, f"{spec}: {ability.name} is too short"


def test_every_throughput_spec_key_names_a_class_the_log_api_reports() -> None:
    from wowperf.adapters.config.toml import load_throughput_cooldowns

    unknown = []
    for key, _abilities in load_throughput_cooldowns().entries:
        class_name, _, spec = key.partition("/")
        if class_name not in WCL_CLASS_NAMES or not spec:
            unknown.append(key)
    assert unknown == [], f"spec keys that can never match a player: {unknown}"


def test_the_committed_roles_file_names_six_tanks_and_seven_healers() -> None:
    from wowperf.adapters.config.toml import load_roles

    roles = load_roles()
    assert len(roles.tanks) == 6
    assert len(roles.healers) == 7
    assert not set(roles.tanks) & set(roles.healers)
    assert all(entry.count("/") == 1 for entry in roles.tanks + roles.healers)


def test_no_ability_is_both_a_defensive_and_a_throughput_cooldown_for_one_spec() -> None:
    """The two files ask opposite questions, so an ability in both answers neither.

    Several abilities are genuinely dual-purpose — a tank cooldown that also
    raises damage — and the judgement of which file owns one belongs in the data,
    made once, rather than being made twice and disagreeing.
    """
    from wowperf.adapters.config.toml import load_defensives, load_throughput_cooldowns

    defensive = {key: {a.ability_id for a in abilities}
                 for key, abilities in load_defensives().entries}
    clashes = []
    for key, abilities in load_throughput_cooldowns().entries:
        overlap = defensive.get(key, set()) & {ability.ability_id for ability in abilities}
        if overlap:
            clashes.append((key, sorted(overlap)))
    assert clashes == [], f"listed as both defensive and throughput: {clashes}"


def test_the_committed_externals_file_parses_and_names_healer_externals() -> None:
    from wowperf.adapters.config.toml import DEFAULT_EXTERNALS_PATH, load_externals

    externals = load_externals(DEFAULT_EXTERNALS_PATH)
    names = {ability.name for _, abilities in externals.entries for ability in abilities}
    assert {"Pain Suppression", "Ironbark", "Life Cocoon", "Guardian Spirit"} <= names
    assert externals.for_spec("Bard", "Jazz") == ()


def test_every_external_has_a_positive_cooldown_and_a_valid_spec_key() -> None:
    from wowperf.adapters.config.toml import load_externals

    for key, abilities in load_externals().entries:
        class_name, _, spec = key.partition("/")
        assert class_name in WCL_CLASS_NAMES and spec, f"spec key can never match: {key}"
        for ability in abilities:
            assert ability.cooldown_seconds > 0, f"{key}: {ability.name} has no cooldown"
            assert ability.charges >= 1


def test_the_committed_resurrections_file_lists_self_resurrection_spells() -> None:
    from wowperf.adapters.config.toml import DEFAULT_RESURRECTIONS_PATH, load_self_resurrections

    spells = load_self_resurrections(DEFAULT_RESURRECTIONS_PATH)
    assert spells.ability_ids, "the file lists no spell at all"
    assert len(set(spells.ability_ids)) == len(spells.ability_ids)


def test_no_ability_lives_in_two_of_the_three_cooldown_files_for_one_spec() -> None:
    """Defensives, throughput cooldowns and externals ask three different questions.

    An ability answering two of them at once would be judged twice and could
    disagree with itself; the judgement of which file owns it is made once, in
    the data.
    """
    from wowperf.adapters.config.toml import (
        load_defensives,
        load_externals,
        load_throughput_cooldowns,
    )

    owners: dict[tuple[str, int], list[str]] = {}
    for label, loaded in (
        ("defensive", load_defensives()),
        ("throughput", load_throughput_cooldowns()),
        ("external", load_externals()),
    ):
        for key, abilities in loaded.entries:
            for ability in abilities:
                owners.setdefault((key, ability.ability_id), []).append(label)
    clashes = {k: v for k, v in owners.items() if len(v) > 1}
    assert clashes == {}, f"listed in more than one file: {clashes}"


def test_the_consumable_buffs_file_loads_its_three_categories() -> None:
    from wowperf.adapters.config.toml import load_consumable_buffs

    buffs = load_consumable_buffs()
    assert set(buffs.categories()) == {"flask", "food", "augment rune"}


def test_well_fed_carries_every_id_it_was_measured_under() -> None:
    from wowperf.adapters.config.toml import load_consumable_buffs

    # Measured 2026-09-14: `Well Fed` spans six ability ids. One id per
    # category would miss five of them and report a fed player as unfed.
    assert len(load_consumable_buffs().ids_for("food")) >= 6


def test_an_unknown_category_has_no_ids() -> None:
    from wowperf.adapters.config.toml import load_consumable_buffs

    assert load_consumable_buffs().ids_for("weapon oil") == ()


def test_no_consumable_buff_category_carries_the_id_measured_for_another() -> None:
    # A wholesale swap of two categories' id lists would still pass the exact-name
    # check above, and would still pass food's >=6 count check above (augment
    # rune also lists more than six ids). Anchoring one measured id per category
    # to that category, and only that category, is what catches a swap.
    from wowperf.adapters.config.toml import load_consumable_buffs

    buffs = load_consumable_buffs()
    known_id_by_category = {
        "flask": 1235057,  # Flask of Thalassian Resistance
        "food": 451920,
        "augment rune": 1287770,  # Rune of the Versatile Warrior
    }
    for category, ability_id in known_id_by_category.items():
        for other_category in known_id_by_category:
            if other_category == category:
                assert ability_id in buffs.ids_for(category)
            else:
                assert ability_id not in buffs.ids_for(other_category)


def test_the_combat_potion_category_is_loaded_from_consumables() -> None:
    from wowperf.adapters.config.toml import load_consumables

    names = {category.name for category in load_consumables().categories}
    assert "combat potion" in names


def test_slot_names_are_read_from_a_toml_file(tmp_path: Path) -> None:
    from wowperf.adapters.config.toml import load_slot_names

    path = tmp_path / "slot_names.toml"
    path.write_text(
        'verified = "2026-09-14"\n'
        "[slots]\n"
        '7 = "feet"\n'
        '12 = "trinket"\n',
        encoding="utf-8",
    )
    slot_names = load_slot_names(path)
    assert slot_names.name_for(7) == "feet"
    assert slot_names.name_for(12) == "trinket"


def test_an_unlisted_slot_falls_back_to_its_raw_index() -> None:
    from wowperf.adapters.config.toml import load_slot_names

    # Slots 3 and 17 were never identified and are absent from the committed
    # file on purpose; the fallback must not invent a name for them.
    slot_names = load_slot_names()
    assert slot_names.name_for(3) == "slot 3"
    assert slot_names.name_for(17) == "slot 17"


def test_the_committed_slot_names_file_names_every_identified_slot() -> None:
    from wowperf.adapters.config.toml import load_slot_names

    slot_names = load_slot_names()
    # Read off icon filenames, per `.claude/skills/wcl-api/SKILL.md`.
    expected = {
        0: "head", 1: "neck", 2: "shoulder", 4: "chest", 5: "waist", 6: "legs",
        7: "feet", 8: "wrist", 9: "hands", 10: "ring", 11: "ring", 12: "trinket",
        13: "trinket", 14: "back", 15: "main hand", 16: "off hand",
    }
    for slot, name in expected.items():
        assert slot_names.name_for(slot) == name
