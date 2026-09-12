# Report second reading — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the seven points the second reading of a real report produced, without the page
claiming anything the log does not support.

**Architecture:** Four independent phases. A drops rows and pins the health curve on a death
card; B moves the player timeline's icons into the gutter and gives its colours a key; C teaches
the interrupt findings to say whether a spell was interruptible at all; D puts tooltips on the
ledger cards, half of them built in `build.py` from data it already holds and half carried on the
finding itself.

**Tech Stack:** Python 3.12, pydantic (`Frozen`), Jinja2, pytest, ruff, mypy, `uv`.

**Spec:** `docs/plans/2026-09-12-report-second-reading-design.md`. Read it first; every task below
argues from a numbered section of it.

## Global Constraints

Copied from `CLAUDE.md` and from the project memory. Every task's requirements include these.

- **`uv` is not on PATH in the Bash tool.** Every command that uses it must begin
  `export PATH="$HOME/.local/bin:$PATH"`.
- **Long bash heredocs fail on this machine.** Write file contents with the Write/Edit tools,
  never with `cat <<EOF`.
- **Use relative forward-slash paths in shell commands.** An absolute Windows path once created a
  literal file named `C:Usersdamien...` at the repository root.
- **Commit messages are plain ASCII.** A `§` once landed in a commit body as `SS`.
- **Never use `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.** State any other git flag
  before running it.
- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`,
  `jinja2`, or anything touching network, disk or template.
- **Every finding carries a confidence badge** — `measured`, `derived` or `inferred`.
- **The report loads nothing.** One HTML file: no stylesheet link, no `@import`, no remote `src`,
  exactly one inline script, which may only show, hide and highlight.
  `tests/adapters/render/test_html_invariants.py` enforces this and must stay green.
- **Never invent an API field name.** `.claude/skills/wcl-api/SKILL.md` is the verified reference.
- **Test data:** no real character name in `tests/`. The sanctioned set is `Emberkin`,
  `Stonewake`, `Bríala`, `Кириллица`.
- **TDD.** Read `.claude/skills/testing/test-driven-development/SKILL.md` with the Read tool — it
  is nested and the harness does not surface it.
- **Every test must fail when the decision it pins is mutated**, not merely when the code is
  touched. This repository's recurring defect is a test that cannot fail.

**The gate, run before every commit:**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

## File Structure

**Created:**

- `src/wowperf/domain/report/finding_tooltip.py` — builds `dict[str, Tooltip]` keyed by finding
  id, for the ledger cards. One responsibility: deciding which panel a finding gets.
- `tests/domain/report/test_finding_tooltip.py`

**Modified:**

| File | Responsibility after this plan |
| --- | --- |
| `src/wowperf/domain/analysis/recap.py` | `consumable_state` returns `None` for a category never drunk |
| `src/wowperf/domain/analysis/interrupts.py` | Per-ability findings carry the interruptible claim and its facts |
| `src/wowperf/domain/findings.py` | `Finding.facts`, and the `FindingFact` it holds |
| `src/wowperf/domain/report/deaths.py` | Drops cast rows with no drawable band; imports the moved tooltip builder |
| `src/wowperf/domain/report/tooltip.py` | Gains `run_ability_tooltip`, moved from `deaths.py` |
| `src/wowperf/domain/report/player_timeline.py` | One icon per row; the state key; damage bucket hovers |
| `src/wowperf/domain/report/model.py` | `LedgerRow.tooltip`, `StateKey`, `DamageBar.hover`, `Press` loses `icon_x` |
| `src/wowperf/domain/report/ledger.py` | `ledger_row` takes a tooltip map and looks up, never computes |
| `src/wowperf/domain/report/players.py` | Passes the tooltip map through |
| `src/wowperf/domain/report/build.py` | Builds the tooltip map once |
| `src/wowperf/adapters/render/_deaths.html.j2` | The sticky curve wrapper |
| `src/wowperf/adapters/render/_player_timeline.html.j2` | Gutter icon, state key, bucket titles |
| `src/wowperf/adapters/render/_macros.html.j2` | `ledger_row` passes `row.tooltip` to `ability()` |
| `src/wowperf/adapters/render/report.css.j2` | Sticky rule, state key rule |

---

# Phase A — the death card (design §4)

### Task 1: A cast row survives only when its press has a drawable band

**Design:** §4.1.

**Files:**
- Modify: `src/wowperf/domain/report/deaths.py` — `build_deaths`, around the `timeline = tuple(...)`
  comprehension
- Test: `tests/domain/report/test_build_deaths.py`

**Interfaces:**
- Consumes: `report/deaths.py::_press_band(event, death, auras) -> tuple[int, int] | None`, which
  already exists and already decides whether a row gets a cover rectangle.
- Produces: nothing new. `build_deaths` keeps its signature.

**Why this test and not another:** the rule is "a cast with a band stays, a cast without one
goes". Both halves need a test, because a filter that drops every cast passes the first half
alone, and a filter that drops nothing passes the second.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/report/test_build_deaths.py`:

```python
def test_a_cast_with_no_resolvable_buff_is_not_a_row() -> None:
    """An offensive cast says nothing a death card can draw, so it is not drawn."""
    card = a_card_with_casts(("Rampage", 845_000), auras=None)
    assert [row.ability for row in card.timeline] == []


def test_a_cast_whose_buff_the_card_can_draw_stays() -> None:
    """A press with a cover band has a window and figures worth a row."""
    card = a_card_with_casts(("Whirlwind", 845_000), auras=auras_covering("Whirlwind"))
    assert [row.ability for row in card.timeline] == ["Whirlwind"]


