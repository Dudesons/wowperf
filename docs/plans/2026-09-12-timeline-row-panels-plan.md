# Player timeline row panels — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote each player-timeline cooldown row from a native SVG `title` to the page's own
`.tip` panel, carrying presses, a three-way partition of the run, and the cover the buff earned.

**Architecture:** A transparent HTML strip is laid over each row inside a positioned wrapper, and
the panel hangs from the strip. The strip's `top` is a percentage the domain computes from the
viewBox numbers the chart already holds; the viewBox fixes the aspect ratio, so that percentage is
exact at every window size and the inline script measures nothing.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, Jinja2, pytest, ruff, mypy, `uv`.

**Spec:** `docs/plans/2026-09-12-timeline-row-panels-design.md`

## Global Constraints

- **The domain performs no I/O.** Nothing under `src/wowperf/domain/` imports `jinja2`, `httpx`, or
  anything touching the network, disk or a template.
- **The template computes nothing.** Every coordinate and every percentage is computed in
  `player_timeline.py`. `_player_timeline.html.j2`'s own ABOUTME says so.
- **The report loads nothing.** One HTML file, no stylesheet link, no `@import`, no remote `src`,
  exactly one inline script. **This work adds no script and changes none.**
- **`TooltipLine.tier = None` means measured.** It is the panel's default tier, not "ungraded". A
  computed or assumed figure that leaves it unset silently claims to have been read from the log.
- **Never delete a test because it now fails.** Restate it against the new behaviour with a comment
  saying what it used to hold. Seven existing tests pin `row.hover`; every one of them is restated
  by name in this plan and none is dropped.
- **No real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`,
  `Кириллица`. No task here adds a player name.
- **Forbidden git flags:** `--no-verify`, `--no-hooks`, `--no-pre-commit-hook`.
- **Commit messages** are imperative, carry no `feat:`/`fix:` prefix, explain *why* in the body, and
  are **plain ASCII** — a non-ASCII body has been mangled into this repository's history before.

**The gate, run before every commit:**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `src/wowperf/domain/report/player_timeline.py` | The partition, the panel, the strip geometry | 1, 2, 3, 5 |
| `src/wowperf/domain/report/model.py` | `CooldownRow.tooltip`/`hit_top`, `PlayerTimeline.row_hit_height` | 2, 3, 5 |
| `src/wowperf/adapters/render/_macros.html.j2` | The one `tip()` macro both surfaces render | 4 |
| `src/wowperf/adapters/render/_player_timeline.html.j2` | The wrapper and the strips | 5 |
| `src/wowperf/adapters/render/report.css.j2` | `.timeline-wrap`, `.row-hit`, `.tip-head` | 4, 5 |
| `tests/domain/report/test_build_player_timeline.py` | Tasks 1, 2, 3 tests; six restatements | 1, 2, 3 |
| `tests/adapters/render/test_html_sections.py` | Tasks 4, 5 tests; one restatement | 4, 5 |
| `tests/adapters/render/golden/minimal.html` | Regenerated once, at the end | 5 |

**Why five tasks.** Task 1 is a pure function with no model change. Task 2 adds the panel but leaves
`hover` in place, so the template keeps working and every task stays green. Task 3 is geometry
only. Task 4 is a template refactor a reviewer could reject on its own. Task 5 is the only task
that changes what the page does, and it is where `hover` finally dies.

---

### Task 1: The three-way partition

A pure function over the spans the chart already holds. No model change, no template change.

**Files:**
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Produces: `_row_shares(not_judged: Span | None, unavailable: tuple[Span, ...]) -> tuple[int, int, int]`,
  returning `(not_judged, on_cooldown, ready_and_unpressed)` as whole percentages that sum to 100.
  Task 2 consumes it.
- Produces: `TRACK_WIDTH: float`, the track's own width, `TRACK_X1 - TRACK_ORIGIN_X` = 506.0.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/report/test_build_player_timeline.py`. Import `Span` from
`wowperf.domain.report.model` and `TRACK_WIDTH`, `_row_shares` from
`wowperf.domain.report.player_timeline`.

```python
def test_the_three_shares_of_a_row_always_sum_to_a_hundred() -> None:
    """Rounded independently these are 26 + 41 + 34 = 101, which reads as a broken
    panel. Largest remainder gives the leftover points to the largest fractions,
    so the column a reader adds up comes to 100 whatever the spans were."""
    shares = _row_shares(
        Span(x=150.0, width=0.257 * TRACK_WIDTH),
        (Span(x=300.0, width=0.406 * TRACK_WIDTH),),
    )
    assert shares == (26, 40, 34)
    assert sum(shares) == 100


def test_overlapping_cooldowns_are_unioned_and_never_summed() -> None:
    """Two presses inside one cooldown cover 194 units of track, not 303.6. A run
    of presses closer together than the cooldown is the normal case, not the edge
    one, so summing the widths would overstate every busy row."""
    not_judged = Span(x=150.0, width=151.8)
    unavailable = (Span(x=403.0, width=151.8), Span(x=445.2, width=151.8))
    assert _row_shares(not_judged, unavailable) == (30, 38, 32)


def test_a_cooldown_running_under_the_unjudged_opening_is_not_counted_twice() -> None:
    """The opening is not judged whatever else is true of it, so a cooldown lying
    under it belongs to neither total twice. Here the press at the origin is
    covered entirely by the opening, so on-cooldown counts only the two later ones."""
    not_judged = Span(x=150.0, width=151.8)
    unavailable = tuple(Span(x=x, width=151.8) for x in (150.0, 318.7, 487.3))
    assert _row_shares(not_judged, unavailable) == (30, 60, 10)


def test_a_row_with_no_presses_is_ready_for_everything_it_was_judged_on() -> None:
    assert _row_shares(Span(x=150.0, width=151.8), ()) == (30, 0, 70)
```

