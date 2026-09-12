# Damage Done Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw a second bar track on the player timeline showing what a player's damage output did over the run, so a press mark on a cooldown row can be read against the output that followed it.

**Architecture:** One `graph(dataType: DamageDone)` query per run — pre-bucketed by the API, no pagination, pets already folded into their owner. `ingest.py` converts the response's per-second rate into per-bucket amounts at the adapter boundary. The domain reuses the existing `DamageTrack` and `DamageBar` view models with a second set of geometry constants, and the template gains a block mirroring the one that already draws damage taken.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, pytest, `uv` (no pip, no poetry).

**Spec:** `docs/plans/2026-09-12-damage-done-track-design.md`

## Global Constraints

Every task's requirements implicitly include all of these.

- **No rate reaches the page.** The response gives DPS natively. A hover says damage in this bucket, never damage per second. The rate dies in `ingest.py`. Design §5.
- **No finding comes out of the track.** No entry in the findings JSON, no `seconds_lost`, no rank, no analyser reads it. Design §5.
- **Each track is scaled to its own player's tallest bucket, never the group's.** This is what keeps `2026-09-03-mplus-postmortem-design.md` §5.5 true. Design §3.
- **The `Total` series never survives ingest.** Design §2.3.
- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx` or `jinja2`.
- **The report loads nothing.** No stylesheet link, no remote `src`, one inline script that may not fetch, write text or read storage.
- **Every new numeric view-model field joins `NUMBERS_THAT_ARE_NOT_TOTALS`** in `tests/adapters/render/test_html_invariants.py`, with a reason it cannot hold a total.
- **TDD.** Write the test, watch it fail for the right reason, then write the code. Read `.claude/skills/testing/test-driven-development/SKILL.md` with the Read tool — the harness does not surface it.
- **Run every mutation in both directions** and read the failure text, never just the exit code. This repository's recurring defect is a test that cannot fail, not wrong code.
- **`Frozen` silently ignores unknown keyword arguments.** A renamed field leaves its old keyword sitting in fixtures with nothing to report it.

**The gate, run before every commit:**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

The `export` is not optional — `uv` is off PATH in this Bash. Bare `git commit` can be refused by the RTK hook; `/mingw64/bin/git` works. **Never `--no-verify`.** Write commit messages in plain ASCII: a non-ASCII character has been mangled into a commit body here before. End each with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

**No API call without asking RwlRwlRwlRwl first.** Each authorisation covers one run; "continue" is not authorisation. Only Task 5 needs one.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/adapters/wcl/queries.py` | `DAMAGE_DONE_GRAPH_QUERY` — the one new query |
| `src/wowperf/domain/model.py` | `DamageDoneSeries`, and `LoadedRun.damage_done` |
| `src/wowperf/adapters/wcl/ingest.py` | `build_damage_done` — rate to amount, `Total` dropped |
| `src/wowperf/adapters/wcl/repository.py` | Fetch it, on the `full` profile only |
| `src/wowperf/domain/report/model.py` | `PlayerTimeline.damage_done`, and the derived badge fields |
| `src/wowperf/domain/report/player_timeline.py` | Geometry constants, `_damage_done_track`, the captions |
| `src/wowperf/adapters/render/_player_timeline.html.j2` | The track's markup |
| `src/wowperf/adapters/render/report.css.j2` | The bar colour |
| `tests/adapters/wcl/test_ingest_damage_done.py` | New — the ingest |
| `tests/adapters/wcl/test_repository.py` | The fetch seam |
| `tests/domain/report/test_build_player_timeline.py` | The builder |
| `tests/adapters/render/test_html_sections.py` | The markup |
| `tests/adapters/render/test_html_invariants.py` | The allowlist and the no-rate invariant |

---

### Task 1: Ingest the graph series

Turns the API's response into domain data. The rate-to-amount conversion lives here and nowhere else.

**Files:**
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Modify: `src/wowperf/domain/model.py`
- Modify: `src/wowperf/adapters/wcl/ingest.py`
- Create: `tests/adapters/wcl/test_ingest_damage_done.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  ```python
  DAMAGE_DONE_GRAPH_QUERY: str   # variables: code, fightId, startTime, endTime

  class DamageDoneSeries(Frozen):
      actor_id: int
      point_start_ms: int
      interval_ms: float
      amounts: tuple[int, ...]

  def build_damage_done(payload: dict[str, Any]) -> tuple[DamageDoneSeries, ...]
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/adapters/wcl/test_ingest_damage_done.py`:

```python
# ABOUTME: The damage done graph, from one API response to domain series.
# ABOUTME: The rate-to-amount conversion is the one line here worth most of the tests.

