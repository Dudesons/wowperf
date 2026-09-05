# The Inference Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Claude the three skills and the one guardrail it needs to turn a Warcraft Logs URL into a finished report, without ever stating a number the tool did not compute.

**Architecture:** One pure function in the domain rejects a narrative containing any digit, called from `analyze` before anything is fetched. Three skills under `.claude/skills/` carry the API reference, the interpretation knowledge, and the workflow. Design §2's verified reference moves into the first of them and §2 becomes a pointer, so there is one copy and it cannot drift.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `typer`, `pytest`, `ruff`, `mypy`. The skills are Markdown.

**Spec:** `docs/plans/2026-09-05-mplus-inference-layer-design.md`. Its authority is `docs/plans/2026-09-03-mplus-postmortem-design.md` §8.

**Depends on:** Plans A to E, all merged. Read `src/wowperf/cli.py`'s `analyze`, `src/wowperf/adapters/wcl/queries.py`, and `docs/plans/2026-09-03-mplus-postmortem-design.md` §2 before starting.

## Global Constraints

- **Python `>=3.12`.** `uv` is the only toolchain: no pip, no poetry, no hand-managed virtualenv.
- **`uv` is not on PATH.** Every bash command using it begins `export PATH="$HOME/.local/bin:$PATH"`.
- **`src/wowperf/domain/` performs no I/O.** No file reads, no clock, no network. The digit check is a pure function over a string; `cli.py` does the reading.
- **The narrative states no numbers.** The check rejects **any** digit — no carve-out for `pull 7` or `+16`, and no `--allow-digits` escape hatch.
- **The check runs before anything is fetched**, beside the existing rule that an unreadable `--narrative` path fails first. A bad narrative costs zero API quota.
- **The check is a tripwire, not a proof.** Spelled-out quantities pass. Do not attempt to catch them.
- **Every claim in `wcl-api` carries how it was verified and when.** A field name with no verification date is a defect.
- **Never accumulate a corpus of other players' logs.** RPGLogs terms §5d.
- **No hardcoded season data.** No zone, encounter, affix or ability ID as a literal in `src/`.
- Every Python file starts with two `# ABOUTME: ` comment lines. Empty `__init__.py` markers are exempt.
- Comments are **evergreen**: they describe the code as it is, never how it came to be, and never cite a task number or a review.
- **English** in code, comments, error strings, skills and commit messages.
- Commit style: imperative mood, no `feat:` / `fix:` prefix. The subject says what the commit does to the repository; the body explains **why**.
- **Never `--no-verify`, `--no-hooks`, or `--no-pre-commit-hook`.**
- The gate is `uv run pytest`, `uv run ruff check .`, `uv run mypy` (no path argument). Ruff's line length is 100.
- Scratch files go under `C:\Users\damien\AppData\Local\Temp\claude\`, never in the repository — a stray file breaks `ruff check .`.
- **Stage files by name.** Never `git add -A` or `git commit -a`.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/report/narrative.py` | *New.* The digit check, pure |
| `tests/domain/report/test_narrative.py` | *New.* Its unit tests |
| `src/wowperf/cli.py` | *Modified.* Calls the check before fetching |
| `tests/test_cli.py` | *Modified.* A digit-bearing narrative fails with zero API calls |
| `.claude/skills/wcl-api/SKILL.md` | *New.* The verified API reference |
| `.claude/skills/mplus-analysis/SKILL.md` | *New.* Interpretation knowledge |
| `.claude/skills/analyzing-a-run/SKILL.md` | *New.* The workflow |
| `tests/test_skills.py` | *New.* Two drift tripwires |
| `docs/plans/2026-09-03-mplus-postmortem-design.md` | *Modified.* §2 becomes a pointer; §8 records what shipped |
| `CLAUDE.md` | *Modified.* Skills table gains three rows |

## Decisions this plan makes

Recorded so an implementer does not rediscover them and a reviewer does not flag them.

1. **The check returns every offending line, not the first.** Fixing a narrative should not be whack-a-mole.
2. **The error explains itself once, then lists the lines.** Repeating the explanation per line is noise.
3. **`wcl-api`'s field table carries an "In `queries.py`" column.** Measured: `rating` is documented in design §2 and never queried, while `totalUptime` and `totalUses` arrive in a response body rather than being requested by name. A drift test asserting every documented field appears in the queries would fail on the day it was written.
4. **The drift test checks both directions of that column.** A row marked `yes` must appear in `queries.py`; a row marked `no` must not. Otherwise the column rots into decoration.
5. **Skills are not tested for their prose.** Only the two mechanical claims — field names and CLI flags — get tripwires.

---

### Task 1: The digit check

