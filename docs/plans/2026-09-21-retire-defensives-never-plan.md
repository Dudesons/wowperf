# Retiring `defensives.never` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `defensives.never` finding family, which is 26.3% of every finding the
tool produces and is already rendered, ability for ability, by the death card's `unseen` row.

**Architecture:** One branch of one analyser goes away, and everything that named the family
follows. There is no replacement: the claim survives on the Deaths tab, where it already
reads "not seen this run". The surviving half of the same analyser is renamed to say what it
now does.

**Tech Stack:** Python 3.12, `uv`, pytest, ruff, mypy (strict), Jinja2.

**Spec:** `docs/plans/2026-09-20-retire-defensives-never-design.md` — read it first. Its §2
holds the measurement, §3 records why gating the finding on real talents is impossible, and
§6 states the falsifier that stops this work.

## Global Constraints

- **`uv` is the only toolchain.** `uv run pytest`, `uv run ruff check .`, `uv run mypy` —
  each its own command. **mypy takes no paths**; they come from `pyproject.toml`.
- **Never use `--no-verify`, `--no-hooks` or `--no-pre-commit-hook`.** If a hook fails, fix
  the cause.
- **Commit messages are plain ASCII**, imperative, no `feat:`/`fix:` prefix, body explains
  *why*. Write the message to a file and use `git commit -F <file>`: non-ASCII is mangled into
  git messages on this machine (a `§5.5` once landed as `SS5.5`). End every message with a
  blank line then exactly:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`,
  `Stonewake`, `Bríala`, `Кириллица`, plus the accent-stripped `Briala`. Every fixture below
  already uses these; keep it that way.
- **Reducing test coverage is worse than failing tests.** A test may be deleted **only** when
  the behaviour it pins is the behaviour being removed. A test that merely *mentions* `never`
  is not evidence of that — see Task 1, which re-anchors nine of them instead.
- **Never delete a test because it is failing.** If one fails for a reason this plan does not
  predict, stop and raise it.
- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` gains an import
  that touches the network, the disk or a template.
- **Call git as `/mingw64/bin/git`.** A bare `git` is rewritten by a user-level hook and
  refused. `uv` may be off `PATH`; `/c/Users/damien/.local/bin/uv` always works.
- **One action per Bash call.** `&&` chains and `cd` inside a compound command get refused.

---

## File Structure

Nothing is created. Every file below already exists and shrinks.

| File | Responsibility after this change |
| --- | --- |
| `src/wowperf/domain/analysis/defensives.py` | Three claims become two: pressed far below the ceiling, and off cooldown at a death. The never-cast branch and its `Finding` construction go; `analyse_defensives` becomes `analyse_defensive_ceiling` |
| `src/wowperf/domain/analysis/service.py` | Mythic+ call site follows the rename |
| `src/wowperf/domain/analysis/encounter_service.py` | Raid call site follows the rename |
| `src/wowperf/domain/analysis/deaths.py` | One comment naming the old function |
| `src/wowperf/domain/report/finding_tooltip.py` | `DEFENSIVE_FAMILIES` names one family |
| `src/wowperf/domain/report/ledger.py`, `raid_ledger.py` | Comments stop naming the retired family; the `("defensives.", "group_rows")` entries **stay** — `defensives.ceiling.` falls through to them |
| `tests/domain/analysis/test_defensives.py` | Re-anchored onto the ceiling family (Task 1), then trimmed (Task 2) |
| `tests/domain/analysis/test_encounter_service.py` | The empty-fight test asserts genuine silence |
| `tests/domain/report/test_finding_tooltip.py`, `test_build_placement.py`, `test_build_observations.py`, `test_ledger.py`, `test_raid_ledger.py` | Fixtures and family lists drop the retired id |
| `docs/how-it-works.md`, `.claude/skills/mplus-analysis/SKILL.md` | Stop advertising a claim the tool does not make |

**No golden file changes.** `tests/adapters/render/golden/raid.html` contains no `defensives`
content at all — verified with a positive control, because a bare zero from `grep` is not
trustworthy in this repo. Do not run `--golden-update`; if a golden test fails, something
unplanned happened — stop and raise it.

---

## Task 1: Re-anchor the surviving properties in `test_defensives.py`

**Why this task exists and must come first.** Nine tests in this file use the never branch as
their *vehicle* while pinning a property that has nothing to do with it — id slugging, actor
disambiguation, ASCII safety, per-player independence. Six of them call
`analyse_defensives(..., casts=(), ...)`. When the branch goes, those calls return `[]`, and
**four of the nine would then pass vacuously rather than fail**: `assert all(...)` over an
empty list is `True`, and `len([]) == len(set([]))` is `0 == 0`. They would go green while
pinning nothing. That is this repository's most expensive recurring failure, so the
re-anchoring happens **before** the removal, while a real failure is still possible.

This task makes **no production change**. The suite is green before it and green after it.

**Files:**
- Modify: `tests/domain/analysis/test_defensives.py`

**Interfaces:**
- Consumes: `analyse_defensives(players, combat_seconds, casts, defensives, deaths) -> list[Finding]` (current signature, unchanged by this task)
- Produces: a test module in which every surviving assertion is anchored on
  `defensives.ceiling.`, so Task 2 can delete the never branch without silencing anything

