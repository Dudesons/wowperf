# Cast ids from the log -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give twelve hand-maintained ability entries the id the game actually logs when the ability is pressed, and add an offline `wowperf audit-data` command that checks every entry the same way, so the next data pass cannot repeat the gap.

**Architecture:**
- **The rule** is a pure domain module, `src/wowperf/domain/data_audit.py`. It receives the entries, cast counts by id, and names to ids, and answers which entries were never cast and what their name was cast as.
- **An adapter**, `src/wowperf/adapters/cache/scan.py`, reads the local cache pages for cast rows and ability tables only.
- **A typer command** joins the two and prints lines.
- **The data correction** is two small scripts run once, pinned by a parametrised test.
- **A live script**, offline from the warm cache, measures before against after, using `git show main:` for the old data.

**Tech Stack:** Python 3.12, pydantic frozen models (`wowperf.domain.base.Frozen`), typer, pytest. `uv` only; in Bash it is `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-30-cast-ids-from-the-log-design.md`. Read it whole before Task 1. Its §3 "The rule" is binding, including the 2026-09-30 decision that a corrected entry keeps its cooldown.

## Global Constraints

- **An entry's id is the id the log casts when the ability is pressed.** Where one press logs several ids, take the one cast most often, the lowest id on a tie, and name the others in a comment. Never sum casts across ids that share a name (spec §3).
- **A corrected entry keeps its base cooldown.** The shortest gap between one player's presses within one fight is recorded, and never used to change the cooldown (spec §3).
- **The five likely entries are not changed:** Doom Winds, Killing Spree, Guardian of Ancient Kings, Vengeance Metamorphosis, Guardian Berserk. Holy Halo is not changed either (spec §2, §6).
- **The audit prints ability and specialisation names only, never a player.** It reads only the local cache and makes no request.
- **`src/wowperf/domain/` performs no I/O.**
- **No real character name in `tests/`:** only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). Players on `cW38jmwdnZfbHVL4`, `6Kx1P9GbNXrcLdHa` and `4vFcVAW1PB2CrD9z` are referred to by class, spec, role or index only, never by name, slug or raw finding id. Never print a reference report's code.
- **Every new test is shown able to fail:** break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test.
- **Every new code file starts with two `ABOUTME: ` lines.** Comments are evergreen.
- **Commits:**
  - imperative subject, no prefix, a body saying why;
  - plain ASCII;
  - last line `Co-Authored-By:` naming the model that wrote the commit;
  - commit with `/mingw64/bin/git -F <file>`, and never `--no-verify`.
- **Gate after every task:** `uv run ruff check .`, `uv run mypy` (strict over `tests/` too) and `uv run pytest` must be green with pristine output.
- **No golden moves.** None of `minimal.html`, `raid.html`, `night.html` or `progression.html` draws any of the eight abilities (checked 2026-09-30). If a golden moves, stop and report.
- **Any script containing a backslash is written with the file-writing tool,** never a shell heredoc, which eats backslashes.

The code in Tasks 1 and 2 was run before this plan was committed, on 2026-09-30:
- **Suite and checks:** 2783 passed after Task 1 and 2795 after Task 2, with ruff and mypy clean and no golden moved. Both were run from this plan's own text, and every prove step in Task 1 that touches the scan was shown red.
- **The audit on the real cache** printed, before Task 2:
  - "defensives: 34 of 139 entries never cast"
  - "externals: 2 of 19 entries never cast"
  - "throughput_cooldowns: 39 of 118 entries never cast"
  - "Read 1171 cached pages: 1159 distinct ability ids cast."

  After Task 2 it printed 29, 2 and 32. The cache on this machine can grow, so the page count may differ. The drop of twelve between the two runs is what must hold.

If a test disagrees now, the code was transcribed differently: diff against the plan before changing a test.

---

### Task 1: The audit command

**Files:**
- Create: `src/wowperf/domain/data_audit.py`
- Create: `src/wowperf/adapters/cache/scan.py`
- Modify: `src/wowperf/cli.py`:
  - two import lines;
  - one command, inserted directly above `def _echo_cost_breakdown(costs: CostLedger) -> None:`.
- Modify: `CLAUDE.md`, the Commands table and the sentence after it.
- Test:
  - Create `tests/domain/test_data_audit.py`
  - Create `tests/adapters/cache/test_scan.py`
  - Create `tests/test_cli_audit_data.py`

**Interfaces:**
- Produces:
  - `AuditEntry(file: str, spec: str, ability_id: int, name: str)`
  - `NeverCast(entry: AuditEntry, cast_as: tuple[tuple[int, int], ...] = ())`
  - `never_cast(entries, casts: Mapping[int, int], named: Mapping[str, frozenset[int]]) -> tuple[NeverCast, ...]`
  - `audit_lines(entries, found) -> tuple[str, ...]`
  - in `wowperf.domain.data_audit`: `CachedIds(pages: int, casts: dict[int, int], named: dict[str, frozenset[int]])` and `scan_cache(directory: Path) -> CachedIds`
  - in `wowperf.adapters.cache.scan`: the command `wowperf audit-data [--cache-dir DIR]`
- The file labels the command uses are `"defensives"`, `"externals"` and `"throughput_cooldowns"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/test_data_audit.py`:

```python
# ABOUTME: The data audit's rule: an entry never cast, and what the logs cast under its name.
# ABOUTME: Ids and names here are made up; the rule is about their relation, not any real spell.

from wowperf.domain.data_audit import AuditEntry, NeverCast, audit_lines, never_cast

SHIELD = AuditEntry(file="defensives", spec="Mage/Arcane", ability_id=100, name="Ice Shield")
BURST = AuditEntry(file="throughput_cooldowns", spec="Warrior/Arms", ability_id=300, name="Burst")


def test_an_entry_never_cast_whose_name_is_cast_under_another_id_is_reported() -> None:
    found = never_cast((SHIELD,), {200: 7}, {"ice shield": frozenset({100, 200})})
    assert found == (NeverCast(entry=SHIELD, cast_as=((200, 7),)),)


def test_an_entry_cast_under_its_own_id_is_not_reported() -> None:
    assert never_cast((SHIELD,), {100: 1, 200: 7}, {"ice shield": frozenset({100, 200})}) == ()


def test_an_id_a_table_names_but_no_row_casts_is_not_offered_as_the_replacement() -> None:
    found = never_cast((SHIELD,), {}, {"ice shield": frozenset({100, 200})})
    assert found == (NeverCast(entry=SHIELD, cast_as=()),)


def test_the_name_is_matched_whatever_its_case() -> None:
    found = never_cast((SHIELD,), {200: 1}, {"ice shield": frozenset({200})})
    assert found[0].cast_as == ((200, 1),)


def test_same_named_ids_come_most_cast_first_then_lowest_id() -> None:
    found = never_cast(
        (SHIELD,), {201: 3, 202: 9, 203: 3}, {"ice shield": frozenset({100, 201, 202, 203})}
    )
    assert found[0].cast_as == ((202, 9), (201, 3), (203, 3))


def test_the_lines_head_each_file_and_say_what_was_cast_instead() -> None:
    entries = (SHIELD, BURST)
    found = (NeverCast(entry=SHIELD, cast_as=((200, 7), (201, 2))), NeverCast(entry=BURST))
    assert audit_lines(entries, found) == (
        "defensives: 1 of 1 entries never cast",
        "  Mage/Arcane  Ice Shield  100: never cast; the logs cast it as 200 x7, 201 x2",
        "throughput_cooldowns: 1 of 1 entries never cast",
        "  Warrior/Arms  Burst  300: never cast, under this or any other id of that name",
    )


def test_a_file_with_nothing_never_cast_still_gets_its_heading() -> None:
    assert audit_lines((SHIELD,), ()) == ("defensives: 0 of 1 entries never cast",)
```

Create `tests/adapters/cache/test_scan.py`:

```python
# ABOUTME: Reading cached pages for cast ids and ability names, on pages written for the test.
# ABOUTME: The pages mimic the API's shapes; every id and name in them is made up.

import json
from pathlib import Path
from typing import Any

from wowperf.adapters.cache.scan import scan_cache


def a_cast(ability_id: int, at: int, source: int = 5, fight: int = 1) -> dict[str, Any]:
    return {"timestamp": at, "type": "cast", "sourceID": source, "targetID": -1,
            "abilityGameID": ability_id, "fight": fight}


def events_page(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"reportData": {"report": {"events": {"data": list(rows), "nextPageTimestamp": None}}}}


def abilities_page(*pairs: tuple[int, str], actors: tuple[str, ...] = ()) -> dict[str, Any]:
    # A real cached actor carries `id`, `name`, `server` and `subType` (checked 2026-09-30).
    return {"reportData": {"report": {"masterData": {
        "actors": [{"id": index, "name": name, "server": "Somewhere", "subType": "Mage"}
                   for index, name in enumerate(actors)],
        "abilities": [{"gameID": game_id, "name": name, "icon": "x.jpg"}
                      for game_id, name in pairs],
    }}}}


def write(directory: Path, *pages: dict[str, Any]) -> Path:
    for index, page in enumerate(pages):
        (directory / f"{index:04d}.json").write_text(json.dumps(page), encoding="utf-8")
    return directory


def test_cast_rows_are_counted_by_ability_id(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, events_page(a_cast(200, 1_000), a_cast(200, 5_000),
                                                  a_cast(300, 9_000))))
    assert (scan.pages, scan.casts) == (1, {200: 2, 300: 1})


def test_a_row_that_is_not_a_cast_is_not_counted(tmp_path: Path) -> None:
    damage = {**a_cast(200, 1_000), "type": "damage"}
    assert scan_cache(write(tmp_path, events_page(damage))).casts == {}


def test_a_row_two_overlapping_pages_both_hold_is_counted_once(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, events_page(a_cast(200, 1_000)),
                            events_page(a_cast(200, 1_000), a_cast(200, 2_000))))
    assert scan.casts == {200: 2}


def test_ability_tables_give_every_id_a_name_has_folded_to_one_case(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, abilities_page((100, "Ice Shield")),
                            abilities_page((200, "ICE SHIELD"), (300, "Burst"))))
    assert scan.named == {"ice shield": frozenset({100, 200}), "burst": frozenset({300})}


def test_no_actor_name_is_read(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, abilities_page((100, "Ice Shield"), actors=("Emberkin",))))
    assert "emberkin" not in scan.named


def test_a_named_id_outside_an_ability_table_is_not_read(tmp_path: Path) -> None:
    page = {"reportData": {"report": {"fights": [{"gameID": 777, "name": "Grand Enemy"}]}}}
    assert scan_cache(write(tmp_path, page)).named == {}


def test_a_page_holding_neither_reads_as_nothing(tmp_path: Path) -> None:
    scan = scan_cache(write(tmp_path, {"rateLimitData": {"pointsSpentThisHour": 3}}))
    assert (scan.pages, scan.casts, scan.named) == (1, {}, {})
```

