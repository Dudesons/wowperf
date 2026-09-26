# Night boss summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every boss the night pulled two or more times gets a summary -- the existing progression page for that boss -- drawn inside the night page as the first, default entry of that boss's pull dropdown.

**Architecture:** `BossSection` gains `summary: ProgressionReport | None`, built by the unchanged `build_progression_report` from the progression findings the `night` command already computes and currently writes only to JSON. The five progression partials take the `{{ scope }}` prefix the raid partials took for the night page, and a `_night_summary.html.j2` macro draws them once per boss under a `b{index}-` prefix minted in the render adapter.

**Tech Stack:** Python 3.12, pydantic frozen models (`wowperf.domain.base.Frozen`), Jinja2, typer, pytest. `uv` is the only toolchain: in Bash it is `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-26-night-boss-summary-design.md`. Read it, and `docs/plans/2026-09-23-night-report-design.md` §3 and §8, before Task 1.

## Global Constraints

- No new analyser, no new query, no new stream, no change to the findings JSON (spec §3).
- `build_progression_report` is called unchanged (spec §3).
- A boss has a summary exactly when `len(boss.attempts_with_events) >= 2` -- drawn pulls, not attempts (spec §4).
- The standalone progression page renders byte-identically before and after the scoping edit (spec §5, §7).
- `src/wowperf/domain/` performs no I/O and imports no template or network code (CLAUDE.md invariants).
- The page keeps exactly one inline script, and `night.js.j2` does not change (spec §5).
- Every template loops and decides nothing; the scope prefix is minted in `src/wowperf/adapters/render/html.py` (spec §5).
- No real character name in `tests/`. The sanctioned names are `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`. Players on report `cW38jmwdnZfbHVL4` are referred to by class, spec, role or index.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before writing the first test.
- Commit messages: imperative subject, no `feat:` prefix, body says why, plain ASCII, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit with `/mingw64/bin/git` (the bare `git` is rewritten by a hook that can refuse commits). Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy`, `uv run pytest` -- all green, output pristine.

---

### Task 1: A boss section carries its summary

**Files:**
- Modify: `src/wowperf/domain/report/night_model.py` (`BossSection` at :42-52, `all_night_ledger_rows` at :108-127)
- Modify: `src/wowperf/domain/report/night_build.py` (`build_night_report` at :115-190)
- Modify: `src/wowperf/cli.py` (the `build_night_report` call at :1994-2005 -- one keyword argument, so the gate stays green)
- Modify: `tests/adapters/render/test_night_html_invariants.py` (`a_night_report` at :272-293 -- one keyword argument)
- Test: `tests/domain/report/test_night_build.py`, `tests/domain/report/test_night_model.py`

**Interfaces:**
- Consumes: `build_progression_report(series: LoadedProgression, findings: Sequence[Finding], fetched_at: str) -> ProgressionReport` (`progression_build.py:34`); `all_progression_ledger_rows(report: ProgressionReport) -> Iterator[LedgerRow]` (`progression_model.py:115`); `analyse_progression(series: LoadedProgression) -> list[Finding]` (`domain/analysis/progression_service.py:36`) for test data.
- Produces:
  - `BossSection.summary: ProgressionReport | None = None`
  - `build_night_report(loaded, findings_by_fight, fetched_at, defensives, consumables, roles, *, deep_fights, death_cards, findings_by_boss: Mapping[int, Sequence[Finding]], externals=..., self_resurrections=...) -> NightReport` -- `findings_by_boss` is keyed by `LoadedProgression.progression.encounter_id`, keyword-only and **required** (no default: a caller that forgot it would silently build a night with empty summaries).
  - `MIN_PULLS_FOR_SUMMARY = 2` in `night_build.py`.
  - `all_night_ledger_rows` yields summary rows after each boss's pull rows.

- [ ] **Step 1: Write the failing builder tests**

Add to `tests/domain/report/test_night_build.py`. Use the existing `a_night(bosses=...)` fixture and real findings from `analyse_progression` -- never hand-built `progression.*` findings, which would test the fixture rather than the summary.

```python
from wowperf.domain.analysis.progression_service import analyse_progression
from wowperf.domain.report.progression_build import build_progression_report