def test_a_heal_that_landed_for_nothing_still_gets_a_row() -> None:
    """Overheal is a fact about who was healing; only casts are filtered."""
    card = a_card_with_heal(amount=0)
    assert [row.detail for row in card.timeline] == ["+0 from Emberkin"]
```

Write `a_card_with_casts`, `a_card_with_heal` and `auras_covering` as module-level helpers in
that test file, following the `loaded`/`a_death` idiom already used in
`tests/domain/analysis/test_recap_timeline.py`.

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_deaths.py -k "cast_with_no_resolvable or cast_whose_buff or heal_that_landed" -v
```

Expected: the first fails (the row is present today), the other two pass.

- [ ] **Step 3: Implement the filter**

In `build_deaths`, between `events = recap_timeline(loaded, death)` and the `timeline = tuple(...)`
comprehension:

```python
        # Every event still reaches the curve and the press tooltips below:
        # health is reconstructed from the whole run-up, and a press sums what
        # arrived inside its cover from the same unfiltered list. Only which
        # rows a reader is shown narrows here -- see design section 4.1.
        drawn = tuple(
            event
            for event in events
            if event.kind != CAST or _press_band(event, death, auras) is not None
        )
```

Then build `timeline` from `drawn` while still passing `events` as the last argument of
`_recap_row`, and keep `enumerate` over `drawn` so marker ids stay unique.

- [ ] **Step 4: Run the full file**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_deaths.py -v
```

Expected: PASS. `timeline_summary` counts `drawn`, so any golden file asserting an event count
changes with it — update the expected count, never the assertion.

- [ ] **Step 5: Mutate and confirm a test dies**

Change the condition to `if event.kind != CAST` and re-run. `test_a_cast_with_no_resolvable_buff_is_not_a_row`
must fail. Change it to `if False` and `test_a_cast_whose_buff_the_card_can_draw_stays` must fail.
Restore.

- [ ] **Step 6: Gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add src/wowperf/domain/report/deaths.py tests/domain/report/test_build_deaths.py
git commit -m "Show a cast on a death card only when it covered something" -m "A death recap listed every button the dying player pressed. On one real death that was eleven rows of offence among forty-five, and the five rows that explained the death sat under twenty-seven rows in which nothing happened. A press whose buff the card can draw has a window and figures worth a row; one without has only the fact that a button was pressed." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The health curve stays on screen while the table scrolls

**Design:** §4.2.

**Files:**
- Modify: `src/wowperf/adapters/render/_deaths.html.j2` — wrap the `svg.hp-curve` and the two
  legend paragraphs beneath it
- Modify: `src/wowperf/adapters/render/report.css.j2` — one rule
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: nothing. Presentation only; no view model changes.
- Produces: a `div.hp-pinned` wrapping the curve and its legends.

**Why this test:** the invariant test already forbids adding a script or a remote source. What it
cannot see is whether the wrapper exists and holds the right children, which is the whole change.

- [ ] **Step 1: Write the failing test**

In `tests/adapters/render/test_html_sections.py`:

```python
def test_the_health_curve_and_its_legends_share_a_pinned_wrapper() -> None:
    """A reader hovering a row 1400px down still needs the curve the row lights."""
    html = render_a_report_with_a_death()
    wrapper = one_element(html, "div", class_="hp-pinned")
    assert wrapper.find("svg", class_="hp-curve") is not None
    assert len(wrapper.find_all("p", class_="legend")) == 2
```

Follow whichever parsing helper that file already uses; do not introduce a new HTML parser.

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_sections.py -k pinned -v
```

Expected: FAIL — no element with that class.

- [ ] **Step 3: Wrap the markup**

In `_deaths.html.j2`, wrap the existing curve block and the two legend paragraphs that follow it
in `<div class="hp-pinned"> ... </div>`. Move nothing else inside.

- [ ] **Step 4: Add the rule**

In `report.css.j2`, beside the other `.hp-*` rules:

```css
/* The curve outlives the table's scroll. A row's hover lights a marker on the
   curve and a press lights the window its buff covered; both were invisible
   while the card stood 2007px tall and the curve left the screen at 300. No
   script: this asks the page's one inline script for nothing.
   Safe because nothing in this card's ancestry sets `overflow` -- the whole
   stylesheet sets it once, on `.icon-defs`. */
.hp-pinned { position: sticky; top: 0; z-index: 4; background: var(--card); }
```

`z-index: 4` sits below `.tip`'s 5, so a tooltip rising from a row still covers the pinned curve
rather than being hidden behind it.

- [ ] **Step 5: Run the test and the invariants**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/ -v
```

Expected: PASS, including `test_html_invariants.py`.

- [ ] **Step 6: Look at it**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf analyze G7MBJZfNakrcPvAx --fight 3 --no-compare --out out
```

`--no-compare` keeps this offline against the existing cache. Serve `out/` with the `report`
config in `.claude/launch.json` and scroll the Deaths tab: the curve must stay, and hovering a
row far down the table must still light its marker.

- [ ] **Step 7: Gate and commit**

```bash
git add src/wowperf/adapters/render/_deaths.html.j2 src/wowperf/adapters/render/report.css.j2 tests/adapters/render/test_html_sections.py
git commit -m "Keep a death's health curve on screen while its table scrolls" -m "The card stands 2007px tall against a 900px viewport, so the curve left the screen before the rows a reader came to read. Hovering a row lights a marker on that curve and a press lights the window its buff covered, and neither had ever been visible to anyone reading the table." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: A consumable nobody drank from is not offered

**Design:** §4.3.

**Files:**
- Modify: `src/wowperf/domain/analysis/recap.py` — `consumable_state`, `availability_at`
- Test: `tests/domain/analysis/test_recap_availability.py`

**Interfaces:**
- Produces: `consumable_state(presses, category, death_ms) -> AbilityState | None` — the return
  type changes from `AbilityState`. `availability_at` drops the `None`s.

**Why this test:** the page contradicted itself — `consumables.never.Rxmain` said no healthstone
was used all run while the death card said one was ready. The test that matters is the one that
fails if the `UNSEEN` case is put back.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/analysis/test_recap_availability.py`:

```python
def test_a_category_never_drunk_is_not_listed_at_all() -> None:
    """The log proves nothing about a consumable nobody used; the run-level
    finding says so once, and the card says nothing."""
    assert consumable_state((), STONE, DEATH_MS) is None


def test_a_category_drunk_long_ago_is_listed_as_ready() -> None:
    drunk = (press(6262, DEATH_MS - 300_000),)
    state = consumable_state(drunk, STONE, DEATH_MS)
    assert state is not None and state.state == READY


def test_availability_omits_the_row_for_a_category_never_drunk() -> None:
    at = availability_at(
        loaded(casts=()), a_death(DEATH_MS),
        Defensives(), Consumables(categories=(STONE,)), Externals(),
        visible_from_ms=0,
    )
    assert at.consumables == ()
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_recap_availability.py -k "never_drunk or drunk_long_ago or omits_the_row" -v
```

Expected: the first and third fail; the second passes already.

- [ ] **Step 3: Change the rule**

Replace `consumable_state`'s body and docstring:

```python
def consumable_state(
    presses: tuple[CastEvent, ...], category: ConsumableCategory, death_ms: int
) -> AbilityState | None:
    """A consumable category's state, or None when the player never drank from it all run.

    A category nobody touched is not an opportunity missed, it is a category
    the log says nothing about: a consumable reaches the log only when it is
    drunk, so silence cannot tell a bag with one in it from a bag without.
    `analysis/consumables.py::consumables_up_at` settled this for the finding
    and its docstring records the run that settled it -- every death of every
    player carried a healthstone line, "true, unarguable and worth nothing".
    The card said the opposite of the finding on the same page until this
    returned None.
    """
    state = state_of(presses, category.name, category.cooldown_seconds, 1, death_ms)
    return None if state.state == UNSEEN else state
```

In `availability_at`, keep the comprehension and drop the `None`s:

```python
    drinks = None
    if player is not None and consumables.categories:
        drinks = tuple(
            state
            for category in consumables.categories
            if consumable_window_start(category, death_ms) >= visible_from_ms
            and (state := consumable_state(
                presses_of(death.actor_id, category.ability_ids), category, death_ms
            )) is not None
        )
```

- [ ] **Step 4: Run the file**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_recap_availability.py tests/domain/report/test_build_deaths.py -v
```

Expected: PASS. If a death card test asserted a healthstone row, that assertion was asserting the
bug — change what it expects, and say so in the commit body.

- [ ] **Step 5: Mutate and confirm a test dies**

Change the return to `return state` and re-run. `test_a_category_never_drunk_is_not_listed_at_all`
and `test_availability_omits_the_row_for_a_category_never_drunk` must both fail. Restore.

- [ ] **Step 6: Gate and commit**

```bash
git add src/wowperf/domain/analysis/recap.py tests/domain/analysis/test_recap_availability.py
git commit -m "Stop offering a consumable the run never saw" -m "The summary said a player used no healthstone at any point and could not tell a bag with one from a bag without. The death card, three tabs away, said the healthstone was ready. The finding had learned this rule and recorded the run that taught it; the card had never been told." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# Phase B — the player timeline (design §5)

### Task 4: One icon per row, in the gutter

**Design:** §5.1.

**Files:**
- Modify: `src/wowperf/domain/report/player_timeline.py` — `TRACK_ORIGIN_X`, new `ICON_SIZE`,
  `LABEL_X`, the `Press` construction, `build_player_timeline`
- Modify: `src/wowperf/domain/report/model.py` — `Press` loses `icon_x`; `PlayerTimeline` gains
  `row_icon_x: float` and `row_icon_size: float`
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Produces: `PlayerTimeline.row_icon_x: float`, `PlayerTimeline.row_icon_size: float`;
  `CooldownRow.ability_id` is unchanged and is what the template draws.
- Removes: `Press.icon_x`. Nothing outside the template and its tests reads it.

**Geometry, computed and not eyeballed.** `ICON_SIZE` is `ROW_HEIGHT` (16). The icon sits
immediately left of the track, so the gutter grows by `ICON_SIZE + LABEL_GAP` = 20 and
`TRACK_ORIGIN_X` goes from 130 to **150**. `LABEL_X` stays `TRACK_ORIGIN_X - LABEL_GAP -
ICON_SIZE - LABEL_GAP` = **126**, which is the value it has today, so the existing check that the
longest name in the data files fits still passes unchanged. The track loses 20 units of its
width, which at a 1260-unit track is 1.6%.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/report/test_build_player_timeline.py`:

```python
def test_a_row_draws_one_icon_however_many_presses_it_has() -> None:
    """281 icons across five players, 67 of them overlapping a neighbour, was
    the state this replaced: an icon per press, ROW_HEIGHT wide, which is
    seventeen seconds of a twenty-three minute run."""
    timeline = a_timeline_with_presses(count=31)
    assert timeline.row_icon_x + timeline.row_icon_size <= timeline.cooldowns[0].presses[0].x


def test_the_longest_ability_name_still_fits_the_gutter() -> None:
    longest = max(len(name) for name in every_name_in_the_data_files())
    assert longest * LABEL_UNITS_PER_CHARACTER <= LABEL_X


