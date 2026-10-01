# Night page, rebuilt for the raid leader: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The night page answers the raid leader's questions first. Every boss opens on a summary
that leads with the outcome, kill speed, why attempts ended and what keeps over-landing. Every
attempt is a table row that opens its pull. A wipe's Summary says how it started. Each notice is
stated once.

**Architecture:**
- The two rollups and the boss's kill speed are new boss-level findings, computed in the
  analysis layer from findings the pulls already carry. The JSON writes them under the boss, and
  a summary still draws exactly its boss's findings.
- The page work lives in the pure builders under `src/wowperf/domain/report/` and in the Jinja
  partials the raid and night pages share. The templates loop and decide nothing.
- The one inline script gains one behaviour: a click on an attempt row shows that pull. It only
  shows and hides.

**Tech Stack:** Python 3.12, `uv`, pytest, pydantic `Frozen` models, Jinja2 templates under
`src/wowperf/adapters/render/`, Typer CLI, httpx `MockTransport` CLI harnesses, golden HTML
files regenerated with `--golden-update`.

**Spec:** `docs/plans/2026-10-01-raid-leader-night-design.md`, section 5 (sub-slice 2). Read §2
and §5 to §9 before any task. Sub-slice 1 (§4) is implemented, on branch
`raid-leader-night-design` (PR #47); this plan builds on it.

## Global Constraints

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`,
  `jinja2`, or touches the disk.
- **The report builder holds every judgement; the templates loop and decide nothing.** A sentence
  the page prints is a constant or a builder output, never composed in a template.
- **Every finding carries a confidence badge.** A rollup takes the confidence of the findings it
  counts. Where those are mixed, it takes the least certain of them
  (`inferred` < `derived` < `measured`).
- **Findings are never summed, and the narrative states no numbers.** Each new aggregate sets
  `Finding.quantifier` with `quantifier_for(matching, total)` (`src/wowperf/domain/findings.py`),
  so a narrative can echo it.
- **The page loads its icons and nothing else, with exactly one inline script.** That script may
  show, hide and highlight. It must not use any token in `FORBIDDEN_IN_SCRIPT`
  (`tests/adapters/render/test_html_invariants.py`), nor `createElement`, `innerHTML` or
  `disabled` (`tests/adapters/render/test_night_html_invariants.py`).
- **Every fragment link lands on an anchor that exists.** Every element id is unique across the
  night page.
- **No hand-written boss knowledge.** No mechanic or ability is named in code.
- **Every code file starts with two `ABOUTME: ` lines.**
- **Tests never carry a real character name.** Use `Emberkin`, `Stonewake`, `Bríala`,
  `Кириллица`. Boss names in tests are invented.
- **Commits:**
  - imperative subject, with no `feat:`/`fix:` prefix, and a body that says why;
  - plain ASCII only;
  - end with `Co-Authored-By: <the model that wrote it> <noreply@anthropic.com>`;
  - never `--no-verify`;
  - commit with `/mingw64/bin/git`.
- **Toolchain:** every Bash command that runs `uv` starts with `export PATH="$HOME/.local/bin:$PATH";`.
  Tests: `uv run pytest`. Lint: `uv run ruff check .`. Types: `uv run mypy` (no paths).
- **Goldens:** three golden pages exist:
  - `tests/adapters/render/golden/raid.html` (a kill);
  - `tests/adapters/render/golden/night.html`;
  - `tests/adapters/render/golden/progression.html`.

  Regenerate one with `uv run pytest <its test file> --golden-update`, then read the diff
  (`/mingw64/bin/git diff --stat` and the hunks) and say in the report what changed. A golden
  diff that touches anything the task did not set out to change is a finding: stop and report it.
- **The night page has a size budget.** `TRIMMED_NIGHT_BUDGET_BYTES` in
  `tests/adapters/render/test_night_html_invariants.py` caps it. If a task trips the budget,
  report the new size; do not raise the bound silently.
- **The brief's code is a strong default, not scripture.** If a worked test or snippet fails,
  first diagnose whether the fixture or the implementation is wrong, then change one, and report
  the evidence.
- **Before asserting on a literal, grep the tree for it.** If it is already on the page or in the
  output for another reason, the assertion is vacuous: pick a literal only this change can
  produce.
- **A test changed on purpose is named, not silently edited.** Where this plan changes what an
  existing test pins, the task lists that test and its new expectation. Any other existing test
  that fails is a finding to report, not a test to rewrite.

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `src/wowperf/domain/report/frame.py` | modify | `fight_ranges(ids)`: "Fight 8", "Fights 8–13", "Fights 8–10, 12 and 15" |
| `src/wowperf/domain/report/night_build.py` | modify | night Provenance groups reasons and drops pull-level pace lines; parse absence once; every boss gets a summary; summary receives pull findings and pace |
| `src/wowperf/domain/report/raid_build.py` | modify | the wipe Summary's opening; the pace pointer in any state; a kill's Summary opens on kill speed; the parse absence once |
| `src/wowperf/domain/report/raid_model.py` | modify | `WipeOpening`, `pace_pointer`, `pace_lead`, `kill_speed` |
| `src/wowperf/domain/report/raid_players.py`, `players.py` | modify | a card says nothing when its reason is the fight's, stated once elsewhere |
| `src/wowperf/domain/analysis/attempt_shape.py` | modify | `VERDICT_HEADLINES` and `verdict_kind(finding)` |
| `src/wowperf/domain/analysis/progression_repeats.py` | modify | public `first_roster_death(one)` |
| `src/wowperf/domain/analysis/deaths.py` | modify | public `chains(deaths)` |
| `src/wowperf/domain/analysis/night_rollups.py` | create | `progression.lead.kill_speed`, `progression.lead.verdicts`, `progression.lead.overlanding` |
| `src/wowperf/domain/analysis/night_service.py` | modify | `analyse_night_boss` takes the pulls' findings and which pulls were compared |
| `src/wowperf/domain/report/progression_*.py` | modify | headline, `lead_rows`, repeat pointers, new attempt columns |
| `src/wowperf/cli.py` | modify | `night` computes pull findings before boss findings |
| `src/wowperf/adapters/render/*.j2` | modify | `_raid_summary`, `_raid_damage`, `_players`, `_progression_summary`, `_progression_attempts`, `night.html.j2`, `night.js.j2` |
| `.claude/skills/analyzing-a-run/SKILL.md`, `.claude/skills/mplus-analysis/SKILL.md`, `README.md` | modify | what the night page shows |

---

### Task 1: Night Provenance states each reason once

**Files:**
- Modify: `src/wowperf/domain/report/frame.py`
- Modify: `src/wowperf/domain/report/night_build.py` (`_withheld`, `_pace_withheld_line`, the `NightProvenance(...)` build around line 294)
- Test: `tests/domain/report/test_frame.py` (create it if it does not exist; grep first), `tests/domain/report/test_night_build.py`

**Interfaces:**
- Produces: `fight_ranges(ids: Iterable[int]) -> str` in `wowperf.domain.report.frame`.

The spec (§5.5) says:
- Provenance groups identical reasons.
- A reason printed in a pull's Provenance is not printed again at night level.

Today a withheld pace notice is printed in both places: in the pull's Provenance, as "Damage pace
against other kills: …", and at night level, as "Fight N: damage pace against the kills was not
compared. …". This task drops the night-level copy. It also groups the night's remaining lines,
which are the failed pulls, by reason.

- [ ] **Step 1: Write the failing tests**

`tests/domain/report/test_frame.py`:

```python
from wowperf.domain.report.frame import fight_ranges


def test_one_fight_is_named_alone() -> None:
    assert fight_ranges([8]) == "Fight 8"


def test_consecutive_fights_read_as_a_range() -> None:
    assert fight_ranges([10, 8, 9, 11, 12, 13]) == "Fights 8–13"


def test_runs_and_strays_are_listed_in_order() -> None:
    assert fight_ranges([15, 8, 9, 10, 12]) == "Fights 8–10, 12 and 15"


def test_two_apart_fights_are_two_names_not_a_range() -> None:
    assert fight_ranges([3, 5]) == "Fights 3 and 5"


def test_a_repeated_id_is_named_once() -> None:
    assert fight_ranges([4, 4, 5]) == "Fights 4–5"
```

Then add to `tests/domain/report/test_night_build.py`, using the file's own builders:

- `test_two_failed_pulls_with_one_reason_are_one_provenance_line`. Two failed pulls (fights 8
  and 9) share a reason; one (fight 12) has another. Assert `report.provenance.withheld` is,
  in order:

  ```python
  (f"Fights 8–9 are not on this page: {SHARED}", f"Fight 12 is not on this page: {OTHER}")
  ```
- `test_a_withheld_pace_notice_is_stated_in_its_pull_and_not_again_for_the_night`. One pull
  handed a `PaceSample(unavailable=NO_BOSS)`. Assert:
  - no `report.provenance.withheld` line contains `NO_BOSS`;
  - that pull's own `report.provenance.withheld` contains `f"Damage pace against other kills: {NO_BOSS}"`.

**Deliberately replaced:** `test_a_withheld_pace_notice_becomes_one_provenance_line` (around line
800) pinned the night-level line. The second test above replaces it.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_frame.py tests/domain/report/test_night_build.py -q`
Expected: FAIL. `fight_ranges` does not exist, and the night line is still there.

- [ ] **Step 3: Implement**

In `frame.py` (import `Iterable` from `collections.abc`):

```python
def fight_ranges(ids: Iterable[int]) -> str:
    """Fight ids as a reader scans them: "Fight 8", "Fights 8–13", "Fights 8–10, 12 and 15".

    A run of consecutive ids reads as one range; ids are sorted and named once.
    """
    ordered = sorted(set(ids))
    runs: list[tuple[int, int]] = []
    for one in ordered:
        if runs and one == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], one)
        else:
            runs.append((one, one))
    parts = [str(first) if first == last else f"{first}–{last}" for first, last in runs]
    if len(ordered) == 1:
        return f"Fight {parts[0]}"
    listed = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    return f"Fights {listed}"
```

In `night_build.py`:
- Stop collecting `pace_withheld`, and delete `_pace_withheld_line` along with its now-unused
  imports.
- Rewrite `_withheld(failed_pulls)` to group by reason, keeping first-seen order of the reasons:

```python
def _withheld(failed_pulls: Sequence[FailedPull]) -> tuple[str, ...]:
    """One line per reason a pull is missing from the page, naming every pull it kept out."""
    by_reason: dict[str, list[int]] = {}
    for one in failed_pulls:
        by_reason.setdefault(one.reason, []).append(one.fight_id)
    return tuple(
        f"{fight_ranges(ids)} {'is' if len(ids) == 1 else 'are'} not on this page: {reason}"
        for reason, ids in by_reason.items()
    )
```

Check the real type name of the failed-pull items before relying on it; the code calls them
`loaded.failed_pulls`. Update `build_night_report`'s docstring where it describes the night
Provenance.

- [ ] **Step 4: Run the night tests, then the render tests**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report tests/adapters/render/test_night_html_invariants.py -q`

Expected:
- PASS, except possibly `test_a_boss_whose_every_pull_failed_still_gets_a_control_and_says_so`.
  It checks every `report.provenance.withheld` line is on the page verbatim. It should pass
  unchanged; if it does not, report why.
- If the night golden moved, regenerate it and confirm the diff is only the night Provenance
  lines.

- [ ] **Step 5: Commit**

```bash
/mingw64/bin/git add src/wowperf/domain/report/frame.py src/wowperf/domain/report/night_build.py tests/domain/report tests/adapters/render
/mingw64/bin/git commit -m "State each night Provenance reason once" -m "A pull's withheld pace reason was printed in that pull's Provenance and again for the night, and every failed pull had its own line even when the reason was shared." -m "Co-Authored-By: ..."
```

---

### Task 2: The parse comparison's absence, stated once

**Files:**
- Modify: `src/wowperf/domain/report/raid_build.py`
  - `build_raid_report`'s parameters;
  - the `_damage_section` call;
  - the Provenance parse lines (around lines 291-355).
- Modify: `src/wowperf/domain/report/raid_players.py` (`build_raid_players`)
- Modify: `src/wowperf/domain/report/players.py` (`_comparison_section`)
- Modify: `src/wowperf/domain/comparison/night_axis.py` (new constant)
- Modify: `src/wowperf/domain/report/night_build.py` (the `parse_withheld=` ternary around line 256)
- Modify: `src/wowperf/adapters/render/_players.html.j2` (lines 32-34)
- Test: `tests/domain/report/test_raid_build.py`, `tests/domain/report/test_raid_players.py`,
  `tests/domain/report/test_night_build.py`, `tests/test_cli_night.py`, `tests/adapters/render/*`

**Interfaces:**
- Produces:
  - `build_raid_report(..., parse_stated_elsewhere: bool = False)`;
  - `PULL_DAMAGE_NOT_DRAWN` in `wowperf.domain.comparison.night_axis`.

The spec (§5.5) says:
- **The night page.** The parse axis's absence is stated once, by the page-level
  `compare.parse.not_drawn` finding. It is not stated on every pull's Damage tab or on every
  player card.
- **A `raid --fight N` wipe.** The absence is stated once on the Damage tab and not on each
  player card.

The rule on both pages: a card whose reason is the fight's own says nothing. A raider whose own
reason differs keeps it (`test_a_raiders_own_reason_is_never_suppressed_with_the_attempts`
stays).

```python
PULL_DAMAGE_NOT_DRAWN = (
    "No damage comparison stands on this pull. Why the parse comparison is not drawn is stated "
    "once, under Findings about the night; why this pull's damage pace was not compared, where "
    "it was not, is in this pull's Provenance."
)
```

- [ ] **Step 1: Read before writing**

Read `build_raid_report` from its start to the `RaidReport(...)` return. The order matters:
- `players` is built (around line 213) before `parse_damage` (around line 286);
- the per-slug `compare.parse.unavailable.<slug>` findings land on each card's
  `spell_and_talent_rows`.

Read `_comparison_section` and `raid_players.build_raid_players`. Grep the templates for
`spell_and_talent`. Write down every site that reads the card's withheld reason before changing
any of them.

- [ ] **Step 2: Write the failing tests**

In `tests/domain/report/test_raid_build.py`, using `a_wipes_findings` and the file's builders:

- `test_a_wipe_states_the_parse_reason_on_its_damage_tab_and_on_no_card`:
  - `report.damage.reason == WITHHELD_DETAIL`;
  - every card's `spell_and_talent.reason == ""`;
  - no card's `spell_and_talent_rows` carries a `compare.parse.unavailable.` row;
  - exactly one Provenance line starts with `"Damage against other kills: "`.
- `test_a_parse_reason_shared_by_the_fight_is_placed_once_not_per_raider`:
  - the per-slug unavailable findings whose detail is the fight's reason are reached by no
    ledger field, because the Damage tab states them;
  - `test_every_finding_reaches_exactly_one_field` still passes, with those ids accounted as
    stated by the Damage tab. Read how that test counts first, then extend its accounting rather
    than exempting ids silently.

In `tests/domain/report/test_night_build.py`:

- `test_a_night_pull_says_nothing_of_the_parse_comparison_on_its_cards`. Every pull's cards have
  `spell_and_talent.reason == ""`. Run it for a compared wipe, a compared kill, and a pull handed
  no sample.
- `test_a_night_pull_with_no_damage_row_points_to_where_the_reasons_are`:
  - a pull handed `PaceSample(unavailable=NO_BOSS)` has `damage.reason == PULL_DAMAGE_NOT_DRAWN`;
  - no Provenance line starts with `"Damage against other kills"` or `"Spell and talent comparison"`.

In `tests/adapters/render/test_raid_html_invariants.py`:

- `test_a_wipes_parse_reason_is_on_the_page_once`:
  `a_wiped_raid_page().count(str(escape(WITHHELD_DETAIL))) == 1`.
  Grep how that page is built. If the reason also reaches the Provenance as "Damage against other
  kills: …", the count is 2. In that case assert 1 on the Damage panel's slice and 0 across every
  player card's slice.

**Deliberately changed** existing tests. Change each to the new expectation, and name it in the
report:
- `test_a_reason_the_whole_attempt_shares_is_disclosed_once_not_once_per_raider`
  (`test_raid_build.py:437`): the cards' reasons become `["", ""]`.
- `test_a_wipe_tells_every_raider_why_their_comparison_is_empty` (`test_raid_players.py:~148`):
  a wipe's cards carry no per-slug unavailable row when the reason is the fight's. Rename it,
  e.g. `test_a_wipe_states_its_shared_reason_on_no_card`.
- `test_a_pull_handed_a_pace_sample_states_the_wipes_own_reason_on_every_card`
  (`test_night_build.py:861`) becomes "on no card".
- `test_a_pull_handed_a_pace_sample_withholds_its_damage_tab_as_raid_does_on_that_wipe`
  (`:877`): the reason is `PULL_DAMAGE_NOT_DRAWN`.
- `test_a_pull_handed_a_pace_sample_states_the_wipes_reason_once_in_its_provenance` (`:891`):
  no parse line in the pull's Provenance.
- `test_a_pull_handed_no_pace_sample_keeps_no_comparison_ran_at_every_site` (`:909`):
  - the cards are silent;
  - the Damage reason is `PULL_DAMAGE_NOT_DRAWN`;
  - no parse lines in Provenance;
  - the night-level finding still says `NOT_DRAWN_DETAIL`.
- `test_a_kill_handed_a_pace_sample_states_the_nights_own_reason_for_its_parse_line` (`:926`):
  silent cards, and `PULL_DAMAGE_NOT_DRAWN` only if the kill's Damage tab has no row. A compared
  kill has kill-time and pace rows, so its Damage tab is present.
- `test_a_compared_night_says_on_each_wipe_what_raid_says_on_that_wipe` (`tests/test_cli_night.py:1302`):
  `WITHHELD_DETAIL` is no longer on a night page. Assert the page carries `NOT_DRAWN_COMPARED_DETAIL`
  exactly once (escaped), and keep its `NO_REFERENCE_SAMPLE` absence check.
- `test_a_night_read_with_no_compare_keeps_the_sentences_for_a_night_that_drew_nothing`
  (`tests/test_cli_night.py`): `NO_COMPARISON_RAN` no longer appears per pull. Assert the
  `--no-compare` page carries `NOT_DRAWN_DETAIL` exactly once, and `WITHHELD_DETAIL` not at all.

- [ ] **Step 3: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report tests/test_cli_night.py -q`
Expected: the new tests FAIL.

- [ ] **Step 4: Implement**

The required behaviour, with the implementation shape left to the existing code's order:

1. `_comparison_section(..., parse_withheld)`:
   - `parse_withheld == ""` means stated elsewhere: return `Section(state=SectionState.WITHHELD, reason="")`.
   - Add a second parameter, `stated_once: str = ""`. When the card's own
     `compare.parse.unavailable.<slug>` finding has `detail == stated_once`, return
     `Section(state=SectionState.WITHHELD, reason="")`.
2. `build_raid_players` gains `stated_once: str = ""`. It passes `stated_once` through. It drops
   from `spell_and_talent_rows` any `compare.parse.unavailable.<slug>` row whose finding's detail
   equals `stated_once`.
3. `build_raid_report`:
   - Compute the fight-wide parse reason before building players. That is the reason
     `_damage_section` would give with no parse rows: the first `compare.parse.unavailable`
     finding's detail, else the fallback. Pass it as `stated_once`.
   - With `parse_stated_elsewhere=True`, pass `parse_withheld=""` to the cards. The Damage tab's
     fallback becomes `PULL_DAMAGE_NOT_DRAWN`. Skip the Provenance lines "Damage against other
     kills: …" and "Spell and talent comparison: …".
4. Placement accounting: the stripped per-slug findings are stated by the Damage tab. Remove
   them from the findings that `place_rows` and `build_observations` see. That is the same
   treatment `verdict_notices` and `pace_notices` get at lines 185-203; follow that pattern.
5. `_players.html.j2` lines 32-34: print the withheld paragraph only when
   `player.spell_and_talent.reason` is non-empty.
6. `night_build.py`: replace the `parse_withheld=(...)` ternary with `parse_stated_elsewhere=True`.
   Drop the imports it orphans.
7. Update the docstrings and comments that describe per-card reasons, in `raid_build.py` (the
   comment at lines 307-331) and `night_build.py`.

- [ ] **Step 5: Run everything, regenerate goldens**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`

Then:
- Regenerate the raid and night goldens.
- The raid golden is a kill, so its cards may not move. Confirm.
- The night golden must lose the per-card and per-Damage-tab sentences and nothing else.
- Report the night page's new byte size against `TRIMMED_NIGHT_BUDGET_BYTES`.

- [ ] **Step 6: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests
/mingw64/bin/git commit -m "State the parse comparison's absence once a page" -m "The same paragraph stood on every player card and every pull's Damage tab; a raid leader read it twenty times per pull and the night's own note once." -m "Co-Authored-By: ..."
```

---

### Task 3: A wipe's Summary says how it started

**Files:**
- Modify: `src/wowperf/domain/analysis/deaths.py`. Rename `_chains` to `chains`, keep one
  definition, and update its callers.
- Modify: `src/wowperf/domain/analysis/progression_repeats.py`. Add `first_roster_death`, and
  have `_first_death_ms` use it.
- Modify: `src/wowperf/domain/report/raid_model.py` (`WipeOpening`, plus `RaidReport` fields)
- Modify: `src/wowperf/domain/report/raid_build.py`
- Modify: `src/wowperf/adapters/render/_raid_summary.html.j2`
- Test: `tests/domain/analysis/test_progression_repeats.py`, `tests/domain/report/test_raid_build.py`,
  `tests/adapters/render/test_raid_html_invariants.py`, `tests/domain/report/test_night_build.py`

**Interfaces:**
- Produces:
  - `chains(deaths: tuple[Death, ...]) -> list[tuple[Death, ...]]` (`wowperf.domain.analysis.deaths`);
  - `first_roster_death(one: LoadedEncounter) -> Death | None` (`wowperf.domain.analysis.progression_repeats`);
  - `WipeOpening` with fields `first_death: str`, `held: str` and `chain: LedgerRow | None`;
  - `RaidReport.opening: WipeOpening | None = None`;
  - `RaidReport.pace_pointer: LedgerRow | None = None` and `RaidReport.pace_lead: str = ""`,
    which replace `pace_warning`.

The spec (§5.4) says that on a wipe the Summary no longer leads with `deaths.total` or ranks
losses in seconds. It shows, in order:
1. the `wipe.cause` verdict;
2. the first death, the chain it set off, and how long the raid held;
3. the pace state;
4. the alive chart.

`deaths.total` and the death costs stay on the Deaths tab. On a kill, the Summary is unchanged
here; Task 4 handles it.

The wording:

```python
FIRST_DEATH = "{name} ({spec} {class_name}) died first, to {ability}, at {clock}"
HELD = "The raid held {clock} after the first death"
NOBODY_DIED = "Nobody died in this attempt"
PACE_LEADS = {
    PaceState.BEHIND: "Ended behind the reference kills' pace.",
    PaceState.ON_PACE: "Ended on the reference kills' pace.",
    PaceState.AHEAD: "Ended ahead of the reference kills' pace.",
}
```

`{clock}` is `format_seconds(...)` from `wowperf.domain.report.frame` (m:ss). The first death's
clock is measured from the fight's start. `held` is `collapse_seconds(loaded)` formatted, or ""
when nobody died.

`chain` is a pointer to the deaths finding that holds the first death:
- `deaths.chain.0` when the first group of `chains(loaded.deaths)` holds more than one death;
- otherwise `deaths.single.0`.

Both numberings run in time order within their own kind (`deaths.py`, the `chain_rank` and
`single_rank` loop), so the first group is index 0 of its kind. If that finding is not in
`findings`, `chain` is None.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_progression_repeats.py`:

- `test_the_first_roster_death_is_the_earliest_death_of_a_rostered_player`. A non-roster death
  precedes a roster one; the function returns the roster one.
- `test_no_roster_death_is_none`.

`tests/domain/report/test_raid_build.py`. Build a wipe with three deaths: Emberkin at 42 s, and
Stonewake and Bríala within 10 s after. Hand it a pace sample that ends on pace.

- `test_a_wipe_summary_opens_on_how_it_started`:
  - `report.opening.first_death == "Emberkin (Frost Mage) died first, to <ability>, at 0:42"`.
    Use the fixture's own spec, class and ability.
  - `report.opening.held == f"The raid held {format_seconds(end - 42)} after the first death"`.
  - `report.opening.chain.finding_id == "deaths.chain.0"`.
- `test_a_wipe_summary_ranks_no_losses_in_seconds`:
  - `report.ledger_decomposition == ()` and `report.summary_pointers == ()`;
  - `"deaths.total"` is on `death_rows`.
- `test_a_wipe_summary_states_its_pace_in_any_state`:
  - on pace: `report.pace_lead == "Ended on the reference kills' pace."` and
    `report.pace_pointer.finding_id == PACE_ID`;
  - repeat for behind and ahead.
- `test_a_wipe_whose_first_death_was_alone_points_at_that_single`: one isolated death, so
  `chain.finding_id == "deaths.single.0"`.
- `test_a_deathless_wipe_says_nobody_died`: `opening.first_death == NOBODY_DIED`,
  `held == ""`, `chain is None`.
- `test_a_kill_summary_is_left_to_its_own_task`: on a kill, `report.opening is None` and
  `ledger_decomposition` is unchanged.

`tests/adapters/render/test_raid_html_invariants.py`:

- `test_a_wipes_summary_draws_how_it_started_and_no_decomposition`. In the Summary panel of a
  wiped page:
  - the opening's first-death line, the held line, and a pointer to `#finding-deaths.chain.0`
    are present;
  - "Figures that contain others" and "Biggest losses" are absent.

**Deliberately changed** existing tests:
- `test_a_behind_wipe_draws_the_pace_rows_the_chart_and_the_summary_pointer`
  (`test_raid_build.py:895`): it reads `pace_pointer` and
  `pace_lead == "Ended behind the reference kills' pace."`.
- `test_an_on_pace_wipe_draws_the_chart_but_raises_no_warning` (`:916`): an on-pace wipe now has
  a `pace_pointer` and the on-pace lead. Rename it to "…states it ended on pace".
- `test_a_kill_with_no_pace_sample_draws_no_pace_fields` (`:1005`) reads `pace_pointer is None`.
- `test_a_behind_wipe_draws_the_pace_chart_and_the_summary_pointer` (`test_raid_html_invariants.py:493`):
  the literal becomes `"Ended behind the reference kills' pace. The chart is on the Damage tab."`.
- `test_an_on_pace_wipe_draws_no_mark_and_no_pointer` (`:518`): an on-pace wipe draws the on-pace
  lead and a pointer. Rename it.
- `test_a_kill_with_a_pace_sample_draws_the_chart_and_card_but_no_summary_warning` (`:1745`): the
  kill draws no `pace_pointer`. Task 4 gives a kill its kill-speed pointers.
- `test_a_pull_given_a_pace_sample_draws_its_chart_row_and_pointer` and
  `test_a_pull_with_no_sample_draws_none_of_the_three` (`test_night_build.py:644`, `:680`): read
  `pace_pointer`.
- `test_the_only_raid_decomposition_heads_the_summary_and_is_not_drawn_twice`
  (`test_raid_build.py:331`): on a wipe there is no decomposition. Run it on a kill, or split it
  into a kill half (unchanged) and a wipe half (no decomposition, `deaths.total` on `death_rows`).
- `test_every_finding_reaches_exactly_one_field` (`:272`): its `placements()` removes one copy per
  `summary_pointers` entry. Make it also account for `opening.chain` and `pace_pointer`, which are
  pointers to cards placed elsewhere. Read it first.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain tests/adapters/render -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

`progression_repeats.py`:

```python
def first_roster_death(one: LoadedEncounter) -> Death | None:
    """The earliest death of a player on this attempt's roster, or None."""
    roster_ids = {player.actor_id for player in one.players}
    deaths = [death for death in one.deaths if death.actor_id in roster_ids]
    return min(deaths, key=lambda death: (death.timestamp_ms, death.actor_id), default=None)
```

Make `_first_death_ms` return `None if death is None else death.timestamp_ms` from it. Keep its
docstring true.

`raid_model.py`:

```python
class WipeOpening(Frozen):
    """How a wipe started: its first death, how long the raid held after it, and that death's card."""

    first_death: str
    held: str = ""
    chain: LedgerRow | None = None
```

Replace `pace_warning` with `pace_pointer: LedgerRow | None = None` and `pace_lead: str = ""`, and
add `opening: WipeOpening | None = None`. `all_raid_ledger_rows` walks none of the three, because
each is a pointer to a card drawn elsewhere. Say so in its docstring, as it says today for
`pace_warning`.

`raid_build.py`, in `build_raid_report`:
- On a wipe (`not loaded.encounter.kill`):
  - Set `ledger_decomposition = ()` and pass an empty `decomposition_ids` to `place_rows` and
    `build_summary_pointers`, so `deaths.total` falls through to `death_rows` (`("deaths.", "death_rows")`).
  - Set `summary_pointers = ()`.
- Build `opening` from `first_roster_death(loaded)`, the roster `Player` matching its `actor_id`,
  `collapse_seconds(loaded)` and `chains(loaded.deaths)`.
  - The chain pointer is `ledger_row(that_finding, titles_by_id, tooltips)`, with the finding
    looked up in `findings` by the id rule above.
- `pace_pointer` is `ledger_row(pace_finding, ...)` on a wipe whose reading has seconds, else None.
  `pace_lead` is `PACE_LEADS[reading.seconds[-1].state]` (`PaceState` from
  `wowperf.domain.comparison.pace_curve`).
- The opening's sentence constants live in `raid_build.py` beside the other Summary wording. If
  the file has a frame or wording module for such constants, put them there instead; check
  `raid_frame.py` first.

`_raid_summary.html.j2`: replace the `pace_warning` block, and add the opening after the verdict.
The final order is verdict, opening, pace, alive chart, decomposition, losses, other findings:

```jinja
{% if report.opening %}
<h2 id="{{ scope }}opening">How it started</h2>
<p class="sub">{{ report.opening.first_death }}{% if report.opening.held %}. {{ report.opening.held }}{% endif %}.</p>
{% if report.opening.chain %}{{ pointer(report.opening.chain) }}{% endif %}
{% endif %}
{% if report.pace_pointer %}
<p class="sub">{{ report.pace_lead }} The chart is on the Damage tab.</p>
{{ pointer(report.pace_pointer) }}
{% endif %}
```

Composing sentences from builder outputs with `. ` is a decision in the template. If a reviewer
would call it one, compose the whole line in the builder (`WipeOpening.line`) and print that.
Prefer that.

Rename `_chains` to `chains` in `deaths.py`; grep its callers.

- [ ] **Step 4: Run, regenerate goldens**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`

Regenerate the raid and night goldens:
- The raid golden is a kill: it must not move in this task. If it does, stop and report.
- The night golden's wipe pulls gain the opening and lose the decomposition and losses.

- [ ] **Step 5: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests
/mingw64/bin/git commit -m "Open a wipe's Summary on how it started" -m "A wipe is not a race: ranking its losses in seconds answered a Mythic+ question. The raid leader asks who died first, to what, how long the raid held, and why it ended." -m "Co-Authored-By: ..."
```

---

### Task 4: A kill's Summary opens on kill speed

**Files:**
- Modify: `src/wowperf/domain/report/raid_model.py` (`kill_speed`)
- Modify: `src/wowperf/domain/report/raid_build.py`
- Modify: `src/wowperf/adapters/render/_raid_summary.html.j2`
- Test: `tests/domain/report/test_raid_build.py`, `tests/adapters/render/test_raid_html_invariants.py`

**Interfaces:**
- Produces: `RaidReport.kill_speed: tuple[LedgerRow, ...] = ()`. These are pointers to the
  kill's `compare.kill.time` and `compare.pace.boss` cards, which stay on the Damage tab. They
  come in that order, each only if present.

- [ ] **Step 1: Write the failing tests**

In `test_raid_build.py`:

- `test_a_kill_summary_opens_on_its_kill_speed`. A kill whose findings carry `compare.kill.time`
  (from `analyse_kill_time` with a three-member sample) and `compare.pace.boss`. Assert:
  - `[row.finding_id for row in report.kill_speed] == [KILL_TIME_ID, PACE_ID]`;
  - both are still on `damage_rows`.
- `test_a_kill_with_no_reference_kill_has_no_kill_speed_pointers`: `report.kill_speed == ()`.
- `test_a_wipe_has_no_kill_speed_pointers`: a wipe with a `compare.pace.boss` has
  `kill_speed == ()`. Its pace is on `pace_pointer`.

In `test_raid_html_invariants.py`:

- `test_a_kill_summary_draws_kill_speed_first`. In the golden kill's Summary panel, the
  "Kill speed" heading comes before every other `<h2>`. A pointer to `#finding-compare.pace.boss`
  is present.

Grep the golden's fixture first. If it carries no `compare.kill.time` (no mechanics sample),
either give it one or assert only the pace pointer. Say which, and why.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/report/test_raid_build.py tests/adapters/render/test_raid_html_invariants.py -q`

- [ ] **Step 3: Implement**

In `build_raid_report`:

```python
    kill_speed = tuple(
        ledger_row(finding, titles_by_id, tooltips)
        for wanted in (KILL_TIME_ID, PACE_ID)
        for finding in findings
        if loaded.encounter.kill and finding.id == wanted
    )
```

`_raid_summary.html.j2`, first in the panel:

```jinja
{% if report.kill_speed %}
<h2 id="{{ scope }}kill-speed">Kill speed</h2>
<p class="sub">Against the execution leaderboard's kills. Each line opens its card on the Damage tab.</p>
{% for row in report.kill_speed %}{{ pointer(row) }}{% endfor %}
{% endif %}
```

`all_raid_ledger_rows` does not walk `kill_speed`; say so beside `pace_pointer`. Extend
`placements()` in `test_raid_build.py` the way Task 3 did.

- [ ] **Step 4: Run, regenerate the raid and night goldens, read the diffs**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`

The raid golden gains the "Kill speed" block and nothing else. In the night golden, only kill
pulls gain it.

- [ ] **Step 5: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests
/mingw64/bin/git commit -m "Open a kill's Summary on its kill speed" -m "After a kill the raid leader asks how fast it was against other kills; the answer sat on the Damage tab under the parse rows." -m "Co-Authored-By: ..."
```

---

### Task 5: The boss-level rollups

**Files:**
- Modify: `src/wowperf/domain/analysis/attempt_shape.py`
- Create: `src/wowperf/domain/analysis/night_rollups.py`
- Modify: `src/wowperf/domain/analysis/night_service.py`
- Modify: `src/wowperf/cli.py` (`night`: the order of `boss_findings` and `findings_by_fight`)
- Modify: `src/wowperf/domain/report/progression_ledger.py` (`PROGRESSION_PLACEMENTS`)
- Modify: `src/wowperf/domain/report/progression_model.py` (`lead_rows`) and `progression_build.py`
- Test: `tests/domain/analysis/test_attempt_shape.py`, `tests/domain/analysis/test_night_rollups.py`
  (create), `tests/domain/analysis/test_night_service.py`, `tests/domain/report/test_progression_ledger.py`,
  `tests/test_cli_night.py`

**Interfaces:**
- Produces:
  - `VERDICT_HEADLINES: dict[str, str]` and `verdict_kind(finding: Finding) -> str` in
    `attempt_shape.py`. The kinds are `"both"`, `"execution"`, `"throughput"` and `"withheld"`;
    any other finding gives `""`.
  - `analyse_night_rollups(attempts, pull_findings, mechanics_compared) -> list[Finding]` in
    `night_rollups.py`. It returns, in this fixed order and each only where it fires:
    `progression.lead.kill_speed`, `progression.lead.verdicts`, `progression.lead.overlanding`.
  - `analyse_night_boss(series, defensives, *, death_cards, pace=None, pull_findings=None, mechanics_compared=frozenset())`.
  - `ProgressionReport.lead_rows: tuple[LedgerRow, ...] = ()`, placed by the prefix `"progression.lead."`.

The rules (spec §5.2):

1. **`progression.lead.kill_speed`**: only when the boss died.
   - It reads the kill pull's `compare.kill.time` and `compare.pace.boss`.
   - Title: the kill-time finding's title.
   - Evidence: `f"On the kill, fight {fight_id}"`, then the kill time's evidence, then
     `f"Damage pace: {pace.title}"` if a pace finding is present.
   - Confidence: the least certain of the two.
   - `quantifier`: `""`, since it is one kill's reading.
   - It is absent when the kill pull carries neither finding.
2. **`progression.lead.verdicts`**: over the boss's drawn wipes that carry `wipe.cause` or
   `wipe.cause.withheld`.
   - Count each kind. Name withheld verdicts by their reason, using the withheld finding's
     `evidence[0]`, e.g. "neither shape fit this attempt".
   - Title: `f"{top} of {total} wipes ended on {kind}"` for the most common read kind. With no read
     verdict at all, the title is `f"No wipe's verdict could be read, of {total}"`.
   - Evidence: one line per kind, most common first, as
     `f"{kind}: {count} of {total} wipes ({fight_ranges(ids)})"`. Then one line per withheld reason,
     as `f"withheld, {reason}: {count} of {total} wipes ({fight_ranges(ids)})"`.
   - `quantifier`: `quantifier_for(top, total)`.
   - Confidence: `inferred` if any verdict was read, else `measured` (only withheld notices).
   - It needs at least one wipe.
3. **`progression.lead.overlanding`**: over the pulls in `mechanics_compared`, which are those
   whose mechanics sample had members.
   - For each `mechanics.ability.*` finding, count the distinct pulls by `ability_id`.
   - An ability fires when it is reported in two or more compared pulls, out of at least two
     compared pulls. This mirrors `repeat_killing_blow`'s rule (`progression_repeats.py`).
   - Cap at `MAX_REPEAT_ABILITIES` from the same module.
   - Title for one ability: `f"{name} over-landed in {n} of {compared} compared attempts"`. For
     several: `f"{k} abilities over-landed in more than one compared attempt"`.
   - Evidence: one line per ability in the single-ability form, plus its `fight_ranges(ids)`.
   - `ability_id`/`ability_name`: set only for a single ability.
   - `quantifier`: `quantifier_for(n, compared)` of the top ability.
   - Confidence: `derived`.

```python
VERDICT_HEADLINES = {
    "both": "both: the raid came apart, and the damage never caught up",
    "execution": "execution: the raid was taken apart",
    "throughput": "throughput: the raid held and the damage was not enough",
}
```

`classify_attempt` builds its titles from this dict, so its titles are byte-identical to today's.
`verdict_kind` inverts it:
- `finding.id == "wipe.cause"`: the kind whose headline the title ends with;
- `finding.id == WITHHELD_ID`: `"withheld"`;
- anything else: `""`.

- [ ] **Step 1: Write the failing tests**

`tests/domain/analysis/test_attempt_shape.py`:

- `test_each_verdict_title_reads_back_as_its_kind`. Build a `wipe.cause` per shape with the
  file's helpers, and assert `verdict_kind` gives `"execution"`, `"throughput"` and `"both"`.
- `test_a_withheld_verdict_reads_as_withheld_and_any_other_finding_as_nothing`.

`tests/domain/analysis/test_night_rollups.py`. Use `tests/domain/progression_fixtures.py`
(`a_loaded_attempt`, `a_loaded_series`). Build pull findings by hand as `Finding`s with the real
ids, and give each a `title` the real analyser would write: copy one from
`classify_attempt`/`analyse_kill_time` through the analysers themselves where cheap.

- `test_the_verdict_rollup_counts_each_kind_and_names_withheld_ones`. Four wipes: three
  execution (fights 20–22) and one withheld "neither shape fit this attempt" (fight 24). Assert:
  - title `"3 of 4 wipes ended on execution"`;
  - quantifier `"most"`;
  - confidence `inferred`;
  - evidence, in order:

    ```python
    ("execution: 3 of 4 wipes (Fights 20–22)",
     "withheld, neither shape fit this attempt: 1 of 4 wipes (Fight 24)")
    ```
- `test_a_boss_whose_every_verdict_was_withheld_says_so_as_measured`.
- `test_kills_are_not_counted_among_the_wipes`.
- `test_an_ability_over_landing_in_two_compared_pulls_is_named_once`. The same `ability_id` is in
  fights 3 and 5 of three compared pulls. Assert:
  - title `"<name> over-landed in 2 of 3 compared attempts"`;
  - quantifier `"most"`;
  - `ability_id` is set.
- `test_an_ability_reported_in_one_pull_does_not_repeat`.
- `test_a_pull_not_compared_is_not_in_the_denominator`. An ability is in 2 pulls, and 3 pulls
  exist but only 2 were compared. The title reads "2 of 2".
- `test_kill_speed_reads_the_kill_pulls_time_and_pace`. Assert the title equals the kill time's
  title, the evidence starts with `"On the kill, fight 9"`, and the confidence is `derived` (the
  pace's).
- `test_the_rollups_come_in_their_fixed_order`: ids are
  `["progression.lead.kill_speed", "progression.lead.verdicts", "progression.lead.overlanding"]`.

`tests/domain/report/test_progression_ledger.py`: parametrize the three new ids to `"lead_rows"`.

`tests/test_cli_night.py`:

- `test_a_bosss_rollups_are_written_under_the_boss`. Using the harness's compared night with two
  wipes at the first boss, the boss's `findings` in the JSON include `progression.lead.verdicts`,
  and no pull's findings do.

- [ ] **Step 2: Run to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/domain/analysis tests/domain/report/test_progression_ledger.py tests/test_cli_night.py -q`

- [ ] **Step 3: Implement**

1. `attempt_shape.py`: introduce `VERDICT_HEADLINES` and use it in `classify_attempt` for its
   three headlines; add `verdict_kind`.
2. `night_rollups.py`: write the three functions and the public `analyse_night_rollups`.
   - Import `fight_ranges` from `wowperf.domain.report.frame`. That is a domain-to-domain import,
     which is allowed. If the dependency direction (analysis importing report) is not already
     used anywhere, move `fight_ranges` to `wowperf.domain.findings` or a small
     `wowperf.domain.text` module, update Task 1's import, and say so.
3. `night_service.analyse_night_boss`: append
   `analyse_night_rollups(series.attempts_with_events, pull_findings, mechanics_compared)` when
   `pull_findings` is given.
4. `cli.py` `night`:
   - Build `findings_by_fight` before `boss_findings`.
   - Pass `pull_findings=findings_by_fight` and
     `mechanics_compared=frozenset(fight for fight, one in comparisons.items() if one.mechanics.members)`.
   - The JSON already writes `boss_findings[...]` under each boss. Confirm nothing else needs
     changing.
5. `PROGRESSION_PLACEMENTS`: add `("progression.lead.", "lead_rows")` first. `ProgressionReport`
   gains `lead_rows`; `all_progression_ledger_rows` walks it; `build_progression_report` fills it
   from `place_rows`.
   - `rank_raid_findings` sorts the `progression` family stably, so the fixed order survives.
     Assert it in `test_the_rollups_come_in_their_fixed_order` at the service level too.

- [ ] **Step 4: Run everything**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`

- `test_a_summary_draws_every_progression_finding_its_boss_earned`
  (`test_night_html_invariants.py:618`) compares drawn ids with `analyse_progression(boss)`. If
  its fixture has pull findings, it now also draws the rollups. Update its expected set to
  `analyse_night_boss`'s output, and name the change.
- `lead_rows` are not drawn until Task 6. If a template test fails because a placed row has no
  section, add the `lead_rows` loop to `_progression_summary.html.j2` now, as plain cards above
  "Other findings", and let Task 6 restyle it.

- [ ] **Step 5: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests
/mingw64/bin/git commit -m "Roll each boss's verdicts, over-landing and kill speed up to the boss" -m "The answers a raid leader wants per boss were spread across every pull; each rollup counts findings the pulls already carry and sets the quantifier a narrative may echo." -m "Co-Authored-By: ..."
```

---

### Task 6: Every boss opens on a summary that leads with the answers

**Files:**
- Modify: `src/wowperf/domain/report/night_build.py` (`MIN_PULLS_FOR_SUMMARY`)
- Modify: `src/wowperf/domain/report/progression_frame.py` (`build_progression_header`: `headline`)
- Modify: `src/wowperf/domain/report/progression_model.py` (`ProgressionHeader.headline`, `ProgressionReport.repeat_pointers`)
- Modify: `src/wowperf/domain/report/progression_build.py`
- Modify: `src/wowperf/adapters/render/_progression_summary.html.j2`, `night.html.j2` (the summary option label)
- Test: `tests/domain/report/test_night_build.py`, `tests/domain/report/test_progression_frame.py`,
  `tests/domain/report/test_progression_build.py`, `tests/adapters/render/test_night_html_invariants.py`,
  `tests/adapters/render/test_progression_html_invariants.py`, `tests/test_cli_night.py`

**Interfaces:**
- Produces:
  - `ProgressionHeader.headline: str`;
  - `ProgressionReport.repeat_pointers: tuple[LedgerRow, ...] = ()`, holding pointers to the
    Repeats cards of `progression.repeat.killing_blow`, `progression.repeat.first_death` and
    `progression.repeat.ability`, in that order, each only where present;
  - `MIN_PULLS_FOR_SUMMARY = 1`.

The spec says:
- **§5.1.** A boss pulled once has a summary too.
- **§5.2.** The Summary opens on the outcome: killed on attempt N, or the best depth reached.
  Then it shows, in a fixed order: kill speed, why attempts ended, what keeps over-landing, and
  the existing repeats. "Nothing else measured" no longer opens the tab.

The headline:
- **A kill:** the header's `outcome`, unchanged ("Killed on attempt 3 of 7").
- **No kill:** `f"{outcome}; the deepest left {left:.1f}% {depth_label}"`, where `left` is the
  deepest attempt's `remaining_percent`. If there is no reading, it is the `outcome` alone.

- [ ] **Step 1: Write the failing tests**

- `test_progression_frame.py`:
  - `test_a_killed_boss_headline_is_its_outcome`
  - `test_an_unkilled_boss_headline_names_its_deepest_attempt`. Fixture: deepest left 23.4% boss
    health; assert `"No kill in 4 attempts; the deepest left 23.4% boss health"`.
- `test_progression_build.py`:
  - `test_the_summary_points_at_the_three_repeats_in_their_order`
  - `test_a_summary_with_no_repeat_carries_no_pointer`
- `test_night_build.py`:
  - **Deliberately replaced:**
    - `test_a_boss_pulled_once_has_no_summary_and_a_boss_pulled_twice_has_one` (`:565`) becomes
      `test_every_boss_with_a_drawn_pull_has_a_summary`;
    - `test_the_threshold_counts_drawn_pulls_not_attempts` (`:580`) becomes a boss with zero
      drawn pulls having no summary (keep `test_a_boss_with_no_drawn_pull_has_no_summary`).
- `test_night_html_invariants.py`:
  - **Deliberately changed:**
    - `test_a_boss_pulled_more_than_once_opens_on_its_summary` (`:583`): every boss with a drawn
      pull opens on `b{i}-summary`;
    - `test_exactly_the_bosses_pulled_more_than_once_carry_a_summary_section` (`:599`): every boss
      with a drawn pull;
    - `test_each_pull_control_offers_its_own_bosss_pulls_and_no_others` (`:467`): the offered
      count is `count + 1` for every boss with a pull;
    - `test_the_summary_option_counts_deepened_pulls_not_attempts` (`:800`): the label for one
      pull reads `"Summary: 1 pull"`. Use `plural` from `frame.py`.
  - New: `test_a_summary_opens_on_its_headline_and_never_on_nothing_else_measured`. Each summary
    block's first `<h2>` holds its headline, and "Nothing else measured" is nowhere on the page.
- `test_progression_html_invariants.py`: the standalone page's Summary carries the headline. The
  progression golden changes; regenerate it and read the diff.
- `tests/test_cli_night.py` `test_each_boss_summary_draws_the_findings_the_file_writes_for_that_boss`
  (`:709`): it asserts that the once-pulled boss has no summary. It now has one, and its drawn ids
  equal its written ids. Name it.

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

`_progression_summary.html.j2`:

```jinja
{% from "_macros.html.j2" import ledger_row, pointer with context %}
<section class="panel" data-tab-panel="{{ scope }}main" id="{{ scope }}tab-summary">

<h2 id="{{ scope }}headline">{{ report.header.headline }}</h2>

{% if report.lead_rows %}
<div class="findings">
{% for row in report.lead_rows %}
{{ ledger_row(row) }}
{% endfor %}
</div>
{% endif %}

{% if report.repeat_pointers %}
<h2 id="{{ scope }}repeating">What kept repeating</h2>
<p class="sub">Each line opens its card on the Repeats tab.</p>
{% for row in report.repeat_pointers %}{{ pointer(row) }}{% endfor %}
{% endif %}

{% if report.observations %}
<h2 id="{{ scope }}observations">Other findings</h2>
<p class="sub">Findings no other section claimed.</p>
<div class="findings">
{% for row in report.observations %}
{{ ledger_row(row) }}
{% endfor %}
</div>
{% endif %}

<p class="sub">Attempts holds every attempt, Repeats what kept happening across them, and Best
attempt what the deepest one did differently.</p>

</section>
```

Rewrite the template's two ABOUTME lines to describe it.

`night_build.py`: `MIN_PULLS_FOR_SUMMARY = 1`; rewrite its docstring and the one at lines
197-202. The summary option label in `night.html.j2` is a judgement (singular or plural). Put it
on `BossSection` as `summary_label: str`, built in `night_build`, and print that.

Update the `night` section of `.claude/skills/analyzing-a-run/SKILL.md`, where it says a boss
pulled once has no summary, and `README.md` if it says so (grep "pulled once").

- [ ] **Step 4: Run everything, regenerate the night and progression goldens, read the diffs**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`

Then report the night page's byte size against its budget.

- [ ] **Step 5: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests .claude/skills/analyzing-a-run/SKILL.md README.md
/mingw64/bin/git commit -m "Open every boss on a summary that leads with its answers" -m "The summary opened on 'Nothing else measured' and a boss pulled once had none; with kill speed and the rollups every boss has a story to lead with." -m "Co-Authored-By: ..."
```

---

### Task 7: The attempt table

**Files:**
- Modify: `src/wowperf/domain/report/progression_model.py` (`AttemptRow` fields, `ProgressionReport.compared`)
- Modify: `src/wowperf/domain/report/progression_frame.py` (`build_attempt_rows`)
- Modify: `src/wowperf/domain/report/progression_build.py` (`build_progression_report` parameters)
- Modify: `src/wowperf/domain/report/night_build.py` (pass the pull findings and pace to the summary)
- Modify: `src/wowperf/adapters/render/_progression_attempts.html.j2`, `night.js.j2`
- Test: `tests/domain/report/test_progression_frame.py`, `tests/domain/report/test_night_build.py`,
  `tests/adapters/render/test_night_html_invariants.py`, `tests/adapters/render/test_progression_html_invariants.py`

**Interfaces:**
- Consumes: `verdict_kind` (Task 5), `first_roster_death` (Task 3), `collapse_seconds`,
  `pace_reading` (`wowperf.domain.comparison.pace`).
- Produces:
  - `build_attempt_rows(series, *, pull_findings=None, pace=None)`;
  - new `AttemptRow` fields: `verdict: str = ""`, `pace: str = ""`, `first_death: str = ""` and
    `held: str = ""`;
  - `ProgressionReport.compared: bool = False`;
  - `build_progression_report(series, findings, fetched_at, *, pull_findings=None, pace=None)`.

The spec (§5.3) adds these columns:
- the wipe verdict;
- the pace state at the end of the attempt;
- the first death (player, specialisation, killing ability);
- how long the raid held after it.

Selecting a row shows that pull's panel. Each cell's text:

| Column | Text |
| --- | --- |
| Verdict | `verdict_kind` of the pull's `wipe.cause`/`wipe.cause.withheld`; `"kill"` on a kill; `NO_READING` when the pull carries neither, or was not drawn |
| Pace at the end | `pace_reading(encounter, sample).seconds[-1].state.value` (`"behind"`, `"on pace"`, `"ahead"`); `"not compared"` when the sample is unavailable; `NO_READING` with no sample |
| First death | `f"{player.name} ({player.spec} {player.class_name}), to {death.killing_blow}"` from `first_roster_death`; `NO_READING` when nobody died or the attempt was not drawn |
| Held after it | `format_seconds(collapse_seconds(loaded))`; `NO_READING` when nobody died |

The Verdict and Pace columns appear only when `report.compared` is true. That is the night page
with comparison on. The standalone `wowperf progression` page and a `--no-compare` night draw no
such column. First death and Held appear on both pages.

The row link: on the night page, a row whose `fight_id` was drawn gets
`<a class="open-pull" href="#f{fight_id}-pull" data-night-show="f{fight_id}-pull">{{ row.index }}</a>`
in its `#` cell.
- The template reads the target id from the `scopes` mapping `render_night` already passes:
  `scopes[row.fight_id] ~ "pull"`. Only fights in `scopes` get a link.
- The standalone page has no `scopes`. Use `{% if scopes is defined and row.fight_id in scopes %}`.

`night.js.j2` gains:

```js
  // An attempt row names its pull: open it, and set the pull control to match.
  var opens = document.querySelectorAll("[data-night-show]");
  for (var o = 0; o < opens.length; o++) {
    opens[o].addEventListener("click", function (event) {
      var id = event.currentTarget.getAttribute("data-night-show");
      var shown = document.querySelector("[data-night-for].active select");
      if (shown) { shown.value = id; }
      showPull(id);
      event.preventDefault();
    });
  }
```

- [ ] **Step 1: Write the failing tests**

`test_progression_frame.py`. Build a series of three drawn attempts:
- a wipe with an execution `wipe.cause` and a behind pace sample;
- a wipe with a withheld verdict and no pace sample;
- a kill.

Give the first attempt a death of Emberkin at 42 s, with the fight ending at 120 s.

- `test_each_attempt_row_carries_its_verdict_pace_first_death_and_hold`. Assert the four cells on
  each row exactly. Row 1 is `("execution", "behind", "Emberkin (Frost Mage), to <ability>", "1:18")`,
  using the fixture's own spec, class and ability.
- `test_an_attempt_nobody_fetched_events_for_has_no_reading_in_any_new_cell`.
- `test_a_series_given_no_pull_findings_is_not_compared`: `build_progression_report(...)` has
  `compared is False`.

`test_night_html_invariants.py`:

- `test_every_drawn_attempt_row_opens_its_pull`. Every `data-night-show` value is the id of a
  `<section class="pull" data-night-pull-panel>` on the page, and each drawn pull is named by
  exactly one row.
- `test_the_script_opens_a_pull_from_its_row`. The script body contains `data-night-show`. Keep
  `test_the_page_executes_only_its_own_script` and `test_the_script_never_reaches_for_an_option_element`
  green.
- **Deliberately changed:** `test_a_fragment_link_inside_a_pull_lands_inside_that_same_pull`
  (`:660`). A row link inside a summary targets another pull section. Exempt exactly the
  `data-night-show` links, by attribute, and assert each lands on a pull section. Read the test
  first. If its rule is about every `.pull` section, the summary counts as one.

`test_progression_html_invariants.py`: the standalone page has the First death and Held columns,
no Verdict and no Pace column, and no `data-night-show`.

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Implement**

`build_attempt_rows`: compute the four cells as the table says, with `pull_findings` keyed by
fight id and `pace` keyed by fight id. `build_progression_report` passes them through and sets
`compared = pace is not None and bool(pace)`.

In `night_build.py`, pass `pull_findings=findings_by_fight` and `pace=pace_by_fight` into
`build_progression_report`. Check the names `build_night_report` uses for those two mappings;
it already receives both.

`_progression_attempts.html.j2`: add the header cells and row cells, with Verdict and Pace inside
`{% if report.compared %}`, and the row link as above. Rewrite the ABOUTME lines if they no longer
describe the file.

- [ ] **Step 4: Run everything, regenerate the night and progression goldens, read the diffs**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -q`

- [ ] **Step 5: Lint, types, commit**

```bash
export PATH="$HOME/.local/bin:$PATH"; uv run ruff check . && uv run mypy
/mingw64/bin/git add -A src tests
/mingw64/bin/git commit -m "Give every attempt row its verdict, pace, first death and hold, and open its pull" -m "The attempt table is where a raid leader reads the night; each row now says how that attempt ended and opens it." -m "Co-Authored-By: ..."
```

---

### Task 8: The skills and the README say what the page shows

**Files:**
- Modify: `.claude/skills/analyzing-a-run/SKILL.md` (the `night` section)
- Modify: `.claude/skills/mplus-analysis/SKILL.md`. Add a section on the three rollups: what
  each counts, that each takes its findings' confidence, and that its quantifier is the only
  count a narrative may echo.
- Modify: `README.md` (the `night` paragraph)
- Test: `tests/test_skills.py` (checks every flag a skill names against `--help`)

- [ ] **Step 1: Write the prose**

Cover, without numbers about any real report:
- every boss opens on a summary, led by its headline;
- the order of the lead (kill speed, why attempts ended, what keeps over-landing, the repeats);
- the attempt table's columns, and that a row opens its pull;
- a wipe's Summary opens on how it started;
- a kill's Summary opens on kill speed;
- the parse absence is stated once.

In `mplus-analysis`, name the three ids, their badges, and their quantifier rule. Remove any
sentence that is now false: grep for "pulled once", "no summary" and "Nothing else measured".

- [ ] **Step 2: Run the skill test and the suite**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest tests/test_skills.py -q && uv run pytest -q`

- [ ] **Step 3: Commit**

```bash
/mingw64/bin/git add .claude/skills README.md
/mingw64/bin/git commit -m "Say what the rebuilt night page shows" -m "The skills and the README described a page that opened on nothing and a boss pulled once with no summary." -m "Co-Authored-By: ..."
```

---

### Task 9: Live verification and the end-to-end tier

Run by the controller, not a subagent: it spends quota and reads real players' logs.

**Files:**
- Modify: `tests/e2e/test_night_e2e.py`. Change the summary assertions: around line 212,
  `boss.summary is not None` iff the boss has a drawn pull; and lines 375-395, the summary-less
  boss.
- Modify: `tests/e2e/test_raid_e2e.py` if a raid e2e asserts the wipe Summary's decomposition.

- [ ] **Step 1: Update the night e2e**

Every boss with a drawn pull has a summary that opens on its headline. Each summary's
`progression.lead.verdicts` exists wherever the boss had a wipe. Assert on shapes only, never a
title.

- [ ] **Step 2: Run the e2e tier**

Run: `export PATH="$HOME/.local/bin:$PATH"; uv run pytest -m e2e tests/e2e/test_raid_e2e.py tests/e2e/test_night_e2e.py -q`

Pass the canonical URLs from `.env.example` explicitly.

- [ ] **Step 3: The live distribution on `6jHcTvtB4XAMGZag` and `cW38jmwdnZfbHVL4`**

Run `wowperf night` on each. Report from the findings file and the page:
- per boss, the headline;
- whether `progression.lead.kill_speed`, `.verdicts` and `.overlanding` fired, with their
  quantifiers;
- the verdict and pace cells' value counts across the attempt table;
- how many times the parse absence sentence appears on each page (it should be 1);
- how many Provenance lines the night carries;
- the night page's byte size.

A rollup state that never fires on either report is investigated before this plan is called done.

- [ ] **Step 4: Commit**

```bash
/mingw64/bin/git add tests/e2e
/mingw64/bin/git commit -m "Pin the rebuilt night page against live logs" -m "Every boss now has a summary, and the rollups depend on verdicts and over-landing only real nights carry." -m "Co-Authored-By: ..."
```
