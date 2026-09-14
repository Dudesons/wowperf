# Raid Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load one raid boss fight and produce ranked findings from it, so `wowperf raid <url>` writes a findings file for a boss the way `wowperf analyze` does for a key.

**Architecture:** A new frozen `Encounter` sits beside `Run` and never pretends to be one; `LoadedEncounter` mirrors `LoadedRun`. Four analysers that today take a whole `Run` narrow to the values they actually use — a roster, a combat-seconds denominator, a visibility anchor, a death locator — so both aggregates can call them. No Mythic+ behaviour changes anywhere.

**Tech Stack:** Python 3.12, pydantic (`wowperf.domain.base.Frozen`), typer, httpx, pytest, uv.

**Spec:** `docs/plans/2026-09-13-raid-analysis-design.md`

**This plan is one of three.** It builds §5 (domain model), §8.3 (ingest) and the internal-frame half of §6 that needs no reference. The comparison axis (§6.1–6.7, §8.1, §8.2) and the mechanics comparison (§6.8) with the report (§10) follow as separate plans, each producing working software on its own.

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches network, disk or template. Adapters do that, behind the ports in `src/wowperf/domain/ports.py`.
- **Every finding carries a confidence badge.** A finding without one is a bug.
- **Never invent an API field name.** The verified reference is `.claude/skills/wcl-api/SKILL.md`; every claim there carries the date it was checked. A field not in it is verified against the live schema first, then added as a dated row.
- **Mythic+ behaviour does not change.** After every task, `uv run pytest` must still report **1539 passed, 9 deselected** or more passed, never fewer.
- **Test-first, always.** Write the test, run it, watch it fail for the right reason, then implement. Where a test passes the moment it is written, mutate the thing it covers and confirm it goes red before trusting it. This repository's recorded failure mode is a test that could never have failed.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. Report `cW38jmwdnZfbHVL4` holds twenty real people; refer to them by class, specialisation or role in code, tests, commit messages and documents.
- **Every command runs under `uv`.** On this machine `uv` is off PATH in bash; prefix with `export PATH="$HOME/.local/bin:$PATH" && `.
- **Commit messages:** imperative mood, no `feat:`/`fix:` prefix, plain ASCII only (non-ASCII is mangled in transit), body explains why. End with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Never use `--no-verify`, `--no-hooks` or `--no-pre-commit-hook`.**

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/encounter.py` | **new** — `Encounter` and `LoadedEncounter`, pure data |
| `src/wowperf/domain/analysis/deaths.py` | narrow `analyse_deaths` off `Run` |
| `src/wowperf/domain/analysis/defensives.py` | narrow `alive_combat_seconds` and its two callers off `Run` |
| `src/wowperf/domain/analysis/consumables.py` | narrow both entry points off `Run` |
| `src/wowperf/domain/analysis/encounter_service.py` | **new** — the raid analyser list |
| `src/wowperf/adapters/wcl/ingest.py` | `select_raid_fight`, `build_encounter` |
| `src/wowperf/adapters/wcl/repository.py` | a raid load path beside the keystone one |
| `src/wowperf/cli.py` | the `raid` subcommand |

---

### Task 1: The `Encounter` model

A raid fight carries a boss, a difficulty, a partition and whether it died. It carries no keystone level, no affixes, no pulls and no enemy forces, and the model says so by not having them.

**Files:**
- Create: `src/wowperf/domain/encounter.py`
- Test: `tests/domain/test_encounter.py`

**Interfaces:**
- Consumes: `wowperf.domain.base.Frozen`, `wowperf.domain.model.Player`, and the event types in `wowperf.domain.events`.
- Produces:
  - `Encounter` with fields `report_code: str`, `fight_id: int`, `encounter_id: int`, `boss_name: str`, `difficulty: int`, `partition: int`, `size: int`, `kill: bool`, `fight_percentage: float | None`, `start_ms: int`, `end_ms: int`, `owner_name: str | None = None`, `players: tuple[Player, ...]`
  - `Encounter.duration_seconds -> float`
  - `Encounter.outcome -> str`
  - `LoadedEncounter` with `encounter: Encounter` plus the same optional event-stream fields `LoadedRun` carries, and the same two read-only mapping properties.

- [ ] **Step 1: Write the failing test**

Create `tests/domain/test_encounter.py`:

```python
# ABOUTME: Behaviour tests for the raid encounter aggregate.
# ABOUTME: A boss fight is not a keystone, and this model is where that is enforced.

import pytest
from pydantic import ValidationError

from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.model import Player


def an_encounter(**overrides: object) -> Encounter:
    fields: dict[str, object] = dict(
        report_code="abc123",
        fight_id=22,
        encounter_id=3421,
        boss_name="The Twin Fangs",
        difficulty=4,
        partition=1,
        size=20,
        kill=True,
        fight_percentage=0.01,
        start_ms=1_000,
        end_ms=375_000,
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=700),
        ),
    )
    fields.update(overrides)
    return Encounter(**fields)  # type: ignore[arg-type]


def test_duration_is_the_span_of_the_fight_in_seconds() -> None:
    assert an_encounter(start_ms=1_000, end_ms=375_000).duration_seconds == 374.0


def test_a_kill_and_a_wipe_describe_themselves_differently() -> None:
    assert an_encounter(kill=True).outcome == "killed"
    assert an_encounter(kill=False, fight_percentage=16.49).outcome == "wiped at 16.5%"


def test_a_wipe_with_no_percentage_says_so_rather_than_printing_a_number() -> None:
    # fightPercentage is null on some fights. Defaulting it to zero would read
    # as "wiped at 0%", which is a kill.
    assert an_encounter(kill=False, fight_percentage=None).outcome == "wiped"


def test_an_encounter_is_frozen() -> None:
    with pytest.raises(ValidationError):
        an_encounter().boss_name = "something else"  # type: ignore[misc]