def test_the_icon_sits_between_the_label_and_the_track() -> None:
    timeline = a_timeline_with_presses(count=1)
    assert LABEL_X <= timeline.row_icon_x
    assert timeline.row_icon_x + timeline.row_icon_size <= TRACK_ORIGIN_X
```

The second test may already exist in some form — extend it rather than adding a second copy.

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -k "one_icon or longest_ability or icon_sits" -v
```

Expected: FAIL — `row_icon_x` does not exist.

- [ ] **Step 3: Change the geometry and the model**

In `player_timeline.py`:

```python
ICON_SIZE = ROW_HEIGHT
"""A row's icon is as tall as its row, and square.

Drawn once, in the gutter. It was drawn at every press until 2026-09-12, at
this same size -- which is about seventeen seconds of a twenty-three minute
run, so any ability pressed oftener than that overlapped itself. Across five
players the page drew 281 of them and 67 overlapped a neighbour.
"""

ICON_X = TRACK_ORIGIN_X - LABEL_GAP - ICON_SIZE
"""Where the row's icon starts: immediately left of the track, clear of it by `LABEL_GAP`."""
```

Set `TRACK_ORIGIN_X = 150.0` and `LABEL_X = ICON_X - LABEL_GAP`. Delete `icon_x` from `Press` in
`model.py` and from wherever `player_timeline.py` sets it. Add `row_icon_x` and `row_icon_size` to
`PlayerTimeline` and populate them from `ICON_X` and `ICON_SIZE`.

- [ ] **Step 4: Draw it once**

In `_player_timeline.html.j2`, delete the `<use>` inside the press loop and add one before it,
inside the row's `<g>`:

```jinja
  {% if row.ability_id in icons_by_id %}
  <use href="#icon-{{ row.ability_id }}" x="{{ timeline.row_icon_x }}" y="{{ row.baseline_y }}"
       width="{{ timeline.row_icon_size }}" height="{{ timeline.row_icon_size }}"/>
  {% endif %}
```

- [ ] **Step 5: Run the tests**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/ tests/adapters/render/ -v
```

Expected: PASS. Golden files holding the old coordinates change; check each diff is a coordinate
and not a disappeared element before accepting it.

- [ ] **Step 6: Mutate and confirm a test dies**

Restore the `<use>` inside the press loop. `test_a_row_draws_one_icon_however_many_presses_it_has`
must fail. Set `TRACK_ORIGIN_X` back to 130 and `test_the_longest_ability_name_still_fits_the_gutter`
must fail. Restore both.

- [ ] **Step 7: Gate and commit**

```bash
git add src/wowperf/domain/report/player_timeline.py src/wowperf/domain/report/model.py src/wowperf/adapters/render/_player_timeline.html.j2 tests/domain/report/test_build_player_timeline.py
git commit -m "Draw a cooldown row's icon once, beside its name" -m "The page drew an ability's icon at every press and then painted the press mark on top of it, which is why the icons looked cut. At sixteen units the icon covers about seventeen seconds of a twenty-three minute run, so a short cooldown overlapped itself: 281 icons across five players, 67 of them overlapping. One icon in the gutter is 19, and it leaves the track free to show the four states it was always drawing." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: A key for the track's four states

**Design:** §5.2.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` — new `StateKey`, `PlayerTimeline.state_key`
- Modify: `src/wowperf/domain/report/player_timeline.py` — the constant and its construction
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`, `report.css.j2`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Produces: `StateKey(label: str, css_class: str)`; `PlayerTimeline.state_key: tuple[StateKey, ...]`.
  `css_class` is the same class the track's own rectangles carry, so the key cannot drift from
  what it names.

**Why this test:** `LEGEND` explains the mark, the cooldown stretch, the unjudged opening and the
ready tick, and never says what the green is. A key whose classes are written out by hand would
drift the first time a colour moved; the test pins them to the track's own classes.

- [ ] **Step 1: Write the failing test**

```python
def test_the_key_names_every_state_the_track_draws() -> None:
    """Green was never named anywhere near the chart: LEGEND covers the mark,
    the cooldown stretch, the pale opening and the ready tick, and stops."""
    timeline = a_timeline_with_presses(count=3)
    assert [key.css_class for key in timeline.state_key] == [
        "press", "cover", "on-cooldown", "not-judged",
    ]
    assert [key.label for key in timeline.state_key] == [
        "a press", "the buff up", "on cooldown", "not judged",
    ]
```

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -k names_every_state -v
```

Expected: FAIL — `state_key` does not exist.

- [ ] **Step 3: Implement**

In `player_timeline.py`:

```python
STATE_KEY = (
    StateKey(label="a press", css_class="press"),
    StateKey(label="the buff up", css_class="cover"),
    StateKey(label="on cooldown", css_class="on-cooldown"),
    StateKey(label="not judged", css_class="not-judged"),
)
"""The four states the track paints, each named in the class it is painted with.

The class is carried rather than the colour so the key and the track cannot
disagree: a swatch takes the same rule the rectangle it stands for takes.
`LEGEND` explains three of these four in prose and has never named the cover,
which is the one a reader is least able to guess.
"""
```

In the template, after the `<svg>` and before the legends:

```jinja
<p class="state-key">{% for key in timeline.state_key %}<span class="state-swatch {{ key.css_class }}"></span>{{ key.label }}{% if not loop.last %} · {% endif %}{% endfor %}</p>
```

In `report.css.j2`:

```css
/* A swatch takes the same fill rule as the rectangle it stands for, so the
   key cannot drift from the track. `.not-judged` is a stroke and no fill, so
   the swatch shows its dash the way the track does. */
.state-key { color: var(--ink-dim); font-size: 12px; margin: 2px 0; }
.state-swatch { display: inline-block; width: 10px; height: 10px; margin-right: 4px;
  vertical-align: -1px; border-radius: 2px; }