Create `tests/test_cli_audit_data.py`:

```python
# ABOUTME: The audit-data command end to end: committed data files against a test-written cache.
# ABOUTME: Offline by construction -- the command builds no client, so no request can be made.

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from wowperf.adapters.config.toml import load_defensives
from wowperf.cli import app

runner = CliRunner()


def a_page(directory: Path, name: str, report: dict[str, Any]) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"reportData": {"report": report}}), encoding="utf-8"
    )


def ice_block_id() -> int:
    [ice_block] = [one for one in load_defensives().for_spec("Mage", "Arcane")
                   if one.name == "Ice Block"]
    return ice_block.ability_id


def test_an_entry_the_logs_cast_under_another_id_is_named_with_that_id(tmp_path: Path) -> None:
    # A made-up id, so the case holds whatever Ice Block's committed id is.
    other = 999_001
    a_page(tmp_path, "abilities", {"masterData": {
        "actors": [{"id": 5, "name": "Emberkin", "server": "Somewhere", "subType": "Mage"}],
        "abilities": [{"gameID": ice_block_id(), "name": "Ice Block", "icon": "a.jpg"},
                      {"gameID": other, "name": "Ice Block", "icon": "a.jpg"}],
    }})
    a_page(tmp_path, "casts", {"events": {"data": [
        {"timestamp": 1_000, "type": "cast", "sourceID": 5, "abilityGameID": other, "fight": 1},
        {"timestamp": 9_000, "type": "cast", "sourceID": 5, "abilityGameID": other, "fight": 1},
    ], "nextPageTimestamp": None}})

    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (
        f"  Mage/Arcane  Ice Block  {ice_block_id()}: never cast; the logs cast it as {other} x2"
        in result.output.splitlines()
    )
    assert "Read 2 cached pages: 1 distinct ability ids cast." in result.output
    assert "Emberkin" not in result.output


def test_every_data_file_gets_its_heading(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path)])
    headings = [line.split(":")[0] for line in result.output.splitlines()
                if not line.startswith(" ") and "entries never cast" in line]
    assert headings == ["defensives", "externals", "throughput_cooldowns"]


def test_a_missing_cache_directory_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit-data", "--cache-dir", str(tmp_path / "absent")])
    assert result.exit_code == 1
    assert "No cache directory at" in result.output
```

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/test_data_audit.py tests/adapters/cache/test_scan.py tests/test_cli_audit_data.py -q`

Expected failures:
- the first two files fail at import: `No module named 'wowperf.domain.data_audit'` and `No module named 'wowperf.adapters.cache.scan'`;
- the CLI tests fail with a non-zero exit, `No such command 'audit-data'`.

- [ ] **Step 3: The rule**

Create `src/wowperf/domain/data_audit.py`:

```python
# ABOUTME: Checks the hand-maintained ability data against the ability ids real logs cast.
# ABOUTME: An entry never cast, whose name the logs cast under another id, reads as a wrong id.

from collections.abc import Mapping, Sequence

from wowperf.domain.base import Frozen


class AuditEntry(Frozen):
    """One ability as a data file lists it: which file, which specialisation, which id."""

    file: str
    spec: str
    ability_id: int
    name: str


class NeverCast(Frozen):
    """One entry no cast row carries, and the same-named ids the logs did cast.

    `cast_as` pairs each such id with how many cast rows carry it, most cast
    first and the lowest id on a tie. Empty means the logs never cast that name
    under any id -- which a talent nobody took explains as well as a wrong id,
    so the audit reports it and does not guess between the two.
    """

    entry: AuditEntry
    cast_as: tuple[tuple[int, int], ...] = ()


def never_cast(
    entries: Sequence[AuditEntry],
    casts: Mapping[int, int],
    named: Mapping[str, frozenset[int]],
) -> tuple[NeverCast, ...]:
    """Every entry whose id no cast row carries, in the order the entries came.

    `casts` counts cast rows by ability id. `named` maps a case-folded ability
    name to every id a report's ability table gives that name. An id a table
    names but no row casts is not offered as a replacement: a table lists what
    a report mentions, and only a cast row says what a press logs.
    """
    found: list[NeverCast] = []
    for entry in entries:
        if casts.get(entry.ability_id, 0):
            continue
        others = named.get(entry.name.casefold(), frozenset()) - {entry.ability_id}
        cast_as = sorted(
            ((other, casts[other]) for other in others if casts.get(other, 0)),
            key=lambda pair: (-pair[1], pair[0]),
        )
        found.append(NeverCast(entry=entry, cast_as=tuple(cast_as)))
    return tuple(found)


