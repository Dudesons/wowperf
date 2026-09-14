# Raid Mechanics Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wowperf raid` says what your raid ate — the per-ability damage-taken profile of one boss fight, compared against the rest of your own raid and against a sample of reference kills — and ranks its findings by severity.

**Architecture:** Two comparisons on the internal frame of design §4, neither needing a parse sample and both working identically on a kill and a wipe. `analyse_players`' damage-outlier half is narrowed off `Run` and reused whole. The per-ability profile comes from the `table(dataType: DamageTaken, viewBy: Ability)` endpoint on both sides, so the two sides reconcile exactly; nothing joins the table to the event stream. A second ranking Protocol sits beside the first rather than widening it, so a Mythic+ caller cannot reach the raid axis.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, typer, httpx, pytest, ruff, mypy — all through `uv`. No new dependencies.

**Spec:** `docs/plans/2026-09-13-raid-analysis-design.md` — read §4, §6.8, §6.9, §7, §8.1, §8.2, §14 and §15 before starting. §14 was resolved by measurement on 2026-09-14 and **§14 wins wherever an unamended section disagrees with it.** The master design `docs/plans/2026-09-03-mplus-postmortem-design.md` remains the authority on architecture, badges and refusals.

**Also read before touching `src/wowperf/domain/comparison/`:** `docs/plans/2026-09-13-comparison-table-rulings.md`. Plan 1 never did; this plan does.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or anything touching the network, disk or a template. Adapters do that, behind the ports in `src/wowperf/domain/ports.py`.
- **Every finding carries a confidence badge** — `measured`, `derived` or `inferred`. A finding without one is a bug.
- **Never invent an API field name.** The verified reference is `.claude/skills/wcl-api/SKILL.md`, where every claim carries the date it was checked. A field not there must be verified against the live schema first, then given a dated row.
- **Shared code narrows, it does not branch.** A function shared between Mythic+ and raid takes the *value* it reads — a roster, a denominator, a locator — never the aggregate, and never an `isinstance` on which aggregate it got. Plan 1 had one implementation widen five builders to `Run | Encounter`; it was rejected. Do not reintroduce one.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`, plus the accent-stripped spelling of one where a test needs two names that reduce to one slug.
- **Report `cW38jmwdnZfbHVL4` holds twenty real people.** Refer to them by class, specialisation, role or index — in code, tests, commit messages and documents.
- **`uv` is the only toolchain.** Gate: `uv run pytest`, `uv run ruff check .`, `uv run mypy` (paths come from `pyproject.toml`; pass none).
- **The baseline is `1566 passed, 11 deselected`.** Verified 2026-09-14 at `b7fe733`. A task ending with fewer passing has broken something and must be reverted, not argued with.
- **Credentials** live in a gitignored UTF-16 `.env`. Never read, echo, print or commit those values, and never put them on a command line. A worktree does not get one — copy it in with `shutil.copy2` and remove it when done.
- **Commit trailer is the fixed literal** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` — never the acting model's name. Commit messages are plain ASCII: a `§` once landed in a commit body as `SS`.
- **NEVER use `--no-verify`**, `--no-hooks` or `--no-pre-commit-hook`.
- **All code files start with two `# ABOUTME: ` lines.**

### The mutation rule, binding on every task

From `docs/plans/2026-09-13-comparison-table-rulings.md` §1.3:

> **No assertion in a test may survive deleting the arithmetic it claims to check** — proven by mutation, on every side of a comparison, not just the one you thought of first.

Every task below carries a mandatory mutation step. It is not verification theatre: plan 1 shipped nine defects and every one was a test that could not fail. Four shapes have actually occurred in this repository:

1. **The fixture dies at an earlier gate than the one under test.** Before trusting a test, list every gate its input passes through and name which one actually rejects it.
2. **A fixture whose arithmetic is the identity.** Every denominator 60 seconds makes `count / seconds * 60 == count`.
3. **A median flanked by equal values.** Three identical reference values are immune to mutating any one of them.
4. **An assertion that reads its expected value off the object it is checking.** True for every value and false for none.

### Two live traps in code this plan touches

- **`rate_measures` in `comparison/spells.py` divides with no zero check, on purpose.** It is the only thing keeping `tables.py`'s `their_boss_seconds <= 0` membership guard from being dead code. Comments say so in three places. Do not make the twins symmetric.
- **The anti-drift test in `tests/domain/comparison/test_tables.py` is load-bearing collateral** for deliberate duplication of three `per_member` builders. It kills seven mutations. Weakening or tidying it silently unmakes that trade.

---

## File Structure

**Created:**

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/analysis/roster.py` | `display_names` alone, narrowed to a roster, so two analysers can share it without a cycle |
| `src/wowperf/domain/analysis/damage_outliers.py` | §6.9: who took far more of one ability than their own group's median |
| `src/wowperf/domain/analysis/severity.py` | §7: the raid ranker and its severity table |
| `src/wowperf/domain/comparison/mechanics.py` | §6.8: the per-ability landing profile, the reference selection rule, and the comparison |
| `src/wowperf/adapters/wcl/ability_tables.py` | Turns a `viewBy: Ability` table payload into `AbilityTakenRow`s; maps, decides nothing |
| `src/wowperf/adapters/wcl/encounter_rankings.py` | The raid leaderboard adapter satisfying `EncounterRankingRepository` |

**Modified:** `src/wowperf/domain/analysis/players.py`, `src/wowperf/domain/ports.py`, `src/wowperf/domain/analysis/encounter_service.py`, `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/cli.py`, `src/wowperf/domain/report/deaths.py`, `src/wowperf/domain/report/players.py`, `.claude/skills/wcl-api/SKILL.md`.

**Tests created:** `tests/domain/analysis/test_damage_outliers.py`, `tests/domain/analysis/test_severity.py`, `tests/domain/comparison/test_mechanics.py`, `tests/adapters/wcl/test_ability_tables.py`, `tests/adapters/wcl/test_encounter_rankings.py`.

---

## Task 1: Narrow the roster helper and split out the damage-outlier half

§6.9 exists and is generic, but it lives inside `analyse_players`, whose other half prices activity against pull windows a boss fight does not have. Plan 1's fence parked the split for "the plan that needs the outliers". This is that plan.

**Files:**
- Create: `src/wowperf/domain/analysis/roster.py`
- Create: `src/wowperf/domain/analysis/damage_outliers.py`
- Create: `tests/domain/analysis/test_damage_outliers.py`
- Modify: `src/wowperf/domain/analysis/players.py` (remove `display_names`, `_DamageOutlier`, `_damage_outliers`, `MEDIAN_MULTIPLE`, `MIN_PLAYERS_FOR_MEDIAN`, `MAX_OUTLIERS_REPORTED` and the outlier loop; import and delegate)
- Modify: `src/wowperf/cli.py:36` and `:769`, `src/wowperf/domain/report/deaths.py:4` and `:312`, `src/wowperf/domain/report/players.py:7`, `tests/e2e/test_compare_e2e.py:17` — `display_names` moves module and narrows. **Five importers, not four**; the fifth is an e2e test excluded from the default suite, so `uv run pytest` will not catch it. Check it by eye.

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `roster.display_names(players: tuple[Player, ...]) -> dict[int, str]`
  - `damage_outliers.analyse_damage_outliers(players: tuple[Player, ...], damage_taken: tuple[DamageTakenEvent, ...], roles: Roles = Roles()) -> list[Finding]`
  - `damage_outliers.MEDIAN_MULTIPLE = 2.0`, `MIN_PLAYERS_FOR_MEDIAN = 3`, `MAX_OUTLIERS_REPORTED = 5`

**This is a refactor of working Mythic+ code. Its output must be byte-identical.** The finding id stays `players.damage.{rank}`, the title, detail, evidence tuple and the four `FindingFact`s stay exactly as they are today. Copy them; do not retype them from memory.

- [ ] **Step 1: Write the failing test**

Create `tests/domain/analysis/test_damage_outliers.py`:

```python
# ABOUTME: The damage-outlier finding, exercised against a roster rather than a Run.
# ABOUTME: Guards the tank exclusion and the three-player floor a median needs.

from wowperf.domain.analysis.damage_outliers import analyse_damage_outliers
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.model import Player
from wowperf.domain.season import Roles

ROLES = Roles(tanks=("Warrior/Protection",), healers=("Priest/Holy",))


def player(actor_id: int, name: str, class_name: str, spec: str) -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name=class_name, spec=spec, item_level=600
    )


def hit(actor_id: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=400,
        ability_name="Ravenous Feast",
        amount=amount,
        timestamp_ms=1000,
    )


