# The wipe call Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A raid pull that reaches its fourth roster death is *lost* if it wiped and *dirty* if it killed; a lost wipe reads its heavy moments only up to that death and stops carding deaths there.

**Architecture:** One pure domain module, `src/wowperf/domain/analysis/wipe_call.py`, holds the rule (`WIPE_CALL_DEATHS = 4`, `lost_at`, `is_dirty`, `deaths_after`) and the two findings. `analyse_encounter` emits the findings and narrows the span `analyse_spikes` reads. The report layer reads the same functions for the death-card fold, the raid header and the attempt rows. The night page builds its pulls with `build_raid_report` and gets everything through it, with no code of its own.

**Tech Stack:** Python 3, pydantic `Frozen` models, Jinja2 templates, pytest, uv.

**Spec:** `docs/plans/2026-10-07-wipe-call-design.md` — read it before Task 1.

## Global Constraints

- The constant: `WIPE_CALL_DEATHS = 4`, the same at every raid size.
- What counts as a death:
  - It is a **roster** death: `death.actor_id` is one of `loaded.players`.
  - Deaths are ordered by `(timestamp_ms, actor_id)`.
  - A player who is battle-rezzed and dies again counts twice.
- The finding ids and their badges are exactly these two:
  - `wipe.lost`, badge `Confidence.DERIVED`.
  - `raid.dirty_kill`, badge `Confidence.MEASURED`.
- The page strings are copied verbatim:
  - Raid header on a dirty kill: `Killed — dirty, N deaths`.
  - Attempt-row verdict on a dirty kill: `dirty kill`.
  - Fold line: `N more deaths after the 4th — not carded`, or `1 more death after the 4th — not carded` for one.
- What stays whole:
  - A kill is never cut.
  - The deaths, defensives (per pull and pooled), consumables, interrupts and mechanics findings, phase cost, `wipe.cause`, pace and kill time all keep reading the whole pull.
  - So do the alive-over-time chart, kill speed and reference selection.
- `src/wowperf/domain/` performs no I/O.
- Every new file starts with two `# ABOUTME: ` lines.
- Names in `tests/` are only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`.
- Never name a real player from reports `cW38jmwdnZfbHVL4` or `6jHcTvtB4XAMGZag` anywhere: not in code, tests, commits or the final report.
- Shell setup:
  - Every bash command that runs `uv` starts with `export PATH="$HOME/.local/bin:$PATH" && `.
  - Use relative forward-slash paths in shell commands.
- Commits:
  - Commit with `/mingw64/bin/git` (the bare `git commit` is refused by the RTK hook).
  - Imperative subject, no `feat:` prefix, plain ASCII only.
  - End every message with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Never `--no-verify`.
- Work on the existing branch `wipe-call`.

---

### Task 1: Record the baseline before any code changes

The live run in Task 10 has to show whether shortening the span ranks a moment that never ranked before. That takes the findings as they are today, so they are captured first.

**Files:** none in the repository; output goes to the git-ignored `out/wipe-call-baseline/`.

- [ ] **Step 1: Confirm the tree is the design commit and nothing else**

Run: `/mingw64/bin/git status --short && /mingw64/bin/git log --oneline -2`
Expected: no changes. The last commit is the design document ("Design the wipe call: ...").

- [ ] **Step 2: Run the night command on both reports from the cache**

Run, one at a time:
```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf night cW38jmwdnZfbHVL4 --no-compare --out out/wipe-call-baseline
```
```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf night 6jHcTvtB4XAMGZag --no-compare --out out/wipe-call-baseline
```
Expected: each writes `<code>.night.json` and `<code>.night.html`, and prints its point spend. The cache was warm on 2026-10-07, so the spend should be near zero. **If either run reports more than 50 points spent, stop and report to RwlRwlRwlRwl before going on.**

- [ ] **Step 3: Check that the baseline carries heavy moments**

Run: `grep -c '"healing.spikes"' out/wipe-call-baseline/cW38jmwdnZfbHVL4.night.json out/wipe-call-baseline/6jHcTvtB4XAMGZag.night.json`
Expected: a count above zero for each file. **If either is zero, stop:** Task 10's comparison cannot be made from the night command, and RwlRwlRwlRwl has to choose another route.

Nothing to commit.

---

### Task 2: The rule

**Files:**
- Create: `src/wowperf/domain/analysis/wipe_call.py`
- Test: `tests/domain/analysis/test_wipe_call.py`

**Interfaces:**
- Produces:
  - `WIPE_CALL_DEATHS: int = 4`
  - `CALL_ORDINAL: str = "4th"`
  - `death_order(death: Death) -> tuple[int, int]`
  - `roster_deaths_in_order(loaded: LoadedEncounter) -> tuple[Death, ...]`
  - `lost_at(loaded: LoadedEncounter) -> Death | None`
  - `is_dirty(loaded: LoadedEncounter) -> bool`
  - `deaths_after(deaths: Sequence[Death], lost: Death) -> tuple[Death, ...]`

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/analysis/test_wipe_call.py`:

```python
# ABOUTME: The wipe call: which roster death loses a wipe, and which kills read as dirty.
# ABOUTME: Boundaries at three and four deaths, ties, pets, and a player who dies twice.

from wowperf.domain.analysis.wipe_call import (
    CALL_ORDINAL,
    WIPE_CALL_DEATHS,
    deaths_after,
    is_dirty,
    lost_at,
)
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import Death
from wowperf.domain.model import Player

ROSTER = (
    Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=700),
    Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Protection", item_level=700),
    Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=700),
    Player(actor_id=4, name="Кириллица", class_name="Rogue", spec="Subtlety", item_level=700),
)
PET = 99
"""An actor on no roster: a pet or an unidentified actor whose death the log still lists."""

START_MS = 10_000


def a_pull(*, kill: bool, deaths: tuple[tuple[int, int], ...]) -> LoadedEncounter:
    """A pull of `ROSTER`; each death is (actor id, seconds into the pull)."""
    names = {player.actor_id: player.name for player in ROSTER}
    encounter = Encounter(
        report_code="abc123", fight_id=7, encounter_id=3470, boss_name="Emberkin",
        difficulty=5, partition=1, size=20, kill=kill, start_ms=START_MS, end_ms=250_000,
        players=ROSTER,
    )
    return LoadedEncounter(
        encounter=encounter,
        deaths=tuple(
            Death(player_name=names.get(actor, "Stonewake"), actor_id=actor,
                  timestamp_ms=START_MS + seconds * 1_000, killing_blow="Ravenous Feast")
            for actor, seconds in deaths
        ),
    )


def test_the_call_is_four_deaths_named_the_fourth() -> None:
    assert WIPE_CALL_DEATHS == 4
    assert CALL_ORDINAL == "4th"


def test_three_roster_deaths_do_not_lose_a_wipe() -> None:
    assert lost_at(a_pull(kill=False, deaths=((1, 30), (2, 40), (3, 60)))) is None


def test_the_fourth_roster_death_in_time_order_loses_a_wipe() -> None:
    # Listed out of order, as a stream may list them: the call is the fourth by time.
    loaded = a_pull(kill=False, deaths=((4, 90), (1, 30), (2, 40), (1, 120), (3, 60)))

    lost = lost_at(loaded)

    assert lost is not None
    assert (lost.actor_id, lost.timestamp_ms) == (4, START_MS + 90_000)


def test_a_tie_breaks_on_the_lowest_actor_id() -> None:
    # Bríala (3) and Кириллица (4) die in the same millisecond: 3 is third, 4 is the call.
    loaded = a_pull(kill=False, deaths=((1, 30), (2, 40), (4, 60), (3, 60)))

    lost = lost_at(loaded)

    assert lost is not None
    assert lost.actor_id == 4


def test_a_death_off_the_roster_never_counts() -> None:
    three_and_a_pet = ((1, 30), (2, 40), (PET, 50), (3, 60))
    assert lost_at(a_pull(kill=False, deaths=three_and_a_pet)) is None

    lost = lost_at(a_pull(kill=False, deaths=(*three_and_a_pet, (4, 70))))
    assert lost is not None
    assert lost.actor_id == 4


def test_a_player_who_dies_twice_counts_twice() -> None:
    # Emberkin dies, is battle-rezzed, and dies again: two of the four.
    loaded = a_pull(kill=False, deaths=((1, 30), (1, 50), (2, 60), (3, 70)))

    lost = lost_at(loaded)

    assert lost is not None
    assert (lost.actor_id, lost.timestamp_ms) == (3, START_MS + 70_000)


def test_a_kill_is_never_lost_and_is_dirty_from_four_deaths() -> None:
    four = a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60), (4, 70)))
    three = a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60)))

    assert lost_at(four) is None
    assert is_dirty(four) is True
    assert is_dirty(three) is False


def test_a_pets_death_does_not_make_a_kill_dirty() -> None:
    assert is_dirty(a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60), (PET, 70)))) is False


def test_a_wipe_is_never_dirty() -> None:
    assert is_dirty(a_pull(kill=False, deaths=((1, 30), (2, 40), (3, 60), (4, 70), (1, 80)))) is False


def test_deaths_after_the_call_count_every_actor_strictly_after_it() -> None:
    # The call is Кириллица at 60 s. A pet at 61 s and Emberkin again at 70 s follow it;
    # Stonewake in the call's own millisecond with a lower actor id does not.
    loaded = a_pull(
        kill=False,
        deaths=((1, 30), (2, 60), (3, 50), (4, 60), (PET, 61), (1, 70)),
    )
    lost = lost_at(loaded)
    assert lost is not None
    assert lost.actor_id == 4

    after = deaths_after(loaded.deaths, lost)

    assert sorted((one.actor_id, one.timestamp_ms - START_MS) for one in after) == [
        (1, 70_000), (PET, 61_000),
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_wipe_call.py -v`
Expected: FAIL during collection, with `ModuleNotFoundError: No module named 'wowperf.domain.analysis.wipe_call'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/analysis/wipe_call.py`:

```python
# ABOUTME: The wipe call: a pull is lost at its fourth roster death, and a kill past it is dirty.
# ABOUTME: One fixed count, the one raid leaders call, measured on twenty-player pulls only.

from collections.abc import Sequence

from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import Death

WIPE_CALL_DEATHS = 4
"""The roster death at which a wipe is lost and a kill is dirty.

Measured 2026-10-07 offline on 37 cached twenty-player pulls, 9 kills and 28
wipes (`cW38jmwdnZfbHVL4` Heroic, `6jHcTvtB4XAMGZag` Mythic). One kill reached
a fourth death, 12 s before the boss died; no other passed three. 26 wipes
reached it, a median 15 s before their end, and 77% of all wipe deaths came
after it. A fixed count rather than a share of the roster: no pull of another
size was measured, and four is the count raid leaders call. Design
`docs/plans/2026-10-07-wipe-call-design.md` section 3.
"""

CALL_ORDINAL = f"{WIPE_CALL_DEATHS}th"
"""How the page names the call's death. "th" is right for every count from 4 to 20."""


def death_order(death: Death) -> tuple[int, int]:
    """The order deaths are counted in: by time, ties to the lowest actor id.

    The rule `first_roster_death` breaks ties by, so a stream listing two
    simultaneous deaths in either order names the same call.
    """
    return (death.timestamp_ms, death.actor_id)


def roster_deaths_in_order(loaded: LoadedEncounter) -> tuple[Death, ...]:
    """Every roster player's death, in `death_order`.

    Filtered to `loaded.players` as `roster_deaths` filters: a pet or an
    unidentified actor dying is not a roster death. A player who is
    battle-resurrected and dies again is in here twice, as a raid leader
    counts them.
    """
    roster_ids = {player.actor_id for player in loaded.players}
    return tuple(
        sorted((death for death in loaded.deaths if death.actor_id in roster_ids), key=death_order)
    )


def lost_at(loaded: LoadedEncounter) -> Death | None:
    """The roster death a wipe is lost at, or None on a kill or a wipe short of the call."""
    if loaded.encounter.kill:
        return None
    ordered = roster_deaths_in_order(loaded)
    if len(ordered) < WIPE_CALL_DEATHS:
        return None
    return ordered[WIPE_CALL_DEATHS - 1]


def is_dirty(loaded: LoadedEncounter) -> bool:
    """A kill with the call's count of roster deaths or more. A wipe never is."""
    return loaded.encounter.kill and len(roster_deaths_in_order(loaded)) >= WIPE_CALL_DEATHS


def deaths_after(deaths: Sequence[Death], lost: Death) -> tuple[Death, ...]:
    """Every death strictly after the call, roster or not: what the death cards leave out.

    Not filtered to the roster, because the death cards are not: a card is
    drawn for every death the log lists, and this counts the cards not drawn.
    """
    return tuple(death for death in deaths if death_order(death) > death_order(lost))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_wipe_call.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Lint and type-check the new files**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run ruff check src/wowperf/domain/analysis/wipe_call.py tests/domain/analysis/test_wipe_call.py && uv run mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/wipe_call.py tests/domain/analysis/test_wipe_call.py
```
```bash
/mingw64/bin/git commit -m "Add the wipe call rule: a pull is lost at its fourth roster death" -m "Raid leaders call a pull at four deaths. The rule lives in one pure module so
the findings, the spike span, the death cards and the labels all read the same
count and the same order.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The two findings

**Files:**
- Modify: `src/wowperf/domain/analysis/wipe_call.py`
- Test: `tests/domain/analysis/test_wipe_call.py`

**Interfaces:**
- Consumes: Task 2's functions, plus `clock_text(seconds: float) -> str` from `wowperf.domain.comparison.pace`.
- Produces:
  - `LOST_ID = "wipe.lost"`
  - `DIRTY_KILL_ID = "raid.dirty_kill"`
  - `analyse_wipe_call(loaded: LoadedEncounter) -> list[Finding]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_wipe_call.py`, and extend its import from `wowperf.domain.analysis.wipe_call` with `DIRTY_KILL_ID, LOST_ID, analyse_wipe_call`. Add `from wowperf.domain.findings import Confidence` to the imports.

```python
def test_a_lost_wipe_says_when_it_was_lost() -> None:
    # The pull runs 240 s; the call is the fourth death, 63 s in.
    loaded = a_pull(kill=False, deaths=((1, 60), (2, 61), (3, 62), (4, 63), (1, 100)))

    [finding] = analyse_wipe_call(loaded)

    assert finding.id == LOST_ID == "wipe.lost"
    assert finding.confidence is Confidence.DERIVED
    assert finding.title == "The pull was lost at the 4th death, 1:03 into 4:00"
    assert "heaviest moments" in finding.detail
    assert "death cards stop there" in finding.detail
    assert "twenty-player" in finding.detail


