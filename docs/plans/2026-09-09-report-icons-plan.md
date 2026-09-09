# Spell Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw a spell icon beside every ability a death card names, embedded in the page as bytes so the report needs no network when it is opened.

**Architecture:** Warcraft Logs already knows each ability's icon filename; one new query field carries it to a map on `LoadedRun`. The view model gains an ability id at each icon site — integers only, never bytes. A one-method `IconSource` port, implemented in the render adapter, turns those ids into `data:` URIs by way of a permanent on-disk byte store and Blizzard's render CDN. The template emits one CSS rule per distinct icon and references it by class, so 181 rows cost 45 images.

**Tech Stack:** Python 3.12, `uv` only. pydantic v2 `Frozen` models, Jinja2 (autoescape mandatory), httpx, typer, pytest, ruff (line length 100), mypy strict.

**Spec:** `docs/plans/2026-09-09-report-icons-design.md`

## Global Constraints

- `src/wowperf/domain/` performs no I/O: no `httpx`, no `jinja2`, nothing touching the network, the disk or a template.
- No template holds a Jinja `{% set %}`, a `|sum` or a `sum(`. Every number reaches the page pre-computed.
- Every new numeric view-model field needs an entry in `NUMBERS_THAT_ARE_NOT_TOTALS` in `tests/adapters/render/test_html_invariants.py`, carrying a written reason.
- Never invent a Warcraft Logs field name. `icon` on `ReportAbility` was introspected against the live schema on 2026-09-09; its row in `.claude/skills/wcl-api/SKILL.md` must land in the same commit as the query change.
- The page loads no external resource. No `src` beginning `http://`, `https://` or `//`; no `url(http` in any CSS.
- Every file opens with two `# ABOUTME: ` lines (`{# ABOUTME: #}` in a template).
- Comments are evergreen: never a reference to a refactor, to "new" behaviour, or to how the code used to be.
- Commits: imperative mood, no `feat:`/`fix:` prefix, subject a sentence saying what the repository now does, body explaining **why**, final line `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Stage by name; never `git add -A`; never `--no-verify`.
- The gate is `uv run pytest && uv run ruff check . && uv run mypy`. `uv` is off PATH in Bash: prefix with `export PATH="$HOME/.local/bin:$PATH"`.
- Icon region and size are `eu` and `36`. Sizes 18, 36 and 56 serve; 128 does not. Region `cn` does not.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/adapters/wcl/queries.py` | `ABILITIES_QUERY` gains `icon` |
| `src/wowperf/adapters/wcl/repository.py` | builds the id → filename map beside the id → name map |
| `src/wowperf/adapters/wcl/ingest.py` | keeps `killingAbilityGameID` on `Death` |
| `src/wowperf/domain/model.py` | `LoadedRun.ability_icons` and its read-only mapping |
| `src/wowperf/domain/events.py` | `Death.killing_blow_id` |
| `src/wowperf/domain/analysis/recap.py` | `RecapEvent.ability_id`, `AbilityState.ability_id` |
| `src/wowperf/domain/report/model.py` | `ability_id` on `RecapRow` and `AvailabilityRow`, `killing_blow_id` on `DeathCard` |
| `src/wowperf/domain/report/deaths.py` | copies each id into the view model |
| `src/wowperf/domain/ports.py` | the `IconSource` protocol |
| `src/wowperf/adapters/render/icons.py` | **new** — filename rules, the on-disk store, the Blizzard resolver |
| `src/wowperf/adapters/render/html.py` | `render(report, icons=None)`, and the walk that collects ids |
| `src/wowperf/adapters/render/report.html.j2` | the CSS rules inside the existing `<style>` |
| `src/wowperf/adapters/render/_deaths.html.j2` | the icon span at three sites |
| `src/wowperf/adapters/render/report.css.j2` | `.icon` sizing |
| `src/wowperf/cli.py` | builds the resolver and hands it to `render` |
| `.claude/skills/wcl-api/SKILL.md` | the `icon` row and the dated findings |

---

### Task 1: Carry each ability's icon filename from Warcraft Logs to the domain

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py:153-163`
- Modify: `src/wowperf/adapters/wcl/repository.py:305-314`
- Modify: `src/wowperf/domain/model.py` (`LoadedRun`, around line 120)
- Modify: `.claude/skills/wcl-api/SKILL.md` (the Fields table, around line 20)
- Test: `tests/domain/test_model.py`, `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Produces: `LoadedRun.ability_icons: tuple[tuple[int, str], ...]` and the property `LoadedRun.ability_icon_map -> Mapping[int, str]`. Task 8 reads the map; nothing else does.

- [ ] **Step 1: Write the failing test for the mapping property**

In `tests/domain/test_model.py`:

```python
def test_a_loaded_run_reads_its_icon_pairs_as_a_mapping() -> None:
    loaded = LoadedRun(run=a_run(), ability_icons=((48792, "spell_deathknight_iceboundfortitude.jpg"),))
    assert loaded.ability_icon_map[48792] == "spell_deathknight_iceboundfortitude.jpg"


def test_a_loaded_run_with_no_icon_pairs_reads_an_empty_mapping() -> None:
    assert dict(LoadedRun(run=a_run()).ability_icon_map) == {}
```

Add `LoadedRun` to that file's existing `from wowperf.domain.model import ...` line. `a_run()` is already defined at line 23, and `test_the_npc_count_map_reads_as_a_mapping` at line 78 is the precedent these two mirror.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_model.py -q
```

Expected: `AttributeError: 'LoadedRun' object has no attribute 'ability_icon_map'`.

- [ ] **Step 3: Add the field and the property**

In `src/wowperf/domain/model.py`, inside `LoadedRun`, after `resurrections`:

```python
    # Icon file names by ability game id, straight from the report's own ability
    # dictionary. A tuple of pairs, not a dict, so a LoadedRun stays immutable and
    # hashable; read it through ability_icon_map. A file name is data of the same
    # kind as an ability name, so carrying it performs no I/O.
    ability_icons: tuple[tuple[int, str], ...] = ()

    @property
    def ability_icon_map(self) -> Mapping[int, str]:
        """Icon file names by ability game id, as a read-only mapping."""
        return MappingProxyType(dict(self.ability_icons))
