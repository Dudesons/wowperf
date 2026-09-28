# Wipe damage pace, slice 3 (the night page) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every wipe pull of `wowperf night` carries slice 1's raid-wide pace comparison exactly as `raid --fight N` draws it for a wipe, each boss adds one line across its wipes on its Attempts tab, and a new `--no-compare` skips all of it.

**Architecture:** No new loader. The night command runs slice 1's `load_pace_sample` once per wipe pull, handing it the same leaderboard rows `raid` would weigh, and the one-day reference cache shares a boss's kills across its pulls. A pure `analyse_night_pace` turns a boss's per-pull samples into one `progression.attempts.pace` finding. `build_night_report` threads each pull's sample and reference records into `build_raid_report` and lists every reference once in the night's Provenance.

**Tech Stack:** Python 3.12, pydantic frozen models, Jinja2, httpx `MockTransport` in CLI tests, typer `CliRunner`, pytest. `uv` only: in Bash, `/c/Users/damien/.local/bin/uv.exe`.

**Spec:** `docs/plans/2026-09-27-wipe-damage-pace-design.md`, **§14** (slice 3). §1-§12 hold where §14 is silent; §13 (per player) is not part of this plan. Read §14 whole before Task 1.

## Global Constraints

- Only wipe pulls are compared; a kill pull, or `--no-compare`, requests nothing for pace (§14.2).
- `--no-compare` is the flag's name, as `raid` and `analyze` spell it (§14.2).
- The reference kills: the execution leaderboard's kills of the same boss, difficulty, partition and raid size, never the fight under analysis, up to `SAMPLE_SIZE` (5) -- one row-selection helper shared by `raid` and `night`; `night` never loads a damage-taken table (§14.2).
- Sharing is the reference cache's: every wipe pull calls `load_pace_sample` with the one-day `DiskCache(cache_dir / REFERENCE_CACHE_SUBDIR, max_age_seconds=REFERENCE_CACHE_SECONDS)`; no second loader (§14.2).
- Each wipe pull's page is the page `raid --fight N` draws for that wipe: findings, chart, Summary pointer, that pull's reference records in its own Provenance (§14.3).
- The night Provenance lists each reference kill once, as a link and never a figure, and says which pulls withheld the comparison and why (§14.3).
- `progression.attempts.pace`, `derived`, on the boss's Attempts tab, only with two or more compared wipes; titles "N of M wipes ended behind the kills' pace" / "None of M wipes ended behind the kills' pace"; one evidence line per wipe pull named by fight id; no damage figure, no trend word (§14.4).
- No per-player pace on night pulls: `analyse_encounter` gets no parse subjects there (§14.1, §14.6).
- `src/wowperf/domain/` performs no I/O. The report's one inline script is untouched.
- Never invent an API field. Every query used already exists in `src/wowperf/adapters/wcl/queries.py`.
- No real character name in `tests/`: only `Emberkin`, `Stonewake`, `Bríala`, `Кириллица` (plus `Briala`). NPC names invented. Players on `cW38jmwdnZfbHVL4` and `6Kx1P9GbNXrcLdHa` are referred to by class, spec, role or index only -- never by name, slug or raw finding id, anywhere. Never print a reference kill's report code in a reply, commit or document.
- Every new test is shown able to fail: break the line it guards, watch it go red, restore. Read `.claude/skills/testing/test-driven-development/SKILL.md` before the first test.
- Every new code file starts with two `ABOUTME: ` lines. Comments evergreen.
- Commits: imperative subject, no prefix, body says why, plain ASCII, last line a `Co-Authored-By:` naming the model that wrote the commit. Commit with `/mingw64/bin/git`. Never `--no-verify`.
- Gate after every task: `uv run ruff check .`, `uv run mypy` (strict over `tests/` too), `uv run pytest` -- green, output pristine.
- Every golden stays byte-identical. The night golden carries no pace, and every new block is guarded; if a golden moves, stop and report.

---

### Task 1: The boss-level line

