# Mythic+ Post-Mortem, The HTML Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write one self-contained HTML report beside the findings JSON every time `analyze` runs, so a person can read what a run cost them without opening a JSON file.

**Architecture:** Three units in one direction. A frozen `Report` value object holds everything the page shows, already formatted. A pure `build_report` function decides what goes where — every judgement lives there and nowhere else. A Jinja2 adapter turns a `Report` into a string; it loops and escapes and decides nothing. The template cannot reach past the `Report`, which is what keeps judgement out of Jinja where it could not be unit-tested.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `jinja2`, `typer`, `pytest`, `ruff`, `mypy`.

**Spec:** `docs/plans/2026-09-05-mplus-report-design.md`. Its authority is `docs/plans/2026-09-03-mplus-postmortem-design.md` §7, amended 2026-09-05 in two places this plan depends on.

**Depends on:** Plans A (`be84a22`), B (`9bd47fb`), C (`ebe3ddc`) and D (`b8d0557`), all merged. Read `src/wowperf/domain/findings.py`, `src/wowperf/domain/model.py`, `src/wowperf/domain/analysis/players.py`, `src/wowperf/domain/comparison/alignment.py` and `src/wowperf/cli.py` before starting.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`uv` is not on PATH.** Every bash command using it begins `export PATH="$HOME/.local/bin:$PATH"`.
- **`src/wowperf/domain/` performs no I/O.** No `httpx`, no `jinja2`, no file reads, no `tomllib`. `domain/report/` is domain code and binds to this. Adapters do I/O.
- **The template may not reach past the `Report`.** No filters that compute, no arithmetic, no conditionals that encode judgement. If the template needs a decision made, the decision belongs in `build_report`.
- **The seconds ledger has no total row**, and nothing anywhere sums `seconds_lost`. Findings are ranked, not additive: `compare.duration` already contains every other figure, `time.gap.*` and `compare.downtime` nest inside `time.residual`, `deaths.single`/`chain` nest inside `deaths.total`, and `compare.route.skipped.*` overlaps `trash.overage`.
- **A withheld section's reason is never invented.** It is the `detail` of the `compare.*.unavailable` finding the tool already emits.
- **No colour carries meaning alone.** Confidence badges are a text label with a tint. Player cards print the class name beside the class colour.
- **Self-containment is absolute**: no `<script>`, no `src` or `href` to any external origin, no webfont, no content delivery network. System font stack only.
- **No hardcoded season data.** No zone, encounter, affix or ability ID as a literal in `src/`.
- Domain models subclass `Frozen` from `wowperf.domain.base` and use **tuple** fields, never `list` or `dict`, so they stay hashable.
- Every file starts with two `# ABOUTME: ` comment lines. Empty `__init__.py` markers are exempt.
- **English** in code, comments, error strings and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains **why**.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument). Ruff's line length is 100.

## Decisions this plan makes

Recorded so an implementer does not rediscover them and a reviewer does not flag them.

1. **A finding appears exactly once in the report.** The ledger holds every finding with a `seconds_lost`; the topical sections hold the rest, grouped by id prefix. Task 10 tests this invariant directly. Without the rule, sections 3 and 6 would both render `interrupts.*` and a reader would double-count.
2. **The deaths section is built from `loaded.deaths` and `loaded.damage_taken`, not from findings.** §7 asks for each death expanded into the last ten seconds of damage taken, which no finding carries.
3. **`summarise_players` is called directly.** It already exists, is public and pure, and returns every per-player number the cards need. There is no extraction task.
4. **Nesting is a static table, not inference.** `NESTS_INSIDE` in `build.py` maps an id prefix to its parent id. The relationships come from the findings JSON's own warning text and change only when an analyser changes.
5. **Timeline geometry is computed in `build_report`**, in viewBox units. The template emits `<rect>` elements from a loop and does no arithmetic.

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | *Modified.* Adds `jinja2` and the package-data entry for the template |
| `src/wowperf/domain/report/__init__.py` | Empty package marker |
| `src/wowperf/domain/report/model.py` | The `Report` value object and every sub-value it holds |
| `src/wowperf/domain/report/build.py` | `build_report`, and the private per-section builders |
| `src/wowperf/adapters/render/__init__.py` | Empty package marker |
| `src/wowperf/adapters/render/html.py` | `render(report) -> str`; the only module that imports `jinja2` |
| `src/wowperf/adapters/render/report.html.j2` | The template |
| `src/wowperf/domain/analysis/timeline.py` | *Modified.* Pack name before map coordinates |
| `src/wowperf/domain/analysis/trash.py` | *Modified.* Same |
| `src/wowperf/cli.py` | *Modified.* `--narrative`, and writing the HTML |
| `CLAUDE.md` | *Modified.* Records that the report shipped |

---

### Task 1: The view model

**Files:**
- Modify: `pyproject.toml`
- Create: `src/wowperf/domain/report/__init__.py`, `src/wowperf/domain/report/model.py`
- Test: `tests/domain/report/__init__.py`, `tests/domain/report/test_model.py`

**Interfaces:**
- Consumes: `Frozen` from `wowperf.domain.base`.
- Produces: every type in the block below, importable from `wowperf.domain.report.model`.

These are pure data with no methods and no validators. Everything is already formatted for display: strings are final, numbers are rounded, order is decided. A later task may add a field it turns out to need; none may add a method, because a method on the view model is judgement the template can reach.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"jinja2>=3.1",` to the `dependencies` list, keeping the list alphabetical — it goes after `"httpx>=0.27",`.

Then, so an installed wheel carries the template, add this after the `[project.scripts]` block:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/wowperf"]

[tool.hatch.build.targets.wheel.force-include]
"src/wowperf/adapters/render/report.html.j2" = "wowperf/adapters/render/report.html.j2"
```

Run: `export PATH="$HOME/.local/bin:$PATH" && uv sync`
Expected: jinja2 installs.

- [ ] **Step 2: Write the failing test**

`tests/domain/report/__init__.py` is empty. `tests/domain/report/test_model.py`:

```python
# ABOUTME: Behaviour tests for the report view model — frozen, hashable, no judgement.
# ABOUTME: The model is pure data; anything that decides something belongs in build.py.

import pytest
from pydantic import ValidationError

from wowperf.domain.report.model import (
    Badge,
    DeathCard,
    Header,
    LedgerRow,
    PlayerCard,
    Provenance,
    Report,
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)


def a_section(state: SectionState = SectionState.PRESENT, reason: str = "") -> Section:
    return Section(state=state, reason=reason)


def test_a_present_section_needs_no_reason() -> None:
    assert a_section().reason == ""


def test_a_withheld_section_carries_its_reason() -> None:
    section = a_section(SectionState.WITHHELD, "no faster run was available")
    assert section.state is SectionState.WITHHELD
    assert section.reason == "no faster run was available"


def test_every_view_model_type_is_frozen() -> None:
    row = LedgerRow(
        finding_id="time.residual",
        title="Time outside pulls",
        detail="Travel, waiting and run-backs.",
        badge=Badge(label="measured", tint="measured"),
        seconds="4:12",
        nests_inside=None,
    )
    with pytest.raises(ValidationError):
        row.title = "something else"  # type: ignore[misc]


def test_a_timeline_block_is_hashable_so_a_report_can_be_compared() -> None:
    block = TimelineBlock(label="Nalorakk", x=10.0, width=40.0, is_boss=True, kind="matched")
    assert hash(block) == hash(
        TimelineBlock(label="Nalorakk", x=10.0, width=40.0, is_boss=True, kind="matched")
    )


def test_a_report_holds_every_section() -> None:
    report = Report(
        header=Header(
            dungeon="Den of Nalorakk",
            keystone_level=16,
            affixes=("Tyrannical",),
            result="Timed by 2:14",
        ),
        narrative=None,
        ledger_decomposition=(),
        ledger_losses=(),
        timeline=Timeline(section=a_section(SectionState.WITHHELD, "no reference")),
        deaths=(),
        interrupts=(),
        players=(),
        provenance=Provenance(
            report_code="abc123",
            fight_id=36,
            fetched_at="2026-09-05 14:02",
            speed_reference_url=None,
            parse_reference_url=None,
        ),
    )
    assert report.narrative is None
    assert report.timeline.section.state is SectionState.WITHHELD


def test_a_player_card_names_the_class_in_text_not_only_in_colour() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        active_time="412s in pulls (38%)",
        deaths=1,
        kicks=7,
        spell_and_talent=a_section(SectionState.WITHHELD, "no ranked parse"),
    )
    assert card.class_name in ("DeathKnight",)
    assert card.colour != card.class_name


def test_a_death_card_can_carry_no_damage_rows() -> None:
    card = DeathCard(
        player="Dudesons",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
    )
    assert card.last_ten_seconds == ()


def test_a_timeline_track_defaults_to_no_blocks() -> None:
    assert TimelineTrack(caption="Ours — 31:48").blocks == ()
```

- [ ] **Step 3: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_model.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.report'`.

- [ ] **Step 4: Write the model**

`src/wowperf/domain/report/__init__.py` is empty. `src/wowperf/domain/report/model.py`:

```python
# ABOUTME: Everything the HTML report shows, already formatted, as one frozen value.
# ABOUTME: No methods: a method here would be judgement the template could reach.

from enum import StrEnum

from wowperf.domain.base import Frozen


class SectionState(StrEnum):
    """Whether a section has data, or is reporting why it has none."""

    PRESENT = "present"
    WITHHELD = "withheld"


class Section(Frozen):
    """A section's state, and the reason when it has nothing to show.

    The reason is never written by the report: it is the detail of the
    `compare.*.unavailable` finding the comparison already emits.
    """

    state: SectionState
    reason: str = ""


class Badge(Frozen):
    """A confidence badge: a word plus a palette token, never a colour alone."""

    label: str
    tint: str


class LedgerRow(Frozen):
    """One finding, formatted for display."""

    finding_id: str
    title: str
    detail: str
    badge: Badge
    seconds: str | None = None
    nests_inside: str | None = None
    evidence: tuple[str, ...] = ()


class TimelineBlock(Frozen):
    """One pull, positioned in viewBox units. All arithmetic happened in build.py."""

    label: str
    x: float
    width: float
    is_boss: bool
    kind: str


class TimelineTrack(Frozen):
    caption: str
    blocks: tuple[TimelineBlock, ...] = ()


class Timeline(Frozen):
    """Both runs on one elapsed-time axis. Empty tracks when the section is withheld."""

    section: Section
    ours: TimelineTrack | None = None
    theirs: TimelineTrack | None = None
    ticks: tuple[tuple[float, str], ...] = ()
    width: float = 0.0
    height: float = 0.0


class DamageRow(Frozen):
    seconds_before: str
    ability: str
    amount: str


class DeathCard(Frozen):
    player: str
    class_name: str
    when: str
    killing_blow: str
    last_ten_seconds: tuple[DamageRow, ...] = ()


class PlayerCard(Frozen):
    """One player's measured facts.

    `damage_rows` states damage against the group median, never as avoidable:
    the log does not record whether a hit could have been dodged, and this card
    follows the analyser that refuses that framing.
    """

    name: str
    class_name: str
    spec: str
    colour: str
    active_time: str
    deaths: int
    kicks: int
    damage_rows: tuple[LedgerRow, ...] = ()
    spell_and_talent: Section
    spell_and_talent_rows: tuple[LedgerRow, ...] = ()


class Header(Frozen):
    """No percentile: nothing this project fetches produces our own player's rank."""

    dungeon: str
    keystone_level: int
    affixes: tuple[str, ...] = ()
    result: str = ""
    warnings: tuple[str, ...] = ()


class Provenance(Frozen):
    report_code: str
    fight_id: int
    fetched_at: str
    speed_reference_url: str | None = None
    parse_reference_url: str | None = None
    withheld: tuple[str, ...] = ()


class Report(Frozen):
    header: Header
    narrative: str | None
    ledger_decomposition: tuple[LedgerRow, ...]
    ledger_losses: tuple[LedgerRow, ...]
    timeline: Timeline
    deaths: tuple[DeathCard, ...]
    interrupts: tuple[LedgerRow, ...]
    players: tuple[PlayerCard, ...]
    provenance: Provenance
```

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_model.py -v`
Expected: 8 passed.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add pyproject.toml uv.lock src/wowperf/domain/report/ tests/domain/report/
git commit -m "Model what the HTML report shows, as one frozen value

The template is going to loop over this and nothing else. Keeping it pure
data with no methods is what stops a decision migrating into Jinja, where
it could not be unit-tested."
```

