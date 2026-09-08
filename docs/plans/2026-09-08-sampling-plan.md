# Sampled Reference Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-reference comparison with a sample of five speed references and five
parse references, so every comparison finding states how many fast runs agreed with it.

**Architecture:** Two new frozen value objects (`SpeedSample`, `ParseSample`) carry the members and
the pairwise measurements taken against them. Each comparison module keeps its existing pairwise
function unchanged and gains a sample-level function beside it; below the floor of three eligible
members the sample function delegates to the pairwise one and says the sample was too small. The
adapter grows two load profiles so a reference fetches only what its axis reads. Nothing about the
domain's no-I/O rule changes.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, typer, Jinja2, pytest, ruff, mypy, `uv`.

**Spec:** `docs/plans/2026-09-08-sampling-design.md`. Read it before Task 1; every task argues from
it. Its evidence is `docs/plans/2026-09-08-sampling-decision-brief.md` and
`docs/plans/2026-09-08-sampling-quota-measurement.md`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Sample size is five per axis.** `SAMPLE_SIZE = 5`.
- **The floor is three.** `MIN_SAMPLE_FOR_AGGREGATE = 3`. Below three *eligible* members for a
  given finding, no aggregate is computed: delegate to the pairwise function and add one evidence
  line saying the sample was too small.
- **Every aggregate finding's title contains its denominator**, in the form `"4 of 5"`. A test
  enforces this in Task 15.
- **Counts are `MEASURED`; medians are `DERIVED`.** Anything with an `inferred` component stays
  `inferred`.
- **Never render a sample share as a percentage.** "4 of 5", never "80%". This does not apply to
  rates and uptimes measured within a run, which keep their present formatting.
- **Every median states its observed range** in `evidence`.
- **Never average** composition, talent build, pull order, keystone level, or `matched_share`.
- **Nothing identifying persists.** No reference character name, per-run duration or death count
  reaches the findings JSON or the HTML. Report codes, fight ids and URLs do.
- **The domain performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx` or `jinja2`.
- **Every finding carries a confidence badge.** A finding without one is a bug.
- **Never invent a Warcraft Logs field name.** Verified names live in
  `.claude/skills/wcl-api/SKILL.md` with the date they were checked.
- **Style:** ruff line length 100, two `# ABOUTME: ` lines at the top of every file, PEP 695
  type-parameter syntax where a generic is needed, evergreen comments.
- **TDD, always.** Failing test first, watch it fail, minimal implementation, watch it pass.
- **The gate**, from the repository root, with `uv` off PATH in Bash:

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest && uv run ruff check . && uv run mypy
```

- **Commits:** imperative mood, no `feat:`/`fix:` prefix, body explains **why**, ending
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Stage by name, never `git add -A`.
  **Never** `--no-verify`, `--no-hooks`, `--no-pre-commit-hook`.

### A convention this plan uses deliberately

Tests for **new pure functions** below carry their fixtures inline, because every type they need
(`SpeedRow`, `Comparability`, `Alignment`) has a small, fully-specified constructor. Tests that need
a `Run`, a `Pull` or a `LoadedRun` say what the fixture must contain and instruct you to build it
with the helpers already at the top of the test file you are editing. Read that file first. This is
not a placeholder: the assertions are given in full and they are the specification.

---

## File Structure

**Created:**

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/comparison/statistics.py` | Median, observed range, and the "k of n" phrase. Nothing else. |
| `src/wowperf/domain/comparison/sample.py` | `SpeedMember`, `ParseMember`, `SpeedSample`, `ParseSample`, the floor, and the three eligibility subsets. |
| `tests/domain/comparison/test_statistics.py` | — |
| `tests/domain/comparison/test_sample.py` | — |

**Modified:**

| File | Change |
| --- | --- |
| `src/wowperf/domain/findings.py` | `Finding.quantifier`, and `quantifier_for`. |
| `src/wowperf/domain/comparison/alignment.py` | `MIN_ALIGNED_SHARE` moves here from `route.py`. |
| `src/wowperf/domain/comparison/reference.py` | `MAX_LEVEL_GAP` becomes load-bearing. |
| `src/wowperf/domain/comparison/route.py` | `compare_route_sample`; `compare.route.order` removed. |
| `src/wowperf/domain/comparison/tempo.py` | `compare_tempo_sample`. |
| `src/wowperf/domain/comparison/confounds.py` | `declare_confounds_sample`. |
| `src/wowperf/domain/comparison/spells.py` | `compare_spells_sample`. |
| `src/wowperf/domain/comparison/uptime.py` | `compare_uptime_sample`. |
| `src/wowperf/domain/comparison/service.py` | `compare()` takes the two samples. |
| `src/wowperf/adapters/wcl/ranking_repository.py` | `_levels_to_try` derives from `MAX_LEVEL_GAP`. |
| `src/wowperf/adapters/wcl/repository.py` | `load_speed_reference` / `load_parse_reference`. |
| `src/wowperf/domain/ports.py` | The two new loader methods on the port. |
| `src/wowperf/cli.py` | Sample construction, exclusions, candidate records, findings JSON. |
| `src/wowperf/domain/report/model.py` | `ReferenceRecord`; `Provenance` carries a sequence. |
| `src/wowperf/domain/report/build.py` | Timeline gating, alignments passed in, provenance. |
| `src/wowperf/adapters/render/report.html.j2` | Renders the reference list. |
| `.claude/skills/mplus-analysis/SKILL.md` | Containment claim, confounds, quantifier rule. |

---

## Task 1: Make `MAX_LEVEL_GAP` the rule it describes

**Files:**
- Modify: `src/wowperf/adapters/wcl/ranking_repository.py:33-37`
- Test: `tests/adapters/wcl/test_ranking_repository.py`

**Interfaces:**
- Consumes: `MAX_LEVEL_GAP` from `wowperf.domain.comparison.reference`.
- Produces: nothing new. `_levels_to_try` keeps its signature and its present output.

`MAX_LEVEL_GAP = 1` is imported by two tests and by nothing in `src/`. The rule is really the
three-element tuple in `_levels_to_try`. Sampling widens brackets to fill a sample, so this seam is
about to carry weight it does not carry today.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/wcl/test_ranking_repository.py`:

```python
def test_the_levels_tried_come_from_the_gap_constant(monkeypatch):
    monkeypatch.setattr(ranking_repository, "MAX_LEVEL_GAP", 2)

    assert WclRankingRepository._levels_to_try(16) == (16, 15, 17, 14, 18)


def test_one_gap_reproduces_our_level_then_one_either_side():
    assert WclRankingRepository._levels_to_try(16) == (16, 15, 17)
```

Import `ranking_repository` as a module at the top of the file so `monkeypatch.setattr` has
something to patch.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/wcl/test_ranking_repository.py -v
```

