# Mythic+ Post-Mortem, Plan C: Comparison — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare an analysed Mythic+ run against two reference runs — a fast completion of the same dungeon and a top parse of the analysed player's specialisation — and turn the differences into `Finding`s alongside the ones Plan B already produces.

**Architecture:** Two leaderboard queries reach the Warcraft Logs rankings API through a new `WclRankingRepository`, which asserts the undocumented bracket convention on every call. The reference reports are then loaded through the existing `WclRunRepository`, so a reference is just another `LoadedRun`. Pure comparison modules under `src/wowperf/domain/comparison/` align the two pull sequences with `difflib`, price what the faster group skipped, and diff spells and talents on boss pulls only. A keystone-level gap withholds every duration-shaped comparison rather than printing a number the reader will misuse.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `typer`, `httpx`, `pytest`, `ruff`, `mypy`. `difflib` from the standard library for pull alignment.

**Spec:** `docs/plans/2026-09-03-mplus-postmortem-design.md` — §6 is what this plan implements, §2.3 and §3.6 are load-bearing for it.

**Depends on:** Plan A (`62fd0e4`) and Plan B (`eae5238`), both merged. Read `src/wowperf/domain/model.py`, `findings.py`, `analysis/timeline.py`, `analysis/service.py`, `adapters/wcl/repository.py` and `cli.py` before starting.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no file reads, no `tomllib` calls. Adapters do that. The comparison modules are pure functions over domain objects.
- **Every `Finding` carries a `Confidence`** of `measured`, `derived`, or `inferred`, and the badge must match how the number was obtained. A derived number labelled `measured` is a defect.
- **Every Mythic+ finding is denominated in seconds.** Not percentiles, not scores. A finding with no honest seconds figure sets `seconds_lost=None` rather than inventing one.
- **The LLM never computes a number.** Every metric comes from tested Python.
- **No hardcoded season data.** No zone, encounter, affix or ability ID in Python. The encounter ID this plan needs is read off the analysed fight at runtime.
- **Cache every Warcraft Logs response.** The budget is 3600 points an hour; an analysis with both references costs about 24.
- **Never invent a Warcraft Logs field name.** Every field this plan uses is listed under "Verified schema" below, confirmed against the live API on 2026-09-04.
- **Never accumulate a corpus of other players' logs.** RPGLogs terms §5d prohibit it. Reference runs are fetched for one comparison and cached locally, never warehoused.
- **Fight, pull and event timestamps are milliseconds relative to report start.** `Report.startTime` is absolute epoch milliseconds. A ranking row's `startTime` is absolute epoch milliseconds.
- **English** in code, comments, error strings, and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains why.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- Every file starts with two `# ABOUTME: ` comment lines. Empty `__init__.py` markers are exempt.
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument — `pyproject.toml` sets `files = ["src", "tests"]`). Ruff's line length is 100.

## Verified schema

Confirmed against the live API on 2026-09-04, using report `6Kx1P9GbNXrcLdHa` fight 36 and encounter 12825. **These are the real names and the real behaviour.** Nothing outside this section may be assumed.

| Field | Verified shape |
| --- | --- |
| `Encounter.fightRankings` arguments | `bracket: Int`, `difficulty: Int`, `filter: String`, `page: Int`, `partition: Int`, `serverRegion: String`, `serverSlug: String`, `size: Int`, `leaderboard: LeaderboardRank`, `hardModeLevel: HardModeLevelRankFilter`, `metric: FightRankingMetricType`, `includeOtherPlayers: Boolean` |
| `Encounter.characterRankings` arguments | the same, minus `includeOtherPlayers`'s siblings and plus `includeCombatantInfo: Boolean`, `className: String`, `specName: String`, `externalBuffs`, `covenantID: Int`, `soulbindID: Int` |
| Either field's return | untyped JSON: `{page: Int, hasMorePages: Bool, count: Int, rankings: [...]}`, 50 rows a page for `fightRankings`, 100 for `characterRankings` |
| `fightRankings` row | `server{id,name,region}`, `duration`, `startTime`, `report{code,fightID,startTime}`, `damageTaken`, `deaths`, `tanks`, `healers`, `melee`, `ranged`, `bracketData`, `affixes[]`, `team[{id,name,class,spec,role}]`, `medal`, `score`, `leaderboard` |
| `characterRankings` row | `name`, `class`, `spec`, `amount`, `hardModeLevel`, `duration`, `startTime`, `report{code,fightID,startTime}`, `guild{id,name,faction}`, `server{id,name,region}`, `bracketData`, `faction`, `affixes[]`, `medal`, `score`, `leaderboard` |
| `ReportFight.talentImportCode(actorID: Int!)` | exists; returns a ~100-character import string such as `C4DAAAAAAAAAAAAAAAAAAAAAAMzwYZmxsgZGamZG…` |
| `ReportFight.encounterID` on a keystone fight | `12825` for Den of Nalorakk, whose `gameZone.id` is `2825`. **The encounter ID this plan needs is on the fight already** — no zone lookup, no hardcoded ID |
| `Report.owner { id name }` | exists; the value is **lowercased** — the owner of a report whose roster shows `Dudesons` reads `dudesons` |
| `worldData.zone(id: 53)` | `{id, name: "The Venomous Abyss", frozen: false, partitions: [{id: 1, name: "12.1", compactName: "12.1", default: true}]}` |

Four behaviours that no documentation states and that a naive implementation gets wrong:

- **`size` is the group size, not a page size.** For a five-player dungeon only `size: 5` is accepted. `1`, `2`, `3`, `4`, `6`, `7`, `8`, `10`, `50` and `100` each return an error. Omitting it works and yields the same rows as `size: 5`. **This plan omits it**, so a future raid slice can pass it without changing the meaning of anything here.
- **A rejected ranking query answers HTTP 200 with no GraphQL error.** The rankings value is `{"error": "Invalid difficulty setting or size specified."}` instead of the usual object. Nothing in the existing adapter notices that, so the ranking repository must check for the `error` key explicitly.
- **`bracket = keystoneLevel - 1` is confirmed.** Requesting `bracket: 15` returns rows whose `bracketData` is `16`, uniformly across all 50 rows. This plan still asserts it on every call, because an off-by-one that changed silently would poison every comparison the tool makes.
- **A `characterRankings` row's `amount` is negative for `playerscore`** — a real row read `-319999564.83`. Use `score`, never `amount`.

## Decisions this plan makes

Recorded here so an implementer does not rediscover them, and so a reviewer does not flag them.

1. **The encounter ID comes off the analysed fight.** Design §3.5 demands no hardcoded season data, and `ReportFight.encounterID` supplies it directly. There is no zone lookup and no `data/*.toml` entry for it.
2. **The partition is not pinned.** Design §6.2 says the partition must match. The API defaults to the zone's current partition, which is what a recently logged run wants, and zone 53 currently has exactly one. Pinning it needs `worldData.zone(id).partitions`, which is verified above but not used. The report declares the reference's affixes instead, and §6.6's "confounds we declare rather than correct" covers the rest. Do not add a partition argument in this plan.
3. **§6.5 items 4 and 5 are deferred, deliberately.** Item 4, cooldown uses against a theoretical maximum, needs a hand-maintained cooldown table with no API source, covering every ability of every specialisation, and the design already labels it `inferred` and wrong for specialisations with reset mechanics. Item 5, buff and debuff uptime, doubles the event fetch on both sides of the comparison. Items 1 to 3 carry the signal the design ranks highest; these two are named as gaps at the end of this plan rather than half-built.
4. **§6.7's parse percentile is Plan D's.** It is a line in the report header, and computing it needs a per-character ranking lookup this plan does not make. The reference's own `score` and `medal` travel in finding evidence, which is what a reader can act on.
5. **A talent comparison prints their import string; it does not diff base64.** The import code is an opaque blob. Reporting that the builds differ, and handing over the string to paste into the game, is the whole honest deliverable.
6. **Confounds are `Finding`s with a `compare.confound.` prefix.** Plan D's report renders them as a banner, but keeping one output type means the findings JSON stays one shape and nothing downstream needs a second parser.
7. **A missing reference is a finding, not a failure.** Design §3.6: ordinary analysis gaps produce findings. The one exception is a bracket assertion failure, which exits non-zero, because every number after it would be wrong.
8. **A reference run is loaded in full.** Route comparison needs only pulls, but deaths and missed interrupts need the event streams, and §6.4 lists both as comparable across a keystone gap. Two full loads cost about 12 points of 3600.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/model.py` | *Modified.* `Run` gains `encounter_id` and `owner_name`; `Player` gains `talent_import_string` |
| `src/wowperf/domain/ports.py` | *Modified.* `RankingRepository` speaks in reference rows; the unused `RunRef` goes |
| `src/wowperf/domain/comparison/reference.py` | `SpeedRow`, `ParseRow`, `SpeedReference`, `ParseReference`, `Comparability` |
| `src/wowperf/domain/comparison/alignment.py` | §6.3 pull alignment over pack signatures |
| `src/wowperf/domain/comparison/route.py` | §6.3/§6.4 findings: packs skipped, packs killed for nothing, order |
| `src/wowperf/domain/comparison/tempo.py` | §6.4 findings: deaths, missed interrupts, downtime, withheld durations |
| `src/wowperf/domain/comparison/spells.py` | §6.5 items 1 to 3, boss pulls only, plus the talent difference |
| `src/wowperf/domain/comparison/confounds.py` | §6.6 declared confounds |
| `src/wowperf/domain/comparison/service.py` | Runs every comparison and ranks the result |
| `src/wowperf/adapters/wcl/queries.py` | *Modified.* Adds two ranking queries and a talent query builder |
| `src/wowperf/adapters/wcl/rankings.py` | Translates ranking rows into `SpeedRow`/`ParseRow`; asserts the bracket |
| `src/wowperf/adapters/wcl/ranking_repository.py` | `WclRankingRepository`, satisfying the port |
| `src/wowperf/adapters/wcl/repository.py` | *Modified.* `load` fetches talent strings |
| `src/wowperf/cli.py` | *Modified.* `--player` and `--no-compare`, and the comparison block in the JSON |

---

### Task 1: The run learns where it is and whose it is

**Files:**
- Modify: `src/wowperf/domain/model.py`, `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/ingest.py`
- Test: `tests/domain/test_model.py`, `tests/adapters/wcl/test_ingest.py`, and every fixture listed in Step 5

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces:
  - `Run.encounter_id: int` — **required**, no default
  - `Run.owner_name: str | None = None`
  - `FIGHTS_QUERY` selects `owner { name }` on the report

`encounter_id` is what the rankings API keys on, and it is already on the fight, so nothing about it is season data. It is required rather than defaulted because a `Run` that cannot say which encounter it is cannot be compared, and a default would let that failure travel silently — the same shape as the bug Plan A shipped when a missing killing blow defaulted to ability id 0.

`owner_name` is optional because a report can have no owner, and because `get` and `load` both read it from the same query.

- [ ] **Step 1: Write the failing domain test**

Append to `tests/domain/test_model.py`:

```python
def test_a_run_carries_the_encounter_it_can_be_compared_against() -> None:
    assert a_run(pulls=()).encounter_id == 12825


def test_a_run_without_an_owner_says_so_rather_than_guessing() -> None:
    assert a_run(pulls=()).owner_name is None
```

Add `encounter_id=12825` to that file's `a_run` helper as part of this step, or the tests cannot construct a `Run` at all.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/test_model.py -v`
Expected: FAIL, a Pydantic `ValidationError` naming `encounter_id` as an unexpected keyword.

- [ ] **Step 3: Add the fields**

In `src/wowperf/domain/model.py`, inside `class Run`, immediately after `dungeon_name`:

```python
    # The rankings API keys on this, and the fight carries it, so no leaderboard
    # lookup in this project ever needs a hardcoded encounter or zone ID.
    encounter_id: int
```

and after `count_required`:

```python
    # Warcraft Logs lowercases the owner's name relative to the character's, so
    # anything matching against it must fold case.
    owner_name: str | None = None
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/test_model.py -v`
Expected: PASS.

- [ ] **Step 5: Repair every other fixture**

`Run` now has a required field, so every construction site needs it. Add `encounter_id=12825,` beside `dungeon_name` in each of these — the value is arbitrary in a fixture, but use the same one everywhere so a reader recognises it:

- `tests/adapters/wcl/test_ingest_events.py`, `a_run`
- `tests/adapters/wcl/test_ingest_streams.py`, `a_run`
- `tests/domain/analysis/test_deaths.py`, `a_run` and `a_run_with_duplicate_names`
- `tests/domain/analysis/test_defensives.py`, `a_run`
- `tests/domain/analysis/test_players.py`, `a_run` and `a_run_with_duplicate_names`
- `tests/domain/analysis/test_timeline.py`, `a_run`
- `tests/domain/analysis/test_trash.py`, `a_run` and `a_run_with_pulls`
- `tests/domain/analysis/test_service.py`, inside `a_loaded_run`

Run: `uv run pytest -q`
Expected: every remaining failure is a `ValidationError` naming `encounter_id`, and the count reaches zero as you work through the list.

- [ ] **Step 6: Write the failing ingest test**

Append to `tests/adapters/wcl/test_ingest.py`:

```python
def a_minimal_fight() -> dict[str, object]:
    return {
        "id": 36,
        "name": "Den of Nalorakk",
        "encounterID": 12825,
        "keystoneLevel": 16,
        "keystoneAffixes": [9, 10, 147],
        "keystoneTime": 1_909_000,
        "keystoneBonus": 1,
        "countReached": 744,
        "countRequired": 729,
        "npcCountMap": {},
        "friendlyPlayers": [],
        "friendlySpecs": [],
        "friendlyItemLevels": [],
        "dungeonPulls": [],
    }


def test_build_run_reads_the_encounter_and_the_owner_off_the_report() -> None:
    report = {
        "code": "abc123",
        "owner": {"name": "dudesons"},
        "masterData": {"actors": []},
    }

    run = build_run(report, a_minimal_fight())

    assert run.encounter_id == 12825
    assert run.owner_name == "dudesons"


def test_build_run_survives_a_report_with_no_owner() -> None:
    report = {"code": "abc123", "masterData": {"actors": []}}

    assert build_run(report, a_minimal_fight()).owner_name is None


def test_a_fight_with_no_encounter_id_fails_loudly() -> None:
    fight = a_minimal_fight()
    del fight["encounterID"]

    with pytest.raises(IngestError, match="encounterID"):
        build_run({"code": "abc123", "masterData": {"actors": []}}, fight)
```

If `pytest` or `IngestError` is not already imported in that file, import them.

- [ ] **Step 7: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest.py -v`
Expected: FAIL, a `ValidationError` naming `encounter_id` as missing.

- [ ] **Step 8: Read the two values in `build_run`**

In `src/wowperf/adapters/wcl/ingest.py`, inside `build_run`, add to the `Run(...)` call after `dungeon_name=fight["name"],`:

```python
        encounter_id=_required(fight, "encounterID"),
```

and after `count_required=_required(fight, "countRequired"),`:

```python
        owner_name=(report.get("owner") or {}).get("name"),