def test_an_encounter_carries_no_keystone_vocabulary() -> None:
    # The whole point of a sibling aggregate. If these ever appear, the model has
    # drifted back towards Run and the analysers will start reading nulls.
    forbidden = {
        "keystone_level", "affix_ids", "affix_names", "keystone_time_ms",
        "keystone_bonus", "count_reached", "count_required", "npc_counts", "pulls",
    }
    present = forbidden & set(Encounter.model_fields)
    assert present == set(), f"Mythic+ fields leaked into Encounter: {sorted(present)}"


def test_a_loaded_encounter_defaults_every_stream_to_empty() -> None:
    loaded = LoadedEncounter(encounter=an_encounter())
    assert loaded.casts == ()
    assert loaded.deaths == ()
    assert loaded.damage_taken == ()
    assert loaded.auras == ()


def test_a_loaded_encounter_reads_its_icons_and_auras_as_mappings() -> None:
    loaded = LoadedEncounter(encounter=an_encounter(), ability_icons=((11, "icon.jpg"),))
    assert loaded.ability_icon_map[11] == "icon.jpg"
    assert loaded.auras_by_actor == {}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_encounter.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'wowperf.domain.encounter'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/encounter.py`:

```python
# ABOUTME: One raid boss fight as a structure: who was there, how long it ran, whether it died.
# ABOUTME: A sibling of Run, not a subtype of it; it holds no keystone vocabulary at all.

from collections.abc import Mapping
from types import MappingProxyType

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    EnemyCastRow,
    HealingEvent,
    HealthSample,
    InterruptEvent,
    Resurrection,
)
from wowperf.domain.model import DamageDoneSeries, Player


class Encounter(Frozen):
    """One boss fight. Carries no pulls: a raid fight has none to carry.

    `fight_percentage` is the boss health remaining when the attempt ended, as
    Warcraft Logs reports it, and is None where the report does not say. A kill
    reports about 0.01 rather than 0, which is why `outcome` reads `kill`
    rather than comparing the percentage against zero.
    """

    report_code: str
    fight_id: int
    encounter_id: int
    boss_name: str
    difficulty: int
    partition: int
    size: int
    kill: bool
    fight_percentage: float | None = None
    start_ms: int
    end_ms: int
    owner_name: str | None = None
    players: tuple[Player, ...]

    @property
    def duration_seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def outcome(self) -> str:
        """How the attempt ended, in the words the report and the findings use."""
        if self.kill:
            return "killed"
        if self.fight_percentage is None:
            return "wiped"
        return f"wiped at {self.fight_percentage:.1f}%"


class LoadedEncounter(Frozen):
    """Everything fetched about one boss fight. Pure data -- no adapter may leak in."""

    encounter: Encounter
    casts: tuple[CastEvent, ...] = ()
    deaths: tuple[Death, ...] = ()
    enemy_cast_rows: tuple[EnemyCastRow, ...] = ()
    interrupts: tuple[InterruptEvent, ...] = ()
    damage_taken: tuple[DamageTakenEvent, ...] = ()
    damage_done: tuple[DamageDoneSeries, ...] = ()
    health_samples: tuple[HealthSample, ...] = ()
    healing: tuple[HealingEvent, ...] = ()
    resurrections: tuple[Resurrection, ...] = ()
    ability_icons: tuple[tuple[int, str], ...] = ()
    auras: tuple[PlayerAuras, ...] = ()

    @property
    def ability_icon_map(self) -> Mapping[int, str]:
        """Icon file names by ability game id, as a read-only mapping."""
        return MappingProxyType(dict(self.ability_icons))

    @property
    def auras_by_actor(self) -> Mapping[int, PlayerAuras]:
        """Buff bands by actor id, as a read-only mapping."""
        return MappingProxyType({one.actor_id: one for one in self.auras})
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_encounter.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Prove the outcome test can fail**

Temporarily change `outcome`'s wipe branch to return `"wiped"` unconditionally. Re-run. Expected: `test_a_kill_and_a_wipe_describe_themselves_differently` FAILS. Restore the code.

- [ ] **Step 6: Run the gate**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

Expected: 1546 passed, 9 deselected; ruff clean; mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/domain/encounter.py tests/domain/test_encounter.py
git commit -F <message file>
```

Subject: `Model a raid boss fight beside the keystone run`

---

### Task 2: Select a raid fight from a report

`select_keystone_fight` filters to fights carrying a `keystoneLevel` and refuses everything else, so a raid fight cannot be loaded at all today. Its raid sibling selects on `encounterID` instead, and accepts a wipe.

**Files:**
- Modify: `src/wowperf/adapters/wcl/ingest.py`
- Test: `tests/adapters/wcl/test_ingest.py`

**Interfaces:**
- Consumes: `IngestError` from the same module.
- Produces: `select_raid_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/wcl/test_ingest.py`:

```python
from wowperf.adapters.wcl.ingest import select_raid_fight


def raid_fights() -> list[dict[str, Any]]:
    """Shaped after a real raid report: trash carries encounterID 0."""
    return [
        {"id": 1, "name": "Venomfang Juggernaut", "encounterID": 0, "kill": None,
         "keystoneLevel": None},
        {"id": 22, "name": "The Twin Fangs", "encounterID": 3421, "kill": True,
         "keystoneLevel": None},
        {"id": 28, "name": "Ula'tek", "encounterID": 3492, "kill": False,
         "keystoneLevel": None},
        {"id": 30, "name": "Ula'tek", "encounterID": 3492, "kill": False,
         "keystoneLevel": None},
    ]


def test_an_explicit_fight_id_selects_that_boss_fight() -> None:
    assert select_raid_fight(raid_fights(), 22)["id"] == 22


def test_a_wipe_is_selected_rather_than_refused() -> None:
    # The whole reason slice 2 does not reuse select_keystone_fight: a
    # progression attempt is exactly the log worth reading.
    assert select_raid_fight(raid_fights(), 30)["id"] == 30


def test_trash_is_not_a_boss_fight() -> None:
    with pytest.raises(IngestError, match="not a boss fight"):
        select_raid_fight(raid_fights(), 1)


def test_a_fight_id_absent_from_the_report_is_refused() -> None:
    with pytest.raises(IngestError, match="no fight 99"):
        select_raid_fight(raid_fights(), 99)


