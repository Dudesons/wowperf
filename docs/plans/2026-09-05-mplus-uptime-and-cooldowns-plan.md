# Mythic+ Post-Mortem, Plan D: Cooldown Ceiling and Aura Uptime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two comparisons slice 1 deferred — how often a player pressed a defensive against how often its cooldown allowed, and how their buff and debuff uptime on boss pulls compares to the top parse of their specialisation.

**Architecture:** Two independent deliverables in two layers. The cooldown ceiling extends the existing `analysis/defensives.py`: it needs no reference run, because it measures a player against the game's own cooldown rules, so it appears under `--no-compare` too. Aura uptime is a new pure module under `domain/comparison/`, fed by one new aliased GraphQL query that returns both aura tables for one actor in a single cached call; the fetch is a new scoped repository method rather than an addition to `load`, so only the two actors being compared are ever paid for.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `typer`, `httpx`, `pytest`, `ruff`, `mypy`.

**Spec:** `docs/plans/2026-09-03-mplus-postmortem-design.md` — §5.7 and §6.5 item 5 are what this plan implements, amended 2026-09-05. §2.2's aura block is load-bearing.

**Depends on:** Plans A (`be84a22`), B (`9bd47fb`) and C (`ebe3ddc`), all merged. Read `src/wowperf/domain/analysis/defensives.py`, `src/wowperf/domain/comparison/spells.py`, `src/wowperf/domain/comparison/service.py`, `src/wowperf/adapters/wcl/repository.py` and `src/wowperf/cli.py` before starting.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no file reads, no `tomllib`. Adapters do that.
- **Every `Finding` carries a `Confidence`** of `measured`, `derived`, or `inferred`, and the badge must match how the claim was obtained. The test is not whether arithmetic happened: it is whether the claim needed an assumption that could be wrong.
- **Every finding is denominated in seconds.** A finding with no honest seconds figure sets `seconds_lost=None`. **Never `seconds_lost=0.0` for something merely unmeasured** — zero sorts above every `None` in the ranking. That bug shipped in Plan B and had to be fixed twice.
- **The LLM never computes a number.** Every metric comes from tested Python.
- **No hardcoded season data.** No zone, encounter, affix or ability ID as a literal in `src/`. Values with no API source live in `data/*.toml` with a `verified` date.
- **Cache every Warcraft Logs response.** The budget is 3600 points an hour.
- **Never invent a Warcraft Logs field name.** Every field this plan uses is in "Verified schema" below, confirmed against the live API on 2026-09-05.
- **Never accumulate a corpus of other players' logs.** RPGLogs terms §5d.
- **Aura band timestamps are milliseconds relative to report start**, the same clock as `Pull.start_ms` / `Pull.end_ms`.
- **English** in code, comments, error strings, and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains **why**.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- Every file starts with two `# ABOUTME: ` comment lines. Empty `__init__.py` markers are exempt.
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument). Ruff's line length is 100.
- **`uv` is not on PATH.** Every bash command using it begins `export PATH="$HOME/.local/bin:$PATH"`.

## Verified schema

Confirmed against the live API on 2026-09-05, using report `6Kx1P9GbNXrcLdHa` fight 36, actor 7 (`Dudesons`, DeathKnight Blood). **These are the real names and the real behaviour.** Nothing outside this section may be assumed.

| Field | Verified shape |
| --- | --- |
| `ReportData.report.table` arguments | `abilityID: Float`, `dataType: TableDataType`, `death: Int`, `difficulty: Int`, `encounterID: Int`, `endTime: Float`, `fightIDs: [Int]`, `filterExpression: String`, `hostilityType: HostilityType`, `killType: KillType`, `sourceAurasAbsent: String`, `sourceAurasPresent: String`, `sourceClass: String`, `sourceID: Int`, `sourceInstanceID: Int`, `startTime: Float`, `targetAurasAbsent: String`, `targetAurasPresent: String`, `targetClass: String`, `targetID: Int` |
| `TableDataType` members used | `Buffs`, `Debuffs` |
| `HostilityType` members used | `Friendlies` (the default), `Enemies` |
| `table` return | untyped JSON: `{"data": {"auras": [...], "totalTime": Int, "useTargets": …, "startTime": Int, "endTime": Int, "logVersion": Int, "gameVersion": Int}}` |
| one `auras` entry | `name: String`, `guid: Int`, `type: Int`, `abilityIcon: String`, `totalUptime: Int` (milliseconds), `totalUses: Int`, `bands: [{startTime: Int, endTime: Int}]` |
| `ReportFight.friendlyPlayers` | the roster of **that fight** — actor ids |

Four behaviours established by running the query, not by reading documentation:

- **`table(dataType: Buffs, targetID: N)` is the auras the player carried.** ~~`table(dataType: Debuffs, sourceID: N, hostilityType: Enemies)` is the debuffs the player kept on enemies.~~ **The second half was never verified and is false.** Corrected 2026-09-05 by Plan D's own Task 9: that combination returns zero auras, and no argument narrows the enemy-debuff table to one caster — `sourceID`, `filterExpression` and `sourceClass` each zero it. `hostilityType: Enemies` alone returns the whole group's debuffs. See design §2.2 for the measured table. The on-target half of this plan ships inert.
- **`bands` carry the exact intervals**, on the same millisecond clock as `Pull.start_ms`. Uptime over an arbitrary sub-window is an intersection, not a second query. Confirmed by recomputing Coagulopathy's uptime over fight 36's three boss pulls and matching the boss window the analysers already derive: 613086ms of 613086ms.
- **`totalTime` is the queried window in milliseconds**, not the aura's uptime. On fight 36 it read `1857623` for both tables — the whole fight.
- **The events endpoint is the wrong tool.** `events(dataType: Buffs)` returns aura *events* needing pagination and manual interval reconstruction; the table returns the same information pre-aggregated with the bands already computed. Do not use the events path.

Measured cost, same day: a roster query, four aura tables and a `rateLimitData` read together spent **12.02 points of 3600**.

## Decisions this plan makes

Recorded here so an implementer does not rediscover them, and so a reviewer does not flag them.

1. **Auras are fetched by a new scoped repository method, not by `load`.** An aura table is per-actor. Folding it into `load` would fetch ten tables per run — five players times two tables — for the two actors anyone looks at. `auras(report_code, fight_id, actor_id)` costs two aliased tables in one cached query, and the CLI calls it exactly twice.
2. **Both tables travel in one aliased query.** GraphQL aliases let `onSelf` and `onTargets` select `table` twice in one document. `talents_query` already aliases `talentImportCode` per actor and works against the live API, so the mechanism is established here rather than assumed.
3. **The ceiling finding fires only when the defensive was pressed at least once.** Never-pressed is §5.6's finding and already ships. Reporting both would say the same thing twice about one ability, with two different badges.
4. **The denominator is approximate, and that is why the badge is `inferred`.** `alive_combat_seconds` is `run.total_pull_seconds` minus that player's `Death.seconds_until_next_action` spans. A run-back can extend past a pull's end, so the subtraction can overshoot. An `inferred` badge on a claim that already carries a situational caveat is the honest place to put that.
5. **Uptime is compared as a fraction of boss time, never as seconds.** Two runs have different boss durations, so a seconds difference would mean nothing. Every uptime finding carries `seconds_lost=None`.
6. **`ParseReference` carries the reference's auras; ours travel as a new optional argument to `compare`.** Auras are per-actor, so `LoadedRun` is the wrong home for ours. The reference's belong with the rest of the reference, beside `row` and `loaded`.

## File Structure

