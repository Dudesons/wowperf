# Not judged before the log -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the death card's defensives and externals, and the "died with a defensive available" findings, from calling an ability ready or available when its base cooldown reaches back before the log's first second.

**Architecture:** One predicate, `window_inside_log`, in `domain/analysis/defensives.py` (the lowest module both callers already import). `recap.py` `state_of` asks it after its COOLDOWN check and answers a new `unjudged` state; `defensives_up_at` asks it before naming an ability; the pooled night finding asks it per pull and leaves an unjudged death out of both counts. The card words the new row with the sentence the Healers group already prints, from one helper.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, pytest. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-29-not-judged-before-the-log-design.md` -- read it whole before Task 1. Its section 2 "The rule" is what every task implements.

## Global Constraints

- The predicate is `moment_ms - seconds * 1000 >= visible_from_ms`, the condition `ready_at` already applies; boundary inclusive (spec section 2).
- The visible origin is a keystone's first pull start and a boss fight's own start -- `window_ms[0]` -- and, for the pooled finding, each pull's own start (spec section 2).
- `state_of` order: `unseen`; `pressed`/`held`/`faded`; `cooldown`; then `unjudged`; else `ready`. Charges, the external's target rule, the held/faded refinement and the `cooldown` bound are unchanged (spec section 2).
- The row: state `unjudged`, detail exactly `not judged, its base cooldown reaches before the {setting}'s first second`, `setting` "run" on a keystone, "fight" on a boss -- the Healers group's sentence, from one helper. Listed, never dropped. No new badge (spec section 3).
- Consumables do not change (spec section 2).
- The heavy-moment finding and the Healers group read `read_cooldown`, not `state_of`: their tests pass unchanged, their output does not move.
- `src/wowperf/domain/` performs no I/O. The report's inline script and the stylesheet are untouched.
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). Players on `cW38jmwdnZfbHVL4`, `6Kx1P9GbNXrcLdHa` and `4vFcVAW1PB2CrD9z` are referred to by class, spec, role or index only -- never by name, slug or raw finding id -- in replies, commits, documents and test messages.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test. New fixture clocks sit on a non-zero origin (`.claude/lessons.md`, 2026-09-29).
- Every new code file starts with two `ABOUTME: ` lines. Comments evergreen.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy` (strict over `tests/` too), `uv run pytest` -- green, output pristine.
- Goldens: **no golden moves.** None of `minimal.html`, `raid.html`, `night.html` holds a `ready` row today (checked 2026-09-29: zero `class="ready"` in each), so none can turn `unjudged`; Task 1 adds a render test instead. If a golden moves, stop and report.

The code and tests in Tasks 1 and 2 were run on 2026-09-29 before this plan was committed: 2754 passed, ruff and mypy clean, no golden moved, and every prove step below turned its named test red. If a test disagrees now, the code was transcribed differently: diff against the plan before changing a test.

## A helper for migrating call sites

Tasks 1 and 2 add a required keyword argument to functions with many test call sites. Write this script **with the file-writing tool** (a shell heredoc eats its backslashes) to your own scratch directory, not the repository, as `migrate_calls.py`:

```python
# ABOUTME: Adds a keyword argument to every call of the named functions that lacks it.
# ABOUTME: Usage: python migrate_calls.py FILE "func=kw=value" ... ; parentheses matched.
import re
import sys
from pathlib import Path

LIMIT = 100


def closing_paren(text: str, open_at: int) -> int:
    depth = 0
    i = open_at
    quote = ""
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced")


