# ABOUTME: Pins the ability ids corrected to what real logs cast, so a revert to the old ids fails.
# ABOUTME: It guards the data, not the game: `wowperf audit-data` is what checks the game.

import pytest

from wowperf.adapters.config.toml import load_defensives, load_throughput_cooldowns

CORRECTED = (
    ("defensives", "Mage", "Arcane", "Alter Time", 342245, 108978),
    ("defensives", "Mage", "Fire", "Alter Time", 342245, 108978),
    ("defensives", "Mage", "Frost", "Alter Time", 342245, 108978),
    ("defensives", "Monk", "Mistweaver", "Fortifying Brew", 115203, 243435),
    ("defensives", "Monk", "Windwalker", "Fortifying Brew", 115203, 243435),
    ("throughput", "Warrior", "Arms", "Bladestorm", 446035, 227847),
    ("throughput", "Warrior", "Fury", "Bladestorm", 446035, 227847),
    ("throughput", "DeathKnight", "Frost", "Breath of Sindragosa", 1249658, 152279),
    ("throughput", "Rogue", "Assassination", "Kingsbane", 385627, 192759),
    ("throughput", "DemonHunter", "Havoc", "Metamorphosis", 200166, 191427),
    ("throughput", "Warrior", "Fury", "Odyn's Fury", 385059, 205545),
    ("throughput", "DemonHunter", "Havoc", "The Hunt", 370965, 323639),
)
"""The twelve entries of docs/plans/2026-09-30-cast-ids-from-the-log-design.md, with the id the
logs cast and the id the entry held before, which no log in the cache casts."""


@pytest.mark.parametrize(("file", "class_name", "spec", "name", "cast", "old"), CORRECTED)
def test_a_corrected_entry_holds_the_id_the_logs_cast(
    file: str, class_name: str, spec: str, name: str, cast: int, old: int
) -> None:
    data = load_defensives() if file == "defensives" else load_throughput_cooldowns()
    ids = [one.ability_id for one in data.for_spec(class_name, spec) if one.name == name]
    assert ids == [cast], f"{class_name}/{spec} {name}: {ids}, expected {cast} (was {old})"
