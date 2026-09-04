# ABOUTME: Reads the committed TOML data files into domain value objects.
# ABOUTME: The only place that knows these constants live on disk rather than in code.

import tomllib
from pathlib import Path

from wowperf.domain.season import SeasonData

DATA_DIR = Path(__file__).resolve().parents[3].parent / "data"
DEFAULT_SEASON_PATH = DATA_DIR / "season.toml"


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