```

`Mapping` and `MappingProxyType` are already imported in this module for `Run.npc_count_map`.

- [ ] **Step 4: Run it and watch it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_model.py -q
```

- [ ] **Step 5: Write the failing test for the repository building the map**

`recording_repository` (line 105) is the fixture every load test is built on, and its
`abilities` payload is hardcoded empty at line 127. Give it a way to carry rows without
changing what existing tests see — add a keyword argument defaulting to the empty list:

```python
def recording_repository(
    ...,
    abilities_rows: list[dict[str, Any]] | None = None,
) -> WclRunRepository:
```

and use it at line 127:

```python
    abilities: dict[str, Any] = {
        "reportData": {"report": {"masterData": {"abilities": abilities_rows or []}}}
    }
```

Every existing caller keeps the empty list and the fallback to "Unknown ability N" they
already assert on. Then add the test:

```python
def test_a_loaded_run_carries_each_abilitys_icon_file_name(tmp_path: Path) -> None:
    repository = recording_repository(
        tmp_path=tmp_path,
        abilities_rows=[{"gameID": 48792, "name": "Icebound Fortitude", "icon": "spell_x.jpg"}],
    )
    loaded, _ = repository.load("CODE", 36)
    assert loaded.ability_icon_map[48792] == "spell_x.jpg"


def test_an_ability_with_no_icon_contributes_no_pair(tmp_path: Path) -> None:
    repository = recording_repository(
        tmp_path=tmp_path,
        abilities_rows=[{"gameID": 48792, "name": "Icebound Fortitude", "icon": None}],
    )
    loaded, _ = repository.load("CODE", 36)
    assert dict(loaded.ability_icon_map) == {}
```

Match `recording_repository`'s real parameter names and the public method the other load
tests call — read lines 105-220 before writing this.

- [ ] **Step 6: Run it and watch it fail**

Expected: `KeyError: 48792`, because `ability_icons` is still empty.

- [ ] **Step 7: Add `icon` to the query**

In `src/wowperf/adapters/wcl/queries.py`, line 158:

```python
        abilities { gameID name icon }
```

- [ ] **Step 8: Build the map in the repository**

In `src/wowperf/adapters/wcl/repository.py`, replace lines 305-314 with:

```python
        abilities = self._query(ABILITIES_QUERY, {"code": report_code}, hits)
        try:
            rows = abilities["reportData"]["report"]["masterData"]["abilities"]
            ability_names = {ability["gameID"]: ability["name"] for ability in rows}
            ability_icons = tuple(
                (ability["gameID"], ability["icon"])
                for ability in rows
                if ability.get("icon")
            )
        except (KeyError, TypeError) as error:
            raise WclError(
                "The abilities response did not carry masterData.abilities as expected"
            ) from error
```

Then add `ability_icons=ability_icons,` to **both** `LoadedRun(...)` constructions in `_load` — the `profile == "speed"` one and the full one.

- [ ] **Step 9: Run the repository tests**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl -q
```

- [ ] **Step 10: Add the skill row, or `test_skills.py` fails**

In `.claude/skills/wcl-api/SKILL.md`, in the Fields table (starts line 20), after the `masterData` row:

```markdown
| `icon` | `ReportAbility` | 2026-09-09 | yes |
```

Then, in the prose section that describes `masterData`, add:

```markdown
- **`ReportAbility` carries exactly `gameID`, `icon`, `name` and `type`** — introspected
  against the live schema 2026-09-09. There is no description, no cooldown and no tooltip
  text on it. `icon` is a bare lower-case file name ending `.jpg`, e.g.
  `spell_holy_magicalsentry.jpg`; all 2511 rows of one report carried one, and three carried
  a literal `?cachebust` suffix naming a file the other rows also named.
```

- [ ] **Step 11: Run the whole gate**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

- [ ] **Step 12: Commit**

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/queries.py src/wowperf/adapters/wcl/repository.py src/wowperf/domain/model.py .claude/skills/wcl-api/SKILL.md tests/domain/test_model.py tests/adapters/wcl/test_repository.py
```

Message subject: `Carry each ability's icon file name off the report's own dictionary`. Body: the icon name rides along on a query already being sent, so it costs no extra points; the field and its skill row land together because the skill table is a machine-checked claim about `queries.py`; changing the query text orphans every cached `Abilities` entry, which is one 7-point refetch.

---

### Task 2: Put the ability id on every recap row

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py` (`RecapEvent` ~line 28, `recap_timeline` ~line 52)
- Modify: `src/wowperf/domain/report/model.py` (`RecapRow` ~line 107)
- Modify: `src/wowperf/domain/report/deaths.py` (`_recap_row` ~line 85)
- Modify: `tests/adapters/render/test_html_invariants.py` (the allowlist)
- Test: `tests/domain/analysis/test_recap_timeline.py`, `tests/domain/report/test_build_deaths.py`

**Interfaces:**
- Produces: `RecapEvent.ability_id: int` and `RecapRow.ability_id: int | None`. Task 7 reads `RecapRow.ability_id`.

- [ ] **Step 1: Write the failing test**

In `tests/domain/analysis/test_recap_timeline.py`:

```python
def test_each_timeline_row_carries_the_ability_it_names() -> None:
    run = loaded(
        damage_taken=(a_hit(55_000, 10_000),),
        casts=(a_cast(56_000),),
    )
    rows = recap_timeline(run, a_death())
    assert [(row.kind, row.ability_id) for row in rows] == [(HIT, 1), (CAST, 9)]