| File | Responsibility |
| --- | --- |
| `data/defensives.toml` | *Modified.* Each ability gains `cooldown_seconds` and `charges` |
| `src/wowperf/domain/season.py` | *Modified.* `DefensiveAbility` gains the two fields |
| `src/wowperf/adapters/config/toml.py` | *Modified.* Reads them |
| `src/wowperf/domain/analysis/defensives.py` | *Modified.* §5.7's ceiling findings beside §5.6's never-pressed ones |
| `src/wowperf/domain/analysis/service.py` | *Modified.* `analyse_defensives` gains `deaths` |
| `src/wowperf/domain/auras.py` | `Aura`, `AuraBand`, `PlayerAuras`, `uptime_seconds_in` |
| `src/wowperf/adapters/wcl/queries.py` | *Modified.* Adds `AURA_TABLE_QUERY` |
| `src/wowperf/adapters/wcl/ingest.py` | *Modified.* Adds `build_player_auras` |
| `src/wowperf/adapters/wcl/repository.py` | *Modified.* Adds `WclRunRepository.auras` |
| `src/wowperf/domain/comparison/reference.py` | *Modified.* `ParseReference` gains `auras` |
| `src/wowperf/domain/comparison/uptime.py` | §6.5 item 5: uptime findings on self and on target |
| `src/wowperf/domain/comparison/service.py` | *Modified.* Runs the uptime comparison |
| `src/wowperf/cli.py` | *Modified.* Fetches both actors' auras and passes them through |

---

### Task 1: Cooldown durations join the defensive list

**Files:**
- Modify: `data/defensives.toml`, `src/wowperf/domain/season.py`, `src/wowperf/adapters/config/toml.py`
- Test: `tests/domain/test_season.py`, `tests/adapters/config/test_toml.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces:
  - `DefensiveAbility.cooldown_seconds: float` — **required**, no default
  - `DefensiveAbility.charges: int = 1`
  - `load_defensives` reads both

`cooldown_seconds` is required because a defensive whose cooldown is unknown cannot be given a ceiling, and a default would let that failure travel silently into a printed number — the same shape as the bug Plan A shipped when a missing killing blow defaulted to ability id 0. `charges` defaults to 1 because the overwhelming majority of defensives have exactly one, and spelling it out thirteen times would bury the two that do not.

The values below are the live cooldowns for patch 12.1, in seconds, and are what the `verified` date attests to. They are the base cooldowns without talent reductions, which is the honest floor: a talented shorter cooldown makes the ceiling an underestimate, and an underestimate cannot produce a false accusation.

- [ ] **Step 1: Write the failing domain test**

Append to `tests/domain/test_season.py`:

```python
def test_a_defensive_carries_the_cooldown_its_ceiling_is_computed_from() -> None:
    ability = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0)

    assert ability.cooldown_seconds == 180.0
    assert ability.charges == 1


def test_a_defensive_with_two_charges_says_so() -> None:
    ability = DefensiveAbility(
        ability_id=55342, name="Mirror Image", cooldown_seconds=120.0, charges=2
    )

    assert ability.charges == 2


def test_a_defensive_without_a_cooldown_cannot_be_built() -> None:
    with pytest.raises(ValidationError):
        DefensiveAbility(ability_id=1, name="Nameless")
```

Add `import pytest` and `from pydantic import ValidationError` to that file's imports if they are not already there, and add `cooldown_seconds=180.0` to any existing `DefensiveAbility(...)` in the file.

- [ ] **Step 2: Run it and watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_season.py -v`
Expected: FAIL, a Pydantic `ValidationError` naming `cooldown_seconds` as an unexpected keyword.

- [ ] **Step 3: Add the fields**

In `src/wowperf/domain/season.py`, inside `class DefensiveAbility`:

```python
class DefensiveAbility(Frozen):
    """One personal damage-reduction cooldown, identified by its spell id."""

    ability_id: int
    name: str
    # Required, not defaulted: an ability whose cooldown is unknown has no honest
    # ceiling, and a default would let that travel silently into a printed number.
    cooldown_seconds: float
    charges: int = 1
```

- [ ] **Step 4: Write the failing adapter test**

Append to `tests/adapters/config/test_toml.py`:

```python
def test_the_defensive_list_carries_cooldowns_and_charges() -> None:
    defensives = load_defensives()
    blood = defensives.for_spec("DeathKnight", "Blood")

    icebound = next(a for a in blood if a.ability_id == 48792)
    assert icebound.cooldown_seconds == 180.0
    assert icebound.charges == 1


def test_every_listed_defensive_has_a_positive_cooldown() -> None:
    defensives = load_defensives()

    for _spec, abilities in defensives.entries:
        for ability in abilities:
            assert ability.cooldown_seconds > 0, f"{ability.name} has no usable cooldown"
```

- [ ] **Step 5: Run it and watch it fail**

Run: `uv run pytest tests/adapters/config/test_toml.py -v`
Expected: FAIL, a `ValidationError` for the missing `cooldown_seconds` — the TOML has no such key yet.

- [ ] **Step 6: Add the data**

Replace the body of `data/defensives.toml` with:

```toml
# Personal damage-reduction cooldowns, by class and specialisation.
# No API exposes this list or the cooldowns, so both are maintained by hand and dated.
# A spec absent from this file simply produces no defensive findings.
#
# Cooldowns are base values in seconds, without talent reductions. That is
# deliberate: a talented shorter cooldown makes the ceiling an underestimate,
# and an underestimate cannot produce a false accusation.
verified = "2026-09-05"

["Mage/Arcane"]
abilities = [
  { ability_id = 235450, name = "Prismatic Barrier", cooldown_seconds = 25.0 },
  { ability_id = 45438, name = "Ice Block", cooldown_seconds = 240.0 },
  { ability_id = 55342, name = "Mirror Image", cooldown_seconds = 120.0 },
]

["Shaman/Elemental"]
abilities = [
  { ability_id = 108271, name = "Astral Shift", cooldown_seconds = 90.0 },
  { ability_id = 198103, name = "Earth Elemental", cooldown_seconds = 300.0 },
]

["Priest/Shadow"]
abilities = [
  { ability_id = 47585, name = "Dispersion", cooldown_seconds = 120.0 },
  { ability_id = 19236, name = "Desperate Prayer", cooldown_seconds = 90.0 },
]

["Paladin/Holy"]
abilities = [
  { ability_id = 498, name = "Divine Protection", cooldown_seconds = 60.0 },
  { ability_id = 642, name = "Divine Shield", cooldown_seconds = 300.0 },
]

["DeathKnight/Blood"]
abilities = [
  { ability_id = 55233, name = "Vampiric Blood", cooldown_seconds = 90.0 },
  { ability_id = 48792, name = "Icebound Fortitude", cooldown_seconds = 180.0 },
  { ability_id = 49028, name = "Dancing Rune Weapon", cooldown_seconds = 120.0 },
]
```

- [ ] **Step 7: Teach the loader to read them**

In `src/wowperf/adapters/config/toml.py`, inside `load_defensives`, replace the `DefensiveAbility(...)` construction with:

```python
                    DefensiveAbility(
                        ability_id=int(item["ability_id"]),
                        name=str(item["name"]),
                        cooldown_seconds=float(item["cooldown_seconds"]),
                        charges=int(item.get("charges", 1)),
                    )
```

- [ ] **Step 8: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add data/defensives.toml src/wowperf/domain/season.py src/wowperf/adapters/config/toml.py tests/domain/test_season.py tests/adapters/config/test_toml.py
git commit -m "Record how long each defensive stays on cooldown

The API publishes neither cooldown durations nor charge counts, so the ceiling
a player is measured against has to be written down by hand and dated. Base
cooldowns, without talent reductions: an underestimate cannot accuse anyone
falsely."
```

---

### Task 2: Defensive uses against the cooldown ceiling

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py`, `src/wowperf/domain/analysis/service.py`
- Test: `tests/domain/analysis/test_defensives.py`

**Interfaces:**
- Consumes: `DefensiveAbility`, `Defensives` as they stand after Task 1; `Death` from `wowperf.domain.events`; `Run`, `Finding`, `Confidence`.
- Produces:
  - `analyse_defensives(run, casts, defensives, deaths)` — a fourth, **required** argument
  - `CEILING_USE_FRACTION: float = 0.5`, `MIN_CEILING_USES: float = 3.0`
  - Findings with id `defensives.ceiling.<name>.<ability_id>`, or `defensives.ceiling.<name>.<actor_id>.<ability_id>` when two players share a display name