**Files:**
- Create: `src/wowperf/domain/comparison/pace_night.py`
- Modify: `src/wowperf/domain/analysis/night_service.py` (`analyse_night_boss`)
- Test: `tests/domain/comparison/test_pace_night.py` (create), `tests/domain/analysis/test_night_service.py`

**Interfaces:**
- Consumes: slice 1's `PaceSample`, `clock_text`, `pace_reading`, `withheld_reason` (`wowperf.domain.comparison.pace`); `PaceReading`, `PaceState`, `final_behind_start` (`pace_curve`).
- Produces: `NIGHT_PACE_ID = "progression.attempts.pace"`, `MIN_COMPARED_PULLS = 2`, `analyse_night_pace(attempts: Sequence[LoadedEncounter], samples: Mapping[int, PaceSample]) -> list[Finding]`; `analyse_night_boss(series, defensives, *, death_cards: bool, pace: Mapping[int, PaceSample] | None = None) -> list[Finding]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domain/comparison/test_pace_night.py`:

```python
# ABOUTME: One boss's wipes on the night page, each read by slice 1's own pace comparison.
# ABOUTME: Pins the count, every pull line's wording, the withheld pull, and the size line.

import re

from tests.domain.comparison.test_pace_curve import a_kill, steady
from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.comparison.pace import NO_SINGLE_BOSS, PaceSample
from wowperf.domain.comparison.pace_curve import PaceReference
from wowperf.domain.comparison.pace_night import NIGHT_PACE_ID, analyse_night_pace
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding

THREE_KILLS = (a_kill(100, 400), a_kill(110, 420), a_kill(120, 440))
"""Three kills fighting through 400 s: at every second the band is 100, 110 and 120 a second."""


def a_pull(
    fight_id: int, *, seconds: int = 200, kill: bool = False, size: int = 20
) -> LoadedEncounter:
    return LoadedEncounter(
        encounter=an_encounter(
            fight_id=fight_id, kill=kill, size=size, start_ms=0, end_ms=seconds * 1000,
            fight_percentage=0.0 if kill else 40.0,
        )
    )


def a_sample(
    per_second: int, seconds: int = 200, kills: tuple[PaceReference, ...] = THREE_KILLS
) -> PaceSample:
    return PaceSample(ours=steady(per_second, seconds), references=kills)


def the_line(
    pulls: list[LoadedEncounter], samples: dict[int, PaceSample]
) -> Finding | None:
    found = analyse_night_pace(pulls, samples)
    assert len(found) <= 1
    return found[0] if found else None


def test_each_wipe_gets_one_line_in_pull_order_and_the_title_counts_the_behind() -> None:
    pulls = [a_pull(12), a_pull(14), a_pull(15)]
    samples = {12: a_sample(80), 14: a_sample(110), 15: a_sample(130)}
    line = the_line(pulls, samples)
    assert line is not None
    assert line.id == NIGHT_PACE_ID
    assert line.confidence is Confidence.DERIVED
    assert line.title == "1 of 3 wipes ended behind the kills' pace"
    assert line.evidence == (
        "Fight 12: behind from 0:01 to the wipe at 3:20",
        "Fight 14: on pace through the wipe at 3:20",
        "Fight 15: ahead through the wipe at 3:20",
    )
    assert "no trend" in line.detail


def test_no_wipe_behind_reads_none_of() -> None:
    line = the_line([a_pull(12), a_pull(14)], {12: a_sample(110), 14: a_sample(130)})
    assert line is not None
    assert line.title == "None of 2 wipes ended behind the kills' pace"


def test_a_band_cut_says_where_the_kills_ran_out() -> None:
    line = the_line(
        [a_pull(12, seconds=430), a_pull(14)], {12: a_sample(80, 430), 14: a_sample(80)}
    )
    assert line is not None
    assert line.evidence[0] == (
        "Fight 12: behind from 0:01 to 6:40, where fewer than three kills were still fighting"
    )


def test_the_slowest_kill_fallback_is_named_on_its_line() -> None:
    single = (a_kill(100, 400),)
    line = the_line(
        [a_pull(12), a_pull(14)], {12: a_sample(80, kills=single), 14: a_sample(80)}
    )
    assert line is not None
    assert line.evidence[0] == (
        "Fight 12, against the slowest kill alone: behind from 0:01 to the wipe at 3:20"
    )


def test_a_withheld_wipe_is_listed_with_its_reason_and_not_counted() -> None:
    pulls = [a_pull(12), a_pull(13), a_pull(14)]
    samples = {12: a_sample(80), 13: PaceSample(unavailable=NO_SINGLE_BOSS), 14: a_sample(80)}
    line = the_line(pulls, samples)
    assert line is not None
    assert line.title == "2 of 2 wipes ended behind the kills' pace"
    assert line.evidence[1] == f"Fight 13: not compared. {NO_SINGLE_BOSS}"


def test_one_compared_wipe_draws_no_line() -> None:
    pulls = [a_pull(12), a_pull(13)]
    samples = {12: a_sample(80), 13: PaceSample(unavailable=NO_SINGLE_BOSS)}
    assert the_line(pulls, samples) is None


def test_a_kill_and_a_pull_with_no_sample_are_not_listed() -> None:
    pulls = [a_pull(12), a_pull(13, kill=True), a_pull(14), a_pull(15)]
    samples = {12: a_sample(80), 14: a_sample(110)}
    line = the_line(pulls, samples)
    assert line is not None
    assert [one.split(":")[0] for one in line.evidence] == ["Fight 12", "Fight 14"]


def test_no_compare_draws_no_line() -> None:
    assert the_line([a_pull(12), a_pull(14)], {}) is None


def test_two_raid_sizes_are_named_on_one_line() -> None:
    pulls = [a_pull(12, size=20), a_pull(14, size=20), a_pull(15, size=18)]
    samples = {12: a_sample(80), 14: a_sample(80), 15: a_sample(80)}
    line = the_line(pulls, samples)
    assert line is not None
    assert line.evidence[-1] == (
        "Fights 12, 14 at 20 players; Fight 15 at 18 players: each against kills of its own size"
    )


def test_one_raid_size_draws_no_size_line() -> None:
    line = the_line([a_pull(12), a_pull(14)], {12: a_sample(80), 14: a_sample(80)})
    assert line is not None
    assert not any("players" in one for one in line.evidence)


def test_no_line_prints_a_raw_damage_figure() -> None:
    pulls = [a_pull(12), a_pull(14, seconds=430), a_pull(15)]
    samples = {12: a_sample(80), 14: a_sample(110, 430), 15: a_sample(130)}
    line = the_line(pulls, samples)
    assert line is not None
    for text in (line.title, line.detail, *line.evidence):
        assert not re.search(r"\d{4,}", text), text
```

