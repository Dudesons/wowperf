# ABOUTME: Reads the committed TOML data files into domain value objects.
# ABOUTME: The only place that knows these constants live on disk rather than in code.

import tomllib
from pathlib import Path

from wowperf.domain.season import (
    ConsumableBuffs,
    ConsumableCategory,
    Consumables,
    CooldownAbility,
    DefensiveAbility,
    Defensives,
    ExternalAbility,
    Externals,
    Roles,
    SeasonData,
    SelfResurrections,
    ThroughputCooldowns,
)

DATA_DIR = Path(__file__).resolve().parents[3].parent / "data"
DEFAULT_SEASON_PATH = DATA_DIR / "season.toml"
DEFAULT_DEFENSIVES_PATH = DATA_DIR / "defensives.toml"
DEFAULT_CONSUMABLES_PATH = DATA_DIR / "consumables.toml"
DEFAULT_CONSUMABLE_BUFFS_PATH = DATA_DIR / "consumable_buffs.toml"
DEFAULT_THROUGHPUT_PATH = DATA_DIR / "throughput_cooldowns.toml"
DEFAULT_ROLES_PATH = DATA_DIR / "roles.toml"
DEFAULT_EXTERNALS_PATH = DATA_DIR / "externals.toml"
DEFAULT_RESURRECTIONS_PATH = DATA_DIR / "resurrections.toml"


def _read(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"No data file at {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_cooldowns[AbilityT: CooldownAbility](
    path: Path, ability: type[AbilityT]
) -> tuple[tuple[str, tuple[AbilityT, ...]], ...]:
    """Read a file of cooldowns grouped by class and specialisation.

    The defensives, the externals and the throughput cooldowns hold the same
    four fields under the same spec keys and differ only in the record they
    build, so all three are read here. A top-level key that is not a table is
    the `verified` date, which the domain does not use.
    """
    entries: list[tuple[str, tuple[AbilityT, ...]]] = []
    for key, value in _read(path).items():
        if not isinstance(value, dict):
            continue
        entries.append(
            (
                key,
                tuple(
                    ability(
                        ability_id=int(item["ability_id"]),
                        name=str(item["name"]),
                        cooldown_seconds=float(item["cooldown_seconds"]),
                        charges=int(item.get("charges", 1)),
                    )
                    for item in value.get("abilities") or ()
                ),
            )
        )
    return tuple(entries)


def load_season_data(path: Path = DEFAULT_SEASON_PATH) -> SeasonData:
    """Read the season timer constants."""
    penalty = _read(path)["death_penalty"]
    assert isinstance(penalty, dict)
    return SeasonData(
        death_penalty_seconds=float(penalty["seconds"]),
        death_penalty_seconds_high_key=float(penalty["seconds_high_key"]),
        high_key_threshold=int(penalty["high_key_threshold"]),
    )


def load_defensives(path: Path = DEFAULT_DEFENSIVES_PATH) -> Defensives:
    """Read the hand-maintained defensive cooldown list."""
    return Defensives(entries=_load_cooldowns(path, DefensiveAbility))


def load_externals(path: Path = DEFAULT_EXTERNALS_PATH) -> Externals:
    """Read the hand-maintained list of cooldowns cast on other players."""
    return Externals(entries=_load_cooldowns(path, ExternalAbility))


def load_consumables(path: Path = DEFAULT_CONSUMABLES_PATH) -> Consumables:
    """Healing consumables by cooldown category, from the committed TOML file.

    `verified` is a date the file carries for a reader, not a field the domain
    uses, so it is skipped like any other non-table key.
    """
    raw = _read(path)
    categories = []
    for name, block in raw.items():
        if not isinstance(block, dict):
            continue
        categories.append(
            ConsumableCategory(
                name=name,
                cooldown_seconds=float(block["cooldown_seconds"]),
                ability_ids=tuple(block.get("ability_ids", ())),
            )
        )
    return Consumables(categories=tuple(categories))


def load_consumable_buffs(
    path: Path = DEFAULT_CONSUMABLE_BUFFS_PATH,
) -> ConsumableBuffs:
    """Consumable buff ids by category, from the committed TOML file.

    `verified` is a date the file carries for a reader, not a field the domain
    uses, so it is skipped like any other non-table key.
    """
    raw = _read(path)
    entries = []
    for name, block in raw.items():
        if not isinstance(block, dict):
            continue
        entries.append((name, tuple(block.get("ability_ids", ()))))
    return ConsumableBuffs(entries=tuple(entries))


def load_roles(path: Path = DEFAULT_ROLES_PATH) -> Roles:
    """Tank and healer specialisations, from the committed TOML file."""
    raw = _read(path)
    tank = raw.get("tank")
    healer = raw.get("healer")
    assert isinstance(tank, dict) and isinstance(healer, dict)
    return Roles(
        tanks=tuple(str(spec) for spec in tank.get("specs", ())),
        healers=tuple(str(spec) for spec in healer.get("specs", ())),
    )


def load_self_resurrections(path: Path = DEFAULT_RESURRECTIONS_PATH) -> SelfResurrections:
    """Read the short list of spells a dead player casts to bring themselves back."""
    raw = _read(path)
    ids = raw.get("ability_ids") or []
    assert isinstance(ids, list)
    return SelfResurrections(ability_ids=tuple(int(item) for item in ids))


def load_throughput_cooldowns(path: Path = DEFAULT_THROUGHPUT_PATH) -> ThroughputCooldowns:
    """Throughput cooldowns per class and specialisation, from the committed TOML file."""
    return ThroughputCooldowns(entries=_load_cooldowns(path, CooldownAbility))
