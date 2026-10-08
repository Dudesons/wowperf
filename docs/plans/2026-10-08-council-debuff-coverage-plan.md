# Council Debuff Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure Mythic+ council boss pulls in the boss debuff figure. A council's figure is coverage across its bosses: debuff-seconds on each boss, over the seconds each boss was alive, summed.

**Architecture:**

- **Task 1** replaces the bands-and-merge internals of `comparison/boss_debuffs.py` with covered seconds counted per boss target. It is a pure refactor: every existing figure stays the same.
- **Task 2** gives a council pull one target per boss, each spanning from the pull's start to that boss's last death. The death times come from a new `DebuffLog.deaths`. The "council" withheld reason is removed.
- **Task 3** has the adapter fill `deaths` from the `EnemyDeaths` stream in `repository.debuff_log`. That read is a cache hit on our side and about 1 point on a reference.
- **Task 4** updates the page wording and the docs.
- **Task 5** is the live proof.

**Tech Stack:** Python 3.12, pydantic `Frozen` models, httpx `MockTransport` for offline tests, Jinja2, `uv`.

**Spec:** `docs/plans/2026-10-08-council-debuff-coverage-design.md`. Read it first. It builds on `docs/plans/2026-10-07-enemy-debuff-uptime-design.md`, the parent design for the same feature, which you should also read.