This is §5.7. Three rules keep it honest, and a reviewer will check each:

1. **It fires only when the defensive was pressed at least once.** Never-pressed is §5.6's existing finding. Reporting both would make two claims about one ability with two different badges.
2. **It fires only well below the ceiling** — under `CEILING_USE_FRACTION` of it — and only when the ceiling itself is at least `MIN_CEILING_USES`. A defensive whose cooldown barely fits twice in the run has no story to tell.
3. **The detail states the situational caveat outright.** A defensive is pressed into incoming damage, not on cooldown. "You used it once of a possible eight" is true and useless unless the reader is told what it does and does not mean.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_defensives.py`:

```python
def a_death(actor_id: int, seconds: float | None) -> Death:
    return Death(
        player_name="Tank",
        actor_id=actor_id,
        timestamp_ms=0,
        killing_blow="Something",
        seconds_until_next_action=seconds,
    )


def test_a_defensive_pressed_far_below_its_ceiling_is_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, ())
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "1 of" in ceiling[0].title
    assert ceiling[0].confidence is Confidence.INFERRED
    assert ceiling[0].seconds_lost is None


def test_a_defensive_never_pressed_produces_no_ceiling_finding() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)

    findings = analyse_defensives(run, (), BLOOD_DEFENSIVES, ())

    assert findings_by_prefix(findings, "defensives.ceiling.") == []
    assert findings_by_prefix(findings, "defensives.Tank.") != []


def test_a_defensive_pressed_close_to_its_ceiling_is_not_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    # 1800s / 180s = a ceiling of 10; eight presses is not a story.
    casts = tuple(a_cast(actor_id=1, ability_id=48792) for _ in range(8))

    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, ())

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_a_run_too_short_for_a_meaningful_ceiling_reports_nothing() -> None:
    # 300s / 180s = a ceiling of 1.67, below MIN_CEILING_USES.
    run = a_run_with_one_blood_death_knight(pull_seconds=300.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, ())

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_time_spent_dead_does_not_count_towards_the_ceiling() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)
    # 1200s of the 1800s were spent dead, so the ceiling falls from 10 to 3.33.
    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, (a_death(1, 1200.0),))
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "of 3" in ceiling[0].title, ceiling[0].title


def test_the_ceiling_detail_says_defensives_are_situational() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    finding = findings_by_prefix(
        analyse_defensives(run, casts, BLOOD_DEFENSIVES, ()), "defensives.ceiling."
    )[0]

    assert "incoming damage" in finding.detail
```

Add whatever the file needs to build those fixtures, in its existing style: a `BLOOD_DEFENSIVES` constant holding `Defensives(entries=(("DeathKnight/Blood", (DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0),)),))`, an `a_run_with_one_blood_death_knight(pull_seconds)` helper building a `Run` with `encounter_id=12825`, one player (`actor_id=1`, `name="Tank"`, `class_name="DeathKnight"`, `spec="Blood"`) and a single trash pull of that length, an `a_cast(actor_id, ability_id)` helper, and a `findings_by_prefix(findings, prefix)` helper matching the one in `tests/domain/comparison/test_route.py`. Import `Death` from `wowperf.domain.events`.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/analysis/test_defensives.py -v`
Expected: FAIL, `TypeError: analyse_defensives() takes 3 positional arguments but 4 were given`.

- [ ] **Step 3: Write the ceiling**

In `src/wowperf/domain/analysis/defensives.py`, add the imports and constants at the top:

```python
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.season import Defensives, DefensiveAbility

CEILING_USE_FRACTION = 0.5
"""How far below the ceiling a player must be before it is worth saying anything."""

MIN_CEILING_USES = 3.0
"""Below this the ceiling itself is too small to argue from."""
```

then add these two helpers above `analyse_defensives`:

```python
def _alive_combat_seconds(run: Run, deaths: tuple[Death, ...], actor_id: int) -> float:
    """Combat time this player could actually have pressed a button in.

    Approximate on purpose, and one of the reasons the finding is `inferred`: a
    run-back can extend past the pull it started in, so the subtraction can
    overshoot. Overshooting lowers the ceiling, which makes the claim weaker
    rather than louder.
    """
    dead = sum(
        death.seconds_until_next_action or 0.0
        for death in deaths
        if death.actor_id == actor_id
    )
    return max(run.total_pull_seconds - dead, 0.0)


def _ceiling(alive_seconds: float, ability: DefensiveAbility) -> float:
    """How many times the cooldown alone would have allowed this to be pressed."""
    return alive_seconds / ability.cooldown_seconds * ability.charges
```

Then replace the per-ability loop inside `analyse_defensives`. Both branches are written inline rather than extracted into a helper, because a helper would need six arguments to say one thing. This is the complete replacement for the loop:

```python
        for ability in known:
            base_id = (
                f"{player.name}.{ability.ability_id}"
                if name_counts[player.name] == 1
                else f"{player.name}.{player.actor_id}.{ability.ability_id}"
            )
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)

            if uses:
                alive = _alive_combat_seconds(run, deaths, player.actor_id)
                ceiling = _ceiling(alive, ability)
                if ceiling < MIN_CEILING_USES or uses >= ceiling * CEILING_USE_FRACTION:
                    continue
                findings.append(
                    Finding(
                        id=f"defensives.ceiling.{base_id}",
                        title=(
                            f"{player.name} used {ability.name} {uses} "
                            f"of a possible {ceiling:.0f} times"
                        ),
                        detail=(
                            f"{ability.name} has a {ability.cooldown_seconds:.0f}s cooldown, "
                            f"which fits {ceiling:.0f} times into the {alive:.0f}s this player "
                            "spent alive and in combat. That is a ceiling, not a target: a "
                            "defensive is pressed into incoming damage, not on cooldown, so a "
                            "gap here is a question to ask rather than a mistake to fix."
                        ),
                        confidence=Confidence.INFERRED,
                        seconds_lost=None,
                        evidence=(
                            f"{player.class_name} {player.spec}",
                            f"ability {ability.ability_id}",
                            f"{uses} cast{'s' if uses != 1 else ''} in {alive:.0f}s alive",
                        ),
                    )
                )
                continue

            findings.append(
                Finding(
                    id=f"defensives.{base_id}",
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
```

This needs counts rather than a set, so replace the `cast_ids` accumulator at the top of the function with:

```python
    cast_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cast in casts:
        cast_counts[cast.actor_id][cast.ability_id] += 1
```

and delete the now-unused `cast_ids` and `pressed` locals. Widen the signature and its docstring:

```python
def analyse_defensives(
    run: Run,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Defensives never pressed (§5.6), and defensives pressed far below their ceiling (§5.7).

    Both are `inferred`. The log emits no cooldown-reset or reduction events, so
    neither claim can be measured, and a defensive is pressed into damage rather
    than on cooldown — the ceiling bounds what was possible, not what was right.
    """
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/analysis/test_defensives.py -v`
Expected: the six new tests pass, and every pre-existing test in the file passes once its `analyse_defensives(...)` call is given a fourth argument of `()`.

- [ ] **Step 5: Pass the deaths in**

In `src/wowperf/domain/analysis/service.py`, change the call:

```python
    findings += analyse_defensives(loaded.run, loaded.casts, defensives, loaded.deaths)
```

- [ ] **Step 6: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/defensives.py src/wowperf/domain/analysis/service.py tests/domain/analysis/test_defensives.py
git commit -m "Report defensives pressed far below what their cooldown allowed

The binary 'never pressed' misses the tank who used Icebound Fortitude once in
half an hour. The ceiling is what the cooldown permitted, not what the fight
demanded, so it fires only well below and says so in the same breath."
```

---

### Task 3: Aura value types and the window intersection

**Files:**
- Create: `src/wowperf/domain/auras.py`
- Test: `tests/domain/test_auras.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces:
  - `class AuraBand(Frozen)`: `start_ms: int`, `end_ms: int`
  - `class Aura(Frozen)`: `ability_id: int`, `name: str`, `total_uptime_ms: int`, `uses: int`, `bands: tuple[AuraBand, ...] = ()`
  - `class PlayerAuras(Frozen)`: `actor_id: int`, `on_self: tuple[Aura, ...] = ()`, `on_targets: tuple[Aura, ...] = ()`
  - `def uptime_seconds_in(aura: Aura, windows: tuple[tuple[int, int], ...]) -> float`