def boss_findings(night: LoadedNight) -> dict[int, tuple[Finding, ...]]:
    """What the command computes per boss: the progression analyser, run for real."""
    return {
        boss.progression.encounter_id: tuple(analyse_progression(boss))
        for boss in night.loaded
    }


def a_report(night: LoadedNight, *, death_cards: bool = True) -> NightReport:
    return build_night_report(
        night,
        NO_FINDINGS,
        FETCHED,
        NO_DEFENSIVES,
        NO_CONSUMABLES,
        NO_ROLES,
        deep_fights=frozenset(),
        death_cards=death_cards,
        findings_by_boss=boss_findings(night),
    )


def test_a_boss_pulled_once_has_no_summary_and_a_boss_pulled_twice_has_one() -> None:
    """One and two, side by side, so the threshold is pinned from both sides at once."""
    report = a_report(a_night(bosses=(1, 2)))

    assert report.bosses[0].summary is None
    assert report.bosses[1].summary is not None


def test_a_boss_with_no_drawn_pull_has_no_summary() -> None:
    report = a_report(a_night(bosses=(2,), failed=(10, 11)))

    assert report.bosses[0].pulls == ()
    assert report.bosses[0].summary is None


def test_the_threshold_counts_drawn_pulls_not_attempts() -> None:
    """Three attempts, two failed: one drawn pull, so no summary -- though three were pulled."""
    report = a_report(a_night(bosses=(3,), failed=(11, 12)))

    assert len(report.bosses[0].pulls) == 1
    assert report.bosses[0].summary is None


def test_a_summary_is_the_progression_page_for_that_boss_and_nothing_else() -> None:
    """Equal to a direct call on the same boss: the reuse is whole, not an imitation."""
    night = a_night(bosses=(1, 3))
    findings = boss_findings(night)
    report = a_report(night)

    boss = night.loaded[1]
    assert report.bosses[1].summary == build_progression_report(
        boss, findings[boss.progression.encounter_id], FETCHED
    )


def test_a_summary_with_a_failed_pull_says_how_many_were_counted_and_how_many_deepened() -> None:
    report = a_report(a_night(bosses=(3,), failed=(12,)))

    summary = report.bosses[0].summary
    assert summary is not None
    assert summary.provenance.attempts_counted == 3
    assert summary.provenance.attempts_deepened == 2


def test_a_summary_does_not_depend_on_the_death_card_tier() -> None:
    """Progression reads deaths and damage taken, which every tier fetches."""
    night = a_night(bosses=(3,))

    assert a_report(night, death_cards=True).bosses[0].summary == a_report(
        night, death_cards=False
    ).bosses[0].summary
```

Also update every existing `build_night_report(...)` call in this file to pass `findings_by_boss={}`: they assert on pulls and tiers, and an empty mapping gives every summary no findings, which is what they had before.

- [ ] **Step 2: Write the failing walker test**

Add to `tests/domain/report/test_night_model.py`, modelled on `test_every_field_holding_rows_is_walked` at :136. Build a `NightReport` by hand with one `BossSection` whose `summary` is a `ProgressionReport` carrying one row in each of `attempt_rows`, `repeat_rows`, `best_rows` and `observations`, each with a distinct `finding_id`, and assert all four ids are in `{row.finding_id for row in all_night_ledger_rows(report)}`. Take an existing `ProgressionReport` construction from `tests/domain/report/test_progression_model.py` rather than inventing one.

- [ ] **Step 3: Run the new tests and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/report/test_night_build.py tests/domain/report/test_night_model.py -v`
Expected: FAIL -- `build_night_report()` got an unexpected keyword argument `findings_by_boss`, and `BossSection` has no field `summary`.

- [ ] **Step 4: Add the field**

In `night_model.py`, import `ProgressionReport` and `all_progression_ledger_rows` from `wowperf.domain.report.progression_model`, then:

```python
class BossSection(Frozen):
    """One boss's pulls, in the order the report's fight list gave them, and its summary.

    Present even when `pulls` is empty: a boss whose every attempt was a
    reset, or whose every attempt failed to deepen, is still a boss the night
    pulled, and the page says so rather than dropping it -- the same ruling
    `LoadedNight` already makes one layer down, in `night.py`.

    `summary` is the progression page for this boss, built whole by
    `build_progression_report`, or None when fewer than two pulls were drawn:
    nearly every progression finding compares attempts with each other, and one
    attempt leaves nothing to compare.
    """

    boss_name: str
    pulls: tuple[PullSection, ...] = ()
    summary: ProgressionReport | None = None
```

In `all_night_ledger_rows`, inside the boss loop and after the pull loop:

```python
        if boss.summary is not None:
            rows.extend(all_progression_ledger_rows(boss.summary))
```

Extend its docstring by one sentence: a boss's summary rows are walked through `all_progression_ledger_rows` for the same reason pulls go through `all_raid_ledger_rows`.

- [ ] **Step 5: Build the summary**

In `night_build.py`:

```python
MIN_PULLS_FOR_SUMMARY = 2
"""Below this many drawn pulls a boss gets no summary: there is nothing to compare."""
```

Add `findings_by_boss: Mapping[int, Sequence[Finding]]` as a required keyword-only parameter after `death_cards`, document it in the docstring (keyed by encounter id, the same mapping the command writes to the JSON), and replace the `bosses.append(...)` with:

```python
        drawn = boss.attempts_with_events
        summary = (
            build_progression_report(
                boss, findings_by_boss.get(boss.progression.encounter_id, ()), fetched_at
            )
            if len(drawn) >= MIN_PULLS_FOR_SUMMARY
            else None
        )
        bosses.append(
            BossSection(
                boss_name=boss.progression.boss_name, pulls=tuple(pulls), summary=summary
            )
        )
```

and iterate `for attempt in drawn:` in the pull loop above it. Import `build_progression_report` from `wowperf.domain.report.progression_build`.

- [ ] **Step 6: Keep the two other callers compiling**

`src/wowperf/cli.py:1994-2005`: add `findings_by_boss=boss_findings,` to the `build_night_report` call. `boss_findings` already exists at :1911 and is keyed by encounter id.

`tests/adapters/render/test_night_html_invariants.py:272-293`: add `findings_by_boss={},` to `a_night_report`'s call. Task 3 replaces it with real findings; here it keeps the rendered page unchanged, so the night golden still passes.

- [ ] **Step 7: Run, pass, prove the tests can fail**

Run the two test files, then the full gate. Then, one at a time, change `MIN_PULLS_FOR_SUMMARY` to `1` and to `3`, change `len(drawn)` to `len(boss.progression.attempts)`, and drop the `rows.extend(...)` line: each must turn at least one new test red. Restore after each.

- [ ] **Step 8: Commit**

Subject: `Give a boss pulled more than once its progression page as a summary`

---

### Task 2: Scope the progression partials

**Files:**
- Modify: `src/wowperf/adapters/render/_progression_summary.html.j2`, `_progression_attempts.html.j2`, `_progression_repeats.html.j2`, `_progression_best.html.j2`, `_progression_provenance.html.j2`
- Modify: `src/wowperf/adapters/render/progression.html.j2` (the `<nav>` at :31-37)
- Test: `tests/adapters/render/test_progression_html_invariants.py`

**Interfaces:**
- Consumes: the `scope` template variable, as the raid partials read it (`_raid_summary.html.j2:4`). Jinja's default `Undefined` renders a missing `scope` as the empty string, which is how `raid.html.j2` and `progression.html.j2` draw unprefixed pages.
- Produces: every `id`, `data-tab-panel`, `data-tab-for` and `href="#..."` drawn by the five partials and by `progression.html.j2`'s nav starts with `{{ scope }}`. Task 3 relies on this.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/render/test_progression_html_invariants.py`:

```python
from wowperf.adapters.render.html import _environment, PROGRESSION_TEMPLATE_NAME

SCOPE = "b9-"


def test_every_anchor_the_progression_partials_draw_takes_the_scope() -> None:
    """The night page draws these partials once per boss; an unprefixed id collides.

    Rendered through the real template with a scope handed in, which is exactly
    how the night page will reach them. Every family of anchor is checked, not
    only ids: a tab button whose `data-tab-for` stayed bare would open another
    boss's panel.
    """
    html = _environment().get_template(PROGRESSION_TEMPLATE_NAME).render(
        report=a_progression_report(), icons_by_id={}, scope=SCOPE
    )
    body = html.split("<main>", 1)[1]
    values = (
        re.findall(r'\sid="([^"]+)"', body)
        + re.findall(r'data-tab-panel="([^"]+)"', body)
        + re.findall(r'data-tab-for="([^"]+)"', body)
        + re.findall(r'href="#([^"]+)"', body)
    )
    assert values, "a page with no anchors would pass this vacuously"
    bare = sorted({value for value in values if not value.startswith(SCOPE)})
    assert bare == [], f"drawn without the scope: {bare}"
```

The split at `<main>` leaves out the `<symbol id="icon-...">` definitions in the page head, which are page-wide by design (`night.html.j2` draws them once for every pull). Check that `a_progression_report()` produces at least one finding card; if it carries none, `ledger_row`'s `finding-` ids go unchecked -- use `a_progression_findings_with_an_ability()` (:333) to build the report instead if so.

- [ ] **Step 2: Run it and watch it fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/test_progression_html_invariants.py -v`
Expected: the new test FAILS listing `tab-summary`, `main`, `observations`, `attempts`, `repeats`, `best`, `provenance`, `tab-attempts`, ... The golden test still passes.

- [ ] **Step 3: Add the prefix**

In each partial, prefix every anchor exactly as `_raid_summary.html.j2` does:

```
<section class="panel" data-tab-panel="{{ scope }}main" id="{{ scope }}tab-summary">
<h2 id="{{ scope }}observations">Other findings</h2>
```

-- and likewise `tab-attempts`/`attempts`, `tab-repeats`/`repeats`, `tab-best`/`best`, `tab-provenance`/`provenance`. In `progression.html.j2`'s nav, `data-tab-group="{{ scope }}main"` and each `data-tab-for="{{ scope }}tab-..."`. `ledger_row` in `_macros.html.j2` already reads `scope`; leave it alone.

- [ ] **Step 4: Run, pass, and hold the golden**

Run the file again: the new test passes, and `test_the_rendered_page_matches_the_golden_file` (:449) must pass **without** `--golden-update`. If the golden moves, the edit changed more than anchors: find what, and undo it. Then the full gate.

Prove the new test can fail: remove `{{ scope }}` from one `h2` id and one `data-tab-for`, run, see both named, restore.

- [ ] **Step 5: Commit**

Subject: `Let the progression partials be drawn more than once on one page`

---

### Task 3: Draw each summary on the night page

**Files:**
- Create: `src/wowperf/adapters/render/_night_summary.html.j2`
- Modify: `src/wowperf/adapters/render/night.html.j2`
- Modify: `src/wowperf/adapters/render/html.py` (`_night_scopes` at :183, `render_night` at :210)
- Modify: `tests/adapters/render/test_night_html_invariants.py`
- Modify: `tests/adapters/render/golden/night.html` (regenerated, and read by eye)

**Interfaces:**
- Consumes: `BossSection.summary` and `findings_by_boss` (Task 1); the scoped partials (Task 2).
- Produces: per boss with a summary, a `<option value="b{i}-summary">` first in `#night-pull-b{i}`, and `<section class="pull" data-night-pull-panel id="b{i}-summary">`. `render_night` passes `boss_scopes: tuple[str, ...]` to the template, one `b{i}-` per boss in `report.bosses` order.

- [ ] **Step 1: Widen the render fixture to a night with a single-pull boss**

