# Mythic+ Post-Mortem, Plan B: Analysers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a fetched Mythic+ run into a ranked list of `Finding`s, each denominated in seconds and each carrying a confidence badge, written to disk as JSON.

**Architecture:** Six pure analysers live under `src/wowperf/domain/analysis/`, each a module of functions taking domain objects and returning `Finding`s. They perform no I/O and know nothing of Warcraft Logs. New event streams (enemy casts, interrupts, enemy deaths, damage taken) arrive through the existing adapter, widening `LoadedRun`. An application service runs every analyser and ranks the result; the `analyze` command writes it.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `typer`, `httpx`, `pytest`, `ruff`, `mypy`. `tomllib` from the standard library for season data.

**Spec:** `docs/plans/2026-09-03-mplus-postmortem-design.md` — §5 is what this plan implements, §3.5 and §4 are load-bearing for it.

**Depends on:** Plan A, merged at `62fd0e4`. Read `src/wowperf/domain/model.py`, `events.py`, `findings.py` and `src/wowperf/adapters/wcl/repository.py` before starting.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no file reads, no `tomllib` calls. Adapters do that. The analysers are pure functions over domain objects.
- **Every `Finding` carries a `Confidence`** of `measured`, `derived`, or `inferred`, and the badge must match how the number was obtained. A derived number labelled `measured` is a defect.
- **Every Mythic+ finding is denominated in seconds.** Not percentiles, not scores. A finding with no honest seconds figure sets `seconds_lost=None` rather than inventing one.
- **The LLM never computes a number.** Every metric comes from tested Python.
- **No hardcoded season data.** Death penalty constants live in `data/season.toml` with a verified-on date. No zone, encounter, or affix IDs in code.
- **Cache every Warcraft Logs response.** The budget is 3600 points an hour; a full event fetch costs about 6.
- **Never invent a Warcraft Logs field name.** Every field this plan uses is listed under "Verified event shapes" below, confirmed against the live API on 2026-09-04.
- **Fight, pull and event timestamps are milliseconds relative to report start.** `Report.startTime` is absolute epoch milliseconds.
- **English** in code, comments, error strings, and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. Subject says what the commit does to the repository; the body explains why.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- Every file starts with two `# ABOUTME: ` comment lines. Empty `__init__.py` markers are exempt.
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument — `pyproject.toml` sets `files = ["src", "tests"]`). Ruff's line length is 100.

## Verified event shapes

Confirmed against report `6Kx1P9GbNXrcLdHa` fight 36 on 2026-09-04 by live query. **These are the real field names.** The design's §5.3 prose uses combat-log names (`SPELL_CAST_START`, `extraSpellId`, `sourceInstanceID`) that do **not** exist in the API; the table below supersedes them.

| Stream | Query arguments | `type` values | Fields |
| --- | --- | --- | --- |
| Enemy casts | `dataType: Casts, hostilityType: Enemies` | `begincast`, `cast` | `abilityGameID`, `fight`, `sourceID`, `sourceInstance`, `sourceMarker`, `targetID`, `timestamp`, `type` |
| Interrupts | `dataType: Interrupts, hostilityType: Friendlies` | `interrupt`, `applydebuff` | `abilityGameID`, `extraAbilityGameID`, `fight`, `sourceID`, `sourceInstance`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type` |
| Enemy deaths | `dataType: Deaths, hostilityType: Enemies` | `death` | `abilityGameID`, `fight`, `killerID`, `killerInstance`, `killingAbilityGameID`, `sourceID`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type` |
| Damage taken | `dataType: DamageTaken, hostilityType: Friendlies` | `damage` | `abilityGameID`, `absorbed`, `amount`, `blocked`, `buffs`, `fight`, `hitType`, `isAoE`, `mitigated`, `sourceID`, `sourceInstance`, `sourceMarker`, `targetID`, `tick`, `timestamp`, `type`, `unmitigatedAmount` |

Four further facts, all verified:

- **`sourceInstance` is absent when the instance is the first one.** Treat a missing `sourceInstance` as instance `0`, consistently on both sides of any comparison. Two copies of the same NPC are distinguished by `(sourceID, sourceInstance)`, never by `sourceID` alone.
- **On an `interrupt` event, `abilityGameID` is the kick and `extraAbilityGameID` is the spell that was interrupted.** The interrupted enemy is `targetID` / `targetInstance`; the player who kicked is `sourceID`.
- **`npcCountMap` keys are strings holding NPC game IDs**, values are the enemy-forces count each kill awards. All 21 keys on the sample fight matched an actor `gameID`, none matched a report actor id. The join is: enemy death `targetID` → `masterData.actors(type: "NPC")` → `gameID` → `npcCountMap[str(gameID)]`.
- **`masterData.actors` accepts `type: "NPC"` and exposes `gameID`.** `ReportActor` fields are `gameID, icon, id, name, petOwner, server, subType, type`. There is no `Resurrects` event data type; `EventDataType` is `All, Buffs, Casts, CombatantInfo, DamageDone, DamageTaken, Deaths, Debuffs, Dispels, Healing, Interrupts, Resources, Summons, Threat`.

On a damage event, `amount` excludes what was absorbed — a real row read `amount: 0, absorbed: 123570`. Use `unmitigatedAmount` for "how hard did this hit", which is the question §5.5 asks.

## Decisions this plan makes

Recorded here so an implementer does not rediscover them, and so a reviewer does not flag them.

1. **`Finding` keeps the shape Plan A shipped.** Design §4 lists `severity` and `pull_ref`; the built model has neither, using `pull_index` and ranking purely by `seconds_lost`. Severity would duplicate the ranking. Do not add it; do not rename `pull_index`.
2. **`analyze` writes only `<code>-<fight>.findings.json` in this plan.** Design §3.6 says two files; the HTML is Plan D and will be added alongside, not instead. The command name is final now so Plan D does not rename it.
3. **§5.5 ships enabled, not behind `--deep`.** Measurement closed that question: a full event fetch costs about 6 points of 3600. `--deep` is not implemented in this plan and must not be added.
4. **Damage taken is compared against the group median for the same ability.** Never "avoidable damage" — the design forbids it explicitly, and this plan must not smuggle it back in under another name.
5. **No damage ranking, no DPS metric, no parse percentile.** Design §5.5 is explicit: the unit of optimisation in Mythic+ is the dungeon, not the player.
6. **The defensive list is data, not code.** It lives in `data/defensives.toml` with its own verified-on date, alongside `data/season.toml`.

## File Structure

| File | Responsibility |
| --- | --- |
| `data/season.toml` | Death timer penalties, with verified-on dates |
| `data/defensives.toml` | Per-spec defensive ability IDs, with a verified-on date |
| `src/wowperf/domain/events.py` | *Modified.* Adds `EnemyCast`, `InterruptEvent`, `EnemyDeath`, `DamageTakenEvent` |
| `src/wowperf/domain/season.py` | `SeasonData`, `Defensives` — pure value objects, no file access |
| `src/wowperf/domain/analysis/timeline.py` | §5.1 time decomposition |
| `src/wowperf/domain/analysis/deaths.py` | §5.2 deaths and their cost |
| `src/wowperf/domain/analysis/interrupts.py` | §5.3 missed interrupts |
| `src/wowperf/domain/analysis/trash.py` | §5.4 trash efficiency |
| `src/wowperf/domain/analysis/players.py` | §5.5 per-player, in combat only |
| `src/wowperf/domain/analysis/defensives.py` | §5.6 explicitly inferred |
| `src/wowperf/domain/analysis/service.py` | Runs every analyser, ranks the result |
| `src/wowperf/adapters/config/toml.py` | Reads the two TOML files into the domain value objects |
| `src/wowperf/adapters/wcl/queries.py` | *Modified.* Adds four queries |
| `src/wowperf/adapters/wcl/ingest.py` | *Modified.* Adds four builders |
| `src/wowperf/adapters/wcl/repository.py` | *Modified.* `LoadedRun` widens; `load` fetches the new streams |
| `src/wowperf/cli.py` | *Modified.* Adds the `analyze` command |

---

### Task 1: Season data, read from TOML

**Files:**
- Create: `data/season.toml`, `src/wowperf/domain/season.py`, `src/wowperf/adapters/config/__init__.py`, `src/wowperf/adapters/config/toml.py`
- Test: `tests/domain/test_season.py`, `tests/adapters/config/test_toml.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces:
  - `class SeasonData(Frozen)`: `death_penalty_seconds: float`, `death_penalty_seconds_high_key: float`, `high_key_threshold: int`; method `def death_penalty(self, keystone_level: int) -> float`
  - `def load_season_data(path: Path) -> SeasonData` in `adapters/config/toml.py`
  - `DEFAULT_SEASON_PATH: Path` pointing at `data/season.toml`

The split matters: `SeasonData` is a pure value object in the domain and knows nothing about files; `load_season_data` is the adapter that reads one. The domain layer must not import `tomllib`.

- [ ] **Step 1: Write the season data file**

`data/season.toml`:

```toml
# Constants Blizzard retunes between seasons and the API does not expose.
# Every value carries the date it was last verified against a live source.

[death_penalty]
# Seconds added to the keystone timer per death.
seconds = 5.0
verified = "2026-09-03"

# At keystone 12 and above the penalty rises.
seconds_high_key = 15.0
high_key_threshold = 12
verified_high_key = "2026-09-03"
```

- [ ] **Step 2: Write the failing domain test**

```bash
mkdir -p src/wowperf/domain/analysis src/wowperf/adapters/config tests/adapters/config
touch src/wowperf/adapters/config/__init__.py tests/adapters/config/__init__.py
```

`tests/domain/test_season.py`:

```python
# ABOUTME: Behaviour tests for the season constants the timer arithmetic depends on.
# ABOUTME: The threshold is a boundary, so both sides of it are pinned here.

from wowperf.domain.season import SeasonData


def a_season() -> SeasonData:
    return SeasonData(
        death_penalty_seconds=5.0,
        death_penalty_seconds_high_key=15.0,
        high_key_threshold=12,
    )


def test_a_low_key_uses_the_base_death_penalty() -> None:
    assert a_season().death_penalty(11) == 5.0


def test_the_threshold_itself_uses_the_high_penalty() -> None:
    assert a_season().death_penalty(12) == 15.0


def test_above_the_threshold_uses_the_high_penalty() -> None:
    assert a_season().death_penalty(20) == 15.0
```

- [ ] **Step 3: Run it and watch it fail**

Run: `uv run pytest tests/domain/test_season.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.season'`.

- [ ] **Step 4: Implement the value object**

`src/wowperf/domain/season.py`:

```python
# ABOUTME: Season constants the API does not expose, as a pure value object.
# ABOUTME: Reading them off disk is an adapter's job; this file performs no I/O.

from wowperf.domain.base import Frozen


class SeasonData(Frozen):
    """Timer constants Blizzard retunes between seasons."""

    death_penalty_seconds: float
    death_penalty_seconds_high_key: float
    high_key_threshold: int

    def death_penalty(self, keystone_level: int) -> float:
        """Seconds a single death adds to the keystone timer at this level."""
        if keystone_level >= self.high_key_threshold:
            return self.death_penalty_seconds_high_key
        return self.death_penalty_seconds
```

- [ ] **Step 5: Run it and watch it pass**

Run: `uv run pytest tests/domain/test_season.py -v`
Expected: 3 passed.

- [ ] **Step 6: Write the failing adapter test**

`tests/adapters/config/test_toml.py`:

```python
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
```

- [ ] **Step 7: Run it and watch it fail**

Run: `uv run pytest tests/adapters/config/test_toml.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.adapters.config.toml'`.

- [ ] **Step 8: Implement the loader**

`src/wowperf/adapters/config/toml.py`:

```python
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
```

`DATA_DIR` resolves from this file's location: `src/wowperf/adapters/config/toml.py` → `parents[3]` is `src/`, whose parent is the repository root. If `test_the_committed_season_file_parses` fails with a path error, that arithmetic is what is wrong.

- [ ] **Step 9: Run the gate**

Run: `uv run pytest -v && uv run ruff check . && uv run mypy`
Expected: all green, no warnings.

- [ ] **Step 10: Commit**

```bash
git add data/season.toml src/wowperf/domain/season.py src/wowperf/adapters/config \
        tests/domain/test_season.py tests/adapters/config
git commit -m "Read the season timer constants from data, not code

Blizzard retunes the death penalty between seasons and the API does not
expose it, so it lives in a dated data file rather than a constant someone
has to remember to find."
```

---

### Task 2: The four new event types