ROSTER = (
    player(1, "Emberkin", "Mage", "Frost"),
    player(2, "Stonewake", "Mage", "Frost"),
    player(3, "Bríala", "Mage", "Frost"),
    player(4, "Кириллица", "Warrior", "Protection"),
)


def test_a_player_far_above_the_median_of_one_ability_is_a_finding() -> None:
    # Median over the three who took it is 100; actor 1 took 400, a 4.0x multiple.
    findings = analyse_damage_outliers(
        ROSTER, (hit(1, 400), hit(2, 100), hit(3, 100)), ROLES
    )
    assert findings, "three takers clear the median floor, so one outlier is expected"
    assert findings[0].id == "players.damage.0"
    assert "4.0x" in findings[0].title
    assert findings[0].ability_id == 400


def test_the_tank_is_excluded_even_when_it_took_the_most() -> None:
    # The tank takes ten times the others. Excluding tanks is the point: as one of
    # two in a raid and one of one in a key, a tank has no honest median.
    findings = analyse_damage_outliers(
        ROSTER, (hit(4, 4000), hit(1, 100), hit(2, 100), hit(3, 100)), ROLES
    )
    assert all(
        "Кириллица" not in finding.title for finding in findings
    ), "the tank reached a finding despite the role exclusion"


def test_two_takers_are_below_the_median_floor_and_produce_nothing() -> None:
    # MIN_PLAYERS_FOR_MEDIAN is 3. A median of two is a mean of two.
    findings = analyse_damage_outliers(ROSTER, (hit(1, 400), hit(2, 100)), ROLES)
    assert findings == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/domain/analysis/test_damage_outliers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.domain.analysis.damage_outliers'`

- [ ] **Step 3: Create `roster.py` by moving `display_names`**

Create `src/wowperf/domain/analysis/roster.py`. Move `display_names` out of `players.py` **unchanged except its parameter**: it takes `players: tuple[Player, ...]` and iterates `players` directly instead of `run.players`. Keep its whole docstring — amend only the final sentence, which names `analyse_players` as the rule's other user, to name `analyse_damage_outliers` instead.

```python
# ABOUTME: The name a report shows for each player, disambiguated when two share one.
# ABOUTME: Its own module so two analysers can share it without importing each other.

from collections import defaultdict

from wowperf.domain.model import Player


def display_names(players: tuple[Player, ...]) -> dict[int, str]:
    ...  # body as it stands in players.py, reading `players` instead of `run.players`
```

- [ ] **Step 4: Create `damage_outliers.py`**

Move `MEDIAN_MULTIPLE`, `MIN_PLAYERS_FOR_MEDIAN`, `MAX_OUTLIERS_REPORTED`, `_DamageOutlier` (renamed `DamageOutlier`, now public) and `_damage_outliers` (renamed `damage_outliers`) across, with their docstrings intact. `damage_outliers` takes `players` in place of `run` and builds its `names` map from `players`. Then add the finding builder, which is the outlier loop lifted out of `analyse_players` verbatim:

```python
def analyse_damage_outliers(
    players: tuple[Player, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
    roles: Roles = Roles(),
) -> list[Finding]:
    """Every player far above their own group's median for one ability.

    Takes a roster rather than a `Run` because a boss fight has no pulls and
    this comparison never needed them: the median is over whoever took the
    ability, and the roster is only there to name them and to find the tanks.
    """
    names_by_actor = display_names(players)
    players_by_id = {player.actor_id: player for player in players}
    findings: list[Finding] = []
    for rank, outlier in enumerate(
        damage_outliers(players, damage_taken, roles)[:MAX_OUTLIERS_REPORTED]
    ):
        ...  # the loop body from players.py, unchanged
    return findings
```

- [ ] **Step 5: Delegate from `analyse_players` and update the three other importers**

In `players.py`, delete the moved code and replace the outlier loop with one line:

```python
findings += analyse_damage_outliers(run.players, damage_taken, roles)
```

`players.py` keeps `summarise_players`, `LOW_ACTIVITY_PERCENT` and the activity loop. Its remaining use of `names_by_actor` disappears with the outlier loop — remove the now-unused local, and `players_by_id` with it if nothing else reads it.

Update `src/wowperf/cli.py:769` to `display_names(loaded.run.players)` and its import on line 36 to `from wowperf.domain.analysis.roster import display_names`. Do the same at `src/wowperf/domain/report/deaths.py:312` and in `src/wowperf/domain/report/players.py`, whose import on line 7 also pulls `summarise_players` — that one stays in `players.py`, so the import splits in two.

- [ ] **Step 6: Run the new test and the whole gate**

Run: `uv run pytest tests/domain/analysis/test_damage_outliers.py -v`
Expected: PASS, 3 tests.

Run: `uv run pytest`
Expected: `1569 passed, 11 deselected` — the baseline 1566 plus this task's 3. **Any Mythic+ test that changes its expected value means the refactor changed behaviour. Revert and find out why; do not update the expectation.**

- [ ] **Step 7: MANDATORY mutation — prove the tank exclusion is load-bearing**

In `damage_outliers`, delete the two lines that skip a tank's hits:

```python
        if hit.actor_id in tank_ids:
            continue
```

Run: `uv run pytest tests/domain/analysis/test_damage_outliers.py -v`
Expected: `test_the_tank_is_excluded_even_when_it_took_the_most` FAILS.

If it passes, the fixture is wrong: check that `ROLES` actually classifies `Warrior/Protection` as a tank, and that the tank's amount clears `MEDIAN_MULTIPLE` against a median of three takers. **Restore the lines before committing.**

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/domain/analysis/roster.py src/wowperf/domain/analysis/damage_outliers.py src/wowperf/domain/analysis/players.py src/wowperf/cli.py src/wowperf/domain/report/deaths.py src/wowperf/domain/report/players.py tests/domain/analysis/test_damage_outliers.py
git commit
```

Subject: `Let the damage outliers read a roster rather than a run`. Body: why the split happens now — a boss fight has no pulls, so the activity half cannot follow, and the outlier half never needed them.

---

## Task 2: The damage-taken ability table

Design §6.8's comparison reads `table(dataType: DamageTaken, viewBy: Ability)`, raid-wide and scoped to one player. §14 item 1 and §14's amendment to §2.5 establish what the row means; this task encodes it and records the fields.

**Measured 2026-09-14 and binding on this task:**

- Landings are `hitCount + tickCount`. `missCount` and `tickMissCount` count attempts that did not land. All four summed over one fight's 26 rows equalled the event count exactly — 11,456, difference zero.
- `total` is **mitigated** damage; `totalReduced` is health damage. The unmitigated figure is not exposed. **This task stores neither — §6.8 states landings and says nothing about damage.**
- `hostilityType` does not exclude friendly sources; it selects whose damage-taken is tabulated, and `Friendlies` is the default for this table. Friendly-sourced rows survive. A row's `sources[].type` reads `"Boss"`, `"NPC"` or `"Pet"` for a hostile source and a **class name** for a player. Every row measured had homogeneous sources.
- `sourceID` scopes this table to the **victim**. `targetID` selects who dealt the damage and returns nothing useful here.
- Points are billed per table, not per request: twenty aliased tables in one operation cost 20.05.

**Files:**
- Create: `src/wowperf/domain/comparison/mechanics.py` (the row model only in this task)
- Create: `src/wowperf/adapters/wcl/ability_tables.py`
- Create: `tests/adapters/wcl/test_ability_tables.py`
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Modify: `.claude/skills/wcl-api/SKILL.md`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `mechanics.AbilityTakenRow` — frozen, fields `ability_id: int`, `ability_name: str`, `hit_count: int`, `tick_count: int`, `miss_count: int`, `tick_miss_count: int`, `source_types: tuple[str, ...]`, and a `landings` property returning `hit_count + tick_count`
  - `ability_tables.build_ability_taken_rows(payload: dict[str, Any], alias: str) -> tuple[AbilityTakenRow, ...]`
  - `queries.ABILITY_TAKEN_TABLE_QUERY`, `queries.ABILITY_TAKEN_TABLE_BY_VICTIM_QUERY`

- [ ] **Step 1: Write the failing test**

Create `tests/adapters/wcl/test_ability_tables.py`:

```python
# ABOUTME: Maps a viewBy-Ability damage-taken table into rows the comparison reads.
# ABOUTME: Landings are hits plus ticks; misses are counted and never added to them.

from wowperf.adapters.wcl.ability_tables import build_ability_taken_rows