**Background an implementer needs.** `cooldown_ceiling` is
`alive_seconds / cooldown_seconds * charges`, and a ceiling finding fires only when
`ceiling >= MIN_CEILING_USES` (3.0) **and** `uses < ceiling * CEILING_USE_FRACTION` (0.2).
The file's `a_run()` fixture is a 100-second run, and its two Mage defensives are Prismatic
Barrier (25s) and Ice Block (240s). At 100 seconds Prismatic Barrier's ceiling is 4.0 and one
press clears `4.0 * 0.2 = 0.8`, so **no ceiling finding fires** — `a_run()` produces ceiling
findings for no input at all. Four comments in the file claim otherwise ("a single press of
it now also qualifies for a ceiling finding (§5.7)"); they are wrong and this task corrects
them. Stretching the run to 1800 seconds moves both ceilings (72.0 and 7.5) far above one
press, so both fire. That is what `a_long_run()` below is for. All of this was verified
against the live analyser while writing the plan; re-verify in Step 2 rather than trusting it.

- [ ] **Step 1: Add the long-run fixture**

Insert directly after `a_run()` (which ends at the `)` closing its `return Run(...)`):

```python
def a_long_run() -> Run:
    """`a_run()` stretched to 1800s, which is what makes a ceiling finding possible.

    At `a_run()`'s 100 seconds Prismatic Barrier's ceiling is 4.0 and a single
    press clears the 0.2 fraction, so no ceiling finding fires for any input.
    At 1800 seconds the two ceilings are 72.0 and 7.5, and one press of each
    sits far below both. Tests that pin id shape, slugging or independence use
    this fixture so that what they assert about is a claim the analyser can
    actually make.
    """
    base = a_run()
    return base.model_copy(
        update={"pulls": (base.pulls[0].model_copy(update={"end_ms": 1_800_000}),)}
    )


def ceiling_ids(findings: list[Finding]) -> list[str]:
    """Ids of the ceiling findings only, sorted.

    Scoped rather than taking every finding, so that an assertion about the
    ceiling family cannot be satisfied — or broken — by a neighbouring family.
    """
    return sorted(
        finding.id for finding in findings if finding.id.startswith("defensives.ceiling.")
    )
```

- [ ] **Step 2: Verify the fixture produces what the task assumes**

Run:
```bash
uv run python -c "import sys; sys.path.insert(0,'tests'); from domain.analysis.test_defensives import a_long_run, cast, DEFENSIVES, ceiling_ids; from wowperf.domain.analysis.defensives import analyse_defensives; r=a_long_run(); print(ceiling_ids(analyse_defensives(r.players, r.total_pull_seconds, (cast(11,235450), cast(11,45438)), DEFENSIVES, ())))"
```
Expected, exactly:
`['defensives.ceiling.emberkin.235450', 'defensives.ceiling.emberkin.45438']`

If this prints `[]`, the ceiling arithmetic above is wrong for this tree — **stop and raise
it** rather than adjusting the numbers until something appears.

- [ ] **Step 3: Re-anchor the four tests that would otherwise pass vacuously**

Replace `test_a_spec_absent_from_the_list_produces_nothing` (currently at `:125`):

```python
def test_a_spec_absent_from_the_list_produces_nothing() -> None:
    # Sublime is an Elemental Shaman and the fixture only knows Arcane Mages.
    # Anchored on casts that do produce findings for the Mage, so the Shaman's
    # absence is this analyser declining to judge an unlisted spec rather than
    # the call having produced nothing for anybody.
    run = a_long_run()
    findings = analyse_defensives(
        run.players, run.total_pull_seconds, (cast(11, 235450), cast(11, 45438)),
        DEFENSIVES, ()
    )
    assert ceiling_ids(findings)
    assert all("Sublime" not in finding.title for finding in findings)
```

Replace `test_same_named_players_get_distinct_finding_ids` (`:173`):

```python
def test_same_named_players_get_distinct_finding_ids() -> None:
    run = a_long_run()
    twin = Player(actor_id=99, name="Emberkin", class_name="Mage", spec="Arcane",
                  item_level=300)
    run = run.model_copy(update={"players": run.players + (twin,)})
    casts = (cast(11, 235450), cast(11, 45438), cast(99, 235450), cast(99, 45438))
    findings = analyse_defensives(run.players, run.total_pull_seconds, casts, DEFENSIVES, ())
    ids = ceiling_ids(findings)
    # Counted, not just deduplicated: `len(ids) == len(set(ids))` holds for an
    # empty list, so it cannot tell a working disambiguation from no findings.
    assert len(ids) == 4, ids
    assert len(set(ids)) == len(ids), ids
```

Replace `test_defensives_with_no_entries_produces_nothing` (`:183`):

```python
def test_defensives_with_no_entries_produces_nothing() -> None:
    # Cast the abilities the populated file lists, so that emptiness here is
    # caused by the empty defensives file and not by an input nobody pressed.
    run = a_long_run()
    casts = (cast(11, 235450), cast(11, 45438))
    assert ceiling_ids(analyse_defensives(
        run.players, run.total_pull_seconds, casts, DEFENSIVES, ()
    ))
    findings = analyse_defensives(
        run.players, run.total_pull_seconds, casts, Defensives(entries=()), ()
    )
    assert findings == []
```

Replace `test_a_defensive_finding_id_carries_no_character_outside_the_ascii_set` (`:400`),
keeping its docstring verbatim and changing only the body:

```python
def test_a_defensive_finding_id_carries_no_character_outside_the_ascii_set() -> None:
    """Every finding id becomes an HTML element id, so it has to be addressable.

    `defensives.*` built its id from the raw display name while every
    `compare.*` family slugs it, which put a real player's name -- and, for a
    non-Latin one, characters no fragment should carry -- into the page's own
    element ids.
    """
    run = a_run_named("Кириллица")
    run = run.model_copy(
        update={"pulls": (run.pulls[0].model_copy(update={"end_ms": 1_800_000}),)}
    )
    findings = analyse_defensives(
        run.players, run.total_pull_seconds, (cast(11, 235450), cast(11, 45438)),
        DEFENSIVES, ()
    )

    ids = ceiling_ids(findings)
    # Anchored: this player presses both listed defensives well below their
    # ceilings, so rows must exist for the assertion below to mean anything.
    assert ids
    for finding_id in ids:
        assert finding_id.isascii(), finding_id
```

- [ ] **Step 4: Re-anchor the two exact-id tests**

Replace `test_two_names_that_slug_alike_still_reach_different_defensive_finding_ids` (`:420`),
keeping its docstring verbatim:

```python
def test_two_names_that_slug_alike_still_reach_different_defensive_finding_ids() -> None:
    """Slugging discards information, so it must not discard the distinction.

    `Bríala` and `Briala` are two different players and reduce to one slug.
    The id appends the actor id when two players share a *name*, and these two
    do not, so that guard never fires -- the disambiguation has to key on what
    the id actually carries, which after this change is the slug.
    """
    base = a_long_run()
    mage = base.players[0]
    run = base.model_copy(update={
        "players": (
            mage.model_copy(update={"name": "Bríala"}),
            mage.model_copy(update={"actor_id": 12, "name": "Briala"}),
        ),
    })
    casts = (cast(11, 235450), cast(11, 45438), cast(12, 235450), cast(12, 45438))

    findings = analyse_defensives(run.players, run.total_pull_seconds, casts, DEFENSIVES, ())

    ids = ceiling_ids(findings)
    assert len(ids) == 4, ids
    assert len(set(ids)) == len(ids), ids
```

Replace `test_a_uniquely_named_player_gets_an_id_with_no_actor_number_in_it` (`:444`),
keeping its docstring but correcting the two example ids it names:

```python
def test_a_uniquely_named_player_gets_an_id_with_no_actor_number_in_it() -> None:
    """The actor id is the disambiguator, and it appears only when needed.

    Pinned exactly rather than by prefix: `defensives.ceiling.emberkin.45438`
    and `defensives.ceiling.emberkin.11.45438` share a prefix, so a prefix
    assertion cannot tell a working disambiguation from one that fires for
    everybody.
    """
    run = a_long_run()
    findings = analyse_defensives(
        run.players, run.total_pull_seconds, (cast(11, 235450), cast(11, 45438)),
        DEFENSIVES, ()
    )

    assert set(ceiling_ids(findings)) == {
        "defensives.ceiling.emberkin.235450",
        "defensives.ceiling.emberkin.45438",
    }
```

- [ ] **Step 5: Re-anchor the two behavioural tests, and correct their false comments**

Replace `test_a_cast_outside_every_pull_still_counts_as_used` (`:140`):

```python
def test_a_cast_outside_every_pull_still_counts_as_used() -> None:
    # pull_index=None means the cast landed outside any pull window (e.g.
    # between packs). The player still pressed the button, so it counts towards
    # the ceiling: a ceiling finding for Ice Block can only exist if the press
    # was counted, because an ability with zero uses reaches no ceiling at all.
    outside_pull = CastEvent(actor_id=11, ability_id=45438, ability_name="Ice Block",
                             timestamp_ms=1_000, pull_index=None)
    run = a_long_run()
    findings = analyse_defensives(
        run.players, run.total_pull_seconds, (cast(11, 235450), outside_pull), DEFENSIVES, ()
    )
    assert "defensives.ceiling.emberkin.45438" in ceiling_ids(findings)
```

Replace `test_two_players_of_the_same_spec_are_reported_independently` (`:156`):

```python
def test_two_players_of_the_same_spec_are_reported_independently() -> None:
    # Two Arcane mages, each pressing both listed defensives once. Each must get
    # their own pair of rows: one player's presses must not answer for the other.
    run = a_long_run()
    other_mage = Player(actor_id=13, name="Othermage", class_name="Mage", spec="Arcane",
                        item_level=300)
    run = run.model_copy(update={"players": run.players + (other_mage,)})
    casts = (cast(11, 235450), cast(11, 45438), cast(13, 235450), cast(13, 45438))
    findings = analyse_defensives(run.players, run.total_pull_seconds, casts, DEFENSIVES, ())

    assert ceiling_ids(findings) == [
        "defensives.ceiling.emberkin.235450",
        "defensives.ceiling.emberkin.45438",
        "defensives.ceiling.othermage.235450",
        "defensives.ceiling.othermage.45438",
    ]
```

- [ ] **Step 6: Run the file and confirm it is green with the never branch still present**

Run: `uv run pytest tests/domain/analysis/test_defensives.py -v`
Expected: all tests PASS. The never branch is untouched, so the five tests that genuinely pin
it still pass too.

If any re-anchored test fails, the ceiling arithmetic assumed above does not hold — stop and
raise it.

- [ ] **Step 7: Prove the re-anchored tests can still fail**

A re-anchored test that cannot fail is the exact defect this task exists to prevent, so check
it rather than assuming. In a scratch copy **outside the repository** — never edit
`src/` for this — patch `cooldown_ceiling` to return `0.0` and confirm the re-anchored tests
fail:

```bash
uv run python -c "
import sys; sys.path.insert(0,'tests')
import wowperf.domain.analysis.defensives as d
d.cooldown_ceiling = lambda alive, ability: 0.0
from domain.analysis.test_defensives import a_long_run, cast, DEFENSIVES, ceiling_ids
r = a_long_run()
print('with a dead ceiling ->', ceiling_ids(d.analyse_defensives(r.players, r.total_pull_seconds, (cast(11,235450), cast(11,45438)), DEFENSIVES, ())))
"
```
Expected: `with a dead ceiling -> []`, which means every `assert ceiling_ids(...)` and every
exact-id assertion above would fail. If it prints ids, the harness did not patch — check for
stale `.pyc` files before trusting the result.

- [ ] **Step 8: Run the full suite and the linters**

Run: `uv run pytest`
Expected: PASS, same count as before this task.

Run: `uv run ruff check .`
Expected: clean.

Run: `uv run mypy`
Expected: clean.

- [ ] **Step 9: Commit**

Write the message to a file first — non-ASCII is mangled into git messages on this machine:

```bash
cat > /tmp/msg1.txt <<'EOF'
Anchor the defensives id tests on a claim the analyser still makes

Nine tests in this file used the never-cast branch as a vehicle while pinning
something else entirely: id slugging, actor disambiguation, ASCII safety, and
per-player independence. Six called the analyser with no casts at all.

Retiring that branch would have left four of them asserting over an empty list,
where `all(...)` is True and `len([]) == len(set([]))` holds. They would have
gone green while pinning nothing, which is how this repository's worst defects
have reached production before. Re-anchoring them now, while a real failure is
still possible, keeps that from happening quietly later.

Four comments claiming a single press also produced a ceiling finding were
wrong: at the fixture's 100 seconds no ceiling finding fires for any input.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

```bash
/mingw64/bin/git add tests/domain/analysis/test_defensives.py
```

```bash
/mingw64/bin/git commit -F /tmp/msg1.txt
```

---

## Task 2: Remove the branch, rename the analyser, and follow it everywhere

**Why this is one task and not five.** `test_raid_ledger.py` holds a list of every family the
raid service emits and checks it against the service
(`test_the_family_list_matches_what_the_service_emits`). The list cannot drop
`defensives.never.` before the service stops emitting it, and the service cannot stop before
the list drops it, without a red commit in between. The removal and everything naming the
family therefore land together.

**Files:**
- Modify: `src/wowperf/domain/analysis/defensives.py`
- Modify: `src/wowperf/domain/analysis/service.py:10`, `:65`
- Modify: `src/wowperf/domain/analysis/encounter_service.py:14`, `:109`
- Modify: `src/wowperf/domain/analysis/deaths.py:202`
- Modify: `src/wowperf/domain/report/finding_tooltip.py:14`
- Modify: `src/wowperf/domain/report/ledger.py:62`, `src/wowperf/domain/report/raid_ledger.py:36`
- Test: `tests/domain/analysis/test_defensives.py`, `tests/domain/analysis/test_encounter_service.py`, `tests/domain/report/test_finding_tooltip.py`, `test_build_placement.py`, `test_build_observations.py`, `test_ledger.py`, `test_raid_ledger.py`

**Interfaces:**
- Consumes: `ceiling_ids(findings)` and `a_long_run()` from Task 1
- Produces: `analyse_defensive_ceiling(players, combat_seconds, casts, defensives, deaths) -> list[Finding]` — same parameters and return type as the old `analyse_defensives`, emitting only `defensives.ceiling.*`

- [ ] **Step 1: Delete the five tests that pin only the retired behaviour**

These are the only tests whose subject is the removal itself. Delete them whole from
`tests/domain/analysis/test_defensives.py`:

- `test_a_defensive_never_cast_is_reported_as_inferred`
- `test_a_defensive_cast_once_is_not_reported_as_never_cast`
- `test_the_finding_admits_the_ability_may_have_been_unavailable`
- `test_another_players_cast_does_not_excuse_this_player`
- `test_a_never_cast_finding_names_the_defensive_it_is_about`

Do not delete anything else from this file. `test_a_ceiling_finding_names_the_defensive_it_judged`
already covers the naming property for the surviving family.

- [ ] **Step 2: Rewrite the two tests that assert the ceiling *and* the retired family**

Replace `test_a_defensive_never_pressed_produces_no_ceiling_finding`, dropping only its
second assertion:

```python
def test_a_defensive_never_pressed_produces_no_ceiling_finding() -> None:
    # Paired against the pressed case on purpose. With no casts at all the
    # result is empty for every reason at once, so an emptiness assertion on
    # its own would still pass if the ceiling branch stopped working entirely.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)

    pressed = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (a_cast(actor_id=1, ability_id=48792),),
        BLOOD_DEFENSIVES, ()
    )
    assert findings_by_prefix(pressed, "defensives.ceiling.") != []

    unpressed = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (), BLOOD_DEFENSIVES, ()
    )
    assert findings_by_prefix(unpressed, "defensives.ceiling.") == []
