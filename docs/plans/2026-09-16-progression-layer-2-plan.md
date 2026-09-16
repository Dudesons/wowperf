# Progression Layer 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wowperf progression` reads each qualifying attempt's deaths and damage taken, and says
what repeated across the night: the phase attempts ended in, how long each collapse took, which
specialisation died first, and which abilities were landing when attempts fell apart.

**Architecture:** Layer 1 already builds a `Progression` from one `Fights` query. This adds a
second fetch pass that deepens each qualifying attempt into a `LoadedEncounter` carrying deaths
and damage taken, and four analysers over the resulting `LoadedProgression`. No new domain
concept, no new event type, no report. Every finding is withheld rather than guessed when the data
does not support it.

**Tech Stack:** Python 3.12, pydantic frozen models, typer CLI, httpx + GraphQL against the
Warcraft Logs v2 client API, pytest, ruff, mypy strict. `uv` is the only toolchain.

**Spec:** `docs/plans/2026-09-16-progression-analysis-design.md` — read §4.1, §4.2, §4.4, §5.2,
§6, §9.1, §10, §11, §12. Read the corrections dated 2026-09-16 in §2.3, §2.6, §5.1 and §5.2:
they change what this plan builds.

---

## What the measurement already settled, before this plan was written

Design §12 says plan 2 "opens with §9.1's measurement, and its first task is to settle open item 1
before any code depends on the answer". **That measurement has been run and committed** (`70aeb50`)
rather than left as a task, because its outcome decides which tasks exist at all. Its readings are
in `.claude/skills/wcl-api/SKILL.md` under three new dated sections. The three results that bind
this plan:

1. **Both player-sourced findings are cut.** Across 19 boss fights and 8 encounters, the
   player-to-player debuff stream is ordinary class debuffs (64 of 67 abilities are applied by
   exactly one class), and friendly-sourced damage is 89.9% self-damage with 95.7% of the
   remainder confined to one encounter where it is a raid damaging a raid member the encounter
   turned hostile. §9.1 says cut rather than hedge. **So this plan builds no `PlayerDebuffEvent`,
   sends no `Debuffs` query, and emits no `progression.player_sourced` finding.**
2. **`source_id` on `DamageTakenEvent` already exists and is already populated**, since `fd90170`
   on 2026-09-11. Nothing adds it. Task 5 reads it to *exclude* friendly-sourced hits.
3. **`lastPhase` is a `PhaseMetadata.id`** on all 8 encounters measured, so a phase name can be
   looked up by matching it against `Progression.phases[].id`. **`lastPhaseAsAbsoluteIndex` counts
   transitions, not phases**, and reading it as a phase number is wrong on 5 of those 8. One
   encounter reports a `lastPhase` that is not its last transition's id, so **read `lastPhase`,
   never `phase_transitions[-1].id`.**

## Global Constraints

Every task's requirements implicitly include this section.

- **The domain performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`,
  or touches the network, disk or a template. Adapters do that.
- **Every finding carries a confidence badge** — `Confidence.MEASURED`, `DERIVED` or `INFERRED`.
  A finding without one is a bug.
- **No boss is encoded.** No per-encounter rule, no phase table, no mechanic list. Phase names
  come from the API or the claim is not made.
- **Never name a mechanic as missed.** Presence and counts only.
- **Never invent an API field name.** `.claude/skills/wcl-api/SKILL.md` is the reference; every
  field this plan uses is already recorded there. If you need one that is not, verify it against
  the live schema first and add a dated row.
- **No real character name reaches `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`,
  `Bríala`, `Кириллица`, plus the accent-stripped spelling of one where two names must reduce to
  one slug.
- **The twenty players on report `cW38jmwdnZfbHVL4` are real people.** Refer to them by class,
  spec, role or index — in code, in tests, in commit messages and in documents. Never print a
  findings file or a rendered page without first proving the payload carries no name.
- **No assertion may survive deleting the arithmetic or the string it claims to check.** This
  repository's stated failure mode is a test that could never have failed. Before you commit a
  test, change the thing it checks and watch it fail.
- **mypy runs `strict = true` over `src` AND `tests`, with no pydantic plugin.** `warn_unused_ignores`
  is on, so a `# type: ignore` that turns out unnecessary is an error. Do not add one speculatively.
- **ruff selects `E, F, I, UP, B` at line-length 100.**
- **NEVER use `--no-verify`, `--no-hooks` or `--no-pre-commit-hook`.**
- **Commit messages are plain ASCII** (a `§` lands as `SS`) and end with a blank line then
  exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Gate before every commit: `uv run pytest`, `uv run ruff check .`, `uv run mypy`. Baseline on
  this branch is **2022 passed, 18 deselected; ruff clean; mypy clean over 229 source files**.
  `uv` is off PATH in Bash — use `/c/Users/damien/.local/bin/uv.exe`.

---

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `src/wowperf/domain/progression.py` | Modify: `LoadedProgression.loaded` typed, and the attempt/loaded pairing | 2 |
| `src/wowperf/domain/analysis/progression_service.py` | Modify: entry point takes `LoadedProgression`; Layer 1 findings unchanged | 1, 3, 4, 5, 6 |
| `src/wowperf/domain/analysis/progression_repeats.py` | Create: the four Layer 2 analysers, pure | 1, 3, 4, 5 |
| `src/wowperf/adapters/wcl/repository.py` | Modify: `load_progression_attempts`, the narrow per-attempt fetch | 2 |
| `src/wowperf/cli.py` | Modify: `progression` deepens and reports the new counts | 6 |
| `tests/domain/progression_fixtures.py` | Create: shared builders, extending `an_attempt` | 1, 3 |
| `tests/domain/analysis/test_progression_repeats.py` | Create: the analysers, one test file | 1, 3, 4, 5 |
| `tests/domain/test_loaded_progression.py` | Create: the aggregate's pairing and guards | 2 |
| `tests/adapters/wcl/test_load_progression_attempts.py` | Create: the fetch shape and its operation count | 2 |
| `tests/e2e/test_progression_e2e.py` | Modify: the real night's Layer 2 claims | 7 |