**Files:**
- Modify: `src/wowperf/domain/events.py`
- Test: `tests/domain/test_events.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces, all inheriting `Frozen`:
  - `class EnemyCastRow`: `source_id: int`, `source_instance: int`, `ability_id: int`, `ability_name: str`, `timestamp_ms: int`, `is_start: bool`, `pull_index: int | None`
  - `class EnemyCast`: `source_id: int`, `source_instance: int`, `ability_id: int`, `ability_name: str`, `started_ms: int`, `completed_ms: int | None`, `interrupted_by: str | None`, `pull_index: int | None`
  - `class InterruptEvent`: `player_name: str`, `actor_id: int`, `interrupted_ability_id: int`, `target_id: int`, `target_instance: int`, `timestamp_ms: int`, `pull_index: int | None`
  - `class EnemyDeath`: `game_id: int`, `actor_id: int`, `timestamp_ms: int`, `forces: int`, `pull_index: int | None`
  - `class DamageTakenEvent`: `actor_id: int`, `ability_id: int`, `ability_name: str`, `amount: int`, `timestamp_ms: int`, `pull_index: int | None`

`EnemyCastRow` is one raw enemy cast event, translated out of Warcraft Logs vocabulary but not yet resolved: `is_start` distinguishes a `begincast` from a `cast`. `EnemyCast` is the reconstructed shape §5.3 needs: one per cast start, with its outcome. `completed_ms` set means the cast landed; `interrupted_by` set means a player kicked it; both `None` means the log does not say and the cast is excluded from the analysis.

The split exists so the reconstruction stays a pure, tested domain function rather than logic buried in the adapter. The adapter's job is translation; deciding what a cast's outcome was is analysis.

```python
class EnemyCastRow(Frozen):
    """One raw enemy cast event, translated but not yet resolved."""

    source_id: int
    source_instance: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    is_start: bool
    pull_index: int | None = None
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_events.py`:

```python
def test_an_enemy_cast_that_landed_records_when() -> None:
    cast = EnemyCast(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        started_ms=1000,
        completed_ms=2500,
    )
    assert cast.landed is True
    assert cast.was_kicked is False
    assert cast.outcome_known is True


def test_an_enemy_cast_that_was_kicked_names_the_interrupter() -> None:
    cast = EnemyCast(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        started_ms=1000,
        interrupted_by="Uglymage",
    )
    assert cast.was_kicked is True
    assert cast.landed is False
    assert cast.outcome_known is True


def test_an_enemy_cast_with_no_resolution_is_excluded() -> None:
    cast = EnemyCast(
        source_id=699,
        source_instance=0,
        ability_id=1238440,
        ability_name="Molten Scar",
        started_ms=1000,
    )
    assert cast.outcome_known is False
    assert cast.landed is False
    assert cast.was_kicked is False
```

Add the import at the top of the file: `from wowperf.domain.events import CastEvent, Death, EnemyCast`.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/domain/test_events.py -v`
Expected: FAIL, `ImportError: cannot import name 'EnemyCast'`.

- [ ] **Step 3: Add the four types**

Append to `src/wowperf/domain/events.py`:

```python
class EnemyCast(Frozen):
    """One enemy cast start, resolved to an outcome.

    Three states, mutually exclusive: the cast landed, a player kicked it, or
    the log does not say. The third is real — the caster may have died, been
    crowd-controlled, or cancelled — and those casts are excluded from the
    interrupt analysis rather than counted as misses.
    """

    source_id: int
    source_instance: int
    ability_id: int
    ability_name: str
    started_ms: int
    completed_ms: int | None = None
    interrupted_by: str | None = None
    pull_index: int | None = None

    @property
    def landed(self) -> bool:
        return self.completed_ms is not None and self.interrupted_by is None

    @property
    def was_kicked(self) -> bool:
        return self.interrupted_by is not None

    @property
    def outcome_known(self) -> bool:
        return self.landed or self.was_kicked


class InterruptEvent(Frozen):
    player_name: str
    actor_id: int
    interrupted_ability_id: int
    target_id: int
    target_instance: int
    timestamp_ms: int
    pull_index: int | None = None


class EnemyDeath(Frozen):
    """An enemy kill and the enemy forces it awarded."""

    game_id: int
    actor_id: int
    timestamp_ms: int
    forces: int
    pull_index: int | None = None


class DamageTakenEvent(Frozen):
    """One hit on a player. `amount` is the unmitigated figure.

    A Warcraft Logs damage event's `amount` excludes what was absorbed, so a
    fully absorbed hit reads zero. `unmitigatedAmount` is the honest answer to
    "how hard did this hit", which is what the per-ability comparison asks.
    """

    actor_id: int
    ability_id: int
    ability_name: str
    amount: int
    timestamp_ms: int
    pull_index: int | None = None
```

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/domain/test_events.py -v`
Expected: all passing, including the three pre-existing tests.

- [ ] **Step 5: Run the gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/events.py tests/domain/test_events.py
git commit -m "Add the event types the analysers read

An enemy cast carries its resolved outcome rather than the raw log rows,
because a cast whose outcome the log does not record must be excluded from
the interrupt count rather than counted as a miss."
```

---

### Task 3: Queries and builders for the four new streams

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/ingest.py`
- Test: `tests/adapters/wcl/test_ingest_streams.py`

**Interfaces:**
- Consumes: `Run`, `pull_index_at`, `_ability_name` from Plan A's `ingest.py`; the event types from Task 2.
- Produces:
  - `queries.ENEMY_CASTS_QUERY`, `queries.INTERRUPTS_QUERY`, `queries.ENEMY_DEATHS_QUERY`, `queries.DAMAGE_TAKEN_QUERY`, `queries.NPC_ACTORS_QUERY`
  - `def build_enemy_cast_rows(events, run, ability_names) -> tuple[EnemyCastRow, ...]`
  - `def build_interrupts(events, run, players) -> tuple[InterruptEvent, ...]`
  - `def build_enemy_deaths(events, run, npc_game_ids, npc_count_map) -> tuple[EnemyDeath, ...]`
  - `def build_damage_taken(events, run, ability_names) -> tuple[DamageTakenEvent, ...]`

  All four take `events: list[dict[str, Any]]` and `run: Run`. `players` is `dict[int, str]` mapping actor id to name; `npc_game_ids` is `dict[int, int]` mapping report actor id to NPC game id; `npc_count_map` is `dict[int, int]` mapping game id to forces.

**Field names are fixed.** Use exactly the ones in this plan's "Verified event shapes" table. Do not consult the design's §5.3 prose for field names — it uses combat-log names that do not exist in the API.

- [ ] **Step 1: Add the queries**

Append to `src/wowperf/adapters/wcl/queries.py`. Note every one carries `allowUnlisted: true`, matching the queries already there.

```python
ENEMY_CASTS_QUERY = """
query EnemyCasts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Casts
        hostilityType: Enemies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

INTERRUPTS_QUERY = """
query Interrupts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Interrupts
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

