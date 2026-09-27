# Wipe damage pace, slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On `raid --fight N` for a wipe, compare the raid's cumulative damage to the boss against the reference kills over the same elapsed seconds, project a kill time from damage pace, draw both on the Damage tab, and point at a "behind" reading from the Summary.

**Architecture:** One pure arithmetic module (`pace_curve.py`) turns boss-only damage series into a per-second band reading; `pace.py` turns that reading into two findings or a withheld notice; `pace_chart.py` turns the same reading into inline SVG coordinates, so findings and chart cannot disagree. An adapter module fetches our boss's actor, our boss-only graph, and each reference kill's boss-only graph, reusing the mechanics comparison's reference kills. `analyse_encounter` gains the analyser; `build_raid_report` gains the chart and the Summary pointer.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, httpx `MockTransport` in adapter tests, typer `CliRunner`, pytest. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-27-wipe-damage-pace-design.md`. Read it before Task 1. Slices 2 and 3 of that design are not in this plan.

## Global Constraints

- Only on a wipe. On a kill nothing is fetched and nothing is emitted; the page is unchanged (spec §4, §7).
- Only with the comparison on. `--no-compare` fetches no pace data and emits no pace notice (the existing `NO_COMPARISON_RAN` line covers it).
- References are exactly the mechanics comparison's members: `tuple(member.row for member in mechanics_sample.members)`. No new selection rule (spec §4).
- Boss actor rule: `subType == "Boss"` **and** `name ==` the fight's name; anything but exactly one match withholds (spec §4). The NPC actor query uses `masterData(translate: true)` because `Encounter.boss_name` comes from `fights(translate: true)`.
- Band from at least `MIN_SAMPLE_FOR_AGGREGATE` (3) references still fighting at a second; below 3 references overall, fall back to the slowest kill (spec §5).
- States: behind below the band's lowest, ahead above its highest, on pace otherwise. Only behind warns (spec §5, §7).
- "Behind from T" is the start of the final unbroken behind stretch ending at the last compared second. An earlier stretch is mentioned only when it lasted **longer than** the widest reference bucket in seconds (spec §5).
- Projection: our total boss damage over the whole wipe / wipe duration; target the median of the references' totals at their own ends; withheld under `MIN_ATTEMPT_SECONDS` (44 s, `wowperf.domain.progression`) or at zero damage. It never prints a rate (spec §6).
- Badges: `compare.pace.boss` `derived`; `compare.pace.projection` `inferred`; notice `compare.pace.unavailable` to Provenance only (spec §5-§7).
- No raw damage figure on the page or in a finding: shares of the kills' median, and times (spec §3, §7).
- Nothing persisted names or tabulates a reference: a `ReferenceRecord` carries a link and never a figure (`domain/report/model.py:634`); findings state only the median and range of the references' durations and shares.
- `src/wowperf/domain/` performs no I/O. The report's one inline script is untouched; the chart is markup.
- Never invent an API field. Every field used is recorded in `.claude/skills/wcl-api/SKILL.md` ("A damage graph can be scoped to the boss, and the boss is found by `subType` and name", 2026-09-27; `fights(fightIDs:)`, `startTime`, `endTime`, `masterData`, `actors` are already in `queries.py`).
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). NPC names in fixtures are invented (e.g. `"The Test Colossus"`). Players on `cW38jmwdnZfbHVL4` and `6Kx1P9GbNXrcLdHa` are referred to by class, spec, role or index only -- never by name, slug or raw finding id, anywhere.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test.
- Every new code file starts with two `ABOUTME: ` lines. Comments evergreen.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy` (strict over `tests/` too), `uv run pytest` -- green, output pristine.

---

### Task 1: The pace arithmetic

**Files:**
- Create: `src/wowperf/domain/comparison/pace_curve.py`
- Test: `tests/domain/comparison/test_pace_curve.py`

**Interfaces:**
- Produces: `BossDamage`, `PaceReference`, `PaceState`, `PaceSecond`, `PaceReading`, `cumulative_at(series: BossDamage, second: float) -> float`, `read_pace(ours: BossDamage, references: tuple[PaceReference, ...], duration_seconds: float) -> PaceReading | None`, `behind_stretches(reading: PaceReading) -> tuple[tuple[int, int], ...]`, `final_behind_start(reading: PaceReading) -> int | None`, `earlier_behind(reading: PaceReading) -> tuple[tuple[int, int], ...]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_pace_curve.py`:

```python
# ABOUTME: Cumulative boss damage per second and the kills' band around it.
# ABOUTME: Pins the interpolation, the band, its cut, the fallback and the behind stretches.

import pytest

from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReference,
    PaceState,
    behind_stretches,
    cumulative_at,
    earlier_behind,
    final_behind_start,
    read_pace,
)


def steady(per_second: int, seconds: int, *, interval_ms: float = 1000.0) -> BossDamage:
    """A constant rate, cut into buckets of `interval_ms`."""
    buckets = int(seconds * 1000 / interval_ms)
    return BossDamage(
        interval_ms=interval_ms,
        amounts=tuple(int(per_second * interval_ms / 1000) for _ in range(buckets)),
    )


def a_kill(per_second: int, seconds: int, *, interval_ms: float = 2000.0) -> PaceReference:
    return PaceReference(
        duration_seconds=float(seconds), damage=steady(per_second, seconds, interval_ms=interval_ms)
    )


def test_cumulative_takes_the_covered_fraction_of_the_straddling_bucket() -> None:
    series = BossDamage(interval_ms=2000.0, amounts=(100, 300, 500))
    assert cumulative_at(series, 0) == 0.0
    assert cumulative_at(series, 1) == pytest.approx(50.0)
    assert cumulative_at(series, 3) == pytest.approx(250.0)
    assert cumulative_at(series, 6) == pytest.approx(900.0)
    assert cumulative_at(series, 60) == pytest.approx(900.0)


def test_a_grid_starting_late_reads_nothing_before_its_start() -> None:
    series = BossDamage(lead_ms=1000, interval_ms=1000.0, amounts=(100, 100))
    assert cumulative_at(series, 1) == 0.0
    assert cumulative_at(series, 2) == pytest.approx(100.0)


def test_the_band_is_the_lowest_median_and_highest_of_the_kills() -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    at_ten = reading.seconds[9]
    assert at_ten.second == 10
    assert (at_ten.low, at_ten.median, at_ten.high) == pytest.approx((900.0, 1000.0, 1300.0))
    assert at_ten.ours == pytest.approx(1000.0)
    assert at_ten.state is PaceState.ON_PACE


@pytest.mark.parametrize(
    ("ours_per_second", "state"),
    [(80, PaceState.BEHIND), (100, PaceState.ON_PACE), (140, PaceState.AHEAD)],
)
def test_the_three_states(ours_per_second: int, state: PaceState) -> None:
    kills = (a_kill(90, 60), a_kill(100, 60), a_kill(130, 60))
    reading = read_pace(steady(ours_per_second, 30), kills, 30.0)
    assert reading is not None
    assert reading.seconds[-1].state is state


def test_the_band_stops_where_fewer_than_three_kills_are_still_fighting() -> None:
    """Two kills end at 20 s: from second 21 only two remain."""
    kills = (a_kill(100, 20), a_kill(100, 20), a_kill(100, 60), a_kill(100, 60))
    reading = read_pace(steady(100, 40), kills, 40.0)
    assert reading is not None
    assert reading.seconds[-1].second == 20
    assert reading.band_cut is True
    assert reading.single is False
    assert reading.references == 4


def test_a_wipe_shorter_than_every_kill_is_compared_to_its_end() -> None:
    kills = (a_kill(100, 60), a_kill(100, 60), a_kill(100, 60))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    assert reading.seconds[-1].second == 30
    assert reading.band_cut is False


def test_below_three_references_the_slowest_kill_stands_alone() -> None:
    """The slowest kill deals least per second, so it is the lenient comparison."""
    fast, slow = a_kill(200, 30), a_kill(100, 60)
    reading = read_pace(steady(150, 40), (fast, slow), 40.0)
    assert reading is not None
    assert reading.single is True
    assert reading.references == 2
    last = reading.seconds[-1]
    assert last.low == last.median == last.high == pytest.approx(4000.0)
    assert last.state is PaceState.AHEAD
    assert reading.target == pytest.approx(6000.0)