def test_a_dirty_kill_counts_its_roster_deaths() -> None:
    loaded = a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60), (4, 70), (PET, 75), (1, 80)))

    [finding] = analyse_wipe_call(loaded)

    assert finding.id == DIRTY_KILL_ID == "raid.dirty_kill"
    assert finding.confidence is Confidence.MEASURED
    assert finding.title == "Killed with 5 deaths"
    assert "nothing is cut on a kill" in finding.detail


def test_a_pull_short_of_the_call_states_nothing() -> None:
    assert analyse_wipe_call(a_pull(kill=False, deaths=((1, 30), (2, 40), (3, 60)))) == []
    assert analyse_wipe_call(a_pull(kill=True, deaths=((1, 30), (2, 40), (3, 60)))) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_wipe_call.py -v`
Expected: FAIL during collection, with `ImportError: cannot import name 'DIRTY_KILL_ID'`.

- [ ] **Step 3: Implement the findings**

In `src/wowperf/domain/analysis/wipe_call.py`, add these imports:

```python
from wowperf.domain.comparison.pace import clock_text
from wowperf.domain.findings import Confidence, Finding
```

Add below `CALL_ORDINAL`:

```python
LOST_ID = "wipe.lost"
DIRTY_KILL_ID = "raid.dirty_kill"

LOST_DETAIL = (
    f"A wipe is read as lost from the {CALL_ORDINAL} death of a roster player, counted in time "
    "order; a player who is battle-resurrected and dies again counts twice. From that death the "
    "heaviest moments of damage are no longer ranked or judged, and death cards stop there. "
    "Every other finding still reads the whole pull. The count is a fixed rule, measured on "
    "twenty-player pulls only, and it can be wrong: a raid can recover from it, and one kill "
    "measured did."
)
DIRTY_KILL_DETAIL = (
    f"A kill on which the log holds {WIPE_CALL_DEATHS} or more roster deaths, the count at which "
    "a wipe is read as lost; a player who is battle-resurrected and dies again counts twice. "
    "The kill is read whole: nothing is cut on a kill."
)
```

Add at the end of the module:

```python
def analyse_wipe_call(loaded: LoadedEncounter) -> list[Finding]:
    """`wipe.lost` on a lost wipe, `raid.dirty_kill` on a dirty kill, or nothing.

    "Lost" is a rule chosen, and the rule can be wrong, so it is derived; a
    dirty kill is a count against a definition, so it is measured.
    """
    encounter = loaded.encounter
    lost = lost_at(loaded)
    if lost is not None:
        into = clock_text((lost.timestamp_ms - encounter.start_ms) / 1000)
        return [
            Finding(
                id=LOST_ID,
                title=(
                    f"The pull was lost at the {CALL_ORDINAL} death, {into} into "
                    f"{clock_text(encounter.duration_seconds)}"
                ),
                detail=LOST_DETAIL,
                confidence=Confidence.DERIVED,
            )
        ]
    if is_dirty(loaded):
        return [
            Finding(
                id=DIRTY_KILL_ID,
                title=f"Killed with {len(roster_deaths_in_order(loaded))} deaths",
                detail=DIRTY_KILL_DETAIL,
                confidence=Confidence.MEASURED,
            )
        ]
    return []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_wipe_call.py -v`
Expected: all 13 PASS.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/wipe_call.py tests/domain/analysis/test_wipe_call.py
```
```bash
/mingw64/bin/git commit -m "State the wipe call as two findings: wipe.lost and raid.dirty_kill" -m "The narrative reads the findings file, never the page, so the call has to be
there too. Lost is a chosen rule that one measured kill outlived, so it is
derived; a dirty kill is a count against a definition, so it is measured.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Emit the findings on every raid pull, ranked and placed

**Files:**
- Modify: `src/wowperf/domain/analysis/encounter_service.py` (imports, and after the `wipe.cause` block at lines 177-184)
- Modify: `src/wowperf/domain/analysis/severity.py:8-18` (`SEVERITY_BY_FAMILY`)
- Modify: `src/wowperf/domain/report/raid_ledger.py:21-34` (`RAID_PLACEMENTS`)
- Test: `tests/domain/analysis/test_encounter_service.py`, `tests/domain/analysis/test_severity.py`, `tests/domain/report/test_raid_ledger.py`

**Interfaces:**
- Consumes: `analyse_wipe_call` and `lost_at` from Task 2 and Task 3.
- Produces:
  - `analyse_encounter` now also returns `wipe.lost` or `raid.dirty_kill`.
  - `SEVERITY_BY_FAMILY["raid"] == 0`.
  - `_raid_field_for("wipe.lost") == _raid_field_for("raid.dirty_kill") == "death_rows"`.
  - The test fixtures `WIPE_CALL_ROSTER` and `a_pull_of_four(*, kill: bool, death_seconds: tuple[int, ...]) -> LoadedEncounter` in `tests/domain/analysis/test_encounter_service.py`, which Task 5 reuses.

- [ ] **Step 1: Write the failing service tests**

Append to `tests/domain/analysis/test_encounter_service.py`. Its imports already cover `Confidence`, `Death`, `LoadedEncounter` and `Player`.

```python
WIPE_CALL_ROSTER = (
    *RAID,
    Player(actor_id=14, name="Кириллица", class_name="Mage", spec="Arcane", item_level=700),
)
"""Four raiders, so a wipe can reach the call without anyone on the roster dying twice."""


def a_pull_of_four(*, kill: bool, death_seconds: tuple[int, ...]) -> LoadedEncounter:
    """`a_loaded_encounter`'s fight with `WIPE_CALL_ROSTER`, one death per second given.

    Deaths go to every raider but Emberkin in turn, so Emberkin -- the one who
    holds the group answer in the heavy-moment fixture -- is alive throughout.
    The fight starts at 1 s and ends at 375 s, so it runs 6:14.
    """
    loaded = a_loaded_encounter()
    start = loaded.encounter.start_ms
    dying = WIPE_CALL_ROSTER[1:]
    deaths = tuple(
        Death(
            player_name=dying[index % len(dying)].name,
            actor_id=dying[index % len(dying)].actor_id,
            timestamp_ms=start + second * 1_000,
            killing_blow="Ravenous Feast",
        )
        for index, second in enumerate(death_seconds)
    )
    encounter = loaded.encounter.model_copy(
        update={
            "kill": kill,
            "boss_percentage": None if kill else 40.0,
            "players": WIPE_CALL_ROSTER,
        }
    )
    return loaded.model_copy(update={"encounter": encounter, "deaths": deaths})


def test_a_wipe_past_the_call_carries_wipe_lost_and_its_verdict() -> None:
    loaded = a_pull_of_four(kill=False, death_seconds=(60, 61, 62, 63, 90))

    findings = analyse_encounter(loaded, DEFENSIVES, Consumables())

    [lost] = [f for f in findings if f.id == "wipe.lost"]
    assert lost.confidence is Confidence.DERIVED
    assert lost.title == "The pull was lost at the 4th death, 1:03 into 6:14"
    assert "raid.dirty_kill" not in {f.id for f in findings}