def migrate(text: str, func: str, keyword: str, value: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<![\w.]){re.escape(func)}\(")
    count = 0
    position = 0
    while True:
        match = pattern.search(text, position)
        if match is None:
            return text, count
        line_start = text.rfind("\n", 0, match.start()) + 1
        if text[line_start:match.start()].lstrip().startswith("def "):
            position = match.end()
            continue
        open_at = match.end() - 1
        close_at = closing_paren(text, open_at)
        args = text[open_at + 1:close_at]
        if re.search(rf"\b{keyword}\s*=", args):
            position = close_at
            continue
        stripped = args.rstrip()
        tail = args[len(stripped):]
        if stripped.endswith(","):
            addition = f"{stripped} {keyword}={value},{tail}"
        else:
            addition = f"{stripped}, {keyword}={value}{tail}"
        candidate = text[:open_at + 1] + addition + text[close_at:]
        region_end = candidate.find("\n", open_at + 1 + len(addition))
        region = candidate[line_start:region_end if region_end != -1 else None]
        if max(len(line) for line in region.split("\n")) > LIMIT:
            indent = len(text[line_start:]) - len(text[line_start:].lstrip(" "))
            if "\n" in args:
                last = stripped[stripped.rfind("\n") + 1:]
                arg_indent = " " * (len(last) - len(last.lstrip(" ")))
                sep = "" if stripped.endswith(",") else ","
                addition = f"{stripped}{sep}\n{arg_indent}{keyword}={value},{tail}"
            else:
                inner = " " * (indent + 4)
                body = stripped.rstrip(",")
                addition = f"\n{inner}{body},\n{inner}{keyword}={value},\n{' ' * indent}"
            candidate = text[:open_at + 1] + addition + text[close_at:]
        text = candidate
        count += 1
        position = open_at + 1 + len(addition)


path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
for spec in sys.argv[2:]:
    func, keyword, value = spec.split("=", 2)
    source, changed = migrate(source, func, keyword, value)
    print(f"{func}: {keyword} added to {changed} calls")
path.write_text(source, encoding="utf-8")
```

After running it, run `uv run ruff check <file>` and hand-wrap any line it still flags as too long.

---

### Task 1: The card withholds what the log cannot show

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py` (add `window_inside_log` only)
- Modify: `src/wowperf/domain/analysis/recap.py` (`UNJUDGED`, `AbilityState` docstring, `state_of`, `consumable_state`, `availability_at`)
- Modify: `src/wowperf/domain/report/deaths.py` (`not_judged_detail`, `_availability_row`, `_group`, `_healer_cooldown_row`, the three `_group` calls in `build_deaths`)
- Test: `tests/domain/analysis/test_recap_availability.py`, `tests/domain/report/test_build_deaths.py`, `tests/domain/report/test_recap_from_an_encounter.py`; create `tests/adapters/render/test_unjudged_row_html.py`

**Interfaces:**
- Produces: `window_inside_log(moment_ms: int, seconds: float, visible_from_ms: int) -> bool` in `defensives.py`; `UNJUDGED = "unjudged"` in `recap.py`; `state_of(..., *, visible_from_ms: int)` and `consumable_state(presses, category, death_ms, *, visible_from_ms: int)` (both required keywords); `not_judged_detail(setting: str) -> str` in `deaths.py`.

- [ ] **Step 1: The predicate**

In `src/wowperf/domain/analysis/defensives.py`, directly above `def defensives_up_at(`:

```python
def window_inside_log(moment_ms: int, seconds: float, visible_from_ms: int) -> bool:
    """Whether the `seconds` before `moment_ms` lie wholly inside the log.

    A press before `visible_from_ms` is invisible -- casts are fetched per
    fight, and a raid cooldown carries over from the pull before -- so a window
    reaching back past it cannot show that an ability was unspent. Every rule
    that calls something ready or available asks this first, and one that
    cannot pass it says "not judged" rather than guess in the one direction
    this project never guesses in.
    """
    return moment_ms - seconds * 1000 >= visible_from_ms
```

- [ ] **Step 2: Migrate the existing tests to a log that began long before**

The existing cases are not about the log's edge, and many place a death 60 s in with a 120 s cooldown. They get a log that began an hour earlier. In `tests/domain/analysis/test_recap_availability.py`, directly after `DEATH_MS = 60_000`:

```python
LOG_FROM = DEATH_MS - 3_600_000
"""A log that began an hour before the death most cases place, so no base cooldown here reaches
past it. The cases about that edge pass their own origin."""
```

Then run:
`/c/Users/damien/.local/bin/uv.exe run python <scratch>/migrate_calls.py tests/domain/analysis/test_recap_availability.py "state_of=visible_from_ms=LOG_FROM" "consumable_state=visible_from_ms=LOG_FROM"`
Expected output: `state_of: visible_from_ms added to 33 calls`, `consumable_state: visible_from_ms added to 3 calls`. `availability_at` calls already pass their origin positionally; leave them.

- [ ] **Step 3: Write the failing tests**

In `tests/domain/analysis/test_recap_availability.py`, add `UNJUDGED,` to the `wowperf.domain.analysis.recap` import (between `READY,` and `UNSEEN,`), and append:

```python


# --- a base cooldown reaching before the log --------------------------------
#
# A press before the log's first second is invisible, and on a raid a cooldown
# carries over from the pull before, so a window reaching past that second
# cannot show an ability unspent. Every case sits on an origin far from zero,
# as report timestamps do.

ORIGIN = 5_000_000
"""The log's first second in these cases."""


def after_origin(seconds: float) -> int:
    return ORIGIN + int(seconds * 1000)


def state_at(
    seconds: float, presses: tuple[CastEvent, ...], ability: DefensiveAbility = ICEBOUND
) -> str:
    return state_of(
        presses, ability.name, ability.cooldown_seconds, ability.charges, after_origin(seconds),
        ability_id=ability.ability_id, visible_from_ms=ORIGIN,
    ).state


def test_a_base_cooldown_starting_at_the_logs_first_second_is_judged() -> None:
    owns = (press(ICEBOUND.ability_id, after_origin(300)),)
    assert state_at(120, owns) == READY


def test_a_base_cooldown_reaching_one_millisecond_before_the_log_is_not_judged() -> None:
    owns = (press(ICEBOUND.ability_id, after_origin(300)),)
    one_ms_early = state_of(
        owns, ICEBOUND.name, ICEBOUND.cooldown_seconds, 1, after_origin(120) - 1,
        ability_id=ICEBOUND.ability_id, visible_from_ms=ORIGIN,
    )
    assert (one_ms_early.state, one_ms_early.seconds) == (UNJUDGED, None)


def test_a_press_in_the_run_up_outranks_a_window_before_the_log() -> None:
    assert state_at(30, (press(ICEBOUND.ability_id, after_origin(25)),)) == PRESSED


def test_a_spent_cooldown_outranks_a_window_before_the_log() -> None:
    # Every press it rests on is in the log, so "at most so long left" stays true.
    assert state_at(60, (press(ICEBOUND.ability_id, after_origin(20)),)) == COOLDOWN


def test_a_spare_charge_early_in_the_log_is_not_judged() -> None:
    # One of Rune Tap's two charges spent 5s in; a press before the log could
    # have spent the other, so 20s in it is not judged -- and a full base
    # cooldown in, the window lies inside the log and the spare charge is ready.
    spent_one = (press(RUNE_TAP.ability_id, after_origin(5)),)
    assert state_at(20, spent_one, RUNE_TAP) == UNJUDGED
    assert state_at(26, spent_one, RUNE_TAP) == READY


def test_a_cooldown_never_pressed_stays_unseen_before_the_log() -> None:
    assert state_at(30, ()) == UNSEEN


def test_the_dying_players_defensives_and_teammates_externals_are_both_not_judged_early() -> None:
    death = a_death(at_ms=after_origin(30))
    casts = (
        press(ICEBOUND.ability_id, after_origin(300)),
        press(IRONBARK.ability_id, after_origin(300), actor_id=2, target_id=1),
    )
    at = availability_at(
        (DUDE, TREE), casts, death, Defensives(entries=(("DeathKnight/Blood", (ICEBOUND,)),)),
        Consumables(), Externals(entries=(("Druid/Restoration", (IRONBARK,)),)), ORIGIN,
    )
    assert at.own is not None
    assert [(one.name, one.state) for one in at.own] == [("Icebound Fortitude", UNJUDGED)]
    assert [(one.name, one.state) for one in at.externals] == [("Ironbark", UNJUDGED)]
```

In `tests/domain/report/test_build_deaths.py`, the existing `test_a_card_lists_a_defensive_that_was_off_cooldown_as_ready` places its death 60 s into a 120 s pull with this file's 180 s Icebound -- exactly the overclaim. Its purpose is the `ready` row, so move its death, not its assertion. Replace its fixture lines

```python
    # Pressed after the rez, so the ability is demonstrably theirs and the cast
    # falls outside the window that ends at the death.
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(70_000)}
    )
```

with

```python
    # Pressed after the rez, so the ability is demonstrably theirs and the cast
    # falls outside the window that ends at the death. The death is a full base
    # cooldown (180s) into the run, so that window lies inside the log.
    loaded = LoadedRun(
        run=a_run(players=(a_player(),), pulls=(a_pull(0, 0, 240_000),)),
        deaths=(a_death(1, 180_000),),
        casts=owns_icebound(190_000),
    )
```

and append to the file:

```python


def test_a_card_withholds_a_defensive_whose_base_cooldown_reaches_before_the_first_pull() -> None:
    # Icebound's 180s base cooldown, 60s into the run: a press before the first
    # pull would be invisible, so the card says it did not judge, in the run's words.
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(70_000)}
    )
    own = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0].availability[0]
    assert [(row.ability, row.state, row.detail) for row in own.rows] == [
        ("Icebound Fortitude", "unjudged",
         "not judged, its base cooldown reaches before the run's first second")
    ]
```

Append to `tests/domain/report/test_recap_from_an_encounter.py` (its fight starts at 1_000_000 ms):

```python


def test_a_boss_card_judges_a_defensive_from_the_fights_own_start() -> None:
    # Icebound's base cooldown is 120s. A death 60s into the fight reaches back
    # before its first second, where a press would be invisible -- and a
    # cooldown carries over from the pull before -- so the row withholds the
    # judgement; 120s in, the window lies inside the log and it reads ready.
    owns = (CastEvent(actor_id=1, ability_id=48792, ability_name="Icebound Fortitude",
                      timestamp_ms=FIGHT_START_MS + 500_000),)

    def own_rows(death_ms: int) -> list[tuple[str, str]]:
        loaded = a_loaded_fight(deaths=(a_death(death_ms),), casts=owns)
        group = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0].availability[0]
        return [(row.state, row.detail) for row in group.rows]

    assert own_rows(FIGHT_START_MS + 60_000) == [
        ("unjudged", "not judged, its base cooldown reaches before the fight's first second")
    ]
    assert own_rows(FIGHT_START_MS + 120_000) == [("ready", "ready")]
```

Create `tests/adapters/render/test_unjudged_row_html.py`:

```python
# ABOUTME: A defensive the card cannot judge reaches the Deaths panel as its builder wrote it.
# ABOUTME: No golden holds such a row, so this is the one render test that draws it.

from markupsafe import escape

from tests.adapters.render.test_deaths_healers_html import mplus_html
from tests.adapters.render.test_raid_html_invariants import _panel
from tests.domain.report.test_build_deaths import BLOOD, a_death, a_loaded_with, owns_icebound
from tests.domain.report.test_build_frame import NO_CONSUMABLES
from wowperf.domain.report.deaths import build_deaths


def test_an_unjudged_row_is_drawn_with_its_state_and_its_sentence() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(70_000)}
    )
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    [row] = card.availability[0].rows
    deaths = _panel(mplus_html(card), "tab-deaths")
    assert '<li class="unjudged">' in deaths
    assert str(escape(row.detail)) in deaths
    assert ">None<" not in deaths
```

- [ ] **Step 4: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_recap_availability.py tests/domain/report/test_build_deaths.py tests/domain/report/test_recap_from_an_encounter.py tests/adapters/render/test_unjudged_row_html.py -q`
Expected: FAIL -- at import, `cannot import name 'UNJUDGED'`, and `state_of() got an unexpected keyword argument 'visible_from_ms'`.

- [ ] **Step 5: The card rule**

In `src/wowperf/domain/analysis/recap.py`:

- the import becomes `from wowperf.domain.analysis.defensives import RUN_UP_SECONDS, window_inside_log`;
- after `FADED = "faded"`:

```python
UNJUDGED = "unjudged"
"""The value `cooldown_reading.Reading.NOT_JUDGED` carries, so the card's rows and the Healers
group beside them name a withheld judgement the same way."""
```

- in `AbilityState`'s docstring, replace

```
    run-up, a lower bound, else None. UNSEEN: always None. `owner_id` is None
    for the dying player's own abilities and a teammate's actor id for an
    external.
```

with

```
    run-up, a lower bound, else None. UNSEEN and UNJUDGED: always None.
    `owner_id` is None for the dying player's own abilities and a teammate's
    actor id for an external.
```

- in `state_of`'s signature, after `blow_ms: int | None = None,` add `visible_from_ms: int,`; its docstring's first line becomes `"""Which of the seven states one ability was in at the death.`; and in the docstring replace `frees its charge, rounded up. Otherwise READY.` with

```
    frees its charge, rounded up -- true however early, since those presses are
    in the log. Otherwise, a base cooldown reaching back before
    `visible_from_ms` is UNJUDGED (`window_inside_log`): an unseen press there
    could have spent it, a charge included, and on a raid a cooldown carries over
    from the pull before. Otherwise READY.
```

- in `state_of`'s body, directly after the `return AbilityState(... state=COOLDOWN ...)` block closes and before the comment `# A charge comes free when the oldest of the last`:

```python
    if not window_inside_log(death_ms, cooldown_seconds, visible_from_ms):
        return AbilityState(name=name, state=UNJUDGED, owner_id=owner_id, ability_id=ability_id)
```

- `consumable_state` becomes:

```python
def consumable_state(
    presses: tuple[CastEvent, ...],
    category: ConsumableCategory,
    death_ms: int,
    *,
    visible_from_ms: int,
) -> AbilityState | None:
```

(docstring unchanged), and its body's first line:

```python
    state = state_of(
        presses, category.name, category.cooldown_seconds, 1, death_ms,
        visible_from_ms=visible_from_ms,
    )
```

- in `availability_at`, pass `visible_from_ms=visible_from_ms,` to all three inner calls: the own-defensives `state_of` (after `auras=auras, window=window, blow_ms=blow_ms,`), the `consumable_state` call (after `category, death_ms,`), and the externals `state_of` (after `ability_id=ability.ability_id,`). The consumables' existing `consumable_window_start(...) >= visible_from_ms` filter stays: consumables are still dropped, not listed, when their window reaches before the log.

- [ ] **Step 6: The card's words**

In `src/wowperf/domain/report/deaths.py`:

- add `UNJUDGED,` to the `wowperf.domain.analysis.recap` import (between `SELF_RESURRECTED,` and `UNSEEN,`);
- after `NO_TEAMMATE_EXTERNALS = ...` (two blank lines either side):

```python
def not_judged_detail(setting: str) -> str:
    """What a row says of a cooldown whose base cooldown reaches before the log's first second.

    One sentence for every group on the card -- a defensive, an external, a
    group healing cooldown -- so the rows beside each other say it one way.
    """
    return f"not judged, its base cooldown reaches before the {setting}'s first second"
```

- `_availability_row` gains a fourth parameter `setting: str` (after `tooltips`), and a branch after the `UNSEEN` one:

```python
    elif state.state == UNJUDGED:
        detail = not_judged_detail(setting)
```

- `_group` gains a keyword-only `setting: str` after `caveat: str = "",` (`*,` then `setting: str,`), and passes it: `rows=tuple(_availability_row(state, names, tooltips, setting) for state in states),`;
- `_healer_cooldown_row`'s last branch becomes `detail = not_judged_detail(setting)`;
- in `build_deaths`, each of the three `_group(...)` calls passes `setting=setting` (the `setting` variable already exists there):

```python
                    _group("Defensives", at.own, names, f"No data file covers {spec}.", tooltips,
                           setting=setting),
                    _group("Consumables", at.consumables, names, NO_CONSUMABLE_DATA, tooltips,
                           CONSUMABLE_CAVEAT, setting=setting),
                    _group("Teammates' externals", at.externals, names, NO_TEAMMATE_EXTERNALS,
                           tooltips, setting=setting),
```

- [ ] **Step 7: Run, pass, prove**

Run the four test files: all pass. Then the full suite: green, and `git status` shows no golden moved. Prove, restoring after each:
- delete the two-line `if not window_inside_log(...)` guard in `state_of` -> `test_a_base_cooldown_reaching_one_millisecond_before_the_log_is_not_judged` red;
- change `>=` to `>` in `window_inside_log` -> `test_a_base_cooldown_starting_at_the_logs_first_second_is_judged` red;
- move the guard above `if len(recent) >= charges:` -> `test_a_spent_cooldown_outranks_a_window_before_the_log` red;
- make the guard never fire (`if False and not window_inside_log(...)`) -> `test_a_spare_charge_early_in_the_log_is_not_judged` red;
- pass `visible_from_ms=-10**12` to the externals' `state_of` in `availability_at`, then (separately) to the own defensives' -> `test_the_dying_players_defensives_and_teammates_externals_are_both_not_judged_early` red each time;
- delete the `UNJUDGED` branch in `_availability_row` -> `test_a_card_withholds_a_defensive_whose_base_cooldown_reaches_before_the_first_pull` red;
- make that branch call `not_judged_detail("run")` -> `test_a_boss_card_judges_a_defensive_from_the_fights_own_start` red;
- replace `{{ row.state }}` with `x` in the availability `<li class=...>` of `src/wowperf/adapters/render/_deaths.html.j2` -> `test_an_unjudged_row_is_drawn_with_its_state_and_its_sentence` red.

- [ ] **Step 8: Gate and commit**

Full gate. No golden moved. Subject: `Say not judged where a cooldown reaches before the log`

---

### Task 2: The finding withholds it too

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py` (`defensives_up_at`, `analyse_defensives_at_death`, `repeat_defensives_up`)
- Modify: `src/wowperf/domain/analysis/service.py`, `src/wowperf/domain/analysis/encounter_service.py` (the `analyse_defensives_at_death` calls)
- Test: `tests/domain/analysis/test_defensives_at_death.py`, `tests/domain/analysis/test_service.py`, `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes: Task 1's `window_inside_log`.
- Produces: `defensives_up_at(casts, abilities, actor_id, death_ms, *, visible_from_ms: int)`; `analyse_defensives_at_death(players, casts, defensives, deaths, *, locate, visible_from_ms: int, shape: str)` -- `shape` is "run" or "fight".

A plan refinement of the spec, recorded in the design: the pooled finding's denominator is "the deaths judged", and a death it cannot judge is unknown, not "not up" -- exactly the reasoning that already keeps unowned pulls out of it. So an unjudged death leaves both counts; left in, "up at 2 of 5 deaths" would count deaths it never judged.

- [ ] **Step 1: Migrate the existing tests**

In `tests/domain/analysis/test_defensives_at_death.py`, after the `DEATH_MS` docstring (the one ending `so it opens at 265_000.`):

```python
LOG_FROM = 0
"""The log's first second for every case not about that edge: both windows above open after it.

The cases about the edge itself pass their own origin.
"""
```

Run:
`/c/Users/damien/.local/bin/uv.exe run python <scratch>/migrate_calls.py tests/domain/analysis/test_defensives_at_death.py "defensives_up_at=visible_from_ms=LOG_FROM" "analyse_defensives_at_death=visible_from_ms=LOG_FROM" 'analyse_defensives_at_death=shape="run"'`
Expected: 10, 10 and 10 calls. Then `ruff check` the file and hand-wrap the two lines it flags (in the two players-sharing-a-name tests) as:

```python
            run.players, casts, DEFENSIVES, deaths, locate=locate_in_a_run,
            visible_from_ms=LOG_FROM, shape="run",
```

In `test_pooled_counts_equal_the_pull_rows_defensives_up_at_would_give`, the hand-summed `defensives_up_at` call now reads `visible_from_ms=LOG_FROM`; change it to `visible_from_ms=pull.window_ms[0],` -- the pooled rule judges each pull from its own start, and the check must say the same.

- [ ] **Step 2: Write the failing tests**

Replace `test_a_late_press_on_one_pull_does_not_bleed_into_the_next_pulls_window` whole. It pinned the overclaim itself: its pull-2 death reads "up" 40 s after pull 1 pressed the shell, which a carried-over cooldown makes false. Its replacement pins the new truth, and a window that must lie inside its own pull can no longer reach a previous pull's press at all:

```python
def test_a_death_whose_window_reaches_into_the_pull_before_is_left_out_of_both_counts() -> None:
    """Real pulls can restart less than a cooldown after the last one ended, and cooldowns carry.

    Anti-Magic Shell's window is (60 + 10) seconds. Pull 1 presses it at 590s
    of a 600s pull, after a death at 100s where it reads up. Pull 2 starts 30s
    after pull 1 ends -- only 40s past that late press -- and the player dies
    there 20s in, battle-rezzed, then presses it again at 200s to prove they
    still own it. That death's window reaches 50s back past pull 2's first
    second, where pull 1's press really did spend the shell: a cooldown carries
    over between pulls. It is not judged, so it counts neither as up nor as a
    death judged. Pull 3 dies judged at 100s, so the player is named -- up at
    two of two deaths, not two of three, and not three of three.
    """
    pull_one = a_pull(
        1,
        deaths=((EMBERKIN, 100.0),),
        casts=((EMBERKIN, AMS, 590.0),),
    )
    pull_two = a_pull(
        2,
        start_ms=pull_one.encounter.end_ms + 30_000,
        deaths=((EMBERKIN, 20.0),),
        casts=((EMBERKIN, AMS, 200.0),),
    )
    pull_three = a_pull(
        3,
        deaths=((EMBERKIN, 100.0),),
        casts=((EMBERKIN, AMS, 200.0),),
    )
    findings = repeat_defensives_up(a_loaded_series(pull_one, pull_two, pull_three), BLOOD)
    assert [f.title for f in findings] == ["Emberkin: Anti-Magic Shell up at 2 of 2 deaths"]
```

Append to `tests/domain/analysis/test_defensives_at_death.py`:

```python


# --- a window reaching before the log ----------------------------------------

ORIGIN = 4_000_000
"""The log's first second in the cases below, far from zero as report timestamps are."""


def test_a_window_starting_at_the_logs_first_second_is_judged() -> None:
    # Prismatic Barrier's window is (25 + 10) seconds; cast after the death to prove it is owned.
    owns = (a_cast(BARRIER, ORIGIN + 100_000),)
    assert defensives_up_at(
        owns, (BARRIER,), 11, ORIGIN + 35_000, visible_from_ms=ORIGIN
    ) == ("Prismatic Barrier",)


def test_a_window_reaching_one_millisecond_before_the_log_is_not_judged() -> None:
    owns = (a_cast(BARRIER, ORIGIN + 100_000),)
    assert defensives_up_at(
        owns, (BARRIER,), 11, ORIGIN + 35_000 - 1, visible_from_ms=ORIGIN
    ) == ()


def test_the_finding_says_what_it_does_not_judge_in_its_own_setting() -> None:
    for shape in ("run", "fight"):
        [finding] = analyse_defensives_at_death(
            a_run().players, owns_both(), DEFENSIVES, (a_death(),), locate=locate_in_a_run,
            visible_from_ms=LOG_FROM, shape=shape,
        )
        assert (
            "An ability whose base cooldown reaches back before the "
            f"{shape}'s first second is not judged, since a press before it is invisible."
        ) in finding.detail
```

In `tests/domain/analysis/test_service.py`, `test_a_death_with_a_defensive_available_reaches_the_ranked_list` is a wiring test whose fixture run lasts 200 s while Ice Block's window is 250 s: no death in it can be judged. Replace the test whole:

```python
def test_a_death_with_a_defensive_available_reaches_the_ranked_list() -> None:
    # Emberkin dies 180s in, on the boss, and casts Prismatic Barrier 10s later,
    # which proves it is talented. Its window, (25 + 10) seconds, lies inside the
    # run, so it was off cooldown -- Ice Block's 250s would reach before the
    # first pull and not be judged. The availability analyser must contribute
    # alongside the never-pressed one it sits beside.
    barrier = DefensiveAbility(ability_id=235450, name="Prismatic Barrier", cooldown_seconds=25.0)
    loaded = a_loaded_run().model_copy(
        update={
            "casts": (
                CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                          timestamp_ms=190_000, pull_index=1),
            ),
            "deaths": (
                Death(player_name="Emberkin", actor_id=11, timestamp_ms=180_000,
                      killing_blow="Molten Scar", pull_index=1,
                      seconds_until_next_action=22.0),
            ),
        }
    )
    ids = {
        finding.id
        for finding in analyse(
            loaded, SEASON, Defensives(entries=(("Mage/Arcane", (barrier,)),)), Consumables(),
            ThroughputCooldowns(),
        )
    }
    assert "defensives.unused.emberkin" in ids