`progression_repeats.py` is a new file rather than more of `progression_service.py`: the service
file is the entry point and Layer 1, and four more analysers would double it. Files that change
together live together — all four Layer 2 analysers read the same `LoadedProgression` and share
the collapse window.

---

## Rulings made while writing this plan

Recorded here so a reviewer can reject them rather than discover them.

**R1 — The command always deepens; no new flag.** Measured 2026-09-16: an event stream costs about
1.00 points a fight, so an eight-attempt night reading two streams is around 20 points of 3600.
The design's 40-to-60 projection priced a third stream this plan does not send. *Cost if wrong:* a
user wanting metadata only pays ~20 points instead of ~3.

**R2 — The "run-up to the end" in §5.2 is the collapse window**: from the attempt's first death to
its end. No new constant, and the same window `progression.collapse` already reports. An attempt
with no death has no run-up and contributes nothing to `progression.repeat.ability`. *Cost if
wrong:* on an attempt where everyone died at once the window is near zero and the finding says
little — which is honest, and `progression.collapse` says so in the same breath.

**R3 — `progression.repeat.ability` excludes hits whose `source_id` is a friendly player other
than the victim.** Measured: on one encounter those are entirely teammates' class abilities
landing on a raid member the encounter turned hostile, and naming them would report a rogue's
Rupture as a repeating threat. Self-damage (`source_id == actor_id`) is excluded by the same
clause. *Cost if wrong:* an encounter where a passed mechanic really does the damage goes
unreported — which is exactly the feature §9.1 cut, so this loses nothing that was going to ship.

**R4 — The severity table needs no new key.** `family_of` in `severity.py` splits on the first
dot, so `progression.repeat.phase` and `progression.collapse` are both family `progression`, which
`SEVERITY_BY_FAMILY` already carries at 1. Do not add `progression.repeat` or any sibling.

**R5 — `progression.repeat.first_death` reports a specialisation, never a name.** CLAUDE.md
sanctions class, spec, role and index. `Player` carries `class_name` and `spec` and no role, so
the finding says "Frost Death Knight" and counts.

**R6 — `analyse_progression` changes signature** from `Progression` to `LoadedProgression`. Layer
1's four findings are untouched and read `loaded.progression`. *Cost if wrong:* one call site.

---

### Task 1: `progression.repeat.phase`

The one Layer 2 finding that needs no fetch: `Encounter.last_phase` and `Progression.phases`
arrived with Layer 1's single query. Building it first means the analyser module exists before
anything has to be loaded into it.

**Files:**
- Create: `src/wowperf/domain/analysis/progression_repeats.py`
- Create: `tests/domain/analysis/test_progression_repeats.py`
- Create: `tests/domain/progression_fixtures.py`

**Interfaces:**
- Consumes: `Progression` and `Phase` from `wowperf.domain.progression` / `wowperf.domain.phases`;
  `Finding`, `Confidence` from `wowperf.domain.findings`.
- Produces: `repeat_phase(progression: Progression) -> Finding | None`, imported by Task 6.

**Requirements:**

- Silent (return `None`) when `progression.separates_wipes` is `False` — §5.2 gates every phase
  claim on it, and the API states it per encounter.
- Silent when `progression.phases` is empty, or when fewer than two attempts carry a `last_phase`
  that is not `None` and not `0`. `0` means a boss with no phases (measured), not a missing
  reading.
- The phase **name** comes from matching `last_phase` against `Phase.id`. Where no phase matches,
  say "phase {id}" rather than inventing a name.
- Confidence `MEASURED`: the report states the phase outright.
- The title names the most common ending phase and how many attempts ended there. The detail must
  not say the raid failed anything.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/analysis/test_progression_repeats.py
from wowperf.domain.analysis.progression_repeats import repeat_phase
from wowperf.domain.findings import Confidence

from tests.domain.progression_fixtures import a_series as series
from tests.domain.test_progression import an_attempt


def attempt(fight_id: int, *, last_phase: int | None = None):
    """One qualifying attempt, 200 seconds long, at a stated ending phase."""
    return an_attempt(fight_id, 50.0, 200.0, last_phase=last_phase)


def test_names_the_phase_most_attempts_ended_in():
    finding = repeat_phase(
        series(
            attempt(1, last_phase=2),
            attempt(2, last_phase=2),
            attempt(3, last_phase=3),
        )
    )
    assert finding is not None
    assert "Intermission: Tide" in finding.title
    assert "2 of 3" in finding.title
    assert finding.confidence is Confidence.MEASURED


def test_is_silent_when_the_api_says_phases_do_not_separate_wipes():
    assert (
        repeat_phase(
            series(attempt(1, last_phase=2), attempt(2, last_phase=2), separates_wipes=False)
        )
        is None
    )


def test_is_silent_when_the_boss_has_no_phase_table():
    assert repeat_phase(series(attempt(1, last_phase=2), attempt(2, last_phase=2), phases=())) is None


def test_treats_phase_zero_as_a_boss_without_phases_not_a_reading():
    assert repeat_phase(series(attempt(1, last_phase=0), attempt(2, last_phase=0))) is None


def test_is_silent_below_two_attempts_with_a_phase():
    assert repeat_phase(series(attempt(1, last_phase=2), attempt(2, last_phase=None))) is None


def test_names_an_unmatched_phase_id_by_number_rather_than_inventing_one():
    finding = repeat_phase(series(attempt(1, last_phase=9), attempt(2, last_phase=9)))
    assert finding is not None
    assert "phase 9" in finding.title


def test_says_nothing_about_failure():
    finding = repeat_phase(series(attempt(1, last_phase=3), attempt(2, last_phase=3)))
    assert finding is not None
    text = f"{finding.title} {finding.detail}".lower()
    for banned in ("fail", "failed", "missed", "mistake", "wrong"):
        assert banned not in text
```

- [ ] **Step 2: Create the shared fixture module**

**Do not write a new `attempt()` helper and do not create a conftest.**
`tests/domain/test_progression.py` already has `an_attempt(fight_id, remaining, seconds,
**overrides)`, and `tests/domain/analysis/test_severity.py` already imports across packages from
it — that is this repo's precedent, and a second builder for the same aggregate is duplication a
reviewer will reject.

Create `tests/domain/progression_fixtures.py`, a plain module (not a conftest — an explicit
import of a `conftest.py` risks pytest loading it twice):

```python
# ABOUTME: Shared builders for progression tests: one attempt, one deepened attempt, one series.
# ABOUTME: Timestamps are offsets from the attempt's own start, because an_attempt offsets by id.