`ability_id` rather than `guid`: the rest of the domain calls a spell id `ability_id`, and one vocabulary matters more than matching the wire format. The adapter does the renaming.

The whole reason the design chose the table endpoint over the event stream is `bands`. `uptime_seconds_in` is the function that cashes that in: given the boss-pull windows, it returns the seconds this aura was up inside them.

- [ ] **Step 1: Write the failing tests**

`tests/domain/test_auras.py`:

```python
# ABOUTME: Behaviour tests for aura bands and the window intersection uptime rests on.
# ABOUTME: The interesting cases are a band straddling a window edge and a band outside it.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras, uptime_seconds_in


def an_aura(*bands: tuple[int, int]) -> Aura:
    return Aura(
        ability_id=391477,
        name="Coagulopathy",
        total_uptime_ms=sum(end - start for start, end in bands),
        uses=len(bands),
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in bands),
    )


def test_a_band_entirely_inside_a_window_counts_in_full() -> None:
    assert uptime_seconds_in(an_aura((1000, 4000)), ((0, 10000),)) == 3.0


def test_a_band_entirely_outside_every_window_counts_for_nothing() -> None:
    assert uptime_seconds_in(an_aura((20000, 24000)), ((0, 10000),)) == 0.0


def test_a_band_straddling_a_window_edge_is_clipped_to_the_window() -> None:
    assert uptime_seconds_in(an_aura((8000, 14000)), ((0, 10000),)) == 2.0


def test_a_band_spanning_two_windows_counts_only_the_covered_parts() -> None:
    aura = an_aura((0, 30000))

    assert uptime_seconds_in(aura, ((0, 5000), (20000, 22000))) == 7.0


def test_an_aura_with_no_bands_has_no_uptime() -> None:
    assert uptime_seconds_in(an_aura(), ((0, 10000),)) == 0.0


def test_no_windows_means_no_uptime_rather_than_the_whole_aura() -> None:
    assert uptime_seconds_in(an_aura((0, 5000)), ()) == 0.0


def test_player_auras_default_to_empty_on_both_sides() -> None:
    auras = PlayerAuras(actor_id=7)

    assert auras.on_self == ()
    assert auras.on_targets == ()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/test_auras.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.auras'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/auras.py`:

```python
# ABOUTME: Buff and debuff intervals as pure values, plus uptime over an arbitrary window.
# ABOUTME: Warcraft Logs hands back the bands already computed; this is what reads them.

from wowperf.domain.base import Frozen


class AuraBand(Frozen):
    """One unbroken stretch during which an aura was present.

    Milliseconds relative to report start, the same clock as `Pull.start_ms`.
    """

    start_ms: int
    end_ms: int


class Aura(Frozen):
    """One buff or debuff, with every interval it was up for."""

    ability_id: int
    name: str
    total_uptime_ms: int
    uses: int
    bands: tuple[AuraBand, ...] = ()


class PlayerAuras(Frozen):
    """The two halves of one player's aura picture.

    `on_self` is what the player carried; `on_targets` is what they kept up on
    enemies. The design calls these "on self and on target".
    """

    actor_id: int
    on_self: tuple[Aura, ...] = ()
    on_targets: tuple[Aura, ...] = ()


def uptime_seconds_in(aura: Aura, windows: tuple[tuple[int, int], ...]) -> float:
    """Seconds this aura was up inside the given millisecond windows.

    Bands are clipped to each window rather than counted whole, which is what
    makes a boss-pull-only figure exact rather than an approximation.
    """
    total_ms = 0
    for band in aura.bands:
        for start, end in windows:
            overlap = min(band.end_ms, end) - max(band.start_ms, start)
            if overlap > 0:
                total_ms += overlap
    return total_ms / 1000
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/test_auras.py -v`
Expected: 7 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/auras.py tests/domain/test_auras.py
git commit -m "Model aura bands, and uptime over a window

Warcraft Logs returns the intervals an aura was up for, so restricting uptime
to boss pulls is an intersection rather than a second query. That is the whole
reason the design chose the table endpoint over the event stream."
```

---

### Task 4: One query for both aura tables

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/ingest.py`
- Test: `tests/adapters/wcl/test_ingest_auras.py`

**Interfaces:**
- Consumes: `Aura`, `AuraBand`, `PlayerAuras` from `wowperf.domain.auras`; `IngestError` from `wowperf.adapters.wcl.errors`.
- Produces:
  - `queries.AURA_TABLE_QUERY`
  - `def build_player_auras(payload: dict[str, Any], actor_id: int) -> PlayerAuras` in `ingest.py`

**Field names are fixed.** Use exactly the ones in this plan's "Verified schema" table. Two behaviours there are not guesses:

1. **`table(dataType: Buffs, targetID: N)` is auras on the player; `table(dataType: Debuffs, sourceID: N, hostilityType: Enemies)` is debuffs the player put on enemies.** Swapping these silently reports the wrong half.
2. **One document selects `table` twice, under two aliases.** `talents_query` already aliases a repeated field per actor and works live, so this is an established mechanism here, not an assumption.

- [ ] **Step 1: Add the query**

Append to `src/wowperf/adapters/wcl/queries.py`:

```python
# Two aliased selections of `table`, so one cached query covers both halves of
# "on self and on target". `Buffs` with targetID is what the player carried;
# `Debuffs` with sourceID and Enemies is what they kept up on the enemy.
AURA_TABLE_QUERY = """
query AuraTable($code: String!, $fightId: Int!, $actorId: Int!) {
  reportData {
    report(code: $code) {
      onSelf: table(fightIDs: [$fightId], dataType: Buffs, targetID: $actorId)
      onTargets: table(
        fightIDs: [$fightId]
        dataType: Debuffs
        sourceID: $actorId
        hostilityType: Enemies
      )
    }
  }
}
"""
```

- [ ] **Step 2: Write the failing ingest tests**

`tests/adapters/wcl/test_ingest_auras.py`:

```python
# ABOUTME: Turns the two aliased aura tables into domain values, with real payload shapes.
# ABOUTME: Fixtures follow the schema verified against the live API on 2026-09-05.

from typing import Any

import pytest

from wowperf.adapters.wcl.errors import IngestError
from wowperf.adapters.wcl.ingest import build_player_auras


def a_table(*auras: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"auras": list(auras), "totalTime": 1857623}}


def an_aura(name: str, guid: int, *bands: tuple[int, int]) -> dict[str, Any]:
    return {
        "name": name,
        "guid": guid,
        "type": 1,
        "abilityIcon": "spell_holy_symbolofhope.jpg",
        "totalUptime": sum(end - start for start, end in bands),
        "totalUses": len(bands),
        "bands": [{"startTime": start, "endTime": end} for start, end in bands],
    }


def a_payload(on_self: dict[str, Any], on_targets: dict[str, Any]) -> dict[str, Any]:
    return {"reportData": {"report": {"onSelf": on_self, "onTargets": on_targets}}}


def test_both_halves_land_on_the_side_they_came_from() -> None:
    payload = a_payload(
        a_table(an_aura("Coagulopathy", 391477, (0, 5000))),
        a_table(an_aura("Frost Fever", 55095, (1000, 2000))),
    )

    auras = build_player_auras(payload, actor_id=7)

    assert auras.actor_id == 7
    assert [a.name for a in auras.on_self] == ["Coagulopathy"]
    assert [a.name for a in auras.on_targets] == ["Frost Fever"]


def test_the_wire_calls_it_guid_and_the_domain_calls_it_an_ability_id() -> None:
    payload = a_payload(a_table(an_aura("Coagulopathy", 391477, (0, 5000))), a_table())

    assert build_player_auras(payload, actor_id=7).on_self[0].ability_id == 391477


def test_bands_survive_with_their_timestamps() -> None:
    payload = a_payload(a_table(an_aura("Voracious", 274009, (100, 400), (900, 1000))), a_table())

    aura = build_player_auras(payload, actor_id=7).on_self[0]

    assert [(b.start_ms, b.end_ms) for b in aura.bands] == [(100, 400), (900, 1000)]
    assert aura.total_uptime_ms == 400
    assert aura.uses == 2


def test_an_aura_with_no_bands_is_kept_rather_than_dropped() -> None:
    bandless = {"name": "Satiated", "guid": 326809, "totalUptime": 0, "totalUses": 1}
    payload = a_payload(a_table(bandless), a_table())

    aura = build_player_auras(payload, actor_id=7).on_self[0]

    assert aura.bands == ()
    assert aura.uses == 1


def test_an_empty_table_yields_no_auras_rather_than_raising() -> None:
    payload = a_payload({"data": {"auras": [], "totalTime": 0}}, a_table())

    assert build_player_auras(payload, actor_id=7).on_self == ()


def test_a_missing_table_block_is_an_error_not_an_empty_result() -> None:
    payload = {"reportData": {"report": {"onSelf": None, "onTargets": None}}}

    with pytest.raises(IngestError, match="onSelf"):
        build_player_auras(payload, actor_id=7)
```

