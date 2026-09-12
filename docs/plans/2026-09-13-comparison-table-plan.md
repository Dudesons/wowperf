# Comparison Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every ability and aura the comparison measured under each compared player's card, so a reader can see where inside the reporting band they sit rather than only which figures crossed it.

**Architecture:** The per-ability measurement is extracted out of the three finding builders into `comparison/measures.py`, so a rate has one definition. The findings become one projection of it and the table a second. A new `comparison/tables.py` assembles the measures per player; the report layer formats them into a view model. Nothing new is fetched.

**Tech Stack:** Python 3.12, pydantic (`wowperf.domain.base.Frozen`), Jinja2, pytest, uv. Domain plus one template and its CSS.

**Spec:** `docs/plans/2026-09-13-comparison-table-design.md`

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or touches network, disk or template.
- **The comparison layer never imports the report layer.** `comparison/` produces domain measures; `report/` formats them. The design's §4 says `comparison_tables()` returns `ComparisonTable`; that would invert the layering, so this plan names the function `comparison_measures()` and returns `PlayerMeasures`. The view model is built in `report/players.py`.
- **The report loads nothing.** One HTML file, no stylesheet link, no `@import`, no remote `src`, exactly one inline script. That script may show, hide and highlight what is already on the page; it may not fetch, write text, or read storage. `<details>` is native HTML and adds no script.
- **The table is not a finding.** It carries no `seconds_lost`, does not enter `rank_findings`, and does not appear in the JSON's `findings` array. It goes in the findings file as the sibling top-level key `comparison_tables`.
- **The view model carries formatted strings.** The template decides nothing, including how a number is spelled.
- **No damage ranking.** Cast rates and aura uptimes only. No percentile, no parse number, no throughput.
- **The refactor in Tasks 1 to 3 must change no finding.** The existing spell, trash and uptime suites are the regression net and must pass untouched.
- **Test-first, always.** Write the test, run it, watch it fail for the right reason, then implement. Where a test passes the moment it is written, mutate the guard it covers and confirm the test goes red before trusting it. Two tests in the trash work passed on first writing because their fixtures were rejected by an earlier gate than the one under test, so list the gates an input passes through and ask which one actually rejects it.
- **Every command runs under `uv`.** On the development machine `uv` is off PATH in bash; prefix with `export PATH="$HOME/.local/bin:$PATH" && `. Git needs its absolute path, `/mingw64/bin/git`.
- **Commit messages:** imperative mood, no `feat:`/`fix:` prefix, plain ASCII, body explains why. End with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Never use `--no-verify`.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/comparison/measures.py` (new) | `Verdict`, `Stretch`, `AbilityRate`, `AuraUptime`, `PlayerMeasures`. Pure data, no logic beyond the verdict rule. |
| `src/wowperf/domain/comparison/spells.py` | Gains `rate_measures()`; `_rate_sample` consumes it instead of computing inline. |
| `src/wowperf/domain/comparison/trash_spells.py` | Gains `trash_rate_measures()`; `_rate_rows` consumes it. |
| `src/wowperf/domain/comparison/uptime.py` | Gains `uptime_measures()`; `_gap_findings_sample` consumes it. |
| `src/wowperf/domain/comparison/tables.py` (new) | `comparison_measures()`: one `PlayerMeasures` per compared player slug. |
| `src/wowperf/domain/report/model.py` | `ComparisonRow`, `ComparisonTable`; `PlayerCard.comparison_tables`. |
| `src/wowperf/domain/report/players.py` | Formats `PlayerMeasures` into tables: sorting, number formatting, captions. |
| `src/wowperf/domain/report/build.py` | Threads measures to `build_players`. |
| `src/wowperf/cli.py` | Calls `comparison_measures()`, passes to `build_report`, writes the JSON key. |
| `src/wowperf/adapters/render/_players.html.j2` | Renders each table inside a `<details>`. |
| `src/wowperf/adapters/render/report.css.j2` | Table styling. |

---

### Task 1: Boss rate measures

Extract the per-ability boss rate computation out of `_rate_sample` so one function owns it. `_rate_sample` keeps producing exactly the findings it produces today.

**Files:**
- Create: `src/wowperf/domain/comparison/measures.py`
- Modify: `src/wowperf/domain/comparison/spells.py`
- Test: `tests/domain/comparison/test_spells.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Verdict` (StrEnum): `BELOW`, `ABOVE`, `LEVEL`, `UNJUDGED`
  - `Stretch` (StrEnum): `BOSS`, `TRASH`
  - `AbilityRate(Frozen)`: `ability_id: int`, `name: str`, `ours: float`, `their_median: float`, `their_rates: tuple[float, ...]`, `stretch: Stretch`, `verdict: Verdict`
  - `rate_measures(ours_on_bosses: dict[int, tuple[str, int]], our_boss_seconds: float, per_member: Sequence[tuple[float, dict[int, int]]]) -> tuple[AbilityRate, ...]`

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_spells.py`, after `test_casting_somewhat_more_than_the_sample_is_not_reported`:

```python
def test_rate_measures_carries_one_row_per_compared_ability_with_its_verdict() -> None:
    """The one place a boss cast rate is computed. The findings are a projection of
    these, and so is the table, so a second computation would let a row and the
    table beneath it disagree about one player's figure."""
    ours_on_bosses = {METEOR: ("Meteor", 2), SHIFTING_POWER: ("Shifting Power", 3)}
    per_member = [
        (60.0, {METEOR: 6, SHIFTING_POWER: 3}),
        (60.0, {METEOR: 8, SHIFTING_POWER: 3}),
        (60.0, {METEOR: 4, SHIFTING_POWER: 3}),
        (60.0, {METEOR: 10, SHIFTING_POWER: 3}),
    ]

    measures = {m.name: m for m in rate_measures(ours_on_bosses, 60.0, per_member)}

    assert measures["Meteor"].ours == 2.0
    assert measures["Meteor"].their_median == 7.0
    assert measures["Meteor"].their_rates == (6.0, 8.0, 4.0, 10.0)
    assert measures["Meteor"].verdict is Verdict.BELOW
    assert measures["Meteor"].stretch is Stretch.BOSS
    assert measures["Shifting Power"].verdict is Verdict.LEVEL


def test_rate_measures_marks_an_ability_we_cast_far_more_as_above() -> None:
    per_member = [(60.0, {METEOR: 6}), (60.0, {METEOR: 8}), (60.0, {METEOR: 4})]

    measures = rate_measures({METEOR: ("Meteor", 20)}, 60.0, per_member)

    assert [m.verdict for m in measures] == [Verdict.ABOVE]


def test_rate_measures_skips_an_ability_too_few_of_the_sample_cast() -> None:
    """Below MIN_MEMBERS_WITH_ABILITY there is no median to argue from, and the
    table must show only what was actually compared."""
    per_member = [(60.0, {METEOR: 6}), (60.0, {METEOR: 8}), (60.0, {}), (60.0, {})]

    measures = rate_measures({METEOR: ("Meteor", 2)}, 60.0, per_member)

    assert measures == ()
```