Expected: the first test fails — the hardcoded tuple ignores the constant. The second passes.

- [ ] **Step 3: Implement**

```python
    @staticmethod
    def _levels_to_try(keystone_level: int) -> Sequence[int]:
        """Our level first, then outwards a gap at a time, to `MAX_LEVEL_GAP`."""
        levels = [keystone_level]
        for gap in range(1, MAX_LEVEL_GAP + 1):
            levels += [keystone_level - gap, keystone_level + gap]
        return tuple(levels)
```

Import `MAX_LEVEL_GAP` from `wowperf.domain.comparison.reference` at the top of the module.

- [ ] **Step 4: Run the tests**

Both pass. Then run the gate — `fastest_runs` and `top_parses` both walk this tuple and their
tests must be unaffected.

- [ ] **Step 5: Commit**

```bash
git add src/wowperf/adapters/wcl/ranking_repository.py tests/adapters/wcl/test_ranking_repository.py
```

Body: the constant documented a rule it did not enforce, and the sample is about to widen brackets
deliberately rather than by accident.

---

## Task 2: The quantifier word, and the field that carries it

**Files:**
- Modify: `src/wowperf/domain/findings.py`
- Test: `tests/domain/test_findings.py`

**Interfaces:**
- Produces: `Finding.quantifier: str = ""`, and
  `quantifier_for(matching: int, total: int) -> str`.

The narrative may contain no digits, so it cannot echo a title carrying "4 of 5". Tested Python
emits the word instead; the narrative may only use the word the findings file supplied.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from wowperf.domain.findings import Confidence, Finding, quantifier_for


@pytest.mark.parametrize(
    ("matching", "total", "expected"),
    [
        (5, 5, "every"),
        (4, 5, "most"),
        (3, 5, "most"),
        (2, 5, "some"),
        (1, 5, "some"),
        (2, 4, "about half"),
        (3, 4, "most"),
        (0, 5, ""),
        (1, 0, ""),
    ],
)
def test_the_quantifier_reads_the_ratio(matching, total, expected):
    assert quantifier_for(matching, total) == expected


def test_a_finding_carries_no_quantifier_unless_it_is_given_one():
    finding = Finding(
        id="compare.route.skipped.0",
        title="4 of 5 fast runs skipped the pack at pull 7",
        detail="",
        confidence=Confidence.MEASURED,
    )
    assert finding.quantifier == ""
```

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/test_findings.py -v
```

Expected: `ImportError` on `quantifier_for`.

- [ ] **Step 3: Implement**

Add the field to `Finding`, after `evidence`:

```python
    # The word a digit-free narrative may use in place of this finding's count.
    # Empty on any finding that is not an aggregate over a sample.
    quantifier: str = ""
```

and the function:

```python
def quantifier_for(matching: int, total: int) -> str:
    """The word a digit-free narrative may use for `matching of total`.

    The narrative file is refused if it contains a digit, so a count cannot
    reach the reader through it. Computing the word here keeps the reading of
    the ratio in tested Python: the narrative echoes, it does not calculate.
    """
    if total <= 0 or matching <= 0:
        return ""
    if matching == total:
        return "every"
    if matching * 2 > total:
        return "most"
    if matching * 2 == total:
        return "about half"
    return "some"
```

- [ ] **Step 4: Run the tests, then the gate**

The new field is optional, so every existing `Finding` construction and every `model_dump` test
must still pass. If a golden JSON fixture pins the full field set, update it in this task and say
so in the commit body.

- [ ] **Step 5: Commit**

Body: why the word is computed rather than chosen — the digit ban means the count cannot reach the
narrative, and letting the model pick "most" would be it reading a number.

---

## Task 3: Statistics — median, range, and the phrase

**Files:**
- Create: `src/wowperf/domain/comparison/statistics.py`
- Test: `tests/domain/comparison/test_statistics.py`

**Interfaces:**
- Produces: `median(values: Sequence[float]) -> float`,
  `observed_range(values: Sequence[float]) -> tuple[float, float]`,
  `count_phrase(matching: int, total: int) -> str`.

Three functions, no cleverness. `statistics.median` from the standard library would do the first;
it is wrapped here so the empty case has one defined answer and every caller shares it.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from wowperf.domain.comparison.statistics import count_phrase, median, observed_range


def test_the_median_of_an_odd_count_is_the_middle_value():
    assert median([30.0, 10.0, 20.0]) == 20.0


def test_the_median_of_an_even_count_is_the_midpoint_of_the_two_middles():
    assert median([10.0, 20.0, 30.0, 40.0]) == 25.0


def test_an_empty_sample_has_no_median():
    with pytest.raises(ValueError):
        median([])


def test_the_observed_range_is_the_lowest_and_the_highest():
    assert observed_range([30.0, 10.0, 20.0]) == (10.0, 30.0)


def test_the_range_of_one_value_is_that_value_twice():
    assert observed_range([7.0]) == (7.0, 7.0)


def test_the_count_phrase_carries_both_numbers():
    assert count_phrase(4, 5) == "4 of 5"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_statistics.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# ABOUTME: The three statistics a sample of reference runs is allowed to state.
# ABOUTME: Median and range only — a mean would let one disaster run speak for the sample.

import statistics
from collections.abc import Sequence


def median(values: Sequence[float]) -> float:
    """The middle value, or the midpoint of the two middles.

    A median rather than a mean throughout: leaderboard tails are skewed, and
    one six-death disaster must not drag the figure the report compares against.
    """
    if not values:
        raise ValueError("a sample with no members has no median")
    return statistics.median(values)


def observed_range(values: Sequence[float]) -> tuple[float, float]:
    """The lowest and highest value seen.

    Every median the report prints states this beside it: a median of five with
    a 200-second spread and one with a 20-second spread must not read alike.
    """
    if not values:
        raise ValueError("a sample with no members has no range")
    return min(values), max(values)


def count_phrase(matching: int, total: int) -> str:
    """How many of the sample agreed, as the title must state it.

    Never a percentage: at these sample sizes a percentage invents precision
    the sample does not have.
    """
    return f"{matching} of {total}"
