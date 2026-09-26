# A summary for every boss the night pulled more than once

**Status:** approved design, planned in docs/plans/2026-09-26-night-boss-summary-plan.md.
**Slice:** the first piece of spec B, the cross-pull half that
`docs/plans/2026-09-23-night-report-design.md` §12 deferred. It adds no analyser. The three new
analyser families that section names come after it, into the container this builds.

## 1. Goal

On the night page, each boss pulled two or more times gets a **summary**: the existing
progression page for that boss, drawn inside the night page and chosen from the boss's own
pull dropdown, where it is the first entry and the default.

## 2. Why this comes before any new analyser

The night command already computes every boss's progression findings and throws them away
before the page. `cli.py:1911-1914` runs `analyse_progression` once per boss;
`cli.py:1959-1962` writes the result into `<code>.night.json`; the call to
`build_night_report` at `cli.py:1994-2005` is never handed it, and `BossSection`
(`night_model.py:42-52`) holds nothing but a name and its pulls.

What those findings already answer, against spec B's three families:

| Family | Already answered by | Not answered |
| --- | --- | --- |
| Is the raid improving | `progression.movement`, `.cluster`, `.best`, `.best.deaths` | nothing this design adds |
| What keeps killing us | `progression.repeat.ability`, `.repeat.phase`, `.collapse` | killing blows counted across pulls |
| Who keeps dying, with what available | `progression.repeat.first_death`, by spec | deaths per player across pulls; availability pooled across pulls |

So one family is nearly complete and invisible, and the other two have their first rows. Showing
them first gives the two new families a place on the page to land, rather than each inventing a
layout for itself.

## 3. Constraint: nothing new is computed or fetched

- No new analyser, no new query, no new stream. Progression reads deaths and damage taken, and
  every night tier fetches both (`repository.py:762-889`).
- `build_progression_report` (`progression_build.py:34`) is called unchanged. It takes a
  `LoadedProgression`, and every entry of `LoadedNight.loaded` already is one.
- The findings JSON does not change. It already carries these findings under each boss.
- Every finding keeps the confidence badge its analyser gave it.

## 4. The view model

- `BossSection` gains `summary: ProgressionReport | None`.
- It is `None` exactly when the boss has **fewer than two drawn pulls** --
  `len(boss.attempts_with_events) < 2`. Drawn, not attempted: the page shows what it holds, and a
  pull that failed to deepen is already named in the night's provenance.
- A boss with three attempts and one failed pull still gets a summary, built over the whole
  `LoadedProgression`. Its own provenance says 3 counted and 2 deepened, the two figures
  `ProgressionProvenance` already carries (`progression_model.py:88-94`).
- `build_night_report` takes the per-boss findings as `findings_by_boss: Mapping[int,
  Sequence[Finding]]`, keyed by encounter id -- the key `cli.py:1911` already builds them under.
  The command hands the same mapping to the builder and to the JSON writer.
- `all_night_ledger_rows` walks every summary's rows as well as every pull's and the night's
  own. It is the walk the page's uniqueness checks and its single icon pass rely on, and a
  summary it skipped would be a class of rows no check ever reads.

**Why not a summary for a single pull.** Almost every progression finding compares attempts
with each other and is withheld below two (`progression_repeats.py`), three
(`MIN_OTHER_ATTEMPTS`, `progression_best.py:10`) or six (`MIN_ATTEMPTS_FOR_MOVEMENT`,
`progression_service.py:16`). One attempt leaves nothing to compare, and a summary saying so
costs the reader a click to learn that. On `cW38jmwdnZfbHVL4`, five of the eight bosses were
pulled once.

## 5. The page

- **The dropdown.** A boss with a summary gets one extra option, first in its list: "Summary: N
  pulls". A single-pull boss's dropdown is unchanged.
- **No script change.** `night.js.j2` opens whichever entry a boss's dropdown sits on, and a
  freshly loaded page sits on the first option, so the summary is the default without a line of
  script. A fresh page, and a boss not yet visited, now open on the summary instead of pull 1:
  a behaviour change, and the one this design is for. Returning to a boss reopens whatever its
  dropdown was last left on, as it did before.