---

### Task 2: The report's frame — header, narrative, provenance, and withholding

**Files:**
- Create: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_build_frame.py`

**Interfaces:**
- Consumes: every type from Task 1; `LoadedRun`, `Run` from `wowperf.domain.model`; `Finding`, `Confidence` from `wowperf.domain.findings`; `SpeedReference`, `ParseReference` from `wowperf.domain.comparison.reference`.
- Produces:
  - `def build_report(loaded, findings, speed, parse, narrative, fetched_at) -> Report`
  - `def badge_for(confidence: Confidence) -> Badge`
  - `def format_seconds(seconds: float | None) -> str | None`
  - `SPEED_UNAVAILABLE_ID: str = "compare.speed.unavailable"`
  - `PARSE_UNAVAILABLE_ID: str = "compare.parse.unavailable"`

This task delivers a `Report` whose sections 1, 2 and 8 are real and whose other five are empty. Later tasks fill them in one at a time. That ordering is deliberate: the withholding machinery is what every other section depends on, and it is easiest to get right in isolation.

`fetched_at` is a parameter, not `datetime.now()` — the domain performs no I/O and reads no clock, and a rendered report must be reproducible from the same inputs.

- [ ] **Step 1: Write the failing test**

`tests/domain/report/test_build_frame.py`:

```python
# ABOUTME: Behaviour tests for the report's frame: header, narrative, provenance, withholding.
# ABOUTME: The withheld reason must come from the finding, never from a string in the template.

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Pull, Run
from wowperf.domain.report.build import build_report, format_seconds
from wowperf.domain.report.model import SectionState

FETCHED = "2026-09-05 14:02"


def a_pull(index: int, start: int, end: int, encounter_id: int = 0) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name=f"Pack {index}",
        encounter_id=encounter_id,
        start_ms=start,
        end_ms=end,
        killed=True,
        x=100,
        y=200,
        enemies=(),
    )


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "report_code": "abc123",
        "fight_id": 36,
        "dungeon_name": "Den of Nalorakk",
        "encounter_id": 12825,
        "keystone_level": 16,
        "affix_ids": (9, 10),
        "keystone_time_ms": 1_800_000,
        "keystone_bonus": 1,
        "count_reached": 100,
        "count_required": 100,
        "npc_counts": (),
        "players": (),
        "pulls": (a_pull(0, 0, 60_000),),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_loaded(**overrides: object) -> LoadedRun:
    return LoadedRun(run=a_run(**overrides))


def unavailable(finding_id: str, detail: str) -> Finding:
    return Finding(
        id=finding_id,
        title="Nothing to compare against",
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
    )


def test_the_header_states_the_dungeon_and_the_key() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.header.dungeon == "Den of Nalorakk"
    assert report.header.keystone_level == 16


def test_a_timed_run_says_so_and_by_how_much() -> None:
    # 60s of pulls against a 1800s key: timed with a lot to spare.
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.header.result.startswith("Timed")


def test_a_depleted_run_says_so_and_by_how_much() -> None:
    report = build_report(a_loaded(keystone_bonus=0), (), None, None, None, FETCHED)
    assert report.header.result.startswith("Depleted")


def test_no_narrative_leaves_the_section_absent_rather_than_withheld() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.narrative is None


def test_a_narrative_is_carried_through_verbatim() -> None:
    report = build_report(a_loaded(), (), None, None, "Both losses were travel.", FETCHED)
    assert report.narrative == "Both losses were travel."


def test_a_withheld_section_takes_its_reason_from_the_finding() -> None:
    detail = "The speed leaderboard returned nothing for this dungeon."
    report = build_report(
        a_loaded(), (unavailable("compare.speed.unavailable", detail),), None, None, None, FETCHED
    )
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.timeline.section.reason == detail


def test_a_withheld_section_with_no_finding_still_says_something_true() -> None:
    # `--no-compare` emits no unavailable finding at all, because no comparison ran.
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.timeline.section.state is SectionState.WITHHELD
    assert report.timeline.section.reason


def test_provenance_lists_every_withheld_section() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert any("timeline" in line.lower() for line in report.provenance.withheld)


def test_provenance_carries_the_report_code_and_the_fetch_time() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.provenance.report_code == "abc123"
    assert report.provenance.fetched_at == FETCHED


def test_seconds_format_as_minutes_and_seconds() -> None:
    assert format_seconds(252.0) == "4:12"
    assert format_seconds(9.4) == "0:09"


def test_no_seconds_formats_as_nothing_rather_than_zero() -> None:
    assert format_seconds(None) is None
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_frame.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.report.build'`.

- [ ] **Step 3: Write the builder**

`src/wowperf/domain/report/build.py`:

```python
# ABOUTME: Turns a loaded run and its findings into the value the template renders.
# ABOUTME: Every judgement about what appears where lives here, and nowhere else.

from collections.abc import Sequence

from wowperf.domain.comparison.reference import ParseReference, SpeedReference
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Run
from wowperf.domain.report.model import (
    Badge,
    Header,
    Provenance,
    Report,
    Section,
    SectionState,
    Timeline,
)

SPEED_UNAVAILABLE_ID = "compare.speed.unavailable"
PARSE_UNAVAILABLE_ID = "compare.parse.unavailable"

NO_COMPARISON_RAN = (
    "No reference run was fetched for this analysis, so there is nothing to compare against."
)
"""Said when `--no-compare` skipped the comparison entirely, so no finding explains the absence."""

REPORT_URL = "https://www.warcraftlogs.com/reports/{code}?fight={fight}"


def badge_for(confidence: Confidence) -> Badge:
    """A word and a palette token. The word is what a reader without colour sees."""
    return Badge(label=str(confidence), tint=f"badge-{confidence}")


def format_seconds(seconds: float | None) -> str | None:
    """Minutes and seconds, or nothing at all.

    `None` stays `None` rather than becoming "0:00": a finding with no honest
    seconds figure must not read as one that cost no time.
    """
    if seconds is None:
        return None
    whole = int(round(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def _finding_by_id(findings: Sequence[Finding], finding_id: str) -> Finding | None:
    return next((finding for finding in findings if finding.id == finding_id), None)


def _section_for(findings: Sequence[Finding], unavailable_id: str, present: bool) -> Section:
    """Present, or withheld with the reason the comparison itself gave.

    When no comparison ran at all there is no finding to quote, so the fallback
    states that plainly rather than implying a leaderboard came back empty.
    """
    if present:
        return Section(state=SectionState.PRESENT)
    finding = _finding_by_id(findings, unavailable_id)
    return Section(
        state=SectionState.WITHHELD,
        reason=finding.detail if finding else NO_COMPARISON_RAN,
    )


def _run_seconds(run: Run) -> float:
    """Wall-clock span from the first pull's start to the last pull's end.

    Not `total_pull_seconds`, which sums pull durations and so omits every
    second spent travelling — the very time this report exists to show.
    """
    if not run.pulls:
        return 0.0
    return (max(p.end_ms for p in run.pulls) - min(p.start_ms for p in run.pulls)) / 1000


def _header(loaded: LoadedRun) -> Header:
    run = loaded.run
    margin = run.keystone_time_seconds - _run_seconds(run)
    verb = "Timed" if run.keystone_bonus >= 1 else "Depleted"
    by = format_seconds(abs(margin)) or "0:00"
    return Header(
        dungeon=run.dungeon_name,
        keystone_level=run.keystone_level,
        affixes=tuple(str(affix_id) for affix_id in run.affix_ids),
        result=f"{verb} by {by}",
    )


def _reference_url(report_code: str, fight_id: int) -> str:
    return REPORT_URL.format(code=report_code, fight=fight_id)


def build_report(
    loaded: LoadedRun,
    findings: Sequence[Finding],
    speed: SpeedReference | None,
    parse: ParseReference | None,
    narrative: str | None,
    fetched_at: str,
) -> Report:
    """Everything the page shows, decided here so the template decides nothing.

    `fetched_at` is a parameter rather than a clock read: the domain performs no
    I/O, and the same inputs must render the same report.
    """
    timeline_section = _section_for(findings, SPEED_UNAVAILABLE_ID, speed is not None)

    withheld: list[str] = []
    if timeline_section.state is SectionState.WITHHELD:
        withheld.append(f"Aligned timeline: {timeline_section.reason}")

    return Report(
        header=_header(loaded),
        narrative=narrative,
        ledger_decomposition=(),
        ledger_losses=(),
        timeline=Timeline(section=timeline_section),
        deaths=(),
        interrupts=(),
        players=(),
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

- [ ] **Step 4: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_frame.py -v`
Expected: 11 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/build.py tests/domain/report/test_build_frame.py
git commit -m "Build the report's frame, and make withholding say why

A section with no data keeps its heading and states its reason, and the
reason is the unavailable finding's own detail rather than a sentence the
template invents. The one case with no finding to quote is --no-compare,
where nothing was withheld so much as never asked for, and the fallback
says that instead."
```

---

### Task 3: The seconds ledger, which is not a sum

**Files:**
- Modify: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_build_ledger.py`

**Interfaces:**
- Consumes: `build_report`, `badge_for`, `format_seconds` from Task 2; `LedgerRow` from Task 1.
- Produces:
  - `NESTS_INSIDE: tuple[tuple[str, str], ...]` — (id prefix, parent finding id) pairs
  - `DECOMPOSITION_IDS: tuple[str, ...]`
  - `def parent_of(finding_id: str) -> str | None`
  - `build_report` now fills `ledger_decomposition` and `ledger_losses`

Two rules make this section honest, and a reviewer will check both.

1. **No total.** `Report` exposes no total field and nothing sums `seconds_lost`. `compare.duration` already contains every other figure in the report; a total row would print a number larger than the run itself.
2. **A finding appears exactly once in the whole report.** The ledger takes every finding with a `seconds_lost`; the topical sections take the rest. Task 10 tests that invariant across the rendered page.

- [ ] **Step 1: Write the failing test**

`tests/domain/report/test_build_ledger.py`:

```python
# ABOUTME: Behaviour tests for the seconds ledger: two parts, nesting stated, never a total.
# ABOUTME: The nesting lines are what stop a reader adding figures that already contain each other.

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.report.build import build_report, parent_of
from wowperf.domain.report.model import LedgerRow

from tests.domain.report.test_build_frame import FETCHED, a_loaded


def a_finding(finding_id: str, seconds: float | None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.MEASURED,
        seconds_lost=seconds,
    )


def ids(rows: tuple[LedgerRow, ...]) -> list[str]:
    return [row.finding_id for row in rows]


def test_a_top_level_figure_goes_to_the_decomposition() -> None:
    report = build_report(
        a_loaded(), (a_finding("time.residual", 300.0),), None, None, None, FETCHED
    )
    assert ids(report.ledger_decomposition) == ["time.residual"]
    assert ids(report.ledger_losses) == []


def test_a_ranked_loss_goes_to_the_losses() -> None:
    report = build_report(a_loaded(), (a_finding("time.gap.0", 41.0),), None, None, None, FETCHED)
    assert ids(report.ledger_losses) == ["time.gap.0"]
    assert ids(report.ledger_decomposition) == []


def test_a_loss_that_nests_says_what_contains_it() -> None:
    report = build_report(
        a_loaded(),
        (a_finding("time.residual", 300.0), a_finding("time.gap.0", 41.0)),
        None,
        None,
        None,
        FETCHED,
    )
    assert report.ledger_losses[0].nests_inside == "time.residual"


def test_a_loss_that_nests_in_nothing_says_nothing() -> None:
    report = build_report(a_loaded(), (a_finding("trash.overage", 55.0),), None, None, None, FETCHED)
    assert report.ledger_losses[0].nests_inside is None


def test_a_finding_with_no_seconds_never_reaches_the_ledger() -> None:
    report = build_report(
        a_loaded(), (a_finding("players.damage.0", None),), None, None, None, FETCHED
    )
    assert ids(report.ledger_decomposition) == []
    assert ids(report.ledger_losses) == []


def test_losses_keep_the_order_they_arrived_in() -> None:
    # `rank_findings` has already ordered them; the ledger must not re-sort.
    report = build_report(
        a_loaded(),
        (a_finding("time.gap.0", 90.0), a_finding("compare.downtime", 40.0)),
        None,
        None,
        None,
        FETCHED,
    )
    assert ids(report.ledger_losses) == ["time.gap.0", "compare.downtime"]


def test_seconds_reach_the_row_already_formatted() -> None:
    report = build_report(a_loaded(), (a_finding("time.gap.0", 252.0),), None, None, None, FETCHED)
    assert report.ledger_losses[0].seconds == "4:12"


def test_the_badge_carries_a_word_not_only_a_tint() -> None:
    report = build_report(a_loaded(), (a_finding("time.gap.0", 12.0),), None, None, None, FETCHED)
    assert report.ledger_losses[0].badge.label == "measured"


def test_every_nesting_relationship_the_findings_file_declares() -> None:
    assert parent_of("time.gap.3") == "time.residual"
    assert parent_of("compare.downtime") == "time.residual"
    assert parent_of("deaths.single.0") == "deaths.total"
    assert parent_of("deaths.chain.1") == "deaths.total"
    assert parent_of("compare.route.skipped.2") == "trash.overage"
    assert parent_of("trash.overage") is None
    assert parent_of("compare.duration") is None
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_ledger.py -v`
Expected: FAIL, `ImportError: cannot import name 'parent_of'`.

- [ ] **Step 3: Add the nesting table**

In `src/wowperf/domain/report/build.py`, add `LedgerRow` to the imports from `wowperf.domain.report.model`, then add below `REPORT_URL`:

```python
DECOMPOSITION_IDS = ("compare.duration", "time.residual", "deaths.total")
"""Figures that contain others. They head the ledger; everything else is ranked beneath."""

NESTS_INSIDE = (
    ("time.gap.", "time.residual"),
    ("compare.downtime", "time.residual"),
    ("deaths.single.", "deaths.total"),
    ("deaths.chain.", "deaths.total"),
    ("compare.route.skipped.", "trash.overage"),
)
"""Which figures are already contained by which, copied from the findings file's own warning.

Stated rather than inferred: the relationships come from what the analysers
measure, and they change when an analyser changes, not when a report renders.
`compare.duration` contains every figure here and is a decomposition row rather
than a parent — repeating it on every line would be noise.
"""
```

- [ ] **Step 4: Add the two functions**

```python
def parent_of(finding_id: str) -> str | None:
    """The figure this one is already contained by, if any."""
    for prefix, parent in NESTS_INSIDE:
        if finding_id.startswith(prefix):
            return parent
    return None


def _ledger_row(finding: Finding) -> LedgerRow:
    return LedgerRow(
        finding_id=finding.id,
        title=finding.title,
        detail=finding.detail,
        badge=badge_for(finding.confidence),
        seconds=format_seconds(finding.seconds_lost),
        nests_inside=parent_of(finding.id),
        evidence=finding.evidence,
    )
```

- [ ] **Step 5: Fill the two parts in `build_report`**

Replace the two empty ledger arguments in the `Report(...)` construction:

```python
        ledger_decomposition=tuple(
            _ledger_row(finding)
            for finding in findings
            if finding.seconds_lost is not None and finding.id in DECOMPOSITION_IDS
        ),
        ledger_losses=tuple(
            _ledger_row(finding)
            for finding in findings
            if finding.seconds_lost is not None and finding.id not in DECOMPOSITION_IDS
        ),
```

The order of `findings` is preserved in both. `rank_findings` has already ordered them by cost, and re-sorting here would let the report disagree with the JSON about which loss was largest.

- [ ] **Step 6: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_ledger.py -v`
Expected: 9 passed.

- [ ] **Step 7: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/build.py tests/domain/report/test_build_ledger.py
git commit -m "Split the seconds ledger into containers and ranked losses

A section called a ledger invites a total row, and a total here would be
larger than the run itself: compare.duration already contains every other
figure, gaps nest inside residual, and single deaths inside the total. So
the containers head the section, each loss says what contains it, and
nothing anywhere adds two seconds figures together."
```

---

### Task 4: The aligned timeline's geometry

**Files:**
- Modify: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_build_timeline.py`

**Interfaces:**
- Consumes: `align_pulls` from `wowperf.domain.comparison.alignment`; `Timeline`, `TimelineTrack`, `TimelineBlock` from Task 1.
- Produces:
  - `def build_timeline(ours: Run, theirs: Run | None, section: Section) -> Timeline`
  - `TIMELINE_WIDTH: float = 680.0`, `TIMELINE_HEIGHT: float = 208.0`
  - `TRACK_X0: float = 46.0`, `TRACK_X1: float = 656.0`
  - `build_report` now fills `timeline`

Both runs share one elapsed-time axis, scaled to the longer of the two so both fit and the shorter one visibly ends early. **The space between blocks is travel**, which is the whole reason this layout was chosen over a per-pull table: every analyser since Plan B has been saying travel is where the time goes, and no table shows it.

Pack names do not fit in thin blocks and are not attempted — each block carries its `label` for an SVG `<title>` child, which shows on hover. A screenshot loses the names, and that is accepted.

Every number here is in viewBox units. The template does no arithmetic.

`Alignment.only_ours` and `Alignment.only_theirs` hold **pull indices**, so they map onto `Pull.index` directly.

- [ ] **Step 1: Write the failing test**

`tests/domain/report/test_build_timeline.py`:

```python
# ABOUTME: Behaviour tests for timeline geometry: shared axis, marked packs, no arithmetic left over.
# ABOUTME: The gaps between blocks are travel, which is the reason this layout was chosen.

from wowperf.domain.report.build import TRACK_X0, TRACK_X1, build_report, build_timeline
from wowperf.domain.report.model import Section, SectionState

from tests.domain.report.test_build_frame import FETCHED, a_loaded, a_pull, a_run

PRESENT = Section(state=SectionState.PRESENT)
WITHHELD = Section(state=SectionState.WITHHELD, reason="no faster run was available")


def test_a_withheld_timeline_has_no_tracks_at_all() -> None:
    timeline = build_timeline(a_run(), None, WITHHELD)
    assert timeline.ours is None
    assert timeline.theirs is None
    assert timeline.section.state is SectionState.WITHHELD


def test_our_first_block_starts_where_the_axis_starts() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 180_000)))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].x == TRACK_X0


def test_the_axis_is_scaled_to_the_longer_run_so_both_fit() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 100_000),))
    theirs = a_run(pulls=(a_pull(0, 0, 200_000),))
    timeline = build_timeline(ours, theirs, PRESENT)
    assert timeline.theirs is not None
    # Theirs is the longer run, so its last block ends at the axis's right edge.
    last = timeline.theirs.blocks[-1]
    assert round(last.x + last.width, 6) == TRACK_X1
    # Ours ran half as long, so it ends halfway along.
    assert timeline.ours is not None
    ours_last = timeline.ours.blocks[-1]
    assert round(ours_last.x + ours_last.width) == round(TRACK_X0 + (TRACK_X1 - TRACK_X0) / 2)


def test_the_space_between_blocks_is_travel_and_is_preserved() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 50_000), a_pull(1, 150_000, 200_000)))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    first, second = timeline.ours.blocks
    assert second.x > first.x + first.width


def test_a_boss_pull_is_marked_as_one() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, encounter_id=12825),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].is_boss is True


def test_a_pack_only_we_pulled_is_marked_as_extra() -> None:
    ours = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    theirs = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    timeline = build_timeline(ours, theirs, PRESENT)
    assert timeline.ours is not None
    assert [block.kind for block in timeline.ours.blocks] == ["matched", "extra"]


def test_a_pack_only_they_pulled_is_marked_as_skipped() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000, enemies=(1,)),))
    theirs = a_run(
        pulls=(a_pull(0, 0, 60_000, enemies=(1,)), a_pull(1, 90_000, 140_000, enemies=(7,)))
    )
    timeline = build_timeline(ours, theirs, PRESENT)
    assert timeline.theirs is not None
    assert [block.kind for block in timeline.theirs.blocks] == ["matched", "skipped"]


def test_every_block_carries_its_pack_name_for_the_tooltip() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 60_000),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].label == "Pack 0"


def test_a_very_short_pull_still_has_a_visible_width() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 100), a_pull(1, 500_000, 900_000)))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks[0].width >= 2.0


def test_a_run_with_no_pulls_yields_no_blocks_and_does_not_divide_by_zero() -> None:
    empty = a_run(pulls=())
    timeline = build_timeline(empty, empty, PRESENT)
    assert timeline.ours is not None
    assert timeline.ours.blocks == ()


def test_the_axis_carries_ticks_a_reader_can_read() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 1_200_000),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ticks
    assert all(":" in label for _x, label in timeline.ticks)


def test_the_caption_names_the_run_and_its_length() -> None:
    ours = a_run(pulls=(a_pull(0, 0, 600_000),))
    timeline = build_timeline(ours, ours, PRESENT)
    assert timeline.ours is not None
    assert "10:00" in timeline.ours.caption


def test_without_a_speed_reference_build_report_leaves_the_tracks_empty() -> None:
    report = build_report(a_loaded(), (), None, None, None, FETCHED)
    assert report.timeline.ours is None
```

The `a_pull` helper in `test_build_frame.py` needs an `enemies` argument for the two alignment tests. Widen it there:

```python
def a_pull(
    index: int, start: int, end: int, encounter_id: int = 0, enemies: tuple[int, ...] = ()
) -> Pull:
    return Pull(
        index=index,
        pull_id=index,
        name=f"Pack {index}",
        encounter_id=encounter_id,
        start_ms=start,
        end_ms=end,
        killed=True,
        x=100,
        y=200,
        enemies=tuple(EnemyNpc(actor_id=n, game_id=n) for n in enemies),
    )
```

and add `EnemyNpc` to that file's imports from `wowperf.domain.model`. Every existing call site passes no `enemies` and keeps working.

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_timeline.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_timeline'`.

- [ ] **Step 3: Add the constants**

In `build.py`, extend the model import with `TimelineBlock, TimelineTrack` and add `from wowperf.domain.comparison.alignment import align_pulls`. `Run` is already imported from Task 2. Then add below `NESTS_INSIDE`:

```python
TIMELINE_WIDTH = 680.0
TIMELINE_HEIGHT = 208.0
TRACK_X0 = 46.0
TRACK_X1 = 656.0
MIN_BLOCK_WIDTH = 2.0
"""A pull narrower than this reads as nothing at all, so it is drawn at this width."""

TICK_SECONDS = 600
"""One axis label every ten minutes: enough to place a pull, few enough to stay legible."""
```

- [ ] **Step 4: Write the geometry**

`_run_seconds` already exists from Task 2 — do not define it again.

