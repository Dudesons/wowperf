# Wipe Analysis Layer 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the raid page a per-player grid of damage taken, a players-alive chart, and the wipe verdict at the top of Summary.

**Architecture:** Two pure extractions lift computations existing functions already perform and discard — the per-ability damage matrix out of `damage_outliers`, and the alive-over-time series out of `_alive_at_the_end`. Two new view models and their builders read those extractions; three templates print coordinates and strings and decide nothing.

**Tech Stack:** Python 3.12, `uv`, pytest, pydantic-style frozen models (`domain.base.Frozen`), Jinja2.

**Spec:** `docs/plans/2026-09-19-wipe-analysis-layer-2-design.md`

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches the network, disk or a template.
- **Every finding carries a confidence badge.** `FindingFact.confidence` left unset means **measured**, not unknown.
- **The report is one HTML file.** No stylesheet link, no `@import`, no remote `src`, exactly one inline script. The only outbound addresses are ability icons on `wow.zamimg.com`.
- **Never put a real character name in `tests/`.** Sanctioned: `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. Larger rosters index players (`Raider 0..19`).
- **The twenty players on report `cW38jmwdnZfbHVL4` are real people.** Refer to them by class, spec, role or index in code, tests, commits and documents.
- **Master design §5.5:** the page describes damage and never assigns intent. Deaths are the single exception.
- **Never use `--no-verify`**, `--no-hooks`, or `--no-pre-commit-hook`.
- **Commit messages are plain ASCII**, imperative, no `feat:`/`fix:` prefix, body explains why, ending with a blank line then `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **`uv` is the only toolchain.** Gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy`, each its own command; mypy takes no paths.
- **Call git as `/mingw64/bin/git`.** A bare `git` is rewritten by the user-level RTK hook and refused by the worktree guard.
- **Every code file starts with two `# ABOUTME: ` comment lines.**

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/analysis/damage_outliers.py` | Modify: gains `DamageMatrix`, `AbilityTotals`, `damage_matrix()`; `damage_outliers()` becomes a filter over it |
| `src/wowperf/domain/analysis/attempt_shape.py` | Modify: gains `AlivePoint`, `alive_over_time()`; `_alive_at_the_end` becomes its last point |
| `src/wowperf/domain/report/raid_grid.py` | Create: `build_raid_grid()` — the per-player table as a view model |
| `src/wowperf/domain/report/alive_chart.py` | Create: `build_alive_chart()` — the step series in viewBox units |
| `src/wowperf/domain/report/raid_model.py` | Modify: `RaidGrid`, `GridRow`, `GridCell`, `AliveChart`, `AlivePlot`; `RaidReport` gains `grid`, `alive_chart`, `verdict` |
| `src/wowperf/domain/report/raid_build.py` | Modify: build the three new fields |
| `src/wowperf/adapters/render/_raid_mechanics.html.j2` | Modify: render the grid |
| `src/wowperf/adapters/render/_raid_summary.html.j2` | Modify: render the verdict, then the chart |
| `src/wowperf/adapters/render/report.css.j2` | Modify: grid and chart styling |

---

### Task 1: The damage matrix

Lift the per-ability, per-player totals `damage_outliers` already builds so the grid can read them. No finding changes.

**Files:**
- Modify: `src/wowperf/domain/analysis/damage_outliers.py`
- Test: `tests/domain/analysis/test_damage_outliers.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `AbilityTotals(ability_id: int, ability_name: str, amounts: dict[int, int], median_amount: float | None, took_count: int)` — `amounts` is keyed by `actor_id` and includes tanks; `median_amount` is `None` where fewer than `MIN_PLAYERS_FOR_MEDIAN` non-tanks took the ability.
  - `DamageMatrix(by_ability: dict[int, AbilityTotals])`
  - `damage_matrix(players, damage_taken, roles) -> DamageMatrix`
  - `damage_outliers(players, damage_taken, roles) -> list[DamageOutlier]` — unchanged signature and unchanged output.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_damage_outliers.py`. Read the file's existing helpers first and reuse them; the fixtures below name their own players so they do not depend on one.

```python
def test_the_matrix_keeps_tank_totals_that_the_median_excludes() -> None:
    """The grid shows a tank's row; the median must still not see it.

    A tank taking ten times what everyone else took is the job. Counting one
    into the baseline would raise it for every non-tank and silently retire
    findings that are correct.
    """
    players = (
        Player(actor_id=1, name="Raider 1", class_name="Mage", spec="Frost", item_level=690),
        Player(actor_id=2, name="Raider 2", class_name="Mage", spec="Frost", item_level=690),
        Player(actor_id=3, name="Raider 3", class_name="Mage", spec="Frost", item_level=690),
        Player(
            actor_id=4, name="Raider 4", class_name="DeathKnight", spec="Blood", item_level=690
        ),
    )
    hits = (
        _hit(actor_id=1, ability_id=11, amount=100),
        _hit(actor_id=2, ability_id=11, amount=100),
        _hit(actor_id=3, ability_id=11, amount=100),
        _hit(actor_id=4, ability_id=11, amount=9000),
    )

    matrix = damage_matrix(players, hits, Roles())
    totals = matrix.by_ability[11]

    assert totals.amounts[4] == 9000, "the tank's own total is not reported"
    assert totals.median_amount == 100, "the tank reached the median"
    assert totals.took_count == 3, "the tank was counted among those who took it"


def test_the_matrix_withholds_a_median_below_the_floor() -> None:
    """Two players is not a group baseline, and `None` says so rather than 0.0."""
    players = (
        Player(actor_id=1, name="Raider 1", class_name="Mage", spec="Frost", item_level=690),
        Player(actor_id=2, name="Raider 2", class_name="Mage", spec="Frost", item_level=690),
    )
    hits = (_hit(actor_id=1, ability_id=11, amount=100), _hit(actor_id=2, ability_id=11, amount=100))

    assert damage_matrix(players, hits, Roles()).by_ability[11].median_amount is None


def test_damage_outliers_reports_exactly_what_it_did_before() -> None:
    """The refactor is behaviour-preserving, and this is what says so.

    Three players at the baseline and one at four times it: the same shape the
    finding was written against. If retaining tank totals moved any median,
    this is where it shows.
    """
    players = tuple(
        Player(actor_id=index, name=f"Raider {index}", class_name="Mage", spec="Frost",
               item_level=690)
        for index in range(1, 5)
    )
    hits = (
        _hit(actor_id=1, ability_id=11, amount=100),
        _hit(actor_id=2, ability_id=11, amount=100),
        _hit(actor_id=3, ability_id=11, amount=100),
        _hit(actor_id=4, ability_id=11, amount=400),
    )

    [outlier] = damage_outliers(players, hits, Roles())

    assert outlier.actor_id == 4
    assert outlier.ability_id == 11
    assert outlier.amount == 400
    assert outlier.median_amount == 100
    assert outlier.took_count == 4
