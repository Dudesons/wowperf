# Phase H: The Report in Tabs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the report's sections under six tabs — Summary, Route & tempo, Deaths, Interrupts, Players, Provenance — driven by one inline script that only shows and hides, so that a sixty-seven-card page becomes six short ones without losing a single finding, a single badge or a single invariant.

**Architecture:** No new layer. The builder (`src/wowperf/domain/report/build.py`) gains one ordered placement table that homes every finding family on a tab's row tuple, and a pointer list for the Summary. The view model (`model.py`) swaps `ledger_losses` for four fields. The template (`report.html.j2`) wraps its sections in panels behind a tab bar and ends with a forty-line script. The tests that pinned "no script" and "eight sections" are rewritten to pin the new rules, not deleted.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `jinja2`, `pytest`, `ruff`, `mypy`. Forty lines of plain JavaScript inside the template, no library.

**Spec:** `docs/plans/2026-09-06-report-tabs-design.md`. It supersedes §11 of `docs/plans/2026-09-05-mplus-report-design.md` and amends its §4, §5, §9 and §10; Task 1 writes those amendments. Read the spec in full before any task, and the report design's §2 ("the template decides nothing") before Tasks 2 to 4.

**Depends on:** `master` at `bfdfdf5` (Phase G merged, design committed). Read `src/wowperf/domain/report/build.py`, `src/wowperf/domain/report/model.py`, `src/wowperf/adapters/render/report.html.j2` and `tests/adapters/render/test_html_invariants.py` before starting any task.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`uv` is not on PATH.** Every bash command using it begins `export PATH="$HOME/.local/bin:$PATH"`.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no file reads, no `tomllib`, no clock, no `jinja2`. Adapters do that.
- **The template decides nothing.** Which finding lands on which tab is the builder's judgement, in `build.py`, tested. The template loops, escapes and interpolates. Which field renders under which panel is fixed structure, like heading order.
- **The script only shows and hides.** It adds and removes a class, sets an `aria-selected` attribute, and writes the URL fragment. It creates no element, sets no text, reads no storage, fetches nothing. Spec §3.
- **The page hides nothing before the script runs.** No `hidden` attribute, no inline `display`, and every rule that hides a panel is scoped under the root class the script adds. Spec §6.
- **Every finding reaches the page exactly once**, as a card with an `<h3>` heading. A Summary pointer is a link to that card and uses no `<h3>`.
- **No total row.** No numeric field joins the view model that is not on the invariants test's allowlist; every seconds figure stays a pre-formatted string on `LedgerRow.seconds`.
- **A withheld section keeps its heading and states its reason**, taken from the finding, never written by the template.
- **The LLM never computes a number.** Every metric comes from tested Python.
- **Never invent a Warcraft Logs field name.** This plan queries nothing new.
- **English** in code, comments, error strings, and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains **why**.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- Every file starts with two `# ABOUTME: ` comment lines (`{# ABOUTME: #}` in the template). Empty `__init__.py` markers are exempt.
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument). Ruff's line length is 100.
- **Comments are evergreen.** No "new", "now", "recently", "fixed" in code comments. Amendment notes with dates belong in the design documents, not in code.
- **Never remove a code comment** unless it is now false. Update it instead.
- **Every existing test that a task breaks is updated by that task**, with the reason in the commit body. No test is deleted; a test that pins behaviour this plan deliberately changes is rewritten to pin the amended behaviour. The tests named in each task are the ones known to break; if another breaks, fix it in the same task and say so.
- **The golden file** `tests/adapters/render/golden/minimal.html` is regenerated with `uv run pytest tests/adapters/render/test_html_invariants.py --golden-update` and its diff **read in full** before the commit that carries it. Tasks 2, 3 and 4 each regenerate it.
- **Git in this worktree.** The session's tool hook refuses a bare `git` inside a worktree, and refuses any command that names git twice. Call the executable by its path, `/cmd/git.exe`, and issue one git invocation per command. Stage files **by name**, never `git add -A`. Never `git stash`: the stash stack is shared with the main checkout.
- **For the controller:** never stage or commit anything while an implementer subagent is running; its `git add` would sweep your files into its commit.

## The real run is the acceptance test

Report `6Kx1P9GbNXrcLdHa` fight 36 (Den of Nalorakk +16) is what showed the page needs tabs. Task 5 regenerates it and walks the browser check in spec §7.5. The main checkout's root `cache/` may have been deleted before this plan runs; a cold run costs roughly twenty-five of the hourly 3600 points, and `analyze` prints what it spent.

---

### Task 1: Amend the documents the design supersedes

**Files:**
- Modify: `docs/plans/2026-09-05-mplus-report-design.md` (§4 after the `Report` sketch, §5 after its amendments, §9, §10, §11)
- Modify: `docs/plans/2026-09-03-mplus-postmortem-design.md` §7 (after "Dark by default.")

**Interfaces:**
- Consumes: `docs/plans/2026-09-06-report-tabs-design.md` §2, §4, §6, §7.
- Produces: nothing code-facing. Later tasks cite these amendments in commit bodies.

No test covers prose. The check is `uv run pytest tests/test_skills.py -q` still passing (it reads the skills, which this task does not touch) and a read-through of each amendment against the spec section it cites.

- [ ] **Step 0: Report design §1** — in the first paragraph, replace `No content delivery network, no external font, no `<script>`.` with:

```markdown
No content delivery network, no external font, and one inline `<script>` that only shows and
hides (*amended 2026-09-06*, see §9 and `2026-09-06-report-tabs-design.md` §3).
```

- [ ] **Step 1: Report design §4** — after the closing ``` of the `Report` code block (the line before `## 5. The eight sections`), insert:

```markdown
*Amended 2026-09-06:* `ledger_losses` is gone. `Report` carries `summary_pointers`, `route`,
`route_rows`, `death_rows` (formerly `death_findings`) and `group_rows` instead, all tuples of
`LedgerRow` except `route`, a `Section`. Every ranked loss lives on the tab that owns its family
and keeps its seconds there; the Summary points at the biggest five. See
`2026-09-06-report-tabs-design.md` §4 and §5.
```

- [ ] **Step 2: Report design §5** — after the paragraph beginning "Section 2 is the one exception", insert:

```markdown
*Amended 2026-09-06:* the sections are grouped under six tabs — Summary, Route & tempo, Deaths,
Interrupts, Players, Provenance — and a tenth section, "Route and tempo", holds the route, gap,
downtime, trash and confound findings that the ledger of losses used to rank on one list. The
Summary's "Biggest losses" heading appears only when a timed loss exists. Which section sits
under which tab is fixed in `2026-09-06-report-tabs-design.md` §2; the heading count in §10 is
superseded by that document's §7.1.
```

- [ ] **Step 3: Report design §9** — replace the bullet beginning "**Self-containment is a hard rule**" with:

```markdown
- **Self-containment is a hard rule**: no `src` or `href` to any external origin, no webfont, and
  exactly one `<script>` — inline, with no `src`, and restricted to showing and hiding sections.
  System font stack only. §10 tests this directly rather than trusting it. *Amended 2026-09-06:*
  this bullet said "no `<script>`" until the report grew to sixty-seven cards; see
  `2026-09-06-report-tabs-design.md` §1 and §3 for the script's four duties and its no-script
  fallback.
```

- [ ] **Step 4: Report design §10** — replace the bullet beginning "- no `<script>` element" with:

```markdown
- exactly one `<script>` element, inline, and its text free of anything that fetches, writes
  text or reads storage; no `src` or `href` whose value is not a fragment or a Warcraft Logs
  report link (*amended 2026-09-06*, see `2026-09-06-report-tabs-design.md` §7.1);
- the rendered page hides nothing before the script runs, every Summary pointer targets an
  anchor that exists, and every finding family lands on the tab the builder's table says
  (*added 2026-09-06*, ibid. §7.2);
```