```

and append:

```python


def test_a_defensive_whose_window_reaches_before_the_first_pull_is_not_held_against_them() -> None:
    # The same death 30s in: Prismatic Barrier's (25 + 10) second window reaches
    # back before the first pull, where a press would be invisible.
    barrier = DefensiveAbility(ability_id=235450, name="Prismatic Barrier", cooldown_seconds=25.0)
    loaded = a_loaded_run().model_copy(
        update={
            "casts": (
                CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                          timestamp_ms=40_000, pull_index=0),
            ),
        }
    )
    ids = {
        finding.id
        for finding in analyse(
            loaded, SEASON, Defensives(entries=(("Mage/Arcane", (barrier,)),)), Consumables(),
            ThroughputCooldowns(),
        )
    }
    assert "defensives.unused.emberkin" not in ids
```

Append to `tests/domain/analysis/test_encounter_service.py` (its fixture fight starts at 1_000 ms):

```python


def test_a_defensive_is_judged_from_the_fights_own_start() -> None:
    # The fight starts at 1s. Prismatic Barrier's window is (25 + 10) seconds, so
    # a death 35s after the start is judged and one half a second earlier is not
    # -- which only a caller passing the fight's start, not zero, can tell apart.
    barrier = DefensiveAbility(ability_id=235450, name="Prismatic Barrier", cooldown_seconds=25.0)
    only_barrier = Defensives(entries=(("Mage/Arcane", (barrier,)),))

    def ids_for(death_ms: int) -> set[str]:
        loaded = a_loaded_encounter(
            casts=(CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                             timestamp_ms=200_000),),
            deaths=(Death(player_name="Emberkin", actor_id=11, timestamp_ms=death_ms,
                          killing_blow="Venom Bolt"),),
        )
        return {finding.id for finding in analyse_encounter(loaded, only_barrier, Consumables())}

    assert "defensives.unused.emberkin" in ids_for(1_000 + 35_000)
    assert "defensives.unused.emberkin" not in ids_for(1_000 + 34_500)