def test_a_kill_past_the_call_carries_raid_dirty_kill_and_is_never_lost() -> None:
    loaded = a_pull_of_four(kill=True, death_seconds=(60, 61, 62, 63))

    ids = [f.id for f in analyse_encounter(loaded, DEFENSIVES, Consumables())]

    assert ids.count("raid.dirty_kill") == 1
    assert "wipe.lost" not in ids


def test_a_pull_short_of_the_call_carries_neither() -> None:
    for kill in (True, False):
        loaded = a_pull_of_four(kill=kill, death_seconds=(60, 61, 62))
        ids = {f.id for f in analyse_encounter(loaded, DEFENSIVES, Consumables())}
        assert not ids & {"wipe.lost", "raid.dirty_kill"}, (kill, ids)
```

- [ ] **Step 2: Write the failing severity and placement tests**

In `tests/domain/analysis/test_severity.py`, add `"raid",` to the `family` parametrize list right after `"wipe",`, and append:

```python
def test_a_dirty_kill_ranks_with_the_outcome_ahead_of_any_death() -> None:
    """`raid.dirty_kill` says how the kill ended, as `wipe.*` says how a wipe did."""
    ranked = rank_raid_findings([finding("deaths.total", 180.0), finding("raid.dirty_kill")])
    assert [item.id for item in ranked] == ["raid.dirty_kill", "deaths.total"]
```

In `tests/domain/report/test_raid_ledger.py`, append:

```python
def test_the_wipe_call_findings_land_on_the_deaths_tab() -> None:
    """Beside the cards the call folds, not in Summary's catch-all."""
    assert _raid_field_for("wipe.lost") == "death_rows"
    assert _raid_field_for("raid.dirty_kill") == "death_rows"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_encounter_service.py tests/domain/analysis/test_severity.py tests/domain/report/test_raid_ledger.py -v`
Expected FAILs:
- The three service tests: no `wipe.lost` / `raid.dirty_kill` is emitted. The "neither" test may pass already, which is fine: it is the guard.
- `test_every_family_the_raid_path_emits_has_a_severity[raid]` and `test_a_dirty_kill_ranks_with_the_outcome_ahead_of_any_death`.
- `test_the_wipe_call_findings_land_on_the_deaths_tab` (`None == "death_rows"`).

- [ ] **Step 4: Emit the findings**

In `src/wowperf/domain/analysis/encounter_service.py`, add the import in alphabetical position among the `wowperf.domain.analysis` imports:

```python
from wowperf.domain.analysis.wipe_call import analyse_wipe_call
```

Directly after the verdict block:

```python
    if verdict is not None:
        findings.append(verdict)
```

add:

```python
    findings += analyse_wipe_call(loaded)
