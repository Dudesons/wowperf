# Debuff Uptime on Bosses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every compared player on a Mythic+ key a "Debuff uptime on bosses" table and findings. The figure is the share of single-boss pull time the boss carried each of their debuffs, pets included, against their specialisation's parse sample.

**Architecture:**

- **Domain.** A pure layer pairs the enemy-debuff event stream into intervals (`domain/debuffs.py`). A second pure layer builds one player's debuffs on each boss (`domain/comparison/boss_debuffs.py`). The comparison then reuses the buff family's `uptime_measures` and thresholds unchanged (`domain/comparison/debuff_uptime.py`).
- **Adapter.** It fetches one `Debuffs`/`Enemies` stream per run. It also widens `ACTORS_QUERY` to carry `petOwner`, `type`, `subType` and `name`.
- **CLI.** It attaches a `BossDebuffs` to our side and to each parse member, exactly where `_fetch_parse_auras` attaches auras today.

**Tech Stack:** Python 3.12, pydantic `Frozen` models, httpx `MockTransport` for offline tests, Jinja2 for the page, `uv` for everything.

**Spec:** `docs/plans/2026-10-07-enemy-debuff-uptime-design.md`. Read it before starting. Its §4 is the component list this plan builds, in order.

## Global Constraints

- **Toolchain:** `uv` is not on PATH in the Bash tool. Begin every shell command that runs it with `export PATH="$HOME/.local/bin:$PATH";`.
- **Git:** use `/mingw64/bin/git` for every git command. The RTK hook can refuse a bare `git commit` in a worktree.
- **Hooks:** never `--no-verify` or any other hook bypass.
- **Commit messages:** plain ASCII only (non-ASCII is mangled into git messages here). Imperative subject, no `feat:`/`fix:` prefix. The body says why, not what. End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **File headers:** every new code file starts with two `# ABOUTME: ` lines.
- **Fixture names:** tests use only the sanctioned character names `Emberkin`, `Stonewake`, `Bríala` and `Кириллица`. NPC and boss names in fixtures are invented (`The Test Colossus`, `Fixture Add`). The two real report codes named in Task 8 are run live and never written into `tests/`.
- **Layering:** the domain performs no I/O. Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2` or touches disk.
- **Badges:** every finding carries a confidence badge. Debuff gaps and unjudged are `derived`. Unavailable is `measured`.
- **Thresholds:** reused, never redefined. `MIN_SAMPLE_FOR_AGGREGATE = 3`, `MIN_UPTIME_FRACTION = 0.10`, `UPTIME_GAP_FRACTION = 0.15` and `MAX_AURAS_REPORTED = 5` are imported from where they live today.
- **Comments:** never remove a comment unless it is actively false. Task 9 amends the ones this feature makes false.
- **Gate before the last commit:** `uv run ruff check .`, `uv run mypy` and `uv run pytest` all pass, and the output stays pristine.

---

## File Structure

| File | Responsibility |
| --- | --- |
| Create `src/wowperf/domain/debuffs.py` | `DebuffEvent`, `DebuffLog`, `DebuffInterval`, `PairingTally`, and `pair_debuffs`. The pairing knows nothing about bosses. |
| Create `src/wowperf/domain/comparison/boss_debuffs.py` | `Withheld`, `BossWindow`, `BossDebuffs`, `boss_windows_of`, `boss_debuffs`, `encounter_share`. One player's debuffs on each boss. |
| Create `src/wowperf/domain/comparison/debuff_uptime.py` | `debuff_fractions`, `per_member_fractions`, `compare_boss_debuffs_sample` (findings) and `boss_debuff_table` (table measures). |
| Modify `src/wowperf/domain/comparison/measures.py` | `BossCell`, `BossDebuffRow`, `BossDebuffTable`, and `PlayerMeasures.boss_debuffs`. |
| Modify `src/wowperf/domain/comparison/sample.py` | `ParseMember.boss_debuffs` and `ParseSample.debuff_eligible`. |
| Modify `src/wowperf/domain/comparison/service.py` | `ComparisonSubject.our_boss_debuffs`, and one call in `_compare_player`. |
| Modify `src/wowperf/domain/comparison/tables.py` | `_for_one` fills `boss_debuffs`. |
| Modify `src/wowperf/domain/report/model.py` | `ComparisonRow.cells` and `ComparisonTable.cell_headings`. |
| Modify `src/wowperf/domain/report/players.py` | The "Debuff uptime on bosses" table. |
| Modify `src/wowperf/adapters/render/_players.html.j2` | One column per boss. |
| Modify `src/wowperf/adapters/wcl/queries.py` | `ENEMY_DEBUFFS_QUERY`, and the wider `ACTORS_QUERY`. |
| Modify `src/wowperf/adapters/wcl/ingest.py` | `build_debuff_log`. |
| Modify `src/wowperf/adapters/wcl/repository.py` | `_actors` and `debuff_log`. |
| Modify `src/wowperf/cli.py` | `_debuff_log`, `_fetch_parse_boss_debuffs`, and the wiring in `analyze`. |
| Create `tests/e2e/test_boss_debuffs_e2e.py` | The live check. |
| Docs (Task 9) | CLAUDE.md, the master design §5, the wcl-api and mplus-analysis skills, and the comments this makes false. |

---

### Task 1: Pair the enemy-debuff stream into intervals

**Files:**
- Create: `src/wowperf/domain/debuffs.py`
- Test: `tests/domain/test_debuffs.py`

**Interfaces:**
- Consumes: `wowperf.domain.base.Frozen`, and `wowperf.domain.comparison.pace_boss.NpcActor` (fields `actor_id`, `game_id`, `name`, `sub_type`).
- Produces:
  - `DebuffEvent(applied: bool, timestamp_ms: int, source_id: int, source_instance: int = 0, target_id: int, target_instance: int = 0, ability_id: int)`
  - `DebuffLog(events: tuple[DebuffEvent, ...] = (), pet_owners: tuple[tuple[int, int], ...] = (), game_ids: tuple[tuple[int, int], ...] = (), npc_actors: tuple[NpcActor, ...] = (), ability_names: tuple[tuple[int, str], ...] = (), end_ms: int)`
  - `DebuffInterval(owner_id: int, ability_id: int, target_game_id: int, target_instance: int, start_ms: int, end_ms: int)`
  - `PairingTally(orphan_removes: int = 0, closed_at_end: int = 0, unresolved_targets: int = 0)`
  - `pair_debuffs(log: DebuffLog) -> tuple[tuple[DebuffInterval, ...], PairingTally]`

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/test_debuffs.py`:

```python
# ABOUTME: Pairing the enemy-debuff stream into intervals: pets fold, targets key on game id.
# ABOUTME: Pins re-keying across two actor ids, end closure, orphans, re-applies and instances.

from wowperf.domain.debuffs import (
    DebuffEvent,
    DebuffInterval,
    DebuffLog,
    PairingTally,
    pair_debuffs,
)

PLAYER = 171
PET = 172
BLOOD_PLAGUE = 55078
WHELP = 189893
WHELP_ACTOR = 261
WHELP_TWIN = 263
FIGHT_END = 100_000


def an_event(
    applied: bool,
    at: int,
    *,
    source: int = PLAYER,
    source_instance: int = 0,
    target: int = WHELP_ACTOR,
    instance: int = 1,
) -> DebuffEvent:
    return DebuffEvent(
        applied=applied,
        timestamp_ms=at,
        source_id=source,
        source_instance=source_instance,
        target_id=target,
        target_instance=instance,
        ability_id=BLOOD_PLAGUE,
    )


def a_log(*events: DebuffEvent) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=((WHELP_ACTOR, WHELP), (WHELP_TWIN, WHELP)),
        end_ms=FIGHT_END,
    )


def spans(intervals: tuple[DebuffInterval, ...]) -> list[tuple[int, int]]:
    return [(one.start_ms, one.end_ms) for one in intervals]


def test_an_apply_and_its_remove_make_one_interval_owned_by_the_caster() -> None:
    intervals, tally = pair_debuffs(a_log(an_event(True, 1000), an_event(False, 4000)))

    assert intervals == (
        DebuffInterval(
            owner_id=PLAYER,
            ability_id=BLOOD_PLAGUE,
            target_game_id=WHELP,
            target_instance=1,
            start_ms=1000,
            end_ms=4000,
        ),
    )
    assert tally == PairingTally()


def test_a_pets_application_is_owned_by_its_owner() -> None:
    intervals, _ = pair_debuffs(
        a_log(
            an_event(True, 1000, source=PET, source_instance=2),
            an_event(False, 3000, source=PET, source_instance=2),
        )
    )

    assert [one.owner_id for one in intervals] == [PLAYER]


def test_one_enemy_logged_under_two_actor_ids_closes_its_own_interval() -> None:
    """Measured 2026-10-07 on a real key: 13 of one player's 168 applications
    opened on one actor id and closed on another of the same game id and copy
    number. Keyed on the actor id, every one of them would read as never removed.
    """
    intervals, tally = pair_debuffs(
        a_log(an_event(True, 1000, target=WHELP_ACTOR), an_event(False, 23_700, target=WHELP_TWIN))
    )

    assert spans(intervals) == [(1000, 23_700)]
    assert (tally.orphan_removes, tally.closed_at_end) == (0, 0)


def test_an_interval_still_open_is_closed_at_the_end_of_the_fight() -> None:
    intervals, tally = pair_debuffs(a_log(an_event(True, 90_000)))

    assert spans(intervals) == [(90_000, FIGHT_END)]
    assert tally.closed_at_end == 1


def test_a_remove_with_no_open_application_is_counted_and_dropped() -> None:
    intervals, tally = pair_debuffs(a_log(an_event(False, 5000)))

    assert intervals == ()
    assert tally.orphan_removes == 1


def test_a_second_apply_while_open_keeps_the_first_start() -> None:
    intervals, tally = pair_debuffs(
        a_log(
            an_event(True, 1000),
            an_event(True, 2000),
            an_event(False, 3000),
            an_event(False, 4000),
        )
    )

    assert spans(intervals) == [(1000, 3000)]
    assert tally.orphan_removes == 1


def test_two_copies_of_one_enemy_are_two_intervals() -> None:
    intervals, _ = pair_debuffs(
        a_log(
            an_event(True, 1000, instance=1),
            an_event(True, 1500, instance=2),
            an_event(False, 3000, instance=2),
            an_event(False, 4000, instance=1),
        )
    )

    assert sorted((one.target_instance, one.start_ms, one.end_ms) for one in intervals) == [
        (1, 1000, 4000),
        (2, 1500, 3000),
    ]


def test_two_summons_of_one_pet_do_not_close_each_other() -> None:
    intervals, tally = pair_debuffs(
        a_log(
            an_event(True, 1000, source=PET, source_instance=2),
            an_event(False, 2000, source=PET, source_instance=3),
        )
    )

    assert (tally.orphan_removes, tally.closed_at_end) == (1, 1)
    assert spans(intervals) == [(1000, FIGHT_END)]


def test_a_target_with_no_game_id_is_counted_and_skipped() -> None:
    intervals, tally = pair_debuffs(
        a_log(an_event(True, 1000, target=999), an_event(False, 2000, target=999))
    )

    assert intervals == ()
    assert tally.unresolved_targets == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_debuffs.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'wowperf.domain.debuffs'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/debuffs.py`:

```python
# ABOUTME: Enemy-debuff applications and removals as pure values, paired into intervals.
# ABOUTME: A pet's application belongs to its owner, and a target is keyed by game id, not actor id.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor


class DebuffEvent(Frozen):
    """One `applydebuff` or `removedebuff` row of the enemy-debuff stream.

    Refreshes and stack changes are dropped at ingest: neither changes whether
    the debuff is on. An absent instance is the stream's first copy, read as 0.
    """

    applied: bool
    timestamp_ms: int
    source_id: int
    source_instance: int = 0
    target_id: int
    target_instance: int = 0
    ability_id: int


class DebuffLog(Frozen):
    """One run's enemy-debuff stream, with what reading it per player needs.

    The stream covers the whole group, so one log serves every player in it.
    Pairs rather than dicts, so the log is immutable and hashable like a `Run`.
    `end_ms` is the fight's own end, where an interval still open is closed.
    """

    events: tuple[DebuffEvent, ...] = ()
    pet_owners: tuple[tuple[int, int], ...] = ()
    """(pet actor id, owning actor id), for every actor carrying `petOwner`."""
    game_ids: tuple[tuple[int, int], ...] = ()
    """(actor id, game id), for every actor in the report."""
    npc_actors: tuple[NpcActor, ...] = ()
    ability_names: tuple[tuple[int, str], ...] = ()
    end_ms: int


class DebuffInterval(Frozen):
    """One unbroken stretch an owner's debuff sat on one copy of one kind of enemy."""

    owner_id: int
    ability_id: int
    target_game_id: int
    target_instance: int
    start_ms: int
    end_ms: int


class PairingTally(Frozen):
    """What the pairing met that a clean log would not hold. Recorded, never judged.

    These counts are the evidence a live run reads back: how often the log's
    own applications and removals failed to meet, and how often a target could
    not be named at all.
    """

    orphan_removes: int = 0
    closed_at_end: int = 0
    unresolved_targets: int = 0


Key = tuple[int, int, int, int, int]
"""(source id, source instance, ability id, target game id, target instance)."""


def pair_debuffs(log: DebuffLog) -> tuple[tuple[DebuffInterval, ...], PairingTally]:
    """Every interval the log's applications and removals describe, and what did not pair.

    The target is keyed on its game id and copy number rather than its actor id.
    Measured 2026-10-07 (`.claude/skills/wcl-api/SKILL.md`, "The debuff event
    stream does name the caster"): one enemy can be logged under two actor ids
    of the same game id, its application on one and its removal on the other.
    Keyed on the actor id, 13 of one player's 168 applications never closed.
    Keyed on the game id, the same ability balanced completely.

    The source stays raw in the key, instance and all, so two summons of one
    pet never close each other's debuff. It is folded to its owner only when
    the interval is written.

    A second application while one is open keeps the first start: the debuff
    never came off. A removal with nothing open is counted and dropped rather
    than guessed at. An interval still open when the stream ends is closed at
    the fight's end.
    """
    owners = dict(log.pet_owners)
    game_ids = dict(log.game_ids)
    opened: dict[Key, int] = {}
    intervals: list[DebuffInterval] = []
    orphan_removes = 0
    unresolved = 0

    def written(key: Key, start_ms: int, end_ms: int) -> DebuffInterval:
        source_id, _, ability_id, game_id, instance = key
        return DebuffInterval(
            owner_id=owners.get(source_id, source_id),
            ability_id=ability_id,
            target_game_id=game_id,
            target_instance=instance,
            start_ms=start_ms,
            end_ms=end_ms,
        )

    # Stable, so rows sharing a millisecond keep the order the log wrote them in.
    for event in sorted(log.events, key=lambda one: one.timestamp_ms):
        game_id = game_ids.get(event.target_id)
        if game_id is None:
            unresolved += 1
            continue
        key = (
            event.source_id,
            event.source_instance,
            event.ability_id,
            game_id,
            event.target_instance,
        )
        if event.applied:
            opened.setdefault(key, event.timestamp_ms)
            continue
        start_ms = opened.pop(key, None)
        if start_ms is None:
            orphan_removes += 1
            continue
        intervals.append(written(key, start_ms, event.timestamp_ms))

    for key, start_ms in opened.items():
        intervals.append(written(key, start_ms, max(start_ms, log.end_ms)))

    return tuple(intervals), PairingTally(
        orphan_removes=orphan_removes,
        closed_at_end=len(opened),
        unresolved_targets=unresolved,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_debuffs.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Lint and type-check the new module**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check src/wowperf/domain/debuffs.py tests/domain/test_debuffs.py`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/debuffs.py tests/domain/test_debuffs.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Pair the enemy-debuff stream into intervals

The boss debuff figure needs to know when each debuff was on, and the log
only says when it was applied and removed. Pets fold to their owner, and
targets key on game id because one enemy can be logged under two actor ids.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: One player's debuffs on each boss

**Files:**
- Create: `src/wowperf/domain/comparison/boss_debuffs.py`
- Test: `tests/domain/comparison/test_boss_debuffs.py`

**Interfaces:**
- Consumes:
  - Task 1's `DebuffLog`, `PairingTally` and `pair_debuffs`.
  - `find_bosses(actors, enemy_ids, fight_name) -> tuple[NpcActor, ...]` from `pace_boss.py`.
  - `Aura`, `AuraBand` and `uptime_seconds_in` from `domain/auras.py`.
  - `Pull` (fields `encounter_id`, `name`, `start_ms`, `end_ms`, `enemies`, `is_boss`).
- Produces:
  - `Withheld(StrEnum)`: `COUNCIL = "council"`, `NO_BOSS = "no boss found"`, `NOT_REACHED = "no reference reached this boss"`, `TOO_FEW = "too few references"`.
  - `BossWindow(encounter_id: int, name: str, start_ms: int, end_ms: int, boss_game_id: int | None = None, withheld: Withheld | None = None)`, with property `seconds: float`.
  - `BossDebuffs(windows: tuple[BossWindow, ...] = (), auras: tuple[Aura, ...] = (), tally: PairingTally = PairingTally())`, with properties `measured: tuple[tuple[int, int], ...]` and `seconds: float`.
  - `boss_windows_of(pulls: Sequence[Pull], npc_actors: tuple[NpcActor, ...]) -> tuple[BossWindow, ...]`
  - `boss_debuffs(log: DebuffLog, pulls: Sequence[Pull], owner_id: int) -> BossDebuffs`
  - `encounter_share(debuffs: BossDebuffs, ability_id: int, encounter_id: int) -> float | Withheld | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_boss_debuffs.py`:

```python
# ABOUTME: One player's debuffs on each boss: the boss alone, clipped to its pull, pets included.
# ABOUTME: Pins councils and missing bosses withheld, a shorter boss name, and per-boss shares.

from wowperf.domain.auras import uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import (
    BossWindow,
    Withheld,
    boss_debuffs,
    boss_windows_of,
    encounter_share,
)
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.debuffs import DebuffEvent, DebuffLog
from wowperf.domain.model import EnemyNpc, Pull

BOSS_NAME = "The Test Colossus"
BOSS_ACTOR, BOSS_GAME = 50, 5000
ADD_ACTOR, ADD_GAME = 51, 5100
PLAYER, PET, OTHER = 7, 8, 9
DOT = 55078
GAME_IDS = {BOSS_ACTOR: BOSS_GAME, ADD_ACTOR: ADD_GAME}


def a_pull(
    index: int,
    start_ms: int,
    end_ms: int,
    *,
    encounter_id: int = 0,
    name: str = "Pack",
    enemies: tuple[int, ...] = (BOSS_ACTOR, ADD_ACTOR),
) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name=name,
        encounter_id=encounter_id,
        start_ms=start_ms,
        end_ms=end_ms,
        killed=True,
        x=0,
        y=0,
        enemies=tuple(
            EnemyNpc(actor_id=actor, game_id=GAME_IDS.get(actor, actor * 100))
            for actor in enemies
        ),
    )


TRASH_PULL = a_pull(0, 0, 8_000)
BOSS_PULL = a_pull(1, 10_000, 70_000, encounter_id=2001, name=BOSS_NAME)
ACTORS = (
    NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name=BOSS_NAME, sub_type="Boss"),
    NpcActor(actor_id=ADD_ACTOR, game_id=ADD_GAME, name="Fixture Add", sub_type="NPC"),
)


def an_event(
    applied: bool, at: int, *, source: int = PLAYER, target: int = BOSS_ACTOR
) -> DebuffEvent:
    return DebuffEvent(
        applied=applied, timestamp_ms=at, source_id=source, target_id=target, ability_id=DOT
    )


def a_log(*events: DebuffEvent, actors: tuple[NpcActor, ...] = ACTORS) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=tuple(GAME_IDS.items()),
        npc_actors=actors,
        ability_names=((DOT, "Blood Plague"),),
        end_ms=80_000,
    )


def test_a_single_boss_is_measured_over_its_own_pull_and_trash_is_not() -> None:
    assert boss_windows_of((TRASH_PULL, BOSS_PULL), ACTORS) == (
        BossWindow(
            encounter_id=2001,
            name=BOSS_NAME,
            start_ms=10_000,
            end_ms=70_000,
            boss_game_id=BOSS_GAME,
        ),
    )


def test_only_the_debuff_on_the_boss_counts() -> None:
    mine = boss_debuffs(
        a_log(
            an_event(True, 20_000),
            an_event(False, 50_000),
            an_event(True, 10_000, target=ADD_ACTOR),
            an_event(False, 70_000, target=ADD_ACTOR),
        ),
        (TRASH_PULL, BOSS_PULL),
        PLAYER,
    )

    [aura] = mine.auras
    assert (aura.ability_id, aura.name, aura.total_uptime_ms) == (DOT, "Blood Plague", 30_000)
    assert [(band.start_ms, band.end_ms) for band in aura.bands] == [(20_000, 50_000)]
    assert mine.seconds == 60.0


def test_an_interval_reaching_past_the_pull_is_clipped_to_it() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 5_000), an_event(False, 75_000)), (BOSS_PULL,), PLAYER
    )

    assert [(band.start_ms, band.end_ms) for band in mine.auras[0].bands] == [(10_000, 70_000)]


def test_a_pet_counts_for_its_owner_and_an_overlap_counts_once() -> None:
    mine = boss_debuffs(
        a_log(
            an_event(True, 20_000),
            an_event(False, 50_000),
            an_event(True, 40_000, source=PET),
            an_event(False, 60_000, source=PET),
        ),
        (BOSS_PULL,),
        PLAYER,
    )

    [aura] = mine.auras
    assert uptime_seconds_in(aura, mine.measured) == 40.0


def test_another_players_debuff_is_not_this_players() -> None:
    mine = boss_debuffs(
        a_log(an_event(True, 20_000, source=OTHER), an_event(False, 50_000, source=OTHER)),
        (BOSS_PULL,),
        PLAYER,
    )

    assert mine.auras == ()


def test_a_council_is_withheld_and_counts_no_seconds() -> None:
    council = (
        NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name="Blood of the Twins", sub_type="Boss"),
        NpcActor(actor_id=ADD_ACTOR, game_id=ADD_GAME, name="Breath of the Twins", sub_type="Boss"),
    )
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name="The Twin Council")

    mine = boss_debuffs(
        a_log(an_event(True, 20_000), an_event(False, 50_000), actors=council), (pull,), PLAYER
    )

    assert [window.withheld for window in mine.windows] == [Withheld.COUNCIL]
    assert (mine.seconds, mine.auras) == (0.0, ())


def test_a_boss_pull_with_no_boss_flagged_enemy_is_withheld() -> None:
    unflagged = tuple(actor.model_copy(update={"sub_type": "NPC"}) for actor in ACTORS)

    assert [window.withheld for window in boss_windows_of((BOSS_PULL,), unflagged)] == [
        Withheld.NO_BOSS
    ]


def test_a_boss_whose_name_only_begins_the_pulls_is_still_the_boss() -> None:
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name="Vashnik the Malignant")
    actors = (NpcActor(actor_id=BOSS_ACTOR, game_id=BOSS_GAME, name="Vashnik", sub_type="Boss"),)

    assert [window.boss_game_id for window in boss_windows_of((pull,), actors)] == [BOSS_GAME]


def test_the_pairing_tally_rides_along() -> None:
    mine = boss_debuffs(a_log(an_event(False, 30_000)), (BOSS_PULL,), PLAYER)

    assert mine.tally.orphan_removes == 1


def test_a_share_is_read_per_boss_and_a_withheld_boss_says_why() -> None:
    second = a_pull(2, 100_000, 200_000, encounter_id=2002, name="The Twin Council")
    council = (
        *ACTORS,
        NpcActor(actor_id=60, game_id=6000, name="Blood of the Twins", sub_type="Boss"),
        NpcActor(actor_id=61, game_id=6100, name="Breath of the Twins", sub_type="Boss"),
    )
    second = second.model_copy(
        update={"enemies": (EnemyNpc(actor_id=60, game_id=6000), EnemyNpc(actor_id=61, game_id=6100))}
    )
    mine = boss_debuffs(
        a_log(an_event(True, 10_000), an_event(False, 40_000), actors=council),
        (BOSS_PULL, second),
        PLAYER,
    )

    assert encounter_share(mine, DOT, 2001) == 0.5
    assert encounter_share(mine, DOT, 2002) is Withheld.COUNCIL
    assert encounter_share(mine, DOT, 9999) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_boss_debuffs.py -q`
Expected: collection error, `No module named 'wowperf.domain.comparison.boss_debuffs'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/comparison/boss_debuffs.py`:

```python
# ABOUTME: One player's debuffs on each boss, rebuilt from the group's paired debuff intervals.
# ABOUTME: A single boss is measured over its own pull; a council or a missing boss is withheld.

from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from wowperf.domain.auras import Aura, AuraBand, uptime_seconds_in
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor, find_bosses
from wowperf.domain.debuffs import DebuffLog, PairingTally, pair_debuffs
from wowperf.domain.model import Pull


class Withheld(StrEnum):
    """Why a boss, or one boss's cell, carries no figure.

    The first two are read off our own route: a council's bosses can die
    apart, which needs the alive-span inference this design defers, and a boss
    pull may hold no enemy `find_bosses` can name. The last two are about the
    sample beside a figure of ours.
    """

    COUNCIL = "council"
    NO_BOSS = "no boss found"
    NOT_REACHED = "no reference reached this boss"
    TOO_FEW = "too few references"


class BossWindow(Frozen):
    """One boss pull, and the boss it is measured on, or why it is not."""

    encounter_id: int
    name: str
    start_ms: int
    end_ms: int
    boss_game_id: int | None = None
    withheld: Withheld | None = None

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


class BossDebuffs(Frozen):
    """One player's debuffs on the bosses of one run, as auras with bands.

    The `Aura` shape is the buff family's own, so the same arithmetic reads
    both: `uptime_seconds_in` merges overlapping bands, which is what keeps a
    player's and their pet's copies of one debuff from counting twice.
    """

    windows: tuple[BossWindow, ...] = ()
    auras: tuple[Aura, ...] = ()
    tally: PairingTally = PairingTally()

    @property
    def measured(self) -> tuple[tuple[int, int], ...]:
        """The millisecond spans of the boss pulls a figure was drawn over."""
        return tuple(
            (window.start_ms, window.end_ms) for window in self.windows if window.withheld is None
        )

    @property
    def seconds(self) -> float:
        """The denominator: single-boss pull seconds, withheld pulls left out."""
        return sum(window.seconds for window in self.windows if window.withheld is None)


def boss_windows_of(
    pulls: Sequence[Pull], npc_actors: tuple[NpcActor, ...]
) -> tuple[BossWindow, ...]:
    """Every boss pull, with its one boss, or the reason it has none to measure.

    `find_bosses` reads the pull's own enemies, their boss flag and the pull's
    name. One boss is measured. Several are a council, withheld. None, which
    includes two named after the pull, is no boss found, withheld.
    """
    windows: list[BossWindow] = []
    for pull in pulls:
        if not pull.is_boss:
            continue
        bosses = find_bosses(
            npc_actors, frozenset(enemy.actor_id for enemy in pull.enemies), pull.name
        )
        boss_game_id = bosses[0].game_id if len(bosses) == 1 else None
        withheld = (
            None if len(bosses) == 1 else Withheld.COUNCIL if bosses else Withheld.NO_BOSS
        )
        windows.append(
            BossWindow(
                encounter_id=pull.encounter_id,
                name=pull.name,
                start_ms=pull.start_ms,
                end_ms=pull.end_ms,
                boss_game_id=boss_game_id,
                withheld=withheld,
            )
        )
    return tuple(windows)


def boss_debuffs(log: DebuffLog, pulls: Sequence[Pull], owner_id: int) -> BossDebuffs:
    """What this player, and their pets, kept on each measured boss of this run.

    The boss is matched by game id, for the same reason the pairing keys on it.
    Each interval is clipped to the pull it falls in.
    """
    windows = boss_windows_of(pulls, log.npc_actors)
    intervals, tally = pair_debuffs(log)
    names = dict(log.ability_names)
    bands: dict[int, list[AuraBand]] = defaultdict(list)
    for window in windows:
        if window.withheld is not None:
            continue
        for one in intervals:
            if one.owner_id != owner_id or one.target_game_id != window.boss_game_id:
                continue
            start_ms = max(one.start_ms, window.start_ms)
            end_ms = min(one.end_ms, window.end_ms)
            if end_ms > start_ms:
                bands[one.ability_id].append(AuraBand(start_ms=start_ms, end_ms=end_ms))

    measured = tuple(
        (window.start_ms, window.end_ms) for window in windows if window.withheld is None
    )
    auras: list[Aura] = []
    for ability_id in sorted(bands):
        aura = Aura(
            ability_id=ability_id,
            name=names.get(ability_id, f"Unknown ability {ability_id}"),
            total_uptime_ms=0,
            uses=len(bands[ability_id]),
            bands=tuple(sorted(bands[ability_id], key=lambda band: band.start_ms)),
        )
        total_ms = round(uptime_seconds_in(aura, measured) * 1000)
        auras.append(aura.model_copy(update={"total_uptime_ms": total_ms}))
    return BossDebuffs(windows=windows, auras=tuple(auras), tally=tally)


def encounter_share(
    debuffs: BossDebuffs, ability_id: int, encounter_id: int
) -> float | Withheld | None:
    """The share of one boss's measured pulls this debuff was on it.

    A boss fought more than once, after a wipe, is summed over its measured
    pulls. `Withheld` when every pull of it was withheld, giving the first
    reason. None when this run fought no such boss at all.
    """
    pulls = [window for window in debuffs.windows if window.encounter_id == encounter_id]
    measured = [window for window in pulls if window.withheld is None]
    if not measured:
        return pulls[0].withheld if pulls else None
    seconds = sum(window.seconds for window in measured)
    if seconds <= 0:
        return None
    aura = next((one for one in debuffs.auras if one.ability_id == ability_id), None)
    if aura is None:
        return 0.0
    spans = tuple((window.start_ms, window.end_ms) for window in measured)
    return uptime_seconds_in(aura, spans) / seconds
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_boss_debuffs.py tests/domain/test_debuffs.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and type-check**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check src/wowperf/domain tests/domain`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Expected: no errors. If ruff reports a line over the limit in the test's council fixture, wrap the call arguments onto separate lines rather than suppressing the rule.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/boss_debuffs.py tests/domain/comparison/test_boss_debuffs.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Read one player's debuffs on each boss of a key

A boss is one target, so the share of its pull it carried a debuff is a
clean figure. A council's bosses can die apart, which needs an inference
this slice defers, so those pulls are withheld with the reason rather than
measured over a span nobody can vouch for.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Debuff findings against the parse sample

**Files:**
- Create: `src/wowperf/domain/comparison/debuff_uptime.py`
- Modify: `src/wowperf/domain/comparison/sample.py` (`ParseMember` and `ParseSample`)
- Modify: `src/wowperf/domain/comparison/service.py` (`ComparisonSubject` and `_compare_player`)
- Modify: `tests/domain/comparison/test_sample.py:99-109` (the closed field set)
- Test: `tests/domain/comparison/test_debuff_uptime.py`

**Interfaces:**
- Consumes:
  - Task 2's `BossDebuffs`.
  - From `uptime.py`: `fractions_of`, `seconds_up_in`, `uptime_measures`, `MAX_AURAS_REPORTED`, `MIN_UPTIME_FRACTION` and `UPTIME_GAP_FRACTION`.
  - From `sample.py`: `MIN_SAMPLE_FOR_AGGREGATE` and `too_few`.
  - `count_phrase` and `observed_range` from `statistics.py`, and `DUNGEON` from `wording.py`.
- Produces:
  - `ParseMember.boss_debuffs: BossDebuffs | None = None`
  - `ParseSample.debuff_eligible -> tuple[ParseMember, ...]`
  - `ComparisonSubject.our_boss_debuffs: BossDebuffs | None = None`
  - `debuff_fractions(debuffs: BossDebuffs) -> dict[int, tuple[str, float]]`
  - `per_member_fractions(members: Sequence[ParseMember]) -> tuple[dict[int, str], list[dict[int, float]]]`
  - `compare_boss_debuffs_sample(our: BossDebuffs | None, our_name: str, sample: ParseSample) -> list[Finding]`
  - Finding ids: `compare.uptime.boss.{rank}`, `compare.uptime.boss.unjudged` and `compare.uptime.boss.unavailable`. `service._for_player` then appends `.{slug}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_debuff_uptime.py`:

```python
# ABOUTME: Boss debuff uptime against the parse sample: the buff family's thresholds, debuff words.
# ABOUTME: Pins the gap, level, unjudged, the pairwise fallback and every unavailable branch.

from tests.domain.comparison.test_uptime import BOSS, a_player, a_run
from wowperf.domain.auras import Aura, AuraBand
from wowperf.domain.comparison.boss_debuffs import BossDebuffs, BossWindow, Withheld
from wowperf.domain.comparison.debuff_uptime import compare_boss_debuffs_sample
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun

OUR_NAME = "Stonewake (actor 7)"
DOT, DOT_NAME = 55078, "Blood Plague"
REFERENCE_NAMES = ("Bríala", "Кириллица", "Emberkin")


def on_the_boss(*shares: tuple[int, str, float], seconds: float = 100.0) -> BossDebuffs:
    """One measured boss pull of `seconds`, each debuff on it for its share from the pull."""
    end_ms = int(seconds * 1000)
    window = BossWindow(
        encounter_id=2001, name="The Test Colossus", start_ms=0, end_ms=end_ms, boss_game_id=5000
    )
    auras = tuple(
        Aura(
            ability_id=ability_id,
            name=name,
            total_uptime_ms=int(end_ms * share),
            uses=1,
            bands=(AuraBand(start_ms=0, end_ms=int(end_ms * share)),),
        )
        for ability_id, name, share in shares
        if share > 0
    )
    return BossDebuffs(windows=(window,), auras=auras)


def a_member(name: str, debuffs: BossDebuffs | None) -> ParseMember:
    return ParseMember(
        character_name=name, report_code="ref", fight_id=1, boss_seconds=100.0, boss_debuffs=debuffs
    )


def a_sample(*shares: float) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, on_the_boss((DOT, DOT_NAME, share)))
            for name, share in zip(REFERENCE_NAMES, shares, strict=False)
        )
    )


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_debuff_kept_up_well_below_the_sample_is_a_gap() -> None:
    findings = by_id(
        compare_boss_debuffs_sample(on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9, 0.9))
    )

    gap = findings["compare.uptime.boss.0"]
    assert gap.confidence is Confidence.DERIVED
    assert gap.title == (
        "Blood Plague was on the boss a median 90% of boss time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "range 90% to 90% across 3 top parses" in gap.evidence
    assert "0 of 3 references had no debuff data" in gap.evidence
    assert (gap.ability_id, gap.ability_name) == (DOT, DOT_NAME)


def test_a_narrow_difference_is_level_and_reports_nothing() -> None:
    findings = compare_boss_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
    )

    assert findings == []


def test_a_debuff_the_sample_kept_and_we_never_applied_is_named_not_judged() -> None:
    findings = by_id(compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9, 0.9)))

    assert set(findings) == {"compare.uptime.boss.unjudged"}
    assert findings["compare.uptime.boss.unjudged"].evidence[0] == DOT_NAME


def test_below_the_floor_one_reference_is_stated_pairwise() -> None:
    findings = by_id(
        compare_boss_debuffs_sample(on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9))
    )

    gap = findings["compare.uptime.boss.0"]
    assert gap.title == (
        "Blood Plague was on the boss for 90% of Bríala's boss time, 50% of Stonewake (actor 7)'s"
    )
    assert gap.evidence[-1].startswith("a single reference, not an aggregate")


def test_an_empty_sample_says_nothing_here() -> None:
    assert compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, ParseSample()) == []


def test_no_reference_with_debuff_data_is_unavailable() -> None:
    sample = ParseSample(members=(a_member("Bríala", None), a_member("Кириллица", None)))

    [finding] = compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, sample)

    assert finding.id == "compare.uptime.boss.unavailable"
    assert finding.confidence is Confidence.MEASURED
    assert "0 of 2 references returned debuff data" in finding.evidence


def test_our_own_missing_stream_is_unavailable() -> None:
    [finding] = compare_boss_debuffs_sample(None, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.boss.unavailable"
    assert "our debuff data absent" in finding.evidence


def test_a_run_whose_every_boss_was_withheld_is_unavailable() -> None:
    council = BossDebuffs(
        windows=(
            BossWindow(
                encounter_id=2001, name="The Twin Council", start_ms=0, end_ms=60_000,
                withheld=Withheld.COUNCIL,
            ),
        )
    )

    [finding] = compare_boss_debuffs_sample(council, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.boss.unavailable"
    assert "our measured boss time 0s" in finding.evidence


def test_at_most_five_gaps_are_reported() -> None:
    six = tuple((DOT + offset, f"Debuff {offset}", 0.9) for offset in range(6))
    ours = tuple((ability_id, name, 0.3) for ability_id, name, _ in six)
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*six)) for name in REFERENCE_NAMES)
    )

    findings = compare_boss_debuffs_sample(on_the_boss(*ours), OUR_NAME, sample)

    assert sorted(finding.id for finding in findings) == [
        f"compare.uptime.boss.{rank}" for rank in range(5)
    ]


def test_the_service_files_the_gap_under_the_players_own_slug() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample(0.9, 0.9, 0.9),
        our_boss_debuffs=on_the_boss((DOT, DOT_NAME, 0.5)),
    )

    ids = [finding.id for finding in compare(LoadedRun(run=a_run(BOSS)), None, [subject])]

    assert "compare.uptime.boss.0.stonewake-0" in ids
```

In `tests/domain/comparison/test_sample.py`, add `"boss_debuffs",` to the closed field set asserted at lines 99-109, after `"pulls",`. Then add one sentence to that test's docstring: `boss_debuffs` is here because the boss debuff comparison reads a reference's own debuffs on its own bosses, and nothing else of its event streams.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_debuff_uptime.py tests/domain/comparison/test_sample.py -q`
Expected:
- `test_debuff_uptime.py` fails to collect, on the missing module.
- The field-set test fails, because `boss_debuffs` is not a field yet.

- [ ] **Step 3: Add the sample and subject fields**

In `src/wowperf/domain/comparison/sample.py`:
- Add `from wowperf.domain.comparison.boss_debuffs import BossDebuffs` to the imports.
- Add the field to `ParseMember`, after `pulls`:

```python
    # This reference's own debuffs on its own bosses, rebuilt from its enemy-
    # debuff stream. None when the stream could not be had, which
    # `compare.uptime.boss.unavailable` states rather than reading as "applied
    # nothing".
    boss_debuffs: BossDebuffs | None = None