ENEMY_DEATHS_QUERY = """
query EnemyDeaths($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Deaths
        hostilityType: Enemies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

DAMAGE_TAKEN_QUERY = """
query DamageTaken($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: DamageTaken
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

NPC_ACTORS_QUERY = """
query NpcActors($code: String!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      masterData(translate: true) {
        actors(type: "NPC") { id gameID }
      }
    }
  }
}
"""
```

- [ ] **Step 2: Write the failing tests**

`tests/adapters/wcl/test_ingest_streams.py`:

```python
# ABOUTME: Integration tests turning the four new event payloads into domain events.
# ABOUTME: Payload shapes are copied from real API responses, not imagined.

from typing import Any

from wowperf.adapters.wcl.ingest import (
    build_damage_taken,
    build_enemy_cast_rows,
    build_enemy_deaths,
    build_interrupts,
)
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

ABILITY_NAMES = {1238440: "Molten Scar", 1241214: "Searing Wave", 47528: "Kick"}
PLAYERS = {693: "Uglymage"}


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=1000, end_ms=5000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=699, game_id=241874),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=9000,
             end_ms=20000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=702, game_id=244889),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(9, 10, 147), keystone_time_ms=1_909_000,
        keystone_bonus=1, count_reached=744, count_required=729,
        npc_counts=((241874, 5), (244889, 35)),
        players=(Player(actor_id=693, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


def test_a_begincast_and_a_cast_become_two_rows_flagged_differently() -> None:
    events: list[dict[str, Any]] = [
        {"type": "begincast", "abilityGameID": 1238440, "sourceID": 699, "timestamp": 2000},
        {"type": "cast", "abilityGameID": 1238440, "sourceID": 699, "timestamp": 3500},
    ]
    rows = build_enemy_cast_rows(events, a_run(), ABILITY_NAMES)
    assert [row.is_start for row in rows] == [True, False]
    assert rows[0].ability_name == "Molten Scar"
    assert rows[0].pull_index == 0


def test_a_missing_source_instance_reads_as_zero() -> None:
    events: list[dict[str, Any]] = [
        {"type": "begincast", "abilityGameID": 1238440, "sourceID": 699, "timestamp": 2000},
        {"type": "begincast", "abilityGameID": 1238440, "sourceID": 699,
         "sourceInstance": 3, "timestamp": 2100},
    ]
    rows = build_enemy_cast_rows(events, a_run(), ABILITY_NAMES)
    assert [row.source_instance for row in rows] == [0, 3]


def test_only_interrupt_rows_become_interrupts() -> None:
    events: list[dict[str, Any]] = [
        {"type": "applydebuff", "abilityGameID": 118, "sourceID": 693, "targetID": 699,
         "timestamp": 2000},
        {"type": "interrupt", "abilityGameID": 47528, "extraAbilityGameID": 1241214,
         "sourceID": 693, "targetID": 702, "targetInstance": 1, "timestamp": 12000},
    ]
    interrupts = build_interrupts(events, a_run(), PLAYERS)
    assert len(interrupts) == 1
    assert interrupts[0].player_name == "Uglymage"
    assert interrupts[0].interrupted_ability_id == 1241214
    assert interrupts[0].target_instance == 1
    assert interrupts[0].pull_index == 1


def test_an_enemy_death_carries_the_forces_its_kill_awarded() -> None:
    events: list[dict[str, Any]] = [
        {"type": "death", "targetID": 699, "timestamp": 4000},
        {"type": "death", "targetID": 702, "timestamp": 15000},
    ]
    deaths = build_enemy_deaths(
        events, a_run(), {699: 241874, 702: 244889}, {241874: 5, 244889: 35}
    )
    assert [death.forces for death in deaths] == [5, 35]
    assert [death.pull_index for death in deaths] == [0, 1]


def test_an_enemy_with_no_forces_entry_counts_zero() -> None:
    events: list[dict[str, Any]] = [{"type": "death", "targetID": 999, "timestamp": 4000}]
    deaths = build_enemy_deaths(events, a_run(), {999: 555}, {241874: 5})
    assert deaths[0].forces == 0


def test_damage_taken_uses_the_unmitigated_amount() -> None:
    events: list[dict[str, Any]] = [
        {"type": "damage", "abilityGameID": 1238440, "targetID": 693, "amount": 0,
         "absorbed": 123570, "unmitigatedAmount": 132788, "timestamp": 2500},
    ]
    taken = build_damage_taken(events, a_run(), ABILITY_NAMES)
    assert taken[0].amount == 132788
    assert taken[0].ability_name == "Molten Scar"
    assert taken[0].actor_id == 693


def test_damage_taken_falls_back_to_amount_when_unmitigated_is_absent() -> None:
    events: list[dict[str, Any]] = [
        {"type": "damage", "abilityGameID": 1238440, "targetID": 693, "amount": 900,
         "timestamp": 2500},
    ]
    assert build_damage_taken(events, a_run(), ABILITY_NAMES)[0].amount == 900
```

- [ ] **Step 3: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest_streams.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_enemy_cast_rows'`.

- [ ] **Step 4: Implement the four builders**

Append to `src/wowperf/adapters/wcl/ingest.py`, and extend its import of `wowperf.domain.events` to cover the new types.

```python
def build_enemy_cast_rows(
    events: list[dict[str, Any]],
    run: Run,
    ability_names: dict[int, str],
) -> tuple[EnemyCastRow, ...]:
    """Translate raw enemy cast events; resolving their outcome is the analyser's job."""
    rows = []
    for event in events:
        kind = event.get("type")
        if kind not in ("begincast", "cast"):
            continue
        ability_id = event["abilityGameID"]
        rows.append(
            EnemyCastRow(
                source_id=event["sourceID"],
                source_instance=event.get("sourceInstance") or 0,
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                timestamp_ms=event["timestamp"],
                is_start=kind == "begincast",
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(rows)


def build_interrupts(
    events: list[dict[str, Any]],
    run: Run,
    players: dict[int, str],
) -> tuple[InterruptEvent, ...]:
    """Keep only real interrupts; the stream also carries debuff applications."""
    interrupts = []
    for event in events:
        if event.get("type") != "interrupt":
            continue
        actor_id = event["sourceID"]
        interrupts.append(
            InterruptEvent(
                player_name=players.get(actor_id, f"Actor {actor_id}"),
                actor_id=actor_id,
                interrupted_ability_id=event["extraAbilityGameID"],
                target_id=event["targetID"],
                target_instance=event.get("targetInstance") or 0,
                timestamp_ms=event["timestamp"],
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(interrupts)


def build_enemy_deaths(
    events: list[dict[str, Any]],
    run: Run,
    npc_game_ids: dict[int, int],
    npc_count_map: dict[int, int],
) -> tuple[EnemyDeath, ...]:
    """Attach the enemy-forces value each kill awarded.

    An enemy absent from npcCountMap awards nothing; that is normal for bosses
    and for mobs that do not count, so it is zero rather than an error.
    """
    deaths = []
    for event in events:
        if event.get("type") != "death":
            continue
        actor_id = event["targetID"]
        game_id = npc_game_ids.get(actor_id, 0)
        deaths.append(
            EnemyDeath(
                game_id=game_id,
                actor_id=actor_id,
                timestamp_ms=event["timestamp"],
                forces=npc_count_map.get(game_id, 0),
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(deaths)


def build_damage_taken(
    events: list[dict[str, Any]],
    run: Run,
    ability_names: dict[int, str],
) -> tuple[DamageTakenEvent, ...]:
    """Record the unmitigated figure: `amount` alone reads zero on an absorbed hit."""
    taken = []
    for event in events:
        if event.get("type") != "damage":
            continue
        ability_id = event["abilityGameID"]
        amount = event.get("unmitigatedAmount")
        if amount is None:
            amount = event.get("amount") or 0
        taken.append(
            DamageTakenEvent(
                actor_id=event["targetID"],
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                amount=int(amount),
                timestamp_ms=event["timestamp"],
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(taken)
```

- [ ] **Step 5: Run them and watch them pass**

Run: `uv run pytest tests/adapters/wcl/test_ingest_streams.py -v`
Expected: 7 passed.

- [ ] **Step 6: Run the gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/adapters/wcl/queries.py src/wowperf/adapters/wcl/ingest.py \
        tests/adapters/wcl/test_ingest_streams.py
git commit -m "Fetch and translate the four streams the analysers need

Enemy casts, interrupts, enemy deaths and damage taken. Damage records the
unmitigated figure because a fully absorbed hit reports an amount of zero,
which would read as a hit that never landed."
```

---

### Task 4: Widen the loaded run

**Files:**
- Modify: `src/wowperf/domain/model.py`, `src/wowperf/adapters/wcl/repository.py`
- Test: `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Consumes: everything from Task 3.
- Produces: `LoadedRun` **moves out of `repository.py` into `src/wowperf/domain/model.py`** as a frozen model, and gains four fields:

```python
class LoadedRun(Frozen):
    """Everything fetched about one run. Pure data — no adapter may leak into it."""

    run: Run
    casts: tuple[CastEvent, ...] = ()
    deaths: tuple[Death, ...] = ()
    enemy_cast_rows: tuple[EnemyCastRow, ...] = ()
    interrupts: tuple[InterruptEvent, ...] = ()
    enemy_deaths: tuple[EnemyDeath, ...] = ()
    damage_taken: tuple[DamageTakenEvent, ...] = ()
```

`repository.py` imports it from the domain instead of defining it. The move is what lets Task 11's analysis service take one argument instead of seven, and it is legitimate: `LoadedRun` is pure data and always was.

`model.py` will need to import the event types from `wowperf.domain.events`. That is a domain-internal import and breaks no invariant.

`get` must keep fetching only the fights query — Plan A made it cheap on purpose, and widening `load` must not widen `get`.

- [ ] **Step 1: Write the failing test**

Append to `tests/adapters/wcl/test_repository.py`, reusing the existing operation-name-recording transport helper in that file:

```python
def test_load_fetches_every_stream_and_get_still_fetches_one() -> None:
    calls: list[str] = []
    repository = recording_repository(calls)

    repository.load("abc123", 36)
    assert sorted(set(calls)) == [
        "Abilities", "Casts", "DamageTaken", "Deaths",
        "EnemyCasts", "EnemyDeaths", "Fights", "Interrupts", "NpcActors",
    ]

    calls.clear()
    repository.get("abc123", 36)
    assert calls == ["Fights"]


def test_a_loaded_run_carries_every_stream() -> None:
    loaded = recording_repository([]).load("abc123", 36)
    assert loaded.run.keystone_level == 16
    for stream in (
        loaded.casts, loaded.deaths, loaded.enemy_cast_rows,
        loaded.interrupts, loaded.enemy_deaths, loaded.damage_taken,
    ):
        assert isinstance(stream, tuple)
```

The existing tests in this file already build a `MockTransport` that dispatches on the GraphQL operation name and returns a fixture payload. Extend that helper — named `recording_repository` after this task — to answer the five new operation names with small payloads shaped like the table at the top of this plan. Do not weaken any existing test in the file.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: FAIL — the new operations are not requested, and `LoadedRun` has no `interrupts`.

- [ ] **Step 3: Widen `LoadedRun` and `load`**

In `src/wowperf/adapters/wcl/repository.py`, give `LoadedRun` the four new attributes in its constructor, and extend `load` to fetch the new streams. The npc actor map comes from `NPC_ACTORS_QUERY` and goes through `_query` like everything else, so it is cached:

```python
    def _npc_game_ids(self, report_code: str) -> dict[int, int]:
        payload = self._query(NPC_ACTORS_QUERY, {"code": report_code})
        report = payload["reportData"]["report"]
        master = report.get("masterData") or {}
        actors = master.get("actors")
        if actors is None:
            raise WclError(f"Report {report_code} returned no masterData.actors block")
        return {actor["id"]: actor["gameID"] for actor in actors}
```

Every new stream goes through `fetch_all_events(self._query, ...)` with the same `event_variables` dict the existing casts and deaths fetches use, so pagination and caching are inherited rather than reimplemented.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: all passing.

- [ ] **Step 5: Run the gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/adapters/wcl/repository.py tests/adapters/wcl/test_repository.py
git commit -m "Carry every analysed stream on a loaded run

Widening load and not get keeps the cheap path cheap: a caller that only
wants the run's shape still pays one query."
```

---

### Task 5: Time decomposition (§5.1) — `measured`

**Files:**
- Create: `src/wowperf/domain/analysis/__init__.py`, `src/wowperf/domain/analysis/timeline.py`
- Test: `tests/domain/analysis/test_timeline.py`

**Interfaces:**
- Consumes: `Run`, `Pull` from `wowperf.domain.model`; `Death` from `wowperf.domain.events`; `SeasonData` from `wowperf.domain.season`; `Finding`, `Confidence` from `wowperf.domain.findings`.
- Produces:
  - `class Gap(Frozen)`: `after_pull_index: int`, `seconds: float`, `x: int`, `y: int`
  - `def gaps_between_pulls(run: Run) -> list[Gap]`
  - `def decompose_time(run: Run, deaths: tuple[Death, ...], season: SeasonData) -> list[Finding]`

The arithmetic: `keystone_time_seconds` minus the sum of pull durations minus `season.death_penalty(level) * len(deaths)` leaves a residual that is travel, run-backs and waiting. The residual is `measured` — every term in it is read from the log or from a dated constant.

`Gap.x` and `Gap.y` come from the pull that *follows* the gap: the coordinates say where the group arrived, which is where the reader should look.

- [ ] **Step 1: Write the failing tests**

```bash
mkdir -p tests/domain/analysis
touch src/wowperf/domain/analysis/__init__.py tests/domain/analysis/__init__.py
```

`tests/domain/analysis/test_timeline.py`:

```python
# ABOUTME: Behaviour tests for splitting a keystone time into pulls, deaths and travel.
# ABOUTME: The residual is the number a reader acts on, so its arithmetic is pinned exactly.

from wowperf.domain.analysis.timeline import decompose_time, gaps_between_pulls
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import SeasonData

SEASON = SeasonData(
    death_penalty_seconds=5.0,
    death_penalty_seconds_high_key=15.0,
    high_key_threshold=12,
)


def a_run(keystone_level: int = 16) -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Trash", encounter_id=0, start_ms=100_000,
             end_ms=160_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
        Pull(index=2, pull_id=3, name="Boss", encounter_id=99001, start_ms=170_000,
             end_ms=230_000, killed=True, x=50, y=60,
             enemies=(EnemyNpc(actor_id=3, game_id=300),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=keystone_level, affix_ids=(), keystone_time_ms=300_000,
        keystone_bonus=1, count_reached=744, count_required=729, npc_counts=(),
        players=(Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


def a_death(timestamp_ms: int) -> Death:
    return Death(player_name="Uglymage", actor_id=11, timestamp_ms=timestamp_ms,
                 killing_blow="Molten Scar")


def test_gaps_are_the_silence_between_consecutive_pulls() -> None:
    gaps = gaps_between_pulls(a_run())
    assert [(gap.after_pull_index, gap.seconds) for gap in gaps] == [(0, 40.0), (1, 10.0)]


def test_a_gap_carries_the_coordinates_of_the_pull_it_leads_to() -> None:
    worst = gaps_between_pulls(a_run())[0]
    assert (worst.x, worst.y) == (30, 40)


def test_a_run_with_one_pull_has_no_gaps() -> None:
    run = a_run()
    single = run.model_copy(update={"pulls": run.pulls[:1]})
    assert gaps_between_pulls(single) == []


def test_the_residual_is_keystone_time_less_pulls_and_death_penalties() -> None:
    # 300s keystone, 180s of pulls, two deaths at 15s each on a +16 -> 90s residual.
    findings = decompose_time(a_run(), (a_death(5_000), a_death(120_000)), SEASON)
    summary = next(f for f in findings if f.id == "time.residual")
    assert summary.seconds_lost == 90.0
    assert summary.confidence is Confidence.MEASURED


def test_a_low_key_uses_the_low_death_penalty() -> None:
    # 300s keystone, 180s of pulls, two deaths at 5s each on a +8 -> 110s residual.
    findings = decompose_time(a_run(keystone_level=8), (a_death(5_000), a_death(120_000)),
                              SEASON)
    summary = next(f for f in findings if f.id == "time.residual")
    assert summary.seconds_lost == 110.0


def test_the_worst_gap_is_reported_with_where_it_happened() -> None:
    findings = decompose_time(a_run(), (), SEASON)
    gap = next(f for f in findings if f.id == "time.gap.0")
    assert gap.seconds_lost == 40.0
    assert gap.pull_index == 1
    assert any("30" in item and "40" in item for item in gap.evidence)


def test_gaps_shorter_than_the_floor_are_not_reported() -> None:
    findings = decompose_time(a_run(), (), SEASON)
    # The 10s gap is below the 15s floor, so only the 40s gap earns a finding.
    assert [f.id for f in findings if f.id.startswith("time.gap.")] == ["time.gap.0"]


def test_every_finding_carries_a_confidence() -> None:
    findings = decompose_time(a_run(), (a_death(5_000),), SEASON)
    assert findings
    assert all(finding.confidence is Confidence.MEASURED for finding in findings)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_timeline.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.analysis.timeline'`.

- [ ] **Step 3: Implement it**

`src/wowperf/domain/analysis/timeline.py`:

```python
# ABOUTME: Splits a keystone time into pull time, death penalties and everything else.
# ABOUTME: The residual is travel, run-backs and hesitation, which is where routes improve.

from wowperf.domain.base import Frozen
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import SeasonData

GAP_FLOOR_SECONDS = 15.0
"""Below this a gap is a loading screen or a drink, not a routing problem."""

MAX_GAPS_REPORTED = 5


class Gap(Frozen):
    """Silence between two consecutive pulls, located on the map."""

    after_pull_index: int
    seconds: float
    x: int
    y: int


def gaps_between_pulls(run: Run) -> list[Gap]:
    """The stretches where nothing was being fought, worst first."""
    gaps = [
        Gap(
            after_pull_index=earlier.index,
            seconds=(later.start_ms - earlier.end_ms) / 1000,
            x=later.x,
            y=later.y,
        )
        for earlier, later in zip(run.pulls, run.pulls[1:], strict=False)
    ]
    return sorted(gaps, key=lambda gap: -gap.seconds)


def decompose_time(run: Run, deaths: tuple[Death, ...], season: SeasonData) -> list[Finding]:
    """Account for every second of the keystone timer."""
    penalty_each = season.death_penalty(run.keystone_level)
    penalty_total = penalty_each * len(deaths)
    residual = run.keystone_time_seconds - run.total_pull_seconds - penalty_total

    findings = [
        Finding(
            id="time.residual",
            title="Time spent outside pulls",
            detail=(
                f"{residual:.0f}s of the {run.keystone_time_seconds:.0f}s timer was neither "
                f"fighting nor the death penalty. That is travel, run-backs and waiting."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=residual,
            evidence=(
                f"keystone time {run.keystone_time_seconds:.0f}s",
                f"pull time {run.total_pull_seconds:.0f}s across {len(run.pulls)} pulls",
                f"{len(deaths)} deaths at {penalty_each:.0f}s = {penalty_total:.0f}s",
            ),
        )
    ]

    for rank, gap in enumerate(gaps_between_pulls(run)[:MAX_GAPS_REPORTED]):
        if gap.seconds < GAP_FLOOR_SECONDS:
            break
        findings.append(
            Finding(
                id=f"time.gap.{rank}",
                title=f"{gap.seconds:.0f}s between pulls {gap.after_pull_index} and "
                      f"{gap.after_pull_index + 1}",
                detail=(
                    f"The group fought nothing for {gap.seconds:.0f}s after pull "
                    f"{gap.after_pull_index}."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=gap.seconds,
                evidence=(f"next pull begins at map position x={gap.x}, y={gap.y}",),
                pull_index=gap.after_pull_index + 1,
            )
        )
    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_timeline.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis tests/domain/analysis
git commit -m "Account for every second of the keystone timer

A key is lost in the gaps between pulls more often than in the pulls, and
the residual is the only number that makes that visible."
```

---

### Task 6: Deaths and their cost (§5.2) — `measured`

**Files:**
- Create: `src/wowperf/domain/analysis/deaths.py`
- Test: `tests/domain/analysis/test_deaths.py`

**Interfaces:**
- Consumes: `Run`, `Death`, `Finding`, `Confidence`.
- Produces: `def analyse_deaths(run: Run, deaths: tuple[Death, ...]) -> list[Finding]`, and `CHAIN_WINDOW_MS: int = 10_000`.

Two facts the design asks for. First, the measured cost: the sum of `seconds_until_next_action`, which is the time players actually spent not playing — a bigger and more honest number than the timer penalty. Second, chains: deaths within `CHAIN_WINDOW_MS` of each other are reported as one event blamed on the first, because in a chain the first death usually causes the rest.

A death whose `seconds_until_next_action` is `None` — the player never acted again — contributes nothing to the total and says so. Do not substitute a default.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_deaths.py`:

```python
# ABOUTME: Behaviour tests for what deaths actually cost and which ones caused others.
# ABOUTME: A death with no measured cost must stay uncounted rather than get a default.

from wowperf.domain.analysis.deaths import analyse_deaths
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=744, count_required=729, npc_counts=(),
        players=(
            Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                   item_level=318),
            Player(actor_id=12, name="Sublime", class_name="Shaman", spec="Elemental",
                   item_level=311),
        ),
        pulls=pulls,
    )


def a_death(name: str, actor_id: int, at: int, cost: float | None) -> Death:
    return Death(player_name=name, actor_id=actor_id, timestamp_ms=at,
                 killing_blow="Molten Scar", pull_index=0,
                 seconds_until_next_action=cost)


def test_the_total_cost_is_the_measured_time_not_played() -> None:
    findings = analyse_deaths(
        a_run(),
        (a_death("Uglymage", 11, 1_000, 20.0), a_death("Sublime", 12, 40_000, 12.5)),
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost == 32.5
    assert total.confidence is Confidence.MEASURED


def test_a_death_with_no_measured_cost_is_excluded_and_said_so() -> None:
    findings = analyse_deaths(
        a_run(), (a_death("Uglymage", 11, 1_000, 20.0), a_death("Sublime", 12, 40_000, None))
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost == 20.0
    assert any("1 death" in item and "not measured" in item for item in total.evidence)


def test_no_deaths_produces_no_findings() -> None:
    assert analyse_deaths(a_run(), ()) == []


def test_deaths_close_together_are_reported_as_one_chain() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 30_000, 10.0),
            a_death("Sublime", 12, 33_000, 8.0),
        ),
    )
    chain = next(f for f in findings if f.id.startswith("deaths.chain."))
    assert chain.seconds_lost == 18.0
    assert "Uglymage" in chain.detail
    assert chain.confidence is Confidence.MEASURED


def test_deaths_far_apart_are_reported_separately() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 1_000, 10.0),
            a_death("Sublime", 12, 200_000, 8.0),
        ),
    )
    assert [f.id for f in findings if f.id.startswith("deaths.chain.")] == []
    assert len([f for f in findings if f.id.startswith("deaths.single.")]) == 2