```

Appended after `wipe.cause` on purpose. Both rank in severity 0 with no `seconds_lost`, and the sort is stable, so the verdict keeps leading the file.

- [ ] **Step 5: Rank the `raid` family and place both ids**

In `src/wowperf/domain/analysis/severity.py`, change the table's first entry:

```python
SEVERITY_BY_FAMILY = {
    "wipe": 0,
    "raid": 0,
```

At the end of that table's docstring, add this sentence: `` `raid` shares `wipe`'s rank: `raid.dirty_kill` says how a kill ended, as `wipe.*` says how a wipe did. ``

In `src/wowperf/domain/report/raid_ledger.py`, make these the first two entries of `RAID_PLACEMENTS`:

```python
RAID_PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("wipe.lost", "death_rows"),
    ("raid.dirty_kill", "death_rows"),
    ("defensives.unused.", "death_rows"),
```

`test_a_verdict_is_claimed_by_no_tab_prefix` keeps passing, because `"wipe.cause"` does not start with `"wipe.lost"`.

- [ ] **Step 6: Run the tests and read the family-list failure**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_encounter_service.py tests/domain/analysis/test_severity.py tests/domain/report/test_raid_ledger.py -v`
Expected:
- The new tests PASS.
- `test_the_family_list_matches_what_the_service_emits` FAILS with `emitted but not in RAID_FAMILIES: ['raid.dirty_kill']`. Its fixture `a_rich_encounter` is a kill with five roster deaths.
- **If it fails for any other reason, or does not fail, stop and report.** The fixture is then not what the gathered context says it is.

- [ ] **Step 7: Add the id to the family lists**

In `tests/domain/report/test_raid_ledger.py`:
- Append `"raid.dirty_kill",` as the last element of `RAID_FAMILIES` (lines 41-54).
- Append `"raid.dirty_kill",` as the last element of `_FAMILY_PREFIXES` (lines 68-95).
- `wipe.lost` goes in neither list. Like `wipe.cause`, it never comes from the kill fixture; its placement is pinned by the test from Step 2.

- [ ] **Step 8: Run the whole offline suite**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q`
Expected: PASS. `test_raid_build.py`'s `one_of_every_raid_family` now includes `raid.dirty_kill` and must place it exactly once.
- **If a golden page test fails** (`tests/adapters/render/golden/raid.html`), first read the diff. Regenerate only if every change is the new Deaths-tab row or the ordering it causes: `uv run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update`. Then inspect `/mingw64/bin/git diff tests/adapters/render/golden/` and commit it with this task.
- Any other failure is a defect to diagnose, not a fixture to edit.

- [ ] **Step 9: Lint, type-check, commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy`
Expected: no errors.

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/encounter_service.py src/wowperf/domain/analysis/severity.py src/wowperf/domain/report/raid_ledger.py tests/domain/analysis/test_encounter_service.py tests/domain/analysis/test_severity.py tests/domain/report/test_raid_ledger.py
```
(Add `tests/adapters/render/golden/raid.html` too if Step 8 regenerated it.)
```bash
/mingw64/bin/git commit -m "Emit the wipe call on every raid pull, ranked with the outcome" -m "raid.dirty_kill is a new family, and a family missing from the severity table
ranks last. It says how a kill ended, so it ranks with wipe. Both ids land on
the Deaths tab, beside the cards the call folds.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Read a lost wipe's heavy moments only up to the call

**Files:**
- Modify: `src/wowperf/domain/analysis/encounter_service.py:164-176` (the spike block)
- Test: `tests/domain/analysis/test_encounter_service.py`

**Interfaces:**
- Consumes:
  - `lost_at` from Task 2.
  - `a_pull_of_four` and `WIPE_CALL_ROSTER` from Task 4.
  - `an_encounter_with_a_heavy_moment`, `GROUP_EXTERNALS`, `SPIKES_ID`, `UNAVAILABLE_ID` and `answers_for`, already in the test module.
- Produces: on a lost wipe, `analyse_spikes` reads `span = (start_ms, lost.timestamp_ms)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/analysis/test_encounter_service.py`:

```python
def a_pull_of_four_with_a_heavy_moment(
    *, kill: bool, death_seconds: tuple[int, ...]
) -> LoadedEncounter:
    """`a_pull_of_four` taking `an_encounter_with_a_heavy_moment`'s damage and its one answer.

    Steady damage every second and a burst at 1:40 to 1:45, answered by
    Emberkin two seconds before it.
    """
    heavy = an_encounter_with_a_heavy_moment()
    return a_pull_of_four(kill=kill, death_seconds=death_seconds).model_copy(
        update={"damage_taken": heavy.damage_taken, "casts": heavy.casts}
    )


def spike_reading(loaded: LoadedEncounter) -> Finding:
    answers = answers_for(WIPE_CALL_ROSTER, ThroughputCooldowns(), GROUP_EXTERNALS, Roles())
    findings = analyse_encounter(loaded, DEFENSIVES, Consumables(), answers=answers)
    [reading] = [f for f in findings if f.id in (SPIKES_ID, UNAVAILABLE_ID)]
    return reading


def test_a_lost_wipe_reads_its_heavy_moments_only_up_to_the_call() -> None:
    # The call falls at 1:03; the burst at 1:40 is after it. Before the call the
    # damage is steady, so no window reaches twice the median and none ranks.
    reading = spike_reading(
        a_pull_of_four_with_a_heavy_moment(kill=False, death_seconds=(60, 61, 62, 63))
    )

    assert reading.id == UNAVAILABLE_ID
    assert reading.title == "No moment of this fight was heavy enough to rank"


def test_a_wipe_short_of_the_call_reads_the_whole_fight() -> None:
    reading = spike_reading(
        a_pull_of_four_with_a_heavy_moment(kill=False, death_seconds=(60, 61, 62))
    )

    assert reading.id == SPIKES_ID
    assert reading.evidence[0].startswith("1:40 to 1:45, the heaviest")


def test_a_dirty_kill_reads_the_whole_fight() -> None:
    reading = spike_reading(
        a_pull_of_four_with_a_heavy_moment(kill=True, death_seconds=(60, 61, 62, 63))
    )

    assert reading.id == SPIKES_ID
    assert reading.evidence[0].startswith("1:40 to 1:45, the heaviest")
```

If `Finding` is not yet imported in this module, add `Finding` to its existing `from wowperf.domain.findings import Confidence` line.

- [ ] **Step 2: Run the tests to verify the first fails**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_encounter_service.py -k "heavy_moments_only_up_to_the_call or short_of_the_call_reads or dirty_kill_reads" -v`
Expected:
- `test_a_lost_wipe_reads_its_heavy_moments_only_up_to_the_call` FAILS: the reading is `healing.spikes`, with the burst at 1:40.
- The other two PASS already. They are the guards that the cut touches only lost wipes.

- [ ] **Step 3: Narrow the span**

In `src/wowperf/domain/analysis/encounter_service.py`, extend the wipe-call import to:

```python
from wowperf.domain.analysis.wipe_call import analyse_wipe_call, lost_at
```

Replace:

```python
    if answers is not None:
        span = (encounter.start_ms, encounter.end_ms)
```

with:

```python
    if answers is not None:
        # A lost wipe's heaviest moments are ranked, weighed and judged only up
        # to the call: collapse damage would otherwise take ranked slots and
        # move the median every earlier moment is measured against.
        lost = lost_at(loaded)
        span = (encounter.start_ms, encounter.end_ms if lost is None else lost.timestamp_ms)
```

The rest of the block (`combat=(span,)`, `setting="fight"`) is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_encounter_service.py -v`
Expected: all PASS.

- [ ] **Step 5: Mutation check**

Change `encounter.end_ms if lost is None else lost.timestamp_ms` temporarily to `encounter.end_ms`, then run the same command. Expected: `test_a_lost_wipe_reads_its_heavy_moments_only_up_to_the_call` FAILS. Restore the line, and confirm the run passes again.

- [ ] **Step 6: Full suite, lint, types, commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, no errors.

```bash
/mingw64/bin/git add src/wowperf/domain/analysis/encounter_service.py tests/domain/analysis/test_encounter_service.py
```
```bash
/mingw64/bin/git commit -m "Read a lost wipe's heavy moments only up to the wipe call" -m "Measured on 28 wipes: 3 of the 4 heavy moments after the fourth death went
unanswered, against 3 of 36 before it. Ending the span at the call keeps
collapse damage out of the ranking and out of the median, not only out of the
verdicts.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Fold a lost wipe's death cards after the call

**Files:**
- Modify: `src/wowperf/domain/report/deaths.py` (`build_deaths` at lines 536-645, plus a new `folded_deaths_line`)
- Modify: `src/wowperf/domain/report/raid_model.py:179-185` (new field `deaths_folded`)
- Modify: `src/wowperf/domain/report/raid_build.py:489-499` and `:519-536` (the `deaths=` / `deaths_note=` arguments)
- Modify: `src/wowperf/adapters/render/_deaths.html.j2:158-160` (after the card loop's `{% endfor %}`)
- Test: `tests/domain/report/test_raid_build.py`, `tests/adapters/render/test_raid_html_invariants.py`

**Interfaces:**
- Consumes: `lost_at`, `deaths_after`, `death_order` and `CALL_ORDINAL` from Task 2.
- Produces:
  - `build_deaths(..., stop_after: Death | None = None)`.
  - `folded_deaths_line(deaths: Sequence[Death], lost: Death | None) -> str`.
  - `RaidReport.deaths_folded: str = ""`.

- [ ] **Step 1: Write the failing builder tests**

Append to `tests/domain/report/test_raid_build.py`:

```python
A_COLLAPSE = (
    a_death(EMBERKIN, FIRST_DEATH_MS),
    a_death(STONEWAKE, FIRST_DEATH_MS + 3_000),
    a_death(HEALER, FIRST_DEATH_MS + 8_000),
    # Emberkin, battle-rezzed and dead again: the fourth roster death, the call.
    a_death(EMBERKIN, FIRST_DEATH_MS + 20_000),
    a_death(STONEWAKE, FIRST_DEATH_MS + 25_000),
    a_death(HEALER, FIRST_DEATH_MS + 26_000),
)
"""Six deaths on a roster of three: the call is the fourth, two follow it."""


def a_report_of(loaded: LoadedEncounter, *, death_cards: bool = True) -> RaidReport:
    return build_raid_report(
        loaded, (), EMBERKIN, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES, NO_ROLES,
        death_cards=death_cards,
    )


def test_a_lost_wipe_cards_its_deaths_up_to_the_call_and_folds_the_rest() -> None:
    report = a_report_of(a_wipe_that_started_with(*A_COLLAPSE))

    assert [card.player for card in report.deaths] == [
        "Emberkin", "Stonewake", "Bríala", "Emberkin",
    ]
    assert report.deaths_folded == "2 more deaths after the 4th — not carded"


def test_one_death_after_the_call_is_folded_in_the_singular() -> None:
    report = a_report_of(a_wipe_that_started_with(*A_COLLAPSE[:5]))

    assert len(report.deaths) == 4
    assert report.deaths_folded == "1 more death after the 4th — not carded"


def test_a_wipe_that_ends_on_the_call_folds_nothing() -> None:
    report = a_report_of(a_wipe_that_started_with(*A_COLLAPSE[:4]))

    assert len(report.deaths) == 4
    assert report.deaths_folded == ""


def test_a_dirty_kill_cards_every_death() -> None:
    wipe = a_wipe_that_started_with(*A_COLLAPSE)
    kill = wipe.model_copy(
        update={"encounter": wipe.encounter.model_copy(update={"kill": True})}
    )

    report = a_report_of(kill)

    assert len(report.deaths) == 6
    assert report.deaths_folded == ""


def test_a_run_that_asked_for_no_cards_folds_nothing() -> None:
    """`--no-deaths` built no card at all; `NO_CARDS_ASKED` says why, not a fold line."""
    report = a_report_of(a_wipe_that_started_with(*A_COLLAPSE), death_cards=False)

    assert report.deaths == ()
    assert report.deaths_folded == ""
    assert report.deaths_note == NO_CARDS_ASKED
```

- [ ] **Step 2: Write the failing render test**

Append to `tests/adapters/render/test_raid_html_invariants.py`:

```python
def test_a_lost_wipe_states_the_deaths_it_did_not_card() -> None:
    from tests.domain.report.test_raid_build import A_COLLAPSE, a_report_of, a_wipe_that_started_with

    html = render_raid(a_report_of(a_wipe_that_started_with(*A_COLLAPSE)))

    assert "2 more deaths after the 4th — not carded" in html
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_raid_build.py tests/adapters/render/test_raid_html_invariants.py -k "call or fold or dirty_kill_cards or asked_for_no_cards or did_not_card" -v`
Expected: FAIL. The two that build a lost wipe card all six deaths, and `RaidReport` has no attribute `deaths_folded`.

- [ ] **Step 4: Teach `build_deaths` to stop after the call**

In `src/wowperf/domain/report/deaths.py`:
- Add `from collections.abc import Sequence` at the top, if it is not already imported.
- Add `from wowperf.domain.analysis.wipe_call import CALL_ORDINAL, death_order, deaths_after` in alphabetical position among the `wowperf.domain.analysis` imports.

Add the keyword parameter after `throughput`:

```python
    throughput: ThroughputCooldowns = ThroughputCooldowns(),
    stop_after: Death | None = None,
) -> tuple[DeathCard, ...]:
```

Append this paragraph to the docstring:

```
    `stop_after` is a lost wipe's call (`wipe_call.lost_at`): no card is drawn
    for a death after it in `death_order`, and `folded_deaths_line` says how
    many that left out. None cards every death, as every kill and every
    Mythic+ run does.
