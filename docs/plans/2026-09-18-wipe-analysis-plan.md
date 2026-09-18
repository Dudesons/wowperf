# Wipe Analysis, Layer 1: the analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one boss fight's findings say where its cost fell, what killed the raid, and whether the attempt failed on execution or on damage.

**Architecture:** Every new analyser is a pure function in `src/wowperf/domain/`, reading data the raid path already fetches. Phase attribution comes from a new locator over the transitions the encounter already carries. The verdict is an internal reading and so lives under `domain/analysis/`, not `domain/comparison/`, which means "us against them".

**Tech Stack:** Python 3.12+, pydantic (`Frozen`), pytest, `uv` as the only toolchain.

**Spec:** `docs/plans/2026-09-18-wipe-analysis-design.md`

**Layer:** This plan ends at findings JSON. The per-player grid table, the players-alive chart and the Summary/Mechanics tab redistribution are Layer 2, and no task here touches a template, a view model or a ledger placement beyond the one routing line in Task 8.

## Global Constraints

Every task's requirements implicitly include all of these.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches the network, disk or a template.
- **Every finding carries a `confidence` badge.** A finding without one is a bug.
- **The page describes damage and never assigns intent** (master design §5.5). No finding may say a mechanic was missed, avoided, or could have been prevented.
- **Our unmitigated figure never sits beside a reference table's mitigated figure.** They were measured 4.61x apart. Cross-raid comparison uses landings per minute or death counts, never damage.
- **No finding may state a phase and a reference figure together.** The reference side carries no timestamps, so a phase-against-phase claim is impossible.
- **Gate an in-fight phase label on the encounter having phases, not on `separatesWipes`.** Measured 2026-09-18: 5 of 8 encounters read true, 3 read false, and all 8 carry named phases.
- **Boss health is `Encounter.boss_percentage`, never `fight_percentage`.** They are different quantities and diverged 51.12 against 3.76 on one measured attempt.
- **No new Warcraft Logs query.** Every input this plan reads is already fetched.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. Fixtures needing more players refer to them by role and index.
- **TDD is mandatory.** Write the failing test, run it, see it fail for the stated reason, then implement.
- **The mutation rule:** no assertion may survive deleting the arithmetic or the string it claims to check.
- **Gate:** `uv run pytest`, `uv run ruff check .`, `uv run mypy` — each its own command. mypy runs over `tests/` too. Line length 100.
- **Commit messages:** imperative mood, no `feat:`/`fix:` prefix, plain ASCII only, body explains why. End with a blank line then `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. **Never use `--no-verify`.**

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/encounter.py` | *modified* — `Encounter` gains `phases` |
| `src/wowperf/adapters/wcl/ingest.py` | *modified* — `build_encounter` populates it |
| `src/wowperf/domain/phase_windows.py` | **new** — which phase an instant fell in, and where an ability's landings concentrated |
| `src/wowperf/domain/comparison/mechanics.py` | *modified* — a phase label on `mechanics.ability`; new `compare_lethal_abilities`; new `compare_phase_cost` |
| `src/wowperf/domain/analysis/attempt_shape.py` | **new** — the `wipe.cause` verdict |
| `src/wowperf/domain/analysis/encounter_service.py` | *modified* — wires the three new analysers |
| `src/wowperf/domain/report/raid_ledger.py` | *modified* — one routing prefix so the findings reach a tab |

`phase_windows.py` sits at `domain/` top level beside `phases.py`, not under `comparison/` or `analysis/`, because both of those consume it.

---

## Task 1: An encounter names its own phases

`Encounter` carries `phase_transitions` (ids and times) and `last_phase`, but not the named
`Phase` list — that lives only on `Progression`. So an encounter can say *when* it changed phase
and not *what the phase is called*. Every later task needs the names.

`build_phases(report, encounter_id) -> tuple[tuple[Phase, ...], bool]` already exists at
`ingest.py:239` and already does the work; `build_encounter` simply never calls it.

**Files:**
- Modify: `src/wowperf/domain/encounter.py` (the `Encounter` class)
- Modify: `src/wowperf/adapters/wcl/ingest.py` (`build_encounter`, the `Encounter(...)` return)
- Test: `tests/adapters/wcl/test_ingest.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Encounter.phases: tuple[Phase, ...]` — empty on an encounter the API names no phases for.

- [ ] **Step 1: Write the failing test**

Append to `tests/adapters/wcl/test_ingest.py`:

```python
def test_an_encounter_carries_the_names_of_its_phases() -> None:
    report = {
        "code": "AbCdEf",
        "phases": [
            {
                "encounterID": 3492,
                "separatesWipes": True,
                "phases": [
                    {"id": 1, "name": "Stage One: Fury", "isIntermission": False},
                    {"id": 2, "name": "Intermission: The Shattering", "isIntermission": True},
                ],
            }
        ],
    }
    encounter = _build_encounter_for(report, encounter_id=3492)

    assert [phase.name for phase in encounter.phases] == [
        "Stage One: Fury",
        "Intermission: The Shattering",
    ]
    assert [phase.is_intermission for phase in encounter.phases] == [False, True]


def test_an_encounter_the_report_names_no_phases_for_carries_none() -> None:
    report = {"code": "AbCdEf", "phases": [{"encounterID": 9999, "phases": []}]}

    assert _build_encounter_for(report, encounter_id=3492).phases == ()
```

Write `_build_encounter_for` as a module-level helper in the same test file, following whatever
fixture shape the file's existing `build_encounter` tests use for `fight` and `players`. It must
pass the `report` dict through unchanged and set `fight["encounterID"]` to `encounter_id`.

- [ ] **Step 2: Run the test and watch it fail**

```bash
uv run pytest tests/adapters/wcl/test_ingest.py -k phases -v
```

Expected: FAIL with `AttributeError: 'Encounter' object has no attribute 'phases'`.

- [ ] **Step 3: Add the field**

In `src/wowperf/domain/encounter.py`, add to `Encounter` immediately after `phase_transitions`:

```python
    # The encounter's named phases, from `Report.phases`. Empty where the API
    # names none, which is a fact about the boss rather than a missing reading.
    # `phase_transitions` says when each began; this says what each is called,
    # and a phase claim needs both.
    phases: tuple[Phase, ...] = ()
```

Add `Phase` to the existing `from wowperf.domain.phases import PhaseTransition` import:

```python
from wowperf.domain.phases import Phase, PhaseTransition
```

- [ ] **Step 4: Populate it**

In `src/wowperf/adapters/wcl/ingest.py`, inside `build_encounter`, hoist the encounter id into a
local before the `return Encounter(...)` (it is currently computed inline):

```python
    encounter_id = _required(fight, "encounterID")
    phases, _separates_wipes = build_phases(report, encounter_id)
```

Then in the `Encounter(...)` call, replace `encounter_id=_required(fight, "encounterID"),` with
`encounter_id=encounter_id,` and add after `phase_transitions=...`:

```python
        phases=phases,
```

`separatesWipes` is discarded here on purpose: this plan's phase claims are about one attempt, and
the flag answers a question about grouping attempts. `Progression` reads it separately.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/adapters/wcl/test_ingest.py -v
```

Expected: PASS, including every pre-existing test in the file.

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

```bash
git add src/wowperf/domain/encounter.py src/wowperf/adapters/wcl/ingest.py tests/adapters/wcl/test_ingest.py
```

```bash
git commit -m "Let a boss fight name the phases it moved through

An Encounter knew when it changed phase and not what the phase was
called: the named list lived only on Progression. build_phases already
returned it and build_encounter never called it.

separatesWipes is discarded here. It answers whether phase is a useful
way to group an encounter's attempts, which is the progression page's
question, not whether one attempt can be sliced.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The phase an instant fell in

A pure locator. This is the trap-heavy function of the plan: a phase transition list is **not a
ladder**, so the highest id reached is not where the fight was.

**Files:**
- Create: `src/wowperf/domain/phase_windows.py`
- Test: `tests/domain/test_phase_windows.py`

**Interfaces:**
- Consumes: `Encounter.phases` from Task 1; `Phase` and `PhaseTransition` from `domain/phases.py`.
- Produces: `phase_at(phases: tuple[Phase, ...], transitions: tuple[PhaseTransition, ...], timestamp_ms: int) -> Phase | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/test_phase_windows.py`:

```python
from wowperf.domain.phase_windows import phase_at
from wowperf.domain.phases import Phase, PhaseTransition

STAGE_ONE = Phase(id=1, name="Stage One")
STAGE_TWO = Phase(id=2, name="Stage Two", is_intermission=True)
PHASES = (STAGE_ONE, STAGE_TWO)


def test_an_instant_takes_the_phase_of_the_transition_before_it() -> None:
    transitions = (PhaseTransition(id=1, start_ms=0), PhaseTransition(id=2, start_ms=5000))

    assert phase_at(PHASES, transitions, 4999) == STAGE_ONE
    assert phase_at(PHASES, transitions, 5000) == STAGE_TWO
    assert phase_at(PHASES, transitions, 9999) == STAGE_TWO


def test_a_fight_that_returned_to_an_earlier_phase_reads_as_that_phase() -> None:
    """The list is not a ladder: 1, 2, 1 was measured on a real attempt.

    The highest id reached is not where the fight was. An implementation
    taking `max` over the ids passed so far returns Stage Two here.
    """
    transitions = (
        PhaseTransition(id=1, start_ms=0),
        PhaseTransition(id=2, start_ms=5000),
        PhaseTransition(id=1, start_ms=9000),
    )

    assert phase_at(PHASES, transitions, 9500) == STAGE_ONE


def test_transitions_out_of_order_are_read_by_time_not_by_position() -> None:
    transitions = (PhaseTransition(id=2, start_ms=5000), PhaseTransition(id=1, start_ms=0))

    assert phase_at(PHASES, transitions, 1000) == STAGE_ONE


def test_an_encounter_with_no_phases_places_nothing() -> None:
    assert phase_at((), (PhaseTransition(id=1, start_ms=0),), 10) is None


def test_an_encounter_with_no_transitions_places_nothing() -> None:
    assert phase_at(PHASES, (), 10) is None


def test_a_transition_naming_an_unlisted_phase_places_nothing() -> None:
    """Encounter 3470 reported `lastPhase: 2` against transitions ending in 3.

    The two vocabularies can disagree, so an id with no `Phase` behind it is
    answered with None rather than with a guess.
    """
    transitions = (PhaseTransition(id=7, start_ms=0),)

    assert phase_at(PHASES, transitions, 10) is None


def test_an_instant_before_the_first_transition_places_nothing() -> None:
    """Measured 2026-09-18: 104 of 104 fights began at their first transition.

    So this case does not arise inside a fight, and the function answers None
    rather than assuming the first listed phase covers the gap.
    """
    transitions = (PhaseTransition(id=1, start_ms=5000),)

    assert phase_at(PHASES, transitions, 4999) is None
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/test_phase_windows.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.phase_windows'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/phase_windows.py`:

```python
# ABOUTME: Which named phase an instant of a boss fight fell in.
# ABOUTME: Reads transitions by time, never by position or by highest id reached.

from wowperf.domain.phases import Phase, PhaseTransition


def phase_at(
    phases: tuple[Phase, ...],
    transitions: tuple[PhaseTransition, ...],
    timestamp_ms: int,
) -> Phase | None:
    """The phase an instant fell in, or None where the encounter names none.

    **A transition list is not a ladder.** One measured attempt ran 1, 2, 1, 2,
    1, 2, 1 (skill file, 2026-09-18), so the phase at an instant is the one the
    *latest* transition at or before it names -- never the highest id seen, and
    never the last element of the list.

    Transitions are read by `start_ms` rather than by their order in the tuple,
    because nothing in the API's contract promises the list is sorted and
    sorting costs nothing at these lengths.

    **Transitions tile the fight.** Measured 2026-09-18 across 104 fights
    carrying transitions, every first transition sat exactly at its fight's
    start, so an instant inside a fight always lands in a window. An instant
    before the first transition is answered None rather than assumed into the
    first listed phase -- it does not arise in practice, and guessing would be
    the kind of quiet fabrication the confidence badges exist to prevent.

    A transition naming an id the phase list does not carry is answered None
    for the same reason: encounter 3470 reported `lastPhase: 2` against
    transitions ending in 3, so the two vocabularies are known to disagree.
    """
    if not phases or not transitions:
        return None
    by_id = {phase.id: phase for phase in phases}
    current: Phase | None = None
    for transition in sorted(transitions, key=lambda one: one.start_ms):
        if transition.start_ms > timestamp_ms:
            break
        current = by_id.get(transition.id)
    return current
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/domain/test_phase_windows.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Run the gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/phase_windows.py tests/domain/test_phase_windows.py
```

```bash
git commit -m "Place an instant of a boss fight in its named phase

A transition list is not a ladder. One measured attempt ran 1, 2, 1, 2,
1, 2, 1, so the highest id reached is not where the fight was, and the
last element of the list is not either. The phase at an instant is the
one the latest transition at or before it names.

Two disagreements are answered with None rather than a guess: a
transition naming an id the phase list lacks, which encounter 3470 is
known to produce, and an instant before the first transition, which 104
of 104 measured fights show does not arise inside a fight.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Where an ability's landings concentrated

`compare_mechanics` reads `AbilityTakenRow` tables, which carry no timestamps. The damage-taken
event stream does. This task joins the two by ability id so a whole-fight comparison can name the
phase its landings fell in, **without** `compare_mechanics` learning to read events.

**Files:**
- Modify: `src/wowperf/domain/phase_windows.py`
- Test: `tests/domain/test_phase_windows.py`

**Interfaces:**
- Consumes: `phase_at` from Task 2; `DamageTakenEvent` from `domain/events.py` (fields used: `ability_id`, `timestamp_ms`).
- Produces: `dominant_phase_by_ability(events, phases, transitions) -> dict[int, PhaseShare]`, and `class PhaseShare(Frozen)` with fields `phase: Phase`, `landings: int`, `total: int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_phase_windows.py`:

```python
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.phase_windows import dominant_phase_by_ability