In `tests/adapters/render/test_night_html_invariants.py`:
- `PULLS_PER_BOSS = (1, 2, 3)`. Rewrite its docstring: three bosses at three different counts, the first pulled once, so the page holds a boss with no summary beside two with one, and still no two bosses share a count.
- `NIGHT_BOSS_NAMES = (*BOSS_NAMES, "Vorthal the Unmade")`, used by `a_loaded_night` at :132 in place of `BOSS_NAMES`. Do **not** extend `BOSS_NAMES` itself: `test_every_pull_is_built_and_grouped_under_its_own_boss` in `test_night_build.py` compares against the whole tuple.
- `ABILITY_IDS` and `ROW_ABILITY_IDS` gain a sixth id each (`445_571`, `700_106`); update "Five ids for five pulls" in their docstrings.
- `a_night_report` passes `findings_by_boss={boss.progression.encounter_id: tuple(analyse_progression(boss)) for boss in night.loaded}` -- the real analyser, not an empty map, so the summary draws real rows.

Run the file. Tests that counted the old shape now fail. For each, decide which it is and write down the decision in the step's commit body:
- **The intended new shape** -- e.g. `:441` hardcodes two bosses, `:707` expects each pull control to hold exactly its pulls, `test_every_pull_is_its_own_tab_group` (:444) counts one tab group per pull, and `:541` expects `pull_blocks` to return one block per pull, where a summary section is now cut as a block too. Make each count the summaries explicitly (`sum(1 for boss in report.bosses if boss.summary)`), never by loosening to `>=`.
- **A real defect** -- stop and report it.
Rename `test_no_element_id_appears_twice_across_five_pulls` to `..._across_every_pull`.

- [ ] **Step 2: Write the failing summary tests**

`pull_blocks` (:510) already cuts the page at every `<section class="pull"`, which a summary section opens with too, and ends the last block at `<section class="night-notes">`. Build on it rather than writing a second cutter:

```python
SUMMARY_ID = re.compile(r'<section class="pull" data-night-pull-panel id="(b\d+-summary)">')


def summary_blocks(html: str) -> dict[str, str]:
    """Each summary section's markup, keyed by its id, cut where `pull_blocks` cuts."""
    blocks: dict[str, str] = {}
    for block in pull_blocks(html):
        opened = SUMMARY_ID.match(block)
        if opened is not None:
            blocks[opened.group(1)] = block
    return blocks
```

```python
def test_a_boss_pulled_more_than_once_opens_on_its_summary() -> None:
    """The summary is the first option, so a fresh page and a boss change both land on it."""
    html = a_night_page()
    for index, count in enumerate(PULLS_PER_BOSS):
        control = re.search(
            rf'<select id="night-pull-b{index}" data-night-pull>(.*?)</select>', html, re.S
        )
        assert control is not None
        first = re.search(r'<option value="([^"]+)"', control.group(1))
        assert first is not None
        if count >= 2:
            assert first.group(1) == f"b{index}-summary"
        else:
            assert first.group(1).endswith("-pull"), "a single-pull boss opens on its pull"


def test_exactly_the_bosses_pulled_more_than_once_carry_a_summary_section() -> None:
    html = a_night_page()
    expected = {f"b{i}-summary" for i, count in enumerate(PULLS_PER_BOSS) if count >= 2}
    assert set(summary_blocks(html)) == expected


def test_a_summary_draws_the_progression_tabs_under_its_own_scope() -> None:
    """Five tabs, each button naming a panel inside the same summary."""
    for scope_id, block in summary_blocks(a_night_page()).items():
        scope = scope_id.removesuffix("summary")
        buttons = re.findall(r'data-tab-for="([^"]+)"', block)
        panels = re.findall(r'<section class="panel" data-tab-panel="[^"]+" id="([^"]+)"', block)
        assert buttons == [f"{scope}tab-{name}" for name in
                           ("summary", "attempts", "repeats", "best", "provenance")]
        assert buttons == panels


def test_a_summary_draws_every_progression_finding_its_boss_earned() -> None:
    night = a_loaded_night()
    html = a_night_page()
    blocks = summary_blocks(html)
    for index, boss in enumerate(night.loaded):
        if len(boss.attempts_with_events) < 2:
            continue
        ids = {finding.id for finding in analyse_progression(boss)}
        assert ids, "a fixture boss with no progression finding pins nothing"
        drawn = set(re.findall(rf'id="b{index}-finding-([^"]+)"', blocks[f"b{index}-summary"]))
        assert drawn == ids
```

