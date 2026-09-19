# Defensives at a Hit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A death card stops saying a defensive was pressed when the buff had already faded, by splitting `pressed` into `held`, `faded`, and an honest `pressed` meaning the page cannot say.

**Architecture:** The aura table already knows. `resolve_aura` maps a cast id to its aura by id and then by name; `band_holding` returns the band covering a moment. The raid path gains a roster-wide aura fetch so the answer exists for every player rather than one, and `state_of` consults it where it currently returns `PRESSED`.

**Tech Stack:** Python 3.12, `uv`, pytest, frozen pydantic-style models (`domain.base.Frozen`), Jinja2.

**Spec:** `docs/plans/2026-09-20-defensives-at-a-hit-design.md`

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches the network, disk or a template. The fetch in Task 1 is adapter/CLI work.
- **Every finding carries a confidence badge.** `FindingFact.confidence` left unset means **measured**, not unknown.
- **The report is one HTML file.** No stylesheet link, no `@import`, no remote `src`, exactly one inline script. The only outbound addresses are ability icons on `wow.zamimg.com`.
- **Never put a real character name in `tests/`.** Sanctioned: `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. Larger rosters index players (`Raider 0..19`).
- **The twenty players on report `cW38jmwdnZfbHVL4` are real people.** Refer to them by class, spec, role or index in code, tests, commits and documents.
- **Master design §5.5:** the page describes damage and never assigns intent. Deaths are the single exception.
- **An unresolved ability is never `faded`.** Silence, not a false accusation. This is the design's load-bearing rule and every task inherits it.
- **Never use `--no-verify`**, `--no-hooks`, or `--no-pre-commit-hook`.
- **Commit messages are plain ASCII**, imperative, no `feat:`/`fix:` prefix, body explains why, ending with a blank line then `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **`uv` is the only toolchain.** Gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy`, each its own command; mypy takes no paths.
- **Call git as `/mingw64/bin/git`.** A bare `git` is rewritten by the user-level RTK hook and refused by the worktree guard.
- **Every code file starts with two `# ABOUTME: ` comment lines.**

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/cli.py` | Modify: gains `load_encounter_with_auras`, the raid analogue of `load_run_with_auras`, and calls it |
| `src/wowperf/domain/analysis/recap.py` | Modify: gains `HELD`, `FADED`, a resolution helper; `state_of` and `availability_at` consult the aura table |
| `src/wowperf/domain/report/deaths.py` | Modify: supplies the dying player's auras, and gives the two new states their prose |
| `src/wowperf/adapters/render/report.css.j2` | Modify: the two new states take a colour |
| `.claude/skills/wcl-api/SKILL.md` | Modify: the dated quota reading for the roster aura fetch |

---

### Task 1: Fetch the roster's auras on the raid path

The raid path fetches aura tables only for comparable parse subjects — measured at one table for a twenty-player report. Everything below is silent without this.

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `_auras(runs, code, fight_id, actor_id) -> PlayerAuras | None` (exists, `cli.py:1070`); `LoadedEncounter.auras: tuple[PlayerAuras, ...]` (exists, `encounter.py:92`, never filled on this path); `LoadedEncounter.players`.
- Produces: `load_encounter_with_auras(runs, code, fight_id, loaded) -> LoadedEncounter`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`. Read the file's existing fake repository first and reuse it rather than writing a new one; the names below are the shape, not necessarily the spelling.

```python
def test_every_roster_player_gets_their_aura_table() -> None:
    """One table per player, or the split below is silent for nineteen in twenty."""
    loaded = a_loaded_encounter(players=3)
    runs = a_repository_returning_auras_for_every_actor()

    with_auras = load_encounter_with_auras(runs, "ABC", 1, loaded)

    assert len(with_auras.auras) == 3
    assert {one.actor_id for one in with_auras.auras} == {1, 2, 3}


def test_one_failed_aura_fetch_does_not_cost_the_others() -> None:
    """A report already paid for is never discarded over one player's table."""
    loaded = a_loaded_encounter(players=3)
    runs = a_repository_failing_auras_for(actor_id=2)

    with_auras = load_encounter_with_auras(runs, "ABC", 1, loaded)

    assert {one.actor_id for one in with_auras.auras} == {1, 3}
```