- [ ] **Step 2: Run them to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -k "shares or unioned or twice or ready_for_everything" -v
```

Expected: FAIL, `ImportError: cannot import name '_row_shares'`.

- [ ] **Step 3: Write the implementation**

Add `from collections.abc import Iterable` to the imports. Add `Span` to the `model` import if it
is not already there (it is). Place the following after `_cover_spans` and before `NO_AURA_DATA`.

```python
TRACK_WIDTH = TRACK_X1 - TRACK_ORIGIN_X
"""How wide a row's track is drawn, and so what a share of the run is a share of."""


def _intervals(spans: Iterable[Span]) -> tuple[tuple[float, float], ...]:
    return tuple((span.x, span.x + span.width) for span in spans)


def _merged(intervals: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """The same stretches with every overlap collapsed.

    A press landing inside a running cooldown is the normal case on a busy row,
    so the drawn spans overlap routinely and summing their widths would report
    more track than the row has.
    """
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def _without(
    intervals: tuple[tuple[float, float], ...], holes: tuple[tuple[float, float], ...]
) -> tuple[tuple[float, float], ...]:
    """`intervals` with every part lying inside `holes` removed. `holes` must be merged."""
    kept: list[tuple[float, float]] = []
    for start, end in intervals:
        cursor = start
        for hole_start, hole_end in holes:
            if hole_end <= cursor or hole_start >= end:
                continue
            if hole_start > cursor:
                kept.append((cursor, hole_start))
            cursor = max(cursor, hole_end)
        if cursor < end:
            kept.append((cursor, end))
    return tuple(kept)


def _length(intervals: Iterable[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _apportion(lengths: tuple[float, float, float]) -> tuple[int, int, int]:
    """Three lengths as whole percentages of the track that sum to 100.

    By largest remainder: floor each, then give the leftover points to the
    largest fractions. Rounding the three independently sums to 99 or 101 often
    enough to reach a reader, and a panel whose own column does not add up
    invites the one doubt this page cannot afford.
    """
    exact = [length / TRACK_WIDTH * 100 for length in lengths]
    shares = [int(part) for part in exact]
    by_remainder = sorted(range(3), key=lambda index: exact[index] - shares[index], reverse=True)
    for index in by_remainder[: 100 - sum(shares)]:
        shares[index] += 1
    return shares[0], shares[1], shares[2]


def _row_shares(
    not_judged: Span | None, unavailable: tuple[Span, ...]
) -> tuple[int, int, int]:
    """What share of the run this row was unjudged, on cooldown, and ready but unpressed.

    These three cover the track exactly once, which is why the drawing's fourth
    state is not among them: cover overlaps the cooldown almost always, because
    the buff is up while the cooldown runs, and four shares of one run would sum
    past 100. Design section 2.1 records the measurement that settled it.

    Read from the drawn spans and not from the milliseconds behind them, for the
    reason the cover figure already states: the panel's claim is about what the
    reader is looking at, so the number and the rectangles cannot disagree.
    """
    opening = _merged(_intervals([not_judged] if not_judged is not None else []))
    cooldown = _without(_merged(_intervals(unavailable)), opening)
    opening_length = _length(opening)
    cooldown_length = _length(cooldown)
    # Clamped against float error only: every span is already clipped to the
    # axis, so the complement cannot truly be negative.
    ready = max(0.0, TRACK_WIDTH - opening_length - cooldown_length)
    return _apportion((opening_length, cooldown_length, ready))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -v
```

Expected: PASS, and every pre-existing test in the file still passes.

- [ ] **Step 5: Check both mutations kill a test**

Each mutation is applied, the suite run, the failure read, then the mutation reverted.

1. In `_apportion`, replace the body's last three lines with
   `return round(exact[0]), round(exact[1]), round(exact[2])`.
   Expected: `test_the_three_shares_of_a_row_always_sum_to_a_hundred` FAILS at `(26, 41, 34)`.
2. In `_row_shares`, replace `_merged(_intervals(unavailable))` with `_intervals(unavailable)`.
   Expected: `test_overlapping_cooldowns_are_unioned_and_never_summed` FAILS.

If either mutation leaves the suite green, the test does not pin what it claims to. Stop and say so.

- [ ] **Step 6: Run the gate, then commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add src/wowperf/domain/report/player_timeline.py tests/domain/report/test_build_player_timeline.py
```

```bash
git commit -m "Partition a cooldown row into the three states it can be in

A row is unjudged, on cooldown, or ready and unpressed, and those three
cover its track exactly once. The drawing's fourth state does not join
them: cover overlaps the cooldown almost always, because the buff is up
while the cooldown runs, so four shares of one run sum past 100 -- 149%
on one row of the report this was read against.

Largest remainder rather than rounding each share, because independent
rounding lands on 99 or 101 often enough to reach a reader.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The panel the row carries

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`CooldownRow`)
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: `_row_shares` from Task 1.
- Produces: `CooldownRow.tooltip: Tooltip | None`, built by
  `_row_panel(label: str, presses: int, bands: tuple[tuple[int, int], ...] | None, shares: tuple[int, int, int]) -> Tooltip`.
  Task 5 renders it.

**`hover` stays in this task.** It is removed in Task 5, with the template that reads it. Removing
it here would leave the template rendering an empty `<title>` for two tasks.

- [ ] **Step 1: Write the failing tests**

Six of these **restate existing tests**, named below. Replace each old test body with the new one;
do not add the new ones beside the old. Import `Tooltip`, `TooltipLine` and `Confidence`, and
`NO_AURA_DATA` from `player_timeline`.

```python
def a_panel_line(row: CooldownRow, label: str) -> TooltipLine:
    """The one line of a row's panel with this label, or a clear failure."""
    assert row.tooltip is not None
    matches = [line for line in row.tooltip.lines if line.label == label]
    assert len(matches) == 1, f"{label} appears {len(matches)} times"
    return matches[0]


# Restates test_a_cooldown_rows_hover_states_its_presses_and_its_cover, which held
# the same two figures as one line of plain text on a native SVG title.
def test_a_cooldown_rows_panel_states_its_presses_and_its_cover() -> None:
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Presses").value == "1"
    assert a_panel_line(row, "Buff up").value == "8.0 s"


# Restates test_a_cooldown_rows_hover_counts_every_press.
def test_a_cooldown_rows_panel_counts_every_press() -> None:
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=tuple(a_cast(1, SHIELD.ability_id, at) for at in (100_000, 300_000, 500_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Presses").value == "3"


# Restates test_a_cooldown_rows_hover_sums_every_window_the_buff_was_up.
def test_a_cooldown_rows_panel_sums_every_window_the_buff_was_up() -> None:
    loaded = a_covered_run(
        bands=(
            AuraBand(start_ms=100_000, end_ms=108_000),
            AuraBand(start_ms=300_000, end_ms=302_500),
        ),
        casts=tuple(a_cast(1, SHIELD.ability_id, at) for at in (100_000, 300_000)),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "10.5 s"


# Restates test_a_cooldown_rows_hover_counts_only_the_cover_the_drawing_shows.
def test_a_cooldown_rows_panel_counts_only_the_cover_the_drawing_shows() -> None:
    """The figure is the drawn windows, never the aura table's own total.

    A buff still up when the axis ends is clipped where the drawing clips it,
    so the number a reader hovers and the rectangles they are looking at
    cannot disagree. `total_uptime_ms` here is 15s and the axis sees 5.
    """
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=595_000, end_ms=610_000),),
        casts=(a_cast(1, SHIELD.ability_id, 595_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "5.0 s"


# Restates test_a_cooldown_row_with_no_aura_for_its_ability_says_so_rather_than_no_cover.
def test_a_cooldown_row_with_no_aura_for_its_ability_says_so_rather_than_no_cover() -> None:
    """An absence of aura data is not a buff that was never up.

    The row draws no cover in either case, so the panel is the only place the
    two can be told apart, and reporting the missing table as zero seconds
    would state as measured a fact nobody measured.
    """
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.tooltip is not None
    assert row.tooltip.note == NO_AURA_DATA
    assert [line.label for line in row.tooltip.lines if line.label == "Buff up"] == []


# Restates test_a_cooldown_row_whose_aura_was_never_up_reports_no_seconds_of_cover.
def test_a_cooldown_row_whose_aura_was_never_up_reports_no_seconds_of_cover() -> None:
    loaded = a_covered_run(bands=(), casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Buff up").value == "0.0 s"
    assert row.tooltip is not None
    assert row.tooltip.note == ""


def test_a_cooldown_rows_panel_grades_the_assumed_figures_and_not_the_counted_ones() -> None:
    """`TooltipLine.tier` means measured when it is None, so an ungraded share
    would badge an assumed cooldown as something read from the log. The three
    shares rest on a base cooldown from `data/` that talents shorten and the log
    never records, which is the claim the chart's own inferred badge grades."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    inferred = badge_for(Confidence.INFERRED)
    assert a_panel_line(row, "Presses").tier is None
    assert a_panel_line(row, "Buff up").tier is None
    for label in ("Not judged", "On cooldown", "Ready and unpressed"):
        assert a_panel_line(row, label).tier == inferred


def test_a_cooldown_rows_panel_reports_the_share_the_partition_computed() -> None:
    """One press at 300s of a 600s run, on a 180s cooldown: 30% unjudged,
    30% on cooldown, and 40% of the run ready and never pressed."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert a_panel_line(row, "Not judged").value == "30%"
    assert a_panel_line(row, "On cooldown").value == "30%"
    assert a_panel_line(row, "Ready and unpressed").value == "40%"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -k panel -v
```

Expected: FAIL. `CooldownRow` has no `tooltip`, so `a_panel_line`'s `assert row.tooltip is not None`
fails. **`Frozen` ignores unknown attributes on construction but still raises on access**, so this
is a real failure and not a silent pass.

- [ ] **Step 3: Add the model field**

In `src/wowperf/domain/report/model.py`, inside `CooldownRow`, after the `hover` field:

```python
    tooltip: Tooltip | None = None
    """The row's figures as the page's own panel: presses, the three states the
    run divides into, and the cover the buff earned.

    A native SVG title carries no badge, which is why `hover` states measured
    figures only. This carries tiers, so it states the assumed figures too --
    which is what promoting the row to a panel buys, and not merely a change of
    styling.
    """
```

`Tooltip` is already defined above `LedgerRow` in this file, so it is in scope.

- [ ] **Step 4: Write the panel builder**

In `player_timeline.py`, add `Tooltip` and `TooltipLine` to the `report.model` import, and place
this immediately after `_cooldown_hover`:

```python
def _row_panel(
    label: str,
    presses: int,
    bands: tuple[tuple[int, int], ...] | None,
    shares: tuple[int, int, int],
) -> Tooltip:
    """What one row's rectangles are worth, as the page's own panel.

    The counted figures carry no tier, which is this panel's way of saying
    measured. The three shares carry `inferred`, because the cooldown they
    divide by is a base value from `data/` that talents shorten and the log
    never records a reset -- the same claim `BADGE_INFERRED_CAPTION` grades on
    the chart.

    `bands` of None is not an empty tuple: the first says no aura table covers
    this ability, the second that a table covered it and recorded no window.
    The row draws nothing either way, so the note is the only place a reader
    can tell them apart, and printing zero seconds for the first would state as
    measured a thing nobody measured.
    """
    not_judged, on_cooldown, ready = shares
    inferred = badge_for(Confidence.INFERRED)
    lines = [
        TooltipLine(label="Presses", value=str(presses)),
        TooltipLine(label="Not judged", value=f"{not_judged}%", tier=inferred),
        TooltipLine(label="On cooldown", value=f"{on_cooldown}%", tier=inferred),
        TooltipLine(label="Ready and unpressed", value=f"{ready}%", tier=inferred),
    ]
    if bands is not None:
        seconds = sum(end - start for start, end in bands) / 1000
        lines.append(TooltipLine(label="Buff up", value=f"{seconds:.1f} s"))
    return Tooltip(lines=tuple(lines), note="" if bands is not None else NO_AURA_DATA)
```

- [ ] **Step 5: Wire it into the row**

In `_cooldown_rows`, the `not_judged` and `unavailable` values are currently built inline inside the
`CooldownRow(...)` call. Lift them to locals before the call so the panel can read the same objects
the chart draws — the panel must divide the drawn spans, not a second computation of them.

Replace the body of the `for ability in abilities:` loop's tail (from `rows.append(` onward) so that
it reads:

```python
        unavailable = tuple(
            Span(
                x=round(_track_x((at - origin_ms) / 1000, scale), PRECISION),
                # Clamped to the time remaining in the run after this press, not
                # to the run's whole length: the ability can only be judged
                # unavailable up to the axis end, never past it.
                width=round(
                    min(
                        ability.cooldown_seconds,
                        max(0.0, span_seconds - (at - origin_ms) / 1000),
                    )
                    * scale,
                    PRECISION,
                ),
            )
            for at in presses
        )
        not_judged = Span(x=TRACK_ORIGIN_X, width=not_judged_width)
        rows.append(
            CooldownRow(
                label=ability.name,
                ability_id=ability.ability_id,
                hover=_cooldown_hover(ability.name, len(presses), bands),
                tooltip=_row_panel(
                    ability.name,
                    len(presses),
                    bands,
                    _row_shares(not_judged, unavailable),
                ),
                baseline_y=FIRST_ROW_Y + len(rows) * ROW_HEIGHT,
                # The label sits on the row's own middle, not on its top edge:
                # a baseline at the top would draw the glyphs over the row above.
                label_y=round(FIRST_ROW_Y + len(rows) * ROW_HEIGHT + ROW_HEIGHT / 2, PRECISION),
                presses=tuple(press_at(at) for at in presses),
                unavailable=unavailable,
                # A cooldown's own end is the moment the ability came back --
                # marked only when that moment falls before the axis does. A
                # cooldown still running when the run ends would need a tick
                # at the axis end, which claims the ability came back at the
                # moment the run finished; the log never says that. Anchored
                # through `_press_x`, the same offsetting the press it
                # answers already uses -- see that helper for why either
                # mark needs offsetting at all.
                ready_ticks=tuple(
                    _press_x(_track_x(end, scale))
                    for end in (
                        (at - origin_ms) / 1000 + ability.cooldown_seconds for at in presses
                    )
                    if end < span_seconds
                ),
                not_judged=not_judged,
                cover=_cover_spans(bands, scale, origin_ms),
            )
        )
```

Every comment above is carried over verbatim from the existing call. None is dropped.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -v
```

Expected: PASS.

- [ ] **Step 7: Check both mutations kill a test**

1. In `_row_panel`, drop `tier=inferred` from all three share lines.
   Expected: `test_a_cooldown_rows_panel_grades_the_assumed_figures_and_not_the_counted_ones` FAILS.
2. In `_row_panel`, change the last line to `return Tooltip(lines=tuple(lines), note="")` and move
   the `Buff up` line out of its `if` so it always renders.
   Expected: `test_a_cooldown_row_with_no_aura_for_its_ability_says_so_rather_than_no_cover` FAILS.

- [ ] **Step 8: Run the gate, then commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add src/wowperf/domain/report/model.py src/wowperf/domain/report/player_timeline.py tests/domain/report/test_build_player_timeline.py
```

```bash
git commit -m "Give each timeline row the panel its native title could not be

The row's title states measured figures only, and its docstring says why:
the chart also draws the stretches an ability was unavailable, and those
rest on a base cooldown assumed from a data file rather than on anything
the log stated. An SVG title carries no badge to grade such a figure
with, so the chart has been drawing an inferred claim its tooltip was
forbidden from stating.

A panel carries tiers. That is what this buys, and it is why the change
is not merely a change of styling.

The six tests that held the title's wording are restated against the
panel rather than dropped; each names the one it replaces.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Where each strip sits

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`CooldownRow`, `PlayerTimeline`)
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Produces: `CooldownRow.hit_top: float` and `PlayerTimeline.row_hit_height: float`, both
  percentages of the chart's rendered height. Task 5 renders them.
- Produces: `_chart_height(row_count: int) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_rows_strip_is_a_percentage_of_the_chart_and_never_a_viewbox_unit() -> None:
    """The strip is HTML laid over an SVG, so it is positioned in the rendered
    box and not in the drawing's own units. The viewBox fixes the aspect ratio,
    which is what makes the percentage exact at every window size -- and is why
    no script has to measure the page to find a row."""
    timeline = a_timeline_with_presses(count=1)
    row = timeline.cooldowns[0]
    assert row.hit_top == round(row.baseline_y / timeline.height * 100, PRECISION)
    assert timeline.row_hit_height == round(ROW_HEIGHT / timeline.height * 100, PRECISION)
    # A percentage, so it can never be the viewBox number it was derived from.
    assert row.hit_top != row.baseline_y


def test_every_rows_strip_sits_below_the_one_above_it_and_inside_the_chart() -> None:
    timeline = a_timeline(
        LoadedRun(
            run=a_run(pulls=(a_pull(0, 0, 600_000),)),
            casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, BURST.ability_id, 200_000)),
        ),
        defensives=KIT,
        throughput=BURSTS,
    )
    tops = [row.hit_top for row in timeline.cooldowns]
    assert len(tops) == 2
    assert tops == sorted(tops)
    assert tops[0] + timeline.row_hit_height <= tops[1]
    assert tops[-1] + timeline.row_hit_height <= 100.0
```

- [ ] **Step 2: Run them to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -k strip -v
```

Expected: FAIL on the missing `hit_top` attribute.

- [ ] **Step 3: Add the model fields**

In `CooldownRow`, after `tooltip`:

```python
    hit_top: float = 0.0
    """Where this row's hover strip starts, as a percentage of the chart's
    rendered height.

    Not a viewBox unit. The strip is HTML laid over the drawing, so it is
    positioned in the rendered box, and the two scales differ by whatever width
    the page was given. A percentage is exact at every width because the viewBox
    fixes the aspect ratio -- which is what lets the panel be placed without the
    script measuring anything, as the invariants require.
    """
```

In `PlayerTimeline`, beside `row_icon_size`:

```python
    row_hit_height: float = 0.0
    """How tall every row's hover strip is, as a percentage of the chart's
    rendered height. One figure for the whole drawing, because every row is
    drawn the same height -- the same split `row_icon_size` already makes."""
```

- [ ] **Step 4: Compute them**

Add beside the other geometry helpers in `player_timeline.py`:

```python
def _chart_height(row_count: int) -> float:
    """The viewBox's own height, and so what a row's strip is a percentage of."""
    return FIRST_ROW_Y + row_count * ROW_HEIGHT + BOTTOM_MARGIN
```

In `build_player_timeline`, replace the line
`height = FIRST_ROW_Y + len(rows) * ROW_HEIGHT + BOTTOM_MARGIN` with:

```python
    height = _chart_height(len(rows))
    # Stamped once the chart's height is known, which it is not while the rows
    # are being built: the height depends on how many of them there turned out
    # to be.
    rows = tuple(
        row.model_copy(update={"hit_top": round(row.baseline_y / height * 100, PRECISION)})
        for row in rows
    )
```

and add to the returned `PlayerTimeline`, beside `row_icon_size`:

```python
        row_hit_height=round(ROW_HEIGHT / height * 100, PRECISION),
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -v
```

- [ ] **Step 6: Check the mutation kills a test**

Change the stamping line to `update={"hit_top": row.baseline_y}`.
Expected: `test_a_rows_strip_is_a_percentage_of_the_chart_and_never_a_viewbox_unit` FAILS.

- [ ] **Step 7: Run the gate, then commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add src/wowperf/domain/report/model.py src/wowperf/domain/report/player_timeline.py tests/domain/report/test_build_player_timeline.py
```

```bash
git commit -m "Place each row's hover strip as a share of the rendered chart

A panel is HTML positioned against an HTML ancestor and a row is SVG, so
the panel hangs from a strip laid over the row rather than from the row
itself. The strip is positioned in the rendered box, where the drawing's
viewBox units mean nothing.

The viewBox is what makes this work rather than what makes it hard: it
fixes the aspect ratio, so a row at baseline_y sits at baseline_y over
the height of the rendered chart at every window size. The figure is
exact, and the inline script still measures nothing -- which the
invariants require of it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: One panel markup, not two

A refactor with no behaviour change. The ledger's panels must render byte for byte as before.

**Files:**
- Modify: `src/wowperf/adapters/render/_macros.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Produces: the Jinja macro `tip(tooltip, heading="")` in `_macros.html.j2`. Task 5 imports it.

- [ ] **Step 1: Write the failing test**

The macro is rendered directly, because Task 4 adds no consumer for the heading — Task 5 is the
first. The builder is `_environment()`, private, at `src/wowperf/adapters/render/html.py:15`;
this suite already reaches for module internals the same way (`player_timeline_module.TITLE`).
`Tooltip` and `TooltipLine` are already imported in this file, so no import changes.

```python
def test_a_panel_can_carry_a_heading_for_a_surface_that_is_not_its_own_label() -> None:
    # A ledger card's panel hangs off the ability's name, so it needs no
    # heading. A timeline row's panel is laid over a drawing and can open a
    # long way from the label it belongs to, so it names its subject itself.
    from wowperf.adapters.render.html import _environment

    macros = _environment().get_template("_macros.html.j2").module
    panel = str(macros.tip(  # type: ignore[attr-defined]
        Tooltip(lines=(TooltipLine(label="Presses", value="4"),)), "Ice Block"
    ))
    assert '<span class="tip-head">Ice Block</span>' in panel
    assert '<span class="tip-label">Presses</span><span class="tip-value">4</span>' in panel


def test_a_ledger_cards_panel_still_names_nothing_above_its_figures() -> None:
    # The other half of the refactor: `ability()` passes no heading, so the
    # ledger's panels must render exactly as they did. The golden file is the
    # byte-level check; this states the rule in one place a reader will find.
    row = a_row(
        "defensives.ceiling.stonewake.48792",
        title_before="Stonewake used ",
        title_ability="Icebound Fortitude",
        title_after=" 2 of a possible 9 times",
        ability_id=48792,
        tooltip=Tooltip(lines=(TooltipLine(label="Presses", value="2"),)),
    )
    html = render(a_report(ledger_decomposition=(row,)))
    assert "tip-head" not in html
```

- [ ] **Step 2: Run it to verify it fails**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_sections.py -k "heading or names_nothing" -v
```

Expected: the first FAILS — `tip` is not a macro on that module. The second PASSES already, since
nothing renders a heading yet; it is there to stay green through the refactor and to go red if a
later change starts passing one from `ability()`.

- [ ] **Step 3: Extract the macro**

In `_macros.html.j2`, replace the body of `ability()`'s tooltip branch with a call, and add `tip`
above it. The `{%- macro ... -%}` trimming is deliberate: it keeps the rendered bytes identical to
today's, so the golden file shows no change to any existing panel.

```jinja
{# A panel of figures, revealed by CSS alone. `heading` names the panel's
   subject for a surface that does not already show it beside the panel: a
   ledger card's panel hangs off the ability's own name and passes none, a
   timeline row's is laid over a drawing and passes the row's label. #}
{%- macro tip(tooltip, heading="") -%}
<span class="tip" role="note">
{%- if heading %}<span class="tip-head">{{ heading }}</span>{% endif %}
{%- for line in tooltip.lines %}<span class="tip-line"><span class="tip-label">{{ line.label }}{% if line.tier %} <span class="badge {{ line.tier.tint }}">{{ line.tier.label }}</span>{% endif %}</span><span class="tip-value">{{ line.value }}</span></span>{% endfor %}
{%- if tooltip.note %}<span class="tip-note">{{ tooltip.note }}</span>{% endif %}</span>
{%- endmacro %}
```

and in `ability()`, replace the final two lines with:

```jinja
{%- if tooltip %}{{ tip(tooltip) }}{% endif %}</span>
{%- endmacro %}
```

- [ ] **Step 4: Add the heading rule**

In `report.css.j2`, immediately after `.tip-line`:

```css
.tip-head { display: block; font-weight: 500; margin-bottom: 4px; color: var(--ink); }
```

- [ ] **Step 5: Run the tests to verify they pass, and that nothing else moved**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render -v
```

Expected: PASS, **including the golden file test**. If the golden test fails, the extraction
changed the ledger's bytes and the trimming is wrong. Fix the trimming rather than regenerating the
golden file — this task is a refactor and must render identically.

- [ ] **Step 6: Check the mutation kills a test**

1. Remove the `{%- if heading %}` line from `tip`.
   Expected: `test_a_panel_can_carry_a_heading_for_a_surface_that_is_not_its_own_label` FAILS.
2. In `ability()`, change the call to `{{ tip(tooltip, name) }}`.
   Expected: `test_a_ledger_cards_panel_still_names_nothing_above_its_figures` FAILS, and so does
   the golden-file test. Both must be checked: the second alone would tempt an implementer to
   regenerate the golden file rather than revert the mutation.

- [ ] **Step 7: Run the gate, then commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add src/wowperf/adapters/render/_macros.html.j2 src/wowperf/adapters/render/report.css.j2 tests/adapters/render/test_html_sections.py
```

```bash
git commit -m "Let one macro decide what a panel looks like

The timeline rows are about to grow the same panel the ledger cards
carry, and a second copy of the markup is how the two would drift apart
the first time either is touched. The ledger renders byte for byte as
before; the golden file is unchanged on purpose.

A heading is added for the surface that needs one. A ledger card's panel
hangs off the ability's own name, so it names nothing; a row's panel is
laid over a drawing and can open a long way from the label it belongs
to.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The strips on the page

The only task that changes what the page does. `hover` dies here.

**Files:**
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Modify: `src/wowperf/domain/report/model.py` (remove `CooldownRow.hover`)
- Modify: `src/wowperf/domain/report/player_timeline.py` (remove `_cooldown_hover`)
- Test: `tests/adapters/render/test_html_sections.py`
- Regenerate: `tests/adapters/render/golden/minimal.html`

- [ ] **Step 1: Update the render fixture, and know that nothing will tell you to**

`a_drawn_timeline()` in `tests/adapters/render/test_html_sections.py` passes `hover=` to
`CooldownRow`. **`Frozen` silently ignores unknown keyword arguments**, so once the field is gone
that argument becomes a lie no test will report. It has to be removed by hand. The same trap left
five orphaned `icon_x=` arguments behind on 2026-09-12.

In that fixture, replace `hover="Ice Block — 1 press, 8.0 s of cover",` with:

```python
                               tooltip=Tooltip(lines=(
                                   TooltipLine(label="Presses", value="1"),
                                   TooltipLine(label="Not judged", value="30%",
                                               tier=Badge(label="inferred", tint="badge-inferred")),
                                   TooltipLine(label="On cooldown", value="30%",
                                               tier=Badge(label="inferred", tint="badge-inferred")),
                                   TooltipLine(label="Ready and unpressed", value="40%",
                                               tier=Badge(label="inferred", tint="badge-inferred")),
                                   TooltipLine(label="Buff up", value="8.0 s"),
                               )),
                               hit_top=68.6,
```

and add `row_hit_height=11.4,` beside `row_icon_size=16.0,`. The fixture's chart is 140.0 tall with
its row at 96.0, so 96/140 is 68.6% and 16/140 is 11.4%.

- [ ] **Step 2: Write the failing tests**

```python
def test_a_cooldown_rows_facts_reach_the_page_as_the_pages_own_panel() -> None:
    # Restates test_a_cooldown_rows_measured_facts_reach_the_page_as_its_groups_title,
    # which held that the facts rode on a native <title> wrapping the row. They
    # now ride on a strip laid over it, which is a hover target the whole width
    # of the row rather than only the parts of it something was painted on.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    assert '<div class="row-hit" tabindex="0" aria-label="Ice Block"' in body
    assert 'style="top: 68.6%; height: 11.4%"' in body
    assert '<span class="tip-head">Ice Block</span>' in body
    assert '<span class="tip-label">Presses</span><span class="tip-value">1</span>' in body


def test_a_cooldown_row_carries_no_native_title_beside_its_panel() -> None:
    # Design section 5.2: one key beneath the chart, one panel on the row. A
    # <title> on the group would win the pointer for about a second and then
    # answer in the operating system's styling, beside the panel that had
    # already appeared.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    svg = body[body.index('<svg class="player-timeline"'):]
    svg = svg[:svg.index("</svg>")]
    assert "<g><title>" not in svg
    assert "1 press, 8.0 s of cover" not in svg


def test_the_strips_are_siblings_of_the_chart_and_never_children_of_it() -> None:
    # A strip inside the <svg> positions against nothing: CSS positioning does
    # not apply to the children of an SVG, so the panel would render at the
    # chart's origin for every row, silently and identically.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    wrap = body[body.index('<div class="timeline-wrap">'):]
    assert wrap.index("</svg>") < wrap.index('<div class="row-hit"')


def test_the_chart_keeps_the_aspect_ratio_the_strips_percentages_assume() -> None:
    # The strips are placed at baseline_y over the chart's height. That is only
    # the right place while the rendered height stays width x H/680 -- which a
    # height attribute or a preserveAspectRatio override would end, moving every
    # panel off its row with no test to notice.
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>"
    )[1]
    opening = body[body.index('<svg class="player-timeline"'):][:200]
    assert "preserveAspectRatio" not in opening
    assert "height=" not in opening
```

- [ ] **Step 3: Run them to verify they fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_sections.py -k "row_hit or native_title or siblings or aspect" -v
```

Expected: FAIL — no `row-hit` in the markup.

- [ ] **Step 4: Change the template**

In `_player_timeline.html.j2`, add to the top, beside the existing ABOUTME lines:

```jinja
{% from "_macros.html.j2" import tip with context %}
```

Wrap the chart: put `<div class="timeline-wrap">` on the line before `<svg class="player-timeline"`.

Remove the row group's title — line 31 becomes:

```jinja
  <g>
```

After `</svg>`, and before the `{% if timeline.damage %}<p class="sub">` line, insert:

```jinja
{% for row in timeline.cooldowns %}{% if row.tooltip %}
<div class="row-hit" tabindex="0" aria-label="{{ row.label }}" style="top: {{ row.hit_top }}%; height: {{ timeline.row_hit_height }}%">{{ tip(row.tooltip, row.label) }}</div>
{% endif %}{% endfor %}
</div>
```

- [ ] **Step 5: Add the CSS**

In `report.css.j2`, replace the `.player-timeline` rule with:

```css
/* The chart's own box, so a row's hover strip can be placed against it. A
   percentage top resolves against this height, so the margin lives here and
   not on the svg: a margin inside the wrapper would offset every strip by its
   own height. */
.timeline-wrap { position: relative; margin: 10px 0 2px; }
.player-timeline { display: block; width: 100%; margin: 0; }
/* A transparent strip over each row, carrying the row's panel. It is what
   makes a whole row hoverable: the row paints only where something happened,
   and across the rest the pull band behind it is what a pointer finds, so
   without this most of most rows answer with the pull's name. */
.row-hit { position: absolute; left: 0; right: 0; }
```

and beside `.ability:hover .tip`:

```css
.row-hit:hover .tip, .row-hit:focus-within .tip { display: block; }
```

- [ ] **Step 6: Remove the orphans**

In `model.py`, delete `CooldownRow.hover` and its docstring. In `player_timeline.py`, delete
`_cooldown_hover` and the `hover=` argument in `_cooldown_rows`. `NO_AURA_DATA` stays — `_row_panel`
uses it.

- [ ] **Step 7: Run the render tests**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render -v
```

Expected: every test passes except the golden-file test, which must fail — the page changed.

- [ ] **Step 8: Regenerate the golden file and read the diff**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_invariants.py --golden-update
```

```bash
git diff tests/adapters/render/golden/minimal.html
```

**Read it before accepting it.** Expected, and nothing else:
- `<div class="timeline-wrap">` and its `</div>` around each chart.
- One `<div class="row-hit">` per cooldown row, each with a `.tip` inside it.
- `<g><title>…</title>` becoming `<g>` on every cooldown row.
- The new `.timeline-wrap`, `.row-hit`, `.tip-head` rules in the stylesheet.

**No change to any existing `.tip`.** If a ledger panel's bytes moved, Task 4's trimming was wrong
and this diff is the first place it shows.

- [ ] **Step 9: Check both mutations kill a test**

1. Move the `{% for row in timeline.cooldowns %}` strip block from after `</svg>` to just before it.
   Expected: `test_the_strips_are_siblings_of_the_chart_and_never_children_of_it` FAILS.
2. Restore `<title>{{ row.label }}</title>` as the first child of the row's `<g>`.
   Expected: `test_a_cooldown_row_carries_no_native_title_beside_its_panel` FAILS.

- [ ] **Step 10: Run the gate, then commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add -A
```

```bash
git commit -m "Lay a hover strip over each timeline row

The row's native title mostly never fired. Pull bands run the full
height of the chart behind every row, and a row paints only where
something happened, so across the rest of it the band beneath is the
topmost painted element and the pointer gets the pull's name. On one row
of the report this was read against, that is 84% of its width.

A strip covers the whole row, so the panel answers wherever a reader
points, and it takes the pull band's place only where the band was
giving the wrong answer -- bands stay hoverable in the damage track
above, which is where a reader pointing at a pull already is.

The group's title goes with it. Design section 5.2 wanted one panel on
the row, not a panel and an operating-system tooltip competing over one
pointer.

The damage buckets keep their own titles. There are 1074 of them and the
page is already 600 KB; the chart carries two hover vocabularies on
purpose.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification on a real page

No API call is authorised by this plan, and none is needed: `out/G7MBJZfNakrcPvAx-3.html` is on
disk and `.claude/launch.json` has a `report` config serving `out/` on 8765. **Ask RwlRwlRwlRwl
before running `analyze` or `fetch` for any reason** — each authorisation covers one run and the
2026-09-12 one is spent.

Re-render from the cache is itself a command that may reach the network, so it needs asking for
too. What can be checked offline, and should be:

1. The rendered fixture page carries one `.row-hit` per cooldown row, and each `top` matches
   `baseline_y / height`.
2. Screenshots came back blank all through the last session; `javascript_tool` against the DOM
   worked throughout and is what to use. Measure `getBoundingClientRect()` of a `.row-hit` against
   the `<g>` it covers and confirm they line up within a pixel at two window widths — that is the
   one claim in this design that no offline test can make.

## Self-review

**Spec coverage.** Design §2 → Task 2. §2.1 and §2.2 → Task 1. §2.3 → Task 2, Step 1's tier test.
§3 markup and CSS → Task 5. §3.1 → Task 3. §3.2 needs no task; it is a decision not to add flip
logic, and no code expresses it. §3.3 → Task 5's `tabindex` and `aria-label`. §4 → Task 5, Step 6.
§5 → Tasks 4 and 5. §6's eight tests map as T1/T2 → Task 1, T3/T4 → Task 2, T5 → Task 3, T6/T7/T8 →
Task 5. §7 and §8 are prose and carry no task.

**Placeholders.** None, and no step is conditional. Task 4's template-environment helper was
checked against the source rather than assumed: it is `_environment()` at
`src/wowperf/adapters/render/html.py:15`, private, and this suite already reaches for module
internals the same way. Every import the new tests need is already present in the file that needs
it — `Tooltip`, `TooltipLine` and `Badge` in `test_html_sections.py`, and Task 1 and Task 2 name
the ones they add.

**Type consistency.** `_row_shares(Span | None, tuple[Span, ...]) -> tuple[int, int, int]` is
produced in Task 1 and consumed in Task 2 with that signature. `_row_panel`'s `bands` parameter is
`tuple[tuple[int, int], ...] | None`, which is what `_cover_bands` already returns. `hit_top` and
`row_hit_height` are `float` in both the model and the template.

**One risk worth naming.** Task 2's `a_panel_line` helper asserts `row.tooltip is not None` before
reading it. If a future row is built with no panel, that helper fails loudly rather than skipping —
which is what it is for.