```

Add this helper beside them if the file has no equivalent:

```python
def _hit(*, actor_id: int, ability_id: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name="Caustic Waves",
        amount=amount,
        timestamp_ms=1000,
    )
```

`DamageTakenEvent` may require more fields than these. Read `src/wowperf/domain/events.py` and pass whatever has no default; do not add defaults to the model to make the helper shorter.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/domain/analysis/test_damage_outliers.py -k "matrix or reports_exactly" -v
```

Expected: the two `damage_matrix` tests fail with `NameError`/`ImportError`; `test_damage_outliers_reports_exactly_what_it_did_before` **passes** already — it is the regression guard, and a guard that fails now would mean the fixture is wrong rather than the code.

- [ ] **Step 3: Add the matrix types and function**

In `src/wowperf/domain/analysis/damage_outliers.py`:

```python
class AbilityTotals(Frozen):
    """One ability's damage across the raid, and the baseline it is read against.

    `amounts` includes tanks, because the grid shows a tank's row. The median
    does not, because a tank taking ten times what the raid took is the job and
    not a finding -- the same exclusion `damage_outliers` has always applied,
    now stated once here and read by both consumers.

    `median_amount` is None below `MIN_PLAYERS_FOR_MEDIAN`, where a median is
    not a group baseline. None rather than 0.0: a zero baseline would divide.
    """

    ability_id: int
    ability_name: str
    amounts: dict[int, int]
    median_amount: float | None
    took_count: int


class DamageMatrix(Frozen):
    """Every ability that hit the raid, keyed by id."""

    by_ability: dict[int, AbilityTotals]


def damage_matrix(
    players: tuple[Player, ...], damage_taken: tuple[DamageTakenEvent, ...], roles: Roles
) -> DamageMatrix:
    """Per-ability, per-player totals with each ability's non-tank median.

    One walk over the hits, serving both the outlier findings and the report's
    per-player grid. Keyed by actor id throughout, never by display name, so
    two players sharing a name are never conflated.
    """
    tank_ids = {
        player.actor_id
        for player in players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }

    amounts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    ability_names: dict[int, str] = {}
    for hit in damage_taken:
        amounts[hit.ability_id][hit.actor_id] += hit.amount
        ability_names[hit.ability_id] = hit.ability_name

    by_ability: dict[int, AbilityTotals] = {}
    for ability_id, per_player in amounts.items():
        took = [
            amount
            for actor_id, amount in per_player.items()
            if amount > 0 and actor_id not in tank_ids
        ]
        by_ability[ability_id] = AbilityTotals(
            ability_id=ability_id,
            ability_name=ability_names[ability_id],
            amounts=dict(per_player),
            median_amount=median(took) if len(took) >= MIN_PLAYERS_FOR_MEDIAN else None,
            took_count=len(took),
        )
    return DamageMatrix(by_ability=by_ability)
```

- [ ] **Step 4: Rewrite `damage_outliers` as a filter over the matrix**

Replace the body between `names = {...}` and the final `return sorted(...)`:

```python
    names = {player.actor_id: player.name for player in players}
    tank_ids = {
        player.actor_id
        for player in players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }
    matrix = damage_matrix(players, damage_taken, roles)

    outliers = []
    for totals in matrix.by_ability.values():
        if totals.median_amount is None:
            continue
        for actor_id, amount in totals.amounts.items():
            # Tanks are outside the baseline, so they are outside the finding.
            if actor_id in tank_ids:
                continue
            if amount / totals.median_amount >= MEDIAN_MULTIPLE:
                outliers.append(
                    DamageOutlier(
                        actor_id=actor_id,
                        ability_id=totals.ability_id,
                        player_name=names.get(actor_id, f"Actor {actor_id}"),
                        ability_name=totals.ability_name,
                        amount=amount,
                        median_amount=totals.median_amount,
                        took_count=totals.took_count,
                    )
                )
    return sorted(outliers, key=lambda row: -row.multiple)
```

- [ ] **Step 5: Run the whole outlier suite**

```bash
uv run pytest tests/domain/analysis/test_damage_outliers.py -v
```

Expected: all pass, including every test that predates this task.

- [ ] **Step 6: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

Expected: all green. If any test outside this file changed behaviour, stop — this task is meant to be behaviour-preserving, and a failure elsewhere means a median moved.

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/damage_outliers.py tests/domain/analysis/test_damage_outliers.py
```

```bash
/mingw64/bin/git commit -m "Expose the damage matrix the outlier finding already builds

The per-player grid needs every player's total for an ability, which
damage_outliers computed and then discarded, keeping only what cleared the
threshold. Lifting it out means the grid and the findings read one
computation and one median rule instead of two that can drift.

Tank totals are now retained, because the grid shows a tank's row. No median
moved: tanks were and remain outside the baseline, and a test asserts the
finding reports exactly what it did before.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Alive over time

Lift the step function out of `_alive_at_the_end`, so the chart and the verdict cannot disagree.

**Files:**
- Modify: `src/wowperf/domain/analysis/attempt_shape.py`
- Test: `tests/domain/analysis/test_attempt_shape.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `AlivePoint(timestamp_ms: int, alive: int)`
  - `alive_over_time(size: int, deaths: tuple[Death, ...], resurrections: tuple[Resurrection, ...]) -> tuple[AlivePoint, ...]` — always at least one point, the first at `timestamp_ms=0` with `alive=size`.
  - `_alive_at_the_end` keeps its signature and returns `alive_over_time(...)[-1].alive`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_attempt_shape.py`, reusing its existing `_deaths` and `_resurrections` helpers.

```python
def test_the_alive_series_starts_with_the_whole_raid_standing() -> None:
    [first, *_] = alive_over_time(20, (), ())

    assert first.timestamp_ms == 0
    assert first.alive == 20


def test_the_alive_series_steps_down_on_each_death() -> None:
    series = alive_over_time(20, _deaths(3), ())

    assert [point.alive for point in series] == [20, 19, 18, 17]


def test_the_alive_series_steps_back_up_on_a_resurrection() -> None:
    """A rez is a step up, and the series has to show it as one."""
    series = alive_over_time(20, _deaths(2), _resurrections(1, at_ms=5_000))

    assert [point.alive for point in series] == [20, 19, 18, 19]
    assert series[-1].timestamp_ms == 5_000


def test_a_resurrection_at_the_instant_of_a_death_leaves_the_player_down() -> None:
    """The rule `_alive_at_the_end` already applies, carried into the series.

    A rez cannot land on somebody who has not died yet, so the equal case is a
    second death landing on somebody just brought back.
    """
    deaths = (
        Death(
            player_name="Raider 0", actor_id=0, timestamp_ms=5_000,
            killing_blow="Caustic Waves", killing_blow_id=11,
        ),
    )

    series = alive_over_time(20, deaths, _resurrections(1, at_ms=5_000))

    assert series[-1].alive == 19


def test_the_series_ends_where_the_verdict_says_it_does() -> None:
    """The point of this extraction: two places on one page cannot disagree.

    The verdict's first evidence line prints "N of 20 alive at the end". A
    chart computing its own step function would eventually end on a different
    number, in two places a reader sees at once.
    """
    deaths = _deaths(5) + (
        Death(
            player_name="Raider 0", actor_id=0, timestamp_ms=60_000,
            killing_blow="Caustic Waves", killing_blow_id=11,
        ),
    )
    resurrections = _resurrections(4, at_ms=10_000)

    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=40.0, seconds=200.0),
        deaths,
        _sample(seconds=300.0, deaths=3),
        resurrections=resurrections,
    )
    series = alive_over_time(20, deaths, resurrections)

    assert finding is not None
    assert f"{series[-1].alive} of 20 alive at the end" in finding.evidence
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/domain/analysis/test_attempt_shape.py -k "alive_series or instant_of_a_death or ends_where_the_verdict" -v
```