```

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

---

## Task 4: The sample types and their eligibility subsets

**Files:**
- Create: `src/wowperf/domain/comparison/sample.py`
- Modify: `src/wowperf/domain/comparison/alignment.py` (receives `MIN_ALIGNED_SHARE`),
  `src/wowperf/domain/comparison/route.py` (imports it from its new home)
- Test: `tests/domain/comparison/test_sample.py`

**Interfaces:**
- Consumes: `Comparability`, `SpeedRow`, `ParseRow` from `comparison/reference.py`; `Alignment` and
  `MIN_ALIGNED_SHARE` from `comparison/alignment.py`; `Run`, `Death`, `EnemyCastRow`,
  `InterruptEvent`, `CastEvent` from `domain/model.py` and `domain/events.py`; `PlayerAuras`.
- Produces: `SAMPLE_SIZE`, `MIN_SAMPLE_FOR_AGGREGATE`, `SpeedMember`, `ParseMember`, `SpeedSample`,
  `ParseSample`.

**Why the members carry streams rather than a `LoadedRun`:** a skipped stream comes back as an
empty tuple, which reads exactly like "this run had none". With two load profiles that hazard
doubles. A member that simply does not have a field for the stream its axis never fetches makes
reading it a mypy error rather than a silent `measured` claim about absence.

`MIN_ALIGNED_SHARE` moves from `route.py` to `alignment.py` because both `route.py` and the new
`sample.py` need it, and importing `route` from `sample` would be a cycle once Task 6 lands. Its
docstring moves with it unchanged.

- [ ] **Step 1: Write the failing test**

```python
from wowperf.domain.comparison.alignment import Alignment, PullMatch
from wowperf.domain.comparison.reference import Comparability, SpeedRow
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    SpeedMember,
    SpeedSample,
)
from wowperf.domain.model import Run


def _member(their_level: int, matched_share_numerator: int) -> SpeedMember:
    """A speed member at `their_level` whose alignment matched N of 10 trash pulls."""
    return SpeedMember(
        row=SpeedRow(
            report_code="aBcD1234", fight_id=1, keystone_level=their_level,
            duration_ms=1_380_000, deaths=0,
        ),
        run=Run(report_code="aBcD1234", fight_id=1, keystone_level=their_level),
        comparability=Comparability(our_level=16, their_level=their_level),
        alignment=Alignment(
            matched=tuple(
                PullMatch(ours_index=i, theirs_index=i)
                for i in range(matched_share_numerator)
            ),
            our_trash_count=10,
        ),
    )


def test_only_members_at_our_keystone_level_are_duration_eligible():
    sample = SpeedSample(members=(_member(16, 10), _member(15, 10), _member(16, 10)))

    assert len(sample.duration_eligible) == 2


def test_a_member_below_the_alignment_threshold_is_not_route_eligible():
    sample = SpeedSample(members=(_member(16, 9), _member(16, 4)))

    assert len(sample.route_eligible) == 1


def test_a_member_that_aligned_badly_still_counts_for_everything_else():
    sample = SpeedSample(members=(_member(16, 9), _member(16, 4)))

    assert len(sample.duration_eligible) == 2


def test_below_the_floor_a_subset_cannot_be_aggregated():
    sample = SpeedSample(members=tuple(_member(16, 10) for _ in range(2)))

    assert not sample.can_aggregate(sample.duration_eligible)


def test_at_the_floor_a_subset_can_be_aggregated():
    sample = SpeedSample(
        members=tuple(_member(16, 10) for _ in range(MIN_SAMPLE_FOR_AGGREGATE))
    )

    assert sample.can_aggregate(sample.duration_eligible)
```

`Run` above is constructed with only the fields this assertion needs; if `Run` requires more,
use the smallest construction the other tests in `tests/domain/comparison/` already use.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_sample.py -v
```

Expected: `ModuleNotFoundError` on `comparison.sample`.

- [ ] **Step 3: Implement**

First move the constant. Cut `MIN_ALIGNED_SHARE` and its docstring out of `route.py` and paste
them into `alignment.py` directly beneath the `Alignment` class, then in `route.py` replace the
definition with `from wowperf.domain.comparison.alignment import Alignment, MIN_ALIGNED_SHARE`.

Then the new module:

```python
# ABOUTME: The reference runs one comparison may draw on, and which of them each finding may use.
# ABOUTME: Members carry only the streams their axis reads, so absence cannot be read as fact.

from collections.abc import Sequence

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.alignment import MIN_ALIGNED_SHARE, Alignment
from wowperf.domain.comparison.reference import Comparability, ParseRow, SpeedRow
from wowperf.domain.events import CastEvent, EnemyCastRow, InterruptEvent
from wowperf.domain.model import Death, Run

SAMPLE_SIZE = 5
"""How many references to draw per axis.

The smallest sample at which one unusual reference cannot carry a finding
alone, and at which two candidates may fail to load and still leave enough to
aggregate.
"""

MIN_SAMPLE_FOR_AGGREGATE = 3
"""Below this many eligible members, state one reference rather than a statistic.

A median of two is a mean of two, and "1 of 2" is noise dressed as a statistic.
"""


class SpeedMember(Frozen):
    """One speed reference, with only the streams the speed comparisons read.

    There is deliberately no `casts` field: a speed reference never fetches
    that stream, and a field holding an empty tuple would read as "this run
    cast nothing".
    """

    row: SpeedRow
    run: Run
    comparability: Comparability
    alignment: Alignment
    deaths: tuple[Death, ...] = ()
    enemy_cast_rows: tuple[EnemyCastRow, ...] = ()
    interrupts: tuple[InterruptEvent, ...] = ()


class ParseMember(Frozen):
    """One parse reference, with only the streams the parse comparisons read.

    Absent auras are a real state, not a failure: `compare.uptime.unavailable`
    reports it.
    """

    row: ParseRow
    run: Run
    comparability: Comparability
    casts: tuple[CastEvent, ...] = ()
    auras: PlayerAuras | None = None


class _Sample(Frozen):
    """What every sample can answer about its own size."""

    def can_aggregate(self, subset: Sequence[object]) -> bool:
        """Whether a subset is large enough to state as a statistic."""
        return len(subset) >= MIN_SAMPLE_FOR_AGGREGATE


class SpeedSample(_Sample):
    """The speed references this comparison may draw on."""

    members: tuple[SpeedMember, ...] = ()

    @property
    def duration_eligible(self) -> tuple[SpeedMember, ...]:
        """Members whose keystone level equals ours, so a duration means the same thing."""
        return tuple(
            member for member in self.members if member.comparability.durations_comparable
        )

    @property
    def route_eligible(self) -> tuple[SpeedMember, ...]:
        """Members whose route lined up well enough to price a pack as skipped.

        A member below the threshold contributes nothing here and still
        contributes to downtime, deaths and interrupts: the two logs cutting
        the route into pulls differently says nothing about either.
        """
        return tuple(
            member
            for member in self.members
            if member.alignment.matched_share >= MIN_ALIGNED_SHARE
        )


class ParseSample(_Sample):
    """The parse references this comparison may draw on."""

    members: tuple[ParseMember, ...] = ()

    @property
    def aura_eligible(self) -> tuple[ParseMember, ...]:
        return tuple(member for member in self.members if member.auras is not None)

    @property
    def top(self) -> ParseMember | None:
        """The highest-ranked member, which the talent row names.

        A talent build has no mean and no mode this project can compute, so
        that row stays one player's build.
        """
        return self.members[0] if self.members else None
```