def payload(entries: list[dict[str, object]]) -> dict[str, object]:
    return {"reportData": {"report": {"taken": {"data": {"entries": entries}}}}}


def test_landings_are_hits_plus_ticks_and_exclude_misses() -> None:
    rows = build_ability_taken_rows(
        payload(
            [
                {
                    "guid": 400,
                    "name": "Ravenous Feast",
                    "hitCount": 7,
                    "tickCount": 5,
                    "missCount": 3,
                    "tickMissCount": 2,
                    "sources": [{"name": "The Twin Fangs", "type": "Boss"}],
                }
            ]
        ),
        "taken",
    )
    assert len(rows) == 1
    # 7 + 5 = 12. The two miss counts total 5 and must not reach it.
    assert rows[0].landings == 12
    assert rows[0].miss_count == 3
    assert rows[0].tick_miss_count == 2


def test_a_missing_count_field_reads_zero_rather_than_raising() -> None:
    # Rows carrying only some of the four counts were observed on real fights.
    rows = build_ability_taken_rows(
        payload([{"guid": 401, "name": "Coiling Ichor", "tickCount": 4, "sources": []}]),
        "taken",
    )
    assert rows[0].landings == 4
    assert rows[0].hit_count == 0
    assert rows[0].source_types == ()


def test_source_types_are_carried_verbatim_for_the_domain_to_judge() -> None:
    rows = build_ability_taken_rows(
        payload(
            [
                {
                    "guid": 6940,
                    "name": "Blessing of Sacrifice",
                    "hitCount": 2,
                    "sources": [{"name": "Stonewake", "type": "Warrior"}],
                }
            ]
        ),
        "taken",
    )
    # The adapter maps and decides nothing: whether a Warrior-sourced row is a
    # mechanic is the domain's judgement, in mechanics.py.
    assert rows[0].source_types == ("Warrior",)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/adapters/wcl/test_ability_tables.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.ability_tables'`

- [ ] **Step 3: Add `AbilityTakenRow` to `mechanics.py`**

```python
# ABOUTME: The per-ability landing profile of one fight, and how two of them compare.
# ABOUTME: Landings only -- the table's damage is mitigated and cannot meet the event stream's.

from wowperf.domain.base import Frozen


class AbilityTakenRow(Frozen):
    """One ability's damage-taken row, as `viewBy: Ability` reports it.

    Damage is deliberately absent. The table's `total` is mitigated -- it
    equals the event stream's health damage plus absorbs -- and the
    unmitigated figure `players.damage.*` ranks on is not exposed and not
    reconstructible. Carrying both would put two figures for one ability on
    one page, measured up to 4.61x apart on a real fight, with nothing a
    reader could reconcile them by.
    """

    ability_id: int
    ability_name: str
    hit_count: int = 0
    tick_count: int = 0
    miss_count: int = 0
    tick_miss_count: int = 0
    # Each source's `type`, verbatim: "Boss", "NPC" or "Pet" for a hostile
    # source, a class name for a player. Empty on a row whose sources array
    # was empty, which was observed carrying a miss count and no damage.
    source_types: tuple[str, ...] = ()

    @property
    def landings(self) -> int:
        """How many times this ability actually landed.

        No single field counts this. Measured 2026-09-14: hits, ticks, misses
        and tick misses summed over one fight's 26 rows equalled the event
        count exactly, so hits plus ticks is what landed and the two miss
        counts are what did not.
        """
        return self.hit_count + self.tick_count
```

- [ ] **Step 4: Add both queries to `queries.py`**

Place them after `AURA_TABLE_QUERY`, following its aliasing convention — the builder reads the selection by name and says so when it is missing.

```python
# `hostilityType` is omitted deliberately. Measured 2026-09-14: omitting it and
# passing `Friendlies` return byte-identical JSON, and `Enemies` returns the
# other side of the fight rather than a filtered version of this one. There is
# no value of it that excludes friendly-sourced abilities; `sources[].type`
# does that, client-side, in `domain/comparison/mechanics.py`.
ABILITY_TAKEN_TABLE_QUERY = """
query AbilityTakenTable($code: String!, $fightId: Int!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      taken: table(fightIDs: [$fightId], dataType: DamageTaken, viewBy: Ability)
    }
  }
}
"""

# `sourceID` scopes a damage-taken table to the victim. Measured 2026-09-14:
# `targetID` selects who dealt the damage instead and returned no rows for a
# player who had taken 26 million. The two are inverted from the reading in
# design 2.5, which its amendment records.
ABILITY_TAKEN_TABLE_BY_VICTIM_QUERY = """
query AbilityTakenTableByVictim($code: String!, $fightId: Int!, $actorId: Int!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      taken: table(
        fightIDs: [$fightId]
        dataType: DamageTaken
        viewBy: Ability
        sourceID: $actorId
      )
    }
  }
}
"""
```

- [ ] **Step 5: Write the builder**

Create `src/wowperf/adapters/wcl/ability_tables.py`. It maps and decides nothing. Follow `ingest.py`'s existing habit of raising a `WclError` naming the alias when the selection is absent, rather than returning an empty tuple that would read as "this fight had no damage taken".

```python
def build_ability_taken_rows(payload: dict[str, Any], alias: str) -> tuple[AbilityTakenRow, ...]:
    report = (payload.get("reportData") or {}).get("report") or {}
    if alias not in report:
        raise WclError(f"The damage-taken table response carried no `{alias}` selection")
    entries = ((report[alias] or {}).get("data") or {}).get("entries") or []
    return tuple(
        AbilityTakenRow(
            ability_id=entry["guid"],
            ability_name=entry.get("name") or "",
            hit_count=entry.get("hitCount") or 0,
            tick_count=entry.get("tickCount") or 0,
            miss_count=entry.get("missCount") or 0,
            tick_miss_count=entry.get("tickMissCount") or 0,
            source_types=tuple(
                source.get("type") or "" for source in entry.get("sources") or ()
            ),
        )
        for entry in entries
    )
```

- [ ] **Step 6: Add the dated rows to the API skill**

Append to the field table in `.claude/skills/wcl-api/SKILL.md`, and flip `sourceID`'s existing row (currently `no`) to `yes`:

```
| `hitCount` | `table` entry, `DamageTaken` `viewBy: Ability` | 2026-09-14 | yes |
| `tickCount` | `table` entry, `DamageTaken` `viewBy: Ability` | 2026-09-14 | yes |
| `missCount` | `table` entry, `DamageTaken` `viewBy: Ability` | 2026-09-14 | yes |
| `tickMissCount` | `table` entry, `DamageTaken` `viewBy: Ability` | 2026-09-14 | yes |
| `sources` | `table` entry, `DamageTaken` `viewBy: Ability` | 2026-09-14 | yes |
```

Then add a dated prose note beneath the table's existing behavioural sections, titled **"`hostilityType` does not exclude friendly sources"**, recording: the two enum values, that omitting it equals `Friendlies` byte-for-byte, that `Enemies` returns the other side of the fight at 223 rows against 26, that 8 of 26 rows on a measured kill were sourced entirely by players (1.97% of damage, Blessing of Sacrifice among them), and that `sources[].type` is what separates them. Add a second note, **"A damage-taken table's damage is mitigated"**, recording that `total` equals health damage plus absorbs and `totalReduced` equals health damage, that the unmitigated figure is absent, and that the gap against the event stream reached 4.61x on one fight. Both dated 2026-09-14.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/adapters/wcl/test_ability_tables.py tests/test_skills.py -v`
Expected: PASS. `test_skills.py` is included because `test_every_field_the_table_says_we_query_is_in_the_queries` reads the table you just edited — it fails if a row says `yes` for a field no query selects.

- [ ] **Step 8: MANDATORY mutation — prove landings exclude misses**

Change `landings` to `self.hit_count + self.tick_count + self.miss_count`.

Run: `uv run pytest tests/adapters/wcl/test_ability_tables.py -v`
Expected: `test_landings_are_hits_plus_ticks_and_exclude_misses` FAILS — 12 became 15.

This is shape 2 from the mutation rule: a fixture whose counts were all equal would survive this. The fixture uses 7, 5, 3 and 2 precisely so no two sums coincide. **Restore before committing.**

- [ ] **Step 9: Commit**

```bash
git add src/wowperf/domain/comparison/mechanics.py src/wowperf/adapters/wcl/ability_tables.py src/wowperf/adapters/wcl/queries.py .claude/skills/wcl-api/SKILL.md tests/adapters/wcl/test_ability_tables.py
git commit
```

Subject: `Read a fight's damage taken one ability at a time`. Body: why landings and not damage — the table's figure is mitigated and the outlier finding's is not.