def _hit(ability_id: int, timestamp_ms: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=1,
        ability_id=ability_id,
        ability_name="Caustic Waves",
        amount=100,
        timestamp_ms=timestamp_ms,
    )


TRANSITIONS = (PhaseTransition(id=1, start_ms=0), PhaseTransition(id=2, start_ms=5000))


def test_an_ability_reports_the_phase_most_of_its_landings_fell_in() -> None:
    events = (_hit(11, 100), _hit(11, 6000), _hit(11, 7000), _hit(11, 8000))

    share = dominant_phase_by_ability(events, PHASES, TRANSITIONS)[11]

    assert share.phase == STAGE_TWO
    assert share.landings == 3
    assert share.total == 4


def test_the_share_counts_rather_than_assuming_the_last_phase() -> None:
    """Three landings in Stage One and one in Stage Two must read Stage One.

    An implementation returning the phase of the newest event passes the test
    above and fails this one.
    """
    events = (_hit(11, 100), _hit(11, 200), _hit(11, 300), _hit(11, 6000))

    share = dominant_phase_by_ability(events, PHASES, TRANSITIONS)[11]

    assert share.phase == STAGE_ONE
    assert share.landings == 3
    assert share.total == 4


def test_each_ability_is_counted_separately() -> None:
    events = (_hit(11, 100), _hit(22, 6000))

    shares = dominant_phase_by_ability(events, PHASES, TRANSITIONS)

    assert shares[11].phase == STAGE_ONE
    assert shares[22].phase == STAGE_TWO


def test_an_encounter_with_no_phases_yields_no_shares() -> None:
    assert dominant_phase_by_ability((_hit(11, 100),), (), TRANSITIONS) == {}


def test_an_ability_whose_landings_all_fall_outside_any_phase_is_absent() -> None:
    late = (PhaseTransition(id=1, start_ms=9000),)

    assert dominant_phase_by_ability((_hit(11, 100),), PHASES, late) == {}
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/test_phase_windows.py -k dominant -v
```

Expected: FAIL with `ImportError: cannot import name 'dominant_phase_by_ability'`.

- [ ] **Step 3: Write the implementation**

Append to `src/wowperf/domain/phase_windows.py`, and add these imports at the top:

```python
from collections import Counter

from wowperf.domain.base import Frozen
from wowperf.domain.events import DamageTakenEvent
```

```python
class PhaseShare(Frozen):
    """Where one ability's landings concentrated, and how concentrated they were.

    Carries `landings` and `total` rather than only a share, because the finding
    states both: "27 landings, 19 of them in Stage Two" is checkable and "70% in
    Stage Two" is not.
    """

    phase: Phase
    landings: int
    total: int


def dominant_phase_by_ability(
    events: tuple[DamageTakenEvent, ...],
    phases: tuple[Phase, ...],
    transitions: tuple[PhaseTransition, ...],
) -> dict[int, PhaseShare]:
    """Per ability id, the phase most of its landings fell in.

    This is the join that lets a whole-fight comparison name a phase. The
    comparison's own input is an `AbilityTakenRow` table carrying no
    timestamps, and the event stream carrying them is fetched anyway, so the
    phase is read here and handed over rather than teaching the comparison to
    read events.

    **Our side only.** The reference side of any comparison is a table with no
    timestamps at all, so nothing here may be used to claim a reference kill
    spent its landings differently -- see the design's section 9.

    An ability whose landings all fall outside every phase window is absent
    from the result rather than present with a null phase: a caller asking
    "which phase" gets an answer or gets nothing.
    """
    counts: dict[int, Counter[int]] = {}
    by_id = {phase.id: phase for phase in phases}
    for event in events:
        placed = phase_at(phases, transitions, event.timestamp_ms)
        if placed is None:
            continue
        counts.setdefault(event.ability_id, Counter())[placed.id] += 1

    shares: dict[int, PhaseShare] = {}
    for ability_id, tally in counts.items():
        phase_id, landings = max(tally.items(), key=lambda pair: (pair[1], -pair[0]))
        shares[ability_id] = PhaseShare(
            phase=by_id[phase_id], landings=landings, total=sum(tally.values())
        )
    return shares
```

The `-pair[0]` in the sort key breaks a tie toward the lower phase id, so a fight splitting an
ability evenly between two phases reports the earlier one rather than an arbitrary one.

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/domain/test_phase_windows.py -v
```

Expected: PASS, 12 tests.

- [ ] **Step 5: Run the gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/phase_windows.py tests/domain/test_phase_windows.py
```

```bash
git commit -m "Say which phase an ability spent its landings in

The mechanics comparison reads a damage-taken table, which carries no
timestamps. The event stream carrying them is fetched anyway, so the
join happens here and the phase is handed over, rather than teaching the
comparison to read events.

Our side only. A reference kill's table carries no timestamps either, so
nothing here can support a claim about how a reference spent its
landings, and the design forbids one.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: A mechanics finding names the phase its landings fell in

**Files:**
- Modify: `src/wowperf/domain/comparison/mechanics.py` (`compare_mechanics` and both `Finding` construction sites)
- Test: `tests/domain/comparison/test_mechanics.py`

**Interfaces:**
- Consumes: `PhaseShare` and `dominant_phase_by_ability` from Task 3.
- Produces: `compare_mechanics(..., phase_shares: Mapping[int, PhaseShare] | None = None)` — the keyword is optional and defaults to no phase labels, so every existing caller and test keeps working.

- [ ] **Step 1: Write the failing test**

Append to `tests/domain/comparison/test_mechanics.py`, reusing whatever helpers the file already
has for building `AbilityTakenRow` and `MechanicsSample`:

```python
def test_a_mechanics_finding_names_the_phase_its_landings_fell_in() -> None:
    shares = {
        11: PhaseShare(phase=Phase(id=2, name="Stage Two"), landings=19, total=27),
    }

    findings = compare_mechanics(
        _our_rows(ability_id=11, landings=27),
        our_seconds=300.0,
        sample=_sample_taking(ability_id=11, landings=2),
        scope="the raid",
        phase_shares=shares,
    )

    assert any("Stage Two" in fact.value for fact in findings[0].facts)
    assert any("19 of 27" in line for line in findings[0].evidence)


def test_a_mechanics_finding_without_a_phase_share_names_no_phase() -> None:
    findings = compare_mechanics(
        _our_rows(ability_id=11, landings=27),
        our_seconds=300.0,
        sample=_sample_taking(ability_id=11, landings=2),
        scope="the raid",
    )

    assert all(fact.label != "Mostly in" for fact in findings[0].facts)


def test_a_phase_finding_states_no_reference_figure_in_the_same_fact() -> None:
    """The reference table carries no timestamps, so a phase fact may never
    carry a reference number beside it. Design section 9."""
    shares = {11: PhaseShare(phase=Phase(id=2, name="Stage Two"), landings=19, total=27)}

    findings = compare_mechanics(
        _our_rows(ability_id=11, landings=27),
        our_seconds=300.0,
        sample=_sample_taking(ability_id=11, landings=2),
        scope="the raid",
        phase_shares=shares,
    )

    phase_facts = [fact for fact in findings[0].facts if fact.label == "Mostly in"]
    assert phase_facts
    assert all("reference" not in fact.value.lower() for fact in phase_facts)
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/comparison/test_mechanics.py -k phase -v
```