- [ ] **Step 5: Report design §11** — replace the whole section body with:

```markdown
~~No table of contents, no print stylesheet, no interactivity, no collapsible sections, no theme
toggle, no chart library, no pagination. If the report ever needs navigation, that is evidence it
has grown too long, and the answer is to cut it rather than to add a contents list.~~

*Superseded 2026-09-06.* The first real run rendered sixty-seven cards that different readers
need different parts of, and cutting would remove something one of them came for. The page is
grouped under six tabs by `2026-09-06-report-tabs-design.md`, whose §1 restates the rule this
section was protecting: "the template decides nothing" is about judgement, and navigation is not
judgement. Still out of scope: a print stylesheet, a theme toggle, a chart library, pagination,
collapsible cards, and storing the chosen tab anywhere but the URL fragment.
```

- [ ] **Step 6: Postmortem design §7** — after the paragraph "Dark by default. …", insert:

```markdown
*Amended 2026-09-06:* the eight sections are grouped under six tabs, driven by one inline script
that only shows and hides, with every section visible when scripting is off. The rule and its
reasons live in `2026-09-06-report-tabs-design.md`.
```

- [ ] **Step 7: Read each amendment once against the spec section it cites.** Fix any sentence that promises something the spec does not.

- [ ] **Step 8: Run the gate's prose-adjacent test**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q`
Expected: all pass (nothing in the skills changed).

- [ ] **Step 9: Commit**

```
/cmd/git.exe add docs/plans/2026-09-05-mplus-report-design.md docs/plans/2026-09-03-mplus-postmortem-design.md
```
```
/cmd/git.exe commit -m "Amend the report design for tabs and retire its refusal of navigation" -m "The report design's §11 said a report needing navigation had grown too long and should be cut. The first real run rendered sixty-seven cards that different readers need different parts of, so the 2026-09-06 tabs design supersedes §11 and amends §4, §5, §9 and §10. Writing the amendments before the code keeps the design documents the authority the implementer reads, not a record written after the fact."
```

---

### Task 2: Home every finding family on its tab

**Files:**
- Modify: `src/wowperf/domain/report/model.py:174-188` (`Report`)
- Modify: `src/wowperf/domain/report/build.py` (`build_interrupts`, `DEATH_FINDING_PREFIXES`, `build_death_findings`, `_placed_finding_ids`, `build_report`)
- Modify: `src/wowperf/adapters/render/report.html.j2` (ledger, a new route section, deaths, players)
- Modify: `tests/domain/report/test_build_ledger.py`, `tests/domain/report/test_build_observations.py`, `tests/domain/report/test_build_deaths.py:293-320`, `tests/domain/report/test_model.py:74-95`, `tests/adapters/render/test_html.py:33-55,104-122`, `tests/adapters/render/test_html_invariants.py` (`SECTION_ORDER`, the two count tests), `tests/adapters/render/golden/minimal.html`
- Create: `tests/domain/report/test_build_placement.py`

**Interfaces:**
- Consumes: `LedgerRow`, `Section`, `_ledger_row`, `_section_for`, `SPEED_UNAVAILABLE_ID`, `PARSE_UNAVAILABLE_ID`, `DECOMPOSITION_IDS` — all already in `build.py`.
- Produces: `Report.route: Section`, `Report.route_rows`, `Report.death_rows`, `Report.group_rows`, all `tuple[LedgerRow, ...]`; `Report.interrupts` now holds timed rows too; `Report.ledger_losses` and `Report.death_findings` no longer exist. `PLACEMENTS: tuple[tuple[str, str], ...]` and `place_rows(findings, titles_by_id, exclude) -> dict[str, tuple[LedgerRow, ...]]` in `build.py`. A heading `<h2 id="route">Route and tempo</h2>` between the timeline and the deaths. Task 3 builds on the field names exactly as spelled here.

The two functions this replaces, `build_interrupts` and `build_death_findings`, are prefix filters over the same findings; the table generalises them. Removing them is the design's restructuring, not a rewrite of working code on the implementer's initiative, and the commit body says so.

- [ ] **Step 1: Write the failing placement tests**

Create `tests/domain/report/test_build_placement.py`:

```python
# ABOUTME: Behaviour tests for the placement table: every finding family lands on one tab's rows.
# ABOUTME: Order in the table is the rule — the narrow death families precede the bare prefixes.

from collections.abc import Sequence

import pytest

from tests.domain.report.test_build_frame import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES, a_run
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import PLACEMENTS, build_report, place_rows
from wowperf.domain.report.model import LedgerRow, Report

SUBJECT = Player(actor_id=1, name="Uglymage", class_name="Mage", spec="Arcane", item_level=680)


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    # The title never starts with "<player> took ", so build_players never claims it.
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
    )


def a_loaded() -> LoadedRun:
    return LoadedRun(run=a_run(players=(SUBJECT,)))


def a_report_of(*findings: Finding) -> Report:
    return build_report(
        a_loaded(), findings, None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES
    )


def ids(rows: Sequence[LedgerRow]) -> list[str]:
    return [row.finding_id for row in rows]


# One representative id per family the analysers and comparisons emit today, and the
# field the design's table (spec §5.1) sends it to. `deaths.total`, `time.residual` and
# `compare.duration` are decomposition rows and are tested separately below.
FAMILY_HOMES = {
    "time.gap.0": "route_rows",
    "compare.downtime": "route_rows",
    "compare.route.skipped.0": "route_rows",
    "compare.route.extra.0": "route_rows",
    "compare.route.summary": "route_rows",
    "compare.route.order": "route_rows",
    "compare.route.unaligned": "route_rows",
    "compare.speed.unavailable": "route_rows",
    "trash.overage": "route_rows",
    "trash.pull.0": "route_rows",
    "compare.confound.affixes": "route_rows",
    "deaths.single.0": "death_rows",
    "deaths.chain.0": "death_rows",
    "deaths.repeat.Uglymage": "death_rows",
    "defensives.unused.45438": "death_rows",
    "consumables.unused.6262": "death_rows",
    "consumables.never.6262": "death_rows",
    "compare.deaths": "death_rows",
    "interrupts.ability.0": "interrupts",
    "interrupts.summary": "interrupts",
    "compare.interrupts": "interrupts",
    "compare.parse.unavailable": "group_rows",
    "defensives.Uglymage.45438": "group_rows",
    "defensives.ceiling.45438": "group_rows",
    "throughput.alignment.12345": "group_rows",
    "throughput.ceiling.12345": "group_rows",
}

ROW_FIELDS = ("route_rows", "death_rows", "interrupts", "group_rows")


@pytest.mark.parametrize(("finding_id", "home"), sorted(FAMILY_HOMES.items()))
def test_each_family_lands_on_the_field_the_table_says(finding_id: str, home: str) -> None:
    report = a_report_of(a_finding(finding_id))
    assert ids(getattr(report, home)) == [finding_id]
    for other in ROW_FIELDS:
        if other != home:
            assert ids(getattr(report, other)) == [], other
    assert report.observations == ()


def test_a_family_the_table_does_not_know_reaches_the_catch_all() -> None:
    report = a_report_of(a_finding("healing.overheal.0"))
    assert ids(report.observations) == ["healing.overheal.0"]
    for field in ROW_FIELDS:
        assert ids(getattr(report, field)) == [], field


def test_a_timed_row_keeps_its_seconds_where_it_lands() -> None:
    # There is no page-wide list of losses any more; a gap is a route row with its cost.
    report = a_report_of(a_finding("time.gap.0", seconds=41.0))
    assert ids(report.route_rows) == ["time.gap.0"]
    assert report.route_rows[0].seconds == "0:41"


def test_a_timed_death_family_finding_lands_once_beneath_the_deaths() -> None:
    # Before the table, a death-family finding carrying seconds went to the ledger of
    # losses alone. It now stays with the deaths, with its seconds, and nowhere else.
    report = a_report_of(a_finding("defensives.unused.45438", seconds=12.0))
    assert ids(report.death_rows) == ["defensives.unused.45438"]
    assert report.death_rows[0].seconds == "0:12"
    assert report.observations == ()


def test_a_decomposition_row_is_never_placed_twice() -> None:
    # `deaths.total` matches the `deaths.` prefix, but a timed one heads the ledger and
    # must not also appear beneath the death cards.
    report = a_report_of(a_finding("deaths.total", seconds=64.0))
    assert ids(report.ledger_decomposition) == ["deaths.total"]
    assert report.death_rows == ()


def test_a_decomposition_id_without_seconds_falls_through_to_its_family() -> None:
    # A withheld `deaths.total` (no honest seconds) is still about deaths, and the Deaths
    # tab is where its reason belongs — not the catch-all.
    report = a_report_of(a_finding("deaths.total"))
    assert report.ledger_decomposition == ()
    assert ids(report.death_rows) == ["deaths.total"]


def test_rows_keep_the_order_they_arrived_in() -> None:
    # `rank_findings` already ordered them; placement must not re-sort.
    report = a_report_of(a_finding("time.gap.0", 90.0), a_finding("compare.downtime", 40.0))
    assert ids(report.route_rows) == ["time.gap.0", "compare.downtime"]


def test_the_narrow_death_families_precede_the_bare_defensives_prefix() -> None:
    # The table overlaps on purpose and resolves by order. If someone sorts it, this fails.
    prefixes = [prefix for prefix, _ in PLACEMENTS]
    assert prefixes.index("defensives.unused.") < prefixes.index("defensives.")


def test_place_rows_excludes_what_it_is_told_to() -> None:
    rows = place_rows(
        (a_finding("time.gap.0"), a_finding("time.gap.1")), {}, exclude={"time.gap.0"}
    )
    assert ids(rows["route_rows"]) == ["time.gap.1"]


def test_the_route_section_is_withheld_without_a_speed_reference() -> None:
    report = a_report_of(
        Finding(
            id="compare.speed.unavailable",
            title="No speed reference",
            detail="No timed run of this dungeon at this level was found.",
            confidence=Confidence.MEASURED,
        )
    )
    assert report.route.state.value == "withheld"
    assert report.route.reason == "No timed run of this dungeon at this level was found."
    # The finding itself still reaches the page once, on the tab it explains.
    assert ids(report.route_rows) == ["compare.speed.unavailable"]


def test_a_withheld_route_is_listed_under_provenance() -> None:
    report = a_report_of()
    assert any(line.startswith("Route and tempo: ") for line in report.provenance.withheld)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_placement.py -q`