.state-swatch.press { background: var(--ours); }
.state-swatch.cover { background: var(--badge-measured); }
.state-swatch.on-cooldown { background: var(--cooldown); }
.state-swatch.not-judged { border: 1px dashed var(--ink-faint); }
```

- [ ] **Step 4: Run the tests**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/ tests/adapters/render/ -v
```

Expected: PASS.

- [ ] **Step 5: Mutate and confirm a test dies**

Drop the `cover` entry from `STATE_KEY`. The test must fail. Restore.

- [ ] **Step 6: Gate and commit**

```bash
git add src/wowperf/domain/report/player_timeline.py src/wowperf/domain/report/model.py src/wowperf/adapters/render/_player_timeline.html.j2 src/wowperf/adapters/render/report.css.j2 tests/domain/report/test_build_player_timeline.py
git commit -m "Name the four states the cooldown track paints" -m "The legend explained the press mark, the cooldown stretch, the unjudged opening and the ready tick, and never said what the green was. A reader met a colour carrying a measured claim with nothing on the page naming it." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: A damage bucket says what it holds

**Design:** §5.3.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` — `DamageBar.hover: str`
- Modify: `src/wowperf/domain/report/player_timeline.py` — the bar construction
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Produces: `DamageBar.hover: str = ""` — the figure, the bucket width, the moment, and the pull.

- [ ] **Step 1: Write the failing test**

```python
def test_a_damage_bucket_says_what_it_holds_and_where() -> None:
    """A spike is only a question until a reader knows which pull it fell in."""
    timeline = a_timeline_with_damage(amount=11_418_755, at_seconds=875.0, pull="Atroxus")
    assert timeline.damage.bars[0].hover == (
        "11,418,755 unmitigated in 5 s, at 14:35, during Atroxus"
    )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_player_timeline.py -k bucket_says -v
```

Expected: FAIL — `hover` does not exist.

- [ ] **Step 3: Implement**

Add `hover: str = ""` to `DamageBar`. Where the bars are built, format it with the existing
`format_seconds`-style helper from `report/frame.py` for the timestamp, and resolve the pull by
the same band lookup the chart already does. A bucket falling between pulls says
`", between pulls"` instead of `", during <name>"`.

- [ ] **Step 4: Draw it**

```jinja
  <rect class="damage-bar" x="{{ bar.x }}" y="{{ bar.y }}" width="{{ bar.width }}" height="{{ bar.height }}"><title>{{ bar.hover }}</title></rect>
```

- [ ] **Step 5: Run the tests, gate and commit**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

```bash
git add src/wowperf/domain/report/player_timeline.py src/wowperf/domain/report/model.py src/wowperf/adapters/render/_player_timeline.html.j2 tests/domain/report/test_build_player_timeline.py
git commit -m "Say what a damage bucket holds and which pull it fell in" -m "The track drew a spike and left the reader to find its pull by eye against the bands behind it." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# Phase C — what can be said about interruptible (design §7)

### Task 7: A finding can carry labelled figures

**Design:** §6.2, second bullet.

**Files:**
- Modify: `src/wowperf/domain/findings.py` — new `FindingFact`, `Finding.facts`
- Test: `tests/domain/test_findings.py`

**Interfaces:**
- Produces:

```python
class FindingFact(Frozen):
    label: str
    value: str
    confidence: Confidence | None = None
```

and `Finding.facts: tuple[FindingFact, ...] = ()`.

**Why this and not string parsing:** every figure a panel wants is already in the finding, as
prose and as evidence strings — "range 0.7 to 2.1 casts a minute across 5 top parses". A builder
that took those apart again would be parsing its own output. `facts` is the same discipline as
`evidence` in a shape a panel can render: `evidence` is prose for a list, `facts` are figures for
a panel.

- [ ] **Step 1: Write the failing test**

```python
def test_a_finding_carries_no_facts_by_default() -> None:
    """Most findings have nothing a panel would add to what their card prints."""
    assert a_finding().facts == ()


def test_a_fact_may_carry_its_own_confidence_tier() -> None:
    """A panel mixes tiers -- an assumed cooldown beside a measured count --
    so a tier belongs to the line, not to the panel."""
    fact = FindingFact(label="Base cooldown", value="25 s", confidence=Confidence.INFERRED)
    assert fact.confidence is Confidence.INFERRED
```

- [ ] **Step 2: Run and watch fail; Step 3: implement; Step 4: run and watch pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/test_findings.py -v
```

- [ ] **Step 5: Check the findings file still round-trips**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/ tests/test_cli.py -v
```

Expected: PASS. The new field is optional with a default, so an existing findings file still
loads and a new one gains one key.

- [ ] **Step 6: Gate and commit**

```bash
git add src/wowperf/domain/findings.py tests/domain/test_findings.py
git commit -m "Let a finding carry labelled figures beside its prose" -m "A finding states its figures twice already, in a title a person reads and in evidence strings a person scans. A panel wants them a third way, as labels and values, and the only alternative was for the report to parse strings the analysis had just formatted." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: An interrupt finding says whether the spell was interruptible

**Design:** §7.

**Files:**
- Modify: `src/wowperf/domain/analysis/interrupts.py` — `analyse_interrupts`
- Test: `tests/domain/analysis/test_interrupts.py`

**Interfaces:**
- Consumes: `FindingFact` from Task 7; `EnemyCast.was_kicked`, which already exists.
- Produces: each `interrupts.ability.*` finding gains one evidence line and matching facts.