from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import DamageTakenEvent, Death
from wowperf.domain.model import Player
from wowperf.domain.phases import Phase
from wowperf.domain.progression import LoadedProgression, Progression

from tests.domain.test_progression import an_attempt

PHASES = (
    Phase(id=1, name="The Gathering"),
    Phase(id=2, name="Intermission: Tide", is_intermission=True),
    Phase(id=3, name="The Drowning"),
)


def a_series(
    *attempts: Encounter,
    separates_wipes: bool = True,
    phases: tuple[Phase, ...] = PHASES,
) -> Progression:
    """A `Progression` around already-built attempts, with nothing discarded."""
    return Progression(
        report_code="abc123",
        encounter_id=3492,
        boss_name="Emberkin",
        difficulty=5,
        size=20,
        phases=phases,
        separates_wipes=separates_wipes,
        attempts=attempts,
    )
```

Tasks 3, 4 and 5 add `a_loaded_attempt` and `a_loaded_series` to this same module. **Task 1 adds
only `a_series`** — the phase finding needs no events.

**The timestamp convention, which Tasks 3-5 depend on:** `an_attempt` sets
`start_ms = fight_id * 1_000_000`, so an attempt's window is not at zero. Every death and damage
timestamp a fixture places is therefore written as an **offset from that attempt's own
`start_ms`**, never as an absolute figure. An absolute 70_000 against fight 1 is 930 seconds
*before* the attempt began.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_progression_repeats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.domain.analysis.progression_repeats'`

- [ ] **Step 4: Write the implementation**

```python
# src/wowperf/domain/analysis/progression_repeats.py
# ABOUTME: What repeated across a night's attempts: the phase, the collapse, who fell first.
# ABOUTME: Counts and presence only -- naming a mechanic as missed is the one claim forbidden here.

from collections import Counter

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import Progression


def repeat_phase(progression: Progression) -> Finding | None:
    """How many attempts ended in the same phase, or nothing.

    Gated on `separates_wipes`, which is the API's own opinion about whether
    phase is a meaningful way to group this encounter's attempts. Two of the
    eight encounters measured on 2026-09-16 report no phase table at all and
    two more report `separatesWipes: false`, so silence is the common case
    rather than the defensive one.

    `last_phase` is a `PhaseMetadata.id` -- measured across all eight, and the
    reason the name is looked up rather than derived from `phase_transitions`,
    whose last entry disagreed with `last_phase` on one of them.
    """
    if not progression.separates_wipes or not progression.phases:
        return None

    ended_in = [
        a.last_phase for a in progression.attempts if a.last_phase is not None and a.last_phase
    ]
    if len(ended_in) < 2:
        return None

    phase_id, count = Counter(ended_in).most_common(1)[0]
    names = {phase.id: phase.name for phase in progression.phases}
    name = names.get(phase_id, f"phase {phase_id}")

    return Finding(
        id="progression.repeat.phase",
        title=f"{count} of {len(ended_in)} attempts ended in {name}",
        detail=(
            f"The report groups this encounter's attempts by phase, so where an attempt "
            f"ended is a fact it states outright. {count} of the {len(ended_in)} attempts "
            f"carrying a phase ended in {name}. This counts where attempts ended and says "
            "nothing about why."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{count} of {len(ended_in)} attempts ended in {name}",
            f"phase table carries {len(progression.phases)} phases",
        ),
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/analysis/test_progression_repeats.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 6: Mutation-check the guards**

Do not skip this and do not commit the mutations. For each, make the change, run the file, confirm
a test fails, revert:

1. Change `if not progression.separates_wipes` to `if False` — expect
   `test_is_silent_when_the_api_says_phases_do_not_separate_wipes` to fail.
2. Change `and a.last_phase` to nothing (accept 0) — expect
   `test_treats_phase_zero_as_a_boss_without_phases_not_a_reading` to fail.
3. Change `len(ended_in) < 2` to `< 1` — expect `test_is_silent_below_two_attempts_with_a_phase`
   to fail.
4. Change `names.get(phase_id, f"phase {phase_id}")` to `names.get(phase_id, "the final phase")` —
   expect `test_names_an_unmatched_phase_id_by_number_rather_than_inventing_one` to fail.

- [ ] **Step 7: Gate and commit**

```bash
/c/Users/damien/.local/bin/uv.exe run pytest
```
```bash
/c/Users/damien/.local/bin/uv.exe run ruff check .
```
```bash
/c/Users/damien/.local/bin/uv.exe run mypy
```
```bash
/mingw64/bin/git add src/wowperf/domain/analysis/progression_repeats.py tests/domain/
```
```bash
/mingw64/bin/git commit -m "Count which phase a night's attempts ended in" -m "Gated on separatesWipes, which two of eight measured encounters report false and two more do not report at all, so silence is the ordinary case. The phase name is looked up from lastPhase against the phase table rather than taken from the last phase transition: one encounter measured 2026-09-16 disagrees between the two." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Deepen the attempts

The fetch pass Layer 2 needs, and the only task that touches an adapter. Two streams per
qualifying attempt and nothing else: no casts, no rankings, no talents, no healing windows. The
narrowness is the point — `load_encounter` fetches nine streams for one fight, and running that
per attempt is what would make this command expensive.

**Files:**
- Modify: `src/wowperf/domain/progression.py` (`LoadedProgression`)
- Modify: `src/wowperf/adapters/wcl/repository.py` (new method after `load_progression`)
- Create: `tests/domain/test_loaded_progression.py`
- Create: `tests/adapters/wcl/test_load_progression_attempts.py`

**Interfaces:**
- Consumes: `Progression` from Task 0's existing code; `LoadedEncounter` from
  `wowperf.domain.encounter`; `build_deaths`, `build_damage_taken` from
  `wowperf.adapters.wcl.ingest`; `DEATHS_QUERY`, `DAMAGE_TAKEN_QUERY` from
  `wowperf.adapters.wcl.queries`; `fetch_all_events` from `wowperf.adapters.wcl.pagination`.