The last test matters: a null table and a table with no auras mean different things, and collapsing them would report "this player had no buffs" for a query that failed.

- [ ] **Step 3: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_ingest_auras.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_player_auras'`.

- [ ] **Step 4: Write the builder**

Append to `src/wowperf/adapters/wcl/ingest.py`, adding `Aura`, `AuraBand` and `PlayerAuras` to the imports from `wowperf.domain.auras`:

```python
def _aura_rows(report: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    """The aura list under one aliased table, or an error if the table is absent.

    A table that came back null and a table with no auras are different claims:
    the first is a failed query, the second is a player who carried nothing.
    """
    table = report.get(alias)
    if not isinstance(table, dict):
        raise IngestError(f"The aura response carried no {alias} table")
    data = table.get("data")
    if not isinstance(data, dict):
        raise IngestError(f"The aura response's {alias} table carried no data block")
    return list(data.get("auras") or [])


def _aura(row: dict[str, Any]) -> Aura:
    return Aura(
        ability_id=int(row["guid"]),
        name=str(row["name"]),
        total_uptime_ms=int(row.get("totalUptime") or 0),
        uses=int(row.get("totalUses") or 0),
        bands=tuple(
            AuraBand(start_ms=int(band["startTime"]), end_ms=int(band["endTime"]))
            for band in row.get("bands") or ()
        ),
    )


def build_player_auras(payload: dict[str, Any], actor_id: int) -> PlayerAuras:
    """Both aliased aura tables for one actor, as domain values."""
    report = payload["reportData"]["report"]
    return PlayerAuras(
        actor_id=actor_id,
        on_self=tuple(_aura(row) for row in _aura_rows(report, "onSelf")),
        on_targets=tuple(_aura(row) for row in _aura_rows(report, "onTargets")),
    )
```

- [ ] **Step 5: Run them and watch them pass**

Run: `uv run pytest tests/adapters/wcl/test_ingest_auras.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/adapters/wcl/queries.py src/wowperf/adapters/wcl/ingest.py tests/adapters/wcl/test_ingest_auras.py
git commit -m "Read both aura tables for one player in a single query

Aliasing lets one document select the table twice, so 'on self and on target'
costs one cached call instead of two. A null table raises rather than reading
as a player who carried no buffs."
```

---

### Task 5: Fetching one player's auras

**Files:**
- Modify: `src/wowperf/adapters/wcl/repository.py`
- Test: `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Consumes: `AURA_TABLE_QUERY`, `build_player_auras`, the existing `_query`.
- Produces: `WclRunRepository.auras(self, report_code: str, fight_id: int, actor_id: int) -> PlayerAuras`

`fight_id` is an `int`, not `int | None`: by the time anyone wants auras the fight is already resolved, and re-running keystone selection here would let the two sides of a comparison silently pick different fights.

This is a scoped method rather than an addition to `load` on purpose — see decision 1. `load` fetching auras would pay for ten tables per run to answer a question about two actors.

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/wcl/test_repository.py`, following the file's existing `httpx.MockTransport` pattern:

```python
def an_aura_payload() -> dict[str, object]:
    return {
        "data": {
            "reportData": {
                "report": {
                    "onSelf": {
                        "data": {
                            "auras": [
                                {
                                    "name": "Coagulopathy",
                                    "guid": 391477,
                                    "totalUptime": 5000,
                                    "totalUses": 1,
                                    "bands": [{"startTime": 0, "endTime": 5000}],
                                }
                            ],
                            "totalTime": 5000,
                        }
                    },
                    "onTargets": {"data": {"auras": [], "totalTime": 5000}},
                }
            }
        }
    }


def test_auras_come_back_for_the_actor_that_was_asked_for(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        calls.append(operation_name(body))
        return httpx.Response(200, json=an_aura_payload())

    repository = a_repository(handler, tmp_path)
    auras = repository.auras("abc123", 36, 7)

    assert calls == ["AuraTable"]
    assert auras.actor_id == 7
    assert [a.name for a in auras.on_self] == ["Coagulopathy"]
    assert auras.on_targets == ()


def test_a_second_lookup_for_the_same_actor_is_served_from_the_cache(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        calls.append(operation_name(body))
        return httpx.Response(200, json=an_aura_payload())

    repository = a_repository(handler, tmp_path)
    repository.auras("abc123", 36, 7)
    repository.auras("abc123", 36, 7)

    assert calls == ["AuraTable"], "the second lookup should not reach the network"


def test_two_different_actors_do_not_collide_in_the_cache(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "oauth" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        calls.append(operation_name(body))
        return httpx.Response(200, json=an_aura_payload())

    repository = a_repository(handler, tmp_path)
    repository.auras("abc123", 36, 7)
    repository.auras("abc123", 36, 8)

    assert len(calls) == 2, "a different actor is a different query"
```

Reuse the file's existing helpers for building a repository over a transport and for reading an operation name out of a request body; if they are not already factored out, factor them out as `a_repository(handler, tmp_path)` and `operation_name(body)` and update the existing tests to use them rather than writing a parallel pair.

**The third test is the one that bites.** The cache key derives from the query text plus its variables, so an implementation that forgot to vary the variables per actor would serve actor 8 the auras of actor 7 — a wrong answer that looks entirely right.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: FAIL, `AttributeError: 'WclRunRepository' object has no attribute 'auras'`.

- [ ] **Step 3: Add the method**

In `src/wowperf/adapters/wcl/repository.py`, import `AURA_TABLE_QUERY` and `build_player_auras`, import `PlayerAuras` from `wowperf.domain.auras`, and add the method after `load`:

```python
    def auras(self, report_code: str, fight_id: int, actor_id: int) -> PlayerAuras:
        """Buff and debuff uptime for one player of one fight.

        Scoped rather than folded into `load`: an aura table is per-actor, so
        loading them for a whole roster would pay for ten tables to answer a
        question about two players.
        """
        payload = self._query(
            AURA_TABLE_QUERY,
            {"code": report_code, "fightId": fight_id, "actorId": actor_id},
        )
        return build_player_auras(payload, actor_id)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -v`
Expected: the three new tests pass and every pre-existing test in the file still passes.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/adapters/wcl/repository.py tests/adapters/wcl/test_repository.py
git commit -m "Fetch one player's aura tables, cached per actor