---

## Task 3: The encounter ranking port and the reference-kill leaderboard

Design §8.2's amendment: a second Protocol beside the first, so a Mythic+ consumer cannot reach the raid axis and a raid consumer cannot pass a keystone level. §14 item 4: the references come from `execution`, the deathless-kill board.

**Files:**
- Create: `src/wowperf/adapters/wcl/encounter_rankings.py`
- Create: `tests/adapters/wcl/test_encounter_rankings.py`
- Modify: `src/wowperf/domain/ports.py`
- Modify: `src/wowperf/domain/comparison/mechanics.py` (add `ReferenceKillRow`)
- Modify: `src/wowperf/adapters/wcl/queries.py`

**Interfaces:**
- Consumes: `mechanics.AbilityTakenRow` from Task 2 (same module, not imported).
- Produces:
  - `mechanics.ReferenceKillRow` — frozen, fields `report_code: str`, `fight_id: int`, `difficulty: int`, `size: int`, `duration_ms: int`, `deaths: int`, and a `duration_seconds` property
  - `ports.EncounterRankingRepository` — a Protocol declaring `reference_kills(self, encounter_id: int, difficulty: int, partition: int) -> tuple[ReferenceKillRow, ...]`
  - `encounter_rankings.WclEncounterRankingRepository(client, cache)` implementing it
  - `queries.ENCOUNTER_KILL_RANKINGS_QUERY`

**`RankingRepository` is not touched.** Do not add a method to it, do not widen `keystone_level`, do not introduce a union axis type. A Mythic+ caller typed against `RankingRepository` must remain unable to name a difficulty.

- [ ] **Step 1: Write the failing test**

Create `tests/adapters/wcl/test_encounter_rankings.py`:

```python
# ABOUTME: Turns the execution leaderboard into reference kills a mechanics comparison can load.
# ABOUTME: A row with no loadable report is dropped, because it can never be fetched.

from wowperf.adapters.wcl.encounter_rankings import build_reference_kill_rows


def test_a_row_becomes_a_reference_kill() -> None:
    rows = build_reference_kill_rows(
        [
            {
                "report": {"code": "abc123", "fightID": 12},
                "difficulty": 4,
                "size": 20,
                "duration": 480000,
                "deaths": 0,
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0].report_code == "abc123"
    assert rows[0].fight_id == 12
    assert rows[0].size == 20
    assert rows[0].duration_seconds == 480.0


def test_a_row_with_no_report_code_is_dropped() -> None:
    # Measured 2026-09-14: 39 of 50 `progress` rows carried a null report code.
    # `execution` carried none, but the shape exists and a row that cannot be
    # loaded is no use as a reference.
    rows = build_reference_kill_rows(
        [
            {"report": {"code": None, "fightID": None}, "difficulty": 4, "size": 20,
             "duration": 480000, "deaths": 0},
            {"report": {"code": "abc123", "fightID": 12}, "difficulty": 4, "size": 20,
             "duration": 500000, "deaths": 1},
        ]
    )
    assert [row.report_code for row in rows] == ["abc123"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/adapters/wcl/test_encounter_rankings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.adapters.wcl.encounter_rankings'`

- [ ] **Step 3: Add `ReferenceKillRow` to `mechanics.py`**

```python
class ReferenceKillRow(Frozen):
    """One kill from the `execution` leaderboard, as a reference candidate.

    Carries no keystone level, no bracket and no affixes: a boss fight has
    none of them, and a row that cannot express a keystone level cannot be
    handed to a Mythic+ comparison by accident.
    """

    report_code: str
    fight_id: int
    difficulty: int
    size: int
    duration_ms: int
    deaths: int = 0

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000
```

- [ ] **Step 4: Add the port**

In `src/wowperf/domain/ports.py`, beside `RankingRepository` and without altering it:

```python
class EncounterRankingRepository(Protocol):
    """The raid axis, as a sibling of `RankingRepository` rather than a widening of it.

    Two protocols rather than one parameter that expresses both axes: a union
    axis type leaves the wrong axis representable -- a Mythic+ caller can
    construct a raid axis and mypy accepts it -- so the only defence would be a
    runtime guard. Design 14 item 3 rules that out. Here the wrong axis is
    unrepresentable because the method is absent, not because it is guarded.
    """

    def reference_kills(
        self, encounter_id: int, difficulty: int, partition: int
    ) -> tuple[ReferenceKillRow, ...]: ...
```

- [ ] **Step 5: Add the query and the adapter**

In `queries.py`, after `CHARACTER_RANKINGS_QUERY`:

```python
# `execution` rather than `speed`. Measured 2026-09-14: `default` and `speed`
# return byte-identical row sets with deaths ranging 0 to 20, while `execution`
# is a separate board overlapping them on 7 of 50 rows with deaths ranging 0 to
# 1. A near-deathless kill is the better reference for what a raid handling the
# boss cleanly actually took. Its durations run 60 to 100 seconds longer, which
# a per-minute rate normalises away.
ENCOUNTER_KILL_RANKINGS_QUERY = """
query EncounterKillRankings(
  $encounterId: Int!, $difficulty: Int!, $partition: Int!, $page: Int!
) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      fightRankings(
        metric: execution
        difficulty: $difficulty
        partition: $partition
        page: $page
      )
    }
  }
}
"""
```

Create `encounter_rankings.py` with `build_reference_kill_rows(rows)` — dropping any row whose `report` is not a dict carrying a truthy `code`, exactly as `rankings._report_of` does — and `WclEncounterRankingRepository`, which caches through `DiskCache.get_or_fetch` with `cache_key(query, variables)` and reuses `rankings.rankings_block` to unwrap the response and refuse its two failure shapes.

There is no `assert_bracket` sibling and no level-widening loop. `difficulty` is passed and returned on the row; Task 4 asserts it.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/adapters/wcl/test_encounter_rankings.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 7: MANDATORY mutation — prove the unloadable row is really dropped**

Change the drop condition so a row with a null code survives (`report is not None` instead of checking `code`).

Run: `uv run pytest tests/adapters/wcl/test_encounter_rankings.py -v`
Expected: `test_a_row_with_no_report_code_is_dropped` FAILS with two rows where one was expected.

**Restore before committing.**

- [ ] **Step 8: Verify the wrong axis is unrepresentable**

Run: `uv run mypy`
Expected: clean. The file count rises as this plan adds modules — read it, do not predict it.

Then, temporarily, add to any file that imports `RankingRepository` a line calling `fastest_runs(encounter_id=1, difficulty=4)`.

Run: `uv run mypy`
Expected: an error naming `difficulty` as an unexpected keyword argument. This is the point of the whole task — if mypy accepts it, the protocols are not separate. **Remove the line.**

- [ ] **Step 9: Commit**

```bash
git add src/wowperf/domain/ports.py src/wowperf/domain/comparison/mechanics.py src/wowperf/adapters/wcl/encounter_rankings.py src/wowperf/adapters/wcl/queries.py tests/adapters/wcl/test_encounter_rankings.py
git commit
```

Subject: `Give the raid axis its own ranking port`. Body: why siblings rather than one widened parameter — a union leaves the wrong axis representable and reduces the guarantee to a runtime check.

---

## Task 4: Select the reference sample

§6.8's amendment: `SAMPLE_SIZE` references, filtered to our own raid size, with a median and an observed range, falling back to one reference below `MIN_SAMPLE_FOR_AGGREGATE`. The selection rule is pure and belongs in the domain; fetching is the CLI's job in Task 8.

**Why size is filtered rather than annotated:** measured 2026-09-14, a single page of kill rankings spanned sizes 14 to 30 against our 20. Heroic is flexible-size and scales, and the comparison is a per-minute landing rate over a whole raid, so a 30-player reference reports half again as many landings for headcount alone. Fifty rows a page means several usually sit at any given size, so matching outright costs nothing.

**Files:**
- Modify: `src/wowperf/domain/comparison/mechanics.py`
- Create: `tests/domain/comparison/test_mechanics.py`

**Interfaces:**
- Consumes: `ReferenceKillRow` from Task 3.
- Produces: `mechanics.select_reference_kills(rows: tuple[ReferenceKillRow, ...], *, our_size: int, our_difficulty: int, limit: int = SAMPLE_SIZE) -> tuple[ReferenceKillRow, ...]`

- [ ] **Step 1: Write the failing test**

Create `tests/domain/comparison/test_mechanics.py`:

```python
# ABOUTME: The mechanics comparison: which references it draws, and what it states.
# ABOUTME: Size is matched, not annotated, because the rate is over a whole raid.

from wowperf.domain.comparison.mechanics import ReferenceKillRow, select_reference_kills
from wowperf.domain.comparison.sample import SAMPLE_SIZE


def kill(code: str, size: int, difficulty: int = 4) -> ReferenceKillRow:
    return ReferenceKillRow(
        report_code=code, fight_id=1, difficulty=difficulty, size=size,
        duration_ms=480000, deaths=0,
    )


def test_only_references_of_our_own_size_are_drawn() -> None:
    rows = (kill("a", 20), kill("b", 30), kill("c", 20), kill("d", 14))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert [row.report_code for row in drawn] == ["a", "c"]


def test_a_reference_at_another_difficulty_is_refused() -> None:
    # Difficulty is matched exactly, never approximated: a Heroic pull against
    # Mythic references is meaningless, and design 13 refuses it rather than
    # annotating it.
    rows = (kill("a", 20, difficulty=5), kill("b", 20, difficulty=4))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert [row.report_code for row in drawn] == ["b"]


def test_no_more_than_the_sample_size_is_drawn() -> None:
    rows = tuple(kill(str(index), 20) for index in range(SAMPLE_SIZE + 3))
    drawn = select_reference_kills(rows, our_size=20, our_difficulty=4)
    assert len(drawn) == SAMPLE_SIZE
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_mechanics.py -v`
Expected: FAIL — `ImportError: cannot import name 'select_reference_kills'`

- [ ] **Step 3: Implement the selection**

```python
def select_reference_kills(
    rows: tuple[ReferenceKillRow, ...],
    *,
    our_size: int,
    our_difficulty: int,
    limit: int = SAMPLE_SIZE,
) -> tuple[ReferenceKillRow, ...]:
    """References comparable to our own fight, in leaderboard order.

    Both filters refuse rather than annotate. Difficulty because the master
    design already refuses a cross-difficulty comparison outright. Size because
    this comparison is a landing rate over a whole raid: measured 2026-09-14, a
    single page spanned 14 to 30 against our 20, and a 30-player reference
    reports half again as many landings for headcount alone. A page holds
    fifty rows, so matching exactly usually leaves plenty.
    """
    matching = [
        row for row in rows if row.size == our_size and row.difficulty == our_difficulty
    ]
    return tuple(matching[:limit])
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/domain/comparison/test_mechanics.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: MANDATORY mutation — prove both filters bite**

First drop the size clause, leaving `row.difficulty == our_difficulty`.
Run: `uv run pytest tests/domain/comparison/test_mechanics.py -v`
Expected: `test_only_references_of_our_own_size_are_drawn` FAILS.

Restore it, then drop the difficulty clause.
Expected: `test_a_reference_at_another_difficulty_is_refused` FAILS.

Both halves must be proven separately — this is shape 1 from the mutation rule: with only one test, a fixture could pass the surviving filter and never reach the dropped one. **Restore before committing.**

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/comparison/mechanics.py tests/domain/comparison/test_mechanics.py
git commit
```

Subject: `Draw reference kills at our own size and difficulty`. Body: why size is refused rather than annotated.

---

## Task 5: The mechanics comparison

Design §6.8 as amended: landings per minute, ours against the sample's median and observed range, per ability. **It never states that a mechanic was missed** — that is a claim about intent no table supports, and master design §5.5 refuses it.

**Files:**
- Modify: `src/wowperf/domain/comparison/mechanics.py`
- Modify: `tests/domain/comparison/test_mechanics.py`

**Interfaces:**
- Consumes: `AbilityTakenRow` (Task 2), `ReferenceKillRow` (Task 3), `select_reference_kills` (Task 4); from `domain/comparison/sample.py`: `SAMPLE_SIZE`, `MIN_SAMPLE_FOR_AGGREGATE`, `too_few`; from `domain/comparison/statistics.py`: `median`, `observed_range`, `count_phrase`; from `domain/findings.py`: `Finding`, `FindingFact`, `Confidence`, `quantifier_for`.
- Produces:
  - `mechanics.MechanicsMember` — frozen, `row: ReferenceKillRow`, `abilities: tuple[AbilityTakenRow, ...]`
  - `mechanics.MechanicsSample` — frozen, `members: tuple[MechanicsMember, ...]`
  - `mechanics.PLAYER_SOURCE_TYPES: frozenset[str]`
  - `mechanics.hostile_rows(rows: tuple[AbilityTakenRow, ...]) -> tuple[AbilityTakenRow, ...]`
  - `mechanics.compare_mechanics(ours: tuple[AbilityTakenRow, ...], our_seconds: float, sample: MechanicsSample, *, scope: str) -> list[Finding]`

**The friendly-source filter fails toward showing a mechanic.** A row is dropped only when every one of its sources is a known player class. An unrecognised type is kept. This is the direction `data/roles.toml`'s own comment argues for — "a tank mistaken for damage produces a loud false finding, a damage player mistaken for a tank produces silence" — applied here: a friendly ability wrongly shown is visible and correctable, a mechanic wrongly hidden is not. The thirteen class names are a module constant with a dated comment; they are not season data, and `data/roles.toml` already spells class names by hand.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_mechanics.py`:

```python
from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow, MechanicsMember, MechanicsSample, compare_mechanics, hostile_rows,
)


def ability(ability_id: int, name: str, hits: int, sources: tuple[str, ...]) -> AbilityTakenRow:
    return AbilityTakenRow(
        ability_id=ability_id, ability_name=name, hit_count=hits, source_types=sources
    )


def member(
    code: str, abilities: tuple[AbilityTakenRow, ...], seconds: float = 120.0
) -> MechanicsMember:
    # Its own row rather than `kill()`: the duration is the denominator under
    # test, so it has to be visible here and equal to ours, or a rate
    # comparison would be testing two things at once.
    return MechanicsMember(
        row=ReferenceKillRow(
            report_code=code, fight_id=1, difficulty=4, size=20,
            duration_ms=int(seconds * 1000), deaths=0,
        ),
        abilities=abilities,
    )


def test_a_row_sourced_only_by_players_is_not_a_mechanic() -> None:
    rows = (
        ability(6940, "Blessing of Sacrifice", 2, ("Warrior",)),
        ability(400, "Ravenous Feast", 4, ("Boss",)),
    )
    assert [row.ability_id for row in hostile_rows(rows)] == [400]


def test_an_unrecognised_source_type_is_kept() -> None:
    # The filter fails toward showing a mechanic. A hostile type this code has
    # never seen must not make an ability disappear in silence.
    rows = (ability(401, "Coiling Ichor", 9, ("Leviathan",)),)
    assert [row.ability_id for row in hostile_rows(rows)] == [401]


def test_an_ability_we_took_far_more_of_than_the_sample_is_a_finding() -> None:
    # Ours: 12 landings in 120s = 6.0 a minute. The five references took
    # 1, 2, 3, 4 and 5 in 120s: a median of 3 landings, 1.5 a minute.
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (1, 2, 3, 4, 5)
        )
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "a 4x gap against five references should state something"
    assert findings[0].id.startswith("mechanics.ability.")
    assert findings[0].confidence.value == "measured"
    # Both absolute rates are pinned, not only their ratio. A ratio is
    # scale-free, so an assertion resting on it alone survives deleting the
    # per-minute conversion from both sides -- mutation shape 2. The sample
    # median (1.5) also differs from its max (2.5) and its mean (1.5 here is
    # both, so the rates are 0.5/1.0/1.5/2.0/2.5 and only the median is 1.5).
    assert any("6.0" in line for line in findings[0].evidence), "our own rate"
    assert any("1.5" in line for line in findings[0].evidence), "the sample median rate"
    # The claim is a count, never an intent. Master design 5.5 refuses the latter.
    assert "missed" not in findings[0].title.lower()
    assert "missed" not in findings[0].detail.lower()


def test_an_ability_in_line_with_the_sample_states_nothing() -> None:
    ours = (ability(400, "Ravenous Feast", 3, ("Boss",)),)
    sample = MechanicsSample(
        members=tuple(
            member(str(index), (ability(400, "Ravenous Feast", index, ("Boss",)),))
            for index in (2, 3, 3, 4, 3)
        )
    )
    assert compare_mechanics(ours, 120.0, sample, scope="the raid") == []


def test_below_the_aggregate_floor_the_finding_says_it_is_one_reference() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    sample = MechanicsSample(
        members=(member("a", (ability(400, "Ravenous Feast", 1, ("Boss",)),)),)
    )
    findings = compare_mechanics(ours, 120.0, sample, scope="the raid")
    assert findings, "one reference is still a comparison, stated as one"
    assert any("single reference" in line for line in findings[0].evidence)


def test_an_empty_sample_states_nothing_rather_than_everything() -> None:
    ours = (ability(400, "Ravenous Feast", 12, ("Boss",)),)
    assert compare_mechanics(ours, 120.0, MechanicsSample(), scope="the raid") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_mechanics.py -v`