from typing import Any

from wowperf.adapters.wcl.ingest import build_damage_done


def a_payload(*series: dict[str, Any]) -> dict[str, Any]:
    return {"reportData": {"report": {"graph": {"data": {
        "series": list(series), "startTime": 0, "endTime": 60_000,
    }}}}}


def a_series(actor_id: Any, points: list[float], interval: float = 6000.0) -> dict[str, Any]:
    return {
        "id": actor_id,
        "guid": 123,
        "type": "Warrior",
        "pointStart": 1000,
        "pointInterval": interval,
        "total": 999,
        "data": points,
    }


def test_a_points_rate_becomes_the_damage_that_bucket_held() -> None:
    """The response states damage per second; the domain holds damage.

    100 a second over a six-second bucket is 600, and the two figures are
    far enough apart that dropping the conversion cannot pass for rounding.
    """
    series = build_damage_done(a_payload(a_series(7, [100.0], interval=6000.0)))
    assert series[0].amounts == (600,)


def test_every_bucket_is_converted_not_only_the_first() -> None:
    series = build_damage_done(a_payload(a_series(7, [100.0, 50.0, 0.0], interval=6000.0)))
    assert series[0].amounts == (600, 300, 0)


def test_the_interval_the_response_states_is_the_one_used() -> None:
    """A fixed six seconds would pass the tests above and be wrong here."""
    series = build_damage_done(a_payload(a_series(7, [100.0], interval=2500.0)))
    assert series[0].amounts == (250,)


def test_the_total_series_is_dropped() -> None:
    """Its id is the string "Total" where a player's is an int. It is the sum
    of the others, and a run-wide damage total in the model is one import away
    from a page that ranks -- which the postmortem design section 5.5 refuses."""
    payload = a_payload(a_series(7, [100.0]), a_series("Total", [4242.0]))
    series = build_damage_done(payload)
    assert [one.actor_id for one in series] == [7]
    assert all(4242 * 6 not in one.amounts for one in series)


def test_each_series_keeps_its_own_actor_and_start() -> None:
    payload = a_payload(a_series(7, [100.0]), a_series(9, [50.0]))
    series = build_damage_done(payload)
    assert [(one.actor_id, one.point_start_ms) for one in series] == [(7, 1000), (9, 1000)]
    assert [one.interval_ms for one in series] == [6000.0, 6000.0]


def test_a_series_with_no_interval_is_skipped_rather_than_divided_by() -> None:
    assert build_damage_done(a_payload(a_series(7, [100.0], interval=0.0))) == ()


def test_a_response_carrying_no_graph_ingests_to_nothing() -> None:
    assert build_damage_done({"reportData": {"report": {"graph": None}}}) == ()
```

- [ ] **Step 2: Run them and watch every one fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_ingest_damage_done.py -q
```

Expected: **7 failed**, each an `ImportError` on `build_damage_done`. An error rather than an assertion failure is correct at this point — the function does not exist yet.

- [ ] **Step 3: Add the query**

In `src/wowperf/adapters/wcl/queries.py`, after `DAMAGE_TAKEN_QUERY`:

```python
# Pre-aggregated, so this is one call rather than an unknown number of event
# pages: `events(dataType: DamageDone)` returns at most 10000 rows a page and
# this fight alone logs 8804 damage-taken events. `graph` also folds a pet's
# damage into its owner, which `events` does not -- see the wcl-api skill,
# measured 2026-09-12. Its numbers are a rate; `build_damage_done` converts.
DAMAGE_DONE_GRAPH_QUERY = """
query DamageDoneGraph($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      graph(
        dataType: DamageDone
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
      )
    }
  }
}
"""
```

- [ ] **Step 4: Add the domain model**

In `src/wowperf/domain/model.py`, beside `DamageTakenEvent`:

```python
class DamageDoneSeries(Frozen):
    """One player's damage output over the run, in the buckets the API chose.

    `amounts` holds damage, never a rate: the response states damage per
    second and `build_damage_done` multiplies it back up at the adapter
    boundary, so nothing above it can print a figure section 5.5 refuses to
    produce. Bucket `i` covers `point_start_ms + i * interval_ms`.
    """

    actor_id: int
    point_start_ms: int
    interval_ms: float
    amounts: tuple[int, ...] = ()
```

And on `LoadedRun`, after `damage_taken`:

```python
    # One graph call serves every player, so this carries the whole roster
    # however many are analysed. Fetched on the full profile only: no
    # comparison reads it.
    damage_done: tuple[DamageDoneSeries, ...] = ()
```

- [ ] **Step 5: Add the ingest**

In `src/wowperf/adapters/wcl/ingest.py`, importing `DamageDoneSeries` alongside `DamageTakenEvent`:

```python
def build_damage_done(payload: dict[str, Any]) -> tuple[DamageDoneSeries, ...]:
    """The damage graph as domain series, with its rate converted to amounts.

    The response's numbers are damage per second. Multiplying by the interval
    reproduces the series' own `total` to within 0.3% to 0.7%, the residual
    being the last bucket overhanging the window -- measured 2026-09-12 and
    recorded in the wcl-api skill. Reading them as amounts instead would
    understate every bucket by the interval in seconds, which was 6.4 on the
    run this was measured against, and the chart would look entirely plausible.

    A player's series is keyed by an integer actor id and the run-wide sum by
    the string "Total", which is what drops the latter: nothing here has a use
    for it, and a run-wide damage total sitting in the model is one import away
    from a page that ranks.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    graph = report.get("graph") or {}
    rows = (graph.get("data") or {}).get("series") or []

    built: list[DamageDoneSeries] = []
    for row in rows:
        actor_id = row.get("id")
        if not isinstance(actor_id, int):
            continue
        interval_ms = float(row.get("pointInterval") or 0.0)
        # Guards the division below rather than any observed response: a
        # zero interval would make every bucket zero seconds wide, and a
        # silent column of noughts is worse than no track.
        if interval_ms <= 0:
            continue
        built.append(
            DamageDoneSeries(
                actor_id=actor_id,
                point_start_ms=int(row.get("pointStart") or 0),
                interval_ms=interval_ms,
                amounts=tuple(
                    int(round(float(point) * interval_ms / 1000)) for point in row.get("data") or []
                ),
            )
        )
    return tuple(built)
```

- [ ] **Step 6: Run the tests and watch them pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_ingest_damage_done.py -q
```

Expected: **7 passed**.

- [ ] **Step 7: Mutate, in both directions**

Run each, confirm the named test fails and read its message, then restore.

| Mutation | Must kill |
| --- | --- |
| Drop `* interval_ms / 1000` | `test_a_points_rate_becomes_the_damage_that_bucket_held` — 100 not 600 |
| Use `/ interval_ms * 1000` | the same test — 0 not 600 |
| Hardcode `6000.0` for the interval | `test_the_interval_the_response_states_is_the_one_used` — 600 not 250 |
| Drop the `isinstance(actor_id, int)` guard | `test_the_total_series_is_dropped` |
| Convert only `amounts[0]` | `test_every_bucket_is_converted_not_only_the_first` |

A mutation that kills nothing means the test is decoration. Fix the test, not the mutation.

- [ ] **Step 8: Gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
/mingw64/bin/git add src/wowperf/adapters/wcl/queries.py src/wowperf/domain/model.py src/wowperf/adapters/wcl/ingest.py tests/adapters/wcl/test_ingest_damage_done.py
```

Commit subject: `Read the damage done graph into domain series`. Body: why the graph rather than the event stream, and that its points are a rate.

---

### Task 2: Fetch it on the full profile

**Files:**
- Modify: `src/wowperf/adapters/wcl/repository.py`
- Modify: `tests/adapters/wcl/test_repository.py`

**Interfaces:**
- Consumes: `DAMAGE_DONE_GRAPH_QUERY`, `build_damage_done`, `LoadedRun.damage_done` from Task 1.
- Produces: a `LoadedRun` from `load()` carrying `damage_done`.

- [ ] **Step 1: Read how the existing tests fake a response**

```bash
grep -n "def a_client\|responses\|DAMAGE_TAKEN\|def test_load" tests/adapters/wcl/test_repository.py | head -30
```

Match whatever shape that file already uses to hand a payload back per query. Do not invent a second harness beside it.

- [ ] **Step 2: Write the failing test**

In `tests/adapters/wcl/test_repository.py`, following that file's own fixture style:

```python
def test_a_full_load_carries_the_damage_done_series() -> None:
    """One graph call per run, on the profile that draws the timeline."""
    loaded = a_loaded_run(profile="full")
    assert [series.actor_id for series in loaded.damage_done] == [1]
    assert loaded.damage_done[0].amounts == (600,)


def test_a_speed_reference_never_fetches_the_damage_graph() -> None:
    """No comparison reads it, and a reference run paying for it would spend
    quota on a track nothing draws."""
    loaded = a_loaded_run(profile="speed")
    assert loaded.damage_done == ()
```

