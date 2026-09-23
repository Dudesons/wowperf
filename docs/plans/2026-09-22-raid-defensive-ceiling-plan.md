# Raid Defensive Ceiling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop discarding players whose death was never followed by an outward action, and say
out loud when a fight was too short for a defensive to have a ceiling worth judging.

**Architecture:** `alive_combat_seconds` gains a `combat_end_ms` argument and stops returning
`None`: a death with no following action counts as dead until combat ended. That deletes the
`alive is None` branch from both ceiling analysers. Separately, `analyse_defensive_ceiling`
mints one `defensives.ceiling.withheld` finding per report when the fight itself was too short
for an ability someone pressed, and both report builders lift it into Provenance rather than
ranking it.

**Tech Stack:** Python 3.12, `uv` (the only toolchain), pytest, ruff, mypy strict, Jinja2.

**Spec:** `docs/plans/2026-09-22-raid-defensive-ceiling-design.md`

## Global Constraints

- `uv` is the only toolchain. `uv run pytest`, `uv run ruff check .`, `uv run mypy` (mypy takes
  no paths; they come from `pyproject.toml`).
- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`,
  `jinja2`, or anything touching network, disk or template.
- **Every finding carries a confidence badge** — `measured`, `derived` or `inferred`. A finding
  without one is a bug.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`,
  `Stonewake`, `Bríala` and `Кириллица`.
- The five players on `6Kx1P9GbNXrcLdHa`, and the twenty on `cW38jmwdnZfbHVL4` and
  `DJfap6RcYKhPGHXZ`, are real people. Refer to them by class, spec, role or index — in code, in
  tests, in commit messages and in documents.
- **NEVER USE `--no-verify`** or any other bypass flag when committing.
- Never delete a test because it is failing. Raise it with RwlRwlRwlRwl instead.
- Commit messages: imperative mood, no `feat:`/`fix:` prefix, body explains **why**. Plain
  ASCII — non-ASCII has been mangled into commit bodies on this machine before.
- **A new judgement is not done until a live run has exercised it.** Task 4 is not optional.

## Amendments to the spec

Two corrections found while writing this plan. Both are deliberate and the design document has
been updated to match.

1. **The withheld finding is badged `measured`, not `derived`.** Section 6 of the design said
   `derived`. The precedent it instructs us to follow, `_withheld` in
   `src/wowperf/domain/analysis/attempt_shape.py`, uses `Confidence.MEASURED` on the reasoning
   that "the absence itself is a fact about the report rather than a reading of it". What this
   finding asserts is that the analyser declined to judge and why; both halves are checked.
2. **Suppression is judged against the fight, not against each player's alive time.** The
   design's minting condition ("at least one pair had a non-zero press count and a ceiling of 5
   or less") used each player's own alive seconds. A player who died early has abilities
   suppressed by their short life, not by a short fight, and an evidence line saying the fight
   was too short would then be false. The condition is therefore
   `cooldown_ceiling(combat_seconds, ability) <= 1 / CEILING_USE_FRACTION`. The counts quoted in
   the design (11, 14, 18, 15, 15 on raid; three of nine keystones) were measured per player and
   are an **upper bound**. Task 4 re-measures them.

---

### Task 1: Repair the denominator

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py` (`alive_combat_seconds`,
  `analyse_defensive_ceiling`)
- Modify: `src/wowperf/domain/analysis/throughput.py:242` (`analyse_cooldown_ceiling`)
- Modify: `src/wowperf/domain/analysis/service.py:65-68`
- Modify: `src/wowperf/domain/analysis/encounter_service.py:109-112`
- Test: `tests/domain/analysis/test_defensives.py`,
  `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Produces: `alive_combat_seconds(combat_seconds: float, deaths: tuple[Death, ...],
  actor_id: int, *, combat_end_ms: int) -> float` — never `None`.
- Produces: `analyse_defensive_ceiling(players, combat_seconds, casts, defensives, deaths, *,
  combat_end_ms: int) -> list[Finding]`.