```

Replace the loop header:

```python
    for index, death in enumerate(sorted(loaded.deaths, key=lambda d: d.timestamp_ms)):
```

with:

```python
    carded = [
        death
        for death in sorted(loaded.deaths, key=lambda d: d.timestamp_ms)
        if stop_after is None or death_order(death) <= death_order(stop_after)
    ]
    for index, death in enumerate(carded):
```

Add after `NO_CARDS_ASKED`:

```python
def folded_deaths_line(deaths: Sequence[Death], lost: Death | None) -> str:
    """The line standing for the cards a lost wipe does not draw, or "" where none were left out."""
    if lost is None:
        return ""
    after = len(deaths_after(deaths, lost))
    if not after:
        return ""
    return f"{quantity(after, 'more death', 'more deaths')} after the {CALL_ORDINAL} — not carded"
```

- [ ] **Step 5: Carry the line on the report**

In `src/wowperf/domain/report/raid_model.py`, add after `deaths_note: str = ""`:

```python
    # The line standing for the death cards a lost wipe does not draw, past
    # its fourth roster death. Empty on a kill, on a wipe short of the call,
    # and on a run that built no cards, whose `deaths_note` already says why.
    deaths_folded: str = ""
```

In `src/wowperf/domain/report/raid_build.py`:
- Add `from wowperf.domain.analysis.wipe_call import lost_at`.
- Add `folded_deaths_line` to the existing import from `wowperf.domain.report.deaths`.

Replace the `deaths = (...)` block with:

```python
    # `death_cards=False` skips the call rather than building cards and
    # throwing them away: the tier exists so the work is never done.
    lost = lost_at(loaded)
    deaths = (
        build_deaths(loaded, defensives, consumables, externals, self_resurrections,
                     trimmed=trimmed,
                     roles=roles if throughput is not None else None,
                     throughput=throughput or ThroughputCooldowns(),
                     stop_after=lost)
        if death_cards
        else ()
    )
```

In the `RaidReport(...)` call, add after the `deaths_note=...` argument:

```python
        deaths_folded=folded_deaths_line(loaded.deaths, lost) if death_cards else "",
```

- [ ] **Step 6: Render the line**

In `src/wowperf/adapters/render/_deaths.html.j2`, directly after the card loop's `{% endfor %}` (the one closing `{% for death in report.deaths %}`), insert:

```jinja
{% if report.deaths_folded %}
<p class="sub">{{ report.deaths_folded }}</p>
{% endif %}
```

The Mythic+ `Report` has no such attribute. Jinja reads a missing attribute as falsy, which is the same way `deaths_note` already works in this shared template.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_raid_build.py tests/adapters/render/test_raid_html_invariants.py -v`
Expected: all PASS.

- [ ] **Step 8: Mutation check**

Change `death_order(death) <= death_order(stop_after)` temporarily to `<`, then run the Step 7 command. Expected: `test_a_lost_wipe_cards_its_deaths_up_to_the_call_and_folds_the_rest` FAILS, because only three cards are drawn. Restore the line.

- [ ] **Step 9: Full suite, lint, types, commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, no errors. Apply the golden-page rule from Task 4 Step 8 if the golden raid page changes.

```bash
/mingw64/bin/git add src/wowperf/domain/report/deaths.py src/wowperf/domain/report/raid_model.py src/wowperf/domain/report/raid_build.py src/wowperf/adapters/render/_deaths.html.j2 tests/domain/report/test_raid_build.py tests/adapters/render/test_raid_html_invariants.py
```
```bash
/mingw64/bin/git commit -m "Stop a lost wipe's death cards at the call and count the rest" -m "On 28 measured wipes the cards ran to 456, 106 of them up to the fourth death.
The late cards show no more ready defensives than the early ones; they add
volume and bury the deaths that started the wipe. One line counts what was
left out, so nothing disappears silently.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Label a dirty kill in the raid header

**Files:**
- Modify: `src/wowperf/domain/report/raid_frame.py:43-61` (`build_raid_header`)
- Modify: `src/wowperf/domain/report/raid_build.py:536` (its one call site)
- Test: `tests/domain/report/test_raid_frame.py`

**Interfaces:**
- Consumes: `is_dirty` and `roster_deaths_in_order` from Task 2.
- Produces: `build_raid_header(loaded: LoadedEncounter) -> RaidHeader`. Its parameter was an `Encounter`.

- [ ] **Step 1: Write the failing tests and move the existing ones to the new signature**

In `tests/domain/report/test_raid_frame.py`:
- Change the imports to:
  ```python
  from wowperf.domain.encounter import Encounter, LoadedEncounter
  from wowperf.domain.events import Death
  from wowperf.domain.model import Player
  from wowperf.domain.report.raid_frame import build_raid_header
  ```
- Replace each of the four `header = build_raid_header(encounter)` lines (30, 47, 62, 76) with `header = build_raid_header(LoadedEncounter(encounter=encounter))`.

Then append:

```python
FOUR = (
    Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Frost", item_level=700),
    Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Arms", item_level=700),
    Player(actor_id=3, name="Bríala", class_name="Priest", spec="Holy", item_level=700),
    Player(actor_id=4, name="Кириллица", class_name="Rogue", spec="Outlaw", item_level=700),
)