```

Add this property to `ParseSample`, after `aura_eligible`:

```python
    @property
    def debuff_eligible(self) -> tuple[ParseMember, ...]:
        return tuple(member for member in self.members if member.boss_debuffs is not None)
```

In `src/wowperf/domain/comparison/service.py`:
- Add `from wowperf.domain.comparison.boss_debuffs import BossDebuffs` and `from wowperf.domain.comparison.debuff_uptime import compare_boss_debuffs_sample`.
- Add the field to `ComparisonSubject`, after `our_auras`:

```python
    # Our player's own debuffs on our bosses. One stream serves the whole group,
    # so `cli.py` fetches it once and builds this per subject from it.
    our_boss_debuffs: BossDebuffs | None = None
```

In `_compare_player`, directly after the `*compare_uptime_sample(...)` entry, add:

```python
        *compare_boss_debuffs_sample(subject.our_boss_debuffs, subject.display_name, parse),
```

- [ ] **Step 4: Write the comparison module**

Create `src/wowperf/domain/comparison/debuff_uptime.py`:

```python
# ABOUTME: Compares one player's debuff uptime on bosses against their specialisation's parses.
# ABOUTME: Shares of measured boss time, judged by the buff family's own thresholds and median.

from collections.abc import Sequence

from wowperf.domain.comparison.boss_debuffs import BossDebuffs
from wowperf.domain.comparison.measures import Verdict
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.statistics import count_phrase, observed_range
from wowperf.domain.comparison.uptime import (
    MAX_AURAS_REPORTED,
    MIN_UPTIME_FRACTION,
    UPTIME_GAP_FRACTION,
    fractions_of,
    seconds_up_in,
    uptime_measures,
)
from wowperf.domain.comparison.wording import DUNGEON
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity

ID_PREFIX = "compare.uptime.boss"

STRETCH = "boss time"

GAP_DETAIL = (
    "Both figures are the share of single-boss pull time the boss carried this debuff from "
    "the player or their pets, which is comparable even though the fights ran for different "
    "lengths. A pull whose bosses are a council is left out on both sides. "
    f"{DUNGEON.uptime_hedge} The intervals are rebuilt from the log's own applications and "
    "removals rather than read from a table."
)


def debuff_fractions(debuffs: BossDebuffs) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of measured boss seconds the boss carried it)."""
    seconds = debuffs.seconds
    if seconds <= 0:
        return {}
    return fractions_of(debuffs.auras, seconds_up_in(debuffs.measured), seconds)


def per_member_fractions(
    members: Sequence[ParseMember],
) -> tuple[dict[int, str], list[dict[int, float]]]:
    """Each member's shares above zero, and every name seen, for `uptime_measures`.

    A share of zero reads the same as never having applied the debuff at all,
    the reading the buff family gives a band that never meets a boss pull.
    """
    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in members:
        assert member.boss_debuffs is not None  # debuff_eligible guarantees it
        carried: dict[int, float] = {}
        for ability_id, (name, share) in debuff_fractions(member.boss_debuffs).items():
            if share <= 0.0:
                continue
            names.setdefault(ability_id, name)
            carried[ability_id] = share
        per_member.append(carried)
    return names, per_member


def _unavailable(our_name: str, detail: str, evidence: tuple[str, ...]) -> Finding:
    return Finding(
        id=f"{ID_PREFIX}.unavailable",
        title=f"Boss debuff uptime could not be compared for {our_name}",
        detail=(
            "A boss debuff comparison needs the enemy-debuff stream, and at least one pull "
            f"with a single boss, on our side and on a reference's. {detail} No figures are "
            "reported rather than figures from one side."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=evidence,
    )


def compare_boss_debuffs_sample(
    our: BossDebuffs | None, our_name: str, sample: ParseSample
) -> list[Finding]:
    """Where the sample's bosses carried a debuff over markedly more of their time than ours did.

    The order of the checks follows `uptime.compare_uptime_sample`. An empty
    sample says nothing here: `compare.parse.unavailable` already says it once.
    """
    if not sample.members:
        return []

    eligible = sample.debuff_eligible
    if not eligible:
        return [
            _unavailable(
                our_name,
                "No reference in the sample returned any debuff data.",
                (f"{count_phrase(0, len(sample.members))} references returned debuff data",),
            )
        ]

    if our is None or our.seconds <= 0:
        return [
            _unavailable(
                our_name,
                "Our own side has no figure: its stream could not be read, or none of its "
                "boss pulls held a single boss.",
                (
                    f"our debuff data {'absent' if our is None else 'present'}",
                    f"our measured boss time {0.0 if our is None else our.seconds:.0f}s",
                ),
            )
        ]

    our_fractions = debuff_fractions(our)
    if not sample.can_aggregate(eligible):
        return too_few(_pairwise(our_fractions, our.seconds, our_name, eligible[0]), len(eligible))

    names, per_member = per_member_fractions(eligible)
    measures = uptime_measures(our_fractions, per_member, names)
    total = len(sample.members)
    missing = total - len(eligible)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )

    findings: list[Finding] = []
    for rank, m in enumerate(gaps[:MAX_AURAS_REPORTED]):
        low, high = observed_range(m.their_fractions)
        findings.append(
            Finding(
                id=f"{ID_PREFIX}.{rank}",
                title=(
                    f"{m.name} was on the boss a median {m.their_median:.0%} of {STRETCH} "
                    f"across {len(m.their_fractions)} top parses; {m.ours:.0%} for {our_name}"
                ),
                detail=GAP_DETAIL,
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our.seconds:.0f}s of measured boss pulls",
                    f"range {low:.0%} to {high:.0%} across {len(m.their_fractions)} top parses",
                    f"{count_phrase(missing, total)} references had no debuff data",
                ),
                facts=(
                    FindingFact(label="Ours", value=f"{m.ours:.0%} of {STRETCH}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference median",
                                value=f"{m.their_median:.0%} of {STRETCH}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Observed range", value=f"{low:.0%} to {high:.0%}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Sample", value=f"{len(m.their_fractions)} top parses"),
                ),
                ability_id=m.ability_id,
                ability_name=m.name,
            )
        )

    unjudged = sorted({m.name for m in measures if m.verdict is Verdict.UNJUDGED})
    if unjudged:
        findings.append(_unjudged(our_name, unjudged))
    return findings


def _pairwise(
    our_fractions: dict[int, tuple[str, float]],
    our_seconds: float,
    our_name: str,
    theirs: ParseMember,
) -> list[Finding]:
    """One reference, named, by the buff family's pairwise rule.

    A zero on our side is passed over here as it is on the buff side: below the
    floor there is no sample to say the debuff is one this build applies.
    """
    assert theirs.boss_debuffs is not None  # chosen from debuff_eligible
    their_seconds = theirs.boss_debuffs.seconds
    gaps = []
    for ability_id, (name, their_share) in debuff_fractions(theirs.boss_debuffs).items():
        if their_share < MIN_UPTIME_FRACTION:
            continue
        our_share = our_fractions.get(ability_id, (name, 0.0))[1]
        if our_share <= 0.0 or their_share - our_share < UPTIME_GAP_FRACTION:
            continue
        gaps.append((their_share - our_share, ability_id, name, our_share, their_share))
    gaps.sort(reverse=True)

    return [
        Finding(
            id=f"{ID_PREFIX}.{rank}",
            title=(
                f"{name} was on the boss for {their_share:.0%} of {theirs.character_name}'s "
                f"{STRETCH}, {our_share:.0%} of {our_name}'s"
            ),
            detail=GAP_DETAIL,
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"ability {ability_id}",
                f"ours over {our_seconds:.0f}s of measured boss pulls",
                f"theirs over {their_seconds:.0f}s of measured boss pulls",
            ),
            facts=(
                FindingFact(label="Ours", value=f"{our_share:.0%} of {STRETCH}",
                            confidence=Confidence.DERIVED),
                FindingFact(label="Reference", value=f"{their_share:.0%} of {STRETCH}",
                            confidence=Confidence.DERIVED),
                FindingFact(label="Sample", value=f"1 reference {DUNGEON.reference_noun}"),
            ),
            ability_id=ability_id,
            ability_name=name,
        )
        for rank, (_, ability_id, name, our_share, their_share) in enumerate(
            gaps[:MAX_AURAS_REPORTED]
        )
    ]


def _unjudged(our_name: str, names: Sequence[str]) -> Finding:
    """Debuffs the sample kept on its bosses that ours never carried.

    A debuff names who applied it, so unlike a buff's zero this one is the
    player's own. What the log cannot say is whether their build has the
    ability at all, which is why it is named rather than judged.
    """
    count = len(names)
    return Finding(
        id=f"{ID_PREFIX}.unjudged",
        title=(
            f"{quantity(count, 'debuff', 'debuffs')} the sample kept on bosses "
            f"{'is' if count == 1 else 'are'} absent for {our_name}"
        ),
        detail=(
            "Each of these was on the boss over enough of the sample's boss time to compare, "
            "and never on ours. A debuff names who applied it, so this zero is the player's "
            "own; what the log cannot say is whether their build has the ability at all. Check "
            "the talents before reading it as a missed button."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(names),
            f"applied by at least {MIN_SAMPLE_FOR_AGGREGATE} top parses each",
            "absent from our own measured boss pulls",
        ),
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison -q`
Expected: all pass, including the updated field-set test and every existing comparison test.

- [ ] **Step 6: Lint and type-check**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check src tests`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Expected: no errors. If ruff flags a long line in the test file, wrap the call rather than suppressing.

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/debuff_uptime.py src/wowperf/domain/comparison/sample.py src/wowperf/domain/comparison/service.py tests/domain/comparison/test_debuff_uptime.py tests/domain/comparison/test_sample.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Compare debuff uptime on bosses against the parse sample

The figure reuses the buff family's thresholds and median rule unchanged,
so a debuff gap means exactly what a buff gap means. Only the words differ:
a debuff names who applied it, so a zero is the player's own and is named
as such rather than blamed on a teammate.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: The table's measures, per debuff and per boss

**Files:**
- Modify: `src/wowperf/domain/comparison/measures.py` (three models, and `PlayerMeasures.boss_debuffs`)
- Modify: `src/wowperf/domain/comparison/debuff_uptime.py` (add `boss_debuff_table`)
- Modify: `src/wowperf/domain/comparison/tables.py` (`comparison_measures` and `_for_one`)
- Test: `tests/domain/comparison/test_debuff_uptime.py` (append)

**Interfaces:**
- Consumes: `encounter_share` and `Withheld` from Task 2, and `per_member_fractions` and `debuff_fractions` from Task 3. Also `median` from `statistics.py` and `PairingTally` from Task 1.
- Produces:
  - `BossCell(encounter_id: int, boss: str, ours: float | None = None, their_median: float | None = None, withheld: Withheld | None = None)`
  - `BossDebuffRow(uptime: AuraUptime, cells: tuple[BossCell, ...] = ())`
  - `BossDebuffTable(rows: tuple[BossDebuffRow, ...] = (), seconds: float = 0.0, bosses: tuple[str, ...] = (), tally: PairingTally = PairingTally())`
  - `PlayerMeasures.boss_debuffs: BossDebuffTable = BossDebuffTable()`
  - `boss_debuff_table(our: BossDebuffs | None, sample: ParseSample) -> BossDebuffTable`

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/comparison/test_debuff_uptime.py`. Merge the new names into the existing import lines at the top of the file, so ruff's import order stays clean. The `LoadedRun` import already exists.

```python
from wowperf.domain.comparison.debuff_uptime import boss_debuff_table
from wowperf.domain.comparison.measures import BossCell, Verdict
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.debuffs import PairingTally

FIRST = BossWindow(
    encounter_id=2001, name="First Boss", start_ms=0, end_ms=100_000, boss_game_id=5000
)
SECOND = BossWindow(
    encounter_id=2002, name="Second Boss", start_ms=200_000, end_ms=300_000, boss_game_id=6000
)
SECOND_COUNCIL = SECOND.model_copy(update={"boss_game_id": None, "withheld": Withheld.COUNCIL})


def on_two_bosses(
    first: float, second: float, *, windows: tuple[BossWindow, ...] = (FIRST, SECOND)
) -> BossDebuffs:
    bands = []
    if first > 0:
        bands.append(AuraBand(start_ms=0, end_ms=int(100_000 * first)))
    if second > 0:
        bands.append(AuraBand(start_ms=200_000, end_ms=200_000 + int(100_000 * second)))
    auras = (
        (Aura(ability_id=DOT, name=DOT_NAME, total_uptime_ms=0, uses=len(bands),
              bands=tuple(bands)),)
        if bands
        else ()
    )
    return BossDebuffs(windows=windows, auras=auras)


def a_two_boss_sample(*members: BossDebuffs) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, debuffs)
            for name, debuffs in zip(REFERENCE_NAMES, members, strict=True)
        )
    )


def test_a_row_carries_the_overall_verdict_and_one_cell_per_boss() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), sample)

    [row] = table.rows
    assert row.uptime.verdict is Verdict.BELOW
    assert row.cells == (
        BossCell(encounter_id=2001, boss="First Boss", ours=0.5, their_median=0.9),
        BossCell(encounter_id=2002, boss="Second Boss", ours=0.9, their_median=0.9),
    )
    assert (table.bosses, table.seconds) == (("First Boss", "Second Boss"), 200.0)


def test_our_council_cell_is_withheld_with_its_reason() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(
        on_two_bosses(0.5, 0.0, windows=(FIRST, SECOND_COUNCIL)), sample
    )

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", withheld=Withheld.COUNCIL
    )


def test_a_boss_no_reference_reached_shows_ours_and_says_so() -> None:
    sample = a_two_boss_sample(
        *(on_two_bosses(0.9, 0.0, windows=(FIRST,)) for _ in range(3))
    )

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.NOT_REACHED
    )


def test_a_boss_too_few_references_applied_it_on_shows_ours_and_says_so() -> None:
    sample = a_two_boss_sample(
        on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.0)
    )

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.TOO_FEW
    )


def test_no_table_below_the_floor_or_without_our_own_figure() -> None:
    two = ParseSample(
        members=(a_member("Bríala", on_two_bosses(0.9, 0.9)),
                 a_member("Кириллица", on_two_bosses(0.9, 0.9)))
    )
    three = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    assert boss_debuff_table(on_two_bosses(0.5, 0.9), two).rows == ()
    assert boss_debuff_table(None, three).rows == ()


def test_our_own_pairing_tally_rides_on_the_table() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = on_two_bosses(0.5, 0.9).model_copy(
        update={"tally": PairingTally(orphan_removes=2, closed_at_end=1)}
    )

    assert boss_debuff_table(ours, sample).tally == PairingTally(
        orphan_removes=2, closed_at_end=1
    )


def test_the_players_measures_carry_the_debuff_table() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3))),
        our_boss_debuffs=on_two_bosses(0.5, 0.9),
    )

    measures = comparison_measures(LoadedRun(run=a_run(BOSS)), [subject])

    assert [row.uptime.name for row in measures["stonewake-0"].boss_debuffs.rows] == [DOT_NAME]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_debuff_uptime.py -q`
Expected: an `ImportError` on `boss_debuff_table` or `BossCell`.

- [ ] **Step 3: Add the measures models**

In `src/wowperf/domain/comparison/measures.py`:
- Add the imports `from wowperf.domain.comparison.boss_debuffs import Withheld` and `from wowperf.domain.debuffs import PairingTally`.
- After `AuraUptime`, add:

```python
class BossCell(Frozen):
    """One boss's figure in one debuff's row: ours against the sample's, never a verdict.

    `ours` is None only when our own pull of this boss was withheld, and
    `their_median` is None whenever `withheld` names a reason, so a cell
    always says why it is missing a figure.
    """

    encounter_id: int
    boss: str
    ours: float | None = None
    their_median: float | None = None
    withheld: Withheld | None = None


class BossDebuffRow(Frozen):
    """One debuff: the judged figure across all boss pulls, and one cell per boss."""

    uptime: AuraUptime
    cells: tuple[BossCell, ...] = ()


class BossDebuffTable(Frozen):
    """Everything the debuff table states, with the denominator and the log's own tally."""

    rows: tuple[BossDebuffRow, ...] = ()
    seconds: float = 0.0
    bosses: tuple[str, ...] = ()
    tally: PairingTally = PairingTally()