def test_several_boss_fights_and_no_choice_is_refused_rather_than_guessed() -> None:
    # Picking "the last one" or "the only kill" would silently analyse a fight
    # the reader did not ask for, on a report that holds a whole night.
    with pytest.raises(IngestError, match="--fight"):
        select_raid_fight(raid_fights(), None)


def test_one_boss_fight_needs_no_choice() -> None:
    only = [
        {"id": 1, "name": "Trash", "encounterID": 0, "kill": None},
        {"id": 22, "name": "The Twin Fangs", "encounterID": 3421, "kill": True},
    ]
    assert select_raid_fight(only, None)["id"] == 22


def test_a_report_with_no_boss_fight_says_so() -> None:
    with pytest.raises(IngestError, match="no boss fight"):
        select_raid_fight(
            [{"id": 1, "name": "Trash", "encounterID": 0, "kill": None,
              "keystoneLevel": None}],
            None,
        )


def test_a_keystone_is_not_a_raid_boss_fight() -> None:
    """A Mythic+ fight carries an encounterID too -- the dungeon's.

    Selecting on encounterID alone would let `raid` analyse a key as if it were
    a boss, producing a report with no route and no timer and never saying why.
    The discriminator is the absence of a keystoneLevel, not the presence of an
    encounter id.
    """
    keys = [{"id": 36, "name": "Den of Nalorakk", "encounterID": 12825, "kill": True,
             "keystoneLevel": 16}]

    with pytest.raises(IngestError, match="analyze"):
        select_raid_fight(keys, 36)
    with pytest.raises(IngestError, match="no boss fight"):
        select_raid_fight(keys, None)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_ingest.py -k raid -v
```

Expected: `ImportError: cannot import name 'select_raid_fight'`.

- [ ] **Step 3: Write the implementation**

Add to `src/wowperf/adapters/wcl/ingest.py`, immediately after `select_keystone_fight`:

```python
def select_raid_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]:
    """Find the boss fight to analyse.

    A raid fight is one with a non-zero encounterID and no keystoneLevel. Trash
    between bosses is logged as sibling fights carrying encounterID 0, and a
    Mythic+ run carries the dungeon's own encounterID -- so the encounter id
    alone does not separate a boss from a key, and selecting on it would let
    this command analyse a keystone as a boss and never say so.

    Unlike a keystone, a boss fight is not required to be a kill: a wipe is the
    log a progression raid most wants read, and the analysers that need a kill
    withhold themselves rather than being gated here.

    With no `fight_id` and several boss fights on the report, this refuses
    rather than choosing. A night holds eight attempts on one boss; picking the
    last, or the only kill, would analyse a fight nobody asked for.
    """
    boss_fights = [
        fight
        for fight in fights
        if fight.get("encounterID") and fight.get("keystoneLevel") is None
    ]

    if fight_id is not None:
        chosen = next((fight for fight in fights if fight["id"] == fight_id), None)
        if chosen is None:
            raise IngestError(f"This report has no fight {fight_id}")
        if chosen.get("keystoneLevel") is not None:
            raise IngestError(f"Fight {fight_id} is a Mythic+ run; analyze it with `analyze`")
        if not chosen.get("encounterID"):
            raise IngestError(f"Fight {fight_id} is not a boss fight")
        return chosen

    if not boss_fights:
        raise IngestError("This report contains no boss fight")
    if len(boss_fights) > 1:
        ids = ", ".join(str(fight["id"]) for fight in boss_fights)
        raise IngestError(f"This report holds several boss fights ({ids}); pass --fight")
    return boss_fights[0]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_ingest.py -k raid -v
```

Expected: 7 passed.

- [ ] **Step 5: Prove the wipe test can fail**

Temporarily add `if not chosen.get("kill"): raise IngestError("not completed")` before the return. Re-run. Expected: `test_a_wipe_is_selected_rather_than_refused` FAILS. Restore.

- [ ] **Step 6: Run the gate, then commit**

Subject: `Select a raid boss fight without demanding a kill`

---

### Task 3: Build an `Encounter` from a report

**Files:**
- Modify: `src/wowperf/adapters/wcl/ingest.py`
- Test: `tests/adapters/wcl/test_ingest.py`

**Interfaces:**
- Consumes: `select_raid_fight` (Task 2), `Encounter` (Task 1), the existing private `_build_players`.
- Produces: `build_encounter(report: dict[str, Any], fight: dict[str, Any], *, partition: int, talents: dict[int, str] | None = None) -> Encounter` — `partition` is keyword-only and required, because a wrong partition silently compares against a different tuning and a default would hide that.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/wcl/test_ingest.py`:

```python
from wowperf.adapters.wcl.ingest import build_encounter


def a_raid_report() -> dict[str, Any]:
    return {
        "code": "cW38jmwdnZfbHVL4",
        "owner": {"name": "Emberkin"},
        "masterData": {
            "actors": [
                {"id": 11, "name": "Emberkin", "subType": "Mage"},
                {"id": 12, "name": "Stonewake", "subType": "Warrior"},
            ]
        },
    }


def a_raid_fight(**overrides: Any) -> dict[str, Any]:
    fight: dict[str, Any] = {
        "id": 22,
        "name": "The Twin Fangs",
        "encounterID": 3421,
        "difficulty": 4,
        "size": 20,
        "kill": True,
        "fightPercentage": 0.01,
        "startTime": 1_000,
        "endTime": 375_000,
        "friendlyPlayers": [11, 12],
        "friendlySpecs": ["Arcane", "Protection"],
        "friendlyItemLevels": [700, 702],
    }
    fight.update(overrides)
    return fight


def test_an_encounter_carries_the_fight_and_the_roster() -> None:
    encounter = build_encounter(a_raid_report(), a_raid_fight(), partition=1)

    assert encounter.report_code == "cW38jmwdnZfbHVL4"
    assert encounter.fight_id == 22
    assert encounter.encounter_id == 3421
    assert encounter.boss_name == "The Twin Fangs"
    assert encounter.difficulty == 4
    assert encounter.partition == 1
    assert encounter.size == 20
    assert encounter.kill is True
    assert encounter.duration_seconds == 374.0
    assert [player.name for player in encounter.players] == ["Emberkin", "Stonewake"]


def test_a_wipe_keeps_the_percentage_it_ended_at() -> None:
    encounter = build_encounter(
        a_raid_report(), a_raid_fight(kill=False, fightPercentage=16.49), partition=1
    )
    assert encounter.kill is False
    assert encounter.fight_percentage == pytest.approx(16.49)
    assert encounter.outcome == "wiped at 16.5%"


def test_a_missing_difficulty_is_refused_rather_than_defaulted() -> None:
    # Difficulty selects the ranking sample. Defaulting it would compare a
    # Heroic pull against Mythic parses and never say so.
    with pytest.raises(IngestError, match="difficulty"):
        build_encounter(a_raid_report(), a_raid_fight(difficulty=None), partition=1)


def test_a_size_the_report_omits_falls_back_to_the_roster() -> None:
    encounter = build_encounter(a_raid_report(), a_raid_fight(size=None), partition=1)
    assert encounter.size == 2
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_ingest.py -k encounter -v
```