Expected: FAIL with `TypeError: compare_mechanics() got an unexpected keyword argument 'phase_shares'`.

- [ ] **Step 3: Implement**

At the top of `src/wowperf/domain/comparison/mechanics.py` add:

```python
from collections.abc import Mapping

from wowperf.domain.phase_windows import PhaseShare
```

Add the keyword to `compare_mechanics`'s signature, after `scope`:

```python
    phase_shares: Mapping[int, PhaseShare] | None = None,
```

Add this helper above `compare_mechanics`:

```python
def _phase_fact(
    shares: Mapping[int, PhaseShare] | None, ability_id: int
) -> tuple[tuple[FindingFact, ...], tuple[str, ...]]:
    """One ability's phase label, as a fact and an evidence line, or nothing.

    Deliberately returns no reference figure of any kind. A reference kill's
    ability table carries no timestamps, so there is no reference phase to
    compare against and a fact implying one would be unfalsifiable -- design
    section 9.
    """
    share = (shares or {}).get(ability_id)
    if share is None:
        return (), ()
    return (
        (
            FindingFact(
                label="Mostly in",
                value=share.phase.name,
                confidence=Confidence.DERIVED,
            ),
        ),
        (f"{share.landings} of {share.total} landings fell in {share.phase.name}",),
    )
```

In **both** `Finding(...)` construction sites inside `compare_mechanics`, bind the helper's output
just before the `candidates.append(...)` call:

```python
        phase_facts, phase_evidence = _phase_fact(phase_shares, our_row.ability_id)
```

then append `+ phase_evidence` to that site's `evidence=(...)` tuple and `+ phase_facts` to its
`facts=(...)` tuple. For example the evidence becomes:

```python
                    evidence=(
                        f"ours {our_rate:.1f} a minute over {our_seconds:.0f}s",
                        f"the reference {their_rate:.1f} a minute over {their_seconds:.0f}s",
                        f"reference kill {member.row.report_code} fight {member.row.fight_id}",
                    )
                    + phase_evidence,
```

Leave the titles and details untouched. A title is the one line a reader always sees, and the
phase belongs in the supporting figures rather than crowding the comparison the finding is about.

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/domain/comparison/test_mechanics.py -v
```

Expected: PASS, including every pre-existing test — the new keyword defaults to `None`.

- [ ] **Step 5: Run the gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/comparison/mechanics.py tests/domain/comparison/test_mechanics.py
```

```bash
git commit -m "Name the phase a mechanic's landings fell in

The comparison stays whole-fight, because the reference side cannot be
split by time. What it gains is context on our own side: how many of our
landings fell in which named phase, as a supporting figure rather than
in the title.

The phase fact carries no reference number and a test asserts it does
not. A reference kill's ability table has no timestamps, so any
phase-against-phase figure would be unfalsifiable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Abilities that killed the raid

The one place the page may judge rather than describe, because nobody dies to a mechanic on
purpose. `ReferenceKillRow.deaths` already carries each reference kill's total death count and is
read by nothing today.

**Files:**
- Modify: `src/wowperf/domain/comparison/mechanics.py`
- Test: `tests/domain/comparison/test_mechanics.py`

**Interfaces:**
- Consumes: `MechanicsSample` and `MAX_MECHANICS_REPORTED` (same module); `Death` from `domain/events.py` (fields used: `killing_blow`, `killing_blow_id`).
- Produces: `compare_lethal_abilities(deaths: tuple[Death, ...], sample: MechanicsSample) -> list[Finding]`, minting ids `mechanics.lethal.<rank>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_mechanics.py`:

```python
def _death(ability_id: int, name: str) -> Death:
    return Death(
        player_name="Emberkin",
        actor_id=1,
        timestamp_ms=1000,
        killing_blow=name,
        killing_blow_id=ability_id,
    )


def _sample_losing(*counts: int) -> MechanicsSample:
    return MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="AbCdEf",
                    fight_id=index,
                    size=20,
                    duration_ms=300_000,
                    deaths=count,
                ),
                abilities=(),
            )
            for index, count in enumerate(counts)
        )
    )


def test_an_ability_that_killed_more_than_the_references_lost_in_total() -> None:
    deaths = tuple(_death(11, "Caustic Waves") for _ in range(4))

    findings = compare_lethal_abilities(deaths, _sample_losing(0, 1, 2, 3, 1))

    assert findings[0].id == "mechanics.lethal.0"
    assert findings[0].confidence is Confidence.DERIVED
    assert "Caustic Waves" in findings[0].title
    assert findings[0].ability_id == 11
    assert any("0 to 3" in line for line in findings[0].evidence)


def test_the_deadliest_ability_is_reported_first() -> None:
    deaths = (
        _death(11, "Caustic Waves"),
        _death(22, "Purge"),
        _death(22, "Purge"),
        _death(22, "Purge"),
    )

    findings = compare_lethal_abilities(deaths, _sample_losing(0, 1, 2))

    assert findings[0].ability_name == "Purge"
    assert findings[1].ability_name == "Caustic Waves"


def test_at_most_five_abilities_are_reported() -> None:
    deaths = tuple(_death(identifier, f"Ability {identifier}") for identifier in range(9))

    assert len(compare_lethal_abilities(deaths, _sample_losing(0, 1, 2))) == 5


def test_a_sample_below_the_aggregate_floor_names_one_reference_kill() -> None:
    deaths = (_death(11, "Caustic Waves"),)

    findings = compare_lethal_abilities(deaths, _sample_losing(2, 3))

    assert any("1 reference kill" in fact.value for fact in findings[0].facts)
    assert all("median" not in line for line in findings[0].evidence)


def test_no_sample_yields_no_finding() -> None:
    assert compare_lethal_abilities((_death(11, "Caustic Waves"),), MechanicsSample()) == []