```python
def _blocks(
    run: Run, kinds: dict[int, str], scale: float, origin_ms: int
) -> tuple[TimelineBlock, ...]:
    return tuple(
        TimelineBlock(
            label=pull.name,
            x=TRACK_X0 + (pull.start_ms - origin_ms) / 1000 * scale,
            width=max(pull.duration_seconds * scale, MIN_BLOCK_WIDTH),
            is_boss=pull.is_boss,
            kind=kinds.get(pull.index, "matched"),
        )
        for pull in run.pulls
    )


def _ticks(longest: float, scale: float) -> tuple[tuple[float, str], ...]:
    marks = []
    second = 0
    while second <= longest:
        marks.append((TRACK_X0 + second * scale, format_seconds(float(second)) or "0:00"))
        second += TICK_SECONDS
    return tuple(marks)


def build_timeline(ours: Run, theirs: Run | None, section: Section) -> Timeline:
    """Both runs on one elapsed-time axis, scaled so the longer one fills the width.

    The space between blocks is travel. That is why this layout exists: a
    per-pull table compares durations, and durations are rarely where a
    Mythic+ run loses its time.
    """
    if section.state is SectionState.WITHHELD or theirs is None:
        return Timeline(section=section, width=TIMELINE_WIDTH, height=TIMELINE_HEIGHT)

    longest = max(_run_seconds(ours), _run_seconds(theirs))
    scale = (TRACK_X1 - TRACK_X0) / longest if longest > 0 else 0.0

    alignment = align_pulls(ours, theirs)
    our_kinds = {index: "extra" for index in alignment.only_ours}
    their_kinds = {index: "skipped" for index in alignment.only_theirs}

    return Timeline(
        section=section,
        ours=TimelineTrack(
            caption=f"Ours — {format_seconds(_run_seconds(ours))}",
            blocks=_blocks(
                ours, our_kinds, scale, min((p.start_ms for p in ours.pulls), default=0)
            ),
        ),
        theirs=TimelineTrack(
            caption=f"Reference — {format_seconds(_run_seconds(theirs))}",
            blocks=_blocks(
                theirs, their_kinds, scale, min((p.start_ms for p in theirs.pulls), default=0)
            ),
        ),
        ticks=_ticks(longest, scale),
        width=TIMELINE_WIDTH,
        height=TIMELINE_HEIGHT,
    )
```

- [ ] **Step 5: Wire it into `build_report`**

Replace `timeline=Timeline(section=timeline_section),` with:

```python
        timeline=build_timeline(
            loaded.run, speed.loaded.run if speed else None, timeline_section
        ),
```

- [ ] **Step 6: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/ -v`
Expected: 13 new tests pass, and every test from Tasks 1 to 3 still passes.

- [ ] **Step 7: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/build.py tests/domain/report/
git commit -m "Lay both runs on one clock, in viewBox units

A per-pull table compares durations, and durations are rarely where a
Mythic+ run loses its time. Two tracks on a shared axis put the travel
between pulls on the page, which is what every analyser since the time
decomposition has been pointing at. All the arithmetic happens here, so
the template only loops."
```

---

### Task 5: Deaths, expanded into what killed them

**Files:**
- Modify: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_build_deaths.py`

**Interfaces:**
- Consumes: `Death`, `DamageTakenEvent` from `wowperf.domain.events`; `DeathCard`, `DamageRow` from Task 1.
- Produces:
  - `def build_deaths(loaded: LoadedRun) -> tuple[DeathCard, ...]`
  - `LAST_SECONDS_BEFORE_DEATH: float = 10.0`
  - `build_report` now fills `deaths`

This section is built from `loaded.deaths` and `loaded.damage_taken`, **not from findings** — no finding carries the last ten seconds of damage, which is the whole point of the section.

Cards are ordered by when the death happened, not by cost. A reader following a run wants them in the order they lived through.

- [ ] **Step 1: Write the failing test**

`tests/domain/report/test_build_deaths.py`:

```python
# ABOUTME: Behaviour tests for the deaths section: ordered by time, expanded into the last ten seconds.
# ABOUTME: Built from raw events rather than findings, because no finding carries the damage run-up.

from wowperf.domain.events import DamageTakenEvent, Death
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_deaths

from tests.domain.report.test_build_frame import a_pull, a_run


def a_player(actor_id: int = 1, name: str = "Dudesons") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_death(actor_id: int, at_ms: int, blow: str = "Frigid Roar") -> Death:
    return Death(
        player_name="Dudesons",
        actor_id=actor_id,
        timestamp_ms=at_ms,
        killing_blow=blow,
        pull_index=0,
    )


def a_hit(actor_id: int, at_ms: int, ability: str, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id,
        ability_id=1,
        ability_name=ability,
        amount=amount,
        timestamp_ms=at_ms,
        pull_index=0,
    )


def a_loaded_with(deaths: tuple[Death, ...], hits: tuple[DamageTakenEvent, ...]) -> LoadedRun:
    return LoadedRun(
        run=a_run(players=(a_player(),), pulls=(a_pull(0, 0, 120_000),)),
        deaths=deaths,
        damage_taken=hits,
    )


def test_a_run_with_no_deaths_yields_no_cards() -> None:
    assert build_deaths(a_loaded_with((), ())) == ()


def test_a_death_names_the_player_and_the_killing_blow() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()))[0]
    assert card.player == "Dudesons"
    assert card.killing_blow == "Frigid Roar"


def test_a_death_names_the_class_so_the_colour_is_not_the_only_signal() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), ()))[0]
    assert card.class_name == "DeathKnight"


def test_a_death_by_an_actor_not_in_the_roster_still_renders() -> None:
    card = build_deaths(a_loaded_with((a_death(99, 60_000),), ()))[0]
    assert card.class_name == "unknown class"


def test_the_run_up_holds_only_hits_on_the_player_who_died() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(2, 55_000, "Snowdrift", 800))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_stops_ten_seconds_before_the_death() -> None:
    hits = (a_hit(1, 45_000, "Old news", 100), a_hit(1, 55_000, "Frigid Roar", 900))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_excludes_hits_landing_after_the_death() -> None:
    hits = (a_hit(1, 55_000, "Frigid Roar", 900), a_hit(1, 61_000, "Posthumous", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["Frigid Roar"]


def test_the_run_up_runs_oldest_first_so_it_reads_as_a_story() -> None:
    hits = (a_hit(1, 58_000, "Second", 200), a_hit(1, 52_000, "First", 100))
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), hits))[0]
    assert [row.ability for row in card.last_ten_seconds] == ["First", "Second"]


def test_each_hit_says_how_long_before_the_death_it_landed() -> None:
    card = build_deaths(a_loaded_with((a_death(1, 60_000),), (a_hit(1, 54_200, "Roar", 900),)))[0]
    assert card.last_ten_seconds[0].seconds_before == "5.8s before"


def test_cards_come_in_the_order_the_deaths_happened() -> None:
    deaths = (a_death(1, 90_000, "Late"), a_death(1, 30_000, "Early"))
    cards = build_deaths(a_loaded_with(deaths, ()))
    assert [card.killing_blow for card in cards] == ["Early", "Late"]
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_deaths.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_deaths'`.

- [ ] **Step 3: Write the builder**

In `build.py`, add `DamageRow, DeathCard` to the model import, then:

```python
LAST_SECONDS_BEFORE_DEATH = 10.0
"""How much of the run-up to a death to show. Long enough to see the sequence, short
enough that the card stays a card."""


def _when(death: Death, run: Run) -> str:
    at = format_seconds(death.timestamp_ms / 1000) or "0:00"
    if death.pull_index is None:
        return f"{at}, between pulls"
    return f"{at}, pull {death.pull_index}"


def build_deaths(loaded: LoadedRun) -> tuple[DeathCard, ...]:
    """One card per death, oldest first, each expanded into its last ten seconds.

    Built from events rather than findings: no finding carries the damage
    run-up, which is the reason this section exists at all.
    """
    players_by_id = {player.actor_id: player for player in loaded.run.players}
    cards = []
    for death in sorted(loaded.deaths, key=lambda d: d.timestamp_ms):
        window_start = death.timestamp_ms - LAST_SECONDS_BEFORE_DEATH * 1000
        hits = sorted(
            (
                hit
                for hit in loaded.damage_taken
                if hit.actor_id == death.actor_id
                and window_start <= hit.timestamp_ms <= death.timestamp_ms
            ),
            key=lambda hit: hit.timestamp_ms,
        )
        player = players_by_id.get(death.actor_id)
        cards.append(
            DeathCard(
                player=death.player_name,
                class_name=player.class_name if player else "unknown class",
                when=_when(death, loaded.run),
                killing_blow=death.killing_blow,
                last_ten_seconds=tuple(
                    DamageRow(
                        seconds_before=(
                            f"{(death.timestamp_ms - hit.timestamp_ms) / 1000:.1f}s before"
                        ),
                        ability=hit.ability_name,
                        amount=f"{hit.amount:,}",
                    )
                    for hit in hits
                ),
            )
        )
    return tuple(cards)
```

- [ ] **Step 4: Wire it into `build_report`**

Replace `deaths=(),` with `deaths=build_deaths(loaded),`.

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_deaths.py -v`
Expected: 10 passed.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/build.py tests/domain/report/test_build_deaths.py
git commit -m "Expand each death into the ten seconds that led to it

A killing blow on its own says almost nothing: the hit that finishes a
player is rarely the one that killed them. The run-up reads as a sequence,
oldest first, which is how the player experienced it."
```

---

### Task 6: Interrupts and the per-player cards

**Files:**
- Modify: `src/wowperf/domain/report/build.py`
- Test: `tests/domain/report/test_build_players.py`

**Interfaces:**
- Consumes: `summarise_players` from `wowperf.domain.analysis.players`; `PlayerCard`, `LedgerRow`, `Section` from Task 1.
- Produces:
  - `def build_interrupts(findings: Sequence[Finding]) -> tuple[LedgerRow, ...]`
  - `def build_players(loaded, findings, parse) -> tuple[PlayerCard, ...]`
  - `def class_colour(class_name: str) -> str`
  - `build_report` now fills `interrupts` and `players`

Two rules a reviewer will check.

1. **A finding appears exactly once.** These sections take only findings with `seconds_lost is None`; anything with a seconds figure went to the ledger in Task 3.
2. **No card says "avoidable damage".** `players.py` states damage against the group median precisely because the log does not record whether a hit could have been dodged, and its finding says so in the same breath. The card carries those findings unchanged. This is a deliberate departure from design §7, recorded in the report design's §3.1.

`summarise_players(run, casts, deaths, interrupts) -> tuple[PlayerSummary, ...]` already exists and is pure. There is nothing to extract.

- [ ] **Step 1: Write the failing test**

`tests/domain/report/test_build_players.py`:

```python
# ABOUTME: Behaviour tests for the interrupts section and the per-player cards.
# ABOUTME: No card claims damage was avoidable — the log does not record that, and the analyser refuses to.

from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_interrupts, build_players, class_colour
from wowperf.domain.report.model import SectionState

from tests.domain.report.test_build_frame import a_pull, a_run


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
    )


def a_player(actor_id: int = 1, name: str = "Dudesons") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_loaded() -> LoadedRun:
    return LoadedRun(run=a_run(players=(a_player(),), pulls=(a_pull(0, 0, 120_000),)))


def ids(rows: object) -> list[str]:
    return [row.finding_id for row in rows]  # type: ignore[union-attr]


def test_the_interrupts_section_takes_its_findings() -> None:
    rows = build_interrupts((a_finding("interrupts.summary"), a_finding("interrupts.ability.0")))
    assert ids(rows) == ["interrupts.summary", "interrupts.ability.0"]


def test_the_interrupts_section_leaves_timed_findings_to_the_ledger() -> None:
    rows = build_interrupts((a_finding("compare.interrupts", seconds=40.0),))
    assert ids(rows) == []


def test_the_interrupts_section_takes_nothing_that_is_not_an_interrupt() -> None:
    rows = build_interrupts((a_finding("players.damage.0"),))
    assert ids(rows) == []


def test_one_card_per_player() -> None:
    cards = build_players(a_loaded(), (), None)
    assert [card.name for card in cards] == ["Dudesons"]


def test_a_card_names_the_class_in_text_beside_its_colour() -> None:
    card = build_players(a_loaded(), (), None)[0]
    assert card.class_name == "DeathKnight"
    assert card.colour == class_colour("DeathKnight")
    assert card.colour != card.class_name


def test_an_unknown_class_still_gets_a_colour_rather_than_an_empty_string() -> None:
    assert class_colour("Bard") == "class-unknown"


def test_a_card_carries_its_players_damage_findings() -> None:
    findings = (a_finding("players.damage.0", title="Dudesons took 2.3x the group median"),)
    card = build_players(a_loaded(), findings, None)[0]
    assert ids(card.damage_rows) == ["players.damage.0"]


def test_a_card_never_calls_damage_avoidable() -> None:
    findings = (a_finding("players.damage.0", title="Dudesons took 2.3x the group median"),)
    card = build_players(a_loaded(), findings, None)[0]
    assert "avoidable" not in " ".join(row.title + row.detail for row in card.damage_rows).lower()


def test_a_card_only_takes_damage_findings_naming_that_player() -> None:
    findings = (a_finding("players.damage.0", title="Someoneelse took 4.1x the group median"),)
    card = build_players(a_loaded(), findings, None)[0]
    assert ids(card.damage_rows) == []


def test_without_a_parse_reference_the_comparison_half_is_withheld() -> None:
    card = build_players(a_loaded(), (), None)[0]
    assert card.spell_and_talent.state is SectionState.WITHHELD
    assert card.spell_and_talent.reason
    assert card.spell_and_talent_rows == ()


def test_a_card_states_active_time_as_a_share_of_pull_time() -> None:
    card = build_players(a_loaded(), (), None)[0]
    assert "%" in card.active_time
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_build_players.py -v`
Expected: FAIL, `ImportError: cannot import name 'build_interrupts'`.