The expected strings were run against this task's code before the plan was committed (2026-09-28, 11 of 11 green). If one disagrees now, the code was transcribed differently: diff against the plan before changing a test.

- [ ] **Step 2: Run and watch them fail**

Run: `/c/Users/damien/.local/bin/uv.exe run pytest tests/domain/comparison/test_pace_night.py -v`
Expected: FAIL at import -- `No module named 'wowperf.domain.comparison.pace_night'`.

- [ ] **Step 3: Write the module**

Create `src/wowperf/domain/comparison/pace_night.py`:

```python
# ABOUTME: One boss's wipes on the night page, each read by slice 1's own pace comparison.
# ABOUTME: A count and one line per wipe pull, in pull order; no new arithmetic and no trend.

from collections.abc import Mapping, Sequence

from wowperf.domain.comparison.pace import PaceSample, clock_text, pace_reading, withheld_reason
from wowperf.domain.comparison.pace_curve import PaceReading, PaceState, final_behind_start
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding

NIGHT_PACE_ID = "progression.attempts.pace"

MIN_COMPARED_PULLS = 2
"""Below this many compared wipes the line would only repeat one pull's own finding."""

NIGHT_PACE_DETAIL = (
    "Each line is one wipe's own damage pace against the reference kills, as that pull's "
    "Damage tab draws it: behind means below the kill that had dealt the boss least by the "
    "pull's last compared second. The count is over the compared wipes only; a wipe that "
    "could not be compared is listed and not counted. The order is pull order, and no trend "
    "is drawn from it."
)


def analyse_night_pace(
    attempts: Sequence[LoadedEncounter], samples: Mapping[int, PaceSample]
) -> list[Finding]:
    """`progression.attempts.pace` for one boss, or nothing.

    `attempts` is the boss's drawn pulls in pull order; `samples` is each wipe
    pull's pace sample by fight id, as the night command loaded it. A pull with
    no sample -- a kill, or a night read with `--no-compare` -- is not listed.
    Every clock and state is the one `pace_reading` already gives that pull, so
    this line and the pull's own finding cannot disagree.
    """
    wipes = [
        one.encounter
        for one in attempts
        if not one.encounter.kill and one.encounter.fight_id in samples
    ]
    lines: list[str] = []
    compared = 0
    behind = 0
    for encounter in wipes:
        sample = samples[encounter.fight_id]
        reason = withheld_reason(encounter, sample)
        if reason:
            lines.append(f"Fight {encounter.fight_id}: not compared. {reason}")
            continue
        reading = pace_reading(encounter, sample)
        assert reading is not None  # withheld_reason("") guarantees a usable reading
        compared += 1
        if reading.seconds[-1].state is PaceState.BEHIND:
            behind += 1
        lines.append(_pull_line(encounter.fight_id, reading))
    if compared < MIN_COMPARED_PULLS:
        return []

    sizes: dict[int, list[int]] = {}
    for encounter in wipes:
        sizes.setdefault(encounter.size, []).append(encounter.fight_id)
    if len(sizes) > 1:
        parts = [
            f"{'Fights' if len(ids) > 1 else 'Fight'} {', '.join(str(one) for one in ids)} "
            f"at {size} players"
            for size, ids in sizes.items()
        ]
        lines.append("; ".join(parts) + ": each against kills of its own size")

    count = f"{behind} of {compared}" if behind else f"None of {compared}"
    return [
        Finding(
            id=NIGHT_PACE_ID,
            title=f"{count} wipes ended behind the kills' pace",
            detail=NIGHT_PACE_DETAIL,
            confidence=Confidence.DERIVED,
            evidence=tuple(lines),
        )
    ]


def _pull_line(fight_id: int, reading: PaceReading) -> str:
    """One wipe's state at its last compared second, and where the comparison stopped."""
    last = reading.seconds[-1]
    clock = clock_text(last.second)
    if not reading.band_cut:
        end = f"the wipe at {clock}"
    elif reading.single:
        end = f"{clock}, when the reference kill ended"
    else:
        end = f"{clock}, where fewer than three kills were still fighting"

    if last.state is PaceState.BEHIND:
        start = final_behind_start(reading)
        assert start is not None  # a reading that ends behind has a final behind stretch
        state = f"behind from {clock_text(start)} to {end}"
    elif last.state is PaceState.ON_PACE:
        state = f"on pace through {end}"
    else:
        state = f"ahead through {end}"
    against = ", against the slowest kill alone" if reading.single else ""
    return f"Fight {fight_id}{against}: {state}"
```