Expected: FAIL with `NameError: name 'alive_over_time' is not defined`.

- [ ] **Step 3: Add `AlivePoint` and `alive_over_time`**

In `src/wowperf/domain/analysis/attempt_shape.py`, above `_alive_at_the_end`:

```python
class AlivePoint(Frozen):
    """How many were standing, from this moment until the next point."""

    timestamp_ms: int
    alive: int


def alive_over_time(
    size: int, deaths: tuple[Death, ...], resurrections: tuple[Resurrection, ...]
) -> tuple[AlivePoint, ...]:
    """The raid's headcount as a step function, deaths down and rezzes up.

    One computation behind both the chart and the verdict's own "N of 20 alive
    at the end": two implementations of a rule involving battle resurrections
    would eventually end on different numbers, in two places on one page a
    reader sees at once.

    A resurrection sharing a death's timestamp is ordered after it, so the
    player is down and then up -- a rez cannot land on somebody who has not
    died yet, which is the rule `_alive_at_the_end` already applies.

    This is a floor on the living, not a reading of them. A player who
    releases and runs back leaves no record at all, so every figure drawn from
    it carries a `derived` badge.
    """
    steps = [(death.timestamp_ms, 0, -1) for death in deaths]
    steps += [(one.timestamp_ms, 1, +1) for one in resurrections]
    steps.sort()

    points = [AlivePoint(timestamp_ms=0, alive=size)]
    alive = size
    for timestamp_ms, _, delta in steps:
        alive = max(0, min(size, alive + delta))
        points.append(AlivePoint(timestamp_ms=timestamp_ms, alive=alive))
    return tuple(points)
```

The middle element of each tuple is the sort tiebreak: `0` for a death and `1` for a resurrection, so a rez at the same millisecond sorts after the death it follows.

- [ ] **Step 4: Make `_alive_at_the_end` read the series**

Replace the body of `_alive_at_the_end` — keep its whole docstring, which records why the figure is a floor and why `died` stays a count of players:

```python
    return alive_over_time(size, deaths, resurrections)[-1].alive
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/domain/analysis/test_attempt_shape.py -v
```

Expected: all pass, including every resurrection test that predates this task. If `test_players_brought_back_count_among_the_living` fails, the step ordering is wrong — do not weaken that test.

- [ ] **Step 6: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/attempt_shape.py tests/domain/analysis/test_attempt_shape.py
```

```bash
/mingw64/bin/git commit -m "Read the raid's headcount as a series, not just its last point

The chart draws players alive over time and the verdict prints how many were
standing at the end. Computing those separately means two implementations of
a rule about battle resurrections, and they would eventually end on different
numbers in two places a reader sees at once.

_alive_at_the_end is now the series' last point, so there is one rule. A test
asserts the series ends on exactly the figure the verdict's evidence prints.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The grid view model and builder

**Files:**
- Modify: `src/wowperf/domain/report/raid_model.py`
- Create: `src/wowperf/domain/report/raid_grid.py`
- Create: `tests/domain/report/test_raid_grid.py`

**Interfaces:**
- Consumes: `damage_matrix`, `DamageMatrix`, `AbilityTotals`, `damage_outliers`, `DamageOutlier` (Task 1).
- Produces:
  - `GridCell(ability_id: int, amount: str, multiple: str, tinted: bool)` — `multiple` is `""` where none exists.
  - `GridRow(player_name: str, cells: tuple[GridCell, ...])`
  - `RaidGrid(columns: tuple[GridColumn, ...], rows: tuple[GridRow, ...], caption: str)`
  - `GridColumn(ability_id: int, ability_name: str)`
  - `MAX_GRID_COLUMNS = 5`
  - `build_raid_grid(players, damage_taken, roles, findings) -> RaidGrid | None` — `None` when no column qualifies.

- [ ] **Step 1: Add the models**

In `src/wowperf/domain/report/raid_model.py`:

```python
class GridColumn(Frozen):
    """One ability's column heading. `ability_id` draws the icon."""

    ability_id: int
    ability_name: str


class GridCell(Frozen):
    """One player's total from one ability, formatted.

    `multiple` is "" where no ratio exists: a tank, who is outside the median
    by design, and a player who took none of the ability, where there is
    nothing to divide. Both still print an `amount`, and a player who took
    none prints "0" -- a reading, not a gap.

    `tinted` is set from the finding's own existence, never from a threshold
    recomputed here. See `build_raid_grid`.
    """

    ability_id: int
    amount: str
    multiple: str
    tinted: bool


class GridRow(Frozen):
    """One player's row, one cell per column, in column order."""

    player_name: str
    cells: tuple[GridCell, ...]


class RaidGrid(Frozen):
    """Who took what, as a table. A view model, never findings.

    Twenty players by five abilities is a hundred cells; as findings that is
    the report's cap problem five times over. The caption carries design 7.3's
    sentence, because a tint means "took far more of this than their raid did"
    and never that somebody made a mistake.
    """

    columns: tuple[GridColumn, ...]
    rows: tuple[GridRow, ...]
    caption: str
```

Add `grid: RaidGrid | None = None` to `RaidReport`.

- [ ] **Step 2: Write the failing tests**

Create `tests/domain/report/test_raid_grid.py`:

```python
# ABOUTME: Behaviour tests for the per-player damage grid: what it shows and what it may claim.
# ABOUTME: A tint is a finding's existence, never a threshold this table recomputed.

from wowperf.domain.analysis.damage_outliers import damage_outliers
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.raid_grid import MAX_GRID_COLUMNS, build_raid_grid
from wowperf.domain.season import Roles


def _player(actor_id: int, class_name: str = "Mage", spec: str = "Frost") -> Player:
    return Player(
        actor_id=actor_id,
        name=f"Raider {actor_id}",
        class_name=class_name,
        spec=spec,
        item_level=690,
    )


def _hit(*, actor_id: int, ability_id: int, amount: int, name: str) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        amount=amount,
        timestamp_ms=1000,
    )


def _ranked(ability_id: int, ability_name: str) -> Finding:
    """A `mechanics.ability.*` finding, which is what earns a column."""
    from wowperf.domain.findings import Confidence

    return Finding(
        id=f"mechanics.ability.{ability_id}",
        title=f"{ability_name} hit the raid",
        detail="",
        confidence=Confidence.DERIVED,
        ability_id=ability_id,
        ability_name=ability_name,
    )


ROSTER = (
    _player(1), _player(2), _player(3),
    _player(4, class_name="DeathKnight", spec="Blood"),
)
HITS = (
    _hit(actor_id=1, ability_id=11, amount=100, name="Caustic Waves"),
    _hit(actor_id=2, ability_id=11, amount=100, name="Caustic Waves"),
    _hit(actor_id=3, ability_id=11, amount=400, name="Caustic Waves"),
    _hit(actor_id=4, ability_id=11, amount=9000, name="Caustic Waves"),
)
RANKED = [_ranked(11, "Caustic Waves")]


def test_a_tinted_cell_always_has_a_finding_behind_it() -> None:
    """The grid may state nothing the page does not already say outright."""
    grid = build_raid_grid(ROSTER, HITS, Roles(), RANKED)
    assert grid is not None

    outliers = {
        (one.actor_id, one.ability_id) for one in damage_outliers(ROSTER, HITS, Roles())
    }
    for row, player in zip(grid.rows, ROSTER, strict=True):
        for cell in row.cells:
            assert cell.tinted == ((player.actor_id, cell.ability_id) in outliers), (
                f"{row.player_name} / {cell.ability_id}"
            )


def test_a_tank_row_is_present_and_never_tinted() -> None:
    """A roster table missing two people reads as a bug; a tinted tank reads as blame."""
    grid = build_raid_grid(ROSTER, HITS, Roles(), RANKED)
    assert grid is not None

    [tank] = [row for row in grid.rows if row.player_name == "Raider 4"]
    assert tank.cells[0].amount == "9,000"
    assert tank.cells[0].multiple == "", "a tank has no median to be a multiple of"
    assert tank.cells[0].tinted is False


def test_a_player_who_took_none_of_an_ability_reads_zero() -> None:
    hits = HITS + (_hit(actor_id=1, ability_id=22, amount=50, name="Purge"),)
    findings = RANKED + [_ranked(22, "Purge")]

    grid = build_raid_grid(ROSTER, hits, Roles(), findings)
    assert grid is not None

    [second] = [row for row in grid.rows if row.player_name == "Raider 2"]
    purge = [cell for cell in second.cells if cell.ability_id == 22][0]
    assert purge.amount == "0"
    assert purge.multiple == ""


def test_the_columns_are_capped() -> None:
    hits = tuple(
        _hit(actor_id=1, ability_id=identifier, amount=100, name=f"Ability {identifier}")
        for identifier in range(1, 10)
    )
    findings = [_ranked(identifier, f"Ability {identifier}") for identifier in range(1, 10)]

    grid = build_raid_grid(ROSTER, hits, Roles(), findings)
    assert grid is not None
    assert len(grid.columns) == MAX_GRID_COLUMNS


def test_no_qualifying_column_yields_no_grid() -> None:
    """Nothing to say, said as nothing -- not an empty table with headings."""
    assert build_raid_grid(ROSTER, HITS, Roles(), []) is None


def test_the_caption_refuses_to_call_a_tint_a_mistake() -> None:
    grid = build_raid_grid(ROSTER, HITS, Roles(), RANKED)
    assert grid is not None
    for word in ("mistake", "avoidable", "should have", "failed"):
        assert word not in grid.caption.lower(), grid.caption
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run pytest tests/domain/report/test_raid_grid.py -v
```

Expected: FAIL at import — `No module named 'wowperf.domain.report.raid_grid'`.

- [ ] **Step 4: Write the builder**

Create `src/wowperf/domain/report/raid_grid.py`:

```python
# ABOUTME: The per-player damage grid as a view model: one row per player, one column per ability.
# ABOUTME: A cell is tinted from a finding's own existence, never from a threshold recomputed here.

from collections.abc import Sequence

from wowperf.domain.analysis.damage_outliers import damage_matrix, damage_outliers
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.raid_model import GridCell, GridColumn, GridRow, RaidGrid
from wowperf.domain.season import Roles

MAX_GRID_COLUMNS = 5
"""How many abilities the grid may show at once.

Its own constant rather than `MAX_MECHANICS_REPORTED`, which already governs
three families: this one's constraint is table width and theirs is list
length, and one number serving two unrelated questions is how a change for one
silently reshapes the other. It starts at the same value only because five
columns is what fits.
"""

CAPTION = (
    "Each cell is what one player took from one ability, against the median of the "
    "players who took it. A highlighted cell means that player took far more of it "
    "than their raid did. It does not mean a mistake: taking a tankbuster is correct, "
    "and soaking is doing the job. Tanks are shown but never highlighted, because a "
    "tank taking more than the raid is the role."
)
"""Design 7.3, on the page rather than only in the design document."""


def _columns(findings: Sequence[Finding]) -> tuple[GridColumn, ...]:
    """The abilities the ranked list reports, then the ones that killed somebody.

    Ranked first and capped, so where the two sources together name more than
    the grid can hold, the ranking decides. A lethal ability that does not fit
    is still named on the same tab by `mechanics.lethal.*`.
    """
    seen: dict[int, str] = {}
    for prefix in ("mechanics.ability.", "mechanics.lethal."):
        for finding in findings:
            if not finding.id.startswith(prefix):
                continue
            if finding.ability_id and finding.ability_id not in seen:
                seen[finding.ability_id] = finding.ability_name
    return tuple(
        GridColumn(ability_id=ability_id, ability_name=name)
        for ability_id, name in list(seen.items())[:MAX_GRID_COLUMNS]
    )


def build_raid_grid(
    players: tuple[Player, ...],
    damage_taken: tuple[DamageTakenEvent, ...],
    roles: Roles,
    findings: Sequence[Finding],
) -> RaidGrid | None:
    """Who took what, as a table, or None where no ability earned a column.

    The tint is the finding's own existence and not a threshold recomputed
    here, so the table can state nothing the page does not already say
    outright and the two cannot drift. It also settles tanks without a rule of
    its own: a tank is outside the median, so never an outlier, so never
    tinted.
    """
    columns = _columns(findings)
    if not columns:
        return None

    matrix = damage_matrix(players, damage_taken, roles)
    outliers = {
        (one.actor_id, one.ability_id) for one in damage_outliers(players, damage_taken, roles)
    }

    rows = []
    for player in players:
        cells = []
        for column in columns:
            totals = matrix.by_ability.get(column.ability_id)
            amount = totals.amounts.get(player.actor_id, 0) if totals else 0
            median_amount = totals.median_amount if totals else None
            multiple = (
                f"{amount / median_amount:.1f}x"
                if median_amount and amount > 0 and (player.actor_id, column.ability_id) not in
                _tank_cells(players, roles, column.ability_id)
                else ""
            )
            cells.append(
                GridCell(
                    ability_id=column.ability_id,
                    amount=f"{amount:,}",
                    multiple=multiple,
                    tinted=(player.actor_id, column.ability_id) in outliers,
                )
            )
        rows.append(GridRow(player_name=player.name, cells=tuple(cells)))

    return RaidGrid(columns=columns, rows=tuple(rows), caption=CAPTION)
```