- [ ] **Step 3: Write the two builders**

In `build.py`, add `from wowperf.domain.analysis.players import summarise_players` and `PlayerCard` to the model import, then:

```python
CLASS_COLOURS = (
    "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
    "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
)
"""Classes with a palette token. A class absent here still renders, in a neutral tone.

The colour never carries meaning alone: every card prints the class name too,
because several class colours are hard to tell apart and reports get
screenshotted and recompressed.
"""

COMPARISON_PREFIXES = ("compare.spells.", "compare.talents", "compare.uptime.")
"""Finding families that belong on the subject player's card rather than in the ledger."""


def class_colour(class_name: str) -> str:
    return f"class-{class_name.lower()}" if class_name in CLASS_COLOURS else "class-unknown"


def build_interrupts(findings: Sequence[Finding]) -> tuple[LedgerRow, ...]:
    """Interrupt findings that carry no seconds. Anything timed went to the ledger."""
    return tuple(
        _ledger_row(finding)
        for finding in findings
        if finding.seconds_lost is None and finding.id.startswith("interrupts.")
    )


def build_players(
    loaded: LoadedRun, findings: Sequence[Finding], parse: ParseReference | None
) -> tuple[PlayerCard, ...]:
    """One card per player.

    Damage is stated as `players.damage.*` states it — a multiple of the group
    median, with the analyser's own caveat that this is a difference and not a
    mistake. The log does not record whether a hit could have been dodged, so
    no card here claims damage was avoidable.
    """
    comparison_section = _section_for(findings, PARSE_UNAVAILABLE_ID, parse is not None)
    subject_name = parse.row.character_name.casefold() if parse else ""

    untimed = [finding for finding in findings if finding.seconds_lost is None]
    damage = [finding for finding in untimed if finding.id.startswith("players.damage.")]
    comparison = [
        finding
        for finding in untimed
        if any(finding.id.startswith(prefix) for prefix in COMPARISON_PREFIXES)
        and not finding.id.endswith(".unavailable")
    ]

    cards = []
    for summary in summarise_players(
        loaded.run, loaded.casts, loaded.deaths, loaded.interrupts
    ):
        mine = tuple(
            _ledger_row(finding)
            for finding in damage
            if finding.title.startswith(summary.name)
        )
        is_subject = summary.name.casefold() == subject_name
        cards.append(
            PlayerCard(
                name=summary.name,
                class_name=summary.class_name,
                spec=summary.spec,
                colour=class_colour(summary.class_name),
                active_time=(
                    f"{summary.active_seconds:.0f}s in pulls "
                    f"({summary.activity_percent:.0f}%)"
                ),
                deaths=summary.deaths,
                kicks=summary.interrupts,
                damage_rows=mine,
                spell_and_talent=comparison_section,
                spell_and_talent_rows=(
                    tuple(_ledger_row(finding) for finding in comparison) if is_subject else ()
                ),
            )
        )
    return tuple(cards)
```

- [ ] **Step 4: Wire both into `build_report`**

Replace `interrupts=(),` with `interrupts=build_interrupts(findings),` and `players=(),` with `players=build_players(loaded, findings, parse),`.

Then extend the withheld list, just below the timeline's entry:

```python
    comparison_section = _section_for(findings, PARSE_UNAVAILABLE_ID, parse is not None)
    if comparison_section.state is SectionState.WITHHELD:
        withheld.append(f"Spell and talent comparison: {comparison_section.reason}")
```

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/ -v`
Expected: 11 new tests pass and every earlier report test still passes.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/build.py tests/domain/report/test_build_players.py
git commit -m "Give each player a card, without calling any damage avoidable

The analyser states damage against the group median because the log does
not record whether a hit could have been dodged, and the card follows the
analyser rather than the design section that asked for 'avoidable damage'.
A page that names a person should not assert something about them that
nothing measured."
```

---

### Task 7: The render adapter and the document skeleton

**Files:**
- Create: `src/wowperf/adapters/render/__init__.py`, `src/wowperf/adapters/render/html.py`, `src/wowperf/adapters/render/report.html.j2`
- Test: `tests/adapters/render/__init__.py`, `tests/adapters/render/test_html.py`

**Interfaces:**
- Consumes: `Report` and every sub-value from Task 1.
- Produces: `def render(report: Report) -> str` in `wowperf.adapters.render.html`

This task delivers the document: doctype, head, the dark palette, the badge markup, and sections 1, 2, 3 and 8. Task 8 adds the remaining four sections to the same template.

**`autoescape=True` is not optional.** Player names, pack names and killing blows come from an external API and land in HTML. Turning it off, or marking a value `|safe`, would let a report name execute markup.

The narrative is the one field a person authored, and it is still escaped. It renders as pre-wrapped text, not as Markdown — rendering Markdown would mean shipping a second dependency and a second escaping story for a paragraph of prose.

- [ ] **Step 1: Write the failing test**

`tests/adapters/render/__init__.py` is empty. `tests/adapters/render/test_html.py`:

```python
# ABOUTME: Behaviour tests for the HTML adapter: self-contained, escaped, every section present.
# ABOUTME: Self-containment is asserted rather than trusted — the file must work offline from disk.

import re

from wowperf.adapters.render.html import render
from wowperf.domain.report.model import (
    Badge,
    Header,
    LedgerRow,
    Provenance,
    Report,
    Section,
    SectionState,
    Timeline,
)

PRESENT = Section(state=SectionState.PRESENT)


def a_row(finding_id: str = "time.gap.0", **overrides: object) -> LedgerRow:
    fields: dict[str, object] = {
        "finding_id": finding_id,
        "title": "A 41 second gap after pull 7",
        "detail": "Travel, not combat.",
        "badge": Badge(label="measured", tint="badge-measured"),
        "seconds": "0:41",
        "nests_inside": None,
        "evidence": ("next pull begins at Loa Speaker Nanea",),
    }
    fields.update(overrides)
    return LedgerRow(**fields)  # type: ignore[arg-type]


def a_report(**overrides: object) -> Report:
    fields: dict[str, object] = {
        "header": Header(
            dungeon="Den of Nalorakk",
            keystone_level=16,
            affixes=("Tyrannical",),
            result="Timed by 2:14",
        ),
        "narrative": None,
        "ledger_decomposition": (),
        "ledger_losses": (),
        "timeline": Timeline(section=Section(state=SectionState.WITHHELD, reason="no reference")),
        "deaths": (),
        "interrupts": (),
        "players": (),
        "provenance": Provenance(
            report_code="abc123", fight_id=36, fetched_at="2026-09-05 14:02"
        ),
    }
    fields.update(overrides)
    return Report(**fields)  # type: ignore[arg-type]


def test_the_document_is_html() -> None:
    assert render(a_report()).lstrip().lower().startswith("<!doctype html>")


def test_nothing_is_fetched_from_anywhere() -> None:
    html = render(a_report())
    assert "<script" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html
    assert "@import" not in html
    assert "//fonts." not in html


def test_every_href_is_a_fragment_or_a_report_link_the_reader_asked_for() -> None:
    html = render(a_report())
    for href in re.findall(r'href="([^"]*)"', html):
        assert href.startswith("#"), href


def test_the_header_is_rendered() -> None:
    html = render(a_report())
    assert "Den of Nalorakk" in html
    assert "Timed by 2:14" in html


def test_a_run_with_no_narrative_renders_no_narrative_section() -> None:
    assert "id=\"narrative\"" not in render(a_report())


def test_a_narrative_is_rendered_when_present() -> None:
    html = render(a_report(narrative="Both losses were travel, not damage."))
    assert "Both losses were travel, not damage." in html


def test_a_narrative_cannot_smuggle_markup_into_the_page() -> None:
    html = render(a_report(narrative="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_a_pack_name_from_the_api_cannot_smuggle_markup_either() -> None:
    html = render(a_report(ledger_losses=(a_row(title="<img onerror=x>"),)))
    assert "<img onerror=x>" not in html
    assert "&lt;img" in html


def test_a_ledger_row_shows_its_badge_as_a_word() -> None:
    html = render(a_report(ledger_losses=(a_row(),)))
    assert "measured" in html


def test_a_nested_row_says_what_contains_it() -> None:
    html = render(a_report(ledger_losses=(a_row(nests_inside="time.residual"),)))
    assert "time.residual" in html


def test_a_withheld_section_renders_its_heading_and_its_reason() -> None:
    html = render(a_report())
    assert "Aligned timeline" in html
    assert "no reference" in html


def test_provenance_names_the_report_and_when_it_was_fetched() -> None:
    html = render(a_report())
    assert "abc123" in html
    assert "2026-09-05 14:02" in html


def test_the_confidence_legend_explains_all_three_badges() -> None:
    html = render(a_report())
    for word in ("measured", "derived", "inferred"):
        assert word in html
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.adapters.render'`.

- [ ] **Step 3: Write the adapter**

`src/wowperf/adapters/render/__init__.py` is empty. `src/wowperf/adapters/render/html.py`:

```python
# ABOUTME: Turns a Report into one self-contained HTML string. The only module importing jinja2.
# ABOUTME: The template loops and escapes; every decision was already made in domain/report/build.py.

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from wowperf.domain.report.model import Report

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "report.html.j2"


def _environment() -> Environment:
    """Autoescaping is mandatory, not a default worth overriding.

    Player names, pack names and killing blows all come from an external API
    and all land in HTML. A `|safe` anywhere in this template would let a
    character name execute markup in whoever opens the file.
    """
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(default_for_string=True, default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(report: Report) -> str:
    """One self-contained HTML document: no script, no network, no external font."""
    return _environment().get_template(TEMPLATE_NAME).render(report=report)
```

- [ ] **Step 4: Write the template skeleton**

`src/wowperf/adapters/render/report.html.j2`. Sections 4 to 7 are added in Task 8; their placeholders below are real headings with empty bodies, not TODOs.