- [ ] **Step 4: Run, pass, prove**

Run the file: all pass. Prove, restoring after each:
- `MIN_COMPARED_PULLS = 1` -> the one-compared-wipe test red;
- count a withheld wipe in `compared` -> the withheld test red (title "2 of 3");
- drop the `one.encounter.fight_id in samples` filter -> the kill-and-no-sample test red (a `KeyError` on the missing fight is red too);
- drop the `if len(sizes) > 1` guard -> the one-size test red;
- swap `ON_PACE` and `AHEAD` wording -> the pull-order test red.

- [ ] **Step 5: Wire it into the boss's findings**

In `night_service.py`, `analyse_night_boss` gains a keyword `pace: Mapping[int, PaceSample] | None = None` and appends `analyse_night_pace(series.attempts_with_events, pace)` after the pooled defensives when `pace` is given (its absence and an empty mapping both append nothing). Docstring: one sentence -- the pace line reads each wipe pull's own sample, so it is only there on a night that fetched them. Test in `tests/domain/analysis/test_night_service.py`, with that file's own fixtures and a sample built with `test_pace_night`'s `a_sample`: two wipe pulls with samples -> the findings carry exactly one `progression.attempts.pace`; the same call without `pace` carries none; `death_cards=False` still carries it (the pace line does not depend on the card tier). Prove red by not appending.

