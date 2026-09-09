# Finding Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw a spell icon inline at the ability's own words in every finding that names one.

**Architecture:** `Finding` gains the ability's id and name while keeping a flat title. The single function every finding already passes through, `ledger_row()`, cuts the title at the name — but only when the name occurs exactly once — and hands the template three pieces. The template reuses the death cards' span, class and CSS rule unchanged. Comparison findings name a reference report's abilities, so the parse references' icon names are threaded onto `ParseMember` and merged into the resolver's map.

**Tech Stack:** Python 3.12, `uv` only. pydantic v2 `Frozen` models, Jinja2 (autoescape mandatory), httpx, typer, pytest, ruff (line length 100), mypy strict.

**Spec:** `docs/plans/2026-09-09-finding-icons-design.md`

## Global Constraints

- `src/wowperf/domain/` performs no I/O: no `httpx`, no `jinja2`, nothing touching the network, the disk or a template.
- No template holds a Jinja `{% set %}`, a `|sum` or a `sum(`. Every number reaches the page pre-computed.
- Every new numeric view-model field needs an entry in `NUMBERS_THAT_ARE_NOT_TOTALS` in `tests/adapters/render/test_html_invariants.py`, carrying a written reason. View-model types only — `Finding` is domain and needs none.
- `tests/adapters/render/golden/minimal.html` stays byte-identical. A non-empty golden diff means the code is wrong, not the golden.
- A page rendered with no `IconSource` is byte-identical to a page rendered before this work.
- The page loads no external resource: no `src` beginning `http://`, `https://` or `//`; no `url(http` or `url(//` in any CSS.
- Autoescape stays on. No `|safe`, no `Markup`, no `autoescape false`.
- Every file opens with two `# ABOUTME: ` lines (`{# ABOUTME: #}` in a template).
- Comments are evergreen: never a reference to a refactor, to "new" behaviour, or to how the code used to be.
- Commits: imperative mood, no `feat:`/`fix:` prefix, subject a sentence saying what the repository now does, body explaining **why**. Final line exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Stage by name; never `git add -A`; never `--no-verify`.
- The gate is `uv run pytest -q && uv run ruff check . && uv run mypy`. `uv` is off PATH in Bash: prefix with `export PATH="$HOME/.local/bin:$PATH"`. mypy takes its paths from `pyproject.toml` — pass none.
- Invoke git by absolute path: `/mingw64/bin/git`.
- **Every new test proves it bites by mutation**: break the line it covers, run the test, watch it FAIL, restore, and record the mutation, the command and the actual failing output in the report. Five of the previous slice's eight tasks failed their first review for tests that could not fail.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/findings.py` | `Finding.ability_id`, `Finding.ability_name` |
| `src/wowperf/domain/analysis/interrupts.py` | populates them on the unkicked-ability finding |
| `src/wowperf/domain/analysis/defensives.py` | populates them on the ceiling and never-cast findings |
| `src/wowperf/domain/analysis/throughput.py` | populates them on the ceiling finding |
| `src/wowperf/domain/analysis/deaths.py` | populates them on the single-death finding |
| `src/wowperf/domain/analysis/players.py` | threads the ability id out of `_damage_outliers`, then populates |
| `src/wowperf/domain/comparison/spells.py` | populates them on four findings |
| `src/wowperf/domain/comparison/uptime.py` | populates them on two findings |
| `src/wowperf/domain/report/ledger.py` | `_split_title`, and `ledger_row` filling the new fields |
| `src/wowperf/domain/report/model.py` | `LedgerRow`'s four fields, and `all_ledger_rows` |
| `src/wowperf/adapters/render/_macros.html.j2` | the icon span inside the `ledger_row` macro |
| `src/wowperf/adapters/render/html.py` | `_icon_uris` walking every ledger row |
| `src/wowperf/adapters/wcl/repository.py` | `ability_icons` on the `parse`-profile `LoadedRun` |
| `src/wowperf/domain/comparison/sample.py` | `ParseMember.ability_icons` |
| `src/wowperf/cli.py` | merging the reference icon names into the resolver |

---

### Task 1: Let a finding carry the ability it names

**Files:**
- Modify: `src/wowperf/domain/findings.py` (`Finding`, around line 10)
- Modify: `src/wowperf/domain/analysis/interrupts.py:172-186`
- Test: `tests/domain/analysis/test_interrupts.py`

**Interfaces:**
- Produces: `Finding.ability_id: int | None = None` and `Finding.ability_name: str = ""`. Every later task sets them; Task 6 reads them.

- [ ] **Step 1: Write the failing test**

In `tests/domain/analysis/test_interrupts.py`. That file's helpers are `row(at, is_start, instance=0, ability=SPELL)`, `kick(at, instance=0, ability=SPELL)` and `hit(at, amount, ability=SPELL)`, with `SPELL` its module-level ability id. Note that `analyse_interrupts(casts, damage_taken)` takes **reconstructed casts**, not raw rows — the file already imports `reconstruct_enemy_casts` for this.

```python
def test_an_unkicked_ability_finding_names_the_ability_it_is_about() -> None:
    # An unkicked cast that completed and was followed by damage is what makes
    # an `interrupts.ability.` finding at all.
    casts = reconstruct_enemy_casts((row(1_000, True), row(3_000, False)), ())
    findings = analyse_interrupts(casts, (hit(3_100, 5_000),))
    ability = next(f for f in findings if f.id.startswith("interrupts.ability."))
    assert ability.ability_id == SPELL
    assert ability.ability_name in ability.title
```

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_interrupts.py -q
```

Expected: `AttributeError: 'Finding' object has no attribute 'ability_id'`.

- [ ] **Step 3: Add the fields**

In `src/wowperf/domain/findings.py`, inside `Finding`, after `pull_index` and before the comment above `quantifier`:

```python
    # The ability this finding is about, for the icon the page draws at its name.
    # `ability_id` is None on a finding that names no single ability; `ability_name`
    # is the same spelling the title uses, so locating it there is never a guess
    # about which words are the spell.
    ability_id: int | None = None
    ability_name: str = ""