Add to the imports at the top of the file:

```python
from wowperf.domain.comparison.measures import Stretch, Verdict
from wowperf.domain.comparison.spells import (
    ...,
    rate_measures,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_spells.py -q`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'wowperf.domain.comparison.measures'`.

- [ ] **Step 3: Create the measures module**

Create `src/wowperf/domain/comparison/measures.py`:

```python
# ABOUTME: The per-ability figures a comparison measures, shared by its findings and its table.
# ABOUTME: One definition of a rate, so a row and the table beneath it cannot disagree.

from enum import StrEnum

from wowperf.domain.base import Frozen


class Verdict(StrEnum):
    """Which branch a compared ability or aura took.

    `UNJUDGED` is reached only by auras: `onSelf` carries no source, so an aura
    we show none of may be a teammate's buff nobody gave this player, and that
    is not the same claim as being below the sample. No cast rate is ever
    unjudged, because a cast is unambiguously the player's own.
    """

    BELOW = "below"
    ABOVE = "above"
    LEVEL = "level"
    UNJUDGED = "unjudged"


class Stretch(StrEnum):
    """Which stretch of the dungeon a rate was measured over.

    The two never share a denominator -- one is boss-pull seconds and the other
    the seconds of trash both routes fought -- so a row carries which it is
    rather than leaving a reader to infer it from the figure.
    """

    BOSS = "boss"
    TRASH = "trash"


class AbilityRate(Frozen):
    """One ability's cast rate against the sample's median, in casts a minute."""

    ability_id: int
    name: str
    ours: float
    their_median: float
    their_rates: tuple[float, ...]
    stretch: Stretch
    verdict: Verdict


class AuraUptime(Frozen):
    """One aura's share of our boss time against the sample's median share.

    Fractions, not seconds: two runs fight the same boss for different long.
    """

    ability_id: int
    name: str
    ours: float
    their_median: float
    their_fractions: tuple[float, ...]
    verdict: Verdict


class PlayerMeasures(Frozen):
    """Everything one player's comparison measured, and the denominators behind it.

    The denominators ride along because a caption has to state them: a rate per
    minute means nothing to a reader who cannot see how many minutes it was
    drawn from.
    """

    boss: tuple[AbilityRate, ...] = ()
    trash: tuple[AbilityRate, ...] = ()
    auras: tuple[AuraUptime, ...] = ()
    boss_seconds: float = 0.0
    trash_seconds: float = 0.0
    pack_count: int = 0
```

- [ ] **Step 4: Add `rate_measures` and rewrite `_rate_sample` on top of it**

In `src/wowperf/domain/comparison/spells.py`, add the import:

```python
from wowperf.domain.comparison.measures import AbilityRate, Stretch, Verdict
```

Add above `_rate_sample`:

```python
def verdict_for(ours: float, their_median: float) -> Verdict:
    """Which of the three branches a rate falls in, at the one bar both directions use.

    `their_median` is never zero here: a member only contributes a rate after
    clearing `MIN_CASTS_TO_COMPARE` over non-zero seconds.
    """
    if ours / their_median >= RATE_GAP_MULTIPLE:
        return Verdict.ABOVE
    if their_median / ours >= RATE_GAP_MULTIPLE:
        return Verdict.BELOW
    return Verdict.LEVEL


def rate_measures(
    ours_on_bosses: dict[int, tuple[str, int]],
    our_boss_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> tuple[AbilityRate, ...]:
    """Every ability compared on boss pulls, with the verdict it earned.

    The one place a boss cast rate is computed. `_rate_sample` turns these into
    findings and `comparison.tables` turns them into table rows; computing them
    twice is how a row and the table beneath it come to state different numbers
    for one player.
    """
    measures: list[AbilityRate] = []
    for ability_id, (name, our_count) in ours_on_bosses.items():
        rates = [
            qualifying[ability_id] / their_boss_seconds * 60
            for their_boss_seconds, qualifying in per_member
            if ability_id in qualifying
        ]
        if len(rates) < MIN_MEMBERS_WITH_ABILITY:
            continue
        our_rate = our_count / our_boss_seconds * 60
        if our_rate <= 0:
            continue
        their_median = median(rates)
        measures.append(
            AbilityRate(
                ability_id=ability_id,
                name=name,
                ours=our_rate,
                their_median=their_median,
                their_rates=tuple(rates),
                stretch=Stretch.BOSS,
                verdict=verdict_for(our_rate, their_median),
            )
        )
    return tuple(measures)
```

Replace the whole body of `_rate_sample` from `gaps = []` down to `return rows` with:

```python
    measures = rate_measures(ours_on_bosses, our_boss_seconds, per_member)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )
    above = sorted(
        (m for m in measures if m.verdict is Verdict.ABOVE),
        key=lambda m: m.ours - m.their_median,
        reverse=True,
    )
    level = [m.name for m in measures if m.verdict is Verdict.LEVEL]

    findings = [_gap_finding(our_name, m, our_boss_seconds) for m in gaps]
    findings += [
        _above_finding(
            our_name, m.ability_id, m.name, m.ours, m.their_median,
            list(m.their_rates), our_boss_seconds,
        )
        for m in above
    ]
    rows = _one_row_per_sentence(findings)
    if level:
        rows.append(_level_finding(our_name, level))
    return rows


def _gap_finding(our_name: str, measure: AbilityRate, our_boss_seconds: float) -> Finding:
    """An ability the sample's median rate clears by `RATE_GAP_MULTIPLE`."""
    low, high = observed_range(measure.their_rates)
    return Finding(
        id="compare.spells.rate",
        title=(
            f"{len(measure.their_rates)} top parses cast {measure.name} a median "
            f"{measure.their_median:.1f} times a minute on bosses; "
            f"{our_name} casts it {measure.ours:.1f}"
        ),
        detail=(
            "Both rates are casts per minute of boss-pull time, which is the one "
            "stretch of a dungeon where every run fought the same encounter. The "
            "reference side is the median across the sample, not one parse, so a "
            "single busy or quiet run cannot carry the comparison alone."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"ability {measure.ability_id}",
            f"ours over {our_boss_seconds:.0f}s of boss pulls",
            f"range {low:.1f} to {high:.1f} casts a minute across "
            f"{len(measure.their_rates)} top parses",
        ),
        facts=(
            FindingFact(label="Ours", value=f"{measure.ours:.1f} casts a minute",
                        confidence=Confidence.DERIVED),
            FindingFact(label="Reference median",
                        value=f"{measure.their_median:.1f} casts a minute",
                        confidence=Confidence.DERIVED),
            FindingFact(label="Observed range", value=f"{low:.1f} to {high:.1f}",
                        confidence=Confidence.DERIVED),
            FindingFact(label="Sample", value=f"{len(measure.their_rates)} top parses"),
        ),
        ability_id=measure.ability_id,
        ability_name=measure.name,
    )