```

Add this field to `PlayerMeasures`, after `stats`:

```python
    boss_debuffs: BossDebuffTable = BossDebuffTable()
```

- [ ] **Step 4: Add `boss_debuff_table`**

Append to `src/wowperf/domain/comparison/debuff_uptime.py`:
- Extend the imports with `encounter_share` and `Withheld` from `boss_debuffs`, `BossCell`, `BossDebuffRow` and `BossDebuffTable` from `measures`, and `median` from `statistics`.

```python
def boss_debuff_table(our: BossDebuffs | None, sample: ParseSample) -> BossDebuffTable:
    """The debuff table: each qualifying debuff, judged overall, with a cell per boss.

    Gated exactly as `tables._auras` gates the buff table: no table below the
    floor, where the comparison states one reference rather than a median.
    """
    eligible = sample.debuff_eligible
    if our is None or our.seconds <= 0 or not eligible or not sample.can_aggregate(eligible):
        return BossDebuffTable()

    names, per_member = per_member_fractions(eligible)
    measures = uptime_measures(debuff_fractions(our), per_member, names)
    bosses: dict[int, str] = {}
    for window in our.windows:
        bosses.setdefault(window.encounter_id, window.name)

    rows = tuple(
        BossDebuffRow(
            uptime=m,
            cells=tuple(
                _cell(our, eligible, m.ability_id, encounter_id, name)
                for encounter_id, name in bosses.items()
            ),
        )
        for m in measures
    )
    return BossDebuffTable(
        rows=rows, seconds=our.seconds, bosses=tuple(bosses.values()), tally=our.tally
    )


def _cell(
    our: BossDebuffs,
    members: Sequence[ParseMember],
    ability_id: int,
    encounter_id: int,
    name: str,
) -> BossCell:
    """One boss's cell. Descriptive only: the verdict is the row's, never a cell's.

    A member that never reached this boss, or whose pull of it was withheld,
    is not counted for it. Those that did and applied the debuff there give the
    median, at the same floor the row's own median keeps.
    """
    ours = encounter_share(our, ability_id, encounter_id)
    if not isinstance(ours, float):
        return BossCell(
            encounter_id=encounter_id, boss=name, withheld=ours or Withheld.NO_BOSS
        )

    shares = []
    for member in members:
        assert member.boss_debuffs is not None  # debuff_eligible guarantees it
        shares.append(encounter_share(member.boss_debuffs, ability_id, encounter_id))
    reached = [share for share in shares if isinstance(share, float)]
    if not reached:
        return BossCell(
            encounter_id=encounter_id, boss=name, ours=ours, withheld=Withheld.NOT_REACHED
        )
    carried = [share for share in reached if share > 0.0]
    if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
        return BossCell(
            encounter_id=encounter_id, boss=name, ours=ours, withheld=Withheld.TOO_FEW
        )
    return BossCell(encounter_id=encounter_id, boss=name, ours=ours, their_median=median(carried))
```

- [ ] **Step 5: Wire it into `tables.py`**

In `src/wowperf/domain/comparison/tables.py`:
- Add `from wowperf.domain.comparison.boss_debuffs import BossDebuffs` and `from wowperf.domain.comparison.debuff_uptime import boss_debuff_table` to the imports.
- In `comparison_measures`, change the call to:

```python
        measures[subject.slug] = _for_one(
            ours, subject.player, subject.our_auras, subject.our_boss_debuffs, parse
        )
```

Change `_for_one` to take and use it:

```python
def _for_one(
    ours: LoadedRun,
    our_player: Player,
    our_auras: PlayerAuras | None,
    our_boss_debuffs: BossDebuffs | None,
    parse: ParseSample,
) -> PlayerMeasures:
```

Add `boss_debuffs=boss_debuff_table(our_boss_debuffs, parse),` to the `PlayerMeasures(...)` it returns, after `stats=...`. Then update the docstring's "three sets of measures" to "sets of measures".

- [ ] **Step 6: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain -q`
Expected: all pass.

- [ ] **Step 7: Lint and type-check**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check src tests`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Expected: no errors. `isinstance(ours, float)` narrows `float | Withheld | None`; if mypy still reports `ours or Withheld.NO_BOSS` as mistyped, assign it to a local of type `Withheld | None` first.

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/measures.py src/wowperf/domain/comparison/debuff_uptime.py src/wowperf/domain/comparison/tables.py tests/domain/comparison/test_debuff_uptime.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Measure each debuff per boss for the player card's table

One verdict per debuff keeps the card readable. A cell per boss still shows
where an overall gap sits, and states why when a boss has no figure.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: The "Debuff uptime on bosses" table on the page

**Files:**
- Modify: `src/wowperf/domain/report/model.py:579-616` (`ComparisonRow` and `ComparisonTable`)
- Modify: `src/wowperf/domain/report/players.py` (`_tables`, plus a new `_debuff_rows` and `_cell`)
- Modify: `src/wowperf/adapters/render/_players.html.j2:54-64`
- Test: `tests/domain/report/test_build_players.py` (append)
- Test: `tests/adapters/render/test_html_invariants.py` (append)

**Interfaces:**
- Consumes: Task 4's `BossDebuffTable`, `BossDebuffRow` and `BossCell`, and Task 2's `Withheld`.
- Produces:
  - `ComparisonRow.cells: tuple[str, ...] = ()`
  - `ComparisonTable.cell_headings: tuple[str, ...] = ()`
  - The table heading `"Debuff uptime on bosses"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/report/test_build_players.py`. Add the imports it needs, following the file's existing import block:
- `BossCell`, `BossDebuffRow` and `BossDebuffTable` from `wowperf.domain.comparison.measures`
- `Withheld` from `wowperf.domain.comparison.boss_debuffs`
- `PairingTally` from `wowperf.domain.debuffs`

```python
def test_the_debuff_table_follows_the_buff_table_with_a_column_per_boss() -> None:
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraUptime(ability_id=195181, name="Bone Shield", ours=0.62,
                           their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                           verdict=Verdict.BELOW),
            ),
            boss_seconds=648.0,
            boss_debuffs=BossDebuffTable(
                rows=(
                    BossDebuffRow(
                        uptime=AuraUptime(ability_id=55078, name="Blood Plague", ours=0.7,
                                          their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                                          verdict=Verdict.BELOW),
                        cells=(
                            BossCell(encounter_id=2001, boss="First Boss", ours=0.5,
                                     their_median=0.9),
                            BossCell(encounter_id=2002, boss="Second Boss",
                                     withheld=Withheld.COUNCIL),
                            BossCell(encounter_id=2003, boss="Third Boss", ours=0.8,
                                     withheld=Withheld.TOO_FEW),
                        ),
                    ),
                ),
                seconds=200.0,
                bosses=("First Boss", "Second Boss", "Third Boss"),
                tally=PairingTally(orphan_removes=1, closed_at_end=2),
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    assert [t.heading for t in card.comparison_tables] == [
        "Buff uptime on boss pulls",
        "Debuff uptime on bosses",
    ]
    table = card.comparison_tables[1]
    assert table.cell_headings == ("First Boss", "Second Boss", "Third Boss")
    [row] = table.rows
    assert (row.ours, row.theirs, row.spread, row.verdict_label) == (
        "70%", "90%", "85% to 95%", "Below"
    )
    assert row.cells == ("50% against 90%", "a council, not measured", "80%; too few references")
    assert table.caption == (
        "Share of 200s of single-boss pulls the boss carried each debuff from this player or "
        "their pets, against the median of the parses that applied each. Council pulls are "
        "left out. Each boss column reads ours against the median and carries no verdict. Our "
        "own log held 1 removal with no application, dropped; 2 applications still open at "
        "the fight's end, closed there; and 0 rows on an enemy with no game id, skipped. "
        "Derived."
    )
```

Append to `tests/adapters/render/test_html_invariants.py`. Import `ComparisonRow` and `ComparisonTable` from `wowperf.domain.report.model` if the file does not already:

```python
def test_a_boss_column_lands_under_its_own_heading() -> None:
    """The per-boss cells are extra columns. Each must sit under the boss it names,
    and a table without them must render exactly as before, which the test above
    already pins for every fixture table."""
    report = rich_report()
    table = ComparisonTable(
        heading="Debuff uptime on bosses",
        caption="Derived.",
        cell_headings=("The Test Colossus", "The Twin Council"),
        rows=(
            ComparisonRow(
                ability_id=55078, name="Blood Plague", ours="70%", theirs="90%",
                spread="85% to 95%", sample="3 top parses", verdict="below",
                verdict_label="Below", cells=("50% against 90%", "a council, not measured"),
            ),
        ),
    )
    first = report.players[0].model_copy(update={"comparison_tables": (table,)})
    report = report.model_copy(update={"players": (first, *report.players[1:])})

    [(headings, rows)] = [
        rendered for rendered in compared_tables(render(report))
        if "The Test Colossus" in rendered[0]
    ]

    assert headings[-2:] == ["The Test Colossus", "The Twin Council"]
    [(_, cells)] = rows
    assert [MARKUP.sub("", cell) for cell in cells[-2:]] == [
        "50% against 90%", "a council, not measured"
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py tests/adapters/render/test_html_invariants.py -q`
Expected: the two new tests fail, on an unknown keyword `cells` or `cell_headings`, or on the missing heading.

- [ ] **Step 3: Add the view-model fields**

In `src/wowperf/domain/report/model.py`, add the field to `ComparisonRow`, after `verdict_label`:

```python
    # One string per column `ComparisonTable.cell_headings` names, in its order.
    # Descriptive only: the row's verdict is the judgement, never a cell.
    cells: tuple[str, ...] = ()
```

Add the field to `ComparisonTable`, after `caption` and before `rows`:

```python
    # Extra column headings after Verdict, one per boss on the debuff table.
    # Empty for every other table, which then renders exactly as it always has.
    cell_headings: tuple[str, ...] = ()
```

- [ ] **Step 4: Build the table in `players.py`**

In `src/wowperf/domain/report/players.py`:
- Import `BossCell` and `BossDebuffRow` from `wowperf.domain.comparison.measures`, `Withheld` from `wowperf.domain.comparison.boss_debuffs`, and `quantity` from `wowperf.domain.findings` if it is not already imported.
- In `_tables`, insert this block between the `if measures.auras:` block and the `if measures.stats:` block:

```python
    debuffs = measures.boss_debuffs
    if debuffs.rows:
        tally = debuffs.tally
        built.append(
            ComparisonTable(
                heading="Debuff uptime on bosses",
                caption=(
                    f"Share of {debuffs.seconds:.0f}s of single-boss pulls the boss carried "
                    "each debuff from this player or their pets, against the median of the "
                    "parses that applied each. Council pulls are left out. Each boss column "
                    "reads ours against the median and carries no verdict. Our own log held "
                    f"{quantity(tally.orphan_removes, 'removal', 'removals')} with no "
                    "application, dropped; "
                    f"{quantity(tally.closed_at_end, 'application', 'applications')} still "
                    "open at the fight's end, closed there; and "
                    f"{quantity(tally.unresolved_targets, 'row', 'rows')} on an enemy with no "
                    "game id, skipped. Derived."
                ),
                cell_headings=debuffs.bosses,
                rows=_debuff_rows(debuffs.rows),
            )
        )
```

Add these after `_aura_rows`:

```python
WITHHELD_LABELS = {
    Withheld.COUNCIL: "a council, not measured",
    Withheld.NO_BOSS: "no boss found",
    Withheld.NOT_REACHED: "no reference reached it",
    Withheld.TOO_FEW: "too few references",
}
"""How a boss cell with no figure says why, in the reader's words."""


def _debuff_rows(rows: Sequence[BossDebuffRow]) -> tuple[ComparisonRow, ...]:
    """Debuff uptimes, our own highest first, for the reason `_aura_rows` gives."""
    ordered = sorted(rows, key=lambda row: row.uptime.ours, reverse=True)
    built = []
    for row in ordered:
        m = row.uptime
        low, high = observed_range(m.their_fractions)
        built.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                ours=f"{m.ours:.0%}",
                theirs=f"{m.their_median:.0%}",
                spread=f"{low:.0%} to {high:.0%}",
                sample=f"{len(m.their_fractions)} top parses",
                verdict=m.verdict.value,
                verdict_label=VERDICT_LABELS[m.verdict],
                cells=tuple(_cell(cell) for cell in row.cells),
            )
        )
    return tuple(built)