```

(`CastEvent`, `Death`, `DefensiveAbility` and `Defensives` are already imported in both service test files; if `ruff` or `mypy` says otherwise, add them to the existing import blocks.)

- [ ] **Step 3: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_defensives_at_death.py tests/domain/analysis/test_service.py tests/domain/analysis/test_encounter_service.py -q`
Expected: FAIL -- `defensives_up_at() got an unexpected keyword argument 'visible_from_ms'`.

- [ ] **Step 4: The finding**

In `src/wowperf/domain/analysis/defensives.py`:

- `defensives_up_at`'s signature gains, after `death_ms: int,`: `*,` and `visible_from_ms: int,`;
- in its docstring, insert before `What remains resolves toward saying nothing.`:

```
    **And that window must lie inside the log** (`window_inside_log`). Casts
    are fetched for the fight, so one pressed before `visible_from_ms` is
    invisible, and on a raid a cooldown carries over from the pull before. A
    window reaching back past the log's first second could hide the press that
    spent the ability, so it is not judged, and the ability is not named.

```

  and replace the false sentence -- from `the log emits no cooldown reset or reduction events` through `cannot produce a false accusation.` -- with:

```
    and the log emits no cooldown reset or reduction events, so a reset reads as
    unavailable. Each understates what was up, and understating cannot produce
    a false accusation.
```