**The claim, and its limit.** The log carries no interruptible flag — `interrupts.py` says so in
its own second line, and the verified field list for `dataType: Interrupts` in
`.claude/skills/wcl-api/SKILL.md` holds none. What the log proves is narrower and real: a spell
kicked at least once in this run was interruptible. A spell never kicked is unknown, and the card
must say unknown rather than imply a miss.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_spell_kicked_at_least_once_is_reported_interruptible() -> None:
    findings = analyse_interrupts(casts=(landed(BOLT), kicked(BOLT)), damage_taken=())
    row = one_with_id_prefix(findings, "interrupts.ability.")
    assert "interruptible: kicked 1 time this run" in row.evidence


def test_a_spell_never_kicked_is_reported_unknown_and_not_as_a_miss() -> None:
    """The log carries no interruptible flag. Silence is not a failure to kick."""
    findings = analyse_interrupts(casts=(landed(BOLT), landed(BOLT)), damage_taken=())
    row = one_with_id_prefix(findings, "interrupts.ability.")
    assert "never kicked this run; the log does not say whether it could be" in row.evidence
    assert not any("missed" in item for item in row.evidence)


def test_the_interruptible_claim_is_measured_not_derived() -> None:
    """It rests on interrupt events, not on a reconstruction."""
    findings = analyse_interrupts(casts=(landed(BOLT), kicked(BOLT)), damage_taken=())
    row = one_with_id_prefix(findings, "interrupts.ability.")
    fact = next(f for f in row.facts if f.label == "Interruptible")
    assert fact.confidence is Confidence.MEASURED
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_interrupts.py -k "interruptible or never_kicked" -v
```

Expected: FAIL on all three.

- [ ] **Step 3: Implement**

Inside `analyse_interrupts`, where the per-ability findings are built, count kicks for that
ability id across `casts` and add the evidence line plus the facts. Keep the finding's existing
`confidence` as it is — the ranking is still derived; only the new fact is measured, and it
carries its own tier.

- [ ] **Step 4: Run, mutate, confirm**

Change the never-kicked wording to claim a miss and
`test_a_spell_never_kicked_is_reported_unknown_and_not_as_a_miss` must fail. Change the tier to
`DERIVED` and the third test must fail. Restore both.

- [ ] **Step 5: Gate and commit**

```bash
git add src/wowperf/domain/analysis/interrupts.py tests/domain/analysis/test_interrupts.py
git commit -m "Say whether an enemy spell was ever interrupted at all" -m "A card said Forked Lightning landed eighteen times and never said whether anybody could have stopped it, so a reader supplied the missing half himself and supplied it wrongly. The log carries no interruptible flag and this invents none: a spell kicked once is provably interruptible, and a spell never kicked is reported unknown rather than as a miss." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# Phase D — tooltips on the ledger cards (design §6)

This phase is larger than the other three together. It is last so that a difficulty here cannot
hold back anything above it.

### Task 9: The run-scoped ability panel moves to where the panels live

**Design:** §6.2, final paragraph.

**Files:**
- Modify: `src/wowperf/domain/report/tooltip.py` — gains `run_ability_tooltip`
- Modify: `src/wowperf/domain/report/deaths.py` — `_ability_tooltip` deleted, import added
- Test: `tests/domain/report/test_tooltip.py`

**Interfaces:**
- Produces:

```python
def run_ability_tooltip(
    ability_id: int,
    ability_name: str,
    cooldown_seconds: float,
    owner_id: int,
    loaded: LoadedRun,
    auras: PlayerAuras | None,
    hits: tuple[DamageTakenEvent, ...],
    window: tuple[int, int],
    on_target: int | None = None,
) -> Tooltip | None
```

This is `deaths.py::_ability_tooltip` unchanged, under a public name, in the module that holds
every other tooltip builder. It is already generic over its window and its hits; a ledger card
differs from a death only in passing the whole run instead of a run-up.

**This is a refactor: behaviour does not change.** Tests exist and pass before it starts
(`tests/domain/report/test_build_deaths.py` covers the death path). Run them, move the function,
run them again.

- [ ] **Step 1: Confirm the existing tests pass before touching anything**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_deaths.py tests/domain/report/test_tooltip.py -v
```

- [ ] **Step 2: Move it**

Cut `_ability_tooltip` from `deaths.py` into `tooltip.py`, rename it `run_ability_tooltip`, keep
its docstring verbatim, and import it in `deaths.py`.

- [ ] **Step 3: Run the same tests and confirm they still pass**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/ -v
```

Expected: PASS, unchanged. If any assertion changed, the move was not a refactor — stop and find
out why.

- [ ] **Step 4: Gate and commit**