Expected: `ImportError: cannot import name 'build_encounter'`.

- [ ] **Step 3: Write the implementation**

Add to `src/wowperf/adapters/wcl/ingest.py`:

```python
def build_encounter(
    report: dict[str, Any],
    fight: dict[str, Any],
    *,
    partition: int,
    talents: dict[int, str] | None = None,
) -> Encounter:
    """One boss fight as a domain object.

    `partition` is passed rather than read off the fight: a ReportFight carries
    no partition, and the report's own rankings row is where it comes from. The
    caller that has it passes it; nothing here guesses.
    """
    actors = report.get("masterData", {}).get("actors") or []
    players = _build_players(fight, actors, talents or {})

    difficulty = fight.get("difficulty")
    if difficulty is None:
        raise IngestError(
            f"Fight {fight.get('id')} is a boss fight but carries no difficulty"
        )

    return Encounter(
        report_code=report["code"],
        fight_id=fight["id"],
        encounter_id=_required(fight, "encounterID"),
        boss_name=fight["name"],
        difficulty=int(difficulty),
        partition=partition,
        # `size` is the raid size the report recorded. Where it is absent the
        # roster is the honest answer, and it is the number every per-player
        # median is drawn over anyway.
        size=int(fight["size"]) if fight.get("size") else len(players),
        kill=bool(fight.get("kill")),
        fight_percentage=fight.get("fightPercentage"),
        start_ms=int(fight["startTime"]),
        end_ms=int(fight["endTime"]),
        owner_name=(report.get("owner") or {}).get("name"),
        players=players,
    )
```

Add `from wowperf.domain.encounter import Encounter` to the module's imports.

- [ ] **Step 4: Run the test to verify it passes**

Expected: 4 passed.

- [ ] **Step 5: Prove the difficulty guard can fail**

Temporarily replace the raise with `difficulty = 0`. Re-run. Expected: `test_a_missing_difficulty_is_refused_rather_than_defaulted` FAILS. Restore.

- [ ] **Step 6: Run the gate, then commit**

Subject: `Build a raid encounter from a report fight`

---

### Task 4: Narrow the defensive ceiling off `Run`

`alive_combat_seconds` subtracts dead time from `run.total_pull_seconds`, which is zero for a fight with no pulls — so every `defensives.ceiling.*` finding vanishes silently on a raid. It needs a combat-seconds number, not a `Run`.

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py:169-188`
- Modify: `src/wowperf/domain/analysis/service.py`
- Test: `tests/domain/analysis/test_defensives.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `alive_combat_seconds(combat_seconds: float, deaths: tuple[Death, ...], actor_id: int) -> float | None` — the `run` parameter becomes the float it used to read off it.
  - `analyse_defensives(players: tuple[Player, ...], combat_seconds: float, casts: tuple[CastEvent, ...], defensives: Defensives, deaths: tuple[Death, ...]) -> list[Finding]`
  - `analyse_defensives_at_death` and `defensive_base_ids` take `players` in place of `run`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/analysis/test_defensives.py`:

```python
from wowperf.domain.analysis.defensives import alive_combat_seconds


def test_alive_seconds_subtracts_dead_time_from_the_combat_denominator() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              ability_name="Melee", seconds_until_next_action=12.0, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11) == 88.0


def test_alive_seconds_is_unknown_when_a_death_was_never_followed_by_an_action() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              ability_name="Melee", seconds_until_next_action=None, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11) is None


def test_alive_seconds_never_goes_negative() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              ability_name="Melee", seconds_until_next_action=500.0, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11) == 0.0


def test_a_fight_with_no_pulls_still_has_a_ceiling_denominator() -> None:
    """The defect this narrowing exists to remove.

    Passing `run.total_pull_seconds` for a raid fight passes zero, and every
    ceiling finding disappears without a word. Passing fight duration does not.
    """
    assert alive_combat_seconds(374.0, (), 11) == 374.0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_defensives.py -k alive -v
```

Expected: FAIL — `alive_combat_seconds` takes a `Run`, so passing `100.0` raises `AttributeError: 'float' object has no attribute 'total_pull_seconds'`.

- [ ] **Step 3: Write the implementation**

In `src/wowperf/domain/analysis/defensives.py`, change the signature and the final line:

```python
def alive_combat_seconds(
    combat_seconds: float, deaths: tuple[Death, ...], actor_id: int
) -> float | None:
    """Combat time this player could actually have pressed a button in.

    `combat_seconds` is the denominator the caller's aggregate defines: summed
    pull time for a keystone, fight duration for a raid boss. Taking the number
    rather than the aggregate is what lets both ask this question; taking a
    `Run` meant a raid fight silently supplied zero.

    Returns `None` when any of this player's deaths has `seconds_until_next_action`
    of `None` -- that death's cost cannot be measured because the player's last
    recorded action was dying, so nothing follows it to measure to. There is no
    honest dead-time figure to subtract, so there is no honest alive-time figure
    either; the caller must report no ceiling finding for this player rather
    than treat the unmeasured death as zero seconds dead.

    Otherwise approximate on purpose, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot. Overshooting lowers the ceiling, which makes the
    claim weaker rather than louder.
    """
    theirs = [death for death in deaths if death.actor_id == actor_id]
    if any(death.seconds_until_next_action is None for death in theirs):
        return None
    dead = sum(death.seconds_until_next_action or 0.0 for death in theirs)
    return max(combat_seconds - dead, 0.0)