```

`_required` is the existing helper that raises `IngestError` naming the field. An encounter ID that is absent or null must fail loudly rather than default: every comparison downstream would otherwise query the wrong leaderboard and answer confidently.

- [ ] **Step 9: Select the owner**

In `src/wowperf/adapters/wcl/queries.py`, in `FIGHTS_QUERY`, add a line immediately after `endTime` on the report and before `fights(translate: true) {`:

```graphql
      owner { name }
```

The fight already selects `encounterID`, so nothing else in the query changes.

- [ ] **Step 10: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src tests
git commit -m "Carry the encounter and the report owner on a run

A comparison needs to know which leaderboard to ask and whose run it is
looking at. Both are already on the fight, so neither becomes season data."
```

---

### Task 2: Reference rows and what a keystone gap invalidates

**Files:**
- Create: `src/wowperf/domain/comparison/__init__.py`, `src/wowperf/domain/comparison/reference.py`
- Test: `tests/domain/comparison/__init__.py`, `tests/domain/comparison/test_reference.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`; `LoadedRun` from `wowperf.domain.model`.
- Produces, all inheriting `Frozen`:
  - `class SpeedRow`: `report_code: str`, `fight_id: int`, `keystone_level: int`, `duration_ms: int`, `deaths: int`, `affix_ids: tuple[int, ...]`, `score: float`, `medal: str`, `team: tuple[str, ...]`; property `duration_seconds`
  - `class ParseRow`: `report_code: str`, `fight_id: int`, `keystone_level: int`, `duration_ms: int`, `character_name: str`, `class_name: str`, `spec: str`, `affix_ids: tuple[int, ...]`, `score: float`, `medal: str`; property `duration_seconds`
  - `class SpeedReference`: `row: SpeedRow`, `loaded: LoadedRun`
  - `class ParseReference`: `row: ParseRow`, `loaded: LoadedRun`
  - `class Comparability`: `our_level: int`, `their_level: int`; properties `level_gap`, `durations_comparable`; method `withheld_because() -> str`
  - `MAX_LEVEL_GAP: int = 1`

`SpeedRow` and `ParseRow` keep the leaderboard's own duration and death count rather than recomputing them from the fetched report: two answers to one question is one answer too many.

`Comparability` is the whole of §6.4 in one object, so no later module has to remember which numbers survive a keystone-level difference.

- [ ] **Step 1: Write the failing tests**

```bash
mkdir -p src/wowperf/domain/comparison tests/domain/comparison
touch src/wowperf/domain/comparison/__init__.py tests/domain/comparison/__init__.py
```

`tests/domain/comparison/test_reference.py`:

```python
# ABOUTME: Behaviour tests for the reference-run value objects and the comparability rule.
# ABOUTME: The rule is what stops the tool printing a duration across a keystone-level gap.

from wowperf.domain.comparison.reference import (
    MAX_LEVEL_GAP,
    Comparability,
    ParseRow,
    SpeedRow,
)


def a_speed_row(level: int = 16) -> SpeedRow:
    return SpeedRow(
        report_code="71cv4MRdNCp8ZFjG",
        fight_id=28,
        keystone_level=level,
        duration_ms=1_379_452,
        deaths=0,
        affix_ids=(9, 10, 147),
        score=435.5,
        medal="silver",
        team=("Warrior Protection", "Evoker Preservation", "Rogue Subtlety"),
    )


def test_a_speed_row_reports_the_leaderboards_own_duration_in_seconds() -> None:
    assert a_speed_row().duration_seconds == 1379.452


def test_a_parse_row_names_the_character_it_belongs_to() -> None:
    row = ParseRow(
        report_code="37FzMg9pVPH6fnJT",
        fight_id=16,
        keystone_level=16,
        duration_ms=1_399_143,
        character_name="Críms",
        class_name="Mage",
        spec="Arcane",
        affix_ids=(9, 10, 147),
        score=435.17,
        medal="silver",
    )
    assert row.character_name == "Críms"
    assert row.duration_seconds == 1399.143


def test_matching_levels_leave_durations_comparable() -> None:
    rule = Comparability(our_level=16, their_level=16)
    assert rule.level_gap == 0
    assert rule.durations_comparable is True


def test_a_higher_reference_key_withholds_durations_and_says_why() -> None:
    rule = Comparability(our_level=16, their_level=17)
    assert rule.level_gap == 1
    assert rule.durations_comparable is False
    reason = rule.withheld_because()
    assert "+17" in reason
    assert "+16" in reason
    assert "health" in reason.lower()


def test_a_lower_reference_key_withholds_durations_too() -> None:
    rule = Comparability(our_level=16, their_level=15)
    assert rule.level_gap == -1
    assert rule.durations_comparable is False


def test_the_accepted_gap_is_one_level() -> None:
    assert MAX_LEVEL_GAP == 1
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_reference.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.reference'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/reference.py`:

```python
# ABOUTME: What a reference run is, and which comparisons a keystone-level gap invalidates.
# ABOUTME: Pure value objects; fetching a reference is an adapter's job, not this module's.

from wowperf.domain.base import Frozen
from wowperf.domain.model import LoadedRun

MAX_LEVEL_GAP = 1
"""A reference further than this from our keystone level is not offered at all.

Two levels of enemy health is roughly a fifth more, which changes which packs a
group can hold together, not merely how long each one takes.
"""


class SpeedRow(Frozen):
    """One row of the speed leaderboard, in this project's vocabulary."""

    report_code: str
    fight_id: int
    keystone_level: int
    duration_ms: int
    deaths: int
    affix_ids: tuple[int, ...] = ()
    score: float = 0.0
    medal: str = ""
    # "Class Spec" per player, in the order the leaderboard listed them.
    team: tuple[str, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


class ParseRow(Frozen):
    """One row of a specialisation's score leaderboard."""

    report_code: str
    fight_id: int
    keystone_level: int
    duration_ms: int
    character_name: str
    class_name: str
    spec: str
    affix_ids: tuple[int, ...] = ()
    score: float = 0.0
    medal: str = ""

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


class SpeedReference(Frozen):
    """A speed leaderboard row together with the run it points at."""

    row: SpeedRow
    loaded: LoadedRun


class ParseReference(Frozen):
    """A score leaderboard row together with the run it points at."""

    row: ParseRow
    loaded: LoadedRun


class Comparability(Frozen):
    """Which comparisons survive the gap between two keystone levels.

    Enemy health scales about 10% a level and compounds, so anything shaped like
    a duration means something different on each side of a gap. Pull
    composition, pull order, packs skipped, death counts, missed interrupts and
    between-pull downtime do not depend on how much health a mob had.
    """

    our_level: int
    their_level: int

    @property
    def level_gap(self) -> int:
        return self.their_level - self.our_level

    @property
    def durations_comparable(self) -> bool:
        return self.level_gap == 0

    def withheld_because(self) -> str:
        """The sentence a reader gets in place of a number we refuse to print."""
        return (
            f"The reference is a +{self.their_level} and this run is a +{self.our_level}. "
            "Enemy health scales about 10% a keystone level and compounds, so pull "
            "durations and kill times are not comparable and are not shown."
        )
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_reference.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison tests/domain/comparison
git commit -m "Describe a reference run and the gap that invalidates a duration

Naming the rule in one object keeps every later comparison from having to
remember which numbers survive a keystone-level difference."
```

---

### Task 3: Ranking queries, and the bracket assertion

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/errors.py`
- Create: `src/wowperf/adapters/wcl/rankings.py`
- Test: `tests/adapters/wcl/test_rankings.py`

**Interfaces:**
- Consumes: `SpeedRow`, `ParseRow` from `wowperf.domain.comparison.reference`; `WclError` from `wowperf.adapters.wcl.errors`.
- Produces:
  - `queries.FIGHT_RANKINGS_QUERY`, `queries.CHARACTER_RANKINGS_QUERY`
  - `errors.BracketMismatch(WclError)`
  - `def bracket_for(keystone_level: int) -> int` in `rankings.py`
  - `def rankings_block(payload: dict[str, Any]) -> dict[str, Any]` in `rankings.py`
  - `def assert_bracket(rows: list[dict[str, Any]], keystone_level: int) -> None` in `rankings.py`
  - `def build_speed_rows(rows: list[dict[str, Any]]) -> tuple[SpeedRow, ...]`
  - `def build_parse_rows(rows: list[dict[str, Any]]) -> tuple[ParseRow, ...]`

**Field names are fixed.** Use exactly the ones in this plan's "Verified schema" table. Three behaviours there are not guesses and must be honoured:

1. **Do not pass `size`.** It is the group size, not a page size; only `5` is valid for a dungeon and every other value is rejected. Omitting it returns the same rows.
2. **A rejected query answers HTTP 200 with no GraphQL error**, and the rankings value is `{"error": "..."}`. `rankings_block` must detect that and raise `WclError` carrying the message, because the existing adapter's null-report check will not.
3. **`bracket = keystone_level - 1`**, confirmed by live query: `bracket: 15` returns rows whose `bracketData` is `16`. `assert_bracket` re-checks that on every call and raises `BracketMismatch` when it does not hold. An off-by-one that changed silently would poison every comparison the tool makes, and a wrong reference looks exactly like a right one.

- [ ] **Step 1: Add the queries**

Append to `src/wowperf/adapters/wcl/queries.py`:

```python
# Rankings take `bracket`, not a keystone level: bracket 15 returns +16 runs.
# `size` is the group size and not a page size — only 5 is valid for a dungeon,
# and omitting it returns the same rows — so neither query passes it.
FIGHT_RANKINGS_QUERY = """
query FightRankings($encounterId: Int!, $bracket: Int!, $page: Int!) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      fightRankings(metric: speed, bracket: $bracket, page: $page)
    }
  }
}
"""

CHARACTER_RANKINGS_QUERY = """
query CharacterRankings(
  $encounterId: Int!, $bracket: Int!, $page: Int!, $className: String!, $specName: String!
) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      characterRankings(
        metric: playerscore
        bracket: $bracket
        page: $page
        className: $className
        specName: $specName
      )
    }
  }
}
"""
```

- [ ] **Step 2: Add the error type**

Append to `src/wowperf/adapters/wcl/errors.py`:

```python
class BracketMismatch(WclError):
    """The leaderboard bracket did not mean what the tool assumed it means.

    `bracket = keystoneLevel - 1` is a community convention that appears in no
    documentation. If it ever changes, every reference run silently becomes the
    wrong one, so the tool stops instead.
    """
```

- [ ] **Step 3: Write the failing tests**

`tests/adapters/wcl/test_rankings.py`:

```python
# ABOUTME: Behaviour tests for translating leaderboard rows and asserting the bracket rule.
# ABOUTME: Fixtures use the real row shape, captured from the live API on 2026-09-04.

import pytest

from wowperf.adapters.wcl.errors import BracketMismatch, WclError
from wowperf.adapters.wcl.rankings import (
    assert_bracket,
    bracket_for,
    build_parse_rows,
    build_speed_rows,
    rankings_block,
)

SPEED_ROW = {
    "server": {"id": None, "name": None, "region": ""},
    "duration": 1379452,
    "startTime": 1787940898991,
    "report": {"code": "71cv4MRdNCp8ZFjG", "fightID": 28, "startTime": 1787925567733},
    "damageTaken": 216419014,
    "deaths": 0,
    "tanks": 1,
    "healers": 1,
    "melee": 2,
    "ranged": 1,
    "bracketData": 16,
    "affixes": [9, 10, 147],
    "team": [
        {"id": 1, "name": "Dzonamvp", "class": "DeathKnight", "spec": "Frost", "role": "DPS"},
        {"id": 2, "name": "Uglydraenor", "class": "Warrior", "spec": "Protection", "role": "Tank"},
    ],
    "medal": "silver",
    "score": 435.557578125,
    "leaderboard": 0,
}

PARSE_ROW = {
    "name": "Críms",
    "class": "Mage",
    "spec": "Arcane",
    "amount": -319999564.8270117,
    "hardModeLevel": 16,
    "duration": 1399143,
    "startTime": 1787850271519,
    "report": {"code": "37FzMg9pVPH6fnJT", "fightID": 16, "startTime": 1787833995139},
    "guild": {"id": 575362, "name": "Mental Apocalypse", "faction": 1},
    "server": {"id": 283, "name": "Draenor", "region": "EU"},
    "bracketData": 16,
    "faction": 0,
    "affixes": [9, 10, 147],
    "medal": "silver",
    "score": 435.17298828125,
    "leaderboard": 0,
}


def test_the_bracket_is_one_below_the_keystone_level() -> None:
    assert bracket_for(16) == 15


def test_a_rankings_error_is_raised_rather_than_read_as_rows() -> None:
    payload = {
        "worldData": {
            "encounter": {
                "id": 12825,
                "name": "Den of Nalorakk",
                "fightRankings": {"error": "Invalid difficulty setting or size specified."},
            }
        }
    }
    with pytest.raises(WclError, match="Invalid difficulty setting"):
        rankings_block(payload)


def test_a_missing_encounter_is_raised_rather_than_subscripted() -> None:
    with pytest.raises(WclError, match="no encounter"):
        rankings_block({"worldData": {"encounter": None}})


def test_a_healthy_payload_yields_the_rankings_object() -> None:
    payload = {
        "worldData": {
            "encounter": {
                "id": 12825,
                "name": "Den of Nalorakk",
                "characterRankings": {"page": 1, "hasMorePages": True, "rankings": [PARSE_ROW]},
            }
        }
    }
    block = rankings_block(payload)
    assert block["page"] == 1
    assert block["rankings"] == [PARSE_ROW]


def test_the_bracket_assertion_passes_when_the_convention_holds() -> None:
    assert_bracket([SPEED_ROW], keystone_level=16)


def test_the_bracket_assertion_fails_loudly_when_it_does_not() -> None:
    with pytest.raises(BracketMismatch, match="16"):
        assert_bracket([SPEED_ROW], keystone_level=17)


def test_rows_without_bracket_data_do_not_trip_the_assertion() -> None:
    assert_bracket([{"duration": 1}], keystone_level=16)


def test_a_speed_row_becomes_the_domains_own_shape() -> None:
    row = build_speed_rows([SPEED_ROW])[0]
    assert row.report_code == "71cv4MRdNCp8ZFjG"
    assert row.fight_id == 28
    assert row.keystone_level == 16
    assert row.duration_ms == 1379452
    assert row.deaths == 0
    assert row.affix_ids == (9, 10, 147)
    assert row.medal == "silver"
    assert row.team == ("DeathKnight Frost", "Warrior Protection")


def test_a_parse_row_becomes_the_domains_own_shape() -> None:
    row = build_parse_rows([PARSE_ROW])[0]
    assert row.report_code == "37FzMg9pVPH6fnJT"
    assert row.fight_id == 16
    assert row.keystone_level == 16
    assert row.character_name == "Críms"
    assert row.class_name == "Mage"
    assert row.spec == "Arcane"
    assert row.score == pytest.approx(435.17298828125)


def test_a_row_with_no_report_is_skipped_rather_than_half_built() -> None:
    orphan = dict(SPEED_ROW)
    orphan["report"] = None
    assert build_speed_rows([orphan, SPEED_ROW]) == build_speed_rows([SPEED_ROW])
```

- [ ] **Step 4: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_rankings.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.rankings'`.

- [ ] **Step 5: Write the module**

`src/wowperf/adapters/wcl/rankings.py`:

```python
# ABOUTME: Turns Warcraft Logs leaderboard rows into this project's reference-run types.
# ABOUTME: Also asserts the undocumented bracket convention, because a wrong reference looks right.

from typing import Any

from wowperf.adapters.wcl.errors import BracketMismatch, WclError
from wowperf.domain.comparison.reference import ParseRow, SpeedRow


def bracket_for(keystone_level: int) -> int:
    """The leaderboard bracket that holds runs of this keystone level.

    Confirmed by live query on 2026-09-04: bracket 15 returns rows whose
    bracketData is 16. The convention appears in no documentation, which is why
    every call also runs `assert_bracket` over what came back.
    """
    return keystone_level - 1


def rankings_block(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the rankings object out of a response, refusing the two failure shapes.

    A rejected ranking query answers HTTP 200 with no GraphQL error at all: the
    rankings value is `{"error": "..."}` instead of the usual object. Nothing
    else in this adapter notices that, so it is caught here.
    """
    encounter = (payload.get("worldData") or {}).get("encounter")
    if not encounter:
        raise WclError("The rankings response carried no encounter")

    for key in ("fightRankings", "characterRankings"):
        block = encounter.get(key)
        if block is None:
            continue
        if "error" in block:
            raise WclError(f"Warcraft Logs rejected the rankings query: {block['error']}")
        return dict(block)

    raise WclError("The rankings response carried neither fightRankings nor characterRankings")


def assert_bracket(rows: list[dict[str, Any]], keystone_level: int) -> None:
    """Fail loudly if the leaderboard did not return the keystone level we asked for.

    Rows that carry no bracketData are ignored rather than assumed wrong: the
    assertion exists to catch a changed convention, not to reject a sparse row.
    """
    seen = {row["bracketData"] for row in rows if row.get("bracketData") is not None}
    if seen and seen != {keystone_level}:
        raise BracketMismatch(
            f"Asked for bracket {bracket_for(keystone_level)} expecting +{keystone_level} runs, "
            f"but the rows say {sorted(seen)}. The bracket convention has changed and every "
            "comparison built on it would be wrong."
        )


def _report_of(row: dict[str, Any]) -> dict[str, Any] | None:
    report = row.get("report")
    return report if isinstance(report, dict) and report.get("code") else None


def build_speed_rows(rows: list[dict[str, Any]]) -> tuple[SpeedRow, ...]:
    built = []
    for row in rows:
        report = _report_of(row)
        if report is None:
            # A row with no report cannot be fetched, so it is no use as a reference.
            continue
        built.append(
            SpeedRow(
                report_code=report["code"],
                fight_id=report["fightID"],
                keystone_level=row["bracketData"],
                duration_ms=row["duration"],
                deaths=row.get("deaths") or 0,
                affix_ids=tuple(row.get("affixes") or ()),
                score=row.get("score") or 0.0,
                medal=row.get("medal") or "",
                team=tuple(
                    f"{member.get('class', '?')} {member.get('spec', '?')}"
                    for member in row.get("team") or ()
                ),
            )
        )
    return tuple(built)


def build_parse_rows(rows: list[dict[str, Any]]) -> tuple[ParseRow, ...]:
    built = []
    for row in rows:
        report = _report_of(row)
        if report is None:
            continue
        built.append(
            ParseRow(
                report_code=report["code"],
                fight_id=report["fightID"],
                keystone_level=row["bracketData"],
                duration_ms=row["duration"],
                character_name=row["name"],
                class_name=row["class"],
                spec=row["spec"],
                affix_ids=tuple(row.get("affixes") or ()),
                # `amount` is negative for playerscore on a real row; `score` is the figure.
                score=row.get("score") or 0.0,
                medal=row.get("medal") or "",
            )
        )
    return tuple(built)
```

- [ ] **Step 6: Run them and watch them pass**

Run: `uv run pytest tests/adapters/wcl/test_rankings.py -v`
Expected: 10 passed.

- [ ] **Step 7: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/adapters/wcl tests/adapters/wcl/test_rankings.py
git commit -m "Read leaderboard rows, and refuse to trust an unverified bracket

The bracket convention appears in no documentation. Asserting it on every call
is the difference between a wrong reference and a wrong reference that looks
exactly like a right one."
```

---

### Task 4: The ranking repository

**Files:**
- Create: `src/wowperf/adapters/wcl/ranking_repository.py`
- Modify: `src/wowperf/domain/ports.py`
- Test: `tests/adapters/wcl/test_ranking_repository.py`

**Interfaces:**
- Consumes: `WclClient`, `DiskCache`, `cache_key`, everything from Task 3.
- Produces:
  - `class WclRankingRepository` with `__init__(self, client: WclClient, cache: DiskCache)`, `fastest_runs(self, encounter_id: int, keystone_level: int) -> tuple[SpeedRow, ...]` and `top_parses(self, encounter_id: int, keystone_level: int, class_name: str, spec: str) -> tuple[ParseRow, ...]`
  - `ports.RankingRepository` restated as a Protocol with those two methods
  - `ports.RunRef` **deleted**

`RunRef` was written speculatively in Plan A and is imported by nothing. The reference rows supersede it; leaving both would mean two answers to "what is a run we might fetch later".

Both methods try keystone levels in the order `[level, level - 1, level + 1]` and return the first non-empty result, which is §6.2's "at most one level" rule. The caller learns which level it actually got from the returned rows, so nothing downstream has to guess.

- [ ] **Step 1: Replace the port**

In `src/wowperf/domain/ports.py`, delete `class RunRef` and replace `class RankingRepository` with:

```python
class RankingRepository(Protocol):
    def fastest_runs(self, encounter_id: int, keystone_level: int) -> tuple[SpeedRow, ...]: ...

    def top_parses(
        self, encounter_id: int, keystone_level: int, class_name: str, spec: str
    ) -> tuple[ParseRow, ...]: ...
```

Add the import `from wowperf.domain.comparison.reference import ParseRow, SpeedRow` and drop the now-unused `Run` import if nothing else in the file uses it.

- [ ] **Step 2: Write the failing tests**

`tests/adapters/wcl/test_ranking_repository.py`:

```python
# ABOUTME: Behaviour tests for fetching leaderboards, against a mock transport and a real cache.
# ABOUTME: Covers the level fallback, the bracket assertion, and that a page is fetched once.

import json
from pathlib import Path

import httpx
import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import BracketMismatch
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository

TOKEN = {"access_token": "t", "expires_in": 86400}


def speed_row(level: int, code: str = "aaa111") -> dict[str, object]:
    return {
        "duration": 1379452,
        "report": {"code": code, "fightID": 28, "startTime": 1},
        "deaths": 0,
        "bracketData": level,
        "affixes": [9, 10, 147],
        "team": [{"class": "Warrior", "spec": "Protection"}],
        "medal": "silver",
        "score": 435.5,
    }


def parse_row(level: int) -> dict[str, object]:
    return {
        "name": "Críms",
        "class": "Mage",
        "spec": "Arcane",
        "duration": 1399143,
        "report": {"code": "bbb222", "fightID": 16, "startTime": 1},
        "bracketData": level,
        "affixes": [9, 10, 147],
        "medal": "silver",
        "score": 435.1,
    }


def repository(
    tmp_path: Path, by_bracket: dict[int, list[dict[str, object]]], calls: list[int]
) -> WclRankingRepository:
    """A repository whose transport answers from `by_bracket` and records each bracket asked."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=TOKEN)
        body = json.loads(request.content)
        bracket = body["variables"]["bracket"]
        calls.append(bracket)
        rows = by_bracket.get(bracket, [])
        field = "characterRankings" if "className" in body["variables"] else "fightRankings"
        return httpx.Response(
            200,
            json={
                "data": {
                    "worldData": {
                        "encounter": {
                            "id": 12825,
                            "name": "Den of Nalorakk",
                            field: {"page": 1, "hasMorePages": False, "rankings": rows},
                        }
                    }
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
    client = WclClient(TokenProvider("id", "secret", http), http)
    return WclRankingRepository(client, DiskCache(tmp_path))


def test_the_fastest_runs_come_back_as_speed_rows(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {15: [speed_row(16)]}, calls).fastest_runs(12825, 16)

    assert calls == [15]
    assert len(rows) == 1
    assert rows[0].report_code == "aaa111"
    assert rows[0].keystone_level == 16


def test_an_empty_bracket_falls_back_one_level_down_then_up(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {16: [speed_row(17)]}, calls).fastest_runs(12825, 16)

    # 15 is +16, 14 is +15, 16 is +17: our level first, then one below, then one above.
    assert calls == [15, 14, 16]
    assert rows[0].keystone_level == 17


def test_no_reference_at_any_accepted_level_returns_nothing(tmp_path: Path) -> None:
    calls: list[int] = []
    assert repository(tmp_path, {}, calls).fastest_runs(12825, 16) == ()
    assert calls == [15, 14, 16]


def test_a_bracket_that_lies_stops_the_run(tmp_path: Path) -> None:
    with pytest.raises(BracketMismatch):
        repository(tmp_path, {15: [speed_row(11)]}, []).fastest_runs(12825, 16)


def test_top_parses_pass_the_class_and_spec_through(tmp_path: Path) -> None:
    calls: list[int] = []
    rows = repository(tmp_path, {15: [parse_row(16)]}, calls).top_parses(
        12825, 16, "Mage", "Arcane"
    )

    assert calls == [15]
    assert rows[0].character_name == "Críms"
    assert rows[0].spec == "Arcane"


def test_a_repeated_lookup_is_served_from_the_cache(tmp_path: Path) -> None:
    calls: list[int] = []
    subject = repository(tmp_path, {15: [speed_row(16)]}, calls)
    subject.fastest_runs(12825, 16)
    subject.fastest_runs(12825, 16)

    assert calls == [15]
```

- [ ] **Step 3: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_ranking_repository.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.ranking_repository'`.

- [ ] **Step 4: Write the repository**

`src/wowperf/adapters/wcl/ranking_repository.py`:

```python
# ABOUTME: Fetches the two leaderboards a comparison needs, caching every response.
# ABOUTME: Satisfies the RankingRepository port so the domain never learns where a row came from.

from collections.abc import Sequence
from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.queries import CHARACTER_RANKINGS_QUERY, FIGHT_RANKINGS_QUERY
from wowperf.adapters.wcl.rankings import (
    assert_bracket,
    bracket_for,
    build_parse_rows,
    build_speed_rows,
    rankings_block,
)
from wowperf.domain.comparison.reference import ParseRow, SpeedRow


class WclRankingRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._client.execute(query, variables),
        )

    @staticmethod
    def _levels_to_try(keystone_level: int) -> Sequence[int]:
        """Our level first, then one either side — §6.2 accepts a gap of one."""
        return (keystone_level, keystone_level - 1, keystone_level + 1)

    def _rows(self, query: str, variables: dict[str, Any], level: int) -> list[dict[str, Any]]:
        payload = self._query(query, {**variables, "bracket": bracket_for(level), "page": 1})
        rows = rankings_block(payload).get("rankings") or []
        # The assertion runs before anything reads a row, so a changed convention
        # stops the run rather than quietly supplying the wrong reference.
        assert_bracket(rows, level)
        return list(rows)

    def fastest_runs(self, encounter_id: int, keystone_level: int) -> tuple[SpeedRow, ...]:
        for level in self._levels_to_try(keystone_level):
            if level < 2:
                continue
            rows = self._rows(FIGHT_RANKINGS_QUERY, {"encounterId": encounter_id}, level)
            if rows:
                return build_speed_rows(rows)
        return ()

    def top_parses(
        self, encounter_id: int, keystone_level: int, class_name: str, spec: str
    ) -> tuple[ParseRow, ...]:
        variables = {"encounterId": encounter_id, "className": class_name, "specName": spec}
        for level in self._levels_to_try(keystone_level):
            if level < 2:
                continue
            rows = self._rows(CHARACTER_RANKINGS_QUERY, variables, level)
            if rows:
                return build_parse_rows(rows)
        return ()
```

`level < 2` is skipped because bracket 0 is not a keystone bracket; a +2 key is the lowest that exists.

- [ ] **Step 5: Run them and watch them pass**

Run: `uv run pytest tests/adapters/wcl/test_ranking_repository.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src tests
git commit -m "Fetch the speed and score leaderboards for a dungeon

Trying one level either side keeps a comparison possible on a key nobody else
ran, and the level that answered travels on the row so no caller has to guess."
```

---

### Task 5: Talent strings on the loaded run

**Files:**
- Modify: `src/wowperf/domain/model.py`, `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/ingest.py`, `src/wowperf/adapters/wcl/repository.py`
- Test: `tests/adapters/wcl/test_ingest.py`, `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Consumes: `Run`, `Player`, `build_run` as they stand after Task 1.
- Produces:
  - `Player.talent_import_string: str | None = None`
  - `def talents_query(actor_ids: Sequence[int]) -> str` in `queries.py`
  - `build_run(report, fight, talents: dict[int, str] | None = None)` — a third, optional argument
  - `WclRunRepository.load` populates it; `get` does not

`ReportFight.talentImportCode(actorID: Int!)` takes one actor at a time, so the query is built with a GraphQL alias per player. It is the only generated query in this codebase; every other one is a constant. That is why it is a function rather than a string, and why the actor IDs are coerced with `int()` before interpolation.

`get` deliberately does not fetch talents. Plan A made it a single cheap query and Plan B kept it that way; a caller that only wants the shape of a run should not pay for a build it will not read. A `Player` from `get` therefore has `talent_import_string is None`, which is a real state and not a failure.

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/wcl/test_ingest.py`:

```python
def test_a_player_has_no_talent_string_until_one_is_fetched() -> None:
    report = {
        "code": "abc123",
        "masterData": {"actors": [{"id": 693, "name": "Uglymage", "subType": "Mage"}]},
    }
    fight = a_minimal_fight()
    fight["friendlyPlayers"] = [693]
    fight["friendlySpecs"] = ["Arcane"]
    fight["friendlyItemLevels"] = [318]

    assert build_run(report, fight).players[0].talent_import_string is None


def test_a_talent_string_reaches_the_player_it_belongs_to() -> None:
    report = {
        "code": "abc123",
        "masterData": {
            "actors": [
                {"id": 693, "name": "Uglymage", "subType": "Mage"},
                {"id": 7, "name": "Dudesons", "subType": "DeathKnight"},
            ]
        },
    }
    fight = a_minimal_fight()
    fight["friendlyPlayers"] = [693, 7]
    fight["friendlySpecs"] = ["Arcane", "Blood"]
    fight["friendlyItemLevels"] = [318, 320]

    run = build_run(report, fight, talents={693: "C4DAAAAA", 7: "CoPAAAAA"})

    by_name = {player.name: player for player in run.players}
    assert by_name["Uglymage"].talent_import_string == "C4DAAAAA"
    assert by_name["Dudesons"].talent_import_string == "CoPAAAAA"
```

Append to `tests/adapters/wcl/test_rankings.py`? No — the query builder is tested here. Add to `tests/adapters/wcl/test_ingest.py` as well:

```python
def test_the_talents_query_asks_for_one_alias_per_actor() -> None:
    query = talents_query([693, 7])

    assert "a693: talentImportCode(actorID: 693)" in query
    assert "a7: talentImportCode(actorID: 7)" in query
    assert "allowUnlisted: true" in query


def test_the_talents_query_coerces_its_actor_ids() -> None:
    # The ids come from the API as integers; coercing makes that explicit rather
    # than interpolating whatever a caller happened to hold.
    assert "a693: talentImportCode(actorID: 693)" in talents_query(["693"])
```

Import `talents_query` from `wowperf.adapters.wcl.queries` at the top of the file.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest.py -v`
Expected: FAIL, `ImportError: cannot import name 'talents_query'`.

- [ ] **Step 3: Add the field**

In `src/wowperf/domain/model.py`, inside `class Player`, after `item_level`:

```python
    # Absent until a talent query runs; `get` never pays for one.
    talent_import_string: str | None = None
```

- [ ] **Step 4: Add the query builder**

Append to `src/wowperf/adapters/wcl/queries.py`:

```python
def talents_query(actor_ids: Sequence[int]) -> str:
    """One aliased `talentImportCode` per player.

    `ReportFight.talentImportCode(actorID: Int!)` takes a single actor, so a
    roster needs an alias each. This is the only generated query here; the ids
    are coerced to `int` so nothing but a number ever reaches the string.
    """
    fields = "\n".join(
        f"        a{int(actor_id)}: talentImportCode(actorID: {int(actor_id)})"
        for actor_id in actor_ids
    )
    return f"""
query Talents($code: String!, $fightId: Int!) {{
  reportData {{
    report(code: $code, allowUnlisted: true) {{
      fights(fightIDs: [$fightId]) {{
        id
{fields}
      }}
    }}
  }}
}}
"""
```

Add `from collections.abc import Sequence` at the top of the file.

- [ ] **Step 5: Thread the talents through `build_run`**

In `src/wowperf/adapters/wcl/ingest.py`, change `_build_players` to take the map and change `build_run` to pass it:

```python
def _build_players(
    fight: dict[str, Any], actors: list[dict[str, Any]], talents: dict[int, str]
) -> tuple[Player, ...]:
```

and inside the `Player(...)` call, after `item_level=...`:

```python
                talent_import_string=talents.get(actor_id),
```

Then in `build_run`:

```python
def build_run(
    report: dict[str, Any], fight: dict[str, Any], talents: dict[int, str] | None = None
) -> Run:
```

and its `players=` line becomes:

```python
        players=_build_players(fight, actors, talents or {}),
```

- [ ] **Step 6: Run them and watch them pass**

Run: `uv run pytest tests/adapters/wcl/test_ingest.py -v`
Expected: PASS.

- [ ] **Step 7: Write the failing repository test**

Append to `tests/adapters/wcl/test_repository.py`:

```python
def test_load_fetches_talents_and_get_does_not() -> None:
    calls: list[str] = []
    subject = recording_repository(calls)

    subject.load("abc123", 36)
    assert "Talents" in calls

    calls.clear()
    subject.get("abc123", 36)
    assert "Talents" not in calls
```

The file's recording transport dispatches on operation name, so it needs a branch answering `Talents`. Add one that returns the roster's aliases:

```python
    if operation == "Talents":
        return {"reportData": {"report": {"fights": [{"id": 36, "a693": "C4DAAAAA"}]}}}
```

matching however that helper already shapes its responses.

- [ ] **Step 8: Run it and watch it fail**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: FAIL on `assert "Talents" in calls`.

- [ ] **Step 9: Fetch the talents in `load`**

In `src/wowperf/adapters/wcl/repository.py`, add a helper beside `_actor_game_ids`:

```python
    def _talents(self, report_code: str, fight: dict[str, Any]) -> dict[int, str]:
        """The talent import string per player, keyed by actor id.

        A player with no recorded build is left out rather than given an empty
        string: absent and "took no talents" are different claims.
        """
        actor_ids = [int(actor_id) for actor_id in fight.get("friendlyPlayers") or []]
        if not actor_ids:
            return {}

        payload = self._query(
            talents_query(actor_ids), {"code": report_code, "fightId": fight["id"]}
        )
        fights = payload["reportData"]["report"]["fights"] or [{}]
        codes = fights[0]
        return {
            actor_id: codes[f"a{actor_id}"]
            for actor_id in actor_ids
            if codes.get(f"a{actor_id}")
        }
```

Then in `load`, replace `run = build_run(report, fight)` with:

```python
        run = build_run(report, fight, self._talents(report_code, fight))
```

`get` is untouched. Import `talents_query` from `wowperf.adapters.wcl.queries`.

- [ ] **Step 10: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src tests
git commit -m "Fetch each player's talent build alongside their casts

The individual comparison hands the reader an importable string, which is the
only honest way to report a difference between two opaque build codes."
```

---

### Task 6: Pull alignment

**Files:**
- Create: `src/wowperf/domain/comparison/alignment.py`
- Test: `tests/domain/comparison/test_alignment.py`

**Interfaces:**
- Consumes: `Run`, `Pull` from `wowperf.domain.model`; `Frozen`.
- Produces:
  - `class PullMatch(Frozen)`: `ours_index: int`, `theirs_index: int`
  - `class Alignment(Frozen)`: `matched: tuple[PullMatch, ...]`, `only_ours: tuple[int, ...]`, `only_theirs: tuple[int, ...]`; property `out_of_order -> tuple[PullMatch, ...]`
  - `def align_pulls(ours: Run, theirs: Run) -> Alignment`

A pull's identity is `Pull.signature`, which Plan A already defines as the sorted multiset of its enemies' game IDs — duplicates kept, because a pack of three casters and a pack of one caster are different packs. Two pulls match when the groups fought the same pack, not when they fought it at the same time or for the same length.

Alignment is `difflib.SequenceMatcher` and nothing more. A bespoke algorithm here would be architecture for its own sake.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_alignment.py`:

```python
# ABOUTME: Behaviour tests for lining two pull sequences up by what each pack was made of.
# ABOUTME: The interesting cases are a skipped pack, an extra pack, and a reordered route.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.model import EnemyNpc, Pull, Run


def a_pull(index: int, game_ids: tuple[int, ...]) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack",
        encounter_id=0,
        start_ms=index * 100_000,
        end_ms=index * 100_000 + 60_000,
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=100 + n, game_id=game_id) for n, game_id in enumerate(game_ids)),
    )


def a_run(*signatures: tuple[int, ...]) -> Run:
    return Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(),
        pulls=tuple(a_pull(index, ids) for index, ids in enumerate(signatures)),
    )


def test_identical_routes_match_every_pull() -> None:
    alignment = align_pulls(a_run((1, 2), (3,)), a_run((1, 2), (3,)))

    assert [(m.ours_index, m.theirs_index) for m in alignment.matched] == [(0, 0), (1, 1)]
    assert alignment.only_ours == ()
    assert alignment.only_theirs == ()


def test_a_pack_we_killed_and_they_skipped_lands_in_only_ours() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((1,), (3,)))

    assert alignment.only_ours == (1,)
    assert alignment.only_theirs == ()
    assert [(m.ours_index, m.theirs_index) for m in alignment.matched] == [(0, 0), (2, 1)]


def test_a_pack_only_they_killed_lands_in_only_theirs() -> None:
    alignment = align_pulls(a_run((1,), (3,)), a_run((1,), (2,), (3,)))

    assert alignment.only_ours == ()
    assert alignment.only_theirs == (1,)


def test_a_replaced_pack_counts_on_both_sides() -> None:
    alignment = align_pulls(a_run((1,), (2,)), a_run((1,), (9,)))

    assert alignment.only_ours == (1,)
    assert alignment.only_theirs == (1,)


def test_pack_composition_ignores_the_order_enemies_arrive_in() -> None:
    alignment = align_pulls(a_run((2, 1),), a_run((1, 2),))

    assert len(alignment.matched) == 1


def test_a_repeated_pack_is_matched_twice_not_folded_into_one() -> None:
    alignment = align_pulls(a_run((1,), (1,)), a_run((1,), (1,)))

    assert len(alignment.matched) == 2


def test_a_route_run_in_a_different_order_is_reported() -> None:
    ours = a_run((1,), (2,), (3,))
    theirs = a_run((2,), (1,), (3,))

    alignment = align_pulls(ours, theirs)
    reordered = [(m.ours_index, m.theirs_index) for m in alignment.out_of_order]

    assert reordered, "a route taken in a different order should be visible"


def test_a_route_in_the_same_order_reports_nothing_out_of_order() -> None:
    alignment = align_pulls(a_run((1,), (2,), (3,)), a_run((1,), (2,), (3,)))

    assert alignment.out_of_order == ()


def test_two_empty_routes_align_without_raising() -> None:
    alignment = align_pulls(a_run(), a_run())

    assert alignment.matched == ()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_alignment.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.alignment'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/alignment.py`:

```python
# ABOUTME: Lines our pull sequence up against a reference run's, by what each pack was made of.
# ABOUTME: Pure sequence matching over enemy game IDs; no Warcraft Logs vocabulary reaches here.

from difflib import SequenceMatcher

from wowperf.domain.base import Frozen
from wowperf.domain.model import Run


class PullMatch(Frozen):
    """One of our pulls paired with the pull of theirs that fought the same pack."""

    ours_index: int
    theirs_index: int


class Alignment(Frozen):
    """What two routes had in common, and what each did alone."""

    matched: tuple[PullMatch, ...] = ()
    only_ours: tuple[int, ...] = ()
    only_theirs: tuple[int, ...] = ()

    @property
    def out_of_order(self) -> tuple[PullMatch, ...]:
        """Matched pulls the two groups reached in a different relative order.

        Walking our pulls in order, any match that points further back in their
        route than a match we have already passed is a pack the two groups took
        at different points on the route.
        """
        furthest = -1
        drifted = []
        for match in sorted(self.matched, key=lambda pair: pair.ours_index):
            if match.theirs_index < furthest:
                drifted.append(match)
            else:
                furthest = match.theirs_index
        return tuple(drifted)


def align_pulls(ours: Run, theirs: Run) -> Alignment:
    """Pair our pulls with theirs on pack composition, using the standard library.

    `Pull.signature` is the sorted multiset of the pack's enemy game IDs, so
    order within a pack does not matter and a repeated pack stays two packs.
    """
    ours_signatures = [pull.signature for pull in ours.pulls]
    theirs_signatures = [pull.signature for pull in theirs.pulls]

    # autojunk discards elements that appear in more than 1% of a sequence longer
    # than 200. A dungeon has a dozen pulls so it would never fire today, but the
    # element it would discard is exactly a pack repeated along a route, and
    # silently dropping those is the failure that would be hardest to notice.
    matcher = SequenceMatcher(a=ours_signatures, b=theirs_signatures, autojunk=False)

    matched: list[PullMatch] = []
    only_ours: list[int] = []
    only_theirs: list[int] = []
    for tag, ours_from, ours_to, theirs_from, theirs_to in matcher.get_opcodes():
        if tag == "equal":
            matched.extend(
                PullMatch(
                    ours_index=ours.pulls[i].index,
                    theirs_index=theirs.pulls[j].index,
                )
                for i, j in zip(range(ours_from, ours_to), range(theirs_from, theirs_to),
                                strict=True)
            )
            continue
        # delete, insert and replace all reduce to "these were only ours" and
        # "these were only theirs"; an empty range on either side handles itself.
        only_ours.extend(ours.pulls[i].index for i in range(ours_from, ours_to))
        only_theirs.extend(theirs.pulls[j].index for j in range(theirs_from, theirs_to))

    return Alignment(
        matched=tuple(matched),
        only_ours=tuple(only_ours),
        only_theirs=tuple(only_theirs),
    )
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_alignment.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/alignment.py tests/domain/comparison/test_alignment.py
git commit -m "Align two routes by what each pack was made of

Matching on composition rather than on timing is what makes a comparison
survive a keystone-level gap, where every duration stops meaning the same thing."
```

---

### Task 7: Route findings — what they skipped, what we killed for nothing

**Files:**
- Create: `src/wowperf/domain/comparison/route.py`
- Test: `tests/domain/comparison/test_route.py`

**Interfaces:**
- Consumes: `Alignment`, `align_pulls` from Task 6; `Run`, `Pull` from `wowperf.domain.model`; `Finding`, `Confidence` from `wowperf.domain.findings`.
- Produces:
  - `def compare_route(ours: Run, theirs: Run, alignment: Alignment) -> list[Finding]`
  - `MAX_PACKS_REPORTED: int = 5`

Every number here is `measured` and every one of them is **ours**. A pack we killed and they skipped costs us the seconds *our* clock recorded for that pull, which is true whatever keystone level either group ran — this is the finding that survives the gap §6.4 describes, and it is usually the largest one the comparison produces.

Three rules a reviewer will check:

1. **Only trash pulls can be skipped.** A boss in `only_ours` means the reference is not the same dungeon route, not that the group skipped a boss. Exclude bosses from the skipped findings and say so.
2. **A pack only they killed carries no seconds.** We have no clock for a pull we never did, and pricing it with *their* duration would import a number from the other side of a keystone gap.
3. **Forces come from our own `npc_count_map`.** The reference's map may differ if the season retuned; ours is the one that priced our run.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_route.py`:

```python
# ABOUTME: Behaviour tests for turning a route alignment into findings a reader can act on.
# ABOUTME: The headline is what a faster group skipped, priced with our own clock.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.route import MAX_PACKS_REPORTED, compare_route
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Pull, Run


def a_pull(index: int, game_ids: tuple[int, ...], seconds: float = 60.0, boss: bool = False) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Boss" if boss else "Pack",
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + int(seconds * 1000),
        killed=True,
        x=100 + index,
        y=200 + index,
        enemies=tuple(
            EnemyNpc(actor_id=100 + n, game_id=game_id) for n, game_id in enumerate(game_ids)
        ),
    )


def a_run(pulls: tuple[Pull, ...], counts: tuple[tuple[int, int], ...] = ()) -> Run:
    return Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=counts,
        players=(),
        pulls=pulls,
    )


def findings_by_prefix(findings: list, prefix: str) -> list:
    return [finding for finding in findings if finding.id.startswith(prefix)]


def test_a_pack_they_skipped_is_priced_with_our_own_clock() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,), seconds=45.0), a_pull(2, (3,))),
                 counts=((2, 12),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    skipped = findings_by_prefix(findings, "compare.route.skipped.")

    assert len(skipped) == 1
    assert skipped[0].seconds_lost == 45.0
    assert skipped[0].confidence is Confidence.MEASURED
    assert skipped[0].pull_index == 1
    assert any("12" in line for line in skipped[0].evidence)


def test_a_boss_is_never_reported_as_a_skipped_pack() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (99,), boss=True)))
    theirs = a_run((a_pull(0, (1,)),))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))

    assert findings_by_prefix(findings, "compare.route.skipped.") == []


def test_a_pack_only_they_killed_carries_no_seconds() -> None:
    ours = a_run((a_pull(0, (1,)),))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, theirs, align_pulls(ours, theirs))
    extra = findings_by_prefix(findings, "compare.route.extra.")

    assert len(extra) == 1
    assert extra[0].seconds_lost is None


def test_the_summary_counts_both_routes() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))
    theirs = a_run((a_pull(0, (1,)),))

    summary = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.summary")[0]

    assert "2" in summary.title
    assert "1" in summary.title
    assert summary.seconds_lost is None


def test_only_the_worst_packs_are_reported() -> None:
    # Eight packs they skipped, each one second shorter than the last.
    skipped = tuple(a_pull(index, (index + 10,), seconds=float(60 - index)) for index in range(1, 9))
    ours = a_run((a_pull(0, (1,)), *skipped))
    theirs = a_run((a_pull(0, (1,)),))

    skipped = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                                 "compare.route.skipped.")

    assert len(skipped) == MAX_PACKS_REPORTED
    seconds = [finding.seconds_lost for finding in skipped]
    assert seconds == sorted(seconds, reverse=True)


def test_a_reordered_route_is_reported_once() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (3,))))
    theirs = a_run((a_pull(0, (2,)), a_pull(1, (1,)), a_pull(2, (3,))))

    order = findings_by_prefix(compare_route(ours, theirs, align_pulls(ours, theirs)),
                               "compare.route.order")

    assert len(order) <= 1


def test_identical_routes_report_only_the_summary() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,))))

    findings = compare_route(ours, ours, align_pulls(ours, ours))

    assert [finding.id for finding in findings] == ["compare.route.summary"]


def test_every_finding_id_is_unique() -> None:
    ours = a_run((a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (4,))))
    theirs = a_run((a_pull(0, (1,)), a_pull(1, (3,))))

    ids = [finding.id for finding in compare_route(ours, theirs, align_pulls(ours, theirs))]

    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_route.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.route'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/route.py`:

```python
# ABOUTME: Turns a route alignment into findings: what a faster group skipped, and what we added.
# ABOUTME: Every second here is measured on our own clock, so a keystone gap cannot distort it.

from wowperf.domain.comparison.alignment import Alignment
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Pull, Run

MAX_PACKS_REPORTED = 5
"""Beyond five packs a reader stops reading and starts skimming."""


def _forces(run: Run, pull: Pull) -> int:
    """Enemy forces the pack awarded, priced by our own run's map.

    The reference's map may differ if the season retuned between the two runs;
    ours is the one that actually counted towards our key.
    """
    counts = run.npc_count_map
    return sum(counts.get(enemy.game_id, 0) for enemy in pull.enemies)


def _pull_by_index(run: Run, index: int) -> Pull | None:
    return next((pull for pull in run.pulls if pull.index == index), None)


def compare_route(ours: Run, theirs: Run, alignment: Alignment) -> list[Finding]:
    """What the two routes did differently, priced where we honestly can."""
    findings: list[Finding] = [
        Finding(
            id="compare.route.summary",
            title=(
                f"We pulled {len(ours.pulls)} packs, the reference pulled {len(theirs.pulls)}"
            ),
            detail=(
                f"{len(alignment.matched)} packs matched on composition. Packs are matched by "
                "which enemies they contain, not by when either group fought them, so this "
                "comparison holds across a keystone-level difference."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(
                f"{len(alignment.matched)} packs in common",
                f"{len(alignment.only_ours)} only ours",
                f"{len(alignment.only_theirs)} only theirs",
            ),
        )
    ]

    skippable = [
        pull
        for index in alignment.only_ours
        # A boss in only_ours means the reference took a different route through
        # the dungeon, not that anyone skipped a boss.
        if (pull := _pull_by_index(ours, index)) is not None and not pull.is_boss
    ]
    skippable.sort(key=lambda pull: pull.duration_seconds, reverse=True)

    for rank, pull in enumerate(skippable[:MAX_PACKS_REPORTED]):
        forces = _forces(ours, pull)
        findings.append(
            Finding(
                id=f"compare.route.skipped.{rank}",
                title=f"The reference skipped the pack at pull {pull.index}",
                detail=(
                    f"We spent {pull.duration_seconds:.0f}s on a pack the faster group never "
                    f"pulled. It awarded {forces} enemy forces."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=pull.duration_seconds,
                evidence=(
                    f"{forces} enemy forces",
                    f"{len(pull.enemies)} enemies",
                    f"map position x={pull.x}, y={pull.y}",
                ),
                pull_index=pull.index,
            )
        )

    extra = [
        pull
        for index in alignment.only_theirs
        if (pull := _pull_by_index(theirs, index)) is not None and not pull.is_boss
    ]
    for rank, pull in enumerate(extra[:MAX_PACKS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.route.extra.{rank}",
                title=f"The reference pulled a pack we did not, at their pull {pull.index}",
                detail=(
                    "They killed a pack that is not on our route. No seconds are attached: we "
                    "have no clock for a pull we never did, and theirs was run at a different "
                    "keystone level."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"{len(pull.enemies)} enemies",
                    f"their pull lasted {pull.duration_seconds:.0f}s",
                ),
            )
        )

    drifted = alignment.out_of_order
    if drifted:
        findings.append(
            Finding(
                id="compare.route.order",
                title=f"{len(drifted)} packs were taken in a different order",
                detail=(
                    "The same packs appear on both routes but in a different sequence. That is "
                    "usually a different path through the dungeon rather than a mistake, and it "
                    "is worth looking at next to the skipped packs above."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=tuple(
                    f"our pull {match.ours_index} is their pull {match.theirs_index}"
                    for match in drifted[:MAX_PACKS_REPORTED]
                ),
            )
        )

    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_route.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/route.py tests/domain/comparison/test_route.py
git commit -m "Price the packs a faster group skipped

A pack we killed and they did not costs the seconds our own clock recorded,
which is the one comparison a keystone-level gap cannot distort."
```

---

### Task 8: Tempo findings, and the durations we refuse to print

**Files:**
- Create: `src/wowperf/domain/comparison/tempo.py`
- Test: `tests/domain/comparison/test_tempo.py`

**Interfaces:**
- Consumes: `Comparability` from Task 2; `gaps_between_pulls` from `wowperf.domain.analysis.timeline`; `reconstruct_enemy_casts` from `wowperf.domain.analysis.interrupts`; `LoadedRun`; `Finding`, `Confidence`.
- Produces: `def compare_tempo(ours: LoadedRun, theirs: LoadedRun, rule: Comparability) -> list[Finding]`

This is §6.4 made concrete. Three comparisons survive a keystone gap and one does not:

- **Downtime** between pulls is walking, not fighting, so it does not scale with enemy health. `gaps_between_pulls` already computes it and is already tested; reuse it rather than writing a second definition of the same thing.
- **Deaths** are a count. `seconds_lost` stays `None`: the deaths analyser has already priced our own deaths in seconds, and pricing them again here would double-count the same loss in one report.
- **Missed interrupts** are a count from a documented reconstruction, so `derived`.
- **Total time** is duration-shaped. When the levels differ, the finding says the comparison was withheld and why, rather than being dropped — a reader who sees nothing assumes nothing was wrong.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_tempo.py`:

```python
# ABOUTME: Behaviour tests for the group-axis comparisons that are not about the route.
# ABOUTME: The important one is the refusal: a duration is never printed across a key gap.

from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.comparison.tempo import compare_tempo
from wowperf.domain.events import Death, EnemyCastRow, InterruptEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Pull, Run


def a_pull(index: int, start_s: float, seconds: float) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack",
        encounter_id=0,
        start_ms=int(start_s * 1000),
        end_ms=int((start_s + seconds) * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def a_loaded(
    *,
    level: int = 16,
    pulls: tuple[Pull, ...] = (),
    deaths: int = 0,
    kicked: int = 0,
    landed: int = 0,
    time_s: float = 1909.0,
) -> LoadedRun:
    run = Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=level,
        affix_ids=(9, 10, 147),
        keystone_time_ms=int(time_s * 1000),
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(),
        pulls=pulls,
    )
    rows = []
    interrupts = []
    for n in range(kicked + landed):
        rows.append(
            EnemyCastRow(
                source_id=500 + n,
                source_instance=0,
                ability_id=1000,
                ability_name="Shoot",
                timestamp_ms=n * 10_000,
                is_start=True,
            )
        )
        rows.append(
            EnemyCastRow(
                source_id=500 + n,
                source_instance=0,
                ability_id=1000,
                ability_name="Shoot",
                timestamp_ms=n * 10_000 + 1_000,
                is_start=False,
            )
        )
        if n < kicked:
            interrupts.append(
                InterruptEvent(
                    player_name="Uglymage",
                    actor_id=693,
                    interrupted_ability_id=1000,
                    target_id=500 + n,
                    target_instance=0,
                    timestamp_ms=n * 10_000 + 500,
                )
            )
    return LoadedRun(
        run=run,
        deaths=tuple(
            Death(player_name="Uglymage", actor_id=693, timestamp_ms=n, killing_blow="X")
            for n in range(deaths)
        ),
        enemy_cast_rows=tuple(rows),
        interrupts=tuple(interrupts),
    )


def one(findings: list, finding_id: str):
    matches = [finding for finding in findings if finding.id == finding_id]
    assert len(matches) == 1, f"expected exactly one {finding_id}, got {len(matches)}"
    return matches[0]


def test_our_extra_downtime_is_measured_and_priced() -> None:
    # Ours: 40s of walking between two pulls. Theirs: 10s.
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    theirs = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 70, 60)))

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.downtime")

    assert finding.seconds_lost == 30.0
    assert finding.confidence is Confidence.MEASURED


def test_less_downtime_than_the_reference_costs_nothing() -> None:
    ours = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 70, 60)))
    theirs = a_loaded(pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.downtime")

    assert finding.seconds_lost is None


def test_deaths_are_counted_and_never_priced_twice() -> None:
    ours = a_loaded(deaths=4)
    theirs = a_loaded(deaths=0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.deaths")

    assert "4" in finding.title
    assert finding.seconds_lost is None
    assert any("deaths.total" in line for line in finding.evidence)


def test_missed_interrupts_are_derived_not_measured() -> None:
    ours = a_loaded(kicked=1, landed=3)
    theirs = a_loaded(kicked=3, landed=1)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.interrupts")

    assert finding.confidence is Confidence.DERIVED


def test_equal_levels_compare_the_total_time() -> None:
    ours = a_loaded(time_s=1909.0)
    theirs = a_loaded(time_s=1379.0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16)),
                  "compare.duration")

    assert finding.seconds_lost == 530.0
    assert finding.confidence is Confidence.MEASURED


def test_a_level_gap_withholds_the_duration_and_says_why() -> None:
    ours = a_loaded(level=16, time_s=1909.0)
    theirs = a_loaded(level=17, time_s=1379.0)

    finding = one(compare_tempo(ours, theirs, Comparability(our_level=16, their_level=17)),
                  "compare.duration")

    assert finding.seconds_lost is None
    assert "not comparable" in finding.detail
    assert "1379" not in finding.detail, "a withheld number must not appear anyway"


def test_a_run_with_no_pulls_compares_without_raising() -> None:
    findings = compare_tempo(a_loaded(), a_loaded(),
                             Comparability(our_level=16, their_level=16))

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(deaths=2, kicked=1, landed=1, pulls=(a_pull(0, 0, 60), a_pull(1, 100, 60)))
    theirs = a_loaded(deaths=0, kicked=2, landed=0)

    ids = [f.id for f in compare_tempo(ours, theirs, Comparability(our_level=16, their_level=16))]

    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_tempo.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.tempo'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/tempo.py`:

```python
# ABOUTME: Compares deaths, missed interrupts and downtime against a reference run.
# ABOUTME: Withholds every duration-shaped number when the two keystone levels differ.

from wowperf.domain.analysis.interrupts import reconstruct_enemy_casts
from wowperf.domain.analysis.timeline import gaps_between_pulls
from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun


def _downtime_seconds(loaded: LoadedRun) -> float:
    """Seconds spent between pulls — walking, not fighting.

    Reuses the timeline analyser's definition so the report never carries two
    different numbers for the same idea.
    """
    return sum(gap.seconds for gap in gaps_between_pulls(loaded.run))


def _kick_counts(loaded: LoadedRun) -> tuple[int, int]:
    """(kicked, landed) enemy casts, by the documented reconstruction rule."""
    casts = reconstruct_enemy_casts(loaded.enemy_cast_rows, loaded.interrupts)
    kicked = sum(1 for cast in casts if cast.was_kicked)
    landed = sum(1 for cast in casts if cast.landed)
    return kicked, landed


def compare_tempo(ours: LoadedRun, theirs: LoadedRun, rule: Comparability) -> list[Finding]:
    """The group-axis comparisons that are not about the route."""
    findings: list[Finding] = []

    our_downtime = _downtime_seconds(ours)
    their_downtime = _downtime_seconds(theirs)
    excess = our_downtime - their_downtime
    findings.append(
        Finding(
            id="compare.downtime",
            title=(
                f"We spent {our_downtime:.0f}s between packs, the reference spent "
                f"{their_downtime:.0f}s"
            ),
            detail=(
                "Time between pulls is travel, run-backs and waiting. It does not depend on how "
                "much health a mob had, so it compares cleanly even across a keystone-level gap."
            ),
            confidence=Confidence.MEASURED,
            # Only an excess is a loss. Beating the reference is not worth negative seconds.
            seconds_lost=excess if excess > 0 else None,
            evidence=(
                f"ours {our_downtime:.0f}s",
                f"theirs {their_downtime:.0f}s",
                f"{len(gaps_between_pulls(ours.run))} gaps on our route",
            ),
        )
    )

    findings.append(
        Finding(
            id="compare.deaths",
            title=f"We died {len(ours.deaths)} times, the reference died {len(theirs.deaths)}",
            detail=(
                "A death count compares across keystone levels; what a death costs does not "
                "need restating here."
            ),
            confidence=Confidence.MEASURED,
            # deaths.total already prices our deaths in seconds. Pricing them again
            # here would count the same loss twice in one report.
            seconds_lost=None,
            evidence=(
                f"ours {len(ours.deaths)}",
                f"theirs {len(theirs.deaths)}",
                "seconds for our own deaths are reported by deaths.total",
            ),
        )
    )

    our_kicked, our_landed = _kick_counts(ours)
    their_kicked, their_landed = _kick_counts(theirs)
    findings.append(
        Finding(
            id="compare.interrupts",
            title=(
                f"We kicked {our_kicked} of {our_kicked + our_landed} resolved casts, "
                f"the reference kicked {their_kicked} of {their_kicked + their_landed}"
            ),
            detail=(
                "Outcomes are reconstructed on both sides by the same documented rule, and "
                "casts the log does not resolve are excluded rather than counted as missed. "
                "Neither side's log records which casts could be interrupted at all."
            ),
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"ours {our_kicked} kicked, {our_landed} landed",
                f"theirs {their_kicked} kicked, {their_landed} landed",
            ),
        )
    )

    if rule.durations_comparable:
        our_time = ours.run.keystone_time_seconds
        their_time = theirs.run.keystone_time_seconds
        behind = our_time - their_time
        findings.append(
            Finding(
                id="compare.duration",
                title=f"We finished in {our_time:.0f}s, the reference in {their_time:.0f}s",
                detail=(
                    "Both runs are the same keystone level, so the official times mean the same "
                    "thing and can be compared directly."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=behind if behind > 0 else None,
                evidence=(f"ours {our_time:.0f}s", f"theirs {their_time:.0f}s"),
            )
        )
    else:
        findings.append(
            Finding(
                id="compare.duration",
                title="Completion times are not compared",
                detail=rule.withheld_because(),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"our key +{rule.our_level}",
                    f"reference key +{rule.their_level}",
                    "route, deaths, interrupts and downtime are still compared",
                ),
            )
        )

    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_tempo.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/tempo.py tests/domain/comparison/test_tempo.py
git commit -m "Compare downtime, deaths and interrupts, and refuse to compare times

A withheld comparison is stated rather than dropped: a reader who sees nothing
concludes nothing was wrong, which is the opposite of what silence means here."
```

---

### Task 9: Spells and talents, on boss pulls only

**Files:**
- Create: `src/wowperf/domain/comparison/spells.py`
- Test: `tests/domain/comparison/test_spells.py`

**Interfaces:**
- Consumes: `LoadedRun`, `Run`, `Player`, `CastEvent`; `Finding`, `Confidence`.
- Produces:
  - `def boss_seconds(run: Run) -> float`
  - `def boss_casts(run: Run, casts: tuple[CastEvent, ...], actor_id: int) -> dict[int, tuple[str, int]]` — ability id to (name, count)
  - `def compare_spells(ours: LoadedRun, our_player: Player, theirs: LoadedRun, their_name: str) -> list[Finding]`
  - `def compare_talents(our_player: Player, their_player: Player | None) -> list[Finding]`
  - `MAX_SPELLS_REPORTED: int = 5`, `MIN_CASTS_TO_COMPARE: int = 3`, `RATE_GAP_MULTIPLE: float = 1.5`

**Boss pulls only, and this is the whole point of the task.** Across trash, an ability ratio is dominated by pull size and route: comparing an area-of-effect pull against a single-target pull says nothing about play. Boss pulls are a fixed, comparable encounter. Restricting to them costs coverage and buys validity.

Three rules:

1. **"Never cast" means never cast anywhere in the run**, not merely never cast on a boss. It is the stronger and more useful claim, and it is a plain set difference — the highest-signal comparison §6.5 lists, with no modelling in it at all.
2. **A rate needs a floor.** An ability the reference cast twice tells us nothing; `MIN_CASTS_TO_COMPARE` keeps a single stray cast from becoming a finding.
3. **A talent comparison prints their string.** The import code is opaque; diffing base64 would produce noise. Report that the builds differ and hand over the string.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_spells.py`:

```python
# ABOUTME: Behaviour tests for the individual comparison: which spells and which build.
# ABOUTME: Everything here is restricted to boss pulls, where the encounter is the same fight.

from wowperf.domain.comparison.spells import (
    MIN_CASTS_TO_COMPARE,
    boss_casts,
    boss_seconds,
    compare_spells,
    compare_talents,
)
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Player, Pull, Run

OURS = Player(actor_id=693, name="Uglymage", class_name="Mage", spec="Arcane", item_level=318)
THEIRS = Player(
    actor_id=11,
    name="Críms",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPAAAAA",
)


def boss_pull(index: int, seconds: float) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Nalorakk",
        encounter_id=2607,
        start_ms=index * 400_000,
        end_ms=index * 400_000 + int(seconds * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def trash_pull(index: int, seconds: float) -> Pull:
    pull = boss_pull(index, seconds)
    return pull.model_copy(update={"encounter_id": 0, "name": "Pack"})


def a_loaded(player: Player, pulls: tuple[Pull, ...], casts: tuple[CastEvent, ...]) -> LoadedRun:
    run = Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(player,),
        pulls=pulls,
    )
    return LoadedRun(run=run, casts=casts)


def cast(actor_id: int, ability_id: int, name: str, at_ms: int, pull: int | None) -> CastEvent:
    return CastEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        timestamp_ms=at_ms,
        pull_index=pull,
    )


def test_boss_seconds_counts_only_boss_pulls() -> None:
    run = a_loaded(OURS, (boss_pull(0, 120.0), trash_pull(1, 60.0), boss_pull(2, 60.0)), ()).run

    assert boss_seconds(run) == 180.0


def test_boss_casts_ignore_trash_and_other_players() -> None:
    pulls = (boss_pull(0, 120.0), trash_pull(1, 60.0))
    casts = (
        cast(693, 30451, "Arcane Blast", 1_000, 0),
        cast(693, 30451, "Arcane Blast", 2_000, 0),
        cast(693, 30451, "Arcane Blast", 3_000, 1),
        cast(693, 30451, "Arcane Blast", 4_000, None),
        cast(7, 30451, "Arcane Blast", 5_000, 0),
    )
    run = a_loaded(OURS, pulls, casts).run

    counted = boss_casts(run, casts, actor_id=693)

    assert counted == {30451: ("Arcane Blast", 2)}


def test_an_ability_they_cast_and_we_never_did_is_reported() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 120.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 120.0),),
        (
            cast(11, 30451, "Arcane Blast", 1_000, 0),
            cast(11, 153626, "Arcane Orb", 2_000, 0),
            cast(11, 153626, "Arcane Orb", 3_000, 0),
        ),
    )

    findings = compare_spells(ours, OURS, theirs, "Críms")
    missing = [f for f in findings if f.id.startswith("compare.spells.missing.")]

    assert len(missing) == 1
    assert "Arcane Orb" in missing[0].title
    assert missing[0].confidence is Confidence.MEASURED
    assert missing[0].seconds_lost is None


def test_an_ability_we_cast_only_on_trash_still_counts_as_cast() -> None:
    ours = a_loaded(
        OURS,
        (boss_pull(0, 120.0), trash_pull(1, 60.0)),
        (cast(693, 153626, "Arcane Orb", 200_000, 1),),
    )
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 120.0),),
        tuple(cast(11, 153626, "Arcane Orb", n * 1_000, 0) for n in range(4)),
    )

    missing = [
        f for f in compare_spells(ours, OURS, theirs, "Críms")
        if f.id.startswith("compare.spells.missing.")
    ]

    assert missing == []


def test_a_rate_gap_on_a_shared_ability_is_derived() -> None:
    ours = a_loaded(
        OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),)
    )
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 30451, "Arcane Blast", n * 1_000, 0) for n in range(6)),
    )

    rates = [
        f for f in compare_spells(ours, OURS, theirs, "Críms")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert len(rates) == 1
    assert rates[0].confidence is Confidence.DERIVED
    assert "Arcane Blast" in rates[0].title


def test_a_reference_cast_too_few_times_is_not_a_rate_finding() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(
            cast(11, 30451, "Arcane Blast", n * 1_000, 0)
            for n in range(MIN_CASTS_TO_COMPARE - 1)
        ),
    )

    rates = [
        f for f in compare_spells(ours, OURS, theirs, "Críms")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert rates == []


def test_a_reference_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(THEIRS, (trash_pull(0, 60.0),), ())

    findings = compare_spells(ours, OURS, theirs, "Críms")

    assert any(f.id == "compare.spells.unavailable" for f in findings)


def test_a_different_build_is_reported_with_their_string() -> None:
    finding = compare_talents(OURS.model_copy(update={"talent_import_string": "C4DAAAAA"}),
                              THEIRS)[0]

    assert finding.id == "compare.talents"
    assert finding.confidence is Confidence.MEASURED
    assert any("CoPAAAAA" in line for line in finding.evidence)


def test_an_identical_build_reports_that_it_matches() -> None:
    same = OURS.model_copy(update={"talent_import_string": "CoPAAAAA"})

    finding = compare_talents(same, THEIRS)[0]

    assert "matches" in finding.title.lower()


def test_a_missing_build_says_the_comparison_could_not_be_made() -> None:
    finding = compare_talents(OURS, THEIRS)[0]

    assert "not" in finding.detail.lower()
    assert finding.seconds_lost is None


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 100 + n, f"Spell {n}", n * 1_000, 0) for n in range(8) for _ in range(4)),
    )

    ids = [f.id for f in compare_spells(ours, OURS, theirs, "Críms")]

    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_spells.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.spells'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/spells.py`:

```python
# ABOUTME: Compares one player's boss-pull casts and talent build against a top parse.
# ABOUTME: Boss pulls only: across trash an ability ratio measures the route, not the player.

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.events import CastEvent
from wowperf.domain.model import LoadedRun, Player, Run

MAX_SPELLS_REPORTED = 5
MIN_CASTS_TO_COMPARE = 3
"""Below this, the reference's own sample is too small to argue from."""

RATE_GAP_MULTIPLE = 1.5
"""How much more often they must cast something before it is worth reporting."""


def boss_seconds(run: Run) -> float:
    """Seconds spent on boss pulls — the only stretch where two runs fought the same thing."""
    return sum(pull.duration_seconds for pull in run.boss_pulls)


def boss_casts(
    run: Run, casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    """One player's casts inside boss pulls, as ability id to (name, count)."""
    boss_indices = {pull.index for pull in run.boss_pulls}
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or event.pull_index not in boss_indices:
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted


def _all_cast_ability_ids(casts: tuple[CastEvent, ...], actor_id: int) -> set[int]:
    """Every ability the player cast anywhere in the run, boss pull or not."""
    return {event.ability_id for event in casts if event.actor_id == actor_id}


def _their_actor_id(theirs: LoadedRun, their_name: str) -> int | None:
    folded = their_name.casefold()
    for player in theirs.run.players:
        if player.name.casefold() == folded:
            return player.actor_id
    return None


def compare_spells(
    ours: LoadedRun, our_player: Player, theirs: LoadedRun, their_name: str
) -> list[Finding]:
    """What the reference player cast on bosses that we did not, and how often."""
    their_actor_id = _their_actor_id(theirs, their_name)
    their_boss_seconds = boss_seconds(theirs.run)
    our_boss_seconds = boss_seconds(ours.run)

    if their_actor_id is None or their_boss_seconds <= 0 or our_boss_seconds <= 0:
        return [
            Finding(
                id="compare.spells.unavailable",
                title="The spell comparison could not be made",
                detail=(
                    "A spell comparison needs boss pulls on both sides and the reference "
                    "player present in their own report. One of those is missing, so no "
                    "ability numbers are reported rather than numbers from an unlike sample."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"our boss time {our_boss_seconds:.0f}s",
                    f"their boss time {their_boss_seconds:.0f}s",
                    f"reference player {their_name!r} "
                    f"{'found' if their_actor_id is not None else 'not found'}",
                ),
            )
        ]

    theirs_on_bosses = boss_casts(theirs.run, theirs.casts, their_actor_id)
    ours_on_bosses = boss_casts(ours.run, ours.casts, our_player.actor_id)
    ours_anywhere = _all_cast_ability_ids(ours.casts, our_player.actor_id)

    findings: list[Finding] = []

    # 1. Abilities they cast and we never cast at all. A set difference: the
    #    highest-signal comparison the design lists, and the one with no modelling in it.
    never = sorted(
        (
            (ability_id, name, count)
            for ability_id, (name, count) in theirs_on_bosses.items()
            if ability_id not in ours_anywhere
        ),
        key=lambda row: row[2],
        reverse=True,
    )
    for rank, (ability_id, name, count) in enumerate(never[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.missing.{rank}",
                title=f"{their_name} cast {name} {count} times on bosses; {our_player.name} never cast it",
                detail=(
                    f"{name} does not appear anywhere in this run for {our_player.name} — not "
                    "on bosses and not on trash. That is either a talent not taken or a button "
                    "not pressed; the log cannot tell which."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"{count} casts across {their_boss_seconds:.0f}s of their boss pulls",
                    "zero casts in the whole of our run",
                ),
            )
        )

    # 2. Abilities both cast, where their rate on bosses is materially higher.
    gaps = []
    for ability_id, (name, their_count) in theirs_on_bosses.items():
        if their_count < MIN_CASTS_TO_COMPARE or ability_id not in ours_on_bosses:
            continue
        our_count = ours_on_bosses[ability_id][1]
        their_rate = their_count / their_boss_seconds * 60
        our_rate = our_count / our_boss_seconds * 60
        if our_rate <= 0 or their_rate / our_rate < RATE_GAP_MULTIPLE:
            continue
        gaps.append((their_rate - our_rate, ability_id, name, our_rate, their_rate))
    gaps.sort(reverse=True)

    for rank, (_, ability_id, name, our_rate, their_rate) in enumerate(gaps[:MAX_SPELLS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.spells.rate.{rank}",
                title=(
                    f"{their_name} cast {name} {their_rate:.1f} times a minute on bosses, "
                    f"{our_player.name} {our_rate:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of boss-pull time, which is the one stretch "
                    "of a dungeon where two runs fought the same encounter. A longer fight at a "
                    "higher key changes how many cooldowns fit, so treat a small gap as noise."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_boss_seconds:.0f}s of boss pulls",
                    f"theirs over {their_boss_seconds:.0f}s of boss pulls",
                ),
            )
        )

    return findings


def compare_talents(our_player: Player, their_player: Player | None) -> list[Finding]:
    """Whether the two builds differ, and the string needed to import theirs."""
    ours = our_player.talent_import_string
    theirs = their_player.talent_import_string if their_player else None

    if ours is None or theirs is None:
        return [
            Finding(
                id="compare.talents",
                title="The talent builds could not be compared",
                detail=(
                    "One of the two reports does not carry a talent import string for its "
                    "player, so the builds are not compared. An absent string is not evidence "
                    "that the builds match."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ours {'present' if ours else 'absent'}",
                    f"theirs {'present' if theirs else 'absent'}",
                ),
            )
        ]

    if ours == theirs:
        return [
            Finding(
                id="compare.talents",
                title="The talent build matches the reference",
                detail="Both players imported the same build, so nothing here needs changing.",
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=("identical import strings",),
            )
        ]

    return [
        Finding(
            id="compare.talents",
            title="The talent build differs from the reference",
            detail=(
                "The import codes differ. They are opaque, so the difference is not spelled out "
                "here — paste the reference's string into the game to see it laid out on the "
                "tree. A different build is not automatically a worse one."
            ),
            confidence=Confidence.MEASURED,
            seconds_lost=None,
            evidence=(f"theirs: {theirs}", f"ours: {ours}"),
        )
    ]
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_spells.py -v`
Expected: 11 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/spells.py tests/domain/comparison/test_spells.py
git commit -m "Compare one player's boss casts and build against a top parse

Restricting to boss pulls costs coverage and buys validity: across trash an
ability ratio measures the route the group took, not the player."
```

---

### Task 10: The confounds we declare rather than correct

**Files:**
- Create: `src/wowperf/domain/comparison/confounds.py`
- Test: `tests/domain/comparison/test_confounds.py`

**Interfaces:**
- Consumes: `LoadedRun`, `Player`; `Comparability`; `Finding`, `Confidence`.
- Produces:
  - `def declare_confounds(ours: LoadedRun, theirs: LoadedRun, rule: Comparability) -> list[Finding]`
  - `ITEM_LEVEL_GAP: int = 5`

§6.6 names three confounds that are large, uncorrectable, and must be stated rather than adjusted away. All of these read facts straight off two rosters, so they are `measured` — what is inferred is the *consequence*, and the detail says so in words rather than hiding it in a badge.

The Augmentation Evoker case is the sharpest: Blizzard's support-attribution hooks are documented as faulty, so throughput debuffs go unaccounted, reattribution can subtract damage, and shared health pools generate duplicate events. When either roster contains one, per-player damage attribution is unreliable on that side and no amount of arithmetic here fixes it.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_confounds.py`:

```python
# ABOUTME: Behaviour tests for the confounds a comparison declares instead of correcting.
# ABOUTME: Each one is read straight off a roster, so the fact is measured even where the risk is not.

from wowperf.domain.comparison.confounds import ITEM_LEVEL_GAP, declare_confounds
from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Player, Run

SAME_LEVEL = Comparability(our_level=16, their_level=16)


def player(name: str, class_name: str, spec: str, item_level: int = 318) -> Player:
    return Player(
        actor_id=abs(hash(name)) % 1000,
        name=name,
        class_name=class_name,
        spec=spec,
        item_level=item_level,
    )


def a_loaded(players: tuple[Player, ...], level: int = 16) -> LoadedRun:
    return LoadedRun(
        run=Run(
            report_code="abc123",
            fight_id=36,
            dungeon_name="Den of Nalorakk",
            encounter_id=12825,
            keystone_level=level,
            affix_ids=(9, 10, 147),
            keystone_time_ms=1_909_000,
            keystone_bonus=1,
            count_reached=744,
            count_required=729,
            npc_counts=(),
            players=players,
            pulls=(),
        )
    )


ROSTER = (
    player("Dudesons", "DeathKnight", "Blood"),
    player("Uglymage", "Mage", "Arcane"),
)


def ids(findings: list) -> set[str]:
    return {finding.id for finding in findings}


def test_an_augmentation_evoker_on_either_side_is_declared() -> None:
    theirs = a_loaded((*ROSTER, player("Augbot", "Evoker", "Augmentation")))

    findings = declare_confounds(a_loaded(ROSTER), theirs, SAME_LEVEL)
    banner = next(f for f in findings if f.id == "compare.confound.augmentation")

    assert banner.confidence is Confidence.MEASURED
    assert "attribution" in banner.detail.lower()
    assert banner.seconds_lost is None


def test_no_augmentation_evoker_means_no_banner() -> None:
    findings = declare_confounds(a_loaded(ROSTER), a_loaded(ROSTER), SAME_LEVEL)

    assert "compare.confound.augmentation" not in ids(findings)


def test_a_keystone_level_gap_is_declared() -> None:
    findings = declare_confounds(
        a_loaded(ROSTER), a_loaded(ROSTER, level=17), Comparability(our_level=16, their_level=17)
    )

    assert "compare.confound.keystone_level" in ids(findings)


def test_matching_levels_need_no_keystone_banner() -> None:
    findings = declare_confounds(a_loaded(ROSTER), a_loaded(ROSTER), SAME_LEVEL)

    assert "compare.confound.keystone_level" not in ids(findings)


def test_a_material_item_level_gap_is_declared() -> None:
    richer = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP + 1}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(richer), SAME_LEVEL)
    banner = next(f for f in findings if f.id == "compare.confound.item_level")

    assert "Catalyst" in banner.detail or "secondary" in banner.detail.lower()


def test_a_small_item_level_gap_is_not_worth_a_banner() -> None:
    close = tuple(p.model_copy(update={"item_level": 318 + ITEM_LEVEL_GAP - 1}) for p in ROSTER)

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(close), SAME_LEVEL)

    assert "compare.confound.item_level" not in ids(findings)


def test_a_different_group_composition_is_declared() -> None:
    theirs = (player("Dudesons", "Warrior", "Protection"), player("Uglymage", "Mage", "Arcane"))

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(theirs), SAME_LEVEL)

    assert "compare.confound.composition" in ids(findings)


def test_the_same_composition_needs_no_banner() -> None:
    shuffled = tuple(reversed(ROSTER))

    findings = declare_confounds(a_loaded(ROSTER), a_loaded(shuffled), SAME_LEVEL)

    assert "compare.confound.composition" not in ids(findings)


def test_an_empty_roster_declares_nothing_and_does_not_divide_by_zero() -> None:
    findings = declare_confounds(a_loaded(()), a_loaded(()), SAME_LEVEL)

    assert "compare.confound.item_level" not in ids(findings)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_confounds.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.confounds'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/confounds.py`:

```python
# ABOUTME: States the differences between two runs that no arithmetic here can correct for.
# ABOUTME: Each is read off a roster, so the fact is measured even where its consequence is not.

from collections import Counter

from wowperf.domain.comparison.reference import Comparability
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player

ITEM_LEVEL_GAP = 5
"""Below this, an item-level difference is noise beside everything else that differs."""


def _mean_item_level(players: tuple[Player, ...]) -> float:
    if not players:
        return 0.0
    return sum(player.item_level for player in players) / len(players)


def _composition(players: tuple[Player, ...]) -> Counter[str]:
    return Counter(f"{player.class_name} {player.spec}" for player in players)


def _augmentation_evokers(players: tuple[Player, ...]) -> tuple[str, ...]:
    return tuple(
        player.name
        for player in players
        if player.class_name == "Evoker" and player.spec == "Augmentation"
    )


def declare_confounds(
    ours: LoadedRun, theirs: LoadedRun, rule: Comparability
) -> list[Finding]:
    """The differences a reader must hold in mind while reading every other finding."""
    findings: list[Finding] = []
    our_players = ours.run.players
    their_players = theirs.run.players

    augmenters = _augmentation_evokers(our_players) + _augmentation_evokers(their_players)
    if augmenters:
        findings.append(
            Finding(
                id="compare.confound.augmentation",
                title="An Augmentation Evoker makes per-player damage attribution unreliable",
                detail=(
                    "Blizzard's support-attribution hooks are documented as faulty: throughput "
                    "debuffs go unaccounted, reattribution can subtract damage, and shared "
                    "health pools generate duplicate events. This cannot be corrected here, so "
                    "treat every per-player damage figure in this report as approximate."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=tuple(f"{name} is an Augmentation Evoker" for name in augmenters),
            )
        )

    if not rule.durations_comparable:
        findings.append(
            Finding(
                id="compare.confound.keystone_level",
                title=f"The reference is a +{rule.their_level} and this run is a +{rule.our_level}",
                detail=rule.withheld_because(),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    f"ours +{rule.our_level}",
                    f"theirs +{rule.their_level}",
                    "route, deaths, interrupts and downtime remain comparable",
                ),
            )
        )

    our_ilvl = _mean_item_level(our_players)
    their_ilvl = _mean_item_level(their_players)
    if our_players and their_players and abs(their_ilvl - our_ilvl) >= ITEM_LEVEL_GAP:
        findings.append(
            Finding(
                id="compare.confound.item_level",
                title=(
                    f"The reference group averages {their_ilvl:.0f} item level against our "
                    f"{our_ilvl:.0f}"
                ),
                detail=(
                    "Item level is the only gear difference this tool can see. Tier count, "
                    "trinkets and embellishments are uncorrected, and the Matrix Catalyst "
                    "preserves original secondary stats, so equal item level no longer implies "
                    "a similar stat profile."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(f"ours {our_ilvl:.1f}", f"theirs {their_ilvl:.1f}"),
            )
        )

    ours_comp = _composition(our_players)
    theirs_comp = _composition(their_players)
    if our_players and their_players and ours_comp != theirs_comp:
        only_theirs = theirs_comp - ours_comp
        only_ours = ours_comp - theirs_comp
        findings.append(
            Finding(
                id="compare.confound.composition",
                title="The two groups were not the same composition",
                detail=(
                    "Group composition changes which packs can be held, which mechanics are "
                    "trivial, and how much damage a route can absorb. It is large and "
                    "uncorrectable, so it is stated rather than adjusted for."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=None,
                evidence=(
                    "only theirs: " + (", ".join(sorted(only_theirs.elements())) or "none"),
                    "only ours: " + (", ".join(sorted(only_ours.elements())) or "none"),
                ),
            )
        )

    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_confounds.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/confounds.py tests/domain/comparison/test_confounds.py
git commit -m "State the differences between two runs that cannot be corrected for

A comparison that hides its confounds reads as more certain than it is, which
is the failure this whole confidence taxonomy exists to prevent."
```

---

### Task 11: The comparison service

**Files:**
- Create: `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_service.py`

**Interfaces:**
- Consumes: everything from Tasks 2 and 6 to 10; `rank_findings` from `wowperf.domain.findings`.
- Produces:
  - `def find_player(run: Run, name: str) -> Player | None`
  - `def compare(ours: LoadedRun, our_player: Player, speed: SpeedReference | None, parse: ParseReference | None) -> list[Finding]`

One function, deliberately dull: run every comparison, concatenate, rank. All the judgement lives in the modules it calls.

Two behaviours it owns because nothing else can:

1. **A missing reference is a finding, not a crash.** Design §3.6 says ordinary analysis gaps produce findings. A dungeon nobody has speed-run at this level, or a specialisation with no ranked parse, is ordinary.
2. **`find_player` folds case.** The report owner's name arrives lowercased from the API while the roster carries the character's own capitalisation — `dudesons` against `Dudesons` on the verified report. Matching exactly would fail on the default path every time.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_service.py`:

```python
# ABOUTME: Behaviour tests for running every comparison over one run and ranking the result.
# ABOUTME: Guards the two things only the service can get wrong: a missing reference, and a name.

from wowperf.domain.comparison.reference import (
    Comparability,
    ParseReference,
    ParseRow,
    SpeedReference,
    SpeedRow,
)
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run

OURS = Player(
    actor_id=693,
    name="Uglymage",
    class_name="Mage",
    spec="Arcane",
    item_level=318,
    talent_import_string="C4DAAAAA",
)
THEIRS = Player(
    actor_id=11,
    name="Críms",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPAAAAA",
)


def a_pull(index: int, game_ids: tuple[int, ...], boss: bool = False) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Nalorakk" if boss else "Pack",
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + 60_000,
        killed=True,
        x=index,
        y=index,
        enemies=tuple(EnemyNpc(actor_id=100 + n, game_id=g) for n, g in enumerate(game_ids)),
    )