```

The `detail`, `evidence` and `facts` above are copied verbatim from the code being replaced. If they differ by a character the existing tests will say so.

- [ ] **Step 5: Run the whole spells suite**

Run: `uv run pytest tests/domain/comparison/test_spells.py -q`
Expected: PASS, all of it. Any failure here is the refactor changing a finding, which it must not.

- [ ] **Step 6: Prove the skip test could fail**

`test_rate_measures_skips_an_ability_too_few_of_the_sample_cast` passes the moment it is written. Change `if len(rates) < MIN_MEMBERS_WITH_ABILITY:` to `if len(rates) < 1:` and confirm that test FAILS. Restore and confirm PASS.

- [ ] **Step 7: Run the full gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/wowperf/domain/comparison/measures.py src/wowperf/domain/comparison/spells.py tests/domain/comparison/test_spells.py
git commit -F - <<'MSG'
Give a boss cast rate one definition to be read from

The rate rows compute a figure per ability, pick one of three branches and
throw the figure away. A table of what was compared needs the same figures,
and computing them a second time is how a row and the table beneath it come
to state different numbers for one player -- the failure extracting casts_in
was meant to prevent, one level up.

The findings are now a projection of the measurement rather than its only
consumer. No finding changes, which the existing suite is the proof of.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Trash rate measures

The same extraction in `trash_spells.py`.

**Files:**
- Modify: `src/wowperf/domain/comparison/trash_spells.py`
- Test: `tests/domain/comparison/test_trash_spells.py`

**Interfaces:**
- Consumes: `AbilityRate`, `Stretch`, `Verdict` from `measures.py`; `verdict_for` from `spells.py` (Task 1).
- Produces: `trash_rate_measures(ours_on_trash: dict[int, tuple[str, int]], our_seconds: float, per_member: Sequence[tuple[float, dict[int, int]]]) -> tuple[AbilityRate, ...]`

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_trash_spells.py`:

```python
def test_trash_rate_measures_stamp_the_trash_stretch() -> None:
    """The two stretches never share a denominator, so a row carries which it is
    rather than leaving a reader to infer it from the figure."""
    per_member = [(60.0, {BLOOD_BOIL: 10}), (60.0, {BLOOD_BOIL: 10}), (60.0, {BLOOD_BOIL: 10})]

    measures = trash_rate_measures({BLOOD_BOIL: ("Blood Boil", 4)}, 60.0, per_member)

    assert [m.stretch for m in measures] == [Stretch.TRASH]
    assert measures[0].verdict is Verdict.BELOW
    assert measures[0].ours == 4.0
    assert measures[0].their_median == 10.0
```

Add to that file's imports:

```python
from wowperf.domain.comparison.measures import Stretch, Verdict
from wowperf.domain.comparison.trash_spells import (
    ...,
    trash_rate_measures,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -q`
Expected: FAIL at import — `cannot import name 'trash_rate_measures'`.

- [ ] **Step 3: Write the implementation**

In `src/wowperf/domain/comparison/trash_spells.py`, add the imports:

```python
from wowperf.domain.comparison.measures import AbilityRate, Stretch, Verdict
from wowperf.domain.comparison.spells import (
    ...,
    verdict_for,
)
```

Add above `_rate_rows`:

```python
def trash_rate_measures(
    ours_on_trash: dict[int, tuple[str, int]],
    our_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> tuple[AbilityRate, ...]:
    """Every ability compared on the shared packs, with the verdict it earned.

    The trash twin of `rate_measures`, sharing its bar through `verdict_for`
    so the two stretches cannot drift apart on what counts as a gap.
    """
    measures: list[AbilityRate] = []
    for ability_id, (name, our_count) in ours_on_trash.items():
        rates = [
            qualifying[ability_id] / their_seconds * 60
            for their_seconds, qualifying in per_member
            if ability_id in qualifying and their_seconds > 0
        ]
        if len(rates) < MIN_MEMBERS_WITH_ABILITY:
            continue
        our_rate = our_count / our_seconds * 60
        if our_rate <= 0:
            continue
        their_median = median(rates)
        measures.append(
            AbilityRate(
                ability_id=ability_id,
                name=name,
                ours=our_rate,
                their_median=their_median,
                their_rates=tuple(rates),
                stretch=Stretch.TRASH,
                verdict=verdict_for(our_rate, their_median),
            )
        )
    return tuple(measures)
```

Replace the body of `_rate_rows` from `gaps = []` down to the `for ability_id, ...` loop's end with:

```python
    measures = trash_rate_measures(ours_on_trash, our_seconds, per_member)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )
    above = sorted(
        (m for m in measures if m.verdict is Verdict.ABOVE),
        key=lambda m: m.ours - m.their_median,
        reverse=True,
    )
    level = [m.name for m in measures if m.verdict is Verdict.LEVEL]
```

Then rewrite the two `enumerate` loops that build the findings to read from `measures` rather than the old tuples. Each loop keeps its existing `Finding(...)` body verbatim, substituting `m.ability_id`, `m.name`, `m.ours`, `m.their_median` and `list(m.their_rates)` for the unpacked tuple fields, and `observed_range(m.their_rates)` for `observed_range(rates)`.

- [ ] **Step 4: Run the whole trash suite**

Run: `uv run pytest tests/domain/comparison/test_trash_spells.py -q`
Expected: PASS, all of it. A failure is the refactor changing a finding.

- [ ] **Step 5: Prove the new test could fail**

Change `stretch=Stretch.TRASH` to `stretch=Stretch.BOSS` and confirm `test_trash_rate_measures_stamp_the_trash_stretch` FAILS. Restore and confirm PASS.

- [ ] **Step 6: Run the full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/trash_spells.py tests/domain/comparison/test_trash_spells.py
git commit -F - <<'MSG'
Give a trash cast rate the same single definition

The trash twin of the previous commit, sharing the bar through verdict_for
rather than restating it, so the two stretches cannot come to disagree about
what counts as a gap.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 3: Aura uptime measures

**Files:**
- Modify: `src/wowperf/domain/comparison/uptime.py`
- Test: `tests/domain/comparison/test_uptime.py`