def test_a_repeat_dier_is_named() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 1_000, 10.0),
            a_death("Uglymage", 11, 200_000, 8.0),
        ),
    )
    repeat = next(f for f in findings if f.id == "deaths.repeat.Uglymage")
    assert repeat.seconds_lost == 18.0
    assert "2" in repeat.detail
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_deaths.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement it**

`src/wowperf/domain/analysis/deaths.py`:

```python
# ABOUTME: What deaths cost in seconds actually not played, and which ones caused others.
# ABOUTME: The timer penalty understates a death; this measures the real thing instead.

from collections import Counter, defaultdict

from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

CHAIN_WINDOW_MS = 10_000
"""Deaths closer together than this are one event, not two independent ones."""


def _cost(deaths: tuple[Death, ...]) -> float:
    return sum(death.seconds_until_next_action or 0.0 for death in deaths)


def _chains(deaths: tuple[Death, ...]) -> list[tuple[Death, ...]]:
    """Group deaths into runs of deaths separated by less than the chain window."""
    ordered = sorted(deaths, key=lambda death: death.timestamp_ms)
    groups: list[list[Death]] = []
    for death in ordered:
        if groups and death.timestamp_ms - groups[-1][-1].timestamp_ms <= CHAIN_WINDOW_MS:
            groups[-1].append(death)
        else:
            groups.append([death])
    return [tuple(group) for group in groups]


def analyse_deaths(run: Run, deaths: tuple[Death, ...]) -> list[Finding]:
    """Report what dying cost, grouped so a wipe reads as one event."""
    if not deaths:
        return []

    unmeasured = [death for death in deaths if death.seconds_until_next_action is None]
    evidence = [f"{len(deaths)} deaths across {len(run.pulls)} pulls"]
    if unmeasured:
        evidence.append(
            f"{len(unmeasured)} death{'s' if len(unmeasured) > 1 else ''} not measured: "
            "the player never acted again"
        )

    findings = [
        Finding(
            id="deaths.total",
            title=f"{len(deaths)} deaths cost {_cost(deaths):.0f}s of play",
            detail=(
                "Measured from each death to that player's next cast, which is longer than "
                "the timer penalty and is the time the group actually lost."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=_cost(deaths),
            evidence=tuple(evidence),
        )
    ]

    chain_rank = single_rank = 0
    for group in _chains(deaths):
        first = group[0]
        if len(group) > 1:
            names = ", ".join(death.player_name for death in group[1:])
            findings.append(
                Finding(
                    id=f"deaths.chain.{chain_rank}",
                    title=f"{len(group)} deaths within {CHAIN_WINDOW_MS // 1000}s",
                    detail=(
                        f"{first.player_name} died first, to {first.killing_blow}, then "
                        f"{names}. In a chain the first death usually causes the rest."
                    ),
                    confidence=Confidence.MEASURED,
                    seconds_lost=_cost(group),
                    evidence=tuple(
                        f"{death.player_name} at {death.timestamp_ms}ms to "
                        f"{death.killing_blow}"
                        for death in group
                    ),
                    pull_index=first.pull_index,
                )
            )
            chain_rank += 1
        else:
            findings.append(
                Finding(
                    id=f"deaths.single.{single_rank}",
                    title=f"{first.player_name} died to {first.killing_blow}",
                    detail=f"Cost {_cost(group):.0f}s of play.",
                    confidence=Confidence.MEASURED,
                    seconds_lost=_cost(group),
                    evidence=(f"pull {first.pull_index}, at {first.timestamp_ms}ms",),
                    pull_index=first.pull_index,
                )
            )
            single_rank += 1

    counts = Counter(death.player_name for death in deaths)
    by_player: dict[str, list[Death]] = defaultdict(list)
    for death in deaths:
        by_player[death.player_name].append(death)
    for name, count in counts.items():
        if count < 2:
            continue
        theirs = tuple(by_player[name])
        findings.append(
            Finding(
                id=f"deaths.repeat.{name}",
                title=f"{name} died {count} times",
                detail=f"{count} of the run's {len(deaths)} deaths were {name}.",
                confidence=Confidence.MEASURED,
                seconds_lost=_cost(theirs),
                evidence=tuple(
                    f"{death.killing_blow} at {death.timestamp_ms}ms" for death in theirs
                ),
            )
        )
    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_deaths.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/deaths.py tests/domain/analysis/test_deaths.py
git commit -m "Measure what deaths cost and group the ones that cascaded

Reporting five deaths in a wipe as five independent findings buries the one
thing worth fixing, which is whatever killed the first player."
```

---

### Task 7: Missed interrupts (§5.3) — `derived`

**Files:**
- Create: `src/wowperf/domain/analysis/interrupts.py`
- Test: `tests/domain/analysis/test_interrupts.py`

**Interfaces:**
- Consumes: `EnemyCastRow`, `EnemyCast`, `InterruptEvent`, `DamageTakenEvent`, `Finding`, `Confidence`.
- Produces:
  - `def reconstruct_enemy_casts(rows: tuple[EnemyCastRow, ...], interrupts: tuple[InterruptEvent, ...]) -> tuple[EnemyCast, ...]`
  - `def analyse_interrupts(casts: tuple[EnemyCast, ...], damage_taken: tuple[DamageTakenEvent, ...]) -> list[Finding]`
  - `FOLLOW_WINDOW_MS: int = 3_000`, `MAX_ABILITIES_REPORTED: int = 5`

**This is the task where naive implementations produce garbage.** Three rules, all load-bearing:

1. **Identity is `(source_id, source_instance, ability_id)`, never `source_id` alone.** Two copies of the same NPC cast the same spell; pairing across them invents kicks that never happened. A missing `sourceInstance` means instance `0` — Task 3 already normalised that.
2. **A cast start with neither a completion nor a kick is EXCLUDED, not missed.** The caster may have died, been crowd-controlled, or cancelled. Counting those as misses is the specific failure mode the design calls out.
3. **A completion with no preceding start is ignored.** That is an instant cast, which could not have been interrupted.

The resolution window for one start ends at the next start with the same identity, so a completion never pairs with a cast two casts later.

Findings are `derived`: the outcomes are reconstructed by a documented rule, not read off the log. `seconds_lost` is `None` — a missed kick has no honest conversion into seconds, and where it caused a death, Task 6 has already counted those seconds. Inventing a figure here would double-count.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_interrupts.py`:

```python
# ABOUTME: Behaviour tests for reconstructing which enemy casts were kicked and which landed.
# ABOUTME: The excluded case is the one naive implementations get wrong, so it is pinned hard.

from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.events import DamageTakenEvent, EnemyCastRow, InterruptEvent
from wowperf.domain.findings import Confidence

SPELL = 1241214
OTHER = 1238440


def row(at: int, is_start: bool, instance: int = 0, ability: int = SPELL) -> EnemyCastRow:
    return EnemyCastRow(source_id=699, source_instance=instance, ability_id=ability,
                        ability_name="Searing Wave", timestamp_ms=at, is_start=is_start,
                        pull_index=0)


def kick(at: int, instance: int = 0, ability: int = SPELL) -> InterruptEvent:
    return InterruptEvent(player_name="Uglymage", actor_id=693,
                          interrupted_ability_id=ability, target_id=699,
                          target_instance=instance, timestamp_ms=at, pull_index=0)


def hit(at: int, amount: int, ability: int = SPELL) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=693, ability_id=ability, ability_name="Searing Wave",
                            amount=amount, timestamp_ms=at, pull_index=0)


def test_a_start_followed_by_a_completion_landed() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(2500, False)), ())
    assert len(casts) == 1
    assert casts[0].landed is True
    assert casts[0].completed_ms == 2500


def test_a_start_followed_by_a_kick_was_interrupted() -> None:
    casts = reconstruct_enemy_casts((row(1000, True),), (kick(1800),))
    assert casts[0].was_kicked is True
    assert casts[0].interrupted_by == "Uglymage"
    assert casts[0].landed is False


def test_a_start_with_no_resolution_is_excluded_not_missed() -> None:
    casts = reconstruct_enemy_casts((row(1000, True),), ())
    assert casts[0].outcome_known is False
    assert casts[0].landed is False


def test_a_kick_on_a_different_instance_does_not_resolve_this_cast() -> None:
    casts = reconstruct_enemy_casts((row(1000, True, instance=0),), (kick(1800, instance=4),))
    assert casts[0].outcome_known is False


