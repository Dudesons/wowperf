# The Per-Player Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every player their own sub-tab in the report's Players panel, carrying a multi-track timeline of their run drawn from data the tool already fetches.

**Architecture:** A new pure module `src/wowperf/domain/report/player_timeline.py` turns a `LoadedRun` and one player into a frozen `PlayerTimeline` of viewBox coordinates. `report/players.py` builds one per card; a new Jinja partial prints it. No new API query, no new analyser, and no change to the tab script — `show()` is already scoped by tab group and `reveal()` already walks the ancestor chain.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, Jinja2, pytest, ruff, mypy strict. `uv` only.

**Spec:** `docs/plans/2026-09-10-per-player-page-design.md`

## Global Constraints

Copied from the spec and from `CLAUDE.md`. Every task's requirements include these.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or anything touching the network, disk or a template.
- **The template decides nothing.** Every coordinate is computed in the domain and printed by the partial. No arithmetic, no branching on data values beyond presence.
- **The page loads nothing.** No stylesheet link, no `@import`, no remote `src`, exactly one inline script. `tests/adapters/render/test_html_invariants.py` enforces every clause.
- **No damage ranking** (postmortem design §5.5). The damage track scales to the player's own largest bucket, never the group's. No player's drawing carries another player's figures.
- **No rotation scoring** (postmortem design §2.6). The timeline says when something happened; it never says a press was wrong.
- **A cooldown row appears only for an ability the player cast at least once in the run.** The rule and its reasoning are at `src/wowperf/domain/analysis/defensives.py:50`.
- **Two lines of `# ABOUTME: ` at the top of every new file.**
- **Comments are evergreen.** No reference to what changed, when, or what it used to be.
- **Never use a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`.
- **Commits:** imperative mood, no `feat:`/`fix:` prefix, subject a sentence saying what the repository now does, body explaining **why**. Final line exactly `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Stage by name; never `git add -A`; never `--no-verify`, `--no-hooks` or `--no-pre-commit-hook`.
- **Git must be invoked as `/mingw64/bin/git`.** A user-level hook rewrites bare `git`.
- **The gate** is `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`. `mypy` takes its paths from `pyproject.toml`; pass none. Ruff line length is 100.
- **`tests/adapters/render/golden/minimal.html` changes in Tasks 1 and 6, and nowhere else.** Its fixture `minimal_loaded()` has one player, so both the sub-tab nav and the timeline SVG reach it. Read the diff line by line before regenerating it. In every other task the golden file must stay byte-identical.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/report/player_timeline.py` | **Create.** Builds one `PlayerTimeline` from a run and a player. Pure. |
| `src/wowperf/domain/report/model.py` | **Modify.** Add `DamageBar`, `DamageTrack`, `Press`, `Span`, `CooldownRow`, `PlayerTimeline`; add `slug` and `timeline` to `PlayerCard`. |
| `src/wowperf/domain/report/timeline.py` | **Modify.** Promote `_ticks` to `axis_ticks` and add `axis_scale`, so both drawings share one x formula. |
| `src/wowperf/domain/report/players.py` | **Modify.** Produce a slug per card and call `build_player_timeline`. |
| `src/wowperf/domain/report/build.py` | **Modify.** Accept `throughput` and pass it to `build_players`. |
| `src/wowperf/cli.py` | **Modify.** Hoist `load_throughput_cooldowns()` into a variable shared by `analyse` and `build_report`. |
| `pyproject.toml` | **Modify.** Add `ThroughputCooldowns` to ruff's `extend-immutable-calls`. |
| `src/wowperf/adapters/render/_players.html.j2` | **Modify.** Sub-tab nav and one panel per player. |
| `src/wowperf/adapters/render/_player_timeline.html.j2` | **Create.** The SVG, printing coordinates only. |
| `src/wowperf/adapters/render/report.css.j2` | **Modify.** Rules for bands, bars, presses, dimming, not-judged. |
| `tests/domain/report/test_build_player_timeline.py` | **Create.** Unit tests for every track function. |
| `tests/domain/report/test_build_players.py` | **Modify.** Slug and timeline on the card. |
| `tests/adapters/render/test_html_sections.py` | **Modify.** Sub-tab markup and the drawn SVG. |

---

### Task 1: Give the Players panel one sub-tab per player

Ships alone and is visible on its own: five sub-tabs carrying today's card content, no drawing yet.

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`PlayerCard`)
- Modify: `src/wowperf/domain/report/players.py`
- Modify: `src/wowperf/adapters/render/_players.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Test: `tests/domain/report/test_build_players.py`, `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: `display_names(run) -> dict[int, str]` from `wowperf.domain.analysis.players`.
- Produces: `PlayerCard.slug: str`; `player_slug(display_name: str) -> str` in `wowperf/domain/report/players.py`.

- [ ] **Step 1: Write the failing test for the slug**

Add to `tests/domain/report/test_build_players.py`:

```python
from wowperf.domain.report.players import player_slug


def test_a_slug_survives_a_name_html_and_a_url_fragment_cannot_carry() -> None:
    assert player_slug("Bríala") == "briala"
    assert player_slug("Кириллица") != ""
    assert " " not in player_slug("Emberkin the Second")


def test_two_players_who_differ_only_by_realm_get_different_slugs() -> None:
    assert player_slug("Emberkin-Ravencrest") != player_slug("Emberkin-Silvermoon")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py -q`
Expected: FAIL, `ImportError: cannot import name 'player_slug'`.

- [ ] **Step 3: Implement `player_slug`**

Add to `src/wowperf/domain/report/players.py`:

```python
import unicodedata

SLUG_FALLBACK = "player"
"""What a name reduces to when nothing in it survives the transliteration.

A wholly non-Latin name — `Кириллица` — keeps no ASCII letter after
decomposition, and an empty id is not addressable. The index the caller
appends is what keeps two such names apart.
"""


def player_slug(display_name: str) -> str:
    """A display name reduced to what an HTML id and a URL fragment both carry.

    Accents decompose and their marks are dropped, so `Bríala` and `Briala`
    reach the same slug — which is why the caller appends an index rather than
    trusting this to be unique. Everything else outside the ASCII alphabet and
    digits becomes a hyphen, and runs of hyphens collapse.
    """
    decomposed = unicodedata.normalize("NFKD", display_name)
    kept = [
        character.lower() if character.isascii() and character.isalnum() else "-"
        for character in decomposed
        if not unicodedata.combining(character)
    ]
    slug = "".join(kept).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or SLUG_FALLBACK
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing test for uniqueness on the card**

Add to `tests/domain/report/test_build_players.py`:

```python
def test_every_card_carries_a_slug_and_no_two_cards_share_one() -> None:
    run = a_run(
        players=(
            a_player(actor_id=1, name="Emberkin"),
            a_player(actor_id=2, name="Bríala"),
            a_player(actor_id=3, name="Briala"),
        ),
    )
    report = build_report(
        LoadedRun(run=run),
        [],
        None,
        None,
        a_player(actor_id=1, name="Emberkin"),
        None,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
    )
    slugs = [card.slug for card in report.players]
    assert all(slugs)
    assert len(set(slugs)) == len(slugs)
```

- [ ] **Step 6: Run it and watch it fail**