**Files:**
- Create: `src/wowperf/domain/report/narrative.py`
- Test: `tests/domain/report/test_narrative.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `def lines_with_digits(text: str) -> tuple[tuple[int, str], ...]` in `wowperf.domain.report.narrative`.

Line numbers start at 1, matching what an editor shows. Blank lines count toward the numbering. The return is a tuple of tuples so it stays hashable and matches the rest of the domain.

- [ ] **Step 1: Write the failing test**

`tests/domain/report/test_narrative.py`:

```python
# ABOUTME: The narrative states no numbers; the report's own sections carry every figure.
# ABOUTME: These pin the tripwire that keeps an unbadged number off the page.

from wowperf.domain.report.narrative import lines_with_digits


def test_an_empty_narrative_has_nothing_to_report() -> None:
    assert lines_with_digits("") == ()


def test_prose_without_a_digit_passes() -> None:
    text = "Your losses are route, not execution. Travel dominates every other figure."
    assert lines_with_digits(text) == ()


def test_a_single_numeral_is_reported_with_its_line_number() -> None:
    assert lines_with_digits("Travel cost 3:13.") == ((1, "Travel cost 3:13."),)


def test_every_offending_line_is_reported_not_only_the_first() -> None:
    text = "Fine.\nTravel cost 3:13.\nAlso fine.\nYou died 4 times."
    assert lines_with_digits(text) == (
        (2, "Travel cost 3:13."),
        (4, "You died 4 times."),
    )


def test_line_numbers_count_blank_lines_so_they_match_an_editor() -> None:
    assert lines_with_digits("Fine.\n\n\nPull 7 was slow.") == ((4, "Pull 7 was slow."),)


def test_a_digit_inside_a_word_still_counts() -> None:
    assert lines_with_digits("The pull7 pack was slow.") == ((1, "The pull7 pack was slow."),)


def test_a_non_ascii_digit_counts() -> None:
    # Arabic-Indic three. `str.isdigit()` is true for it, and it is a number on
    # the page exactly as an ASCII digit would be.
    assert lines_with_digits("Travel cost ٣ minutes.") == ((1, "Travel cost ٣ minutes."),)


def test_a_superscript_digit_counts() -> None:
    assert lines_with_digits("Damage went up².") == ((1, "Damage went up²."),)


def test_spelled_out_quantities_pass_because_this_is_a_tripwire_not_a_proof() -> None:
    # Stated as a test so nobody later mistakes the check for a guarantee: the
    # instruction forbids quantities, this function only catches numerals.
    assert lines_with_digits("You lost three minutes to travel.") == ()
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_narrative.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'wowperf.domain.report.narrative'`.

- [ ] **Step 3: Write the check**

`src/wowperf/domain/report/narrative.py`:

```python
# ABOUTME: The narrative states no numbers; every figure lives in a section that owns it.
# ABOUTME: A pure check over text, so the command can refuse a narrative before fetching.


def lines_with_digits(text: str) -> tuple[tuple[int, str], ...]:
    """Every line carrying a digit, as (line number, line) pairs, in order.

    The report's own sections carry every figure, badged and sourced, directly
    below the narrative. A number repeated in the narrative is a second,
    unbadged claim competing with the first.

    Line numbers start at 1 and count blank lines, so they match what an editor
    shows. Every offending line is returned rather than only the first, so
    fixing a narrative is not whack-a-mole.

    This is a tripwire, not a proof: it catches numerals, which is where drift
    happens. "You lost three minutes to travel" passes, and the instruction that
    forbids it lives in the `analyzing-a-run` skill.
    """
    return tuple(
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if any(character.isdigit() for character in line)
    )
```

- [ ] **Step 4: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/domain/report/test_narrative.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/domain/report/narrative.py tests/domain/report/test_narrative.py
git commit -m "Add the check that keeps numbers out of the narrative

Every figure on the page already sits in a section that owns it, badged and
sourced. A number repeated in the narrative is a second, unbadged claim
competing with the first, and this is the only claim on the page with no
tested Python behind it."
```

---

### Task 2: The command refuses a narrative with numbers

**Files:**
- Modify: `src/wowperf/cli.py` — the narrative-reading block inside `analyze`, currently at lines 206-215
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `lines_with_digits` from Task 1.
- Produces: `analyze --narrative` raising `ValueError` before any fetch when the file carries a digit.

