# Raid Parse Axis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `wowperf raid` says how a player performed against the world on this boss — throughput, target focus, cast rates, missing buttons, build and buff uptime, and a percentile — drawn from the external frame of design §4, and withheld in the tool's own words on an attempt that did not kill.

**Architecture:** The parse axis narrows rather than branches. `ParseMember` stops holding a `Run` and holds the four values it is read for, so one `ParseSample` serves Mythic+ and raid unchanged; `casts_in` stops filtering on a pull index and takes a predicate, which is what makes a raid sample countable at all. Throughput and the percentile come from `Report.rankings`, one query for the whole roster, against a median drawn off the free `characterRankings` leaderboard — so reporting both `dps` and `bossdps` costs 2.0 extra points rather than a second sample of reference reports.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, typer, httpx, pytest, ruff, mypy — all through `uv`. No new dependencies.

**Spec:** `docs/plans/2026-09-13-raid-analysis-design.md` — read §3, §4, §6.1 to §6.7, §8.1, §8.2, §9, §14 and §15 before starting. §14 was resolved by measurement on 2026-09-14 and **§14 wins wherever an unamended section disagrees with it.** The master design `docs/plans/2026-09-03-mplus-postmortem-design.md` remains the authority on architecture, badges and refusals; §9 of the raid design records exactly which of its rules do not reach raid, and nothing else in it is relaxed.

**Also read before touching `src/wowperf/domain/comparison/`:** `docs/plans/2026-09-13-comparison-table-rulings.md`, binding on everything in that package, and `docs/plans/2026-09-14-raid-mechanics-rulings.md` §1.1 to §1.3, §3 and §4, which records what plan 2 left for this one.

**This is plan 3a of two.** Design §15 gives plan 3 the external frame *and* §10's HTML report. They are separated here because each produces working, testable software on its own, because the report is better designed once it knows what these seven findings need from it, and because plan 2's worst defects were found by a live run that came too late to change anything. This plan ends with findings JSON and a live run; **§10, the raid report, is plan 3b** and is out of scope here. Nothing in this plan may add a tab, a template, or a field to `src/wowperf/domain/report/model.py`.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **The domain layer performs no I/O.** Nothing under `src/wowperf/domain/` imports `httpx`, `jinja2`, or anything touching the network, disk or a template. Adapters do that, behind the ports in `src/wowperf/domain/ports.py`.
- **Every finding carries a confidence badge** — `measured`, `derived` or `inferred`. A finding without one is a bug.
- **Never invent an API field name.** The verified reference is `.claude/skills/wcl-api/SKILL.md`, where every claim carries the date it was checked. A field not there must be verified against the live schema first, then given a dated row. Everything this plan needs was measured on 2026-09-14 and is reproduced under "Measured facts" below; **Task 1 puts it into the skill file before any code reads it.**
- **Shared code narrows, it does not branch.** A function shared between Mythic+ and raid takes the *value* it reads — a roster, a denominator, a locator, a predicate — never the aggregate, and never an `isinstance` on which aggregate it got. Plan 1 had one implementation widen five builders to `Run | Encounter`; it was rejected. Do not reintroduce one.
- **Never put a real character name in `tests/`.** The sanctioned set is `Emberkin`, `Stonewake`, `Bríala`, `Кириллица`, plus the accent-stripped spelling of one where a test needs two names that reduce to one slug.
- **Report `cW38jmwdnZfbHVL4` holds twenty real people** and `6Kx1P9GbNXrcLdHa` holds five. Refer to them by class, specialisation, role or index — in code, tests, commit messages and documents. A character id and a realm name identify a person as surely as a name does: neither reaches this repository.
- **`uv` is the only toolchain.** Gate: `uv run pytest`, `uv run ruff check .`, `uv run mypy` (paths come from `pyproject.toml`; pass none).
- **The baseline is `1772 passed, 14 deselected`**, ruff clean, mypy clean across 189 source files. Verified 2026-09-14 at `d555d4f`, twice — once in the main checkout and once in this worktree. A task ending with fewer passing has broken something and must be reverted, not argued with.
- **Credentials** live in a gitignored UTF-16 `.env` in the main checkout. Never read, echo, print or commit those values, and never put them on a command line. A worktree does not get one — copy it in with `shutil.copy2` and **remove it when done**.
- **Commit trailer is the fixed literal** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` — never the acting model's name, and with **a blank line before it** so `git interpret-trailers` recognises it. Both mistakes happened during plan 2.
- **Commit messages are plain ASCII.** A `§` once landed in a commit body as `SS`. Write "section 6.1", not "§6.1".
- **NEVER use `--no-verify`**, `--no-hooks` or `--no-pre-commit-hook`.
- **All code files start with two `# ABOUTME: ` lines.**
- **Delete only paths you created yourself**, named individually — never a wildcard, never clearing a directory wholesale. A probe subagent once swept ~35 unrelated files out of a session scratchpad and destroyed a plan's ledger.

### The mutation rule, binding on every task

From `docs/plans/2026-09-13-comparison-table-rulings.md` §1.3:

> **No assertion in a test may survive deleting the arithmetic it claims to check** — proven by mutation, on every side of a comparison, not just the one you thought of first.

Every task below carries a mandatory mutation step naming the test that must fail. It is not verification theatre: across plans 1 and 2 every shipped defect was a test that could not fail, and none was a wrong implementation. Five shapes have actually occurred here:

1. **The fixture dies at an earlier gate than the one under test.** Before trusting a test, list every gate its input passes through and name which one actually rejects it.
2. **A fixture whose arithmetic is the identity.** Every denominator 60 seconds makes `count / seconds * 60 == count`.
3. **A median flanked by equal values.** Three identical reference values are immune to mutating any one of them.
4. **An assertion that reads its expected value off the object it is checking.** True for every value and false for none.
5. **A type-correct call that says something false.** Plan 2 shipped a finding title naming the boss as the party that took its own damage, because `scope` is a `str` and a boss name is a `str`. A signature check cannot see this. **Where a task below specifies a user-visible sentence, it also specifies the assertion that reads that sentence's numbers** — never only its surroundings.

### Three live traps in code this plan touches

- **`casts_in` silently returns nothing for a raid.** `src/wowperf/domain/comparison/spells.py:46` filters on `event.pull_index not in indices`. A raid cast's `pull_index` is `None`, which is in no `frozenset`, so **every ability of every player counts zero and nothing raises.** Task 2 is the fix, and it comes before anything that counts a raid cast.
- **`rate_measures` in `comparison/spells.py` divides with no zero check, on purpose.** It is the only thing keeping `tables.py`'s `their_boss_seconds <= 0` membership guard from being dead code. Comments say so in three places. Do not make the twins symmetric.
- **The anti-drift test in `tests/domain/comparison/test_tables.py` is load-bearing collateral** for deliberate duplication of three `per_member` builders. It kills seven mutations. Weakening or tidying it silently unmakes that trade.

---

## Measured facts

Every line below was run against the live API on **2026-09-14**, against report `cW38jmwdnZfbHVL4` fight 2 (encounter 3470, Heroic, 20 players) unless stated. The whole probe cost **12.2 points of 3600** on a cold cache. **Nothing here is inferred**; where a question was not answered, this section says so rather than guessing. Task 1 copies these into `.claude/skills/wcl-api/SKILL.md` with their date.

### F1. `Report.rankings` arguments

`compare: RankingCompareType`, `difficulty: Int`, `encounterID: Int`, `fightIDs: [Int]`, `playerMetric: ReportRankingMetricType`, `timeframe: RankingTimeframeType`. **There is no `partition` argument** — partition comes back on the row, it is never sent.

### F2. `ReportRankingMetricType` — the enum `playerMetric` accepts

`bosscdps`, `bossdps`, `bossndps`, `bossrdps`, `default`, `dps`, `hps`, `krsi`, `playerscore`, `playerspeed`, `cdps`, `ndps`, `rdps`, `tankhps`, `wdps`.

**`bossdps` is accepted.** This is what makes the both-metrics decision buildable.

### F3. `CharacterRankingMetricType`

Every value in F2, plus sixteen `healercombined*` and `tankcombined*` variants. `bossdps` is present here too.

`.claude/skills/wcl-api/SKILL.md`'s 2026-09-03 line "WoW has `dps`, `wdps`, `playerscore`, `hps`, `tankhps`, and `playerspeed`" is **incomplete, not wrong** — it predates any raid query. Task 1 amends it rather than deleting it.

### F4. A `Report.rankings` payload, and the row it returns

The field returns a `JSON` scalar whose top level is exactly one key, `data`, holding a list of rows. **One row per requested fight.**

Row keys, all seventeen: `bracket`, `bracketData`, `damageTakenExcludingTanks`, `deaths`, `difficulty`, `duration`, `encounter`, `execution`, `fightID`, `guild`, `kill`, `partition`, `reportsBlacklistForCharacters`, `roles`, `size`, `speed`, `zone`.

`roles` has exactly three keys — `tanks`, `healers`, `dps` — each an object holding `characters`, a list. A character entry's keys, all thirteen: `amount`, `best`, `bracket`, `bracketData`, `bracketPercent`, `class`, `id`, `name`, `rank`, `rankPercent`, `server`, `spec`, `totalParses`.

### F5. The row carries the player's own throughput, and the two metrics differ

One tank on that fight read `amount` **59991.462335693** under `playerMetric: dps` and **44818.47826087** under `playerMetric: bossdps` — a ratio of 0.747, consistent with the 0.634-to-0.743 spread §14 item 5 measured by another route. `rankPercent` moved 80 to 87 and `bracketPercent` 73 to 81 for the same player.

**Consequence: §6.1 needs no damage table for our own side.** One query, 2.0 points, returns every one of the twenty players' own `amount` *and* their `rank`, `rankPercent`, `bracketPercent`, `best` and `totalParses`. §6.1 and §6.7 are the same fetch.

### F6. `rank` and `best` are strings, not integers

They came back as `"~5764"` and `"~3746"` — with a leading tilde. `int(row["rank"])` raises `ValueError`. `rankPercent` (80) and `bracketPercent` (73) and `totalParses` (28822) are integers.

### F7. `partition` and `difficulty` are on the row

Measured present on the row returned for a kill. This is the source design §2.2 prescribes for the partition, and the reason `data/season.toml`'s `[raid]` section exists as a placeholder.

**It is absent on a wipe.** §14 item 7 measured `Report.rankings` returning an empty list for an attempt that did not kill, with no field distinguishing the case. So the row is a source for a kill and no source at all for a wipe, and Task 5 keeps the file as the fallback rather than removing it.

### F8. A `characterRankings` row, and what it does not carry

Row keys, all thirteen: `amount`, `bracketData`, `class`, `duration`, `faction`, `guild`, `hardModeLevel`, `name`, `report`, `server`, `size`, `spec`, `startTime`.

**`score`, `medal` and `affixes` are absent.** `build_parse_rows` (`src/wowperf/adapters/wcl/rankings.py:88`) reads all three and writes `keystone_level=row["bracketData"]`. On a raid board `bracketData` read **319 to 325** — which is not a keystone level, and whose meaning is not verified. **`build_parse_rows` is therefore not reusable on this axis**, and this plan does not guess at what `bracketData` means: it carries the field nowhere.

100 rows came back for **0.0 points**, on both metrics.

### F9. `amount` is a rate, not a total

On the `dps` board the first four rows read `amount` 247358.16, 240273.40, 237153.76, 236147.44 against `duration` 407086, 375044, 276534, 321355 ms. The board descends by `amount` while `amount × duration` swings from 65.6M to 100.7M, so **the board is ordered by a per-second rate and `amount` is that rate.** `Report.rankings`' `amount` is the same unit — 59991.46 for a tank over a six-minute fight is a rate, not a total.

**Both sides of §6.1 are therefore rates, and neither needs dividing by a duration.** Plan 2 shipped a title comparing an absolute count against a per-minute rate; this is the same trap one plan later, and it is disarmed by measurement rather than by care.

### F10. The two metrics' boards hold different reports