- `combat_end_ms` is keyword-only on both. Four positional numbers, two of them plain ints,
  invite a silent swap of `actor_id` and `combat_end_ms` that no type checker would catch.

- [ ] **Step 1: Write the failing test for the exact alive figure**

Add to `tests/domain/analysis/test_defensives.py`, beside the existing
`test_alive_seconds_is_unknown_when_a_death_was_never_followed_by_an_action` (which this task
replaces — see Step 6):

```python
def test_a_death_never_followed_by_an_action_counts_as_dead_until_combat_ended() -> None:
    # Combat ran to 300_000ms. This player died at 200_000 and never acted on
    # another actor again, so the fight ended with them dead: they were alive
    # for 200s of the 300s and dead for the last 100. Exact, not estimated --
    # a fight that ended at that death is a fight they provably never rejoined.
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=200_000,
              killing_blow="Something", seconds_until_next_action=None),
    )

    assert alive_combat_seconds(300.0, deaths, 11, combat_end_ms=300_000) == 200.0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/domain/analysis/test_defensives.py::test_a_death_never_followed_by_an_action_counts_as_dead_until_combat_ended -v`

Expected: FAIL — `TypeError: alive_combat_seconds() got an unexpected keyword argument
'combat_end_ms'`.

- [ ] **Step 3: Rewrite `alive_combat_seconds`**

Replace the whole function in `src/wowperf/domain/analysis/defensives.py`. The docstring is
part of the deliverable: the old one argues for a `None` that no longer exists.

```python
def alive_combat_seconds(
    combat_seconds: float,
    deaths: tuple[Death, ...],
    actor_id: int,
    *,
    combat_end_ms: int,
) -> float:
    """Combat time this player could actually have pressed a button in.

    `combat_seconds` is the denominator the caller's aggregate defines: summed
    pull time for a keystone, fight duration for a raid boss. Taking the number
    rather than the aggregate is what lets both ask this question; taking a
    `Run` meant a raid fight silently supplied zero.

    A death's dead time is `seconds_until_next_action` where the log recorded
    one. Where it did not, the player was never seen to act on another actor
    again, and they count as dead from that death until `combat_end_ms`. On a
    wipe that is exact: the fight ended, so they provably never returned. For a
    player resurrected who then only ever casts on themselves it understates
    their alive time, which lowers their ceiling and weakens the claim -- the
    same direction every other approximation here leans, because understating
    cannot produce a false accusation.

    Approximate on purpose either way, and one of the reasons the finding is
    `inferred`: a run-back can extend past the pull it started in, so the
    subtraction can overshoot.
    """
    dead = 0.0
    for death in deaths:
        if death.actor_id != actor_id:
            continue
        if death.seconds_until_next_action is None:
            # Clamped because a death can sit a millisecond past the window a
            # keystone computes for itself; see `Run.window_ms`.
            dead += max(combat_end_ms - death.timestamp_ms, 0) / 1000
        else:
            dead += death.seconds_until_next_action
    return max(combat_seconds - dead, 0.0)
```

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/domain/analysis/test_defensives.py::test_a_death_never_followed_by_an_action_counts_as_dead_until_combat_ended -v`

Expected: PASS.

- [ ] **Step 5: Add the understating-direction test**

This documents a deliberate choice rather than an accident, so it must exist even though it
exercises the same branch:

```python
def test_a_player_who_only_self_buffed_after_dying_has_their_alive_time_understated() -> None:
    # `seconds_until_next_action` is None for a resurrected player whose only
    # later casts are on themselves -- ingest counts a cast at another actor and
    # nothing else. Treating them as dead to the end understates how long they
    # were alive, which lowers their ceiling and makes the claim weaker. That is
    # the direction this module leans everywhere, and this pins it: 300s of
    # combat, dead at 100_000ms, credited with 100s alive rather than more.
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=100_000,
              killing_blow="Something", seconds_until_next_action=None),
    )

    assert alive_combat_seconds(300.0, deaths, 11, combat_end_ms=300_000) == 100.0