**Interfaces:**
- Consumes: `AuraUptime`, `Verdict` from `measures.py`.
- Produces: `uptime_measures(our_fractions: dict[int, tuple[str, float]], per_member: Sequence[dict[int, float]], names: dict[int, str]) -> tuple[AuraUptime, ...]`

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/comparison/test_uptime.py`:

```python
def test_uptime_measures_carry_a_verdict_per_aura() -> None:
    """Four outcomes, and the table has to tell them apart: a gap, a level aura,
    one we show none of, and one too few of the sample carried to judge."""
    names = {1: "Wide gap", 2: "Level", 3: "We have none", 4: "Too few carried it"}
    per_member = [
        {1: 0.90, 2: 0.80, 3: 0.70, 4: 0.60},
        {1: 0.90, 2: 0.80, 3: 0.70},
        {1: 0.90, 2: 0.80, 3: 0.70},
    ]
    our_fractions = {1: ("Wide gap", 0.10), 2: ("Level", 0.78), 3: ("We have none", 0.0)}

    measures = {m.name: m for m in uptime_measures(our_fractions, per_member, names)}

    assert measures["Wide gap"].verdict is Verdict.BELOW
    assert measures["Wide gap"].their_median == 0.90
    assert measures["Level"].verdict is Verdict.LEVEL
    assert measures["We have none"].verdict is Verdict.UNJUDGED
    assert "Too few carried it" not in measures


def test_an_aura_the_sample_barely_carried_is_not_measured() -> None:
    """Below MIN_UPTIME_FRACTION the reference barely had it either, so there is
    nothing to argue from and nothing to put in a table."""
    names = {1: "Barely up"}
    per_member = [{1: 0.05}, {1: 0.05}, {1: 0.05}]

    measures = uptime_measures({1: ("Barely up", 0.0)}, per_member, names)

    assert measures == ()
```

Add `uptime_measures` to the file's `uptime` import block and `Verdict` from `measures`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_uptime.py -q`
Expected: FAIL at import — `cannot import name 'uptime_measures'`.

- [ ] **Step 3: Write the implementation**

In `src/wowperf/domain/comparison/uptime.py`, add:

```python
from wowperf.domain.comparison.measures import AuraUptime, Verdict
```

Add above `_gap_findings_sample`:

```python
def uptime_measures(
    our_fractions: dict[int, tuple[str, float]],
    per_member: Sequence[dict[int, float]],
    names: dict[int, str],
) -> tuple[AuraUptime, ...]:
    """Every aura the sample carried often enough to judge, with its verdict.

    The one place an uptime fraction is compared. An aura below
    `MIN_SAMPLE_FOR_AGGREGATE` carriers or below `MIN_UPTIME_FRACTION` is
    absent entirely rather than carrying a verdict: neither was compared, and
    a table that showed them would claim a judgement nobody made.
    """
    measures: list[AuraUptime] = []
    for ability_id, name in names.items():
        carried = [q[ability_id] for q in per_member if ability_id in q]
        if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
            continue
        their_median = median(carried)
        if their_median < MIN_UPTIME_FRACTION:
            continue
        our_fraction = our_fractions.get(ability_id, (name, 0.0))[1]
        if our_fraction <= 0.0:
            verdict = Verdict.UNJUDGED
        elif their_median - our_fraction >= UPTIME_GAP_FRACTION:
            verdict = Verdict.BELOW
        else:
            verdict = Verdict.LEVEL
        measures.append(
            AuraUptime(
                ability_id=ability_id,
                name=name,
                ours=our_fraction,
                their_median=their_median,
                their_fractions=tuple(carried),
                verdict=verdict,
            )
        )
    return tuple(measures)
```

Rewrite `_gap_findings_sample`'s own loop to consume `uptime_measures(our_fractions, per_member, names)`: `gaps` becomes the `Verdict.BELOW` measures and `unjudged` the names of the `Verdict.UNJUDGED` ones, with each finding body kept verbatim.

- [ ] **Step 4: Run the whole uptime suite**

Run: `uv run pytest tests/domain/comparison/test_uptime.py -q`
Expected: PASS, all of it.

- [ ] **Step 5: Prove the floor test could fail**

Change `if their_median < MIN_UPTIME_FRACTION:` to `if their_median < 0.0:` and confirm `test_an_aura_the_sample_barely_carried_is_not_measured` FAILS. Restore and confirm PASS.

- [ ] **Step 6: Run the full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/uptime.py tests/domain/comparison/test_uptime.py
git commit -F - <<'MSG'
Give an aura uptime comparison one definition to be read from

The third and last of the measurements the table needs. An aura too few of
the sample carried, or one the sample barely kept up itself, carries no
verdict at all rather than a weak one: neither was compared, and a table
showing them would claim a judgement nobody made.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 4: Assemble the measures per player

**Files:**
- Create: `src/wowperf/domain/comparison/tables.py`
- Test: `tests/domain/comparison/test_tables.py`

**Interfaces:**
- Consumes: `rate_measures`, `their_actor_id`, `boss_casts`, `boss_seconds` (spells); `trash_rate_measures`, `aligned_trash`, `is_comparable`, `casts_in` (trash_spells); `uptime_measures`, `boss_windows`, `_fractions` (uptime); `ComparisonSubject` from `service.py`.
- Produces: `comparison_measures(ours: LoadedRun, subjects: Sequence[ComparisonSubject]) -> dict[str, PlayerMeasures]`

- [ ] **Step 1: Write the failing test**

Create `tests/domain/comparison/test_tables.py`:

```python
# ABOUTME: The per-player measures the report's comparison table is built from.
# ABOUTME: One entry per compared player, keyed by the slug the page matches cards on.

from wowperf.domain.comparison.measures import Stretch, Verdict
from wowperf.domain.comparison.service import ComparisonSubject
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.comparison.sample import ParseSample
from tests.domain.comparison.test_service import (
    ARCANE_BLAST,
    OUR_SLUG,
    OURS,
    a_run_sharing_a_pack,
    a_shared_pack_member,
)


def test_every_compared_player_gets_one_entry_keyed_by_slug() -> None:
    sample = ParseSample(
        members=tuple(a_shared_pack_member(code) for code in ("REF1", "REF2", "REF3"))
    )
    subject = ComparisonSubject(
        player=OURS, slug=OUR_SLUG, display_name=OURS.name, parse=sample
    )

    measures = comparison_measures(a_run_sharing_a_pack(), (subject,))

    assert set(measures) == {OUR_SLUG}
    trash = {m.name: m for m in measures[OUR_SLUG].trash}
    assert trash["Arcane Blast"].verdict is Verdict.BELOW
    assert trash["Arcane Blast"].stretch is Stretch.TRASH
    assert measures[OUR_SLUG].pack_count == 1


def test_a_player_with_no_parse_sample_gets_no_entry() -> None:
    """A slug with an empty table and a slug that is absent read differently: the
    first says a comparison ran and found nothing, the second that none ran."""
    subject = ComparisonSubject(
        player=OURS, slug=OUR_SLUG, display_name=OURS.name, parse=None
    )

    assert comparison_measures(a_run_sharing_a_pack(), (subject,)) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_tables.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wowperf.domain.comparison.tables'`.