```

`a_hit` builds a `DamageTakenEvent` with `ability_id=1` and `a_cast` a `CastEvent` with `ability_id=9`; both helpers are already at the top of that file.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_recap_timeline.py -q
```

Expected: `AttributeError: 'RecapEvent' object has no attribute 'ability_id'`.

- [ ] **Step 3: Add the field and populate it**

In `src/wowperf/domain/analysis/recap.py`, add to `RecapEvent` after `ability_name`:

```python
    ability_id: int = 0
```

and extend its docstring with:

```
    `ability_id` is the game id of the ability named, which the page uses to
    draw its icon. Zero means the log named no ability for this row.
```

Then in `recap_timeline`, add `ability_id=hit.ability_id`, `ability_id=heal.ability_id` and `ability_id=cast.ability_id` to the three `RecapEvent(...)` constructions.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Write the failing test for the view model**

In `tests/domain/report/test_build_deaths.py`:

```python
def test_a_recap_row_carries_the_ability_id_the_page_draws_an_icon_from() -> None:
    hits = (a_hit(1, 54_200, "Snowdrift", 82_410),)
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), hits), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.timeline[0].ability_id == hits[0].ability_id
```

- [ ] **Step 6: Run it and watch it fail**

Expected: `AttributeError: 'RecapRow' object has no attribute 'ability_id'`.

- [ ] **Step 7: Add the field to the view model and copy it through**

In `src/wowperf/domain/report/model.py`, add to `RecapRow` after `health_percent`:

```python
    ability_id: int | None = None
```

and extend its docstring with:

```
    `ability_id` names the ability for an icon, or is None where the log named
    none. Zero is never used: the ability dictionary maps zero to "Unknown
    Ability" with a real icon file, so a zero would draw art beside a row
    nobody identified.
```

In `src/wowperf/domain/report/deaths.py`, in `_recap_row`, add to the returned `RecapRow(...)`:

```python
        ability_id=event.ability_id or None,
```

The `or None` is what turns the zero sentinel into an absence, and is the only place that conversion happens.

- [ ] **Step 8: Run it and watch it pass**

- [ ] **Step 9: Add the allowlist entry**

In `tests/adapters/render/test_html_invariants.py`, inside `NUMBERS_THAT_ARE_NOT_TOTALS`:

```python
    (RecapRow, "ability_id"),  # a spell's identity, not a duration
```

- [ ] **Step 10: Run the whole gate**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

- [ ] **Step 11: Commit**

Subject: `Keep the ability id on a recap row beside the name it shows`. Body: the id exists on every event the recap reads and was dropped one layer before the page; an icon is keyed on identity rather than on a display string, and two abilities can share a name.

---

### Task 3: Put the ability id on defensive and external availability rows

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py` (`AbilityState` ~line 174, `state_of` ~line 204, `availability_at` ~line 288)
- Modify: `src/wowperf/domain/report/model.py` (`AvailabilityRow`)
- Modify: `src/wowperf/domain/report/deaths.py` (`_availability_row` ~line 108)
- Modify: `tests/adapters/render/test_html_invariants.py`
- Test: `tests/domain/analysis/test_recap_availability.py`, `tests/domain/report/test_build_deaths.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `AbilityState.ability_id: int | None`, `AvailabilityRow.ability_id: int | None`.

- [ ] **Step 1: Write the failing test**

In `tests/domain/analysis/test_recap_availability.py`, using that file's existing helpers for defensives and a loaded run:

```python
def test_a_defensives_state_carries_the_ability_id_it_was_judged_from() -> None:
    at = availability_at(
        a_loaded_run(), a_death(), DEFENSIVES, NO_CONSUMABLES, NO_EXTERNALS,
        visible_from_ms=0,
    )
    assert at.own is not None
    assert [state.ability_id for state in at.own] == [48792]


def test_a_consumable_state_carries_no_ability_id() -> None:
    at = availability_at(
        a_loaded_run(), a_death(), NO_DEFENSIVES, CONSUMABLES, NO_EXTERNALS,
        visible_from_ms=0,
    )
    assert at.consumables is not None
    assert all(state.ability_id is None for state in at.consumables)
```

Match the fixture names this file already uses; `48792` must be the ability id in whatever defensives fixture it defines.

- [ ] **Step 2: Run it and watch it fail**

Expected: `AttributeError: 'AbilityState' object has no attribute 'ability_id'`.

- [ ] **Step 3: Add the field and thread it through the two call sites that have one**

In `src/wowperf/domain/analysis/recap.py`, add to `AbilityState` after `owner_id`:

```python
    ability_id: int | None = None
```

and extend its docstring with:

```
    `ability_id` is the game id this state was judged from, and None for a
    consumable: a category is a cooldown group holding several ids, and no one
    of them is the item.
```

Give `state_of` a keyword-only parameter, beside `owner_id`:

```python
    ability_id: int | None = None,
```

and pass it into the `AbilityState(...)` it returns. Then in `availability_at`, add `ability_id=ability.ability_id,` to the `state_of(...)` call for `own` and to the one for `mates`. Leave `consumable_state` alone — it names a category, not an ability.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Write the failing test for the view model**

In `tests/domain/report/test_build_deaths.py`, extend the existing test that asserts on a defensives group, or add:

```python
def test_an_availability_row_carries_the_ability_id_it_names() -> None:
    card = build_deaths(
        a_loaded_with((a_death(1, 60_000),), ()), DEFENSIVES, NO_CONSUMABLES
    )[0]
    defensives = card.availability[0]
    assert [row.ability_id for row in defensives.rows] == [48792]
```