Expected: FAIL at import — `PLACEMENTS` and `place_rows` do not exist.

- [ ] **Step 3: Change the view model**

In `src/wowperf/domain/report/model.py`, replace the `Report` class with:

```python
class Report(Frozen):
    header: Header
    narrative: str | None
    ledger_decomposition: tuple[LedgerRow, ...]
    timeline: Timeline
    # Withheld without a speed reference, with the reason the timeline reads too. The
    # rows beneath it that need no reference — gaps, trash — still render.
    route: Section
    # Gaps, downtime, the route comparison, trash and confounds: what the route cost.
    route_rows: tuple[LedgerRow, ...] = ()
    deaths: tuple[DeathCard, ...]
    # The death costs and what a dying player still had, beneath the death cards.
    death_rows: tuple[LedgerRow, ...] = ()
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    # Per-player rate rows — defensive and throughput — beneath the player cards.
    group_rows: tuple[LedgerRow, ...] = ()
    # Every finding no field above claimed — a structural catch-all, not a
    # whitelist of its own. See `build_observations`.
    observations: tuple[LedgerRow, ...]
    provenance: Provenance
```

- [ ] **Step 4: Replace the two prefix filters with the placement table**

In `src/wowperf/domain/report/build.py`, delete `build_interrupts`, `DEATH_FINDING_PREFIXES` with its docstring, and `build_death_findings`. In their place (after `_plural`), add:

```python
PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("defensives.unused.", "death_rows"),
    ("consumables.", "death_rows"),
    ("deaths.", "death_rows"),
    ("compare.deaths", "death_rows"),
    ("time.gap.", "route_rows"),
    ("compare.downtime", "route_rows"),
    ("compare.route.", "route_rows"),
    (SPEED_UNAVAILABLE_ID, "route_rows"),
    ("trash.", "route_rows"),
    ("compare.confound.", "route_rows"),
    ("interrupts.", "interrupts"),
    ("compare.interrupts", "interrupts"),
    (PARSE_UNAVAILABLE_ID, "group_rows"),
    ("defensives.", "group_rows"),
    ("throughput.", "group_rows"),
)
"""Which tab's rows a finding family lands in: the first prefix that matches wins.

Unlike `NESTS_INSIDE`, the entries here overlap on purpose — `defensives.unused.`
is a death-shaped claim and the bare `defensives.` prefix is a rate — so order is
the rule and the narrow families come first. A finding no prefix matches is not
dropped: `build_observations` picks up everything unplaced. The player-card
families (`players.damage.`, `compare.spells.`, `compare.talents`,
`compare.uptime.`) are placed by `build_players` and are deliberately absent.
"""


def _field_for(finding_id: str) -> str | None:
    return next((field for prefix, field in PLACEMENTS if finding_id.startswith(prefix)), None)


def place_rows(
    findings: Sequence[Finding], titles_by_id: dict[str, str], exclude: set[str]
) -> dict[str, tuple[LedgerRow, ...]]:
    """Every finding's row, keyed by the `Report` field it lands in.

    `exclude` holds the ids the decomposition already claimed, so a timed
    `deaths.total` heads the ledger and does not also sit beneath the death
    cards. Order within a field is the order the findings arrived in:
    `rank_findings` has already sorted them, and one ranking authority is enough.
    """
    placed: dict[str, list[LedgerRow]] = {field: [] for _, field in PLACEMENTS}
    for finding in findings:
        if finding.id in exclude:
            continue
        field = _field_for(finding.id)
        if field is not None:
            placed[field].append(_ledger_row(finding, titles_by_id))
    return {field: tuple(rows) for field, rows in placed.items()}
```

Replace `_placed_finding_ids` with:

```python
def _placed_finding_ids(
    ledger_decomposition: Sequence[LedgerRow],
    placed_rows: dict[str, tuple[LedgerRow, ...]],
    players: Sequence[PlayerCard],
) -> set[str]:
    """Every finding id some field already claims.

    Read back off the fields themselves rather than recomputed from a prefix
    list: this is what keeps `build_observations` a structural partition
    instead of a second whitelist someone has to remember to update.
    """
    ids = {row.finding_id for row in ledger_decomposition}
    for rows in placed_rows.values():
        ids |= {row.finding_id for row in rows}
    for card in players:
        ids |= {row.finding_id for row in card.damage_rows}
        ids |= {row.finding_id for row in card.spell_and_talent_rows}
    return ids
```

In `build_report`, replace everything from `titles_by_id = ...` down to the `return Report(` block's start with:

```python
    route_section = _section_for(findings, SPEED_UNAVAILABLE_ID, speed is not None)
    if route_section.state is SectionState.WITHHELD:
        withheld.append(f"Route and tempo: {route_section.reason}")

    titles_by_id = {finding.id: finding.title for finding in findings}

    ledger_decomposition = tuple(
        _ledger_row(finding, titles_by_id)
        for finding in findings
        if finding.seconds_lost is not None and finding.id in DECOMPOSITION_IDS
    )
    placed_rows = place_rows(
        findings, titles_by_id, exclude={row.finding_id for row in ledger_decomposition}
    )
    players = build_players(loaded, findings, parse, subject, titles_by_id)
    placed_ids = _placed_finding_ids(ledger_decomposition, placed_rows, players)
```

and the `Report(...)` construction with:

```python
    return Report(
        header=_header(loaded),
        narrative=narrative,
        ledger_decomposition=ledger_decomposition,
        timeline=build_timeline(
            loaded.run, speed.loaded.run if speed else None, timeline_section
        ),
        route=route_section,
        route_rows=placed_rows["route_rows"],
        deaths=build_deaths(loaded, defensives, consumables),
        death_rows=placed_rows["death_rows"],
        interrupts=placed_rows["interrupts"],
        players=players,
        group_rows=placed_rows["group_rows"],
        observations=build_observations(findings, placed_ids, titles_by_id),
        provenance=Provenance(
            report_code=loaded.run.report_code,
            fight_id=loaded.run.fight_id,
            fetched_at=fetched_at,
            speed_reference_url=(
                _reference_url(speed.row.report_code, speed.row.fight_id) if speed else None
            ),
            parse_reference_url=(
                _reference_url(parse.row.report_code, parse.row.fight_id) if parse else None
            ),
            withheld=tuple(withheld),
        ),
    )
```

The `withheld` list must be built in this order: timeline, comparison, route — the existing two `if ... WITHHELD` blocks stay where they are and the route block goes after them.

- [ ] **Step 5: Run the placement tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_placement.py -q`
Expected: all pass.

- [ ] **Step 6: Regroup the template**

In `src/wowperf/adapters/render/report.html.j2`:

Replace the block from `<h2 id="ledger">Where the time went</h2>` to the `{% endif %}` after the `ledger_losses` loop with:

```html
<h2 id="ledger">Where the time went</h2>
<p class="sub">Not additive — every figure below can already contain another, so they must
never be summed.</p>
{% for row in report.ledger_decomposition %}
{{ ledger_row(row) }}
{% endfor %}
```

After the timeline's closing `{% endif %}` and before `<h2 id="deaths">Deaths</h2>`, insert. Note that `report.route` is the `Section` itself, unlike `report.timeline.section`:

```html
<h2 id="route">Route and tempo</h2>
{% if report.route.state.value == "withheld" %}
<p class="withheld">{{ report.route.reason }}</p>
{% endif %}
{% if report.route_rows %}
<p class="sub">Not additive — every figure below can already contain another, so they must
never be summed.</p>
{% for row in report.route_rows %}
{{ ledger_row(row) }}
{% endfor %}
{% elif report.route.state.value != "withheld" %}
<p class="sub">Nothing to report.</p>
{% endif %}
```

Replace the `{% for row in report.death_findings %}` loop with:

```html
{% if report.death_rows %}
<p class="sub">Not additive — every figure below can already contain another, so they must
never be summed.</p>
{% for row in report.death_rows %}
{{ ledger_row(row) }}
{% endfor %}
{% endif %}
```

After the players' `{% endfor %}` and before `<h2 id="observations">`, insert:

```html
{% if report.group_rows %}
<p class="sub">Group. Per-player rates, until each finds its player.</p>
{% for row in report.group_rows %}
{{ ledger_row(row) }}
{% endfor %}
{% endif %}
```

Update the template's second ABOUTME line to name the route section:
`{# ABOUTME: route, deaths, interrupts, players and provenance — one self-contained file, no script or fetch. #}`

- [ ] **Step 7: Update the tests that pinned the old fields**

`tests/domain/report/test_build_ledger.py`: every `report.ledger_losses` becomes `report.route_rows` (all nine occurrences use `time.gap.0`, `compare.downtime` or `trash.overage`, which are route families). Rename `test_a_ranked_loss_goes_to_the_losses` to `test_a_ranked_loss_goes_to_the_tab_that_owns_its_family`. In `test_a_finding_with_no_seconds_never_reaches_the_ledger`, replace `assert ids(report.ledger_losses) == []` with `assert ids(report.route_rows) == []`. Update the file's first ABOUTME line to `# ABOUTME: Behaviour tests for the seconds ledger: decomposition rows, nesting stated, never a total.`

`tests/domain/report/test_build_observations.py`:
- `test_a_finding_no_section_claims_reaches_observations`: both ids now have homes. Replace the two findings with `a_finding("healing.overheal.0", title="Uglymage overhealed by 40%")` and `a_finding("dispels.missed.0", title="Two curses went undispelled")`, update the comment to say these match no prefix in `PLACEMENTS`, and assert `["healing.overheal.0", "dispels.missed.0"]`.
- `test_every_input_finding_is_placed_exactly_once`: replace the `placed_ids` collection with

```python
    placed_ids: list[str] = []
    placed_ids += [row.finding_id for row in report.ledger_decomposition]
    placed_ids += [row.finding_id for row in report.route_rows]
    placed_ids += [row.finding_id for row in report.death_rows]
    placed_ids += [row.finding_id for row in report.interrupts]
    for card in report.players:
        placed_ids += [row.finding_id for row in card.damage_rows]
        placed_ids += [row.finding_id for row in card.spell_and_talent_rows]
    placed_ids += [row.finding_id for row in report.group_rows]
    placed_ids += [row.finding_id for row in report.observations]
```

  and add one unknown-family finding, `a_finding("healing.overheal.0", title="Uglymage overhealed")`, to its input so the catch-all is exercised.
- `test_a_death_family_finding_carrying_seconds_goes_to_the_ledger_alone`: rename to `test_a_death_family_finding_carrying_seconds_stays_beneath_the_deaths`, keep the docstring's first line and replace the rest with "A timed row keeps its seconds where its family lives; there is no separate list of losses for it to appear in twice.", and assert `[row.finding_id for row in report.death_rows] == ["defensives.unused.0"]`, `report.death_rows[0].seconds == "0:12"`, `report.observations == ()`.

`tests/domain/report/test_build_deaths.py:293-320`: `report.death_findings` becomes `report.death_rows`; the last assertion becomes `assert [row.finding_id for row in report.route_rows] == ["trash.pull.0"]` and `assert report.observations == ()`.

`tests/domain/report/test_model.py`, `test_a_report_holds_every_section`: replace `ledger_losses=(),` with `route=a_section(SectionState.WITHHELD, "no reference"),` and add `assert report.route.state is SectionState.WITHHELD`.

`tests/adapters/render/test_html.py`: in `a_report`, replace `"ledger_losses": (),` with `"route": Section(state=SectionState.PRESENT),`. In the three tests that pass `ledger_losses=(a_row(...),)`, pass `route_rows=` instead.

`tests/adapters/render/test_html_invariants.py`: `SECTION_ORDER` becomes

```python
SECTION_ORDER = [
    "ledger", "timeline", "route", "deaths", "interrupts", "players", "observations",
    "provenance",
]
```

Rename `test_a_report_without_a_narrative_renders_eight_sections_not_nine` to `test_a_report_without_a_narrative_renders_one_heading_per_section` and `test_a_report_with_a_narrative_renders_nine_sections_not_eight` to `test_a_narrative_adds_exactly_one_heading`; their bodies already count against `len(SECTION_ORDER)`. Update the comments inside them from "seven always-present" to "the always-present".

- [ ] **Step 8: Add a render test for the route section**

Append to `tests/adapters/render/test_html_sections.py`:

```python
def test_route_rows_render_inside_the_route_section() -> None:
    html = render(build_report(a_loaded(), (
        a_finding("time.gap.0", seconds=41.0, title="A 41 second gap after pull 0"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    route_start = html.index('<h2 id="route">')
    deaths_start = html.index('<h2 id="deaths">')
    title_at = html.index("A 41 second gap after pull 0")
    assert route_start < title_at < deaths_start


def test_a_withheld_route_states_its_reason_and_still_shows_the_gaps() -> None:
    # Without a speed reference the comparison is withheld, but a gap between our
    # own pulls needs no reference and must not disappear with it.
    html = render(build_report(a_loaded(), (
        a_finding("time.gap.0", seconds=41.0, title="A 41 second gap after pull 0"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    route = html[html.index('<h2 id="route">'):html.index('<h2 id="deaths">')]
    assert 'class="withheld"' in route
    assert "A 41 second gap after pull 0" in route


def test_group_rows_render_inside_the_players_section() -> None:
    html = render(build_report(a_loaded(), (
        a_finding("throughput.alignment.1", title="Uglymage had a cooldown ready and unpressed"),
    ), None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES, NO_CONSUMABLES))
    players_start = html.index('<h2 id="players">')
    observations_start = html.index('<h2 id="observations">')
    title_at = html.index("Uglymage had a cooldown ready and unpressed")
    assert players_start < title_at < observations_start
```

`a_finding` in that file comes from `test_build_observations` and accepts `seconds=`.

- [ ] **Step 9: Regenerate the golden file and read the diff**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update -q`
Then: `/cmd/git.exe diff tests/adapters/render/golden/minimal.html`
Expected in the diff: the gap and interrupt rows leave "Where the time went" and appear under the new "Route and tempo" heading and the existing "Interrupts" heading; the withheld route reason appears; nothing else moves. Anything else is a defect to fix before committing.

- [ ] **Step 10: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 11: Commit**

```
/cmd/git.exe add src/wowperf/domain/report/model.py src/wowperf/domain/report/build.py src/wowperf/adapters/render/report.html.j2 tests/domain/report/test_build_placement.py tests/domain/report/test_build_ledger.py tests/domain/report/test_build_observations.py tests/domain/report/test_build_deaths.py tests/domain/report/test_model.py tests/adapters/render/test_html.py tests/adapters/render/test_html_sections.py tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/minimal.html
```
```
/cmd/git.exe commit -m "Home every finding family on the tab that owns it" -m "The ledger of ranked losses put a skipped pack, a gap and a death cost on one list because that was the only list. With the page about to split into tabs, each family needs one home, and one ordered table is easier to hold in the head than two prefix filters plus a catch-all. build_interrupts and build_death_findings were that pair; the table generalises them (tabs design 2026-09-06, §5.1). A timed death-family finding stays beneath the deaths with its seconds instead of jumping to a separate list, which is the one behaviour this changes on purpose; the test that pinned the old behaviour now pins this one."
```

---

### Task 3: Point the Summary at the biggest losses

**Files:**
- Modify: `src/wowperf/domain/report/model.py` (`Report.summary_pointers`)
- Modify: `src/wowperf/domain/report/build.py` (`POINTER_COUNT`, `build_summary_pointers`, `build_report`)
- Modify: `src/wowperf/adapters/render/report.html.j2` (anchor on cards, pointer macro, "Biggest losses" section)
- Modify: `tests/domain/report/test_model.py:74-95`, `tests/adapters/render/test_html.py:33-55`, `tests/adapters/render/test_html_invariants.py` (`SECTION_ORDER`, new tests), `tests/adapters/render/golden/minimal.html`
- Create: `tests/domain/report/test_build_pointers.py`

**Interfaces:**
- Consumes: `Report` fields from Task 2; `_ledger_row`, `DECOMPOSITION_IDS`, `format_seconds`.
- Produces: `Report.summary_pointers: tuple[LedgerRow, ...]`; `build_summary_pointers(findings, titles_by_id, exclude) -> tuple[LedgerRow, ...]`; `POINTER_COUNT = 5`; every card rendered by the `ledger_row` macro carries `id="finding-<finding_id>"`; a `<h2 id="losses">Biggest losses</h2>` heading rendered only when pointers exist; a `pointer` macro. Task 4 wraps the "losses" heading in the Summary panel.

- [ ] **Step 1: Write the failing builder tests**

Create `tests/domain/report/test_build_pointers.py`:

```python
# ABOUTME: Behaviour tests for the Summary's pointers: the biggest timed losses, in the order
# ABOUTME: rank_findings already gave them, never a decomposition row, never re-sorted.

from collections.abc import Sequence

from tests.domain.report.test_build_frame import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES, a_run
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import POINTER_COUNT, build_report
from wowperf.domain.report.model import LedgerRow, Report

SUBJECT = Player(actor_id=1, name="Uglymage", class_name="Mage", spec="Arcane", item_level=680)


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.MEASURED,
        seconds_lost=seconds,
    )