- [ ] **Step 3: Write the implementation**

Create `src/wowperf/domain/comparison/tables.py`:

```python
# ABOUTME: Assembles everything one player's comparison measured, for the report's table.
# ABOUTME: Reads the same measurements the findings do, so the two cannot disagree.

from collections.abc import Sequence

from wowperf.domain.comparison.measures import PlayerMeasures
from wowperf.domain.comparison.sample import ParseSample
from wowperf.domain.comparison.service import ComparisonSubject
from wowperf.domain.comparison.spells import (
    MIN_CASTS_TO_COMPARE,
    boss_casts,
    boss_seconds,
    casts_in,
    rate_measures,
    their_actor_id,
)
from wowperf.domain.comparison.trash_spells import (
    aligned_trash,
    is_comparable,
    trash_rate_measures,
)
from wowperf.domain.comparison.uptime import (
    _fractions,
    boss_windows,
    uptime_measures,
)
from wowperf.domain.model import LoadedRun, Player


def comparison_measures(
    ours: LoadedRun, subjects: Sequence[ComparisonSubject]
) -> dict[str, PlayerMeasures]:
    """Everything each compared player's comparison measured, keyed by slug.

    A player whose parse sample is absent or empty gets no entry at all. An
    empty table and a missing one are different claims: the first says a
    comparison ran and measured nothing, the second that none ran.

    This repeats the arithmetic `compare()` already did. That is deliberate:
    the alternative is for `compare()` to return a tuple, changing a signature
    every test and both callers use, to save microseconds of pure arithmetic
    over data already in memory. Duplicate execution, single definition.
    """
    measures: dict[str, PlayerMeasures] = {}
    for subject in subjects:
        parse = subject.parse
        if parse is None or not parse.members:
            continue
        measures[subject.slug] = _for_one(ours, subject.player, subject.our_auras, parse)
    return measures
```

Then `_for_one`, which rebuilds the three `per_member` shapes exactly as the three comparison entry points do and calls the three measure functions. Its boss half:

```python
def _boss(ours: LoadedRun, our_player: Player, parse: ParseSample) -> tuple[...]:
    per_member: list[tuple[float, dict[int, int]]] = []
    for member in parse.members:
        actor_id = their_actor_id(member, member.row.character_name)
        seconds = boss_seconds(member.run)
        if actor_id is None or seconds <= 0:
            per_member.append((0.0, {}))
            continue
        counted = boss_casts(member.run, member.casts, actor_id)
        per_member.append(
            (seconds, {a: c for a, (_n, c) in counted.items() if c >= MIN_CASTS_TO_COMPARE})
        )
    our_seconds = boss_seconds(ours.run)
    if our_seconds <= 0:
        return (), 0.0
    return (
        rate_measures(boss_casts(ours.run, ours.casts, our_player.actor_id),
                      our_seconds, per_member),
        our_seconds,
    )
```

The trash half mirrors `compare_trash_spells_sample`'s member loop, including the union of `aligned.our_pulls` across comparable members, and the aura half mirrors `_gap_findings_sample`'s. Write each by reading its counterpart and keeping the same guards; a divergence here is exactly the drift Task 8's test exists to catch.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/domain/comparison/test_tables.py -q`
Expected: PASS.

- [ ] **Step 5: Prove the no-entry test could fail**

Change `if parse is None or not parse.members:` to `if parse is None:` and confirm `test_a_player_with_no_parse_sample_gets_no_entry` still passes (a `None` parse is still skipped), then change it to `if False:` and confirm it FAILS. Restore and confirm PASS. The two-step check is the point: the first mutation shows the guard has two halves and only one is covered, so add a third test passing `ParseSample()` and asserting `{}` before moving on.

- [ ] **Step 6: Run the full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/comparison/tables.py tests/domain/comparison/test_tables.py
git commit -F - <<'MSG'
Assemble what each player's comparison measured

One entry per compared player, keyed by the slug the page matches cards on.
A player whose sample is absent gets no entry rather than an empty one: an
empty table says a comparison ran and measured nothing, and a missing one
says none ran, which are different claims about the same player.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 5: The view model and the formatting

**Files:**
- Modify: `src/wowperf/domain/report/model.py`
- Modify: `src/wowperf/domain/report/players.py`
- Test: `tests/domain/report/test_build_players.py`

**Interfaces:**
- Consumes: `PlayerMeasures`, `AbilityRate`, `AuraUptime`, `Verdict` (Task 1); `comparison_measures` (Task 4).
- Produces:
  - `ComparisonRow(Frozen)`: `ability_id: int`, `name: str`, `ours: str`, `theirs: str`, `spread: str`, `sample: str`, `verdict: str`
  - `ComparisonTable(Frozen)`: `heading: str`, `caption: str`, `rows: tuple[ComparisonRow, ...] = ()`
  - `PlayerCard.comparison_tables: tuple[ComparisonTable, ...] = ()`
  - `build_players(..., measures: Mapping[str, PlayerMeasures] = NO_MEASURES)`

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/report/test_build_players.py`:

```python
def test_a_compared_players_card_carries_its_tables_sorted_by_gap() -> None:
    """The top of each table is the end worth reading, so the largest difference
    comes first whichever direction it runs in."""
    measures = {
        "stonewake-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=1, name="Small gap", ours=9.0, their_median=10.0,
                            their_rates=(10.0,), stretch=Stretch.BOSS, verdict=Verdict.LEVEL),
                AbilityRate(ability_id=2, name="Big gap", ours=2.0, their_median=9.0,
                            their_rates=(9.0,), stretch=Stretch.BOSS, verdict=Verdict.BELOW),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    boss = next(t for t in card.comparison_tables if "boss" in t.heading.lower())
    assert [row.name for row in boss.rows] == ["Big gap", "Small gap"]
    assert boss.rows[0].ours == "2.0"
    assert boss.rows[0].theirs == "9.0"
    assert boss.rows[0].verdict == "below"


def test_an_uncompared_player_gets_no_tables() -> None:
    card = build_players(
        a_loaded(), (), frozenset(), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures={},
    )[0]

    assert card.comparison_tables == ()


def test_an_uptime_row_is_spelled_as_a_percentage() -> None:
    """Rates are casts a minute and uptimes are a share of boss time. A column
    that spelled both the same way would invite reading one as the other."""
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraUptime(ability_id=3, name="Bone Shield", ours=0.984,
                           their_median=1.0, their_fractions=(1.0,), verdict=Verdict.LEVEL),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    auras = next(t for t in card.comparison_tables if "uptime" in t.heading.lower())
    assert auras.rows[0].ours == "98%"
    assert auras.rows[0].theirs == "100%"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/domain/report/test_build_players.py -q`
Expected: FAIL — `build_players() got an unexpected keyword argument 'measures'`.

- [ ] **Step 3: Add the view model types**

In `src/wowperf/domain/report/model.py`, above `PlayerCard`:

```python
class ComparisonRow(Frozen):
    """One ability or aura the comparison measured, formatted for a table cell.

    Strings, not floats: the template decides nothing, including how a number
    is spelled. `verdict` is the word the row is styled by -- below, above,
    level or unjudged -- and never a colour.
    """

    ability_id: int
    name: str
    ours: str
    theirs: str
    spread: str
    sample: str
    verdict: str