Expected: FAIL, `AttributeError: 'PlayerCard' object has no attribute 'slug'`.

- [ ] **Step 7: Add the field and populate it**

In `src/wowperf/domain/report/model.py`, add to `PlayerCard`:

```python
    slug: str = ""
    """This player's fragment id, unique within the report.

    Derived from the disambiguated display name and suffixed with the card's
    index, because two names can reduce to the same slug and a duplicate id
    would give one player another's sub-tab.
    """
```

In `src/wowperf/domain/report/players.py`, inside the `for` loop over `summarise_players`, track the index and pass it:

```python
    for index, summary in enumerate(
        summarise_players(loaded.run, loaded.casts, loaded.deaths, loaded.interrupts)
    ):
```

and in the `PlayerCard(...)` call add:

```python
                slug=f"{player_slug(display_name)}-{index}",
```

- [ ] **Step 8: Run the suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`
Expected: PASS.

- [ ] **Step 9: Write the failing render test**

Add to `tests/adapters/render/test_html_sections.py`. That file imports neither `re` nor
`rich_html`, so add both:

```python
import re

from tests.adapters.render.test_html_invariants import rich_html
```

```python
def test_each_player_gets_a_sub_tab_button_pointing_at_their_own_panel() -> None:
    html = rich_html()
    navs = re.findall(r'data-tab-group="players".*?</nav>', html, flags=re.S)
    assert navs, "the players panel has no sub-tab nav"
    targets = re.findall(r'data-tab-for="(player-[^"]+)"', navs[0])
    # rich_loaded() has two players. Asserting the count rather than truthiness is
    # what stops this passing against a nav that rendered one button, or none.
    assert len(targets) == 2
    for target in targets:
        assert f'id="{target}"' in html
    assert html.count('data-tab-panel="players"') == len(targets)
```

- [ ] **Step 10: Run it and watch it fail**

Expected: FAIL on `assert buttons`.

- [ ] **Step 11: Render the sub-tabs**

Replace the player loop in `src/wowperf/adapters/render/_players.html.j2` with:

```jinja
<nav class="tabs subtabs" data-tab-group="players" aria-label="Players">
{% for player in report.players %}
  <button type="button" class="tab" data-tab-for="player-{{ player.slug }}">{{ player.name }}</button>
{% endfor %}
</nav>
{% for player in report.players %}
<div class="card" data-tab-panel="players" id="player-{{ player.slug }}">
  <div class="player-head">
    <span class="swatch" style="background: var(--{{ player.colour }})"></span>
    <h3>{{ player.name }}</h3>
    <span class="sub">{{ player.class_name }} {{ player.spec }}</span>
  </div>
  <p class="stats">{{ player.stats_line }}</p>
  {% for row in player.damage_rows %}
  {{ ledger_row(row) }}
  {% endfor %}
  {% if player.spell_and_talent.state.value == "withheld" %}
  <p class="withheld">{{ player.spell_and_talent.reason }}</p>
  {% endif %}
  {% for row in player.spell_and_talent_rows %}
  {{ ledger_row(row) }}
  {% endfor %}
</div>
{% endfor %}
```

Add to `src/wowperf/adapters/render/report.css.j2`:

```css
.subtabs { margin: 8px 0 12px; }
.js .card[data-tab-panel]:not(.active) { display: none; }
```

- [ ] **Step 12: Run the suite and the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: the golden-file test FAILS, and should. `minimal_loaded()` has one player, so the panel gains a sub-tab nav and one wrapped card. Read the diff: it must show the nav, the wrapper `div` and its id, and nothing else — the card's own contents are unchanged by this task. Regenerate the golden and say in the commit body what moved.

- [ ] **Step 13: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/model.py src/wowperf/domain/report/players.py src/wowperf/adapters/render/_players.html.j2 src/wowperf/adapters/render/report.css.j2 tests/domain/report/test_build_players.py tests/adapters/render/test_html_sections.py
```

Commit subject: `Give each player their own sub-tab in the report`. Body: why a nested group needs no script change, and why the slug carries an index.

---

### Task 2: Carry the throughput cooldowns into the report builder

Nothing visible changes. It puts the data the drawing needs where the drawing can reach it, and closes a gap the existing comment at `src/wowperf/cli.py:552` already argues against.

**Files:**
- Modify: `src/wowperf/domain/report/build.py`
- Modify: `src/wowperf/domain/report/players.py`
- Modify: `src/wowperf/cli.py:554-563`, `src/wowperf/cli.py:646-658`
- Modify: `pyproject.toml`
- Test: `tests/domain/report/test_build_players.py`

**Interfaces:**
- Consumes: `ThroughputCooldowns` and `Defensives` from `wowperf.domain.season`.
- Produces: `build_report(..., throughput: ThroughputCooldowns = ThroughputCooldowns())` and `build_players(loaded, findings, parse, subject, titles_by_id, defensives, throughput)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/report/test_build_players.py`:

```python
from wowperf.domain.season import CooldownAbility, ThroughputCooldowns


def test_the_report_builder_accepts_the_throughput_cooldowns_the_analysers_read() -> None:
    throughput = ThroughputCooldowns(
        entries=(("DeathKnight/Blood", (CooldownAbility(
            ability_id=1, name="Dancing Rune Weapon", cooldown_seconds=120.0
        ),)),)
    )
    report = build_report(
        a_loaded(),
        [],
        None,
        None,
        a_player(),
        None,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        throughput=throughput,
    )
    assert report.players == ()
```

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL, `TypeError: build_report() got an unexpected keyword argument 'throughput'`.

- [ ] **Step 3: Thread the parameter through**

In `src/wowperf/domain/report/build.py`, import `ThroughputCooldowns` from `wowperf.domain.season` and add to `build_report`'s signature, after `self_resurrections`:

```python
    throughput: ThroughputCooldowns = ThroughputCooldowns(),
```

and change the `build_players` call to:

```python
    players = build_players(
        loaded, findings, parse, subject, titles_by_id, defensives, throughput
    )
```

In `src/wowperf/domain/report/players.py`, add the two parameters to `build_players` after `titles_by_id`:

```python
    defensives: Defensives,
    throughput: ThroughputCooldowns,
```

importing both from `wowperf.domain.season`. They are unused in this task; the next task reads them.

- [ ] **Step 4: Add the ruff exemption**

`ThroughputCooldowns()` as a parameter default trips bugbear's B008, the same way `Externals()` and `Roles()` already do. In `pyproject.toml`, add to `[tool.ruff.lint.flake8-bugbear].extend-immutable-calls`:

```toml
    "wowperf.domain.season.ThroughputCooldowns",
```

- [ ] **Step 5: Run the test and the linter**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_players.py -q && uv run ruff check .`
Expected: both pass.

- [ ] **Step 6: Hoist the loader in the CLI**

In `src/wowperf/cli.py`, the block at 554 loads `defensives` and `consumables` into variables under a comment saying the analysers and the death cards must read the same cooldowns. `load_throughput_cooldowns()` is passed inline to `analyse` and so is loaded twice once the report needs it. Change:

```python
        defensives = load_defensives()
        consumables = load_consumables()
        throughput = load_throughput_cooldowns()
        findings = analyse(
            loaded,
            load_season_data(),
            defensives,
            consumables,
            throughput,
            roles=load_roles(),
            include_cooldown_ceiling=throughput_ceiling,
        )