```

Then replace every `run` parameter in `analyse_defensives`, `analyse_defensives_at_death` and `defensive_base_ids` with `players: tuple[Player, ...]`, adding `combat_seconds: float` to `analyse_defensives`. Inside them, `run.players` becomes `players` and the `alive_combat_seconds(run, ...)` call becomes `alive_combat_seconds(combat_seconds, ...)`. Import `Player` from `wowperf.domain.model` and drop the `Run` import if nothing else uses it.

In `src/wowperf/domain/analysis/service.py`, update the two call sites:

```python
    findings += analyse_defensives(
        loaded.run.players, loaded.run.total_pull_seconds, loaded.casts, defensives,
        loaded.deaths,
    )
    findings += analyse_defensives_at_death(
        loaded.run.players, loaded.casts, defensives, loaded.deaths
    )
```

- [ ] **Step 4: Run the full defensive suite**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_defensives.py -v
```

Expected: all pass. Existing tests that construct a `Run` and pass it now pass `a_run().players` and `a_run().total_pull_seconds`; update those call sites and change nothing about what they assert.

- [ ] **Step 5: Run the gate**

Expected: same passed count as before this task plus 4, and **no Mythic+ test asserts anything different**. If a Mythic+ assertion changed, the refactor changed behaviour and must be reverted.

- [ ] **Step 6: Commit**

Subject: `Give the defensive ceiling a denominator instead of a run`

---

### Task 5: Narrow the consumable claims off `Run`

`visible_from_ms` is `min(pull.start_ms ...)` with a default of 0, so a raid fight anchors visibility at the beginning of time and the guard that exists to prevent a false accusation stops guarding.

**Files:**
- Modify: `src/wowperf/domain/analysis/consumables.py:73-100` and the sibling entry point
- Modify: `src/wowperf/domain/analysis/service.py`
- Test: `tests/domain/analysis/test_consumables.py`

**Interfaces:**
- Produces:
  - `analyse_consumables_at_death(players: tuple[Player, ...], visible_from_ms: int, casts: tuple[CastEvent, ...], consumables: Consumables, deaths: tuple[Death, ...]) -> list[Finding]`
  - `analyse_consumables_never_used(players: tuple[Player, ...], casts: tuple[CastEvent, ...], consumables: Consumables, deaths: tuple[Death, ...]) -> list[Finding]`

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/analysis/test_consumables.py`:

```python
def test_the_visibility_anchor_is_the_callers_and_not_a_default_of_zero() -> None:
    """The defect this narrowing removes.

    With `min(pull.start_ms, default=0)` a raid fight anchors at 0, so every
    consumable window reaches back before the log and the guard at
    `consumables.py` stops refusing claims it cannot support. Passing the
    fight's own start keeps the refusal working.
    """
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=30_000,
              ability_name="Melee", seconds_until_next_action=5.0, pull_index=None),
    )
    findings = analyse_consumables_at_death(
        PLAYERS, 25_000, (), CONSUMABLES, deaths
    )
    assert findings == [], (
        "a death 5s after the log became visible cannot support a claim about a "
        "two-minute consumable window"
    )
```

Reuse whichever `PLAYERS` and `CONSUMABLES` constants that file already defines; if it builds a `Run` inline, take `.players` off it rather than introducing a second fixture.

- [ ] **Step 2: Run the test to verify it fails**

Expected: `TypeError` — the function takes a `Run` first.

- [ ] **Step 3: Write the implementation**

Replace the `run` parameter on both entry points with `players: tuple[Player, ...]`, and give `analyse_consumables_at_death` a `visible_from_ms: int` parameter in place of the line that computed it:

```python
    # Casts are fetched from the fight's start, so nothing before it is visible.
    # `consumables_up_at` needs that boundary to refuse a claim it cannot
    # support. The caller supplies it: a keystone's first pull start, a raid
    # fight's own start. Computing it from pulls here meant a fight without
    # pulls anchored at zero and the refusal never fired.
```

Update `run.players` to `players` throughout both functions, and update `src/wowperf/domain/analysis/service.py`:

```python
    findings += analyse_consumables_at_death(
        loaded.run.players,
        min((pull.start_ms for pull in loaded.run.pulls), default=0),
        loaded.casts, consumables, loaded.deaths,
    )
    findings += analyse_consumables_never_used(
        loaded.run.players, loaded.casts, consumables, loaded.deaths
    )
```

- [ ] **Step 4: Run the suite, fix existing call sites, run the gate**

Expected: every existing consumable test passes with its assertions unchanged.

- [ ] **Step 5: Commit**

Subject: `Take the consumable visibility anchor from the caller`

---

### Task 6: Narrow the death analyser off `Run`

`analyse_deaths` reads `run.pulls` twice: once for an evidence line and once through `pull_offset`. A raid fight locates a death against the fight, not against a pull.

**Files:**
- Modify: `src/wowperf/domain/analysis/deaths.py:69-76`
- Modify: `src/wowperf/domain/analysis/service.py`
- Test: `tests/domain/analysis/test_deaths.py`

**Interfaces:**
- Produces:
  - `analyse_deaths(deaths: tuple[Death, ...], locate: Callable[[Death], str], scope: str) -> list[Finding]`
  - `pull_offset(run: Run, death: Death) -> str` keeps its signature and behaviour.
  - `fight_offset(start_ms: int, death: Death) -> str` — new, in the same module.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/analysis/test_deaths.py`:

```python
from wowperf.domain.analysis.deaths import fight_offset


def test_a_death_locates_against_the_fight_when_there_are_no_pulls() -> None:
    death = Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
                  ability_name="Ravenous Feast", seconds_until_next_action=3.0,
                  pull_index=None)
    assert fight_offset(1_000, death) == "60s in"


def test_the_scope_phrase_reaches_the_evidence_verbatim() -> None:
    """A raid report must not print 'across 0 pulls'."""
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              ability_name="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_deaths(deaths, lambda d: fight_offset(1_000, d),
                              "in 374s of The Twin Fangs")

    assert findings, "one death must produce one finding"
    assert "1 deaths in 374s of The Twin Fangs" in findings[0].evidence
    assert not any("pull" in line for line in findings[0].evidence)
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: `ImportError: cannot import name 'fight_offset'`.

- [ ] **Step 3: Write the implementation**

Add to `src/wowperf/domain/analysis/deaths.py`:

```python
def fight_offset(start_ms: int, death: Death) -> str:
    """Where a death happened, in seconds since the fight began.

    The raid counterpart of `pull_offset`. A boss fight is its own window, so
    there is no pull to be inside or outside of, and the reader can act on
    "60s in" against a timeline they remember.
    """
    return f"{(death.timestamp_ms - start_ms) / 1000:.0f}s in"
```

Change `analyse_deaths` to take the locator and the scope phrase:

```python
def analyse_deaths(
    deaths: tuple[Death, ...],
    locate: Callable[[Death], str],
    scope: str,
) -> list[Finding]:
    """Report what dying cost, grouped so a wipe reads as one event.

    `locate` turns one death into the words that say where it happened, and
    `scope` says what the count is measured across. Both are passed because a
    keystone and a boss fight answer them differently, and reading them off a
    `Run` meant a raid report evidenced "across 0 pulls".
    """
    if not deaths:
        return []

    total_cost, unmeasured_count = _measured_cost(deaths)
    evidence = [f"{len(deaths)} deaths {scope}"]
```

Replace every internal `pull_offset(run, death)` call with `locate(death)`. Add `from collections.abc import Callable` to the imports.

In `service.py`:

```python
    findings += analyse_deaths(
        loaded.deaths,
        lambda death: pull_offset(loaded.run, death),
        f"across {len(loaded.run.pulls)} pulls",
    )
```

- [ ] **Step 4: Run the suite, fix existing call sites, run the gate**

Every existing Mythic+ death test must assert exactly what it asserted before.

- [ ] **Step 5: Commit**

Subject: `Let a death say where it happened without a pull`

---

### Task 7: The raid analyser list

**Files:**
- Create: `src/wowperf/domain/analysis/encounter_service.py`
- Test: `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes: Tasks 1, 4, 5, 6, and the untouched `analyse_interrupts` / `reconstruct_enemy_casts`.
- Produces: `analyse_encounter(loaded: LoadedEncounter, defensives: Defensives, consumables: Consumables, *, roles: Roles = Roles()) -> list[Finding]`

- [ ] **Step 1: Write the failing test**

Create `tests/domain/analysis/test_encounter_service.py`:

```python
# ABOUTME: The raid analyser list, and which claims a boss fight can support.
# ABOUTME: What is absent here matters as much as what is present.

from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
from wowperf.domain.season import Consumables, DefensiveAbility, Defensives

DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (DefensiveAbility(ability_id=45438, name="Ice Block", cooldown_seconds=240.0),),
        ),
    )
)


def a_loaded_encounter(**overrides: object) -> LoadedEncounter:
    encounter = Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=375_000,
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=700),
        ),
    )
    fields: dict[str, object] = {"encounter": encounter}
    fields.update(overrides)
    return LoadedEncounter(**fields)  # type: ignore[arg-type]


def test_a_fight_with_nothing_in_it_produces_no_findings() -> None:
    assert analyse_encounter(a_loaded_encounter(), DEFENSIVES, Consumables()) == []


def test_a_death_is_reported_and_located_against_the_fight() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              ability_name="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())

    assert findings, "a death must produce a finding"
    assert any("The Twin Fangs" in line for line in findings[0].evidence)
    assert not any("pull" in line for f in findings for line in f.evidence)


def test_the_defensive_ceiling_uses_fight_duration_and_therefore_fires() -> None:
    """The regression this whole slice guards against.

    Under the rejected design -- a Run holding one degenerate pull -- the
    ceiling denominator was zero and this finding disappeared in silence.
    """
    casts = (
        CastEvent(actor_id=11, ability_id=45438, ability_name="Ice Block",
                  timestamp_ms=10_000, pull_index=None, succeeded=True),
    )
    findings = analyse_encounter(a_loaded_encounter(casts=casts), DEFENSIVES,
                                 Consumables())

    ceiling = [f for f in findings if f.id.startswith("defensives.ceiling")]
    assert ceiling, "one Ice Block in a 374s fight is below its ceiling; say so"
    assert ceiling[0].confidence is Confidence.INFERRED


def test_every_finding_carries_a_confidence_badge() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              ability_name="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())
    assert findings, "the guard below proves nothing against an empty list"
    assert all(isinstance(f.confidence, Confidence) for f in findings)


def test_no_keystone_shaped_finding_reaches_a_raid_report() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              ability_name="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())
    assert findings, "the guard below proves nothing against an empty list"
    forbidden = ("time.residual", "time.gap", "trash.", "compare.route")
    leaked = [f.id for f in findings if f.id.startswith(forbidden)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: `ModuleNotFoundError: No module named 'wowperf.domain.analysis.encounter_service'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/analysis/encounter_service.py`:

```python
# ABOUTME: Runs the analysers a single boss fight can support, and ranks the findings.
# ABOUTME: Deliberately dull: all the judgement lives in the analysers, none of it here.

from wowperf.domain.analysis.consumables import (
    analyse_consumables_at_death,
    analyse_consumables_never_used,
)
from wowperf.domain.analysis.deaths import analyse_deaths, fight_offset
from wowperf.domain.analysis.defensives import (
    analyse_defensives,
    analyse_defensives_at_death,
)
from wowperf.domain.analysis.interrupts import analyse_interrupts, reconstruct_enemy_casts
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Finding, rank_findings
from wowperf.domain.season import Consumables, Defensives, Roles