- Produces:
  - `LoadedProgression.loaded: tuple[LoadedEncounter, ...]`
  - `LoadedProgression.attempts_with_events` — `tuple[LoadedEncounter, ...]`, the loaded attempts
    in pull order (Tasks 3, 4, 5 and 6 iterate this, never `loaded` directly).
  - `LoadedProgression.deepest_loaded: LoadedEncounter | None`
  - `WclRunRepository.load_progression_attempts(progression: Progression) -> LoadedProgression`

**Requirements:**

- `loaded` holds only attempts in `progression.attempts`. Discarded attempts are never deepened —
  they take no part in any figure the series reports, so fetching them would spend points on rows
  nothing reads.
- `attempts_with_events` returns them sorted by `encounter.start_ms`, so an analyser's notion of
  "earlier" matches Layer 1's.
- `deepest_loaded` returns the `LoadedEncounter` whose `encounter` is `progression.deepest`,
  matched **by `fight_id`**, or `None`. Do not match by model equality: pydantic compares frozen
  models by value, and two attempts with identical fields would collide.
- `build_deaths` takes `casts` to compute `seconds_until_next_action`. Pass `()`. That figure is a
  Mythic+ recap's, nothing in Layer 2 reads it, and fetching a casts stream per attempt would
  double the command's cost for a field nobody uses. Pass `()` for `pulls` too: an `Encounter`
  carries none, exactly as `load_encounter` does.
- One `_ability_dictionary` call for the whole command, not one per attempt. It is keyed by report
  code and cached, but a loop that calls it N times still reads the cache N times and muddies the
  operation count the test asserts.

- [ ] **Step 1: Write the failing aggregate tests**

```python
# tests/domain/test_loaded_progression.py
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.progression import LoadedProgression

from tests.domain.progression_fixtures import a_series
from tests.domain.test_progression import an_attempt


def loaded(*fight_ids, boss_percentages=None):
    """A series whose `loaded` tuple is deliberately in the reverse of pull order."""
    attempts = tuple(
        an_attempt(f, 50.0, 200.0, boss_percentage=(boss_percentages or {}).get(f))
        for f in fight_ids
    )
    return LoadedProgression(
        progression=a_series(*attempts),
        loaded=tuple(LoadedEncounter(encounter=a) for a in reversed(attempts)),
    )


def test_attempts_with_events_are_in_pull_order_however_they_were_loaded():
    series = loaded(1, 2, 3)
    assert [one.encounter.fight_id for one in series.attempts_with_events] == [1, 2, 3]


def test_deepest_loaded_is_the_attempt_that_got_furthest_not_the_last():
    series = loaded(1, 2, 3, boss_percentages={1: 60.0, 2: 12.5, 3: 55.0})
    deepest = series.deepest_loaded
    assert deepest is not None
    assert deepest.encounter.fight_id == 2


def test_deepest_loaded_is_none_when_no_attempt_carries_a_reading():
    assert loaded(1, 2).deepest_loaded is None


def test_deepest_loaded_follows_progression_deepest_not_load_order():
    # `loaded` is built in reverse, so a lookup that returns loaded[0] would
    # answer fight 3 here while progression.deepest names fight 2.
    series = loaded(1, 2, 3, boss_percentages={1: 60.0, 2: 12.5, 3: 55.0})
    deepest = series.deepest_loaded
    assert deepest is not None
    assert series.loaded[0].encounter.fight_id == 3
    assert series.progression.deepest is not None
    assert deepest.encounter.fight_id == series.progression.deepest.fight_id == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/test_loaded_progression.py -v`
Expected: FAIL — `AttributeError: 'LoadedProgression' object has no attribute 'attempts_with_events'`,
and a pydantic validation error on `loaded`, which is still `tuple[object, ...]`.

- [ ] **Step 3: Implement the aggregate**

In `src/wowperf/domain/progression.py`, add the import and replace `LoadedProgression` whole:

```python
from wowperf.domain.encounter import Encounter, LoadedEncounter
```

```python
class LoadedProgression(Frozen):
    """A `Progression` and the attempts that have been deepened.

    `loaded` carries only attempts in `progression.attempts`: a discarded
    attempt takes no part in any figure the series reports, so fetching its
    events would spend points on rows nothing reads.
    """

    progression: Progression
    loaded: tuple[LoadedEncounter, ...] = ()

    @property
    def attempts_with_events(self) -> tuple[LoadedEncounter, ...]:
        """The deepened attempts in pull order, whatever order they arrived in.

        Every Layer 2 analyser iterates this rather than `loaded`, so "earlier"
        and "later" mean the same thing here as they do in Layer 1's movement
        finding.
        """
        return tuple(sorted(self.loaded, key=lambda one: one.encounter.start_ms))

    @property
    def deepest_loaded(self) -> LoadedEncounter | None:
        """The deepened attempt that got furthest, matched by fight id.

        Not by model equality: pydantic compares frozen models by value, so two
        attempts identical in every field would be indistinguishable, and the
        one this returns would depend on iteration order.
        """
        deepest = self.progression.deepest
        if deepest is None:
            return None
        for one in self.loaded:
            if one.encounter.fight_id == deepest.fight_id:
                return one
        return None
```

- [ ] **Step 4: Run them to verify they pass**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/test_loaded_progression.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Write the failing adapter test**

`tests/adapters/wcl/test_load_progression.py` already builds a fake client; read it first and
reuse its fixtures rather than writing a second one. This test asserts three things: which
streams are sent, that discarded attempts are not deepened, and the operation count.

```python
# tests/adapters/wcl/test_load_progression_attempts.py
def test_deepens_every_qualifying_attempt_and_no_discarded_one(...):
    # Build a report with three fights at one encounter: two above the floor,
    # one below it. Load the progression, then load its attempts.
    series = repository.load_progression("abc123", 3492, 5)
    deep = repository.load_progression_attempts(series)

    assert [one.encounter.fight_id for one in deep.attempts_with_events] == [1, 2]
    assert len(series.discarded) == 1


def test_sends_only_deaths_and_damage_taken_per_attempt(...):
    # The operation names the fake client was asked for, in order.
    assert operations.count("Deaths") == 2
    assert operations.count("DamageTaken") == 2
    assert "Casts" not in operations
    assert "Debuffs" not in operations
    assert "Healing" not in operations
    assert operations.count("Abilities") == 1  # once for the command, not once per attempt


def test_carries_the_deaths_and_damage_the_streams_returned(...):
    first = deep.attempts_with_events[0]
    assert [death.actor_id for death in first.deaths] == [11]
    assert [hit.ability_id for hit in first.damage_taken] == [12345]
    assert first.damage_taken[0].source_id == 249
```