def a_report_of(*findings: Finding) -> Report:
    return build_report(
        LoadedRun(run=a_run(players=(SUBJECT,))), findings, None, None, SUBJECT, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )


def ids(rows: Sequence[LedgerRow]) -> list[str]:
    return [row.finding_id for row in rows]


def test_pointers_are_the_timed_findings_in_the_order_they_arrived() -> None:
    report = a_report_of(a_finding("time.gap.0", 90.0), a_finding("compare.downtime", 40.0))
    assert ids(report.summary_pointers) == ["time.gap.0", "compare.downtime"]


def test_pointers_stop_at_the_count_the_builder_fixes() -> None:
    findings = tuple(a_finding(f"time.gap.{i}", 100.0 - i) for i in range(POINTER_COUNT + 2))
    report = a_report_of(*findings)
    assert len(report.summary_pointers) == POINTER_COUNT
    assert ids(report.summary_pointers) == [f"time.gap.{i}" for i in range(POINTER_COUNT)]


def test_a_decomposition_row_is_never_a_pointer() -> None:
    # It already heads the ledger on the same tab; pointing at it would say it twice.
    report = a_report_of(a_finding("time.residual", 300.0), a_finding("time.gap.0", 41.0))
    assert ids(report.summary_pointers) == ["time.gap.0"]


def test_an_untimed_finding_is_never_a_pointer() -> None:
    report = a_report_of(a_finding("interrupts.summary"), a_finding("time.gap.0", 41.0))
    assert ids(report.summary_pointers) == ["time.gap.0"]


def test_no_timed_loss_means_no_pointers() -> None:
    report = a_report_of(a_finding("interrupts.summary"))
    assert report.summary_pointers == ()


def test_a_pointer_equals_the_card_it_points_at() -> None:
    # Same title, seconds and badge, by construction from the same finding.
    report = a_report_of(a_finding("time.gap.0", 41.0, title="A 41 second gap"))
    assert report.summary_pointers == (report.route_rows[0],)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_pointers.py -q`
Expected: FAIL at import — `POINTER_COUNT` does not exist.

- [ ] **Step 3: Add the field and the builder**

In `model.py`, insert into `Report` after `ledger_decomposition`:

```python
    # The biggest timed losses, in the order the findings arrived. Each equals its
    # card on another tab; the Summary renders it as a link to that card, never as
    # a second card.
    summary_pointers: tuple[LedgerRow, ...] = ()
```

In `build.py`, after `place_rows`, add:

```python
POINTER_COUNT = 5
"""How many losses the Summary points at: enough to show the run's shape, few enough to stay a list."""