```

and in the `build_report(...)` call, add after `self_resurrections=load_self_resurrections(),`:

```python
                    throughput=throughput,
```

- [ ] **Step 7: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/build.py src/wowperf/domain/report/players.py src/wowperf/cli.py pyproject.toml tests/domain/report/test_build_players.py
```

Commit subject: `Let the report read the same cooldowns the analysers do`. Body: the file was already loaded once for the analysers and inline a second time; the page and the findings must not disagree about a cooldown's length.

---

### Task 3: Share one x formula, and draw the frame

The timeline's frame: width, height, axis ticks, shaded pull bands, and a withheld section when there is nothing to draw.

**Files:**
- Create: `src/wowperf/domain/report/player_timeline.py`
- Modify: `src/wowperf/domain/report/model.py`
- Modify: `src/wowperf/domain/report/timeline.py`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: `run_start_ms(run)`, `run_seconds(run)`, `format_seconds(float | None)` from `wowperf.domain.report.frame`; `TIMELINE_WIDTH`, `TRACK_X0`, `TRACK_X1`, `MIN_BLOCK_WIDTH`, `TICK_SECONDS` from `wowperf.domain.report.timeline`; `TimelineBlock`, `Section`, `SectionState` from `wowperf.domain.report.model`.
- Produces: `axis_scale(seconds: float) -> float` and `axis_ticks(longest: float, scale: float) -> tuple[tuple[float, str], ...]` in `report/timeline.py`; `PlayerTimeline`, `DamageTrack`, `DamageBar`, `Press`, `Span`, `CooldownRow` in `report/model.py`; `build_player_timeline(loaded, actor_id, class_name, spec, defensives, throughput) -> PlayerTimeline` in `report/player_timeline.py`.

- [ ] **Step 1: Write the failing test for the shared x formula**

Create `tests/domain/report/test_build_player_timeline.py`:

```python
# ABOUTME: Behaviour tests for one player's timeline: bands, bars, rows, and what is not judged.
# ABOUTME: Every coordinate is asserted here, because the template computes none of them.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.report.timeline import TRACK_X0, TRACK_X1, axis_scale, axis_ticks


def test_the_axis_scale_fills_the_track_width() -> None:
    scale = axis_scale(100.0)
    assert TRACK_X0 + 100.0 * scale == TRACK_X1


def test_a_run_of_no_length_scales_to_zero_rather_than_dividing_by_it() -> None:
    assert axis_scale(0.0) == 0.0


def test_the_first_tick_sits_at_the_axis_origin() -> None:
    ticks = axis_ticks(1200.0, axis_scale(1200.0))
    assert ticks[0][0] == TRACK_X0
    assert ticks[0][1] == "0:00"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_player_timeline.py -q`
Expected: FAIL, `ImportError: cannot import name 'axis_scale'`.

- [ ] **Step 3: Promote the two helpers in `timeline.py`**

In `src/wowperf/domain/report/timeline.py`, rename `_ticks` to `axis_ticks` and add `axis_scale` above it:

```python
def axis_scale(seconds: float) -> float:
    """viewBox units per second for a drawing that fills the track width.

    A span of no length scales to zero rather than dividing by it: a run with
    one instantaneous pull is degenerate, not an error, and every coordinate
    derived from a zero scale collapses onto the axis origin where a reader can
    see there is nothing to read.
    """
    return (TRACK_X1 - TRACK_X0) / seconds if seconds > 0 else 0.0


def axis_ticks(longest: float, scale: float) -> tuple[tuple[float, str], ...]:
    """One labelled mark every `TICK_SECONDS`, from the origin to `longest`."""
    marks = []
    second = 0
    while second <= longest:
        label = format_seconds(float(second))
        assert label is not None  # a float input always formats to a string
        marks.append((TRACK_X0 + second * scale, label))
        second += TICK_SECONDS
    return tuple(marks)
```

Replace the body of `build_timeline` that computes `scale` with `scale = axis_scale(longest)`, and its `_ticks(longest, scale)` call with `axis_ticks(longest, scale)`.

- [ ] **Step 4: Run the tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report -q`
Expected: PASS, including every existing `test_build_timeline.py` test.

- [ ] **Step 5: Write the failing test for the frame**

Add to `tests/domain/report/test_build_player_timeline.py`:

```python
from wowperf.domain.model import LoadedRun
from wowperf.domain.report.model import SectionState
from wowperf.domain.report.player_timeline import (
    FIRST_ROW_Y,
    ROW_HEIGHT,
    build_player_timeline,
)
from wowperf.domain.season import Defensives, ThroughputCooldowns

NO_DEFENSIVES = Defensives(entries=())
NO_THROUGHPUT = ThroughputCooldowns(entries=())


def a_timeline(loaded: LoadedRun, **kwargs: object):
    return build_player_timeline(
        loaded,
        actor_id=int(kwargs.get("actor_id", 1)),
        class_name=str(kwargs.get("class_name", "DeathKnight")),
        spec=str(kwargs.get("spec", "Blood")),
        defensives=kwargs.get("defensives", NO_DEFENSIVES),  # type: ignore[arg-type]
        throughput=kwargs.get("throughput", NO_THROUGHPUT),  # type: ignore[arg-type]
    )


def test_a_player_with_nothing_to_draw_gets_a_withheld_section_and_no_bands() -> None:
    timeline = a_timeline(LoadedRun(run=a_run(pulls=())))
    assert timeline.section.state is SectionState.WITHHELD
    assert timeline.section.reason
    assert timeline.pulls == ()


def test_a_pull_band_starts_where_the_axis_starts_and_a_boss_is_marked() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000, encounter_id=2599)))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.pulls[0].x == TRACK_X0
    assert timeline.pulls[1].is_boss
    assert "block-boss" in timeline.pulls[1].css_class


def test_the_height_grows_with_the_rows_it_has_to_hold() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = a_timeline(LoadedRun(run=run))
    assert timeline.height == FIRST_ROW_Y + len(timeline.cooldowns) * ROW_HEIGHT + 28.0
```

- [ ] **Step 6: Run it and watch it fail**

Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.report.player_timeline'`.

- [ ] **Step 7: Add the view-model types**

In `src/wowperf/domain/report/model.py`, after `Timeline`:

```python
class DamageBar(Frozen):
    """One bucket of damage taken, in viewBox units."""

    x: float
    width: float
    y: float
    height: float


class DamageTrack(Frozen):
    """Damage taken over the run, bucketed and scaled to this player's own peak.

    Never to the group's. A shared scale across five players would rank them,
    which the postmortem design's §5.5 refuses.
    """

    baseline_y: float = 0.0
    bars: tuple[DamageBar, ...] = ()
    peak_label: str = ""


class Press(Frozen):
    """One cast of a tracked cooldown. `icon_class` is empty when none resolved."""

    x: float
    icon_class: str = ""


class Span(Frozen):
    """A stretch of a cooldown row, in viewBox units."""

    x: float
    width: float


class CooldownRow(Frozen):
    """One ability this player owns, and what the run did with it.

    `not_judged` covers the run's opening, where the log cannot say whether the
    ability was available: casts are fetched per fight, so a press before the
    timer started is invisible.
    """

    label: str
    ability_id: int | None = None
    baseline_y: float = 0.0
    presses: tuple[Press, ...] = ()
    unavailable: tuple[Span, ...] = ()
    not_judged: Span | None = None


class PlayerTimeline(Frozen):
    """One player's run on one axis. Every coordinate the SVG needs lives here."""

    section: Section
    width: float = 0.0
    height: float = 0.0
    pulls: tuple[TimelineBlock, ...] = ()
    band_y: float = 0.0
    band_height: float = 0.0
    damage: DamageTrack | None = None
    cooldowns: tuple[CooldownRow, ...] = ()
    ticks: tuple[tuple[float, str], ...] = ()
    tick_y1: float = 0.0
    tick_y2: float = 0.0
    tick_label_y: float = 0.0
    label_x: float = 0.0
    row_height: float = 0.0
    legend: str = ""
    badges: tuple[Badge, ...] = ()
```

- [ ] **Step 8: Create the module with its frame**

Create `src/wowperf/domain/report/player_timeline.py`:

```python
# ABOUTME: One player's run on a single axis, in viewBox units the template only prints.
# ABOUTME: Pull bands behind, damage taken above, one row per cooldown the player owns.

from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.frame import badge_for, run_seconds, run_start_ms
from wowperf.domain.report.model import (
    CooldownRow,
    DamageTrack,
    PlayerTimeline,
    Section,
    SectionState,
    TimelineBlock,
)
from wowperf.domain.report.timeline import (
    MIN_BLOCK_WIDTH,
    TIMELINE_WIDTH,
    TRACK_X0,
    axis_scale,
    axis_ticks,
)
from wowperf.domain.season import Defensives, ThroughputCooldowns

PRECISION = 1
"""Coordinates are rounded to a tenth of a viewBox unit.

A run's worth of damage buckets and cooldown presses is hundreds of numbers per
player. Unrounded binary fractions would fill the page, and its golden file,
with digits no reader and no reviewer can use.
"""

AXIS_TOP = 22.0
"""Where the tick lines start, above the pull band."""

BAND_Y = 28.0
"""The pull band's top edge: a thin strip the rest of the drawing hangs under."""

BAND_HEIGHT = 10.0

DAMAGE_BASELINE_Y = 76.0
"""The foot of the damage bars. They grow upward from here."""

DAMAGE_HEIGHT = 32.0
"""How tall the largest bucket is drawn. Every other bar is a fraction of it."""

FIRST_ROW_Y = 96.0
"""The baseline of the first cooldown row."""

ROW_HEIGHT = 16.0

BOTTOM_MARGIN = 28.0
"""Gap between the last row and the viewBox's bottom edge, holding the tick labels."""

TICK_LABEL_MARGIN = 12.0

LABEL_X = 40.0
"""Where a row's ability name ends, right-aligned into the margin left of the axis."""

NOTHING_TO_DRAW = (
    "This player cast none of the cooldowns tracked for their specialisation, and the run "
    "recorded no pulls to place them against, so there is no timeline to draw."
)

LEGEND = (
    "A mark is a cast the log recorded. The stretch after it is the ability's cooldown, "
    "computed from its base length: talents shorten cooldowns and the log records no reset, "
    "so this shows an ability as unavailable at least as often as it truly was. The pale "
    "stretch at the start is not judged at all — a press before the timer began is invisible "
    "to a log fetched per fight."
)


def _pull_bands(run: Run, scale: float, origin_ms: int) -> tuple[TimelineBlock, ...]:
    """Every pull as a band behind the tracks, boss pulls outlined."""
    return tuple(
        TimelineBlock(
            label=pull.name,
            x=round(TRACK_X0 + (pull.start_ms - origin_ms) / 1000 * scale, PRECISION),
            width=round(max(pull.duration_seconds * scale, MIN_BLOCK_WIDTH), PRECISION),
            is_boss=pull.is_boss,
            kind="band",
            css_class="pull-band block-boss" if pull.is_boss else "pull-band",
        )
        for pull in run.pulls
    )


def build_player_timeline(
    loaded: LoadedRun,
    actor_id: int,
    class_name: str,
    spec: str,
    defensives: Defensives,
    throughput: ThroughputCooldowns,
) -> PlayerTimeline:
    """One player's run, drawn on the span from the first pull's start to the last pull's end.

    Not the run timeline's scale: that one fits the longer of our run and its
    reference into the width, so a pull sits at a different x there whenever a
    reference ran longer. Every player timeline in one report shares this scale
    instead, which is what lets five of them be read against each other.
    """
    run = loaded.run
    span = run_seconds(run)
    rows: tuple[CooldownRow, ...] = ()

    if span <= 0:
        return PlayerTimeline(
            section=Section(state=SectionState.WITHHELD, reason=NOTHING_TO_DRAW),
            width=TIMELINE_WIDTH,
        )

    scale = axis_scale(span)
    origin = run_start_ms(run)
    height = FIRST_ROW_Y + len(rows) * ROW_HEIGHT + BOTTOM_MARGIN

    return PlayerTimeline(
        section=Section(state=SectionState.PRESENT),
        width=TIMELINE_WIDTH,
        height=height,
        pulls=_pull_bands(run, scale, origin),
        band_y=BAND_Y,
        band_height=BAND_HEIGHT,
        damage=None,
        cooldowns=rows,
        ticks=axis_ticks(span, scale),
        tick_y1=AXIS_TOP,
        tick_y2=height - BOTTOM_MARGIN,
        tick_label_y=height - TICK_LABEL_MARGIN,
        label_x=LABEL_X,
        row_height=ROW_HEIGHT,
        legend=LEGEND,
        badges=(badge_for(Confidence.MEASURED), badge_for(Confidence.INFERRED)),
    )
```

- [ ] **Step 9: Run the tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_player_timeline.py -q`
Expected: PASS.

- [ ] **Step 10: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`

```bash
/mingw64/bin/git add src/wowperf/domain/report/player_timeline.py src/wowperf/domain/report/model.py src/wowperf/domain/report/timeline.py tests/domain/report/test_build_player_timeline.py
```

Commit subject: `Draw the frame a player's own run timeline hangs on`. Body: why the player timeline does not share the run timeline's scale, and why one x formula is now shared by both.

---

### Task 4: The damage-taken track

**Files:**
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: `DamageTakenEvent` from `wowperf.domain.events` — fields `actor_id`, `amount`, `timestamp_ms`.
- Produces: `BUCKET_SECONDS: float` and `_damage_track(...) -> DamageTrack | None` in `report/player_timeline.py`; `PlayerTimeline.damage` populated.

- [ ] **Step 1: Write the failing tests**

Add to `tests/domain/report/test_build_player_timeline.py`:

```python
from wowperf.domain.events import DamageTakenEvent


def a_hit(actor_id: int, at_ms: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=9, ability_name="Cleave", amount=amount, timestamp_ms=at_ms
    )


def test_the_tallest_bar_fills_the_damage_track_and_a_half_sized_hit_is_half_of_it() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(
        run=run, damage_taken=(a_hit(1, 1_000, 1000), a_hit(1, 50_000, 500))
    )
    track = a_timeline(loaded).damage
    assert track is not None
    tallest = max(bar.height for bar in track.bars)
    shortest = min(bar.height for bar in track.bars)
    assert tallest == DAMAGE_HEIGHT
    assert shortest == DAMAGE_HEIGHT / 2


def test_another_players_damage_never_reaches_this_players_track() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(2, 1_000, 9999),))
    assert a_timeline(loaded, actor_id=1).damage is None


def test_two_hits_inside_one_bucket_are_one_bar_of_their_sum() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    both = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 400), a_hit(1, 2_000, 600)))
    one = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 1000),))
    assert len(a_timeline(both).damage.bars) == 1  # type: ignore[union-attr]
    assert a_timeline(both).damage == a_timeline(one).damage


def test_a_bucket_with_no_damage_draws_no_bar() -> None:
    run = a_run(pulls=(a_pull(0, 0, 100_000),))
    loaded = LoadedRun(run=run, damage_taken=(a_hit(1, 1_000, 100),))
    assert len(a_timeline(loaded).damage.bars) == 1  # type: ignore[union-attr]
```

Add `DAMAGE_HEIGHT` to the module's import list at the top of the test file.

- [ ] **Step 2: Run and watch them fail**

Expected: FAIL — `track is not None` fails, because Task 3 returns `damage=None`.

- [ ] **Step 3: Implement the track**

Add to `src/wowperf/domain/report/player_timeline.py`:

```python
BUCKET_SECONDS = 5.0
"""How much of the run one damage bar covers.

Narrow enough that a single lethal spike stays one bar rather than being
averaged into its neighbours, wide enough that a thirty-minute run does not
emit hundreds of rectangles into a file that has to stay openable. Confirmed
against a real run rather than assumed; see the plan's final task.
"""
```

and, above `build_player_timeline`:

```python
def _damage_track(
    events: tuple[DamageTakenEvent, ...], actor_id: int, scale: float, origin_ms: int
) -> DamageTrack | None:
    """Damage this player took, bucketed, scaled to their own largest bucket.

    `amount` is the unmitigated figure — what the hit was worth before armour
    and absorbs — which is the same number the per-ability comparison reads, so
    the drawing and the findings cannot disagree about how hard something hit.

    Returns `None` when this player took nothing the log recorded: an empty
    track drawn at full height would read as a run of zero-damage buckets
    rather than as an absence.
    """
    ours = [event for event in events if event.actor_id == actor_id]
    if not ours:
        return None

    buckets: dict[int, int] = defaultdict(int)
    for event in ours:
        index = int((event.timestamp_ms - origin_ms) / 1000 // BUCKET_SECONDS)
        buckets[index] += event.amount

    peak = max(buckets.values())
    width = round(BUCKET_SECONDS * scale, PRECISION)
    bars = tuple(
        DamageBar(
            x=round(TRACK_X0 + index * BUCKET_SECONDS * scale, PRECISION),
            width=max(width, MIN_BLOCK_WIDTH),
            y=round(DAMAGE_BASELINE_Y - DAMAGE_HEIGHT * amount / peak, PRECISION),
            height=round(DAMAGE_HEIGHT * amount / peak, PRECISION),
        )
        for index, amount in sorted(buckets.items())
    )
    return DamageTrack(
        baseline_y=DAMAGE_BASELINE_Y,
        bars=bars,
        peak_label=f"Tallest bar: {peak:,} damage in {int(BUCKET_SECONDS)} seconds",
    )
```

Add `from collections import defaultdict`, `from wowperf.domain.events import DamageTakenEvent`, and `DamageBar` to the model import. In `build_player_timeline`, replace `damage=None,` with:

```python
        damage=_damage_track(loaded.damage_taken, actor_id, scale, origin),
```

- [ ] **Step 4: Run the tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_player_timeline.py -q`
Expected: PASS.

- [ ] **Step 5: Run the gate and commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/player_timeline.py tests/domain/report/test_build_player_timeline.py
```

Commit subject: `Draw the damage a player took across their own run`. Body: why the track scales to the player's own peak and never the group's, and why no damage means no track rather than a flat one.

---

### Task 5: The cooldown rows, and the stretch that is not judged

The task that carries the design's honesty rule. Read `src/wowperf/domain/analysis/defensives.py:50` and `src/wowperf/domain/analysis/throughput.py:26` before writing a line.

**Files:**
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Test: `tests/domain/report/test_build_player_timeline.py`

**Interfaces:**
- Consumes: `CastEvent` (`actor_id`, `ability_id`, `timestamp_ms`); `Defensives.for_spec(class_name, spec) -> tuple[DefensiveAbility, ...]`; `ThroughputCooldowns.for_spec(...) -> tuple[CooldownAbility, ...]`; `CooldownAbility` fields `ability_id`, `name`, `cooldown_seconds`.
- Produces: `_cooldown_rows(...) -> tuple[CooldownRow, ...]`; `PlayerTimeline.cooldowns` populated.

- [ ] **Step 1: Write the failing tests**

Add to `tests/domain/report/test_build_player_timeline.py`:

```python
from wowperf.domain.events import CastEvent
from wowperf.domain.season import CooldownAbility, DefensiveAbility


def a_cast(actor_id: int, ability_id: int, at_ms: int) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability_id, ability_name="Shield", timestamp_ms=at_ms
    )


SHIELD = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0)
BURST = CooldownAbility(ability_id=49028, name="Dancing Rune Weapon", cooldown_seconds=120.0)
KIT = Defensives(entries=(("DeathKnight/Blood", (SHIELD,)),))
BURSTS = ThroughputCooldowns(entries=(("DeathKnight/Blood", (BURST,)),))


def test_an_ability_the_player_never_cast_gets_no_row_at_all() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=())
    assert a_timeline(loaded, defensives=KIT).cooldowns == ()


def test_an_ability_the_player_cast_once_gets_a_row_with_one_press() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    rows = a_timeline(loaded, defensives=KIT).cooldowns
    assert len(rows) == 1
    assert rows[0].label == "Icebound Fortitude"
    assert rows[0].ability_id == SHIELD.ability_id
    assert len(rows[0].presses) == 1


def test_another_players_cast_never_gives_this_player_a_row() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(2, SHIELD.ability_id, 300_000),))
    assert a_timeline(loaded, actor_id=1, defensives=KIT).cooldowns == ()


def test_a_press_dims_the_row_for_the_abilitys_own_cooldown() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    scale = axis_scale(600.0)
    span = next(s for s in row.unavailable if s.x == round(TRACK_X0 + 300.0 * scale, 1))
    assert span.width == round(180.0 * scale, 1)


def test_the_runs_opening_is_not_judged_for_as_long_as_the_cooldown_lasts() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    row = a_timeline(loaded, defensives=KIT).cooldowns[0]
    assert row.not_judged is not None
    assert row.not_judged.x == TRACK_X0
    assert row.not_judged.width == round(180.0 * axis_scale(600.0), 1)


def test_throughput_rows_come_before_defensive_rows() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, BURST.ability_id, 400_000)),
    )
    rows = a_timeline(loaded, defensives=KIT, throughput=BURSTS).cooldowns
    assert [row.label for row in rows] == ["Dancing Rune Weapon", "Icebound Fortitude"]


def test_each_row_sits_one_row_height_below_the_last() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(
        run=run,
        casts=(a_cast(1, SHIELD.ability_id, 300_000), a_cast(1, BURST.ability_id, 400_000)),
    )
    rows = a_timeline(loaded, defensives=KIT, throughput=BURSTS).cooldowns
    assert rows[1].baseline_y - rows[0].baseline_y == ROW_HEIGHT
```