def _cell(cell: BossCell) -> str:
    """One boss's cell: ours against the median, or ours and why there is no median."""
    reason = WITHHELD_LABELS[cell.withheld] if cell.withheld is not None else ""
    if cell.ours is None:
        return reason
    if cell.their_median is None:
        return f"{cell.ours:.0%}; {reason}" if reason else f"{cell.ours:.0%}"
    return f"{cell.ours:.0%} against {cell.their_median:.0%}"
```

- [ ] **Step 5: Add the columns to the template**

In `src/wowperf/adapters/render/_players.html.j2`, the extra columns are written inline, on the lines that already exist, so a table without them renders byte for byte as before.

Replace the `<thead>` line with:

```
    <thead><tr><th scope="col">Ability</th><th scope="col" class="num">Ours</th><th scope="col" class="num">Median</th><th scope="col" class="num">Range</th><th scope="col">Sample</th><th scope="col">Verdict</th>{% for heading in table.cell_headings %}<th scope="col" class="num">{{ heading }}</th>{% endfor %}</tr></thead>
```

Replace `      <td>{{ row.verdict_label }}</td>` with:

```
      <td>{{ row.verdict_label }}</td>{% for cell in row.cells %}<td class="num">{{ cell }}</td>{% endfor %}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report tests/adapters/render -q`
Expected: all pass, the golden-file tests under `tests/adapters/render/golden` included. A golden failure means the template change altered other tables' bytes; fix the template, never the golden file.

- [ ] **Step 7: Lint and type-check**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check src tests`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/model.py src/wowperf/domain/report/players.py src/wowperf/adapters/render/_players.html.j2 tests/domain/report/test_build_players.py tests/adapters/render/test_html_invariants.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Show debuff uptime on bosses on the player card

The table sits under the buff table it mirrors. The per-boss columns are
optional on every comparison table, so the existing tables render byte for
byte as before.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Fetch and ingest the enemy-debuff stream

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py` (`ACTORS_QUERY`, and a new `ENEMY_DEBUFFS_QUERY`)
- Modify: `src/wowperf/adapters/wcl/ingest.py` (`build_debuff_log`)
- Modify: `src/wowperf/adapters/wcl/repository.py` (`_actors` and `debuff_log`)
- Modify: `.claude/skills/wcl-api/SKILL.md` (the `petOwner` row of the field table)
- Modify: `tests/adapters/wcl/test_repository.py`:
  - `recording_repository` fixture, about lines 144-155 and 205-249;
  - `test_actors_query_carries_no_type_filter`, about lines 759-768.
- Test: `tests/adapters/wcl/test_ingest_debuffs.py` (create)
- Test: `tests/adapters/wcl/test_repository.py` (append)

**Interfaces:**
- Consumes: Task 1's `DebuffEvent` and `DebuffLog`, and `NpcActor`. Also the existing `fetch_all_events`, `select_keystone_fight`, `_report`, `_ability_dictionary` and `_query`.
- Produces:
  - `ENEMY_DEBUFFS_QUERY`, with operation name `EnemyDebuffs`.
  - `ACTORS_QUERY` selecting `actors { id gameID name type subType petOwner }`.
  - `build_debuff_log(events: list[dict[str, Any]], actors: list[dict[str, Any]], ability_names: dict[int, str], end_ms: int) -> DebuffLog`
  - `WclRunRepository.debuff_log(report_code: str, fight_id: int) -> DebuffLog`

- [ ] **Step 1: Write the failing tests**

Create `tests/adapters/wcl/test_ingest_debuffs.py`:

```python
# ABOUTME: Turns the raw enemy-debuff stream and the report's actors into one DebuffLog.
# ABOUTME: Row shapes are the ones measured live on 2026-10-07; absent keys read as zero or empty.

from typing import Any

from wowperf.adapters.wcl.ingest import build_debuff_log
from wowperf.domain.comparison.pace_boss import NpcActor

ACTORS: list[dict[str, Any]] = [
    {"id": 171, "gameID": 0, "type": "Player", "subType": "DeathKnight", "name": "Stonewake"},
    {"id": 172, "gameID": 27893, "type": "Pet", "subType": "Pet", "name": "Rune Weapon",
     "petOwner": 171},
    {"id": 261, "gameID": 189893, "type": "NPC", "subType": "NPC", "name": "Fixture Whelp"},
    {"id": 279, "gameID": 999, "type": "NPC", "subType": "Boss", "name": "Fixture Boss"},
    {"id": 280, "gameID": 998, "type": "NPC"},
]

EVENTS: list[dict[str, Any]] = [
    {"timestamp": 1000, "type": "applydebuff", "sourceID": 171, "targetID": 261,
     "targetInstance": 1, "abilityGameID": 55078, "fight": 9, "sourceMarker": 6},
    {"timestamp": 1500, "type": "refreshdebuff", "sourceID": 171, "targetID": 261,
     "targetInstance": 1, "abilityGameID": 55078, "fight": 9},
    {"timestamp": 1600, "type": "applydebuffstack", "sourceID": 171, "targetID": 261,
     "targetInstance": 1, "abilityGameID": 55078, "fight": 9, "stack": 2},
    {"timestamp": 2000, "type": "removedebuff", "sourceID": 172, "sourceInstance": 122,
     "targetID": 279, "abilityGameID": 55078, "fight": 9},
]


def a_log() -> Any:
    return build_debuff_log(EVENTS, ACTORS, {55078: "Blood Plague"}, 9000)


def test_only_applications_and_removals_are_kept() -> None:
    assert [(event.applied, event.timestamp_ms) for event in a_log().events] == [
        (True, 1000),
        (False, 2000),
    ]


def test_an_absent_instance_reads_as_the_first_copy() -> None:
    applied, removed = a_log().events
    assert (applied.source_instance, applied.target_instance) == (0, 1)
    assert (removed.source_instance, removed.target_instance) == (122, 0)


def test_pets_resolve_to_their_owners_and_every_actor_to_its_game_id() -> None:
    log = a_log()
    assert log.pet_owners == ((172, 171),)
    assert (261, 189893) in log.game_ids
    assert (172, 27893) in log.game_ids


def test_only_npcs_are_offered_to_the_boss_finder_and_missing_names_read_empty() -> None:
    assert a_log().npc_actors == (
        NpcActor(actor_id=261, game_id=189893, name="Fixture Whelp", sub_type="NPC"),
        NpcActor(actor_id=279, game_id=999, name="Fixture Boss", sub_type="Boss"),
        NpcActor(actor_id=280, game_id=998, name="", sub_type=""),
    )


def test_names_and_the_fight_end_ride_along() -> None:
    log = a_log()
    assert (log.ability_names, log.end_ms) == (((55078, "Blood Plague"),), 9000)
```

In `tests/adapters/wcl/test_repository.py`, inside `recording_repository`:
- Replace the two `all_actors` rows with:

```python
                        {"id": 699, "gameID": 241874, "type": "NPC", "subType": "NPC",
                         "name": "Fixture Add"},
                        {"id": 702, "gameID": 244889, "type": "NPC", "subType": "Boss",
                         "name": "Boss"},
```

- Add this entry to `event_payloads`, after `"Resurrects"`:

```python
        "EnemyDebuffs": events_payload(
            [
                {"type": "applydebuff", "abilityGameID": 55078, "sourceID": 693,
                 "targetID": 702, "timestamp": 10000},
                {"type": "removedebuff", "abilityGameID": 55078, "sourceID": 693,
                 "targetID": 702, "timestamp": 15000},
            ]
        ),
```

Replace the body of `test_actors_query_carries_no_type_filter` with the following. Keep its docstring, and add one sentence to it: the selection now also carries `name`, `type`, `subType` and `petOwner`, for the boss finder and the pet folding.

```python
    assert 'actors(type:' not in ACTORS_QUERY
    assert 'actors { id gameID name type subType petOwner }' in ACTORS_QUERY
```

Append:

```python
def test_the_debuff_log_reads_the_stream_and_the_actors_of_one_fight(tmp_path: Path) -> None:
    calls: list[str] = []

    log = recording_repository(calls, tmp_path).debuff_log("abc123", 36)

    assert [(event.applied, event.timestamp_ms) for event in log.events] == [
        (True, 10000),
        (False, 15000),
    ]
    assert log.end_ms == 1920000
    assert [actor.actor_id for actor in log.npc_actors if actor.sub_type == "Boss"] == [702]
    assert {"EnemyDebuffs", "Actors", "Abilities"} <= set(calls)


def test_the_enemy_debuff_query_asks_for_debuffs_on_enemies() -> None:
    from wowperf.adapters.wcl.queries import ENEMY_DEBUFFS_QUERY

    assert "query EnemyDebuffs(" in ENEMY_DEBUFFS_QUERY
    assert "dataType: Debuffs" in ENEMY_DEBUFFS_QUERY
    assert "hostilityType: Enemies" in ENEMY_DEBUFFS_QUERY
    assert "nextPageTimestamp" in ENEMY_DEBUFFS_QUERY
```

Move the `ENEMY_DEBUFFS_QUERY` import up into the module's existing `from wowperf.adapters.wcl.queries import ACTORS_QUERY, FIGHTS_QUERY` line rather than leaving it inside the function. It is shown inline above only to keep the step readable.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl -q`
Expected: failures on `build_debuff_log`, `ENEMY_DEBUFFS_QUERY`, `debuff_log` and the actors-query assertion.

- [ ] **Step 3: Write the queries**

In `src/wowperf/adapters/wcl/queries.py`, change `ACTORS_QUERY`'s selection to `actors { id gameID name type subType petOwner }`, and put this comment above it:

```python
# Every actor in the report, untyped, so a pet or a mechanic modelled as a
# hostile pet resolves too. `name`, `type` and `subType` let `find_bosses` read
# a boss off a key's own pulls, and `petOwner` folds a pet's debuffs into its
# owner's (wcl-api skill, "The debuff event stream does name the caster",
# 2026-10-07). `translate: true` for the reason `NPC_ACTORS_QUERY` gives.
```

Add after `ENEMY_CASTS_QUERY`:

```python
# Every debuff the group put on enemies, each row naming its caster. The table
# endpoint cannot be scoped to one caster; this stream can (wcl-api skill, "The
# debuff event stream does name the caster", verified 2026-10-07). About one
# point per 10,000-row page.
ENEMY_DEBUFFS_QUERY = """
query EnemyDebuffs($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Debuffs
        hostilityType: Enemies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""
```