Add a graph payload to that file's canned responses, keyed on `DAMAGE_DONE_GRAPH_QUERY`, with one series: `id` 1, `pointInterval` 6000.0, `pointStart` 0, `data` `[100.0]`.

- [ ] **Step 3: Run and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_repository.py -q -k damage_done
```

Expected: FAIL with `[] == [1]` — the field exists and is empty, because nothing fetches it yet. **If it errors instead, the fixture is wrong, not the code.**

- [ ] **Step 4: Fetch it**

In `_load`, immediately after `damage_taken_events` is fetched — below the `profile == "speed"` early return, so only the full profile pays:

```python
        damage_done = build_damage_done(query(DAMAGE_DONE_GRAPH_QUERY, event_variables))
```

and pass `damage_done=damage_done` in the final `LoadedRun(...)` call. Import `DAMAGE_DONE_GRAPH_QUERY` and `build_damage_done` at the top.

- [ ] **Step 5: Run and watch both pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/wcl/test_repository.py -q
```

- [ ] **Step 6: Mutate**

| Mutation | Must kill |
| --- | --- |
| Move the fetch above the `profile == "speed"` return | `test_a_speed_reference_never_fetches_the_damage_graph` |
| Drop `damage_done=damage_done` from the `LoadedRun(...)` call | `test_a_full_load_carries_the_damage_done_series` |

The second matters more than it looks: `Frozen` ignores unknown keyword arguments, so a mistyped keyword here would leave the field empty and raise nothing at all.

- [ ] **Step 7: Gate and commit**

Subject: `Fetch the damage done graph with the run's other streams`.

---

### Task 3: Make room, and build the track

**Files:**
- Modify: `src/wowperf/domain/report/model.py`
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Modify: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: `LoadedRun.damage_done`, `DamageDoneSeries` from Tasks 1 and 2.
- Produces:
  ```python
  DAMAGE_DONE_BASELINE_Y: float   # 116.0
  FIRST_ROW_Y: float              # 136.0, was 96.0
  BADGE_DERIVED_CAPTION: str

  def _damage_done_track(
      series: tuple[DamageDoneSeries, ...], actor_id: int, run: Run,
      scale: float, origin_ms: int,
  ) -> DamageTrack | None

  PlayerTimeline.damage_done: DamageTrack | None
  PlayerTimeline.badge_derived: Badge | None
  PlayerTimeline.badge_derived_caption: str
  ```

**The view models are reused, not duplicated.** `DamageTrack` and `DamageBar` already hold exactly what this track needs — bars, a baseline, a peak label, an axis line, a bucket caption — and the existing one's docstring already states the own-peak rule. A second pair of classes would be the same fields under different names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/report/test_build_player_timeline.py`. Use the file's own helpers (`a_run`, `a_pull`, `a_timeline`, `a_cast`) and add:

```python
def a_done_series(actor_id: int, amounts: tuple[int, ...], interval_ms: float = 6000.0):
    return DamageDoneSeries(
        actor_id=actor_id, point_start_ms=0, interval_ms=interval_ms, amounts=amounts
    )


def test_a_players_damage_done_track_is_scaled_to_their_own_tallest_bucket() -> None:
    """Never to the group's. Two players an order of magnitude apart both draw
    a full-height bar at their own peak, which is the postmortem design's
    section 5.5 expressed as a drawing: a shared scale would rank them."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (100, 50)), a_done_series(2, (10_000, 5_000))),
    )
    small = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    large = a_timeline(loaded, actor_id=2, defensives=KIT).damage_done
    assert small is not None and large is not None
    assert small.bars[0].height == large.bars[0].height
    assert small.bars[1].height == small.bars[0].height / 2


def test_a_damage_done_bar_sits_where_its_bucket_falls_on_the_axis() -> None:
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (100, 100, 100)),),
    )
    track = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    assert track is not None
    gaps = [
        round(track.bars[i + 1].x - track.bars[i].x, 1) for i in range(len(track.bars) - 1)
    ]
    assert len(set(gaps)) == 1, gaps
    assert gaps[0] > 0


def test_a_player_with_no_series_draws_no_damage_done_track() -> None:
    """Absence, not a flat line: a track of zero-height bars reads as a run of
    empty buckets rather than as a figure nobody measured."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(2, (100,)),),
    )
    assert a_timeline(loaded, actor_id=1, defensives=KIT).damage_done is None


def test_a_damage_done_hover_states_an_amount_and_never_a_rate() -> None:
    """The response gives damage per second natively and printing it would
    cost one line. It is the figure section 5.5 refuses to produce."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (600,)),),
    )
    track = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    assert track is not None
    hover = track.bars[0].hover
    assert "600 damage done" in hover
    assert "6 s" in hover
    for forbidden in ("per second", "a second", "DPS", "dps"):
        assert forbidden not in hover


def test_the_damage_done_caption_keeps_a_fractional_bucket_width() -> None:
    """The API's interval is not a whole number of seconds. Rounding it to one
    would claim 6-second buckets for 6.4-second bars."""
    loaded = LoadedRun(
        run=a_run(pulls=(a_pull(0, 0, 600_000),)),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
        damage_done=(a_done_series(1, (600,), interval_ms=6411.7),),
    )
    track = a_timeline(loaded, actor_id=1, defensives=KIT).damage_done
    assert track is not None
    assert "6.4-second bucket" in track.bucket_caption


def test_the_damage_taken_caption_still_reads_as_a_whole_number() -> None:
    """The shared formatter must not turn the existing track's 5 into 5.0."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    if timeline.damage is not None:
        assert "5-second bucket" in timeline.damage.bucket_caption


def test_the_chart_leaves_room_for_the_damage_done_track() -> None:
    """Every row hover strip is placed as a share of the chart's own height,
    so a track added without moving the rows would lay each strip over the
    row above it."""
    loaded = a_covered_run(
        bands=(AuraBand(start_ms=300_000, end_ms=308_000),),
        casts=(a_cast(1, SHIELD.ability_id, 300_000),),
    )
    timeline = a_timeline(loaded, defensives=KIT)
    row = timeline.cooldowns[0]
    assert row.baseline_y == FIRST_ROW_Y
    assert row.hit_top == round(row.baseline_y / timeline.height * 100, 1)
```

Import `DamageDoneSeries` and `FIRST_ROW_Y` at the top of the test file. If `a_timeline` does not already take an `actor_id`, add that parameter to the helper with the existing actor as its default, rather than writing a second helper.

- [ ] **Step 2: Run and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -q
```

Expected: the new tests fail on `ImportError` for `DamageDoneSeries`/`FIRST_ROW_Y`, then on `timeline.damage_done` being absent. **Existing tests must still pass at this point** — nothing has moved yet.

- [ ] **Step 3: Add the view-model fields**

In `src/wowperf/domain/report/model.py`, on `PlayerTimeline`, after `damage`:

```python
    # The same view model as `damage`: a track of bars scaled to this player's
    # own peak is the same object whichever direction the damage went.
    damage_done: DamageTrack | None = None
```

and after `badge_inferred_caption`:

```python
    badge_derived: Badge | None = None
    badge_derived_caption: str = ""
```

- [ ] **Step 4: Move the rows and add the constants**

In `src/wowperf/domain/report/player_timeline.py`, after `DAMAGE_HEIGHT`:

```python
DAMAGE_DONE_GAP = 8.0
"""Clear space between the damage taken bars' baseline and the done track's top."""

DAMAGE_DONE_BASELINE_Y = DAMAGE_BASELINE_Y + DAMAGE_DONE_GAP + DAMAGE_HEIGHT
"""The foot of the damage done bars, which also grow upward from it.

Below the damage taken track and immediately above the first cooldown row,
which is the placement the reader's eye path decides: a press mark is read
against the output that followed it, so the two sit together and nothing goes
between them.
"""
```

and change:

```python
FIRST_ROW_Y = 136.0
```

from 96.0, updating its docstring to say the damage done track is what the extra forty units are.

- [ ] **Step 5: Add the bucket-width formatter and the hover**

```python
def _bucket_width_text(seconds: float) -> str:
    """A bucket width as a reader would write it: "5", and "6.4".

    The damage taken track buckets at a whole five seconds and the graph hands
    back 6.4117, so one formatter serves both without the first gaining a
    decimal it never had.
    """
    return f"{round(seconds, 1):g}"


def _done_bucket_hover(
    amount: int, at_seconds: float, bucket_seconds: float, run: Run, origin_ms: int
) -> str:
    """What one damage done bar holds, when it fell, and which pull it fell in.

    States an amount, never a rate. The response this is built from is in
    damage per second, and printing that would hand the reader the throughput
    figure the postmortem design's section 5.5 refuses to produce.
    """
    start_ms = origin_ms + int(at_seconds * 1000)
    at = format_seconds(at_seconds)
    assert at is not None  # a float input always formats to a string
    names = _bucket_pulls(run, start_ms, start_ms + int(bucket_seconds * 1000))
    where = f"during {' and '.join(names)}" if names else "between pulls"
    return (
        f"{amount:,} damage done in {_bucket_width_text(bucket_seconds)} s, at {at}, {where}"
    )