- [ ] **Step 6: Gate and commit**

Full gate. Subject: `Say where each of a boss's wipes fell behind the kills`

---

### Task 2: The night page carries each wipe's pace

**Files:**
- Modify: `src/wowperf/domain/report/night_build.py` (`build_night_report`)
- Modify: `src/wowperf/domain/report/night_model.py` (`NightProvenance.references`)
- Modify: `src/wowperf/adapters/render/_night_provenance.html.j2`
- Test: `tests/domain/report/test_night_build.py`, `tests/adapters/render/test_night_html_invariants.py`

**Interfaces:**
- Consumes: slice 1's `PaceSample`, `UNAVAILABLE_ID`, `analyse_pace`; Task 1's `analyse_night_pace`; `ReferenceRecord` (`wowperf.domain.report.model`).
- Produces: `build_night_report(..., pace_by_fight: Mapping[int, PaceSample] | None = None, records_by_fight: Mapping[int, tuple[ReferenceRecord, ...]] | None = None)` (keywords, after `self_resurrections`); `NightProvenance.references: tuple[ReferenceRecord, ...] = ()`.

Read `build_night_report`, `NightProvenance`, `_night_provenance.html.j2`, `_raid_provenance.html.j2` and `build_raid_report`'s signature whole before editing.

- [ ] **Step 1: The builder, test first**