Fill these in against the existing fake client's shape — the assertions above are the claims that
must be made, and the fixtures are whatever that file already provides. **`Debuffs` must be
asserted absent**: it is the stream this plan deliberately does not send, and a later change that
quietly adds it should fail a test rather than a code review.

- [ ] **Step 6: Run it to verify it fails**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/wcl/test_load_progression_attempts.py -v`
Expected: FAIL — `AttributeError: 'WclRunRepository' object has no attribute 'load_progression_attempts'`

- [ ] **Step 7: Implement the loader**

In `src/wowperf/adapters/wcl/repository.py`, directly after `load_progression`:

```python
    def load_progression_attempts(self, progression: Progression) -> LoadedProgression:
        """Deepen every qualifying attempt: deaths and damage taken, nothing else.

        Two streams an attempt, against the nine `load_encounter` fetches for one
        fight. Measured 2026-09-16: an event stream costs about 1.00 points a
        fight whatever its size, so an eight-attempt night lands near 20 points
        of 3600 rather than the design's projected 40 to 60 -- which priced a
        debuff stream the measurement then cut.

        No casts stream. `build_deaths` uses casts only to time how long a dead
        player stayed out of the fight, which is a Mythic+ recap's figure and
        which nothing in Layer 2 reads; fetching one per attempt would double
        the command's cost for a field nobody looks at.
        """
        hits: list[bool] = []
        ability_names, _icons = self._ability_dictionary(progression.report_code, hits)

        def query(one_query: str, variables: dict[str, Any]) -> dict[str, Any]:
            return self._query(one_query, variables, hits)

        no_pulls: tuple[Pull, ...] = ()
        loaded: list[LoadedEncounter] = []
        for attempt in progression.attempts:
            event_variables = {
                "code": attempt.report_code,
                "fightId": attempt.fight_id,
                "startTime": float(attempt.start_ms),
                "endTime": float(attempt.end_ms),
            }
            player_names = {player.actor_id: player.name for player in attempt.players}
            deaths = build_deaths(
                fetch_all_events(query, DEATHS_QUERY, event_variables),
                no_pulls,
                (),
                player_names,
                ability_names,
            )
            damage_taken = build_damage_taken(
                fetch_all_events(query, DAMAGE_TAKEN_QUERY, event_variables),
                no_pulls,
                ability_names,
            )
            loaded.append(
                LoadedEncounter(
                    encounter=attempt, deaths=deaths, damage_taken=damage_taken
                )
            )

        return LoadedProgression(progression=progression, loaded=tuple(loaded))
```

Add `LoadedProgression` to the existing `from wowperf.domain.progression import ...` line. Check
whether `Pull`, `build_deaths`, `build_damage_taken`, `DEATHS_QUERY`, `DAMAGE_TAKEN_QUERY` and
`fetch_all_events` are already imported in this module before adding an import — `load_encounter`
uses all of them, so they should be.

- [ ] **Step 8: Run both test files to verify they pass**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/wcl/ tests/domain/test_loaded_progression.py -v`

- [ ] **Step 9: Mutation-check**

1. Change `for attempt in progression.attempts` to iterate `progression.attempts +
   progression.discarded` — expect `test_deepens_every_qualifying_attempt_and_no_discarded_one`
   to fail.
2. Move the `_ability_dictionary` call inside the loop — expect the `Abilities` count assertion to
   fail.
3. Change `deepest_loaded` to `return self.loaded[0] if self.loaded else None` — expect
   `test_deepest_loaded_follows_progression_deepest_not_load_order` to fail. Then change
   `attempts_with_events` to `return self.loaded` — expect
   `test_attempts_with_events_are_in_pull_order_however_they_were_loaded` to fail. Both fixtures
   build `loaded` in reverse precisely so these two mutations are reachable.

- [ ] **Step 10: Gate and commit**

```bash
/mingw64/bin/git commit -m "Deepen each qualifying attempt with its deaths and damage taken" -m "Two streams an attempt, against the nine load_encounter sends for one fight. Discarded attempts are never deepened: they take no part in any figure the series reports. No casts stream -- build_deaths uses casts only for how long a dead player stayed out, which nothing in Layer 2 reads, and one per attempt would double the cost for an unread field." -m "deepest_loaded matches by fight id rather than by model equality. Pydantic compares frozen models by value, so two attempts identical in every field would be indistinguishable and which one came back would depend on iteration order." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `progression.collapse`

Seconds from the first death to the end of the attempt. A slow bleed and a sudden detonation are
different problems wanting different fixes, and this is the one figure that separates them.

**Files:**
- Modify: `src/wowperf/domain/analysis/progression_repeats.py`
- Modify: `tests/domain/analysis/test_progression_repeats.py`

**Interfaces:**
- Consumes: `LoadedProgression`, `LoadedEncounter`.
- Produces:
  - `collapse_seconds(one: LoadedEncounter) -> float | None` — the window Task 5 also uses.
  - `collapse(series: LoadedProgression) -> Finding | None`

**Requirements:**

- `collapse_seconds` is `(encounter.end_ms - first death timestamp) / 1000`, or `None` when the
  attempt has no death. A kill with no deaths is the ordinary case for this returning `None`.
- The finding reports the **median** across attempts and the observed range, never a mean. This is
  the house style and `progression.cluster` already states why in its own detail text.
- Withheld entirely when fewer than two attempts have a collapse.
- Confidence `MEASURED`: both timestamps are read, not modelled.
- The detail names what the two ends of the range mean without naming a cause.

- [ ] **Step 1: Write the failing tests**

**Every timestamp below is an offset from the attempt's own start** (ruling R8). An attempt built
by `an_attempt(1, 50.0, 100.0)` runs from `1_000_000` to `1_100_000`, so `death_after_ms=70_000`
places the death at `1_070_000` and leaves a 30-second collapse.

```python
def test_collapse_seconds_is_first_death_to_the_end_of_the_attempt():
    one = a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(70_000, 90_000))
    assert collapse_seconds(one) == 30.0