```

- [ ] **Step 6: Build the track**

```python
def _damage_done_track(
    series: tuple[DamageDoneSeries, ...],
    actor_id: int,
    run: Run,
    scale: float,
    origin_ms: int,
) -> DamageTrack | None:
    """This player's output, in the buckets the API chose, scaled to their own peak.

    Never to the group's, for the reason `_damage_track` states above: a shared
    scale across five players would rank them.

    Returns None where the graph carried no series for this player, so the
    absence is drawn as an absence. A track of zero-height bars would read as a
    run of empty buckets, which is a different claim and one nobody measured.
    """
    ours = next((one for one in series if one.actor_id == actor_id), None)
    if ours is None or not ours.amounts:
        return None

    peak = max(ours.amounts)
    if peak == 0:
        return None

    bucket_seconds = ours.interval_ms / 1000
    offset_seconds = (ours.point_start_ms - origin_ms) / 1000
    width = round(bucket_seconds * scale, PRECISION)
    bars = tuple(
        DamageBar(
            x=round(_track_x(offset_seconds + index * bucket_seconds, scale), PRECISION),
            width=max(width, MIN_BLOCK_WIDTH),
            y=round(DAMAGE_DONE_BASELINE_Y - DAMAGE_HEIGHT * amount / peak, PRECISION),
            height=round(DAMAGE_HEIGHT * amount / peak, PRECISION),
            hover=_done_bucket_hover(
                amount, offset_seconds + index * bucket_seconds, bucket_seconds, run, origin_ms
            ),
        )
        for index, amount in enumerate(ours.amounts)
    )
    return DamageTrack(
        baseline_y=DAMAGE_DONE_BASELINE_Y,
        label_y=round(DAMAGE_DONE_BASELINE_Y - DAMAGE_HEIGHT / 2, PRECISION),
        bars=bars,
        peak_label=(
            f"Tallest bar: {peak:,} damage done in "
            f"{_bucket_width_text(bucket_seconds)} seconds."
        ),
        axis_top_y=round(DAMAGE_DONE_BASELINE_Y - DAMAGE_HEIGHT, PRECISION),
        axis_x0=TRACK_ORIGIN_X,
        axis_x1=TRACK_X1,
        axis_top_label=f"{peak:,}",
        bucket_caption=(
            f"Each bar is a {_bucket_width_text(bucket_seconds)}-second bucket, and the axis "
            f"runs from nothing to this player's own tallest, never the group's."
        ),
    )
```

- [ ] **Step 7: Reuse the formatter in the existing captions**

In `_damage_track` and `_bucket_hover`, replace `int(BUCKET_SECONDS)` with `_bucket_width_text(BUCKET_SECONDS)` in all three places. The rendered text is unchanged — `round(5.0, 1):g` is `"5"` — which `test_the_damage_taken_caption_still_reads_as_a_whole_number` holds.

- [ ] **Step 8: Add the derived badge caption and wire the track in**

Amend the existing caption, which currently says "the damage bars" and would now be ambiguous:

```python
BADGE_MEASURED_CAPTION = "the damage taken bars, the press marks and the cover windows."

BADGE_DERIVED_CAPTION = (
    "the damage done bars, rebuilt from the per-second figures the log's own graph reports."
)
```

In `build_player_timeline`, build the track and pass it, along with `badge_derived=badge_for(Confidence.DERIVED)` and `badge_derived_caption=BADGE_DERIVED_CAPTION` — following exactly how `badge_measured` is set today, including whatever condition guards it.

- [ ] **Step 9: Run the tests and watch them pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -q
```

Expected: all pass, **including the pre-existing `hit_top` tests** — they are what prove the strips followed the rows down.

- [ ] **Step 10: Mutate**

| Mutation | Must kill |
| --- | --- |
| `peak = max(amount for s in series for amount in s.amounts)` (group-wide) | `test_a_players_damage_done_track_is_scaled_to_their_own_tallest_bucket` |
| Leave `FIRST_ROW_Y = 96.0` | `test_the_chart_leaves_room_for_the_damage_done_track` |
| Return an empty `DamageTrack()` instead of `None` | `test_a_player_with_no_series_draws_no_damage_done_track` |
| `f"{amount / bucket_seconds:,.0f} damage a second"` in the hover | `test_a_damage_done_hover_states_an_amount_and_never_a_rate` |
| `int(bucket_seconds)` in the caption | `test_the_damage_done_caption_keeps_a_fractional_bucket_width` |
| `f"{seconds:.1f}"` in `_bucket_width_text` | `test_the_damage_taken_caption_still_reads_as_a_whole_number` |