```jinja
{# The report: one self-contained file. No script, no network, no external font. #}
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ report.header.dungeon }} +{{ report.header.keystone_level }}</title>
<style>
:root {
  --ink: #e8e6e3; --ink-dim: #a8a29b; --ink-faint: #6f6a64;
  --page: #16181c; --card: #1e2126; --line: #2c3038;
  --ours: #6ba3d6; --theirs: #7d8590; --extra: #d6a55c;
  --badge-measured: #6fae7e; --badge-derived: #6ba3d6; --badge-inferred: #d6a55c;
  --class-deathknight: #c41f3b; --class-demonhunter: #a330c9; --class-druid: #ff7d0a;
  --class-evoker: #33937f; --class-hunter: #abd473; --class-mage: #69ccf0;
  --class-monk: #00ff96; --class-paladin: #f58cba; --class-priest: #ffffff;
  --class-rogue: #fff569; --class-shaman: #0070de; --class-warlock: #9482c9;
  --class-warrior: #c79c6e; --class-unknown: #a8a29b;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 64px; background: var(--page); color: var(--ink);
  font: 15px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 760px; margin: 0 auto; }
h1 { font-size: 24px; font-weight: 600; margin: 0 0 4px; }
h2 { font-size: 17px; font-weight: 600; margin: 40px 0 10px; padding-bottom: 6px;
  border-bottom: 1px solid var(--line); }
h3 { font-size: 15px; font-weight: 600; margin: 0 0 6px; }
p { margin: 0 0 10px; }
.sub { color: var(--ink-dim); font-size: 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: 12px 14px; margin: 0 0 10px; }
.row-head { display: flex; align-items: baseline; gap: 10px; }
.row-head h3 { flex: 1; }
.cost { font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
.badge { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
  padding: 2px 7px; border-radius: 3px; white-space: nowrap; color: var(--page); }
.badge-measured { background: var(--badge-measured); }
.badge-derived { background: var(--badge-derived); }
.badge-inferred { background: var(--badge-inferred); }
.detail { color: var(--ink-dim); font-size: 14px; margin: 4px 0 0; }
.evidence { margin: 6px 0 0; padding: 0; list-style: none; color: var(--ink-faint); font-size: 13px; }
.evidence li::before { content: "· "; }
.nests { color: var(--ink-faint); font-size: 13px; margin: 4px 0 0; }
.withheld { color: var(--ink-dim); font-style: italic; }
.narrative { border-left: 3px solid var(--ours); padding: 2px 0 2px 14px;
  white-space: pre-wrap; margin: 0 0 10px; }
.legend { color: var(--ink-faint); font-size: 13px; }
</style>
</head>
<body>
<main>

<h1>{{ report.header.dungeon }} +{{ report.header.keystone_level }}</h1>
<p class="sub">{{ report.header.result }}{% if report.header.affixes %} · {{ report.header.affixes|join(", ") }}{% endif %}</p>
{% for warning in report.header.warnings %}
<p class="withheld">{{ warning }}</p>
{% endfor %}

{% if report.narrative %}
<h2 id="narrative">What this run says</h2>
<div class="narrative">{{ report.narrative }}</div>
<p class="legend">Interpretation, written from the findings below.</p>
{% endif %}

{% macro ledger_row(row) %}
<div class="card">
  <div class="row-head">
    <h3>{{ row.title }}</h3>
    {% if row.seconds %}<span class="cost">{{ row.seconds }}</span>{% endif %}
    <span class="badge {{ row.badge.tint }}">{{ row.badge.label }}</span>
  </div>
  <p class="detail">{{ row.detail }}</p>
  {% if row.nests_inside %}
  <p class="nests">Already counted inside {{ row.nests_inside }}.</p>
  {% endif %}
  {% if row.evidence %}
  <ul class="evidence">{% for item in row.evidence %}<li>{{ item }}</li>{% endfor %}</ul>
  {% endif %}
</div>
{% endmacro %}

<h2 id="ledger">Where the time went</h2>
{% for row in report.ledger_decomposition %}
{{ ledger_row(row) }}
{% endfor %}
{% if report.ledger_losses %}
<p class="sub">Ranked losses. These are not additive — each says what already contains it.</p>
{% for row in report.ledger_losses %}
{{ ledger_row(row) }}
{% endfor %}
{% endif %}

<h2 id="timeline">Aligned timeline</h2>
{% if report.timeline.section.state.value == "withheld" %}
<p class="withheld">{{ report.timeline.section.reason }}</p>
{% endif %}

<h2 id="deaths">Deaths</h2>

<h2 id="interrupts">Interrupts</h2>

<h2 id="players">Players</h2>

<h2 id="provenance">Provenance</h2>
<p class="sub">Report {{ report.provenance.report_code }}, fight {{ report.provenance.fight_id }},
fetched {{ report.provenance.fetched_at }}.</p>
{% for line in report.provenance.withheld %}
<p class="withheld">{{ line }}</p>
{% endfor %}
<p class="legend">
<span class="badge badge-measured">measured</span> read from the log, or arithmetic over logged facts.
<span class="badge badge-derived">derived</span> reconstructed by a documented rule, or a modelling choice that could be wrong.
<span class="badge badge-inferred">inferred</span> requires an assumption the log cannot confirm.
</p>

</main>
</body>
</html>
```

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html.py -v`
Expected: 13 passed.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/adapters/render/ tests/adapters/render/
git commit -m "Render the report's frame as one self-contained document

The file has to open from disk, offline, after being posted to a chat
client, so nothing is fetched: no script, no webfont, no stylesheet from
anywhere. Autoescaping stays on because player and pack names come from an
external API and land straight in the markup."
```

---

### Task 8: The remaining four sections, and the timeline SVG

**Files:**
- Modify: `src/wowperf/adapters/render/report.html.j2`
- Test: `tests/adapters/render/test_html_sections.py`

**Interfaces:**
- Consumes: the template and `render` from Task 7; `Timeline`, `DeathCard`, `PlayerCard` from Task 1.
- Produces: sections 4 to 7 rendered.

The timeline is inline SVG built entirely from numbers `build_timeline` already computed. **The template does no arithmetic** — no `+`, no `*`, no filters that compute. If a coordinate is needed that the view model does not carry, it belongs in `build_timeline`, not here.

Each block carries a `<title>` child so the pack name appears on hover.

- [ ] **Step 1: Write the failing test**

`tests/adapters/render/test_html_sections.py`:

```python
# ABOUTME: Behaviour tests for the report's four data sections and the inline timeline SVG.
# ABOUTME: The template does no arithmetic: every coordinate here was computed in build_timeline.

from wowperf.adapters.render.html import render
from wowperf.domain.report.model import (
    DamageRow,
    DeathCard,
    PlayerCard,
    Section,
    SectionState,
    Timeline,
    TimelineBlock,
    TimelineTrack,
)

from tests.adapters.render.test_html import a_report, a_row

PRESENT = Section(state=SectionState.PRESENT)


def a_timeline() -> Timeline:
    return Timeline(
        section=PRESENT,
        ours=TimelineTrack(
            caption="Ours — 31:48",
            blocks=(
                TimelineBlock(label="Loa Speaker Nanea", x=46.0, width=50.0, is_boss=True,
                              kind="matched"),
                TimelineBlock(label="Frostbound trio", x=120.0, width=20.0, is_boss=False,
                              kind="extra"),
            ),
        ),
        theirs=TimelineTrack(
            caption="Reference — 27:30",
            blocks=(
                TimelineBlock(label="Shale Prowlers", x=60.0, width=15.0, is_boss=False,
                              kind="skipped"),
            ),
        ),
        ticks=((46.0, "0:00"), (240.0, "10:00")),
        width=680.0,
        height=208.0,
    )


def test_the_timeline_renders_as_inline_svg() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<svg" in html
    assert 'viewBox="0 0 680.0 208.0"' in html


def test_every_block_carries_its_pack_name_as_a_tooltip() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<title>Loa Speaker Nanea</title>" in html
    assert "<title>Frostbound trio</title>" in html


def test_a_boss_block_is_distinguishable_from_a_trash_block() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "block-boss" in html


def test_an_extra_pack_and_a_skipped_pack_are_marked_differently() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "block-extra" in html
    assert "block-skipped" in html


def test_both_captions_are_rendered() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "Ours — 31:48" in html
    assert "Reference — 27:30" in html


def test_the_axis_ticks_are_rendered() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert ">10:00<" in html


def test_a_death_card_shows_the_run_up() -> None:
    card = DeathCard(
        player="Dudesons",
        class_name="DeathKnight",
        when="12:04, pull 5",
        killing_blow="Frigid Roar",
        last_ten_seconds=(
            DamageRow(seconds_before="5.8s before", ability="Snowdrift", amount="82,410"),
        ),
    )
    html = render(a_report(deaths=(card,)))
    assert "Frigid Roar" in html
    assert "Snowdrift" in html
    assert "5.8s before" in html


def test_a_run_with_no_deaths_says_so_rather_than_showing_an_empty_heading() -> None:
    html = render(a_report(deaths=()))
    assert "No deaths" in html


def test_the_interrupts_section_renders_its_rows() -> None:
    html = render(a_report(interrupts=(a_row("interrupts.ability.0", title="Snowdrift, 3 casts"),)))
    assert "Snowdrift, 3 casts" in html


def test_a_player_card_prints_the_class_name_beside_the_colour() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        active_time="412s in pulls (38%)",
        deaths=1,
        kicks=7,
        spell_and_talent=Section(state=SectionState.WITHHELD, reason="no ranked parse"),
    )
    html = render(a_report(players=(card,)))
    assert "DeathKnight" in html
    assert "Blood" in html
    assert "class-deathknight" in html


def test_a_player_cards_withheld_comparison_states_its_reason() -> None:
    card = PlayerCard(
        name="Dudesons",
        class_name="DeathKnight",
        spec="Blood",
        colour="class-deathknight",
        active_time="412s in pulls (38%)",
        deaths=0,
        kicks=0,
        spell_and_talent=Section(state=SectionState.WITHHELD, reason="no ranked parse was found"),
    )
    html = render(a_report(players=(card,)))
    assert "no ranked parse was found" in html


def test_the_template_still_fetches_nothing() -> None:
    html = render(a_report(timeline=a_timeline()))
    assert "<script" not in html.lower()
    assert "https://" not in html
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_sections.py -v`
Expected: FAIL — the timeline SVG, the death cards and the player cards are not rendered yet.

- [ ] **Step 3: Add the section styles**

In the template's `<style>` block, before the closing `</style>`:

```css
.track-label { fill: var(--ink-dim); font-size: 12px; }
.tick { stroke: var(--line); stroke-width: 0.5; }
.tick-label { fill: var(--ink-faint); font-size: 11px; }
.block { fill: var(--ours); }
.block-theirs { fill: var(--theirs); }
.block-extra { fill: var(--extra); }
.block-skipped { fill: none; stroke: var(--ink-dim); stroke-width: 1; stroke-dasharray: 3 2; }
.block-boss { stroke: var(--ink); stroke-width: 1; }
.death-when { color: var(--ink-dim); font-size: 13px; }
.runup { width: 100%; border-collapse: collapse; margin: 8px 0 0; font-size: 13px; }
.runup td { padding: 3px 8px 3px 0; border-top: 1px solid var(--line); color: var(--ink-dim); }
.runup td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.player-head { display: flex; align-items: baseline; gap: 8px; }
.swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.stats { color: var(--ink-dim); font-size: 14px; margin: 4px 0 0; }
```

- [ ] **Step 4: Replace the four empty headings**

Replace the `<h2 id="timeline">` block and the three bare headings after it with:

```jinja
<h2 id="timeline">Aligned timeline</h2>
{% if report.timeline.section.state.value == "withheld" %}
<p class="withheld">{{ report.timeline.section.reason }}</p>
{% else %}
<p class="sub">Blocks are pulls. The space between them is travel.</p>
<svg width="100%" viewBox="0 0 {{ report.timeline.width }} {{ report.timeline.height }}"
     role="img" aria-label="Both runs on one elapsed-time axis">
  {% for x, label in report.timeline.ticks %}
  <line class="tick" x1="{{ x }}" y1="46" x2="{{ x }}" y2="176"></line>
  <text class="tick-label" x="{{ x }}" y="192" text-anchor="middle">{{ label }}</text>
  {% endfor %}
  {% for track, y, extra_class in [(report.timeline.ours, 58, ""), (report.timeline.theirs, 132, "block-theirs")] %}
  {% if track %}
  <text class="track-label" x="46" y="{{ y }}" dy="-10">{{ track.caption }}</text>
  {% for block in track.blocks %}
  <rect x="{{ block.x }}" y="{{ y }}" width="{{ block.width }}" height="26" rx="2"
        class="{% if block.kind == 'extra' %}block-extra{% elif block.kind == 'skipped' %}block-skipped{% else %}block {{ extra_class }}{% endif %}{% if block.is_boss %} block-boss{% endif %}">
    <title>{{ block.label }}</title>
  </rect>
  {% endfor %}
  {% endif %}
  {% endfor %}
</svg>
{% endif %}

<h2 id="deaths">Deaths</h2>
{% if not report.deaths %}
<p class="sub">No deaths.</p>
{% endif %}
{% for death in report.deaths %}
<div class="card">
  <div class="row-head">
    <h3>{{ death.player }} — {{ death.killing_blow }}</h3>
    <span class="death-when">{{ death.when }}</span>
  </div>
  <p class="detail">{{ death.class_name }}</p>
  {% if death.last_ten_seconds %}
  <table class="runup">
    {% for hit in death.last_ten_seconds %}
    <tr><td>{{ hit.seconds_before }}</td><td>{{ hit.ability }}</td><td>{{ hit.amount }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}
</div>
{% endfor %}

<h2 id="interrupts">Interrupts</h2>
{% if not report.interrupts %}
<p class="sub">Nothing to report.</p>
{% endif %}
{% for row in report.interrupts %}
{{ ledger_row(row) }}
{% endfor %}

<h2 id="players">Players</h2>
{% for player in report.players %}
<div class="card">
  <div class="player-head">
    <span class="swatch" style="background: var(--{{ player.colour }})"></span>
    <h3>{{ player.name }}</h3>
    <span class="sub">{{ player.class_name }} {{ player.spec }}</span>
  </div>
  <p class="stats">{{ player.active_time }} · {{ player.deaths }} death{{ "" if player.deaths == 1 else "s" }} · {{ player.kicks }} interrupt{{ "" if player.kicks == 1 else "s" }}</p>
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

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/ -v`
Expected: 12 new tests pass and Task 7's 13 still pass.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/adapters/render/report.html.j2 tests/adapters/render/test_html_sections.py
git commit -m "Draw the timeline, the deaths, the interrupts and the players

Every coordinate in the SVG was computed in build_timeline, so the
template only loops over numbers. Pack names go in title children rather
than inside the blocks, because a block for a forty-second pull on a
thirty-minute axis is eight pixels wide."
```

---

### Task 9: The invariants, and one tiny golden file

**Files:**
- Create: `tests/adapters/render/test_html_invariants.py`, `tests/adapters/render/golden/minimal.html`
- Test: the two files above

**Interfaces:**
- Consumes: `render` from Task 7; `build_report` from Tasks 2 to 6.
- Produces: nothing importable. This task adds the tests that hold the whole report to its rules.

These are the assertions that catch what a per-section test cannot: that the page is genuinely offline, that no finding is reported twice, and that no structural change slipped in unnoticed.

**The golden file is deliberately tiny** — two pulls, one player, one finding. A full-page golden over a realistic run would churn on every CSS edit and train everyone to approve it unread, which is worse than having no test.

Regenerate the golden with `uv run pytest tests/adapters/render/test_html_invariants.py --golden-update` only after reading the diff.

- [ ] **Step 1: Write the failing test**

`tests/adapters/render/test_html_invariants.py`:

```python
# ABOUTME: Whole-page rules: offline, every finding once, sections in order, and one golden file.
# ABOUTME: The golden fixture is tiny on purpose — a 2000-line diff is a test nobody reads.

import re
from pathlib import Path

import pytest

from wowperf.adapters.render.html import render
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_report

from tests.domain.report.test_build_frame import FETCHED, a_pull, a_run

GOLDEN = Path(__file__).parent / "golden" / "minimal.html"

SECTION_ORDER = ["ledger", "timeline", "deaths", "interrupts", "players", "provenance"]


def minimal_loaded() -> LoadedRun:
    return LoadedRun(
        run=a_run(
            players=(
                Player(
                    actor_id=1,
                    name="Uglymage",
                    class_name="Mage",
                    spec="Arcane",
                    item_level=680,
                ),
            ),
            pulls=(a_pull(0, 0, 60_000), a_pull(1, 120_000, 200_000, encounter_id=12825)),
        ),
        casts=(CastEvent(actor_id=1, ability_id=1, ability_name="Arcane Blast",
                         timestamp_ms=10_000, pull_index=0),),
        deaths=(Death(player_name="Uglymage", actor_id=1, timestamp_ms=50_000,
                      killing_blow="Frigid Roar", pull_index=0),),
        damage_taken=(DamageTakenEvent(actor_id=1, ability_id=2, ability_name="Snowdrift",
                                       amount=82_410, timestamp_ms=45_000, pull_index=0),),
    )


def minimal_findings() -> tuple[Finding, ...]:
    return (
        Finding(
            id="time.residual",
            title="Time outside pulls",
            detail="Travel, waiting and run-backs.",
            confidence=Confidence.MEASURED,
            seconds_lost=300.0,
        ),
        Finding(
            id="time.gap.0",
            title="A 41 second gap after pull 0",
            detail="Travel, not combat.",
            confidence=Confidence.MEASURED,
            seconds_lost=41.0,
            evidence=("next pull begins at Pack 1",),
        ),
        Finding(
            id="interrupts.summary",
            title="Three enemy casts went uninterrupted",
            detail="Grouped by spell.",
            confidence=Confidence.DERIVED,
        ),
    )


def minimal_html() -> str:
    return render(build_report(minimal_loaded(), minimal_findings(), None, None, None, FETCHED))


def test_the_page_fetches_nothing_at_all() -> None:
    html = minimal_html()
    assert "<script" not in html.lower()
    assert not re.search(r'(src|href)="(?!#)', html)
    assert "http://" not in html and "https://" not in html
    assert "@import" not in html


def test_every_section_appears_in_the_order_the_design_fixes() -> None:
    html = minimal_html()
    positions = [html.index(f'id="{name}"') for name in SECTION_ORDER]
    assert positions == sorted(positions)


def test_a_report_without_a_narrative_renders_seven_sections_not_eight() -> None:
    html = minimal_html()
    assert 'id="narrative"' not in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER)


def test_a_report_with_a_narrative_renders_all_eight() -> None:
    html = render(
        build_report(minimal_loaded(), minimal_findings(), None, None, "A sentence.", FETCHED)
    )
    assert 'id="narrative"' in html
    assert len(re.findall(r"<h2 ", html)) == len(SECTION_ORDER) + 1


def test_every_finding_reaches_the_page() -> None:
    html = minimal_html()
    for finding in minimal_findings():
        assert finding.title in html, finding.id


def test_no_finding_reaches_the_page_twice() -> None:
    html = minimal_html()
    for finding in minimal_findings():
        assert html.count(finding.title) == 1, finding.id


def test_every_withheld_section_gives_a_reason() -> None:
    html = minimal_html()
    # The timeline is withheld here: no speed reference was passed.
    heading = html.index('id="timeline"')
    deaths = html.index('id="deaths"')
    assert 'class="withheld"' in html[heading:deaths]


def test_the_report_carries_no_total_row() -> None:
    report = build_report(minimal_loaded(), minimal_findings(), None, None, None, FETCHED)
    assert not any(field.startswith("total") for field in report.model_fields)
    template = (
        Path(__file__).parents[2] / "src" / "wowperf" / "adapters" / "render" / "report.html.j2"
    ).read_text(encoding="utf-8")
    assert "|sum" not in template
    assert "sum(" not in template