def test_the_single_kill_ending_first_cuts_the_comparison() -> None:
    reading = read_pace(steady(100, 40), (a_kill(100, 25),), 40.0)
    assert reading is not None
    assert reading.seconds[-1].second == 25
    assert reading.band_cut is True


def test_no_reference_reads_nothing() -> None:
    assert read_pace(steady(100, 30), (), 30.0) is None


def test_the_target_is_the_median_of_the_kills_totals_at_their_own_ends() -> None:
    kills = (a_kill(100, 50), a_kill(100, 60), a_kill(100, 70))
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    assert reading.target == pytest.approx(6000.0)
    assert reading.reference_durations == (50.0, 60.0, 70.0)


def test_the_widest_bucket_is_the_coarsest_reference_grid() -> None:
    kills = (
        a_kill(100, 60, interval_ms=1000.0),
        a_kill(100, 60, interval_ms=3000.0),
        a_kill(100, 60, interval_ms=2000.0),
    )
    reading = read_pace(steady(100, 30), kills, 30.0)
    assert reading is not None
    assert reading.widest_bucket_seconds == pytest.approx(3.0)


def a_behind_pattern(pattern: str) -> tuple[BossDamage, tuple[PaceReference, ...]]:
    """Ours per second from a string, against three kills dealing 100 a second.

    'b' deals 0 (the gap to the band widens by 100), '.' deals 100 (the gap
    holds), '+' deals 300 (the gap closes by 200). The band is one line at
    100 per second, so a second is behind exactly when the running gap is
    negative -- and each stretch's bounds can be worked out on paper.
    """
    per_mark = {"b": 0, ".": 100, "+": 300}
    ours = BossDamage(interval_ms=1000.0, amounts=tuple(per_mark[mark] for mark in pattern))
    kills = tuple(a_kill(100, 100, interval_ms=1000.0) for _ in range(3))
    return ours, kills


def test_behind_stretches_are_read_as_inclusive_seconds() -> None:
    """Gap by second: -100 -200 0 +200, held to s10, then +100 0 -100 -200."""
    ours, kills = a_behind_pattern("bb++......bbbb")
    reading = read_pace(ours, kills, 14.0)
    assert reading is not None
    assert behind_stretches(reading) == ((1, 2), (13, 14))


def test_t_is_the_start_of_the_final_stretch_not_the_first() -> None:
    ours, kills = a_behind_pattern("bb++......bbbb")
    reading = read_pace(ours, kills, 14.0)
    assert reading is not None
    assert final_behind_start(reading) == 13


def test_no_t_when_the_raid_was_not_behind_at_the_end() -> None:
    """Ends 200 ahead: the early stretch is never mentioned."""
    ours, kills = a_behind_pattern("bb++......")
    reading = read_pace(ours, kills, 10.0)
    assert reading is not None
    assert final_behind_start(reading) is None
    assert earlier_behind(reading) == ()


def test_an_earlier_stretch_counts_only_when_longer_than_the_widest_bucket() -> None:
    """Gap by second: -100 +100 0 -100 -200 0 0 -100 -200.

    Stretches (1, 1), (4, 5) and the final (8, 9). With 1 s reference buckets
    the one-second stretch sits exactly on the bar and is left out; the
    two-second one outlasts it and is kept.
    """
    ours, kills = a_behind_pattern("b+bbb+.bb")
    reading = read_pace(ours, kills, 9.0)
    assert reading is not None
    assert behind_stretches(reading) == ((1, 1), (4, 5), (8, 9))
    assert final_behind_start(reading) == 8
    assert earlier_behind(reading) == ((4, 5),)
```

The gaps in each docstring were worked by hand; if a run disagrees, recheck the arithmetic against `cumulative_at` before touching either side, and fix whichever is wrong.

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/comparison/test_pace_curve.py -v`
Expected: FAIL at import -- `No module named 'wowperf.domain.comparison.pace_curve'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/comparison/pace_curve.py`:

```python
# ABOUTME: Cumulative boss damage second by second, and where one raid's curve sits in the kills' band.
# ABOUTME: Pure arithmetic the pace findings and the pace chart both read, so the two cannot disagree.

from enum import StrEnum
from statistics import median

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE


class BossDamage(Frozen):
    """Damage to one boss per bucket, as the boss-only damage graph cut it.

    `amounts` holds damage, never a rate: the adapter converts the graph's
    per-second figures at the boundary, as it does for `DamageDoneSeries`.
    Bucket `i` covers `lead_ms + i * interval_ms` onward from the fight's start.
    `lead_ms` was measured 0 on every graph read (2026-09-27); it is carried so
    a grid that ever starts late is honoured rather than assumed away.
    """

    interval_ms: float
    amounts: tuple[int, ...] = ()
    lead_ms: int = 0


class PaceReference(Frozen):
    """One reference kill: how long it ran and what it dealt the boss.

    Carries no report code and no name. It lives for one comparison in memory
    and is never written anywhere.
    """

    duration_seconds: float
    damage: BossDamage


class PaceState(StrEnum):
    BEHIND = "behind"
    ON_PACE = "on pace"
    AHEAD = "ahead"


class PaceSecond(Frozen):
    """Our cumulative boss damage at one second, and the kills' band at it."""

    second: int
    ours: float
    low: float
    median: float
    high: float

    @property
    def state(self) -> PaceState:
        if self.ours < self.low:
            return PaceState.BEHIND
        if self.ours > self.high:
            return PaceState.AHEAD
        return PaceState.ON_PACE


class PaceReading(Frozen):
    """Every compared second of one wipe against its reference kills.

    `single` is the fallback below three references: the band is the slowest
    kill alone. `band_cut` says the comparison stopped before the wipe because
    too few kills were still fighting. `target` is the kills' median total boss
    damage at their own ends -- the slowest kill's alone under the fallback.
    """

    seconds: tuple[PaceSecond, ...]
    references: int
    single: bool
    band_cut: bool
    widest_bucket_seconds: float
    target: float
    reference_durations: tuple[float, ...]


def cumulative_at(series: BossDamage, second: float) -> float:
    """Damage dealt by `second` from the pull: whole buckets, plus the covered part of one."""
    elapsed_ms = second * 1000 - series.lead_ms
    if elapsed_ms <= 0 or series.interval_ms <= 0:
        return 0.0
    whole, fraction = divmod(elapsed_ms / series.interval_ms, 1)
    index = int(whole)
    done = float(sum(series.amounts[:index]))
    if index >= len(series.amounts):
        return done
    return done + series.amounts[index] * fraction


def read_pace(
    ours: BossDamage, references: tuple[PaceReference, ...], duration_seconds: float
) -> PaceReading | None:
    """Our curve against the kills', every whole second from 1 to the wipe.

    With three or more references, each second's band is built from the kills
    still fighting at it, and the reading stops at the last second that had
    three. Below three references the slowest kill stands alone: it dealt least
    per second, so "behind" against it can only understate. None without any
    reference.
    """
    if not references:
        return None
    single = len(references) < MIN_SAMPLE_FOR_AGGREGATE
    band = (max(references, key=lambda one: one.duration_seconds),) if single else references
    needed = 1 if single else MIN_SAMPLE_FOR_AGGREGATE

    seconds: list[PaceSecond] = []
    cut = False
    for second in range(1, int(duration_seconds) + 1):
        fighting = [one for one in band if second <= one.duration_seconds]
        if len(fighting) < needed:
            cut = True
            break
        values = [cumulative_at(one.damage, second) for one in fighting]
        seconds.append(
            PaceSecond(
                second=second,
                ours=cumulative_at(ours, second),
                low=min(values),
                median=median(values),
                high=max(values),
            )
        )

    return PaceReading(
        seconds=tuple(seconds),
        references=len(references),
        single=single,
        band_cut=cut,
        widest_bucket_seconds=max(one.damage.interval_ms for one in band) / 1000,
        target=median(cumulative_at(one.damage, one.duration_seconds) for one in band),
        reference_durations=tuple(sorted(one.duration_seconds for one in band)),
    )


def behind_stretches(reading: PaceReading) -> tuple[tuple[int, int], ...]:
    """Every unbroken run of behind seconds, as inclusive (first, last) pairs."""
    stretches: list[tuple[int, int]] = []
    start: int | None = None
    previous = 0
    for one in reading.seconds:
        if one.state is PaceState.BEHIND:
            if start is None:
                start = one.second
        elif start is not None:
            stretches.append((start, previous))
            start = None
        previous = one.second
    if start is not None:
        stretches.append((start, previous))
    return tuple(stretches)


def final_behind_start(reading: PaceReading) -> int | None:
    """T: where the last stretch began, when it runs to the last compared second."""
    stretches = behind_stretches(reading)
    if not stretches or not reading.seconds:
        return None
    start, end = stretches[-1]
    return start if end == reading.seconds[-1].second else None


def earlier_behind(reading: PaceReading) -> tuple[tuple[int, int], ...]:
    """Stretches before the final one that outlasted the widest reference bucket.

    A shorter dip cannot be told from interpolating across one coarse bucket:
    measured 2026-09-27, every wipe's first ten seconds flickered this way.
    Empty unless the reading ends behind.
    """
    if final_behind_start(reading) is None:
        return ()
    return tuple(
        (start, end)
        for start, end in behind_stretches(reading)[:-1]
        if end - start + 1 > reading.widest_bucket_seconds
    )
```