def a_pull_with_deaths(count: int, *, kill: bool) -> LoadedEncounter:
    """`count` roster deaths, one per raider in turn, ten seconds apart."""
    return LoadedEncounter(
        encounter=an_encounter(kill=kill, fight_percentage=0.0 if kill else 12.4, players=FOUR),
        deaths=tuple(
            Death(player_name=FOUR[index % 4].name, actor_id=FOUR[index % 4].actor_id,
                  timestamp_ms=(index + 1) * 10_000, killing_blow="Ravenous Feast")
            for index in range(count)
        ),
    )


def test_a_kill_with_four_deaths_reads_as_dirty_and_counts_them() -> None:
    assert build_raid_header(a_pull_with_deaths(4, kill=True)).outcome == "Killed — dirty, 4 deaths"
    assert build_raid_header(a_pull_with_deaths(5, kill=True)).outcome == "Killed — dirty, 5 deaths"


def test_a_kill_with_three_deaths_reads_as_a_kill() -> None:
    assert build_raid_header(a_pull_with_deaths(3, kill=True)).outcome == "Killed"


def test_a_wipe_past_the_call_still_states_how_far_the_raid_got() -> None:
    assert build_raid_header(a_pull_with_deaths(6, kill=False)).outcome == "Wiped at 12.4% remaining"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_raid_frame.py -v`
Expected: the dirty-kill test FAILS (`'Killed' == 'Killed — dirty, 4 deaths'`), and the moved tests fail with attribute errors on `LoadedEncounter`.

- [ ] **Step 3: Implement**

In `src/wowperf/domain/report/raid_frame.py`, add `from wowperf.domain.analysis.wipe_call import is_dirty, roster_deaths_in_order`, then replace the head of `build_raid_header`:

```python
def build_raid_header(encounter: Encounter) -> RaidHeader:
    if encounter.kill:
        outcome = "Killed"
```

with:

```python
def build_raid_header(loaded: LoadedEncounter) -> RaidHeader:
    """The facts above the tabs; a kill past the wipe call is labelled dirty, nothing more."""
    encounter = loaded.encounter
    if is_dirty(loaded):
        outcome = f"Killed — dirty, {len(roster_deaths_in_order(loaded))} deaths"
    elif encounter.kill:
        outcome = "Killed"
```

The rest of the function is unchanged. If `Encounter` is now unused in this module's imports, remove it from the import line (ruff will flag it).

In `src/wowperf/domain/report/raid_build.py`, change `header=build_raid_header(loaded.encounter),` to `header=build_raid_header(loaded),`.

- [ ] **Step 4: Run the tests, the full suite, lint and types**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, no errors. Apply the golden-page rule from Task 4 Step 8 if the golden raid page changes: a golden kill with four or more roster deaths now reads dirty in its header.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/raid_frame.py src/wowperf/domain/report/raid_build.py tests/domain/report/test_raid_frame.py
```
```bash
/mingw64/bin/git commit -m "Label a kill past the wipe call as dirty in the raid header" -m "The header needs the pull's deaths to say so, so it takes the loaded encounter.
The night page quotes the header in each pull's label and inherits the label.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Label a dirty kill in the attempt rows

**Files:**
- Modify: `src/wowperf/domain/report/progression_frame.py:22-23`, `:92-106` (`_verdict`), `:185` (its call)
- Test: `tests/domain/report/test_progression_frame.py`

**Interfaces:**
- Consumes: `is_dirty` from Task 2.
- Produces:
  - `DIRTY_KILL_VERDICT = "dirty kill"`.
  - `_verdict(kill: bool, findings: Sequence[Finding], loaded: LoadedEncounter | None) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/report/test_progression_frame.py`:

```python
def a_kill_with_deaths(count: int) -> LoadedEncounter:
    """A deepened kill whose `count` deaths all fall on `FROST_MAGE`: a raider rezzed each time."""
    return a_loaded_attempt(
        3, remaining=0.01, seconds=180.0, players=(FROST_MAGE,), kill=True,
        deaths_after_ms=tuple(10_000 * (index + 1) for index in range(count)),
    )


def test_a_kill_past_the_wipe_call_reads_as_a_dirty_kill() -> None:
    [row] = build_attempt_rows(a_loaded_series(a_kill_with_deaths(4)))

    assert row.verdict == "dirty kill"
    assert row.is_kill is True


def test_a_kill_short_of_the_wipe_call_reads_as_a_kill() -> None:
    [row] = build_attempt_rows(a_loaded_series(a_kill_with_deaths(3)))

    assert row.verdict == "kill"


def test_a_kill_nobody_deepened_reads_as_a_kill() -> None:
    """With no deaths fetched the row cannot tell, and does not guess."""
    progression = a_series(an_attempt(3, 0.01, 180.0, kill=True))

    [row] = build_attempt_rows(LoadedProgression(progression=progression))

    assert row.verdict == "kill"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_progression_frame.py -k "wipe_call or nobody_deepened" -v`
Expected: `test_a_kill_past_the_wipe_call_reads_as_a_dirty_kill` FAILS (`'kill' == 'dirty kill'`). The other two PASS: they are the guards.

- [ ] **Step 3: Implement**

In `src/wowperf/domain/report/progression_frame.py`, add `from wowperf.domain.analysis.wipe_call import is_dirty`, and below `KILL_VERDICT`'s docstring:

```python
DIRTY_KILL_VERDICT = "dirty kill"
"""The Verdict cell of a kill past the wipe call: still a kill, with a lost pull's deaths.

Only where the attempt's deaths were fetched; an attempt nobody deepened keeps
`KILL_VERDICT`, because nothing says how many died."""
```

Change `_verdict`:

```python
def _verdict(kill: bool, findings: Sequence[Finding], loaded: LoadedEncounter | None) -> str:
```

Append this sentence to its docstring: `A kill whose deaths were fetched and that reached the wipe call reads "dirty kill".` Change its kill branch to:

```python
    if kill:
        return DIRTY_KILL_VERDICT if loaded is not None and is_dirty(loaded) else KILL_VERDICT
```

Change the call at line 185 to:

```python
                verdict=_verdict(
                    attempt.kill, (pull_findings or {}).get(attempt.fight_id, ()), loaded
                ),
```

- [ ] **Step 4: Run the tests, the full suite, lint and types**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, no errors.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/progression_frame.py tests/domain/report/test_progression_frame.py
```
```bash
/mingw64/bin/git commit -m "Label a kill past the wipe call as a dirty kill in the attempt rows" -m "The progression page and the night summary share these rows. An attempt whose
deaths were never fetched keeps reading kill rather than a guess.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: End-to-end assertions and the skills' prose

**Files:**
- Modify: `tests/e2e/test_raid_e2e.py`: `test_a_real_wipe_is_analysed_rather_than_refused` (ends at line 471) and `test_a_real_kill_is_read_against_the_kills_time_and_pace` (ends at line 827).
- Modify: `.claude/skills/mplus-analysis/SKILL.md` (the `healing.spikes` section, lines 188-216)
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` (the wipe/kill pull Summary paragraph, lines 243-250)
- Modify: `CLAUDE.md` (the "Repository Overview" analysers sentence)

The assertions are added to tests that already run, so the end-to-end suite spends no extra points.

- [ ] **Step 1: Assert the call on the canonical wipe**

In `test_a_real_wipe_is_analysed_rather_than_refused`, insert before `assert_mechanics_output_is_well_formed(...)`:

```python
    # The canonical wipe logs 21 deaths, far past the call.
    lost = [f for f in findings if f.id == "wipe.lost"]
    assert len(lost) == 1, "the canonical wipe was not called lost"
    assert lost[0].confidence is Confidence.DERIVED, "wipe.lost was not badged derived"
    assert "raid.dirty_kill" not in {f.id for f in findings}, "a wipe was labelled a dirty kill"
```

- [ ] **Step 2: Assert its absence on the canonical kill**

In `test_a_real_kill_is_read_against_the_kills_time_and_pace`, insert before the final `assert spent <= 140.0, ...`:

```python
    # The canonical kill has no deaths: neither side of the wipe call applies.
    assert "wipe.lost" not in ids, "a kill was called lost"
    assert "raid.dirty_kill" not in ids, "a deathless kill was labelled dirty"
```

- [ ] **Step 3: Check the end-to-end module still collects**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/e2e/test_raid_e2e.py --collect-only -q`
Expected: it collects with no errors. The live run happens in Task 10.

- [ ] **Step 4: Update the skills' prose**

Read the two skill sections named above, then add:

- In `.claude/skills/mplus-analysis/SKILL.md`'s `healing.spikes` section, as its own paragraph:
  > On a raid wipe that reached its fourth roster death, the heaviest moments are ranked and judged only up to that death: the pull carries `wipe.lost`, and a moment after it is never picked, so its absence says nothing about how the collapse was healed.
- In `.claude/skills/analyzing-a-run/SKILL.md`'s wipe and kill pull Summary paragraph:
  > A wipe that reached its fourth roster death carries `wipe.lost` (derived): the pull is read as lost from that death, its death cards stop there with one line counting the rest, and its heaviest moments are read only up to it. A kill with four roster deaths or more carries `raid.dirty_kill` (measured) and reads "dirty" in its header; nothing on a kill is cut.
- In `CLAUDE.md`, in the Repository Overview's list of what the analysers produce, change "the group's heaviest moments of damage taken and whether a group cooldown answered each" to "the group's heaviest moments of damage taken and whether a group cooldown answered each, read on a wipe only up to its fourth roster death".

- [ ] **Step 5: Run the skill tests and the full suite**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS. `tests/test_skills.py` checks only flags and field names, so it should stay green; if it fails, read why before changing anything.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add tests/e2e/test_raid_e2e.py .claude/skills/mplus-analysis/SKILL.md .claude/skills/analyzing-a-run/SKILL.md CLAUDE.md
```
```bash
/mingw64/bin/git commit -m "Assert the wipe call end to end and document it for the narrative" -m "The assertions ride on tests that already run against the canonical kill and
wipe, so the end-to-end suite spends nothing more. The skills tell the
narrative what wipe.lost and raid.dirty_kill license it to say.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: The live run, and what it found

The invariant: a new judgement is not done until a live run has exercised it and reported how often each state occurred.

**Files:** none in the repository. A comparison script is written to the git-ignored `out/wipe-call-live/compare.py`.

- [ ] **Step 1: Re-run the night command on both reports**

Run, one at a time:
```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf night cW38jmwdnZfbHVL4 --no-compare --out out/wipe-call-after
```
```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf night 6jHcTvtB4XAMGZag --no-compare --out out/wipe-call-after
```
Expected: both succeed and spend about the same points as Task 1, near zero.

- [ ] **Step 2: Write the comparison script**

Create `out/wipe-call-live/compare.py` with the Write tool:

```python
# ABOUTME: Compares the night findings before and after the wipe call, per pull.
# ABOUTME: Prints each state's frequency and every heavy moment that appeared or vanished.

import json
import re
from collections import Counter
from pathlib import Path

CODES = ("cW38jmwdnZfbHVL4", "6jHcTvtB4XAMGZag")
CLOCKS = re.compile(r"^(\d+:\d{2} to \d+:\d{2})")


def pulls(directory: str, code: str) -> dict[int, dict]:
    night = json.loads(Path(directory, f"{code}.night.json").read_text(encoding="utf-8"))
    return {pull["fight_id"]: pull for boss in night["bosses"] for pull in boss["pulls"]}


def moments(pull: dict) -> set[str]:
    return {
        match.group(1)
        for finding in pull["findings"] if finding["id"] == "healing.spikes"
        for line in finding["evidence"] if (match := CLOCKS.match(line))
    }


states: Counter[str] = Counter()
for code in CODES:
    before, after = pulls("out/wipe-call-baseline", code), pulls("out/wipe-call-after", code)
    for fight_id, pull in sorted(after.items()):
        ids = {finding["id"] for finding in pull["findings"]}
        if "wipe.lost" in ids:
            state = "lost wipe"
        elif "raid.dirty_kill" in ids:
            state = "dirty kill"
        elif pull["kill"]:
            state = "clean kill"
        else:
            state = "wipe short of the call"
        states[state] += 1
        gained = moments(pull) - moments(before.get(fight_id, {"findings": []}))
        lost = moments(before.get(fight_id, {"findings": []})) - moments(pull)
        if gained or lost:
            print(f"{code} fight {fight_id} ({state}): newly ranked {sorted(gained)}, "
                  f"no longer ranked {sorted(lost)}")
print(dict(states))
```

The layout is the one `cli.py` writes (lines 2220-2246): a top-level `bosses` list, each boss carrying a `pulls` list whose entries hold `fight_id`, `kill` and `findings`.

- [ ] **Step 3: Run it**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run python out/wipe-call-live/compare.py`
Expected: the design (§7) predicts `lost wipe` 26, `wipe short of the call` 2, `dirty kill` 1 (`cW38` fight 27), and `clean kill` 8. Any difference is a finding to explain, not to paper over: the night command may draw a slightly different set of pulls than the offline measurement did. **Every state must occur at least once; a state that never occurs is a defect.** The script also lists each pull whose ranked moments changed:
- A moment **no longer ranked** on a lost wipe is the intended cut.
- A moment **newly ranked** is the new verdict the design said the live run must show. Report each one.
- Any change on a kill or on a wipe short of the call is a defect.

- [ ] **Step 4: Run the end-to-end raid tests**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -m e2e tests/e2e/test_raid_e2e.py -k "wipe_is_analysed_rather_than_refused or kill_is_read_against_the_kills_time" -v`
Expected: both PASS. This spends live quota: about 140 points at most for the kill test, and a cold-cache wipe run, which was measured at 65 points on a wipe.

- [ ] **Step 5: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: PASS, no errors, and no warnings in the output.

- [ ] **Step 6: Open the pages and look**

Serve `out/wipe-call-after` over `uv run python -m http.server` (run it in the background), and open `cW38jmwdnZfbHVL4.night.html` in the browser pane, in a new tab. Confirm:
- Fight 27's pull label reads "Killed — dirty, …".
- Fight 30's Deaths tab ends its cards at the fourth death, followed by the "… more deaths after the 4th — not carded" line and the `wipe.lost` row.

Take a screenshot of each for the report to RwlRwlRwlRwl.

- [ ] **Step 7: Report**

Report to RwlRwlRwlRwl:
- The state distribution.
- Every newly ranked moment, with its pull and clock.
- The points spent.
- The two screenshots.

Name no player. Do not push and do not open a PR until RwlRwlRwlRwl asks.