- [ ] **Step 4: Run the tests, then the gate**

The constant move touches `route.py` and any test importing `MIN_ALIGNED_SHARE` from it. Update
those imports; do not re-export it from `route.py`, which would leave two homes for one rule.

- [ ] **Step 5: Commit**

Two commits, in this order: one moving `MIN_ALIGNED_SHARE` (a pure move, so the body says why the
new home is right), then one adding `sample.py`.

---

## Task 5: `compare()` takes the two samples

**Files:**
- Modify: `src/wowperf/domain/comparison/service.py`, `src/wowperf/cli.py`
- Test: `tests/domain/comparison/test_service.py`

**Interfaces:**
- Consumes: `SpeedSample`, `ParseSample`, `SpeedMember`, `ParseMember` from Task 4.
- Produces: `compare(ours, our_player, speed: SpeedSample | None, parse: ParseSample | None,
  our_auras) -> list[Finding]`.

This task changes the signature and nothing else. Inside, `compare` still calls today's pairwise
functions, against `speed.members[0]` and `parse.members[0]`. With a one-member sample the output
is byte-identical to today's, which is exactly what the existing service tests assert. Tasks 6 to
10 then convert one module at a time behind a stable signature.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_service.py`, alongside the existing tests:

```python
def test_an_empty_speed_sample_reports_the_speed_comparison_unavailable():
    findings = compare(
        ours=OURS, our_player=SUBJECT, speed=SpeedSample(), parse=None, our_auras=None
    )

    assert any(finding.id == "compare.speed.unavailable" for finding in findings)


def test_a_one_member_sample_compares_against_that_member():
    findings = compare(
        ours=OURS,
        our_player=SUBJECT,
        speed=SpeedSample(members=(SPEED_MEMBER,)),
        parse=None,
        our_auras=None,
    )

    assert any(finding.id == "compare.route.summary" for finding in findings)
    assert not any(finding.id == "compare.speed.unavailable" for finding in findings)
```

`OURS`, `SUBJECT` and the member fixture: build `SPEED_MEMBER` from whatever reference fixture this
file already uses for `SpeedReference`, plus `Comparability(our_level=…, their_level=…)` and
`align_pulls(OURS.run, theirs_run)`.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_service.py -v
```

Expected: `TypeError` — `compare()` does not accept a sample.

- [ ] **Step 3: Implement**

In `service.py`, change the signature and treat an empty sample exactly as today's `None`:

```python
def compare(
    ours: LoadedRun,
    our_player: Player,
    speed: SpeedSample | None,
    parse: ParseSample | None,
    our_auras: PlayerAuras | None = None,
) -> list[Finding]:
    """Every comparison, one ranked list.

    An empty sample and no sample at all mean the same thing to a reader: the
    leaderboard offered nothing to compare against.
    """
    findings: list[Finding] = []
    speed_members = speed.members if speed else ()
    parse_members = parse.members if parse else ()

    if not speed_members:
        findings.append(_unavailable("compare.speed.unavailable", ...))
    else:
        first = speed_members[0]
        findings += compare_route(ours.run, first.run, first.alignment, forces_by_pull(...))
        findings += compare_tempo(ours, first, first.comparability)
        findings += declare_confounds(ours, first, first.comparability)
    ...
```

`compare_tempo` and `declare_confounds` currently take a `LoadedRun` for `theirs` and read
`theirs.run`, `theirs.deaths`, `theirs.enemy_cast_rows` and `theirs.interrupts`. A `SpeedMember`
carries all four under the same names, so their bodies do not change — only their type annotations,
from `LoadedRun` to `SpeedMember`. Do the same for `compare_spells` (`theirs.run`, `theirs.casts`
→ `ParseMember`) and `compare_uptime` (already takes a `Run` and a `PlayerAuras`).

In `cli.py`, wrap what `_references` returns into one-member samples at the `compare(...)` call so
the command still runs. Task 12 replaces that wrapping with real sample construction.

- [ ] **Step 4: Run the full suite**

Every existing comparison test must still pass unchanged. If one fails on content rather than on
types, stop: the pairwise path has changed behaviour and it must not.

- [ ] **Step 5: Commit**

Body: the signature moves first so the five modules can be converted one at a time behind it.

---

## Task 6: `compare_route` over the sample

**Files:**
- Modify: `src/wowperf/domain/comparison/route.py`, `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_route.py`

**Interfaces:**
- Consumes: `SpeedSample`, `count_phrase`, `quantifier_for`.
- Produces: `compare_route_sample(ours: Run, sample: SpeedSample, forces: Mapping[int, int])
  -> list[Finding]`.

Three changes, in one task because they share a function:

1. **`compare.route.skipped.*` becomes a count.** A pack is keyed by *our* pull index, so counting
   how many route-eligible members left it unmatched is a set membership test per member. The
   price does not move: `seconds_lost` is our own pull's duration.
2. **`compare.route.order` is deleted**, with its block and its tests.
3. **`compare.route.extra.*` stays pairwise** against the first route-eligible member, named in
   the finding's detail. `align_pulls` matches by containment rather than signature equality
   (documented 2026-09-06), so grouping their packs across members needs a clustering rule, not a
   dict key. That is out of scope; the spec says so.

- [ ] **Step 1: Write the failing test**

```python
def test_a_pack_every_reference_skipped_is_counted_in_the_title():
    sample = SpeedSample(members=(member_missing_pull_7(), member_missing_pull_7()))
    # plus a third, so the sample clears the floor
    ...
    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.title == "3 of 3 fast runs skipped the pack at pull 7"
    assert skipped.quantifier == "every"
    assert skipped.confidence is Confidence.MEASURED


def test_the_price_of_a_skipped_pack_is_our_own_pull_duration():
    ...
    assert skipped.seconds_lost == 42.0


def test_a_pack_only_some_references_skipped_says_so():
    # two of three route-eligible members skipped pull 7
    assert skipped.title == "2 of 3 fast runs skipped the pack at pull 7"
    assert skipped.quantifier == "some"


def test_below_the_floor_the_pairwise_wording_is_used():
    sample = SpeedSample(members=(member_missing_pull_7(),))

    findings = compare_route_sample(OUR_RUN, sample, forces={})

    skipped = next(f for f in findings if f.id == "compare.route.skipped.0")
    assert skipped.title == "The reference skipped the pack at pull 7"
    assert "too few comparable references to aggregate" in skipped.evidence


def test_no_finding_reports_a_different_pull_order():
    findings = compare_route_sample(OUR_RUN, SAMPLE_WITH_REORDERED_PACKS, forces={})

    assert not any(f.id == "compare.route.order" for f in findings)
```

