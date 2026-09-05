# ABOUTME: Reads the committed TOML data files into domain value objects.
# ABOUTME: The only place that knows these constants live on disk rather than in code.

import tomllib
from pathlib import Path

from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    CooldownAbility,
    DefensiveAbility,
    Defensives,
    OffensiveCooldowns,
    SeasonData,
)

DATA_DIR = Path(__file__).resolve().parents[3].parent / "data"
DEFAULT_SEASON_PATH = DATA_DIR / "season.toml"
DEFAULT_DEFENSIVES_PATH = DATA_DIR / "defensives.toml"
DEFAULT_CONSUMABLES_PATH = DATA_DIR / "consumables.toml"
DEFAULT_OFFENSIVE_PATH = DATA_DIR / "offensive_cooldowns.toml"


def _read(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"No data file at {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


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
    raw = _read(path)
    entries = []
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue  # the top-level `verified` date
        abilities = value.get("abilities") or []
        entries.append(
            (
                key,
                tuple(
                    DefensiveAbility(
                        ability_id=int(item["ability_id"]),
                        name=str(item["name"]),
                        cooldown_seconds=float(item["cooldown_seconds"]),
                        charges=int(item.get("charges", 1)),
                    )
                    for item in abilities
                ),
            )
        )
    return Defensives(entries=tuple(entries))


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


def load_offensive_cooldowns(path: Path = DEFAULT_OFFENSIVE_PATH) -> OffensiveCooldowns:
    """Throughput cooldowns per class and specialisation, from the committed TOML file."""
    raw = _read(path)
    entries = []
    for key, block in raw.items():
        if not isinstance(block, dict):
            continue
        entries.append(
            (
                key,
                tuple(
                    CooldownAbility(**ability) for ability in block.get("abilities", ())
                ),
            )
        )
    return OffensiveCooldowns(entries=tuple(entries))