```

- [ ] **Step 6: Replace the test that asserted the `None` return**

`test_alive_seconds_is_unknown_when_a_death_was_never_followed_by_an_action` asserts
`alive_combat_seconds(100.0, deaths, 11) is None`. That behaviour is gone. Do **not** delete the
test: repoint it at what replaces it, keeping its name accurate.

Rename it to `test_a_death_with_no_following_action_no_longer_makes_alive_time_unknown` and
assert the figure it now produces. If the rename makes it a duplicate of the Step 1 test,
raise that with RwlRwlRwlRwl rather than deleting either.

- [ ] **Step 7: Thread `combat_end_ms` through `analyse_defensive_ceiling`**

Signature becomes:

```python
def analyse_defensive_ceiling(
    players: tuple[Player, ...],
    combat_seconds: float,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
    *,
    combat_end_ms: int,
) -> list[Finding]:
```

Inside the loop, replace these four lines:

```python
            alive = alive_combat_seconds(combat_seconds, deaths, player.actor_id)
            if alive is None:
                continue
            ceiling = cooldown_ceiling(alive, ability)
```

with:

```python
            alive = alive_combat_seconds(
                combat_seconds, deaths, player.actor_id, combat_end_ms=combat_end_ms
            )
            ceiling = cooldown_ceiling(alive, ability)
```

- [ ] **Step 8: Do the same in `analyse_cooldown_ceiling`**

In `src/wowperf/domain/analysis/throughput.py`, replace:

```python
            alive = alive_combat_seconds(run.total_pull_seconds, deaths, player.actor_id)
            if alive is None:
                continue
            ceiling = cooldown_ceiling(alive, ability)
```

with:

```python
            alive = alive_combat_seconds(
                run.total_pull_seconds, deaths, player.actor_id,
                combat_end_ms=run.window_ms[1],
            )
            ceiling = cooldown_ceiling(alive, ability)
```

`Run.window_ms` is an existing property (`src/wowperf/domain/model.py`) returning
`(first pull start, last pull end)` and `(0, 0)` when there are no pulls — so the empty case
needs no guard of its own here. With no pulls `total_pull_seconds` is also zero, the ceiling is
zero, and nothing can fire.

- [ ] **Step 9: Update both service call sites**

`src/wowperf/domain/analysis/service.py`:

```python
    findings += analyse_defensive_ceiling(
        loaded.run.players, loaded.run.total_pull_seconds, loaded.casts, defensives,
        loaded.deaths, combat_end_ms=loaded.run.window_ms[1],
    )
```

`src/wowperf/domain/analysis/encounter_service.py`:

```python
    findings += analyse_defensive_ceiling(
        encounter.players, encounter.duration_seconds, loaded.casts, defensives,
        loaded.deaths, combat_end_ms=encounter.end_ms,
    )
```

- [ ] **Step 10: Add the wipe test that could not have existed before**

In `tests/domain/analysis/test_encounter_service.py`. The fixture `a_loaded_encounter` builds a
fight from `start_ms=1_000` to `end_ms=375_000` with one Arcane Mage at `actor_id=11`.

```python
def test_a_wipe_where_nobody_acted_again_still_judges_the_ceiling() -> None:
    """The defect this task repairs, at the level a reader would meet it.

    On a wipe every player who died has no cast at another actor afterwards,
    so `seconds_until_next_action` is None for all of them. The old rule read
    that as "this player cannot be measured" and dropped them, which silenced
    the ceiling for the entire raid on exactly the fights a reader most wants
    it. Dying at 361_000 of a fight that ended at 375_000 leaves 360s alive,
    which fits Prismatic Barrier's 30s cooldown twelve times.
    """
    casts = (
        CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                  timestamp_ms=10_000, pull_index=None),
    )
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=361_000,
              killing_blow="Something", seconds_until_next_action=None),
    )

    findings = analyse_encounter(
        a_loaded_encounter(casts=casts, deaths=deaths), DEFENSIVES, Consumables()
    )

    ceiling = [f for f in findings if f.id.startswith("defensives.ceiling.")]
    assert ceiling, "a player who died on a wipe still had time alive to judge"