The `bossdps` board's first four durations were 173050, 212911, 231133, 263277 ms against the `dps` board's 407086, 375044, 276534, 321355 — different rows, not a reordering of the same five. **Drawing reference reports from both boards would genuinely double the fetch**, which is why Ruling R1 below draws them from one.

### F11. Raid size varies widely on a parse board

The `dps` board's first four rows read `size` 29, 30, 29, 30 and the `bossdps` board's 29, 24, 23, 25, against our own 20. This is the confound §14.1 records, and `compare.confound.raid_size` is where it is declared.

### F12. A damage-done target row names the boss itself

`table(dataType: DamageDone, fightIDs: [N], viewBy: Target)` returned three entries whose `type` read `'NPC'`, `'Boss'`, `'NPC'`, with `total` 144629000, 498963668 and 111365043. Entry keys: `abilities`, `activeTime`, `activeTimeReduced`, `damageAbilities`, `given`, `guid`, `icon`, `id`, `name`, `sources`, `taken`, `total`, `totalRDPSGiven`, `totalRDPSTaken`, `totalReduced`, `type`.

**So the boss/add split needs no per-encounter rule.** The API's own `type` field separates them, which keeps §3.3's "no encoding any boss" intact. This call was unscoped; §2.3 measured the `sourceID`-scoped version at 0.94 points.

### F13. What was NOT measured, and must not be assumed

- **What `bracketData` means on a raid board.** Observed 319-325 and nothing more. No code in this plan reads it.
- **Whether a Target-viewed table's `sources` can substitute for twenty scoped queries.** §14 item 6 records that `abilities`, `sources` and `targets` are each capped at five rows, which rules it out for a twenty-player roster — so this plan does not try, and Task 8 scopes per subject.
- **The real cost of a full-roster parse run at twenty players.** §14 item 6 projects roughly 730 points of 3600 and says plainly that it is a projection. Task 11 measures it. **No document this plan produces may state that projection as a measurement.**

---

## Rulings made before execution

Each is a decision the spec left open or the measurements forced. They bind every task.

### R1. Both metrics, but one sample of reference reports

RwlRwlRwlRwl chose `dps` and `bossdps` stated side by side (design §14 item 5 left the choice to this plan). The naive reading — two leaderboards, two samples — doubles §14 item 6's ~730-point projection, because F10 shows the boards hold different reports.

**The ruling:** both metrics feed §6.1 and §6.7, because both sides of those come from rows that cost 0.0 (F8) and 2.0 (F5) points. **The reference *reports* fetched for §6.3, §6.4, §6.5 and §6.6 are drawn from the `dps` board alone**, and the provenance says so. Cast rates, missing buttons, talents and buff uptime are about rotation and build, not about which throughput metric a player ranks on.

**Cost if wrong:** the cast/talent/uptime sample is the five best `dps` parses rather than the five best `bossdps` parses. Both are defensible samples of "players who did this well"; the wrong one costs a slightly different five references, and the provenance names which board they came from.

### R2. `build_parse_rows` is not reused; a sibling builder exists

F8 forces this. Reusing it would write an unverified `bracketData` into a field named `keystone_level` and read three keys a raid row does not have. This is §8.2's "siblings rather than conditionals" applied one level further down than §8.2 wrote it.

**Cost if wrong:** two small builders where one general one might have done. The alternative is a row type whose `keystone_level` means item level on one axis, which is the "merely unlikely" failure §14 item 3 rules out.

### R3. `ParseMember` holds values, never a `Run`

§8.2's amendment: "a member is read for only four things: `boss_seconds`, the roster, the casts, and the row's `character_name`." A raid reference has no `Run` to give, and inventing a degenerate one is the shape §5.3 rejects at length.

**Cost if wrong:** a wide, mechanical diff across six files. If a fifth thing turns out to be read from the run, it is added as a fifth value rather than by putting the run back.

### R4. The whole external frame is withheld on a wipe, in the tool's own words

§14 item 4: `fightRankings` is a kill leaderboard under every metric, and §14 item 7: `Report.rankings` returns zero rows for a wipe. **There is no external reference for an attempt that did not kill**, and §13's first risk is that readers will expect one anyway.

Every §6.1-§6.7 finding is therefore withheld on a wipe with a stated reason naming the cause, not merely absent. Plan 2's internal frame still runs and still answers the wipe — that is why it was built first.

**Cost if wrong:** nothing measurable. The alternative is a page of empty sections that teaches nothing.

### R5. The partition is read from the rankings row and falls back to the file

F7: the row carries `partition`, and returns no row at all on a wipe. `data/season.toml`'s `[raid]` section therefore stays, demoted from "the source" to "the fallback when no kill row exists", with its comment rewritten to say so. The findings file records which source was used.

**Cost if wrong:** a wipe analysed at a stale partition after the next patch, exactly as today — no worse than the debt this inherits, and better for every kill.

### R6. Nothing here touches the Mythic+ report or `analyze`'s behaviour

Design §3.3: "Nothing in `analyze` changes behaviour." Tasks 2 and 3 change code `analyze` runs through, so **every task that touches shared code re-runs the full suite and the Mythic+ end-to-end test**, and the diff is reviewed against that rule specifically.

### R7. The word ban of plan 2 is not inherited; the claim ban is

`docs/plans/2026-09-14-raid-mechanics-rulings.md` §4.0 records that plan 2's Task 5 brief banned four words outright and that the rule was drawn too widely: this repository bans a **claim**, not a word. The Mythic+ damage finding says "avoidable" deliberately, in order to refuse the phrase, and master design §5.5 requires that.

**No sentence this plan produces may claim a player should have done something, or that any outcome was avoidable, missed or a failure.** Naming such a phrase in order to deny it applies is permitted and is the better sentence. **Do not change the Mythic+ wording**, and do not change plan 2's `compare_mechanics` wording either — that is a separate, reviewed string and this plan does not touch it.

---

## File Structure

**Created:**

| File | Responsibility |
| --- | --- |
| `src/wowperf/domain/comparison/raid_reference.py` | `RaidParseRow` and `RankedPlayer`/`ReportRankings`: what a raid leaderboard row and a report's own rankings row are, as domain values |
| `src/wowperf/domain/comparison/throughput.py` | §6.1 and §6.7: damage against the board median, and the percentile, both metrics |
| `src/wowperf/domain/comparison/targets.py` | §6.2: the share of damage per target, ours against the sample's |
| `src/wowperf/domain/comparison/parse_axis.py` | The raid parse comparison's own service seam: which findings run, and what each says when withheld |
| `src/wowperf/adapters/wcl/report_rankings.py` | `build_report_rankings` — the `Report.rankings` payload as domain rows; maps, decides nothing |
| `src/wowperf/adapters/wcl/raid_rankings.py` | `build_raid_parse_rows` and the raid half of the ranking adapter |
| `src/wowperf/adapters/wcl/damage_tables.py` | `build_target_rows` — the `viewBy: Target` payload as domain rows |

**Modified:** `src/wowperf/domain/comparison/spells.py`, `uptime.py`, `sample.py`, `loadout.py`, `service.py`, `tables.py`, `src/wowperf/domain/comparison/reference.py`, `src/wowperf/domain/ports.py`, `src/wowperf/domain/analysis/encounter_service.py`, `src/wowperf/domain/analysis/severity.py`, `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/repository.py`, `src/wowperf/adapters/config/toml.py`, `src/wowperf/cli.py`, `data/season.toml`, `.claude/skills/wcl-api/SKILL.md`, `CLAUDE.md`.

**Tests created:** `tests/domain/comparison/test_raid_reference.py`, `tests/domain/comparison/test_throughput.py`, `tests/domain/comparison/test_targets.py`, `tests/domain/comparison/test_parse_axis.py`, `tests/adapters/wcl/test_report_rankings.py`, `tests/adapters/wcl/test_raid_rankings.py`, `tests/adapters/wcl/test_damage_tables.py`.

**Tests modified:** `tests/domain/comparison/test_spells.py`, `test_uptime.py`, `test_sample.py`, `tests/domain/analysis/test_severity.py`, `tests/domain/analysis/test_encounter_service.py`, `tests/test_cli.py`, `tests/test_skills.py`, `tests/adapters/config/test_toml.py`, `tests/e2e/test_raid_e2e.py`.

---

## Task order, and why

1. **Task 1** puts the measured API facts in the skill file, because every later task reads a field name from it and the invariant is that no field is used before it is recorded.
2. **Tasks 2 and 3** are the two narrowings §8.2 prescribes. They touch shared Mythic+ code and change no behaviour, so they land first and alone, while the suite can still prove that nothing moved.
3. **Tasks 4 to 6** build the adapters: the two leaderboards and the report's own rankings row. Nothing yet reads them.
4. **Tasks 7 to 10** are the seven findings.
5. **Task 11** wires the command together and runs it live against a real kill and a real wipe.

**Task 11 is not the last chance to learn something.** It is placed after the wiring because it cannot run before it, but plan 2's §1.1 records a core deliverable that crashed on every real report because a fixture invented a field. The defence here is Task 1: every field name this plan reads was measured before the plan was written, and Task 11 confirms rather than discovers. **If Task 11 finds the API disagreeing with "Measured facts" above, stop and record the contradiction before fixing anything** — that is a correction to the skill file first and to code second.

---

### Task 1: Record the measured API surface before anything reads it

**Files:**
- Modify: `.claude/skills/wcl-api/SKILL.md`
- Modify: `CLAUDE.md`
- Test: `tests/test_skills.py` (run it; do not change it)

**Interfaces:**
- Consumes: nothing.
- Produces: no code. Every later task cites this section rather than re-deriving a field name.

**Why this is a task and not a footnote.** `CLAUDE.md`'s invariant is "Never invent an API field name… If a field is not there, verify against the live schema before using it, then add a dated row." `Report.rankings`, `playerMetric` and `bossdps` appear nowhere in the skill file today — `grep -rn "bossdps\|playerMetric\|Report.rankings" .claude/skills/wcl-api/SKILL.md` returns nothing. Every one of the seven findings below reads one of them.

- [ ] **Step 1: Confirm the gap is real**

Run: `grep -rn "bossdps\|playerMetric\|Report\.rankings" .claude/skills/wcl-api/SKILL.md src/wowperf/adapters/wcl/queries.py`
Expected: no output. If there is output, someone has already started this — read it before adding anything.

- [ ] **Step 2: Add a prose section to the skill file**

These go in **prose, not the machine-checked table.** The table's own rule, at `.claude/skills/wcl-api/SKILL.md:71-76`, is that it holds "the fields a test can assert by name in both directions", and `tests/test_skills.py` holds it against `queries.py`. A row added before the query exists breaks that test. The file states the alternative in the same breath: "A field documented in prose is documented."

Append this section after the existing "`fightRankings` takes `difficulty` and `partition`…" section:

```markdown
## A report carries its own players' ranks, and their amounts

Measured 2026-09-14 against report `cW38jmwdnZfbHVL4` fight 2 (encounter 3470, Heroic, 20
players), by schema introspection and by running the queries. The whole probe -- three
introspections and three queries -- cost 12.2 points of 3600 on a cold cache.

**`Report.rankings` takes six arguments**: `compare: RankingCompareType`, `difficulty: Int`,
`encounterID: Int`, `fightIDs: [Int]`, `playerMetric: ReportRankingMetricType`,
`timeframe: RankingTimeframeType`. **There is no `partition` argument** -- partition comes back
on the row and is never sent.

**`ReportRankingMetricType`**, the enum `playerMetric` accepts, holds `bosscdps`, `bossdps`,
`bossndps`, `bossrdps`, `default`, `dps`, `hps`, `krsi`, `playerscore`, `playerspeed`, `cdps`,
`ndps`, `rdps`, `tankhps` and `wdps`. **`CharacterRankingMetricType`** holds all of those plus
sixteen `healercombined*` and `tankcombined*` variants.

This **amends, rather than contradicts, the 2026-09-03 line under "Corrections to widespread
errors"** below, which reads "WoW has `dps`, `wdps`, `playerscore`, `hps`, `tankhps`, and
`playerspeed`". That list was taken before this project sent a raid query and is incomplete:
`bossdps` is a real World of Warcraft metric and returns 100 fully populated rows. What that
correction got right and this does not disturb is that `rdps`, `ndps` and `cdps` describe
themselves in the schema as unique to FFXIV, and `rdps` fails at the server.

**The payload is a `JSON` scalar whose top level is exactly one key, `data`**, holding a list of
rows -- one row per requested fight. A row's keys, all seventeen: `bracket`, `bracketData`,
`damageTakenExcludingTanks`, `deaths`, `difficulty`, `duration`, `encounter`, `execution`,
`fightID`, `guild`, `kill`, `partition`, `reportsBlacklistForCharacters`, `roles`, `size`,
`speed`, `zone`.

**`roles` has exactly three keys** -- `tanks`, `healers`, `dps` -- each an object holding
`characters`, a list. A character entry's keys, all thirteen: `amount`, `best`, `bracket`,
`bracketData`, `bracketPercent`, `class`, `id`, `name`, `rank`, `rankPercent`, `server`, `spec`,
`totalParses`.

**The entry carries the player's own throughput as `amount`, and the two metrics differ.** One
tank read 59991.462335693 under `playerMetric: dps` and 44818.47826087 under
`playerMetric: bossdps` -- a ratio of 0.747. `rankPercent` moved 80 to 87 and `bracketPercent`
73 to 81 for the same player. So one query returns every player's own figure and their
percentile together, for 2.00 points, whatever the roster's size.

**`rank` and `best` are strings, not integers.** They read `"~5764"` and `"~3746"` -- with a
leading tilde, which `int()` rejects. `rankPercent`, `bracketPercent` and `totalParses` are
integers.

**A wipe returns an empty list.** Recorded 2026-09-14 in
`docs/plans/2026-09-13-raid-analysis-design.md` section 14 item 7: a kill returned one row and
the wipe returned none, with no field distinguishing the cases. Code tests for emptiness.

**`id` on a character entry is a Warcraft Logs character id, not a report actor id.** One read
seven digits on a report whose actor ids are small integers. Joining a rankings entry to a
`ReportFight` roster is done on the name, never on the id.

## A raid `characterRankings` row is not a Mythic+ one

Measured 2026-09-14 against encounter 3470 at `difficulty: 4, partition: 1`, one specialisation,
under both `dps` and `bossdps`. 100 rows each, **0.0 points each**.

A row's keys, all thirteen: `amount`, `bracketData`, `class`, `duration`, `faction`, `guild`,
`hardModeLevel`, `name`, `report`, `server`, `size`, `spec`, `startTime`.

**`score`, `medal` and `affixes` are absent**, and `build_parse_rows` in
`src/wowperf/adapters/wcl/rankings.py` reads all three. It also writes `row["bracketData"]` into
a field named `keystone_level`; on a raid board `bracketData` read **319 to 325**, which is not a
keystone level. **What it does mean is not verified**, and nothing in this project reads it on
this axis rather than guessing.

**`amount` is a rate, not a total.** The first four `dps` rows read 247358.16, 240273.40,
237153.76 and 236147.44 against durations of 407086, 375044, 276534 and 321355 ms: the board
descends by `amount` while `amount x duration` swings from 65.6M to 100.7M, so the ordering is by
a per-second figure. `Report.rankings`' own `amount` is the same unit. Neither side of a
throughput comparison needs dividing by a duration, and dividing one of them would be the
count-against-rate mistake that reached a user-visible sentence on 2026-09-14.

**The two metrics' boards hold different reports.** The `bossdps` board's first four durations
were 173050, 212911, 231133 and 263277 ms against the `dps` board's 407086, 375044, 276534 and
321355 -- different rows, not a reordering. Drawing reference reports from both boards doubles
the fetch.

**Raid size varies widely on a parse board.** The `dps` board's first four rows read `size` 29,
30, 29, 30 and the `bossdps` board's 29, 24, 23, 25, against an analysed raid of 20.

## A damage-done table split by target names the boss itself

Measured 2026-09-14, same report and fight. `table(dataType: DamageDone, fightIDs: [N],
viewBy: Target)` returned three entries whose `type` read `'NPC'`, `'Boss'` and `'NPC'`, with
`total` 144629000, 498963668 and 111365043. Entry keys: `abilities`, `activeTime`,
`activeTimeReduced`, `damageAbilities`, `given`, `guid`, `icon`, `id`, `name`, `sources`,
`taken`, `total`, `totalRDPSGiven`, `totalRDPSTaken`, `totalReduced`, `type`.

So separating a boss from its adds needs no per-encounter rule and no boss table: the row's own
`type` does it. This call was unscoped; the `sourceID`-scoped version was measured at 0.94 points
on 2026-09-13.
```

- [ ] **Step 3: Add the second report of real people to CLAUDE.md's test-data rule**

`CLAUDE.md` already names `cW38jmwdnZfbHVL4`. Confirm it does — `grep -n "cW38jmwdnZfbHVL4" CLAUDE.md` — and if it does, change nothing. If it does not, add it beside `6Kx1P9GbNXrcLdHa` under "Test Data", in the same shape as the existing line.

- [ ] **Step 4: Run the gate**

Run: `uv run pytest tests/test_skills.py -v`
Expected: PASS. This test holds the machine-checked table against `queries.py`; a prose addition must not move it. If it fails, a row was added to the table by mistake — move it into prose.

Run: `uv run pytest`
Expected: `1772 passed, 14 deselected`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/wcl-api/SKILL.md CLAUDE.md
git commit -m "Record what a report's own rankings row carries"
```

Body: say that Report.rankings, playerMetric and bossdps were used by no code and named in no
verified reference, that all three were measured live on 2026-09-14 for 12.2 points, and that
the 2026-09-03 metric list is amended rather than replaced. Plain ASCII. Blank line before the
trailer.

---

### Task 2: `casts_in` takes a predicate, so a raid sample can be counted at all

**Files:**
- Modify: `src/wowperf/domain/comparison/spells.py:41-70`
- Test: `tests/domain/comparison/test_spells.py`

**Interfaces:**
- Consumes: `CastEvent` from `src/wowperf/domain/events.py` — `actor_id: int`, `ability_id: int`, `ability_name: str`, `timestamp_ms: int`, `pull_index: int | None = None`, `target_id: int | None = None`.
- Produces:
  - `casts_in(casts: tuple[CastEvent, ...], actor_id: int, include: Callable[[CastEvent], bool]) -> dict[int, tuple[str, int]]`
  - `in_pulls(indices: frozenset[int]) -> Callable[[CastEvent], bool]`
  - `whole_fight(event: CastEvent) -> bool`
  - `boss_casts(run: Run, casts: tuple[CastEvent, ...], actor_id: int) -> dict[int, tuple[str, int]]` — signature unchanged, body now builds the predicate.

**The defect this closes.** `casts_in` filters on `event.pull_index not in indices`. A raid cast's `pull_index` is `None`, which is in no `frozenset`, so **handed a raid sample today it returns zero casts for every ability and every player, and raises nothing.** Design §8.2 names it and prescribes the predicate, "the shape plan 1 established with `locate: Callable[[Death], str]`".

- [ ] **Step 1: Write the failing tests**

Two tests. The first pins the trap so that reverting the fix is visible; the second is the new capability.

```python
def test_a_raid_cast_counts_for_nobody_when_the_rule_is_a_pull_index():
    """The defect this predicate exists to close, pinned so a revert is loud.

    A raid cast carries `pull_index=None`, which is in no frozenset. Before the
    predicate, this returned an empty dict for a real cast and raised nothing --
    the quiet wrong answer this repository's failure mode is made of.
    """
    casts = (
        CastEvent(actor_id=7, ability_id=100, ability_name="Fire Breath", timestamp_ms=1000),
        CastEvent(actor_id=7, ability_id=100, ability_name="Fire Breath", timestamp_ms=2000),
    )
    assert all(event.pull_index is None for event in casts)
    assert casts_in(casts, 7, in_pulls(frozenset({0, 1}))) == {}


def test_a_raid_cast_counts_when_the_rule_is_the_whole_fight():
    casts = (
        CastEvent(actor_id=7, ability_id=100, ability_name="Fire Breath", timestamp_ms=1000),
        CastEvent(actor_id=7, ability_id=100, ability_name="Fire Breath", timestamp_ms=2000),
        CastEvent(actor_id=7, ability_id=200, ability_name="Eternity Surge", timestamp_ms=3000),
        CastEvent(actor_id=8, ability_id=100, ability_name="Fire Breath", timestamp_ms=4000),
    )
    assert casts_in(casts, 7, whole_fight) == {100: ("Fire Breath", 2), 200: ("Eternity Surge", 1)}
```

The second test's counts are 2 and 1 against a third event for another actor, so no assertion
here is true for every input: a predicate that let everything through would read
`{100: ("Fire Breath", 3), ...}` and fail, and one that let nothing through would read `{}`
and fail.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_spells.py -k "raid_cast" -v`
Expected: FAIL — `NameError: name 'in_pulls' is not defined` on both.

- [ ] **Step 3: Change `casts_in` and add the two predicates**

Replace `src/wowperf/domain/comparison/spells.py:46-62` with:

```python
def in_pulls(indices: frozenset[int]) -> Callable[[CastEvent], bool]:
    """Count a cast only inside these pulls -- the Mythic+ rule.

    A `Run` has pulls and a raid `Encounter` does not, so which casts count is
    the caller's to decide rather than this module's to assume.
    """
    return lambda event: event.pull_index in indices


def whole_fight(event: CastEvent) -> bool:
    """Count every cast the stream carries -- the raid rule.

    A raid cast's `pull_index` is always `None`, so no index rule can match one.
    The stream is already scoped to one fight by the query that fetched it,
    which is what makes "everything" the right denominator here and not a
    widening.
    """
    return True


def casts_in(
    casts: tuple[CastEvent, ...], actor_id: int, include: Callable[[CastEvent], bool]
) -> dict[int, tuple[str, int]]:
    """Each ability this actor cast, and how often, over the casts `include` admits."""
    counted: dict[int, tuple[str, int]] = {}
    for event in casts:
        if event.actor_id != actor_id or not include(event):
            continue
        name, count = counted.get(event.ability_id, (event.ability_name, 0))
        counted[event.ability_id] = (name, count + 1)
    return counted
```

Add `from collections.abc import Callable, Sequence` to the imports if `Callable` is not already
there — check the existing import line rather than adding a second one.

Change `boss_casts` (`spells.py:65`) to build the predicate:

```python
def boss_casts(
    run: Run, casts: tuple[CastEvent, ...], actor_id: int
) -> dict[int, tuple[str, int]]:
    return casts_in(casts, actor_id, in_pulls(frozenset(pull.index for pull in run.boss_pulls)))
```

- [ ] **Step 4: Fix every other caller**

Run: `grep -rn "casts_in(" src/ tests/`
Every call passing a `frozenset` becomes `in_pulls(<that frozenset>)`. Change no behaviour.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/domain/comparison/test_spells.py -v`
Expected: PASS, including the two new ones.

Run: `uv run pytest`
Expected: `1772 passed, 14 deselected` plus the 2 new — `1774 passed, 14 deselected`.

- [ ] **Step 6: Mutation check (mandatory)**

Change `whole_fight` to `return event.pull_index is not None`.
Run: `uv run pytest tests/domain/comparison/test_spells.py -k "raid_cast" -v`
Expected: `test_a_raid_cast_counts_when_the_rule_is_the_whole_fight` FAILS with `{} == {100: ...}`.
Revert the mutation. If it passed, the fixture's casts carry a `pull_index` — they must not.

Then change `in_pulls` to `return lambda event: True`.
Expected: `test_a_raid_cast_counts_for_nobody_when_the_rule_is_a_pull_index` FAILS.
Revert. This is the assertion that keeps the trap closed.

- [ ] **Step 7: Commit**

```bash
git add src/wowperf/domain/comparison/spells.py tests/domain/comparison/test_spells.py
git commit -m "Count a cast by a rule the caller gives, not by a pull index"
```

Body: a raid cast carries no pull index, so the old rule counted zero for every ability and
raised nothing; name design section 8.2 as prescribing the predicate. Plain ASCII.

---

### Task 3: `ParseMember` holds the four values it is read for, not a `Run`

**Files:**
- Modify: `src/wowperf/domain/comparison/sample.py:62-82`
- Modify: `src/wowperf/domain/comparison/spells.py`, `uptime.py`, `loadout.py`, `service.py`, `tables.py`
- Modify: `src/wowperf/cli.py:620-632`
- Test: `tests/domain/comparison/test_sample.py`, and every test constructing a `ParseMember`

**Interfaces:**
- Consumes: `casts_in` / `whole_fight` / `in_pulls` from Task 2.
- Produces:

```python
class ParseMember(Frozen):
    character_name: str
    report_code: str
    fight_id: int
    boss_seconds: float
    players: tuple[Player, ...] = ()
    casts: tuple[CastEvent, ...] = ()
    auras: PlayerAuras | None = None
    ability_icons: tuple[tuple[int, str], ...] = ()