def test_a_completion_by_a_different_instance_does_not_resolve_this_cast() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True, instance=0), row(2500, False, instance=4)), ()
    )
    resolved = [cast for cast in casts if cast.source_instance == 0]
    assert resolved[0].outcome_known is False


def test_a_kick_on_a_different_spell_does_not_resolve_this_cast() -> None:
    casts = reconstruct_enemy_casts((row(1000, True),), (kick(1800, ability=OTHER),))
    assert casts[0].outcome_known is False


def test_a_completion_after_the_next_start_belongs_to_the_next_cast() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True), row(5000, True), row(6000, False)), ()
    )
    by_start = {cast.started_ms: cast for cast in casts}
    assert by_start[1000].outcome_known is False
    assert by_start[5000].landed is True


def test_an_instant_cast_with_no_start_is_ignored() -> None:
    assert reconstruct_enemy_casts((row(2500, False),), ()) == ()


def test_the_earlier_of_a_kick_and_a_completion_wins() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(3000, False)), (kick(1800),))
    assert casts[0].was_kicked is True


def test_landed_casts_are_ranked_by_the_damage_that_followed() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True), row(2000, False), row(5000, True, ability=OTHER),
         row(6000, False, ability=OTHER)),
        (),
    )
    findings = analyse_interrupts(
        casts, (hit(2100, 50_000), hit(6100, 200_000, ability=OTHER))
    )
    ranked = [f for f in findings if f.id.startswith("interrupts.ability.")]
    assert ranked[0].evidence[0].startswith("200000") or "200000" in ranked[0].evidence[0]


def test_damage_outside_the_follow_window_is_not_attributed() -> None:
    casts = reconstruct_enemy_casts((row(1000, True), row(2000, False)), ())
    findings = analyse_interrupts(casts, (hit(99_000, 500_000),))
    ranked = [f for f in findings if f.id.startswith("interrupts.ability.")]
    assert ranked == []


def test_the_summary_counts_kicked_missed_and_excluded_separately() -> None:
    casts = reconstruct_enemy_casts(
        (row(1000, True), row(2000, False), row(5000, True), row(9000, True),
         row(9500, False)),
        (kick(5500),),
    )
    findings = analyse_interrupts(casts, ())
    summary = next(f for f in findings if f.id == "interrupts.summary")
    assert summary.confidence is Confidence.DERIVED
    assert summary.seconds_lost is None
    joined = " ".join(summary.evidence)
    assert "2 landed" in joined
    assert "1 kicked" in joined
    assert "0 excluded" in joined or "excluded" in joined


def test_no_casts_produces_no_findings() -> None:
    assert analyse_interrupts((), ()) == []
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_interrupts.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement it**

`src/wowperf/domain/analysis/interrupts.py`:

```python
# ABOUTME: Reconstructs which enemy casts were kicked, which landed, and which are unknowable.
# ABOUTME: The combat log carries no interruptible flag, so outcomes are derived, not read.

from collections import defaultdict

from wowperf.domain.events import (
    DamageTakenEvent,
    EnemyCast,
    EnemyCastRow,
    InterruptEvent,
)
from wowperf.domain.findings import Confidence, Finding

FOLLOW_WINDOW_MS = 3_000
"""Damage from a spell lands within a few seconds of the cast completing."""

MAX_ABILITIES_REPORTED = 5

Identity = tuple[int, int, int]


def reconstruct_enemy_casts(
    rows: tuple[EnemyCastRow, ...],
    interrupts: tuple[InterruptEvent, ...],
) -> tuple[EnemyCast, ...]:
    """Pair each cast start with its outcome, leaving unresolvable starts unresolved.

    Identity is (source, instance, ability). Two copies of one NPC casting the
    same spell are different casters, and pairing across them would invent
    kicks that never happened.
    """
    starts: dict[Identity, list[EnemyCastRow]] = defaultdict(list)
    completions: dict[Identity, list[int]] = defaultdict(list)
    for row in rows:
        identity = (row.source_id, row.source_instance, row.ability_id)
        if row.is_start:
            starts[identity].append(row)
        else:
            completions[identity].append(row.timestamp_ms)

    kicks: dict[Identity, list[InterruptEvent]] = defaultdict(list)
    for interrupt in interrupts:
        identity = (
            interrupt.target_id,
            interrupt.target_instance,
            interrupt.interrupted_ability_id,
        )
        kicks[identity].append(interrupt)

    resolved: list[EnemyCast] = []
    for identity, group in starts.items():
        group.sort(key=lambda row: row.timestamp_ms)
        landed_at = sorted(completions.get(identity, []))
        kicked_at = sorted(kicks.get(identity, []), key=lambda event: event.timestamp_ms)

        for position, start in enumerate(group):
            floor = start.timestamp_ms
            ceiling = (
                group[position + 1].timestamp_ms if position + 1 < len(group) else None
            )

            # Written as explicit comparisons rather than a closure: ruff's B023
            # rejects a function defined in a loop that captures the loop variable,
            # and it is right to — the bug it prevents is exactly the one that would
            # pair every start with the last iteration's window.
            completion = next(
                (
                    stamp
                    for stamp in landed_at
                    if floor <= stamp and (ceiling is None or stamp < ceiling)
                ),
                None,
            )
            kick = next(
                (
                    event
                    for event in kicked_at
                    if floor <= event.timestamp_ms
                    and (ceiling is None or event.timestamp_ms < ceiling)
                ),
                None,
            )

            if kick is not None and (completion is None or kick.timestamp_ms <= completion):
                resolved.append(
                    EnemyCast(
                        source_id=start.source_id,
                        source_instance=start.source_instance,
                        ability_id=start.ability_id,
                        ability_name=start.ability_name,
                        started_ms=start.timestamp_ms,
                        interrupted_by=kick.player_name,
                        pull_index=start.pull_index,
                    )
                )
            else:
                resolved.append(
                    EnemyCast(
                        source_id=start.source_id,
                        source_instance=start.source_instance,
                        ability_id=start.ability_id,
                        ability_name=start.ability_name,
                        started_ms=start.timestamp_ms,
                        completed_ms=completion,
                        pull_index=start.pull_index,
                    )
                )
    return tuple(sorted(resolved, key=lambda cast: cast.started_ms))


def _damage_after(cast: EnemyCast, damage_taken: tuple[DamageTakenEvent, ...]) -> int:
    if cast.completed_ms is None:
        return 0
    end = cast.completed_ms + FOLLOW_WINDOW_MS
    return sum(
        hit.amount
        for hit in damage_taken
        if hit.ability_id == cast.ability_id and cast.completed_ms <= hit.timestamp_ms < end
    )


def analyse_interrupts(
    casts: tuple[EnemyCast, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
) -> list[Finding]:
    """Rank the enemy casts that landed by the damage they actually did to this group.

    No curated must-kick list: what hurt this group is a fact, and what a
    spreadsheet nominates is an opinion.
    """
    if not casts:
        return []

    landed = [cast for cast in casts if cast.landed]
    kicked = [cast for cast in casts if cast.was_kicked]
    excluded = [cast for cast in casts if not cast.outcome_known]

    findings = [
        Finding(
            id="interrupts.summary",
            title=f"{len(landed)} interruptible casts landed, {len(kicked)} were kicked",
            detail=(
                "Outcomes are reconstructed: the log records no interruptible flag. Casts "
                "whose outcome the log does not resolve are excluded rather than counted "
                "as missed."
            ),
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"{len(landed)} landed",
                f"{len(kicked)} kicked",
                f"{len(excluded)} excluded: caster died, was crowd-controlled, or cancelled",
            ),
        )
    ]

    damage_by_ability: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    counts: dict[int, int] = defaultdict(int)
    for cast in landed:
        damage_by_ability[cast.ability_id] += _damage_after(cast, damage_taken)
        names[cast.ability_id] = cast.ability_name
        counts[cast.ability_id] += 1

    ranked = sorted(damage_by_ability.items(), key=lambda item: -item[1])
    for rank, (ability_id, damage) in enumerate(ranked[:MAX_ABILITIES_REPORTED]):
        if damage <= 0:
            break
        findings.append(
            Finding(
                id=f"interrupts.ability.{rank}",
                title=f"{names[ability_id]} landed {counts[ability_id]} times",
                detail=(
                    f"{names[ability_id]} was cast to completion {counts[ability_id]} times "
                    f"and did {damage} damage to the group within "
                    f"{FOLLOW_WINDOW_MS // 1000}s of each cast."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{damage} damage attributed",
                    f"ability {ability_id}",
                ),
            )
        )
    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_interrupts.py -v`
Expected: 13 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/interrupts.py tests/domain/analysis/test_interrupts.py
git commit -m "Reconstruct interrupt outcomes without guessing at the unknown

A cast whose outcome the log does not record is excluded rather than blamed
on the group, and enemy casts are ranked by the damage they did here rather
than against a curated list of spells someone else thought mattered."
```

---

### Task 8: Trash efficiency (§5.4) — `measured`

**Files:**
- Create: `src/wowperf/domain/analysis/trash.py`
- Test: `tests/domain/analysis/test_trash.py`

**Interfaces:**
- Consumes: `Run`, `EnemyDeath`, `Finding`, `Confidence`.
- Produces: `def analyse_trash(run: Run, enemy_deaths: tuple[EnemyDeath, ...]) -> list[Finding]`, and `OVERKILL_FLOOR_PERCENT: float = 2.0`.

Reaching 112% of required forces means roughly 12% of trash time bought nothing. That percentage is `measured` — `countReached` and `countRequired` are both read off the fight. Converting it into seconds is a **derived** estimate, so it uses the trash-pull time actually spent, and says which pulls contributed least per second.

Do not report an overage below `OVERKILL_FLOOR_PERCENT`: a couple of percent is a patrol that walked into the group, not a routing mistake.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_trash.py`:

```python
# ABOUTME: Behaviour tests for enemy-forces efficiency and the pulls that bought least.
# ABOUTME: The percentage is measured; turning it into seconds is derived and labelled so.

from wowperf.domain.analysis.trash import analyse_trash
from wowperf.domain.events import EnemyDeath
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run


def a_run(reached: int, required: int = 100) -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=30_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Trash", encounter_id=0, start_ms=40_000,
             end_ms=100_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
        Pull(index=2, pull_id=3, name="Boss", encounter_id=99001, start_ms=110_000,
             end_ms=140_000, killed=True, x=50, y=60,
             enemies=(EnemyNpc(actor_id=3, game_id=300),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=reached, count_required=required, npc_counts=(),
        players=(Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )


def kill(pull_index: int, forces: int, at: int) -> EnemyDeath:
    return EnemyDeath(game_id=100 + pull_index, actor_id=pull_index, timestamp_ms=at,
                      forces=forces, pull_index=pull_index)


def test_reaching_exactly_the_requirement_reports_no_overage() -> None:
    findings = analyse_trash(a_run(reached=100), (kill(0, 100, 10_000),))
    assert [f.id for f in findings if f.id == "trash.overage"] == []


def test_a_large_overage_is_reported_as_wasted_trash_time() -> None:
    findings = analyse_trash(
        a_run(reached=112), (kill(0, 40, 10_000), kill(1, 72, 50_000))
    )
    overage = next(f for f in findings if f.id == "trash.overage")
    assert overage.confidence is Confidence.DERIVED
    assert overage.seconds_lost is not None
    # 12% over, 90s of trash pull time -> about 9.6s bought nothing.
    assert 9.0 < overage.seconds_lost < 10.5
    assert any("112" in item for item in overage.evidence)


def test_an_overage_under_the_floor_is_not_reported() -> None:
    findings = analyse_trash(a_run(reached=101), (kill(0, 101, 10_000),))
    assert [f.id for f in findings if f.id == "trash.overage"] == []


def test_the_least_efficient_trash_pull_is_named() -> None:
    findings = analyse_trash(
        a_run(reached=112), (kill(0, 90, 10_000), kill(1, 22, 50_000))
    )
    # Pull 0 bought 90 forces in 30s; pull 1 bought 22 in 60s. Pull 1 is worse.
    worst = next(f for f in findings if f.id.startswith("trash.pull."))
    assert worst.pull_index == 1


def test_boss_pulls_are_not_judged_on_forces() -> None:
    findings = analyse_trash(a_run(reached=112), (kill(0, 112, 10_000),))
    assert all(f.pull_index != 2 for f in findings if f.pull_index is not None)


def test_a_run_with_no_enemy_deaths_still_reports_the_count() -> None:
    findings = analyse_trash(a_run(reached=112), ())
    assert any(f.id == "trash.overage" for f in findings)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_trash.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement it**

`src/wowperf/domain/analysis/trash.py`:

```python
# ABOUTME: How much trash was killed against how much was needed, and which packs paid worst.
# ABOUTME: The overage percentage is measured; its cost in seconds is a labelled estimate.