Build `OUR_RUN` and the members with the helpers already at the top of `test_route.py`. Delete the
existing `compare.route.order` tests in this step, and say why in the commit body.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/comparison/test_route.py -v
```

- [ ] **Step 3: Implement**

Delete the `drifted` block at the end of `compare_route` and the `MAX_PACKS_REPORTED` slice that
feeds it. Then add:

```python
def compare_route_sample(
    ours: Run, sample: SpeedSample, forces: Mapping[int, int]
) -> list[Finding]:
    """What the sample's routes did differently from ours, priced on our own clock.

    Only route-eligible members are counted: a member whose pulls did not line
    up with ours cannot say whether a pack was skipped or merely cut
    differently, and counting it would put the largest wrong number on the page.
    """
    eligible = sample.route_eligible
    if not sample.can_aggregate(eligible):
        first = eligible[0] if eligible else sample.members[0]
        return _too_few(compare_route(ours, first.run, first.alignment, forces), len(eligible))

    total = len(eligible)
    findings = [_summary(ours, eligible), *_skipped(ours, eligible, forces)]
    findings += _extra_from(eligible[0], ours)
    return findings
```

with `_skipped` counting members that left our pull unmatched:

```python
def _skipped(
    ours: Run, eligible: Sequence[SpeedMember], forces: Mapping[int, int]
) -> list[Finding]:
    counts: Counter[int] = Counter()
    for member in eligible:
        counts.update(index for index in member.alignment.only_ours)

    skippable = [
        (pull, counts[pull.index])
        for index, count in counts.items()
        if (pull := _pull_by_index(ours, index)) is not None and not pull.is_boss
    ]
    skippable.sort(key=lambda row: (row[1], row[0].duration_seconds), reverse=True)

    total = len(eligible)
    findings = []
    for rank, (pull, matching) in enumerate(skippable[:MAX_PACKS_REPORTED]):
        findings.append(
            Finding(
                id=f"compare.route.skipped.{rank}",
                title=(
                    f"{count_phrase(matching, total)} fast runs skipped the pack "
                    f"at pull {pull.index}"
                ),
                detail=(
                    f"We spent {pull.duration_seconds:.0f}s on it. It awarded "
                    f"{forces.get(pull.index, 0)} enemy forces. The seconds are our own: a "
                    "reference's clock never prices one of our packs."
                ),
                confidence=Confidence.MEASURED,
                seconds_lost=pull.duration_seconds,
                evidence=(
                    pull.name,
                    f"{forces.get(pull.index, 0)} enemy forces",
                    f"{total - matching} of {total} pulled it too",
                ),
                quantifier=quantifier_for(matching, total),
                pull_index=pull.index,
            )
        )
    return findings
```

and `_too_few` appending one evidence line to each finding:

```python
def _too_few(findings: list[Finding], eligible: int) -> list[Finding]:
    """Say plainly that a statistic was not computed, rather than computing a bad one."""
    note = (
        f"only {eligible} comparable reference{'s' if eligible != 1 else ''}; "
        "too few comparable references to aggregate"
    )
    return [
        finding.model_copy(update={"evidence": (*finding.evidence, note)})
        for finding in findings
    ]
```

`_too_few` is used by every module below. Put it in `sample.py` and import it, rather than writing
it five times.

`_summary` states our pull count against the sample's observed range:

```python
        title=(
            f"We pulled {len(ours.pulls)} packs; the {total} fast runs pulled "
            f"{low:.0f} to {high:.0f}"
        ),
```

- [ ] **Step 4: Run the tests, then the gate**

`service.py` switches its route call to `compare_route_sample`, so its tests move with it.

- [ ] **Step 5: Commit**

Body: why route-order is gone (six pairwise diffs is not an aggregate a reader can use, and the
only real aggregate is a different claim), and why extra packs stay pairwise (containment matching).

---

## Task 7: `compare_tempo` over the sample

**Files:**
- Modify: `src/wowperf/domain/comparison/tempo.py`, `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_tempo.py`

**Interfaces:**
- Produces: `compare_tempo_sample(ours: LoadedRun, sample: SpeedSample) -> list[Finding]`.

Four findings. Downtime, deaths and interrupts take every member; duration takes only the
duration-eligible ones.

- [ ] **Step 1: Write the failing test**

```python
def test_downtime_is_stated_against_the_median_with_its_range():
    findings = compare_tempo_sample(OURS, SAMPLE_OF_THREE)

    downtime = next(f for f in findings if f.id == "compare.downtime")
    assert downtime.title == "We spent 180s between packs; the median of 3 fast runs is 120s"
    assert "range 100s to 150s" in downtime.evidence
    assert downtime.confidence is Confidence.DERIVED
    assert downtime.seconds_lost == 60.0


def test_beating_the_median_is_not_a_loss():
    assert next(f for f in findings if f.id == "compare.downtime").seconds_lost is None


def test_completion_time_uses_only_the_members_at_our_keystone_level():
    # three members, one of them a +15 against our +16
    duration = next(f for f in findings if f.id == "compare.duration")
    assert "median of 2" in duration.title


def test_completion_time_is_withheld_when_no_member_shares_our_level():
    duration = next(f for f in findings if f.id == "compare.duration")
    assert duration.title == "Completion times are not compared"
    assert "3 of 3 references were at a different keystone level" in duration.evidence


def test_the_kick_share_is_a_median_of_per_run_shares_not_a_pooled_ratio():
    # members kicking 1 of 2 and 8 of 10: the median share is 0.5, not 9/12
    interrupts = next(f for f in findings if f.id == "compare.interrupts")
    assert "median 50%" in interrupts.title
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

Keep `_downtime_seconds` and `_kick_counts` exactly as they are; they now take a `SpeedMember`.
Add the sample function, and note the two rules it encodes:

```python
def compare_tempo_sample(ours: LoadedRun, sample: SpeedSample) -> list[Finding]:
    """The group-axis comparisons that are not about the route, against a sample.

    Kick shares are the median of each run's own share, never the pooled ratio:
    pooling weights by run length, so a long reference would dominate a figure
    that is supposed to describe a group's discipline. One reference, one
    observation.
    """
```

`compare.duration` when duration-eligible members clear the floor:

```python
                title=(
                    f"We finished in {our_time:.0f}s; the median of {total} fast runs "
                    f"is {their_median:.0f}s"
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=behind if behind > 0 else None,
```

and when they do not, today's withheld finding with a generalised reason: how many of the sample
were at a different keystone level, in place of `Comparability.withheld_because()`'s single "+N".
Add that sentence as a module-level constant so the confounds task can quote the same words.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

Body: why the median and not the minimum — the minimum is the old single-best-run behaviour with
extra steps, and it maximises the number on the page.

---

## Task 8: `declare_confounds` over the sample