def test_collapse_seconds_is_none_without_a_death():
    assert collapse_seconds(a_loaded_attempt(1, seconds=100.0, deaths_after_ms=())) is None


def test_collapse_reports_a_median_and_a_range_never_a_mean():
    finding = collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),   # 10.0s
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=(80_000,)),   # 20.0s
        a_loaded_attempt(3, seconds=100.0, deaths_after_ms=(10_000,)),   # 90.0s
    ))
    assert finding is not None
    assert "20" in finding.title              # the median, not the 40.0 mean
    assert "40" not in finding.title
    assert "10" in " ".join(finding.evidence)
    assert "90" in " ".join(finding.evidence)


def test_collapse_is_withheld_below_two_attempts_with_a_death():
    assert collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=()),
    )) is None


def test_collapse_counts_only_attempts_that_had_one():
    finding = collapse(a_loaded_series(
        a_loaded_attempt(1, seconds=100.0, deaths_after_ms=(90_000,)),
        a_loaded_attempt(2, seconds=100.0, deaths_after_ms=(80_000,)),
        a_loaded_attempt(3, seconds=100.0, deaths_after_ms=()),
    ))
    assert finding is not None
    assert "2 attempts" in finding.detail
```

**Add both helpers to `tests/domain/progression_fixtures.py`** (Task 1 created it). They are the
fixtures Tasks 4 and 5 extend, so give them the full signature now even though this task uses only
part of it:

```python
def a_loaded_attempt(
    fight_id: int,
    *,
    seconds: float = 200.0,
    remaining: float = 50.0,
    deaths_after_ms: tuple[int, ...] = (),
    damage_after_ms: tuple[tuple[int, int, int | None], ...] = (),
    players: tuple[Player, ...] = (),
    **overrides: object,
) -> LoadedEncounter:
    """One deepened attempt.

    `deaths_after_ms` and `damage_after_ms` are offsets from this attempt's own
    start, because `an_attempt` places the window at `fight_id * 1_000_000`.
    Each `damage_after_ms` entry is `(offset, ability_id, source_id)`; a
    `source_id` of None means the log named no source.

    Deaths are dealt round-robin to `players` where a roster is given, so a
    test that cares which actor died first can say so by ordering the roster.
    """


def a_loaded_series(*loaded: LoadedEncounter, **series_kwargs: object) -> LoadedProgression:
    """A `LoadedProgression` whose `progression.attempts` are these attempts' encounters."""
```

Use the sanctioned names only where a roster is built: `Emberkin`, `Stonewake`, `Bríala`,
`Кириллица`.

- [ ] **Step 2: Run to verify failure.** Expected: `ImportError: cannot import name 'collapse_seconds'`.

- [ ] **Step 3: Implement**

```python
def collapse_seconds(one: LoadedEncounter) -> float | None:
    """From the first death to the end of the attempt, or None if nobody died.

    The same window `repeat_ability` reads, so the two findings cannot disagree
    about when an attempt started falling apart.
    """
    if not one.deaths:
        return None
    first = min(death.timestamp_ms for death in one.deaths)
    return (one.encounter.end_ms - first) / 1000


def collapse(series: LoadedProgression) -> Finding | None:
    """How long each attempt took to fall apart once the first player died."""
    windows = [
        seconds
        for seconds in (collapse_seconds(one) for one in series.attempts_with_events)
        if seconds is not None
    ]
    if len(windows) < 2:
        return None

    middle = median(windows)
    return Finding(
        id="progression.collapse",
        title=f"Attempts took a median of {middle:.0f} seconds to fall apart",
        detail=(
            f"Measured across {len(windows)} attempts that had a death, from the first one "
            f"to the end of the attempt. The observed range ran {min(windows):.0f} to "
            f"{max(windows):.0f} seconds. A long window is a raid bleeding out and a short "
            "one is a raid losing the fight at once; they want different fixes, and this "
            "figure is the one that tells them apart. A median and a range, never an average."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{len(windows)} attempts with a death",
            f"range {min(windows):.0f} to {max(windows):.0f} seconds",
        ),
    )
```

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Mutation-check.** Replace `median(windows)` with `sum(windows) / len(windows)` and
      expect `test_collapse_reports_a_median_and_a_range_never_a_mean` to fail on the `"40" not in`
      assertion. Replace `min(death.timestamp_ms ...)` with `max(...)` and expect
      `test_collapse_seconds_is_first_death_to_the_end_of_the_attempt` to fail.

- [ ] **Step 6: Gate and commit.**

---

### Task 4: `progression.repeat.first_death`

Which specialisation died first, counted across attempts. A count, not an accusation.

**Files:**
- Modify: `src/wowperf/domain/analysis/progression_repeats.py`
- Modify: `tests/domain/analysis/test_progression_repeats.py`

**Interfaces:**
- Produces: `repeat_first_death(series: LoadedProgression) -> Finding | None`

**Requirements:**

- The first death of an attempt is the one with the lowest `timestamp_ms`. Ties: take the lowest
  `actor_id`, so the result is deterministic rather than dependent on stream order.
- The specialisation comes from matching `Death.actor_id` against `encounter.players[].actor_id`
  and reading `f"{player.spec} {player.class_name}"`. Where no player matches, the attempt
  contributes nothing — a death with no roster row is a pet or an unknown actor, not a raider.
- **Never print `Death.player_name` or `Player.name`.** The report holds real people. A test must
  assert the finding's text contains no roster name.
- Withheld below two attempts with an identified first death.
- Confidence `MEASURED`: the log states who died and when.
- The detail must say that a specialisation dying first is usually about where that role stands,
  not about the player — this is the finding most easily read as blame, and the design forbids
  that reading.

- [ ] **Step 1: Write the failing tests**, including:

```python
def test_counts_the_specialisation_that_died_first_most_often():
    finding = repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=0),
        loaded_attempt_with_roster(2, first_dead_index=0),
        loaded_attempt_with_roster(3, first_dead_index=1),
    ))
    assert finding is not None
    assert "Frost Death Knight" in finding.title
    assert "2 of 3" in finding.title