- [ ] **Step 2: Run and watch them fail**

Expected: FAIL — `cooldowns` is `()` for every case, so the tests that expect a row fail while `test_an_ability_the_player_never_cast_gets_no_row_at_all` passes vacuously. That vacuous pass is expected at this step and is why the other tests exist.

- [ ] **Step 3: Implement the rows**

Add to `src/wowperf/domain/report/player_timeline.py`:

```python
def _cooldown_rows(
    casts: tuple[CastEvent, ...],
    abilities: tuple[CooldownAbility, ...],
    actor_id: int,
    scale: float,
    origin_ms: int,
    span_seconds: float,
) -> tuple[CooldownRow, ...]:
    """One row per ability in `abilities` this player cast at least once.

    Ownership is the whole rule. The data files list what a specialisation can
    take, not what this player took, and `analysis/defensives.py` already
    refuses to read silence as availability because "reporting silence as
    availability would accuse someone of not pressing a button they do not
    own". Drawn, that accusation is worse than written: an empty row across a
    whole run reads as a run of missed presses.

    The row's opening is marked not-judged for the ability's own cooldown, for
    the reason `analysis/throughput.py:ready_at` refuses to judge a window
    reaching back past the run's start — casts are fetched per fight, so a
    press before the timer began leaves no record, and calling that stretch
    ready would guess in the one direction this project never guesses in.
    """
    ours = [cast for cast in casts if cast.actor_id == actor_id]
    owned = {cast.ability_id for cast in ours}

    rows = []
    for ability in abilities:
        if ability.ability_id not in owned:
            continue
        presses = sorted(
            cast.timestamp_ms for cast in ours if cast.ability_id == ability.ability_id
        )
        width = round(min(ability.cooldown_seconds, span_seconds) * scale, PRECISION)
        rows.append(
            CooldownRow(
                label=ability.name,
                ability_id=ability.ability_id,
                baseline_y=FIRST_ROW_Y + len(rows) * ROW_HEIGHT,
                presses=tuple(
                    Press(x=round(TRACK_X0 + (at - origin_ms) / 1000 * scale, PRECISION))
                    for at in presses
                ),
                unavailable=tuple(
                    Span(
                        x=round(TRACK_X0 + (at - origin_ms) / 1000 * scale, PRECISION),
                        width=width,
                    )
                    for at in presses
                ),
                not_judged=Span(x=TRACK_X0, width=width),
            )
        )
    return tuple(rows)
```

Add `CastEvent` to the events import, `CooldownRow`, `Press` and `Span` to the model import, and `CooldownAbility` to the season import.

In `build_player_timeline`, replace `rows: tuple[CooldownRow, ...] = ()` and its use with a computation placed after `scale` and `origin` are known:

```python
    rows = _cooldown_rows(
        loaded.casts,
        throughput.for_spec(class_name, spec) + defensives.for_spec(class_name, spec),
        actor_id,
        scale,
        origin,
        span,
    )
    height = FIRST_ROW_Y + len(rows) * ROW_HEIGHT + BOTTOM_MARGIN
```

- [ ] **Step 4: Run the tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_player_timeline.py -q`
Expected: PASS.

- [ ] **Step 5: Prove the ownership test can fail**

Temporarily delete the two lines

```python
        if ability.ability_id not in owned:
            continue
```

and run the suite. `test_an_ability_the_player_never_cast_gets_no_row_at_all` MUST fail. If it still passes, the test is not holding the rule and must be rewritten before the guard is restored. Restore the guard and re-run.

- [ ] **Step 6: Run the gate and commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/player_timeline.py tests/domain/report/test_build_player_timeline.py
```

Commit subject: `Give a player a cooldown row only for a button they own`. Body: why silence is not availability, and why the run's opening is drawn as unjudged rather than as ready.

---

### Task 6: Render the timeline

**Files:**
- Create: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Modify: `src/wowperf/adapters/render/_players.html.j2`
- Modify: `src/wowperf/adapters/render/report.css.j2`
- Modify: `src/wowperf/domain/report/model.py` (`PlayerCard.timeline`)
- Modify: `src/wowperf/domain/report/players.py`
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: `build_player_timeline(loaded, actor_id, class_name, spec, defensives, throughput)`.
- Produces: `PlayerCard.timeline: PlayerTimeline | None`.

- [ ] **Step 1: Write the failing render test**

Add to `tests/adapters/render/test_html_sections.py`. These build a card directly rather than
reaching for `rich_html()`: that fixture passes `NO_DEFENSIVES` and no throughput, so it has no
cooldown row to find, and a test written against it would assert only what happens to be there.

```python
def a_player_card(**overrides: object) -> PlayerCard:
    fields: dict[str, object] = {
        "name": "Emberkin",
        "class_name": "Mage",
        "spec": "Arcane",
        "colour": "class-mage",
        "stats_line": "180 casts in 4:20 of pulls \u00b7 1 death \u00b7 2 interrupts",
        "slug": "emberkin-0",
        "spell_and_talent": Section(state=SectionState.PRESENT),
    }
    fields.update(overrides)
    return PlayerCard(**fields)  # type: ignore[arg-type]


def a_drawn_timeline() -> PlayerTimeline:
    """A timeline with one of everything, so a template that drops a layer fails here."""
    return PlayerTimeline(
        section=Section(state=SectionState.PRESENT),
        width=680.0,
        height=140.0,
        pulls=(TimelineBlock(label="Pack 0", x=46.0, width=100.0, is_boss=False,
                             kind="band", css_class="pull-band"),),
        band_y=28.0,
        band_height=10.0,
        damage=DamageTrack(
            baseline_y=76.0,
            bars=(DamageBar(x=46.0, width=6.0, y=44.0, height=32.0),),
            peak_label="Tallest bar: 120,000 damage in 5 seconds",
        ),
        cooldowns=(CooldownRow(label="Ice Block", ability_id=45438, baseline_y=96.0,
                               presses=(Press(x=200.0, icon_class="i-45438"),),
                               unavailable=(Span(x=200.0, width=90.0),),
                               not_judged=Span(x=46.0, width=90.0)),),
        ticks=((46.0, "0:00"),),
        tick_y1=22.0,
        tick_y2=112.0,
        tick_label_y=128.0,
        label_x=40.0,
        row_height=16.0,
        legend="The pale stretch at the start is not judged at all.",
        badges=(Badge(label="measured", tint="badge-measured"),),
    )


def test_every_layer_of_a_players_timeline_reaches_the_page() -> None:
    html = render(a_report(players=(a_player_card(timeline=a_drawn_timeline()),)))
    assert 'data-tab-panel="players"' in html
    assert 'class="player-timeline"' in html
    for layer in ("pull-band", "damage-bar", "not-judged", "on-cooldown", "press"):
        assert layer in html, layer
    assert "Ice Block" in html
    assert "not judged" in html


def test_a_withheld_timeline_says_why_instead_of_drawing_an_empty_axis() -> None:
    withheld = PlayerTimeline(
        section=Section(state=SectionState.WITHHELD, reason="no pulls to place anything against"),
    )
    html = render(a_report(players=(a_player_card(timeline=withheld),)))
    assert "no pulls to place anything against" in html
    assert 'class="player-timeline"' not in html
```