**Files:**
- Modify: `src/wowperf/domain/comparison/confounds.py`, `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_confounds.py`

**Interfaces:**
- Produces: `declare_confounds_sample(ours: LoadedRun, sample: SpeedSample) -> list[Finding]`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_spec_every_fast_run_brought_and_we_did_not_is_counted():
    confounds = declare_confounds_sample(OURS, SAMPLE_OF_FIVE_WITH_AUGMENTATION)

    composition = next(f for f in confounds if f.id == "compare.confound.composition")
    assert composition.title == "4 of 5 fast runs brought an Evoker Augmentation; your group did not"
    assert composition.quantifier == "most"
    assert composition.seconds_lost is None


def test_the_composition_finding_gives_no_advice():
    detail = composition.detail
    assert "bring" not in detail.lower()
    assert "recruit" not in detail.lower()


def test_item_level_is_compared_against_the_median_of_the_group_means():
    item_level = next(f for f in confounds if f.id == "compare.confound.item_level")
    assert "the 5 fast runs average 632 item level" in item_level.title


def test_the_keystone_confound_counts_the_members_at_a_different_level():
    keystone = next(f for f in confounds if f.id == "compare.confound.keystone_level")
    assert keystone.title == "2 of 5 fast runs were at a different keystone level"
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

Composition: count, per `"Class Spec"` string, how many member rosters contain it and ours does
not. Title names the highest count; `evidence` lists every absent spec with its count, and the
specs only we brought. When no spec is absent from ours, fall back to today's title unchanged.
The detail keeps §6.6's posture verbatim — it states, it does not correct — and the test above
pins that no imperative reaches the page.

`compare.confound.augmentation` keeps today's title and detail: the claim is about attribution
being unreliable, which one Augmentation Evoker anywhere is enough to establish. Add an evidence
line counting how many member rosters contained one.

`compare.confound.affixes`: `f"{count_phrase(k, total)} fast runs ran your affix set"`, emitted
only when `k < total`.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

Body: the composition confound is now specific enough to act on, and deliberately stops short of
saying what to do — §6.6 declares confounds rather than correcting for them.

---

## Task 9: `compare_spells` over the sample

**Files:**
- Modify: `src/wowperf/domain/comparison/spells.py`, `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_spells.py`

**Interfaces:**
- Produces: `compare_spells_sample(ours: LoadedRun, our_player: Player, sample: ParseSample)
  -> list[Finding]`.

`compare_talents` is **unchanged** and keeps taking one player. `service.py` calls it with
`sample.top`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_spell_most_top_parses_cast_and_we_never_did_is_counted():
    findings = compare_spells_sample(OURS, SUBJECT, SAMPLE_OF_FIVE)

    missing = next(f for f in findings if f.id == "compare.spells.missing.0")
    assert missing.title == "4 of 5 top parses cast Shifting Power on bosses; Emberkin never did"
    assert missing.quantifier == "most"
    assert missing.confidence is Confidence.MEASURED


def test_no_reference_player_is_named_in_a_sampled_spell_finding():
    for finding in findings:
        assert "Bríala" not in finding.title
        assert all("Bríala" not in line for line in finding.evidence)


def test_an_ability_seen_in_too_few_members_is_not_reported():
    # cast by 2 of 5, below MIN_MEMBERS_WITH_ABILITY
    assert not any("Rune of Power" in f.title for f in findings)


def test_the_rate_finding_uses_the_median_of_per_run_rates():
    rate = next(f for f in findings if f.id == "compare.spells.rate.0")
    assert "median of 4 top parses casts" in rate.title
    assert rate.confidence is Confidence.DERIVED
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

Reuse `boss_casts` and `boss_seconds` unchanged, once per member. Replace `MIN_CASTS_TO_COMPARE`'s
role for the sample path with a sample-shaped threshold, keeping the per-run one:

```python
MIN_MEMBERS_WITH_ABILITY = 3
"""An ability seen in fewer members than this is one player's build, not a pattern.

The per-run `MIN_CASTS_TO_COMPARE` still applies to each member, so a single
stray cast cannot make a member count towards this threshold either.
"""
```

`missing` counts members whose boss casts contain an ability our player never cast anywhere; the
title carries the count, and no member is named. `rate` takes the median of the per-run casts per
minute over the members that cast it at least `MIN_CASTS_TO_COMPARE` times, and compares it to ours
by the existing `RATE_GAP_MULTIPLE`.

Below the floor, delegate to `compare_spells` against `sample.top` and add the `_too_few` note.
That path still names the reference player in its title, which is the pairwise wording; that is
the one place a name persists, and Task 12 records it in the findings JSON as a URL only.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

---

## Task 10: `compare_uptime` over the sample

**Files:**
- Modify: `src/wowperf/domain/comparison/uptime.py`, `src/wowperf/domain/comparison/service.py`
- Test: `tests/domain/comparison/test_uptime.py`

**Interfaces:**
- Produces: `compare_uptime_sample(ours: Run, our_auras: PlayerAuras | None, our_player: Player,
  sample: ParseSample) -> list[Finding]`.

The sample removes this finding's worst caveat and the detail text must stop claiming it. `onSelf`
carries no source filter, so it returns teammate buffs, consumables and gear procs; a one-off proc
cannot reach three of five, so the sample filters exactly the noise the caveat was written for.

- [ ] **Step 1: Write the failing test**

```python
def test_uptime_is_the_median_of_the_members_that_had_aura_data():
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_OF_FIVE)

    gap = next(f for f in findings if f.id == "compare.uptime.self.0")
    assert "median of 4 top parses" in gap.title


def test_members_without_aura_data_are_reported_not_silently_dropped():
    assert "1 of 5 references had no aura data" in gap.evidence


def test_the_detail_no_longer_blames_a_single_players_gear():
    assert "gear this player does not own" not in gap.detail


def test_no_aura_data_at_all_still_reports_unavailable():
    findings = compare_uptime_sample(OUR_RUN, OUR_AURAS, SUBJECT, SAMPLE_WITHOUT_AURAS)

    assert findings[0].id == "compare.uptime.unavailable"
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

`_fractions` and `boss_windows` are unchanged. Compute a fraction per aura-eligible member, take
the median over the members that carried the aura at all, and keep `MIN_UPTIME_FRACTION` and
`UPTIME_GAP_FRACTION` as they are. Rewrite the detail's last sentence: the gap is now stated over
several parses, so a single player's missing trinket no longer explains it — say that, and keep the
sentence about the aura table not being scoped to one caster, which is still true.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

Body: the sample removes the caveat rather than restating it, and a detail that keeps a caveat it
no longer needs teaches the reader to discount the finding.

---

## Task 11: Two load profiles

**Files:**
- Modify: `src/wowperf/adapters/wcl/repository.py`, `src/wowperf/domain/ports.py`
- Test: `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Produces: `load_speed_reference(report_code, fight_id) -> LoadedRun` and
  `load_parse_reference(report_code, fight_id) -> LoadedRun`, replacing `load_reference`.