def a_loaded(players: tuple[Player, ...], pulls: tuple[Pull, ...], level: int = 16) -> LoadedRun:
    return LoadedRun(
        run=Run(
            report_code="abc123",
            fight_id=36,
            dungeon_name="Den of Nalorakk",
            encounter_id=12825,
            keystone_level=level,
            affix_ids=(9, 10, 147),
            keystone_time_ms=1_909_000,
            keystone_bonus=1,
            count_reached=744,
            count_required=729,
            npc_counts=((2, 12),),
            players=players,
            pulls=pulls,
            owner_name="uglymage",
        )
    )


def our_run() -> LoadedRun:
    return a_loaded((OURS,), (a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (9,), boss=True)))


def a_speed_reference(level: int = 16) -> SpeedReference:
    return SpeedReference(
        row=SpeedRow(
            report_code="71cv4MRdNCp8ZFjG",
            fight_id=28,
            keystone_level=level,
            duration_ms=1_379_452,
            deaths=0,
            medal="silver",
        ),
        loaded=a_loaded((OURS,), (a_pull(0, (1,)), a_pull(1, (9,), boss=True)), level=level),
    )


def a_parse_reference() -> ParseReference:
    return ParseReference(
        row=ParseRow(
            report_code="37FzMg9pVPH6fnJT",
            fight_id=16,
            keystone_level=16,
            duration_ms=1_399_143,
            character_name="Críms",
            class_name="Mage",
            spec="Arcane",
        ),
        loaded=a_loaded((THEIRS,), (a_pull(0, (9,), boss=True),)),
    )