- [ ] **Step 2: Run them and watch them fail**

```bash
uv run pytest tests/test_cli.py -k aura -v
```

Expected: FAIL with `NameError` / `ImportError` on `load_encounter_with_auras`.

- [ ] **Step 3: Write it**

In `src/wowperf/cli.py`, directly beneath `load_run_with_auras`, whose shape this follows:

```python
def load_encounter_with_auras(
    runs: WclRunRepository, code: str, fight_id: int, loaded: LoadedEncounter
) -> LoadedEncounter:
    """The fight, with every roster player's buff bands attached.

    One `AuraTable` query per player, about 1.06 points each, so about 21 for a
    twenty-player fight against an hourly budget of 3600. The raid path fetched
    these only for comparable parse subjects, which measured at one table for a
    twenty-player report -- and a held-or-faded answer drawn from bands is
    silent for every player without one.

    A player whose fetch fails simply has no bands, and the states that read
    them say `pressed` rather than guessing. `_auras` already swallows the
    failure for the same reason on the Mythic+ side: a report that has been
    fetched and paid for is not discarded over one player's table.
    """
    fetched = tuple(
        one
        for one in (
            _auras(runs, code, fight_id, player.actor_id) for player in loaded.players
        )
        if one is not None
    )
    return loaded.model_copy(update={"auras": fetched})
```

- [ ] **Step 4: Call it from the raid command**

Find the call site:

```bash
grep -n "build_raid_report\|load_encounter" src/wowperf/cli.py
```

**Read that function before editing it** — its name and the variable holding the encounter are deliberately not guessed here, because this plan's predecessor shipped eight defects from exactly that kind of guess. Insert the fetch immediately after the encounter is loaded and before it is analysed, so every consumer sees one object:

```python
    loaded = load_encounter_with_auras(ours, code, fight_id, loaded)
```

The repository variable is `ours` in the parse-subject code at `cli.py:1037`; confirm it is the same one in scope here rather than assuming.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_cli.py -k aura -v
```

Expected: PASS.

- [ ] **Step 6: Run the gate**

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

Subject: `Fetch every raid player's aura table, not just the compared ones`. The body explains that the split in the next task reads bands, and bands exist only for players whose table was fetched — one for a twenty-player report before this.

---

### Task 2: `state_of` answers held or faded

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py`
- Test: `tests/domain/analysis/test_recap_availability.py`

**Interfaces:**
- Consumes: `resolve_aura(auras, ability_id, ability_name) -> Aura | None` and `band_holding(aura, start_ms, end_ms, at_ms) -> tuple[int, int] | None`, both in `src/wowperf/domain/report/cover.py`.
- Produces: module constants `HELD = "held"` and `FADED = "faded"`; `state_of(..., auras: PlayerAuras | None = None, window: tuple[int, int] | None = None)` — the signature keeps every existing parameter and default, so callers that pass neither are unchanged.

**Note on the import direction.** `analysis/recap.py` importing from `report/cover.py` is the wrong way round if `report` is meant to sit above `analysis`. **Check which way the dependency already runs before writing the import.** If `report` already imports `analysis`, move `resolve_aura` and `band_holding` into the domain layer proper (e.g. `domain/auras.py`, beside the models they read) and leave re-exports behind, rather than creating a cycle. Report which you found and what you did.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_defensive_still_up_at_the_death_reads_held() -> None:
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=1000, end_ms=9000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000),
    )

    assert state.state == HELD


def test_a_defensive_that_lapsed_before_the_blow_reads_faded() -> None:
    """The overstatement this exists to correct: pressed, and gone by then."""
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=1000, end_ms=3000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000),
    )

    assert state.state == FADED


def test_an_ability_with_no_aura_of_its_own_stays_pressed() -> None:
    """Silence, never an accusation: an unresolved ability is not faded."""
    auras = _auras_with_band(ability_id=99999, name="Something Else", start_ms=0, end_ms=9000)

    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=auras, window=(0, 10_000),
    )

    assert state.state == PRESSED


def test_a_player_with_no_aura_table_stays_pressed() -> None:
    state = state_of(
        _presses(22812, at_ms=2000), "Barkskin", 45.0, 1, death_ms=5000,
        ability_id=22812, auras=None, window=(0, 10_000),
    )

    assert state.state == PRESSED


def test_the_name_fallback_resolves_a_buff_whose_id_differs_from_its_cast() -> None:
    """Greater Invisibility casts as 110959 and buffs as 110960."""
    auras = _auras_with_band(
        ability_id=110960, name="Greater Invisibility", start_ms=1000, end_ms=9000
    )

    state = state_of(
        _presses(110959, at_ms=2000), "Greater Invisibility", 90.0, 1, death_ms=5000,
        ability_id=110959, auras=auras, window=(0, 10_000),
    )

    assert state.state == HELD
```

