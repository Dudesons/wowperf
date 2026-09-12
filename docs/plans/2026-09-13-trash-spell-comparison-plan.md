# Trash Spell Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare a player's cast rates on the trash packs their route shares with a reference's, so the parse axis speaks about more than the third of a dungeon that is boss pulls.

**Architecture:** A new pure module `trash_spells.py` reduces an `Alignment` to two denominators — our aligned trash seconds and theirs — then reuses the existing rate machinery to emit three findings. Nothing new is fetched: `Pull.enemies` and fight-wide casts already arrive on every parse reference and are currently discarded.

**Tech Stack:** Python 3.12, pydantic (`wowperf.domain.base.Frozen`), pytest, uv. Domain layer only — no I/O, no adapters touched.

**Spec:** `docs/plans/2026-09-13-trash-spell-comparison-design.md`

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches network, disk or template.
- **Every finding carries a confidence badge.** All findings in this plan are `Confidence.DERIVED`.
- **No finding in this family carries `seconds_lost`.** A cast rate is never priced in time; pass `seconds_lost=None`.
- **The LLM never computes a number.** Every figure comes from tested Python.
- **No damage ranking.** This compares which buttons were pressed and how often. No percentile, no parse number.
- **Test-first, always.** Write the test, run it, watch it fail for the right reason, then implement. Where a test passes the moment it is written, mutate the guard it covers and confirm the test goes red before trusting it. The repository's recorded failure mode is a test that could never have failed.
- **Every command runs under `uv`.** `uv run pytest`, `uv run ruff check .`, `uv run mypy`. On the development machine `uv` is off PATH in bash; prefix with `export PATH="$HOME/.local/bin:$PATH" && `.
- **Commit messages:** imperative mood, no `feat:`/`fix:` prefix, plain ASCII, body explains why. End with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Never use `--no-verify`.**

---

### Task 1: One counting rule, and a public actor lookup

`trash_spells.py` needs to count one player's casts inside an arbitrary set of pull indices, and to find a reference player's actor id. `spells.py` already does both, privately and boss-scoped. Extract rather than duplicate, so one rule counts casts everywhere.

**Files:**
- Modify: `src/wowperf/domain/comparison/spells.py`
- Test: `tests/domain/comparison/test_spells.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `casts_in(casts: tuple[CastEvent, ...], actor_id: int, indices: frozenset[int]) -> dict[int, tuple[str, int]]`
  - `their_actor_id(theirs: ParseMember, their_name: str) -> int | None` (renamed from `_their_actor_id`)
  - `boss_casts` keeps its existing signature and behaviour.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_spells.py`, after `test_boss_casts_ignore_trash_and_other_players`:

```python
def test_casts_in_counts_only_the_given_pulls_for_the_given_actor() -> None:
    """The counting rule boss_casts uses, taken out so a trash-scoped caller
    shares it rather than writing a second one that can drift."""
    casts = (
        cast(693, 100, "Kept", 1_000, 0),
        cast(693, 100, "Kept", 2_000, 0),
        cast(693, 100, "Kept", 3_000, 5),
        cast(693, 200, "Other pull", 4_000, 9),
        cast(11, 100, "Other actor", 5_000, 0),
        cast(693, 300, "No pull", 6_000, None),
    )

    counted = casts_in(casts, 693, frozenset({0, 5}))

    assert counted == {100: ("Kept", 3)}
```

Add `casts_in` to the import block at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_spells.py::test_casts_in_counts_only_the_given_pulls_for_the_given_actor -v`
Expected: FAIL at import — `ImportError: cannot import name 'casts_in'`.

- [ ] **Step 3: Write minimal implementation**

In `src/wowperf/domain/comparison/spells.py`, add `casts_in` above `boss_casts` and rewrite `boss_casts` on top of it:

```python
def casts_in(
    casts: tuple[CastEvent, ...], actor_id: int, indices: frozenset[int]
) -> dict[int, tuple[str, int]]:
    """One player's casts inside `indices`, as ability id to (name, count).

    The one counting rule in this package. `boss_casts` is this scoped to the
    boss pulls; the trash comparison is this scoped to the packs two routes
    shared. Two callers counting casts two ways is how a page ends up stating
    a rate its own evidence cannot reproduce.
    """
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or event.pull_index not in indices:
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted


def boss_casts(
    run: Run, casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    """One player's casts inside boss pulls, as ability id to (name, count)."""
    return casts_in(casts, actor_id, frozenset(pull.index for pull in run.boss_pulls))
```

- [ ] **Step 4: Run the test and the whole spells suite**

Run: `uv run pytest tests/domain/comparison/test_spells.py -v`
Expected: PASS, including every pre-existing `boss_casts` test — the rewrite must not change behaviour.

- [ ] **Step 5: Publish `their_actor_id`**

Rename `_their_actor_id` to `their_actor_id` in `src/wowperf/domain/comparison/spells.py` and update both call sites inside that file (`compare_spells` and `compare_spells_sample`). Leave the body and docstring unchanged.

- [ ] **Step 6: Run the full suite, lint and types**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all pass. If any test referenced `_their_actor_id` by name, update it.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/domain/comparison/spells.py tests/domain/comparison/test_spells.py
git commit -F - <<'MSG'
Share one cast-counting rule between boss and pull-scoped callers

The trash comparison needs the same counting boss_casts does, over a
different set of pull indices. Extracting the rule keeps one definition of
what counts as a cast, rather than leaving a second caller free to drift
from it and print a rate the evidence beside it cannot reproduce.

their_actor_id loses its underscore for the same reason: the new module has
to find a reference player the same way this one does.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Aligned trash denominators

The heart of the feature. Reduce two runs to the trash packs they share and the seconds each side spent on them.

**Files:**
- Create: `src/wowperf/domain/comparison/trash_spells.py`
- Test: `tests/domain/comparison/test_trash_spells.py`

**Interfaces:**
- Consumes: `align_pulls(ours: Run, theirs: Run) -> Alignment` from `alignment.py`; `Alignment.matched` (tuple of `PullMatch` with `ours_index`/`theirs_index`) and `Alignment.our_packs` (frozenset of our trash pull indices that are real packs).
- Produces:
  - `class AlignedTrash(Frozen)` with `our_pulls: frozenset[int]`, `their_pulls: frozenset[int]`, `our_seconds: float`, `their_seconds: float`, and a `pack_count: int` property returning `len(self.our_pulls)`.
  - `aligned_trash(ours: Run, theirs: Run) -> AlignedTrash`

- [ ] **Step 1: Write the failing test**

Create `tests/domain/comparison/test_trash_spells.py`:

```python
# ABOUTME: Behaviour tests for the trash-pack half of the individual comparison.
# ABOUTME: Only packs two routes shared are compared, and only their own seconds count.

from wowperf.domain.comparison.trash_spells import AlignedTrash, aligned_trash
from wowperf.domain.model import EnemyNpc, Player, Pull, Run

OURS = Player(
    actor_id=693, name="Emberkin", class_name="DeathKnight", spec="Blood", item_level=318
)
THEIRS = Player(
    actor_id=11, name="Bríala", class_name="DeathKnight", spec="Blood", item_level=330
)


def a_pull(index: int, seconds: float, *game_ids: int, encounter_id: int = 0) -> Pull:
    """A pull holding one enemy actor per game id, so alignment can match on types."""
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack" if encounter_id == 0 else "Boss",
        encounter_id=encounter_id,
        start_ms=index * 400_000,
        end_ms=index * 400_000 + int(seconds * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=1000 + n, game_id=g) for n, g in enumerate(game_ids)),
    )


def a_run(player: Player, *pulls: Pull) -> Run:
    return Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(player,),
        pulls=pulls,
    )


def test_only_packs_both_routes_fought_are_counted() -> None:
    ours = a_run(OURS, a_pull(0, 60.0, 100, 101), a_pull(1, 40.0, 200))
    theirs = a_run(THEIRS, a_pull(0, 30.0, 100, 101))

    aligned = aligned_trash(ours, theirs)

    assert aligned.our_pulls == frozenset({0})
    assert aligned.our_seconds == 60.0
    assert aligned.their_seconds == 30.0
    assert aligned.pack_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.domain.comparison.trash_spells'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/wowperf/domain/comparison/trash_spells.py`:

```python
# ABOUTME: Compares one player's cast rates on the trash packs two routes shared.
# ABOUTME: Only aligned packs count, so a rate measures play rather than the route.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.model import Run


class AlignedTrash(Frozen):
    """The trash packs two routes shared, and the seconds each side spent on them."""

    our_pulls: frozenset[int] = frozenset()
    their_pulls: frozenset[int] = frozenset()
    our_seconds: float = 0.0
    their_seconds: float = 0.0

    @property
    def pack_count(self) -> int:
        """Our packs that found a counterpart — the denominator a title states."""
        return len(self.our_pulls)


def aligned_trash(ours: Run, theirs: Run) -> AlignedTrash:
    """The packs both groups fought, as pull indices and seconds on each side.

    Indices are collected into sets before any duration is summed, and the
    reason differs on the two sides. `align_pulls` runs a sweep after its main
    pass that pairs each of their unclaimed trash pulls back to the best
    counterpart among ours, with nothing marked taken, so one chain-pulled
    stretch of ours can appear in several matches — summing per match would
    inflate our own denominator and depress our own rate. Their indices cannot
    repeat, because the main pass claims each one and the sweep visits only
    what it left; the set on that side is defensive, not load-bearing.
    """
    alignment = align_pulls(ours, theirs)
    packs = alignment.our_packs
    ours_by_index = {pull.index: pull for pull in ours.pulls}
    theirs_by_index = {pull.index: pull for pull in theirs.pulls}

    our_pulls = {match.ours_index for match in alignment.matched if match.ours_index in packs}
    their_pulls = {
        match.theirs_index for match in alignment.matched if match.ours_index in packs
    }
    return AlignedTrash(
        our_pulls=frozenset(our_pulls),
        their_pulls=frozenset(their_pulls),
        our_seconds=sum(ours_by_index[i].duration_seconds for i in our_pulls),
        their_seconds=sum(
            theirs_by_index[i].duration_seconds for i in their_pulls if i in theirs_by_index
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: PASS.

- [ ] **Step 5: Write the de-duplication test**

This is the defect most likely to ship silently. A fixture must reproduce the sweep-back: one chain-pulled stretch of ours covering two packs they took separately.

```python
def test_one_chain_pull_of_ours_counts_its_seconds_once() -> None:
    """align_pulls sweeps back over their unclaimed pulls and can name the same
    pull of ours twice. Summing per match would count our stretch twice, inflate
    our denominator and depress our own rate — an error that makes the player
    look worse than they were."""
    ours = a_run(OURS, a_pull(0, 90.0, 100, 101, 200, 201))
    theirs = a_run(THEIRS, a_pull(0, 30.0, 100, 101), a_pull(1, 25.0, 200, 201))

    aligned = aligned_trash(ours, theirs)

    # Both of their packs matched our single stretch.
    assert aligned.their_pulls == frozenset({0, 1})
    assert aligned.their_seconds == 55.0
    # Ours is one pull and counts once, however many of theirs it covered.
    assert aligned.our_pulls == frozenset({0})
    assert aligned.our_seconds == 90.0
    assert aligned.pack_count == 1