def test_no_deaths_yields_no_finding() -> None:
    assert compare_lethal_abilities((), _sample_losing(0, 1, 2)) == []
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/comparison/test_mechanics.py -k lethal -v
```

Expected: FAIL with `ImportError: cannot import name 'compare_lethal_abilities'`.

- [ ] **Step 3: Implement**

Add to the imports at the top of `src/wowperf/domain/comparison/mechanics.py`:

```python
from wowperf.domain.events import Death
```

Append to the module:

```python
def _reference_deaths(members: tuple[MechanicsMember, ...]) -> tuple[str, str, str]:
    """What the reference kills lost, as a title phrase, a fact and an evidence line.

    Below `MIN_SAMPLE_FOR_AGGREGATE` members this names a single reference kill
    rather than a median, exactly as `compare_mechanics` does one function
    above: a median of two is a mean of two, and the sample label must not
    claim an aggregate nobody drew.
    """
    counts = [float(member.row.deaths) for member in members]
    if len(counts) >= MIN_SAMPLE_FOR_AGGREGATE:
        low, high = observed_range(counts)
        return (
            f"a median of {median(counts):.0f}",
            f"{len(counts)} reference kills",
            f"reference kills lost {low:.0f} to 3 players, median {median(counts):.0f}".replace(
                "to 3", f"to {high:.0f}"
            ),
        )
    return (
        f"{counts[0]:.0f}",
        "1 reference kill",
        f"one reference kill lost {counts[0]:.0f} players in total",
    )


def compare_lethal_abilities(
    deaths: tuple[Death, ...],
    sample: MechanicsSample,
) -> list[Finding]:
    """Abilities that killed our raid, against what the reference kills lost in total.

    This is the one comparison in this area that judges rather than describes.
    Master design 5.5 refuses to call a hit avoidable, because a damage-taken
    table cannot tell a careless player from one soaking on purpose. A death is
    different: nobody dies to a mechanic deliberately, so a death count needs no
    claim about intent to mean something.

    The two sides are deliberately not symmetrical, and the wording says so:
    ours is one ability's kills, theirs is everything that killed anyone. A
    per-ability reference death count would need each reference kill's own
    death stream, which is a query per candidate.
    """
    if not deaths or not sample.members:
        return []

    tally: Counter[tuple[int, str]] = Counter(
        (death.killing_blow_id, death.killing_blow) for death in deaths
    )
    phrase, sample_label, evidence_line = _reference_deaths(sample.members)

    ranked = sorted(tally.items(), key=lambda pair: (-pair[1], pair[0][1]))
    findings = []
    for rank, ((ability_id, ability_name), killed) in enumerate(ranked[:MAX_MECHANICS_REPORTED]):
        findings.append(
            Finding(
                id=f"mechanics.lethal.{rank}",
                title=(
                    f"{ability_name} killed {quantity(killed, 'player', 'players')}, "
                    f"where the reference kills lost {phrase} to everything combined"
                ),
                detail=(
                    f"{killed} of this raid's deaths came from {ability_name}. The "
                    "reference figure counts every death in those kills, from any "
                    "source, so it is the whole budget this one ability spent."
                ),
                confidence=Confidence.DERIVED,
                evidence=(f"{ability_name} killed {killed}", evidence_line),
                facts=(
                    FindingFact(label="Killed by this", value=f"{killed}"),
                    FindingFact(label="Reference deaths, all sources", value=phrase),
                    FindingFact(label="Sample", value=sample_label),
                ),
                ability_id=ability_id,
                ability_name=ability_name,
            )
        )
    return findings
```

Add `Counter` to the module's imports:

```python
from collections import Counter
```

- [ ] **Step 4: Simplify the evidence line**

The `.replace` in `_reference_deaths` is a placeholder-shaped hack. Replace that branch with a
direct f-string:

```python
    if len(counts) >= MIN_SAMPLE_FOR_AGGREGATE:
        low, high = observed_range(counts)
        middle = median(counts)
        return (
            f"a median of {middle:.0f}",
            f"{len(counts)} reference kills",
            f"reference kills lost {low:.0f} to {high:.0f} players, median {middle:.0f}",
        )
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/domain/comparison/test_mechanics.py -v
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

```bash
git add src/wowperf/domain/comparison/mechanics.py tests/domain/comparison/test_mechanics.py
```

```bash
git commit -m "Name the abilities that killed the raid

Master design 5.5 refuses to call a hit avoidable, because a damage-taken
table cannot tell a careless player from one soaking on purpose. A death
carries no such ambiguity: nobody dies to a mechanic deliberately. So the
judgement this area is allowed to make rests on deaths, and the
descriptive comparison keeps damage.

ReferenceKillRow.deaths has carried each reference kill's death count
since the row was written and nothing read it until now.

The two sides are not symmetrical and the wording says so. Ours is one
ability's kills; theirs is every death from any source. A per-ability
reference count would need each candidate's own death stream.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Where in the fight the cost concentrated

**Files:**
- Modify: `src/wowperf/domain/comparison/mechanics.py`
- Test: `tests/domain/comparison/test_mechanics.py`

**Interfaces:**
- Consumes: `phase_at` from Task 2; `DamageTakenEvent`, `Phase`, `PhaseTransition`.
- Produces: `compare_phase_cost(events, phases, transitions) -> list[Finding]`, minting ids `mechanics.phase.<rank>`.

Despite the module it lives in, this function compares nothing across raids — it is filed here to
sit beside the other `mechanics.*` families, and its docstring says so.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_mechanics.py`:

```python
def test_the_phase_taking_the_most_damage_is_reported_first() -> None:
    events = (
        _taken(ability_id=11, timestamp_ms=100, amount=50),
        _taken(ability_id=11, timestamp_ms=6000, amount=400),
        _taken(ability_id=11, timestamp_ms=7000, amount=300),
    )

    findings = compare_phase_cost(events, PHASES, TRANSITIONS)

    assert findings[0].id == "mechanics.phase.0"
    assert "Stage Two" in findings[0].title
    assert findings[0].confidence is Confidence.DERIVED


def test_a_phase_finding_carries_no_reference_figure() -> None:
    """Design section 9: the reference table has no timestamps, so no phase
    finding may imply a reference side."""
    events = (_taken(ability_id=11, timestamp_ms=6000, amount=400),)

    finding = compare_phase_cost(events, PHASES, TRANSITIONS)[0]

    assert all(
        "reference" not in text.lower()
        for text in (finding.title, finding.detail, *finding.evidence)
    )
    assert all(fact.label != "Reference" for fact in finding.facts)


def test_an_encounter_with_no_phases_reports_nothing() -> None:
    events = (_taken(ability_id=11, timestamp_ms=100, amount=50),)

    assert compare_phase_cost(events, (), TRANSITIONS) == []


def test_the_share_is_of_damage_not_of_landings() -> None:
    """One huge hit in Stage Two must outrank three small ones in Stage One.

    An implementation counting events passes every test above and fails this.
    """
    events = (
        _taken(ability_id=11, timestamp_ms=100, amount=10),
        _taken(ability_id=11, timestamp_ms=200, amount=10),
        _taken(ability_id=11, timestamp_ms=300, amount=10),
        _taken(ability_id=11, timestamp_ms=6000, amount=900),
    )

    assert "Stage Two" in compare_phase_cost(events, PHASES, TRANSITIONS)[0].title
```