def analyse_encounter(
    loaded: LoadedEncounter,
    defensives: Defensives,
    consumables: Consumables,
    *,
    roles: Roles = Roles(),
) -> list[Finding]:
    """Every analyser a single boss fight supports, as one ranked list.

    Four of slice 1's analysers are absent, and their absence is the design
    rather than an omission. `decompose_time` and `analyse_trash` measure a
    keystone timer and an enemy-forces requirement, neither of which a boss
    fight has. `analyse_players` prices activity against pull windows. The
    throughput pair ranks pulls worth a cooldown. Their raid counterparts are
    comparisons against a reference sample and belong to the next plan, not
    here.
    """
    encounter = loaded.encounter
    enemy_casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)

    findings: list[Finding] = []
    findings += analyse_deaths(
        loaded.deaths,
        lambda death: fight_offset(encounter.start_ms, death),
        f"in {encounter.duration_seconds:.0f}s of {encounter.boss_name}",
    )
    findings += analyse_interrupts(enemy_casts, loaded.damage_taken)
    findings += analyse_defensives(
        encounter.players, encounter.duration_seconds, loaded.casts, defensives,
        loaded.deaths,
    )
    findings += analyse_defensives_at_death(
        encounter.players, loaded.casts, defensives, loaded.deaths
    )
    findings += analyse_consumables_at_death(
        encounter.players, encounter.start_ms, loaded.casts, consumables, loaded.deaths
    )
    findings += analyse_consumables_never_used(
        encounter.players, loaded.casts, consumables, loaded.deaths
    )
    return rank_findings(findings)
```

- [ ] **Step 4: Run the test to verify it passes**

Expected: 5 passed.

- [ ] **Step 5: Prove the ceiling test can fail**

Temporarily pass `0.0` instead of `encounter.duration_seconds`. Re-run. Expected: `test_the_defensive_ceiling_uses_fight_duration_and_therefore_fires` FAILS. Restore. **This mutation is the point of the task; do not skip it.**

- [ ] **Step 6: Run the gate, then commit**

Subject: `Run the analysers a boss fight can support`

---

### Task 8: Load a raid fight

**Files:**
- Modify: `src/wowperf/adapters/wcl/repository.py`
- Test: `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Consumes: `select_raid_fight`, `build_encounter`, and the existing event-stream builders, which need no change.
- Produces: `WclRunRepository.load_encounter(report_code: str, fight_id: int | None) -> LoadedEncounter`

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/wcl/test_repository.py`, following whatever fake-client pattern that file already uses:

```python
def test_loading_a_raid_fight_fetches_the_same_streams_a_run_does() -> None:
    """The event builders are already generic; this asserts they are reached.

    A raid fight that came back with no casts and no deaths would look exactly
    like a quiet fight, which is why this asserts on the queries sent rather
    than only on the result.
    """
    client = a_fake_client_returning_a_raid_report()
    repository = WclRunRepository(client, cache=a_cache())

    loaded = repository.load_encounter("cW38jmwdnZfbHVL4", 22)

    assert loaded.encounter.boss_name == "The Twin Fangs"
    assert loaded.encounter.kill is True
    assert loaded.casts, "casts must be fetched for a boss fight"
    assert loaded.deaths, "deaths must be fetched for a boss fight"


def test_loading_a_wipe_is_not_refused() -> None:
    client = a_fake_client_returning_a_raid_report(kill=False, fightPercentage=16.49)
    repository = WclRunRepository(client, cache=a_cache())

    loaded = repository.load_encounter("cW38jmwdnZfbHVL4", 30)

    assert loaded.encounter.kill is False
    assert loaded.encounter.outcome == "wiped at 16.5%"
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: `AttributeError: 'WclRunRepository' object has no attribute 'load_encounter'`.

- [ ] **Step 3: Write the implementation**

**First, widen `FIGHTS_QUERY`.** It selects neither `difficulty` nor `size` today (checked 2026-09-14 against `src/wowperf/adapters/wcl/queries.py:73-99`). Both exist on `ReportFight` — confirmed by schema introspection on 2026-09-14, alongside `fightPercentage`, `bossPercentage`, `lastPhase`, `phaseTransitions` and `wipeCalledTime`. Add three fields to the `fights(translate: true)` selection set, immediately after `kill`:

```graphql
        difficulty
        size
        fightPercentage
```

Then add a dated row for each to `.claude/skills/wcl-api/SKILL.md`'s field table, marked as queried. `tests/test_skills.py::test_every_field_the_table_says_we_query_is_in_the_queries` holds that table against `queries.py` and will fail until they are there.

Adding these three costs nothing: `FIGHTS_QUERY` is already sent for every Mythic+ run, and three scalars on an existing selection set do not change its shape. Mythic+ ignores all three.

**Then add `load_encounter`** beside the existing `load`, reusing the same query fan-out and the same cache. It calls `select_raid_fight` in place of `select_keystone_fight` and `build_encounter` in place of `build_run`, and skips the two Mythic+-only steps — `_affix_names` and the enemy-deaths forces splice, both of which read fields a raid fight does not carry.

**Partition:** `ReportFight` has no partition field, so `build_encounter` takes it as a keyword. Until the next plan fetches the report's own rankings row (design §2.2, where partition arrives for free), pass the zone's default partition, which is `1` for the current tier. Record in the call site's comment that this is the default and not a read value, so the next plan replaces it rather than trusting it.

- [ ] **Step 4: Run the suite and the gate, then commit**

Subject: `Load a boss fight through the existing stream builders`

---

### Task 9: `wowperf raid`

**Files:**
- Modify: `src/wowperf/cli.py`
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` — `tests/test_skills.py` holds the skill's flag list equal to the command's help, so a new command with new flags breaks that test until the skill names them
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_encounter` (Task 8), `analyse_encounter` (Task 7).
- Produces: the `raid` subcommand, writing `<code>-<fight>.findings.json`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`, using the `plain()` helper that file already defines:

```python
def test_raid_is_a_subcommand_of_its_own() -> None:
    result = runner.invoke(app, ["raid", "--help"])
    assert result.exit_code == 0
    assert "--fight" in plain(result.output)
    assert "--out" in plain(result.output)
    assert "Traceback" not in result.output