def test_a_player_is_found_whatever_the_case() -> None:
    assert find_player(our_run().run, "uglymage") is OURS
    assert find_player(our_run().run, "UGLYMAGE") is OURS
    assert find_player(our_run().run, "Nobody") is None


def test_every_comparison_contributes() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), a_parse_reference())
    prefixes = {".".join(finding.id.split(".")[:2]) for finding in findings}

    assert {"compare.route", "compare.downtime", "compare.deaths", "compare.talents"} <= prefixes


def test_findings_come_back_ranked() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), a_parse_reference())
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]

    assert timed == sorted(timed, reverse=True)


def test_every_finding_id_is_unique() -> None:
    ids = [f.id for f in compare(our_run(), OURS, a_speed_reference(), a_parse_reference())]

    assert len(ids) == len(set(ids))


def test_every_finding_carries_a_badge() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), a_parse_reference())

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_no_speed_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), OURS, None, a_parse_reference())

    assert any(f.id == "compare.speed.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.route.") for f in findings)


def test_no_parse_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), None)

    assert any(f.id == "compare.parse.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.spells.") for f in findings)


def test_neither_reference_still_produces_a_usable_list() -> None:
    findings = compare(our_run(), OURS, None, None)

    assert len(findings) == 2
    assert all(finding.seconds_lost is None for finding in findings)