```

  and `compare_talents(our_player: Player, our_name: str, their_player: Player | None, theirs: ParseMember) -> list[Finding]`.

**Why.** Design §8.2: "a member is read for only four things: `boss_seconds`, the roster, the casts, and the row's `character_name`. `ParseMember` therefore stops holding a `Run` and holds those values instead." A raid reference has no `Run`, and §5.3 rejects at length the idea of inventing a degenerate one. `report_code` and `fight_id` join the four because `compare_talents` builds a report URL from them and nothing else.

**This is a refactor: behaviour does not change.** The suite is the proof. `SpeedMember` keeps its `run` and is not touched — the speed axis is Mythic+-only.

- [ ] **Step 1: Write the failing test**

```python
def test_a_parse_member_carries_no_run():
    """The narrowing design 8.2 prescribes, pinned by absence.

    A raid reference has no `Run` to give. A member that still accepted one
    would let a caller pass a degenerate single-pull run, which design 5.3
    rejects because four analysers then compute quiet wrong answers.
    """
    assert "run" not in ParseMember.model_fields
    assert set(ParseMember.model_fields) == {
        "character_name",
        "report_code",
        "fight_id",
        "boss_seconds",
        "players",
        "casts",
        "auras",
        "ability_icons",
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/domain/comparison/test_sample.py -k "carries_no_run" -v`
Expected: FAIL — `assert 'run' not in {...}`.

- [ ] **Step 3: Narrow the model**

Replace the `ParseMember` class in `src/wowperf/domain/comparison/sample.py` with the definition
in **Interfaces** above. Keep the existing class docstring and extend it with a sentence saying
the member holds values rather than a run so that one sample serves both axes.

- [ ] **Step 4: Follow the type errors**

Run: `uv run mypy`

Every error is one of five rewrites. Make them mechanically; invent nothing:

| Was | Becomes |
| --- | --- |
| `boss_seconds(member.run)` | `member.boss_seconds` |
| `boss_casts(member.run, member.casts, actor_id)` | `casts_in(member.casts, actor_id, whole_fight)` for a raid member — but here, preserving Mythic+ behaviour, `casts_in(member.casts, actor_id, in_pulls(member.boss_pull_indices))` is **wrong**: there is no such field. See Step 5. |
| `member.run.players` | `member.players` |
| `member.row.character_name` | `member.character_name` |
| `their_row.report_code` / `their_row.fight_id` | `theirs.report_code` / `theirs.fight_id` |

- [ ] **Step 5: Resolve the one rewrite that is not mechanical**

`spells.py:352` reads `boss_casts(member.run, member.casts, actor_id)` — it needs the member's
own boss-pull indices, which a narrowed member no longer carries. **Do not add them back.**

The member's casts are fetched per reference fight and the only stretch that was ever counted is
its boss pulls, so the honest narrowing is to pre-filter the casts at construction and let the
member carry only what counts. In `cli.py`, where the member is built:

```python
ParseMember(
    character_name=parse_row.character_name,
    report_code=parse_row.report_code,
    fight_id=parse_row.fight_id,
    boss_seconds=boss_seconds(theirs.run),
    players=theirs.run.players,
    casts=tuple(
        event
        for event in theirs.casts
        if event.pull_index in frozenset(pull.index for pull in theirs.run.boss_pulls)
    ),
    ability_icons=theirs.ability_icons,
)
```

and every reader inside `spells.py` and `uptime.py` then counts with `whole_fight`, because the
member's casts are already the boss-pull casts. Uptime's `aura_fractions(member.auras.on_self,
boss_windows(member.run), their_seconds)` becomes a `windows` value on the member if and only if
mypy shows it is still needed; if the auras are already clipped upstream, do not add a field
nothing reads.

**Ruling for the implementer, made in advance so you do not stop on it:** if resolving this
honestly needs a sixth value on `ParseMember` (a `boss_windows: tuple[tuple[int, int], ...]`),
add it, extend the Step 1 test's field set to match, and say so in the commit body. Adding a
value is the shape this task is about; putting the `Run` back is not.

- [ ] **Step 6: Update every test that constructs a `ParseMember`**

Run: `grep -rln "ParseMember(" tests/`
Each becomes the narrowed construction. **Real character names may not appear** — use
`Emberkin`, `Stonewake`, `Bríala` or `Кириллица`.

- [ ] **Step 7: Run the gate**

Run: `uv run pytest`
Expected: `1775 passed, 14 deselected` (Task 2's two plus this one). **Any other number means
behaviour moved, and this task changes none.**

Run: `uv run ruff check .` and `uv run mypy`
Expected: clean, 189 source files.

- [ ] **Step 8: Prove the Mythic+ path is unmoved**

Run: `uv run pytest tests/adapters/render/test_html_invariants.py -v`
Expected: PASS, golden file included. The golden file is rendered from a real `compare()` run
over a `ParseSample`; if it moved, behaviour moved and this task is wrong.

- [ ] **Step 9: Mutation check (mandatory)**

Change `boss_seconds=boss_seconds(theirs.run)` in `cli.py` to `boss_seconds=0.0`.
Run: `uv run pytest tests/domain/comparison/ -v`
Expected: at least one rate-comparison test FAILS. Revert.
If nothing fails, the sample fixtures never exercise a rate — say so in the task report, because
that is a gap Task 8 must close rather than inherit.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "Give a parse member the values it is read for, not a whole run"
```

Body: design section 8.2 prescribes this; a raid reference has no Run and section 5.3 records
what a degenerate one silently breaks. Say explicitly that this changes no behaviour and that
the golden report file is unmoved. Plain ASCII.

---

### Task 4: A report's own rankings row, as domain values

**Files:**
- Create: `src/wowperf/domain/comparison/raid_reference.py`
- Create: `src/wowperf/adapters/wcl/report_rankings.py`
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Test: `tests/domain/comparison/test_raid_reference.py`, `tests/adapters/wcl/test_report_rankings.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:

```python
# src/wowperf/domain/comparison/raid_reference.py
class RankedPlayer(Frozen):
    character_name: str
    class_name: str
    spec: str
    role: str
    amount: float
    rank: str
    best: str
    rank_percent: int
    bracket_percent: int
    total_parses: int


class ReportRankings(Frozen):
    fight_id: int
    difficulty: int
    partition: int
    size: int
    kill: bool
    players: tuple[RankedPlayer, ...] = ()

    def player_named(self, name: str) -> RankedPlayer | None: ...


# src/wowperf/adapters/wcl/report_rankings.py
def build_report_rankings(payload: dict[str, Any], fight_id: int) -> ReportRankings | None: ...
```

**`rank` and `best` are `str`, not `int`.** Measured F6: they come back as `"~5764"` and
`"~3746"`, with a tilde. `int()` raises on them. Anything that wants a number uses
`rank_percent`, which is an integer.

**The join to our roster is by name, not by id.** Measured: a character entry's `id` is a
Warcraft Logs character id (one read seven digits), not the small report actor id our `Player`
carries. `player_named` casefolds, exactly as `find_player` does.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/wcl/test_report_rankings.py`:

```python
PAYLOAD = {
    "reportData": {
        "report": {
            "rankings": {
                "data": [
                    {
                        "fightID": 2,
                        "difficulty": 4,
                        "partition": 1,
                        "size": 20,
                        "kill": True,
                        "roles": {
                            "tanks": {"characters": [
                                {"name": "Stonewake", "class": "Warrior", "spec": "Protection",
                                 "amount": 44818.47826087, "rank": "~3747", "best": "~2017",
                                 "rankPercent": 87, "bracketPercent": 81, "totalParses": 28826},
                            ]},
                            "healers": {"characters": []},
                            "dps": {"characters": [
                                {"name": "Emberkin", "class": "Evoker", "spec": "Devastation",
                                 "amount": 247358.15773571, "rank": "~12", "best": "~9",
                                 "rankPercent": 96, "bracketPercent": 94, "totalParses": 31004},
                            ]},
                        },
                    }
                ]
            }
        }
    }
}


def test_a_rankings_row_becomes_one_ranked_player_per_role():
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    assert built.difficulty == 4
    assert built.partition == 1
    assert built.size == 20
    assert built.kill is True
    assert len(built.players) == 2
    assert {player.role for player in built.players} == {"tanks", "dps"}


def test_a_rank_survives_the_tilde_the_api_puts_on_it():
    """`rank` and `best` are strings. Measured 2026-09-14: they read "~5764"."""
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    tank = built.player_named("Stonewake")
    assert tank is not None
    assert tank.rank == "~3747"
    assert tank.best == "~2017"
    assert tank.rank_percent == 87
    assert tank.bracket_percent == 81


def test_the_two_players_differ_in_every_field_a_finding_reads():
    """Guard against an identity fixture: two rows that agree test nothing."""
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    tank = built.player_named("Stonewake")
    dps = built.player_named("Emberkin")
    assert tank is not None and dps is not None
    assert tank.amount != dps.amount
    assert tank.rank != dps.rank
    assert tank.rank_percent != dps.rank_percent
    assert tank.bracket_percent != dps.bracket_percent
    assert tank.total_parses != dps.total_parses
    assert tank.role != dps.role


def test_a_wipe_returns_no_row_and_the_builder_says_so_rather_than_inventing_one():
    """Design section 14 item 7: a wipe returns an empty list, with no field
    distinguishing it from a kill. Code tests for emptiness."""
    empty = {"reportData": {"report": {"rankings": {"data": []}}}}
    assert build_report_rankings(empty, fight_id=2) is None


def test_a_row_for_another_fight_is_not_mistaken_for_ours():
    other = {"reportData": {"report": {"rankings": {"data": [
        {**PAYLOAD["reportData"]["report"]["rankings"]["data"][0], "fightID": 30}
    ]}}}}
    assert build_report_rankings(other, fight_id=2) is None


def test_a_name_matches_whatever_case_the_roster_spells_it_in():
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    assert built.player_named("stonewake") is not None
    assert built.player_named("STONEWAKE") is not None
    assert built.player_named("Bríala") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_report_rankings.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_report_rankings'`.

- [ ] **Step 3: Write the domain values**

`src/wowperf/domain/comparison/raid_reference.py`:

```python
# ABOUTME: What a raid leaderboard row and a report's own rankings row are, as domain values.
# ABOUTME: A rank is a string here because the API puts a tilde on it, and int() rejects that.

from wowperf.domain.base import Frozen


class RankedPlayer(Frozen):
    """One player's standing on this boss, as the report's own rankings row states it.

    `rank` and `best` are strings, not integers: measured 2026-09-14, they read
    "~5764" and "~3746" -- the API's own approximation marker, which `int()`
    rejects. Anything that needs arithmetic uses `rank_percent`.

    There is no actor id here on purpose. A rankings entry's `id` is a Warcraft
    Logs character id, not this report's actor id, so joining the two on it
    would match nothing while looking exactly like a join that works.
    """

    character_name: str
    class_name: str
    spec: str
    role: str
    amount: float
    rank: str
    best: str
    rank_percent: int
    bracket_percent: int
    total_parses: int


class ReportRankings(Frozen):
    """The report's own rankings for one fight, and the roster's standings in it.

    Absent entirely for an attempt that did not kill -- design section 14 item 7
    measured a kill returning one row and a wipe returning none, with no field
    telling the two apart. `build_report_rankings` returns `None` rather than an
    empty `ReportRankings`, so a caller cannot read a difficulty of 0 off a wipe.
    """

    fight_id: int
    difficulty: int
    partition: int
    size: int
    kill: bool
    players: tuple[RankedPlayer, ...] = ()

    def player_named(self, name: str) -> RankedPlayer | None:
        folded = name.casefold()
        return next(
            (player for player in self.players if player.character_name.casefold() == folded),
            None,
        )
```

- [ ] **Step 4: Write the adapter and the query**

Add to `src/wowperf/adapters/wcl/queries.py`, beside the other rankings queries:

```python
# `playerMetric` is a variable rather than a literal because this plan reports
# `dps` and `bossdps` side by side: measured 2026-09-14, the same tank read
# 59991.46 under one and 44818.48 under the other, and a reader given one figure
# cannot tell which. Costs 2.00 points, whatever the roster's size.
REPORT_RANKINGS_QUERY = """
query ReportRankings($code: String!, $fightId: Int!, $metric: ReportRankingMetricType!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      rankings(fightIDs: [$fightId], playerMetric: $metric)
    }
  }
}
"""
```

`src/wowperf/adapters/wcl/report_rankings.py`:

```python
# ABOUTME: Turns a `Report.rankings` payload into domain rows; maps, decides nothing.
# ABOUTME: A wipe returns no row at all, so the absence is returned rather than a zeroed row.

from typing import Any

from wowperf.domain.comparison.raid_reference import RankedPlayer, ReportRankings

ROLES = ("tanks", "healers", "dps")


def build_report_rankings(payload: dict[str, Any], fight_id: int) -> ReportRankings | None:
    """The rankings row for this fight, or `None` where the API returned none.

    The payload's top level is exactly one key, `data`, holding one row per
    requested fight -- measured 2026-09-14. A wipe's list is empty, and no field
    on a row distinguishes a wipe from a kill, so emptiness is the test.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    block = report.get("rankings")
    rows = (block or {}).get("data") or []
    row = next((one for one in rows if one.get("fightID") == fight_id), None)
    if row is None:
        return None

    players: list[RankedPlayer] = []
    for role in ROLES:
        for entry in ((row.get("roles") or {}).get(role) or {}).get("characters") or ():
            players.append(
                RankedPlayer(
                    character_name=entry["name"],
                    class_name=entry.get("class") or "",
                    spec=entry.get("spec") or "",
                    role=role,
                    amount=float(entry.get("amount") or 0.0),
                    # Strings, not integers: the API writes "~5764".
                    rank=str(entry.get("rank") or ""),
                    best=str(entry.get("best") or ""),
                    rank_percent=int(entry.get("rankPercent") or 0),
                    bracket_percent=int(entry.get("bracketPercent") or 0),
                    total_parses=int(entry.get("totalParses") or 0),
                )
            )

    return ReportRankings(
        fight_id=row["fightID"],
        difficulty=int(row["difficulty"]),
        partition=int(row["partition"]),
        size=int(row["size"]),
        kill=bool(row["kill"]),
        players=tuple(players),
    )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/adapters/wcl/test_report_rankings.py tests/domain/comparison/test_raid_reference.py -v`
Expected: PASS.

- [ ] **Step 6: Mutation check (mandatory)**

1. Change `rank=str(entry.get("rank") or "")` to `rank=str(entry.get("best") or "")`.
   Expected: `test_a_rank_survives_the_tilde_the_api_puts_on_it` FAILS. Revert.
   The fixture's `rank` and `best` differ for exactly this reason.
2. Change the `fightID` filter to `rows[0]`.
   Expected: `test_a_row_for_another_fight_is_not_mistaken_for_ours` FAILS. Revert.
3. Change `player_named` to compare without `.casefold()`.
   Expected: `test_a_name_matches_whatever_case_the_roster_spells_it_in` FAILS. Revert.
4. Change `ROLES` to `("dps",)`.
   Expected: `test_a_rankings_row_becomes_one_ranked_player_per_role` FAILS on the length. Revert.

- [ ] **Step 7: Run the gate and commit**

Run: `uv run pytest` / `uv run ruff check .` / `uv run mypy`
Expected: all green; the count is the baseline plus this task's new tests.

```bash
git add -A
git commit -m "Read the roster's own standings off the report's rankings row"
```

---

### Task 5: The partition comes from the report, and the file becomes the fallback

**Files:**
- Modify: `src/wowperf/adapters/wcl/repository.py:260-290`
- Modify: `src/wowperf/adapters/config/toml.py:84-95`
- Modify: `data/season.toml:14-22`
- Test: `tests/adapters/wcl/test_repository.py`, `tests/adapters/config/test_toml.py`

**Interfaces:**
- Consumes: `build_report_rankings`, `ReportRankings`, `REPORT_RANKINGS_QUERY` from Task 4.
- Produces: `LoadedEncounter.encounter.partition` sourced from the API on a kill; `Encounter` gains **no new field**.

**The debt.** `repository.py:281-288` carries the comment "design 2.2 prescribes reading it from the report's own `Report.rankings` row, and no plan has built that fetch yet". Task 4 built it. Design §2.2: "Reading `difficulty` and `partition` off this row removes any need to resolve them separately."

**Why the file stays.** F7: a wipe returns no row, so there is no partition to read for the one case plan 2's mechanics comparison exists to serve. Ruling R5: prefer the row, fall back to the file, and say which was used.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_kill_takes_its_partition_from_the_report_not_the_file(monkeypatch):
    """Design 2.2's prescription, finally built. The file's value is deliberately
    different from the API's here, so an assertion that reads the file passes
    for the wrong reason and this one does not."""
    monkeypatch.setattr(repository_module, "load_raid_partition", lambda: 99)
    loaded = <load a kill whose rankings payload carries "partition": 1>
    assert loaded.encounter.partition == 1


def test_a_wipe_falls_back_to_the_file_because_no_row_exists(monkeypatch):
    monkeypatch.setattr(repository_module, "load_raid_partition", lambda: 99)
    loaded = <load a wipe whose rankings payload carries "data": []>
    assert loaded.encounter.partition == 99


def test_the_partition_source_is_recorded_rather_than_left_to_be_guessed():
    kill = <load the same kill>
    wipe = <load the same wipe>
    assert kill.partition_source == "report rankings"
    assert wipe.partition_source == "data/season.toml"
```

The stub repository fixture already used by `tests/adapters/wcl/test_repository.py` is the model
— read `test_loading_a_raid_fight_fetches_the_same_streams_a_run_does` at
`tests/adapters/wcl/test_repository.py:1054` and extend its fake payload map with a
`ReportRankings` response rather than writing a new harness.

**`partition_source` lives on `LoadedEncounter`, not on `Encounter`.** `Encounter` is the
fight's own facts; which of two sources supplied one of them is provenance, and provenance
travels with the load. Add `partition_source: str = ""` to `LoadedEncounter`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_repository.py -k "partition" -v`
Expected: FAIL — the kill reads 99, because nothing queries the rankings yet.

- [ ] **Step 3: Fetch the row during `load_encounter` and prefer it**

In `repository.py`'s `load_encounter`, before `build_encounter`:

```python
rankings = self._query(
    REPORT_RANKINGS_QUERY,
    {"code": report_code, "fightId": fight["id"], "metric": "dps"},
    hits,
)
standing = build_report_rankings(rankings, fight["id"])
# Design 2.2 prescribes reading the partition from the report's own rankings
# row, and this is that read. A wipe returns no row at all -- measured, design
# section 14 item 7 -- so `data/season.toml` stays as the fallback for exactly
# that case rather than as the source for every case.
partition = standing.partition if standing else load_raid_partition()
partition_source = "report rankings" if standing else "data/season.toml"
```

Pass `partition=partition` to `build_encounter` and `partition_source=partition_source` to
`LoadedEncounter`. Keep `standing` on the `LoadedEncounter` too — Tasks 7 and 8 read it, and
fetching it twice costs 2.00 points twice.

**Add `standing: ReportRankings | None = None` to `LoadedEncounter`.**

- [ ] **Step 4: Rewrite the comment in `data/season.toml`**

The `[raid]` block's comment currently reads "no plan has built that fetch yet". That is no
longer true and a false comment is worse than none:

```toml
[raid]
# The rankings partition a raid encounter's leaderboard is read at, used only
# where the report itself cannot supply one. `Report.rankings` carries
# `partition` on its row and `load_encounter` prefers it -- but that row is
# absent for an attempt that did not kill (measured 2026-09-14, design section
# 14 item 7), and the mechanics comparison still runs on a wipe. This is the
# value used then, dated, rather than a literal in an adapter.
partition = 1
verified = "2026-09-14"
```

Update `load_raid_partition`'s docstring in `src/wowperf/adapters/config/toml.py` the same way,
and check whether `tests/adapters/config/test_toml.py:44`
(`test_the_committed_season_file_carries_a_raid_partition`) asserts on the `verified` date — if
it does, update it.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/adapters/wcl/test_repository.py tests/adapters/config/test_toml.py -v`
Expected: PASS.

- [ ] **Step 6: Mutation check (mandatory)**

Change `partition = standing.partition if standing else load_raid_partition()` to
`partition = load_raid_partition()`.
Expected: `test_a_kill_takes_its_partition_from_the_report_not_the_file` FAILS with `99 == 1`.
Revert.

Then change it to `partition = standing.partition if standing else 1`.
Expected: `test_a_wipe_falls_back_to_the_file_because_no_row_exists` FAILS with `1 == 99`.
Revert. This is the assertion that keeps the file load real rather than a coincidence.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Take a raid partition from the report, and keep the file for a wipe"
```

Body: design section 2.2 prescribed this read and nothing had built it; the row is absent for a
wipe, which is the one case the mechanics comparison exists for, so the file is demoted to
fallback rather than deleted. Plain ASCII.

---

### Task 6: The raid parse leaderboard, as its own row and its own builder

**Files:**
- Modify: `src/wowperf/domain/comparison/raid_reference.py`
- Create: `src/wowperf/adapters/wcl/raid_rankings.py`
- Modify: `src/wowperf/adapters/wcl/queries.py`, `src/wowperf/adapters/wcl/encounter_rankings.py`, `src/wowperf/domain/ports.py`
- Test: `tests/adapters/wcl/test_raid_rankings.py`

**Interfaces:**
- Consumes: `RaidParseRow` is added to Task 4's module.
- Produces:

```python
class RaidParseRow(Frozen):
    report_code: str
    fight_id: int
    duration_ms: int
    character_name: str
    class_name: str
    spec: str
    amount: float
    size: int

    @property
    def duration_seconds(self) -> float: ...


def build_raid_parse_rows(rows: list[dict[str, Any]]) -> tuple[RaidParseRow, ...]: ...
```

  and on the `EncounterRankingRepository` Protocol in `ports.py`:

```python
    def top_parses(
        self, encounter_id: int, difficulty: int, partition: int,
        class_name: str, spec: str, metric: str,
    ) -> tuple[RaidParseRow, ...]: ...
```

**Ruling R2 in force: `build_parse_rows` is not reused.** F8 measured a raid row carrying no
`score`, no `medal` and no `affixes`, and a `bracketData` of 319-325 that is not a keystone
level and whose meaning is unverified. **`RaidParseRow` carries no `bracketData` at all** — this
plan does not name a field it cannot explain.

**No `assert_bracket` sibling, and this is deliberate.** Design §8.2 asks for one, reasoning that
"an undocumented off-by-one in `difficulty` would poison every comparison as surely as one in
`bracket` would". But `difficulty` is sent as a query variable and **the API echoes no
`difficulty` back on a row** — measured over 100 rows on two encounters, recorded in the skill
file and in plan 2's rulings §1.1. There is nothing to assert against. Writing the guard anyway
would produce a check with no path to failure, which is the exact defect that ruling exists to
stop. **Record this in the task report**; it is a departure from the spec's letter in service of
its reason.

- [ ] **Step 1: Write the failing tests**

```python
ROWS = [
    {"name": "Emberkin", "class": "Evoker", "spec": "Devastation",
     "amount": 247358.15773571, "duration": 407086, "size": 29, "bracketData": 325,
     "report": {"code": "aaaaaaaaaaaaaaaa", "fightID": 3}},
    {"name": "Stonewake", "class": "Warrior", "spec": "Arms",
     "amount": 236147.44130323, "duration": 321355, "size": 30, "bracketData": 321,
     "report": {"code": "bbbbbbbbbbbbbbbb", "fightID": 7}},
    {"name": "Bríala", "class": "Priest", "spec": "Shadow",
     "amount": 190000.0, "duration": 300000, "size": 20, "bracketData": 319},
]


def test_a_raid_row_becomes_a_row_carrying_a_rate_and_a_size():
    built = build_raid_parse_rows(ROWS)
    assert len(built) == 2
    assert built[0].character_name == "Emberkin"
    assert built[0].amount == 247358.15773571
    assert built[0].duration_seconds == 407.086
    assert built[0].size == 29
    assert built[1].size == 30


def test_a_row_with_no_report_is_dropped_because_it_cannot_be_fetched():
    assert all(row.character_name != "Bríala" for row in build_raid_parse_rows(ROWS))


def test_the_row_carries_no_keystone_level_and_no_bracket_data():
    """Measured 2026-09-14: `bracketData` reads 319 to 325 on a raid board, which
    is not a keystone level, and what it does mean is not verified. A field this
    project cannot explain is a field it does not carry."""
    assert "keystone_level" not in RaidParseRow.model_fields
    assert "bracket_data" not in RaidParseRow.model_fields
    assert "score" not in RaidParseRow.model_fields


def test_the_two_rows_differ_in_every_field_a_comparison_reads():
    built = build_raid_parse_rows(ROWS)
    assert built[0].amount != built[1].amount
    assert built[0].duration_ms != built[1].duration_ms
    assert built[0].size != built[1].size
    assert built[0].report_code != built[1].report_code
    assert built[0].fight_id != built[1].fight_id
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/adapters/wcl/test_raid_rankings.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_raid_parse_rows'`.

- [ ] **Step 3: Add the row, the builder, the query and the repository method**

`RaidParseRow` goes in `raid_reference.py` beside Task 4's models, with a docstring saying why
it is not `ParseRow`: the fields a Mythic+ row carries are absent here, and the one field whose
name suggests it carries over means something else.

Query, in `queries.py`:

```python
# `metric` is a variable because this plan draws both `dps` and `bossdps`. The
# boards are not a reordering of each other -- measured 2026-09-14, their top
# rows are different reports entirely -- so both are drawn and the reference
# reports are fetched from the `dps` board alone. 100 rows, 0.0 points.
RAID_CHARACTER_RANKINGS_QUERY = """
query RaidCharacterRankings(
  $encounterId: Int!, $difficulty: Int!, $partition: Int!, $page: Int!,
  $className: String!, $specName: String!, $metric: CharacterRankingMetricType!
) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      characterRankings(
        metric: $metric
        difficulty: $difficulty
        partition: $partition
        page: $page
        className: $className
        specName: $specName
      )
    }
  }
}
"""
```

`build_raid_parse_rows` mirrors `build_reference_kill_rows` in
`src/wowperf/adapters/wcl/encounter_rankings.py:13` — same `report_of` guard, same shape, and
reuse `report_of` and `rankings_block` from `src/wowperf/adapters/wcl/rankings.py` rather than
writing them twice.

`WclEncounterRankingRepository` gains `top_parses` beside `reference_kills`, caching through the
same transient store. Add the matching method to the `EncounterRankingRepository` Protocol in
`ports.py`.

- [ ] **Step 4: Prove the Mythic+ protocol still cannot reach the raid axis**

**No pytest test holds this rule, and none should.** `tests/test_ports.py` covers
`RunRepository` only, and plan 2's ruling on §8.2 is explicit that "mypy is what enforces that,
and the plan required proving it rejects the wrong axis." A runtime assertion over
`inspect.signature` would re-test what the type checker already refuses, in a weaker way.

So prove it the way plan 2 did — with a deliberate type error that is never committed. Write
this to a scratch file **outside the repository** (your session scratchpad), run mypy on it, and
delete it:

```python
from wowperf.domain.ports import RankingRepository

def wrong_axis(repo: RankingRepository) -> None:
    # A Mythic+ caller reaching for the raid board. `top_parses` on this Protocol
    # takes `keystone_level`, not `difficulty`/`partition`/`metric`.
    repo.top_parses(encounter_id=1, difficulty=4, partition=1, class_name="Evoker",
                    spec="Devastation", metric="dps")
```

Run: `uv run mypy <scratch path>`
Expected: an error naming `difficulty` as an unexpected keyword argument. **If mypy accepts
this, the sibling separation has been lost** — stop and report it, because the wrong axis has
become representable and only a runtime guard would be left, which is the "merely unlikely"
outcome §14 item 3 rules out.

Then delete the scratch file — that one path, named individually — and record the mypy output
in the task report.

- [ ] **Step 5: Run the tests, then the gate**

Run: `uv run pytest tests/adapters/wcl/test_raid_rankings.py -v`
Expected: PASS.
Run: `uv run pytest` / `uv run ruff check .` / `uv run mypy`
Expected: all green — mypy over the repository, with the Step 4 scratch file already deleted.

- [ ] **Step 6: Mutation check (mandatory)**

1. Change `duration_seconds` to `self.duration_ms` (drop the `/ 1000`).
   Expected: `test_a_raid_row_becomes_a_row_carrying_a_rate_and_a_size` FAILS on `407.086`. Revert.
   The fixture's duration is deliberately not a round number of seconds.
2. Delete the `report_of` guard so a row with no report is kept.
   Expected: `test_a_row_with_no_report_is_dropped_because_it_cannot_be_fetched` FAILS. Revert.
3. Add `keystone_level: int = 0` to `RaidParseRow`.
   Expected: `test_the_row_carries_no_keystone_level_and_no_bracket_data` FAILS. Revert.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Draw a raid parse board with its own row, not the keystone one"
```

Body: a raid ranking row carries no score, medal or affixes, and its bracketData is not a
keystone level; say that no bracket assertion is written because the API echoes no difficulty
per row, so the guard would have no path to failure. Plain ASCII.

---

### A ruling on finding ids, binding on Tasks 7 to 10

**Every finding this plan emits sits in the `compare.` family.** Three reasons:

1. §6.4, §6.5 and §6.6 already exist as `compare.spells.*`, `compare.talents` and
   `compare.uptime.*`. Renaming them would change the Mythic+ report, which §3.3 forbids.
2. `SEVERITY_BY_FAMILY` in `src/wowperf/domain/analysis/severity.py` already holds `compare: 6`,
   and `tests/domain/analysis/test_severity.py:44` enumerates every family the raid path emits.
   A new family would need a new severity, and §7 chose that table deliberately.
3. §6.7 binds the percentile: "it is never a headline." Last in the sort order is where a triage
   line belongs.

So: `compare.damage.total`, `compare.damage.targets`, `compare.rank`, and the three that already
exist. **Do not add a family to `SEVERITY_BY_FAMILY`.** Task 11 verifies that test still passes
rather than changing it.

**One finding per subject per comparison, carrying both metrics as facts** — not two findings
that differ only in a metric name. A reader given one figure cannot tell which metric produced
it; a reader given two rows has to reconcile them. Where the two metrics disagree, that
disagreement is the finding.

---

### Task 7: The percentile, as triage and never as a headline

**Files:**
- Create: `src/wowperf/domain/comparison/throughput.py`
- Test: `tests/domain/comparison/test_throughput.py`

**Interfaces:**
- Consumes: `ReportRankings`, `RankedPlayer` from Task 4.
- Produces: `compare_rank(standing: ReportRankings | None, boss_standing: ReportRankings | None, our_name: str) -> list[Finding]`

  where `standing` is the `dps` row and `boss_standing` the `bossdps` row. Either may be `None`.

**§6.7's binding constraint**, from master design §6.7 and quoted by the raid design: the
percentile "indicates that something is wrong and never what, it is never a headline, and it is
never an optimisation target." The finding's own words must carry that, not just the ranking.

- [ ] **Step 1: Write the failing tests**

```python
def standing(rank_percent: int, bracket_percent: int, amount: float) -> ReportRankings:
    return ReportRankings(
        fight_id=2, difficulty=4, partition=1, size=20, kill=True,
        players=(RankedPlayer(
            character_name="Emberkin", class_name="Evoker", spec="Devastation", role="dps",
            amount=amount, rank="~12", best="~9", rank_percent=rank_percent,
            bracket_percent=bracket_percent, total_parses=31004,
        ),),
    )


def test_the_percentile_states_both_metrics_and_names_itself_as_triage():
    findings = compare_rank(standing(96, 94, 247358.0), standing(71, 68, 167000.0), "Emberkin")
    assert len(findings) == 1
    one = findings[0]
    assert one.id == "compare.rank"
    assert one.confidence is Confidence.MEASURED
    assert one.seconds_lost is None
    values = {fact.label: fact.value for fact in one.facts}
    assert "96" in values["All damage"]
    assert "71" in values["Boss damage only"]
    # The constraint master design 6.7 puts on this finding, in the finding's own words.
    assert "what" in one.detail and "triage" in one.detail.lower()


def test_a_gap_between_the_two_percentiles_is_what_the_title_says():
    """96th on all damage and 71st on boss damage is the padding signal the
    side-by-side pair exists to show. A title naming only one hides it."""
    findings = compare_rank(standing(96, 94, 247358.0), standing(71, 68, 167000.0), "Emberkin")
    title = findings[0].title
    assert "96" in title and "71" in title


def test_two_percentiles_that_agree_are_said_once():
    findings = compare_rank(standing(96, 94, 247358.0), standing(96, 94, 167000.0), "Emberkin")
    assert "96" in findings[0].title
    assert findings[0].title.count("96") == 1


def test_no_percentile_is_printed_for_an_attempt_that_did_not_kill():
    """Design 14 item 7: a wipe returns no rankings row at all. Silence would
    read as a clean result, so the finding says why instead."""
    findings = compare_rank(None, None, "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.rank.unavailable"
    assert "did not kill" in findings[0].detail
    assert findings[0].seconds_lost is None


def test_a_player_absent_from_the_rankings_row_is_not_given_a_rank_of_zero():
    findings = compare_rank(standing(96, 94, 247358.0), None, "Stonewake")
    assert findings[0].id == "compare.rank.unavailable"
    assert "0" not in findings[0].title
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_throughput.py -v`
Expected: FAIL — `ImportError: cannot import name 'compare_rank'`.

- [ ] **Step 3: Write `compare_rank`**

One finding. Both percentiles in the title when they differ, one when they agree. The detail
carries §6.7's constraint in plain words — that a percentile says something is worth looking at
and never what, and that it is not a target. Badge `MEASURED`: the API computed it and nothing
here reconstructs it. `seconds_lost=None`: a percentile costs no time, and `rank_raid_findings`
sorts a `None` last within its family, which is where §6.7 wants it.

Facts: `("All damage", "<n>th percentile of <total_parses> parses")` and
`("Boss damage only", ...)`. Use `rank_percent`; **never `rank`**, which is the string `"~5764"`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/domain/comparison/test_throughput.py -v`
Expected: PASS.

- [ ] **Step 5: Mutation check (mandatory)**

1. Build the title from `standing` alone, dropping the boss percentile.
   Expected: `test_a_gap_between_the_two_percentiles_is_what_the_title_says` FAILS. Revert.
2. Change `rank_percent` to `bracket_percent` in the facts.
   Expected: `test_the_percentile_states_both_metrics_and_names_itself_as_triage` FAILS — the
   fixture's two numbers differ (96/94 and 71/68) for exactly this reason. Revert.
3. Return `[]` when `standing is None`.
   Expected: `test_no_percentile_is_printed_for_an_attempt_that_did_not_kill` FAILS on the
   length. Revert. Silence and a withheld reason must not look the same to a test — §12's first
   named trap.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "State a raid percentile on both metrics, as triage"
```

---

### Task 8: Damage against the board median, on both metrics

**Files:**
- Modify: `src/wowperf/domain/comparison/throughput.py`
- Test: `tests/domain/comparison/test_throughput.py`

**Interfaces:**
- Consumes: `RaidParseRow` (Task 6), `ReportRankings` (Task 4), `median` and `observed_range` from `src/wowperf/domain/comparison/statistics.py`.
- Produces:

```python
def compare_damage_total(
    ours: RankedPlayer | None,
    our_boss: RankedPlayer | None,
    board: tuple[RaidParseRow, ...],
    boss_board: tuple[RaidParseRow, ...],
    our_name: str,
) -> list[Finding]: ...
```

**F9 is the whole of this task's arithmetic risk.** Both `RankedPlayer.amount` and
`RaidParseRow.amount` are **per-second rates, already**. Neither side is divided by a duration.
Plan 2 shipped a user-visible title comparing a count against a per-minute rate; this is the same
trap, and the defence is that no division appears in this function at all. **If you find yourself
writing `/ duration` here, stop and re-read "Measured facts" F9.**

The board is sliced to `SAMPLE_SIZE` (5) before the median, matching every other sample in this
codebase, and `observed_range` gives the spread. Below `MIN_SAMPLE_FOR_AGGREGATE` (3) rows, use
`too_few` from `src/wowperf/domain/comparison/sample.py` exactly as the other axes do.

- [ ] **Step 1: Write the failing tests**

```python
def board(*amounts: float) -> tuple[RaidParseRow, ...]:
    return tuple(
        RaidParseRow(
            report_code=f"code{i:012d}", fight_id=i, duration_ms=300_000 + i * 1000,
            character_name="Stonewake", class_name="Evoker", spec="Devastation",
            amount=amount, size=25 + i,
        )
        for i, amount in enumerate(amounts)
    )


def ranked(amount: float) -> RankedPlayer:
    return RankedPlayer(
        character_name="Emberkin", class_name="Evoker", spec="Devastation", role="dps",
        amount=amount, rank="~12", best="~9", rank_percent=96, bracket_percent=94,
        total_parses=31004,
    )


def test_our_rate_is_compared_against_the_board_median_without_dividing_anything():
    """Both sides are already per-second rates -- measured 2026-09-14. The median
    of 100, 200, 300, 400, 500 is 300, and none of the five is 300, so a
    mutation that picks a row instead of the median cannot pass."""
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0),
        board(100.0, 200.0, 300.0, 400.0, 500.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    assert len(findings) == 1
    values = {fact.label: fact.value for fact in findings[0].facts}
    assert "300" in values["All damage"]
    assert "150" in values["All damage"]
    assert "150" in values["Boss damage only"]
    assert "90" in values["Boss damage only"]


def test_a_player_above_one_median_and_below_the_other_is_told_so():
    """The signal the side-by-side pair exists for: ahead on everything, behind
    on the boss, means damage went into adds."""
    findings = compare_damage_total(
        ranked(400.0), ranked(90.0),
        board(100.0, 200.0, 300.0, 400.0, 500.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    title = findings[0].title.lower()
    assert "above" in title and "below" in title


def test_the_observed_range_is_stated_and_is_not_the_median():
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0),
        board(100.0, 200.0, 300.0, 400.0, 500.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    evidence = " ".join(findings[0].evidence)
    assert "100" in evidence and "500" in evidence


def test_only_the_first_five_of_a_longer_board_are_counted():
    """SAMPLE_SIZE is 5 everywhere else in this codebase and is 5 here."""
    long_board = board(100.0, 200.0, 300.0, 400.0, 500.0, 10_000.0, 20_000.0)
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), long_board, long_board, "Emberkin"
    )
    values = {fact.label: fact.value for fact in findings[0].facts}
    assert "300" in values["All damage"]
    assert "10" not in values["All damage"].replace("300", "")


def test_two_references_fall_back_to_a_single_one_and_say_so():
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), board(100.0, 200.0), board(50.0, 100.0), "Emberkin"
    )
    assert any("a single reference, not an aggregate" in note for note in findings[0].evidence)