def test_never_prints_a_player_name():
    finding = repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=0),
        loaded_attempt_with_roster(2, first_dead_index=0),
    ))
    assert finding is not None
    text = f"{finding.title} {finding.detail} {' '.join(finding.evidence)}"
    for name in ("Emberkin", "Stonewake", "Bríala", "Кириллица"):
        assert name not in text


def test_a_death_with_no_roster_row_contributes_nothing():
    # Both attempts' earliest death is an actor absent from `players`.
    assert repeat_first_death(series_of(
        loaded_attempt_with_roster(1, first_dead_index=None),
        loaded_attempt_with_roster(2, first_dead_index=None),
    )) is None


def test_ties_resolve_by_actor_id_not_by_stream_order():
    forwards = repeat_first_death(series_of(tied_attempt(1, order="forwards"), tied_attempt(2, order="forwards")))
    backwards = repeat_first_death(series_of(tied_attempt(1, order="backwards"), tied_attempt(2, order="backwards")))
    assert forwards is not None and backwards is not None
    assert forwards.title == backwards.title
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** `repeat_first_death`, resolving ties on `(timestamp_ms, actor_id)`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Mutation-check.** Sort by `timestamp_ms` alone and confirm the tie test fails; emit
      `player.name` instead of the specialisation and confirm `test_never_prints_a_player_name`
      fails.
- [ ] **Step 6: Gate and commit.**

---

### Task 5: `progression.repeat.ability`

Which abilities were landing while attempts fell apart, stated as presence and a count.

**Files:**
- Modify: `src/wowperf/domain/analysis/progression_repeats.py`
- Modify: `tests/domain/analysis/test_progression_repeats.py`

**Interfaces:**
- Consumes: `collapse_seconds` from Task 3.
- Produces: `repeat_ability(series: LoadedProgression) -> Finding | None`

**Requirements:**

- The window is the collapse window (R2): from an attempt's first death to its end. An attempt
  with no death contributes nothing.
- **Exclude any hit whose `source_id` is a friendly player** — that is, whose `source_id` is in
  `{player.actor_id for player in encounter.players}` — including self-damage (R3). Measured
  2026-09-16: outside one anomalous encounter this population is 99 hits across 17 fights, and
  inside it, it is entirely teammates' class abilities landing on a raid member the encounter
  turned hostile.
- Count **attempts in which the ability appeared**, not hits. Presence and a count, per §5.2.
- Report only abilities present in **more than half** the attempts with a window, and at most the
  top five, so the finding is a short list rather than the whole damage table.
- **Never say a mechanic was missed, failed or avoidable.** A test asserts the banned vocabulary
  is absent, and the analyser's own prose must not trip it — check the words you write against the
  test's list before committing.
- Confidence `DERIVED`, not `MEASURED`: which hits count depends on the window, and the window is
  a modelling choice. The detail says so.
- Withheld below two attempts with a window.

- [ ] **Step 1: Write the failing tests**, including:

```python
def test_counts_attempts_an_ability_appeared_in_not_hits():
    # ability 100 lands 9 times in one attempt, ability 200 lands once in each of three.
    finding = repeat_ability(...)
    assert finding is not None
    assert "3 of 3" in finding.detail
    assert "Tidal Crush" in finding.detail          # the ability in three attempts
    assert "Rockfall" not in finding.detail          # the nine-hit, one-attempt ability


def test_excludes_hits_sourced_by_a_teammate():
    # Two abilities in every attempt's window: 300 sourced by a raider's actor
    # id, 301 sourced by an enemy. The finding must name 301 and not 300 --
    # asserting only the absence would pass if the finding were withheld
    # entirely, which "exclude everything" would also achieve.
    finding = repeat_ability(...)
    assert finding is not None
    assert "Soul Sever" in finding.detail          # ability 301, enemy-sourced
    assert "Blessing of Sacrifice" not in finding.detail   # ability 300, teammate-sourced


def test_excludes_self_damage():
    # As above, with source_id == the victim's own actor id on ability 400.
    # Assert the enemy-sourced ability is still named, so the test cannot pass
    # by the finding being withheld.
    ...


def test_only_counts_hits_inside_the_collapse_window():
    # ability 500 lands only before the first death.
    ...


def test_says_nothing_about_a_mechanic_being_missed():
    finding = repeat_ability(...)
    assert finding is not None
    text = f"{finding.title} {finding.detail}".lower()
    for banned in ("missed", "avoidable", "should have", "failed", "mistake"):
        assert banned not in text
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** Build the friendly actor id set per attempt from
      `one.encounter.players`, filter `one.damage_taken` to hits at or after the first death whose
      `source_id` is not in that set, and count distinct attempts per `ability_id`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Mutation-check.** Drop the `source_id` filter and confirm
      `test_excludes_hits_sourced_by_a_teammate` fails; count hits instead of attempts and confirm
      `test_counts_attempts_an_ability_appeared_in_not_hits` fails; widen the window to the whole
      attempt and confirm `test_only_counts_hits_inside_the_collapse_window` fails.
- [ ] **Step 6: Gate and commit.**

---

### Task 6: Wire Layer 2 into the analyser and the command

**Files:**
- Modify: `src/wowperf/domain/analysis/progression_service.py`
- Modify: `src/wowperf/cli.py`
- Modify: `tests/domain/analysis/test_progression_service.py`
- Modify: `tests/domain/analysis/test_severity.py`
- Modify: `tests/test_cli.py` — it already covers the `progression` command
- Modify: `tests/test_skills.py` if the command's `--help` text changes. That file checks each
  command's own section against its own `--help`, parametrized over `("analyze", "raid",
  "progression")`; a reworded docstring must be matched in
  `.claude/skills/analyzing-a-run/SKILL.md`.

**Interfaces:**
- `analyse_progression(series: LoadedProgression) -> list[Finding]` — signature change (R6).

**Requirements:**

- `analyse_progression` takes a `LoadedProgression`. Layer 1's four findings read
  `series.progression` and are otherwise untouched: do not reword or renumber them.
- Append the Layer 2 findings in this order, skipping any that returned `None`:
  `repeat_phase`, `repeat_first_death`, `repeat_ability`, `collapse`.
- The CLI calls `load_progression` then `load_progression_attempts`, and passes the result to
  `analyse_progression`. Ranking still goes through `rank_raid_findings`.
- The payload gains `attempts_deepened: len(deep.loaded)`. Nothing else: the payload names no
  player today and must not start.
- **`test_every_family_the_progression_path_emits_has_a_severity` in
  `tests/domain/analysis/test_severity.py` fires the real analyser** over
  `tests.domain.test_progression.a_measured_night()` and checks every id it emits. Task 6's
  signature change breaks it, and the repair is where the trap is: wrapping the night in a bare
  `LoadedProgression(progression=...)` with no `loaded` makes it compile and emit **only Layer 1's
  ids**, so the test would keep passing while covering none of the new ones. **Deepen the fixture**
  — give it loaded attempts carrying deaths and damage taken — and assert the emitted id set
  contains all four Layer 2 ids. Per R4 they all resolve through the single `progression` key; the
  test proves that rather than assuming it.
- The command's docstring says "Layer 1 only: it reads fight metadata and draws no external
  reference". That is now false. Rewrite it: it reads each qualifying attempt's deaths and damage
  taken, still draws no external reference, and still writes no HTML.

- [ ] **Step 1: Write the failing tests** — a service test that a `LoadedProgression` with two
      attempts emits both Layer 1 and Layer 2 findings, a service test that an empty
      `LoadedProgression` still emits Layer 1 and no Layer 2, the severity test extension, and a
      CLI test that the payload carries `attempts_deepened`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Run the whole gate.** Every existing caller of `analyse_progression` must compile;
      `uv run mypy` is what proves it.
- [ ] **Step 6: Commit.**

---

### Task 7: End to end, against the real night

**Files:**
- Modify: `tests/e2e/test_progression_e2e.py`

**Requirements:**

- Marked `e2e`, so it is deselected by the offline gate and runs only under
  `uv run pytest -m e2e` with credentials.
- Runs against the eight-attempt night the existing e2e already uses. Read that file first: it
  already pins the report, the encounter, the attempt count and the deepest attempt's fight id and
  scale. **Do not duplicate those assertions — add to them.**
- New assertions, each of which must be able to fail:
  - Seven attempts are deepened, and every one carries at least one damage-taken row. The night's
    shortest qualifying attempt is 88 seconds, so an attempt with no damage at all means a stream
    came back empty and the test should say so.
  - `progression.collapse` is present and its median is strictly between 0 and the longest
    attempt's duration.
  - `progression.repeat.phase` is present: encounter 3492 reports `separatesWipes: true` and four
    phases, measured 2026-09-16.
  - No finding's text contains any of the twenty rosters' names. Assert it by reading the roster
    from the loaded progression and checking each name is absent from every finding's title,
    detail and evidence — **not** by listing names in the test file.
  - The command spends fewer than 40 points. Measured cost is around 20 for this night; 40 leaves
    room for pagination without letting a third stream in unnoticed.
- **Never print the findings file.** If you need to see it, write a script that first proves the
  payload carries no roster key and no per-player field, as
  `scripts/show_findings.py` did for Layer 1.

- [ ] **Step 1: Read the existing e2e file and list what it already asserts.**
- [ ] **Step 2: Write the new assertions.**
- [ ] **Step 3: Run it with credentials.** Copy `.env` from the main checkout into the worktree,
      run `uv run pytest -m e2e -k progression -v`, then delete the copy with
      `uv run python -c "import pathlib; pathlib.Path('.env').unlink(missing_ok=True)"`. `rm` is
      denied by the permission layer here.
- [ ] **Step 4: Record the measured cost** in `.claude/skills/wcl-api/SKILL.md` as a dated row, and
      in this plan's completion note.
- [ ] **Step 5: Gate and commit.**

---

## Self-review

**Spec coverage.** §5.2 lists five findings. Four are built here (Tasks 1, 3, 4, 5); the fifth,
`progression.player_sourced`, is cut by the measurement §9.1 required and the cut is committed in
`70aeb50`. §4.4's damage half already existed and its debuff half is cut with the finding it
served. §4.1's "deepens only the attempts a layer asks for" is Task 2. §6's severity vocabulary is
R4 plus Task 6's test. §12's "opens with §9.1's measurement" is satisfied before Task 1.

**Placeholders.** Tasks 4, 5 and 6 give test names, assertions and requirements rather than every
line of fixture code, because their fixtures are extensions of helpers Tasks 1-3 create and
repeating them would invite drift between two copies. Every assertion that must exist is written
out. Task 2's adapter test is deliberately shaped rather than transcribed: its fixtures belong to
an existing file whose current contents the implementer must read.

**Type consistency.** `collapse_seconds` is defined in Task 3 and consumed in Task 5.
`attempts_with_events` and `deepest_loaded` are defined in Task 2 and consumed in Tasks 3, 4 and 5.
`repeat_phase` takes a `Progression`; the other three take a `LoadedProgression` — deliberate, as
the phase finding needs no events, and Task 6 calls it with `series.progression`.

**Known gaps, stated rather than hidden.**

- `Encounter.outcome` prints `f"wiped at {fight_percentage:.1f}%"` with no scale named, against
  §2.4's rule that every printed percentage names which one it is. Nothing in this plan reads it.
  Left alone as a separate change, because fixing it edits a string several slice-2 tests assert.
- `rank_raid_findings` ranks progression findings, so its name is wider than its subject. Renaming
  touches slice 2's call sites. Still a follow-up.
- `Encounter.last_phase_is_intermission` stays `bool`. Task 1 does not read it: given `last_phase`
  and the phase table, whether that phase is an intermission is a lookup, so the field is
  redundant here rather than wrong. The tri-state change waits for a consumer that needs it.
- The 5.0-point movement threshold in `progression_service.py` is still chosen rather than
  measured, and the fixture night clears it by 0.1 points. Nothing in this plan builds on
  `progression.movement`, so it stays as design open item 5.