- [ ] **Step 4: Run, pass, prove**

Run the file: all pass. Prove each guard, one at a time, restoring after each:
- use `amounts[index] * 0` for the fraction -> the straddling-bucket test red;
- build the band from all references instead of those still fighting -> the band-stops test red;
- `needed = MIN_SAMPLE_FOR_AGGREGATE` always -> the single-kill-cut test red;
- pick `min(..., key=duration)` for the fallback -> the slowest-kill test red;
- in `final_behind_start`, return `stretches[0][0]` -> the T test red;
- use `>=` for the earlier-stretch bar -> the earlier-stretch test red (its `(1, 1)` stretch sits exactly on the 1 s bar).

- [ ] **Step 5: Gate and commit**

Full gate. Subject: `Read a wipe's boss damage against the kills' band, second by second`

---

### Task 2: The findings

**Files:**
- Create: `src/wowperf/domain/comparison/pace.py`
- Test: `tests/domain/comparison/test_pace.py`

**Interfaces:**
- Consumes: Task 1's `BossDamage`, `PaceReference`, `PaceReading`, `PaceState`, `read_pace`, `final_behind_start`, `earlier_behind`, `cumulative_at`.
- Produces: `PACE_PREFIX = "compare.pace."`, `PACE_ID = "compare.pace.boss"`, `PROJECTION_ID = "compare.pace.projection"`, `UNAVAILABLE_ID = "compare.pace.unavailable"`; reasons `NO_SINGLE_BOSS`, `NO_BOSS_DAMAGE`, `NO_REFERENCE_KILL`, `BOSS_IN_NO_REFERENCE`; `PaceSample(ours: BossDamage | None = None, references: tuple[PaceReference, ...] = (), unavailable: str = "")`; `analyse_pace(encounter: Encounter, sample: PaceSample) -> list[Finding]`; `pace_reading(encounter: Encounter, sample: PaceSample) -> PaceReading | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_pace.py`. Reuse Task 1's `steady` and `a_kill` by importing them from `tests.domain.comparison.test_pace_curve`, and `an_encounter` from `tests.domain.report.test_raid_frame`.

```python
# ABOUTME: The two pace findings and the notice, from one wipe and its reference kills.
# ABOUTME: Pins the titles, evidence, badges and every withhold the design names.

import re

from tests.domain.comparison.test_pace_curve import a_kill, steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import (
    BOSS_IN_NO_REFERENCE,
    NO_REFERENCE_KILL,
    NO_SINGLE_BOSS,
    PACE_ID,
    PROJECTION_ID,
    UNAVAILABLE_ID,
    PaceSample,
    analyse_pace,
)
from wowperf.domain.comparison.pace_curve import BossDamage
from wowperf.domain.findings import Confidence, Finding

THREE_KILLS = (a_kill(100, 400), a_kill(110, 420), a_kill(120, 440))


def a_wipe(seconds: int) -> object:
    return an_encounter(kill=False, start_ms=0, end_ms=seconds * 1000, fight_percentage=40.0)


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_raid_behind_the_band_is_told_so_with_its_share_and_t() -> None:
    found = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=THREE_KILLS)))
    pace = found[PACE_ID]
    assert pace.title == "Behind the kills' pace: 73% of their median boss damage by 3:20"
    assert pace.confidence is Confidence.DERIVED
    assert pace.evidence[0] == "Against 3 reference kills of this raid size"
    assert pace.evidence[1] == "Their range at 3:20: 91% to 109% of their median"
    assert "Compared through the wipe at 3:20" in pace.evidence
    assert "Behind from 0:01 to 3:20" in pace.evidence


def test_on_pace_and_ahead_carry_no_behind_line() -> None:
    on = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(110, 200), references=THREE_KILLS)))
    ahead = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(150, 200), references=THREE_KILLS)))
    assert on[PACE_ID].title.startswith("On the kills' pace: 100% ")
    assert ahead[PACE_ID].title.startswith("Ahead of the kills' pace: 136% ")
    for finding in (on[PACE_ID], ahead[PACE_ID]):
        assert not any(line.startswith("Behind from") for line in finding.evidence)


def test_the_band_cut_is_stated() -> None:
    kills = (a_kill(100, 100), a_kill(100, 100), a_kill(100, 400), a_kill(100, 400))
    found = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(100, 200), references=kills)))
    assert (
        "Compared through 1:40, after which fewer than three kills were still fighting"
        in found[PACE_ID].evidence
    )


def test_the_fallback_names_the_slowest_kill_and_gives_no_range() -> None:
    kills = (a_kill(200, 300), a_kill(100, 400))
    found = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=kills)))
    pace = found[PACE_ID]
    assert pace.title == "Behind the slowest kill's pace: 80% of its boss damage by 3:20"
    assert pace.evidence[0] == (
        "Against the slowest of 2 reference kills of this raid size: "
        "fewer than three were available"
    )
    assert not any(line.startswith("Their range") for line in pace.evidence)


def test_the_projection_times_the_kills_total_at_our_average_pace() -> None:
    """Target 46200 (median of 40000, 46200, 52800); 80 a second reaches it at 577.5 s."""
    found = by_id(analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=THREE_KILLS)))
    projection = found[PROJECTION_ID]
    assert projection.confidence is Confidence.INFERRED
    assert projection.title == (
        "At its average pace this raid would have dealt the kills' boss damage by about 9:38"
    )
    assert projection.evidence == ("The kills took 6:40 to 7:20, median 7:00",)
    assert "enrage" in projection.detail


def test_a_short_wipe_gets_no_projection_and_says_so() -> None:
    found = by_id(analyse_pace(a_wipe(40), PaceSample(ours=steady(80, 40), references=THREE_KILLS)))
    assert PROJECTION_ID not in found
    assert "No projection: the attempt lasted under 44 seconds" in found[PACE_ID].evidence


def test_zero_boss_damage_gets_no_projection() -> None:
    found = by_id(analyse_pace(a_wipe(100), PaceSample(ours=steady(0, 100), references=THREE_KILLS)))
    assert PROJECTION_ID not in found
    assert found[PACE_ID].title.startswith("Behind the kills' pace: 0% ")
    assert "No projection: the raid dealt the boss no damage" in found[PACE_ID].evidence


def test_a_kill_is_never_compared() -> None:
    kill = an_encounter(kill=True, start_ms=0, end_ms=200_000)
    assert analyse_pace(kill, PaceSample(ours=steady(80, 200), references=THREE_KILLS)) == []


def test_each_withhold_is_one_notice_carrying_its_reason() -> None:
    for sample, reason in (
        (PaceSample(unavailable=NO_SINGLE_BOSS), NO_SINGLE_BOSS),
        (PaceSample(ours=steady(80, 200), unavailable=BOSS_IN_NO_REFERENCE), BOSS_IN_NO_REFERENCE),
        (PaceSample(ours=steady(80, 200)), NO_REFERENCE_KILL),
    ):
        [notice] = analyse_pace(a_wipe(200), sample)
        assert notice.id == UNAVAILABLE_ID
        assert notice.detail == reason


def test_no_finding_prints_a_raw_damage_figure() -> None:
    """Shares and times only: no run of four or more digits anywhere."""
    found = analyse_pace(a_wipe(200), PaceSample(ours=steady(80, 200), references=THREE_KILLS))
    for finding in found:
        for text in (finding.title, finding.detail, *finding.evidence):
            assert not re.search(r"\d{4,}", text), text
```