```bash
git add src/wowperf/domain/report/tooltip.py src/wowperf/domain/report/deaths.py
git commit -m "Move the run-scoped ability panel beside the other panel builders" -m "A ledger card differs from a death only in passing the whole run instead of a run-up, and this builder was already generic over its window. Moving it is what stops a second copy being written next to it." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: The panels are decided in one place

**Design:** §6.2.

**Files:**
- Create: `src/wowperf/domain/report/finding_tooltip.py`
- Test: `tests/domain/report/test_finding_tooltip.py`

**Interfaces:**
- Consumes: `run_ability_tooltip` (Task 9), `FindingFact` (Task 7).
- Produces:

```python
def tooltips_by_finding_id(
    findings: Sequence[Finding],
    loaded: LoadedRun,
    defensives: Defensives,
) -> dict[str, Tooltip]
```

Two rules, one per half of the table, and no third:

- A `defensives.ceiling.*` or `defensives.never.*` finding gets `run_ability_tooltip`, scoped to
  the whole run and to that finding's own player. Everything it needs — `loaded`, the per-actor
  aura tables, the defensives data file — is already in `build.py`'s hands.
- Any finding carrying `facts` gets a panel built from them, one `TooltipLine` per fact.
- A finding with neither gets nothing, and its heading stays a plain name.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_defensives_finding_gets_the_measured_ability_panel() -> None:
    tooltips = tooltips_by_finding_id((a_ceiling_finding(),), a_loaded_run(), a_defensives_file())
    lines = tooltips["defensives.ceiling.stonewake.48792"].lines
    assert [line.label for line in lines][:2] == ["Base cooldown", "Presses"]


def test_a_finding_with_facts_gets_a_panel_built_from_them() -> None:
    finding = a_finding(id="interrupts.ability.0", facts=(
        FindingFact(label="Interruptible", value="kicked 6 times this run"),
    ))
    lines = tooltips_by_finding_id((finding,), a_loaded_run(), a_defensives_file())[
        "interrupts.ability.0"
    ].lines
    assert [(line.label, line.value) for line in lines] == [
        ("Interruptible", "kicked 6 times this run")
    ]


def test_a_finding_with_no_ability_and_no_facts_gets_no_panel() -> None:
    """Twenty-one of one run's thirty-four findings name no ability. An empty
    panel is a hover target that rewards nothing."""
    finding = a_finding(id="time.residual", ability_id=None)
    assert tooltips_by_finding_id((finding,), a_loaded_run(), a_defensives_file()) == {}
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_finding_tooltip.py -v
```

Expected: FAIL — the module does not exist.

- [ ] **Step 3: Write the module**

Two ABOUTME lines at the top, per the repository's rule. Keep it to the two rules above; resist a
third branch for a family that has neither facts nor an ability.

- [ ] **Step 4: Run and confirm; Step 5: mutate**

Drop the `facts` branch and the second test must fail. Drop the defensives branch and the first
must fail.

- [ ] **Step 6: Gate and commit**

```bash
git add src/wowperf/domain/report/finding_tooltip.py tests/domain/report/test_finding_tooltip.py
git commit -m "Decide each finding's hover panel in one place" -m "Two rules and no third: a defensive is measured against the run's own aura table, and anything else brings its figures with it on the finding. Keeping the decision here is what lets ledger_row stay a formatter, which is the part of the overturned ruling that was right." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: The comparison findings carry their figures

**Design:** §6.2.

**Files:**
- Modify: `src/wowperf/domain/comparison/spells.py` — `compare.spells.rate.*` gains facts
- Modify: `src/wowperf/domain/comparison/uptime.py` — `compare.uptime.self.*` gains facts
- Test: `tests/domain/comparison/test_spells.py`, `tests/domain/comparison/test_uptime.py`

**Interfaces:**
- Consumes: `FindingFact` (Task 7).
- Produces: facts on both families. Labels, fixed: `"Ours"`, `"Reference median"`,
  `"Observed range"`, `"Sample"`.

**Every figure already exists at the point the finding is built.** The analyser formats them into
a title and into evidence strings there; the facts are the same numbers taken a third way, not a
new measurement. Nothing is recomputed and nothing is parsed.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_spell_rate_finding_carries_both_sides_as_facts() -> None:
    finding = one_rate_finding(ours=0.2, median=1.4, low=0.7, high=2.1, sample=5)
    assert [(f.label, f.value) for f in finding.facts] == [
        ("Ours", "0.2 casts a minute"),
        ("Reference median", "1.4 casts a minute"),
        ("Observed range", "0.7 to 2.1"),
        ("Sample", "5 top parses"),
    ]


def test_a_rate_fact_is_derived_because_a_rate_is_computed() -> None:
    finding = one_rate_finding(ours=0.2, median=1.4, low=0.7, high=2.1, sample=5)
    assert all(f.confidence is Confidence.DERIVED for f in finding.facts[:2])
```

Write the matching pair for uptime, whose values are percentages of boss-pull time.

- [ ] **Step 2: Run, watch fail, implement, run, mutate**

Change `("Observed range", ...)` to report a mean and the first test must fail — the project
reports a median and an observed range, never a mean.

- [ ] **Step 3: Gate and commit**

```bash
git add src/wowperf/domain/comparison/spells.py src/wowperf/domain/comparison/uptime.py tests/domain/comparison/test_spells.py tests/domain/comparison/test_uptime.py
git commit -m "Carry both sides of a comparison as labelled figures" -m "The numbers were already in the title and the evidence, as prose. A panel needs them as labels and values, and the analyser is where they exist unformatted." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: The ledger cards show their panels

**Design:** §6, §6.3.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` — `LedgerRow.tooltip: Tooltip | None = None`
- Modify: `src/wowperf/domain/report/ledger.py` — `ledger_row`, `place_rows`,
  `build_summary_pointers`, `build_observations`
- Modify: `src/wowperf/domain/report/players.py` — `build_players`
- Modify: `src/wowperf/domain/report/build.py` — build the map once, pass it down
- Modify: `src/wowperf/adapters/render/_macros.html.j2`
- Test: `tests/domain/report/test_build_ledger.py`, `tests/adapters/render/test_html.py`

**Interfaces:**
- Consumes: `tooltips_by_finding_id` (Task 10).
- Produces: `ledger_row(finding, titles_by_id, tooltips: Mapping[str, Tooltip] = {})`. The map is
  an optional trailing parameter, so every existing call keeps working while the four callers are
  updated one at a time.

`ledger_row` looks the panel up. It does not build one, does not take `LoadedRun`, and does not
take an aura table. That is deliberate: it is a formatter.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_ledger_row_carries_the_panel_its_finding_was_given() -> None:
    row = ledger_row(a_ceiling_finding(), {}, {"defensives.ceiling.stonewake.48792": A_PANEL})
    assert row.tooltip is A_PANEL