An aura table is per-actor, so this stays out of load: two players are compared
and five would be paid for. The cache key varies with the actor, because
serving one player's buffs for another is a wrong answer that looks right."
```

---

### Task 6: Uptime findings against the top parse

**Files:**
- Create: `src/wowperf/domain/comparison/uptime.py`
- Test: `tests/domain/comparison/test_uptime.py`

**Interfaces:**
- Consumes: `Aura`, `PlayerAuras`, `uptime_seconds_in` from `wowperf.domain.auras`; `boss_seconds` from `wowperf.domain.comparison.spells`; `Run`, `Player`; `Finding`, `Confidence`.
- Produces:
  - `def boss_windows(run: Run) -> tuple[tuple[int, int], ...]`
  - `def compare_uptime(ours: Run, our_auras: PlayerAuras | None, our_player: Player, theirs: Run, their_auras: PlayerAuras | None, their_name: str) -> list[Finding]`
  - `MAX_AURAS_REPORTED: int = 5`, `MIN_UPTIME_FRACTION: float = 0.10`, `UPTIME_GAP_FRACTION: float = 0.15`

Two finding families, `compare.uptime.self.<rank>` and `compare.uptime.target.<rank>`, plus `compare.uptime.unavailable` when either side is missing.

**Fractions, never seconds.** Two runs have different boss durations, so a seconds difference between them measures the fight length as much as the player. Every finding here carries `seconds_lost=None`.

`boss_seconds` is imported from `spells.py` rather than reimplemented: the two modules must agree on what boss time is, and one definition is how that stays true.

- [ ] **Step 1: Write the failing tests**

`tests/domain/comparison/test_uptime.py`:

```python
# ABOUTME: Behaviour tests for buff and debuff uptime against a top parse, on boss pulls only.
# ABOUTME: The interesting cases are a missing reference, a small sample, and a gap below cut-off.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.uptime import (
    UPTIME_GAP_FRACTION,
    boss_windows,
    compare_uptime,
)
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player, Pull, Run


def a_player(name: str = "Dudesons", actor_id: int = 7) -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=315
    )


def a_pull(index: int, start_ms: int, end_ms: int, encounter_id: int) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name="Pack",
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def a_run(*pulls: Pull, player: Player | None = None) -> Run:
    return Run(
        report_code="abc123",
        fight_id=1,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(),
        keystone_time_ms=1_800_000,
        keystone_bonus=1,
        count_reached=100,
        count_required=100,
        npc_counts=(),
        players=(player or a_player(),),
        pulls=pulls,
    )


def an_aura(ability_id: int, name: str, *bands: tuple[int, int]) -> Aura:
    return Aura(
        ability_id=ability_id,
        name=name,
        total_uptime_ms=sum(end - start for start, end in bands),
        uses=len(bands),
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in bands),
    )


def ids(findings: list[Finding], prefix: str) -> list[str]:
    return [f.id for f in findings if f.id.startswith(prefix)]


BOSS = a_pull(0, 0, 100_000, encounter_id=12825)
TRASH = a_pull(1, 100_000, 200_000, encounter_id=0)


def test_boss_windows_covers_boss_pulls_only() -> None:
    assert boss_windows(a_run(BOSS, TRASH)) == ((0, 100_000),)


def test_an_uptime_gap_on_self_is_reported() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Bríala")
    reported = [f for f in findings if f.id.startswith("compare.uptime.self.")]

    assert len(reported) == 1
    assert "Coagulopathy" in reported[0].title
    assert reported[0].confidence is Confidence.DERIVED
    assert reported[0].seconds_lost is None


def test_a_debuff_gap_on_the_target_is_reported_separately() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    our_auras = PlayerAuras(actor_id=7, on_targets=(an_aura(55095, "Frost Fever", (0, 10_000)),))
    their_auras = PlayerAuras(actor_id=3, on_targets=(an_aura(55095, "Frost Fever", (0, 95_000)),))

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Bríala")

    assert ids(findings, "compare.uptime.target.") == ["compare.uptime.target.0"]
    assert ids(findings, "compare.uptime.self.") == []


def test_uptime_outside_boss_pulls_is_not_counted() -> None:
    ours = a_run(BOSS, TRASH)
    theirs = a_run(BOSS, TRASH, player=a_player("Bríala", 3))
    # Ours is up for the whole boss pull; theirs only during trash.
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 100_000)),))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (100_000, 200_000)),)
    )

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Bríala")

    assert ids(findings, "compare.uptime.") == []


def test_a_gap_below_the_cut_off_is_left_alone() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    gap = int((UPTIME_GAP_FRACTION - 0.05) * 100_000)
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 80_000)),))
    their_auras = PlayerAuras(
        actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 80_000 + gap)),)
    )

    findings = compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Bríala")

    assert ids(findings, "compare.uptime.") == []


def test_an_aura_the_reference_barely_carried_is_not_argued_from() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 5_000)),))

    findings = compare_uptime(
        ours, PlayerAuras(actor_id=7), a_player(), theirs, their_auras, "Bríala"
    )

    assert ids(findings, "compare.uptime.") == []


def test_a_missing_reference_says_so_rather_than_reporting_nothing() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))

    findings = compare_uptime(ours, PlayerAuras(actor_id=7), a_player(), theirs, None, "Bríala")

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]
    assert findings[0].seconds_lost is None


def test_a_run_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_run(TRASH)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))

    findings = compare_uptime(
        ours, PlayerAuras(actor_id=7), a_player(), theirs, PlayerAuras(actor_id=3), "Bríala"
    )

    assert ids(findings, "compare.uptime.") == ["compare.uptime.unavailable"]


def test_no_more_than_the_cap_is_reported() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Bríala", 3))
    their_auras = PlayerAuras(
        actor_id=3,
        on_self=tuple(an_aura(100 + n, f"Buff {n}", (0, 90_000)) for n in range(8)),
    )

    findings = compare_uptime(
        ours, PlayerAuras(actor_id=7), a_player(), theirs, their_auras, "Bríala"
    )

    assert len(ids(findings, "compare.uptime.self.")) == 5
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_uptime.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.comparison.uptime'`.

- [ ] **Step 3: Write the module**

`src/wowperf/domain/comparison/uptime.py`:

```python
# ABOUTME: Compares one player's buff and debuff uptime on boss pulls against a top parse.
# ABOUTME: Fractions of boss time, never seconds: two runs fight the same boss for different long.

from wowperf.domain.auras import Aura, PlayerAuras, uptime_seconds_in
from wowperf.domain.comparison.spells import boss_seconds
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player, Run

MAX_AURAS_REPORTED = 5

MIN_UPTIME_FRACTION = 0.10
"""Below this the reference barely carried it either, so there is nothing to argue from."""

UPTIME_GAP_FRACTION = 0.15
"""How much more of the boss fight they must have it up before it is worth reporting."""


def boss_windows(run: Run) -> tuple[tuple[int, int], ...]:
    """The millisecond spans of the boss pulls, for intersecting aura bands against."""
    return tuple((pull.start_ms, pull.end_ms) for pull in run.boss_pulls)


def _fractions(
    auras: tuple[Aura, ...], windows: tuple[tuple[int, int], ...], seconds: float
) -> dict[int, tuple[str, float]]:
    """Ability id to (name, fraction of boss time this aura was up)."""
    return {
        aura.ability_id: (aura.name, uptime_seconds_in(aura, windows) / seconds)
        for aura in auras
    }


def _unavailable(our_seconds: float, their_seconds: float, has_auras: bool) -> Finding:
    return Finding(
        id="compare.uptime.unavailable",
        title="Buff and debuff uptime could not be compared",
        detail=(
            "An uptime comparison needs boss pulls on both sides and aura data for both "
            "players. One of those is missing, so no uptime numbers are reported rather "
            "than numbers from an unlike sample."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(
            f"our boss time {our_seconds:.0f}s",
            f"their boss time {their_seconds:.0f}s",
            f"reference aura data {'present' if has_auras else 'absent'}",
        ),
    )


def _gap_findings(
    kind: str,
    ours: dict[int, tuple[str, float]],
    theirs: dict[int, tuple[str, float]],
    our_player: Player,
    their_name: str,
    our_seconds: float,
    their_seconds: float,
) -> list[Finding]:
    gaps = []
    for ability_id, (name, their_fraction) in theirs.items():
        if their_fraction < MIN_UPTIME_FRACTION:
            continue
        our_fraction = ours.get(ability_id, (name, 0.0))[1]
        if their_fraction - our_fraction < UPTIME_GAP_FRACTION:
            continue
        gaps.append((their_fraction - our_fraction, ability_id, name, our_fraction,
                     their_fraction))
    gaps.sort(reverse=True)

    where = "on themselves" if kind == "self" else "on the enemy"
    findings = []
    for rank, (_, ability_id, name, our_fraction, their_fraction) in enumerate(
        gaps[:MAX_AURAS_REPORTED]
    ):
        findings.append(
            Finding(
                id=f"compare.uptime.{kind}.{rank}",
                title=(
                    f"{their_name} kept {name} up for {their_fraction:.0%} of boss time "
                    f"{where}, {our_player.name} {our_fraction:.0%}"
                ),
                detail=(
                    "Both figures are the share of boss-pull time the aura was present, which "
                    "is comparable even though the two fights ran for different lengths. A "
                    "shorter fight at a different keystone level still changes what fits, so "
                    "read a narrow gap as noise."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_seconds:.0f}s of boss pulls",
                    f"theirs over {their_seconds:.0f}s of boss pulls",
                ),
            )
        )
    return findings


def compare_uptime(
    ours: Run,
    our_auras: PlayerAuras | None,
    our_player: Player,
    theirs: Run,
    their_auras: PlayerAuras | None,
    their_name: str,
) -> list[Finding]:
    """Where the reference kept an aura up markedly more of the boss fight than we did."""
    our_seconds = boss_seconds(ours)
    their_seconds = boss_seconds(theirs)

    if our_auras is None or their_auras is None or our_seconds <= 0 or their_seconds <= 0:
        return [_unavailable(our_seconds, their_seconds, their_auras is not None)]

    our_windows = boss_windows(ours)
    their_windows = boss_windows(theirs)

    findings: list[Finding] = []
    for kind, ours_side, theirs_side in (
        ("self", our_auras.on_self, their_auras.on_self),
        ("target", our_auras.on_targets, their_auras.on_targets),
    ):
        findings += _gap_findings(
            kind,
            _fractions(ours_side, our_windows, our_seconds),
            _fractions(theirs_side, their_windows, their_seconds),
            our_player,
            their_name,
            our_seconds,
            their_seconds,
        )
    return findings
```

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_uptime.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/uptime.py tests/domain/comparison/test_uptime.py
git commit -m "Compare buff and debuff uptime on boss pulls

As a share of boss time, never as seconds: two runs fight the same boss for
different lengths, so a seconds difference would measure the fight rather than
the player."
```

---

### Task 7: The service runs the uptime comparison

**Files:**
- Modify: `src/wowperf/domain/comparison/reference.py`, `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_service.py`

**Interfaces:**
- Consumes: `compare_uptime` from Task 6; `PlayerAuras` from `wowperf.domain.auras`.
- Produces:
  - `ParseReference.auras: PlayerAuras | None = None`
  - `compare(ours, our_player, speed, parse, our_auras: PlayerAuras | None = None)` — a fifth, optional argument

Optional and defaulted, unlike Task 1's `cooldown_seconds`, because absent auras are a real and expected state that the comparison already knows how to report: `compare.uptime.unavailable` says so. A missing cooldown, by contrast, has no honest rendering at all.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_service.py`:

```python
def test_uptime_findings_appear_when_both_sides_carry_auras() -> None:
    ours, our_player, speed, parse = a_comparable_pair_with_auras()

    ids = {f.id.rsplit(".", 1)[0] for f in compare(ours, our_player, speed, parse,
                                                   our_auras=OUR_AURAS)}

    assert "compare.uptime.self" in ids


def test_a_comparison_without_auras_says_uptime_was_not_compared() -> None:
    ours, our_player, speed, parse = a_comparable_pair_with_auras()

    ids = [f.id for f in compare(ours, our_player, speed, parse)]

    assert "compare.uptime.unavailable" in ids


def test_no_parse_reference_means_no_uptime_findings_at_all() -> None:
    ours, our_player, speed, _parse = a_comparable_pair_with_auras()

    ids = [f.id for f in compare(ours, our_player, speed, None, our_auras=OUR_AURAS)]

    assert [i for i in ids if i.startswith("compare.uptime.")] == []
    assert "compare.parse.unavailable" in ids
```

Extend the file's existing shared fixture into `a_comparable_pair_with_auras()` rather than building a second parallel one, and define `OUR_AURAS` and the parse reference's `auras` so that one aura clears `UPTIME_GAP_FRACTION` on boss pulls. If widening the fixture breaks another test's expectation, say which and why in your report rather than weakening that test's assertions to accommodate the new one.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/domain/comparison/test_service.py -v`
Expected: FAIL, `TypeError: compare() got an unexpected keyword argument 'our_auras'`.

- [ ] **Step 3: Carry the reference's auras**

In `src/wowperf/domain/comparison/reference.py`, import `PlayerAuras` from `wowperf.domain.auras` and add the field to `ParseReference`:

```python
class ParseReference(Frozen):
    row: ParseRow
    loaded: LoadedRun
    # Absent is a real state, not a failure: `compare.uptime.unavailable` reports it.
    auras: PlayerAuras | None = None
```

- [ ] **Step 4: Run the comparison**

In `src/wowperf/domain/comparison/service.py`, import `PlayerAuras` and `compare_uptime`, widen the signature, and add the call inside the existing `else` branch that already runs `compare_spells` and `compare_talents`:

```python
def compare(
    ours: LoadedRun,
    our_player: Player,
    speed: SpeedReference | None,
    parse: ParseReference | None,
    our_auras: PlayerAuras | None = None,
) -> list[Finding]:
```

```python
        findings += compare_uptime(
            ours.run,
            our_auras,
            our_player,
            parse.loaded.run,
            parse.auras,
            parse.row.character_name,
        )
```

- [ ] **Step 5: Run them and watch them pass**

Run: `uv run pytest tests/domain/comparison/test_service.py -v`
Expected: the three new tests pass and every pre-existing test in the file still passes.

- [ ] **Step 6: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/reference.py src/wowperf/domain/comparison/service.py tests/domain/comparison/test_service.py
git commit -m "Run the uptime comparison alongside spells and talents

Auras are per-actor, so ours travel as an argument while the reference's ride
with the rest of the reference. Absent on either side is a finding, matching
how every other missing reference behaves."
```

---

### Task 8: The command fetches both players' auras

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `WclRunRepository.auras` from Task 5; `find_player`; `compare` as it stands after Task 7.
- Produces: `analyze` fetching auras for the subject and their counterpart, and passing both into `compare`.

Two rules, both of which a reviewer will check by running the command:

1. **`--no-compare` must issue zero aura queries.** There is no parse reference to compare against, so there is nothing to fetch.
2. **An aura fetch that fails must not kill the command.** This is the same rule Plan C's final review established for reference loads: a failure discards findings the user already paid quota for. Catch the project's own error types, fall back to `None`, and let `compare.uptime.unavailable` report it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`, extending `build_analyze_transport` to answer the `AuraTable` operation:

```python
def test_a_compared_run_reports_uptime(tmp_path: Path) -> None:
    result = run_analyze(tmp_path)

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0
    assert any(i.startswith("compare.uptime.") for i in ids)


def test_no_compare_issues_no_aura_queries(tmp_path: Path) -> None:
    calls: list[str] = []
    result = run_analyze(tmp_path, "--no-compare", calls=calls)

    assert result.exit_code == 0
    assert "AuraTable" not in calls


def test_an_aura_fetch_that_fails_still_writes_the_report(tmp_path: Path) -> None:
    result = run_analyze(tmp_path, aura_response=httpx.Response(200, json={"data": None}))

    payload = written_findings(tmp_path)
    ids = [f["id"] for f in payload["findings"]]

    assert result.exit_code == 0, result.output
    assert "compare.uptime.unavailable" in ids