Add a `_taken` helper to the file mirroring `_hit` from Task 3 but taking an `amount`, and import
`PHASES`, `TRANSITIONS`, `Phase` and `PhaseTransition` as that file needs.

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/comparison/test_mechanics.py -k phase_cost -v
```

Expected: FAIL with `ImportError: cannot import name 'compare_phase_cost'`.

- [ ] **Step 3: Implement**

Append to `src/wowperf/domain/comparison/mechanics.py`:

```python
def compare_phase_cost(
    events: tuple[DamageTakenEvent, ...],
    phases: tuple[Phase, ...],
    transitions: tuple[PhaseTransition, ...],
) -> list[Finding]:
    """Which named phases cost this raid the most damage taken.

    **This compares nothing across raids.** It lives beside the other
    `mechanics.*` families so one prefix reaches one tab, but a reference
    kill's ability table carries no timestamps, so there is no reference phase
    to compare against and the design forbids implying one. Every figure here
    is our own.

    Damage rather than landings, because a phase is a stretch of time and the
    question is what it cost: three chip hits do not outweigh one that nearly
    killed someone.
    """
    if not phases or not transitions:
        return []

    totals: Counter[int] = Counter()
    for event in events:
        placed = phase_at(phases, transitions, event.timestamp_ms)
        if placed is not None:
            totals[placed.id] += event.amount
    if not totals:
        return []

    by_id = {phase.id: phase for phase in phases}
    overall = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    findings = []
    for rank, (phase_id, amount) in enumerate(ranked[:MAX_MECHANICS_REPORTED]):
        phase = by_id[phase_id]
        findings.append(
            Finding(
                id=f"mechanics.phase.{rank}",
                title=(
                    f"{phase.name} cost this raid {amount:,} damage taken, "
                    f"{amount / overall * 100:.0f}% of the attempt's total"
                ),
                detail=(
                    f"Damage taken inside {phase.name}, summed over every player. "
                    "This states where the attempt's damage fell, not that any of "
                    "it could have been avoided."
                ),
                confidence=Confidence.DERIVED,
                evidence=(
                    f"{amount:,} of {overall:,} damage taken",
                    f"phase named by the API as {phase.name}",
                ),
                facts=(
                    FindingFact(label="Damage taken", value=f"{amount:,}"),
                    FindingFact(
                        label="Share of attempt",
                        value=f"{amount / overall * 100:.0f}%",
                        confidence=Confidence.DERIVED,
                    ),
                ),
            )
        )
    return findings
```

Add `phase_at` to the Task 3 import line:

```python
from wowperf.domain.phase_windows import PhaseShare, phase_at
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/domain/comparison/test_mechanics.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/comparison/mechanics.py tests/domain/comparison/test_mechanics.py
```

```bash
git commit -m "Say which phase of an attempt cost the most

Damage rather than landings, because a phase is a stretch of time and
the question is what it cost: three chip hits do not outweigh one that
nearly killed someone.

This compares nothing across raids despite the module it sits in. A
reference kill's ability table carries no timestamps, so there is no
reference phase to compare against, and a test asserts no phase finding
mentions one.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Execution or throughput

The verdict. It reads our own attempt's shape against the reference kills' durations and death
counts, and it is the only `inferred` finding in this plan.

It lives under `domain/analysis/` rather than `domain/comparison/` because `comparison/` means
"us against them" and the question here is what our own attempt looked like.

**Files:**
- Create: `src/wowperf/domain/analysis/attempt_shape.py`
- Test: `tests/domain/analysis/test_attempt_shape.py`

**Interfaces:**
- Consumes: `Encounter` (fields used: `kill`, `size`, `boss_percentage`, `duration_seconds`), `Death`, `MechanicsSample`.
- Produces: `classify_attempt(encounter: Encounter, deaths: tuple[Death, ...], sample: MechanicsSample) -> Finding | None`, minting the id `wipe.cause`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/analysis/test_attempt_shape.py`:

```python
from wowperf.domain.analysis.attempt_shape import classify_attempt
from wowperf.domain.comparison.mechanics import MechanicsMember, MechanicsSample, ReferenceKillRow
from wowperf.domain.encounter import Encounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player


def _players(count: int) -> tuple[Player, ...]:
    """Twenty raiders cannot come from a four-name allowlist, so they are indexed."""
    return tuple(
        Player(
            actor_id=index,
            name=f"Raider {index}",
            class_name="Mage",
            spec="Frost",
            item_level=690,
        )
        for index in range(count)
    )


def _encounter(*, kill: bool, boss_percentage: float | None, seconds: float) -> Encounter:
    return Encounter(
        report_code="AbCdEf",
        fight_id=1,
        encounter_id=3492,
        boss_name="The Boss",
        difficulty=5,
        partition=1,
        size=20,
        kill=kill,
        boss_percentage=boss_percentage,
        start_ms=0,
        end_ms=int(seconds * 1000),
        players=_players(20),
    )


def _deaths(count: int) -> tuple[Death, ...]:
    return tuple(
        Death(
            player_name=f"Raider {index}",
            actor_id=index,
            timestamp_ms=1000 * index,
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        )
        for index in range(count)
    )


def _sample(*, seconds: float, deaths: int) -> MechanicsSample:
    return MechanicsSample(
        members=tuple(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ZzZzZz",
                    fight_id=index,
                    size=20,
                    duration_ms=int(seconds * 1000),
                    deaths=deaths,
                ),
                abilities=(),
            )
            for index in range(5)
        )
    )


def test_a_dismantled_raid_reads_as_execution() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=40.0, seconds=200.0),
        _deaths(14),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert finding.id == "wipe.cause"
    assert finding.confidence is Confidence.INFERRED
    assert "execution" in finding.title.lower()
    assert "14" in finding.detail


def test_an_intact_raid_on_a_long_attempt_reads_as_throughput() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(1),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "throughput" in finding.title.lower()


def test_a_dismantled_raid_on_a_long_attempt_reads_as_both_deaths_first() -> None:
    finding = classify_attempt(
        _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
        _deaths(14),
        _sample(seconds=300.0, deaths=1),
    )

    assert finding is not None
    assert "both" in finding.title.lower()
    assert finding.detail.lower().index("died") < finding.detail.lower().index("damage")


def test_an_unlucky_wipe_near_the_kill_is_withheld() -> None:
    """Raid mostly alive, boss nearly dead, attempt shorter than the references.
    Neither reading holds, so the verdict abstains rather than guessing."""
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=2.0, seconds=250.0),
            _deaths(3),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_a_kill_gets_no_verdict() -> None:
    assert (
        classify_attempt(
            _encounter(kill=True, boss_percentage=0.0, seconds=400.0),
            _deaths(14),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )


def test_an_attempt_with_no_reference_sample_is_withheld() -> None:
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=45.0, seconds=400.0),
            _deaths(1),
            MechanicsSample(),
        )
        is None
    )