These expected strings were run against this task's code, and Task 1's, before the plan was committed (2026-09-27, all 27 tests green). If one disagrees now, the code was transcribed differently: diff it against the plan before changing a test.

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/comparison/test_pace.py -v`
Expected: FAIL at import -- `No module named 'wowperf.domain.comparison.pace'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/comparison/pace.py`:

```python
# ABOUTME: A wipe's damage pace against the reference kills, and when that pace would have killed.
# ABOUTME: Two findings or one withheld notice, all read from `pace_curve`'s one reading.

from statistics import median

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReading,
    PaceReference,
    PaceState,
    cumulative_at,
    earlier_behind,
    final_behind_start,
    read_pace,
)
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import MIN_ATTEMPT_SECONDS

PACE_PREFIX = "compare.pace."
PACE_ID = "compare.pace.boss"
PROJECTION_ID = "compare.pace.projection"
UNAVAILABLE_ID = "compare.pace.unavailable"

NO_SINGLE_BOSS = (
    "This fight has no single boss to compare: the report names no one boss actor after the "
    "fight, which is what a council encounter looks like."
)
NO_BOSS_DAMAGE = "The damage graph for this boss held no series to compare."
NO_REFERENCE_KILL = "No reference kill of this raid size could be loaded to compare against."
BOSS_IN_NO_REFERENCE = "This boss could not be found in any reference kill's fight."

BOSS_DETAIL = (
    "Cumulative damage to the boss, second by second from the pull, against the reference "
    "kills over the same seconds, both sides read from the same boss-only damage graph. "
    "Behind means below the kill that had dealt least by that second; ahead, above the one "
    "that had dealt most. Each graph is read within its own buckets, so a dip shorter than "
    "the coarsest bucket is not reported."
)
PROJECTION_DETAIL = (
    "Assumes the raid's average damage to the boss would have held for the rest of the "
    "fight. Phases, intermissions and a shrinking raid all break that, and a wipe is where "
    "the raid shrank. This is damage pace, not a forecast of the boss's health, and it says "
    "nothing about an enrage timer, for which this tool has no data."
)


class PaceSample(Frozen):
    """What the pace comparison was given: our boss damage and the kills', or why neither.

    `unavailable` is set exactly when nothing can be compared, and names why.
    """

    ours: BossDamage | None = None
    references: tuple[PaceReference, ...] = ()
    unavailable: str = ""