The `multiple` expression above is deliberately left awkward so you rewrite it rather than paste it: a tank must get `""`. Compute the tank id set **once**, before the loops, exactly as `damage_matrix` does:

```python
    tank_ids = {
        player.actor_id
        for player in players
        if roles.role_of(player.class_name, player.spec) == "tank"
    }
```

then the cell's multiple is:

```python
            multiple = (
                f"{amount / median_amount:.1f}x"
                if median_amount and amount > 0 and player.actor_id not in tank_ids
                else ""
            )
```

Delete `_tank_cells`; it does not exist and must not be written.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/domain/report/test_raid_grid.py -v
```

Expected: all pass.

- [ ] **Step 6: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/raid_grid.py src/wowperf/domain/report/raid_model.py tests/domain/report/test_raid_grid.py
```

```bash
/mingw64/bin/git commit -m "Build the per-player damage grid as a view model

Twenty players by five abilities is a hundred cells. As findings that is the
report's cap problem five times over, so this is a view model and the finding
cap stays where it is.

A cell is tinted where damage_outliers minted a finding for that exact player
and ability -- the finding's own existence, not a threshold recomputed here.
The grid can therefore state nothing the page does not already say outright,
and the two cannot drift apart. It also settles tanks without a rule of its
own: a tank sits outside the median, so is never an outlier, so is never
tinted. Tanks still get rows, because a roster table missing two people reads
as a bug.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Render the grid

**Files:**
- Modify: `src/wowperf/domain/report/raid_build.py`
- Modify: `src/wowperf/adapters/render/_raid_mechanics.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_raid_html_invariants.py`
- Modify: `tests/adapters/render/golden/raid.html`

**Interfaces:**
- Consumes: `build_raid_grid` (Task 3), `RaidReport.grid` (Task 3).
- Produces: a rendered `<table class="damage-grid">` inside the Mechanics panel.

- [ ] **Step 1: Wire the builder**

In `build_raid_report`, after `players = build_raid_players(...)`:

```python
    grid = build_raid_grid(loaded.players, loaded.damage_taken, roles, findings)
```

`build_raid_report` does not currently take `roles`. Read its signature and the one call site in `src/wowperf/cli.py`; add `roles: Roles = Roles()` as a keyword parameter with a default, and pass the real one from the CLI. Then pass `grid=grid` into the `RaidReport(...)` construction.

- [ ] **Step 2: Write the failing render test**

Append to `tests/adapters/render/test_raid_html_invariants.py`, reusing the module's existing helper that renders a page:

```python
def test_the_mechanics_panel_draws_the_damage_grid() -> None:
    html = golden_raid_html()

    assert 'class="damage-grid"' in html
    assert "It does not mean a mistake" in html, "7.3's sentence never reached the page"


def test_a_grid_tint_is_a_class_not_a_colour_word() -> None:
    """A reader who cannot separate two tints, or who printed the page, needs the number.

    The same rule `ComparisonRow` already follows: a tint carries no meaning
    alone.
    """
    html = golden_raid_html()

    assert 'class="cell tinted"' in html
```

- [ ] **Step 3: Run it to verify it fails**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py -k "damage_grid or grid_tint" -v
```

Expected: FAIL — the markup does not exist.

- [ ] **Step 4: Render it**

Append to `src/wowperf/adapters/render/_raid_mechanics.html.j2`, before `</section>`:

```jinja
{% if report.grid %}
<h2 id="grid">Who took what</h2>
<p class="sub">{{ report.grid.caption }}</p>
<table class="damage-grid">
<thead>
<tr><th>Player</th>
{% for column in report.grid.columns %}
<th>{{ ability(column.ability_id, column.ability_name) }}</th>
{% endfor %}
</tr>
</thead>
<tbody>
{% for row in report.grid.rows %}
<tr><th scope="row">{{ row.player_name }}</th>
{% for cell in row.cells %}
<td class="cell{% if cell.tinted %} tinted{% endif %}">{{ cell.amount }}{% if cell.multiple %}
<span class="multiple">{{ cell.multiple }}</span>{% endif %}</td>
{% endfor %}
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
```

`ability(...)` is an existing macro. Read `_macros.html.j2` for its real name and signature before using it, and import it at the top of this template the way the file already imports `ledger_row`.

- [ ] **Step 5: Style it**

Add to `src/wowperf/adapters/render/report.css.j2`, following the file's existing conventions for colour variables:

```css
.damage-grid { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
.damage-grid th, .damage-grid td { padding: 4px 8px; text-align: right; }
.damage-grid th[scope="row"] { text-align: left; font-weight: normal; }
.damage-grid .cell.tinted { background: var(--warn-bg); font-weight: 600; }
.damage-grid .multiple { opacity: 0.7; margin-left: 6px; }
```

Use whatever the file already calls its warning background; do not invent `--warn-bg` if a name already exists.

- [ ] **Step 6: Run the render tests**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py -k "damage_grid or grid_tint" -v
```

Expected: PASS.

- [ ] **Step 7: Regenerate the golden file and read the diff**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update
```

```bash
/mingw64/bin/git diff --stat tests/adapters/render/golden/raid.html
```

Read the diff. Expected: the grid added inside the Mechanics panel and nothing else changed. If any existing finding moved, stop and find out why.

- [ ] **Step 8: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 9: Commit**

```bash
/mingw64/bin/git add -A
```

```bash
/mingw64/bin/git commit -m "Draw the per-player grid on the Mechanics tab

The table states design 7.3's sentence above itself rather than only in the
design document: a highlighted cell means that player took far more of an
ability than their raid did, and never that they made a mistake.

A tint is a class and the number stays in the cell beside it, because a tint
carries no meaning alone -- a reader who cannot separate two colours, or who
printed the page, reads the figure instead.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The chart view model and builder

**Files:**
- Modify: `src/wowperf/domain/report/raid_model.py`
- Create: `src/wowperf/domain/report/alive_chart.py`
- Create: `tests/domain/report/test_alive_chart.py`

**Interfaces:**
- Consumes: `alive_over_time`, `AlivePoint` (Task 2).
- Produces:
  - `AliveStep(x: float, y: float)`
  - `AliveChart(points, ticks, legend, boss_note, width, height, tick_x1, tick_x2, tick_label_x, baseline_y)` — `points` is `tuple[AliveStep, ...]`, `ticks` is `tuple[tuple[float, str], ...]`.
  - `build_alive_chart(size, deaths, resurrections, duration_ms, boss_percentage) -> AliveChart | None` — `None` when `duration_ms <= 0` or `size <= 0`.

- [ ] **Step 1: Add the models**

In `raid_model.py`, mirroring `AttemptsChart` in `progression_model.py`, which this follows deliberately:

```python
class AliveStep(Frozen):
    """One corner of the step function, in viewBox units."""

    x: float
    y: float