using whatever defensives fixture this file already defines, and its ability id.

- [ ] **Step 6: Run it and watch it fail**

- [ ] **Step 7: Add the field and copy it**

In `src/wowperf/domain/report/model.py`, add to `AvailabilityRow`:

```python
    ability_id: int | None = None
```

and extend its docstring with:

```
    `ability_id` is None on a consumable row, which names a cooldown group
    rather than one item, so those rows carry no icon.
```

In `src/wowperf/domain/report/deaths.py`, in `_availability_row`, add to the returned `AvailabilityRow(...)`:

```python
        ability_id=state.ability_id,
```

- [ ] **Step 8: Run it and watch it pass**

- [ ] **Step 9: Add the allowlist entry**

```python
    (AvailabilityRow, "ability_id"),  # a spell's identity, not a duration
```

- [ ] **Step 10: Run the whole gate**

- [ ] **Step 11: Commit**

Subject: `Keep the ability id on the defensives and externals a death card lists`. Body: both come from data files that already hold the id, and `availability_at` already read it to find the presses; a consumable row keeps None because its category holds several ids and none of them is the item.

---

### Task 4: Keep the killing blow's ability id

**Files:**
- Modify: `src/wowperf/domain/events.py` (`Death` ~line 7)
- Modify: `src/wowperf/adapters/wcl/ingest.py:224-235`
- Modify: `src/wowperf/domain/report/model.py` (`DeathCard`)
- Modify: `src/wowperf/domain/report/deaths.py` (`build_deaths` ~line 201)
- Modify: `tests/adapters/render/test_html_invariants.py`
- Test: `tests/adapters/wcl/test_ingest.py`, `tests/domain/report/test_build_deaths.py`

**Interfaces:**
- Produces: `Death.killing_blow_id: int`, `DeathCard.killing_blow_id: int | None`.

- [ ] **Step 1: Write the failing test**

In `tests/adapters/wcl/test_ingest.py`, extend the file's existing death-building test or add one, mirroring its fixture shape:

```python
def test_a_death_keeps_the_id_of_the_ability_that_killed_it() -> None:
    events = [{"type": "death", "targetID": 1, "timestamp": 60_000,
               "killingAbilityGameID": 1297749}]
    deaths = build_deaths(events, a_run(), (), {1297749: "Frozen Tempest"})
    assert deaths[0].killing_blow_id == 1297749
```

- [ ] **Step 2: Run it and watch it fail**

Expected: `AttributeError: 'Death' object has no attribute 'killing_blow_id'`.

- [ ] **Step 3: Add the field and stop discarding the id**

In `src/wowperf/domain/events.py`, add to `Death` after `killing_blow`:

```python
    killing_blow_id: int = 0
```

In `src/wowperf/adapters/wcl/ingest.py`, replace the `killing_blow=` line inside the `Death(...)` construction (lines 229-231) with:

```python
                killing_blow_id=event.get("killingAbilityGameID", 0),
                killing_blow=_ability_name(
                    ability_names, event.get("killingAbilityGameID", 0)
                ),
```

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Write the failing test for the card**

In `tests/domain/report/test_build_deaths.py`:

```python
def test_a_death_card_carries_the_killing_blows_ability_id() -> None:
    death = a_death(1, 60_000).model_copy(update={"killing_blow_id": 1297749})
    card = build_deaths(
        a_loaded_with((death,), ()), NO_DEFENSIVES, NO_CONSUMABLES
    )[0]
    assert card.killing_blow_id == 1297749
```

- [ ] **Step 6: Run it and watch it fail**

- [ ] **Step 7: Add the field and copy it**

In `src/wowperf/domain/report/model.py`, add to `DeathCard` after `killing_blow`:

```python
    killing_blow_id: int | None = None
```

In `src/wowperf/domain/report/deaths.py`, inside the `DeathCard(...)` construction, after `killing_blow=death.killing_blow,`:

```python
                killing_blow_id=death.killing_blow_id or None,
```

- [ ] **Step 8: Run it and watch it pass**

- [ ] **Step 9: Add the allowlist entry**

```python
    (DeathCard, "killing_blow_id"),  # a spell's identity, not a duration
```

- [ ] **Step 10: Run the whole gate**

- [ ] **Step 11: Commit**

Subject: `Keep the id of the ability that killed a player, not only its name`. Body: the ingest read `killingAbilityGameID` and used it once to look a name up; the heading of every death card names that ability and is the most prominent place on the page an icon belongs.

---

### Task 5: A permanent on-disk store for icon bytes

**Files:**
- Create: `src/wowperf/adapters/render/icons.py`
- Test: `tests/adapters/render/test_icons.py` (new)

**Interfaces:**
- Produces: `icon_filename(raw: str) -> str | None`; `IconStore(directory: Path)` with `read(name) -> bytes | None`, `known_miss(name) -> bool`, `write(name, payload: bytes) -> None`, `write_miss(name) -> None`.

- [ ] **Step 1: Write the failing tests for the file-name rule**

Create `tests/adapters/render/test_icons.py`:

```python
# ABOUTME: The rules that decide what an icon file name is, and the store that keeps the bytes.
# ABOUTME: No network: every rule here is decided before a request would be made.

from pathlib import Path

from wowperf.adapters.render.icons import IconStore, icon_filename


def test_a_plain_icon_name_is_accepted() -> None:
    assert icon_filename("spell_holy_magicalsentry.jpg") == "spell_holy_magicalsentry.jpg"


def test_a_query_suffix_is_stripped_so_two_spellings_name_one_file() -> None:
    assert icon_filename("ability_monk_chiexplosion.jpg?cachebust") == (
        "ability_monk_chiexplosion.jpg"
    )


def test_a_name_that_could_walk_out_of_the_cache_directory_is_refused() -> None:
    assert icon_filename("../../../etc/passwd.jpg") is None
    assert icon_filename("sub/dir/spell.jpg") is None


def test_a_name_that_is_not_a_jpg_is_refused() -> None:
    assert icon_filename("spell_holy_magicalsentry.png") is None
    assert icon_filename("") is None
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_icons.py -q
```