`_load(..., *, full: bool)` becomes `_load(..., *, profile: …)`. **Do not guess the query set.**
Before writing the test, grep what each axis reads:

```bash
grep -rn "member\.\|theirs\." src/wowperf/domain/comparison/ | grep -v "^.*#"
```

A speed member's comparisons read `run`, `deaths`, `enemy_cast_rows` and `interrupts`. A parse
member's read `run` and `casts`. Then confirm which queries each of those requires by reading
`_load` — in particular whether the abilities table is needed to name a cast, and whether
`build_run` can be called without the talents query. Record what you find in the commit body.

- [ ] **Step 1: Write the failing test**

```python
def test_a_speed_reference_never_fetches_the_cast_stream():
    client = RecordingClient(...)
    repository = WclRunRepository(client, cache)

    repository.load_speed_reference("aBcD1234", 1)

    assert "Casts" not in client.queries_issued


def test_a_parse_reference_never_fetches_the_interrupt_stream():
    repository.load_parse_reference("aBcD1234", 1)

    assert "Interrupts" not in client.queries_issued
    assert "EnemyCasts" not in client.queries_issued


def test_a_speed_reference_fetches_what_tempo_reads():
    repository.load_speed_reference("aBcD1234", 1)

    assert {"Deaths", "EnemyCasts", "Interrupts"} <= client.queries_issued
```

`RecordingClient` records the query name of every `execute` call. If this test file already has a
fake client, extend it rather than adding a second one.

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

Split `_load`'s early return into two, one per profile, each returning a `LoadedRun` carrying only
its own streams. Keep and extend `load_reference`'s docstring warning: the fields left behind are
empty tuples, which read the same as "this run had none", and Task 4's member types exist so that
no comparison can reach them.

Update the `RunRepository` port. `load` for our own run is unchanged.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

Body: the measured figures — a speed member at about 6 points and 0.30 MB against 14.5 and 4.80 —
and that the trim, not N, is where the cost of this feature lives.

---

## Task 12: Build the samples

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py` (or wherever `_references` is covered today — find it with
  `grep -rn "_references" tests/`)

**Interfaces:**
- Consumes: `SAMPLE_SIZE`, `SpeedMember`, `ParseMember`, the two loaders.
- Produces: `_samples(...) -> tuple[SpeedSample, ParseSample, tuple[ReferenceRecord, ...]]`.

`_references` becomes `_samples`. Four changes:

1. Take `SAMPLE_SIZE` rows that load, not the first one.
2. Exclude our own report-and-fight **and any candidate whose roster contains one of our
   characters by name**. At N=1 drawing the analysed player's own other run was negligible; at N=5
   it is not, and "the fast runs did this" is a small lie if one of them is you.
3. Record every candidate considered — code, fight, level, URL, loaded or the reason it did not,
   and whether the response came from cache. The bare `except: continue` stops being silent.

   **`DiskCache` cannot report a hit today**, so this sub-deliverable starts there. `get_or_fetch`
   returns only the payload; add a way for the caller to learn whether the fetch happened — a
   second return value, or a `last_was_hit` the repository reads immediately after. Prefer the
   explicit return: a flag on the adapter is state, and two concurrent loads would race it. Test
   it in `tests/adapters/cache/test_disk.py` before using it here. Without this the cache-reuse
   disclosure the spec's §2 promises has nothing to report, and the field would silently always
   read `false`.
4. Build the pairwise measurements once: `Comparability` and `align_pulls` per speed member.
   `build_timeline` must not compute a second alignment (Task 13).

- [ ] **Step 1: Write the failing test**

```python
def test_the_sample_stops_at_the_configured_size():
    speed, _, _ = _samples(rankings_with_ten_rows, runs, OUR_RUN, SUBJECT)

    assert len(speed.members) == SAMPLE_SIZE


def test_our_own_run_is_never_a_member():
    assert all(m.row.report_code != OUR_RUN.report_code for m in speed.members)


def test_a_candidate_whose_roster_holds_one_of_our_characters_is_skipped():
    # the second leaderboard row's roster contains SUBJECT.name
    assert all(m.row.report_code != "sameplayer" for m in speed.members)


def test_a_candidate_that_failed_to_load_is_recorded_with_its_reason():
    records = _samples(rankings, runs_where_row_two_raises, OUR_RUN, SUBJECT)[2]

    failed = next(r for r in records if not r.loaded)
    assert failed.reason


def test_a_short_leaderboard_yields_a_short_sample_rather_than_an_error():
    speed, _, _ = _samples(rankings_with_two_rows, runs, OUR_RUN, SUBJECT)

    assert len(speed.members) == 2
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

The character exclusion needs the roster, which arrives only with the run — so it is applied
*after* the load, and a rejected candidate is recorded with that reason. Note that in a comment:
it costs one load, and the alternative is comparing a player against themselves.

Widening brackets is already handled: `_levels_to_try` (Task 1) returns the order, and
`fastest_runs` returns the first bracket with rows. To fill from the next bracket when the first is
short, `fastest_runs` gains a `minimum` argument, or the CLI walks the levels itself. Prefer the
former — `assert_bracket` must keep running per page, and it lives in the repository.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

---

## Task 13: Provenance, the timeline, and the single alignment

**Files:**
- Modify: `src/wowperf/domain/report/model.py`, `src/wowperf/domain/report/build.py`,
  `src/wowperf/adapters/render/report.html.j2`, `src/wowperf/cli.py`
- Test: `tests/domain/report/test_build_timeline.py`, `tests/domain/report/test_build_frame.py`,
  `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Produces: `ReferenceRecord` frozen value; `Provenance.references: tuple[ReferenceRecord, ...]`
  replacing the two URL scalars; `build_timeline(ours, member, section)`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_timeline_is_withheld_when_no_member_shares_our_keystone_level():
    timeline = build_timeline(OUR_RUN, sample_all_one_level_below(), SECTION)

    assert timeline.theirs is None


def test_the_timeline_track_names_the_member_it_drew_and_the_sample_size():
    assert timeline.theirs.caption.endswith("one of 5 fast runs")


def test_provenance_lists_every_candidate_considered():
    assert len(report.provenance.references) == 7  # five loaded, two that failed


def test_provenance_carries_no_reference_character_name():
    for record in report.provenance.references:
        assert SOME_REFERENCE_CHARACTER not in record.model_dump_json()
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

```python
class ReferenceRecord(Frozen):
    """One candidate the comparison considered, whether or not it was used.

    Carries a link and never a figure: the findings JSON and this report are
    kept forever, and a file that tabulates other players' durations and death
    counts is the corpus the 24-hour reference cache exists to avoid.
    """

    report_code: str
    fight_id: int
    keystone_level: int
    url: str
    axis: str
    loaded: bool = True
    reason: str = ""
    from_cache: bool = False
    fetched_at: str = ""