1. Each pull's `build_raid_report(...)` call also receives `reference_records=records_by_fight.get(fight_id, ())` and `pace=pace_by_fight.get(fight_id)` (both mappings read as empty when None). `compared_slugs` stays `None`. That is all it takes for the chart, the pointer and the Damage-tab rows: `build_raid_report` already draws them from the pace finding in the pull's findings and the sample.
2. `NightProvenance.references: tuple[ReferenceRecord, ...] = ()`, docstring: every reference kill any pull weighed, each once, in the order the pulls first weighed them; a link and never a figure. Replace the class docstring's sentence saying the command never fetches references (it is now false); keep the reason `Provenance` is not reused (the `fight_id`).
3. `build_night_report` fills it from `records_by_fight` walked in pull order across bosses, keeping the first record per `url` (a later pull's copy is the same kill read back from cache).
4. `NightProvenance.withheld` gains, after the failed-pull lines, one line per drawn pull whose findings carry an `UNAVAILABLE_ID` finding: `f"Fight {fight_id}: damage pace against the kills was not compared. {finding.detail}"`, in pull order. Read from the findings, so the line and the pull's own notice cannot disagree.
5. Update `build_night_report`'s docstring where it says `reference_records` is left at its empty default because no reference run is fetched: now each pull gets its own records, and `compared_slugs` stays `None` because no parse comparison runs.

Tests in `tests/domain/report/test_night_build.py`, with its `a_night` fixture and samples from `tests.domain.comparison.test_pace_night.a_sample` (behind: `a_sample(80, seconds)` with `seconds` the pull's own duration -- read it off the fixture's encounter), findings from slice 1's `analyse_pace(encounter, sample)` -- never hand-typed pace findings -- and `ReferenceRecord`s built directly (they are records, not findings):
- a wipe pull given a sample carries `report.pace_chart` not None, its `compare.pace.boss` row on the Damage tab (`damage_rows`), and `report.pace_warning` when it ends behind; a pull given no sample carries none of the three;
- a pull's own `provenance.references` equals the records handed for it;
- two pulls handed the same three records (the second copy `from_cache=True`) give `NightProvenance.references` three entries, the first copies;
- a pull whose sample is `PaceSample(unavailable=NO_SINGLE_BOSS)` gives exactly one withheld line naming its fight and `NO_SINGLE_BOSS`;
- the boss line from Task 1 handed in `findings_by_boss` lands in that boss's `summary.attempt_rows` exactly once and nowhere on a pull.
Prove red: drop `pace=` (chart test), drop the dedupe (three becomes six), drop the withheld loop.

- [ ] **Step 2: The template**

In `_night_provenance.html.j2`, after the "Report ..., fetched ..." line and before the withheld lines, one line per `report.provenance.references` in the same markup `_raid_provenance.html.j2` uses for a record (the link, "candidate", report and fight, the from-cache note, the not-used reason). Copy that line's markup; do not invent another.

- [ ] **Step 3: Render tests and goldens**

In `tests/adapters/render/test_night_html_invariants.py`, on a night built with Step 1's fixtures: a wipe pull's own section carries its pace finding's title and the chart's heading (the `_raid_damage.html.j2` heading text) inside that pull's Damage panel; a pull with no sample carries neither; the `night-notes` section carries each reference url exactly once; the boss line's title sits inside that boss's summary block; no `>None<` anywhere. Assert what the page renders -- the titles and lines taken from the finding objects -- not that an element exists. Run the golden tests: the night golden must stay byte-identical; if it moves, stop and report.

- [ ] **Step 4: Gate and commit**

Full gate. Subject: `Draw each night wipe's pace and list its kills once`

---

### Task 3: Wire the night command

**Files:**
- Modify: `src/wowperf/cli.py` (the `night` command; `_mechanics_sample`; two helpers)
- Modify: `CLAUDE.md` (the commands table's `night` row)
- Test: `tests/test_cli_night.py`, `tests/test_cli.py` only if the raid refactor needs it

**Interfaces:**
- Consumes: Task 1's `analyse_night_boss(..., pace=)`; Task 2's `build_night_report(..., pace_by_fight=, records_by_fight=)`; slice 1's `load_pace_sample(client, own_cache, reference_cache, encounter, references)`.
- Produces: `_reference_kill_rows(rankings, encounter) -> tuple[ReferenceKillRow, ...]`, `_pace_references(rankings, encounter) -> tuple[ReferenceKillRow, ...]` in `cli.py`; the `--no-compare` flag on `night`.

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections, the whole `night` command, `raid`'s comparison block (the `if not no_compare:` block that builds `transient` and calls `load_pace_sample`), and `_mechanics_sample` before editing.

- [ ] **Step 1: One row-selection rule, test first where it moves**

Extract from `_mechanics_sample`:

```python
def _reference_kill_rows(
    rankings: WclEncounterRankingRepository, encounter: Encounter
) -> tuple[ReferenceKillRow, ...]:
    """Every execution-leaderboard kill of this boss a comparison may draw, in leaderboard order.

    The one rule `raid` and `night` both select their reference kills by: this
    difficulty (the query's own argument) and partition, and this raid size.
    """
    rows = rankings.reference_kills(
        encounter.encounter_id, encounter.difficulty, encounter.partition
    )
    return select_reference_kills(rows, our_size=encounter.size, limit=None)
```

`_mechanics_sample` calls it in place of its own two lines; its behaviour and docstring otherwise stay. Add beside it:

```python
def _pace_references(
    rankings: WclEncounterRankingRepository, encounter: Encounter
) -> tuple[ReferenceKillRow, ...]:
    """The kills a night wipe's pace is read against: `raid`'s rule, without its tables.

    `raid` takes its pace references from the mechanics sample, which also
    loads each kill's damage-taken table; the night page draws no mechanics
    comparison, so it takes the first `SAMPLE_SIZE` rows the same rule
    selects, never the fight under analysis. A reference whose own fight
    will not load is dropped by `load_pace_sample`, not refilled.
    """
    ours = (encounter.report_code, encounter.fight_id)
    rows = tuple(
        row
        for row in _reference_kill_rows(rankings, encounter)
        if (row.report_code, row.fight_id) != ours
    )
    return rows[:SAMPLE_SIZE]
```

Every existing `raid` test stays green unchanged (the refactor moves two lines).

- [ ] **Step 2: The command, test first**

In `night`:
1. A `no_compare: bool = typer.Option(False, "--no-compare", help="Fetch no reference kill: no wipe pull's damage pace is compared against the kills")` option. Rewrite the docstring's paragraph that says `--no-compare` is not offered: the parse axis is still not drawn (keep why), and `--no-compare` now skips the one comparison the night does draw, each wipe's damage pace.
2. After `drawn` is built and before `boss_findings`: when not `no_compare`, build `transient` exactly as `raid` builds it and one `WclEncounterRankingRepository(repository.client, transient)`, then for each wipe attempt in `drawn` (skip `attempt.encounter.kill`) call `load_pace_sample(repository.client, repository.cache, transient, attempt.encounter, _pace_references(encounter_rankings, attempt.encounter))` and keep `pace_by_fight[fight_id]` and `records_by_fight[fight_id]`. Comment why the reference cache is what shares a boss's kills across its pulls (§14.2), so nothing here needs to.
3. `analyse_night_boss(boss, defensives, death_cards=death_cards, pace=pace_by_fight)`; `analyse_encounter(attempt, defensives, consumables, roles=roles, pace=pace_by_fight.get(attempt.encounter.fight_id))`. No parse subjects: the per-player half then compares nobody, which §14.6 asks for. Update the comment above `findings_by_fight` that says the command fetches no reference kill.
4. `build_night_report(..., pace_by_fight=pace_by_fight, records_by_fight=records_by_fight)`.
5. The payload's `asked_for` gains `"compare": not no_compare`.
6. `CLAUDE.md`'s commands table: the `night` row gains `[--no-compare]` after `[--no-deaths]`.

Tests in `tests/test_cli_night.py`. Extend `build_night_transport` (and `run_night`) with a `kill_rankings: list[dict[str, Any]] | None = None` argument and answers for the pace queries, following how `tests/test_cli.py`'s raid transport answers them (read its `npc_actors_payload`, `reference_fight_payload`, `boss_damage_graph_payload` and `_reference_kill_row`; copy the shapes, do not import that module):
- `EncounterKillRankings` -> `worldData.encounter.fightRankings` with `kill_rankings` (empty by default) as its rows; rows carry `report.code`, `report.fightID`, `report.startTime`, `size` (`NIGHT_SIZE`), `duration`, `deaths: 0` and never a `difficulty` (the wcl-api skill says live rows carry none);
- `NpcActors` -> one `subType: "Boss"` actor per boss, named `FIRST_BOSS_NAME` and `SECOND_BOSS_NAME`, each with its own game id;
- `ReferenceFight` -> a fight whose `enemyNPCs` carry both bosses' game ids, empty `friendlyPlayers` and `friendlySpecs`;
- `BossDamageGraph` -> a `Total` series at 1-second buckets, 5 a second for `NIGHT_REPORT_CODE` and 50 for any other code, so every compared wipe reads behind.
With the default empty `kill_rankings`, every existing test keeps working: each wipe withholds with `NO_REFERENCE_KILL` before any graph is fetched. Update the spies that replace `analyse_night_boss` or `build_night_report` (`test_each_boss_summary_asks_for_the_pooled_finding_only_with_death_cards`, `test_the_loader_and_the_builder_are_handed_the_same_tier`) to accept the new keywords, and extend `test_night_states_what_it_spent` to the new operations it sees.

New tests (three reference rows, `A_NIGHT`: the first boss has two wipes, the second one):
- every pull's findings in the file carry `compare.pace.boss`; the first boss's findings carry `progression.attempts.pace` and the second boss's do not;
- `EncounterKillRankings` is requested once per boss (by its `encounterId` variable), `ReferenceFight` once per reference for the whole night, and `BossDamageGraph` once per reference plus once per wipe pull for `NIGHT_REPORT_CODE` -- counted by operation name and variables, which is what proves the cache shares a boss's kills;
- `--no-compare` requests none of `EncounterKillRankings`, `NpcActors`, `ReferenceFight`, `BossDamageGraph`, writes no `compare.pace.` and no `progression.attempts.pace` finding, and writes `asked_for.compare` false;
- a night whose every pull is a kill requests none of those four;
- the HTML carries each reference url once inside the `night-notes` section.
Prove red: skip the `kill` check (the all-kills test); build a fresh `DiskCache` in a new temporary directory per pull instead of one `transient` for the night (the once-per-reference counts go red: each pull re-requests every reference); drop `pace=` from `analyse_night_boss` (the boss-line test).

- [ ] **Step 3: Gate and commit**

Full gate. Subject: `Compare each night wipe's pace against the kills`

---

### Task 4: Exercise it on the real report

**Files:**
- Modify: `tests/e2e/test_night_e2e.py`
- Modify: `docs/plans/2026-09-27-wipe-damage-pace-design.md` (status, §14.5 live)

**This task is not optional.** A new judgement is not done until a live run has exercised it, and a state that never occurs is a defect.

- [ ] **Step 1: The e2e, run once**

Read `.claude/skills/wcl-api/SKILL.md`'s rate-limit sections and the whole of `tests/e2e/test_night_e2e.py`. Its header says "No comparison of any kind is drawn": rewrite that paragraph (the parse axis is still not drawn; each wipe's pace now is, and what it costs). Extend `test_a_whole_report_reads_as_one_night` on its same single run (keep `--no-deaths`): every wipe pull's findings carry exactly one of `compare.pace.boss` or `compare.pace.unavailable`; every `compare.pace.boss` is `derived` with a title starting `"Behind "`, `"On "` or `"Ahead of "`; no kill pull carries any `compare.pace.` finding; every `progression.attempts.pace` is `derived`, sits on a boss with two or more wipe pulls, and has one evidence line per wipe pull of that boss (plus at most one size line); at least one `compare.pace.boss` exists. The cost bound rises by what the run measures, with the figure and date in a comment; stop and report if pace added more than 60 points over the header's recorded no-deaths cost. Reduce every live check to a bool before asserting; no assertion message carries a title or evidence text. Run once: `/c/Users/damien/.local/bin/uv.exe run pytest -m e2e tests/e2e/test_night_e2e.py -v -s`. On failure, diagnose from the output before any second run.

- [ ] **Step 2: The live distribution**

From the findings file the command writes (`out/cW38jmwdnZfbHVL4.night.json`, from one `wowperf night cW38jmwdnZfbHVL4 --no-deaths` run, which a warm cache makes cheap -- read the points it prints), with a scratch script in the session scratchpad that prints no name, no slug and no reference report code: per boss index and fight id, whether the pull was a kill, the pull's pace state (behind / on pace / ahead / withheld and the withheld reason's first clause), whether the band was cut, whether the fallback was used, and per boss whether the line fired, its count and whether a size line appeared. Report how often each occurred: behind, on pace, ahead, band cut, fallback, withheld per reason, boss line fired, "None of" title, size line. Scan `out/cW38jmwdnZfbHVL4.night.html` for `>None<`, `>null<`, `>nan<`, `nan%`, `{{`, `{%` (a leak check, reduced to counts).

A state that never occurs is reported as open, not settled; do not go looking for another report -- RwlRwl supplies one.

- [ ] **Step 3: Amend the design**

Status line: slice 3 planned in `docs/plans/2026-09-28-wipe-pace-night-plan.md` and built. Under §14.5, a "Live" paragraph with the per-state counts (numbers, boss indices and fight ids only), the points the pace half added, and every state that did not occur, marked open.

- [ ] **Step 4: Gate and commit**

Offline gate. Subject: `Exercise the night page's wipe pace on a real report`. Body: the points spent and the per-state counts, no names.

---

## What this plan deliberately does not build

- Per-player pace lines on night pulls.
- Any trend judgement across a boss's wipes.
- Any change to the `progression` command.
- Any change to `raid`'s behaviour beyond moving its row-selection lines into `_reference_kill_rows`.