def _clock(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def _share(value: float, of: float) -> int:
    return round(100 * value / of)


def pace_reading(encounter: Encounter, sample: PaceSample) -> PaceReading | None:
    """The one reading both the findings and the chart draw from, or None."""
    if encounter.kill or sample.unavailable or sample.ours is None:
        return None
    return read_pace(sample.ours, sample.references, encounter.duration_seconds)


def _notice(reason: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID,
        title="Damage pace against other kills was not compared",
        detail=reason,
        confidence=Confidence.MEASURED,
    )


def analyse_pace(encounter: Encounter, sample: PaceSample) -> list[Finding]:
    """`compare.pace.boss` and `compare.pace.projection`, or the notice saying why not.

    A kill is never compared: kills have the parse comparison. The notice is
    badged `measured` because what it states -- that a lookup found nothing --
    is a plain reading, and Provenance draws it rather than the Damage tab.
    """
    if encounter.kill:
        return []
    if sample.unavailable or sample.ours is None:
        return [_notice(sample.unavailable or NO_BOSS_DAMAGE)]
    reading = pace_reading(encounter, sample)
    if reading is None:
        return [_notice(NO_REFERENCE_KILL)]
    if not reading.seconds or reading.seconds[-1].median <= 0:
        return []

    total = cumulative_at(sample.ours, encounter.duration_seconds)
    withheld_projection = ""
    if encounter.duration_seconds < MIN_ATTEMPT_SECONDS:
        withheld_projection = (
            f"No projection: the attempt lasted under {int(MIN_ATTEMPT_SECONDS)} seconds"
        )
    elif total <= 0:
        withheld_projection = "No projection: the raid dealt the boss no damage"

    findings = [_pace_finding(reading, withheld_projection)]
    if not withheld_projection:
        findings.append(_projection(reading, total, encounter.duration_seconds))
    return findings


def _pace_finding(reading: PaceReading, withheld_projection: str) -> Finding:
    last = reading.seconds[-1]
    clock = _clock(last.second)
    against = "the slowest kill's" if reading.single else "the kills'"
    of = "its boss damage" if reading.single else "their median boss damage"
    lead = {
        PaceState.BEHIND: f"Behind {against} pace",
        PaceState.ON_PACE: f"On {against} pace",
        PaceState.AHEAD: f"Ahead of {against} pace",
    }[last.state]

    evidence: list[str] = []
    if reading.single:
        evidence.append(
            "Against the one reference kill of this raid size: fewer than three were available"
            if reading.references == 1
            else f"Against the slowest of {reading.references} reference kills of this raid "
            "size: fewer than three were available"
        )
    else:
        evidence.append(f"Against {reading.references} reference kills of this raid size")
        evidence.append(
            f"Their range at {clock}: {_share(last.low, last.median)}% to "
            f"{_share(last.high, last.median)}% of their median"
        )
    if not reading.band_cut:
        evidence.append(f"Compared through the wipe at {clock}")
    elif reading.single:
        evidence.append(f"Compared through {clock}, when the reference kill ended")
    else:
        evidence.append(
            f"Compared through {clock}, after which fewer than three kills were still fighting"
        )
    start = final_behind_start(reading)
    if start is not None:
        evidence.append(f"Behind from {_clock(start)} to {clock}")
        evidence.extend(
            f"Also behind between {_clock(first)} and {_clock(end)}"
            for first, end in earlier_behind(reading)
        )
    if withheld_projection:
        evidence.append(withheld_projection)

    return Finding(
        id=PACE_ID,
        title=f"{lead}: {_share(last.ours, last.median)}% of {of} by {clock}",
        detail=BOSS_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(evidence),
    )


def _projection(reading: PaceReading, total: float, duration_seconds: float) -> Finding:
    projected = reading.target / (total / duration_seconds)
    whose = "the slowest kill's" if reading.single else "the kills'"
    durations = reading.reference_durations
    if reading.single:
        evidence = (f"The reference kill took {_clock(durations[0])}",)
    else:
        evidence = (
            f"The kills took {_clock(durations[0])} to {_clock(durations[-1])}, "
            f"median {_clock(median(durations))}",
        )
    return Finding(
        id=PROJECTION_ID,
        title=(
            f"At its average pace this raid would have dealt {whose} boss damage by about "
            f"{_clock(projected)}"
        ),
        detail=PROJECTION_DETAIL,
        confidence=Confidence.INFERRED,
        evidence=evidence,
    )
```

- [ ] **Step 4: Run, pass, prove**

Run the file: all pass. Prove, restoring after each:
- `if encounter.kill: return []` removed -> the kill test red;
- `< MIN_ATTEMPT_SECONDS` changed to `< 0` -> the short-wipe test red;
- `reading.single` ignored in the title -> the fallback test red;
- `earlier_behind` lines dropped -> add a test with an earlier stretch longer than the bar (use Task 1's `a_behind_pattern` idea with 1 s reference buckets) asserting its `Also behind between` line, and prove it red;
- the projection's target taken as `max` of the kills' totals -> the projection test red.

- [ ] **Step 5: Gate and commit**

Full gate. Subject: `Say whether a wipe was on the kills' pace, and project its kill time`

---

### Task 3: Fetch the boss damage

**Files:**
- Create: `src/wowperf/domain/comparison/pace_boss.py`
- Create: `src/wowperf/adapters/wcl/pace.py`
- Modify: `src/wowperf/adapters/wcl/queries.py` (three queries beside `DAMAGE_DONE_GRAPH_QUERY`)
- Modify: `src/wowperf/adapters/wcl/ingest.py` (three builders beside `build_damage_done`)
- Test: `tests/domain/comparison/test_pace_boss.py`, `tests/adapters/wcl/test_pace.py`, and `tests/adapters/wcl/test_queries.py` if it enumerates queries

**Interfaces:**
- Consumes: Task 1's `BossDamage`, `PaceReference`; Task 2's `PaceSample`, `NO_SINGLE_BOSS`, `NO_BOSS_DAMAGE`, `NO_REFERENCE_KILL`, `BOSS_IN_NO_REFERENCE`.
- Produces: `NpcActor(actor_id, game_id, name, sub_type)`, `find_boss_actor(actors: tuple[NpcActor, ...], fight_name: str) -> NpcActor | None`; queries `NPC_ACTORS_QUERY`, `REFERENCE_FIGHT_QUERY`, `BOSS_DAMAGE_GRAPH_QUERY`; `build_npc_actors(payload) -> tuple[NpcActor, ...]`, `build_reference_fight(payload) -> ReferenceFight | None`, `build_boss_damage(payload, *, fight_start_ms: int) -> BossDamage | None`; `load_pace_sample(client: WclClient, own_cache: DiskCache, reference_cache: DiskCache, encounter: Encounter, references: tuple[ReferenceKillRow, ...]) -> tuple[PaceSample, tuple[ReferenceRecord, ...]]`.

- [ ] **Step 1: The boss rule, test first**

`tests/domain/comparison/test_pace_boss.py`:

```python
# ABOUTME: Which enemy actor is the boss: flagged a boss and named after the fight, exactly one.
# ABOUTME: Pins the same-named non-boss, the boss-framed adds, and a council.

from wowperf.domain.comparison.pace_boss import NpcActor, find_boss_actor

FIGHT = "The Test Colossus"


def actor(actor_id: int, name: str, sub_type: str, game_id: int = 900) -> NpcActor:
    return NpcActor(actor_id=actor_id, game_id=game_id, name=name, sub_type=sub_type)


def test_the_one_boss_named_after_the_fight_is_the_boss() -> None:
    actors = (
        actor(57, FIGHT, "Boss"),
        actor(58, "Colossal Rattle", "Boss", 901),
        actor(59, "Colossal Heart", "Boss", 902),
        actor(60, FIGHT, "NPC", 903),
    )
    boss = find_boss_actor(actors, FIGHT)
    assert boss is not None and boss.actor_id == 57


def test_a_council_names_no_boss_after_the_fight() -> None:
    actors = (actor(10, "First Warden", "Boss"), actor(11, "Second Warden", "Boss", 901))
    assert find_boss_actor(actors, "The Wardens") is None


def test_two_bosses_named_after_the_fight_are_not_one_boss() -> None:
    actors = (actor(10, FIGHT, "Boss"), actor(11, FIGHT, "Boss", 901))
    assert find_boss_actor(actors, FIGHT) is None
```

`src/wowperf/domain/comparison/pace_boss.py`:

```python
# ABOUTME: Picks the boss out of a report's enemy actors, by its boss flag and the fight's name.
# ABOUTME: Anything but exactly one match is no boss, which is what a council encounter reads as.

from wowperf.domain.base import Frozen

BOSS_SUB_TYPE = "Boss"


class NpcActor(Frozen):
    """One enemy actor of a report, as `masterData.actors(type: "NPC")` lists it."""

    actor_id: int
    game_id: int
    name: str
    sub_type: str


def find_boss_actor(actors: tuple[NpcActor, ...], fight_name: str) -> NpcActor | None:
    """The one actor flagged a boss and named after the fight, or None.

    Both halves are needed, measured 2026-09-27: the flag alone also marks adds
    that carry a boss frame, and the name alone also matches a same-named actor
    flagged `NPC` that took no damage.
    """
    matches = [
        one for one in actors if one.sub_type == BOSS_SUB_TYPE and one.name == fight_name
    ]
    return matches[0] if len(matches) == 1 else None
```

Run, pass; prove: drop the `sub_type` half -> first test red; drop the name half -> first and council tests red; return `matches[0] if matches` -> the two-bosses test red.

- [ ] **Step 2: The queries**

In `queries.py`, beside `DAMAGE_DONE_GRAPH_QUERY`, add (read the file first and match its comment style; each query gets a comment saying what it is for and pointing at the wcl-api skill section of 2026-09-27):

```python
NPC_ACTORS_QUERY = """
query NpcActors($code: String!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      masterData(translate: true) {
        actors(type: "NPC") { id gameID name subType }
      }
    }
  }
}
"""

REFERENCE_FIGHT_QUERY = """
query ReferenceFight($code: String!, $fightId: Int!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      fights(fightIDs: [$fightId]) {
        id
        startTime
        endTime
        enemyNPCs { id gameID }
      }
    }
  }
}
"""

BOSS_DAMAGE_GRAPH_QUERY = """
query BossDamageGraph(
  $code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!, $targetId: Int!
) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      graph(
        dataType: DamageDone
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        targetID: $targetId
      )
    }
  }
}
"""
```

`masterData(translate: true)` is required: `Encounter.boss_name` is read from `fights(translate: true)`, and the rule compares the two names. If `tests/adapters/wcl/test_queries.py` checks every query (names, variables, or a schema snapshot), extend it for the three; read it first.

- [ ] **Step 3: The builders, test first**

In `tests/adapters/wcl/test_pace.py`, test each builder on a hand-written payload shaped as the wcl-api skill records it (series `id` is an int per player and the string `"Total"` for the sum; points are damage per second):

```python
def test_the_total_series_becomes_boss_damage_converted_from_its_rate() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": 7, "name": "Emberkin", "pointStart": 5000, "pointInterval": 2000.0,
         "data": [10.0, 20.0]},
        {"id": "Total", "name": "Total", "pointStart": 5000, "pointInterval": 2000.0,
         "data": [15.0, 25.0, 5.0]},
    ]}}}}}
    damage = build_boss_damage(payload, fight_start_ms=5000)
    assert damage == BossDamage(interval_ms=2000.0, amounts=(30, 50, 10), lead_ms=0)


def test_a_graph_without_a_total_series_is_no_boss_damage() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": 7, "pointStart": 0, "pointInterval": 1000.0, "data": [1.0]},
    ]}}}}}
    assert build_boss_damage(payload, fight_start_ms=0) is None


def test_a_late_grid_keeps_its_lead() -> None:
    payload = {"reportData": {"report": {"graph": {"data": {"series": [
        {"id": "Total", "pointStart": 6000, "pointInterval": 1000.0, "data": [1.0]},
    ]}}}}}
    damage = build_boss_damage(payload, fight_start_ms=5000)
    assert damage is not None and damage.lead_ms == 1000


def test_npc_actors_are_read_with_their_boss_flag() -> None:
    payload = {"reportData": {"report": {"masterData": {"actors": [
        {"id": 57, "gameID": 900, "name": "The Test Colossus", "subType": "Boss"},
        {"id": 60, "gameID": 903, "name": "The Test Colossus", "subType": "NPC"},
    ]}}}}
    assert build_npc_actors(payload) == (
        NpcActor(actor_id=57, game_id=900, name="The Test Colossus", sub_type="Boss"),
        NpcActor(actor_id=60, game_id=903, name="The Test Colossus", sub_type="NPC"),
    )


def test_a_reference_fight_carries_its_window_and_enemies() -> None:
    payload = {"reportData": {"report": {"fights": [
        {"id": 12, "startTime": 1000, "endTime": 481000,
         "enemyNPCs": [{"id": 31, "gameID": 900}, {"id": 32, "gameID": 901}]},
    ]}}}
    fight = build_reference_fight(payload)
    assert fight is not None
    assert (fight.start_ms, fight.end_ms) == (1000, 481000)
    assert [(one.actor_id, one.game_id) for one in fight.enemies] == [(31, 900), (32, 901)]


def test_a_missing_reference_fight_is_none() -> None:
    assert build_reference_fight({"reportData": {"report": {"fights": []}}}) is None
```

Then write in `ingest.py`, beside `build_damage_done` and in its style (read it first):
- `build_boss_damage(payload, *, fight_start_ms)`: the row whose `id == "Total"`; `interval_ms = float(pointInterval)`; `lead_ms = int(pointStart) - fight_start_ms`; amounts `int(round(point * interval_ms / 1000))` exactly as `build_damage_done` converts; `None` when no `Total` row or `interval_ms <= 0`. Its docstring says why `Total` is read here when `build_damage_done` drops it: this graph is scoped to one enemy and states no per-player ranking; the per-player rows are left for slice 2.
- `build_npc_actors(payload)`: `reportData.report.masterData.actors`, skipping a row missing `id` or `gameID`.
- `ReferenceFight(Frozen)` with `start_ms: int`, `end_ms: int`, `enemies: tuple[EnemyNpc, ...]` (reuse `EnemyNpc` from `wowperf.domain.model`), defined in `ingest.py` beside its builder; `build_reference_fight(payload)` reads `fights[0]`, `None` when the list is empty.

Prove each builder test red once by breaking the line it guards (read `id == "Total"` as `isinstance(id, int)`; drop the rate conversion; drop the lead subtraction).

- [ ] **Step 4: The loader, test first**

`load_pace_sample` in `src/wowperf/adapters/wcl/pace.py`, following `WclEncounterRankingRepository.reference_kills` for fetching (`cache.get_or_fetch(cache_key(query, variables), lambda: client.execute(query, variables))`) and `_mechanics_record` in `cli.py` for records (`ReferenceRecord(report_code=..., fight_id=..., keystone_level=0, url=REPORT_URL.format(...), axis="pace", loaded=..., reason=..., from_cache=...)`, `REPORT_URL` from `wowperf.domain.comparison.reference`):

```python
def load_pace_sample(
    client: WclClient,
    own_cache: DiskCache,
    reference_cache: DiskCache,
    encounter: Encounter,
    references: tuple[ReferenceKillRow, ...],
) -> tuple[PaceSample, tuple[ReferenceRecord, ...]]:
    """Our boss's damage graph and each reference kill's, for one wipe.

    Our report's responses go in `own_cache`, which never expires; the
    reference kills' in `reference_cache`, which does -- other players' logs,
    kept for one comparison. `references` is the mechanics comparison's own
    members, so the page's two comparisons stand on one sample.

    A reference is dropped, with its reason recorded, when its fight is
    missing, when our boss's game id names no actor in it or more than one, or
    when its graph carries no boss series. Never fatal: a `WclError` or
    `IngestError` on one reference is recorded and the loop moves on.
    """
```

Body, in order:
1. `NPC_ACTORS_QUERY` with `{"code": encounter.report_code}` in `own_cache`; `boss = find_boss_actor(build_npc_actors(payload), encounter.boss_name)`; `None` -> `(PaceSample(unavailable=NO_SINGLE_BOSS), ())`.
2. `BOSS_DAMAGE_GRAPH_QUERY` with `{"code", "fightId": encounter.fight_id, "startTime": float(encounter.start_ms), "endTime": float(encounter.end_ms), "targetId": boss.actor_id}` in `own_cache`; `build_boss_damage(..., fight_start_ms=encounter.start_ms)`; `None` -> `(PaceSample(unavailable=NO_BOSS_DAMAGE), ())`.
3. No `references` -> `(PaceSample(ours=ours, unavailable=NO_REFERENCE_KILL), ())`.
4. Per row: `REFERENCE_FIGHT_QUERY` `{"code": row.report_code, "fightId": row.fight_id}` in `reference_cache`; `None` fight -> record `reason="the reference fight is not in its report"`; ids of `fight.enemies` with `game_id == boss.game_id`: none -> record `reason="the boss is not among this fight's enemies"` and count it as boss-absent; more than one -> record `reason="the boss appears as more than one actor"`; else the graph with that fight's `start_ms`/`end_ms` and the one actor id; `None` damage -> record `reason="the damage graph held no series for the boss"`. Success -> `PaceReference(duration_seconds=row.duration_seconds, damage=damage)` and a loaded record whose `from_cache` is true only when both responses came from the cache.
5. No members -> `unavailable = BOSS_IN_NO_REFERENCE` when every row was boss-absent, else `NO_REFERENCE_KILL`, with the records.

Test it with `httpx.MockTransport` exactly as `tests/adapters/wcl/test_encounter_rankings.py::test_top_parses_sends_its_own_arguments_and_returns_built_rows` builds a `WclClient` (read it), routing on the request body's `query` operation name (`NpcActors`, `ReferenceFight`, `BossDamageGraph`) and `variables`. Cases, each its own test:
- a council report (no single boss) -> `NO_SINGLE_BOSS`, and **no** graph request was made (count requests by operation name);
- three references loaded -> three `PaceReference`s with their leaderboard durations, three `axis == "pace"` loaded records, and the reference graph was asked for the reference fight's own boss actor id and window (capture variables);
- one reference whose enemies lack the boss, two that load -> two members, one record with the boss-absent reason;
- every reference lacking the boss -> `BOSS_IN_NO_REFERENCE`;
- a reference answering with an HTTP error -> recorded, not raised, the others loaded;
- our responses land in `own_cache` and the references' in `reference_cache` (two `DiskCache`s on two `tmp_path` subdirectories; assert each directory's file count).