Write `_auras_with_band` and `_presses` as local helpers building `PlayerAuras`/`Aura`/`AuraBand` and `CastEvent`. Read those models for their real field names before writing the helpers.

- [ ] **Step 2: Run them and watch them fail**

```bash
uv run pytest tests/domain/analysis/test_recap_availability.py -k "held or faded or fallback" -v
```

Expected: FAIL — `HELD` is not defined, and `state_of` takes no `auras`.

- [ ] **Step 3: Add the constants and the resolver**

Beside `PRESSED`/`READY`/`COOLDOWN`/`UNSEEN` in `recap.py`:

```python
HELD = "held"
FADED = "faded"
```

And a module-level helper:

```python
def _press_state(
    auras: PlayerAuras | None,
    window: tuple[int, int] | None,
    ability_id: int | None,
    name: str,
    death_ms: int,
) -> str:
    """Whether a press was still up when the blow landed, or PRESSED if unknowable.

    Three ways to be unknowable, and each one says `pressed` rather than
    guessing: no aura table for this player, no window to clip bands to, and an
    ability whose aura cannot be resolved -- which covers both an id the table
    does not carry under any name and an ability that raises no aura at all.
    The damage stream cannot tell those two apart; neither can this, and neither
    needs to, because both answer the same way.

    A resolved aura with no band over the death is FADED. That is a reading and
    not an absence: the table lists every interval the aura was up, so a death
    outside all of them is the table saying it was down.
    """
    if auras is None or window is None or ability_id is None:
        return PRESSED
    aura = resolve_aura(auras, ability_id, name)
    if aura is None:
        return PRESSED
    start_ms, end_ms = window
    return HELD if band_holding(aura, start_ms, end_ms, death_ms) else FADED
```

- [ ] **Step 4: Consult it where PRESSED is returned**

`state_of` currently returns `PRESSED` unconditionally at its `if in_run_up:` branch. Add the two keyword parameters (`auras: PlayerAuras | None = None`, `window: tuple[int, int] | None = None`) and change only that branch's `state=`:

```python
    if in_run_up:
        return AbilityState(
            name=name,
            state=_press_state(auras, window, ability_id, name, death_ms),
            owner_id=owner_id, ability_id=ability_id,
            seconds=(death_ms - max(in_run_up)) / 1000,
        )
```

Extend `state_of`'s docstring: it says "Which of the four states" and there are now six, of which `pressed` has become the explicit unknown.

- [ ] **Step 5: Run the tests, then the gate**

```bash
uv run pytest tests/domain/analysis/test_recap_availability.py -v
```

```bash
uv run pytest
```

Expected: every pre-existing availability test still passes untouched — the new parameters default to `None`, so nothing that does not pass them changes.

- [ ] **Step 6: Commit**

Subject: `Say whether a pressed defensive was still up when the blow landed`.

---