from collections import defaultdict

from wowperf.domain.events import EnemyDeath
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

OVERKILL_FLOOR_PERCENT = 2.0
"""Below this an overage is a wandering patrol, not a routing decision."""

MAX_PULLS_REPORTED = 3


def analyse_trash(run: Run, enemy_deaths: tuple[EnemyDeath, ...]) -> list[Finding]:
    """Report trash killed beyond the requirement, and the packs that bought least."""
    if run.count_required <= 0:
        return []

    percent = run.count_reached / run.count_required * 100
    overage_percent = percent - 100
    trash_seconds = sum(pull.duration_seconds for pull in run.trash_pulls)

    findings: list[Finding] = []
    if overage_percent >= OVERKILL_FLOOR_PERCENT:
        wasted = trash_seconds * (overage_percent / percent)
        findings.append(
            Finding(
                id="trash.overage",
                title=f"{overage_percent:.0f}% more trash than the key required",
                detail=(
                    f"The group killed {run.count_reached} of {run.count_required} required "
                    f"forces. Spread across {trash_seconds:.0f}s of trash pulls, the excess "
                    f"is worth roughly {wasted:.0f}s."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=wasted,
                evidence=(
                    f"{run.count_reached}/{run.count_required} forces = {percent:.0f}%",
                    f"{trash_seconds:.0f}s spent in {len(run.trash_pulls)} trash pulls",
                    "seconds are apportioned from the percentage, not measured directly",
                ),
            )
        )

    forces_by_pull: dict[int, int] = defaultdict(int)
    for death in enemy_deaths:
        if death.pull_index is not None:
            forces_by_pull[death.pull_index] += death.forces

    rates = [
        (pull.index, forces_by_pull.get(pull.index, 0) / pull.duration_seconds)
        for pull in run.trash_pulls
        if pull.duration_seconds > 0
    ]
    for rank, (pull_index, rate) in enumerate(sorted(rates, key=lambda item: item[1])):
        if rank >= MAX_PULLS_REPORTED:
            break
        pull = run.pulls[pull_index]
        findings.append(
            Finding(
                id=f"trash.pull.{rank}",
                title=f"Pull {pull_index} bought {rate:.1f} forces per second",
                detail=(
                    f"{forces_by_pull.get(pull_index, 0)} forces over "
                    f"{pull.duration_seconds:.0f}s."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(f"map position x={pull.x}, y={pull.y}",),
                pull_index=pull_index,
            )
        )
    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_trash.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/trash.py tests/domain/analysis/test_trash.py
git commit -m "Report trash killed past the requirement and the packs that paid worst

Overkilling forces is invisible in a timer that still made it, so the
percentage is stated plainly and its cost in seconds is labelled derived
rather than dressed up as a measurement."
```

---

### Task 9: Per-player, in combat only (§5.5) — `derived`

**Files:**
- Create: `src/wowperf/domain/analysis/players.py`
- Test: `tests/domain/analysis/test_players.py`

**Interfaces:**
- Consumes: `Run`, `Player`, `CastEvent`, `Death`, `InterruptEvent`, `DamageTakenEvent`, `Finding`, `Confidence`.
- Produces:
  - `class PlayerSummary(Frozen)`: `name: str`, `actor_id: int`, `class_name: str`, `spec: str`, `casts_in_pulls: int`, `active_seconds: float`, `activity_percent: float`, `interrupts: int`, `deaths: int`
  - `def summarise_players(run, casts, deaths, interrupts) -> tuple[PlayerSummary, ...]`
  - `def analyse_players(run, casts, deaths, interrupts, damage_taken) -> list[Finding]`
  - `MEDIAN_MULTIPLE: float = 2.0`, `MIN_PLAYERS_FOR_MEDIAN: int = 3`, `LOW_ACTIVITY_PERCENT: float = 60.0`

Three rules the design is emphatic about, and a reviewer will check:

1. **Only casts inside pull windows count.** Downtime between packs belongs to the route, not the player. A `CastEvent` with `pull_index is None` is outside every pull and is ignored.
2. **Damage taken is reported per ability against the group median for that same ability.** Never as "avoidable damage". The comparison states a fact; deciding whether a hit was avoidable needs per-mechanic knowledge this slice does not have.
3. **No damage ranking, no DPS, no parse.** If you find yourself computing throughput, stop.

The median is taken over players who took at least one hit of that ability, and fewer than `MIN_PLAYERS_FOR_MEDIAN` such players means no comparison is made — a median of two numbers is not a group baseline. The finding's evidence must say which definition was used, because the reader cannot otherwise tell.

Activity is cast-based on purpose. Warcraft Logs computes its own "Activity" from damage events, so damage-over-time ticks mask real downtime; ours counts casts and is therefore a different, stricter number.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_players.py`:

```python
# ABOUTME: Behaviour tests for per-player activity, interrupts and damage against the median.
# ABOUTME: Activity counts casts inside pulls only, so route downtime is not blamed on people.

from wowperf.domain.analysis.players import analyse_players, summarise_players
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

NAMES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo")


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=100_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=tuple(
            Player(actor_id=index, name=name, class_name="Mage", spec="Arcane",
                   item_level=318)
            for index, name in enumerate(NAMES)
        ),
        pulls=pulls,
    )


def cast(actor_id: int, at: int, pull_index: int | None = 0) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=1, ability_name="Frostbolt",
                     timestamp_ms=at, pull_index=pull_index)


def hit(actor_id: int, amount: int, ability: int = 500) -> DamageTakenEvent:
    return DamageTakenEvent(actor_id=actor_id, ability_id=ability,
                            ability_name="Molten Scar", amount=amount,
                            timestamp_ms=1_000, pull_index=0)


def test_casts_outside_every_pull_do_not_count_towards_activity() -> None:
    summaries = summarise_players(
        a_run(), (cast(0, 1_000), cast(0, 2_000, pull_index=None)), (), ()
    )
    alpha = next(s for s in summaries if s.name == "Alpha")
    assert alpha.casts_in_pulls == 1


def test_interrupts_and_deaths_are_counted_per_player() -> None:
    summaries = summarise_players(
        a_run(),
        (),
        (Death(player_name="Bravo", actor_id=1, timestamp_ms=5_000,
               killing_blow="Molten Scar"),),
        (InterruptEvent(player_name="Bravo", actor_id=1, interrupted_ability_id=9,
                        target_id=99, target_instance=0, timestamp_ms=6_000),),
    )
    bravo = next(s for s in summaries if s.name == "Bravo")
    assert (bravo.interrupts, bravo.deaths) == (1, 1)


def test_every_player_gets_a_summary_even_with_no_events() -> None:
    assert len(summarise_players(a_run(), (), (), ())) == 5


def test_taking_far_more_than_the_median_of_one_ability_is_a_finding() -> None:
    damage = (
        hit(0, 100_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000), hit(4, 10_000),
    )
    findings = analyse_players(a_run(), (), (), (), damage)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert "Alpha" in outlier.title
    assert outlier.confidence is Confidence.DERIVED
    assert outlier.seconds_lost is None


def test_the_median_definition_is_stated_in_the_evidence() -> None:
    damage = (
        hit(0, 100_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000), hit(4, 10_000),
    )
    findings = analyse_players(a_run(), (), (), (), damage)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert any("median" in item and "took at least one" in item for item in outlier.evidence)


def test_too_few_players_took_an_ability_for_a_median_to_mean_anything() -> None:
    findings = analyse_players(a_run(), (), (), (), (hit(0, 100_000), hit(1, 1_000)))
    assert [f for f in findings if f.id.startswith("players.damage.")] == []


def test_damage_within_the_normal_range_is_not_flagged() -> None:
    damage = (
        hit(0, 12_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000), hit(4, 11_000),
    )
    findings = analyse_players(a_run(), (), (), (), damage)
    assert [f for f in findings if f.id.startswith("players.damage.")] == []


def test_low_activity_inside_pulls_is_reported() -> None:
    # One cast in a 100s pull is far below the activity floor.
    findings = analyse_players(a_run(), (cast(0, 1_000),), (), (), ())
    assert any(f.id == "players.activity.Alpha" for f in findings)


def test_no_finding_claims_a_damage_ranking() -> None:
    damage = (hit(0, 100_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000))
    findings = analyse_players(a_run(), (cast(0, 1_000),), (), (), damage)
    joined = " ".join(f"{f.title} {f.detail}" for f in findings).lower()
    for forbidden in ("dps", "damage done", "parse", "percentile"):
        assert forbidden not in joined
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_players.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement it**

`src/wowperf/domain/analysis/players.py`:

```python
# ABOUTME: Per-player facts measured inside pull windows only, never a throughput ranking.
# ABOUTME: Damage taken is stated against the group median, never as "avoidable damage".

from collections import defaultdict
from statistics import median

from wowperf.domain.base import Frozen
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run

MEDIAN_MULTIPLE = 2.0
"""Taking this many times the group median of one ability is worth saying out loud."""

MIN_PLAYERS_FOR_MEDIAN = 3
"""Fewer than this and a median is not a group baseline."""

LOW_ACTIVITY_PERCENT = 60.0
MAX_OUTLIERS_REPORTED = 5


class PlayerSummary(Frozen):
    name: str
    actor_id: int
    class_name: str
    spec: str
    casts_in_pulls: int
    active_seconds: float
    activity_percent: float
    interrupts: int
    deaths: int


def summarise_players(
    run: Run,
    casts: tuple[CastEvent, ...],
    deaths: tuple[Death, ...],
    interrupts: tuple[InterruptEvent, ...],
) -> tuple[PlayerSummary, ...]:
    """One row per player, counting only what happened inside a pull."""
    in_pull_seconds = sum(pull.duration_seconds for pull in run.pulls)

    cast_counts: dict[int, int] = defaultdict(int)
    for cast in casts:
        if cast.pull_index is not None:
            cast_counts[cast.actor_id] += 1

    interrupt_counts: dict[int, int] = defaultdict(int)
    for interrupt in interrupts:
        interrupt_counts[interrupt.actor_id] += 1

    death_counts: dict[int, int] = defaultdict(int)
    for death in deaths:
        death_counts[death.actor_id] += 1

    summaries = []
    for player in run.players:
        count = cast_counts.get(player.actor_id, 0)
        # One global-cooldown-ish second per cast. Deliberately coarse: this is a
        # floor on time spent acting, not a simulation of the rotation.
        active = float(count)
        summaries.append(
            PlayerSummary(
                name=player.name,
                actor_id=player.actor_id,
                class_name=player.class_name,
                spec=player.spec,
                casts_in_pulls=count,
                active_seconds=active,
                activity_percent=(
                    active / in_pull_seconds * 100 if in_pull_seconds > 0 else 0.0
                ),
                interrupts=interrupt_counts.get(player.actor_id, 0),
                deaths=death_counts.get(player.actor_id, 0),
            )
        )
    return tuple(summaries)


def _damage_outliers(
    run: Run, damage_taken: tuple[DamageTakenEvent, ...]
) -> list[tuple[str, str, int, float]]:
    """(player name, ability name, amount, multiple of the median), worst first."""
    names = {player.actor_id: player.name for player in run.players}
    totals: dict[tuple[int, int], int] = defaultdict(int)
    ability_names: dict[int, str] = {}
    for hit in damage_taken:
        totals[(hit.ability_id, hit.actor_id)] += hit.amount
        ability_names[hit.ability_id] = hit.ability_name

    by_ability: dict[int, dict[int, int]] = defaultdict(dict)
    for (ability_id, actor_id), amount in totals.items():
        by_ability[ability_id][actor_id] = amount

    outliers = []
    for ability_id, per_player in by_ability.items():
        took = [amount for amount in per_player.values() if amount > 0]
        if len(took) < MIN_PLAYERS_FOR_MEDIAN:
            continue
        baseline = median(took)
        if baseline <= 0:
            continue
        for actor_id, amount in per_player.items():
            multiple = amount / baseline
            if multiple >= MEDIAN_MULTIPLE:
                outliers.append(
                    (
                        names.get(actor_id, f"Actor {actor_id}"),
                        ability_names[ability_id],
                        amount,
                        multiple,
                    )
                )
    return sorted(outliers, key=lambda row: -row[3])


def analyse_players(
    run: Run,
    casts: tuple[CastEvent, ...],
    deaths: tuple[Death, ...],
    interrupts: tuple[InterruptEvent, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
) -> list[Finding]:
    """Per-player facts, stated without ranking anyone's throughput."""
    findings: list[Finding] = []

    for summary in summarise_players(run, casts, deaths, interrupts):
        if summary.activity_percent >= LOW_ACTIVITY_PERCENT:
            continue
        findings.append(
            Finding(
                id=f"players.activity.{summary.name}",
                title=f"{summary.name} cast {summary.casts_in_pulls} times inside pulls",
                detail=(
                    f"About {summary.activity_percent:.0f}% of pull time. Counted from "
                    "casts inside pull windows only, so waiting between packs is not "
                    "charged to the player."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{summary.casts_in_pulls} casts in "
                    f"{sum(pull.duration_seconds for pull in run.pulls):.0f}s of pulls",
                    "cast-based, unlike Warcraft Logs' damage-based Activity figure",
                ),
            )
        )

    for rank, (name, ability, amount, multiple) in enumerate(
        _damage_outliers(run, damage_taken)[:MAX_OUTLIERS_REPORTED]
    ):
        findings.append(
            Finding(
                id=f"players.damage.{rank}",
                title=f"{name} took {multiple:.1f}x the group median from {ability}",
                detail=(
                    f"{amount} damage from {ability}. This states a difference, not a "
                    "mistake: whether any single hit was avoidable is not something the "
                    "log records."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"{multiple:.1f}x the median",
                    "median is over the players who took at least one hit of this ability",
                ),
            )
        )
    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_players.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/players.py tests/domain/analysis/test_players.py
git commit -m "State per-player facts without ranking anyone

Activity is counted from casts inside pulls, so route downtime is not
charged to a player, and damage taken is compared against the group median
for the same ability rather than labelled avoidable, which the log cannot
support."
```

---

### Task 10: Defensives never used (§5.6) — `inferred`

**Files:**
- Create: `data/defensives.toml`, `src/wowperf/domain/analysis/defensives.py`
- Modify: `src/wowperf/domain/season.py`, `src/wowperf/adapters/config/toml.py`
- Test: `tests/domain/analysis/test_defensives.py`, `tests/adapters/config/test_toml.py`

**Interfaces:**
- Consumes: `Run`, `CastEvent`, `Finding`, `Confidence`, `Frozen`.
- Produces:
  - In `season.py`: `class DefensiveAbility(Frozen)` with `ability_id: int`, `name: str`; `class Defensives(Frozen)` with `entries: tuple[tuple[str, tuple[DefensiveAbility, ...]], ...]` and `def for_spec(self, class_name: str, spec: str) -> tuple[DefensiveAbility, ...]`
  - In `toml.py`: `def load_defensives(path: Path = DEFAULT_DEFENSIVES_PATH) -> Defensives`, `DEFAULT_DEFENSIVES_PATH`
  - In `analysis/defensives.py`: `def analyse_defensives(run, casts, defensives) -> list[Finding]`

`Defensives` uses a tuple of pairs rather than a dict for the same reason `Run.npc_counts` does: a dict field makes a frozen Pydantic model unhashable and mutable through the field. The lookup key is `f"{class_name}/{spec}"`.

**This analyser is `inferred` and must say so loudly.** The combat log emits no cooldown-reset or cooldown-reduction events, so the tool cannot know a defensive was available. It reports only the unambiguous case: the ability was never cast at any point in the run. `seconds_lost` is `None`.

- [ ] **Step 1: Write the data file**

`data/defensives.toml`. Keep it to the specs in the sample roster plus a couple more; a missing spec produces no findings, which is the correct behaviour for an incomplete list.

```toml
# Personal damage-reduction cooldowns, by class and specialisation.
# No API exposes this list, so it is maintained by hand and dated.
# A spec absent from this file simply produces no defensive findings.
verified = "2026-09-04"

["Mage/Arcane"]
abilities = [
  { ability_id = 235450, name = "Prismatic Barrier" },
  { ability_id = 45438, name = "Ice Block" },
  { ability_id = 55342, name = "Mirror Image" },
]

["Shaman/Elemental"]
abilities = [
  { ability_id = 108271, name = "Astral Shift" },
  { ability_id = 198103, name = "Earth Elemental" },
]

["Priest/Shadow"]
abilities = [
  { ability_id = 47585, name = "Dispersion" },
  { ability_id = 19236, name = "Desperate Prayer" },
]

["Paladin/Holy"]
abilities = [
  { ability_id = 498, name = "Divine Protection" },
  { ability_id = 642, name = "Divine Shield" },
]

["DeathKnight/Blood"]
abilities = [
  { ability_id = 55233, name = "Vampiric Blood" },
  { ability_id = 48792, name = "Icebound Fortitude" },
  { ability_id = 49028, name = "Dancing Rune Weapon" },
]
```

- [ ] **Step 2: Write the failing tests**

`tests/domain/analysis/test_defensives.py`:

```python
# ABOUTME: Behaviour tests for the one defensive claim the log can support.
# ABOUTME: Never cast at all is a fact; not cast at the right time is not, and is not claimed.

from wowperf.domain.analysis.defensives import analyse_defensives
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import Defensives, DefensiveAbility

DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(ability_id=235450, name="Prismatic Barrier"),
                DefensiveAbility(ability_id=45438, name="Ice Block"),
            ),
        ),
    )
)


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=100_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                   item_level=318),
            Player(actor_id=12, name="Sublime", class_name="Shaman", spec="Elemental",
                   item_level=311),
        ),
        pulls=pulls,
    )