Prove red: swap the two caches; drop the `game_id` match (take the first enemy); drop the boss-absent counting.

- [ ] **Step 5: Gate and commit**

Full gate. Subject: `Fetch a wipe's boss damage and its reference kills' by boss actor`

---

### Task 4: On the raid page

**Files:**
- Create: `src/wowperf/domain/report/pace_chart.py`
- Modify: `src/wowperf/domain/report/raid_model.py` (`ChartPoint`, `PaceChart`; `RaidReport.pace_chart`, `RaidReport.pace_warning`)
- Modify: `src/wowperf/domain/report/raid_build.py` (`build_raid_report`)
- Modify: `src/wowperf/domain/report/raid_ledger.py` (`RAID_PLACEMENTS`)
- Modify: `src/wowperf/adapters/render/_raid_damage.html.j2`, `_raid_summary.html.j2`, `report.css.j2`
- Test: `tests/domain/report/test_pace_chart.py` (create), `tests/domain/report/test_raid_build.py`, `tests/domain/report/test_raid_ledger.py`, `tests/adapters/render/test_raid_html_invariants.py` and its golden `tests/adapters/render/golden/raid.html`

**Interfaces:**
- Consumes: Task 2's `PaceSample`, `pace_reading`, `PACE_PREFIX`, `PACE_ID`, `UNAVAILABLE_ID`; Task 1's `PaceReading`, `PaceState`, `final_behind_start`.
- Produces: `build_pace_chart(reading: PaceReading, duration_seconds: float) -> PaceChart | None`; `build_raid_report(..., pace: PaceSample | None = None)`; `RaidReport.pace_chart: PaceChart | None = None`, `RaidReport.pace_warning: LedgerRow | None = None`.

- [ ] **Step 1: The chart model and builder, test first**

In `raid_model.py`, beside `AliveChart` (read it; mirror its docstring habits):