class ComparisonTable(Frozen):
    """One stretch's worth of measured figures, under its own denominator.

    The caption states the denominator because a rate per minute means nothing
    to a reader who cannot see how many minutes it came from, and the three
    tables never share one.
    """

    heading: str
    caption: str
    rows: tuple[ComparisonRow, ...] = ()
```

Add to `PlayerCard`:

```python
    comparison_tables: tuple[ComparisonTable, ...] = ()
    """Every figure this player's comparison measured, as the evidence for the
    rows above. Empty for a player nobody compared."""
```

- [ ] **Step 4: Build the tables in `build_players`**

In `src/wowperf/domain/report/players.py`, add beside the other module constants. `Mapping` is already imported at the top of that file; `MappingProxyType` is not, so add `from types import MappingProxyType` beside it. This mirrors `NO_TOOLTIPS` in `report/ledger.py:100`:

```python
NO_MEASURES: Mapping[str, PlayerMeasures] = MappingProxyType({})
```

Add `measures: Mapping[str, PlayerMeasures] = NO_MEASURES` as the last parameter of `build_players`, and inside the per-player loop set `comparison_tables=_tables(measures.get(slug))` on the card. Then:

```python
def _tables(measures: PlayerMeasures | None) -> tuple[ComparisonTable, ...]:
    """The three tables, each dropped when it has no rows to show."""
    if measures is None:
        return ()
    built = []
    if measures.boss:
        built.append(
            ComparisonTable(
                heading="Casts on boss pulls",
                caption=(
                    f"Casts a minute over {measures.boss_seconds:.0f}s of boss pulls, "
                    "against the median of the parses that cast each. Derived."
                ),
                rows=_rate_rows(measures.boss),
            )
        )
    if measures.trash:
        built.append(
            ComparisonTable(
                heading="Casts on shared trash packs",
                caption=(
                    f"Casts a minute over {measures.trash_seconds:.0f}s of trash across "
                    f"{measures.pack_count} {plural(measures.pack_count, 'pack')} both routes fought, "
                    "against the median of the parses that cast each. Derived."
                ),
                rows=_rate_rows(measures.trash),
            )
        )
    if measures.auras:
        built.append(
            ComparisonTable(
                heading="Buff uptime on boss pulls",
                caption=(
                    f"Share of {measures.boss_seconds:.0f}s of boss pulls, against the "
                    "median of the parses that carried each. Derived."
                ),
                rows=_aura_rows(measures.auras),
            )
        )
    return tuple(built)


def _rate_rows(measures: Sequence[AbilityRate]) -> tuple[ComparisonRow, ...]:
    """Cast rates, widest difference first, whichever direction it runs in."""
    ordered = sorted(measures, key=lambda m: abs(m.ours - m.their_median), reverse=True)
    rows = []
    for m in ordered:
        low, high = observed_range(m.their_rates)
        rows.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                ours=f"{m.ours:.1f}",
                theirs=f"{m.their_median:.1f}",
                spread=f"{low:.1f} to {high:.1f}",
                sample=f"{len(m.their_rates)} top parses",
                verdict=m.verdict.value,
            )
        )
    return tuple(rows)


def _aura_rows(measures: Sequence[AuraUptime]) -> tuple[ComparisonRow, ...]:
    """Aura uptimes, as a share of boss time rather than as seconds."""
    ordered = sorted(measures, key=lambda m: abs(m.ours - m.their_median), reverse=True)
    rows = []
    for m in ordered:
        low, high = observed_range(m.their_fractions)
        rows.append(
            ComparisonRow(
                ability_id=m.ability_id,
                name=m.name,
                ours=f"{m.ours:.0%}",
                theirs=f"{m.their_median:.0%}",
                spread=f"{low:.0%} to {high:.0%}",
                sample=f"{len(m.their_fractions)} top parses",
                verdict=m.verdict.value,
            )
        )
    return tuple(rows)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/domain/report/test_build_players.py -q`
Expected: PASS.

- [ ] **Step 6: Prove the sorting test could fail**

Remove `reverse=True` from `_rate_rows`'s sort and confirm `test_a_compared_players_card_carries_its_tables_sorted_by_gap` FAILS on the row order. Restore and confirm PASS.

- [ ] **Step 7: Run the full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/model.py src/wowperf/domain/report/players.py tests/domain/report/test_build_players.py
git commit -F - <<'MSG'
Format the measured figures into a table per stretch

Three tables rather than one, because the three never share a denominator:
648 seconds of boss pulls, 950 of aligned trash, and a share of the first.
One table with a stretch column would put figures drawn from different
denominators in one column and leave a reader comparing them unwarned.

Widest difference first in each, whichever direction it runs in, so the top
of a table is the end worth reading.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 6: Thread it through the report and the findings file

**Files:**
- Modify: `src/wowperf/domain/report/build.py:38-87`
- Modify: `src/wowperf/cli.py:824`, `:832-874`, `:891`
- Test: `tests/domain/report/test_build_frame.py`

**Interfaces:**
- Consumes: `comparison_measures` (Task 4), `build_players(..., measures=...)` (Task 5).
- Produces: `build_report(..., comparison_measures: Mapping[str, PlayerMeasures] = NO_MEASURES)`; the findings file's top-level `comparison_tables` key.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/report/test_build_frame.py`, following that file's existing `build_report` call style:

```python
def test_build_report_passes_measures_through_to_the_card() -> None:
    """One parameter, threaded rather than recomputed: the report layer must not
    reach back into the comparison for figures it was handed."""
    measures = {
        "emberkin-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=1, name="Meteor", ours=2.0, their_median=9.0,
                            their_rates=(9.0,), stretch=Stretch.BOSS, verdict=Verdict.BELOW),
            ),
            boss_seconds=600.0,
        )
    }

    report = build_report(..., comparison_measures=measures)  # that file's own call, plus this argument

    card = next(c for c in report.players if c.slug == "emberkin-0")
    assert [t.heading for t in card.comparison_tables] == ["Casts on boss pulls"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/domain/report/test_build_frame.py -q`
Expected: FAIL — `build_report() got an unexpected keyword argument 'comparison_measures'`.

- [ ] **Step 3: Thread the parameter**