```

- [ ] **Step 4: Populate the interrupts finding**

In `src/wowperf/domain/analysis/interrupts.py`, the `Finding(...)` at line 173 sits inside `for rank, (ability_id, damage) in enumerate(ranked[:MAX_ABILITIES_REPORTED]):`, so both values are already in scope. Add to that `Finding(...)`:

```python
                ability_id=ability_id,
                ability_name=names[ability_id],
```

- [ ] **Step 5: Run it and watch it pass**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_interrupts.py -q
```

- [ ] **Step 6: Prove the test bites**

Remove `ability_id=ability_id,` from the `Finding(...)`, re-run the test, confirm it fails, restore, confirm it passes. Record the mutation, the command and the failing output.

- [ ] **Step 7: Run the whole gate**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/findings.py src/wowperf/domain/analysis/interrupts.py tests/domain/analysis/test_interrupts.py
```

Subject: `Let a finding carry the ability it names, not only its name in prose`. Body: the page draws an icon from an identity, and two abilities can share a name; the title stays one string so the findings JSON, the digit-free narrative guardrail and `titles_by_id` are untouched.

---

### Task 2: Name the ability on the defensive, throughput and death findings

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py:234-254` and `:259-274`
- Modify: `src/wowperf/domain/analysis/throughput.py:255-275`
- Modify: `src/wowperf/domain/analysis/deaths.py:151-159`
- Test: `tests/domain/analysis/test_defensives.py`, `tests/domain/analysis/test_throughput.py`, `tests/domain/analysis/test_deaths.py`

**Interfaces:**
- Consumes: `Finding.ability_id`, `Finding.ability_name` (Task 1).
- Produces: nothing new; four more findings carry them.

- [ ] **Step 1: Write the three failing tests**

In `tests/domain/analysis/test_defensives.py`. `analyse_defensives(run, casts, defensives, deaths)`. `BLOOD_DEFENSIVES` holds Icebound Fortitude `48792`; `DEFENSIVES` holds Prismatic Barrier `235450` and Ice Block `45438`, so casting the first leaves the second never cast.

```python
def test_a_ceiling_finding_names_the_defensive_it_judged() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    findings = analyse_defensives(run, (a_cast(actor_id=1, ability_id=48792),),
                                  BLOOD_DEFENSIVES, ())
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")[0]
    assert ceiling.ability_id == 48792
    assert ceiling.ability_name in ceiling.title


def test_a_never_cast_finding_names_the_defensive_it_is_about() -> None:
    findings = analyse_defensives(a_run(), (cast(11, 235450),), DEFENSIVES, ())
    never = next(f for f in findings if "never cast" in f.title)
    assert never.ability_id == 45438
    assert never.ability_name in never.title
```

In `tests/domain/analysis/test_throughput.py`. `BURST = CooldownAbility(ability_id=31884, name="Avenging Wrath", cooldown_seconds=120.0)`, and note the existing test imports the function *inside* the test body:

```python
def test_a_throughput_ceiling_finding_names_the_cooldown_it_judged() -> None:
    from wowperf.domain.analysis.throughput import analyse_cooldown_ceiling

    pulls = (a_pull(0, 0, 1_800_000),)
    casts = (a_cast(31884, 10_000), a_cast(343721, 10_000))
    findings = analyse_cooldown_ceiling(a_run(pulls), casts, COOLDOWNS, ())
    ceiling = next(f for f in findings if f.id.startswith("throughput.ceiling."))
    assert ceiling.ability_id == BURST.ability_id
    assert ceiling.ability_name in ceiling.title
```

In `tests/domain/analysis/test_deaths.py`. `analyse_deaths(run, deaths)`, and the local helper is:

```python
def a_death(
    name: str, actor_id: int, at: int, cost: float | None, pull_index: int | None = 0
) -> Death:
    return Death(player_name=name, actor_id=actor_id, timestamp_ms=at,
                 killing_blow="Molten Scar", pull_index=pull_index,
                 seconds_until_next_action=cost)
```

It sets `killing_blow` but not `killing_blow_id`. Extend it with a defaulted keyword so every existing caller is untouched — add `killing_blow_id: int = 0` to its signature and `killing_blow_id=killing_blow_id` to the `Death(...)`. Then:

```python
def test_a_single_death_finding_names_the_ability_that_killed() -> None:
    deaths = (a_death("Emberkin", 11, 1_000, 10.0, killing_blow_id=1297749),)
    findings = analyse_deaths(a_run(), deaths)
    single = next(f for f in findings if f.id.startswith("deaths.single."))
    assert single.ability_id == 1297749
    assert single.ability_name == "Molten Scar"


def test_a_death_whose_killing_blow_has_no_id_names_no_ability() -> None:
    # `a_death` leaves killing_blow_id at Death's default of 0, which the
    # dictionary maps to "Unknown Ability" with a real axe icon.
    findings = analyse_deaths(a_run(), (a_death("Emberkin", 11, 1_000, 10.0),))
    single = next(f for f in findings if f.id.startswith("deaths.single."))
    assert single.ability_id is None
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis/test_defensives.py tests/domain/analysis/test_throughput.py tests/domain/analysis/test_deaths.py -q
```

Expected: assertion failures on `ability_id`, which is `None`.

- [ ] **Step 3: Populate the two defensives findings**

Both sit inside `for ability in known:` (`defensives.py:218`), so `ability` is in scope for each. Add to the `Finding(...)` at line 234 and again to the one at line 259:

```python
                        ability_id=ability.ability_id,
                        ability_name=ability.name,
```

- [ ] **Step 4: Populate the throughput finding**

The `Finding(...)` at `throughput.py:255` sits inside `for ability in cooldowns.for_spec(player.class_name, player.spec):` (line 239). Add:

```python
                    ability_id=ability.ability_id,
                    ability_name=ability.name,
```

- [ ] **Step 5: Populate the single-death finding**

`first = group[0]` at `deaths.py:110` is a `Death`, and `Death.killing_blow_id: int = 0` exists (`domain/events.py:12`). Add to the `Finding(...)` at line 151:

```python
                    ability_id=first.killing_blow_id or None,
                    ability_name=first.killing_blow,
```

The `or None` turns the zero sentinel into an absence. The report's ability dictionary maps id zero to "Unknown Ability" with a real axe icon, so a zero reaching the page would draw art beside a killing blow nobody identified.

- [ ] **Step 6: Run them and watch them pass**

- [ ] **Step 7: Prove each test bites**