class AliveChart(Frozen):
    """How many of the raid were standing, across the attempt.

    Every coordinate the SVG needs lives here so the template computes none,
    exactly as `AttemptsChart` does for the progression page.

    One series, not two. There is no boss health curve to draw beside it:
    measured 2026-09-18, `graph(dataType: Resources, hostilityType: Enemies)`
    returns zero series. What the boss did is one note at the end point.

    The series is a floor on the living rather than a reading of them -- a
    player who releases and runs back leaves no record -- so it is badged
    `derived` wherever it is stated.
    """

    points: tuple[AliveStep, ...]
    ticks: tuple[tuple[float, str], ...]
    legend: str
    boss_note: str
    width: float
    height: float
    tick_x1: float
    tick_x2: float
    tick_label_x: float
    baseline_y: float
```

Add `alive_chart: AliveChart | None = None` to `RaidReport`.

- [ ] **Step 2: Write the failing tests**

Create `tests/domain/report/test_alive_chart.py`:

```python
# ABOUTME: Behaviour tests for the players-alive chart: a step function in viewBox units.
# ABOUTME: Its last point is the verdict's own figure, and the two may never disagree.

from wowperf.domain.events import Death, Resurrection
from wowperf.domain.report.alive_chart import CHART_HEIGHT, CHART_WIDTH, build_alive_chart


def _deaths(count: int) -> tuple[Death, ...]:
    return tuple(
        Death(
            player_name=f"Raider {index}",
            actor_id=index,
            timestamp_ms=10_000 * (index + 1),
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        )
        for index in range(count)
    )


def test_a_full_raid_starts_at_the_top_of_the_plot() -> None:
    chart = build_alive_chart(20, (), (), duration_ms=100_000, boss_percentage=40.0)

    assert chart is not None
    assert chart.points[0].x == 0.0 or chart.points[0].x > 0.0
    assert chart.points[0].y == min(point.y for point in chart.points)


def test_the_series_steps_down_and_never_leaves_the_plot() -> None:
    chart = build_alive_chart(20, _deaths(5), (), duration_ms=100_000, boss_percentage=40.0)

    assert chart is not None
    assert len(chart.points) >= 6
    for point in chart.points:
        assert 0.0 <= point.x <= CHART_WIDTH
        assert 0.0 <= point.y <= CHART_HEIGHT


def test_a_resurrection_steps_the_line_back_up() -> None:
    """Up on the page means up in the count, so y decreases."""
    resurrections = (
        Resurrection(
            actor_id=0, caster_id=19, ability_id=20484,
            ability_name="Rebirth", timestamp_ms=50_000,
        ),
    )

    chart = build_alive_chart(
        20, _deaths(2), resurrections, duration_ms=100_000, boss_percentage=40.0
    )

    assert chart is not None
    assert chart.points[-1].y < chart.points[-2].y


def test_the_boss_note_states_where_the_boss_finished() -> None:
    chart = build_alive_chart(20, _deaths(5), (), duration_ms=100_000, boss_percentage=16.49)

    assert chart is not None
    assert "16.5%" in chart.boss_note


def test_an_attempt_with_no_duration_draws_nothing() -> None:
    """An axis with no length draws a line at a single x, which reads as a bug."""
    assert build_alive_chart(20, (), (), duration_ms=0, boss_percentage=40.0) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run pytest tests/domain/report/test_alive_chart.py -v
```

Expected: FAIL at import.

- [ ] **Step 4: Write the builder**

Create `src/wowperf/domain/report/alive_chart.py`. Follow `progression_chart.py`'s shape: module constants with docstrings, one pure function, all arithmetic here.

```python
# ABOUTME: Players alive across one attempt, as a step function in viewBox units.
# ABOUTME: Its last point is the verdict's own alive count, by construction.

from wowperf.domain.analysis.attempt_shape import alive_over_time
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.report.raid_model import AliveChart, AliveStep

CHART_WIDTH = 680.0
CHART_HEIGHT = 200.0

PLOT_X0 = 46.0
"""Where the line starts: right of the headcount axis's labels."""

PLOT_X1 = 664.0
PLOT_TOP = 16.0
"""The y of the whole raid standing."""

BASELINE_Y = 170.0
"""The y of nobody standing."""

TICK_LABEL_X = 40.0

LEGEND = "Players still standing, across the attempt. A battle resurrection steps the line back up."