Expected: FAIL — `ImportError: cannot import name 'compare_mechanics'`

- [ ] **Step 3: Implement the filter and the comparison**

```python
PLAYER_SOURCE_TYPES = frozenset(
    {
        "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
        "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
    }
)
"""Source types that mean a player dealt the damage, not the encounter.

Measured 2026-09-14: a damage-taken row's `sources[].type` reads "Boss", "NPC"
or "Pet" for a hostile source and the class name for a player, and every row
observed had homogeneous sources. Held as the *player* set rather than the
hostile one so the filter fails toward showing a mechanic: an unrecognised
type is kept, because an ability wrongly shown is visible and an ability
wrongly hidden is not.
"""

MECHANIC_MULTIPLE = 2.0
"""Taking this many times the sample's median rate of one ability is worth saying.

The same threshold `players.damage.*` uses against a group median, for the same
reason: below it, sample noise and a real difference are indistinguishable.
"""


def hostile_rows(rows: tuple[AbilityTakenRow, ...]) -> tuple[AbilityTakenRow, ...]:
    """Rows the encounter dealt, dropping those a friendly player dealt."""
    return tuple(
        row
        for row in rows
        if not (row.source_types and all(kind in PLAYER_SOURCE_TYPES for kind in row.source_types))
    )
```

Then the comparison itself:

```python
MAX_MECHANICS_REPORTED = 5
"""At most this many abilities, worst gap first, matching `MAX_OUTLIERS_REPORTED`."""


def _rate(landings: int, seconds: float) -> float:
    return landings / seconds * 60


def compare_mechanics(
    ours: tuple[AbilityTakenRow, ...],
    our_seconds: float,
    sample: MechanicsSample,
    *,
    scope: str,
) -> list[Finding]:
    """Abilities this raid took far more often than kills of the same boss did.

    States landings per minute and nothing else. It never says a mechanic was
    missed: that is a claim about intent no table supports, and master design
    5.5 refuses it. The reader is handed two counts and draws their own
    conclusion.
    """
    # An empty sample means no comparison ran at all, which the caller states
    # once. Repeating it per ability would bury the findings that did run.
    if not sample.members or our_seconds <= 0:
        return []

    their_rows = [
        {row.ability_id: row for row in hostile_rows(member.abilities)}
        for member in sample.members
    ]
    total = len(sample.members)

    candidates: list[tuple[float, Finding]] = []
    for our_row in hostile_rows(ours):
        our_rate = _rate(our_row.landings, our_seconds)
        if our_rate <= 0:
            continue

        # A member that never took this ability contributes a zero, not an
        # absence. The encounter is fixed, so both sides draw from the same
        # ability set, and an ability we took and they did not is precisely
        # the finding. Dropping them would also let the denominator drift
        # from the number of references the title names.
        their_rates = [
            _rate(rows[our_row.ability_id].landings, member.row.duration_seconds)
            if our_row.ability_id in rows
            else 0.0
            for rows, member in zip(their_rows, sample.members, strict=True)
        ]
        carrying = sum(1 for rows in their_rows if our_row.ability_id in rows)

        their_median = median(their_rates)
        low, high = observed_range(their_rates)
        # A ratio against zero is not computed. Where the sample took none and
        # we took some, the gap is the whole finding and the evidence says so.
        if their_median > 0 and our_rate / their_median < MECHANIC_MULTIPLE:
            continue

        candidates.append(
            (
                our_rate - their_median,
                Finding(
                    id="mechanics.ability",
                    title=(
                        f"{scope} took {our_row.landings} of {our_row.ability_name} "
                        f"where the references took a median of {their_median:.1f} a minute"
                    ),
                    detail=(
                        f"{our_rate:.1f} landings a minute against a reference median of "
                        f"{their_median:.1f}. This states a difference, not a mistake: "
                        "whether any single landing was avoidable is not something the "
                        "log records."
                    ),
                    confidence=Confidence.MEASURED,
                    seconds_lost=None,
                    evidence=(
                        f"ours {our_rate:.1f} a minute over {our_seconds:.0f}s",
                        f"reference median {their_median:.1f} a minute",
                        f"range {low:.1f} to {high:.1f} across {total} reference kills",
                        f"{count_phrase(carrying, total)} references took it at all",
                    ),
                    facts=(
                        FindingFact(
                            label="This raid",
                            value=f"{our_rate:.1f} a minute",
                            confidence=Confidence.DERIVED,
                        ),
                        FindingFact(
                            label="Reference median",
                            value=f"{their_median:.1f} a minute",
                            confidence=Confidence.DERIVED,
                        ),
                        FindingFact(label="Range", value=f"{low:.1f} to {high:.1f}"),
                        FindingFact(label="Landings", value=f"{our_row.landings}"),
                    ),
                    ability_id=our_row.ability_id,
                    ability_name=our_row.ability_name,
                    quantifier=quantifier_for(carrying, total),
                ),
            )
        )

    candidates.sort(key=lambda pair: -pair[0])
    findings = [
        finding.model_copy(update={"id": f"mechanics.ability.{rank}"})
        for rank, (_, finding) in enumerate(candidates[:MAX_MECHANICS_REPORTED])
    ]
    # Reuses the sample module's own wording rather than inventing a second way
    # to say the same thing.
    if total < MIN_SAMPLE_FOR_AGGREGATE:
        return too_few(findings, total)
    return findings
```

**No sentence this function produces may contain "missed", "avoidable", "should have" or "failed".** The rank is assigned after sorting, which is why the `id` is built twice — `compare_spells_sample` does the same and explains why in `_one_row_per_sentence`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/domain/comparison/test_mechanics.py -v`
Expected: PASS, 9 tests (3 from Task 4, 6 here).

- [ ] **Step 5: MANDATORY mutation — three of them**

Run each, confirm the named failure, and restore before the next.

1. Delete the `* 60` from the rate, making it landings per second on both sides. Expected: `test_an_ability_we_took_far_more_of_than_the_sample_is_a_finding` FAILS on the evidence assertions — rates become 0.1 and 0.025, so neither "6.0" nor "1.5" appears. **The ratio assertions alone would have survived this**, because a ratio is scale-free; the evidence assertions are the only thing that catches it.
2. Change the member rate to use `hit_count` alone instead of `landings`. Expected: a test fails — if none does, every fixture has `tick_count` zero, which is mutation shape 2. Give one reference a tick count and assert the median moves.
3. Change `median` to `max` over the member rates. Expected: `..._is_a_finding` FAILS, because the evidence states 2.5 where 1.5 was asserted. Note it will **not** fail on the ratio: median 1.5 gives 4.0 and max 2.5 gives 2.4, and both clear `MECHANIC_MULTIPLE`. The fixture rates are 0.5, 1.0, 1.5, 2.0 and 2.5 precisely so median and max differ — mutation shape 3 is a sample of identical values, which this fixture avoids.

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/comparison/mechanics.py tests/domain/comparison/test_mechanics.py
git commit
```

Subject: `Compare what the raid took against kills of the same boss`. Body: why landings and not damage, and why an absent ability counts as zero rather than as absence.

---

## Task 6: Rank raid findings by severity

Design §7. Slice 1 denominates everything in seconds and `rank_findings` sorts on `seconds_lost`, with every `None` falling to the bottom in arbitrary order. Most findings this plan adds cost no seconds, so a raid file ranked that way has no ranking at all.

**No `severity` field is added to `Finding`.** A required one touches every slice-1 analyser, which §7 explicitly says not to disturb; an optional one defaults quietly, which is this repository's documented failure mode. The table lives in the ranker, and a test enumerates every family the raid path can emit so a new analyser cannot slip in on a default.

**Files:**
- Create: `src/wowperf/domain/analysis/severity.py`
- Create: `tests/domain/analysis/test_severity.py`

**Interfaces:**
- Consumes: `Finding`, `rank_findings` from `domain/findings.py` — **`rank_findings` is not modified.**
- Produces: `severity.SEVERITY_BY_FAMILY: dict[str, int]`, `severity.family_of(finding_id: str) -> str`, `severity.rank_raid_findings(findings: Iterable[Finding]) -> list[Finding]`