def test_a_reference_at_another_level_withholds_the_duration() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(level=17), None)
    duration = next(f for f in findings if f.id == "compare.duration")

    assert duration.seconds_lost is None
    assert Comparability(our_level=16, their_level=17).withheld_because() == duration.detail
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_service.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.service'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/service.py`:

```python
# ABOUTME: Runs every comparison against the two reference runs and ranks what they find.
# ABOUTME: Deliberately dull: all the judgement lives in the comparison modules, none of it here.

from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.confounds import declare_confounds
from wowperf.domain.comparison.reference import Comparability, ParseReference, SpeedReference
from wowperf.domain.comparison.route import compare_route
from wowperf.domain.comparison.spells import compare_spells, compare_talents
from wowperf.domain.comparison.tempo import compare_tempo
from wowperf.domain.findings import Confidence, Finding, rank_findings
from wowperf.domain.model import LoadedRun, Player, Run


def find_player(run: Run, name: str) -> Player | None:
    """Find a roster member by name, folding case.

    The report owner's name comes back from Warcraft Logs lowercased while the
    roster carries the character's own capitalisation, so an exact match would
    fail on the default path every time.
    """
    folded = name.casefold()
    return next((player for player in run.players if player.name.casefold() == folded), None)


def _unavailable(finding_id: str, title: str, detail: str) -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("no reference run was available",),
    )


def compare(
    ours: LoadedRun,
    our_player: Player,
    speed: SpeedReference | None,
    parse: ParseReference | None,
) -> list[Finding]:
    """Every comparison, one ranked list."""
    findings: list[Finding] = []

    if speed is None:
        findings.append(
            _unavailable(
                "compare.speed.unavailable",
                "No faster run was available to compare the route against",
                "The speed leaderboard returned nothing for this dungeon within one keystone "
                "level of this run, so route, downtime, deaths and interrupts are not compared.",
            )
        )
    else:
        rule = Comparability(
            our_level=ours.run.keystone_level, their_level=speed.loaded.run.keystone_level
        )
        findings += compare_route(
            ours.run, speed.loaded.run, align_pulls(ours.run, speed.loaded.run)
        )
        findings += compare_tempo(ours, speed.loaded, rule)
        findings += declare_confounds(ours, speed.loaded, rule)

    if parse is None:
        findings.append(
            _unavailable(
                "compare.parse.unavailable",
                f"No ranked parse was available for {our_player.class_name} {our_player.spec}",
                "The score leaderboard returned nothing for this specialisation within one "
                "keystone level of this run, so spells and talents are not compared.",
            )
        )
    else:
        findings += compare_spells(ours, our_player, parse.loaded, parse.row.character_name)
        findings += compare_talents(
            our_player, find_player(parse.loaded.run, parse.row.character_name)
        )

    return rank_findings(findings)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_service.py -v`