def _ticks(size: int) -> tuple[tuple[float, str], ...]:
    """A gridline at nobody, half the raid, and everybody.

    Three lines rather than one per player: twenty gridlines on a 200-unit
    plot is a grey field, and the line's own shape is what a reader follows.
    """
    marks = (0, size // 2, size)
    return tuple(
        (BASELINE_Y - (count / size) * (BASELINE_Y - PLOT_TOP), f"{count}")
        for count in marks
    )


def build_alive_chart(
    size: int,
    deaths: tuple[Death, ...],
    resurrections: tuple[Resurrection, ...],
    duration_ms: int,
    boss_percentage: float | None,
) -> AliveChart | None:
    """The attempt's headcount as one drawing, or None where there is no axis.

    Reads `alive_over_time` rather than counting deaths itself, so this chart
    and the verdict's "N of 20 alive at the end" are one computation.
    """
    if duration_ms <= 0 or size <= 0:
        return None

    span = PLOT_X1 - PLOT_X0
    height = BASELINE_Y - PLOT_TOP
    points = tuple(
        AliveStep(
            x=PLOT_X0 + min(1.0, point.timestamp_ms / duration_ms) * span,
            y=BASELINE_Y - (point.alive / size) * height,
        )
        for point in alive_over_time(size, deaths, resurrections)
    )

    boss_note = (
        f"The boss finished on {boss_percentage:.1f}% health."
        if boss_percentage is not None
        else "This report gives no boss health for this attempt."
    )

    return AliveChart(
        points=points,
        ticks=_ticks(size),
        legend=LEGEND,
        boss_note=boss_note,
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        tick_x1=PLOT_X0,
        tick_x2=PLOT_X1,
        tick_label_x=TICK_LABEL_X,
        baseline_y=BASELINE_Y,
    )
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/domain/report/test_alive_chart.py -v
```

- [ ] **Step 6: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/alive_chart.py src/wowperf/domain/report/raid_model.py tests/domain/report/test_alive_chart.py
```

```bash
/mingw64/bin/git commit -m "Draw the attempt's headcount as a step function

One series, not two: there is no boss health curve to put beside it, measured
against a Mythic kill on 2026-09-18, so what the boss did is one note at the
end point instead.

The line reads alive_over_time rather than counting deaths itself, so the
chart's last point and the verdict's alive count are the same computation
rather than two that agree today.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Render the chart

**Files:**
- Modify: `src/wowperf/domain/report/raid_build.py`
- Modify: `src/wowperf/adapters/render/_raid_summary.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_raid_html_invariants.py`
- Modify: `tests/adapters/render/golden/raid.html`

**Interfaces:**
- Consumes: `build_alive_chart` (Task 5), `RaidReport.alive_chart` (Task 5).
- Produces: an inline `<svg class="alive-chart">` at the top of the Summary panel.

- [ ] **Step 1: Wire the builder**

In `build_raid_report`, beside the grid:

```python
    alive_chart = build_alive_chart(
        loaded.encounter.size or len(loaded.players),
        loaded.deaths,
        loaded.resurrections,
        duration_ms=loaded.encounter.end_ms - loaded.encounter.start_ms,
        boss_percentage=loaded.encounter.boss_percentage,
    )
```

Read `LoadedEncounter` and `Encounter` first and use their real attribute names; the above is the shape, not necessarily the spelling. Pass `alive_chart=alive_chart` into `RaidReport(...)`.

- [ ] **Step 2: Write the failing test**

```python
def test_the_summary_draws_the_alive_chart() -> None:
    html = golden_raid_html()

    assert 'class="alive-chart"' in html
    assert "Players still standing" in html


def test_the_alive_chart_is_inline_svg_and_fetches_nothing() -> None:
    """The report is one file. The only outbound addresses are ability icons."""
    html = golden_raid_html()

    start = html.index('class="alive-chart"')
    chart = html[start : html.index("</svg>", start)]
    for forbidden in ("<image", "href=", "url("):
        assert forbidden not in chart, f"the chart reaches outside the page: {forbidden}"
```

- [ ] **Step 3: Run it to verify it fails**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py -k "alive_chart" -v
```

- [ ] **Step 4: Render it**

In `_raid_summary.html.j2`, immediately after the opening `<section ...>` tag:

```jinja
{% if report.alive_chart %}
<h2 id="alive">How the attempt went</h2>
<p class="legend">{{ report.alive_chart.legend }} {{ report.alive_chart.boss_note }}</p>
<svg class="alive-chart" width="100%"
     viewBox="0 0 {{ report.alive_chart.width }} {{ report.alive_chart.height }}">
  {% for y, label in report.alive_chart.ticks %}
  <line class="tick" x1="{{ report.alive_chart.tick_x1 }}" y1="{{ y }}"
        x2="{{ report.alive_chart.tick_x2 }}" y2="{{ y }}"></line>
  <text class="tick-label" x="{{ report.alive_chart.tick_label_x }}" y="{{ y }}"
        text-anchor="end" dominant-baseline="middle">{{ label }}</text>
  {% endfor %}
  <polyline class="alive-line" fill="none" points="
    {%- for point in report.alive_chart.points %}{{ point.x }},{{ point.y }} {% endfor -%}
  "></polyline>
</svg>
{% endif %}
```

A `<polyline>` draws straight segments between corners. `alive_over_time` emits one point per event, so the line slopes between them rather than stepping. If the reviewer wants true steps, emit two points per event in the builder — same x, old y then new y — and change nothing here. Do that only if asked; a sloped line is not wrong, it is a different reading.

- [ ] **Step 5: Style it**

```css
.alive-chart .alive-line { stroke: var(--accent); stroke-width: 2; }
```

Use the file's existing accent variable name.

- [ ] **Step 6: Run the render tests, then regenerate the golden**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py -k "alive_chart" -v
```

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update
```

```bash
/mingw64/bin/git diff --stat tests/adapters/render/golden/raid.html
```

- [ ] **Step 7: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add -A
```

```bash
/mingw64/bin/git commit -m "Put the attempt's shape at the top of Summary

Summary is the landing tab and it opened on a list. The chart says what
happened before any row has to be read.

Inline SVG, like every other drawing this report makes: no stylesheet, no
remote asset, and a test asserts the chart reaches outside the page for
nothing at all.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The verdict headline

**Files:**
- Modify: `src/wowperf/domain/report/raid_model.py`
- Modify: `src/wowperf/domain/report/raid_build.py`
- Modify: `src/wowperf/adapters/render/_raid_summary.html.j2`
- Test: `tests/domain/report/test_raid_build.py`
- Modify: `tests/adapters/render/golden/raid.html`

**Interfaces:**
- Consumes: `LedgerRow`, `ledger_row` (both existing).
- Produces: `RaidReport.verdict: LedgerRow | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/report/test_raid_build.py`, reusing `a_raid_fixture`, `a_wipes_findings`, `a_raids_findings` and the slug constants already in that file.

```python
def test_a_wipe_with_a_verdict_heads_the_summary_with_it() -> None:
    loaded, subject = a_raid_fixture(kill=False)
    verdict = Finding(
        id="wipe.cause",
        title="This attempt failed on execution: the raid was taken apart",
        detail="12 of 20 died.",
        confidence=Confidence.INFERRED,
    )

    report = build_raid_report(
        loaded, (*a_wipes_findings(), verdict), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.verdict is not None
    assert report.verdict.finding_id == "wipe.cause"


def test_a_kill_has_no_verdict_to_head_the_summary_with() -> None:
    """A kill produces no verdict at all, and the slot is absent rather than empty."""
    loaded, subject = a_raid_fixture(kill=True)

    report = build_raid_report(
        loaded, a_raids_findings(), subject, frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.verdict is None


def test_a_withheld_verdict_does_not_head_the_summary() -> None:
    """Its reason is already in Provenance. A landing tab whose first line says
    nothing was concluded is the complaint section 11 exists to fix."""
    loaded, subject = a_raid_fixture(kill=False)

    report = build_raid_report(
        loaded, (*a_wipes_findings(), _a_withheld_verdict()), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    assert report.verdict is None
```

`_a_withheld_verdict()` already exists in this file. `a_raids_findings` is the kill-shaped fixture; if it lives in another module, import it the way the file already imports its neighbours.

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run pytest tests/domain/report/test_raid_build.py -k "verdict" -v
```

Expected: FAIL with `AttributeError: 'RaidReport' object has no attribute 'verdict'`.

- [ ] **Step 3: Add the field and build it**

In `raid_model.py`, on `RaidReport`:

```python
    verdict: LedgerRow | None = None
    """The wipe verdict, heading Summary. None on a kill, which produces none,
    and on a withheld wipe, whose reason is disclosed in Provenance instead:
    a landing tab whose first line announces that nothing was concluded is the
    complaint design section 11 exists to fix."""
```

In `build_raid_report`, after `verdict_notices` is split out (that code already exists from the withheld-reason work):

```python
    verdict_finding = next((one for one in findings if one.id == "wipe.cause"), None)
    verdict = (
        ledger_row(verdict_finding, titles_by_id, tooltips) if verdict_finding else None
    )
```

Pass `verdict=verdict` into `RaidReport(...)`.

Matched on the exact id, not a prefix: `wipe.cause.withheld` was removed from `findings` before this line, and matching by prefix would pick up any future `wipe.cause.*` sibling that is not the verdict.

- [ ] **Step 4: Keep the verdict out of the other sections**

The verdict finding must not also appear as a summary pointer or an observation — one finding, one place. Check whether `placed_finding_ids` already claims it; if it reaches `report.observations` as well, add `wipe.cause` to the placement that claims it in `raid_ledger.py` and assert it:

```python
def test_the_verdict_appears_once_on_the_page() -> None:
    loaded, subject = a_raid_fixture(kill=False)
    verdict = Finding(
        id="wipe.cause",
        title="This attempt failed on execution: the raid was taken apart",
        detail="12 of 20 died.",
        confidence=Confidence.INFERRED,
    )

    report = build_raid_report(
        loaded, (*a_wipes_findings(), verdict), subject,
        frozenset({EMBERKIN_SLUG, STONEWAKE_SLUG}),
        FETCHED, NO_DEFENSIVES, NO_CONSUMABLES,
    )

    elsewhere = [row.finding_id for row in all_raid_ledger_rows(report)]
    assert elsewhere.count("wipe.cause") <= 1, elsewhere
```

- [ ] **Step 5: Render it**

In `_raid_summary.html.j2`, above the chart block added in Task 6:

```jinja
{% if report.verdict %}
<h2 id="verdict">Why this attempt ended</h2>
<div class="findings verdict">
{{ ledger_row(report.verdict) }}
</div>
{% endif %}
```

- [ ] **Step 6: Run the tests and regenerate the golden**

```bash
uv run pytest tests/domain/report/test_raid_build.py -k "verdict" -v
```

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update
```

```bash
/mingw64/bin/git diff --stat tests/adapters/render/golden/raid.html
```

- [ ] **Step 7: Run the full gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add -A
```

```bash
/mingw64/bin/git commit -m "Head the Summary with the verdict when there is one

Summary is the landing tab, and a landing tab that opens on a list reads as a
null result. A verdict at the top replaces the list with an answer.

The slot is absent rather than empty where there is no verdict: a kill
produces none, and a withheld wipe states its reason in Provenance. A first
line announcing that nothing was concluded is the complaint this change
exists to fix, not a fix for it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Live verification

Offline fixtures agree with the code that produced them. This is the task that finds what they cannot.

**Files:**
- Modify (only if a defect is found): any of the above.

**Interfaces:**
- Consumes: everything above.
- Produces: a verified report, and a recorded quota cost.

- [ ] **Step 1: Run the canonical wipe**

```bash
uv run wowperf raid 'https://www.warcraftlogs.com/reports/cW38jmwdnZfbHVL4#fight=30' --cache-dir cache --out out
```

This is a 20-player wipe with real battle resurrections — the shape the chart and the grid are built for. `out/` and `cache/` are both gitignored.

- [ ] **Step 2: Check the chart against the verdict**

```bash
grep -o 'id="verdict"' out/cW38jmwdnZfbHVL4-30.html
```

```bash
grep -o '[0-9]* of 20 alive at the end' out/cW38jmwdnZfbHVL4-30.html
```

Open the page and read the chart's last point against that sentence. They are one computation, so they must agree; if they do not, the wiring passed the chart a different `size` than the verdict used.

- [ ] **Step 3: Check the grid against the findings**

```bash
grep -c 'class="cell tinted"' out/cW38jmwdnZfbHVL4-30.html
```

```bash
grep -c 'finding-players.damage' out/cW38jmwdnZfbHVL4-30.html
```

Every tinted cell must correspond to a `players.damage.*` card. The counts need not be equal — the grid only has five columns and the findings cap at five — but a tint with no card is the defect this design exists to prevent.

- [ ] **Step 4: Read the page as a reader would**

Open it in a browser. Check, specifically:

- the grid has twenty rows, including both tanks, and neither tank is tinted;
- a column where nobody was an outlier shows twenty untinted numbers and does not look broken;
- the caption's sentence is above the table, where a reader meets it before the colours;
- the chart's line steps back up where the battle resurrections landed.

- [ ] **Step 5: Run the raid end-to-end suite**

```bash
WOWPERF_E2E_RAID_KILL='https://www.warcraftlogs.com/reports/cW38jmwdnZfbHVL4#fight=2' WOWPERF_E2E_RAID_WIPE='https://www.warcraftlogs.com/reports/cW38jmwdnZfbHVL4#fight=30' uv run pytest -m e2e tests/e2e/test_raid_e2e.py -v
```

Expected: 5 passed. These are the canonical subjects, recorded in `.env.example`.

- [ ] **Step 6: Record what it cost**

The command prints its own quota breakdown. If this shape has not been priced before, add a dated line to `.claude/skills/wcl-api/SKILL.md` under the rate-limit section, in the style of the readings already there.

- [ ] **Step 7: Commit anything the live run changed**

```bash
/mingw64/bin/git add -A
```

```bash
/mingw64/bin/git commit -m "Record what Layer 2 costs against a real wipe

<Replace this line with what the live run actually found. If it found no
defect, say so and give the quota reading. Do not claim a clean run without
having read the page.>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** §3.1 `damage_matrix` → Task 1. §3.2 `alive_over_time` → Task 2. §4.1 `RaidGrid` → Tasks 3 and 4. §4.2 `AliveChart` → Tasks 5 and 6. §4.3 verdict headline → Task 7. §5 placement → Tasks 4, 6, 7. §6 testing → every task, plus Task 8 for the live run. §2.2's deferrals appear in no task, which is what deferred means.

**Type consistency.** `AbilityTotals.median_amount` is `float | None` in Task 1 and every later reader checks for `None` before dividing. `GridCell.multiple` is `str` and `""` where absent, never `None`. `build_raid_grid` and `build_alive_chart` both return `X | None`, and both call sites in `raid_build.py` pass the optional straight into `RaidReport`, whose fields are `X | None = None`.

**Two deliberate traps.** Task 3's step 4 contains a `_tank_cells` call that does not exist, and says so, with the correct code beneath it. Task 6's step 4 explains that `<polyline>` slopes rather than steps and says not to change it unasked. Both are places an implementer pasting without reading would produce something wrong, and both are called out rather than smoothed over.