def test_a_ledger_row_with_no_panel_carries_none() -> None:
    assert ledger_row(a_ceiling_finding(), {}, {}).tooltip is None


def test_the_death_card_heading_still_carries_no_panel() -> None:
    """Its ground was never answered: the heading names the killing blow and
    the recap row beneath it already carries that hit's own figures."""
    html = render_a_report_with_a_death()
    heading = one_element(html, "div", class_="row-head")
    assert heading.find("span", class_="tip") is None
```

- [ ] **Step 2: Run them and watch them fail**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_ledger.py -k "carries_the_panel or with_no_panel" -v
```

- [ ] **Step 3: Thread the map**

Add the trailing parameter to `ledger_row` and to `place_rows`, `build_summary_pointers`,
`build_observations` and `build_players`. In `build.py`, call `tooltips_by_finding_id` once and
pass the result to each.

- [ ] **Step 4: Render it**

In `_macros.html.j2`, the one line that changes:

```jinja
    <h3>{{ row.title_before }}{% if row.title_ability %}{{ ability(row.ability_id, row.title_ability, row.tooltip) }}{% endif %}{{ row.title_after }}</h3>
```

`ability()` already takes the third argument and already adds `tabindex` only when a panel is
present.

- [ ] **Step 5: Run everything**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

- [ ] **Step 6: Mutate and confirm a test dies**

Drop the third argument from the `ability()` call and
`test_a_ledger_row_carries_the_panel_its_finding_was_given` still passes — it tests the view model
— but the render test must fail. If it does not, the render test is not testing the template, and
that is the defect this repository keeps producing. Fix the test before moving on.

- [ ] **Step 7: Gate and commit**

```bash
git add src/wowperf/domain/report/model.py src/wowperf/domain/report/ledger.py src/wowperf/domain/report/players.py src/wowperf/domain/report/build.py src/wowperf/adapters/render/_macros.html.j2 tests/domain/report/test_build_ledger.py tests/adapters/render/test_html.py
git commit -m "Put a finding's figures where the reader looks for them" -m "The 2026-09-11 design ruled these headings carry no panel, because the evidence list three lines below already prints the facts. A reader with that list on screen went looking for a tooltip anyway, which is what overturned it: a fact three lines from where a reader looks is a fact that was not delivered. The death card heading keeps the ruling, its ground unanswered." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: Read the finished page

**Design:** §8.

**Interfaces:** consumes everything above.

**This is the only task that reaches the network, and it is authorised once.** RwlRwlRwlRwl
authorised one `--all-players` run on 2026-09-12 for this reading. Spend it here and nowhere
else. A warm-cache run last measured 78.21 points of a 3600 hourly budget. Do not run `analyze`
or `fetch` to "check something" at any earlier point — Tasks 1 to 12 are served by `--no-compare`
against the existing cache, and by `cache/*.json` read directly.

- [ ] **Step 1: Confirm the gate is green first**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy
```

- [ ] **Step 2: Render the run**

```bash
export PATH="$HOME/.local/bin:$PATH" && uv run wowperf analyze G7MBJZfNakrcPvAx --fight 3 --all-players --out out
```

- [ ] **Step 3: Read it, against the seven points**

Serve `out/` with the `report` config in `.claude/launch.json` and check each:

1. The curve stays put while the death table scrolls, and a row hovered far down still lights its
   marker on it.
2. No offensive cast rows; `Whirlwind` at 2.1 s still there with its cover.
3. No healthstone on any card, and `consumables.never.*` still in the Summary.
4. The dots and the line still read as measured and derived.
5. One icon per row, none overlapping, none cut by a press mark.
6. Every ability-carrying ledger card has a panel; the death card heading has none.
7. Every interrupt card says kicked-and-therefore-interruptible or never-kicked-and-unknown.

- [ ] **Step 4: Report what the page actually shows**

Including anything that looks wrong. A finding here is worth more than any fixture: every plan in
this repository has had its worst defects survive the offline suite and appear on the first live
run.

---

## Self-review

**Spec coverage.** §4.1 → Task 1. §4.2 → Task 2. §4.3 → Task 3. §4.4 → no task, and none is
wanted: the design states the drawing does not change. §5.1 → Task 4. §5.2 → Task 5. §5.3 →
Task 6. §6.1 → Task 12's commit body and the amendment note already committed in `157b1f3`.
§6.2 → Tasks 7, 9, 10, 11, 12. §6.3 → Task 12, third test. §6.4 → **no task.**

**The gap, stated rather than hidden.** §6.4 promotes the player timeline's rows from a native
SVG `title` to the page's own `.tip` panel, and the design itself flags it as "the one piece of
this section with no precedent on the page … the task most likely to need a second attempt": a
panel is HTML, a row is SVG, and the panel would have to anchor against the chart rather than the
row. It is deliberately not planned here. The rows already carry their figures, so the page loses
nothing by waiting, and guessing at an approach in a plan is how a task becomes three. It gets
its own short design once Phase D has shown what the panels look like in place.

**Type consistency.** `FindingFact(label, value, confidence)` is defined in Task 7 and used with
those names in Tasks 8, 10 and 11. `run_ability_tooltip` is defined in Task 9 and used in Task 10.
`tooltips_by_finding_id` is defined in Task 10 and used in Task 12. `StateKey(label, css_class)`
is defined in Task 5 and used only there. `Press.icon_x` is removed in Task 4 and referenced
nowhere after.

**Placeholder scan.** No TBD, no "handle edge cases", no "similar to Task N". Task 6's step 3
names a helper by module rather than by signature, which is the one place an implementer will have
to read existing code to finish a line — `report/frame.py` is small and the neighbouring bars
already format a time.