```

`build_timeline` takes the best-aligned **duration-eligible** member and draws nothing when there
is none. That is the gating fix the spec calls for: the report withholds the reference's durations
as numbers today and then draws them as a picture. It also takes the member's alignment rather than
calling `align_pulls` a second time.

The template renders the reference list as links. `autoescape` is on and `|safe` is forbidden.

- [ ] **Step 4: Run the tests, then the gate**

- [ ] **Step 5: Commit**

Body: the timeline drew durations the findings refused to print, which was one inconsistency with
one reference and a question about which of five with a sample.

---

## Task 14: The findings JSON, the warning, and the skill

**Files:**
- Modify: `src/wowperf/cli.py`, `.claude/skills/mplus-analysis/SKILL.md`, and the module holding
  `FINDINGS_ARE_RANKED_NOT_ADDITIVE`
- Test: the test that holds the "Already counted inside …" label set in step with the warning
  (find it with `grep -rn "Already counted inside" tests/`)

The `comparison` block becomes `{"compared": bool, "references": [...], "sample_size": {...}}`,
carrying report codes, fights, levels and URLs — and no character names, durations or death counts.

`compare.duration`'s documented containment claim breaks against a median: the total gap is
measured against one quantity while the component losses were priced against particular runs'
routes. Rewrite the warning, the skill's "Findings are ranked, never summed" section, and the test
together, in this one pass.

The skill also gains the quantifier rule: **the narrative may use only the `quantifier` the
findings file supplied, for the finding it supplied it for.** Without that rule the model reaches
for "most" on its own, which is it reading a number.

- [ ] **Step 1: Write the failing test**

```python
def test_the_findings_json_names_no_reference_character():
    payload = json.loads(written.read_text(encoding="utf-8"))

    assert SOME_REFERENCE_CHARACTER not in json.dumps(payload)


def test_every_reference_in_the_json_carries_a_url_and_no_duration():
    for reference in payload["comparison"]["references"]:
        assert reference["url"].startswith("https://www.warcraftlogs.com/reports/")
        assert "duration_seconds" not in reference
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement**

The `comparison` block, replacing the two singular objects:

```python
        "comparison": {
            "compared": bool(speed.members or parse.members),
            "sample_size": {"speed": len(speed.members), "parse": len(parse.members)},
            "references": [
                {
                    "axis": record.axis,
                    "report_code": record.report_code,
                    "fight_id": record.fight_id,
                    "keystone_level": record.keystone_level,
                    "url": record.url,
                    "loaded": record.loaded,
                    "reason": record.reason,
                    "from_cache": record.from_cache,
                }
                for record in records
            ],
        },
```

No `character_name`, no `duration_seconds`, no `medal`, no death count. Those three keys exist in
today's block and are deliberately gone: the file is kept forever and a link reaches everything a
reader needs to check a claim.

Then the warning. Today it says `compare.duration` already contains every other `seconds_lost` in
the file. Against a median it does not, and the replacement must say what is true instead: the
duration gap is measured against the median of the sample while each component loss was priced
against a particular run's route, so the figures overlap without one containing the others. Change
the constant, the skill section that repeats it, and the label-set test in the same commit — a
warning that disagrees with the skill is worse than either alone.

- [ ] **Step 4: Run the tests, then the gate**

`.claude/skills/wcl-api/SKILL.md` is held against the code by a test; `mplus-analysis` may be too.
Check before editing.

- [ ] **Step 5: Commit**

---

## Task 15: The denominator test, and the golden report

**Files:**
- Test: `tests/domain/comparison/test_sample_invariants.py` (new),
  `tests/adapters/render/golden/minimal.html`

The badge rule makes the denominator load-bearing: a `measured` count whose denominator went
missing is the exact failure the badge system exists to prevent. A convention will not hold it.

- [ ] **Step 1: Write the failing test**

```python
AGGREGATE_PREFIXES = (
    "compare.route.skipped.",
    "compare.spells.missing.",
    "compare.confound.composition",
    "compare.confound.affixes",
    "compare.confound.keystone_level",
)


def test_every_count_finding_states_its_denominator_in_its_title():
    findings = compare(ours=OURS, our_player=SUBJECT, speed=SAMPLE, parse=PARSE_SAMPLE)

    counted = [f for f in findings if f.id.startswith(AGGREGATE_PREFIXES)]
    assert counted, "the fixture must produce at least one aggregate finding"
    for finding in counted:
        assert re.search(r"\b\d+ of \d+\b", finding.title), finding.id


def test_every_median_finding_states_its_range_in_its_evidence():
    for finding in [f for f in findings if f.id in MEDIAN_IDS]:
        assert any("range" in line for line in finding.evidence), finding.id


def test_a_count_finding_is_measured_and_a_median_finding_is_derived():
    ...
```

Mutation-check each: delete the denominator from one title and confirm the test fails.

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement** — nothing, if Tasks 6 to 10 were done right. Any failure here is a real
  defect in one of them; fix it there, not by loosening the test.

- [ ] **Step 4: Regenerate the golden report and read the diff in full**

Do not accept it wholesale. Every changed line must be a line this plan intended to change.

- [ ] **Step 5: Commit**

---

## Task 16: End to end, and a live run

**Files:**
- Test: the e2e suite (`grep -rn "e2e" tests/` for where the marker lives)

- [ ] **Step 1: Write the e2e test**

A real sampled analysis against the live API: assert the sample filled, that at least one finding
carries a `quantifier`, and that provenance lists more than one reference. About 111 points of
3600.

- [ ] **Step 2: Run it**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e -v
```

- [ ] **Step 3: Run the real thing and read the page**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run wowperf analyze "https://www.warcraftlogs.com/reports/6Kx1P9GbNXrcLdHa?fight=36"
```

Then open `out/6Kx1P9GbNXrcLdHa-36.html` and read it. On this project every plan's worst defects
have survived the offline suite and appeared on the first real run. Check specifically: every
aggregate title carries its denominator; no reference character name appears anywhere on the page
or in the JSON; the timeline either draws a named member or is withheld; and the reported point
cost is near the projected 111.

- [ ] **Step 4: Record what it cost**

Add a dated row to `.claude/skills/wcl-api/SKILL.md` under **Rate limit**, in the form the existing
rows use.

- [ ] **Step 5: Commit**

---

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-driven (recommended)** — a fresh subagent per task, review between tasks, fast
iteration.

**2. Inline execution** — tasks executed in one session with checkpoints for review.