def audit_lines(entries: Sequence[AuditEntry], found: Sequence[NeverCast]) -> tuple[str, ...]:
    """The audit as the command prints it: one heading per file, one line per entry never cast."""
    lines: list[str] = []
    for file in dict.fromkeys(entry.file for entry in entries):
        total = sum(entry.file == file for entry in entries)
        missing = [one for one in found if one.entry.file == file]
        lines.append(f"{file}: {len(missing)} of {total} entries never cast")
        for one in missing:
            entry = one.entry
            where = f"  {entry.spec}  {entry.name}  {entry.ability_id}"
            if one.cast_as:
                cast = ", ".join(f"{other} x{count}" for other, count in one.cast_as)
                lines.append(f"{where}: never cast; the logs cast it as {cast}")
            else:
                lines.append(f"{where}: never cast, under this or any other id of that name")
    return tuple(lines)
```

- [ ] **Step 4: The cache scan**

Create `src/wowperf/adapters/cache/scan.py`:

```python
# ABOUTME: Reads cached Warcraft Logs pages for the ability ids they cast and the names they give.
# ABOUTME: Only cast rows and ability tables are read; actors, and so player names, never are.

import json
from collections import Counter
from pathlib import Path
from typing import NamedTuple


class CachedIds(NamedTuple):
    """What the cache says about ability ids: how often each was cast, and every id a name has."""

    pages: int
    casts: dict[int, int]
    named: dict[str, frozenset[int]]