### Task 3: `availability_at` passes the player's auras through

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py`
- Test: `tests/domain/analysis/test_recap_availability.py`

**Interfaces:**
- Consumes: Task 2's `state_of(..., auras=, window=)`.
- Produces: `availability_at(..., auras: PlayerAuras | None = None, window: tuple[int, int] | None = None) -> AvailabilityAt`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_dying_players_own_defensives_are_judged_against_their_bands() -> None:
    auras = _auras_with_band(ability_id=22812, name="Barkskin", start_ms=0, end_ms=3000)

    at = availability_at(
        _roster(), _presses(22812, at_ms=2000), _death(at_ms=5000),
        _defensives_with_barkskin(), Consumables(), Externals(),
        visible_from_ms=0, auras=auras, window=(0, 10_000),
    )

    assert at.own is not None
    assert [one.state for one in at.own if one.name == "Barkskin"] == [FADED]
```

- [ ] **Step 2: Run it and watch it fail**

```bash
uv run pytest tests/domain/analysis/test_recap_availability.py -k bands -v
```

Expected: FAIL — `availability_at` takes no `auras`.

- [ ] **Step 3: Thread them to the own-abilities branch only**

Add the two keyword parameters, and pass them in the `own = ...` comprehension. **Externals keep `pressed`**: an external's aura sits on the dying player but is resolved against the *caster's* ability id, and `resolve_aura` is scoped to one player's own `on_self` list, so a teammate's cooldown is not answerable this way without a second table. Say so in the docstring rather than leaving it to be rediscovered.

```python
            own = tuple(
                state_of(
                    presses_of(death.actor_id, (ability.ability_id,)),
                    ability.name, ability.cooldown_seconds, ability.charges, death_ms,
                    ability_id=ability.ability_id,
                    auras=auras, window=window,
                )
                for ability in known
            )
```

- [ ] **Step 4: Run the tests and the gate**

```bash
uv run pytest tests/domain/analysis/ -v
```

```bash
uv run pytest
```

- [ ] **Step 5: Commit**

Subject: `Judge a dying player's own defensives against their aura bands`.

---

### Task 4: The death card supplies the auras and names the two states

**Files:**
- Modify: `src/wowperf/domain/report/deaths.py`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_raid_html_invariants.py`
- Modify: `tests/adapters/render/golden/raid.html`, `golden/minimal.html`, `golden/progression.html`

**Interfaces:**
- Consumes: Task 3's `availability_at(..., auras=, window=)`; `loaded.auras_by_actor` (exists).
- Produces: a rendered availability row reading `held` or `faded`.

- [ ] **Step 1: Write the failing test**

Read the file's existing death-page fixture builder first and reuse it; the helper names below are the shape, not the spelling. Build through the real pipeline rather than hand-building an `AbilityState`, or the test covers none of the wiring this task adds.

```python
def test_a_defensive_that_lapsed_says_so_on_the_card() -> None:
    """The overstatement this branch exists to correct, as a reader meets it."""
    html = a_death_page_where(
        pressed_at_ms=2000, band=(1000, 3000), death_at_ms=5000, ability="Barkskin"
    )

    assert "over by then" in html
    assert 'class="state faded"' in html


def test_a_defensive_still_covering_says_that_instead() -> None:
    html = a_death_page_where(
        pressed_at_ms=2000, band=(1000, 9000), death_at_ms=5000, ability="Barkskin"
    )

    assert "still up" in html
    assert "over by then" not in html
```

- [ ] **Step 2: Run it and watch it fail**

```bash
uv run pytest tests/adapters/render/test_raid_html_invariants.py -k "lapsed or covering" -v
```

Expected: FAIL — the page says `pressed` for both, so neither string is present.

- [ ] **Step 3: Supply the auras at the call site**

`deaths.py:351` calls `availability_at`. The variable `auras = loaded.auras_by_actor.get(death.actor_id)` is **already in scope a few lines above** — read the surrounding function and reuse it rather than fetching it twice. The window is the fight's own start and end; read how `start_ms` is derived there and use the same origin.

- [ ] **Step 4: Give the two states their prose**

In `_availability_row`, the `state == PRESSED` branch currently produces `f"{state.seconds:.1f} s before death"`. Add two branches beside it. The wording must not praise or blame: `held` means the aura was up, **not** that it was enough, and `faded` is a statement about timing, not effort.

```python
    if state.state == HELD:
        detail = f"{state.seconds:.1f} s before death, still up"
    elif state.state == FADED:
        detail = f"{state.seconds:.1f} s before death, over by then"
    elif state.state == PRESSED:
        detail = f"{state.seconds:.1f} s before death"