def cast(actor_id: int, ability_id: int) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                     timestamp_ms=1_000, pull_index=0)


def test_a_defensive_never_cast_is_reported_as_inferred() -> None:
    findings = analyse_defensives(a_run(), (cast(11, 235450),), DEFENSIVES)
    assert len(findings) == 1
    assert "Ice Block" in findings[0].title
    assert findings[0].confidence is Confidence.INFERRED
    assert findings[0].seconds_lost is None


def test_a_defensive_cast_once_is_not_reported() -> None:
    findings = analyse_defensives(
        a_run(), (cast(11, 235450), cast(11, 45438)), DEFENSIVES
    )
    assert findings == []


def test_the_finding_admits_the_ability_may_have_been_unavailable() -> None:
    findings = analyse_defensives(a_run(), (), DEFENSIVES)
    assert any("cooldown" in f.detail.lower() for f in findings)


def test_a_spec_absent_from_the_list_produces_nothing() -> None:
    # Sublime is an Elemental Shaman and the fixture only knows Arcane Mages.
    findings = analyse_defensives(a_run(), (), DEFENSIVES)
    assert all("Sublime" not in finding.title for finding in findings)


def test_another_players_cast_does_not_excuse_this_player() -> None:
    findings = analyse_defensives(a_run(), (cast(12, 45438),), DEFENSIVES)
    assert any("Ice Block" in finding.title for finding in findings)
```

Append to `tests/adapters/config/test_toml.py`:

```python
def test_the_committed_defensives_file_parses() -> None:
    from wowperf.adapters.config.toml import DEFAULT_DEFENSIVES_PATH, load_defensives

    defensives = load_defensives(DEFAULT_DEFENSIVES_PATH)
    arcane = defensives.for_spec("Mage", "Arcane")
    assert any(ability.name == "Ice Block" for ability in arcane)
    assert defensives.for_spec("Druid", "Feral") == ()
```

- [ ] **Step 3: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_defensives.py tests/adapters/config -v`
Expected: FAIL, `ImportError: cannot import name 'Defensives'`.

- [ ] **Step 4: Add the value objects**

Append to `src/wowperf/domain/season.py`:

```python
class DefensiveAbility(Frozen):
    ability_id: int
    name: str


class Defensives(Frozen):
    """Personal damage-reduction cooldowns per class and specialisation.

    A tuple of pairs rather than a dict, so the model stays hashable and cannot
    be mutated through the field.
    """

    entries: tuple[tuple[str, tuple[DefensiveAbility, ...]], ...] = ()

    def for_spec(self, class_name: str, spec: str) -> tuple[DefensiveAbility, ...]:
        wanted = f"{class_name}/{spec}"
        for key, abilities in self.entries:
            if key == wanted:
                return abilities
        return ()
```

- [ ] **Step 5: Add the loader**

Append to `src/wowperf/adapters/config/toml.py`, importing `Defensives` and `DefensiveAbility`:

```python
DEFAULT_DEFENSIVES_PATH = DATA_DIR / "defensives.toml"


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
                    DefensiveAbility(ability_id=int(item["ability_id"]), name=str(item["name"]))
                    for item in abilities
                ),
            )
        )
    return Defensives(entries=tuple(entries))
```

- [ ] **Step 6: Implement the analyser**

`src/wowperf/domain/analysis/defensives.py`:

```python
# ABOUTME: The one defensive claim a combat log can support: never cast at all.
# ABOUTME: Labelled inferred, because no event says whether a cooldown was available.

from collections import defaultdict

from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Run
from wowperf.domain.season import Defensives


def analyse_defensives(
    run: Run,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
) -> list[Finding]:
    """Name defensives a player never pressed at any point in the run.

    Deliberately narrow. "Should have used it there" needs to know the cooldown
    was up, and the log emits no cooldown-reset or reduction events, so that
    claim is not available at any confidence level.
    """
    cast_ids: dict[int, set[int]] = defaultdict(set)
    for cast in casts:
        cast_ids[cast.actor_id].add(cast.ability_id)

    findings = []
    for player in run.players:
        known = defensives.for_spec(player.class_name, player.spec)
        pressed = cast_ids.get(player.actor_id, set())
        for ability in known:
            if ability.ability_id in pressed:
                continue
            findings.append(
                Finding(
                    id=f"defensives.{player.name}.{ability.ability_id}",
                    title=f"{player.name} never cast {ability.name}",
                    detail=(
                        f"{ability.name} was not cast at any point in the run. This is "
                        "inferred, not measured: the log records no cooldown state, so it "
                        "may have been unavailable, or the talent may not be taken."
                    ),
                    confidence=Confidence.INFERRED,
                    seconds_lost=None,
                    evidence=(
                        f"{player.class_name} {player.spec}",
                        f"ability {ability.ability_id}",
                        "zero casts in the whole run",
                    ),
                )
            )
    return findings
```

- [ ] **Step 7: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_defensives.py tests/adapters/config -v`
Expected: all passing.

- [ ] **Step 8: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add data/defensives.toml src/wowperf/domain/season.py \
        src/wowperf/adapters/config/toml.py src/wowperf/domain/analysis/defensives.py \
        tests/domain/analysis/test_defensives.py tests/adapters/config/test_toml.py
git commit -m "Name defensives that were never pressed, and admit it is inference

The log carries no cooldown state, so the only honest claim is that an
ability was never cast at all. Anything sharper would be the tool guessing
with a straight face."
```

---

### Task 11: The analysis service

**Files:**
- Create: `src/wowperf/domain/analysis/service.py`
- Test: `tests/domain/analysis/test_service.py`

**Interfaces:**
- Consumes: `LoadedRun` from `wowperf.domain.model`; every `analyse_*` function from Tasks 5 to 10; `reconstruct_enemy_casts` from Task 7; `SeasonData` and `Defensives` from `wowperf.domain.season`; `rank_findings` from `wowperf.domain.findings`.
- Produces: `def analyse(loaded: LoadedRun, season: SeasonData, defensives: Defensives) -> list[Finding]`

One function, and it is deliberately dull: run every analyser, concatenate, rank. The interrupt reconstruction happens here because it is the one analyser needing a preparation step, and no caller should have to remember it.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_service.py`:

```python
# ABOUTME: Behaviour tests for running every analyser over one run and ranking the result.
# ABOUTME: Guards the two invariants a reader depends on: every badge set, worst finding first.

from wowperf.domain.analysis.service import analyse
from wowperf.domain.events import CastEvent, Death, EnemyCastRow, EnemyDeath
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run
from wowperf.domain.season import Defensives, DefensiveAbility, SeasonData

SEASON = SeasonData(death_penalty_seconds=5.0, death_penalty_seconds_high_key=15.0,
                    high_key_threshold=12)
DEFENSIVES = Defensives(
    entries=(("Mage/Arcane", (DefensiveAbility(ability_id=45438, name="Ice Block"),)),)
)


def a_loaded_run() -> LoadedRun:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
        Pull(index=1, pull_id=2, name="Boss", encounter_id=99001, start_ms=150_000,
             end_ms=200_000, killed=True, x=30, y=40,
             enemies=(EnemyNpc(actor_id=2, game_id=200),)),
    )
    run = Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=120, count_required=100, npc_counts=((100, 60),),
        players=(Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                        item_level=318),),
        pulls=pulls,
    )
    return LoadedRun(
        run=run,
        casts=(CastEvent(actor_id=11, ability_id=1, ability_name="Frostbolt",
                         timestamp_ms=1_000, pull_index=0),),
        deaths=(Death(player_name="Uglymage", actor_id=11, timestamp_ms=30_000,
                      killing_blow="Molten Scar", pull_index=0,
                      seconds_until_next_action=22.0),),
        enemy_cast_rows=(
            EnemyCastRow(source_id=1, source_instance=0, ability_id=900,
                         ability_name="Searing Wave", timestamp_ms=10_000, is_start=True,
                         pull_index=0),
            EnemyCastRow(source_id=1, source_instance=0, ability_id=900,
                         ability_name="Searing Wave", timestamp_ms=12_000, is_start=False,
                         pull_index=0),
        ),
        enemy_deaths=(EnemyDeath(game_id=100, actor_id=1, timestamp_ms=50_000, forces=120,
                                 pull_index=0),),
    )