```python
class ChartPoint(Frozen):
    """One point of a line or a polygon, in viewBox units."""

    x: float
    y: float


class PaceChart(Frozen):
    """Our cumulative boss damage against the kills' band, as one drawing.

    Every coordinate lives here so the template computes none. The y axis is a
    share of the kills' median total boss damage and the tick labels are
    percentages: no raw damage figure reaches the page. `band` is a closed
    polygon -- the highest edge left to right, then the lowest edge back.
    """

    band: tuple[ChartPoint, ...]
    median: tuple[ChartPoint, ...]
    ours: tuple[ChartPoint, ...]
    behind_x: float | None
    cut_x: float | None
    plot_top: float
    baseline_y: float
    ticks: tuple[tuple[float, str], ...]
    legend: str
    badge: Badge
    width: float
    height: float
    tick_x1: float
    tick_x2: float
    tick_label_x: float
```

`src/wowperf/domain/report/pace_chart.py` reuses `alive_chart.py`'s geometry constants by import (`CHART_WIDTH`, `CHART_HEIGHT`, `PLOT_X0`, `PLOT_X1`, `PLOT_TOP`, `BASELINE_Y`, `TICK_LABEL_X`) so the two charts on one page share a frame:
- x: `PLOT_X0 + (second / duration_seconds) * (PLOT_X1 - PLOT_X0)` -- the whole wipe, so a cut band visibly ends early.
- y: `BASELINE_Y - (value / reading.target / top) * (BASELINE_Y - PLOT_TOP)`, where `top` is the largest of every `high`, every `ours` and `median` in the reading divided by `reading.target`, floored at 0.25 and rounded up to the next 0.25.
- ticks: `0%`, half of `top`, `top`, each labelled `f"{round(100 * share)}%"`.
- `behind_x`: the x of `final_behind_start(reading)`, else `None`. `cut_x`: the x of the last compared second when `reading.band_cut`, else `None`.
- `legend`: "Damage to the boss since the pull, as a share of the kills' median total. The band runs from the kill that had dealt least by each second to the one that had dealt most; the thin line is their median; the heavy line is this raid." Under the fallback: "Damage to the boss since the pull, as a share of the slowest reference kill's total. The thin line is that kill; the heavy line is this raid." Append " The band ends where fewer than three kills were still fighting." when cut and not single.
- `badge = badge_for(Confidence.DERIVED)`.
- `None` when `reading.seconds` is empty or `reading.target <= 0`.