The eight families the raid path can emit, verified by grep of every analyser `analyse_encounter` calls plus this plan's two additions: `deaths`, `mechanics`, `players`, `defensives`, `consumables`, `interrupts`, `compare`.

- [ ] **Step 1: Write the failing test**

```python
# ABOUTME: Raid findings rank by severity, then by what each analyser measured.
# ABOUTME: The enumerating test is what stops a new analyser ranking on a default.

import pytest

from wowperf.domain.analysis.severity import (
    SEVERITY_BY_FAMILY, family_of, rank_raid_findings,
)
from wowperf.domain.findings import Confidence, Finding


def finding(finding_id: str, seconds: float | None = None) -> Finding:
    return Finding(
        id=finding_id, title=finding_id, detail="", confidence=Confidence.MEASURED,
        seconds_lost=seconds,
    )


def test_a_death_outranks_a_mechanic_even_with_no_seconds() -> None:
    ranked = rank_raid_findings([finding("mechanics.ability.0"), finding("deaths.total")])
    assert [item.id for item in ranked] == ["deaths.total", "mechanics.ability.0"]


def test_within_one_family_seconds_still_order_them() -> None:
    ranked = rank_raid_findings(
        [finding("deaths.single.0", 10.0), finding("deaths.single.1", 40.0)]
    )
    assert [item.id for item in ranked] == ["deaths.single.1", "deaths.single.0"]


def test_an_unknown_family_sorts_last_rather_than_first() -> None:
    # A new analyser that nobody added to the table must not silently outrank
    # a death. Last is the safe default: visible, and harmless.
    ranked = rank_raid_findings([finding("unheard.of.0"), finding("consumables.never.x")])
    assert [item.id for item in ranked] == ["consumables.never.x", "unheard.of.0"]


@pytest.mark.parametrize(
    "family",
    ["deaths", "mechanics", "players", "defensives", "consumables", "interrupts", "compare"],
)
def test_every_family_the_raid_path_emits_has_a_severity(family: str) -> None:
    # The whole guarantee of the table-not-a-field design rests on this test.
    # If an analyser is added to `analyse_encounter`, its family belongs here.
    assert family in SEVERITY_BY_FAMILY


def test_family_of_reads_the_first_segment() -> None:
    assert family_of("mechanics.ability.3") == "mechanics"
    assert family_of("deaths.total") == "deaths"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/domain/analysis/test_severity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.domain.analysis.severity'`

- [ ] **Step 3: Implement**

```python
SEVERITY_BY_FAMILY = {
    "deaths": 0,
    "mechanics": 1,
    "players": 2,
    "defensives": 3,
    "consumables": 4,
    "interrupts": 5,
    "compare": 6,
}
"""How much each finding family is worth reading first, lowest first.

A table rather than a field on `Finding`: a required field would touch every
slice-1 analyser, which design 7 says not to disturb, and an optional one would
let a new analyser rank on a default nobody chose. The weakness of a table is
that same silent default, which
`test_every_family_the_raid_path_emits_has_a_severity` closes by enumeration.

Deaths first because a death ends a player's contribution outright. Mechanics
next because it is the one finding that says what to do differently. `compare`
last because a confound explains the others rather than standing beside them.
"""

UNKNOWN_SEVERITY = max(SEVERITY_BY_FAMILY.values()) + 1


def family_of(finding_id: str) -> str:
    return finding_id.split(".", 1)[0]


def rank_raid_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Severity first, then time cost within a family, as design 7 specifies.

    `rank_findings` is untouched and still ranks Mythic+: slice 1 depends on
    its present behaviour, and nothing about Mythic+ changes here.
    """
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_BY_FAMILY.get(family_of(finding.id), UNKNOWN_SEVERITY),
            finding.seconds_lost is None,
            -(finding.seconds_lost or 0.0),
        ),
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/domain/analysis/test_severity.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: MANDATORY mutation — prove severity outranks seconds**

Remove the severity element from the sort key, leaving the two `rank_findings` elements.

Run: `uv run pytest tests/domain/analysis/test_severity.py -v`
Expected: `test_a_death_outranks_a_mechanic_even_with_no_seconds` FAILS.

Note why it fails rather than passing by luck: both findings in that fixture have `seconds_lost=None`, so without severity the sort is stable and returns them in input order, which is `mechanics` first. **Restore before committing.**

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/analysis/severity.py tests/domain/analysis/test_severity.py
git commit
```

Subject: `Rank a raid's findings by severity before seconds`. Body: why a table in the ranker and not a field on the model.

---

## Task 7: Wire the analysers into `analyse_encounter`

**Files:**
- Modify: `src/wowperf/domain/analysis/encounter_service.py`
- Modify: `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes: `analyse_damage_outliers` (Task 1), `MechanicsSample` and `compare_mechanics` (Task 5), `rank_raid_findings` (Task 6).
- Produces: `analyse_encounter(loaded, defensives, consumables, *, roles=Roles(), mechanics=MechanicsSample(), our_abilities=())` returning findings ranked by `rank_raid_findings`.

The two new keyword arguments default to empty so every existing caller keeps working and the signature change is additive.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/analysis/test_encounter_service.py`:

The module imports `Consumables`, `Encounter`, `Player` and `CastEvent` already; add `DamageTakenEvent`, `Roles`, and the four mechanics names from `domain/comparison/mechanics.py`. It already has `DEFENSIVES` and an `a_loaded_encounter(**overrides)` factory whose
`encounter` field an override can replace. Add beside them:

```python
ROLES = Roles(tanks=("Warrior/Protection",))

RAID = (
    Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=12, name="Stonewake", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=13, name="Bríala", class_name="Mage", spec="Arcane", item_level=700),
)


def a_raid_encounter() -> Encounter:
    """Three players and a 120-second fight, so a median has three takers."""
    return Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=121_000,
        players=RAID,
    )


def took(actor_id: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=400, ability_name="Ravenous Feast",
        amount=amount, timestamp_ms=2_000,
    )


def test_the_outlier_finding_now_reaches_a_raid_report() -> None:
    # `roles` stopped being inert with this plan: the outlier half of
    # `analyse_players` is the one piece of it a boss fight supports.
    loaded = a_loaded_encounter(
        encounter=a_raid_encounter(),
        damage_taken=(took(11, 400), took(12, 100), took(13, 100)),
    )
    findings = analyse_encounter(loaded, DEFENSIVES, Consumables(), roles=ROLES)
    assert any(finding.id.startswith("players.damage.") for finding in findings)


def test_a_mechanic_outranks_a_defensive_though_neither_costs_seconds() -> None:
    """Severity, and only severity, can produce this order.

    Both families carry `seconds_lost=None`, and `analyse_encounter` appends
    defensives long before mechanics, so under `rank_findings` the sort is
    stable and defensives come first. Deaths would have been the wrong pair to
    test with: a raid death does carry seconds, so `rank_findings` already
    sorts it above a mechanic and the assertion could not have failed.
    """
    sample = MechanicsSample(
        members=(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ref", fight_id=1, difficulty=4, size=20,
                    duration_ms=120_000, deaths=0,
                ),
                abilities=(),
            ),
        )
    )
    ours = (
        AbilityTakenRow(
            ability_id=400, ability_name="Ravenous Feast", hit_count=12,
            source_types=("Boss",),
        ),
    )
    findings = analyse_encounter(
        a_loaded_encounter(encounter=a_raid_encounter()),
        DEFENSIVES, Consumables(), roles=ROLES,
        mechanics=sample, our_abilities=ours,
    )
    families = [finding.id.split(".", 1)[0] for finding in findings]
    assert "mechanics" in families, "the fixture must produce a mechanics finding"
    assert "defensives" in families, "the fixture must produce a defensives finding"
    assert families.index("mechanics") < families.index("defensives")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/domain/analysis/test_encounter_service.py -v`
Expected: FAIL — `analyse_encounter() got an unexpected keyword argument 'mechanics'`

- [ ] **Step 3: Wire it**

Add the two calls and swap the ranker:

```python
    findings += analyse_damage_outliers(encounter.players, loaded.damage_taken, roles)
    findings += compare_mechanics(
        our_abilities, encounter.duration_seconds, mechanics, scope=encounter.boss_name
    )
    return rank_raid_findings(findings)
```

Rewrite the docstring's `roles` paragraph: it is no longer accepted-and-unused. Keep the paragraph explaining the four absent slice-1 analysers, and amend it — `analyse_players`' activity half is still absent, its outlier half is not.

- [ ] **Step 4: Run the whole gate**

Run: `uv run pytest`
Expected: all green, and the count risen by this task's new tests.