- [ ] **Step 11: Gate and commit**

Subject: `Draw what a player's damage did beside when they pressed`.

---

### Task 4: Render it

**Files:**
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Modify: `tests/adapters/render/test_html_sections.py`
- Modify: `tests/adapters/render/test_html_invariants.py`
- Modify: the golden file, via `--golden-update`

**Interfaces:**
- Consumes: `PlayerTimeline.damage_done`, `badge_derived`, `badge_derived_caption` from Task 3.

- [ ] **Step 1: Write the failing tests**

In `tests/adapters/render/test_html_sections.py`, give `a_drawn_timeline()` a `damage_done` track — mirroring the `damage=DamageTrack(...)` it already builds, with `baseline_y=116.0` and one bar — plus `badge_derived=Badge(label="derived", tint="badge-derived")` and a caption. Then:

```python
def test_a_timeline_draws_the_damage_done_bars() -> None:
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>", 1
    )[1]
    assert 'class="damage-done-bar"' in body


def test_a_timeline_names_the_damage_done_track_beside_it() -> None:
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>", 1
    )[1]
    assert "Damage done" in body


def test_a_timeline_legend_grades_the_damage_done_bars_as_derived() -> None:
    body = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),))).split(
        "</style>", 1
    )[1]
    assert "badge-derived" in body
```

In `tests/adapters/render/test_html_invariants.py`, add the page-wide no-rate invariant beside the existing ones:

```python
def test_no_timeline_hover_states_a_damage_rate() -> None:
    """The graph this track is built from reports damage per second, and the
    postmortem design's section 5.5 refuses to produce that figure. The
    conversion happens in ingest; this holds the page to it."""
    body = render(a_full_report()).split("</style>", 1)[1]
    for forbidden in ("damage a second", "per second", "DPS"):
        assert forbidden not in body
```

Use whatever whole-report helper that file already has in place of `a_full_report()`.

- [ ] **Step 2: Run and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render -q
```

Expected: the three markup tests fail on the missing class and label. **The no-rate invariant will pass immediately** — nothing prints a rate yet. That is a test which cannot currently fail, so prove it can: temporarily make `_done_bucket_hover` print `"damage a second"`, re-run, watch it fail, then revert. A guard nobody has seen fail is not a guard.

- [ ] **Step 3: Render the track**

In `_player_timeline.html.j2`, after the `{% if timeline.damage %}` block and before the cooldown rows loop:

```jinja
  {% if timeline.damage_done %}
  <line class="damage-axis" x1="{{ timeline.damage_done.axis_x0 }}" y1="{{ timeline.damage_done.axis_top_y }}"
        x2="{{ timeline.damage_done.axis_x1 }}" y2="{{ timeline.damage_done.axis_top_y }}"/>
  <text class="tick-label row-label" x="{{ timeline.label_x }}"
        y="{{ timeline.damage_done.axis_top_y }}">{{ timeline.damage_done.axis_top_label }}</text>
  {% for bar in timeline.damage_done.bars %}
  <rect class="damage-done-bar" x="{{ bar.x }}" y="{{ bar.y }}" width="{{ bar.width }}" height="{{ bar.height }}"><title>{{ bar.hover }}</title></rect>
  {% endfor %}
  <text class="track-label row-label" x="{{ timeline.label_x }}" y="{{ timeline.damage_done.label_y }}">Damage done</text>
  {% endif %}
```

Add the peak and bucket captions to the `<p class="sub">` line the damage track already uses, and the derived badge to the badge legend paragraph, both following the existing pattern exactly.

- [ ] **Step 4: Add the colour**

In `report.css.j2`, beside `.damage-bar`:

```css
.damage-done-bar { fill: var(--done); }
```

with `--done` defined in the palette block as a hue distinct from the damage bars and from the four cooldown-row states, in both the light and dark blocks if that file defines both.

- [ ] **Step 5: Run the render tests and watch them pass**

- [ ] **Step 6: Add the invariant allowlist entries**

In `tests/adapters/render/test_html_invariants.py`, add to `NUMBERS_THAT_ARE_NOT_TOTALS` any numeric field this work introduced on a view model. If `DamageTrack` is reused unchanged, there may be none — **check rather than assume**, and run that test to confirm:

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_invariants.py -q
```