def test_the_rendered_page_matches_the_golden_file(pytestconfig: pytest.Config) -> None:
    html = minimal_html()
    if pytestconfig.getoption("--golden-update"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(html, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert html == GOLDEN.read_text(encoding="utf-8"), (
        "The rendered report changed. Read the diff, then regenerate with "
        "`uv run pytest tests/adapters/render/test_html_invariants.py --golden-update`."
    )
```

- [ ] **Step 2: Add the `--golden-update` flag**

In `tests/conftest.py` — create it if it does not exist, with the two ABOUTME lines:

```python
# ABOUTME: Shared pytest configuration. Currently only the golden-file update flag.
# ABOUTME: Regenerating a golden file is a deliberate act, so it needs a deliberate flag.

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--golden-update",
        action="store_true",
        default=False,
        help="Rewrite golden files from the current output. Read the diff first.",
    )
```

- [ ] **Step 3: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_invariants.py -v`
Expected: eight pass; `test_the_rendered_page_matches_the_golden_file` FAILS with `FileNotFoundError`, because the golden file does not exist yet.

- [ ] **Step 4: Generate the golden file, then read it**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/test_html_invariants.py --golden-update`

Then **open `tests/adapters/render/golden/minimal.html` in a browser and look at it.** This is the first time anyone sees the report. Check: the headings read in order, the badge is legible against the dark background, the death card shows its run-up, the withheld timeline says why. If any of it is wrong, fix the template and regenerate — do not commit a golden file you have not looked at.

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/adapters/render/ -v`
Expected: 9 invariant tests pass alongside Tasks 7 and 8.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add tests/conftest.py tests/adapters/render/test_html_invariants.py tests/adapters/render/golden/
git commit -m "Hold the whole page to its rules, with a golden file small enough to read

Self-containment is the report's one hard promise, so it is asserted
rather than trusted. The golden fixture is two pulls and one player on
purpose: a full-page snapshot of a real run would churn on every style
edit until nobody read the diff, which is worse than having no test."
```

---

### Task 10: The command writes the report

**Files:**
- Modify: `src/wowperf/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_report` from Tasks 2 to 6; `render` from Tasks 7 and 8.
- Produces: `analyze` gains `--narrative` and writes `<code>-<fight>.html` beside the JSON.

Three rules a reviewer will check by running the command.

1. **The HTML is written every time**, on the same paths as the JSON — including `--no-compare`, where most sections are withheld and say so.
2. **A `--narrative` path that cannot be read is an error before any fetching.** A typo must cost nothing, and must never silently produce a report with no narrative.
3. **`fetched_at` is passed in**, not read inside the domain. `datetime.now()` belongs in the CLI.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`, following the file's existing fixture conventions:

```python
def test_analyze_writes_an_html_report_beside_the_findings(tmp_path: Path) -> None:
    transport, _calls = build_analyze_transport()
    result = run_analyze(tmp_path, transport)
    assert result.exit_code == 0
    written = tmp_path / "out" / "abc123-1.html"
    assert written.exists()
    assert written.read_text(encoding="utf-8").lstrip().lower().startswith("<!doctype html>")


def test_the_html_report_fetches_nothing_from_the_network(tmp_path: Path) -> None:
    transport, _calls = build_analyze_transport()
    run_analyze(tmp_path, transport)
    html = (tmp_path / "out" / "abc123-1.html").read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    assert "https://" not in html


def test_no_compare_still_writes_a_report(tmp_path: Path) -> None:
    transport, _calls = build_analyze_transport()
    result = run_analyze(tmp_path, transport, extra_args=["--no-compare"])
    assert result.exit_code == 0
    assert (tmp_path / "out" / "abc123-1.html").exists()


def test_a_narrative_file_reaches_the_report(tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("Both of your largest losses were travel.", encoding="utf-8")
    transport, _calls = build_analyze_transport()
    run_analyze(tmp_path, transport, extra_args=["--narrative", str(notes)])
    html = (tmp_path / "out" / "abc123-1.html").read_text(encoding="utf-8")
    assert "Both of your largest losses were travel." in html


def test_a_missing_narrative_file_fails_before_anything_is_fetched(tmp_path: Path) -> None:
    transport, calls = build_analyze_transport()
    result = run_analyze(
        tmp_path, transport, extra_args=["--narrative", str(tmp_path / "absent.md")]
    )
    assert result.exit_code == 1
    assert "absent.md" in result.output
    # The whole point: a typo must not cost an API round trip.
    assert calls == []
```

`run_analyze` is the file's existing helper. If it does not yet accept `extra_args`, widen it:

```python
def run_analyze(
    tmp_path: Path,
    transport: httpx.MockTransport,
    extra_args: list[str] | None = None,
) -> Result:
```

and append `extra_args or []` to the argument list it builds. Every existing call site passes no `extra_args` and is unaffected. **If widening it changes what any existing test asserts, stop and report that rather than adjusting the assertion.**

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -k "html or narrative" -v`
Expected: FAIL — `analyze` has no `--narrative` option and writes no HTML.

- [ ] **Step 3: Add the option and read the file first**

In `src/wowperf/cli.py`, add to the imports:

```python
from datetime import datetime

from wowperf.adapters.render.html import render
from wowperf.domain.report.build import build_report
```

Add the option to `analyze`'s signature, after `no_compare`:

```python
    narrative: Path | None = typer.Option(
        None, help="Markdown notes to render as the report's interpretation section"
    ),
```

Then, as the **first** statement inside the `try:` block, before `parse_report_url`:

```python
        # Read this before anything is fetched: a typo in the path must cost
        # nothing, and must never quietly produce a report with no narrative.
        narrative_text = narrative.read_text(encoding="utf-8") if narrative else None
```

`OSError` is already in the caught tuple, so a missing file exits 1 with the path in the message.

- [ ] **Step 4: Write the report beside the JSON**

After the existing `written.write_text(...)` line:

```python
    report_file = out / f"{run.report_code}-{run.fight_id}.html"
    report_file.write_text(
        render(
            build_report(
                loaded,
                findings,
                speed,
                parse,
                narrative_text,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        ),
        encoding="utf-8",
    )
    typer.echo(f"report written to {report_file}")
```

`datetime.now()` lives here because the domain reads no clock: `build_report` takes the timestamp as an argument so the same inputs always render the same report.

- [ ] **Step 5: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v`
Expected: the five new tests pass, and every pre-existing CLI test still passes.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/cli.py tests/test_cli.py
git commit -m "Write the report beside the findings on every run

One command and one code path, so the HTML can never be stale relative to
the JSON it was built from. The narrative file is read before anything is
fetched: a mistyped path should cost nothing, and should never quietly
produce a report missing the section the reader asked for."
```

---

### Task 11: Pack names before map coordinates

**Files:**
- Modify: `src/wowperf/domain/analysis/timeline.py`, `src/wowperf/domain/analysis/trash.py`
- Test: `tests/domain/analysis/test_timeline.py`, `tests/domain/analysis/test_trash.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change. Two evidence strings gain the pack name.

`comparison/route.py` already leads its evidence with `pull.name` before the map coordinates. These two analysers still print only `map position x=488860, y=467099`, which was tolerable in a JSON blob and is not on a page a person reads. This aligns all three.

`timeline.py`'s gap finding describes the pull that comes *after* the gap, so the name it needs is that pull's.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/analysis/test_timeline.py`:

```python
def test_a_gaps_evidence_names_the_pack_it_leads_to() -> None:
    run = a_run(pulls=(a_pull(0, 0, 60_000), a_pull(1, 200_000, 260_000, name="Loa Speaker Nanea")))
    findings = decompose_time(run, (), a_season())
    gaps = [f for f in findings if f.id.startswith("time.gap.")]
    assert gaps
    assert gaps[0].evidence[0] == "Loa Speaker Nanea"
```

Add to `tests/domain/analysis/test_trash.py`:

```python
def test_a_slow_pulls_evidence_names_the_pack() -> None:
    run = a_run(pulls=(a_pull(0, 0, 300_000, name="Shale Prowlers"),))
    findings = analyse_trash(run, ())
    slow = [f for f in findings if f.id.startswith("trash.pull.")]
    assert slow
    assert slow[0].evidence[0] == "Shale Prowlers"
```

Both test files' `a_pull` helpers need a `name` argument if they do not already have one. Widen them with `name: str = "Pack"` and pass it through; existing call sites are unaffected.

- [ ] **Step 2: Run them to watch them fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/test_timeline.py tests/domain/analysis/test_trash.py -k "names_the_pack" -v`
Expected: FAIL — the first evidence line is the map position.

- [ ] **Step 3: Put the name first in both**

In `src/wowperf/domain/analysis/timeline.py`, the gap finding's `evidence` becomes:

```python
                evidence=(
                    next_pull.name,
                    f"next pull begins at map position x={gap.x}, y={gap.y}",
                ),
```

where `next_pull` is the pull at `gap.after_pull_index + 1`. Look it up just above the `Finding(...)` construction:

```python
            next_pull = run.pulls[gap.after_pull_index + 1]
```

In `src/wowperf/domain/analysis/trash.py`:

```python
                    evidence=(pull.name, f"map position x={pull.x}, y={pull.y}"),
```

- [ ] **Step 4: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/analysis/ -v`
Expected: the two new tests pass and every existing analyser test still passes.

- [ ] **Step 5: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/analysis/timeline.py src/wowperf/domain/analysis/trash.py tests/domain/analysis/
git commit -m "Name the pack before its map coordinates

A reader cannot do anything with 'x=488860, y=467099'. The route
comparison already leads with the pack name and these two did not, which
mattered little in a JSON blob and matters now that the same strings are
rendered onto a page."
```

---

### Task 12: End to end, and the repository description

**Files:**
- Create: `tests/e2e/test_report_e2e.py`
- Modify: `CLAUDE.md`
- Test: the file above, marked `e2e` and deselected by default

**Interfaces:**
- Consumes: everything.
- Produces: an `e2e`-marked test proving the report renders from a real run, and a corrected repository description.

This test costs nothing beyond a normal compared analysis: every response it needs is already cached, and it fetches nothing new.

- [ ] **Step 1: Write the test**

`tests/e2e/test_report_e2e.py`:

```python
# ABOUTME: End-to-end report rendering against a real run; no mocks, real credentials.
# ABOUTME: Excluded from the default suite because it needs a network and spends API quota.

import os
import re
from pathlib import Path

import pytest

from wowperf.adapters.render.html import render
from wowperf.cli import build_repository
from wowperf.domain.analysis.service import analyse
from wowperf.domain.report.build import build_report
from wowperf.adapters.config.toml import load_defensives, load_season_data
from wowperf.urls import parse_report_url

REPORT = os.environ.get("WOWPERF_E2E_REPORT", "")


@pytest.mark.e2e
def test_a_real_run_renders_a_self_contained_report(tmp_path: Path) -> None:
    if not REPORT:
        pytest.fail(
            "Set WOWPERF_E2E_REPORT to a public Warcraft Logs Mythic+ report URL to run this"
        )

    code, fight = parse_report_url(REPORT)
    runs = build_repository(tmp_path)
    loaded = runs.load(code, fight)
    findings = analyse(loaded, load_season_data(), load_defensives())

    html = render(build_report(loaded, findings, None, None, None, "2026-09-05 00:00"))

    # The report's one hard promise: it opens from disk, offline, forever.
    assert "<script" not in html.lower()
    assert not re.search(r'(src|href)="(?!#)', html)
    assert "https://" not in html

    # Real rosters carry non-ASCII names; the file must hold them.
    written = tmp_path / "report.html"
    written.write_text(html, encoding="utf-8")
    assert written.read_text(encoding="utf-8") == html

    # Every finding the analysis produced reaches the page exactly once.
    for finding in findings:
        assert html.count(finding.title) == 1, finding.id

    # Without a speed reference the timeline is withheld, and says so.
    assert "Aligned timeline" in html
```

- [ ] **Step 2: Confirm it is deselected**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q`
Expected: the new test is deselected; everything else passes.

- [ ] **Step 3: Run it against the real API**

```bash
WCL_CLIENT_ID=... WCL_CLIENT_SECRET=... \
WOWPERF_E2E_REPORT='https://www.warcraftlogs.com/reports/<code>?fight=<n>' \
uv run pytest -m e2e -v
```

Expected: PASS.

**Then open the report and look at it.** Run `analyze` on the reference report and open the written HTML in a browser. Report what you see rather than only asserting on it: a heading with nothing under it, a number that reads as nonsense, a finding whose title runs off the card, a colour that vanishes against the background, a timeline where every block is the same width. Every plan in this repository has shipped a defect that only appeared on first contact with real data, and this is the first time anyone looks at the page.

- [ ] **Step 4: Correct the repository description**

In `CLAUDE.md`, the state paragraph ends by saying the HTML report gets its own plan and is not written yet. Amend it to record that the report shipped: the view model and builder under `src/wowperf/domain/report/`, the Jinja adapter under `src/wowperf/adapters/render/`, and `analyze` writing both artifacts. Add `--narrative` to the `analyze` row of the Commands table. Note that design §8 — the three skills and the narrative's authorship — remains unwritten.

- [ ] **Step 5: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add tests/e2e/test_report_e2e.py CLAUDE.md
git commit -m "Prove the report renders from a real run and fetches nothing

A hand-written fixture cannot check the thing that matters most here: that
a page built from a real roster, with real pack names and real non-ASCII
characters, still opens from disk with no network. Every plan in this
repository has shipped a defect that only appeared on first contact."
```

---

## Plan Self-Review

**Spec coverage.** Design §2's three units are Tasks 1 (model), 2 to 6 (build), 7 and 8 (adapter). §2.1's signature is Task 2, with `fetched_at` added so the domain reads no clock. §3 is satisfied by Task 6 calling `summarise_players` directly — the extraction the design once called for does not exist because the function already does. §3.1's refusal to say "avoidable damage" is Task 6, with a test asserting the word never reaches a card. §4's view model is Task 1. §5's section table is Tasks 2 to 6, one section at a time; §5.1's absent percentile is Task 1's `Header`, which has no such field. §6's timeline is Task 4 (geometry) and Task 8 (SVG). §7's no-total rule is Task 3, enforced structurally and tested in Task 9. §8's command surface is Task 10. §9's rendering rules are Tasks 7 and 8, with self-containment tested in Tasks 7, 9 and 12. §10's three-part testing strategy is Tasks 9 and 12. §12's carried-forward coordinate strings are Task 11.

**Nothing in the spec is unimplemented.** §11's out-of-scope list is honoured by absence: no task adds a table of contents, a print stylesheet, interactivity, a collapse, a theme toggle or a chart library.

**Type consistency.** `Report` and its sub-values are defined in Task 1 and used unchanged in Tasks 2 to 12. `build_report(loaded, findings, speed, parse, narrative, fetched_at)` is fixed in Task 2 and called with the same six arguments in Tasks 3, 4, 5, 6, 9, 10 and 12. `build_timeline(ours, theirs, section)` is Task 4 only. `build_deaths(loaded)` is Task 5 only. `build_interrupts(findings)` and `build_players(loaded, findings, parse)` are Task 6 only. `render(report)` is Task 7 and used in Tasks 8, 9, 10 and 12. `format_seconds`, `badge_for`, `parent_of` and `class_colour` are each defined once and referenced by name thereafter. The shared test helpers `a_run`, `a_pull`, `a_loaded` and `FETCHED` live in `tests/domain/report/test_build_frame.py` and are imported from there by Tasks 4, 5, 6 and 9; Task 4 widens `a_pull` with an `enemies` argument and Task 11 widens two different `a_pull` helpers in the analyser tests with a `name` argument, both additively.

**Known gaps, carried forward.**

- **Pack names are lost in a screenshot**, because they live in SVG `<title>` tooltips. Accepted in the design's §6; revisit only if screenshots turn out to be how the report is read.
- **`--narrative` renders as pre-wrapped plain text, not Markdown.** Rendering Markdown means a second dependency and a second escaping story for one paragraph of prose. If the narrative grows headings and lists, that is the moment to reconsider.
- **The ledger's nesting is stated in words**, not shown as a hierarchy. The words are what stop a reader summing, which is the part that matters; a nested visual is a candidate for a later plan.
- **No task renders a report with both references present in a test.** Tasks 4 and 6 cover the withheld halves and Task 12 covers a real run without references. A compared report is exercised only through `analyze`'s existing CLI fixtures in Task 10.
- **The palette is unreviewed by anyone with eyes** until Task 9 Step 4 and Task 12 Step 3. Both steps say to open the file and look; neither can be replaced by an assertion.