- in its body, between the ownership test and the `and not any(` window test:

```python
        and window_inside_log(
            death_ms, ability.cooldown_seconds + RUN_UP_SECONDS, visible_from_ms
        )
```

- `analyse_defensives_at_death` gains keyword-only `visible_from_ms: int,` and `shape: str,` after `locate: Callable[[Death], str],`; its docstring's `locate` paragraph ends:

```
    against. `visible_from_ms` is the log's first second as the card reads it
    -- a keystone's first pull, a boss fight's own start -- and `shape` names
    that setting, "run" or "fight", for the sentence saying what is not judged.
```

  its call becomes

```python
            up = defensives_up_at(
                casts, abilities, player.actor_id, death.timestamp_ms,
                visible_from_ms=visible_from_ms,
            )
```

  and its detail, after `"record them. `, gains the clause:

```python
                    "record them. An ability whose base cooldown reaches back before the "
                    f"{shape}'s first second is not judged, since a press before it is "
                    "invisible. A defensive is pressed into damage rather than on "
                    "cooldown, so this is a question to ask, not a mistake to fix."
```

- `repeat_defensives_up`: its docstring's `deaths are unknown rather than "not up".` sentence continues:

```
    deaths are unknown rather than "not up". A death whose window reaches back
    before its own pull's first second is unknown the same way
    (`window_inside_log`): a cooldown carries over between pulls, so it is
    left out of both counts rather than read as down. A player is named when some
```

  in its loop, after `for one in series.attempts_with_events:` add `pull_start_ms = one.window_ms[0]`; its `defensives_up_at` call passes `visible_from_ms=pull_start_ms,`; and after the `if ability.ability_id not in cast_ids: continue` pair:

```python
                    if not window_inside_log(
                        death.timestamp_ms, ability.cooldown_seconds + RUN_UP_SECONDS,
                        pull_start_ms,
                    ):
                        continue
```

  its detail becomes:

```python
                detail=(
                    "Judged pull by pull from this player's own casts against each "
                    "ability's base cooldown, counting only abilities they cast somewhere "
                    "in that pull, then added up across the boss's pulls. A death at which "
                    "an ability's base cooldown reaches back before that pull's first "
                    "second is not judged or counted for it, since a press before the pull "
                    "is invisible. Every other death counts, late wipe deaths included: "
                    "the share of defensives still up at death was measured not to rise "
                    "once a wipe comes apart. A defensive is pressed into damage rather "
                    "than on cooldown, so this is a question to ask, not a mistake to fix."
                ),
```

- `src/wowperf/domain/analysis/service.py`: the `analyse_defensives_at_death` call gains `visible_from_ms=loaded.run.window_ms[0],` and `shape="run",` after its `locate=`;
- `src/wowperf/domain/analysis/encounter_service.py`: its call's last line becomes `locate=locate, visible_from_ms=encounter.start_ms, shape="fight",`.

- [ ] **Step 5: Run, pass, prove**

The three files pass; the full suite is green; no golden moved. Prove, restoring after each:
- delete the `and window_inside_log(...)` clause in `defensives_up_at` -> `test_a_window_reaching_one_millisecond_before_the_log_is_not_judged` red;
- drop `+ RUN_UP_SECONDS` from that clause -> the same test red;
- in `repeat_defensives_up`, make the new `continue` a `pass` -> `test_a_death_whose_window_reaches_into_the_pull_before_is_left_out_of_both_counts` red;
- set `pull_start_ms = 0` -> the same test red;
- pass `visible_from_ms=0` in `encounter_service.py` -> `test_a_defensive_is_judged_from_the_fights_own_start` red;
- pass `visible_from_ms=-10**12` in `service.py` -> `test_a_defensive_whose_window_reaches_before_the_first_pull_is_not_held_against_them` red;
- drop the new detail clause -> `test_the_finding_says_what_it_does_not_judge_in_its_own_setting` red.