- [ ] **Step 4: Write the ingest**

In `src/wowperf/adapters/wcl/ingest.py`, import `DebuffEvent` and `DebuffLog` from `wowperf.domain.debuffs` and `NpcActor` from `wowperf.domain.comparison.pace_boss`, then add after `build_interrupts`:

```python
DEBUFF_TYPES = ("applydebuff", "removedebuff")
"""The two rows that change whether a debuff is on. Refreshes and stacks do not."""


def build_debuff_log(
    events: list[dict[str, Any]],
    actors: list[dict[str, Any]],
    ability_names: dict[int, str],
    end_ms: int,
) -> DebuffLog:
    """The enemy-debuff stream and the report's actors, as one log a player can be read off."""
    return DebuffLog(
        events=tuple(
            DebuffEvent(
                applied=event["type"] == "applydebuff",
                timestamp_ms=event["timestamp"],
                source_id=event["sourceID"],
                source_instance=event.get("sourceInstance") or 0,
                target_id=event["targetID"],
                target_instance=event.get("targetInstance") or 0,
                ability_id=event["abilityGameID"],
            )
            for event in events
            if event.get("type") in DEBUFF_TYPES
        ),
        pet_owners=tuple(
            (actor["id"], actor["petOwner"])
            for actor in actors
            if actor.get("petOwner") is not None
        ),
        game_ids=tuple(
            (actor["id"], actor["gameID"]) for actor in actors if actor.get("gameID") is not None
        ),
        npc_actors=tuple(
            NpcActor(
                actor_id=actor["id"],
                game_id=actor["gameID"],
                name=actor.get("name") or "",
                sub_type=actor.get("subType") or "",
            )
            for actor in actors
            if actor.get("type") == "NPC" and actor.get("gameID") is not None
        ),
        ability_names=tuple(sorted(ability_names.items())),
        end_ms=end_ms,
    )
```

- [ ] **Step 5: Write the repository method**

In `src/wowperf/adapters/wcl/repository.py`:
- Import `build_debuff_log` and `ENEMY_DEBUFFS_QUERY` into the existing import lists, alphabetically, and `DebuffLog` from `wowperf.domain.debuffs`.
- Extract the actors read out of `_actor_game_ids`:

```python
    def _actors(self, report_code: str, hits: list[bool] | None = None) -> list[dict[str, Any]]:
        """Every actor row of the report, untyped, as the actors query returns them."""
        payload = self._query(ACTORS_QUERY, {"code": report_code}, hits)
        report = payload["reportData"]["report"]
        master = report.get("masterData") or {}
        actors = master.get("actors")
        if actors is None:
            raise WclError(f"Report {report_code} returned no masterData.actors block")
        return cast(list[dict[str, Any]], actors)
```

Make `_actor_game_ids` read it. Its docstring stays as it is:

```python
        return {actor["id"]: actor["gameID"] for actor in self._actors(report_code, hits)}
```

Add after `auras`:

```python
    def debuff_log(self, report_code: str, fight_id: int) -> DebuffLog:
        """One keystone fight's enemy-debuff stream, with the actors that read it per player.

        Fetched on its own, like `auras`, rather than folded into `load`: only a
        compared run reads it, and one stream serves every player in the group,
        so the caller fetches it once per run. The fight's window and its end
        come from the report the cache already holds.
        """
        report = self._report(report_code)
        fight = select_keystone_fight(report["fights"], fight_id)
        ability_names, _ = self._ability_dictionary(report_code)
        events = fetch_all_events(
            lambda one_query, variables: self._query(one_query, variables),
            ENEMY_DEBUFFS_QUERY,
            {
                "code": report_code,
                "fightId": fight["id"],
                "startTime": float(fight["startTime"]),
                "endTime": float(fight["endTime"]),
            },
        )
        return build_debuff_log(
            events, self._actors(report_code), ability_names, int(fight["endTime"])
        )
```

- [ ] **Step 6: Flip the skill's `petOwner` row**

In `.claude/skills/wcl-api/SKILL.md`, change the field-table row:

```
| `petOwner` | `ReportActor` | 2026-09-12 | no |
```

to:

```
| `petOwner` | `ReportActor` | 2026-09-12 | yes |
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl tests/test_skills.py -q`
Expected: all pass. `test_skills.py` holds the flipped row against `queries.py`, which now names `petOwner`.

- [ ] **Step 8: Run the whole offline suite**

The actors query change touches every `load`, so run everything.

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`
Expected: all pass. A CLI test that counts `Actors` calls is Task 7's to update. If it fails here, leave it failing, note it, and fix it in Task 7. Do not change it in this task.

- [ ] **Step 9: Lint, type-check, commit**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check .`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/queries.py src/wowperf/adapters/wcl/ingest.py src/wowperf/adapters/wcl/repository.py .claude/skills/wcl-api/SKILL.md tests/adapters/wcl/test_ingest_debuffs.py tests/adapters/wcl/test_repository.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Fetch the enemy-debuff stream and the actors that read it

The actors query now carries petOwner and the boss flags, so one query
serves both the pet folding and the boss finder. Its text changed, so every
report already cached re-reads its actors once, at about a point each.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: Wire the debuffs into `analyze`

**Files:**
- Modify: `src/wowperf/cli.py`:
  - imports;
  - new `_debuff_log` and `_fetch_parse_boss_debuffs`, after `_fetch_parse_auras`;
  - `analyze`, about lines 1492-1533.
- Modify: `tests/test_cli.py`:
  - `build_analyze_transport`, about lines 1970-2215;
  - `run_analyze`, about lines 2244-2269;
  - `test_a_reference_does_not_pay_for_the_streams_no_comparison_reads`, about line 2640.
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes:
  - Task 6's `WclRunRepository.debuff_log`.
  - Task 2's `boss_debuffs` and `BossDebuffs`.
  - Task 3's `ComparisonSubject.our_boss_debuffs` and `ParseMember.boss_debuffs`.
  - The existing `find_player`.
- Produces:
  - `_debuff_log(runs: WclRunRepository, code: str, fight_id: int) -> DebuffLog | None`
  - `_fetch_parse_boss_debuffs(sample: ParseSample, references: WclRunRepository, our_log: Callable[[], DebuffLog | None], our_run: Run, subject: Player) -> tuple[ParseSample, BossDebuffs | None]`

- [ ] **Step 1: Write the failing tests and widen the fake**

In `tests/test_cli.py`, change `build_analyze_transport`:
- Add a keyword parameter `debuff_rows_by_code: dict[str, list[dict[str, Any]]] | None = None`.
- Document it in the docstring: `debuff_rows_by_code` answers `EnemyDebuffs` with the rows given for the report codes named, in place of the default empty stream.
- Change the default `actors_payload` row to carry the boss finder's fields:

```python
    actors_payload: dict[str, Any] = {
        "reportData": {
            "report": {
                "masterData": {
                    "actors": [
                        {"id": 699, "gameID": 241874, "type": "NPC", "subType": "Boss",
                         "name": "Trash"}
                    ]
                }
            }
        }
    }
```

Add this to `answer`, before the final `return`:

```python
        if name == "EnemyDebuffs" and debuff_rows_by_code is not None:
            rows = debuff_rows_by_code.get(body["variables"]["code"], [])
            return httpx.Response(
                200,
                json={
                    "data": {
                        "reportData": {
                            "report": {"events": {"data": rows, "nextPageTimestamp": None}}
                        }
                    }
                },
            )
```

Then add `debuff_rows_by_code` to `run_analyze`'s parameters, defaulting to `None`, and pass it through to `build_analyze_transport`.

The fixture's only pull is named "Trash" and holds actor 699. Under `boss_pull_reports` it becomes a boss pull, and actor 699, boss-flagged and named after it, is its one boss.

In `test_a_reference_does_not_pay_for_the_streams_no_comparison_reads`, replace `assert calls.count("Actors") == 1` with:

```python
    # Ours, and the parse reference's own: its boss debuffs need its pets and
    # its boss flags. Our own second read is a cache hit. The speed reference
    # reads no actors at all, which is what keeps this at two.
    assert calls.count("Actors") == 2
```

Append:

```python
def test_a_compared_run_reads_both_sides_debuffs_on_the_boss(tmp_path: Path) -> None:
    """One parse reference is below the floor, so the gap is stated pairwise.
    Ours kept the debuff on the boss for 1s of its 4s pull and theirs for all
    4s, a 25% against 100% gap that clears every threshold.
    """
    def on_the_boss(apply_ms: int, remove_ms: int) -> list[dict[str, Any]]:
        return [
            {"type": "applydebuff", "abilityGameID": 55078, "sourceID": 693,
             "targetID": 699, "timestamp": apply_ms},
            {"type": "removedebuff", "abilityGameID": 55078, "sourceID": 693,
             "targetID": 699, "timestamp": remove_ms},
        ]

    calls: list[str] = []
    result = run_analyze(
        tmp_path,
        calls=calls,
        boss_pull_reports=("abc123", PARSE_REFERENCE_CODE),
        debuff_rows_by_code={
            "abc123": on_the_boss(1000, 2000),
            PARSE_REFERENCE_CODE: on_the_boss(1000, 5000),
        },
    )

    assert result.exit_code == 0, result.output
    assert calls.count("EnemyDebuffs") == 2
    ids = [finding["id"] for finding in written_findings(tmp_path)["findings"]]
    assert "compare.uptime.boss.0.emberkin-0" in ids


def test_no_compare_reads_no_debuff_stream(tmp_path: Path) -> None:
    calls: list[str] = []

    result = run_analyze(tmp_path, "--no-compare", calls=calls)

    assert result.exit_code == 0, result.output
    assert "EnemyDebuffs" not in calls
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -q -k "debuff or does_not_pay"`
Expected:
- The compared-run test fails with `calls.count("EnemyDebuffs") == 0`.
- The `Actors` count test fails at 1.

- [ ] **Step 3: Write the CLI helpers**

In `src/wowperf/cli.py`:
- Add `import functools` to the stdlib imports.
- Add `from collections.abc import Callable` if it is not already imported.
- Add `from wowperf.domain.comparison.boss_debuffs import BossDebuffs, boss_debuffs` and `from wowperf.domain.debuffs import DebuffLog`.

Add after `_fetch_parse_auras`:

```python
def _debuff_log(runs: WclRunRepository, code: str, fight_id: int) -> DebuffLog | None:
    """One fight's enemy-debuff log, or None if it cannot be had.

    Swallowed and re-raised on the same terms as `_auras`: a failed stream must
    not discard a report already paid for, and `compare.uptime.boss.unavailable`
    states the gap. A spent budget alone is re-raised, because it is every
    later fetch's failure too.
    """
    try:
        return runs.debuff_log(code, fight_id)
    except RateLimitExceeded:
        raise
    except (IngestError, WclError, httpx.HTTPError):
        return None


def _fetch_parse_boss_debuffs(
    sample: ParseSample,
    references: WclRunRepository,
    our_log: Callable[[], DebuffLog | None],
    our_run: Run,
    subject: Player,
) -> tuple[ParseSample, BossDebuffs | None]:
    """Every parse member's own debuffs on its own bosses, and our subject's.

    The rule is `_fetch_parse_auras`'s. A member whose counterpart cannot be
    found in its own roster is left without debuff data, unfetched. Our own
    side is built only once some member's counterpart resolves. `our_log` is
    shared across every subject of one run, because the stream covers the
    whole group: the caller memoises it, so it is fetched once at most.
    """
    ours: BossDebuffs | None = None
    ours_built = False
    members: list[ParseMember] = []
    for member in sample.members:
        their_player = find_player(member.players, member.character_name)
        if their_player is None:
            members.append(member)
            continue
        if not ours_built:
            log = our_log()
            ours = None if log is None else boss_debuffs(log, our_run.pulls, subject.actor_id)
            ours_built = True
        their_log = _debuff_log(references, member.report_code, member.fight_id)
        members.append(
            member.model_copy(
                update={
                    "boss_debuffs": None
                    if their_log is None
                    else boss_debuffs(their_log, member.pulls, their_player.actor_id)
                }
            )
        )
    return sample.model_copy(update={"members": tuple(members)}), ours
```

- [ ] **Step 4: Wire it into `analyze`**

In `analyze`, inside `if not no_compare:`, directly before `for player_to_compare, slug, name in requested:`, add:

```python
            # One enemy-debuff stream covers the whole group, so every subject
            # reads the same one: memoised, it is fetched once at most, and only
            # once some member's counterpart resolves.
            our_debuff_log = functools.cache(
                lambda: _debuff_log(repository, loaded.run.report_code, loaded.run.fight_id)
            )
```

Inside the loop, directly after the `_fetch_parse_auras(...)` call, add:

```python
                sample, our_boss_debuffs = _fetch_parse_boss_debuffs(
                    sample, references, our_debuff_log, loaded.run, player_to_compare
                )
```