Expected: `ModuleNotFoundError: No module named 'wowperf.adapters.render.icons'`.

- [ ] **Step 3: Write the module with the rule only**

Create `src/wowperf/adapters/render/icons.py`:

```python
# ABOUTME: Turns an ability id into an embedded image, through a permanent store and Blizzard's CDN.
# ABOUTME: Every rule here decides what to fetch, what to keep, and what to draw nothing for.

import base64
import os
import re
import tempfile
from pathlib import Path

SAFE_NAME = re.compile(r"[a-z0-9_-]+\.jpg")
"""What the ability dictionary's icon strings look like, and nothing else.

The string comes from an API and becomes both a URL and a path on this machine,
so it is checked before it is either. Every one of the 2511 names in a real
report matches this, so the rule refuses nothing that exists today.
"""


def icon_filename(raw: str) -> str | None:
    """The file an icon string names, or None when it does not name one.

    A handful of strings carry a `?cachebust` suffix over a file the dictionary
    also names plainly, so dropping the query both builds the right URL and
    collapses the two spellings onto one cache entry.
    """
    name = raw.split("?", 1)[0]
    return name if SAFE_NAME.fullmatch(name) else None
```

- [ ] **Step 4: Run them and watch them pass**

- [ ] **Step 5: Write the failing tests for the store**

Append to `tests/adapters/render/test_icons.py`:

```python
def test_the_store_reads_back_what_it_wrote(tmp_path: Path) -> None:
    store = IconStore(tmp_path)
    store.write("spell_a.jpg", b"\xff\xd8bytes")
    assert store.read("spell_a.jpg") == b"\xff\xd8bytes"


def test_an_unknown_file_reads_as_nothing_and_is_not_a_known_miss(tmp_path: Path) -> None:
    store = IconStore(tmp_path)
    assert store.read("spell_a.jpg") is None
    assert store.known_miss("spell_a.jpg") is False


def test_a_recorded_miss_is_remembered_so_it_is_asked_for_once(tmp_path: Path) -> None:
    store = IconStore(tmp_path)
    store.write_miss("spell_a.jpg")
    assert store.known_miss("spell_a.jpg") is True
    assert store.read("spell_a.jpg") is None
```

- [ ] **Step 6: Run them and watch them fail**

Expected: `ImportError: cannot import name 'IconStore'`.

- [ ] **Step 7: Write the store**

Append to `src/wowperf/adapters/render/icons.py`:

```python
class IconStore:
    """Icon bytes on disk, kept for good, one file per icon.

    Never expires. The art does not change, and an expiring store would re-pull
    every icon on a schedule to receive the same bytes back. An absence is
    recorded too, beside the file it stands in for, so an icon Blizzard does not
    serve costs one request ever rather than one per run.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def read(self, name: str) -> bytes | None:
        path = self._directory / name
        return path.read_bytes() if path.is_file() else None

    def known_miss(self, name: str) -> bool:
        return (self._directory / f"{name}.miss").is_file()

    def write(self, name: str, payload: bytes) -> None:
        self._write_atomically(self._directory / name, payload)

    def write_miss(self, name: str) -> None:
        self._write_atomically(self._directory / f"{name}.miss", b"")

    def _write_atomically(self, path: Path, payload: bytes) -> None:
        handle, temporary = tempfile.mkstemp(dir=self._directory)
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(payload)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
```

- [ ] **Step 8: Run them and watch them pass**

- [ ] **Step 9: Run the whole gate**

- [ ] **Step 10: Commit**

Subject: `Keep icon bytes on disk for good, and remember the ones that are missing`. Body: the existing `DiskCache` keys on a GraphQL query and stores JSON, which fits neither an image nor a URL; the name arrives from an API and becomes a path, so it is validated before it is either; a recorded absence stops a known-missing icon being asked for on every run.

---

### Task 6: Resolve an ability id to an embedded image

**Files:**
- Modify: `src/wowperf/domain/ports.py`
- Modify: `src/wowperf/adapters/render/icons.py`
- Test: `tests/adapters/render/test_icons.py`

**Interfaces:**
- Consumes: `icon_filename`, `IconStore` (Task 5); `LoadedRun.ability_icon_map` (Task 1), as the `filenames` argument.
- Produces: `IconSource` protocol with `data_uri(ability_id: int) -> str | None`; `BlizzardIcons(filenames: Mapping[int, str], store: IconStore, fetch: Callable[[str], tuple[int, str, bytes]])`.

`fetch` returns `(status_code, content_type, body)` for a URL. Injecting it is what keeps the network out of the suite; Task 8 passes one built on `httpx`.

- [ ] **Step 1: Add the port**

In `src/wowperf/domain/ports.py`:

```python
class IconSource(Protocol):
    def data_uri(self, ability_id: int) -> str | None: ...
```

with the comment:

```python
# None means no icon for that ability, whatever the reason -- an id the report's
# dictionary does not name, a file the CDN does not serve, a store that could not
# be read. The page does the same thing for all three, so it is told no more.
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/adapters/render/test_icons.py`:

```python
from wowperf.adapters.render.icons import BlizzardIcons, IconStore, icon_filename

JPEG = b"\xff\xd8\xff\xe0jpegbytes"


def a_source(tmp_path: Path, filenames: dict[int, str], responses: dict[str, tuple[int, str, bytes]],
             asked: list[str] | None = None) -> BlizzardIcons:
    def fetch(url: str) -> tuple[int, str, bytes]:
        if asked is not None:
            asked.append(url)
        return responses.get(url, (404, "text/html", b""))

    return BlizzardIcons(filenames, IconStore(tmp_path), fetch)


def test_an_ability_the_dictionary_names_is_embedded(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    source = a_source(tmp_path, {1: "spell_a.jpg"}, {url: (200, "image/jpeg", JPEG)})
    assert source.data_uri(1) == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()


def test_an_ability_the_dictionary_does_not_name_draws_nothing(tmp_path: Path) -> None:
    assert a_source(tmp_path, {}, {}).data_uri(1) is None


def test_ability_zero_draws_nothing_even_though_it_names_a_file(tmp_path: Path) -> None:
    # The dictionary maps zero to "Unknown Ability" and gives it a real axe icon.
    # Drawing it would put art beside a row nobody identified.
    url = "https://render.worldofwarcraft.com/eu/icons/36/inv_axe_02.jpg"
    source = a_source(tmp_path, {0: "inv_axe_02.jpg"}, {url: (200, "image/jpeg", JPEG)})
    assert source.data_uri(0) is None


def test_a_refusal_carrying_xml_is_a_miss_and_is_never_embedded(tmp_path: Path) -> None:
    # Blizzard answers an absent icon with 403 and an XML body, not a 404.
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    source = a_source(tmp_path, {1: "spell_a.jpg"}, {url: (403, "application/xml", b"<Error/>")})
    assert source.data_uri(1) is None


def test_a_200_that_is_not_an_image_is_a_miss(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    source = a_source(tmp_path, {1: "spell_a.jpg"}, {url: (200, "text/html", b"<html>")})
    assert source.data_uri(1) is None


def test_a_missing_icon_is_asked_for_once_and_then_remembered(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    asked: list[str] = []
    responses = {url: (403, "application/xml", b"<Error/>")}
    assert a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1) is None
    assert a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1) is None
    assert asked == [url]


def test_a_stored_icon_is_not_asked_for_again(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    asked: list[str] = []
    responses = {url: (200, "image/jpeg", JPEG)}
    a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1)
    a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1)
    assert asked == [url]


def test_a_name_the_rule_refuses_is_never_requested(tmp_path: Path) -> None:
    asked: list[str] = []
    source = a_source(tmp_path, {1: "../escape.jpg"}, {}, asked)
    assert source.data_uri(1) is None
    assert asked == []
```

Add `import base64` at the top of the test file.

- [ ] **Step 3: Run them and watch them fail**

Expected: `ImportError: cannot import name 'BlizzardIcons'`.

- [ ] **Step 4: Write the resolver**

Append to `src/wowperf/adapters/render/icons.py`:

```python
ICON_BASE = "https://render.worldofwarcraft.com/eu/icons/36/"
"""Blizzard's own render CDN, which needs no API key.

Sizes 18, 36 and 56 are served and 128 is not; regions us, eu, kr and tw are
served and cn is not. Thirty-six matches the size these are drawn at.
"""

UNKNOWN_ABILITY = 0
"""The ability dictionary's own row for an ability it could not name.

It carries a real icon file -- a generic axe -- so drawing it would put art
beside a row nobody identified. It is refused before anything is fetched.
"""


class BlizzardIcons:
    """An ability id, drawn as bytes the page carries with it.

    `fetch` is handed in rather than built here so the rules above it can be
    tested without a network. It answers a URL with a status, a content type and
    a body.
    """

    def __init__(
        self,
        filenames: Mapping[int, str],
        store: IconStore,
        fetch: Callable[[str], tuple[int, str, bytes]],
    ) -> None:
        self._filenames = filenames
        self._store = store
        self._fetch = fetch

    def data_uri(self, ability_id: int) -> str | None:
        name = self._name_of(ability_id)
        if name is None:
            return None
        payload = self._store.read(name)
        if payload is None:
            if self._store.known_miss(name):
                return None
            payload = self._download(name)
        if payload is None:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(payload).decode()

    def _name_of(self, ability_id: int) -> str | None:
        if ability_id == UNKNOWN_ABILITY:
            return None
        raw = self._filenames.get(ability_id)
        return None if raw is None else icon_filename(raw)

    def _download(self, name: str) -> bytes | None:
        """An answer counts as an icon only if it says so twice.

        A file Blizzard does not serve comes back as a refusal carrying XML
        rather than as a not-found, so the status alone would have an error
        document embedded in the page as though it were a picture.
        """
        status, content_type, body = self._fetch(ICON_BASE + name)
        if status != 200 or not content_type.startswith("image/"):
            self._store.write_miss(name)
            return None
        self._store.write(name, body)
        return body
```

Add to the module's imports:

```python
from collections.abc import Callable, Mapping
```

- [ ] **Step 5: Run them and watch them pass**

- [ ] **Step 6: Run the whole gate**

- [ ] **Step 7: Commit**

Subject: `Turn an ability id into an image the page carries with it`. Body: the rules that decide what is fetched and what is drawn are the feature, so `fetch` is injected and every one of them is tested without a network; a status code alone is not enough because a missing icon answers 403 with an XML body, which would otherwise be embedded as a picture.

---

### Task 7: Draw the icons

**Files:**
- Modify: `src/wowperf/adapters/render/html.py`
- Modify: `src/wowperf/adapters/render/report.html.j2`
- Modify: `src/wowperf/adapters/render/_deaths.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_html_sections.py`, `tests/adapters/render/test_html_invariants.py`

**Interfaces:**
- Consumes: `IconSource` (Task 6); `RecapRow.ability_id` (Task 2), `AvailabilityRow.ability_id` (Task 3), `DeathCard.killing_blow_id` (Task 4).
- Produces: `render(report: Report, icons: IconSource | None = None) -> str`.