Expected: 9 passed.

If `test_every_finding_id_is_unique` fails, the culprit is two comparison modules sharing a prefix. Fix the id scheme, not the test.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/service.py tests/domain/comparison/test_service.py
git commit -m "Run every comparison and rank what it finds

A missing reference is an ordinary gap, so it produces a finding saying so
rather than failing a run that is otherwise perfectly analysable."
```

---

### Task 12: Wiring the comparison into the command

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `WclRankingRepository`, `compare`, `find_player`, `SpeedReference`, `ParseReference`, and the existing `analyse`, `build_repository`, `parse_report_url`.
- Produces: `wowperf analyze <report> [--fight N] [--player NAME] [--no-compare] [--cache-dir DIR] [--out DIR]`, writing the same `<code>-<fight>.findings.json` with two new top-level keys.

The JSON is the contract Plan D's report reads and the narrative layer interprets, so the additions are settled here:

```json
{
  "report_code": "6Kx1P9GbNXrcLdHa",
  "fight_id": 36,
  "dungeon_name": "Den of Nalorakk",
  "keystone_level": 16,
  "keystone_time_seconds": 1908.976,
  "in_time": true,
  "player": "Uglymage",
  "comparison": {
    "compared": true,
    "speed_reference": {
      "report_code": "71cv4MRdNCp8ZFjG", "fight_id": 28,
      "keystone_level": 16, "duration_seconds": 1379.452, "medal": "silver"
    },
    "parse_reference": {
      "report_code": "37FzMg9pVPH6fnJT", "fight_id": 16, "keystone_level": 16,
      "character_name": "Críms", "class_name": "Mage", "spec": "Arcane", "medal": "silver"
    }
  },
  "findings_are_ranked_not_additive": "…",
  "findings": [ … ]
}
```

`comparison.compared` is `false` and both references are `null` under `--no-compare`, or when neither leaderboard answered. Every existing key keeps its name and meaning.

Three rules:

1. **A bad `--player` exits non-zero, listing the roster.** It is a user error, and guessing at a name would analyse the wrong person.
2. **`BracketMismatch` propagates and exits non-zero.** §3.6 makes it one of the three fatal cases, because every number after it would be wrong.
3. **A reference that cannot be fetched degrades to no comparison.** `--no-compare` and an empty leaderboard produce the same JSON shape, so nothing downstream needs two code paths.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`, reusing the file's existing mock-transport helper for the report queries and extending it to answer `FightRankings` and `CharacterRankings`:

```python
def test_analyze_writes_a_comparison_block(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, ["--player", "Uglymage"])

    assert result.exit_code == 0
    payload = written_payload(tmp_path)
    assert payload["player"] == "Uglymage"
    assert payload["comparison"]["compared"] is True
    assert payload["comparison"]["speed_reference"]["report_code"]
    assert any(f["id"].startswith("compare.") for f in payload["findings"])


def test_no_compare_skips_both_references(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, ["--no-compare"])

    assert result.exit_code == 0
    payload = written_payload(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert payload["comparison"]["speed_reference"] is None
    assert not any(f["id"].startswith("compare.") for f in payload["findings"])


def test_an_unknown_player_exits_and_lists_the_roster(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, ["--player", "Nobody"])

    assert result.exit_code == 1
    assert "Uglymage" in result.output


def test_the_player_defaults_to_the_report_owner(tmp_path: Path) -> None:
    # The API lowercases the owner's name; the roster does not.
    result = run_analyze(tmp_path, [])

    assert result.exit_code == 0
    assert written_payload(tmp_path)["player"] == "Uglymage"


def test_a_bracket_that_lies_stops_the_command(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, [], bracket_data=11)

    assert result.exit_code == 1
    assert "bracket" in result.output.lower()


def test_an_empty_leaderboard_degrades_to_no_comparison(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, [], rankings=[])

    assert result.exit_code == 0
    payload = written_payload(tmp_path)
    assert payload["comparison"]["compared"] is False
    assert any(f["id"] == "compare.speed.unavailable" for f in payload["findings"])
```