def test_an_attempt_the_report_gives_no_boss_health_for_is_withheld() -> None:
    assert (
        classify_attempt(
            _encounter(kill=False, boss_percentage=None, seconds=400.0),
            _deaths(1),
            _sample(seconds=300.0, deaths=1),
        )
        is None
    )
```

If `Player` requires more fields than `actor_id` and `name`, extend `_players` to match its real
signature — check `src/wowperf/domain/model.py` before writing the helper.

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/analysis/test_attempt_shape.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'wowperf.domain.analysis.attempt_shape'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/analysis/attempt_shape.py`:

```python
# ABOUTME: Whether an attempt failed because the raid died or because it ran out of damage.
# ABOUTME: An inferred reading of our own attempt, never a comparison of one raid against another.

from wowperf.domain.comparison.mechanics import MechanicsSample
from wowperf.domain.comparison.statistics import median
from wowperf.domain.encounter import Encounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding, FindingFact

DISMANTLED_SHARE = 0.5
"""Half the raid dead or more is a raid that was taken apart, not one that slipped.

At twenty players a wipe with ten dead has lost its healers' mana, its
battle-resurrections and most of its damage, and no reading of the damage
figures survives that.
"""

INTACT_SHARE = 0.8
"""Four in five still standing is a raid that held. Below this, neither reading is clean."""

WALL_HEALTH = 20.0
"""Boss health above this at the end is a boss that was never close to dying."""


def classify_attempt(
    encounter: Encounter,
    deaths: tuple[Death, ...],
    sample: MechanicsSample,
) -> Finding | None:
    """Why this attempt ended, when the log supports saying.

    The only `inferred` finding this area mints, because it is the only
    judgement. The four measured facts behind it are stated in the finding
    rather than summarised, so a reader who disagrees can see what it read.

    It withholds rather than guesses. A wipe where the raid mostly stood and
    the boss was nearly dead is neither an execution failure nor a wall, and
    the honest answer is to say nothing -- the same habit the comparison axes
    keep when their samples are too thin.

    Boss health is `boss_percentage`, never `fight_percentage`. The two are
    different quantities and diverged 51.12 against 3.76 on one measured
    attempt.
    """
    if encounter.kill or not sample.members or encounter.boss_percentage is None:
        return None

    size = encounter.size or len(encounter.players)
    if size <= 0:
        return None

    died = len({death.actor_id for death in deaths})
    alive = max(size - died, 0)
    reference_seconds = median([member.row.duration_seconds for member in sample.members])
    reference_deaths = median([float(member.row.deaths) for member in sample.members])

    dismantled = died / size >= DISMANTLED_SHARE
    stalled = (
        encounter.boss_percentage > WALL_HEALTH
        and encounter.duration_seconds >= reference_seconds
    )

    if dismantled and stalled:
        headline = "both: the raid came apart, and the damage never caught up"
        story = (
            f"{died} of {size} died, and the attempt still ran "
            f"{encounter.duration_seconds:.0f}s against the reference kills' "
            f"{reference_seconds:.0f}s with {encounter.boss_percentage:.1f}% boss health "
            "left. The deaths came first: a raid this far down cannot make the damage."
        )
    elif dismantled:
        headline = "execution: the raid was taken apart"
        story = (
            f"{died} of {size} died, against a median of {reference_deaths:.0f} across "
            "the reference kills. This attempt ended before the damage question could "
            "be asked."
        )
    elif stalled and alive / size >= INTACT_SHARE:
        headline = "throughput: the raid held and the damage was not enough"
        story = (
            f"{alive} of {size} were still alive, and the boss finished on "
            f"{encounter.boss_percentage:.1f}% health after "
            f"{encounter.duration_seconds:.0f}s against the reference kills' "
            f"{reference_seconds:.0f}s. Nobody died and it still was not enough."
        )
    else:
        return None

    return Finding(
        id="wipe.cause",
        title=f"This attempt failed on {headline}",
        detail=story,
        confidence=Confidence.INFERRED,
        evidence=(
            f"{alive} of {size} alive at the end",
            f"{encounter.boss_percentage:.1f}% boss health remaining",
            f"{encounter.duration_seconds:.0f}s against a reference median of "
            f"{reference_seconds:.0f}s",
            f"{died} deaths against a reference median of {reference_deaths:.0f}",
        ),
        facts=(
            FindingFact(label="Alive at the end", value=f"{alive} of {size}"),
            FindingFact(label="Boss health left", value=f"{encounter.boss_percentage:.1f}%"),
            FindingFact(
                label="Our duration",
                value=f"{encounter.duration_seconds:.0f}s",
            ),
            FindingFact(
                label="Reference duration",
                value=f"{reference_seconds:.0f}s median",
                confidence=Confidence.DERIVED,
            ),
        ),
    )
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/domain/analysis/test_attempt_shape.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Run the gate**

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/wowperf/domain/analysis/attempt_shape.py tests/domain/analysis/test_attempt_shape.py
```

```bash
git commit -m "Say whether an attempt failed on execution or on damage

The two want opposite fixes, and drilling mechanics wastes a night when
the real problem is that the boss outlived the cooldowns. Four measured
facts decide it: who was alive at the end, the boss health left, our
duration against the reference kills' median, and our deaths against
theirs.

It withholds rather than guesses. A wipe where the raid mostly stood and
the boss was nearly dead is neither reading, and saying nothing is the
habit the comparison axes already keep when a sample is too thin.

Filed under analysis rather than comparison: comparison means us against
them, and this reads the shape of our own attempt.

Boss health is boss_percentage. fight_percentage is the encounter's
progress and the two diverged 51.12 against 3.76 on one attempt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Wire the three analysers into the raid findings

Nothing above reaches a findings file yet. This task calls them and routes their ids.

**Files:**
- Modify: `src/wowperf/domain/analysis/encounter_service.py`
- Modify: `src/wowperf/domain/report/raid_ledger.py`
- Test: `tests/domain/analysis/test_encounter_service.py`, `tests/domain/report/test_raid_ledger.py`

**Interfaces:**
- Consumes: `compare_lethal_abilities` and `compare_phase_cost` (Tasks 5, 6), `classify_attempt` (Task 7), `dominant_phase_by_ability` (Task 3).
- Produces: findings with ids `mechanics.lethal.*`, `mechanics.phase.*` and `wipe.cause` in `analyse_encounter`'s output.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_encounter_service.py`, following the file's existing
fixture helpers for `LoadedEncounter`:

```python
def test_a_wipe_reaches_a_lethal_finding_and_a_verdict() -> None:
    loaded = _loaded_wipe_with(deaths=14, sample_deaths=1)

    ids = {finding.id for finding in analyse_encounter(loaded, _defensives(), _consumables(),
                                                       mechanics=_mechanics_sample())}

    assert any(one.startswith("mechanics.lethal.") for one in ids)
    assert "wipe.cause" in ids


def test_a_fight_with_phases_reaches_a_phase_finding() -> None:
    loaded = _loaded_wipe_with_phases()

    ids = {finding.id for finding in analyse_encounter(loaded, _defensives(), _consumables(),
                                                       mechanics=_mechanics_sample())}

    assert any(one.startswith("mechanics.phase.") for one in ids)
```

Append to `tests/domain/report/test_raid_ledger.py`, following the shape its existing tests use to
exercise `RAID_PLACEMENTS`:

```python
def test_the_new_mechanics_families_land_where_the_old_one_does() -> None:
    """`RAID_PLACEMENTS` carries a bare `mechanics.` prefix, so both new
    families route themselves. This test fails if someone narrows it."""
    assert _tab_for("mechanics.lethal.0") == _tab_for("mechanics.ability.0") == "mechanics_rows"
    assert _tab_for("mechanics.phase.0") == "mechanics_rows"


def test_a_verdict_is_claimed_by_no_tab_prefix() -> None:
    """`wipe.cause` matches no prefix and falls through to Summary's unclaimed
    observations, which is where Layer 1 wants it. Layer 2 promotes it to a
    headline; until then this asserts it is not silently swallowed elsewhere."""
    assert _tab_for("wipe.cause") is None
```

Write `_tab_for(finding_id)` as a module-level helper returning the first matching
`RAID_PLACEMENTS` destination or `None`.

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/domain/analysis/test_encounter_service.py tests/domain/report/test_raid_ledger.py -v
```

Expected: FAIL — the new ids are neither produced nor routed.

- [ ] **Step 3: Call the analysers**

In `src/wowperf/domain/analysis/encounter_service.py`, add to the imports:

```python
from wowperf.domain.analysis.attempt_shape import classify_attempt
from wowperf.domain.comparison.mechanics import compare_lethal_abilities, compare_phase_cost
from wowperf.domain.phase_windows import dominant_phase_by_ability
```

and extend the existing `compare_mechanics` import on the same line it already occupies.

Replace the existing `compare_mechanics` call with:

```python
    phase_shares = dominant_phase_by_ability(
        loaded.damage_taken, encounter.phases, encounter.phase_transitions
    )
    findings += compare_mechanics(
        our_abilities,
        encounter.duration_seconds,
        mechanics,
        scope="the raid",
        phase_shares=phase_shares,
    )
    findings += compare_lethal_abilities(loaded.deaths, mechanics)
    findings += compare_phase_cost(
        loaded.damage_taken, encounter.phases, encounter.phase_transitions
    )
    verdict = classify_attempt(encounter, loaded.deaths, mechanics)
    if verdict is not None:
        findings.append(verdict)
```

- [ ] **Step 4: Confirm the routing, and change nothing**

`RAID_PLACEMENTS` in `src/wowperf/domain/report/raid_ledger.py` already carries
`("mechanics.", "mechanics_rows")`, and the first matching prefix wins, so `mechanics.lethal.*`
and `mechanics.phase.*` route themselves onto the Mechanics tab with no edit.

`wipe.cause` matches no prefix and falls through to Summary's unclaimed observations, which is
where Layer 1 wants it. **Add no row for it.** Promoting it to the Summary headline is Layer 2's
job, and a placement added here would have to be removed there.

So this step edits no source file — it exists to make that a decision rather than an oversight,
and the two tests in Step 1 hold it.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/domain/analysis/test_encounter_service.py tests/domain/report/test_raid_ledger.py -v
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

Golden-file tests for the raid page may now fail with new findings present. That churn is
expected and is the regression net: read each diff, confirm it is the new families appearing where
Task 4 and this task put them, and regenerate.

- [ ] **Step 7: Verify against the real night**

```bash
uv run wowperf raid https://www.warcraftlogs.com/reports/DJfap6RcYKhPGHXZ --fight 13 --cache-dir ../progression-layer-3/cache --out out
```

Then read the findings file and confirm by eye: `wipe.cause` is **absent** (fight 13 is a kill),
`mechanics.lethal.*` is present, and `mechanics.phase.*` names phases from encounter 3470's list —
`Stage One: Soulcoiler Initiation`, `Intermission: Ritual of Awakening`, `Stage Two: Uncoiling`.

Then run a wipe from the same night and confirm `wipe.cause` **is** present:

```bash
uv run wowperf raid https://www.warcraftlogs.com/reports/DJfap6RcYKhPGHXZ --fight 5 --cache-dir ../progression-layer-3/cache --out out
```

The roster of this report are real people. Refer to them by class, spec, role or index in any
note, commit message or test you write from what you see.

- [ ] **Step 8: Commit**

```bash
git add -A
```

```bash
git commit -m "Let a boss fight report what killed it and why it ended

The three new analysers existed and nothing called them. This wires
them, routes their ids to the tabs the design places them on, and
verifies against a real Mythic night: a kill mints no verdict, a wipe
does, and the phase findings carry the names the API supplies rather
than any table this project encodes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Section 6's ranked list: Task 4 adds the phase label; the ranking itself already
exists and the spec says not to rebuild it. Section 6's `mechanics.lethal`: Task 5. Section 8's
`wipe.cause`: Task 7. Section 9's `mechanics.phase` and the phase gate: Tasks 1, 2, 3, 6. Section
10's families: all five accounted for, `players.damage.*` unchanged because it already exists and
already caps. **Deliberately not in this plan:** section 7's grid table, section 8.4's chart and
section 11's layout — all Layer 2, as the header states.

**Type consistency.** `PhaseShare` is defined in Task 3 and consumed in Task 4 under the same
name and field spellings. `phase_at` is defined in Task 2 and consumed in Tasks 3 and 6.
`compare_lethal_abilities`, `compare_phase_cost` and `classify_attempt` are defined in Tasks 5, 6
and 7 and consumed in Task 8 with the same signatures.

**Files modified, and the one that is not.** Task 8 was drafted to edit `raid_ledger.py` and does
not: the table already carries a bare `mechanics.` prefix, and `wipe.cause` should stay unclaimed
until Layer 2 promotes it. The step survives as a confirmation with two tests behind it, because
"we checked and nothing was needed" and "we forgot" look identical in a diff.

**One known unknown, and it is scoped.** Tasks 4, 5, 6 and 8 append to test files whose existing
fixture helpers this plan does not reproduce — `_our_rows`, `_sample_taking`, `_loaded_wipe_with`,
`_defensives`, `_consumables`, `_mechanics_sample`, `_tab_for`. Each of those steps says to read
the file and follow its shape. No step invents a helper the plan then relies on silently: every
one is named here, and an implementer who cannot find its equivalent should write it rather than
guess at a different spelling.

**`Player` takes five required fields** — `actor_id`, `name`, `class_name`, `spec`, `item_level` —
and Task 7's helper passes all five. Checked against `src/wowperf/domain/model.py:23`.