- [ ] **Step 1: Write the failing tests**

In `tests/adapters/render/test_html_sections.py`:

```python
class FakeIcons:
    """Answers for the ids it was given and for no others."""

    def __init__(self, uris: dict[int, str]) -> None:
        self.uris = uris
        self.asked: list[int] = []

    def data_uri(self, ability_id: int) -> str | None:
        self.asked.append(ability_id)
        return self.uris.get(ability_id)


def test_an_icon_is_drawn_beside_the_ability_it_names() -> None:
    card = a_card(timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                                     ability_id=42),))
    html = render(a_report(deaths=(card,)), icons=FakeIcons({42: "data:image/jpeg;base64,AAA"}))
    assert ".i-42 { background-image: url(data:image/jpeg;base64,AAA); }" in html
    assert '<span class="icon i-42" aria-hidden="true"></span>' in html
    assert "Snowdrift" in html


def test_an_ability_with_no_icon_still_shows_its_name_and_emits_no_span() -> None:
    card = a_card(timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                                     ability_id=42),))
    html = render(a_report(deaths=(card,)), icons=FakeIcons({}))
    assert "Snowdrift" in html
    assert 'class="icon' not in html


def test_an_ability_drawn_many_times_is_embedded_once() -> None:
    rows = tuple(
        RecapRow(seconds_before=f"{n}.0 s", kind="hit", ability="Snowdrift", ability_id=42)
        for n in range(9)
    )
    html = render(a_report(deaths=(a_card(timeline=rows),)),
                  icons=FakeIcons({42: "data:image/jpeg;base64,AAA"}))
    assert html.count("background-image") == 1
    assert html.count('class="icon i-42"') == 9


def test_rendering_without_an_icon_source_is_the_page_as_it_was() -> None:
    card = a_card(timeline=(RecapRow(seconds_before="5.8 s", kind="hit", ability="Snowdrift",
                                     ability_id=42),))
    assert render(a_report(deaths=(card,))) == render(a_report(deaths=(card,)), icons=None)
    assert "background-image" not in render(a_report(deaths=(card,)))
```

`a_card(**changes)` at line 427 applies `model_copy(update=changes)`, so `a_card(timeline=...)` works as written — no change to the helper.

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_sections.py -q
```

Expected: `TypeError: render() got an unexpected keyword argument 'icons'`.

- [ ] **Step 3: Collect the ids and resolve them, in `html.py`**

```python
def _icon_uris(report: Report, icons: IconSource) -> dict[int, str]:
    """Every ability the page can draw, resolved once each, in the order it is met.

    Only the adapter can build this: which ids resolve is a question about a CDN
    and a cache, and the builder that made the report is forbidden from asking it.
    """
    resolved: dict[int, str] = {}
    for card in report.deaths:
        candidates = [card.killing_blow_id]
        candidates.extend(row.ability_id for row in card.timeline)
        for group in card.availability:
            candidates.extend(row.ability_id for row in group.rows)
        for ability_id in candidates:
            if ability_id is None or ability_id in resolved:
                continue
            uri = icons.data_uri(ability_id)
            if uri is not None:
                resolved[ability_id] = uri
    return resolved
```

and change `render`:

```python
def render(report: Report, icons: IconSource | None = None) -> str:
    """One self-contained HTML document: one inline script that only shows and hides,
    no network, no external font.

    Without an `icons` source the page is drawn exactly as it is without icons:
    the ids on the view model are inert until something can turn them into bytes.
    """
    uris = {} if icons is None else _icon_uris(report, icons)
    return _environment().get_template(TEMPLATE_NAME).render(report=report, icons_by_id=uris)
```

Import `IconSource` from `wowperf.domain.ports`.

- [ ] **Step 4: Emit the CSS in `report.html.j2`**

Inside the existing `<style>`, after the `{% include "report.css.j2" %}` line:

```jinja
{% for ability_id, uri in icons_by_id.items() %}
.i-{{ ability_id }} { background-image: url({{ uri }}); }
{% endfor %}
```

A data URI holds only base64 and punctuation autoescape leaves alone, so this needs no `|safe` — which is the reason it is a loop over pairs rather than one pre-built string.

- [ ] **Step 5: Add the span at the three sites in `_deaths.html.j2`**

The heading:

```jinja
    <h3>{% if death.killing_blow_id in icons_by_id %}<span class="icon i-{{ death.killing_blow_id }}"
      aria-hidden="true"></span>{% endif %}{{ death.player }} — {{ death.killing_blow }}</h3>
```

The recap row's ability cell:

```jinja
          <td>{% if row.ability_id in icons_by_id %}<span class="icon i-{{ row.ability_id }}"
            aria-hidden="true"></span>{% endif %}{{ row.ability }}</td>
```

The availability row:

```jinja
            <span class="avail-name">{% if row.ability_id in icons_by_id %}<span
              class="icon i-{{ row.ability_id }}" aria-hidden="true"></span>{% endif %}{{ row.ability }}
```

The membership test is a lookup, not arithmetic, and it is what keeps the markup and the CSS driven by one answer.

- [ ] **Step 6: Add the sizing to `report.css.j2`**

```css
.icon { display: inline-block; width: 16px; height: 16px; margin-right: 5px;
  vertical-align: -3px; border-radius: 2px; background-size: cover; }
```

- [ ] **Step 7: Run them and watch them pass**

- [ ] **Step 8: Add the invariant test**

In `tests/adapters/render/test_html_invariants.py`, beside `test_the_page_executes_only_its_own_script`:

```python
def test_the_page_loads_no_image_over_the_network() -> None:
    # The existing script test checks `src` attributes; an icon reaches the page
    # through a CSS url() instead, which that check never sees. A hotlinked icon
    # would leave the report blank the day Blizzard moved the file.
    html = render(a_report())
    assert "url(http" not in html
    assert "url(//" not in html