In `src/wowperf/domain/report/build.py`, add `comparison_measures: Mapping[str, PlayerMeasures] = NO_MEASURES` to `build_report`'s defaulted tail, and pass it to `build_players` as `measures=comparison_measures`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/domain/report/test_build_frame.py -q`
Expected: PASS.

- [ ] **Step 5: Call it from the CLI and write the JSON key**

In `src/wowperf/cli.py`, after the `findings += compare(...)` line:

```python
            tables = comparison_measures(ours=loaded, subjects=subjects)
```

Initialise `tables: dict[str, PlayerMeasures] = {}` beside the other pre-comparison locals so the `--no-compare` path has one. Pass `comparison_measures=tables` to `build_report`. Add to `payload`, directly after `"findings"`:

```python
        "comparison_tables": {
            slug: measured.model_dump(mode="json") for slug, measured in tables.items()
        },
```

Add the import:

```python
from wowperf.domain.comparison.tables import comparison_measures
```

- [ ] **Step 6: Write the JSON test**

Add to `tests/test_cli.py`, following its existing style for asserting on a written findings file:

```python
def test_the_findings_file_carries_the_tables_outside_the_ranked_list() -> None:
    """The table is evidence, not a finding: it must not enter the ranked array,
    where every entry is a claim with a badge and a place in the order."""
    payload = json.loads(written_findings_file().read_text(encoding="utf-8"))

    assert "comparison_tables" in payload
    assert all(not f["id"].startswith("compare.spells.table") for f in payload["findings"])
```

- [ ] **Step 7: Run the full gate and commit**

Run: `uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/build.py src/wowperf/cli.py tests/domain/report/test_build_frame.py tests/test_cli.py
git commit -F - <<'MSG'
Carry the measured figures to the page and the findings file

One threaded parameter rather than a second reach into the comparison from
the report layer, and a sibling key in the findings file rather than an entry
in the ranked array. The table is evidence: every entry in that array is a
claim with a badge and a place in the order, and this is neither.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 7: Render it

**Files:**
- Modify: `src/wowperf/adapters/render/_players.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_html_invariants.py`

**Interfaces:**
- Consumes: `PlayerCard.comparison_tables` (Task 5), the `ability(ability_id, name, tooltip=None)` macro in `_macros.html.j2`.
- Produces: no Python interface. The rendered `<details class="compared">` blocks.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/render/test_html_invariants.py`:

```python
def test_a_comparison_table_renders_collapsed_and_adds_no_script() -> None:
    """`<details>` is native HTML. The page is allowed exactly one inline script
    and that script may only show, hide and highlight what is already there, so a
    collapsible built from a second script would break the invariant above."""
    html = rich_html()

    assert "<details class=\"compared\"" in html
    assert html.count("<script") == 1


def test_every_compared_row_reaches_the_page() -> None:
    html = rich_html()
    for card in a_report(players=(a_player_card(),)).players:
        for table in card.comparison_tables:
            assert escape(table.caption) in html
            for row in table.rows:
                assert escape(row.name) in html
```