Add `CooldownRow`, `DamageBar`, `DamageTrack`, `PlayerCard`, `PlayerTimeline`, `Press`, `Span` and
`TimelineBlock` to the existing `wowperf.domain.report.model` import at the top of the file.

- [ ] **Step 2: Run and watch them fail**

Expected: FAIL, `TypeError: PlayerCard() got an unexpected keyword argument 'timeline'`.

- [ ] **Step 3: Put the timeline on the card**

In `src/wowperf/domain/report/model.py`, add to `PlayerCard`:

```python
    timeline: PlayerTimeline | None = None
    """This player's own run, drawn. `None` when the run had no span to draw on."""
```

`PlayerTimeline` is defined above `PlayerCard` in the same module, so no import is needed. If it is not, move its definition above `PlayerCard` rather than using a forward reference.

In `src/wowperf/domain/report/players.py`, import `build_player_timeline` and add to the `PlayerCard(...)` call:

```python
                timeline=build_player_timeline(
                    loaded, summary.actor_id, summary.class_name, summary.spec,
                    defensives, throughput,
                ),
```

- [ ] **Step 4: Create the partial**

Create `src/wowperf/adapters/render/_player_timeline.html.j2`:

```jinja
{# ABOUTME: One player's run as an SVG: pull bands, damage bars, and a row per cooldown. #}
{# ABOUTME: Prints coordinates computed in the domain; no arithmetic happens here. #}
{% macro player_timeline(timeline) %}
{% if timeline and timeline.section.state.value == "withheld" %}
<p class="withheld">{{ timeline.section.reason }}</p>
{% elif timeline %}
<svg class="player-timeline" viewBox="0 0 {{ timeline.width }} {{ timeline.height }}" role="img">
  {% for x, label in timeline.ticks %}
  <line class="tick" x1="{{ x }}" y1="{{ timeline.tick_y1 }}" x2="{{ x }}" y2="{{ timeline.tick_y2 }}"/>
  <text class="tick-label" x="{{ x }}" y="{{ timeline.tick_label_y }}">{{ label }}</text>
  {% endfor %}
  {% for band in timeline.pulls %}
  <rect class="{{ band.css_class }}" x="{{ band.x }}" y="{{ timeline.band_y }}" width="{{ band.width }}" height="{{ timeline.band_height }}"><title>{{ band.label }}</title></rect>
  {% endfor %}
  {% if timeline.damage %}
  {% for bar in timeline.damage.bars %}
  <rect class="damage-bar" x="{{ bar.x }}" y="{{ bar.y }}" width="{{ bar.width }}" height="{{ bar.height }}"/>
  {% endfor %}
  <text class="track-label" x="{{ timeline.label_x }}" y="{{ timeline.damage.baseline_y }}">Damage taken</text>
  {% endif %}
  {% for row in timeline.cooldowns %}
  {% if row.not_judged %}
  <rect class="not-judged" x="{{ row.not_judged.x }}" y="{{ row.baseline_y }}" width="{{ row.not_judged.width }}" height="{{ timeline.row_height }}"/>
  {% endif %}
  {% for span in row.unavailable %}
  <rect class="on-cooldown" x="{{ span.x }}" y="{{ row.baseline_y }}" width="{{ span.width }}" height="{{ timeline.row_height }}"/>
  {% endfor %}
  {% for press in row.presses %}
  <rect class="press" x="{{ press.x }}" y="{{ row.baseline_y }}" width="4" height="{{ timeline.row_height }}"/>
  {% endfor %}
  <text class="track-label" x="{{ timeline.label_x }}" y="{{ row.baseline_y }}">{{ row.label }}</text>
  {% endfor %}
</svg>
{% if timeline.damage %}<p class="sub">{{ timeline.damage.peak_label }}</p>{% endif %}
<p class="sub">{{ timeline.legend }}</p>
<p class="badges">{% for badge in timeline.badges %}<span class="badge {{ badge.tint }}">{{ badge.label }}</span>{% endfor %}</p>
{% endif %}
{% endmacro %}
```

- [ ] **Step 5: Call it from the players panel**

At the top of `src/wowperf/adapters/render/_players.html.j2`, beside the existing macro import, add:

```jinja
{% from "_player_timeline.html.j2" import player_timeline with context %}
```

**`with context` is required.** A macro imported without it cannot see `icons_by_id`, and the membership test that guards an icon evaluates false silently rather than raising, so the omission ships as "no icons ever" with a green suite.

Inside the player panel, after the `<p class="stats">` line, add:

```jinja
  {{ player_timeline(player.timeline) }}
```

- [ ] **Step 6: Add the CSS**

Add to `src/wowperf/adapters/render/report.css.j2`:

```css
.player-timeline { display: block; width: 100%; margin: 10px 0 2px; }
.pull-band { fill: var(--line); }
.damage-bar { fill: var(--hit); }
.on-cooldown { fill: var(--line); opacity: 0.55; }
.not-judged { fill: none; stroke: var(--ink-faint); stroke-width: 1; stroke-dasharray: 3 2; }
.press { fill: var(--ours); }
```

`.not-judged` is dashed and unfilled rather than a paler shade of `.on-cooldown`: the two mean different things, and a difference of shape survives a greyscale screenshot where a difference of opacity does not.

- [ ] **Step 7: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: the golden-file test FAILS again, this time gaining the timeline SVG for its one player. Read the diff, confirm it is only the SVG and its legend, and regenerate.

- [ ] **Step 8: Prove the `with context` matters**

Delete ` with context` from the import added in Step 5 and run the render tests. Note in the commit body whether any test failed. If none did, add one that does before restoring it — the finding-icons review found four of five templates where removing it changed nothing that any test observed.

- [ ] **Step 9: Commit**

```bash
/mingw64/bin/git add src/wowperf/adapters/render/_player_timeline.html.j2 src/wowperf/adapters/render/_players.html.j2 src/wowperf/adapters/render/report.css.j2 src/wowperf/domain/report/model.py src/wowperf/domain/report/players.py tests/adapters/render/test_html_sections.py
```

Commit subject: `Draw each player's run on their own sub-tab`. Body: why the partial computes nothing, and why not-judged is drawn as a shape rather than a shade.

---

### Task 7: Put the ability's icon on each press

**Files:**
- Modify: `src/wowperf/domain/report/model.py` — nothing new; `Press.icon_class` already exists.
- Modify: `src/wowperf/domain/report/player_timeline.py`
- Modify: `src/wowperf/adapters/render/_player_timeline.html.j2`
- Modify: `src/wowperf/adapters/render/html.py`
- Test: `tests/domain/report/test_build_player_timeline.py`, `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: `all_ledger_rows(report)` and the icon walk in `adapters/render/html.py`; `icons_by_id` in the template context.
- Produces: `Press.icon_class` populated as `f"i-{ability_id}"`.

- [ ] **Step 1: Write the failing domain test**

```python
def test_a_press_carries_the_class_that_draws_its_ability_icon() -> None:
    run = a_run(pulls=(a_pull(0, 0, 600_000),))
    loaded = LoadedRun(run=run, casts=(a_cast(1, SHIELD.ability_id, 300_000),))
    press = a_timeline(loaded, defensives=KIT).cooldowns[0].presses[0]
    assert press.icon_class == f"i-{SHIELD.ability_id}"