```

- [ ] **Step 11: Fix every other call site the signature change breaks**

Run `uv run pytest -q` and repair the collection and call errors. Call sites are in
`tests/domain/analysis/test_defensives.py`, `tests/domain/analysis/test_throughput.py`,
`tests/domain/analysis/test_service.py` and `tests/domain/analysis/test_encounter_service.py`.
For a keystone fixture pass `combat_end_ms=<run>.window_ms[1]`; for an encounter fixture pass
`combat_end_ms=<encounter>.end_ms`. Do not add a default value to make the failures go away —
a default would let a future caller silently supply zero, which is the class of bug that put a
raid ceiling at zero in the first place.

- [ ] **Step 12: Prove the new behaviour is not vacuous**

Mutation, not inspection. In a throwaway process, change the new branch in
`alive_combat_seconds` from

```python
            dead += max(combat_end_ms - death.timestamp_ms, 0) / 1000
```

to `dead += 0.0` and run
`uv run pytest tests/domain/analysis/test_defensives.py tests/domain/analysis/test_encounter_service.py -q`.

Expected: the Step 1, Step 5 and Step 10 tests all fail. If any of them passes, that test cannot
detect the behaviour it claims to cover — fix the test, not the mutation. Restore the file
afterwards and confirm `git status --porcelain` is clean.

- [ ] **Step 13: Full gate**

```bash
uv run pytest -q
```

Then `uv run ruff check .` and `uv run mypy`. All three must be clean.

- [ ] **Step 14: Commit**

```bash
git add -A
git commit -F <message file>
```

Subject: `Count a death with no following action as dead until combat ended`. The body explains
why: on a wipe nobody acts again, so the old rule dropped every player who died and silenced
the ceiling on the fights it mattered most; the alive figure was knowable all along.

---

### Task 2: Say when the fight was too short to judge

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py` (`analyse_defensive_ceiling`, plus one new
  module-level helper)
- Test: `tests/domain/analysis/test_defensives.py`

**Interfaces:**
- Consumes: `analyse_defensive_ceiling(..., *, combat_end_ms: int)` from Task 1.
- Produces: a finding with id exactly `defensives.ceiling.withheld`, appended to the list
  `analyse_defensive_ceiling` returns. Task 3 lifts it out by that exact id.

- [ ] **Step 1: Write the failing test for the withheld finding**

```python
def test_a_fight_too_short_for_a_pressed_defensive_says_so() -> None:
    # Icebound Fortitude's 180s cooldown needs 900s of combat before a single
    # press could ever clear `uses < ceiling * 0.2`. This run is 600s, so the
    # analyser cannot judge it -- and silence about it would read exactly like
    # having pressed it enough.
    run = a_run_with_one_blood_death_knight(pull_seconds=600.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1],
    )

    withheld = [f for f in findings if f.id == "defensives.ceiling.withheld"]
    assert len(withheld) == 1, [f.id for f in findings]
    assert withheld[0].confidence is Confidence.MEASURED
    assert "Icebound Fortitude" in " ".join(withheld[0].evidence)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/domain/analysis/test_defensives.py::test_a_fight_too_short_for_a_pressed_defensive_says_so -v`

Expected: FAIL — the list is empty, so `len(withheld) == 1` fails.

- [ ] **Step 3: Write the helper**

Add to `src/wowperf/domain/analysis/defensives.py`:

```python
def _ceiling_withheld(combat_seconds: float, needs: dict[str, float]) -> Finding:
    """The abilities this fight was too short to judge, said out loud.

    `measured`, on the same reasoning `attempt_shape._withheld` gives: what is
    asserted is that the analyser declined and why, and both halves are checked
    rather than read. The ceiling claim it declined to make is `inferred`; this
    is not that claim.

    One finding per report rather than per player or per ability. The
    suppression is a fact about the fight's length, identical for every raider
    carrying the ability, and twenty players against sixty-five abilities is a
    wall rather than a disclosure.
    """
    count = len(needs)
    return Finding(
        id="defensives.ceiling.withheld",
        title=(
            f"This fight was too short to judge {count} "
            f"pressed defensive{'s' if count != 1 else ''}"
        ),
        detail=(
            "A ceiling claim needs combat to have run longer than five of an ability's "
            "cooldowns: below that, a single press already clears the threshold, so no "
            f"press count could ever be low enough to report. This fight ran "
            f"{combat_seconds:.0f}s, which is short of what {count} of the defensives "
            "someone pressed would need. Nothing is being said about how those were "
            "used -- this is the analyser declining to judge them, not a clean bill of "
            "health."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=tuple(
            f"{name} would need {seconds:.0f}s of combat"
            for name, seconds in sorted(needs.items())
        ),
    )
```

- [ ] **Step 4: Mint it from the analyser**

Inside `analyse_defensive_ceiling`, before the loop:

```python
    # Keyed by name so two specs carrying the same ability state it once.
    too_short: dict[str, float] = {}
```

Inside the loop, immediately after the `if not uses: continue` guard:

```python
            # Judged against the fight, not against this player's alive time: a
            # player who died early has abilities suppressed by their short life
            # rather than by a short fight, and a line saying the fight was too
            # short would then be false.
            if cooldown_ceiling(combat_seconds, ability) <= 1 / CEILING_USE_FRACTION:
                too_short[ability.name] = (
                    ability.cooldown_seconds / ability.charges / CEILING_USE_FRACTION
                )
```

And immediately before `return findings`:

```python
    if too_short:
        findings.append(_ceiling_withheld(combat_seconds, too_short))
```

Note this adds no `continue`: a pair the fight is too short for is already skipped by
`uses >= ceiling * CEILING_USE_FRACTION`, because `ceiling <= 5` and `uses >= 1` force it. The
new branch records, it does not decide. Task 4 proves output is otherwise unchanged.

- [ ] **Step 5: Run it and watch it pass**

Run: `uv run pytest tests/domain/analysis/test_defensives.py::test_a_fight_too_short_for_a_pressed_defensive_says_so -v`

Expected: PASS.

- [ ] **Step 6: Write the not-minted test**

```python
def test_an_ability_nobody_pressed_does_not_produce_a_withheld_notice() -> None:
    # Same 600s run, and Icebound Fortitude is still out of reach -- but nobody
    # pressed it, so there is nothing the analyser declined to judge. Minting a
    # notice from the cooldown table alone would put a line on every report.
    run = a_run_with_one_blood_death_knight(pull_seconds=600.0)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (), BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1],
    )

    assert [f for f in findings if f.id == "defensives.ceiling.withheld"] == []


def test_a_fight_long_enough_for_every_pressed_defensive_says_nothing() -> None:
    # 1080s fits Icebound Fortitude's 180s cooldown six times, clear of the
    # floor, so the ability is judgeable and there is nothing to withhold.
    run = a_run_with_one_blood_death_knight(pull_seconds=1080.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1],
    )

    assert [f for f in findings if f.id == "defensives.ceiling.withheld"] == []
```

- [ ] **Step 7: Prove the boundary can fail**

In a throwaway process change `<= 1 / CEILING_USE_FRACTION` to `<= 0` and run the three tests
from Steps 1 and 6. Expected: the Step 1 test fails, the two Step 6 tests still pass. Then
change it to `<= 1000` and run them again: expected, the two Step 6 tests fail and Step 1
passes. A condition that survives both mutations is not being tested. Restore and confirm
`git status --porcelain` is clean.

- [ ] **Step 8: Full gate and commit**

`uv run pytest -q`, `uv run ruff check .`, `uv run mypy`, all clean.