Tests in `tests/domain/report/test_pace_chart.py` (reuse Task 1's `steady`/`a_kill`): the band polygon has `2 * len(seconds)` points and its first half is the highs; our last point's y is below the band's lowest edge's last y on a behind reading (larger y); `behind_x` is the x of T; `cut_x` is set only on a cut reading; every tick label matches `r"^\d+%$"`; the fallback legend names the slowest kill; `None` on an empty reading. Prove red: swap `low`/`high` in the polygon; drop the cut; label ticks with raw values.

- [ ] **Step 2: The builder, test first**

Read `build_raid_report` whole before editing. Changes:
1. New keyword `pace: PaceSample | None = None` (keep the signature's existing order; add it after `death_cards`).
2. Beside the ceiling-notice block, strip `UNAVAILABLE_ID` notices out of `findings` the same way, and add each to `withheld` as `f"Damage pace against other kills: {notice.detail}"`. Comment why, in the style of the two blocks beside it.
3. `RAID_PLACEMENTS` gains `("compare.pace.", "damage_rows")` before `("compare.damage.", "damage_rows")`; the notice never reaches placement because step 2 removed it.
4. **Keep the parse comparison's fight-wide Provenance line.** Today `damage = _damage_section(...)` is withheld on a wipe, and that one reason both becomes the Provenance line "Damage against other kills: ..." and suppresses the same reason on every raider's card (`stated_for_the_whole_fight`). Pace rows would make the tab present and silently turn that into one line per raider. So compute the parse half on the rows that are not pace rows: `parse_damage = _damage_section(findings, tuple(row for row in placed_rows["damage_rows"] if not row.finding_id.startswith(PACE_PREFIX)))`; use `parse_damage` for the Provenance line and for `stated_for_the_whole_fight`; the tab's `damage` is `Section(state=SectionState.PRESENT)` when `placed_rows["damage_rows"]` is non-empty, else `parse_damage`. Comment why.
5. `reading = pace_reading(loaded.encounter, pace) if pace is not None else None`; `pace_finding = next((f for f in findings if f.id == PACE_ID), None)`; `pace_chart = build_pace_chart(reading, loaded.encounter.duration_seconds) if reading and pace_finding else None`; `pace_warning = ledger_row(pace_finding, titles_by_id, tooltips) if pace_finding and reading and reading.seconds and reading.seconds[-1].state is PaceState.BEHIND else None`.
6. `RaidReport(..., pace_chart=pace_chart, pace_warning=pace_warning)`.

Tests in `tests/domain/report/test_raid_build.py`, using its `a_raid_fixture(kill=False, ...)` and findings from `analyse_pace` on a `PaceSample` built with Task 1's helpers (never hand-typed pace findings, so the builder and analyser are tested together):
- a behind wipe: both pace rows on `report.damage_rows`, `report.damage.state` present, `report.pace_chart` set, `report.pace_warning.finding_id == PACE_ID`;
- an on-pace wipe: rows and chart, `pace_warning` is `None`;
- the notice: `"Damage pace against other kills: ..."` in `report.provenance.withheld`, and no row with `UNAVAILABLE_ID` anywhere on the page's rows or observations;
- on a wipe with pace rows **and** a `compare.parse.unavailable.<slug>` finding for two raiders: Provenance holds `"Damage against other kills: ..."` exactly once and no per-raider "Spell and talent comparison for ..." line repeating that reason;
- a kill with `pace=None`: `pace_chart` and `pace_warning` are `None` and `damage_rows` unchanged.

Add the two pace ids and the notice to `RAID_FAMILIES` in `tests/domain/report/test_raid_ledger.py` (read how it enumerates) and a placement row for `compare.pace.boss` -> `damage_rows`. Prove red: remove the placement entry; skip the notice strip; use `damage` instead of `parse_damage` for the Provenance line.

- [ ] **Step 3: The templates**

`_raid_damage.html.j2`, inside the `{% else %}` branch and before the rows:

```jinja
{% if report.pace_chart %}
<h3 id="{{ scope }}pace">Damage to the boss against the kills
  <a class="badge {{ report.pace_chart.badge.tint }}" href="#{{ scope }}provenance">{{ report.pace_chart.badge.label }}</a></h3>
<p class="legend">{{ report.pace_chart.legend }}</p>
<svg class="pace-chart" width="100%"
     viewBox="0 0 {{ report.pace_chart.width }} {{ report.pace_chart.height }}">
  {% for y, label in report.pace_chart.ticks %}
  <line class="tick" x1="{{ report.pace_chart.tick_x1 }}" y1="{{ y }}"
        x2="{{ report.pace_chart.tick_x2 }}" y2="{{ y }}"></line>
  <text class="tick-label" x="{{ report.pace_chart.tick_label_x }}" y="{{ y }}"
        text-anchor="end" dominant-baseline="middle">{{ label }}</text>
  {% endfor %}
  <polygon class="pace-band" points="
    {%- for point in report.pace_chart.band %}{{ point.x }},{{ point.y }} {% endfor -%}
  "></polygon>
  <polyline class="pace-median" fill="none" points="
    {%- for point in report.pace_chart.median %}{{ point.x }},{{ point.y }} {% endfor -%}
  "></polyline>
  <polyline class="pace-ours" fill="none" points="
    {%- for point in report.pace_chart.ours %}{{ point.x }},{{ point.y }} {% endfor -%}
  "></polyline>
  {% if report.pace_chart.behind_x is not none %}
  <line class="pace-mark" x1="{{ report.pace_chart.behind_x }}" y1="{{ report.pace_chart.plot_top }}"
        x2="{{ report.pace_chart.behind_x }}" y2="{{ report.pace_chart.baseline_y }}"></line>
  {% endif %}
  {% if report.pace_chart.cut_x is not none %}
  <line class="pace-cut" x1="{{ report.pace_chart.cut_x }}" y1="{{ report.pace_chart.plot_top }}"
        x2="{{ report.pace_chart.cut_x }}" y2="{{ report.pace_chart.baseline_y }}"></line>
  {% endif %}
</svg>
{% endif %}
```

`plot_top` and `baseline_y` are `alive_chart.PLOT_TOP` and `BASELINE_Y`, carried on the model so the template computes nothing. The render test asserts both marks: `pace-mark` on a behind page, `pace-cut` on a cut one.

`_raid_summary.html.j2`, directly after the verdict block's `{% endif %}`:

```jinja
{% if report.pace_warning %}
<p class="sub">Behind the reference kills' pace. The chart is on the Damage tab.</p>
{{ pointer(report.pace_warning) }}
{% endif %}
```

`report.css.j2`, beside `.alive-chart .alive-line`: rules for `.pace-chart .pace-band` (a translucent fill of an existing palette token, no stroke), `.pace-median` (thin), `.pace-ours` (`var(--ours)`, width 2), `.pace-mark` (dashed), `.pace-cut` (dotted). Read the palette tokens first; add no new colour value where a token exists.

- [ ] **Step 4: Render tests and the golden**

In `tests/adapters/render/test_raid_html_invariants.py`: a wipe page with a behind pace sample draws `class="pace-chart"`, a `pace-band` polygon, the pointer on the Summary linking to the pace row's id, and every page-wide invariant test in the file still passes (the one-script and icon-host checks in `test_html_invariants.py` included). A kill page draws none of it. Give the golden builder `a_golden_raid_report()` a behind `PaceSample` built with Task 1's helpers and the pace findings from `analyse_pace`, regenerate with `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/test_raid_html_invariants.py --golden-update`, and read the diff: it may add only the pace rows, the chart, the pointer, their CSS and the Provenance line. Anything else moving is a defect to stop on. The night golden must not move (`RaidReport`'s new fields default to `None`, and the night builder passes no `pace`).

- [ ] **Step 5: Gate and commit**

Full gate. Subject: `Draw a wipe's damage pace on the raid page, and point at it when behind`

---

### Task 5: Wire the raid command

**Files:**
- Modify: `src/wowperf/domain/analysis/encounter_service.py` (`analyse_encounter`)
- Modify: `src/wowperf/cli.py` (the `raid` command, ~:1537-1670)
- Test: `tests/domain/analysis/` (the file testing `analyse_encounter`), `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2's `PaceSample`, `analyse_pace`; Task 3's `load_pace_sample`; Task 4's `build_raid_report(..., pace=)`.

- [ ] **Step 1: The service, test first**

`analyse_encounter` gains `pace: PaceSample | None = None` (keyword, after `parse_subjects`) and, when it is not `None`, appends `analyse_pace(loaded.encounter, pace)` to its findings. Docstring: one sentence saying the pace comparison runs on wipes the command fetched references for, and why `None` means not asked rather than nothing found. Test in the file that already tests `analyse_encounter` (find it): a wipe with a behind sample carries `compare.pace.boss`; the same call with `pace=None` carries no `compare.pace.` finding. Prove red by ignoring the parameter.

- [ ] **Step 2: The command, test first**

In `tests/test_cli.py`, read `run_raid`, its handler and its fixtures, and extend them so a wipe can be run: a flag (for example `kill=False`) that serves a wipe fight, and routes for `NpcActors`, `ReferenceFight` and `BossDamageGraph` answering from invented payloads (NPC names invented, one boss actor named after the fixture fight). Tests:
- a wipe run writes `compare.pace.boss` into the findings file and records `axis == "pace"` references beside the mechanics ones, one per mechanics member;
- a kill run asks for none of the three operations (count requests by operation name in the handler);
- `--no-compare` on a wipe asks for none of them and writes no `compare.pace.` finding.

Then in `cli.py`, inside `if not no_compare:` after `mechanics_sample, reference_records = _mechanics_sample(...)`:

```python
            # A wipe only: kills have the parse comparison, and nothing is fetched for a
            # comparison the page would not draw. The references are the mechanics
            # sample's own members, so the page's two comparisons stand on one sample.
            if not encounter.kill:
                pace_sample, pace_records = load_pace_sample(
                    repository.client,
                    repository.cache,
                    transient,
                    encounter,
                    tuple(member.row for member in mechanics_sample.members),
                )
                reference_records += pace_records
```

with `pace_sample: PaceSample | None = None` initialised beside `mechanics_sample`; pass `pace=pace_sample` to `analyse_encounter` and to `build_raid_report`. Prove red: drop the `not encounter.kill` guard (the kill test goes red); pass `limit`-free leaderboard rows instead of the members (the one-per-member test goes red, if the fixture offers a row the mechanics loop discards -- make it offer one).

- [ ] **Step 3: Gate and commit**

Full gate. Subject: `Compare a wipe's damage pace in the raid command`

---

### Task 6: Exercise it on the real report

**Files:**
- Modify: `tests/e2e/test_raid_e2e.py` (a new test)
- Modify: `docs/plans/2026-09-27-wipe-damage-pace-design.md` (status, §10 live, §11)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: The e2e, run once**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections and `tests/e2e/test_raid_e2e.py` (its `WIPE` report, `CliRunner` use at ~:496 and the findings-file read at ~:516). Add `test_a_real_wipe_is_compared_against_the_kills_pace`: run the `raid` command through `CliRunner` on `WIPE` (the canonical wipe, fight 30 of `cW38jmwdnZfbHVL4`) with `--cache-dir` and `--out` under `tmp_path`, read the findings file, and assert shape only:
- exactly one `compare.pace.boss`, `derived`, its title starting with one of `"Behind "`, `"On "`, `"Ahead of "`;
- its share (parsed from the title with a regex) between 1 and 300;
- a `Behind from a to b` line, when present, has `a <= b`, and `b` equals the "Compared through" clock;
- the projection, when present, is `inferred`;
- every `axis == "pace"` reference record is `loaded` or carries a reason;
- the run's cost under a bound set from the measured figure, in the file's style (figure and date in a comment).

Reduce every check to a bool before asserting, and give each assertion a message with no title or evidence text in it: pytest prints a failing assertion's operands, and the reference records carry other players' report codes. Run once:
`/c/Users/damien/.local/bin/uv.exe run pytest -m e2e tests/e2e/test_raid_e2e.py::test_a_real_wipe_is_compared_against_the_kills_pace -v -s`. On failure, diagnose from the output before any second run. Set the cost bound from the printed figure.

- [ ] **Step 2: The live distribution**

Run `/c/Users/damien/.local/bin/uv.exe run wowperf raid cW38jmwdnZfbHVL4 --fight N` for N in 28, 29, 30, 31, 32, 33, 34, 26, 8, one at a time, reading the points each prints; stop and report if any single run passes 120 points. Read each `out/cW38jmwdnZfbHVL4-N.findings.json` -- never the HTML -- with a scratch script (in the session scratchpad, not the repo) that prints **no name, no slug, no raw id of a player finding**: per fight, the pace state, the share, T, whether the band was cut, the fallback, the projection's clock against the kills' range, and for 26 and 8 the notice's reason. Report how often each state occurred: behind, on pace, ahead, notice by reason, fallback, band cut.

The measurement already found every comparable wipe here behind. If on pace, ahead or the fallback never occurs, **stop and report**: RwlRwl supplies another report to look for them on; do not go looking for one.

- [ ] **Step 3: Amend the design**

Status line: `approved design; slice 1 planned in docs/plans/2026-09-27-wipe-damage-pace-plan.md and built.` Under §10 "Live", record the per-state counts (numbers and fight indices only) and the e2e's cost; under §11, correct anything the live run contradicts, with the date.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Exercise a wipe's damage pace on a real report`. Body: the points spent and the per-state counts, no names.

---

## What this plan deliberately does not build

- Slice 2 (per player) and slice 3 (the night page).
- Councils: withheld with a notice.
- Any change to `wipe.cause`, to kills' pages, or to the reference selection.
- A findings-JSON field beyond the findings themselves.