```

- [ ] **Step 2: Run and watch it fail**

Expected: FAIL, `assert '' == 'i-48792'`.

- [ ] **Step 3: Populate it**

In `_cooldown_rows`, change the `Press(...)` construction to:

```python
                    Press(
                        x=round(TRACK_X0 + (at - origin_ms) / 1000 * scale, PRECISION),
                        icon_class=f"i-{ability.ability_id}",
                    )
```

- [ ] **Step 4: Write the failing test for the icon reaching the page**

Icons reach the page only when `render()` is given an `IconSource`. `test_html_sections.py`
already has `FakeIcons` for exactly this. Add:

```python
def test_a_pressed_abilitys_icon_is_both_embedded_and_drawn_on_the_timeline() -> None:
    html = render(
        a_report(players=(a_player_card(timeline=a_drawn_timeline()),)),
        icons=FakeIcons({45438: "data:image/jpeg;base64,AAA"}),
    )
    assert ".i-45438 { background-image: url(data:image/jpeg;base64,AAA); }" in html
    # The rule alone proves the resolver ran, not that anything was drawn. Split the
    # stylesheet off and require the class in the body too -- the finding-icons review
    # found four sites where only the rule was asserted and the mark was never emitted.
    assert "i-45438" in html.split("</style>")[1]


def test_a_press_whose_icon_never_resolves_still_draws_its_mark() -> None:
    html = render(
        a_report(players=(a_player_card(timeline=a_drawn_timeline()),)),
        icons=FakeIcons({}),
    )
    assert "background-image" not in html
    assert "press" in html.split("</style>")[1]
```

- [ ] **Step 5: Make the resolver see the presses**

In `src/wowperf/adapters/render/html.py`, the icon walk collects ability ids from `report.deaths` and `all_ledger_rows(report)`. Add the presses: for every `card` in `report.players` with a `timeline`, for every `row` in `card.timeline.cooldowns`, take `row.ability_id`. Follow the existing walk's shape rather than inventing a second one, and ask an unresolved id only once — `tests/adapters/render/test_html_sections.py:640` already holds that rule for the other sites.

- [ ] **Step 6: Draw it**

In `_player_timeline.html.j2`, change the press rect to carry the icon when one resolved:

```jinja
  {% for press in row.presses %}
  {% if row.ability_id in icons_by_id %}
  <rect class="press {{ press.icon_class }}" x="{{ press.x }}" y="{{ row.baseline_y }}" width="{{ timeline.row_height }}" height="{{ timeline.row_height }}"/>
  {% else %}
  <rect class="press" x="{{ press.x }}" y="{{ row.baseline_y }}" width="4" height="{{ timeline.row_height }}"/>
  {% endif %}
  {% endfor %}
```

An SVG `<rect>` cannot show a CSS `background-image`. If the gate shows nothing rendering, switch the icon branch to `<image href="{{ icons_by_id[row.ability_id] }}" .../>`, which takes the data URI directly and needs no CSS class — and then delete `Press.icon_class` and the test from Step 1 rather than leaving a field nothing reads.

- [ ] **Step 7: Run the gate and commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/player_timeline.py src/wowperf/adapters/render/_player_timeline.html.j2 src/wowperf/adapters/render/html.py tests/domain/report/test_build_player_timeline.py tests/adapters/render/test_html_sections.py
```

Commit subject: `Show which ability each press on the timeline was`. Body: why the test asserts a drawn element and not only an embedded rule.

---

### Task 8: Measure against a real run, then fix the constants

The design refuses to assert these figures. This task takes them. It spends quota: roughly 83 points of the 3600 available in an hour.

**Files:**
- Modify: `src/wowperf/domain/report/player_timeline.py` (`BUCKET_SECONDS`, and `ROW_HEIGHT` if the row count demands it)
- Modify: `docs/plans/2026-09-10-per-player-page-design.md` (§12, replacing the measurements to take with the measurements taken)

- [ ] **Step 1: Render a real run**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run wowperf analyze <report-url> --out out
```

Use a real keystone run with five players and at least one death. Record the report code and fight id.

- [ ] **Step 2: Record the four figures**

1. **Row count.** How many tracked abilities each of the five players actually cast. The design assumes six to twelve. If any player exceeds twenty, `ROW_HEIGHT` or the drawing's shape needs revisiting before this task closes.
2. **Page size in bytes**, against the 257,988 recorded before this work, and how many of the added bytes are new icons rather than reused ones.
3. **Bucket width.** Re-render at `BUCKET_SECONDS` of 2, 5 and 10. Keep the value where a single lethal spike is still one bar and the file has not gained thousands of rects. Record all three numbers, not just the winner.
4. **Pre-layout height.** With scripting disabled, the document's height against the same page before this work — the figure the deep-link defect note now says a harness should expect.

- [ ] **Step 3: Fix the constant and say why**

Set `BUCKET_SECONDS` to the measured value. Its docstring must state the figure it was chosen against, not the rule alone.

- [ ] **Step 4: Rewrite §12 of the design**

Replace "Measurements to take, not assert" with the measurements taken, each with its number and the date. Leave the section's title honest — it is a record now, not a promise.

- [ ] **Step 5: Run the gate and commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/player_timeline.py docs/plans/2026-09-10-per-player-page-design.md
```

Commit subject: `Fix the timeline's bucket width against a run rather than a guess`. Body: the three widths tried and what each did to the page.

---

## Self-review

**Spec coverage.** §1 → Tasks 1, 6. §2 → Task 2 (the one input not already reaching the report). §3 → Task 1. §4 → Tasks 3, 4, 5. §5 → Task 5, with a mutation check at Step 5. §6 → Task 3 (`badges`) and Task 6 (the legend). §7 → Tasks 3, 4, 5. §8 → Task 6. §9 → the Global Constraints, and Task 6's gate. §10 → every task's tests. §11 → already recorded in the defect note; no task needed. §12 → Task 8. §13 → out of scope by design. §14 → open, and Task 8's row-count measurement is what would settle §14.2.

**Placeholders.** None. Task 7 Step 5 describes the icon walk rather than quoting it, because the walk's current shape must be read before it is extended; the step names the file, the two existing sources, and the test that already holds the once-only rule.

**Type consistency.** `build_player_timeline` takes `(loaded, actor_id, class_name, spec, defensives, throughput)` in Tasks 3, 4, 5, 6. `Press.icon_class` is introduced in Task 3's model and populated in Task 7. `axis_scale`/`axis_ticks` are named identically in Tasks 3, 4 and 5. `PlayerCard.slug` is a `str` throughout; `PlayerCard.timeline` is `PlayerTimeline | None`.

**One risk the plan carries deliberately.** Task 7 Step 6 may discover that a CSS `background-image` cannot paint an SVG `<rect>`. The step says what to do instead and instructs the implementer to delete `Press.icon_class` rather than leave a field nothing reads.