The existing block already reads the narrative before anything is fetched, and already wraps `UnicodeDecodeError` so the message names the file. Add the digit check immediately after the read, inside the same `try`, so the existing `except (ValueError, WclError, httpx.HTTPError, OSError)` catches it and prints it in red before exiting 1.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`, beside the existing narrative tests:

```python
def test_a_narrative_with_numbers_fails_before_anything_is_fetched(tmp_path: Path) -> None:
    """Every figure lives in a section that owns it, so a number in the narrative is a
    second unbadged claim. The refusal must cost no API quota, exactly as an unreadable
    narrative path does."""
    notes = tmp_path / "notes.md"
    notes.write_text("Fine.\nTravel cost 3:13.\nAlso fine.\nYou died 4 times.", encoding="utf-8")
    calls: list[str] = []
    result = run_analyze(tmp_path, "--narrative", str(notes), calls=calls)
    assert result.exit_code == 1
    assert calls == []
    assert "notes.md" in result.output
    # Every offending line, not only the first.
    assert "line 2" in result.output
    assert "line 4" in result.output
    assert "Travel cost 3:13." in result.output
    assert "You died 4 times." in result.output


def test_a_narrative_without_numbers_is_accepted(tmp_path: Path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("Your losses are route, not execution.", encoding="utf-8")
    result = run_analyze(tmp_path, "--narrative", str(notes))
    assert result.exit_code == 0, result.output
    html = (tmp_path / "out" / "abc123-36.html").read_text(encoding="utf-8")
    assert "Your losses are route, not execution." in html
```

**Read the neighbouring tests before writing these.** `run_analyze`'s signature and the fixture's report code and fight id come from that file; the values above match what the other narrative tests use, but confirm rather than assume.

- [ ] **Step 2: Run them to watch the first fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -k "narrative_with_numbers or narrative_without_numbers" -v`
Expected: `test_a_narrative_with_numbers_fails_before_anything_is_fetched` FAILS with `exit_code == 0` — the narrative is currently accepted. The second test passes already.

- [ ] **Step 3: Add the check and its message**

In `src/wowperf/cli.py`, add to the imports:

```python
from wowperf.domain.report.narrative import lines_with_digits
```

Add this module-level helper, beside the other private helpers:

```python
def _narrative_digits_message(path: Path, offending: tuple[tuple[int, str], ...]) -> str:
    """Explain the rule once, then list every line that breaks it."""
    lines = "\n".join(f"  line {number}: {line}" for number, line in offending)
    return (
        f"{path}: the narrative states no numbers — the figures live in the "
        f"report's own sections, directly below it.\n{lines}"
    )
```

Then, in `analyze`, immediately after `narrative_text = narrative.read_text(...)` and its `except` block:

```python
            offending = lines_with_digits(narrative_text)
            if offending:
                raise ValueError(_narrative_digits_message(narrative, offending))
```

- [ ] **Step 4: Run them and watch them pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -k "narrative" -v`
Expected: every narrative test passes, including the pre-existing missing-file and undecodable-file ones.

- [ ] **Step 5: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add src/wowperf/cli.py tests/test_cli.py
git commit -m "Refuse a narrative that states numbers, before fetching anything

A check you have to remember to run is a check that stops running, so this
sits on the only path in. It fails beside the existing unreadable-path rule,
so a bad narrative costs no API quota either way."
```

---

### Task 3: The `wcl-api` skill, and design §2 becomes a pointer

**Files:**
- Create: `.claude/skills/wcl-api/SKILL.md`
- Modify: `docs/plans/2026-09-03-mplus-postmortem-design.md` — §2, lines 47-181
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `.claude/skills/wcl-api/SKILL.md` containing one Markdown table of field names with the columns `Field`, `Appears on`, `Verified`, `In queries.py`; and `tests/test_skills.py` with the field-drift test.

This task **moves** content. Design §2's prose is already correct and dated — do not rewrite it, restructure it. What is new is the table, which gathers the field names scattered through that prose into one machine-readable place.

- [ ] **Step 1: Write the failing test**

`tests/test_skills.py`:

```python
# ABOUTME: The skills make mechanical claims about the code; these keep the two in step.
# ABOUTME: A reference that has quietly drifted from the code is worse than no reference.

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WCL_API_SKILL = REPO_ROOT / ".claude" / "skills" / "wcl-api" / "SKILL.md"
QUERIES = REPO_ROOT / "src" / "wowperf" / "adapters" / "wcl" / "queries.py"

FIELD_ROW = re.compile(
    r"^\|\s*`(?P<field>[^`]+)`\s*\|[^|]*\|\s*(?P<verified>\d{4}-\d{2}-\d{2})\s*\|"
    r"\s*(?P<used>yes|no)\s*\|"
)


def field_rows() -> list[tuple[str, str]]:
    """(field name, "yes" or "no") for every row of the skill's field table."""
    rows = []
    for line in WCL_API_SKILL.read_text(encoding="utf-8").splitlines():
        match = FIELD_ROW.match(line.strip())
        if match:
            rows.append((match.group("field"), match.group("used")))
    return rows


def test_the_field_table_is_not_empty() -> None:
    # Guards the parser itself: a table this test cannot read would make every
    # assertion below pass vacuously.
    assert len(field_rows()) >= 20


def test_every_field_the_table_says_we_query_is_in_the_queries() -> None:
    queries = QUERIES.read_text(encoding="utf-8")
    missing = [field for field, used in field_rows() if used == "yes" and field not in queries]
    assert missing == [], f"documented as queried but absent from queries.py: {missing}"


def test_every_field_the_table_says_we_do_not_query_is_absent() -> None:
    queries = QUERIES.read_text(encoding="utf-8")
    present = [field for field, used in field_rows() if used == "no" and field in queries]
    assert present == [], f"documented as unused but present in queries.py: {present}"
```

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_skills.py -v`
Expected: FAIL — `FileNotFoundError`, because the skill does not exist yet.

- [ ] **Step 3: Write the skill**

`.claude/skills/wcl-api/SKILL.md`. Begin with this frontmatter and heading:

```markdown
---
name: wcl-api
description: Use when writing or changing any code that queries the Warcraft Logs API — the verified field names, the terms of service, and the rate-limit budget
---

# The Warcraft Logs API, as verified

This is the live reference. `docs/plans/2026-09-03-mplus-postmortem-design.md` §2 points here.

**Every claim carries how it was verified and when.** A field name with no date is a defect, not
a shortcut. This project shipped a half-feature that does nothing because a line said "verified"
and had never been run — see the debuff row below.

**Never invent a field name.** If a field is not in the table, verify it against the live schema
and add a row, with the date.
```

Then the table. Include one row per field, with the dates and `In queries.py` values below — these were measured on 2026-09-05 by reading `src/wowperf/adapters/wcl/queries.py`, and the test in Step 1 keeps them true:

```markdown
## Fields

| Field | Appears on | Verified | In queries.py |
| --- | --- | --- | --- |
| `keystoneLevel` | `ReportFight` | 2026-09-03 | yes |
| `keystoneAffixes` | `ReportFight` | 2026-09-03 | yes |
| `keystoneTime` | `ReportFight` | 2026-09-03 | yes |
| `keystoneBonus` | `ReportFight` | 2026-09-03 | yes |
| `countReached` | `ReportFight` | 2026-09-03 | yes |
| `countRequired` | `ReportFight` | 2026-09-03 | yes |
| `npcCountMap` | `ReportFight` | 2026-09-03 | yes |
| `rating` | `ReportFight` | 2026-09-03 | no |
| `friendlyPlayers` | `ReportFight` | 2026-09-04 | yes |
| `friendlySpecs` | `ReportFight` | 2026-09-04 | yes |
| `friendlyItemLevels` | `ReportFight` | 2026-09-04 | yes |
| `dungeonPulls` | `ReportFight` | 2026-09-03 | yes |
| `encounterID` | `ReportDungeonPull` | 2026-09-03 | yes |
| `enemyNPCs` | `ReportDungeonPull` | 2026-09-03 | yes |
| `gameID` | `ReportDungeonPull.enemyNPCs` | 2026-09-03 | yes |
| `masterData` | `Report` | 2026-09-03 | yes |
| `allowUnlisted` | `reportData.report` argument | 2026-09-03 | yes |
| `rateLimitData` | `Query` | 2026-09-04 | yes |
| `limitPerHour` | `RateLimitData` | 2026-09-04 | yes |
| `pointsSpentThisHour` | `RateLimitData` | 2026-09-04 | yes |
| `pointsResetIn` | `RateLimitData` | 2026-09-04 | yes |
| `characterRankings` | `worldData.encounter` | 2026-09-03 | yes |
| `fightRankings` | `worldData.encounter` | 2026-09-03 | yes |
| `fightIDs` | `table` argument | 2026-09-05 | yes |
| `hostilityType` | `table` argument | 2026-09-05 | yes |
| `sourceID` | `table` argument | 2026-09-05 | yes |
| `targetID` | `table` argument | 2026-09-05 | yes |
```

**Before committing, run the test from Step 1 and correct any row it rejects rather than editing the test.** The table is a claim about the code; the code wins.

After the table, carry across design §2's prose, restructured under these headings and otherwise **unchanged in substance**:

- `## The endpoint and auth` — from §2.1: the endpoint URL, OAuth2 client credentials, the token URI and Basic-auth arrangement, where clients are created, and the fact that client credentials read public reports only (unlisted works through `allowUnlisted: true` when the code is known; private needs the authorization-code flow, which is not implemented).
- `## Rate limit` — from §2.1: points per hour per client on fixed one-hour cycles; `limitPerHour: 3600` read by live introspection on 2026-09-04 for the unsubscribed tier; read the real value at runtime rather than hardcoding it; the point-cost formula is undocumented, `pointsSpentThisHour` is a Float implying fractional costs, so measure rather than predict. Add the two measured costs this project has: roughly 28 points for a full compared analysis, and 12.02 points for a roster query plus four aura tables plus a `rateLimitData` read (2026-09-05).
- `## Mythic+ in the schema` — from §2.2: what makes a complete run, the index-aligned roster arrays and the trap that `masterData.actors` spans the whole report rather than one fight, `dungeonPulls` segmentation, `npcCountMap` joined against `UNIT_DIED`, and that fight and pull timestamps are relative to report start while `Report.startTime` is absolute epoch milliseconds.
- `## Aura tables` — from §2.2: the `table` signature, what it returns, that uptime is pre-aggregated so no event pagination is needed, and that `bands` make a sub-window an intersection rather than a second query.
- `## The debuff half cannot be scoped to one caster` — from §2.2, **including the five-row measurement table verbatim**, and the closing sentence that anything built on the per-player reading returns nothing, silently. This is the entry the skill's opening paragraph points at; keep it prominent.
- `## Leaderboards return report codes` — from §2.3, including the **unverified** `bracket = keystoneLevel - 1` convention, clearly marked as unverified.
- `## Terms of service` — from §2.4: §5d prohibits scraping, building databases and permanent copies; §2c prohibits multiple credentials to multiply quota; we never accumulate a dataset.
- `## Corrections to widespread errors` — from §2.5: rDPS/aDPS/nDPS/cDPS do not exist in World of Warcraft; Warcraft Logs computes Activity from damage events, not casts.

Do **not** carry across §2.6 (existing tools). It is competitive context for the design, not an API reference, and it stays in the design document.

- [ ] **Step 4: Run the test and watch it pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_skills.py -v`
Expected: 3 passed.

If `test_every_field_the_table_says_we_query_is_in_the_queries` fails, a row's `In queries.py` value is wrong — fix the row. If `test_the_field_table_is_not_empty` fails, the table's formatting does not match the parser; fix the table, not the regex.

- [ ] **Step 5: Replace design §2 with a pointer**

In `docs/plans/2026-09-03-mplus-postmortem-design.md`, replace the whole of §2 — from the `## 2. Verified context` heading through to just before `## 3. Architecture` — **except §2.6**, which stays. The replacement:

```markdown
## 2. Verified context

The verified API reference now lives in `.claude/skills/wcl-api/SKILL.md`, where every claim
carries the date it was checked and a field table that a test holds against the code. It moved
there on 2026-09-05: two copies of a schema reference drift, and the drifted one is read as true.

### 2.6 Existing tools
```

...followed by the existing §2.6 content unchanged.

- [ ] **Step 6: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add .claude/skills/wcl-api/SKILL.md tests/test_skills.py docs/plans/2026-09-03-mplus-postmortem-design.md
git commit -m "Move the verified API reference into a skill that a test holds honest

A schema reference is only worth what its verification dates are worth. Keeping
it in one place, with a date beside every claim and a test asserting the fields
we say we query are the fields we query, is what stops the next session
inventing a field name the way Plan D's debuff half was built on one."
```

---

### Task 4: The `mplus-analysis` skill

**Files:**
- Create: `.claude/skills/mplus-analysis/SKILL.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `.claude/skills/mplus-analysis/SKILL.md`.

This skill is prose and has no test. It is what a session needs in order to read a findings file honestly — and it is also the answer when someone asks a domain question having run nothing.

- [ ] **Step 1: Write the skill**

`.claude/skills/mplus-analysis/SKILL.md`:

```markdown
---
name: mplus-analysis
description: Use when interpreting a wowperf findings file, or answering a question about what this project's Mythic+ analysis can and cannot honestly say
---

# Interpreting a Mythic+ run

## Everything is seconds

A keystone is a race. The unit that makes findings comparable is time, so every analyser that can
express a loss in seconds does, and `seconds_lost` is what the findings are ranked by.

A finding with `seconds_lost: null` is not a small finding. It is one where no honest figure
exists — a missing defensive, a talent the top parse takes and you do not. Never treat `null` as
zero, and never sort it as though it were.

## Findings are ranked, never summed

The findings file says this itself, in `findings_are_ranked_not_additive`. It is the single
easiest way to produce a confident wrong number, so it is worth restating:

- `compare.duration` is the total gap against the reference run. It already contains every other
  `seconds_lost` figure in the file.
- `time.gap.*` and `compare.downtime` both nest inside `time.residual`.
- `deaths.single.*`, `deaths.chain.*` and `deaths.repeat.*` nest inside `deaths.total`.
- `compare.route.skipped.*` overlaps the waste `trash.overage` already reports.

Adding any two of those together produces a number larger than the run. The report prints
"Already counted inside …" under a nested row for exactly this reason.

## What each confidence badge licenses you to say

Every finding carries one. It is the difference between a report that is trusted and one that is
argued with.

| Badge | What it means | What you may write |
| --- | --- | --- |
| `measured` | read from the log, or arithmetic over logged facts | "was", "cost", plain assertion |
| `derived` | reconstructed by a documented rule, or a modelling choice that could be wrong | "works out to", "on this reckoning" |
| `inferred` | requires an assumption the log cannot confirm | "suggests", "looks like", never a flat claim |

Asserting an `inferred` finding as fact is the fastest way to lose a reader who knows the game
better than the tool does.

## Why damage goes unranked

Mythic+ has no damage leaderboard worth comparing against, and damage in a key is dominated by
pull size and route rather than by play. This project therefore does not rank damage, and
`players.py` states a player's damage taken against the **group median** with the analyser's own
caveat attached: it is a difference, not a mistake. The log does not record whether a hit could
have been dodged.

Do not turn that into "avoidable damage". The report deliberately refuses the phrase.

A tank taking many multiples of the group median from melee is the job, not a finding. The card
names the class and spec beside the figure so a reader can discount it on sight.

## Activity is cast-based here, and Warcraft Logs' is not

Warcraft Logs computes Activity from damage events, so damage-over-time ticks mask real downtime.
This project counts `SPELL_CAST_SUCCESS` instead. The two numbers will not agree, and ours is the
one that answers "were you doing something".

The cast count is deliberately coarse — it is a floor on time spent acting, not a simulation of a
rotation. Do not present it as a share of anything.

## The confounds the comparison declares rather than corrects

A reference run is a different group on a different key. The comparison states its confounds
instead of adjusting for them, because adjusting would invent a number:

- **Group composition.** Which packs can be held, which mechanics are trivial, and how much damage
  a route can absorb all change with the roster.
- **Keystone level.** A level gap makes every duration-shaped comparison misleading, and the tool
  withholds those comparisons entirely rather than printing one.
- **The spell comparison runs on boss pulls only**, so a spell used mainly on trash will look
  unused.
- **The parse reference is a different character.** A missing talent is a prompt to check a build,
  not a verdict on it.

When a comparison was withheld, the report says why in the tool's own words. Repeat that reason;
do not invent a better-sounding one.

## Reading the file

`out/<code>-<fight>.findings.json` carries the run's metadata, both reference runs when they were
fetched, the non-additivity warning, and the findings themselves — each with an `id`, a `title`, a
`detail`, an `evidence` list, a `confidence` and a `seconds_lost`.

The `title` is prose written for a reader. The `id` is a machine identifier. When you want to
point a reader at a finding, echo its title — they can find it on the page. An id means nothing to
them.
```

- [ ] **Step 2: Check it reads as it should**

Read the file top to bottom as though you had never seen this project. Every claim in it must be
one you could point at code or at the design for. If you find one you cannot, remove it — an
interpretation guide that overstates is worse than a short one.

- [ ] **Step 3: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add .claude/skills/mplus-analysis/SKILL.md
git commit -m "Write down what the findings license a reader to say

The badges are the difference between a report that is trusted and one that is
argued with, and until now what each one permits lived only in the design. So
did the reasons this project refuses to rank damage or to call any of it
avoidable."
```

---

### Task 5: The `analyzing-a-run` skill

**Files:**
- Create: `.claude/skills/analyzing-a-run/SKILL.md`
- Modify: `tests/test_skills.py`

**Interfaces:**
- Consumes: `tests/test_skills.py` from Task 3, whose `REPO_ROOT` and `re` import this task reuses.
- Produces: `.claude/skills/analyzing-a-run/SKILL.md`, and a second drift test asserting every `--flag` the skill tells you to type appears in `analyze --help`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_skills.py`:

```python
from typer.testing import CliRunner

from wowperf.cli import app

ANALYZING_SKILL = REPO_ROOT / ".claude" / "skills" / "analyzing-a-run" / "SKILL.md"

FLAG = re.compile(r"--[a-z][a-z-]+")


def test_every_flag_the_workflow_tells_you_to_type_exists() -> None:
    # Asserted against the command's own help rather than against cli.py's text:
    # typer infers `--player` and `--narrative` from their parameter names, so
    # neither string appears in the source at all.
    help_text = CliRunner().invoke(app, ["analyze", "--help"]).output
    flags = set(FLAG.findall(ANALYZING_SKILL.read_text(encoding="utf-8")))
    assert flags, "the workflow names no flags at all, so this test proves nothing"
    missing = sorted(flag for flag in flags if flag not in help_text)
    assert missing == [], f"named in the skill but absent from the command: {missing}"
```

**Note for the implementer:** rich wraps help output at 80 columns, breaking on spaces. No current
flag is long enough to be split, but if one ever is, widen the runner rather than loosening the
assertion.

- [ ] **Step 2: Run it to watch it fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_skills.py -v`
Expected: FAIL — `FileNotFoundError`, because the skill does not exist yet.

- [ ] **Step 3: Write the skill**

`.claude/skills/analyzing-a-run/SKILL.md`:

```markdown
---
name: analyzing-a-run
description: Use when given a Warcraft Logs Mythic+ URL to analyse — runs the tool, interprets the findings, writes the narrative, and hands back a finished report
---

# Analysing a run

You are given a Warcraft Logs URL. You hand back one HTML file and say what it found.

## The workflow

1. **Run the tool.**

   ```bash
   uv run wowperf analyze <url>
   ```

   Add `--player NAME` when the person named someone other than the report's owner. Add
   `--no-compare` only if they asked for the run in isolation; the comparison is the most useful
   half of the report.

2. **Read `out/<code>-<fight>.findings.json`.** The command prints the path. Do not read the HTML —
   it is for people, and every fact in it came from this file.

3. **Read the `mplus-analysis` skill before forming an opinion.** It carries what the badges
   license you to say, why findings are never summed, and the confounds the comparison declares.

4. **Write the narrative** to `out/<code>-<fight>.narrative.md`. See below for what it must and
   must not contain.

5. **Re-run with the narrative.**

   ```bash
   uv run wowperf analyze <url> --narrative out/<code>-<fight>.narrative.md
   ```

   Every response is cached from step 1, so this spends no API quota and takes about fifteen
   seconds.

6. **Hand over the HTML path.**

7. **Say the conclusion in chat too.** Nobody should have to open a file to learn what the tool
   found.

## The narrative

**It states no numbers.** Not one digit. The command will refuse it, before fetching anything, and
name every offending line.

That is not a formatting rule. Every figure on the page already sits in a section that owns it,
badged and sourced, directly below the narrative. A number repeated up there is a second, unbadged
claim competing with the first.

The rule is "state no quantities"; the check only catches numerals. "You lost three minutes to
travel" would pass and is still wrong — write the meaning, and let the ledger carry the figure.

**Shape.** Three to six sentences. Lead with what dominated and what *kind* of problem it is. Say
what to change. Hedge where the finding is inferred.

**Echo finding titles, never ids.** A title is prose a reader can scan down the page and find;
`compare.route.skipped.2` means nothing to them.

**It renders as plain text.** Escaped, pre-wrapped, not Markdown. Asterisks arrive as asterisks.

### Four things it must never do

1. **Restate the ledger in words.** The ledger already says it, with figures, better.
2. **Add figures up.** The findings file explains why in `findings_are_ranked_not_additive`.
3. **Assert an `inferred` finding as fact.**
4. **Give advice that traces to no finding at all.**

### What good looks like

> Your losses are route, not execution. The largest figure on this page is time spent outside
> pulls, and every one of the biggest ranked losses beneath it is a gap between packs — the group
> was travelling or waiting, not fighting. Underneath that, you pulled several packs the faster
> reference run skipped, which is why the trash overage and the skipped-pack findings both appear:
> one detour, counted two ways.
>
> Deaths barely register beside it, and nothing in the damage findings suggests a mechanical
> problem worth fixing before the route is.
>
> Treat the missing-talent finding as a prompt rather than a verdict — the spell comparison runs on
> boss pulls only, and the reference is a different character on a different key.

## When it goes wrong

- **No credentials.** The tool needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in the environment.
  Ask the person to set them; never read them from a file and never print them.
- **Not a completed keystone.** The URL must point at a Mythic+ run that finished. A wipe, a raid
  fight or a report code with no keystone fight will fail with a message saying so.
- **A reference could not be fetched.** The report still renders, with the affected sections
  withheld and stating the tool's own reason. Say so rather than pretending the comparison ran.
- **Quota.** The budget is 3600 points an hour; a full compared analysis costs roughly 28. This is
  not a constraint in normal use, but it is a reason not to loop.
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_skills.py -v`
Expected: 4 passed.

If a flag is reported missing, the skill named one the CLI does not have — fix the skill.

- [ ] **Step 5: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add .claude/skills/analyzing-a-run/SKILL.md tests/test_skills.py
git commit -m "Write the workflow that turns a URL into a finished report

The two-pass shape is not obvious from the outside: the second run costs
nothing because everything is cached, which is why no separate narrate command
exists. Writing it down is what stops the next session inventing one."
```

---

### Task 6: The repository describes what it has

**Files:**
- Modify: `CLAUDE.md` — the skills table and the sentence promising three more
- Modify: `docs/plans/2026-09-03-mplus-postmortem-design.md` — §8

**Interfaces:**
- Consumes: the three skills from Tasks 3 to 5.
- Produces: no code. A correct repository description.

- [ ] **Step 1: Update the skills table in `CLAUDE.md`**

The table currently has one row, for `testing/test-driven-development`. Add three, and **delete the
sentence beginning "Three more land during slice 1"** — they have landed.

```markdown
| Skill | Read before… |
| --- | --- |
| `testing/test-driven-development` | Writing any test in this repository |
| `wcl-api` | Writing or changing any code that queries the Warcraft Logs API |
| `mplus-analysis` | Interpreting a findings file, or answering a question about what the analysis can honestly say |
| `analyzing-a-run` | Handling a Warcraft Logs URL end to end |
```

- [ ] **Step 2: Record the guardrail in `CLAUDE.md`'s invariants**

The "Invariants not to break" list already says "The LLM never computes a number." Extend that
entry so it covers the narrative too:

```markdown
- **The LLM never computes a number.** Every metric comes from tested Python. Claude reads the
  findings JSON and interprets it; it does not calculate, and it does not parse the HTML. The
  narrative it writes states **no numbers at all** — `analyze --narrative` refuses a file
  containing any digit, before fetching anything.
```

- [ ] **Step 3: Amend design §8 to record what shipped**

In `docs/plans/2026-09-03-mplus-postmortem-design.md` §8, the guardrail paragraph currently says a
number absent from the findings file may not appear in the narrative. That was loosened to
something both stronger and checkable. Amend it in place, in the style of the document's existing
amendments — struck through with the date and reason:

- ~~"A number absent from the findings file may not appear in the narrative."~~ **Amended
  2026-09-05:** the narrative states **no** numbers. Every figure already sits in a badged section
  directly below it, so a number repeated in the narrative is a second, unbadged claim competing
  with the first. `analyze --narrative` enforces it by refusing any digit, before fetching. The
  check is a tripwire rather than a proof — spelled-out quantities pass, and the instruction that
  forbids them lives in `analyzing-a-run`. See
  `docs/plans/2026-09-05-mplus-inference-layer-design.md` §3.

Add a line under §8.1 noting the three skills now exist at `.claude/skills/`, and that `wcl-api`
holds what was §2.

- [ ] **Step 4: Run the gate and commit**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest && uv run ruff check . && uv run mypy`

```bash
git add CLAUDE.md docs/plans/2026-09-03-mplus-postmortem-design.md
git commit -m "Record that the inference layer shipped

The design promised three skills and a guardrail that was an instruction. What
shipped is three skills and a guardrail with tested Python behind it, which is
a stronger claim than the one it replaces and deserves to be written down as
what the repository now guarantees."
```

---

## Plan Self-Review

**Spec coverage.** Design §2's two layers are the premise, not a task. §3's guardrail is Tasks 1
and 2 — §3.1's rule, §3.2's location and error format, §3.3's tripwire honesty, which appears both
in the docstring and as a named test. §4's three skills are Tasks 3, 4 and 5; §4.1's field-table
requirement is Task 3 Step 3, and its "verified when" principle is the table's `Verified` column.
§5's workflow is Task 5's skill body, including the no-second-command reasoning in its commit
message and the four failure modes. §6's narrative shape and four anti-patterns are Task 5. §7's
unchanged command surface is honoured by Task 2 adding no flag. §8's tests are Tasks 1, 2, 3 and 5.
§9's file list is the File Structure table. §11's six decisions are each implemented by the task
that owns them.

**Nothing in the spec is unimplemented.** §10's out-of-scope list is honoured by absence: no task
changes the findings JSON, renders Markdown, or touches slices 2 to 4.

**Type consistency.** `lines_with_digits(text: str) -> tuple[tuple[int, str], ...]` is defined in
Task 1 and called in Task 2 with the same signature. `_narrative_digits_message(path, offending)`
is Task 2 only. `tests/test_skills.py`'s `REPO_ROOT`, `FIELD_ROW` and `field_rows()` are defined in
Task 3 and reused in Task 5, which adds `ANALYZING_SKILL` and `FLAG` beside them. The skill file
paths are identical everywhere they appear.

**Known gaps, carried forward.**

- **The drift tests read files, not the schema.** They catch a skill that has drifted from the
  code. They cannot catch a skill and the code drifting together away from the live API — only
  running against it can, which is what the `e2e`-marked tests are for.
- **The `In queries.py` column is a substring match.** A field name that is a substring of another
  identifier would pass falsely. Every current field name is distinctive enough that this does not
  bite; if one ever is not, the fix is to match on the quoted GraphQL token rather than the bare
  name. The same caveat applies to the flag test's search of the help text.
- **The flag test imports the app**, so `tests/test_skills.py` is not purely a documentation test.
  That is deliberate: asserting against the command's real help is the only way to check a flag
  typer never spells out in source.
- **`mplus-analysis` has no test at all**, because it makes no mechanical claim. Its accuracy rests
  on Task 4 Step 2 being done honestly.