```

Replace `test_a_death_with_unmeasured_cost_disables_the_ceiling_but_not_never_cast`. **Its
surviving half is a real guard with nothing to do with this work** — a death whose cost could
not be measured must withhold *every* ceiling finding for that player, not only the one for
the ability they pressed. The second defensive stays in the fixture for exactly that reason:

```python
def test_a_death_with_unmeasured_cost_disables_every_ceiling_for_that_player() -> None:
    # seconds_until_next_action=None means the player's last recorded action in
    # the run was dying, so there is no honest dead-time figure for them and
    # therefore no honest alive-time figure either. That must withhold every
    # ceiling finding for this player, not just the one for the ability they
    # actually pressed -- which is why the fixture lists two defensives and
    # presses one.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    defensives = Defensives(
        entries=(
            (
                "DeathKnight/Blood",
                (
                    DefensiveAbility(
                        ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0
                    ),
                    DefensiveAbility(
                        ability_id=194679, name="Rune Tap", cooldown_seconds=30.0
                    ),
                ),
            ),
        )
    )
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, defensives, (a_death(1, None),)
    )

    assert findings == []
```

- [ ] **Step 3: Rename every remaining call in the test file**

In `tests/domain/analysis/test_defensives.py`, change the import on line 4 and every call:

```python
from wowperf.domain.analysis.defensives import alive_combat_seconds, analyse_defensive_ceiling
```

Then replace every remaining `analyse_defensives(` with `analyse_defensive_ceiling(`. Update
the file's second ABOUTME line, which currently advertises the retired claim:

```python
# ABOUTME: Behaviour tests for the defensive claims a combat log can support.
# ABOUTME: Pressed far below the cooldown ceiling is a caveated claim; the ceiling is a bound.
```

- [ ] **Step 4: Run the file and watch it fail for the right reason**

Run: `uv run pytest tests/domain/analysis/test_defensives.py -x -q`
Expected: FAIL with `ImportError: cannot import name 'analyse_defensive_ceiling'`.

That is the red this task needs. A different failure means Step 1-3 changed something they
should not have.

- [ ] **Step 5: Remove the branch and rename the function**

In `src/wowperf/domain/analysis/defensives.py`, rename `analyse_defensives` to
`analyse_defensive_ceiling`, replace its docstring, and delete the entire `findings.append(...)`
block that mints `defensives.never.{base_id}` along with the `continue` that guarded it. The
`if uses:` gate becomes an early skip:

```python
def analyse_defensive_ceiling(
    players: tuple[Player, ...],
    combat_seconds: float,
    casts: tuple[CastEvent, ...],
    defensives: Defensives,
    deaths: tuple[Death, ...],
) -> list[Finding]:
    """Defensives pressed far below their cooldown ceiling (§5.7).

    `inferred`. The log emits no cooldown-reset or reduction events, so the
    claim cannot be measured, and a defensive is pressed into damage rather
    than on cooldown -- the ceiling bounds what was possible, not what was
    right.

    An ability the player never pressed produces nothing here. It has no
    ceiling to be judged against, and the claim that they never pressed it is
    the death card's, where it sits beside the three other states a reader
    needs to weigh it.
    """
```

and in the loop body, replacing `if uses:` and everything after the ceiling `continue`:

```python
            uses = cast_counts.get(player.actor_id, {}).get(ability.ability_id, 0)
            if not uses:
                continue

            alive = alive_combat_seconds(combat_seconds, deaths, player.actor_id)
            if alive is None:
                continue
            ceiling = cooldown_ceiling(alive, ability)
            if ceiling < MIN_CEILING_USES or uses >= ceiling * CEILING_USE_FRACTION:
                continue
            findings.append(
```

Keep the existing ceiling `Finding(...)` construction exactly as it is, de-indented by one
level to match. **Delete nothing else** — `defensive_base_ids`, `alive_combat_seconds`,
`cooldown_ceiling` and `defensives_up_at` all survive and are used elsewhere.

Update the file's first ABOUTME line, which lists three claims:

```python
# ABOUTME: Defensive claims a combat log can support: cast far below the cooldown ceiling,
# ABOUTME: or off cooldown at a death. Both are inferred.
```

Also correct the two docstrings that name the old function: `:109`
(`"...case entirely to analyse_defensives, which discloses the ambiguity"` — the never-cast
case now belongs to the death card, so say that) and `:214`
(`"Minted here rather than inside analyse_defensives..."` — follow the rename).

- [ ] **Step 6: Follow the rename at both call sites**

In `src/wowperf/domain/analysis/service.py`, change the import at `:10` and the call at `:65`
from `analyse_defensives` to `analyse_defensive_ceiling`. Do the same in
`src/wowperf/domain/analysis/encounter_service.py` at `:14` and `:109`. Neither call's
arguments change.

In `src/wowperf/domain/analysis/deaths.py:202`, the comment reads
`# \`analyse_defensives\`, which still count off the full roster, do count them.` — change the
name to `analyse_defensive_ceiling`.

- [ ] **Step 7: Run the analyser tests**

Run: `uv run pytest tests/domain/analysis/test_defensives.py -q`
Expected: PASS.

Run: `uv run pytest tests/domain/analysis/ -q`
Expected: FAIL in `test_encounter_service.py::test_a_fight_with_nothing_in_it_produces_only_never_cast_defensives`
on `assert findings`. That is Step 8's subject.

- [ ] **Step 8: Rewrite the empty-fight test, which now makes a stronger claim**

In `tests/domain/analysis/test_encounter_service.py`, replace the test. An empty fight used to
produce never-cast rows; now it genuinely produces nothing, and the leak check that was the
test's real content gets sharper:

```python
def test_a_fight_with_nothing_in_it_produces_nothing() -> None:
    """An empty fight invents nothing it lacks data for.

    Every claim this service can make needs evidence an empty fight has none
    of: a death, a landed or kicked enemy cast, a consumable, or a ceiling
    computed from an actual cast. With no casts there is no ceiling to judge
    and nothing else to report, so the honest answer is silence.
    """
    findings = analyse_encounter(a_loaded_encounter(), DEFENSIVES, Consumables())

    assert findings == [], f"an empty fight has no evidence for: {[f.id for f in findings]}"
```

In the same file, `test_a_death_is_reported_and_located_against_the_fight` carries a comment
explaining the rank tie-break in terms of `defensives.never.*`. The assertion
(`findings[0].id == "deaths.total"`) still holds; rewrite the comment so it does not explain
the ordering with a family that no longer exists:

```python
    # deaths.total carries a seconds_lost and the defensives families do not,
    # so rank_findings' (None-last) key puts it first deterministically, not by
    # insertion luck.
```

- [ ] **Step 9: Follow the family through the report layer**

`src/wowperf/domain/report/finding_tooltip.py:14`:

```python
DEFENSIVE_FAMILIES = ("defensives.ceiling.",)
"""The family whose panel is measured here rather than carried on the finding.

It names one ability of one player over one run, which is what
`run_ability_tooltip` already answers for a death card. A ledger card differs
only in passing the whole run instead of a run-up.
"""
```

`src/wowperf/domain/report/ledger.py:61-64` — the comment explaining `PLACEMENTS` ordering
names the retired family. Rewrite so it names only surviving ones; **the entries themselves do
not change.**

```python
Unlike `NESTS_INSIDE`, the entries here overlap on purpose -- `defensives.unused.`
is a death-shaped claim, while `defensives.ceiling.` is a claim about the whole
run and falls through to the bare `defensives.` -- so order
```

`src/wowperf/domain/report/raid_ledger.py:35-37` — the same rewrite, reading "about the whole
fight" rather than "the whole run", matching the wording already there.

- [ ] **Step 10: Follow the family through the report tests**

`tests/domain/report/test_finding_tooltip.py` — delete the `NEVER_ID` constant at `:20` and
the whole of `test_a_never_cast_defensive_gets_the_same_panel_as_a_ceiling_one` at `:71`. With
one family left, "both families take the same builder" is not a claim that can be made.

`tests/domain/report/test_build_observations.py:77` — the fixture uses a retired id. Repoint
it to the surviving family, keeping it a group-rows finding so the union it feeds is unchanged:

```python
        a_finding("defensives.ceiling.emberkin.45438",
                  title="Emberkin used Ice Block 1 of a possible 7 times"),
```

`tests/domain/report/test_build_placement.py:68-74` — replace the three retired ids. The
slug-collision guard is still real and still worth keeping; only the family carrying it
changes:

```python
    "defensives.ceiling.emberkin.45438": "group_rows",
    # A player whose display name slugs to a word another defensives family
    # uses. The `ceiling` segment is what keeps the player out of the position a
    # claim is read from; without it this id would match `defensives.unused.`
    # and file a whole-run row on the Deaths tab.
    "defensives.ceiling.unused.45438": "group_rows",
    "defensives.ceiling.never.45438": "group_rows",
```

Note the existing bare `"defensives.ceiling.45438": "group_rows"` entry on the following line
stays as it is.

`tests/domain/report/test_ledger.py` — `:30`, `:35`, `:56` and `:81` use
`"Emberkin never cast Ice Block"` as *title text* to exercise title cutting, not the family.
The cutting logic does not care, but a fixture quoting a sentence the tool no longer writes is
misleading. Replace the title text with one the tool does produce, keeping each test's
existing expected split intact:

- `:30`/`:35`: title `"Emberkin used Ice Block 1 of a possible 7 times"`, expected cut
  `"Emberkin used ", "Ice Block", " 1 of a possible 7 times"`
- `:56`: title `"Ice Block was ready; Emberkin used Ice Block 1 of a possible 7 times"`
- `:81`: title `"Stonewake used Ice Block 1 of a possible 7 times"`

Read each assertion before editing and keep the three-part cut consistent with what that test
asserts; if a test's expectation cannot be preserved under the new title, **stop and raise it**
rather than weakening the assertion.

`tests/domain/report/test_raid_ledger.py` — remove `"defensives.never.emberkin.0",` from
`RAID_FAMILIES` at `:34` and `"defensives.never.",` from `_FAMILY_PREFIXES` at `:62`. The
comment at `:328` naming `analyse_defensives` follows the rename.

- [ ] **Step 11: Run the full suite**

Run: `uv run pytest`
Expected: PASS. The count drops by the seven tests deleted across Steps 1 and 10.

If `test_the_family_list_matches_what_the_service_emits` fails, `RAID_FAMILIES` and the
service disagree — that test is the guard for exactly this change, so read what it reports
rather than editing the list until it passes.

- [ ] **Step 12: Confirm no reference to the family survives**

Run:
```bash
grep -rn 'defensives\.never' src tests docs/how-it-works.md
```
Expected: no matches. `docs/plans/` is excluded deliberately — those are a historical record
and are not edited.

Use the `Grep` tool rather than shell `grep` if the pattern needs quotes: a `grep` pattern
containing a literal double quote can silently return `0` on this machine, and a zero then
reads as a measurement.

- [ ] **Step 13: Run the linters**

Run: `uv run ruff check .`
Expected: clean.

Run: `uv run mypy`
Expected: clean. Watch for an unused-import error in `service.py` or `encounter_service.py` if
Step 6 missed one.

- [ ] **Step 14: Commit**

```bash
cat > /tmp/msg2.txt <<'EOF'
Stop claiming a defensive was never pressed

The finding fired once per player per listed defensive they did not cast, which
made it 203 of the 773 findings across the fifteen reports on disk - 26.3%, and
59.8% of one raid report on its own. It was the largest family the tool
produced.

It was also redundant. Matched ability by ability against the death cards, 158
of those 203 were already an `unseen` row for that exact ability on that
player's own card, with nothing in either residual bucket. The card's wording,
"not seen this run", is the same run-wide claim in a place a reader can weigh it
against the three other states.

The 45 that remain belong to players with no death card at all. Each says the
player survived the whole run and never pressed this defensive, which is the
weakest ground the claim had, and the talent ambiguity it always disclosed
cannot be closed: combatantInfo carries talentTree, not talents, and its ids are
talent-entry ids rather than spell ids.

The surviving half of the analyser is renamed for what it now does.

Design: docs/plans/2026-09-20-retire-defensives-never-design.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

```bash
/mingw64/bin/git add -A src tests
```

```bash
/mingw64/bin/git commit -F /tmp/msg2.txt
```

---

## Task 3: Stop advertising the claim in the documentation

**Files:**
- Modify: `docs/how-it-works.md:462`
- Modify: `.claude/skills/mplus-analysis/SKILL.md:14`, `:69`

**Interfaces:**
- Consumes: nothing
- Produces: nothing

- [ ] **Step 1: Correct the module table in `how-it-works.md`**

Line 462 currently reads:

```
| `defensives.py` | never cast, cast far below the cooldown ceiling, or off cooldown at a death |
```

Replace with:

```
| `defensives.py` | cast far below the cooldown ceiling, or off cooldown at a death |
```

- [ ] **Step 2: Correct the two claims in the analysis skill**

`.claude/skills/mplus-analysis/SKILL.md:14` lists "a defensive never pressed" among the things
the tool says. Remove that item from the list, leaving the rest of the sentence intact.

`:69` reads "the log emits no cooldown-reset events, so a defensive that was never pressed may
genuinely have been unavailable". The caveat is still true and still applies — to the death
card's `unseen` state and to `defensives.unused`. Rewrite it to attach to those rather than to
the retired finding.

**Leave `:277` alone.** That is the `compare.spells.missing` finding's "never cast it", a
different family that this work does not touch.

- [ ] **Step 3: Verify no documentation still promises the finding**

Run:
```bash
grep -rn 'never pressed\|never cast' docs/how-it-works.md .claude/skills/mplus-analysis/SKILL.md
```
Expected: one match only — `SKILL.md:277`, the comparison family.

- [ ] **Step 4: Commit**

```bash
cat > /tmp/msg3.txt <<'EOF'
Stop documenting a defensives claim the tool no longer makes

Two live documents still promised a finding for a defensive never pressed. The
cooldown-reset caveat beside it is still true, so it moves to the claims it
still qualifies - the death card's unseen state and defensives.unused - rather
than being deleted with the finding.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

```bash
/mingw64/bin/git add docs/how-it-works.md .claude/skills/mplus-analysis/SKILL.md
```

```bash
/mingw64/bin/git commit -F /tmp/msg3.txt
```

---

## Task 4: Verify the removal against the fifteen real reports

**Why.** `CLAUDE.md`'s live-run invariant asks that a judgement be exercised against a real log
and its state distribution reported. This judgement is being removed, so the mirror applies:
every report must come back with **exactly `total - never` findings and every other family
unchanged count for count**. Design §6 makes this the falsifier — a family that moves by even
one stops the work.

**Files:**
- Create: nothing in the repository. The comparison script lives in the scratchpad.

**Interfaces:**
- Consumes: the retired analyser's absence, from Task 2
- Produces: the measurement recorded in the design document's §7

- [ ] **Step 1: Record the before picture from the reports already on disk**

`out/` holds fifteen `*.findings.json` built before this change. **Do not regenerate them
yet.** Copy the whole directory to the scratchpad so the comparison has a fixed baseline:

```bash
uv run python -c "import shutil; shutil.copytree('out', 'OUT_BASELINE_PATH')"
```

Substitute the session scratchpad directory for `OUT_BASELINE_PATH`. `rm` is denied on this
machine but `shutil` works.

- [ ] **Step 2: Regenerate every report against the warm cache**

Each findings file names the command that made it. Derive the list from the files themselves
rather than from memory, and **print it for review before running anything**:

```bash
uv run python -c "
import json, pathlib
for p in sorted(pathlib.Path('OUT_BASELINE_PATH').glob('*.findings.json')):
    b = json.loads(p.read_text(encoding='utf-8'))
    code, fight = b['report_code'], b['fight_id']
    raid = 'boss_name' in b and b.get('boss_name')
    players = {f.get('player_slug') for f in b['findings'] if f.get('player_slug')}
    every = '--all-players' if len(players) > 1 else ''
    print(f\"{'raid' if raid else 'analyze'} {code} --fight {fight} {every} --out out\")
"
```

`boss_name` is what tells a raid report from a Mythic+ one; more than one distinct
`player_slug` is what tells a whole-roster run from a single-player one. If any line looks
wrong against the file it came from, fix the derivation before running the batch.

Then run each printed command as `uv run wowperf <line>`. The cache is warm, so this should
cost close to nothing; **report whatever each command prints for its point spend** rather than
assuming zero.

If a command tries to fetch and credentials are absent, stop and say so — do not spend the
hourly budget to make a verification pass.

- [ ] **Step 3: Compare, family by family**

Write this to the scratchpad and run it from the repository root:

```python
# ABOUTME: Confirm retiring defensives.never changed that family and nothing else.
# ABOUTME: Compares regenerated out/ against the pre-change baseline, per family.
import collections
import json
import pathlib
import sys

BASELINE = pathlib.Path(sys.argv[1])
CURRENT = pathlib.Path("out")


def families(path: pathlib.Path) -> collections.Counter[str]:
    body = json.loads(path.read_text(encoding="utf-8"))
    counted: collections.Counter[str] = collections.Counter()
    for finding in body["findings"]:
        fid = finding.get("id", "")
        parts = fid.split(".")
        counted[".".join(parts[:2]) if fid.startswith("defensives.") else parts[0]] += 1
    return counted


bad = 0
for before_path in sorted(BASELINE.glob("*.findings.json")):
    after_path = CURRENT / before_path.name
    if not after_path.exists():
        print(f"MISSING  {before_path.name} was not regenerated")
        bad += 1
        continue
    before, after = families(before_path), families(after_path)
    never = before.get("defensives.never", 0)
    moved = {
        family: (before.get(family, 0), after.get(family, 0))
        for family in set(before) | set(after)
        if family != "defensives.never" and before.get(family, 0) != after.get(family, 0)
    }
    total_before, total_after = sum(before.values()), sum(after.values())
    ok = after.get("defensives.never", 0) == 0 and not moved and total_after == total_before - never
    print(
        f"{'ok ' if ok else 'BAD'} {before_path.name:34} "
        f"{total_before:4} -> {total_after:4}  (never {never})"
        + (f"  MOVED: {moved}" if moved else "")
    )
    bad += 0 if ok else 1

print(f"\n{'all fifteen clean' if not bad else f'{bad} report(s) failed the check'}")
```

Expected: every line `ok`, and `all fifteen clean`. Any `MOVED` entry is design §6's falsifier
firing — **stop and raise it**; do not adjust the script.

- [ ] **Step 4: Confirm the Deaths tab did not move**

Nothing in this work touches `recap.py`, so the `unseen` rows must be identical. Compare the
rendered HTML:

```bash
uv run python -c "
import pathlib, re, sys
base = pathlib.Path(sys.argv[1])
for b in sorted(base.glob('*.html')):
    a = pathlib.Path('out')/b.name
    count = lambda p: len(re.findall(r'<li class=\"unseen\"', p.read_text(encoding='utf-8')))
    before, after = count(b), count(a)
    print(('ok ' if before == after else 'BAD'), b.name, before, '->', after)
" OUT_BASELINE_PATH
```

Expected: every line `ok`. A change here means the death card moved, which this work does not
do — stop and raise it.

- [ ] **Step 5: Record the result in the design document**

Add a short subsection to `docs/plans/2026-09-20-retire-defensives-never-design.md` under §7,
stating the date, the fifteen reports, the before and after totals, that no other family moved,
that the `unseen` counts were unchanged, and what the regeneration cost in points. Numbers
only — no player names.

- [ ] **Step 6: Run the gate one final time, in this checkout**

Run: `uv run pytest`
Expected: PASS.

Run: `uv run ruff check .`
Expected: clean.

Run: `uv run mypy`
Expected: clean.

Report the actual counts these print. Do not relay a number from an earlier step.

- [ ] **Step 7: Commit**

```bash
cat > /tmp/msg4.txt <<'EOF'
Record what retiring defensives.never did to fifteen real reports

The design made this the falsifier: every report must come back with exactly
its total less its never count, and every other family unchanged. Regenerating
all fifteen against a warm cache and comparing family by family is what turns
that from an intention into a measurement.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

```bash
/mingw64/bin/git add docs/plans/2026-09-20-retire-defensives-never-design.md
```

```bash
/mingw64/bin/git commit -F /tmp/msg4.txt
```

---

## Notes for the implementer

**Do not add a compatibility shim.** No deprecation alias for `analyse_defensives`, no flag to
re-enable the family. Nothing outside this repository imports it.

**Do not touch `data/defensives.toml`.** Every entry still feeds the ceiling claim,
`defensives.unused`, and the death card's states. An ability that now appears in no finding is
still doing work.

**Do not touch `recap.py` or the death card.** The `unseen` state is the surviving form of
this claim and already reads correctly. Task 4 Step 4 checks it did not move.

**If a test fails in a way this plan does not predict, stop and raise it.** Do not delete it,
and do not weaken an assertion to get to green. Every failure this plan expects is named at
the step that causes it.