def test_no_damage_comparison_is_printed_for_an_attempt_that_did_not_kill():
    findings = compare_damage_total(None, None, (), (), "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.damage.total.unavailable"
    assert "did not kill" in findings[0].detail
```

**Read `test_our_rate_is_compared_against_the_board_median_without_dividing_anything` before
writing anything.** Its board is 100/200/300/400/500 rather than five equal values because a
median flanked by equal values is immune to mutation — shape 3 of the five this repository has
actually shipped.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/domain/comparison/test_throughput.py -k "damage_total or rate or median or range or five or single or did_not_kill" -v`
Expected: FAIL — `ImportError: cannot import name 'compare_damage_total'`.

- [ ] **Step 3: Write `compare_damage_total`**

One finding, `compare.damage.total`, badged `MEASURED` (§6.1 says so, and §9.1 records why §5.5's
"No damage ranking" does not reach raid). `seconds_lost=None`.

Facts: `("All damage", "<ours> against a median of <median>")` and `("Boss damage only", ...)`.
Evidence: the observed range on each board, and the count phrase. The title states each side as
above, below or level, and where the two differ it says both — that difference is the finding.

**The title must not advise.** Ruling R7: no sentence may say a player should have done
something. "sat below the sample median on boss damage while above it on all damage" is a
difference; "should have focused the boss" is a claim about intent that no table supports.

- [ ] **Step 4: Run the tests, then the gate**

Run: `uv run pytest tests/domain/comparison/test_throughput.py -v`
Expected: PASS.
Run: `uv run pytest` / `uv run ruff check .` / `uv run mypy`
Expected: all green.

- [ ] **Step 5: Mutation check (mandatory)**

1. Replace `median(values)` with `values[0]`.
   Expected: `test_our_rate_is_compared_against_the_board_median_without_dividing_anything`
   FAILS — 100 is not 300. Revert.
2. Divide our amount by the board's first duration.
   Expected: the same test FAILS. Revert. **This is the plan-2 defect, pinned.**
3. Change the slice to `board[:7]`.
   Expected: `test_only_the_first_five_of_a_longer_board_are_counted` FAILS. Revert.
4. Build the title from the all-damage side only.
   Expected: `test_a_player_above_one_median_and_below_the_other_is_told_so` FAILS. Revert.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Compare raid damage against the board median on both metrics"
```

Body: both sides are already per-second rates, measured 2026-09-14, so nothing here divides by a
duration; name the count-against-rate defect this avoids. Plain ASCII.

---

### Task 9: Where the damage went, as a share per target

**Files:**
- Create: `src/wowperf/domain/comparison/targets.py`
- Create: `src/wowperf/adapters/wcl/damage_tables.py`
- Modify: `src/wowperf/adapters/wcl/queries.py`
- Test: `tests/domain/comparison/test_targets.py`, `tests/adapters/wcl/test_damage_tables.py`

**Interfaces:**
- Produces:

```python
class TargetRow(Frozen):
    target_id: int
    name: str
    kind: str          # the API's own `type`: "Boss", "NPC", "Pet"
    total: int

    @property
    def is_boss(self) -> bool: ...


def build_target_rows(payload: dict[str, Any], alias: str) -> tuple[TargetRow, ...]: ...

def compare_targets(
    ours: tuple[TargetRow, ...], theirs: Sequence[tuple[TargetRow, ...]], our_name: str
) -> list[Finding]: ...
```

**F12 is what makes this buildable without breaking §3.3.** The entry's own `type` reads
`'Boss'` or `'NPC'`, so separating a boss from its adds needs no per-encounter rule, no phase
table and no mechanic list. `is_boss` is `self.kind == "Boss"` and nothing more.

**§6.2's own refusal:** "A boss with one target produces one row and no finding. The analyser
says so rather than printing a comparison worth nothing." And: "Reported as a distribution,
never as a total: totals confound target focus with fight length and gear." **Shares only.**

- [ ] **Step 1: Write the failing tests**

```python
def test_a_single_target_fight_draws_no_comparison_and_says_why():
    ours = (TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=500_000_000),)
    findings = compare_targets(ours, [ours], "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.damage.targets.unavailable"
    assert "one target" in findings[0].detail


def test_a_share_is_reported_and_a_total_is_not():
    """Design 6.2: totals confound target focus with fight length and gear."""
    ours = (
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=880_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=120_000_000),
    )
    theirs = [(
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=470_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=30_000_000),
    )]
    findings = compare_targets(ours, theirs, "Emberkin")
    text = findings[0].title + findings[0].detail + " ".join(findings[0].evidence)
    assert "88" in text and "94" in text      # our 88.0% against their 94.0%
    assert "880000000" not in text and "470000000" not in text