- [ ] **Step 6: Gate and commit**

Full gate. No golden moved. Subject: `Name no defensive as available where its cooldown reaches before the log`

---

### Task 3: The documents say it

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `.claude/skills/mplus-analysis/SKILL.md`
- Modify: `docs/plans/2026-09-03-mplus-postmortem-design.md`, `docs/plans/2026-09-07-death-recap-design.md`, `docs/plans/2026-09-20-retire-defensives-never-design.md`, `docs/plans/2026-09-26-night-defensives-pooled-design.md`, `docs/plans/2026-09-29-healer-side-of-death-design.md`

- [ ] **Step 1: The current-state descriptions**

`CLAUDE.md`, in the death-card paragraph, and `README.md`, in the matching paragraph ("Each death gets a recap"): replace `one of six states at the moment of death — pressed, ready, on cooldown, or never seen all run, and` (README: `...at the moment you died — pressed, ready, on cooldown, or never seen all run, and`) with the same text reading `one of seven states ... — pressed, ready, on cooldown, not judged where its base cooldown reaches before the log's first second, or never seen all run, and`. Keep each file's own pronoun ("the moment of death" / "the moment you died") and rewrap to the file's width.

- [ ] **Step 2: Amendment notes in the earlier designs**

Add each note as its own paragraph, in the house form `*Amended 2026-09-29:*`:
- `2026-09-03-mplus-postmortem-design.md`, directly after the paragraph beginning `*Amended 2026-09-07:* on the death card the two-state answer becomes four`: `*Amended 2026-09-29:* a base cooldown reaching back before the log's first second -- a keystone's first pull, a boss fight's own start -- is not judged. The card lists the ability as "not judged", and the finding does not name it. See `2026-09-29-not-judged-before-the-log-design.md`.`
- `2026-09-07-death-recap-design.md`, at the end of section 4.3 "Availability" (before `### 4.4 The return`): `*Amended 2026-09-29:* a seventh state, `unjudged`, sits between on cooldown and ready: a base cooldown reaching before the log's first second is not judged, because a press before the log is invisible and a raid cooldown carries over between pulls. See `2026-09-29-not-judged-before-the-log-design.md`.`
- `2026-09-20-retire-defensives-never-design.md`, after the section 2.2 paragraph beginning `The death card places every defensive in one of six states`: `*Amended 2026-09-29:* seven states now -- `unjudged` joined them. See `2026-09-29-not-judged-before-the-log-design.md`.`
- `2026-09-26-night-defensives-pooled-design.md`, after the list item ending `Each ability carries its own denominator.`: `*Amended 2026-09-29:* a death whose window reaches back before its own pull's first second is left out of both the count and the denominator: a cooldown carries over between pulls, so that death is unknown, not "not up". See `2026-09-29-not-judged-before-the-log-design.md`.`
- `2026-09-29-healer-side-of-death-design.md`, at the start of the section 7 bullet `**The card's externals overclaim ready early in a fight.**`: prefix `**Closed 2026-09-29** by `2026-09-29-not-judged-before-the-log-design.md`, which widened it to the dying player's own defensives and the defensives findings.`