Subject: `Say when a fight was too short to judge a defensive's ceiling`. Body: silence and
approval are indistinguishable on the page, and on a 316s kill that covered 11 of 25 pressed
abilities.

---

### Task 3: Put it in Provenance, on both report shapes

**Files:**
- Modify: `src/wowperf/domain/report/raid_build.py`
- Modify: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_raid_ledger.py`, and the matching keystone report test

**Interfaces:**
- Consumes: a finding with id exactly `defensives.ceiling.withheld` from Task 2.

`raid_ledger.py` routes the bare `defensives.` prefix to `group_rows`, which renders on the
Players tab. Left alone, the notice would appear as a ranked group row on both pages. Both
builders already hold the pattern to follow: `raid_build.py` reads `WITHHELD_ID` out of
`findings` before placement and turns it into a Provenance line, and `build.py` builds the same
`withheld: list[str]` and passes `withheld=tuple(withheld)` to its report model.

- [ ] **Step 1: Write the failing test on the raid side**

In `tests/domain/report/test_raid_ledger.py`, using that module's existing rich fixture, assert
that a `defensives.ceiling.withheld` finding does **not** reach `group_rows` and **does** reach
the report's `withheld` tuple, with its detail in the line.

- [ ] **Step 2: Run it and watch it fail**

Expected: the id appears among `group_rows`, and `withheld` does not mention it.

- [ ] **Step 3: Lift it out in `raid_build.py`**

Beside the existing `verdict_notices` read-out, before anything places rows:

```python
    ceiling_notices = [one for one in findings if one.id == CEILING_WITHHELD_ID]
    findings = [one for one in findings if one.id != CEILING_WITHHELD_ID]
```

and beside the existing `withheld.append(...)` calls:

```python
    for notice in ceiling_notices:
        withheld.append(f"Defensive ceiling: {notice.detail}")