def test_the_boss_is_named_by_the_api_not_by_a_rule_this_project_wrote():
    rows = build_target_rows(PAYLOAD, "targets")
    assert [row.kind for row in rows] == ["NPC", "Boss", "NPC"]
    assert [row.is_boss for row in rows] == [False, True, False]


def test_our_share_and_theirs_are_not_read_off_the_same_object():
    """Shape 4 of the five: an assertion reading its expected value off the
    thing it checks is true for every input. Ours and theirs differ here."""
    ours = (
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=500_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=500_000_000),
    )
    theirs = [(
        TargetRow(target_id=57, name="The Twin Fangs", kind="Boss", total=900_000_000),
        TargetRow(target_id=88, name="Venom Spitter", kind="NPC", total=100_000_000),
    )]
    findings = compare_targets(ours, theirs, "Emberkin")
    text = findings[0].title + " ".join(findings[0].evidence)
    assert "50" in text and "90" in text
```

`PAYLOAD` mirrors F12's measured shape: three entries whose `type` reads `'NPC'`, `'Boss'`,
`'NPC'` with totals 144629000, 498963668 and 111365043.

- [ ] **Step 2 to 6:** the same cycle — run to see them fail, write `build_target_rows` (modelled
on `src/wowperf/adapters/wcl/ability_tables.py`, which is the same shape one endpoint over), write
`compare_targets`, run, then the mandatory mutations:

1. Change `is_boss` to `self.kind != "Pet"`.
   Expected: `test_the_boss_is_named_by_the_api_not_by_a_rule_this_project_wrote` FAILS. Revert.
2. Report `total` instead of the share.
   Expected: `test_a_share_is_reported_and_a_total_is_not` FAILS on the raw figures. Revert.
3. Compare our share against our own share.
   Expected: `test_our_share_and_theirs_are_not_read_off_the_same_object` FAILS. Revert.
4. Return `[]` for a one-target fight.
   Expected: `test_a_single_target_fight_draws_no_comparison_and_says_why` FAILS. Revert.

The query goes in `queries.py` as `DAMAGE_DONE_TARGETS_QUERY`, aliased `targets`, taking
`$code`, `$fightId` and `$sourceId`, with a comment recording the 0.94-points-per-table
measurement and that it is one query per subject because a Target-viewed table's nested arrays
cap at five rows (§14 item 6).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Report where a player's damage went, as shares against the sample"
```