```

- [ ] **Step 9: Regenerate the golden file and read its diff**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update -q
```

```bash
/mingw64/bin/git diff tests/adapters/render/golden/minimal.html
```

The minimal fixture has no `IconSource`, so this diff should be **empty**. If it is not, the no-icon path is not byte-identical and Step 3's `uris = {}` branch is wrong — fix that rather than accepting the diff.

- [ ] **Step 10: Run the whole gate**

- [ ] **Step 11: Commit**

Subject: `Draw a spell's icon beside its name on every death card`. Body: 181 rows draw 45 distinct icons, so the bytes are emitted once per ability as a CSS rule and referenced by class — a data URI per row would cost about 400 KB for one section; the span is emitted only where an image was actually resolved, so a missing icon costs appearance and never meaning, and a page rendered without a source is byte-identical to before.

---

### Task 8: Wire the CLI and verify against a real report

**Files:**
- Modify: `src/wowperf/cli.py:94-117` and `:583-602`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the failing test**

In `tests/test_cli.py`, mirroring how that file already builds an `analyze` invocation against stubbed data:

```python
def test_analyze_writes_a_report_whose_icons_are_embedded(tmp_path: Path) -> None:
    # The stubbed CDN answers every icon; the point is that the CLI wires one in
    # at all, not what it returns.
    html = (tmp_path / "out" / "CODE-1.html").read_text(encoding="utf-8")
    assert "url(data:image/jpeg;base64," in html
    assert "url(http" not in html
```

Build it on whatever fixture that file already uses to run `analyze` end to end offline, extending its abilities payload with an `icon` per row and pointing the icon fetcher at a fake.

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Build the fetcher and the source in the CLI**

Add near `build_repository`:

```python
ICON_CACHE_SUBDIR = "icons"


def build_icons(loaded: LoadedRun, cache_dir: Path) -> BlizzardIcons:
    """Icons for one run: its own ability dictionary, and a store that keeps them for good."""

    def fetch(url: str) -> tuple[int, str, bytes]:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        return response.status_code, response.headers.get("content-type", ""), response.content

    return BlizzardIcons(
        loaded.ability_icon_map, IconStore(cache_dir / ICON_CACHE_SUBDIR), fetch
    )
```

and at the render call, pass it:

```python
        render(
            build_report(...),
            icons=build_icons(loaded, cache_dir),
        ),
```

leaving the `build_report(...)` arguments exactly as they are.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Run the whole gate**

- [ ] **Step 6: Render a real report and look at it**

```bash
export PATH="$HOME/.local/bin:$PATH"
set -a && . <(iconv -f UTF-16 -t UTF-8 .env | tr -d '\r') 2>/dev/null && set +a
uv run wowperf analyze 6Kx1P9GbNXrcLdHa --fight 36 --out out
```

Then check the three things the design predicted, and report the actual numbers rather than asserting success:

```bash
export PATH="$HOME/.local/bin:$PATH"; python - <<'PY'
import pathlib, re
t = pathlib.Path("out/6Kx1P9GbNXrcLdHa-36.html").read_text(encoding="utf-8")
print("bytes:", len(t))
print("distinct icons embedded:", t.count("background-image"))
print("icon spans drawn:", t.count('class="icon i-'))
print("external references:", len(re.findall(r"url\((?:http|//)", t)))
PY
```

Expected: roughly 258,000 bytes, about 60 embedded, around 220 spans, and **zero** external references. A second run should embed the same number while making no requests, because the store is permanent.

- [ ] **Step 7: Look at the page**

Serve `out/` and open a death card:

```bash
export PATH="$HOME/.local/bin:$PATH"; python -m http.server 8765 --directory out
```

Confirm by eye: icons sit beside names in the recap table, in the two availability groups that have ids, and in each card heading; consumable rows show a name with no icon and no gap where one should be; nothing is an icon without its name.

- [ ] **Step 8: Commit**

Subject: `Fetch a run's icons when the report is written`. Body: the resolver is built from the run's own ability dictionary and a store under the cache directory, so a second analysis of the same run makes no image requests at all; the fetcher is the only thing in this feature that touches the network and it is the only part not covered by the suite.

---

## Self-Review

**Spec coverage.** §3's scope: recap rows (Task 2), defensives and externals (Task 3), killing blow (Task 4); consumables excluded by Task 3 leaving `ability_id` None on them. §4.1's six fields: Tasks 2, 3 and 4. §4.2's map: Task 1. §5's port and `render` signature: Tasks 6 and 7. §6's five resolver rules: Task 6, one test each, plus the file-name rule in Task 5. §7's embed-once: Task 7 Step 1. §8's store and validation: Task 5. §11's tests: throughout, with the new `url(http` invariant in Task 7 Step 8. §13's skill rows: Task 1 Step 10.

**Two spec points deliberately not given their own task.** §9's byte and request figures are measured in Task 8 Step 6 rather than asserted in a test, because a size assertion would fail on every unrelated change to the page. §12's existing invariants are already enforced by the suite; no task may weaken them, and the gate in every task's last steps is what proves it.

**Ordering.** Tasks 2, 3 and 4 are independent of each other and of Task 1; each touches a different type. Task 6 needs Task 5. Task 7 needs 2, 3, 4 and 6. Task 8 needs everything.

**One risk worth naming.** Task 1 changes the text of `ABILITIES_QUERY`, and `cache_key` hashes that text, so the first run after that task refetches the ability dictionary for 7 points. If the gate is run repeatedly against a live report between tasks it will pay that once, not each time.