Give `a_player_card()` in that file a `comparison_tables` argument defaulting to one `ComparisonTable` with two rows, so `rich_html()` renders it. `test_the_richer_fixture_actually_exercises_what_it_claims_to` guards that fixture against going vacuous; add an assertion for the table there too, following its existing lines.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/render/test_html_invariants.py -q`
Expected: FAIL on the missing `<details class="compared"`.

- [ ] **Step 3: Render the tables**

In `_players.html.j2`, after the `spell_and_talent_rows` block and inside the card `div`:

```jinja
  {% for table in player.comparison_tables %}
  <details class="compared">
    <summary>{{ table.heading }}</summary>
    <p class="sub">{{ table.caption }}</p>
    <table class="compared-rows">
      <thead>
        <tr><th scope="col">Ability</th><th scope="col">Ours</th>
            <th scope="col">Median</th><th scope="col">Range</th>
            <th scope="col">Sample</th></tr>
      </thead>
      <tbody>
      {% for row in table.rows %}
        <tr class="v-{{ row.verdict }}">
          <td>{{ ability(row.ability_id, row.name) }}</td>
          <td class="num">{{ row.ours }}</td>
          <td class="num">{{ row.theirs }}</td>
          <td class="num">{{ row.spread }}</td>
          <td>{{ row.sample }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </details>
  {% endfor %}
```

Import the macro at the top of the file, beside the two already imported:

```jinja
{% from "_macros.html.j2" import ability with context %}
```

- [ ] **Step 4: Add the styling**

Append to `report.css.j2`:

```css
/* Collapsed by default and opened by the reader: `<details>` is native, so the
   page's one script stays the only script and still only shows and hides. */
.compared { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 8px; }
.compared > summary { cursor: pointer; color: var(--ink-dim); font-size: 13px; }
.compared-rows { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 12px; }
.compared-rows th { text-align: left; color: var(--ink-faint); font-weight: 500;
  padding: 4px 6px; border-bottom: 1px solid var(--line); }
.compared-rows td { padding: 4px 6px; border-bottom: 1px solid var(--line); }
.compared-rows .num { text-align: right; font-variant-numeric: tabular-nums; }
/* The verdict is a word in the markup and a tint here, never a colour alone.
   --ours and --theirs are the palette the report already uses for the two sides
   of a comparison, so this table tints the way the drawings above it do. */
.compared-rows tr.v-below td:nth-child(2) { color: var(--theirs); }
.compared-rows tr.v-above td:nth-child(2) { color: var(--ours); font-weight: 500; }
.compared-rows tr.v-unjudged td { color: var(--ink-faint); }
```

Every token above is one `report.css.j2` already defines: `--line`, `--ink`, `--ink-dim`, `--ink-faint`, `--ours`, `--theirs`. Checked 2026-09-13; check again before pasting rather than trusting this line.

- [ ] **Step 5: Run the render suite**

Run: `uv run pytest tests/adapters/render -q`
Expected: PASS, including `test_no_element_id_appears_twice`, `test_the_page_loads_no_image_over_the_network` and `test_the_page_executes_only_its_own_script`.

- [ ] **Step 6: Measure the page**

Render a real run and compare the file size against the same run before this task:

```bash
uv run wowperf analyze "<report url>" --player <name> --all-players
```

Record the before and after byte counts. Design §12 question 1: if the growth is large, change the template to draw an icon only where `row.ability_id in icons_by_id` already holds, which the `ability` macro does on its own, and record the measured figures in the commit message either way.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/adapters/render/_players.html.j2 src/wowperf/adapters/render/report.css.j2 tests/adapters/render/test_html_invariants.py
git commit -F - <<'MSG'
Put the measured figures on the page, collapsed

Native details elements rather than a toggle of our own: the page is allowed
exactly one inline script, that script may only show and hide what is already
rendered, and a second one would break the invariant the whole report rests
on.

The verdict rides in the markup as a word and is tinted from it, so a reader
who cannot separate the colours still has the column.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

### Task 8: Prove the table and the findings cannot disagree

The test the design's §8 rests on, then a real run.

**Files:**
- Modify: `tests/domain/comparison/test_tables.py`
- Modify: `tests/e2e/test_compare_e2e.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the anti-drift test**

Add to `tests/domain/comparison/test_tables.py`:

```python
def test_every_rate_finding_has_a_table_row_stating_the_same_figures() -> None:
    """The property the table's honesty rests on. Both are projections of one
    measurement, so this cannot fail while that holds -- and it is the test that
    would catch a later change reintroducing a second computation."""
    sample = ParseSample(
        members=tuple(a_shared_pack_member(code) for code in ("REF1", "REF2", "REF3"))
    )
    ours = a_run_sharing_a_pack()
    subject = ComparisonSubject(
        player=OURS, slug=OUR_SLUG, display_name=OURS.name, parse=sample
    )

    findings = compare(ours, None, (subject,))
    measures = comparison_measures(ours, (subject,))[OUR_SLUG]

    by_name = {m.name: m for m in measures.boss + measures.trash}
    rate_rows = [
        f for f in findings
        if f.ability_name and (".rate." in f.id or ".above." in f.id)
    ]
    assert rate_rows, "no rate finding to check against"
    for finding in rate_rows:
        measured = by_name[finding.ability_name]
        assert f"{measured.ours:.1f}" in finding.title
        assert f"{measured.their_median:.1f}" in finding.title
```

- [ ] **Step 2: Run it, then prove it could fail**

Run: `uv run pytest tests/domain/comparison/test_tables.py -q`

It passes on first writing. Multiply `our_rate` by 2 inside `trash_rate_measures` only and confirm this test FAILS while the trash finding tests still pass — that is precisely the drift it exists to catch. Restore and confirm PASS.

- [ ] **Step 3: Write the end-to-end test**

Add to `tests/e2e/test_compare_e2e.py`, following that file's conventions:

```python
@pytest.mark.e2e
def test_a_real_run_measures_more_than_it_reports(tmp_path: Path) -> None:
    """Offline fixtures compare a handful of abilities. Only a real run shows
    whether the table holds the abilities the rows are silent about."""
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    # Build `loaded`, `subject`, `subject_slug`, `subject_name` and `parse_sample`
    # exactly as test_a_real_run_compares_trash_packs_against_real_parses does, then:
    subjects = (
        ComparisonSubject(
            player=subject, slug=subject_slug, display_name=subject_name, parse=parse_sample
        ),
    )
    findings = compare(loaded, speed_sample, subjects)
    measures = comparison_measures(loaded, subjects)[subject_slug]

    named_in_rows = {f.ability_name for f in findings if f.ability_name}
    measured = {m.name for m in measures.boss + measures.trash}
    assert measured - named_in_rows, (
        "every measured ability produced a row, so the table adds nothing on this run"
    )
    assert measures.auras, "a real parse sample should carry aura data"
```

- [ ] **Step 4: Run it**

Run: `WOWPERF_E2E_REPORT="<a public M+ report URL>" uv run pytest -m e2e tests/e2e/test_compare_e2e.py -q`

This spends API quota. The budget is 3600 points an hour and a cold compared analysis cost about 83 on the one run measured. Run it once, not in a loop.

- [ ] **Step 5: Read the real output**

```bash
uv run wowperf analyze "<report url>" --player <name>
```

Read `out/<code>-<fight>.findings.json`, not the HTML. Check that every ability named in a rate row appears in `comparison_tables` with the same two figures, that the aura table holds the auras the `unjudged` row names, and that no table row states a figure no finding would recognise.

- [ ] **Step 6: Commit**

```bash
git add tests/domain/comparison/test_tables.py tests/e2e/test_compare_e2e.py
git commit -F - <<'MSG'
Hold the table and the rows to the same figures

The property the table's honesty rests on, asserted rather than assumed.
Both are projections of one measurement so it cannot fail while that holds,
which is exactly why it is worth pinning: a later change that reintroduced a
second computation would break this and nothing else.

The end-to-end test asserts the table holds abilities no row names. If it
ever stops doing so, the rows have grown to cover everything measured and
the table has no reason to exist.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Self-Review

**Spec coverage.**

| Spec section | Task |
| --- | --- |
| §1 a table per compared player, every measured ability and aura | 4, 5, 7 |
| §2 the silence it answers | no task — motivation |
| §3 measurement separated from finding, one definition | 1, 2, 3 |
| §3 `verdict` computed with the finding, not re-derived | 1 (`verdict_for`), 3 |
| §4 `compare()` keeps its signature; a function beside it | 4 |
| §4 threaded to `PlayerCard` | 6 |
| §5 row fields, formatted strings, sorted by absolute difference | 5 |
| §6 three tables, each captioned with its denominator | 5 |
| §7 collapsed in `<details>`, no script | 7 |
| §7 page size measured | 7 (step 6) |
| §8 one badge per table, in the caption | 5 (caption text ends "Derived.") |
| §8 never contradicts a finding | 8 |
| §9 not a finding, not ranked, sibling JSON key | 6 |
| §10 approaches rejected | no task — rationale |
| §11 unit, integration, HTML, e2e | 1–5, 6, 7, 8 |
| §12 question 1 icon volume | 7 (step 6) |
| §12 questions 2, 3, 4 | 3 (auras below the floor are absent), 4 (every compared player), 5 (one count per row) |

**Deviation from the spec, recorded.** §4 names the function `comparison_tables()` returning `ComparisonTable`. `ComparisonTable` is a view model in `report/model.py`, and `comparison/` importing `report/` inverts the layering. The function is therefore `comparison_measures()` returning `PlayerMeasures`, and the view model is built in `report/players.py`. The findings file's key keeps the name `comparison_tables`, which is what a reader of that file would look for.

**Placeholders.** Task 2 step 3, Task 4 step 3 and Task 8 step 3 each describe a body to be written by reading a named counterpart rather than reproducing it. Each names the exact function to copy the guards from, and Task 8's anti-drift test is the net under all three. No step defers a decision.

**Type consistency.** `Verdict` and `Stretch` are used in Tasks 1, 2, 3, 4, 5 and 6 with the members defined in Task 1. `AbilityRate.their_rates` and `AuraUptime.their_fractions` are `tuple[float, ...]` throughout and are passed to `observed_range` and `median` unwrapped: both take a `Sequence[float]`, which a tuple is. `PlayerMeasures` is produced in Task 4 and consumed in Tasks 5 and 6 under the parameter name `measures` in `build_players` and `comparison_measures` in `build_report`. `build_players`'s new parameter is last and defaulted, so every existing call site keeps working untouched.