---

### Task 10: The four comparisons that already exist, pointed at a raid

**Files:**
- Create: `src/wowperf/domain/comparison/parse_axis.py`
- Modify: `src/wowperf/domain/comparison/spells.py`, `uptime.py`
- Test: `tests/domain/comparison/test_parse_axis.py`

**Interfaces:**
- Consumes: everything from Tasks 2, 3, 4, 6, 7, 8, 9.
- Produces:

```python
def compare_parse_axis(
    our_player: Player,
    our_name: str,
    our_seconds: float,
    our_casts: tuple[CastEvent, ...],
    our_auras: PlayerAuras | None,
    sample: ParseSample,
    standing: RankedPlayer | None,
    boss_standing: RankedPlayer | None,
    board: tuple[RaidParseRow, ...],
    boss_board: tuple[RaidParseRow, ...],
    our_targets: tuple[TargetRow, ...],
    their_targets: Sequence[tuple[TargetRow, ...]],
) -> list[Finding]: ...
```

**This task builds no new comparison.** §6.4 (`compare_spells_sample`), §6.5 (`compare_talents`)
and §6.6 (`compare_uptime_sample`) exist and, after Task 3, are axis-blind. §6.3 is
`compare_spells_sample`'s rate half, and **§14 item 8 removed its count half**: the top five
references spread 33.9% of our own duration on one boss and 16.1% on another, so casts per minute
is the only expression and no threshold chooses between them. **Do not build a count comparison.**