```

Import `CEILING_WITHHELD_ID` from `wowperf.domain.analysis.defensives`. Export it there as a
module constant in Task 2 rather than repeating the string literal in three files — if the
literal is still inline from Task 2, promote it now and use it in `_ceiling_withheld` too.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Do the same on the keystone side**

Repeat Steps 1 to 4 against `src/wowperf/domain/report/build.py`, which already has
`withheld: list[str]` and `withheld=tuple(withheld)`. Write the test first there too.

Note the deliberate difference recorded in `raid_build.py`: the raid page states a fight-wide
reason once, the keystone page restates per card. This notice is fight-wide on both, so it is
one line on both. The comment warning "Do not fix this back" is about per-raider comparison
reasons, not about this.

- [ ] **Step 6: Full gate and commit**

`uv run pytest -q`, `uv run ruff check .`, `uv run mypy`.

Subject: `Disclose the withheld defensive ceiling in Provenance`.

---

### Task 4: Exercise it on real runs

`CLAUDE.md`: *a new judgement is not done until a live run has exercised it. A state that never
occurs is a defect, not a quiet success.* This task produces numbers, and it is where the
design's claims get checked rather than trusted.

**Files:**
- Modify: `docs/plans/2026-09-22-raid-defensive-ceiling-design.md` (record the outcome)

- [ ] **Step 1: Build an offline harness**

No API quota and no credentials. Construct `WclRunRepository(client, DiskCache(Path("cache")))`
where `client.execute` raises `RuntimeError`, so a cache miss is loud instead of a silent
network call. Read the report code and fight id from each `out/*.findings.json` (`report_code`,
`fight_id`); a file carrying `dungeon_name` is a keystone and uses `repo.load(...)`, one
carrying `boss_name` is a raid fight and uses `repo.load_encounter(...)`. Thirteen of the
fifteen are still cached; `43HaCNQwPrKqtYgn-2` and `CmzA8dnZyaD4Wkw1-1` have aged out and will
raise. Skip them and say so.

**Do not print a character name.** Identify players by class, spec and index.

- [ ] **Step 2: Check that no existing finding moved**

For every cached run, compare the set of `defensives.ceiling.*` finding ids the repaired
analyser produces against the set in the shipped `out/*.findings.json`, excluding
`defensives.ceiling.withheld`.

Expected on the **nine keystones and on any kill**: identical, except for the two keystone pairs
that previously exited at `alive is None`. Investigate any other difference before continuing —
that would mean the repair changed a case the design said it could not.

- [ ] **Step 3: Report the raid distribution against the design's baseline**

Produce, per raid fight, the count of pairs judged and findings produced, and compare against
the table in section 2.1 of the design:

| fight | kill | seconds | judged today | fires today | judged proposed | fires proposed |
| --- | --- | --- | --- | --- | --- | --- |
| `cW38jmwdnZfbHVL4-2` | yes | 316 | 68 | 7 | 68 | 7 |
| `cW38jmwdnZfbHVL4-8` | no | 106 | 0 | 0 | 68 | 0 |
| `cW38jmwdnZfbHVL4-26` | no | 271 | 15 | 0 | 68 | 4 |
| `cW38jmwdnZfbHVL4-30` | no | 480 | 2 | 0 | 68 | 8 |
| `DJfap6RcYKhPGHXZ-7` | no | 542 | 0 | 0 | 70 | 5 |

The "fires proposed" column was modelled by hand before implementation. If the implementation
disagrees with it, the implementation is the fact and the design's table is the error — record
which, and why.

- [ ] **Step 4: Measure the withheld notice's real fire rate**

Count how many of the thirteen cached runs carry `defensives.ceiling.withheld`, split keystone
against raid. The design measured three of nine keystones and five of five raid fights using
per-player ceilings; this plan's fight-level condition makes those an upper bound, so expect the
same or fewer.

**A notice on every report carries no information, and a notice on none is dead code.** If it
fires on all thirteen or on none, stop and raise it with RwlRwlRwlRwl rather than shipping it.

- [ ] **Step 5: Record the outcome in the design document**

Append a section to `docs/plans/2026-09-22-raid-defensive-ceiling-design.md` giving the measured
before-and-after, the withheld fire rate, and any place the implementation disagreed with the
predicted table. State what was measured and what was left unmeasured. Commit.

Subject: `Record what the repaired defensive ceiling does on the cached runs`.

---

## Self-review

**Spec coverage.** Design §3 (D1) → Task 1. §4 and §6 (D2, disclosure) → Tasks 2 and 3. §5
(signature, callers, no-pulls guard) → Task 1 Steps 3, 8, 9. §7 non-goals: no task touches
`CEILING_USE_FRACTION`, the `never` family, the death card, or `seconds_until_next_action`. §8
testing items 1 to 6 → Task 1 Steps 1/5/10/12, Task 2 Steps 1/6/7, Task 3 Steps 1/5, Task 4.
§9 risks: Mythic+ movement → Task 4 Step 2; fire rate → Task 4 Step 4; `max()` on empty pulls →
Task 1 Step 8, resolved by `Run.window_ms` already returning `(0, 0)`. §11 open items are
deliberately out of scope for this plan.

**Placeholder scan.** No "TBD", no "handle edge cases", no "similar to Task N". Task 3 Steps 1,
2, 4 and 5 describe assertions against fixtures the implementer must read rather than quoting
test bodies, because those fixtures are large and module-local; every other step carries its
code.

**Type consistency.** `alive_combat_seconds(..., *, combat_end_ms: int) -> float` and
`analyse_defensive_ceiling(..., *, combat_end_ms: int)` are used identically in Tasks 1, 2 and
3. The id `defensives.ceiling.withheld` is written the same way in Task 2 Steps 1/4/6 and Task 3
Steps 1/3, and Task 3 Step 3 promotes it to `CEILING_WITHHELD_ID`. `Run.window_ms[1]` and
`encounter.end_ms` are the only two sources of `combat_end_ms` anywhere in the plan.