```

- [ ] **Step 5: Give them a colour**

`AvailabilityRow.state` is already the CSS hook. Add rules for the two new values in `report.css.j2`, reusing existing variables rather than inventing a token. **`report.css.j2` is shared by all three report types**, so `golden/minimal.html` and `golden/progression.html` will also change; those diffs must be CSS-only.

- [ ] **Step 6: Regenerate the goldens and read the diff**

```bash
uv run pytest tests/adapters/render/ --golden-update -q
```

```bash
/mingw64/bin/git diff tests/adapters/render/golden/
```

**Read it.** On the previous branch this exact habit caught a rendering bug the whole offline suite missed. Say in the commit what changed.

- [ ] **Step 7: Run the gate and commit**

Subject: `Say on the card whether a pressed defensive was still up`.

---

### Task 5: Live verification and the premise check

Offline fixtures agree with the code that produced them. This is the task that finds what they cannot — and it is the task that decides whether this design was worth building.

**Files:**
- Modify: `.claude/skills/wcl-api/SKILL.md`
- Modify (only if a defect is found): any of the above.

- [ ] **Step 1: Run the canonical wipe**

```bash
uv run wowperf raid 'https://www.warcraftlogs.com/reports/cW38jmwdnZfbHVL4#fight=30' --cache-dir cache --out out
```

- [ ] **Step 2: Count the split**

```bash
uv run python -c "
import re, pathlib, collections
html = pathlib.Path('out/cW38jmwdnZfbHVL4-30.html').read_text(encoding='utf-8')
states = re.findall(r'class=\"state ([a-z]+)\"', html)
print(collections.Counter(states))
"
```

Report the counts for `held`, `faded` and `pressed`. If the class attribute is spelled differently, read one rendered availability row and adjust the pattern rather than guessing.

**The twenty players on this report are real people.** Report counts and roles, never names.

- [ ] **Step 3: Judge the premise**

The design's §7 states the falsifier: **if essentially none come back `faded`, the overstatement this design exists to correct does not occur in practice, and the design was not worth building.**

Record what the numbers actually say. If the answer is that it was not worth building, **say so plainly** — that result is to be recorded, not explained away, and it belongs in the commit body and in a note on the design document.

- [ ] **Step 4: Read the page**

Open a death card with each of the three states and check the prose reads as timing rather than blame, and that `held` does not imply the defensive was sufficient.

- [ ] **Step 5: Record what the aura fetch cost**

The command prints its own quota breakdown. Add a dated line to `.claude/skills/wcl-api/SKILL.md` under the rate-limit section, in the style of the readings already there, naming whether the cache was warm.

- [ ] **Step 6: Commit**

Write the message from what the run actually found. Do not claim a clean run without having read the page.

---

## Self-Review

**Spec coverage.** §1 the three states → Tasks 2 and 4. §3.1 `resolve_aura` + `band_holding` → Task 2. §3.2 why not `buff_ids` → no task; it is a record of a rejected route. §4 the roster fetch and its cost → Tasks 1 and 5. §5 the split and `pressed` as unknown → Task 2. §6 failure modes → Task 2's tests for each unknowable path. §7 testing and the falsifier → Tasks 2-5.

**Type consistency.** `auras` is `PlayerAuras | None` everywhere, never a tuple of ids — the first draft of the design used `tuple[int, ...]` and that spelling must not survive anywhere. `window` is `tuple[int, int] | None`. `HELD` and `FADED` are plain `str` constants matching the existing four, so `AbilityState.state` stays `str` and `AvailabilityRow.state` keeps working as a CSS hook unchanged.

**Two instructions that are load-bearing, not padding.** Task 2 asks which way the `analysis` ↔ `report` dependency already runs before importing `cover.py`; getting that wrong creates an import cycle. Task 4 says the `auras` variable is already in scope at the call site; fetching it a second time would work and would be wrong.