- [ ] **Step 3: The skill**

In `.claude/skills/mplus-analysis/SKILL.md`, after the paragraph beginning `` `defensives.unused.*` reconstructs "off cooldown" from cast timestamps``, add:

```
A base cooldown reaching back before the log's first second -- a keystone's first pull, a boss
fight's own start -- is not judged. The death card lists the ability as "not judged, its base
cooldown reaches before the run's (or fight's) first second", `defensives.unused.*` does not
name it, and `progression.repeat.ready.*` leaves that death out of its count and its
denominator. Read "not judged" as a withheld judgement, never as a fault and never as "it was
up": a press before the log is invisible, and on a raid a cooldown carries over from the pull
before.
```

Run `/c/Users/damien/.local/bin/uv.exe run pytest tests/test_skills.py -q`: green.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Record the not-judged state in the documents that list the card's states`

---

### Task 4: Exercise it on real reports

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: The live runs**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections. All with `--no-compare`, `--out` in your scratch directory; note the points each prints, and stop and report if any single run spends more than 30:
- `raid cW38jmwdnZfbHVL4 --fight N` for N in 2, 30, 32, 8, 29, 31 (warm);
- `analyze 6Kx1P9GbNXrcLdHa --fight 36` and `analyze 4vFcVAW1PB2CrD9z --fight 72` (warm).

- [ ] **Step 2: The distribution**

The HTML is not read. Write a scratch script (outside the repository) that loads each of those eight fights through the repository at the default cache dir (`build_repository(Path("cache"))`, then `load_encounter` + `load_encounter_with_auras` for a raid fight, `load` + `load_run_with_auras` for a key, as `wowperf.cli` does), builds the cards with `build_deaths(loaded, load_defensives(), load_consumables(), load_externals(), load_self_resurrections())`, and prints counts only -- no name, slug or reference code:
- per fight: deaths; own-defensive rows by state and external rows by state (`availability[0]` and `availability[2]` rows' `.state`);
- `ready` claims withdrawn: the `unjudged` rows (the guard only ever turns a `ready` into `unjudged`, so that count is the size of the overclaim);
- the finding, now and before: for each death, `defensives_up_at(loaded.casts, abilities, actor_id, death.timestamp_ms, visible_from_ms=loaded.window_ms[0])` against the same call with `visible_from_ms=-10**15` (the old rule) -- deaths naming at least one ability, and abilities named, under each;
- the `defensives.unused.*` findings in each written findings file, as a count;
- totals across all eight.

Scan each written HTML only for `>None<`, `>null<`, `>nan<`, `{{`, `{%`, as counts. A state that never occurs is reported as open; do not look for another report -- RwlRwl supplies one. The pooled night finding is exercised offline only unless RwlRwl asks for a night run: a `night` run at the card tier fetches every pull's casts.

- [ ] **Step 3: The design**

In `docs/plans/2026-09-29-not-judged-before-the-log-design.md`: the status line gains "built"; under section 4 a **Live** paragraph with the counts (numbers and fight ids only), the points spent, the ready claims withdrawn and the findings withdrawn, and every state that did not occur, marked open.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Exercise the not-judged rule on real reports`. Body: the points spent and the counts, no names.

---

## What this plan deliberately does not build

- The `unseen` row's "not seen this run" and the card's "Not seen acting again this run." on a boss fight, where there is no run: recorded in the design, not fixed here.
- Modelling talents that shorten a cooldown, early charge refreshes, or resets.
- Any change to the heavy-moment finding or the Healers group.
- A stylesheet rule for the new state.