```

Reuse the file's existing helpers for driving `analyze` over a mock transport and for reading the written findings file; if `run_analyze` and `written_findings` do not exist under those names, factor the existing tests' setup into them rather than writing a parallel pair.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — no `compare.uptime.` finding appears, because nothing fetches auras yet.

- [ ] **Step 3: Fetch them**

In `src/wowperf/cli.py`, add a helper beside `_references`:

```python
def _auras(runs: WclRunRepository, code: str, fight_id: int, actor_id: int) -> PlayerAuras | None:
    """One player's auras, or None if they cannot be had.

    A failed aura fetch must not discard the whole report: everything else has
    already been fetched and paid for, and `compare.uptime.unavailable` states
    the gap rather than hiding it.
    """
    try:
        return runs.auras(code, fight_id, actor_id)
    except (IngestError, WclError):
        return None
```

and in `analyze`, after the references are resolved and before `compare` is called:

```python
    our_auras = None
    if parse is not None:
        our_auras = _auras(runs, loaded.run.report_code, loaded.run.fight_id, subject.actor_id)
        their_player = find_player(parse.loaded.run, parse.row.character_name)
        if their_player is not None:
            parse = parse.model_copy(
                update={
                    "auras": _auras(
                        runs,
                        parse.loaded.run.report_code,
                        parse.loaded.run.fight_id,
                        their_player.actor_id,
                    )
                }
            )
```

then pass them through:

```python
    findings = analyse(loaded, season, defensives) + compare(
        ours=loaded, our_player=subject, speed=speed, parse=parse, our_auras=our_auras
    )
```

Match however `analyze` currently combines the analysis and comparison findings — do not restructure that line beyond adding the argument. Import `PlayerAuras`, `find_player`, `IngestError` and `WclError` if they are not already imported.

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: the three new tests pass and every pre-existing test in the file still passes.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/cli.py tests/test_cli.py
git commit -m "Fetch auras for the two players actually being compared

Only the subject and their counterpart, and only when there is a parse to
compare against. A failed aura fetch degrades to a finding rather than
discarding a report the user already spent quota on."
```

---

### Task 9: End to end, and the repository description

**Files:**
- Create: `tests/e2e/test_uptime_e2e.py`
- Modify: `CLAUDE.md`
- Test: the file above, marked `e2e` and deselected by default

**Interfaces:**
- Consumes: everything.
- Produces: an `e2e`-marked test proving uptime and the cooldown ceiling work against the live API, and a corrected repository description.

This test costs about 4 points of the 3600-per-hour budget on top of a normal compared analysis: two aura queries, each covering both tables.

- [ ] **Step 1: Write the test**

`tests/e2e/test_uptime_e2e.py`:

```python
# ABOUTME: End-to-end aura uptime against the real Warcraft Logs API; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.comparison.uptime import boss_windows
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_players_auras_come_back_with_usable_bands(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    subject = loaded.run.players[0]

    auras = runs.auras(loaded.run.report_code, loaded.run.fight_id, subject.actor_id)

    assert auras.actor_id == subject.actor_id
    assert auras.on_self, "a real player carries at least one buff"

    # Bands must be on the same clock as pulls, or every uptime figure is nonsense.
    windows = boss_windows(loaded.run)
    assert windows, "the reference report should contain boss pulls"
    earliest = min(band.start_ms for aura in auras.on_self for band in aura.bands)
    assert earliest >= 0
    assert earliest < max(end for _start, end in windows)

    # An aura cannot be up for longer than it exists.
    for aura in auras.on_self:
        spanned = sum(band.end_ms - band.start_ms for band in aura.bands)
        assert spanned <= aura.total_uptime_ms + 1, aura.name
```

The last two assertions are the ones that matter. The first proves the band clock matches the pull clock — if Warcraft Logs ever returned absolute epoch timestamps here, every uptime fraction would be zero and every test with hand-written fixtures would still pass. The second proves the bands and the pre-aggregated total agree with each other.

- [ ] **Step 2: Confirm it is deselected**

Run: `uv run pytest -q`
Expected: the new test is deselected; everything else passes.

- [ ] **Step 3: Run it against the real API**

```bash
WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... \
WOWPERF_E2E_REPORT='https://www.warcraftlogs.com/reports/<code>?fight=<n>' \
uv run pytest -m e2e -v
```

Expected: PASS. If the aura table comes back empty, re-read the "Verified schema" table before changing anything — `targetID` versus `sourceID` and the `hostilityType` on the debuff half are the two that bite.

**Report the observed findings to your human partner rather than only asserting on them.** Run `wowperf analyze` on the reference report and read the new `compare.uptime.*` and `defensives.ceiling.*` findings as a player would. A technically valid but obviously wrong number is what to catch: an uptime above 100%, a buff nobody would call a rotational choice topping the list, a cooldown ceiling that accuses a tank of nothing. Plan C's first contact found two defects the offline tests could not see; expect the same.

- [ ] **Step 4: Correct the repository description**

In `CLAUDE.md`, the state paragraph ends by saying Plan D — the HTML report — is not written. That is still true, but this plan is not the report. Amend the paragraph to record that the cooldown ceiling and aura uptime shipped, and leave the HTML report attributed to its own plan. Update the `analyze` row of the Commands table only if its flags changed, which they did not.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add tests/e2e/test_uptime_e2e.py CLAUDE.md
git commit -m "Prove aura uptime against a real report

The band clock is the one thing a hand-written fixture cannot check: if these
timestamps were ever absolute rather than report-relative, every uptime figure
would be zero and every offline test would still pass."
```

---

## Plan Self-Review

**Spec coverage.** §5.7's cooldown ceiling is Tasks 1 and 2 — the data in 1, the finding in 2, with the denominator built from the death spans §5.2 already produces. §6.5 item 5 is Tasks 3 to 8: the value types and the window intersection in 3, the verified query and its ingest in 4, the scoped fetch in 5, the findings in 6, the wiring in 7 and 8. §2.2's aura block is the authority for Task 4 and is reproduced in this plan's "Verified schema". Task 9 proves both against the live API.

Nothing else in the design is in scope here. §7 and §8 — the HTML report and the skills layer — remain unwritten and get their own plan.

**Known gaps, carried forward.**

- The cooldown values are base cooldowns without talent reductions, so a talented player's real ceiling is higher than the one printed. This makes the finding an underestimate, which is the safe direction, but it means a shortfall against a reduced cooldown goes unreported.
- `MIN_UPTIME_FRACTION`, `UPTIME_GAP_FRACTION`, `CEILING_USE_FRACTION` and `MIN_CEILING_USES` are judgement calls with no empirical backing. They are named constants so a later plan can tune them against real reports rather than hunting for literals.
- Uptime is compared for the subject player only. A group-wide view is a healer and support question, which is slice 4.
- An aura's `type` field is read and discarded. It appears to be a magic-school or category code; nothing in this plan needs it, and guessing at its meaning would violate the project's own rule about inventing API semantics.

**Type consistency.** `DefensiveAbility` gains `cooldown_seconds` and `charges` in Task 1 and they are read in Task 2 only. `Aura`, `AuraBand`, `PlayerAuras` and `uptime_seconds_in` are defined in Task 3 and used unchanged in Tasks 4, 5, 6, 7, 8 and 9. `build_player_auras(payload, actor_id) -> PlayerAuras` is defined in Task 4 and called in Task 5. `WclRunRepository.auras(report_code, fight_id, actor_id)` is defined in Task 5 and called in Tasks 8 and 9. `compare_uptime`'s six-argument signature is fixed in Task 6 and called only in Task 7. `boss_seconds` is imported from `spells.py` rather than redefined, so both comparison modules agree on what boss time is.

**Field-name provenance.** Every Warcraft Logs field this plan names appears in the "Verified schema" table, confirmed by live query on 2026-09-05. The four behaviours recorded there — the two table argument shapes, the band clock, `totalTime`'s meaning, and the events endpoint being the wrong tool — were each established by running the query and reading what came back.