```

- [ ] **Step 6: Run it, then prove it could fail**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`

If it passes immediately, mutate `aligned_trash` to sum per match instead of per distinct index:

```python
        our_seconds=sum(
            ours_by_index[m.ours_index].duration_seconds
            for m in alignment.matched
            if m.ours_index in packs
        ),
```

Re-run and confirm `test_one_chain_pull_of_ours_counts_its_seconds_once` FAILS with `our_seconds == 180.0`. Restore the correct implementation and confirm PASS. Do not skip this: a one-to-one fixture passes either way.

- [ ] **Step 7: Write the boss-exclusion test**

```python
def test_boss_pulls_are_not_aligned_trash() -> None:
    """Bosses match by encounter id and are the other comparison's subject. Counting
    them here would put the same seconds in two denominators."""
    ours = a_run(OURS, a_pull(0, 60.0, 100, encounter_id=2607), a_pull(1, 40.0, 200))
    theirs = a_run(THEIRS, a_pull(0, 55.0, 100, encounter_id=2607), a_pull(1, 35.0, 200))

    aligned = aligned_trash(ours, theirs)

    assert aligned.our_pulls == frozenset({1})
    assert aligned.our_seconds == 40.0
```

- [ ] **Step 8: Run the full suite, lint and types**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/wowperf/domain/comparison/trash_spells.py tests/domain/comparison/test_trash_spells.py
git commit -F - <<'MSG'
Reduce two routes to the trash packs they shared

A cast rate across trash measures the route unless both sides are restricted
to the packs both groups actually fought. This is that restriction, expressed
as two denominators and the pull indices behind them.

Our own indices are collected into a set before any duration is summed.
align_pulls sweeps back over their unclaimed pulls and pairs each to the best
counterpart among ours with nothing marked taken, so one chain-pulled stretch
of ours can appear in several matches. Summing per match would count that
stretch once per pack it covered, inflate our denominator and depress our own
rate, which reads as the player having done less than they did.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 3: The floor on aligned trash seconds

The design refuses to guess this value. Measure it, then set it with the date and the runs behind it.

**Files:**
- Modify: `src/wowperf/domain/comparison/trash_spells.py`
- Test: `tests/domain/comparison/test_trash_spells.py`

**Interfaces:**
- Produces: `MIN_ALIGNED_TRASH_SECONDS: float` and `def is_comparable(aligned: AlignedTrash) -> bool`.

- [ ] **Step 1: Measure before choosing**

Run the analyser over the cached runs already in `out/` and print, for each parse member of each, the aligned trash seconds on both sides. Write a throwaway script under the scratchpad — not in the repo — that loads each cached run and its parse sample and calls `aligned_trash`. Record the distribution: the smallest denominator that still produced a sane rate, and the largest that clearly did not.

The value must be low enough that an ordinary route keeps most of its references and high enough that two casts over twenty seconds never becomes a rate. Record the date, the runs measured, and the observed spread in the constant's docstring. **Do not proceed to Step 2 until a measured number exists.**

- [ ] **Step 2: Write the failing test**

The test pins the behaviour at the boundary and reads the constant rather than hardcoding it, so the number can be re-measured without rewriting the test:

```python
def test_a_denominator_below_the_floor_is_not_comparable() -> None:
    """A handful of seconds turns two casts into a wild rate. The floor is the only
    guard the rate rows have against a tiny denominator."""
    thin = AlignedTrash(
        our_pulls=frozenset({0}),
        their_pulls=frozenset({0}),
        our_seconds=MIN_ALIGNED_TRASH_SECONDS - 0.1,
        their_seconds=MIN_ALIGNED_TRASH_SECONDS * 10,
    )

    assert not is_comparable(thin)


def test_either_side_below_the_floor_disqualifies_the_pair() -> None:
    """A rate needs both denominators. A reference with almost no aligned trash is
    as useless as our own side having almost none."""
    theirs_thin = AlignedTrash(
        our_pulls=frozenset({0}),
        their_pulls=frozenset({0}),
        our_seconds=MIN_ALIGNED_TRASH_SECONDS * 10,
        their_seconds=MIN_ALIGNED_TRASH_SECONDS - 0.1,
    )

    assert not is_comparable(theirs_thin)


def test_both_sides_at_the_floor_are_comparable() -> None:
    at_floor = AlignedTrash(
        our_pulls=frozenset({0}),
        their_pulls=frozenset({0}),
        our_seconds=MIN_ALIGNED_TRASH_SECONDS,
        their_seconds=MIN_ALIGNED_TRASH_SECONDS,
    )

    assert is_comparable(at_floor)
```

Add `MIN_ALIGNED_TRASH_SECONDS` and `is_comparable` to the test file's imports.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: FAIL at import — `cannot import name 'MIN_ALIGNED_TRASH_SECONDS'`.

- [ ] **Step 4: Write minimal implementation**

In `trash_spells.py`, below the imports. Replace `<VALUE>`, `<DATE>` and the spread with what Step 1 measured:

```python
MIN_ALIGNED_TRASH_SECONDS = <VALUE>
"""Aligned trash seconds a side must reach before its rate is argued from.

Measured <DATE> against the cached runs in `out/`: <record the observed spread
of aligned trash seconds per reference here, and the two runs at its ends>. A
rate over a handful of seconds is arithmetic, not evidence — two casts over
twenty seconds is six a minute and means nothing — and the rate rows have no
other guard against a small denominator.
"""


def is_comparable(aligned: AlignedTrash) -> bool:
    """Whether both sides spent long enough on shared packs to state a rate.

    Both, not either: a rate is a ratio of two denominators and a thin one on
    the reference's side skews it exactly as badly as a thin one on ours.
    """
    return (
        aligned.our_seconds >= MIN_ALIGNED_TRASH_SECONDS
        and aligned.their_seconds >= MIN_ALIGNED_TRASH_SECONDS
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: PASS.

- [ ] **Step 6: Prove the "both sides" test could fail**

Mutate `is_comparable` to use `or` instead of `and`. Re-run and confirm `test_either_side_below_the_floor_disqualifies_the_pair` FAILS. Restore and confirm PASS.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/domain/comparison/trash_spells.py tests/domain/comparison/test_trash_spells.py
git commit -F - <<'MSG'
Set a measured floor under an aligned trash denominator

A rate over a handful of seconds is arithmetic rather than evidence, and the
rate rows have no other guard against a small denominator. The value is
measured against the cached runs rather than guessed, and its docstring
carries the date and the spread it came from so a later reader can judge
whether it still holds.

Both sides must clear it. A rate is a ratio of two denominators, and a thin
one on the reference's side skews it exactly as badly as a thin one on ours.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 4: The rate rows

**Files:**
- Modify: `src/wowperf/domain/comparison/trash_spells.py`
- Test: `tests/domain/comparison/test_trash_spells.py`

**Interfaces:**
- Consumes: `casts_in`, `their_actor_id` (Task 1); `aligned_trash`, `is_comparable` (Tasks 2–3); `MIN_CASTS_TO_COMPARE`, `MIN_MEMBERS_WITH_ABILITY`, `RATE_GAP_MULTIPLE`, `MAX_SPELLS_REPORTED` from `spells.py`; `median`, `observed_range` from `statistics.py`; `ParseSample`, `ParseMember` from `sample.py`.
- Produces: `compare_trash_spells_sample(ours: LoadedRun, our_player: Player, our_name: str, sample: ParseSample) -> list[Finding]` emitting ids `compare.spells.trash.rate.<rank>`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_trash_spells.py`. The fixtures build a sample of five references that each fought the same pack we did:

```python
BLOOD_BOIL = 50842


def a_loaded(player: Player, *pulls: Pull, casts: tuple[CastEvent, ...] = ()) -> LoadedRun:
    return LoadedRun(run=a_run(player, *pulls), casts=casts)


def cast(actor_id: int, ability_id: int, name: str, at_ms: int, pull: int | None) -> CastEvent:
    return CastEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        timestamp_ms=at_ms,
        pull_index=pull,
    )


def a_trash_member(name: str, actor_id: int, blood_boils: int) -> ParseMember:
    """A reference who fought our pack for 60s and pressed Blood Boil that often."""
    player = Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=320
    )
    run = a_run(player, a_pull(0, 60.0, 100, 101))
    casts = tuple(
        cast(actor_id, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(blood_boils)
    )
    return ParseMember(
        row=ParseRow(
            report_code=f"REF{actor_id}",
            fight_id=1,
            keystone_level=16,
            duration_ms=1_909_000,
            character_name=name,
            class_name="DeathKnight",
            spec="Blood",
        ),
        run=run,
        casts=casts,
    )


# Four press Blood Boil 10 times over their 60s pack; the fifth never does.
TRASH_SAMPLE = ParseSample(
    members=(
        a_trash_member("Bríala", 11, 10),
        a_trash_member("Dawnseeker", 12, 10),
        a_trash_member("Emberfall", 13, 10),
        a_trash_member("Frostwhisper", 14, 10),
        a_trash_member("Glimmerose", 15, 0),
    )
)

# Our own run: the same pack, 60s, pressed 4 times — well past the 1.5x bar.
OURS_LOADED = a_loaded(
    OURS,
    a_pull(0, 60.0, 100, 101),
    casts=tuple(cast(693, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(4)),
)

OUR_NAME = "Emberkin (actor 693)"


def test_a_trash_rate_gap_states_its_pack_count_in_the_title() -> None:
    """Permissive alignment means thin rows appear. The denominator rides in the
    title so a row drawn from one pack cannot be quoted as though drawn from eight."""
    findings = compare_trash_spells_sample(OURS_LOADED, OURS, OUR_NAME, TRASH_SAMPLE)

    rate = next(f for f in findings if f.id == "compare.spells.trash.rate.0")
    assert "across 1 aligned pack" in rate.title
    assert "Blood Boil" in rate.title
    assert rate.confidence is Confidence.DERIVED
    assert rate.seconds_lost is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py::test_a_trash_rate_gap_states_its_pack_count_in_the_title -v`
Expected: FAIL — `cannot import name 'compare_trash_spells_sample'`.

- [ ] **Step 3: Write minimal implementation**

Append to `trash_spells.py`:

```python
def compare_trash_spells_sample(
    ours: LoadedRun, our_player: Player, our_name: str, sample: ParseSample
) -> list[Finding]:
    """Cast rates on the trash packs our route shared with the sample's.

    Boss pulls are `compare_spells_sample`'s subject and are excluded here, so
    the two families never price the same seconds twice. No member is named:
    the claim is about the sample as a population, exactly as on the boss rows.
    """
    if not sample.members:
        return []

    ours_aligned: list[AlignedTrash] = []
    per_member: list[tuple[float, dict[int, int]]] = []
    names: dict[int, str] = {}
    for member in sample.members:
        actor_id = their_actor_id(member, member.row.character_name)
        aligned = aligned_trash(ours.run, member.run)
        if actor_id is None or not is_comparable(aligned):
            per_member.append((0.0, {}))
            continue
        ours_aligned.append(aligned)
        their_casts = casts_in(member.casts, actor_id, aligned.their_pulls)
        for ability_id, (name, _count) in their_casts.items():
            names.setdefault(ability_id, name)
        per_member.append(
            (
                aligned.their_seconds,
                {
                    ability_id: count
                    for ability_id, (_name, count) in their_casts.items()
                    if count >= MIN_CASTS_TO_COMPARE
                },
            )
        )

    if not ours_aligned:
        return []

    # Our own denominator is the union of every pack that aligned with anybody:
    # a pack one reference skipped is still a pack we fought and were compared on.
    our_pulls = frozenset().union(*(aligned.our_pulls for aligned in ours_aligned))
    our_seconds = sum(
        pull.duration_seconds for pull in ours.run.pulls if pull.index in our_pulls
    )
    if our_seconds <= 0:
        return []
    ours_on_trash = casts_in(ours.casts, our_player.actor_id, our_pulls)
    return _rate_rows(our_name, ours_on_trash, our_seconds, len(our_pulls), per_member)


def _rate_rows(
    our_name: str,
    ours_on_trash: dict[int, tuple[str, int]],
    our_seconds: float,
    pack_count: int,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> list[Finding]:
    """Abilities both sides cast on shared packs, where the sample's median is higher."""
    gaps = []
    for ability_id, (name, our_count) in ours_on_trash.items():
        rates = [
            qualifying[ability_id] / their_seconds * 60
            for their_seconds, qualifying in per_member
            if ability_id in qualifying and their_seconds > 0
        ]
        if len(rates) < MIN_MEMBERS_WITH_ABILITY:
            continue
        our_rate = our_count / our_seconds * 60
        their_median = median(rates)
        if our_rate <= 0 or their_median / our_rate < RATE_GAP_MULTIPLE:
            continue
        gaps.append((their_median - our_rate, ability_id, name, our_rate, their_median, rates))
    gaps.sort(key=lambda row: row[0], reverse=True)

    findings = []
    for rank, (_, ability_id, name, our_rate, their_median, rates) in enumerate(
        gaps[:MAX_SPELLS_REPORTED]
    ):
        low, high = observed_range(rates)
        findings.append(
            Finding(
                id=f"compare.spells.trash.rate.{rank}",
                title=(
                    f"{len(rates)} top parses cast {name} a median {their_median:.1f} times a "
                    f"minute across {quantity(pack_count, 'aligned pack', 'aligned packs')}; "
                    f"{our_name} casts it {our_rate:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of time spent on trash packs both routes "
                    "fought, matched by the enemy types in them. Restricting to shared packs is "
                    "what separates a rate about play from a rate about the route — but an "
                    "aligned pair is a comparable pair, not an identical one, so pack size still "
                    "varies within it and pull order still moves a rate."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {ability_id}",
                    f"ours over {our_seconds:.0f}s of aligned trash",
                    f"range {low:.1f} to {high:.1f} casts a minute across "
                    f"{len(rates)} top parses",
                ),
                facts=(
                    FindingFact(label="Ours", value=f"{our_rate:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference median",
                                value=f"{their_median:.1f} casts a minute",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Observed range", value=f"{low:.1f} to {high:.1f}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Aligned packs", value=str(pack_count)),
                ),
                ability_id=ability_id,
                ability_name=name,
            )
        )
    return findings
```

Add to the module's imports:

```python
from collections.abc import Sequence

from wowperf.domain.comparison.sample import ParseSample
from wowperf.domain.comparison.spells import (
    MAX_SPELLS_REPORTED,
    MIN_CASTS_TO_COMPARE,
    MIN_MEMBERS_WITH_ABILITY,
    RATE_GAP_MULTIPLE,
    casts_in,
    their_actor_id,
)
from wowperf.domain.comparison.statistics import median, observed_range
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity
from wowperf.domain.model import LoadedRun, Player, Run
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: PASS.

- [ ] **Step 5: Write the boss-exclusion test**

```python
def test_a_boss_only_cast_never_reaches_a_trash_row() -> None:
    """The two families must not price the same seconds twice."""
    ours = a_loaded(
        OURS,
        a_pull(0, 60.0, 100, 101),
        a_pull(1, 60.0, 300, encounter_id=2607),
        casts=tuple(cast(693, 999, "Boss Only", n * 1_000, 1) for n in range(2)),
    )

    findings = compare_trash_spells_sample(ours, OURS, OUR_NAME, TRASH_SAMPLE)

    assert all("Boss Only" not in f.title for f in findings)
```

- [ ] **Step 6: Write the below-floor test**

```python
def test_a_reference_below_the_floor_contributes_no_rate() -> None:
    """A reference whose aligned trash is too thin is not argued from, and its
    absence must not be mistaken for it having cast nothing."""
    thin = ParseSample(members=(a_trash_member("Bríala", 11, 10),))
    tiny_pack = a_loaded(
        OURS,
        a_pull(0, 0.5, 100, 101),
        casts=(cast(693, BLOOD_BOIL, "Blood Boil", 100, 0),),
    )

    findings = compare_trash_spells_sample(tiny_pack, OURS, OUR_NAME, thin)

    assert not any(f.id.startswith("compare.spells.trash.rate") for f in findings)