def test_the_keystone_flags_are_not_offered_by_raid() -> None:
    """`raid` is a sibling of `analyze`, not a copy of it.

    --throughput-ceiling ranks pulls worth a cooldown, which a boss fight has
    none of. Offering a flag that cannot work is worse than not offering it.
    """
    offered = plain(runner.invoke(app, ["raid", "--help"]).output)
    assert "--fight" in offered, "the guard below proves nothing against empty output"
    assert "--throughput-ceiling" not in offered


@pytest.mark.usefixtures("wired_cli")
def test_raid_on_a_keystone_report_names_the_command_that_does_handle_it() -> None:
    """`wired_cli`'s mock transport serves a Mythic+ report.

    Pointing `raid` at one is the mistake a reader will actually make, and the
    error has to be a signpost rather than a complaint.
    """
    result = runner.invoke(app, ["raid", "abc123"])

    assert result.exit_code != 0
    assert "analyze" in plain(result.output)
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run the test to verify it fails**

Expected: `raid` is not a command; exit code 2.

- [ ] **Step 3: Write the implementation**

Add the `raid` command to `src/wowperf/cli.py`, modelled on `analyze` minus its Mythic+ flags. It takes `url`, `--fight`, `--player` (repeatable), `--all-players`, `--no-compare`, `--cache-dir`, `--out`. In this plan `--player`, `--all-players` and `--no-compare` are accepted and inert — the comparison axis is the next plan — and the command says so in one line rather than pretending to compare.

Write `<code>-<fight>.findings.json` with the same envelope `analyze` writes, replacing its Mythic+ header block with `boss_name`, `difficulty`, `partition`, `size`, `kill`, `fight_percentage` and `duration_seconds`. Close by printing what the run spent from the hourly budget, dearest operation first, exactly as the other two commands do.

- [ ] **Step 4: Run the suite and the gate**

`tests/test_skills.py::test_every_flag_the_command_offers_is_named_in_the_workflow` covers `analyze` only. Confirm it still passes and do not widen it in this task.

- [ ] **Step 5: Commit**

Subject: `Add a raid command that writes a boss fight's findings`

---

### Task 10: End to end, against the real API

**Files:**
- Create: `tests/e2e/test_raid_e2e.py`

- [ ] **Step 1: Write the test**

```python
# ABOUTME: One real raid fight, fetched from the live API, analysed end to end.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.adapters.config.toml import load_consumables, load_defensives
from wowperf.cli import build_repository
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.findings import Confidence
from wowperf.urls import parse_report_url

KILL = os.environ.get("WOWPERF_E2E_RAID_KILL", "")
WIPE = os.environ.get("WOWPERF_E2E_RAID_WIPE", "")

# Findings a boss fight cannot support. Slice 1 emits all four; if one reaches a
# raid report, an analyser is reading an aggregate that has no such thing and
# answering zero rather than abstaining.
KEYSTONE_SHAPED = ("time.", "trash.", "compare.route", "compare.downtime")


@pytest.mark.e2e
def test_a_real_boss_kill_produces_ranked_findings(tmp_path: Path) -> None:
    if not KILL:
        pytest.fail(
            "Set WOWPERF_E2E_RAID_KILL to a public report URL naming a boss kill "
            "(include the #fight=N fragment) to run this"
        )

    code, fight = parse_report_url(KILL)
    loaded = build_repository(tmp_path).load_encounter(code, fight)
    findings = analyse_encounter(loaded, load_defensives(), load_consumables())

    assert loaded.encounter.kill is True
    assert loaded.encounter.duration_seconds > 0
    assert findings, "a real boss kill should produce at least one finding"
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    leaked = [f.id for f in findings if f.id.startswith(KEYSTONE_SHAPED)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"

    # The streams the analysers depend on must have actually arrived, or every
    # assertion above holds over an empty list and proves nothing.
    assert loaded.casts, "no casts fetched"
    assert loaded.damage_taken, "no damage taken fetched"


@pytest.mark.e2e
def test_a_real_wipe_is_analysed_rather_than_refused(tmp_path: Path) -> None:
    if not WIPE:
        pytest.fail(
            "Set WOWPERF_E2E_RAID_WIPE to a public report URL naming a wiped attempt "
            "(include the #fight=N fragment) to run this"
        )

    code, fight = parse_report_url(WIPE)
    loaded = build_repository(tmp_path).load_encounter(code, fight)
    findings = analyse_encounter(loaded, load_defensives(), load_consumables())

    assert loaded.encounter.kill is False
    assert loaded.encounter.outcome.startswith("wiped")
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert loaded.casts, "no casts fetched for the wipe"
```

- [ ] **Step 2: Run it**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest -m e2e tests/e2e/test_raid_e2e.py -v
```

This spends quota. The budget is 3600 points an hour; a cold raid load is expected to cost under 20. **Record the measured figure** in the test's docstring — §14 of the design owes this number and nobody may state it until it is measured.

- [ ] **Step 3: Run the whole gate, then commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

Subject: `Analyse one real boss kill and one real wipe end to end`

---

## What this plan deliberately leaves undone

Named here so the next plan starts from a record rather than a rediscovery.

- **The comparison axis.** Rankings, the sample, `damage.total`, `damage.targets`, `casts.count`, `casts.missing`, `talents`, `uptime.buffs`, `rank`. Design §6.1–6.7, §8.1, §8.2.
- **The mechanics comparison.** Design §6.8, the headline of the slice, and the two API facts §14 items 1 and 2 owe a measurement before it can be written.
- **The report.** Design §10. `raid` writes findings JSON only; there is no HTML until then.
- **`analyse_players`' damage-outlier half.** Design §6.9. It is generic, but its activity half is not, and splitting it belongs with the plan that needs the outliers.
- **Widening the ranking port.** Design §8.2 and §14 item 3. Nothing in this plan calls a ranking.