Then add `our_boss_debuffs=our_boss_debuffs,` to the `ComparisonSubject(...)` call, after `our_auras=our_auras,`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 6: Run the full gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check .`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`
Expected: everything passes, with no warnings in the output.

- [ ] **Step 7: Commit**

```bash
/mingw64/bin/git add src/wowperf/cli.py tests/test_cli.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Read boss debuff uptime in every compared analysis

Our side's stream is fetched once and shared by every subject, since it
covers the whole group. A parse reference reads its own stream and its own
actors only when its counterpart is found, as its auras already do.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Prove it live

This task carries the CLAUDE.md invariant: a new judgement is not done until a live run has shown how often each state it can reach occurred. It spends quota. Budget about 400 points of 3600 (design §6).

**Files:**
- Create: `tests/e2e/test_boss_debuffs_e2e.py`
- Modify: `.claude/skills/wcl-api/SKILL.md` (the cost reading, in the section "The debuff event stream does name the caster")
- Scratch, not committed: two scripts in the session scratchpad.

- [ ] **Step 1: Write the end-to-end test**

Create `tests/e2e/test_boss_debuffs_e2e.py`:

```python
# ABOUTME: End-to-end boss debuff uptime against the real Warcraft Logs API; no mocks.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
from pathlib import Path

import pytest

from wowperf.cli import build_repository
from wowperf.domain.auras import uptime_seconds_in
from wowperf.domain.comparison.boss_debuffs import boss_debuffs
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_keys_debuffs_on_its_bosses_stay_inside_the_boss_pulls(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    run = runs.get(code, fight)
    log = runs.debuff_log(run.report_code, run.fight_id)

    assert log.events, "a real key applies debuffs to enemies"
    assert all(event.timestamp_ms <= log.end_ms for event in log.events)

    boss_pulls = [pull for pull in run.pulls if pull.is_boss]
    landed = 0
    for player in run.players:
        mine = boss_debuffs(log, run.pulls, player.actor_id)
        assert len(mine.windows) == len(boss_pulls)
        for aura in mine.auras:
            # An uptime cannot exceed the stretch it was measured over.
            assert uptime_seconds_in(aura, mine.measured) <= mine.seconds + 1e-9, aura.name
            landed += 1
    assert landed, "no player's debuff landed on any measured boss of this key"
```

- [ ] **Step 2: Run it**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e tests/e2e/test_boss_debuffs_e2e.py -q`
Expected: pass. `WOWPERF_E2E_REPORT` must be set. If it is unset, the test fails with instructions; ask RwlRwlRwlRwl for a key rather than inventing one.

- [ ] **Step 3: Commit the end-to-end test**

```bash
/mingw64/bin/git add tests/e2e/test_boss_debuffs_e2e.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Check boss debuff uptime against a real key

The offline suite cannot tell whether the live stream's clock, the boss
finder on dungeon bosses, and the pairing all agree. A real key can.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 4: Run the two live analyses**

Use the repository's real cache, `cache/` at the main checkout, so the responses are kept. Write output under the main checkout's `out/debuffs/`.

The Bash tool's working directory is reset to the worktree, and the credentials live in the main checkout's `.env`, which is UTF-16. So each command loads them into its own environment first, which wins over any `.env` lookup (memory: "The .env is UTF-16"). Never echo, print or write the values.

```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; uv run wowperf analyze LyKXYvVZm192TDr6 --fight 9 --all-players --cache-dir ../../../cache --out ../../../out/debuffs
```
```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; uv run wowperf analyze nd6Rz47Gj1ZPxFfm --fight 3 --cache-dir ../../../cache --out ../../../out/debuffs
```

If the second refuses because the report owner is not in the roster, rerun it with `--player` naming the first player of the roster it printed. Never write that name into a file or a commit. Keep each command's printed cost breakdown; Step 7 records it.

- [ ] **Step 5: Measure the distribution of states**

Write `debuff_states.py` in the session scratchpad. Use the Write tool, not a heredoc: heredocs eat backslashes here.

```python
"""How often each boss-debuff state occurred in the findings files given."""
import json
import sys
from collections import Counter

stems: Counter[str] = Counter()
verdicts: Counter[str] = Counter()
cells: Counter[str] = Counter()
for path in sys.argv[1:]:
    payload = json.load(open(path, encoding="utf-8"))
    for finding in payload["findings"]:
        if not finding["id"].startswith("compare.uptime.boss."):
            continue
        stem = finding["id"].split(".")[3]
        stem = "gap" if stem.isdigit() else stem
        pairwise = any(e.startswith("a single reference") for e in finding["evidence"])
        stems[f"{stem}{' (pairwise)' if pairwise else ''}"] += 1
    for slug, table in payload["comparison_tables"].items():
        debuffs = table["boss_debuffs"]
        print(path.rsplit("/", 1)[-1], slug, "tally", debuffs["tally"], "seconds", debuffs["seconds"])
        for row in debuffs["rows"]:
            verdicts[row["uptime"]["verdict"]] += 1
            for cell in row["cells"]:
                cells[cell["withheld"] or "measured"] += 1
print("findings", dict(stems))
print("row verdicts", dict(verdicts))
print("cells", dict(cells))
```

Run it from the worktree with the scratchpad path to the script and both findings files. It reads only files, so it needs no credentials:

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run python <scratchpad>/debuff_states.py ../../../out/debuffs/LyKXYvVZm192TDr6-9.findings.json ../../../out/debuffs/nd6Rz47Gj1ZPxFfm-3.findings.json
```

- [ ] **Step 6: Check the boss finder on dungeon bosses**

Write `boss_windows.py` in the scratchpad. It reads only the warm cache, so it spends one `RateLimit` read at most:

```python
"""Each boss pull of the two keys: its name, and whether it was measured or why not."""
import sys
from pathlib import Path

from wowperf.cli import build_repository
from wowperf.domain.comparison.boss_debuffs import boss_windows_of

runs = build_repository(Path(sys.argv[1]))
for code, fight in (("LyKXYvVZm192TDr6", 9), ("nd6Rz47Gj1ZPxFfm", 3)):
    run = runs.get(code, fight)
    log = runs.debuff_log(code, fight)
    for window in boss_windows_of(run.pulls, log.npc_actors):
        print(code, window.name, window.withheld or f"measured on game id {window.boss_game_id}")
```

Run it from the worktree, with the credentials loaded as in Step 4:

```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; uv run python <scratchpad>/boss_windows.py ../../../cache
```

Expected: Temple of Sethraliss's first boss, Adderis and Aspix, reads `council`. Every other boss pull of both keys reads `measured`. Any `no boss found` on a single-boss pull is a `find_bosses` defect on dungeons. Stop and report it to RwlRwlRwlRwl before going on, because design §4 item 5 depends on it.

- [ ] **Step 7: Judge the distribution and record it**

These states must each have occurred at least once across both runs:
- row verdicts `below`, `level` and `unjudged`;
- the cell `measured`, and the cell `council`;
- the finding `gap`.

`unavailable`, the pairwise fallback, `no boss found`, `no reference reached this boss` and `too few references` may not occur on these two keys. **A state that never occurred is a defect to chase, not a quiet success.** For each one that did not occur:
- Find a real case cheaply, by pre-checking raw cached data before paying for a full run (memory: "Pre-check before a full run"). For example, scan cached parse samples for a member with no resolvable counterpart, or for a reference key whose route skipped a boss.
- If no real case can be found within about 100 more points, stop and report the unexercised states to RwlRwlRwlRwl with what was tried. Do not mark this task done.

Then add a dated paragraph to `.claude/skills/wcl-api/SKILL.md`, at the end of the section "The debuff event stream does name the caster". Record:
- each command's `EnemyDebuffs` and `Actors` calls and points, as the command printed them;
- each command's total;
- that the `Actors` re-read cost is the one-time cache-key change.

Use the same style as the cost readings above it: the date, the report and fight, and the composition as printed.

- [ ] **Step 8: Commit the measurement**

```bash
/mingw64/bin/git add .claude/skills/wcl-api/SKILL.md
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Record what boss debuff uptime cost on two live keys

The design priced it from a probe; this is the feature's own reading, and
the distribution of states that run reached.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 9: Make the documentation true again

**Files:**
- Modify: `CLAUDE.md` (the "Uptime covers buffs only" sentence)
- Modify: `docs/plans/2026-09-03-mplus-postmortem-design.md:582-594`
- Modify: `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` (the status line)
- Modify: `.claude/skills/wcl-api/SKILL.md` (the sentence "Nothing in `queries.py` reads this stream yet.")
- Modify: `.claude/skills/mplus-analysis/SKILL.md` (after the bullet that ends "...whose report its evidence links to.", about line 428)
- Modify the comments this feature makes false:
  - `src/wowperf/domain/comparison/uptime.py:4-8`
  - `src/wowperf/domain/auras.py:37-42`
  - `src/wowperf/domain/comparison/tables.py` (`_auras` docstring)
  - `src/wowperf/adapters/wcl/repository.py` (`auras` docstring)
  - `src/wowperf/adapters/wcl/queries.py` (the comment above `AURA_TABLE_QUERY`, if it says the enemy figure does not exist)

- [ ] **Step 1: Amend CLAUDE.md**

Replace the sentence that begins "Uptime covers buffs only: Warcraft Logs offers no way to scope the enemy-debuff table to one caster" with the following. That sentence runs through "...under "The debuff half cannot be scoped to one caster"."

```
Uptime covers buffs everywhere and debuffs on Mythic+ bosses. The enemy-debuff *table* cannot be
scoped to one caster (measured 2026-09-05), but the `Debuffs` event stream names each
application's caster (measured 2026-10-07), and the boss figure is rebuilt from it. Both are
recorded in `.claude/skills/wcl-api/SKILL.md`. Trash, raid and council pulls are not measured
yet; `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` §2 says why.
```

- [ ] **Step 2: Amend the master design §5 item 5**

In `docs/plans/2026-09-03-mplus-postmortem-design.md`, append this to item 5, after "Neither is decided.":

```
     *Amended 2026-10-07:* the per-source route exists. The `Debuffs` event stream names each
     application's caster, and `docs/plans/2026-10-07-enemy-debuff-uptime-design.md` revives
     the on-target half for single-boss pulls on that basis. Trash and raid remain open.
```

- [ ] **Step 3: Update the debuff design's status, and the skills**

- **Debuff design status.** Change the design's `**Status:**` line to: `approved design, 2026-10-07; planned in docs/plans/2026-10-07-enemy-debuff-uptime-plan.md, built, and exercised live on <date of Task 8>.`
- **wcl-api skill.** Replace "Nothing in `queries.py` reads this stream yet." with: "`ENEMY_DEBUFFS_QUERY` in `queries.py` reads it, for the boss figure of `docs/plans/2026-10-07-enemy-debuff-uptime-design.md`, and keys targets on game id as recommended here."
- **mplus-analysis skill.** Add this bullet after the parse-references bullet:

```
- **Debuff uptime on bosses is rebuilt, not read.** `compare.uptime.boss.<rank>.<slug>` is the
  share of single-boss pull time the boss carried a debuff from the player or their pets,
  against the median of the parses that applied it, by the buff family's thresholds. It is
  derived: the intervals come from the log's own applications and removals. A council pull is
  left out on both sides, and the card's per-boss columns describe, never judge. Unlike a buff,
  a debuff names who applied it, so `compare.uptime.boss.unjudged` is the player's own zero;
  what it cannot say is whether their build has the ability. `comparison_tables.<slug>
  .boss_debuffs.tally` counts what the pairing met in our own log, and is provenance, not a
  finding.
```

- [ ] **Step 4: Amend the comments this feature made false**

Each of the listed comments says, in some form, that the per-player figure for what a player kept up on enemies does not exist. Keep each one's first claim, about the table. Replace the "does not exist" claim with a pointer, in each comment's own voice, for example:

```
# Buffs only, from this table. What a player kept up on enemies cannot come from the
# aura table -- no argument narrows its debuff half to one caster -- and is rebuilt
# from the event stream instead, for bosses, in `comparison/boss_debuffs.py` (see
# `.claude/skills/wcl-api/SKILL.md`, "The debuff event stream does name the caster").
```

Do not delete a comment, and do not touch any comment that is still true.

- [ ] **Step 5: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run ruff check .`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run mypy`
Then: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`
Expected: all pass. `tests/test_skills.py` checks the edited skills.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add CLAUDE.md docs/plans/2026-09-03-mplus-postmortem-design.md docs/plans/2026-10-07-enemy-debuff-uptime-design.md .claude/skills/wcl-api/SKILL.md .claude/skills/mplus-analysis/SKILL.md src/wowperf/domain/comparison/uptime.py src/wowperf/domain/auras.py src/wowperf/domain/comparison/tables.py src/wowperf/adapters/wcl/repository.py src/wowperf/adapters/wcl/queries.py
```
```bash
/mingw64/bin/git commit -q -F - <<'EOF'
Say where the per-player enemy-debuff figure now comes from

Every place that said the figure does not exist was true of the table and
is now false of the project. Each keeps its claim about the table and
points at the event stream that replaced it, for bosses.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```