```

- [ ] **Step 7: Run the full suite, lint and types, then prove the new tests could fail**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

For each test that passed on first writing, mutate the guard it covers and confirm it goes red: drop the `is_comparable` check for the floor test; drop the `aligned.their_pulls` scoping for the boss test.

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/domain/comparison/trash_spells.py tests/domain/comparison/test_trash_spells.py
git commit -F - <<'MSG'
Compare cast rates across the trash packs two routes shared

The parse axis read boss pulls only, which on a real key is about a third of
the dungeon. These rows read the rest of it, restricted to packs both groups
fought so the figure is about play rather than about routing.

The aligned pack count sits in the title rather than the evidence. The
alignment posture chosen for this feature is permissive, so thin rows will
appear, and a rate quoted away from its denominator is the failure mode that
posture has to answer for.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 5: The level row

Without this the feature recreates the ambiguity it was built to remove.

**Files:**
- Modify: `src/wowperf/domain/comparison/trash_spells.py`
- Test: `tests/domain/comparison/test_trash_spells.py`

**Interfaces:**
- Produces: id `compare.spells.trash.level`, unranked, appended after the rate rows.

- [ ] **Step 1: Write the failing test**

```python
def test_an_ability_compared_on_trash_and_level_is_named() -> None:
    """Silence must not mean both "not compared on trash" and "compared and fine"."""
    level = a_loaded(
        OURS,
        a_pull(0, 60.0, 100, 101),
        casts=tuple(cast(693, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(9)),
    )

    findings = compare_trash_spells_sample(level, OURS, OUR_NAME, TRASH_SAMPLE)

    row = next(f for f in findings if f.id == "compare.spells.trash.level")
    assert "Blood Boil" in " ".join(row.evidence)
    assert not any(f.id.startswith("compare.spells.trash.rate") for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py::test_an_ability_compared_on_trash_and_level_is_named -v`
Expected: FAIL with `StopIteration`.

- [ ] **Step 3: Write minimal implementation**

In `_rate_rows`, collect the level abilities and append one row. Replace the gap loop's rejection branch and the return:

```python
        if our_rate <= 0:
            continue
        if their_median / our_rate < RATE_GAP_MULTIPLE:
            level.append(name)
            continue
```

Declare `level: list[str] = []` beside `gaps`, and end the function:

```python
    if level:
        findings.append(_level_row(our_name, level, pack_count))
    return findings


def _level_row(our_name: str, names: Sequence[str], pack_count: int) -> Finding:
    """Abilities compared on the shared packs that produced no gap row."""
    ordered = sorted(set(names))
    return Finding(
        id="compare.spells.trash.level",
        title=(
            f"{quantity(len(ordered), 'ability', 'abilities')} {our_name} cast across "
            f"{quantity(pack_count, 'aligned pack', 'aligned packs')} "
            f"{'was' if len(ordered) == 1 else 'were'} compared and showed no gap"
        ),
        detail=(
            "Enough of the sample cast each of these on packs both routes fought, and our own "
            f"rate was inside the bar the gap rows use: the sample's median has to be "
            f"{RATE_GAP_MULTIPLE} times ours before one is written. Read it as 'no gap wide "
            "enough to report', never as 'the same rate'."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(ordered),
            f"compared against at least {MIN_MEMBERS_WITH_ABILITY} top parses each",
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: PASS.

- [ ] **Step 5: Write the empty-row and singular tests**

```python
def test_no_trash_level_row_when_every_ability_showed_a_gap() -> None:
    findings = compare_trash_spells_sample(OURS_LOADED, OURS, OUR_NAME, TRASH_SAMPLE)

    assert not any(f.id == "compare.spells.trash.level" for f in findings)


def test_a_single_level_ability_on_trash_is_counted_in_the_singular() -> None:
    level = a_loaded(
        OURS,
        a_pull(0, 60.0, 100, 101),
        casts=tuple(cast(693, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(9)),
    )

    findings = compare_trash_spells_sample(level, OURS, OUR_NAME, TRASH_SAMPLE)

    row = next(f for f in findings if f.id == "compare.spells.trash.level")
    assert row.title.startswith("1 ability ")
    assert "1 aligned pack " in row.title
```

- [ ] **Step 6: Run, then prove they could fail**

Mutate the `if level:` guard to `if True:` and confirm the empty-row test goes red. Mutate `quantity` back to an f-string with a bare plural and confirm the singular test goes red. Restore both.

- [ ] **Step 7: Run the full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/trash_spells.py tests/domain/comparison/test_trash_spells.py
git commit -F - <<'MSG'
Name the abilities compared on shared packs that showed no gap

Without this row the new family reproduces the ambiguity it was built to
remove: silence on a trash ability would mean both "never compared" and
"compared and level", and a reader would have no way to tell which.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 6: The unavailable row

**Files:**
- Modify: `src/wowperf/domain/comparison/trash_spells.py`
- Test: `tests/domain/comparison/test_trash_spells.py`

**Interfaces:**
- Produces: id `compare.spells.trash.unavailable`, returned alone when no member cleared the floor.

- [ ] **Step 1: Write the failing test**

```python
def test_no_comparable_reference_says_so_rather_than_going_quiet() -> None:
    """A withheld comparison and a comparison that found nothing must not look alike."""
    no_shared_packs = a_loaded(
        OURS,
        a_pull(0, 60.0, 900, 901),
        casts=(cast(693, BLOOD_BOIL, "Blood Boil", 100, 0),),
    )

    findings = compare_trash_spells_sample(no_shared_packs, OURS, OUR_NAME, TRASH_SAMPLE)

    row = next(f for f in findings if f.id == "compare.spells.trash.unavailable")
    assert OUR_NAME in row.title
    assert row.confidence is Confidence.DERIVED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py::test_no_comparable_reference_says_so_rather_than_going_quiet -v`
Expected: FAIL with `StopIteration` — the current code returns `[]`.

- [ ] **Step 3: Write minimal implementation**

Replace both bare `return []` guards after the member loop in `compare_trash_spells_sample`:

```python
    if not ours_aligned:
        return [_unavailable_row(our_name, len(sample.members))]
```

and, after computing `our_seconds`:

```python
    if our_seconds <= 0:
        return [_unavailable_row(our_name, len(sample.members))]
```

Leave the `if not sample.members: return []` guard alone — `service.compare` already says `compare.parse.unavailable` once for a sample that does not exist, and repeating it here would print the same absence twice.

```python
def _unavailable_row(our_name: str, total: int) -> Finding:
    """No reference shared enough trash with our route to state a rate."""
    return Finding(
        id="compare.spells.trash.unavailable",
        title=f"Trash cast rates could not be compared for {our_name}",
        detail=(
            "A trash comparison needs packs both routes fought, matched by the enemy types in "
            "them, and enough time on them to divide by. No reference in the sample reached "
            "that, so no trash rates are reported rather than rates from packs only one group "
            "fought. Boss-pull rates are unaffected and are reported above."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"{count_phrase(0, total)} references shared enough trash to compare",
            f"a side must reach {MIN_ALIGNED_TRASH_SECONDS:.0f}s of aligned trash",
        ),
    )
```

Add `count_phrase` to the `statistics` import.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -v`
Expected: PASS.

- [ ] **Step 5: Write the no-double-absence test**

```python
def test_an_empty_sample_stays_silent_here() -> None:
    """service.compare already says compare.parse.unavailable once for a sample that
    does not exist. Saying it again in this family prints one absence twice."""
    findings = compare_trash_spells_sample(OURS_LOADED, OURS, OUR_NAME, ParseSample())

    assert findings == []
```

- [ ] **Step 6: Run, prove it could fail, commit**

Mutate the empty-sample guard to return `[_unavailable_row(our_name, 0)]` and confirm the test goes red. Restore.

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/trash_spells.py tests/domain/comparison/test_trash_spells.py
git commit -F - <<'MSG'
Say when no reference shared enough trash to compare

A withheld comparison and a comparison that found nothing read identically
when both produce no rows. This states the first, names the floor it failed,
and says the boss rows above are unaffected.

An empty sample stays silent: service.compare already reports that absence
once, and repeating it here would print one gap twice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 7: Wire it into the comparison and the page

**Files:**
- Modify: `src/wowperf/domain/comparison/service.py:116-125`
- Test: `tests/domain/comparison/test_service.py`, `tests/domain/report/test_build_players.py`

**Interfaces:**
- Consumes: `compare_trash_spells_sample` (Task 4).
- Produces: findings carrying `player_slug`, ids suffixed `.<slug>`, routed to the Players tab by the existing `COMPARISON_PREFIXES` match on `compare.spells.`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_service.py`, following the fixtures already there:

```python
def test_a_trash_row_carries_the_players_slug_like_every_parse_finding() -> None:
    """The parse family is a statement about one player, and the page matches a
    card by the slug. A family that forgot it would render nowhere."""
    findings = compare(OURS, None, [A_SUBJECT])

    trash = [f for f in findings if f.id.startswith("compare.spells.trash.")]
    assert trash, "the trash family produced nothing to check"
    for finding in trash:
        assert finding.player_slug == A_SUBJECT.slug
        assert finding.id.endswith(f".{A_SUBJECT.slug}")
```

Use whichever subject fixture that file already defines; if none produces aligned trash, extend the fixture's run and its parse member with one matching pack rather than inventing a new fixture style.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_service.py -k trash_row -v`
Expected: FAIL on the `assert trash` line — the family is not wired in.

- [ ] **Step 3: Write minimal implementation**

In `src/wowperf/domain/comparison/service.py`, add the call to `_compare_player`'s return list, directly after the boss-pull spells so the two read in order on the page:

```python
    return [
        *compare_spells_sample(ours, subject.player, subject.display_name, parse),
        *compare_trash_spells_sample(ours, subject.player, subject.display_name, parse),
        *compare_talents(
            subject.player,
            subject.display_name,
            find_player(top.run, top.row.character_name),
            top.row,
        ),
        *compare_uptime_sample(ours.run, subject.our_auras, subject.display_name, parse),
    ]
```

Add the import:

```python
from wowperf.domain.comparison.trash_spells import compare_trash_spells_sample
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/domain/comparison/test_service.py -v`
Expected: PASS.

- [ ] **Step 5: Write the tab-routing test**

Add to `tests/domain/report/test_build_players.py`, following that file's existing style for asserting a finding lands under a player's card:

```python
def test_a_trash_spell_row_lands_under_the_players_card() -> None:
    """COMPARISON_PREFIXES matches on "compare.spells.", so the trash family is
    routed by the same rule as the boss rows. Pinned because a family that fell
    through would land in the Summary catch-all without failing anything else."""
    finding = Finding(
        id="compare.spells.trash.rate.0.emberkin-0",
        title="3 top parses cast Blood Boil a median 9.1 times a minute across 4 aligned "
        "packs; Emberkin casts it 6.0",
        detail="",
        confidence=Confidence.DERIVED,
        player_slug="emberkin-0",
    )

    # Build the view model the way this file's other tests do, then assert the
    # finding appears in the player's comparison rows and in no other tab.
```

Complete the body using the helpers already in that file.

- [ ] **Step 6: Run the full gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/domain/comparison/service.py tests/domain/comparison/test_service.py tests/domain/report/test_build_players.py
git commit -F - <<'MSG'
Report trash cast rates beside the boss ones

Wires the new family into the per-player comparison, directly after the
boss-pull rows so the two stretches read in order under one card.

The routing test is pinned rather than assumed: COMPARISON_PREFIXES matches a
prefix, so a family that fell through it would land in the Summary catch-all
and no other test would notice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 8: End to end against a real run

**Files:**
- Modify: `tests/e2e/test_compare_e2e.py`

**Interfaces:**
- Consumes: everything above, through the real fetch path.

- [ ] **Step 1: Write the test**

Follow the conventions already in that file — `@pytest.mark.e2e`, the `WOWPERF_E2E_REPORT` environment variable, `build_repository(tmp_path)`:

```python
@pytest.mark.e2e
def test_a_real_run_compares_trash_packs_against_real_parses(tmp_path: Path) -> None:
    """The offline fixtures cut every pull by hand. Only a real run exercises the
    sweep-back in align_pulls, which is where the denominator defect would live."""
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    # Build the run and its parse sample the way this file's other tests do, then:
    findings = compare(loaded, speed, subjects)

    trash = [f for f in findings if f.id.startswith("compare.spells.trash.")]
    assert trash, "a real run shared no trash with any reference, which needs investigating"

    for finding in trash:
        assert finding.confidence is Confidence.DERIVED
        assert finding.seconds_lost is None

    rates = [f for f in trash if ".rate." in f.id]
    for rate in rates:
        # The pack count in the title is the claim this family's honesty rests on.
        assert "aligned pack" in rate.title
```

- [ ] **Step 2: Run it**

Run: `WOWPERF_E2E_REPORT="<a public M+ report URL>" uv run pytest -m e2e tests/e2e/test_compare_e2e.py -v`

This spends API quota. The budget is 3600 points an hour and a full cold compared analysis cost 83.39 on the one run anyone has measured. Run it once, not in a loop.

Expected: PASS. If `assert trash` fails, do not weaken it — find out whether alignment genuinely found no shared packs on that run, or whether the floor from Task 3 is set too high. Both are findings worth recording.

- [ ] **Step 3: Compare against a real report and read the output**

Run the analyser over a real run and read the new rows:

```bash
uv run wowperf analyze "<report url>" --player <name>
```

Read `out/<code>-<fight>.findings.json`, not the HTML. Check that the aligned pack counts in the titles are plausible against the route, and that no trash row names an ability the boss rows already reported at the same rate — which would suggest the pull scoping leaked.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_compare_e2e.py
git commit -F - <<'MSG'
Exercise the trash comparison against a real run

Every offline fixture cuts its pulls by hand and matches one to one. The
sweep-back in align_pulls, where a chain-pulled stretch of ours picks up
several counterparts, only happens on routes nobody designed for the test --
which is exactly where the denominator defect would live.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Self-Review

**Spec coverage.**

| Spec section | Task |
| --- | --- |
| §1 new family, side by side with bosses | 4, 7 |
| §3 no new fetching | none needed — verified, nothing to build |
| §4 casts per minute of aligned trash time | 2, 4 |
| §5 denominators, de-duplicate our own indices | 2 (steps 5–6) |
| §6 reused thresholds | 4 |
| §6 `MIN_ALIGNED_TRASH_SECONDS`, measured not guessed | 3 |
| §7 `compare.spells.trash.rate`, pack count in the title | 4 |
| §7 `compare.spells.trash.level` | 5 |
| §7 `compare.spells.trash.unavailable` | 6 |
| §7 derived, no `seconds_lost` | 4, 5, 6, 8 |
| §8 confounds declared on the findings | 4 (the `detail` text) |
| §9 permissive posture, denominator in the title | 4 |
| §10 no merge with boss rows | 4 (step 5), 8 (step 3) |
| §11 unit, integration, e2e | 2–6, 7, 8 |
| §12 open question 1 | 3 |
| §12 open questions 2 and 3 | 6, 5 — both resolved the way the design inclined |

**Type consistency.** `aligned_trash` returns `AlignedTrash` in Tasks 2, 3 and 4. `casts_in(casts, actor_id, indices)` takes a `frozenset[int]` in Tasks 1 and 4; `AlignedTrash.our_pulls` and `their_pulls` are `frozenset[int]`, so they pass directly. `per_member` is `list[tuple[float, dict[int, int]]]` in Task 4 and consumed as `Sequence[tuple[float, dict[int, int]]]` by `_rate_rows`, matching `spells._rate_sample`'s existing shape. `quantity(n, singular, plural)` is used in Tasks 4 and 5 with the signature committed in `e08e370`.

**Placeholders.** Task 3 Step 4 carries `<VALUE>` and `<DATE>` deliberately: the design refuses to guess the constant, and Step 1 is the measurement that fills them. Task 7 Step 5 and Task 8 Step 1 leave a test body to complete against helpers in files this plan does not reproduce; both name the file and the helper style to follow. No other step defers work.