- **The section.** `<section class="pull" data-night-pull-panel id="b{i}-summary">`, drawn by a
  `_night_summary.html.j2` macro that mirrors `_night_pull.html.j2`: a heading, the five
  progression tabs, and the five progression partials included unchanged. The summary keeps its
  own Provenance tab, which records what that boss's summary read and discarded -- something the
  night's page-level provenance does not say.
- **Scoping.** The five `_progression_*.html.j2` partials take the `{{ scope }}` prefix on every
  `id`, `data-tab-panel`, `data-tab-for` and `href="#..."`, exactly as the raid partials took it
  for spec A. The standalone `progression.html.j2` renders them with an empty scope.
- **The prefix** is `b{index}-`, minted in the render adapter beside `_night_scopes`, because
  which strings keep a document's anchors apart is a fact about HTML, not about the view model.
  It reuses the `b{i}` naming the boss dropdown and the "Nothing to show" section already carry,
  and cannot collide with a pull's `f{fight_id}-`.
- **Icons.** `render_night` makes one icon pass over `all_night_ledger_rows`; once that walk
  reaches the summaries (§4), a recurring-ability row gets its art with no further code.

## 6. Edge cases

| Boss | Page |
| --- | --- |
| no drawn pull | no summary; the existing "Nothing to show" section |
| one drawn pull | no summary; the dropdown opens on pull 1 |
| two drawn pulls | a summary; `best.deaths` and `movement` are withheld, and say so |
| three to five | a summary; `best.deaths` can fire, `movement` says not compared |
| six or more | a summary; every progression finding can fire |

- **Tier independence.** A boss's summary is the same under `--no-deaths`, the default and
  `--deep`, because progression reads only streams every tier fetches. It is a property a test
  asserts, not one this design assumes.
- **One difficulty per boss.** `load_night` resolves each boss to a single difficulty
  (`repository.py:579`), so a summary never mixes two.
- **One findings object, two readers.** The page and the JSON are handed the same per-boss
  findings. A summary whose rows drift from the JSON is a defect a test must catch.

## 7. Testing

Every test below must be shown able to fail against the code it guards, by breaking that code
and watching it go red; `.claude/skills/testing/test-driven-development` has the method.

**Builder.**
- `summary` is `None` at zero and one drawn pull, and present at two.
- A present summary equals `build_progression_report` called directly on the same boss --
  frozen models compared, no mock.
- The same night built with `death_cards=True` and `False` yields equal summaries.
- `all_night_ledger_rows` yields every summary row.

**Render.**
- The standalone progression golden is byte-identical before and after the scoping edit. If it
  moves, the edit changed something it should not have.
- The night golden is rebuilt from a fixture holding one single-pull boss and two multi-pull
  bosses, so both shapes are pinned.
- No element id repeats across the page, and every `href="#..."` resolves to one.
- A multi-pull boss's dropdown opens on its summary; a single-pull boss's opens on pull 1.
- The night byte budget is re-derived from the measured size, not bumped to whatever passes.

**Command.** Each boss's finding ids in the JSON equal the finding ids on that boss's summary.

**End to end.** `tests/e2e/test_night_e2e.py` asserts that three of the report's eight bosses
carry a summary -- those drawn at 2, 2 and 7 pulls (`PULLS_PER_BOSS`) -- still at `--no-deaths`,
so the run costs what it costs today.

**Live.** Read the findings JSON across those three summaries and report, for each progression
family, how often it fired, was withheld, or was not compared. `movement` can fire only on the
seven-pull boss, so the expectation is once fired and twice not compared. A family that fires
on none of the three is reported as such, never as a pass.

## 8. Out of scope

- The unanswered cells of §2's table: killing blows counted across pulls, deaths per player
  across pulls, and availability pooled across pulls. They are the next designs, and they land in
  this summary.
- Any trend line. Progression states the gap between two halves and never a slope
  (`2026-09-16-progression-analysis-design.md`), and a summary drawn on a night page is bound by
  the same rule.
- Any parse-axis comparison, any narrative, and any claim that one raider's action caused
  another's death -- unchanged from the night design's §12.