If the fixture's bosses earn no progression finding, change the fixture's `deaths_after_ms` per pull (different death times give `progression.collapse` and `progression.repeat.first_death` something to find) rather than weakening the assertion.

- [ ] **Step 3: Run and watch them fail**

Expected: FAIL -- no `b0-summary` option or section exists.

- [ ] **Step 4: Mint the boss scopes**

In `html.py`, beside `_night_scopes`:

```python
def _night_boss_scopes(report: NightReport) -> tuple[str, ...]:
    """The id prefix each boss's summary is drawn under, in `report.bosses` order.

    A boss has no fight id of its own, so its index names it -- the same `b{i}`
    the boss dropdown and the "Nothing to show" section already carry. It can
    never collide with a pull's `f{fight_id}-`, which begins with another letter.
    """
    return tuple(f"b{index}-" for index in range(len(report.bosses)))
```

and pass `boss_scopes=_night_boss_scopes(report)` to the template in `render_night`. The icon walk needs no change: it reads `all_night_ledger_rows`, which Task 1 widened.

- [ ] **Step 5: The macro**

Create `_night_summary.html.j2`:

```
{# ABOUTME: One boss's summary on the night page: its heading, the five progression tabs, #}
{# ABOUTME: and the progression partials below. A macro, so `scope` and `report` bind as arguments. #}
{# Rebinds `report` to one boss's ProgressionReport exactly as `_night_pull.html.j2`
   rebinds it to one pull's RaidReport, with no assignment tag. `scope` prefixes
   every id drawn under here; the adapter minted it from the boss's index. #}
{% macro summary_section(report, scope) %}
<section class="pull" data-night-pull-panel id="{{ scope }}summary">

<h2>{{ report.header.boss }} {{ report.header.difficulty }} &middot; summary</h2>
<p class="sub">{{ report.header.outcome }} &middot; {{ report.header.attempts_counted }} attempts read{% if report.header.attempts_discarded %}, {{ report.header.attempts_discarded }} excluded as too short{% endif %} &middot; depth is {{ report.header.depth_label }}</p>

<nav class="tabs" data-tab-group="{{ scope }}main" aria-label="Sections">
  <button type="button" class="tab" data-tab-for="{{ scope }}tab-summary">Summary</button>
  <button type="button" class="tab" data-tab-for="{{ scope }}tab-attempts">Attempts</button>
  <button type="button" class="tab" data-tab-for="{{ scope }}tab-repeats">Repeats</button>
  <button type="button" class="tab" data-tab-for="{{ scope }}tab-best">Best attempt</button>
  <button type="button" class="tab" data-tab-for="{{ scope }}tab-provenance">Provenance</button>
</nav>
{# The blank lines below are page output, not source spacing. #}



{% include "_progression_summary.html.j2" %}

{% include "_progression_attempts.html.j2" %}

{% include "_progression_repeats.html.j2" %}

{% include "_progression_best.html.j2" %}

{% include "_progression_provenance.html.j2" %}

</section>
{% endmacro %}
```

The header line is `progression.html.j2`'s own sub-line at :29, so the two pages say the same thing about the same boss.

- [ ] **Step 6: The dropdown and the sections**

In `night.html.j2`, import the macro beside `pull_section`:

```
{% from "_night_summary.html.j2" import summary_section with context %}
```

As the first thing inside each `<select id="night-pull-b{{ loop.index0 }}" data-night-pull>`:

```
{% if boss.summary %}
    <option value="{{ boss_scopes[loop.index0] }}summary">Summary: {{ boss.summary.provenance.attempts_deepened }} pulls</option>
{% endif %}
```

`attempts_deepened` is the drawn-pull count and is at least two whenever a summary exists, so "pulls" is always the right number; the template makes no decision. In the section loop, before `{% for pull in boss.pulls %}`:

```
{% if boss.summary %}
{{ summary_section(boss.summary, boss_scopes[loop.index0]) }}
{% endif %}
```

`loop` inside a `{% for pull %}` is the inner loop's -- place both `boss_scopes[loop.index0]` reads where `loop` is still the boss loop's.

- [ ] **Step 7: Run, pass, prove each test can fail**

Run the file and the full gate. Then break each in turn and watch the named test fail: drop the `{% if boss.summary %}` option; move it after the pull options; unscope one `data-tab-for` in the macro; pass `boss_scopes` shifted by one.

- [ ] **Step 8: Regenerate the golden, and read it**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/adapters/render/test_night_html_invariants.py --golden-update`, then run without the flag. Read the diff of `golden/night.html` by eye: the first boss's control holds only its pull, the other two open on "Summary: N pulls", each summary draws five tabs, and no player name appears in a summary.

- [ ] **Step 9: Re-derive the byte budget**

Measure `len(golden_night_html().encode("utf-8"))` and `len(golden_night_html(deep_every_pull=True).encode("utf-8"))`. Set `TRIMMED_NIGHT_BUDGET_BYTES` a little above the first -- within about 5%, as the current 70,000 over 67,334 is -- and rewrite its docstring with both measured figures and today's date. `test_the_budget_would_catch_a_full_card_regression` must still pass: if the deep page no longer exceeds the new budget, stop and report, because the budget has then stopped telling the two tiers apart.

- [ ] **Step 10: Commit**

Subject: `Open each boss pulled more than once on its summary`

---

### Task 4: The command hands the page the findings the JSON already carries

**Files:**
- Test: `tests/test_cli_night.py`

Task 1 already added `findings_by_boss=boss_findings` to the command. This task pins that the page and the file agree, which is the one defect the design (§6) says a test must catch: a summary drawn from a different list than the one written out.

**Interfaces:**
- Consumes: `run_night(tmp_path)` and `_written(tmp_path)` in `tests/test_cli_night.py`; its fixture holds two pulls under `NIGHT_FIRST_BOSS` and one under `NIGHT_SECOND_BOSS`.

- [ ] **Step 1: Write the test**

```python
def test_each_boss_summary_draws_the_findings_the_file_writes_for_that_boss(
    tmp_path: Path,
) -> None:
    """One findings object, two readers: a summary drawn from another list is a defect.

    The first boss was pulled twice and has a summary; the second was pulled
    once and has none, so its findings are in the file and on no summary.
    """
    result = run_night(tmp_path)
    assert result.exit_code == 0, result.output
    findings_file, report_file = _written(tmp_path)
    payload = json.loads(findings_file.read_text(encoding="utf-8"))
    html = report_file.read_text(encoding="utf-8")

    written = {finding["id"] for finding in payload["bosses"][0]["findings"]}
    assert written, "a boss with no finding pins nothing"
    drawn = set(re.findall(r'id="b0-finding-([^"]+)"', html))
    assert drawn == written
    assert 'id="b1-summary"' not in html
```

Add `import re` if the file lacks it.

- [ ] **Step 2: Prove it can fail**

It passes at once, because Task 1 wired the argument; that is expected, since the wiring had to land with the signature to keep the gate green. Prove it guards something: in `cli.py`, pass `findings_by_boss={}` and watch it fail on `drawn == written`; pass a mapping with the two bosses' findings swapped and watch it fail again. Restore.

- [ ] **Step 3: Gate, and commit**

Subject: `Pin that a night's summaries and its findings file agree`

---

### Task 5: Say on the skill page what the night page now opens on

**Files:**
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` (the `## The \`night\` command` section's last paragraph)
- Modify: `docs/plans/2026-09-26-night-boss-summary-design.md` (the status line)

- [ ] **Step 1: The skill paragraph**

After "…behind two dropdowns, a boss and then a pull within it.", add:

> A boss pulled two or more times opens on a summary before any pull: the page `wowperf progression` draws for that boss — its attempts, what kept repeating across them and what the best one did differently — built from the same findings the night's JSON writes under that boss. A boss pulled once has no summary, since one attempt leaves nothing to compare, and opens on its pull.