- [ ] **Step 7: Regenerate the golden file**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest --golden-update -q
```

**Read the diff before accepting it.** Expect the CSS rule and, if the minimal fixture carries a damage-done series, the track's markup. If the diff carries anything else — moved cooldown rows, changed strip percentages — stop and find out why before committing.

```bash
/mingw64/bin/git diff --stat
```

- [ ] **Step 8: Gate and commit**

Subject: `Put the damage done track on the page`.

---

### Task 5: Verify on a rendered report

The offline suite cannot see a strip laid over the wrong row, and this change moved every row.

**Files:** none. This task produces a verification, not a diff.

- [ ] **Step 1: Ask RwlRwlRwlRwl to authorise one render**

State what will run and what it costs. **Do not run it before the answer.** A warm-cache render of this report cost 1.00 point on 2026-09-12; the graph query adds one uncached call the first time.

- [ ] **Step 2: Render**

```bash
export PATH="$HOME/.local/bin:$PATH" && set -a && . <(iconv -f UTF-16 -t UTF-8 .env | tr -d '\r') && set +a && uv run wowperf analyze G7MBJZfNakrcPvAx --fight 3 --all-players
```

The `.env` is UTF-16; a naive read sees mojibake.

- [ ] **Step 3: Check the track reached the page**

```bash
grep -c 'class="damage-done-bar"' out/G7MBJZfNakrcPvAx-3.html
grep -o 'damage done in [0-9.]* s' out/G7MBJZfNakrcPvAx-3.html | head -3
grep -c 'per second\|damage a second\|DPS' out/G7MBJZfNakrcPvAx-3.html
```

Expect: several hundred bars, hovers reading "damage done in 6.4 s", and **zero** rate mentions.

- [ ] **Step 4: Check the strips still land on their rows**

Serve `out/` and measure — screenshots and every layout reading come back **zero until a viewport is set**, so call `resize_window` with an explicit width first. For each `.row-hit`, compare its box against the `<text class="row-label">` of the row it names; the worst mismatch measured before this change was 0.19 px at 1400 px. Anything over a pixel means `FIRST_ROW_Y` and the chart height disagree.

Note `elementFromPoint` returns the `.row-hit` strip, not the SVG beneath it — a paint-order question needs `elementsFromPoint`.

- [ ] **Step 5: Sanity-check one figure against the API's own total**

For one player, sum that track's bar amounts and compare against the `total` the graph reported. Expect agreement within about 1% — the design records 0.3% to 0.7% from the last bucket's overhang, plus per-bucket rounding. **A gap near a factor of 6.4 means the rate conversion was lost somewhere after ingest.**

- [ ] **Step 6: Report to RwlRwlRwlRwl**

Say what was measured, not that it looks right. Send the rendered report with `SendUserFile`.

---

## Self-review

**Spec coverage.** §1 needs no task. §2 is Tasks 1 and 2; §2.1 the rate is Task 1 Steps 5 and 7; §2.2 pets need no code, as the design says; §2.3 the `Total` drop is Task 1. §3 geometry and own-peak scaling are Task 3 Steps 4, 6 and 10; §3.1 the fractional bucket width is Task 3 Steps 5 and 7. §4's derived badge is Task 3 Step 8 and Task 4 Step 1. §5's refusals: no rate is tested in Tasks 3 and 4 and verified in Task 5; no finding is enforced by there being no analyser task at all; own-peak scaling and the abstention are Task 3. §6's six tests map to Tasks 1, 3 and 4, the seam to Task 4, and the strip regression to Task 5 Step 4.

**Placeholders.** None. Every step carries the code or the command it needs. Two steps deliberately say "match the file's existing shape" rather than inventing one — Task 2 Step 1 and Task 4 Step 1 — because guessing at a fixture harness that already exists is how a plan produces a second one.

**Type consistency.** `DamageDoneSeries(actor_id, point_start_ms, interval_ms, amounts)` is used with those names in Tasks 1, 2 and 3. `build_damage_done(payload) -> tuple[DamageDoneSeries, ...]` is called in Task 2 with a payload and nothing else. `_damage_done_track(series, actor_id, run, scale, origin_ms) -> DamageTrack | None` returns the same `DamageTrack` the template already renders, so Task 4 reads `axis_x0`, `axis_top_y`, `axis_top_label`, `label_y`, `bars`, `peak_label` and `bucket_caption` — all fields that exist on it today.