Write `run_analyze(tmp_path, extra_args, *, bracket_data=16, rankings=None)` beside the existing helpers: it installs a mock transport answering every operation the command issues — `Fights`, `Abilities`, `Talents`, the six event streams, `Actors`, `FightRankings` and `CharacterRankings` — and invokes the command through `CliRunner` with `--cache-dir` and `--out` under `tmp_path`. Have the ranking answers use `bracket_data` and `rankings` so the last two tests can vary them. `written_payload(tmp_path)` reads back the single `*.findings.json` file and parses it.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_cli.py -v -k comparison or player`
Expected: FAIL — `--player` and `--no-compare` are not options yet, so Typer reports "No such option".

- [ ] **Step 3: Add the options and the reference fetch**

In `src/wowperf/cli.py`, extend the `analyze` signature:

```python
    player: str | None = typer.Option(
        None, help="Subject of the individual comparison; defaults to the report owner"
    ),
    no_compare: bool = typer.Option(
        False, "--no-compare", help="Skip both reference runs and analyse in isolation"
    ),
```

Add a helper above `analyze`:

```python
def _resolve_player(run: Run, requested: str | None) -> Player:
    """Whose run this is, for the individual comparison.

    The report owner is the default because it is the only name the log itself
    volunteers. Warcraft Logs lowercases it, so the match folds case.
    """
    name = requested or run.owner_name
    if name is not None:
        found = find_player(run, name)
        if found is not None:
            return found

    roster = ", ".join(sorted(player.name for player in run.players)) or "nobody"
    raise ValueError(
        f"{name!r} is not in this run's roster. Pass --player with one of: {roster}"
    )
```

and a second one that fetches both references:

```python
def _references(
    rankings: WclRankingRepository,
    runs: WclRunRepository,
    run: Run,
    subject: Player,
) -> tuple[SpeedReference | None, ParseReference | None]:
    """The two reference runs, or None where the leaderboard had nothing to offer."""
    speed = None
    for row in rankings.fastest_runs(run.encounter_id, run.keystone_level):
        # Comparing a run against itself would report a perfect route and teach
        # the reader nothing.
        if row.report_code == run.report_code and row.fight_id == run.fight_id:
            continue
        speed = SpeedReference(row=row, loaded=runs.load(row.report_code, row.fight_id))
        break

    parse = None
    for row in rankings.top_parses(
        run.encounter_id, run.keystone_level, subject.class_name, subject.spec
    ):
        if row.report_code == run.report_code and row.fight_id == run.fight_id:
            continue
        parse = ParseReference(row=row, loaded=runs.load(row.report_code, row.fight_id))
        break

    return speed, parse
```

- [ ] **Step 4: Call them from the command**

Inside `analyze`, replace the body of the existing `try` with:

```python
    try:
        code, fight_from_url = parse_report_url(report)
        repository = build_repository(cache_dir)
        loaded = repository.load(code, fight if fight is not None else fight_from_url)
        findings = analyse(loaded, load_season_data(), load_defensives())

        subject = _resolve_player(loaded.run, player)
        speed: SpeedReference | None = None
        parse: ParseReference | None = None
        if not no_compare:
            rankings = WclRankingRepository(repository.client, repository.cache)
            speed, parse = _references(rankings, repository, loaded.run, subject)
            findings += compare(loaded, subject, speed, parse)
            findings = rank_findings(findings)
    except (ValueError, WclError, httpx.HTTPError, OSError) as error:
        typer.secho(str(error), err=True, fg="red")
        raise typer.Exit(1) from error
```

`BracketMismatch` subclasses `WclError`, so it is caught by that clause and exits 1, which is what §3.6 asks for.

`WclRunRepository` does not currently expose its client or cache. Add two read-only properties to it rather than rebuilding a second client — one HTTP client and one cache directory per command run:

```python
    @property
    def client(self) -> WclClient:
        return self._client

    @property
    def cache(self) -> DiskCache:
        return self._cache
```

- [ ] **Step 5: Widen the payload**

Still in `analyze`, add these keys to `payload`, `player` immediately after `in_time` and `comparison` after it:

```python
        "player": subject.name,
        "comparison": {
            "compared": speed is not None or parse is not None,
            "speed_reference": (
                {
                    "report_code": speed.row.report_code,
                    "fight_id": speed.row.fight_id,
                    "keystone_level": speed.row.keystone_level,
                    "duration_seconds": speed.row.duration_seconds,
                    "medal": speed.row.medal,
                }
                if speed
                else None
            ),
            "parse_reference": (
                {
                    "report_code": parse.row.report_code,
                    "fight_id": parse.row.fight_id,
                    "keystone_level": parse.row.keystone_level,
                    "character_name": parse.row.character_name,
                    "class_name": parse.row.class_name,
                    "spec": parse.row.spec,
                    "medal": parse.row.medal,
                }
                if parse
                else None
            ),
        },
```

- [ ] **Step 6: Add the imports**

At the top of `src/wowperf/cli.py`:

```python
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.domain.comparison.reference import ParseReference, SpeedReference
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import rank_findings
from wowperf.domain.model import Player, Run
```

- [ ] **Step 7: Run them and watch them pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS, including every pre-existing `fetch` and `analyze` test.

- [ ] **Step 8: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/cli.py src/wowperf/adapters/wcl/repository.py tests/test_cli.py
git commit -m "Compare a run against two references from the command line

--no-compare and an empty leaderboard produce the same JSON shape, so the
report and the narrative never need a second code path for a missing reference."
```

---

### Task 13: End to end against real leaderboards

**Files:**
- Create: `tests/e2e/test_compare_e2e.py`
- Modify: `CLAUDE.md`
- Test: the file above, marked `e2e` and deselected by default

**Interfaces:**
- Consumes: everything.
- Produces: an `e2e`-marked test proving the comparison works against the live API, and a corrected repository description.

This test costs about 24 points of the 3600-per-hour budget: our run, two reference loads, and two leaderboard queries.

- [ ] **Step 1: Write the test**

`tests/e2e/test_compare_e2e.py`:

```python
# ABOUTME: End-to-end comparison against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.adapters.cache.disk import DiskCache
from wowperf.adapters.wcl.ranking_repository import WclRankingRepository
from wowperf.cli import build_repository
from wowperf.domain.comparison.reference import MAX_LEVEL_GAP
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import Confidence
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_compares_against_real_leaderboards(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    rankings = WclRankingRepository(runs.client, runs.cache)

    subject = find_player(loaded.run, loaded.run.owner_name or loaded.run.players[0].name)
    assert subject is not None, "the report owner should be in the roster"

    speed_rows = rankings.fastest_runs(loaded.run.encounter_id, loaded.run.keystone_level)
    assert speed_rows, "the speed leaderboard should have a run for this dungeon"

    # The bracket convention is asserted inside the repository; this checks the
    # consequence a reader depends on, which is that we got the key we asked for.
    assert all(
        abs(row.keystone_level - loaded.run.keystone_level) <= MAX_LEVEL_GAP for row in speed_rows
    )

    parse_rows = rankings.top_parses(
        loaded.run.encounter_id, loaded.run.keystone_level, subject.class_name, subject.spec
    )

    speed = None
    for row in speed_rows:
        if (row.report_code, row.fight_id) != (loaded.run.report_code, loaded.run.fight_id):
            speed = row
            break
    assert speed is not None

    from wowperf.domain.comparison.reference import ParseReference, SpeedReference

    speed_reference = SpeedReference(row=speed, loaded=runs.load(speed.report_code, speed.fight_id))
    parse_reference = None
    if parse_rows:
        parse_row = parse_rows[0]
        parse_reference = ParseReference(
            row=parse_row, loaded=runs.load(parse_row.report_code, parse_row.fight_id)
        )

    findings = compare(loaded, subject, speed_reference, parse_reference)

    assert findings
    assert all(isinstance(finding.confidence, Confidence) for finding in findings)
    assert len({finding.id for finding in findings}) == len(findings)

    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]
    assert timed == sorted(timed, reverse=True)

    # Both reference runs must actually be the same dungeon we ran.
    assert speed_reference.loaded.run.encounter_id == loaded.run.encounter_id
    assert speed_reference.loaded.run.pulls, "a reference with no pulls cannot be a route"
```

Also assert the talent string arrived, since `load` now fetches it and nothing offline proves the live shape:

```python
    assert any(
        player.talent_import_string for player in loaded.run.players
    ), "at least one player should carry a talent import string"
```

- [ ] **Step 2: Confirm it is deselected**

Run: `uv run pytest -q`
Expected: the new test is deselected; everything else passes.

- [ ] **Step 3: Run it against the real API**

```bash
WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... \
WOWPERF_E2E_REPORT='https://www.warcraftlogs.com/reports/<code>?fight=<n>' \
uv run pytest -m e2e -v
```

Expected: PASS. If a ranking query returns an error, re-read the "Verified schema" table before changing anything — `size` and the `{"error": ...}` shape are the two that bite.

**Report the observed findings to your human partner rather than only asserting on them.** This is the first time real leaderboard data meets the comparison, and a technically valid but obviously wrong number is what to catch here: a route with nothing in common, a reference that is the same run, a skipped pack worth more seconds than the whole key. Plan B's first contact found three defects the offline tests could not see; expect the same.

- [ ] **Step 4: Correct the repository description**

In `CLAUDE.md`, the state paragraph says Plans C and D are not written. Plan C is now built: the comparison against a speed reference and a top parse, reaching the leaderboards through `WclRankingRepository`. Update that paragraph and add a row to the Commands table for the new flags:

```
| `uv run wowperf analyze <url> [--player NAME] [--no-compare]` | Analyse a run, compare it against two references, and write the findings JSON |
```

Leave the HTML report attributed to Plan D.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add tests/e2e/test_compare_e2e.py CLAUDE.md
git commit -m "Prove the comparison against real leaderboards

The bracket convention, the group-size argument and the silent error shape are
all undocumented, and only a live call can show that the tool still reads them
the way it did the day they were verified."
```

---

## Plan Self-Review

**Spec coverage.** §6.1's two reference runs are Tasks 4 and 12. §6.2's matching rules are Task 4 (dungeon by encounter ID, the one-level fallback) and Task 3 (the bracket assertion); partition is a recorded decision rather than a task. §6.3's alignment is Task 6 and its findings are Task 7. §6.4's comparability split is Task 2, enforced in Task 8. §6.5 items 1 to 3 are Task 9. §6.6 is Task 10. §3.6's `--player` and `--no-compare` are Task 12.

Deliberately deferred, each with its reason recorded under "Decisions this plan makes": §6.5 item 4 (cooldown uses against a theoretical maximum), §6.5 item 5 (buff and debuff uptime), and §6.7 (the parse percentile, which belongs to Plan D's report header).

**Known gaps, carried forward.**

- The comparison always uses the first acceptable leaderboard row. A reference whose roster is wildly unlike ours is reported as a confound rather than skipped, which is the honest behaviour but means the reader does the choosing.
- `compare.spells.rate.*` compares casts per minute of boss time across two keystone levels when the fallback fires. The finding says a longer fight changes cooldown coverage, but it does not correct for it.
- Nothing checks that the reference's affixes match ours. §6.2 says affixes are displayed as a difference rather than filtered on, and `SpeedRow.affix_ids` carries them, but no finding renders that difference yet — Plan D's report header is where it belongs.
- `WclRankingRepository` reads page 1 only. Fifty rows is far more than the one reference this plan uses, and paging exists on the query for a future slice.

**Type consistency.** `SpeedRow`, `ParseRow`, `SpeedReference`, `ParseReference` and `Comparability` are defined in Task 2 and used unchanged in Tasks 3, 4, 8, 10, 11 and 12. `Alignment` and `PullMatch` come from Task 6 and are consumed only by Task 7. `compare` takes exactly `(LoadedRun, Player, SpeedReference | None, ParseReference | None)` in Tasks 11, 12 and 13. `Run.encounter_id` is added in Task 1 and read in Tasks 4, 12 and 13; `Player.talent_import_string` is added in Task 5 and read in Task 9.

**Field-name provenance.** Every Warcraft Logs field this plan names appears in the "Verified schema" table, confirmed by live query on 2026-09-04. The three undocumented behaviours — `size` as a group size, the `{"error": ...}` response shape, and `bracket = keystoneLevel - 1` — were each established by running the query and reading what came back, not by reading community code.