Four mutations, one per site: remove the `ability_id=` line, run that site's test, confirm it fails, restore. For the deaths site, additionally confirm a death with `killing_blow_id=0` yields `ability_id is None` — write that as a fifth assertion or a sibling test, because a test using only a non-zero id does not cover the `or None`.

- [ ] **Step 8: Run the whole gate**

- [ ] **Step 9: Commit**

Subject: `Name the ability on the defensive, cooldown and death findings`. Body: each of these already held the ability it judged in a local and dropped it at the `Finding`; the id is what an icon is keyed on, and the killing blow keeps `None` for id zero because the dictionary gives "Unknown Ability" a real icon.

---

### Task 3: Carry the ability id out of the damage outliers

**Files:**
- Modify: `src/wowperf/domain/analysis/players.py` (`_damage_outliers` and its caller around line 220)
- Test: `tests/domain/analysis/test_players.py`

**Interfaces:**
- Consumes: `Finding.ability_id`, `Finding.ability_name` (Task 1).
- Produces: `_damage_outliers` returns a six-element tuple rather than five.

This site is unlike the others: the ability id is the loop key inside `_damage_outliers` but is **not** in the tuple it returns, so it has to be threaded out before the `Finding` can name it.

- [ ] **Step 1: Write the failing test**

In `tests/domain/analysis/test_players.py`. `analyse_players(run, casts, deaths, interrupts, damage_taken, roles=Roles())`, and the local `hit(actor_id, amount, ability=500)` builds a `DamageTakenEvent` named `"Molten Scar"` with ability id `500`:

```python
def test_a_damage_outlier_finding_names_the_ability_that_hit() -> None:
    run = a_run_with_duplicate_names()
    damage = (
        hit(0, 300_000), hit(5, 300_000), hit(1, 10_000), hit(2, 10_000), hit(3, 10_000),
    )
    findings = analyse_players(run, (), (), (), damage)
    outlier = next(f for f in findings if f.id.startswith("players.damage."))
    assert outlier.ability_id == 500
    assert outlier.ability_name == "Molten Scar"
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Widen the returned tuple**

In `src/wowperf/domain/analysis/players.py`, change `_damage_outliers`' annotation from

```python
) -> list[tuple[int, str, str, int, float]]:
```

to

```python
) -> list[tuple[int, int, str, str, int, float]]:
```

and update its docstring's first line to read:

```
    """(actor id, ability id, player name, ability name, amount, multiple of the median), worst first.
```

Then add the id to the tuple it appends:

```python
                outliers.append(
                    (
                        actor_id,
                        ability_id,
                        names.get(actor_id, f"Actor {actor_id}"),
                        ability_names[ability_id],
                        amount,
                        multiple,
                    )
                )
```

- [ ] **Step 4: Unpack it at the call site and populate the finding**

Find where `_damage_outliers(...)` is unpacked (it feeds the loop containing the `Finding` at line 220) and add `ability_id` in the second position, matching the tuple above. Then add to that `Finding(...)`:

```python
                ability_id=ability_id,
                ability_name=ability,
```

`ability` is the existing local holding the ability's name — the same value the title interpolates.

- [ ] **Step 5: Run it and watch it pass**

- [ ] **Step 6: Prove the test bites**

Remove `ability_id=ability_id,` from the `Finding(...)`, run the test, confirm it fails, restore. Then separately confirm the tuple widening is load-bearing: mypy must fail if the call site's unpacking and the return annotation disagree — run `uv run mypy` with the call site left at five names and record that it errors.

- [ ] **Step 7: Run the whole gate**

- [ ] **Step 8: Commit**

Subject: `Carry the ability id out of the damage outliers, not only its name`. Body: the id was the key the outliers were grouped by and was dropped from the tuple that leaves the function, so the finding could name the ability in prose but not identify it.

---

### Task 4: Name the ability on the comparison findings

**Files:**
- Modify: `src/wowperf/domain/comparison/spells.py:108-126`, `:144-162`, `:249-269`, `:304-323`
- Modify: `src/wowperf/domain/comparison/uptime.py:119-140`, `:312-334`
- Test: `tests/domain/comparison/test_spells.py`, `tests/domain/comparison/test_uptime.py`

**Interfaces:**
- Consumes: `Finding.ability_id`, `Finding.ability_name` (Task 1).

All six already unpack `ability_id` and `name` in their loop headers. This is the same two-line addition six times, in two files.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/comparison/test_spells.py`. `compare_spells(ours, our_player, theirs, their_name)` and `compare_spells_sample(ours, our_player, sample)`. Module fixtures: `SHIFTING_POWER = 314791` (cast by 4 of 5 sample members, never by us), `METEOR = 153561`, `OURS_LOADED`, `SAMPLE_OF_FIVE`.

```python
def test_a_missing_spell_finding_names_the_ability_against_one_reference() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 120.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 120.0),),
        (
            cast(11, 30451, "Arcane Blast", 1_000, 0),
            cast(11, 153626, "Arcane Orb", 2_000, 0),
            cast(11, 153626, "Arcane Orb", 3_000, 0),
        ),
    )
    missing = next(
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.missing.")
    )
    assert missing.ability_id == 153626
    assert missing.ability_name in missing.title


def test_a_rate_spell_finding_names_the_ability_against_one_reference() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_member(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 30451, "Arcane Blast", n * 1_000, 0) for n in range(6)),
    )
    rate = next(
        f for f in compare_spells(ours, OURS, theirs, "Bríala")
        if f.id.startswith("compare.spells.rate.")
    )
    assert rate.ability_id == 30451
    assert rate.ability_name in rate.title


def test_a_missing_spell_finding_names_the_ability_across_the_sample() -> None:
    missing = next(
        f for f in compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.spells.missing.")
    )
    assert missing.ability_id == SHIFTING_POWER
    assert missing.ability_name in missing.title


def test_a_rate_spell_finding_names_the_ability_across_the_sample() -> None:
    rate = next(
        f for f in compare_spells_sample(OURS_LOADED, OURS, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.spells.rate.")
    )
    assert rate.ability_id == METEOR
    assert rate.ability_name in rate.title
```

In `tests/domain/comparison/test_uptime.py`. `compare_uptime(ours, our_auras, our_player, theirs, their_auras, their_name)` and `compare_uptime_sample(ours, our_auras, our_player, sample)`. Coagulopathy is `391477`.

```python
def test_an_uptime_gap_finding_names_the_aura_against_one_reference() -> None:
    ours = a_run(BOSS)
    theirs = a_run(BOSS, player=a_player("Wipsdk", 3))
    our_auras = PlayerAuras(actor_id=7, on_self=(an_aura(391477, "Coagulopathy", (0, 20_000)),))
    their_auras = PlayerAuras(actor_id=3, on_self=(an_aura(391477, "Coagulopathy", (0, 90_000)),))
    gap = next(
        f for f in compare_uptime(ours, our_auras, a_player(), theirs, their_auras, "Wipsdk")
        if f.id.startswith("compare.uptime.")
    )
    assert gap.ability_id == 391477
    assert gap.ability_name in gap.title


def test_an_uptime_gap_finding_names_the_aura_across_the_sample() -> None:
    gap = next(
        f for f in compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)
        if f.id.startswith("compare.uptime.")
    )
    assert gap.ability_id == 391477
    assert gap.ability_name in gap.title
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_spells.py tests/domain/comparison/test_uptime.py -q
```

- [ ] **Step 3: Populate all six**

To each of the six `Finding(...)` constructions listed in **Files**, add:

```python
                ability_id=ability_id,
                ability_name=name,
```

Both names are already unpacked in each enclosing loop header — `spells.py` at lines 106, 142, 247 and 299-301; `uptime.py` at lines 115-117 and 308-310. Match each site's indentation.

- [ ] **Step 4: Run them and watch them pass**

- [ ] **Step 5: Prove the tests bite**

Mutate one site per file by removing its `ability_id=` line, run that file's tests, confirm failure, restore. Then, to catch a cross-site copy-paste, confirm that each of your new tests asserts against the ability id its own arrangement uses rather than a shared constant.

- [ ] **Step 6: Run the whole gate**

- [ ] **Step 7: Commit**

Subject: `Name the ability on the spell and uptime comparison findings`. Body: all six already unpacked the id beside the name and used only the name; a comparison finding names an ability our player never cast, which is exactly the case an icon has to be keyed on identity to draw.

---

### Task 5: Cut a finding's title at the ability it names

**Files:**
- Modify: `src/wowperf/domain/report/ledger.py:77-95`
- Modify: `src/wowperf/domain/report/model.py` (`LedgerRow`, around line 34)
- Modify: `tests/adapters/render/test_html_invariants.py` (the allowlist)
- Test: `tests/domain/report/test_ledger.py`

**Interfaces:**
- Consumes: `Finding.ability_id`, `Finding.ability_name` (Tasks 1-4).
- Produces: `LedgerRow.title_before: str`, `LedgerRow.title_ability: str`, `LedgerRow.title_after: str`, `LedgerRow.ability_id: int | None`. Task 6 renders them; Task 7 reads `ability_id`.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/report/test_ledger.py` (create it if that path does not exist; check for the file the existing `ledger_row` tests live in first and use that one):

```python
def test_a_title_is_cut_at_the_ability_it_names() -> None:
    row = ledger_row(
        a_finding(title="Uglymage never cast Ice Block",
                  ability_id=45438, ability_name="Ice Block"),
        {},
    )
    assert (row.title_before, row.title_ability, row.title_after) == (
        "Uglymage never cast ", "Ice Block", ""
    )
    assert row.ability_id == 45438


def test_a_title_whose_ability_is_not_in_it_is_left_whole() -> None:
    row = ledger_row(
        a_finding(title="Uglymage pressed nothing",
                  ability_id=45438, ability_name="Ice Block"),
        {},
    )
    assert (row.title_before, row.title_ability, row.title_after) == (
        "Uglymage pressed nothing", "", ""
    )
    assert row.ability_id is None


def test_a_title_naming_its_ability_twice_is_left_whole() -> None:
    # Two occurrences and no way to say which one the reader means, so the row
    # keeps its whole title and draws no icon.
    row = ledger_row(
        a_finding(title="Ice Block was ready; Uglymage never cast Ice Block",
                  ability_id=45438, ability_name="Ice Block"),
        {},
    )
    assert row.title_ability == ""
    assert row.ability_id is None


def test_a_finding_that_names_no_ability_is_left_whole() -> None:
    row = ledger_row(a_finding(title="4 deaths cost 64s of play"), {})
    assert row.title_before == "4 deaths cost 64s of play"
    assert row.ability_id is None
```

`a_finding(**changes)` is the local helper that builds a `Finding` with defaults and applies the changes; add it if that file has no equivalent, following the `a_card(**changes)` pattern at `tests/adapters/render/test_html_sections.py:427`.

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_ledger.py -q
```

Expected: `AttributeError: 'LedgerRow' object has no attribute 'title_before'`.

- [ ] **Step 3: Add the view-model fields**

In `src/wowperf/domain/report/model.py`, inside `LedgerRow`, after `title`:

```python
    title_before: str = ""
    title_ability: str = ""
    title_after: str = ""
    ability_id: int | None = None
```

and extend its docstring with:

```
    `title` is the whole sentence and is what the compact summary pointer
    renders. The three `title_*` fields are that same sentence cut at the
    ability the finding names, for the card that draws an icon there:
    `title_before + title_ability + title_after == title` always holds. When
    the sentence was not cut, `title_before` carries all of it, the other two
    are empty, and `ability_id` is None, so the card has one shape to render
    and nothing to draw.
```

- [ ] **Step 4: Write the split**

In `src/wowperf/domain/report/ledger.py`, above `ledger_row`:

```python
def _split_title(finding: Finding) -> tuple[str, str, str]:
    """A finding's title cut at the ability it names, or whole when it cannot be.

    The cut is made only when the name appears exactly once. Absent, the
    analyser and its own title disagree; twice, and there is no way to say
    which one a reader means. Either way the row keeps its whole title and
    draws no icon, which is the same silent fallback every other missing icon
    already uses.

    The identity always comes from `ability_id`. The name only locates a
    substring already known to be there, so this recovers nothing from prose.
    """
    name = finding.ability_name
    if finding.ability_id is None or not name or finding.title.count(name) != 1:
        return finding.title, "", ""
    before, after = finding.title.split(name)
    return before, name, after
```

- [ ] **Step 5: Fill the fields in `ledger_row`**

Replace the body of `ledger_row` after the `parent_id` line with:

```python
    before, ability, after = _split_title(finding)
    return LedgerRow(
        finding_id=finding.id,
        title=finding.title,
        title_before=before,
        title_ability=ability,
        title_after=after,
        # Set only when the cut succeeded, so one field answers both "where does
        # the icon go" and "is there one at all".
        ability_id=finding.ability_id if ability else None,
        detail=finding.detail,
        badge=badge_for(finding.confidence),
        seconds=format_seconds(finding.seconds_lost),
        nests_inside=titles_by_id.get(parent_id) if parent_id is not None else None,
        evidence=finding.evidence,
    )
```

- [ ] **Step 6: Run them and watch them pass**

- [ ] **Step 7: Add the concatenation invariant**

In the same test file:

```python
def test_every_row_of_a_real_report_can_be_reassembled_from_its_parts() -> None:
    # Two representations of one sentence would drift apart on their own; this
    # is what keeps them one sentence.
    report = a_full_report()
    rows = list(all_ledger_rows(report))
    assert rows, "a report with no findings would make this vacuous"
    for row in rows:
        assert row.title_before + row.title_ability + row.title_after == row.title
```

`all_ledger_rows` arrives in Task 7. Until then, write this against whichever fixture the file already uses to build a populated `Report`, iterating the row-bearing fields by hand, and change it to `all_ledger_rows` in Task 7 — the plan revisits it there.

- [ ] **Step 8: Add the allowlist entry**

In `tests/adapters/render/test_html_invariants.py`, inside `NUMBERS_THAT_ARE_NOT_TOTALS`:

```python
    (LedgerRow, "ability_id"),  # a spell's identity, not a duration
```

- [ ] **Step 9: Prove the tests bite**

Three mutations. Change `!= 1` to `< 1` in `_split_title` and confirm the twice-named test fails. Change `finding.ability_id if ability else None` to `finding.ability_id` and confirm the not-in-title test fails. Change `title=finding.title` to `title=before` and confirm the concatenation invariant fails. Restore each.

- [ ] **Step 10: Run the whole gate**

- [ ] **Step 11: Commit**

Subject: `Cut a finding's title at the ability it names`. Body: an ability sits mid-sentence in a finding, unlike a death card's table cell, so the icon belongs at the words rather than at the start of the row; the cut is refused unless the name appears exactly once, because two occurrences give no way to say which one a reader means.

---

### Task 6: Draw the icon inside the finding's sentence

**Files:**
- Modify: `src/wowperf/adapters/render/_macros.html.j2:9`
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: `LedgerRow.title_before`, `.title_ability`, `.title_after`, `.ability_id` (Task 5).

- [ ] **Step 1: Write the failing tests**

In `tests/adapters/render/test_html_sections.py`. `FakeIcons` already exists in that file from the previous slice; reuse it.

```python
def test_an_icon_is_drawn_at_the_ability_inside_a_findings_sentence() -> None:
    row = a_ledger_row(
        title="Uglymage never cast Ice Block",
        title_before="Uglymage never cast ",
        title_ability="Ice Block",
        ability_id=45438,
    )
    html = render(a_report(interrupts=(row,)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    assert 'Uglymage never cast <span class="icon i-45438" aria-hidden="true"></span>Ice Block' in html


def test_a_finding_whose_ability_has_no_icon_still_reads_as_a_sentence() -> None:
    row = a_ledger_row(
        title="Uglymage never cast Ice Block",
        title_before="Uglymage never cast ",
        title_ability="Ice Block",
        ability_id=45438,
    )
    html = render(a_report(interrupts=(row,)), icons=FakeIcons({}))
    assert "Uglymage never cast Ice Block" in html
    assert 'class="icon' not in html


def test_a_summary_pointer_names_the_finding_without_an_icon() -> None:
    # A pointer is a one-line cross-reference into another section; the icon
    # belongs at the finding itself, not at every mention of it.
    row = a_ledger_row(
        title="Uglymage never cast Ice Block",
        title_before="Uglymage never cast ",
        title_ability="Ice Block",
        ability_id=45438,
    )
    html = render(a_report(summary_pointers=(row,)),
                  icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}))
    assert "pointer-title" in html
    assert 'class="icon i-45438"' not in html.split('class="pointer-title"')[1][:200]
```

`a_ledger_row(**changes)` is a local helper building a `LedgerRow` with defaults; add it following `a_card(**changes)` at line 427 if the file has none.

- [ ] **Step 2: Run them and watch them fail**

- [ ] **Step 3: Change the card macro**

In `src/wowperf/adapters/render/_macros.html.j2`, replace line 9:

```jinja
    <h3>{{ row.title }}</h3>
```

with:

```jinja
    <h3>{{ row.title_before }}{% if row.ability_id in icons_by_id %}<span
      class="icon i-{{ row.ability_id }}" aria-hidden="true"></span>{% endif %}{{ row.title_ability }}{{ row.title_after }}</h3>
```

Leave line 27, `<span class="pointer-title">{{ row.title }}</span>`, exactly as it is.

Jinja whitespace control is unforgiving here — the span must not introduce a line break inside the sentence. **Render the output and read it** rather than predicting it.

- [ ] **Step 4: Run them and watch them pass**

- [ ] **Step 5: Confirm the golden file has not moved**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py -q
/mingw64/bin/git diff tests/adapters/render/golden/minimal.html
```

That diff must be **empty**. A page rendered with no `IconSource` resolves no ids, so every `{% if %}` takes its false branch and the markup is unchanged. If the diff is not empty, the whitespace in Step 3 is wrong — fix the template, never the golden file. If you cannot make it empty, report BLOCKED with the diff.

- [ ] **Step 6: Prove the tests bite**

Move the span outside its `{% if %}`, run the no-icon test, confirm it fails, restore. Then change the card macro's `row.ability_id` to a row's other field and confirm the first test fails. Restore.

- [ ] **Step 7: Run the whole gate**

- [ ] **Step 8: Commit**

Subject: `Draw a spell's icon inside the sentence of the finding that names it`. Body: an icon leading a column makes rows without one sit ragged against their siblings, which an icon inside a sentence cannot do; the compact summary pointer keeps its plain title because a one-line cross-reference should not sprout art.

---

### Task 7: Reach every finding row on the page

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (add `all_ledger_rows` at the end)
- Modify: `src/wowperf/adapters/render/html.py:33-53`
- Modify: `tests/domain/report/test_ledger.py` (point the Task 5 invariant at the helper)
- Test: `tests/domain/report/test_model.py`, `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: `LedgerRow.ability_id` (Task 5).
- Produces: `all_ledger_rows(report: Report) -> Iterator[LedgerRow]`.

Findings live in nine places: seven on `Report` and two nested inside each `PlayerCard`. `_icon_uris` reaches none of them today, and an id that arrives without a CSS rule draws nothing and raises nothing.

- [ ] **Step 1: Write the failing guard test**

In `tests/domain/report/test_model.py`:

```python
def test_all_ledger_rows_reaches_every_field_that_holds_them() -> None:
    """A tenth section that holds findings must be reached, or its icons vanish.

    The fields are discovered by introspection rather than listed here, so
    adding one and forgetting to name it in `all_ledger_rows` fails this test
    instead of silently losing that section's icons.
    """
    expected: set[str] = set()
    report_changes: dict[str, object] = {}
    for name, field in Report.model_fields.items():
        if field.annotation == tuple[LedgerRow, ...]:
            report_changes[name] = (a_ledger_row(finding_id=f"report.{name}"),)
            expected.add(f"report.{name}")
    card_changes: dict[str, object] = {}
    for name, field in PlayerCard.model_fields.items():
        if field.annotation == tuple[LedgerRow, ...]:
            card_changes[name] = (a_ledger_row(finding_id=f"card.{name}"),)
            expected.add(f"card.{name}")

    assert expected, "introspection found no row-bearing fields, so this proves nothing"
    report = a_report().model_copy(
        update={**report_changes, "players": (a_player_card().model_copy(update=card_changes),)}
    )
    assert {row.finding_id for row in all_ledger_rows(report)} == expected
```

`a_report()`, `a_player_card()` and `a_ledger_row(**changes)` are local helpers; reuse whatever that file already has and add the missing ones minimally.

- [ ] **Step 2: Run it and watch it fail**

Expected: `ImportError: cannot import name 'all_ledger_rows'`.

- [ ] **Step 3: Write the helper**

At the end of `src/wowperf/domain/report/model.py`:

```python
def all_ledger_rows(report: Report) -> Iterator[LedgerRow]:
    """Every finding row on the page, including the two nested in each player card.

    One place names the sections, so a caller cannot reach eight of the nine and
    lose the ninth in silence: a row whose ability reaches the page without
    reaching the icon resolver draws nothing and reports nothing.
    """
    yield from report.ledger_decomposition
    yield from report.summary_pointers
    yield from report.route_rows
    yield from report.death_rows
    yield from report.interrupts
    yield from report.group_rows
    yield from report.observations
    for player in report.players:
        yield from player.damage_rows
        yield from player.spell_and_talent_rows
```

Add `from collections.abc import Iterator` to that module's imports if it is not already there. This iterates frozen models and performs no I/O.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Point the Task 5 invariant at the helper**

In `tests/domain/report/test_ledger.py`, change `test_every_row_of_a_real_report_can_be_reassembled_from_its_parts` to iterate `all_ledger_rows(report)` as written in Task 5 Step 7, replacing the by-hand field walk.

- [ ] **Step 6: Write the failing test for the resolver**

In `tests/adapters/render/test_html_sections.py`:

```python
def test_an_ability_named_only_by_a_finding_is_embedded() -> None:
    row = a_ledger_row(title="Uglymage never cast Ice Block",
                       title_before="Uglymage never cast ",
                       title_ability="Ice Block", ability_id=45438)
    icons = FakeIcons({45438: "data:image/jpeg;base64,AAA"})
    html = render(a_report(interrupts=(row,)), icons=icons)
    assert ".i-45438 { background-image: url(data:image/jpeg;base64,AAA); }" in html


def test_an_ability_named_only_inside_a_player_card_is_embedded() -> None:
    # spell_and_talent_rows is nested one level down, which is where the
    # comparison findings land.
    row = a_ledger_row(title="Emberkin never cast Ice Nova",
                       title_before="Emberkin never cast ",
                       title_ability="Ice Nova", ability_id=157997)
    card = a_player_card().model_copy(update={"spell_and_talent_rows": (row,)})
    html = render(a_report(players=(card,)),
                  icons=FakeIcons({157997: "data:image/jpeg;base64,BBB"}))
    assert ".i-157997 { background-image: url(data:image/jpeg;base64,BBB); }" in html
```

- [ ] **Step 7: Run them and watch them fail**

Expected: the CSS rule is absent, because `_icon_uris` walks only `report.deaths`.

- [ ] **Step 8: Have `_icon_uris` consume the helper**

In `src/wowperf/adapters/render/html.py`, inside `_icon_uris`, after the `for card in report.deaths:` block, add:

```python
    for row in all_ledger_rows(report):
        if row.ability_id is None or row.ability_id in asked:
            continue
        asked.add(row.ability_id)
        uri = icons.data_uri(row.ability_id)
        if uri is not None:
            resolved[row.ability_id] = uri
```

Import `all_ledger_rows` from `wowperf.domain.report.model`.

- [ ] **Step 9: Run them and watch them pass**

- [ ] **Step 10: Prove the tests bite**

Remove one `yield from` line from `all_ledger_rows`, run the guard test, confirm it fails naming the missing field, restore. Then remove the `for row in all_ledger_rows(report):` block from `_icon_uris`, run both resolver tests, confirm they fail, restore.

- [ ] **Step 11: Confirm the golden file has not moved**

```bash
/mingw64/bin/git diff tests/adapters/render/golden/minimal.html
```

Empty.

- [ ] **Step 12: Run the whole gate**

- [ ] **Step 13: Commit**

Subject: `Resolve an icon for every finding row, wherever the page keeps it`. Body: findings sit in nine fields across two models and half the new icons are in the two nested inside a player card; an id that reaches the view model without reaching the resolver produces no CSS rule, so it draws nothing and raises nothing, and the introspecting test is what stops a tenth section repeating that quietly.

---

### Task 8: Give the resolver the reference reports' icon names

**Files:**
- Modify: `src/wowperf/adapters/wcl/repository.py:331`
- Modify: `src/wowperf/domain/comparison/sample.py:46-61`
- Modify: `src/wowperf/cli.py:401` and the `build_icons` definition
- Test: `tests/adapters/wcl/test_repository.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `LoadedRun.ability_icons`, `BlizzardIcons` (both shipped).
- Produces: `ParseMember.ability_icons: tuple[tuple[int, str], ...]`; `build_icons(loaded, parse_sample, cache_dir)`.

A comparison finding names an ability our player never cast, so it is absent from our own report's dictionary and present only in the reference's. Without this task, Task 4's ids resolve to nothing.

- [ ] **Step 1: Write the failing test for the parse-profile load**

In `tests/adapters/wcl/test_repository.py`. `recording_repository`'s first parameter is `calls: list[str]`, required and positional, and it takes an `abilities_rows` keyword. `load_parse_reference(report_code, fight_id) -> tuple[LoadedRun, bool]` returns a tuple — unlike `load`, which returns a bare `LoadedRun` — so the unpacking below is correct. The idiom to mirror is `test_a_speed_reference_fetches_only_the_streams_the_speed_comparisons_read` at line 314.

```python
def test_a_parse_reference_carries_each_abilitys_icon_file_name(tmp_path: Path) -> None:
    repository = recording_repository(
        [], tmp_path,
        abilities_rows=[{"gameID": 157997, "name": "Ice Nova", "icon": "spell_x.jpg"}],
    )
    loaded, _ = repository.load_parse_reference("abc123", None)
    assert loaded.ability_icon_map[157997] == "spell_x.jpg"
```

- [ ] **Step 2: Run it and watch it fail**

Expected: `KeyError: 157997`.

- [ ] **Step 3: Thread the icons into the parse-profile run**

In `src/wowperf/adapters/wcl/repository.py`, line 331 reads:

```python
            loaded = LoadedRun(run=run, casts=build_casts(cast_events, run, ability_names))
```

Change it to:

```python
            loaded = LoadedRun(
                run=run,
                casts=build_casts(cast_events, run, ability_names),
                ability_icons=ability_icons,
            )
```

`ability_icons` is already computed at line 308, before the profile branch.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Carry the names onto the member**

In `src/wowperf/domain/comparison/sample.py`, inside `ParseMember`, after `auras`:

```python
    # Icon file names by ability game id, from this reference's own report. A
    # comparison names abilities our player never cast, which are therefore in
    # no dictionary but this one.
    ability_icons: tuple[tuple[int, str], ...] = ()
```

In `src/wowperf/cli.py:401`:

```python
            ParseMember(
                row=parse_row,
                run=theirs.run,
                casts=theirs.casts,
                ability_icons=theirs.ability_icons,
            )
```

- [ ] **Step 6: Write the failing test for the merge**

**Do not try to write this end to end through `run_analyze`.** `build_analyze_transport` answers the `Abilities` operation from a single shared `abilities_payload` for every report code, so our report and the parse reference always receive the *same* dictionary. There is no id present in one and absent from the other, which is precisely the condition this task exists to handle. Making the transport answer per code — an `abilities_by_code` parameter mirroring its existing `aura_rows_by_code` — is a bigger change to a 200-line fixture than the behaviour warrants.

Test `build_icons` directly instead. In `tests/test_cli.py`:

```python
def test_the_resolver_knows_an_icon_named_only_by_a_reference_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A comparison finding names an ability our player never cast, so its file
    name is in the reference's dictionary and in no other."""

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        assert url.endswith("/spell_ice_nova.jpg")
        return httpx.Response(
            200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8fake"
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    ours = LoadedRun(run=a_minimal_run())
    theirs = ParseMember(
        row=_parse_row_model(),
        run=a_minimal_run(),
        ability_icons=((157997, "spell_ice_nova.jpg"),),
    )
    icons = build_icons(ours, ParseSample(members=(theirs,)), tmp_path)

    assert icons is not None  # build_icons returns None only when the store fails
    assert icons.data_uri(157997) is not None


def test_our_own_dictionary_wins_where_both_name_an_ability(tmp_path: Path) -> None:
    ours = LoadedRun(run=a_minimal_run(), ability_icons=((1, "ours.jpg"),))
    theirs = ParseMember(
        row=_parse_row_model(), run=a_minimal_run(), ability_icons=((1, "theirs.jpg"),)
    )
    asked: list[str] = []

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        asked.append(url)
        return httpx.Response(
            200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8fake"
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "get", fake_get)
        resolver = build_icons(ours, ParseSample(members=(theirs,)), tmp_path)
        assert resolver is not None
        resolver.data_uri(1)

    assert asked == ["https://render.worldofwarcraft.com/eu/icons/36/ours.jpg"]
```

`a_minimal_run()` and `_parse_row_model()` are whatever that file already uses to build a bare `Run` and a `ParseRow`; `test_cli.py` already imports `ParseMember`, `ParseSample` and `ParseRow`. Build the smallest ones that construct, and add a local helper if none exists — a `ParseMember` needs only `row` and `run`.

- [ ] **Step 7: Merge the maps in the CLI**

`build_icons` currently reads `def build_icons(loaded: LoadedRun, cache_dir: Path) -> BlizzardIcons | None:` — it returns `None` when the store cannot be created, and its `fetch` closure carries a `try/except httpx.HTTPError` returning a status-`0` sentinel. **Leave both of those exactly as they are.** Change only the signature and the map it hands to `BlizzardIcons`:

```python
def build_icons(
    loaded: LoadedRun, parse_sample: ParseSample | None, cache_dir: Path
) -> BlizzardIcons | None:
```

Extend its docstring with:

```
    A comparison names an ability our player never cast, so that ability's file
    name is in the reference's own dictionary and in no other. Ours is overlaid
    last: where both name an id they name the same file, so the order settles
    determinism rather than correctness.
```

Then replace the final `return` with:

```python
    names: dict[int, str] = {}
    for member in parse_sample.members if parse_sample else ():
        names.update(member.ability_icons)
    names.update(loaded.ability_icon_map)
    return BlizzardIcons(names, store, fetch)
```

`store` is the local the existing `try/except OSError` block already binds. At the call site, `icons=build_icons(loaded, cache_dir)` becomes `icons=build_icons(loaded, parse_sample, cache_dir)` — `parse_sample` is already in scope there, since `build_report` is handed it two lines above.

- [ ] **Step 8: Run it and watch it pass**

- [ ] **Step 9: Prove the tests bite**

Remove `ability_icons=ability_icons` from the parse-profile `LoadedRun`, run the repository test, confirm failure, restore. Remove the `for member in ...` loop from `build_icons`, run the CLI test, confirm failure, restore.

- [ ] **Step 10: Run the whole gate**

- [ ] **Step 11: Commit**

Subject: `Give the icon resolver the reference reports' ability dictionaries`. Body: a comparison finding names an ability our player never cast, so its icon file name exists only in the reference's own dictionary, which the load already fetched and then dropped at the sample boundary; our names are overlaid last so a shared id resolves the same way every run.

---

### Task 9: Verify against a real report

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Run the whole gate**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy
```

- [ ] **Step 2: Render the real report, once**

```bash
export PATH="$HOME/.local/bin:$PATH"
set -a && . <(iconv -f UTF-16 -t UTF-8 .env | tr -d '\r') 2>/dev/null && set +a
uv run wowperf analyze 6Kx1P9GbNXrcLdHa --fight 36 --out out
```

Run it **once**. The Warcraft Logs cache is warm for this report and it cost 1.00 point last time, out of 3600 an hour. Never echo, `cat` or `printenv` any credential.

- [ ] **Step 3: Measure, and print rather than assert**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run python - <<'PY'
import pathlib, re
t = pathlib.Path("out/6Kx1P9GbNXrcLdHa-36.html").read_text(encoding="utf-8")
print("bytes:", len(t))
print("distinct icons embedded:", t.count("background-image"))
print("icon spans drawn:", t.count('class="icon i-'))
print("external references:", len(re.findall(r"url\((?:http|//)", t)))
for sid, body in re.findall(r'<section class="panel"[^>]*id="([^"]+)"(.*?)</section>', t, re.S):
    print(f"  {sid:22} {body.count('class=\"icon i-'):>5}")
PY
```

Report every number verbatim. Do not assert them — a size assertion fails on every unrelated change to the page.

The 2026-09-09 baseline, before this work: 234,571 bytes, 53 distinct icons, 189 spans, 0 external references, and every span inside `tab-deaths`. Expect the per-section counts to become non-zero for `tab-summary`, `tab-interrupts` and `tab-players`; expect external references to stay **0**.

- [ ] **Step 4: Run it a second time and confirm the store is quiet**

Re-run Step 2 and Step 3. Report whether the icon count held and whether `cache/icons` gained any file. A second run should make no image requests.

- [ ] **Step 5: Check the sentences by eye**

Serve `out/` and read a few finding cards:

```bash
export PATH="$HOME/.local/bin:$PATH"; python -m http.server 8765 --directory out
```

Confirm three things and report them: an icon sits immediately before the spell's words inside the sentence, with no line break; a finding whose ability resolved no icon reads as an ordinary sentence with no gap; and a summary pointer names its finding with no icon.

Screenshots time out past the first viewport on this machine — drive the DOM with `javascript_tool` and read computed geometry instead.

- [ ] **Step 6: Commit anything the measurements changed**

If Steps 3-5 found nothing, there is nothing to commit and this task ends with the numbers reported. If they found a defect, fix it under TDD and commit that fix; do not fold unrelated changes in.

---

## Self-Review

**Spec coverage.** §3's twelve sites: Tasks 1 (interrupts), 2 (defensives ×2, throughput, deaths), 3 (players), 4 (spells ×4, uptime ×2). §4's exclusions are respected by omission — no task touches `consumables.py:202`, the detail paragraph, the evidence bullets, or the speed comparison. §5's domain change: Task 1. §6's split rule and its exactly-once refusal: Task 5, one test per case. §7's `LedgerRow` fields, the retained `title`, the concatenation invariant and the allowlist entry: Task 5. §8's template and the untouched pointer macro: Task 6. §9's two maps: Task 8. §10's nine row-bearing fields and the introspecting guard: Task 7. §11's tests: throughout. §12's invariants: the golden diff is checked explicitly in Tasks 6 and 7. §13's measurements: Task 9.

**One spec point deliberately given no task.** §14's deferrals — sequential fetching, the Defensives ragged edge, the `mkdir` guard, tooltips and reference-data staleness — are out of scope by decision and no task may drift into them.

**Ordering.** Tasks 1 through 4 are independent of each other except that all need Task 1's fields. Task 5 needs 1-4 to have something to cut, though it can be written against 1 alone. Task 6 needs 5. Task 7 needs 5. Task 8 is independent of 5-7 but is what makes Task 4's ids resolve. Task 9 needs everything.

**Type consistency.** `Finding.ability_id: int | None` and `ability_name: str` (Task 1) are the names every populating task uses. `_damage_outliers`' widened tuple (Task 3) is the only signature change, and mypy checks it. `LedgerRow`'s four fields (Task 5) are the names Tasks 6 and 7 render and walk. `all_ledger_rows(report) -> Iterator[LedgerRow]` (Task 7) is consumed in Task 7 Step 8 and retrofitted into Task 5's invariant at Task 7 Step 5. `ParseMember.ability_icons` and `build_icons(loaded, parse_sample, cache_dir)` (Task 8) match their call sites.

**Three risks worth naming.**

Task 3 widens a tuple that mypy checks, so an incomplete edit fails the gate rather than passing quietly — the good direction.

Task 5's `test_every_row_of_a_real_report_can_be_reassembled_from_its_parts` is written twice: by hand in Task 5, then against `all_ledger_rows` in Task 7 Step 5. That is deliberate, so Task 5 does not depend on a helper it does not create — but Task 7 must actually perform the swap, or the invariant keeps checking a hand-written subset of the rows forever.

Task 8's merge cannot be tested end to end through `run_analyze`. `build_analyze_transport` answers `Abilities` from one shared payload for every report code, so our dictionary and the reference's are always identical and the condition the task exists for cannot be reproduced. Task 8 Step 6 therefore tests `build_icons` directly and says so; an implementer who tries the end-to-end route will burn time before discovering this.