def build_summary_pointers(
    findings: Sequence[Finding], titles_by_id: dict[str, str], exclude: set[str]
) -> tuple[LedgerRow, ...]:
    """The first timed findings that are not decomposition rows, in the order given.

    `rank_findings` has already sorted the findings by seconds, descending, in
    the CLI. Re-sorting here would be a second ranking authority that could
    disagree with the findings file; taking the first few in order cannot.
    """
    timed = [
        finding
        for finding in findings
        if finding.seconds_lost is not None and finding.id not in exclude
    ]
    return tuple(_ledger_row(finding, titles_by_id) for finding in timed[:POINTER_COUNT])
```

In `build_report`, after `placed_rows = place_rows(...)`, add:

```python
    decomposition_ids = {row.finding_id for row in ledger_decomposition}
    summary_pointers = build_summary_pointers(findings, titles_by_id, exclude=decomposition_ids)
```

and reuse `decomposition_ids` in the `place_rows` call (`exclude=decomposition_ids`), computing it before that call. Pass `summary_pointers=summary_pointers,` to `Report(...)` right after `ledger_decomposition=`.

- [ ] **Step 4: Run the builder tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_build_pointers.py -q`
Expected: all pass.

- [ ] **Step 5: Write the failing render tests**

Append to `tests/adapters/render/test_html_invariants.py`:

```python
def test_every_pointer_targets_an_anchor_that_exists() -> None:
    html = minimal_html()
    targets = re.findall(r'class="pointer" href="#([^"]+)"', html)
    assert targets, "the minimal fixture has a timed loss, so the Summary must point at it"
    for target in targets:
        assert f'id="{target}"' in html, target


def test_a_pointer_is_a_link_not_a_second_card() -> None:
    # Once-only is anchored on <h3>; a pointer that emitted one would double every loss.
    html = minimal_html()
    pointers = re.findall(r'<a class="pointer"[^>]*>(.*?)</a>', html, flags=re.S)
    assert pointers
    for body in pointers:
        assert "<h3>" not in body
    # Every finding still appears exactly once as a heading, pointers notwithstanding.
    for finding in minimal_findings():
        assert html.count(f"<h3>{escape(finding.title)}</h3>") == 1, finding.id


def test_the_losses_heading_is_absent_when_nothing_was_timed() -> None:
    untimed = tuple(f for f in minimal_findings() if f.seconds_lost is None)
    html = render(
        build_report(
            minimal_loaded(), untimed, None, None, SUBJECT, None, FETCHED, NO_DEFENSIVES,
            NO_CONSUMABLES,
        )
    )
    assert 'id="losses"' not in html
```

Update `SECTION_ORDER` to include `"losses"` after `"ledger"` (the minimal fixture has timed findings, so the heading renders there). Add a comment above it: `# "losses" renders only when a timed loss exists; the minimal fixture has two.`

- [ ] **Step 6: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py -q`
Expected: the three new tests and the order test FAIL — no pointer, no anchor, no `losses` heading yet.

- [ ] **Step 7: Anchors, the pointer macro, and the section**

In `report.html.j2`:

In the `ledger_row` macro, change `<div class="card">` to `<div class="card" id="finding-{{ row.finding_id }}">`.

After the `ledger_row` macro's `{% endmacro %}`, add:

```html
{% macro pointer(row) %}
<a class="pointer" href="#finding-{{ row.finding_id }}">
  <span class="pointer-title">{{ row.title }}</span>
  <span class="cost">{{ row.seconds }}</span>
  <span class="badge {{ row.badge.tint }}">{{ row.badge.label }}</span>
</a>
{% endmacro %}
```

After the decomposition loop under "Where the time went", add:

```html
{% if report.summary_pointers %}
<h2 id="losses">Biggest losses</h2>
<p class="sub">Each line opens its card. Ranked, not additive.</p>
{% for row in report.summary_pointers %}
{{ pointer(row) }}
{% endfor %}
{% endif %}
```

Add to the `<style>` block, after `.nests`:

```css
.pointer { display: flex; align-items: baseline; gap: 10px; padding: 8px 14px; margin: 0 0 6px;
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  color: var(--ink); text-decoration: none; }
.pointer-title { flex: 1; }
```

- [ ] **Step 8: Update the fixtures**

`tests/domain/report/test_model.py`, `test_a_report_holds_every_section`: add `summary_pointers=(),` after `ledger_decomposition=(),`. `tests/adapters/render/test_html.py`, `a_report`: add `"summary_pointers": (),`.

- [ ] **Step 9: Regenerate the golden file and read the diff**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update -q`
Then: `/cmd/git.exe diff tests/adapters/render/golden/minimal.html`
Expected: every card gained an `id="finding-…"`; a "Biggest losses" heading with exactly one pointer line, for `time.gap.0` — the fixture's only other timed finding, `time.residual`, is a decomposition row; the two new CSS rules. Nothing else.

- [ ] **Step 10: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 11: Commit**

```
/cmd/git.exe add src/wowperf/domain/report/model.py src/wowperf/domain/report/build.py src/wowperf/adapters/render/report.html.j2 tests/domain/report/test_build_pointers.py tests/domain/report/test_model.py tests/adapters/render/test_html.py tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/minimal.html
```
```
/cmd/git.exe commit -m "Point the Summary at the five biggest losses instead of listing every one" -m "Once each loss lives on the tab that owns its family, the first tab has no ranked view unless it repeats cards, and every-finding-once forbids that. A pointer is one line — title, seconds, badge — linking to the card's anchor, built from the same finding so it cannot drift. The count is five and the order is the one rank_findings already fixed in the CLI; re-sorting here would be a second ranking authority (tabs design 2026-09-06, §5.2)."
```

---

### Task 4: The tab bar, the panels, and the script

**Files:**
- Modify: `src/wowperf/adapters/render/report.html.j2` (CSS, tab bar, panels, script, ABOUTME)
- Modify: `src/wowperf/adapters/render/html.py:31-34` (docstring)
- Modify: `tests/adapters/render/test_html_invariants.py` (`test_the_page_fetches_nothing_at_all`, `SECTION_ORDER`, the count tests; new tests), `tests/adapters/render/golden/minimal.html`
- Modify: `tests/test_cli.py:977-988` (`test_the_html_report_fetches_nothing_from_the_network`), `tests/e2e/test_report_e2e.py:93-99` (the same assertion, deselected by default — it must be updated even though the gate does not run it)
- Modify: `.claude/skills/mplus-analysis/SKILL.md` ("Reading the file", one paragraph)

**Interfaces:**
- Consumes: every heading id from Tasks 2 and 3; `Report` as it stands after Task 3.
- Produces: six `<section class="panel" data-tab-panel="main" id="tab-…">` elements with ids `tab-summary`, `tab-route`, `tab-deaths`, `tab-interrupts`, `tab-players`, `tab-provenance`; a `<nav class="tabs" data-tab-group="main">` of six `<button type="button" class="tab" data-tab-for="tab-…">`; the root class `js`; one inline `<script>`. Phase J adds a nested group by reusing the same attributes with another group name.

- [ ] **Step 1: Rewrite the self-containment invariant and write the failing structure tests**

In `tests/adapters/render/test_html_invariants.py`, replace `test_the_page_fetches_nothing_at_all` with:

```python
FORBIDDEN_IN_SCRIPT = (
    "fetch",
    "XMLHttpRequest",
    "import(",
    "document.write",
    "innerHTML",
    "textContent",
    "localStorage",
    "sessionStorage",
    "eval",
    "WebSocket",
)
"""What the script may not contain: anything that fetches, writes text or reads storage."""


def test_the_page_executes_only_its_own_script() -> None:
    # A Warcraft Logs reference-run link and the SVG's own namespace attribute
    # both legitimately contain "http://" without fetching anything, so
    # self-containment is checked by what the page can *execute* or *load*,
    # not by whether the string appears at all. One inline script is allowed,
    # and only one: the tab toggle. Its text is checked for anything that could
    # reach past showing and hiding.
    html = rich_html()
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.S | re.I)
    assert len(scripts) == 1
    attributes, body = scripts[0]
    assert "src=" not in attributes.lower()
    for forbidden in FORBIDDEN_IN_SCRIPT:
        assert forbidden not in body, forbidden
    assert "@import" not in html.lower()
    assert "<link rel=" not in html.lower()
    for src in re.findall(r'src="([^"]*)"', html, flags=re.IGNORECASE):
        assert not src.startswith(("http://", "https://", "//")), src


PANEL_ORDER = [
    "tab-summary", "tab-route", "tab-deaths", "tab-interrupts", "tab-players", "tab-provenance",
]


def test_the_page_hides_nothing_before_the_script_runs() -> None:
    # Without the script the root class is absent, so every hiding rule must be
    # scoped under it. The tab bar is the one thing hidden *without* the script,
    # by the bare `.tabs` rule, and that is checked by name.
    html = rich_html()
    assert not re.search(r"<[^>]*\shidden[\s>=]", html)
    assert not re.search(r'style="[^"]*display', html)
    style = html[html.index("<style>"):html.index("</style>")]
    for rule in re.finditer(r"([^{}]+)\{[^{}]*display:\s*none", style):
        selector = rule.group(1).strip().splitlines()[-1].strip()
        assert selector.startswith(".js ") or selector == ".tabs", selector


def test_every_panel_appears_once_in_tab_order() -> None:
    html = minimal_html()
    positions = [html.index(f'id="{name}"') for name in PANEL_ORDER]
    assert positions == sorted(positions)
    assert len(re.findall(r'<section class="panel"', html)) == len(PANEL_ORDER)


def test_every_panel_has_exactly_one_tab_button() -> None:
    html = minimal_html()
    for name in PANEL_ORDER:
        assert html.count(f'data-tab-for="{name}"') == 1, name


def test_the_root_class_the_script_adds_is_not_in_the_markup() -> None:
    # The script adds it at run time; rendering it would hide panels with no script.
    html = rich_html()
    assert '<html lang="en">' in html
    assert 'class="js' not in html
```

Update `SECTION_ORDER` to the document order the panels impose (observations moves to Summary):

```python
SECTION_ORDER = [
    "ledger", "losses", "timeline", "observations", "route", "deaths", "interrupts", "players",
    "provenance",
]
```

Two other tests mirror the old invariant and must move with it. In `tests/test_cli.py`, `test_the_html_report_fetches_nothing_from_the_network`: change the docstring's first line to say it mirrors `test_the_page_executes_only_its_own_script`, and replace `assert "<script" not in html.lower()` with:

```python
    scripts = re.findall(r"<script\b([^>]*)>", html, flags=re.I)
    assert len(scripts) == 1 and "src=" not in scripts[0].lower()
```

In `tests/e2e/test_report_e2e.py`, replace `assert "<script" not in html.lower()` with the same two lines and extend the comment above it: "One inline script is allowed — the tab toggle — and only one; its text is checked in `test_html_invariants.py`."

- [ ] **Step 2: Run them to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py tests/test_cli.py -q`
Expected: the panel tests and the order test FAIL; `test_the_page_executes_only_its_own_script` and the CLI mirror FAIL because no script exists yet (`len(scripts) == 0`). The e2e test is deselected and cannot be run without credentials; Task 5's real run exercises the same rendered page.

- [ ] **Step 3: Restructure the template**

In `report.html.j2`:

Add to `<style>` after the `.narrative` rule:

```css
.tabs { display: none; }
.js .tabs { display: flex; flex-wrap: wrap; gap: 2px; margin: 20px 0 0;
  border-bottom: 1px solid var(--line); }
.tab { background: none; border: 0; border-bottom: 2px solid transparent; color: var(--ink-dim);
  font: inherit; font-size: 14px; padding: 8px 12px; cursor: pointer; }
.tab.active { color: var(--ink); font-weight: 600; border-bottom-color: var(--ours); }
.js .panel:not(.active) { display: none; }
```

Immediately after the header's `<p class="sub">…</p>` line, insert the bar:

```html
<nav class="tabs" data-tab-group="main" aria-label="Sections">
  <button type="button" class="tab" data-tab-for="tab-summary">Summary</button>
  <button type="button" class="tab" data-tab-for="tab-route">Route &amp; tempo</button>
  <button type="button" class="tab" data-tab-for="tab-deaths">Deaths</button>
  <button type="button" class="tab" data-tab-for="tab-interrupts">Interrupts</button>
  <button type="button" class="tab" data-tab-for="tab-players">Players</button>
  <button type="button" class="tab" data-tab-for="tab-provenance">Provenance</button>