**A clarification the spec leaves open (decided here, recorded in Task 4's design amendment):** the shared-debuff rule compares two players' copies only on a boss both of them held the debuff on. Each player dotting a different council boss is therefore no evidence of anything. Without this, two players whose copies never met, because each kept to their own boss, would read as "shared". For a single boss every pair holds the one target, so the rule is unchanged there.

## Global Constraints

- **Toolchain:** `uv` is not on PATH in the Bash tool. Begin every shell command that runs it with `export PATH="$HOME/.local/bin:$PATH";`.
- **Git:** use `/mingw64/bin/git` for every git command.
- **Hooks:** never use `--no-verify` or any other hook bypass.
- **Commit messages:**
  - plain ASCII only;
  - imperative subject, no `feat:` prefix;
  - the body says why;
  - end with a `Co-Authored-By:` trailer naming the model that wrote the commit.
- **File headers:** every new code file starts with two `# ABOUTME: ` lines.
- **Fixture names:** tests use only the sanctioned character names `Emberkin`, `Stonewake`, `Bríala` and `Кириллица`. NPC and boss names are invented, e.g. `Alpha Fixture`, `Beta Fixture`, `The Test Colossus`. No real report code appears in `tests/`.
- **Layering:** the domain performs no I/O.
- **Badges:** debuff gaps and unjudged findings are `derived`, and unavailable is `measured`. Nothing here changes a badge.
- **Thresholds:** they are reused, never redefined. `SHARED_OVERLAP_TOLERANCE_S = 1.0` stays as it is.
- **Comments:** never remove a comment unless it is actively false.
- **Line length:** ruff's limit applies. Wrap long lines; never `noqa`.
- **Gate before every commit:** `uv run ruff check .`, `uv run mypy` and `uv run pytest -q` all pass, with pristine output.
- **Network:** no task except Task 5 makes a network call. Never read `.env`.

---

## File Structure

| File | Change |
| --- | --- |
| `src/wowperf/domain/debuffs.py` | `DebuffLog.deaths` (Task 2). |
| `src/wowperf/domain/comparison/boss_debuffs.py` | `BossTarget`, `BossWindow.targets` and `.deathless`, `BossDebuffs.covered`, `.names` and `.covered_seconds`, `bosses_of`, per-target `find_shared`, and the removal of `Withheld.COUNCIL` (Tasks 1-2). |
| `src/wowperf/domain/comparison/debuff_uptime.py` | `debuff_fractions` reads covered seconds (Task 1); `GAP_DETAIL` (Task 4); the table's `deathless` (Task 4). |
| `src/wowperf/domain/comparison/measures.py` | `BossDebuffTable.deathless` (Task 4). |
| `src/wowperf/domain/report/players.py` | the `WITHHELD_LABELS` entry (Task 2), the caption (Task 4). |
| `src/wowperf/adapters/wcl/ingest.py`, `repository.py` | deaths into the log (Task 3). |
| Tests | `tests/domain/comparison/test_boss_debuffs.py`, `test_debuff_uptime.py`, `test_sample_invariants.py`, `tests/domain/report/test_build_players.py`, `tests/adapters/wcl/test_ingest_debuffs.py`, `test_repository.py`, `tests/test_cli.py` and `tests/e2e/test_boss_debuffs_e2e.py`. |
| Docs (Task 4) | the parent design §2, this design's status line, the mplus-analysis skill, CLAUDE.md and `docs/how-it-works.md`. |
| Docs (Task 5) | the wcl-api skill's cost reading, and this design's live amendment. |

---

### Task 1: Count covered seconds per boss target (a refactor: no figure moves)

**Files:**
- Modify: `src/wowperf/domain/comparison/boss_debuffs.py`
- Modify: `src/wowperf/domain/comparison/debuff_uptime.py`, specifically `debuff_fractions` and its imports
- Modify tests:
  - `tests/domain/comparison/test_boss_debuffs.py`
  - `tests/domain/comparison/test_debuff_uptime.py`
  - `tests/domain/comparison/test_sample_invariants.py`
  - `tests/e2e/test_boss_debuffs_e2e.py`

**Interfaces:**
- Produces:
  - `BossTarget(game_id: int, start_ms: int, end_ms: int)`, with property `seconds: float`.
  - `BossWindow(encounter_id, name, start_ms, end_ms, targets: tuple[BossTarget, ...] = (), withheld: Withheld | None = None)`. Its property `seconds` is now the sum of its targets' seconds. The `boss_game_id` field is removed.
  - `BossDebuffs(windows, covered: tuple[tuple[int, int, int], ...] = (), names: tuple[tuple[int, str], ...] = (), tally, shared_with)`, with property `seconds` and method `covered_seconds(ability_id: int, encounter_id: int | None = None) -> float`. The `auras` field and the `measured` property are removed.
  - `find_shared(held: Mapping[tuple[int, int], Mapping[tuple[int, int], Sequence[tuple[int, int]]]], owner_id: int) -> tuple[tuple[int, tuple[int, ...]], ...]`. `held` is keyed by (owner, ability id), then by (window index, target game id), and its values are clipped millisecond spans.
- Unchanged signatures: `boss_debuffs(log, pulls, owner_id, players)`, `boss_windows_of(pulls, npc_actors)`, `boss_game_id_of(...)`, `encounter_share(debuffs, ability_id, encounter_id)` and `debuff_fractions(debuffs)`.

- [ ] **Step 1: Rewrite the tests that read the old internals (they fail to run until Step 3)**

In `tests/domain/comparison/test_boss_debuffs.py`:
- Import `BossTarget` from `wowperf.domain.comparison.boss_debuffs`. Remove the `uptime_seconds_in` import.
- Add this helper after `an_enemy`:

```python
def boss_ids(window: BossWindow) -> tuple[int, ...]:
    """The game ids a window is measured on, in order."""
    return tuple(target.game_id for target in window.targets)
```

- Replace the body of `test_a_single_boss_is_measured_over_its_own_pull_and_trash_is_not` with:

```python
    assert boss_windows_of((TRASH_PULL, BOSS_PULL), ACTORS) == (
        BossWindow(
            encounter_id=2001,
            name=BOSS_NAME,
            start_ms=10_000,
            end_ms=70_000,
            targets=(BossTarget(game_id=BOSS_GAME, start_ms=10_000, end_ms=70_000),),
        ),
    )
```

- In `test_only_the_debuff_on_the_boss_counts`, replace the three assertions with:

```python
    assert mine.covered == ((2001, DOT, 30_000),)
    assert mine.names == ((DOT, "Blood Plague"),)
    assert mine.seconds == 60.0
```

- In `test_an_interval_reaching_past_the_pull_is_clipped_to_it`: `assert mine.covered == ((2001, DOT, 60_000),)`
- In `test_a_pet_counts_for_its_owner_and_an_overlap_counts_once`, replace both assertions with `assert mine.covered_seconds(DOT) == 40.0`
- In `test_another_players_debuff_is_not_this_players`: `assert mine.covered == ()`
- In `test_a_council_is_withheld_and_counts_no_seconds`: `assert (mine.seconds, mine.covered) == (0.0, ())`
- In `test_a_boss_whose_name_only_begins_the_pulls_is_still_the_boss`: `assert [boss_ids(window) for window in boss_windows_of((pull,), actors)] == [(BOSS_GAME,)]`
- In every test that asserts `(window.boss_game_id, window.withheld) == (X, None)`, use `(boss_ids(window), window.withheld) == ((X,), None)`.
- In every test that asserts `(window.boss_game_id, window.withheld) == (None, R)`, use `(boss_ids(window), window.withheld) == ((), R)`.
- In `test_a_debuff_one_teammates_application_replaces_is_shared_with_them`, the last line: `assert mine.covered_seconds(DOT) == 40.0`
- In `test_our_zero_is_shared_when_two_teammates_took_the_debuff_over_from_each_other`: `assert mine.covered == ()`

Append this new test, which pins the arithmetic the refactor must keep:

```python
def test_covered_seconds_merge_a_players_and_their_pets_copies_on_one_boss() -> None:
    # Ours 20-50s, our pet 40-60s, ours again 65-80s (clipped to the pull's 70s):
    # 20-60 merged is 40s, plus 65-70 is 5s. A sum of the parts would read 65s.
    mine = boss_debuffs(
        a_log(
            *held(PLAYER, 20_000, 50_000),
            *held(PET, 40_000, 60_000),
            *held(PLAYER, 65_000, 80_000),
        ),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered == ((2001, DOT, 45_000),)
    assert mine.covered_seconds(DOT, 2001) == 45.0
    assert mine.covered_seconds(DOT, 9999) == 0.0
```

In `tests/domain/comparison/test_debuff_uptime.py`:
- Import `BossTarget` with the other `boss_debuffs` names. Remove the `Aura, AuraBand` import if nothing else in the file uses it.
- Replace `on_the_boss` with:

```python
def on_the_boss(*shares: tuple[int, str, float], seconds: float = 100.0) -> BossDebuffs:
    """One measured boss pull of `seconds`, each debuff on it for its share from the pull."""
    end_ms = int(seconds * 1000)
    window = BossWindow(
        encounter_id=2001,
        name="The Test Colossus",
        start_ms=0,
        end_ms=end_ms,
        targets=(BossTarget(game_id=5000, start_ms=0, end_ms=end_ms),),
    )
    carried = [(ability_id, name, share) for ability_id, name, share in shares if share > 0]
    return BossDebuffs(
        windows=(window,),
        covered=tuple(
            (2001, ability_id, int(end_ms * share)) for ability_id, _, share in carried
        ),
        names=tuple((ability_id, name) for ability_id, name, _ in carried),
    )
```

- Replace `FIRST`, `SECOND` and `SECOND_COUNCIL` with:

```python
FIRST = BossWindow(
    encounter_id=2001,
    name="First Boss",
    start_ms=0,
    end_ms=100_000,
    targets=(BossTarget(game_id=5000, start_ms=0, end_ms=100_000),),
)
SECOND = BossWindow(
    encounter_id=2002,
    name="Second Boss",
    start_ms=200_000,
    end_ms=300_000,
    targets=(BossTarget(game_id=6000, start_ms=200_000, end_ms=300_000),),
)
SECOND_COUNCIL = SECOND.model_copy(update={"targets": (), "withheld": Withheld.COUNCIL})
```

- Replace `on_two_bosses` with:

```python
def on_two_bosses(
    first: float, second: float, *, windows: tuple[BossWindow, ...] = (FIRST, SECOND)
) -> BossDebuffs:
    covered = []
    if first > 0:
        covered.append((2001, DOT, int(100_000 * first)))
    if second > 0:
        covered.append((2002, DOT, int(100_000 * second)))
    return BossDebuffs(
        windows=windows,
        covered=tuple(covered),
        names=((DOT, DOT_NAME),) if covered else (),
    )
```

In `tests/domain/comparison/test_sample_invariants.py`, make `_boss_debuffs` return:

```python
    return BossDebuffs(
        windows=(
            BossWindow(
                encounter_id=BOSS_ENCOUNTER_ID,
                name="Boss",
                start_ms=start_ms,
                end_ms=end_ms,
                targets=(BossTarget(game_id=99, start_ms=start_ms, end_ms=end_ms),),
            ),
        ),
        covered=((BOSS_ENCOUNTER_ID, UPTIME_BOSS_ABILITY_ID, up_ms),),
        names=((UPTIME_BOSS_ABILITY_ID, UPTIME_BOSS_ABILITY_NAME),),
    )
```

Import `BossTarget` there. Keep `Aura` and `AuraBand`, which the buff fixtures still use.

In `tests/e2e/test_boss_debuffs_e2e.py`, remove the `uptime_seconds_in` import, and replace the inner loop and the `boss_ids` line with:

```python
        for ability_id, name in mine.names:
            # A share cannot exceed the boss-alive time it was measured over.
            assert mine.covered_seconds(ability_id) <= mine.seconds + 1e-9, name
            landed += 1
```

```python
    boss_ids = {target.game_id for window in measured for target in window.targets}
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison -q`
Expected: errors on `BossTarget` (ImportError), or failures on `covered` and `names`.

- [ ] **Step 3: Rewrite `boss_debuffs.py`'s model and arithmetic**

Change the ABOUTME's second line to: `# ABOUTME: Covered seconds per boss target, summed; a council or a missing boss is withheld.`

Replace the imports with the following. `Aura`, `AuraBand` and `uptime_seconds_in` are no longer used:

```python
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from itertools import combinations

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor, find_bosses, named_after
from wowperf.domain.debuffs import DebuffLog, PairingTally, pair_debuffs
from wowperf.domain.model import Pull

Span = tuple[int, int]
"""A start and an end, in milliseconds of the log's clock."""
```

Replace `BossWindow` and `BossDebuffs` with:

```python
class BossTarget(Frozen):
    """One boss of a measured pull, and the span its figure is drawn over."""

    game_id: int
    start_ms: int
    end_ms: int

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


class BossWindow(Frozen):
    """One boss pull, and the bosses it is measured on, or why it is not."""

    encounter_id: int
    name: str
    start_ms: int
    end_ms: int
    targets: tuple[BossTarget, ...] = ()
    withheld: Withheld | None = None

    @property
    def seconds(self) -> float:
        """Boss-alive seconds: each target's span, summed. A withheld pull has none."""
        return sum(target.seconds for target in self.targets)


class BossDebuffs(Frozen):
    """One player's debuffs on the bosses of one run, as seconds covered per boss.

    A player's and their pets' copies of one debuff on one boss are merged
    before they are counted, so a second is never counted twice on one boss.
    A second covered on two bosses at once counts on each: the figure is
    coverage, debuff-seconds over boss-alive seconds.
    """

    windows: tuple[BossWindow, ...] = ()
    covered: tuple[tuple[int, int, int], ...] = ()
    """(encounter id, ability id, milliseconds it covered that encounter's measured bosses)."""
    names: tuple[tuple[int, str], ...] = ()
    """(ability id, name), for every debuff in `covered`."""
    tally: PairingTally = PairingTally()
    shared_with: tuple[tuple[int, tuple[int, ...]], ...] = ()
    """(ability id, the other players' actor ids), for each debuff `find_shared` finds shared."""

    @property
    def seconds(self) -> float:
        """The denominator: boss-alive seconds of the measured pulls, withheld ones left out."""
        return sum(window.seconds for window in self.windows if window.withheld is None)

    def covered_seconds(self, ability_id: int, encounter_id: int | None = None) -> float:
        """Seconds this debuff covered the measured bosses, of one encounter or of all."""
        return (
            sum(
                ms
                for encounter, ability, ms in self.covered
                if ability == ability_id and (encounter_id is None or encounter == encounter_id)
            )
            / 1000
        )
```

In `boss_windows_of`, build each window as follows. The targets replace `boss_game_id`:

```python
        found = boss_game_id_of(
            npc_actors, frozenset(enemy.actor_id for enemy in pull.enemies), pull.name
        )
        windows.append(
            BossWindow(
                encounter_id=pull.encounter_id,
                name=pull.name,
                start_ms=pull.start_ms,
                end_ms=pull.end_ms,
                targets=()
                if isinstance(found, Withheld)
                else (BossTarget(game_id=found, start_ms=pull.start_ms, end_ms=pull.end_ms),),
                withheld=found if isinstance(found, Withheld) else None,
            )
        )
```

Replace `boss_debuffs`, `find_shared`, `_overlap_ms` and `encounter_share` with the following:

```python
def boss_debuffs(
    log: DebuffLog, pulls: Sequence[Pull], owner_id: int, players: frozenset[int]
) -> BossDebuffs:
    """What this player, and their pets, kept on each measured boss of this run.

    The boss is matched by game id, for the same reason the pairing keys on it.
    Each interval is clipped to the span of the boss it sat on.

    `players` is the actor ids of the run's players, the only owners whose
    debuffs `find_shared` reads: a pet is already folded into its owner by the
    pairing, and an enemy is never a player. A reference is read with none, so
    nothing on its side is ever shared.
    """
    windows = boss_windows_of(pulls, log.npc_actors)
    intervals, tally = pair_debuffs(log)
    owners = players | {owner_id}
    held: dict[tuple[int, int], dict[tuple[int, int], list[Span]]] = {}
    for index, window in enumerate(windows):
        for target in window.targets:
            for one in intervals:
                if one.owner_id not in owners or one.target_game_id != target.game_id:
                    continue
                start_ms = max(one.start_ms, target.start_ms)
                end_ms = min(one.end_ms, target.end_ms)
                if end_ms > start_ms:
                    by_target = held.setdefault((one.owner_id, one.ability_id), {})
                    by_target.setdefault((index, target.game_id), []).append((start_ms, end_ms))

    covered: dict[tuple[int, int], int] = defaultdict(int)
    for (owner, ability_id), by_target in held.items():
        if owner != owner_id:
            continue
        for (index, _), spans in by_target.items():
            covered[(windows[index].encounter_id, ability_id)] += _length_ms(_merged(spans))
    names = dict(log.ability_names)
    return BossDebuffs(
        windows=windows,
        covered=tuple(
            (encounter_id, ability_id, ms)
            for (encounter_id, ability_id), ms in sorted(covered.items())
        ),
        names=tuple(
            (ability_id, names.get(ability_id, f"Unknown ability {ability_id}"))
            for ability_id in sorted({ability_id for _, ability_id in covered})
        ),
        tally=tally,
        shared_with=find_shared(held, owner_id),
    )


def find_shared(
    held: Mapping[tuple[int, int], Mapping[tuple[int, int], Sequence[Span]]], owner_id: int
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Each debuff this owner shares one slot of with other players, and who those are.

    `held` is every player's clipped spans on the measured bosses, keyed by
    (owner, ability id) and then by (window index, boss game id). A debuff is
    exclusive when at least two owners held it and no two of them overlapped by
    more than `SHARED_OVERLAP_TOLERANCE_S` in total, the overlaps measured
    boss by boss and summed: a teammate's application replaced the one before
    it. Several owners holding it is not enough on its own, since copies of a
    per-caster debuff coexist.

    It is shared with this owner when it is exclusive and someone else held it.
    That includes a debuff this owner never held, once two others took it over
    from each other. Beside a single other owner, the overlap that would show
    exclusivity has no second owner to be measured against, so the debuff is
    not shared and its zero stays unjudged.
    """
    holders: dict[int, dict[int, dict[tuple[int, int], list[Span]]]] = defaultdict(dict)
    for (owner, ability_id), by_target in held.items():
        holders[ability_id][owner] = {target: _merged(spans) for target, spans in by_target.items()}

    shared: list[tuple[int, tuple[int, ...]]] = []
    for ability_id in sorted(holders):
        owners = holders[ability_id]
        others = tuple(sorted(owner for owner in owners if owner != owner_id))
        exclusive = len(owners) >= 2 and all(
            _overlap_ms(first, second) <= SHARED_OVERLAP_TOLERANCE_S * 1000
            for first, second in combinations(owners.values(), 2)
        )
        if exclusive and others:
            shared.append((ability_id, others))
    return tuple(shared)


def _overlap_ms(
    first: Mapping[tuple[int, int], Sequence[Span]],
    second: Mapping[tuple[int, int], Sequence[Span]],
) -> int:
    """The milliseconds two owners' copies of one debuff sat on the same boss at once.

    Boss by boss, each alone less the two together is exactly the time counted
    twice; those are summed. Every edge is a whole millisecond, so it is exact.
    """
    return sum(
        _length_ms(first[target])
        + _length_ms(second[target])
        - _length_ms(_merged([*first[target], *second[target]]))
        for target in first.keys() & second.keys()
    )


def _merged(spans: Iterable[Span]) -> list[Span]:
    """The spans, overlaps joined, in order."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _length_ms(spans: Iterable[Span]) -> int:
    return sum(end - start for start, end in spans)


def encounter_share(
    debuffs: BossDebuffs, ability_id: int, encounter_id: int
) -> float | Withheld | None:
    """The share of one encounter's boss-alive seconds this debuff covered.

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
    return debuffs.covered_seconds(ability_id, encounter_id) / seconds
```

In `src/wowperf/domain/comparison/debuff_uptime.py`, replace `debuff_fractions` with the version below, and drop `fractions_of` and `seconds_up_in` from the `uptime` import:

```python
def debuff_fractions(debuffs: BossDebuffs) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of measured boss-alive seconds it covered)."""
    seconds = debuffs.seconds
    if seconds <= 0:
        return {}
    return {
        ability_id: (name, debuffs.covered_seconds(ability_id) / seconds)
        for ability_id, name in debuffs.names
    }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain -q`
Expected: all pass, including every shared-debuff test, unchanged except for the assertions rewritten in Step 1.

- [ ] **Step 5: Gate**

Run `uv run ruff check .`, `uv run mypy`, then `uv run pytest -q`. All must pass. Then grep `src/` and `tests/` for `boss_game_id`, `.auras` on a `BossDebuffs`, and `.measured`. Nothing may still read the removed names. `boss_game_id_of` is a function that survives this task.

- [ ] **Step 6: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/boss_debuffs.py src/wowperf/domain/comparison/debuff_uptime.py tests/domain/comparison/test_boss_debuffs.py tests/domain/comparison/test_debuff_uptime.py tests/domain/comparison/test_sample_invariants.py tests/e2e/test_boss_debuffs_e2e.py
```

Commit subject: `Count debuff seconds per boss rather than merging one timeline`. Body: a council's bosses are alive at once, so a second covered on both must count twice, which merged bands cannot express. Every existing figure is unchanged.

---

### Task 2: Measure a council over each boss's alive time

**Files:**
- Modify:
  - `src/wowperf/domain/debuffs.py` (`DebuffLog.deaths`)
  - `src/wowperf/domain/comparison/boss_debuffs.py`
  - `src/wowperf/domain/report/players.py` (remove the `Withheld.COUNCIL` label)
- Modify tests:
  - `tests/domain/comparison/test_boss_debuffs.py`
  - `tests/domain/comparison/test_debuff_uptime.py`
  - `tests/domain/report/test_build_players.py`
  - `tests/e2e/test_boss_debuffs_e2e.py`

**Interfaces:**
- Consumes: Task 1's `BossTarget`, `BossWindow.targets`, `BossDebuffs.covered` and `find_shared`.
- Produces:
  - `DebuffLog.deaths: tuple[tuple[int, int], ...] = ()`, as (enemy game id, timestamp ms).
  - `BossesFound(game_ids: tuple[int, ...], council: bool = False)`.
  - `bosses_of(npc_actors, enemy_ids, pull_name) -> BossesFound | Withheld`, which replaces `boss_game_id_of`.
  - `boss_windows_of(pulls, npc_actors, deaths: tuple[tuple[int, int], ...] = ())`.
  - `BossWindow.deathless: int = 0`, the council bosses with no death in a kill pull.
  - `BossDebuffs.deathless`, a property summing the windows' counts.
  - `Withheld` loses `COUNCIL`.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/comparison/test_boss_debuffs.py`, the council expectations change:
- `test_a_council_is_withheld_and_counts_no_seconds`: rename it to `test_a_council_is_measured_over_its_bosses_lives`. Give the log `deaths=((BOSS_GAME, 40_000), (ADD_GAME, 70_000))`; the council fixture's actors carry those game ids. Assert:
  - `[window.withheld for window in mine.windows] == [None]`;
  - `mine.seconds == 30.0 + 60.0`;
  - `mine.covered == ((2001, DOT, 20_000),)`. The player's 20-50 s on BOSS_ACTOR is clipped to that boss's death at 40 s.
- `test_a_share_is_read_per_boss_and_a_withheld_boss_says_why`: the second pull is now measured. Rename the test to `test_a_share_is_read_per_boss`, and replace `is Withheld.COUNCIL` with `== 0.0`, since nothing was on the council's bosses.
- Every `(boss_ids(window), window.withheld) == ((), Withheld.COUNCIL)` becomes the council's game ids with `None`:
  - the two unflagged-pair, flagged-pair and two-flagged tests: `((FIRST_GAME, SECOND_GAME), None)`;
  - `test_a_pull_named_for_two_bosses_with_one_in_it_is_still_a_council`: `((FIRST_GAME,), None)`. Rename it `test_a_pull_named_for_two_bosses_with_one_in_it_measures_that_one`.

Give `a_log` a `deaths` keyword: `deaths: tuple[tuple[int, int], ...] = ()`, passed through to `DebuffLog(deaths=deaths, ...)`.

Append these tests:

```python
ALPHA, BETA = 63, 64
ALPHA_GAME, BETA_GAME = 6300, 6400
COUNCIL_NAME = "Alpha Fixture and Beta Fixture"
COUNCIL_ACTORS = (
    an_enemy(ALPHA, ALPHA_GAME, "Alpha Fixture"),
    an_enemy(BETA, BETA_GAME, "Beta Fixture"),
)


def a_council_pull(*, killed: bool = True) -> Pull:
    pull = a_pull(1, 10_000, 70_000, encounter_id=2001, name=COUNCIL_NAME, enemies=(ALPHA, BETA))
    return pull.model_copy(
        update={
            "killed": killed,
            "enemies": (
                EnemyNpc(actor_id=ALPHA, game_id=ALPHA_GAME),
                EnemyNpc(actor_id=BETA, game_id=BETA_GAME),
            ),
        }
    )


def a_council_log(*events: DebuffEvent, deaths: tuple[tuple[int, int], ...] = ()) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=((ALPHA, ALPHA_GAME), (BETA, BETA_GAME), (THIRD, ALPHA_GAME)),
        npc_actors=COUNCIL_ACTORS,
        ability_names=((DOT, "Blood Plague"),),
        deaths=deaths,
        end_ms=80_000,
    )


def on(target: int, source: int, start_ms: int, end_ms: int) -> tuple[DebuffEvent, DebuffEvent]:
    """One application and its removal, by `source`, on `target`."""
    return (
        an_event(True, start_ms, source=source, target=target),
        an_event(False, end_ms, source=source, target=target),
    )


def test_a_councils_coverage_sums_each_boss_over_its_own_life() -> None:
    # Alpha dies at 40s, Beta at 70s: 30s and 60s alive. Ours covered Alpha for
    # 30s (all of it) and Beta for 30s: 60s of 90s. A pull-length reading would
    # be 60s over 60s, and a merged timeline 30s over 60s.
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 40_000),
            *on(BETA, PLAYER, 10_000, 40_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    [window] = mine.windows
    assert window.targets == (
        BossTarget(game_id=ALPHA_GAME, start_ms=10_000, end_ms=40_000),
        BossTarget(game_id=BETA_GAME, start_ms=10_000, end_ms=70_000),
    )
    assert mine.seconds == 90.0
    assert mine.covered_seconds(DOT) == 60.0
    assert encounter_share(mine, DOT, 2001) == 60.0 / 90.0


def test_a_wiped_council_runs_each_boss_to_the_pulls_end_and_counts_no_missing_death() -> None:
    [window] = boss_windows_of((a_council_pull(killed=False),), COUNCIL_ACTORS)

    assert [target.end_ms for target in window.targets] == [70_000, 70_000]
    assert window.deathless == 0


def test_a_killed_council_boss_with_no_death_runs_to_the_pulls_end_and_is_counted() -> None:
    [window] = boss_windows_of(
        (a_council_pull(),), COUNCIL_ACTORS, ((ALPHA_GAME, 40_000),)
    )

    assert [target.end_ms for target in window.targets] == [40_000, 70_000]
    assert window.deathless == 1


def test_a_boss_that_dies_twice_lives_until_its_last_death() -> None:
    [window] = boss_windows_of(
        (a_council_pull(),),
        COUNCIL_ACTORS,
        ((ALPHA_GAME, 30_000), (ALPHA_GAME, 50_000), (BETA_GAME, 60_000)),
    )

    assert [target.end_ms for target in window.targets] == [50_000, 60_000]


def test_a_death_outside_the_pull_is_not_this_pulls() -> None:
    [window] = boss_windows_of(
        (a_council_pull(),),
        COUNCIL_ACTORS,
        ((ALPHA_GAME, 5_000), (ALPHA_GAME, 75_000), (BETA_GAME, 60_000)),
    )

    assert [target.end_ms for target in window.targets] == [70_000, 60_000]
    assert window.deathless == 1


def test_a_single_boss_runs_the_whole_pull_whatever_the_deaths_say() -> None:
    [window] = boss_windows_of((BOSS_PULL,), ACTORS, ((BOSS_GAME, 50_000),))

    assert window.targets == (BossTarget(game_id=BOSS_GAME, start_ms=10_000, end_ms=70_000),)


def test_a_council_boss_logged_under_a_second_actor_id_is_still_that_boss() -> None:
    # Actor THIRD is a second id of Alpha's game id: what sat on it, sat on Alpha.
    mine = boss_debuffs(
        a_council_log(*on(THIRD, PLAYER, 10_000, 40_000), deaths=((ALPHA_GAME, 40_000),)),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.covered_seconds(DOT) == 30.0


def test_two_players_on_different_council_bosses_do_not_share() -> None:
    # Ours only ever on Alpha, theirs only ever on Beta: the copies never met on
    # one boss, which says nothing about whether they could coexist.
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 40_000),
            *on(BETA, OTHER, 10_000, 40_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()


def test_a_debuff_two_players_swap_on_each_council_boss_is_shared() -> None:
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 25_000),
            *on(ALPHA, OTHER, 25_000, 40_000),
            *on(BETA, OTHER, 10_000, 40_000),
            *on(BETA, PLAYER, 40_000, 70_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ((DOT, (OTHER,)),)


def test_copies_that_coexist_on_one_council_boss_are_per_caster() -> None:
    # They swap on Alpha but sit together on Beta for 20s: per caster after all.
    mine = boss_debuffs(
        a_council_log(
            *on(ALPHA, PLAYER, 10_000, 25_000),
            *on(ALPHA, OTHER, 25_000, 40_000),
            *on(BETA, PLAYER, 10_000, 50_000),
            *on(BETA, OTHER, 30_000, 70_000),
            deaths=((ALPHA_GAME, 40_000), (BETA_GAME, 70_000)),
        ),
        (a_council_pull(),),
        PLAYER,
        RUN_PLAYERS,
    )

    assert mine.shared_with == ()
```

`test_two_players_on_different_council_bosses_do_not_share` is the clarification test. It must fail against Task 1's `find_shared`, because there two owners with no common boss overlap by 0 ms, which reads as exclusive.

In `tests/domain/comparison/test_debuff_uptime.py`, two things change:
- `SECOND_COUNCIL` becomes `SECOND.model_copy(update={"targets": (), "withheld": Withheld.NO_BOSS})`. Rename it `SECOND_UNFOUND`, and update its users.
- Every other `Withheld.COUNCIL` in that file becomes `Withheld.NO_BOSS`, and every window or cell name "The Twin Council" becomes "The Fixture Hall".
  - The expectation in `test_our_council_cell_is_withheld_with_its_reason` becomes `withheld=Withheld.NO_BOSS`. Rename the test `test_our_unfound_boss_cell_is_withheld_with_its_reason`.

In `tests/domain/report/test_build_players.py`, apply the same rule. The fixture cell `withheld=Withheld.COUNCIL` becomes `withheld=Withheld.NO_BOSS`, and its pinned rendering `"a council, not measured"` becomes `"no boss found"`.

In `tests/e2e/test_boss_debuffs_e2e.py`, call `boss_windows_of(run.pulls, log.npc_actors, log.deaths)`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain -q`
Expected:
- failures on the missing `deaths` keyword, `deathless` and the council expectations;
- `test_two_players_on_different_council_bosses_do_not_share` fails, reading as shared.

- [ ] **Step 3: Add the deaths to the log**

In `src/wowperf/domain/debuffs.py`, add this to `DebuffLog`, after `ability_names`:

```python
    deaths: tuple[tuple[int, int], ...] = ()
    """(game id, timestamp ms) of each enemy death in the fight, for a council boss's span."""
```

- [ ] **Step 4: Find councils and their spans in `boss_debuffs.py`**

1. Update the ABOUTME's second line to `# ABOUTME: Covered seconds per boss, summed; a council's bosses each over their own life.`
2. Remove `COUNCIL` from `Withheld`. Rewrite its docstring's first paragraph so it no longer names a council. Only "no boss found" is now read off our own route.
3. Replace `boss_game_id_of` with:

```python
class BossesFound(Frozen):
    """The game ids a boss pull is measured on, and whether they are a council's."""

    game_ids: tuple[int, ...]
    council: bool = False


def bosses_of(
    npc_actors: tuple[NpcActor, ...], enemy_ids: frozenset[int], pull_name: str
) -> BossesFound | Withheld:
    """The bosses a pull is measured on, or why it has none.

    Measured 2026-10-08: dungeon logs flag only some bosses as `Boss`, and a
    council's pull is named "A and B", which begins with A's name alone. So the
    pull's name is read first: split on " and " (never on a comma, which marks
    a title), each part names the pull's enemies that open with it, counted by
    game id because one enemy can be logged under two actor ids. A part naming
    two game ids is no boss. A pull named for several bosses is a council,
    measured on every one of them among its enemies, even one. One part with
    one game id is the boss. When the name matches no enemy, the boss flag is
    read as `find_bosses` reads it, also by game id: several flagged bosses are
    a council.
    """
    enemies = [one for one in npc_actors if one.actor_id in enemy_ids]
    parts = pull_name.split(" and ")
    named = [{one.game_id for one in enemies if named_after(one.name, part)} for part in parts]
    if any(len(game_ids) > 1 for game_ids in named):
        return Withheld.NO_BOSS
    found = sorted(set[int]().union(*named))
    if found:
        return BossesFound(game_ids=tuple(found), council=len(parts) > 1)
    flagged = sorted({one.game_id for one in find_bosses(npc_actors, enemy_ids, pull_name)})
    if not flagged:
        return Withheld.NO_BOSS
    return BossesFound(game_ids=tuple(flagged), council=len(flagged) > 1)
```

4. Add `deathless: int = 0` to `BossWindow`, after `withheld`, with this docstring: `"""Council bosses of a kill pull with no death inside it, measured to its end."""`
5. Add this property to `BossDebuffs`:

```python
    @property
    def deathless(self) -> int:
        """Council bosses of a kill pull that never died inside it, over every window."""
        return sum(window.deathless for window in self.windows)
```

6. Replace `boss_windows_of` with:

```python
def boss_windows_of(
    pulls: Sequence[Pull],
    npc_actors: tuple[NpcActor, ...],
    deaths: tuple[tuple[int, int], ...] = (),
) -> tuple[BossWindow, ...]:
    """Every boss pull, with the bosses it is measured on, or the reason it has none.

    One boss is measured over the whole pull. A council's bosses are each
    measured from the pull's start to their last death inside it: the log
    records a death but never an appearance, so the start is the pull's. A
    council boss that never died there runs to the pull's end, and on a kill
    that is counted, since a killed council's bosses all died.
    """
    windows: list[BossWindow] = []
    for pull in pulls:
        if not pull.is_boss:
            continue
        found = bosses_of(
            npc_actors, frozenset(enemy.actor_id for enemy in pull.enemies), pull.name
        )
        if isinstance(found, Withheld):
            windows.append(
                BossWindow(
                    encounter_id=pull.encounter_id,
                    name=pull.name,
                    start_ms=pull.start_ms,
                    end_ms=pull.end_ms,
                    withheld=found,
                )
            )
            continue
        targets: list[BossTarget] = []
        deathless = 0
        for game_id in found.game_ids:
            end_ms = pull.end_ms
            if found.council:
                died = [
                    at for dead, at in deaths if dead == game_id and pull.start_ms <= at <= pull.end_ms
                ]
                if died:
                    end_ms = max(died)
                elif pull.killed:
                    deathless += 1
            targets.append(BossTarget(game_id=game_id, start_ms=pull.start_ms, end_ms=end_ms))
        windows.append(
            BossWindow(
                encounter_id=pull.encounter_id,
                name=pull.name,
                start_ms=pull.start_ms,
                end_ms=pull.end_ms,
                targets=tuple(targets),
                deathless=deathless,
            )
        )
    return tuple(windows)
```

Wrap the `died` comprehension to ruff's line limit.

7. In `boss_debuffs`, call `boss_windows_of(pulls, log.npc_actors, log.deaths)`.
8. In `find_shared`, apply the clarification: only pairs holding a common boss are evidence. Replace the `exclusive` expression with:

```python
        pairs = [
            (first, second)
            for first, second in combinations(owners.values(), 2)
            if first.keys() & second.keys()
        ]
        exclusive = bool(pairs) and all(
            _overlap_ms(first, second) <= SHARED_OVERLAP_TOLERANCE_S * 1000
            for first, second in pairs
        )
```

Add this sentence to its docstring, after "measured boss by boss and summed": "Only owners who held it on a common boss are compared: two copies that each kept to a different boss of a council never met, which shows nothing either way."

9. In `src/wowperf/domain/report/players.py`, remove the `Withheld.COUNCIL` entry from `WITHHELD_LABELS`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain -q`
Expected: all pass. `grep -rn "COUNCIL\|boss_game_id_of" src tests` finds nothing.

- [ ] **Step 6: Gate and commit**

Run ruff, mypy and the full suite.

```bash
/mingw64/bin/git add src/wowperf/domain/debuffs.py src/wowperf/domain/comparison/boss_debuffs.py src/wowperf/domain/report/players.py tests/domain/comparison/test_boss_debuffs.py tests/domain/comparison/test_debuff_uptime.py tests/domain/report/test_build_players.py tests/e2e/test_boss_debuffs_e2e.py
```

Commit subject: `Measure a council's bosses each over their own life`. Body: the log records each boss's death, so a council's time is bounded by measurement. Two players' copies are compared only where both sat on a common boss.

---

### Task 3: Read the enemy deaths into the debuff log

**Files:**
- Modify:
  - `src/wowperf/adapters/wcl/ingest.py`: `build_debuff_log`
  - `src/wowperf/adapters/wcl/repository.py`: `debuff_log`
- Modify tests:
  - `tests/adapters/wcl/test_ingest_debuffs.py`
  - `tests/adapters/wcl/test_repository.py`
  - `tests/test_cli.py`, the test `test_a_reference_does_not_pay_for_the_streams_no_comparison_reads`

**Interfaces:**
- Consumes: Task 2's `DebuffLog.deaths`.
- Produces: `build_debuff_log(events, actors, ability_names, end_ms, death_events: Sequence[dict[str, Any]] = ())`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/wcl/test_ingest_debuffs.py`:

```python
def test_enemy_deaths_ride_along_by_game_id_and_unknown_actors_are_skipped() -> None:
    log = build_debuff_log(
        EVENTS,
        ACTORS,
        {55078: "Blood Plague"},
        9000,
        death_events=[
            {"type": "death", "targetID": 279, "timestamp": 8000},
            {"type": "death", "targetID": 12345, "timestamp": 8100},
            {"type": "resurrect", "targetID": 279, "timestamp": 8200},
        ],
    )

    assert log.deaths == ((999, 8000),)


def test_no_death_events_mean_no_deaths() -> None:
    assert a_log().deaths == ()
```

Append to `tests/adapters/wcl/test_repository.py`:

```python
def test_the_debuff_log_carries_the_fights_enemy_deaths(tmp_path: Path) -> None:
    calls: list[str] = []

    log = recording_repository(calls, tmp_path).debuff_log("abc123", 36)

    assert log.deaths == ((244889, 15000),)
    assert "EnemyDeaths" in calls


def test_the_debuff_logs_deaths_cost_nothing_after_a_load(tmp_path: Path) -> None:
    """Our own run's full load already read EnemyDeaths with the same variables."""
    calls: list[str] = []
    repository = recording_repository(calls, tmp_path)

    repository.load("abc123", 36)
    repository.debuff_log("abc123", 36)

    assert calls.count("EnemyDeaths") == 1
```

In `tests/test_cli.py`, in `test_a_reference_does_not_pay_for_the_streams_no_comparison_reads`, replace `assert calls.count("EnemyDeaths") == 1` with:

```python
    # Ours, from its full load, and the parse reference's own: a council boss's
    # life ends at its death on either side. Our own second read, inside
    # debuff_log, is a cache hit; the speed reference reads none.
    assert calls.count("EnemyDeaths") == 2
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl tests/test_cli.py -q -k "death or does_not_pay"`
Expected:
- an unknown keyword `death_events`;
- `log.deaths == ()`;
- `EnemyDeaths` counted 1, not 2.

- [ ] **Step 3: Implement**

In `ingest.py`, give `build_debuff_log` a keyword parameter `death_events: Sequence[dict[str, Any]] = ()` (import `Sequence` from `collections.abc` if it is not already imported). Add `deaths` to the `DebuffLog(...)` it builds:

```python
        deaths=tuple(
            (game_ids[event["targetID"]], event["timestamp"])
            for event in death_events
            if event.get("type") == "death" and event.get("targetID") in game_ids
        ),
```

Compute `game_ids = {actor["id"]: actor["gameID"] for actor in actors if actor.get("gameID") is not None}` once at the top of the function, and let the existing `game_ids=` field use it. Add a sentence to the docstring: a death on an actor with no game id is skipped, because it cannot be a boss the figure measures.

In `repository.debuff_log`:
1. Import `ENEMY_DEATHS_QUERY` if it is not already imported.
2. Build the variables dict once, keyed in the same order as `_load`'s `event_variables` (code, fightId, startTime, endTime), so our side's read hits the cache.
3. Fetch both streams with it:

```python
        death_events = fetch_all_events(
            lambda one_query, variables: self._query(one_query, variables),
            ENEMY_DEATHS_QUERY,
            variables,
        )
```

4. Pass `death_events=death_events` to `build_debuff_log`.
5. Add a sentence to the docstring: the fight's enemy deaths ride along, because a council boss's life ends at its death. On our own run, the full load already read them, so it costs nothing; a reference pays about one point.

- [ ] **Step 4: Run the tests to see them pass, gate, commit**

Run the Step 2 command, then ruff, mypy and the full suite.

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/ingest.py src/wowperf/adapters/wcl/repository.py tests/adapters/wcl/test_ingest_debuffs.py tests/adapters/wcl/test_repository.py tests/test_cli.py
```

Commit subject: `Read each fight's enemy deaths into the debuff log`. Body: a council boss is measured until its death, on our side and on each reference. Ours is a cache hit, since the full load already read the stream; a reference pays about one point.

---

### Task 4: Say it on the page and in the docs

**Files:**
- Modify:
  - `src/wowperf/domain/comparison/measures.py`: `BossDebuffTable.deathless`
  - `src/wowperf/domain/comparison/debuff_uptime.py`: `GAP_DETAIL`, plus `deathless` on the table
  - `src/wowperf/domain/report/players.py`: the caption
  - `tests/domain/comparison/test_debuff_uptime.py` and `tests/domain/report/test_build_players.py`
- Docs:
  - `docs/plans/2026-10-07-enemy-debuff-uptime-design.md`
  - `docs/plans/2026-10-08-council-debuff-coverage-design.md`
  - `.claude/skills/mplus-analysis/SKILL.md`
  - `CLAUDE.md`
  - `docs/how-it-works.md`

- [ ] **Step 1: Write the failing tests**

In `tests/domain/comparison/test_debuff_uptime.py`, add:

```python
def test_the_table_carries_our_count_of_deathless_council_bosses() -> None:
    window = FIRST.model_copy(update={"deathless": 1})
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(on_two_bosses(0.5, 0.9, windows=(window, SECOND)), sample)

    assert table.deathless == 1
```

In `tests/domain/report/test_build_players.py`, in `test_the_debuff_table_follows_the_buff_table_with_a_column_per_boss`, update the pinned caption to the new text:

```python
    assert table.caption == (
        "Share of 200s of boss-alive time the bosses carried each debuff from this player "
        "or their pets, against the median of the parses that applied each. A council's "
        "bosses each count from the pull's start to their own death; a pull with no boss "
        "found is left out. Each boss column reads ours against the median and carries no "
        "verdict. A debuff a teammate's application replaces is marked shared, not judged. "
        "The group's log for the whole fight held 1 removal with no application, dropped (a "
        "pet copy's second removal counts here); 2 applications still open at the fight's "
        "end, closed there; and 0 rows on an enemy with no game id, skipped. Derived."
    )
```

Give the helper `a_shared_debuff_table` a keyword `deathless: int = 0`, passed to its `BossDebuffTable(..., deathless=deathless)`. Then append:

```python
@pytest.mark.parametrize(
    ("deathless", "stated"),
    [
        (0, None),
        (1, "1 council boss of a kill pull had no death in the log and was measured to the "
            "pull's end."),
        (2, "2 council bosses of a kill pull had no death in the log and were measured to "
            "the pull's end."),
    ],
)
def test_a_council_boss_with_no_death_is_stated_only_when_there_is_one(
    deathless: int, stated: str | None
) -> None:
    caption = a_shared_debuff_table(deathless=deathless).caption

    if stated is None:
        assert "had no death" not in caption
    else:
        assert caption.endswith(f"skipped. {stated} Derived.")
```

Import `pytest` if the file does not already.

- [ ] **Step 2: Run the tests to see them fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_debuff_uptime.py tests/domain/report/test_build_players.py -q`

- [ ] **Step 3: Implement**

1. **`measures.py`.** In `BossDebuffTable`, add `deathless: int = 0` after `tally`, with a field docstring: "Our own council bosses of a kill pull with no death in the log, measured to the pull's end."
2. **`debuff_uptime.boss_debuff_table`.** Pass `deathless=our.deathless` in both the rows return and the no-rows return. The bare return for `our is None` stays bare.
3. **`GAP_DETAIL`.** Replace its first two sentences with: "Both figures are the share of boss-alive time the bosses carried this debuff from the player or their pets: a single boss over its whole pull, a council's bosses each from the pull's start to their own death. That is comparable even though the fights ran for different lengths. A pull with no boss found is left out on both sides."
4. **`players.py`.** Rewrite the caption's first sentences to the pinned text above, keeping the tally clause. Append the deathless sentence before "Derived." only when `debuffs.deathless > 0`:

```python
    deathless = (
        f"{quantity(debuffs.deathless, 'council boss', 'council bosses')} of a kill pull "
        "had no death in the log and "
        f"{'was' if debuffs.deathless == 1 else 'were'} measured to the pull's end. "
        if debuffs.deathless
        else ""
    )
```

   End the caption with `f"... game id, skipped. {deathless}Derived."`.

5. **Docs.**
   - **Parent design** (`2026-10-07-enemy-debuff-uptime-design.md`): append under §2 a note `*Amended 2026-10-08:* council pulls are measured, as coverage across their bosses, by docs/plans/2026-10-08-council-debuff-coverage-design.md.`
   - **This design** (`2026-10-08-council-debuff-coverage-design.md`):
     - Change the status line to `approved design, 2026-10-08; planned in docs/plans/2026-10-08-council-debuff-coverage-plan.md.`
     - Append to §4 item 4 a dated note `*Amended 2026-10-08, while planning:*` stating the clarification: only owners who held the debuff on a common boss are compared, since copies that each kept to a different council boss never met. For a single boss this is the existing rule.
   - **`.claude/skills/mplus-analysis/SKILL.md`**, in the debuff bullet:
     - Replace any wording that says a council is left out with: a council's cell is coverage across its bosses, each counted from the pull's start to its own death.
     - Mention `comparison_tables.<slug>.boss_debuffs.deathless` as provenance.
     - `tests/test_skills.py` checks skill prose.
   - **`CLAUDE.md`**: in the sentence ending "Trash, raid and council pulls are not measured yet; ...", drop "and council" so it reads "Trash and raid pulls are not measured yet;".
   - **`docs/how-it-works.md`**: in "Trash, raid and council pulls, and any pull with no single boss, are not measured yet", drop the council clause so it reads "Trash and raid pulls, and any pull with no boss found, are not measured yet".

- [ ] **Step 4: Run the tests to see them pass, gate, commit**

Run the Step 2 command, then ruff, mypy and the full suite (`test_skills.py` included).

```bash
/mingw64/bin/git add src/wowperf/domain/comparison/measures.py src/wowperf/domain/comparison/debuff_uptime.py src/wowperf/domain/report/players.py tests/domain/comparison/test_debuff_uptime.py tests/domain/report/test_build_players.py docs/plans/2026-10-07-enemy-debuff-uptime-design.md docs/plans/2026-10-08-council-debuff-coverage-design.md .claude/skills/mplus-analysis/SKILL.md CLAUDE.md docs/how-it-works.md
```

Commit subject: `Say on the page and in the docs that a council is measured`. Body: the caption, the gap detail and the docs all said council pulls were left out, which is now false.

---

### Task 5: Prove it live

This task carries the CLAUDE.md invariant: a new judgement is not done until a live run shows how often each state it can reach occurred. Budget: about 40 points of the 3600-point hour.

**Files:**
- Modify:
  - `.claude/skills/wcl-api/SKILL.md`: a dated paragraph at the end of "The debuff event stream does name the caster"
  - `docs/plans/2026-10-08-council-debuff-coverage-design.md`: a dated live amendment under §5 and §7
- Scratch, not committed: scripts in the session scratchpad. Write them with the Write tool, never a heredoc, and run them with `uv run python <path>`.

- [ ] **Step 1: Re-run the two keys**

Run these from the worktree. Load the credentials inline: they are UTF-16, and must never be printed.

```bash
set -a && . <(iconv -f UTF-16 -t UTF-8 ../../../.env | tr -d '\r') 2>/dev/null && set +a; export PATH="$HOME/.local/bin:$PATH"; uv run wowperf analyze nd6Rz47Gj1ZPxFfm --fight 3 --cache-dir ../../../cache --out ../../../out/debuffs
```

For `LyKXYvVZm192TDr6` fight 9, `--all-players` needs `--player` naming the roster's first player, because the report owner's name differs from the roster's. Pass that name without ever printing it. The scratchpad script `run_key1.py`, if it is still present, does exactly this. Otherwise write one that reads `run.players[0].name` from the cache and calls `wowperf analyze` through `subprocess`, printing only the cost lines.

Keep each command's cost breakdown. The new cost is the `EnemyDeaths` line, one call per parse reference whose counterpart resolved.

- [ ] **Step 2: Measure the distribution**

Write a scratch script that reads both findings files. It prints, never naming a player (use an index or a class):
- the row verdict counts: `below`, `level`, `unjudged` and shared (a row with a non-empty `shared_with`);
- the cell states: measured, `no boss found`, `no reference measured this boss` and `too few references`;
- each council cell: ours and the median;
- each table's `tally` and `deathless`.

- [ ] **Step 3: Survey the councils on the cached keys**

Write a scratch script over the 26 cached keys. Read them the way the session scratchpad's `survey.py` and `live_shared.py` do, with the network blocked so that a cache miss is reported, never paid for. A reference whose `EnemyDeaths` is not yet cached is reported as missing, not fetched.

For every council pull, print:
- each boss's alive seconds, and whether a death was found;
- a kill pull's deathless bosses;
- the group's coverage of each qualifying debuff, so you can see how far the top parses sit below 100%;
- a check that no coverage exceeds 100%.

- [ ] **Step 4: Judge**

These must each have occurred:
- council cells measured on both keys: Kyrakka and Erkhart Stormvein, and Adderis and Aspix;
- row verdicts `level` and `unjudged`;
- the shared state;
- deathless reported as 0 or more, with a check that every council boss of a kill pull had its death found.

A deathless council boss on a kill is a log oddity. Report it with the pull and the boss name; boss names are allowed.

Coverage above 100% would be a defect. Stop and report it.

`below` and the gap finding were not live before this change. Report whether council coverage now produces them, and if so, check the row's figures by hand against the survey.

- [ ] **Step 5: Record and commit**

1. Add a dated paragraph to the wcl-api skill, at the end of the section "The debuff event stream does name the caster". It records:
   - the `EnemyDeaths` calls and points each command printed;
   - each command's total;
   - that our own side's read was a cache hit.
2. Append a dated `*Amended <date>, live:*` note to this design:
   - under §5, the council coverages measured, and how far the references sat below 100% on Kyrakka and Erkhart (the untargetable question);
   - under §7, the real cost.

```bash
/mingw64/bin/git add .claude/skills/wcl-api/SKILL.md docs/plans/2026-10-08-council-debuff-coverage-design.md
```

Commit subject: `Record council debuff coverage on two live keys`. Body: the design priced this from the cache; this is the feature's own reading.