def test_every_finding_carries_a_confidence_badge() -> None:
    findings = analyse(a_loaded_run(), SEASON, DEFENSIVES)
    assert findings
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_findings_are_ranked_worst_first_with_untimed_ones_last() -> None:
    findings = analyse(a_loaded_run(), SEASON, DEFENSIVES)
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)
    first_untimed = next(
        (index for index, f in enumerate(findings) if f.seconds_lost is None), len(findings)
    )
    assert all(f.seconds_lost is None for f in findings[first_untimed:])


def test_finding_ids_are_unique() -> None:
    ids = [finding.id for finding in analyse(a_loaded_run(), SEASON, DEFENSIVES)]
    assert len(ids) == len(set(ids))


def test_every_analyser_contributes() -> None:
    ids = {finding.id.split(".")[0] for finding in analyse(a_loaded_run(), SEASON, DEFENSIVES)}
    assert {"time", "deaths", "interrupts", "trash", "defensives"} <= ids


def test_an_empty_run_analyses_without_raising() -> None:
    loaded = a_loaded_run()
    bare = LoadedRun(run=loaded.run)
    findings = analyse(bare, SEASON, DEFENSIVES)
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_service.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement it**

`src/wowperf/domain/analysis/service.py`:

```python
# ABOUTME: Runs every analyser over one loaded run and ranks the findings by time cost.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from wowperf.domain.analysis.deaths import analyse_deaths
from wowperf.domain.analysis.defensives import analyse_defensives
from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.analysis.players import analyse_players
from wowperf.domain.analysis.timeline import decompose_time
from wowperf.domain.analysis.trash import analyse_trash
from wowperf.domain.findings import Finding, rank_findings
from wowperf.domain.model import LoadedRun
from wowperf.domain.season import Defensives, SeasonData


def analyse(loaded: LoadedRun, season: SeasonData, defensives: Defensives) -> list[Finding]:
    """Every analyser, one ranked list."""
    enemy_casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)

    findings: list[Finding] = []
    findings += decompose_time(loaded.run, loaded.deaths, season)
    findings += analyse_deaths(loaded.run, loaded.deaths)
    findings += analyse_interrupts(enemy_casts, loaded.damage_taken)
    findings += analyse_trash(loaded.run, loaded.enemy_deaths)
    findings += analyse_players(
        loaded.run, loaded.casts, loaded.deaths, loaded.interrupts, loaded.damage_taken
    )
    findings += analyse_defensives(loaded.run, loaded.casts, defensives)
    return rank_findings(findings)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_service.py -v`
Expected: 5 passed.

If `test_finding_ids_are_unique` fails, the culprit is almost certainly two analysers using the same prefix, or a player name appearing twice in `deaths.repeat.<name>`. Fix the id scheme, not the test.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/service.py tests/domain/analysis/test_service.py
git commit -m "Run every analyser and rank what they find

Ranking by seconds in one place is what lets a reader trust that the first
finding is the one worth acting on."
```

---

### Task 12: The `analyze` command

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `analyse` from the service, `load_season_data` and `load_defensives` from `adapters/config/toml.py`, `WclRunRepository.load`, `parse_report_url`.
- Produces: `wowperf analyze <report-url-or-code> [--fight N] [--cache-dir DIR] [--out DIR]`, writing `<code>-<fight>.findings.json` into `--out` (default `./out`).

The JSON is the contract Plan D's report reads and the Claude narrative interprets, so its shape is settled here:

```json
{
  "report_code": "6Kx1P9GbNXrcLdHa",
  "fight_id": 36,
  "dungeon_name": "Den of Nalorakk",
  "keystone_level": 16,
  "keystone_time_seconds": 1909.0,
  "in_time": true,
  "findings": [ { "id": "...", "title": "...", "detail": "...", "confidence": "measured",
                  "seconds_lost": 90.0, "evidence": ["..."], "pull_index": 1 } ]
}
```

`in_time` is `keystone_bonus >= 1`. Reuse the UTF-8 stdout handling and the `try/except` error path the `fetch` command already has — real rosters contain non-ASCII names and this command writes a file as well as printing.

Do **not** add `--deep`, `--player`, `--no-compare`, or `--narrative`. Those belong to Plans C and D; adding a flag that does nothing is worse than not having it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`, reusing that file's `CliRunner` fixtures:

```python
def test_analyze_writes_a_findings_file(tmp_path: Path) -> None:
    result = invoke_analyze(tmp_path)
    assert result.exit_code == 0
    written = tmp_path / "out" / "abc123-36.findings.json"
    assert written.is_file()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["report_code"] == "abc123"
    assert payload["keystone_level"] == 16
    assert isinstance(payload["findings"], list)


def test_every_written_finding_carries_a_confidence(tmp_path: Path) -> None:
    invoke_analyze(tmp_path)
    payload = json.loads(
        (tmp_path / "out" / "abc123-36.findings.json").read_text(encoding="utf-8")
    )
    for finding in payload["findings"]:
        assert finding["confidence"] in {"measured", "derived", "inferred"}


def test_analyze_is_a_subcommand_of_its_own() -> None:
    result = CliRunner().invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--out" in result.output


def test_analyze_reports_a_bad_url_as_a_message_not_a_traceback() -> None:
    result = CliRunner().invoke(app, ["analyze", "https://example.com/nope"])
    assert result.exit_code != 0
    assert not isinstance(result.exception, ValueError)
    assert "is not a Warcraft Logs report code or URL" in result.stderr
```

Write `invoke_analyze` alongside the existing helpers: it should point the command at a `MockTransport`-backed repository (the same one the `fetch` tests use, extended for the new operation names) and pass `--out tmp_path / "out"`.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `analyze` is not a command.

- [ ] **Step 3: Implement the command**

Add these imports to `src/wowperf/cli.py` first — `json` from the standard library, and:

```python
from wowperf.adapters.config.toml import load_defensives, load_season_data
from wowperf.adapters.wcl.errors import WclError
from wowperf.domain.analysis.service import analyse
```

`WclError` may already be imported for the `fetch` command's error path; if so, do not import it twice.

Then add the command:

```python
@app.command()
def analyze(
    report: str = typer.Argument(..., help="Report URL or code"),
    fight: int | None = typer.Option(None, help="Fight ID; defaults to the only keystone run"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Where to cache API responses"),
    out: Path = typer.Option(Path("out"), help="Where to write the findings file"),
) -> None:
    """Analyse a Mythic+ run and write its findings as JSON."""
    try:
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        loaded = repository.load(code, fight if fight is not None else fight_from_url)
        findings = analyse(loaded, load_season_data(), load_defensives())
    except (ValueError, WclError, httpx.HTTPError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error

    run = loaded.run
    payload = {
        "report_code": run.report_code,
        "fight_id": run.fight_id,
        "dungeon_name": run.dungeon_name,
        "keystone_level": run.keystone_level,
        "keystone_time_seconds": run.keystone_time_seconds,
        "in_time": run.keystone_bonus >= 1,
        "findings": [finding.model_dump(mode="json") for finding in findings],
    }

    out.mkdir(parents=True, exist_ok=True)
    written = out / f"{run.report_code}-{run.fight_id}.findings.json"
    written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"{len(findings)} findings written to {written}")
```

`ensure_ascii=False` matters: player names are real and should read as themselves in the file, exactly as they now do on stdout.

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: all passing, including the pre-existing `fetch` tests.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/cli.py tests/test_cli.py
git commit -m "Add the analyze command and settle the findings JSON shape

The report and the narrative both read this file, so fixing its shape now
means Plan D adds an HTML file beside it rather than renegotiating it."
```

---

### Task 13: End to end against a real run

**Files:**
- Create: `tests/e2e/test_analyze_e2e.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything.
- Produces: an `e2e`-marked test proving the whole pipeline works against the live API, and a corrected Commands table.

This test is deselected by default, like the Plan A one. It costs about 6 points of the 3600-per-hour budget.

- [ ] **Step 1: Write the test**

`tests/e2e/test_analyze_e2e.py`:

```python
# ABOUTME: End-to-end analysis against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.adapters.config.toml import load_defensives, load_season_data
from wowperf.cli import build_repository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.findings import Confidence
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_produces_ranked_findings(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    loaded = build_repository(tmp_path).load(code, fight)
    findings = analyse(loaded, load_season_data(), load_defensives())

    assert findings, "a real run should produce at least one finding"
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)

    # The streams the analysers depend on must have actually arrived.
    assert loaded.enemy_cast_rows, "no enemy casts fetched"
    assert loaded.damage_taken, "no damage-taken events fetched"
    assert loaded.enemy_deaths, "no enemy deaths fetched"

    # Sanity against the run itself: the residual cannot exceed the whole timer.
    residual = next(f for f in findings if f.id == "time.residual")
    assert residual.seconds_lost is not None
    assert abs(residual.seconds_lost) <= loaded.run.keystone_time_seconds
```

```bash
uv run pytest -v
```
Expected: the new test shows as deselected; everything else passes.

- [ ] **Step 2: Run it against the real API**

```bash
WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... \
WOWPERF_E2E_REPORT='https://www.warcraftlogs.com/reports/<code>?fight=<n>' \
uv run pytest -m e2e -v
```

Expected: PASS. If a finding id collides, fix the id scheme. If a stream is empty, the query arguments are wrong — check them against this plan's "Verified event shapes" table before changing anything else.

**Report the observed findings to your human partner rather than only asserting on them.** This is the first time real data meets the analysers, and a number that is technically valid but obviously wrong — a residual larger than the run, an interrupt count of zero on a dungeon full of casters — is the thing worth catching here. Plan A's first contact found four defects the offline tests could not see; expect the same.

- [ ] **Step 3: Correct the Commands table**

In `CLAUDE.md`, the Commands table marks `uv run wowperf analyze <url>` as planned. It exists now: it analyses a run and writes the findings JSON. The HTML report is still Plan D. Update that row and the repository-state paragraph to say what is built.

- [ ] **Step 4: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add tests/e2e/test_analyze_e2e.py CLAUDE.md
git commit -m "Prove the analysers against a real run

Plan A shipped four defects that only real data exposed, all in code the
offline tests covered. An end-to-end test is the cheapest guard against
repeating that."
```

---

## Plan Self-Review

**Spec coverage.** §5.1 is Task 5, §5.2 Task 6, §5.3 Task 7, §5.4 Task 8, §5.5 Task 9, §5.6 Task 10. §3.5's `data/season.toml` is Task 1 — the gap Plan A deliberately carried forward is closed here. §4's `Finding` shape is honoured as built, with the divergence from the design's prose recorded under "Decisions". §3.6's `analyze` command arrives in Task 12, minus the flags that belong to Plans C and D.

Deliberately deferred, each to a named plan: §6 comparison to Plan C, §7 report and §8 skills to Plan D. §5.5's `--deep` flag is not implemented at all, because measurement closed the question that motivated it.

**Known gaps, carried forward.**

- `data/defensives.toml` covers five specs. A missing spec produces no findings rather than a wrong one, which is the right failure, but the list wants filling out before the report ships to anyone else.
- `PlayerSummary.active_seconds` counts one second per cast. That is a deliberately coarse floor, not a rotation model; the activity percentage it produces is a comparison between players in the same run, not an absolute.
- The trash overage's conversion into seconds apportions from a percentage. It is labelled `derived` and its evidence says so.
- Nothing yet reads `Player.talent_import_string` — design §4 lists it and Plan A does not fetch it. It is needed by Plan C's spell comparison, not by any analyser here.

**Type consistency.** `LoadedRun` moves to the domain in Task 4 and every later task imports it from `wowperf.domain.model`. `analyse` takes exactly `(LoadedRun, SeasonData, Defensives)` in Tasks 11, 12 and 13. `Finding.pull_index` is used throughout; `pull_ref` and `severity` appear nowhere. Every event type constructed in Tasks 5 to 10 uses the field names declared in Task 2.

**Field-name provenance.** Every Warcraft Logs field this plan names appears in the "Verified event shapes" table, confirmed by live query on 2026-09-04. The design's §5.3 prose uses combat-log names that do not exist in the API; the table supersedes it and Task 3 says so explicitly.