</nav>
```

Then wrap the sections in panels, in this document order. Move the "Other findings" block (heading, its `{% if %}` and its rows) up so it follows the timeline. Each panel is `<section class="panel" data-tab-panel="main" id="tab-…">` … `</section>`:

| Panel id | Contains, in order |
| --- | --- |
| `tab-summary` | narrative block; `ledger_row` macro definition may stay above the panels (macros render nothing); "Where the time went"; "Biggest losses"; "Aligned timeline"; "Other findings" |
| `tab-route` | "Route and tempo" |
| `tab-deaths` | "Deaths" with its cards and `death_rows` |
| `tab-interrupts` | "Interrupts" |
| `tab-players` | "Players" with its cards and `group_rows` |
| `tab-provenance` | "Provenance" |

Keep both macros (`ledger_row`, `pointer`) defined before the first panel; a Jinja macro definition emits nothing.

After `</main>` and before `</body>`, add the script:

```html
<script>
(function () {
  document.documentElement.classList.add("js");

  function show(panel) {
    var group = panel.getAttribute("data-tab-panel");
    var panels = document.querySelectorAll('[data-tab-panel="' + group + '"]');
    var buttons = document.querySelectorAll('[data-tab-group="' + group + '"] [data-tab-for]');
    for (var i = 0; i < panels.length; i++) {
      panels[i].classList.toggle("active", panels[i] === panel);
    }
    for (var j = 0; j < buttons.length; j++) {
      var on = buttons[j].getAttribute("data-tab-for") === panel.id;
      buttons[j].classList.toggle("active", on);
      buttons[j].setAttribute("aria-selected", on ? "true" : "false");
    }
  }

  function reveal(target) {
    var panels = [];
    for (var node = target; node && node !== document.body; node = node.parentElement) {
      if (node.hasAttribute("data-tab-panel")) { panels.unshift(node); }
    }
    for (var i = 0; i < panels.length; i++) { show(panels[i]); }
    return panels.length > 0;
  }

  function resolve() {
    var id = decodeURIComponent(location.hash.slice(1));
    var target = id ? document.getElementById(id) : null;
    if (target && reveal(target) && !target.hasAttribute("data-tab-panel")) {
      target.scrollIntoView();
    }
  }

  var buttons = document.querySelectorAll("[data-tab-for]");
  for (var b = 0; b < buttons.length; b++) {
    buttons[b].addEventListener("click", function (event) {
      var panel = document.getElementById(event.currentTarget.getAttribute("data-tab-for"));
      if (panel) {
        show(panel);
        history.replaceState(null, "", "#" + panel.id);
      }
    });
  }

  var groups = document.querySelectorAll("[data-tab-group]");
  for (var g = 0; g < groups.length; g++) {
    var first = groups[g].querySelector("[data-tab-for]");
    var panel = first ? document.getElementById(first.getAttribute("data-tab-for")) : null;
    if (panel) { show(panel); }
  }
  window.addEventListener("hashchange", resolve);
  resolve();
})();
</script>
```

Four duties, as the spec lists them: the root class; click handling that writes the fragment with `replaceState` (so the page does not jump); fragment resolution on load and on change, opening every panel that contains the target — outermost first, which is what lets a nested group in Phase J open too — and scrolling only when the target is not itself a panel; and the first tab of every group opened by default. Nothing else. `setAttribute("aria-selected", …)` sets an attribute, not text.

Update the template's ABOUTME lines:

```
{# ABOUTME: Document skeleton for the Mythic+ post-mortem report: a header, six tab panels holding #}
{# ABOUTME: the sections, and one inline script that only shows and hides — one self-contained file. #}
```

In `html.py`, change `render`'s docstring to `"""One self-contained HTML document: one inline script that only shows and hides, no network, no external font."""`.

- [ ] **Step 4: Run the invariants**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render -q`
Expected: everything passes except the golden test.

- [ ] **Step 5: Regenerate the golden file and read the diff**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/adapters/render/test_html_invariants.py --golden-update -q`
Then: `/cmd/git.exe diff tests/adapters/render/golden/minimal.html`
Expected: the CSS rules, the nav, six `<section>` wrappers, "Other findings" moved after the timeline, the script. Every card, every heading and every badge from before is still present, once.

- [ ] **Step 6: Tell the narrative's author where each claim lands**

In `.claude/skills/mplus-analysis/SKILL.md`, at the end of "Reading the file", add:

```markdown
The page groups the findings under six tabs, so when you point a reader at one, you can also say
where to look. Summary holds the three decomposition rows, up to five pointers at the biggest
losses, the aligned timeline and anything no tab claimed. Route & tempo holds the gaps, the
downtime, the skipped and extra packs, the trash rates and the confounds. Deaths holds each death
card and the death costs, defensives and consumables beneath them. Interrupts holds the kicks.
Players holds the cards and, beneath them, the per-player defensive and throughput rates.
Provenance holds the sources, everything withheld, and the badge legend. Without scripting, the
same sections stack in that order.
```

- [ ] **Step 7: Run the gate**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass.

- [ ] **Step 8: Commit**

```
/cmd/git.exe add src/wowperf/adapters/render/report.html.j2 src/wowperf/adapters/render/html.py tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/minimal.html tests/test_cli.py tests/e2e/test_report_e2e.py .claude/skills/mplus-analysis/SKILL.md
```
```
/cmd/git.exe commit -m "Group the report's sections under six tabs behind a script that only shows and hides" -m "Sixty-seven cards on one page is too long to read and too complete to cut: the route belongs to the caller, a death to the player who died, provenance to whoever doubts a number. The tab bar and the panel hiding are scoped under a class the script adds at run time, so a page without scripting is today's layout regrouped and a test parses the same content either way. The no-script invariant becomes an executes-only-its-own-script invariant that reads the script's text for anything that could fetch, write or store (tabs design 2026-09-06, §3, §6, §7.1)."
```

---

### Task 5: Re-run the real report and walk the browser check (orchestrator, needs credentials)

**Files:** none in the repo. Output under the worktree's `out/`. Outcomes recorded in the plan's ledger.

This task is run by the orchestrating session, not a subagent: it needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET`, which live in the main checkout's UTF-16 `.env` and are never printed. The scratch script `run_real_analyze.py` in the session's Temp scratchpad shows how to load them; if the scratchpad is gone, write the same twelve lines again there, never in the repo.

- [ ] **Step 1: Run the analysis**

```
uv run wowperf analyze https://www.warcraftlogs.com/reports/6Kx1P9GbNXrcLdHa?fight=36 --cache-dir C:/Users/damien/claude_perso/wow_perf/cache --out out
```

Expected on stderr: the quota sentence, roughly twenty-five points if the cache was deleted, about one if not. Expected on stdout: the two file paths.

- [ ] **Step 2: Check the placement against the findings file**

With a throwaway script in the scratchpad, list every finding id in `out/6Kx1P9GbNXrcLdHa-36.findings.json` and, for each, the `<h2>` section its `<h3>` title sits under in `out/6Kx1P9GbNXrcLdHa-36.html`. Confirm, one line each in the final report to RwlRwlRwlRwl:

- Every `compare.route.*`, `time.gap.*`, `trash.*`, `compare.downtime` and `compare.confound.*` is under "Route and tempo".
- Every `deaths.single.*`, `deaths.chain.*`, `deaths.repeat.*`, `defensives.unused.*`, `consumables.*` and `compare.deaths` is under "Deaths".
- Every `defensives.<player>.*`, `defensives.ceiling.*`, `throughput.*` and `compare.parse.unavailable` (if present) is under "Players".
- "Other findings" is empty ("Nothing else measured") or names only families the table does not know — and if it names one, say which, because that is a table row to add.
- Exactly five pointers under "Biggest losses", and the first is the finding with the largest `seconds_lost`.
- Every finding's title appears as an `<h3>` exactly once.

- [ ] **Step 3: The browser check, spec §7.5**

Open `out/6Kx1P9GbNXrcLdHa-36.html` in the browser pane. Record each outcome:

1. Summary is open; the other five panels are not visible.
2. Click each tab in turn; after each click exactly one panel is visible and the URL fragment is that panel's id.
3. On Route & tempo, click a badge; the Provenance tab opens and the legend is in view.
4. On Summary, click the first pointer; the tab holding its card opens and the card is in view.
5. Navigate to the file with `#deaths` appended; the Deaths tab is open on load.
6. Disable scripting for the page and reload — in the browser pane, run `document.documentElement.classList.remove("js")` through the JavaScript tool if no setting exists, which reproduces the no-script CSS state — and confirm the tab bar is gone and every panel is visible, stacked in tab order.

A step that fails is a defect: record it, fix it in the template, re-run Task 4's gate, commit, and repeat the step.

- [ ] **Step 4: Read the page once through as a player would.** Note anything the checks above missed.

- [ ] **Step 5: Update `.claude/lessons.md`** only if RwlRwlRwlRwl corrects something during review; otherwise leave it.

---

## Self-review against the spec

| Spec section | Task |
| --- | --- |
| §1 why, §10 decisions | 1 (amendments record them), commit bodies |
| §2 the page: six tabs, section per tab, Summary first, catch-all on Summary | 4 |
| §3 the script's four duties, no-script fallback, generic groups | 4 |
| §4 view model: fields added, `ledger_losses` gone, `death_findings` renamed, anchors | 2 (fields), 3 (`summary_pointers`, anchors) |
| §5.1 placement table, order is the rule, catch-all unchanged | 2 |
| §5.2 pointers: first five timed, service order, equal to card, heading omitted when none | 3 |
| §5.3 route section withheld reason, provenance line | 2 |
| §6 template and CSS: buttons, scoped rules, active mark, three not-additive sentences, pointer macro without `<h3>` | 2 (sentences), 3 (macro), 4 (bar, rules) |
| §7.1 invariants rewritten: script rule, order, counts, golden | 2 (counts renamed), 3 (`losses` in order), 4 (script rule in the invariants, the CLI mirror and the e2e mirror; panels) |
| §7.2 invariants added: hides nothing, pointer anchors, no `<h3>` in pointers, family table | 4, 3, 3, 2 |
| §7.3 unchanged invariants keep passing | every task's gate |
| §7.4 view-model tests | 2 (`test_build_placement.py`), 3 (`test_build_pointers.py`) |
| §7.5 browser check | 5 |
| §8 amendments to report design, postmortem design, analysis skill | 1, 1, 4 |
| §9 out of scope | nothing here builds it |