- [ ] **Step 5: MANDATORY mutation — prove the ranker swap is observable**

Change `rank_raid_findings` back to `rank_findings`.

Run: `uv run pytest tests/domain/analysis/test_encounter_service.py -v`
Expected: `test_a_mechanic_outranks_a_defensive_though_neither_costs_seconds` FAILS — under `rank_findings` both families sort equal on `(None, 0.0)`, the sort is stable, and defensives were appended first.

If it passes, the two findings are not both `seconds_lost=None`, or mechanics is no longer appended after defensives. Check both before changing the test. **Restore before committing.**

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/analysis/encounter_service.py tests/domain/analysis/test_encounter_service.py
git commit
```

Subject: `Run the two comparisons a boss fight supports`.

---

## Task 8: Make the flags live

Plan 1 left `--player`, `--all-players` and `--no-compare` accepted and inert, and says so on every run. This task makes them select subjects for the mechanics comparison.

**Files:**
- Modify: `src/wowperf/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2 to 7.
- Produces: `raid` writing a findings file whose `comparison` block reports what was compared.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py` a test that `raid --help` no longer describes the three flags as unimplemented, and one that the "not yet available" notice is gone:

```python
def test_the_raid_flags_no_longer_announce_themselves_as_inert() -> None:
    # Read from the command's own help rather than from cli.py's source: typer
    # infers `--player` from the parameter name, so the string is not in the
    # source at all. `plain` strips the box-drawing Rich wraps help text in.
    help_text = plain(CliRunner().invoke(app, ["raid", "--help"]).output)
    assert "not yet implemented" not in help_text.lower()


def test_no_compare_writes_a_findings_file_that_compared_nothing() -> None:
    # The flag has to be observable in the artefact, not only in the absence of
    # a network call a unit test cannot see.
    result = CliRunner().invoke(
        app, ["raid", "abc123", "--fight", "22", "--no-compare", "--out", str(tmp)]
    )
    assert result.exit_code == 0
    payload = json.loads((tmp / "abc123-22.findings.json").read_text(encoding="utf-8"))
    assert payload["comparison"]["compared"] is False
    assert payload["comparison"]["references"] == []
```

`test_the_raid_warning_names_only_findings_the_encounter_analyser_emits` already exists in this
file and holds `RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE` in step with what `analyse_encounter`
emits. Step 5 below says what it should now assert.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -k raid -v`
Expected: FAIL — the help still carries "Not yet implemented".

- [ ] **Step 3: Rewrite the three flag helps and delete the notice**

Remove `RAID_COMPARISON_NOT_YET_AVAILABLE` and its `typer.secho` call, and give each flag the help `analyze` gives it.

- [ ] **Step 4: Assemble the sample and call the analysers**

Following `analyze`'s existing `_samples` shape:

1. Build `WclEncounterRankingRepository` beside the run repository in `build_repository`'s caller.
2. Unless `--no-compare`, call `reference_kills(encounter.encounter_id, encounter.difficulty, encounter.partition)`, pass the rows through `select_reference_kills(rows, our_size=encounter.size, our_difficulty=encounter.difficulty)`, and fetch each survivor's ability table, building one `MechanicsMember` each.
3. Fetch our own raid-wide ability table with `ABILITY_TAKEN_TABLE_QUERY`, and one scoped table per subject with `ABILITY_TAKEN_TABLE_BY_VICTIM_QUERY`.
4. Call `analyse_encounter` with `mechanics=` and `our_abilities=`.
5. Fill the `comparison` block with what actually happened: `compared`, the subjects, `sample_size`, and a `ReferenceRecord` per reference so the provenance links land in the findings file as they do for `analyze`.

**Cost note for the implementer, measured 2026-09-14:** each ability table is about one point, so a five-reference sample is about five. Per-player tables are one point each, so `--all-players` at twenty is about twenty. Points are billed per table even when tables are aliased into one operation, so aliasing saves requests and not points.

- [ ] **Step 5: Amend the ranked-not-additive note**

`RAID_FINDINGS_ARE_RANKED_NOT_ADDITIVE` currently names only the `deaths.*` nesting, correctly, because those were the only findings carrying seconds. That is still true — neither `mechanics.*` nor `players.damage.*` carries `seconds_lost`. **Leave the sentence as it is**, and add one clause saying findings are now ordered by severity first, so a reader does not read the order as a time ranking. The existing test holds the note in step with the analyser; update it to match.

- [ ] **Step 6: Run the gate**

Run: `uv run pytest`
Expected: all green.

- [ ] **Step 7: MANDATORY mutation — prove `--no-compare` is honoured**

Make `--no-compare` fetch the sample anyway.

Run: `uv run pytest tests/test_cli.py -k raid -v`
Expected: a test fails. If none does, there is no test asserting that `--no-compare` produces `compared: False` and an empty reference list — write one now. **Restore before committing.**

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/cli.py tests/test_cli.py
git commit
```

Subject: `Let the raid command compare what it loaded`.

---

## Task 9: End to end against a real kill and a real wipe

`docs/plans/2026-09-13-comparison-table-rulings.md` §1.4: real data found what no offline test could, twice. **Budget a real run before trusting any comparison work.**

**Files:**
- Modify: `tests/e2e/test_raid_e2e.py`

- [ ] **Step 1: Extend the two existing tests**

They already load a real kill and a real wipe through `WclRunRepository.load_encounter` and assert the loaded streams are non-empty. Add, to each: that at least one `mechanics.ability.*` finding or an explicit empty-sample reason exists, that no finding id starts with any `KEYSTONE_SHAPED` prefix, and that the findings come back in non-decreasing severity order.

Guard every collection assertion with a non-empty check first. A wipe with no comparable reference is a real outcome, not a failure — assert the withholding, not a finding.

- [ ] **Step 2: Run them**

```bash
WOWPERF_E2E_RAID_KILL=... WOWPERF_E2E_RAID_WIPE=... uv run pytest -m e2e -v
```

Expected: 2 passed. Fight 2 of report `cW38jmwdnZfbHVL4` is a kill (encounter 3470, 316.5s, 0 deaths); fight 30 is a wipe (encounter 3492, 480.0s, 21 deaths). Both are difficulty 4, size 20.

- [ ] **Step 3: Record the measured cost**

Run each command against a fresh `--cache-dir` and read the cost from the command's own "Rate limit: ... points spent" line. Update the module docstring's cost table with the new figures beside plan 1's 14.21 and 34.21. **State no figure you did not measure.**

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_raid_e2e.py
git commit
```

Subject: `Compare a real kill and a real wipe end to end`.

---

## Task 10: Record the rulings

Plan 1's ledger lived only in gitignored scratch and was destroyed before anyone read it; its fifteen rulings are gone. The repository already has this convention — `docs/plans/2026-09-13-comparison-table-rulings.md` and `2026-09-13-earlier-plan-rulings-archive.md`.

- [ ] **Step 1: Write `docs/plans/2026-09-14-raid-mechanics-rulings.md`**

Modelled on the comparison-table rulings: the rulings made during execution with their reasoning and their cost if wrong; every mutation that survived a review and why; any coupling no test announces; and the gaps left open. Do not restate what the commits already say.

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-09-14-raid-mechanics-rulings.md
git commit
```

Subject: `Keep this plan's rulings where git can hold them`.

---

## What this plan deliberately leaves undone

Named here so the next plan starts from a record rather than a rediscovery.

- **The external frame.** §6.1 to §6.7 — `damage.total`, `damage.targets`, `casts.count`, `casts.missing`, `talents`, `uptime.buffs`, `rank` — and §8.2's parse half. Plan 3.
- **The `ParseMember` narrowing**, and with it the `casts_in` predicate. §8.2's amendment describes both; they belong with the parse axis they serve. **The trap goes with them:** `casts_in` filters on `event.pull_index not in indices`, and a raid cast's `pull_index` is `None`, so a raid sample handed to it today returns zero casts for every ability and raises nothing.
- **The report.** §10. `raid` writes findings JSON only.
- **`dps` versus `bossdps`.** §14 item 5 narrowed it to two and left the choice to the plan that builds §6.1.
- **The healing fight-wide fetch.** Measured at 8.00 points against the per-death fan-out's 21.00, with identical data, break-even around eight deaths. It changes `repository.py` on the Mythic+ path too, so it is its own change and not this plan's. **The obvious implementation is wrong:** the server-side filter `target.id in (...)` returns zero rows for one point, silently.
- **`CLAUDE.md`'s list of reports holding real people** still owes `cW38jmwdnZfbHVL4`, which holds twenty. Design §12 records it.