def scan_cache(directory: Path) -> CachedIds:
    """Every cast row and every ability-table entry across the pages under `directory`.

    A page is read wherever its rows sit, since a query can nest them under any
    alias: a cast row is any object with `type` "cast" and an integer
    `abilityGameID`, and an ability-table entry is any object inside an
    `abilities` list with an integer `gameID` and a string `name`. Paginated
    streams repeat rows at their boundaries, so a cast row is counted once per
    fight, caster, ability and timestamp.
    """
    rows: set[tuple[object, object, int, object]] = set()
    named: dict[str, set[int]] = {}
    pages = 0

    def walk(node: object, in_abilities: bool) -> None:
        if isinstance(node, dict):
            ability_id = node.get("abilityGameID")
            if node.get("type") == "cast" and isinstance(ability_id, int):
                rows.add((node.get("fight"), node.get("sourceID"), ability_id,
                          node.get("timestamp")))
            game_id, name = node.get("gameID"), node.get("name")
            if in_abilities and isinstance(game_id, int) and isinstance(name, str):
                named.setdefault(name.casefold(), set()).add(game_id)
            for key, value in node.items():
                walk(value, key == "abilities")
        elif isinstance(node, list):
            for item in node:
                walk(item, in_abilities)

    for path in sorted(directory.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")), False)
        pages += 1
    counts = Counter(ability_id for _fight, _source, ability_id, _at in rows)
    return CachedIds(
        pages=pages,
        casts=dict(counts),
        named={name: frozenset(ids) for name, ids in named.items()},
    )
```

- [ ] **Step 5: The command**

In `src/wowperf/cli.py`:
- after `from wowperf.adapters.cache.disk import DiskCache, cache_key`, add `from wowperf.adapters.cache.scan import scan_cache`;
- after `from wowperf.domain.comparison.targets import TargetRow`, add `from wowperf.domain.data_audit import AuditEntry, audit_lines, never_cast`;
- directly above `def _echo_cost_breakdown(costs: CostLedger) -> None:`, add the following, with two blank lines either side:

```python
@app.command("audit-data")
def audit_data(
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="The cache of API responses to read"),
) -> None:
    """Check the ability ids in data/ against the ids the cached logs cast. Offline."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not cache_dir.is_dir():
        typer.echo(f"No cache directory at {cache_dir}", err=True)
        raise typer.Exit(1)

    cached = scan_cache(cache_dir)
    entries = tuple(
        AuditEntry(file=file, spec=spec, ability_id=ability.ability_id, name=ability.name)
        for file, collection in (
            ("defensives", load_defensives().entries),
            ("externals", load_externals().entries),
            ("throughput_cooldowns", load_throughput_cooldowns().entries),
        )
        for spec, abilities in collection
        for ability in abilities
    )
    for line in audit_lines(entries, never_cast(entries, cached.casts, cached.named)):
        typer.echo(line)
    typer.echo(
        f"Read {cached.pages} cached pages: {len(cached.casts)} distinct ability ids cast."
    )
```

`load_defensives`, `load_externals` and `load_throughput_cooldowns` are already imported in `cli.py`.

- [ ] **Step 6: Run, pass, prove**

Run the three test files: all pass (17 tests). Then prove each guard, restoring after each:
- in `never_cast`, delete the two lines `if casts.get(entry.ability_id, 0):` / `continue`. Expect `test_an_entry_cast_under_its_own_id_is_not_reported` red.
- in `never_cast`, change `for other in others if casts.get(other, 0)` to `for other in others`. Expect `test_an_id_a_table_names_but_no_row_casts_is_not_offered_as_the_replacement` red. It fails with a `KeyError` inside the sort, which is a red result.
- in `never_cast`, change `key=lambda pair: (-pair[1], pair[0])` to `key=lambda pair: pair[0]`. Expect `test_same_named_ids_come_most_cast_first_then_lowest_id` red.
- in `never_cast`, change `named.get(entry.name.casefold(), frozenset())` to `named.get(entry.name, frozenset())`. Expect `test_the_name_is_matched_whatever_its_case` red.
- in `scan_cache`, change `if node.get("type") == "cast" and isinstance(ability_id, int):` to `if isinstance(ability_id, int):`. Expect `test_a_row_that_is_not_a_cast_is_not_counted` red.
- in `scan_cache`, change the tuple added to `rows` to end with `node.get("timestamp"), pages)` and widen the set's annotation to match. Mypy is not the check here; run the test only. Expect `test_a_row_two_overlapping_pages_both_hold_is_counted_once` red.
- in `scan_cache`, change `if in_abilities and isinstance(game_id, int) and isinstance(name, str):` to `if isinstance(name, str):`. Expect `test_no_actor_name_is_read` red.
- in `scan_cache`, change `walk(value, key == "abilities")` to `walk(value, True)`. Expect `test_a_named_id_outside_an_ability_table_is_not_read` red.
- in `audit_data`, change the label in `("externals", load_externals().entries),` to `"defensives"`. Expect `test_every_data_file_gets_its_heading` red.

- [ ] **Step 7: The docs**

In `CLAUDE.md`'s Commands table, add a row directly after the `night` row:

```
| `uv run wowperf audit-data [--cache-dir DIR]` | Check every ability id in `data/` against the ids the cached logs cast, and print the entries never cast with what their name was cast as instead; offline, spends nothing |
```

and replace the sentence

```
All five take a report URL or a bare report code, and all five print what the run
spent from the hourly point budget, broken down by operation.
```

with

```
The five that read a report take a report URL or a bare report code, and each prints what
the run spent from the hourly point budget, broken down by operation. `audit-data` reads only
the local cache and spends nothing.
```

- [ ] **Step 8: Try it on the real cache**

Run: `/c/Users/damien/.local/bin/uv.exe run wowperf audit-data`

Expect three headings: defensives 34 of 139, externals 2 of 19, throughput_cooldowns 39 of 118. Among the lines, expect every one of the twelve entries Task 2 corrects, e.g. `  Warrior/Arms  Bladestorm  227847: never cast; the logs cast it as 446035 x498`. The output holds ability and specialisation names only. Keep it for your report. It prints no player name, but paste only the headings and the twelve lines into the report.

- [ ] **Step 9: Gate and commit**

Full gate. No golden moved. Subject: `Add an offline audit of the ability data against the ids logs cast`

---

### Task 2: The twelve entries take the id the log casts

**Files:**
- Modify: `data/defensives.toml`, `data/throughput_cooldowns.toml` (by the script below)
- Modify: `src/wowperf/domain/auras.py` (one docstring line), `tests/domain/report/test_build_deaths.py`, `tests/domain/test_cover.py`, `.claude/skills/wcl-api/SKILL.md` (by the second script below)
- Test: Create `tests/adapters/config/test_cast_ids.py`

**Interfaces:**
- Consumes: Task 1's `wowperf audit-data`, for the check in Step 6.

- [ ] **Step 1: Write the failing test**

Create `tests/adapters/config/test_cast_ids.py`:

```python
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
```

- [ ] **Step 2: Run and watch it fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/config/test_cast_ids.py -q`
Expected: `12 failed`, each naming its old id.

- [ ] **Step 3: Correct the data**

Write this script **with the file-writing tool** to your scratch directory (not the repository) as `correct_cast_ids.py`, and run it from the repository root with `/c/Users/damien/.local/bin/uv.exe run python <scratch>/correct_cast_ids.py`. It prints `applied`. It refuses to write anything if any line is not found exactly the stated number of times: stop and report if it asserts.

```python
# ABOUTME: Applies the twelve cast-id corrections and the header notes to the two data files.
# ABOUTME: Every replacement must match exactly the number of times stated, or nothing is written.
from pathlib import Path

DEFENSIVES = Path("data/defensives.toml")
THROUGHPUT = Path("data/throughput_cooldowns.toml")

HEADER = """#
# Amended 2026-09-30: an id is the one real logs cast when the ability is pressed, not
# only one the spell data names correctly. Several ids resolved to the right name and
# were never cast, because the game now logs the press under another id.
# `wowperf audit-data` checks every entry against the local cache. An entry marked
# "log id 2026-09-30" was corrected by that check. It keeps the base cooldown read when
# it was written -- the same ability, and no source this project may script confirms a
# new id's cooldown (docs/plans/2026-09-30-cast-ids-from-the-log-design.md).
"""

EDITS = {
    DEFENSIVES: [
        ('  { ability_id = 108978, name = "Alter Time", cooldown_seconds = 60.0 },\n',
         '  { ability_id = 342245, name = "Alter Time", cooldown_seconds = 60.0 },'
         '  # log id 2026-09-30, was 108978; 342247 is the early return\n', 3),
        ('  { ability_id = 243435, name = "Fortifying Brew", cooldown_seconds = 420.0 },\n',
         '  { ability_id = 115203, name = "Fortifying Brew", cooldown_seconds = 420.0 },'
         '  # log id 2026-09-30, was 243435\n', 2),
        ('verified = "2026-09-05"\n',
         HEADER
         + "# Unconfirmed by the same check, left unchanged until a log of that specialisation\n"
         + "# casts them: Guardian of Ancient Kings (86659; 212641 cast in reference runs),\n"
         + "# Vengeance Metamorphosis (187827; 200166 cast, possibly by Havoc).\n"
         + 'verified = "2026-09-05"\n', 1),
    ],
    THROUGHPUT: [
        ('  { ability_id = 227847, name = "Bladestorm", cooldown_seconds = 90.0 },\n',
         '  { ability_id = 446035, name = "Bladestorm", cooldown_seconds = 90.0 },'
         '  # log id 2026-09-30, was 227847\n', 2),
        ('  { ability_id = 152279, name = "Breath of Sindragosa", cooldown_seconds = 120.0 },\n',
         '  { ability_id = 1249658, name = "Breath of Sindragosa", cooldown_seconds = 120.0 },'
         '  # log id 2026-09-30, was 152279\n', 1),
        ('  { ability_id = 192759, name = "Kingsbane", cooldown_seconds = 45.0 },\n',
         '  { ability_id = 385627, name = "Kingsbane", cooldown_seconds = 45.0 },'
         '  # log id 2026-09-30, was 192759\n', 1),
        ('  { ability_id = 191427, name = "Metamorphosis", cooldown_seconds = 120.0 },\n',
         '  { ability_id = 200166, name = "Metamorphosis", cooldown_seconds = 120.0 },'
         '  # log id 2026-09-30, was 191427\n', 1),
        ('  { ability_id = 205545, name = "Odyn\'s Fury", cooldown_seconds = 45.0 },\n',
         '  { ability_id = 385059, name = "Odyn\'s Fury", cooldown_seconds = 45.0 },'
         '  # log id 2026-09-30, was 205545; 385060 and 385062 log with it\n', 1),
        ('  { ability_id = 323639, name = "The Hunt", cooldown_seconds = 90.0 },\n',
         '  { ability_id = 370965, name = "The Hunt", cooldown_seconds = 90.0 },'
         '  # log id 2026-09-30, was 323639; 370966 logs with it\n', 1),
        ('verified = "2026-09-06"\n',
         HEADER
         + "# Unconfirmed by the same check, left unchanged until a log of that specialisation\n"
         + "# casts them: Doom Winds (384352; 469270 cast in reference runs), Killing Spree\n"
         + "# (51690; 474478), Guardian Berserk (50334; 106951, possibly Feral's), and Holy\n"
         + "# Halo (120517; 120644 is Shadow's, and no Holy priest cast any Halo).\n"
         + 'verified = "2026-09-06"\n', 1),
    ],
}

texts = {path: path.read_text(encoding="utf-8") for path in EDITS}
for path, edits in EDITS.items():
    for old, new, times in edits:
        found = texts[path].count(old)
        assert found == times, f"{path}: expected {times} of {old!r}, found {found}"
        texts[path] = texts[path].replace(old, new)
for path, text in texts.items():
    path.write_text(text, encoding="utf-8")
print("applied")
```

Mistweaver and Windwalker keep 420 s, the cooldown their entry held. Brewmaster's own `115203` entry reads 360 s. The two are left different on purpose: the rule keeps each entry's cooldown, and the longer one only understates what was up. Say so in the report; do not reconcile them.

- [ ] **Step 4: Correct every note that Alter Time casts as 108978**

Write this script **with the file-writing tool** to your scratch directory as `correct_alter_time_notes.py`, and run it the same way. It prints `applied`, or asserts and writes nothing.

```python
# ABOUTME: Corrects every statement that Alter Time casts as 108978: the log casts it as 342245.
# ABOUTME: Every replacement must match exactly the number of times stated, or nothing is written.
from pathlib import Path

EDITS = {
    Path("src/wowperf/domain/auras.py"): [
        ("but not always: Alter Time casts as 108978 and buffs as 342246, Greater",
         "but not always: Alter Time casts as 342245 and buffs as 342246, Greater", 1),
    ],
    Path("tests/domain/report/test_build_deaths.py"): [
        ("# The regression this fix is for: Alter Time casts as 108978 but the aura",
         "# The regression this fix is for: Alter Time casts as 342245 but the aura", 1),
        ("# Alter Time casts as 108978 but the aura table keys the buff at 342246",
         "# Alter Time casts as 342245 but the aura table keys the buff at 342246", 1),
        ("ability_id=108_978", "ability_id=342_245", 3),
        ("(`.claude/skills/wcl-api/SKILL.md`,\n    # 2026-09-11)",
         "(`.claude/skills/wcl-api/SKILL.md`,\n    # 2026-09-11, corrected 2026-09-30)", 1),
        ("# (`.claude/skills/wcl-api/SKILL.md`, 2026-09-11). A hit's own `buff_ids`",
         "# (`.claude/skills/wcl-api/SKILL.md`, corrected 2026-09-30). A hit's own `buff_ids`", 1),
    ],
    Path("tests/domain/test_cover.py"): [
        ("# Time (cast 108978, buff 342246) or Greater Invisibility (cast 110959, buff",
         "# Time (cast 342245, buff 342246) or Greater Invisibility (cast 110959, buff", 1),
        ("# The regression this resolver exists for: the cast id (108978, Alter",
         "# The regression this resolver exists for: the cast id (342245, Alter", 1),
        ('assert resolve_aura(auras, 108978, "Alter Time") is aura',
         'assert resolve_aura(auras, 342245, "Alter Time") is aura', 1),
    ],
    Path(".claude/skills/wcl-api/SKILL.md"): [
        ("by name — Alter Time, cast `108978` against aura `342246`, and Greater Invisibility, cast\n"
         "`110959` against aura `110960` — while 100 did not appear because they were never cast in that\n"
         "run.\n",
         "by name — Alter Time, cast `108978` against aura `342246`, and Greater Invisibility, cast\n"
         "`110959` against aura `110960` — while 100 did not appear because they were never cast in that\n"
         "run. *Corrected 2026-09-30:* `108978` was the data file's id, not a measured cast. No cached\n"
         "page casts it; the log casts Alter Time as `342245` (the press) and `342247` (the early\n"
         "return), against the same aura `342246`. The id match failed because the data held the wrong\n"
         "id, and the name fallback is what found the aura. See\n"
         "`docs/plans/2026-09-30-cast-ids-from-the-log-design.md`.\n", 1),
    ],
}

texts = {path: path.read_text(encoding="utf-8") for path in EDITS}
for path, edits in EDITS.items():
    for old, new, times in edits:
        found = texts[path].count(old)
        assert found == times, f"{path}: expected {times} of {old!r}, found {found}"
        texts[path] = texts[path].replace(old, new)
for path, text in texts.items():
    path.write_text(text, encoding="utf-8")
print("applied")
```

The resolver those tests pin is still needed: the cast id `342245` and the aura id `342246` still differ.

- [ ] **Step 5: Run, pass, prove**

`tests/adapters/config/test_cast_ids.py` passes (12). The existing config tests pass unchanged, including the rule that no ability lives in two files for one spec. Then run the full suite: green, and no golden moved.

Prove it, restoring after each:
- In `data/throughput_cooldowns.toml`, change the Kingsbane entry's `385627` back to `192759`. Expect exactly the Kingsbane case of `test_a_corrected_entry_holds_the_id_the_logs_cast` red.
- In `data/defensives.toml`, change one Alter Time entry (Frost's) back to `108978`. Expect exactly the Frost Alter Time case red.
- Run `tests/domain/test_cover.py` and `tests/domain/report/test_build_deaths.py` after the Step 4 script. Both pass: the fixtures moved to `342245` and still differ from the aura's `342246`.

- [ ] **Step 6: The audit agrees**

Run: `/c/Users/damien/.local/bin/uv.exe run wowperf audit-data`

Expect defensives 29 of 139, externals 2 of 19, throughput_cooldowns 32 of 118: twelve fewer than Task 1's run. None of the twelve corrected entries is listed. These entries are still listed, as the design leaves them:
- Guardian of Ancient Kings;
- Vengeance Metamorphosis;
- Doom Winds;
- Killing Spree;
- Guardian Berserk;
- Holy Halo.

If the counts differ from Task 1's by anything but twelve, stop and report.

- [ ] **Step 7: Gate and commit**

Full gate. Subject: `Give twelve ability entries the id the logs cast when they are pressed`

---

### Task 3: Exercise it on real logs

**This task is not optional.** A new judgement is not done until a live run has exercised it.

**Files:**
- Modify: `docs/plans/2026-09-30-cast-ids-from-the-log-design.md` (status line and a Live paragraph in §5)

- [ ] **Step 1: The before and after, offline**

Write this script **with the file-writing tool** to your scratch directory as `cast_ids_live.py`, and run it from the repository root, with the network blocked so it cannot spend a point:

`HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 /c/Users/damien/.local/bin/uv.exe run --offline python <scratch>/cast_ids_live.py`

It reads the eight fights from the warm cache. It loads the old data from `git show main:` (the branch's base holds the old ids) and the new data from the working tree, and prints counts, fight ids and ability names only.

```python
# ABOUTME: Counts, on eight real fights from the warm cache, what the corrected ids change.
# ABOUTME: Old data comes from `git show main:<file>`; prints counts and ability names only.
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from wowperf.adapters.config.toml import (
    load_consumables,
    load_defensives,
    load_externals,
    load_roles,
    load_season_data,
    load_self_resurrections,
    load_throughput_cooldowns,
)
from wowperf.cli import build_repository
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.analysis.service import analyse
from wowperf.domain.report.deaths import build_deaths

ABILITIES = ("Alter Time", "Fortifying Brew", "Bladestorm", "Breath of Sindragosa", "Kingsbane",
             "Metamorphosis", "Odyn's Fury", "The Hunt")
NEW_IDS = {342245: 60.0, 115203: 420.0, 446035: 90.0, 1249658: 120.0, 385627: 45.0,
           200166: 120.0, 385059: 45.0, 370965: 90.0}
RAID = "cW38jmwdnZfbHVL4"
FIGHTS = [(RAID, 2, "raid"), (RAID, 30, "raid"), (RAID, 32, "raid"), (RAID, 8, "raid"),
          (RAID, 29, "raid"), (RAID, 31, "raid"),
          ("6Kx1P9GbNXrcLdHa", 36, "key"), ("4vFcVAW1PB2CrD9z", 72, "key")]

scratch = Path(tempfile.mkdtemp())
for name in ("defensives", "throughput_cooldowns"):
    old = subprocess.run(["git", "show", f"main:data/{name}.toml"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    (scratch / f"{name}.toml").write_text(old, encoding="utf-8")
SETS = {
    "old": (load_defensives(scratch / "defensives.toml"),
            load_throughput_cooldowns(scratch / "throughput_cooldowns.toml")),
    "new": (load_defensives(), load_throughput_cooldowns()),
}

repository = build_repository(Path("cache"))
rows: Counter[tuple[str, str]] = Counter()
findings: Counter[tuple[str, str]] = Counter()
gaps: dict[int, float] = {}
for code, fight, kind in FIGHTS:
    loaded = (repository.load_encounter(code, fight) if kind == "raid"
              else repository.load(code, fight))
    for label, (defensives, throughput) in SETS.items():
        cards = build_deaths(loaded, defensives, load_consumables(), load_externals(),
                             load_self_resurrections())
        for card in cards:
            for row in card.availability[0].rows:
                if row.ability in ABILITIES:
                    rows[(label, row.state)] += 1
        found = (analyse_encounter(loaded, defensives, load_consumables(), roles=load_roles())
                 if kind == "raid" else
                 analyse(loaded, load_season_data(), defensives, load_consumables(), throughput,
                         roles=load_roles()))
        for finding in found:
            text = " ".join((finding.title, finding.detail, *finding.evidence))
            if any(ability in text for ability in ABILITIES):
                findings[(label, finding.id.split(".")[0] + "." + finding.id.split(".")[1])] += 1
    by_actor: dict[tuple[int, int], list[int]] = {}
    for cast in loaded.casts:
        if cast.ability_id in NEW_IDS:
            by_actor.setdefault((cast.actor_id, cast.ability_id), []).append(cast.timestamp_ms)
    for (_actor, ability_id), times in by_actor.items():
        times.sort()
        for earlier, later in zip(times, times[1:], strict=False):
            gap = (later - earlier) / 1000
            gaps[ability_id] = min(gaps.get(ability_id, gap), gap)

print("own-defensive rows of the eight abilities, by state:")
for label in ("old", "new"):
    print(f"  {label}: {dict(sorted((s, c) for (l, s), c in rows.items() if l == label))}")
print("findings naming one of the eight, by kind:")
for label in ("old", "new"):
    print(f"  {label}: {dict(sorted((k, c) for (l, k), c in findings.items() if l == label))}")
print("shortest gap between one player's presses of a corrected id, within one fight:")
for ability_id, cooldown in NEW_IDS.items():
    gap = gaps.get(ability_id)
    shown = "no second press" if gap is None else f"{gap:.1f} s"
    print(f"  {ability_id:>8}: {shown} against a data cooldown of {cooldown:g} s")
sys.exit(0)
```

Finding ids carry player slugs. The script prints only each id's first two segments, such as `defensives.unused`, never the full id.

- [ ] **Step 2: One warm command run, as a reader sees it**

Run `/c/Users/damien/.local/bin/uv.exe run wowperf raid cW38jmwdnZfbHVL4 --fight 30 --no-compare --out <scratch>/live` and `/c/Users/damien/.local/bin/uv.exe run wowperf analyze 6Kx1P9GbNXrcLdHa --fight 36 --no-compare --out <scratch>/live`.
- Note the points each prints. Stop and report if either spends more than 30. Warm, each is about 1.
- Scan each written HTML only for `>None<`, `>null<`, `>nan<`, `{{` and `{%`, as counts.

The HTML is not otherwise read.

- [ ] **Step 3: The design's record**

In `docs/plans/2026-09-30-cast-ids-from-the-log-design.md`:
- The status line becomes `**Status:** approved and built, 2026-09-30.`
- Under §5, add a **Live** paragraph holding only what the runs printed:
  - the audit's headings before (Task 1 Step 8) and after (Task 2 Step 6);
  - the rows by state, old against new;
  - the findings by kind, old against new;
  - the shortest gap for each corrected id against its data cooldown;
  - the points spent, and the leak-scan counts.

  It uses numbers, fight ids and ability names only.
- Mark any outcome that never occurred as **open**, for example a state no corrected row reached.
- **For any corrected id whose shortest gap is under half its data cooldown, write one sentence** saying the gap is unexplained: a talent, a reset, or more than one cast row per press, and the log cannot say which. Do not change the cooldown. It was measured 2026-09-30 before this plan: Bladestorm's 446035 showed 24.5 s against 90 s.

- [ ] **Step 4: Gate and commit**

Run the offline gate. Subject: `Exercise the corrected ability ids on real logs`. The body gives the points and the counts, and no names.

---

## What this plan deliberately does not build

- **The five likely entries and Holy Halo.** They wait for a log of that specialisation, and the audit lists them every time it runs.
- **Any change to a cooldown,** including Fortifying Brew's 420 s beside Brewmaster's 360 s, and Bladestorm's short gap.
- **A way to model one press that logs several ids,** beyond choosing one.
- **Reading the spell data by script.**