Name no flag that `wowperf night --help` does not offer: `tests/test_skills.py` compares the section's flags against the real command in both directions.

- [ ] **Step 2: The design's status**

Change the design's status line to: `approved design, planned in docs/plans/2026-09-26-night-boss-summary-plan.md.`

- [ ] **Step 3: Run the skill tests, then the gate**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/test_skills.py -v`

- [ ] **Step 4: Commit**

Subject: `Document the night page's boss summaries`

---

### Task 6: Exercise it on the real report

**Files:**
- Modify: `tests/e2e/test_night_e2e.py`

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: Extend the e2e**

In `test_a_whole_report_reads_as_one_night`:

- After `build_night_report(...)` -- which now also takes `findings_by_boss={boss.progression.encounter_id: tuple(rank_raid_findings(analyse_progression(boss))) for boss in loaded.loaded}`, the same expression `cli.py:1911-1914` uses, importing `analyse_progression` from `wowperf.domain.analysis.progression_service` and `rank_raid_findings` from `wowperf.domain.analysis.severity` -- assert the summaries sit exactly where the pull counts say:

```python
    assert tuple(boss.summary is not None for boss in report.bosses) == tuple(
        count >= 2 for count in PULLS_PER_BOSS
    )
```

- The tab-group assertion (`len(set(groups)) == report.total_pulls`) now counts the summaries' groups too: make it `report.total_pulls + sum(1 for boss in report.bosses if boss.summary)`, and update the comment above it.
- After the page is read, assert each boss with a summary has a `b{i}-summary` option first in its control, as Task 3's test does, and that `set(re.findall(rf'id="b{i}-finding-([^"]+)"', html))` equals the ids in `payload["bosses"][i]["findings"]` for every `i` with a summary.
- Update the header's "verified live" paragraph with today's date and what this run confirmed.

Read `.claude/skills/wcl-api/SKILL.md` first; this test spends real quota.

- [ ] **Step 2: Run it once, live**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest -m e2e tests/e2e/test_night_e2e.py -v -s`
Expected: PASS, spending about the 106 to 118 points recorded in its header -- summaries fetch nothing. A figure far outside that is a finding: report it.

- [ ] **Step 3: Report the distribution**

Run the default command once over the warm cache -- `/c/Users/damien/.local/bin/uv.exe run wowperf night cW38jmwdnZfbHVL4` -- and read `out/cW38jmwdnZfbHVL4.night.json`, never the HTML. For the three bosses with a summary, and for each progression family (`progression.best`, `.cluster`, `.movement`, `.attempts.discarded`, `.repeat.phase`, `.collapse`, `.repeat.first_death`, `.repeat.ability`, `.best.deaths`), report whether it fired, was withheld or said "not compared", per boss. `movement` is expected to fire only on the seven-pull boss. A family that fires on none of the three is reported as such -- not as a pass -- and the finding ids are reported by family, never with a player slug.

- [ ] **Step 4: Open the page and check the controls**

Serve `out/` with the `report` configuration in `.claude/launch.json` and open `cW38jmwdnZfbHVL4.night.html` over http, never `file://`. Confirm: the page opens on the first boss's first entry; choosing a boss with a summary shows its summary; choosing a pull there shows that pull; choosing the summary again shows it; a single-pull boss opens on its pull; a summary's five tabs switch its own panels and no other boss's. Check the console for errors.

- [ ] **Step 5: Commit**

Subject: `Exercise the night page's boss summaries on a real report`

---

## What this plan deliberately does not build

- Killing blows counted across pulls, deaths per player across pulls, and availability pooled across pulls -- the next designs, which land in the summary this builds (spec §8).
- Any change to progression's own prose. `METHOD_NO_ANATOMY` says the page "draws the night, never one attempt's internals" and names `wowperf raid --fight N`; inside a night page, a pull one dropdown away draws some of those internals. It stays as written because `build_progression_report` is reused unchanged; a reader of this plan who thinks that wording now misleads should raise it rather than edit it.
- Any trend line, parse axis, narrative, or claim that one raider's action caused another's death.