The three existing functions still take `ours: LoadedRun` / `ours: Run` for one thing each — our
own boss seconds, our own casts, our own roster. Narrow those parameters to the values, exactly
as Task 3 narrowed the member. A raid `Encounter` then supplies `duration_seconds`, `casts` and
`players` with no aggregate crossing the boundary.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_wipe_withholds_the_whole_external_frame_in_one_sentence():
    """Design 14 item 4: `fightRankings` is a kill leaderboard under every metric
    and `Report.rankings` returns nothing for a wipe, so there is no external
    reference at all. Design 13's first risk is that readers expect one anyway."""
    findings = compare_parse_axis(
        our_player=PLAYER, our_name="Emberkin", our_seconds=300.0, our_casts=(),
        our_auras=None, sample=ParseSample(), standing=None, boss_standing=None,
        board=(), boss_board=(), our_targets=(), their_targets=[],
    )
    ids = [finding.id for finding in findings]
    assert ids == ["compare.parse.unavailable"]
    assert "did not kill" in findings[0].detail
    # Every comparison it stands in for is named, so no reader wonders which ran.
    for family in ("damage", "casts", "talents", "buff uptime", "percentile"):
        assert family in findings[0].detail


def test_a_kill_with_a_sample_emits_every_family_the_external_frame_owns():
    findings = compare_parse_axis(**KILL_ARGS)
    families = {finding.id.rsplit(".", 1)[0] if finding.id[-1].isdigit() else finding.id
                for finding in findings}
    assert "compare.damage.total" in families
    assert "compare.damage.targets" in families
    assert "compare.rank" in families
    assert any(one.startswith("compare.spells") for one in families)
    assert "compare.talents" in families
    assert any(one.startswith("compare.uptime") for one in families)


def test_a_raid_cast_reaches_the_rate_comparison_at_all():
    """The Task 2 trap, asserted end to end rather than only at `casts_in`.
    Before the predicate, every ability counted zero here and nothing raised."""
    findings = compare_parse_axis(**KILL_ARGS)
    rate_rows = [one for one in findings if one.id.startswith("compare.spells.rate")]
    assert rate_rows, "a raid cast counted for nothing -- casts_in is filtering on pull_index"


def test_no_finding_this_axis_emits_claims_a_player_should_have_done_anything():
    """Ruling R7: this repository bans a claim, not a word. A sentence may name a
    phrase in order to refuse it; none may assert intent the log cannot show."""
    for finding in compare_parse_axis(**KILL_ARGS):
        sentence = f"{finding.title} {finding.detail}".lower()
        for claim in ("should have", "failed to", "was avoidable", "missed the"):
            assert claim not in sentence, f"{finding.id}: {claim}"
```

`KILL_ARGS` is a module-level dict built once, with a `ParseSample` of five members whose
`boss_seconds` **differ from each other and from ours** and whose cast counts differ — shape 2
and shape 3 of the five, avoided deliberately. Do not give every member 60 seconds.

- [ ] **Step 2 to 5:** run to fail, narrow the three existing signatures, write
`compare_parse_axis`, run, gate.

`compare_parse_axis` is a seam, not a calculation: it calls the seven comparisons in §6's order
and returns their findings unranked. Ranking is `rank_raid_findings`' job and happens in
`analyse_encounter`.

- [ ] **Step 6: Mutation check (mandatory)**

1. Revert Task 2's predicate at the call site — pass `in_pulls(frozenset())` for the raid path.
   Expected: `test_a_raid_cast_reaches_the_rate_comparison_at_all` FAILS. Revert.
   **This is the single most important mutation in the plan**: it proves the end-to-end path,
   not just the unit.
2. Return `[]` when `standing is None`.
   Expected: `test_a_wipe_withholds_the_whole_external_frame_in_one_sentence` FAILS. Revert.
3. Give every sample member the same `boss_seconds` as ours.
   Expected: at least one rate assertion FAILS. If none does, the fixture's arithmetic is the
   identity and the test proves nothing — fix the fixture before continuing.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Point the four existing parse comparisons at a raid fight"
```

---

### Task 11: Wire the command, and run it against a real kill and a real wipe

**Files:**
- Modify: `src/wowperf/cli.py`, `src/wowperf/domain/analysis/encounter_service.py`
- Test: `tests/test_cli.py`, `tests/domain/analysis/test_encounter_service.py`, `tests/domain/analysis/test_severity.py`, `tests/e2e/test_raid_e2e.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `wowperf raid <url>` emitting the seven external findings beside plan 2's internal ones, and a findings JSON whose `comparison` block names both metrics, the board each sample came from, and the partition's source.

- [ ] **Step 1: Confirm the severity table needs no change**

Run: `uv run pytest tests/domain/analysis/test_severity.py -v`
Expected: PASS unchanged. Every id this plan adds begins `compare.`, which the table already
holds. **If this fails, an id was named outside the `compare.` family — fix the id, not the
table.**

- [ ] **Step 2: Write the failing CLI tests**

Extend `tests/test_cli.py`'s existing raid fakes (`test_raid_compares_against_the_execution_leaderboard_sample` at `:475` is the model):

```python
def test_raid_names_both_damage_metrics_in_the_findings_file():
    payload = <run raid against a stubbed kill>
    assert payload["comparison"]["metrics"] == ["dps", "bossdps"]
    # Ruling R1: reference reports come from one board, and the file says which.
    assert payload["comparison"]["sample_board"] == "dps"


def test_raid_records_where_the_partition_came_from():
    kill = <run raid against a stubbed kill>
    wipe = <run raid against a stubbed wipe>
    assert kill["partition_source"] == "report rankings"
    assert wipe["partition_source"] == "data/season.toml"


def test_raid_on_a_wipe_still_answers_with_the_internal_frame():
    """Design 15's whole reason for building plan 2 first."""
    payload = <run raid against a stubbed wipe>
    ids = [one["id"] for one in payload["findings"]]
    assert any(one.startswith("mechanics.") for one in ids)
    assert "compare.parse.unavailable" in ids
    assert not any(one.startswith("compare.rank") and "unavailable" not in one for one in ids)


def test_all_players_draws_one_sample_per_specialisation_not_one_per_player():
    """Design 14 item 6: a 20-player roster held 19 distinct class and spec
    pairs. Two players sharing a spec share a leaderboard query."""
    calls = <run raid --all-players against a roster with two Devastation Evokers>
    assert calls.count_of("RaidCharacterRankings") == <specs>, "a sample per spec, not per player"
```

- [ ] **Step 3: Wire `analyse_encounter` and `cli.py`**

`analyse_encounter` gains the parse-axis findings the way it already takes `mechanics=` and
`our_abilities=` — as values, defaulted, computed by the adapter layer. It keeps calling
`rank_raid_findings` last.

`cli.py` gains a `_parse_samples` helper beside `_mechanics_sample`, drawing one sample per
distinct `(class_name, spec)` pair rather than per player, and reusing the transient reference
cache. `--no-compare` skips it. `--player` / `--all-players` choose subjects, and **here they do
narrow the comparison** — unlike the mechanics comparison, which plan 2's rulings §1.3 explains
is raid-wide for an arithmetic reason that does not apply to a parse sample.

- [ ] **Step 4: Run the whole offline gate**

Run: `uv run pytest` / `uv run ruff check .` / `uv run mypy`
Expected: all green. Record the passing count in the task report.

- [ ] **Step 5: Run it live, against a kill and against a wipe**

Copy the credentials in without reading them:

```python
import shutil, pathlib
shutil.copy2(pathlib.Path.home() / "claude_perso" / "wow_perf" / ".env", pathlib.Path(".env"))
```

Then, against report `cW38jmwdnZfbHVL4` — **twenty real people; name nobody**:

```bash
uv run wowperf raid cW38jmwdnZfbHVL4 --fight 2
```

and again against a fight in the same report that did not kill.

**Read the findings JSON and check five things by hand:**

1. Every `compare.damage.total` figure is a plausible per-second rate, not a total. A raid boss
   total is hundreds of millions; a rate is tens or hundreds of thousands. **If you see nine
   digits, F9 was violated somewhere.**
2. Every sentence is true of the thing it names. Read the rendered titles, not the field names —
   plan 2 shipped two false sentences that were type-correct and passed a scoped review.
3. The wipe carries `compare.parse.unavailable` and no external figure at all.
4. The kill's `rank` percentiles differ between the two metrics, or, if they do not, that is
   recorded as an observation rather than assumed to be a bug.
5. No character name, realm or character id appears in anything you write down.

Then **measure the cost** and write it down with the conditions it was measured under:

```bash
uv run wowperf raid cW38jmwdnZfbHVL4 --fight 2 --all-players
```

§14 item 6 projects roughly **730 points of 3600** for the parse axis at nineteen
specialisations. **That is a projection. Report what you measured, and say plainly that the
projection was a projection** — `docs/plans/2026-09-13-raid-analysis-design.md` §13's last risk
requires exactly this.

- [ ] **Step 6: Remove the credentials**

```python
import pathlib
pathlib.Path(".env").unlink()
```

Confirm: `ls -a | grep env` shows only `.env.example`. **Do not skip this.**

- [ ] **Step 7: Update the end-to-end test and the skill files**

`tests/e2e/test_raid_e2e.py` gains a parse-axis assertion behind `-m e2e`. Plan 2's rulings §4
records that its kill test degrades to `assert not mechanics_ids` when the leaderboard holds no
same-size reference — **do not repeat that shape here.** If an assertion can pass by the
comparison doing nothing, it is not an assertion.

Add the measured cost to `.claude/skills/wcl-api/SKILL.md`'s rate-limit section, with its date
and its conditions, beside the existing rows.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Give a raid boss the external frame, and withhold it on a wipe"
```

---

## Self-review

**1. Spec coverage.** §6.1 Task 8 · §6.2 Task 9 · §6.3 Task 10 (rate half only; §14 item 8
removed the count half) · §6.4, §6.5, §6.6 Task 10 · §6.7 Task 7 · §8.1's four queries Tasks 4,
6, 9 and 5 · §8.2's parse half Tasks 2, 3, 6 · §14 item 5 settled by RwlRwlRwlRwl as both metrics
· §14 item 6 measured in Task 11 · §2.2's partition read Task 5.

**Deliberately not covered, and why:** §10, the report — plan 3b, stated at the top. §8.2's
`assert_bracket` sibling — Task 6 records that the API echoes no `difficulty` per row, so the
guard would have no path to failure, which is the defect the mutation rule exists to stop.
§8.3's raid fight selector — built by plan 1 and already working.

**2. Placeholder scan.** Task 5's test bodies carry `<load a kill …>` placeholders because the
stub-repository fixture they extend is 40 lines of existing test scaffolding that the implementer
must read at `tests/adapters/wcl/test_repository.py:1054` rather than have transcribed; the
same is true of Task 11's `<run raid against a stubbed kill>`. Both name the exact file and line
to read. **Every assertion is written out; only the fixture construction is delegated, and only
where an existing fixture already does the job.**

**3. Type consistency.** `RaidParseRow`, `RankedPlayer`, `ReportRankings`, `TargetRow`,
`ParseMember`, `ParseSample`, `build_report_rankings`, `build_raid_parse_rows`,
`build_target_rows`, `compare_rank`, `compare_damage_total`, `compare_targets`,
`compare_parse_axis`, `casts_in`, `in_pulls`, `whole_fight` — each is spelled identically in
every task that names it, and each is defined in exactly one task before any task consumes it.

**4. A gap this plan leaves for plan 3b, named so it is not rediscovered.** `PLACEMENTS` in
`src/wowperf/domain/report/ledger.py:42` has no `mechanics.` prefix, so plan 2's mechanics
findings currently fall through to `build_observations`. That is invisible today because `raid`
writes no HTML. Plan 3b owns it.

