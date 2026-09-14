# Raid Mechanics Comparison — Rulings and Evidence

**Status:** Recorded 2026-09-14, after the plan was executed and every task's review came back
clean. This is a record of judgement, not a specification.

**Scope.** `docs/plans/2026-09-14-raid-mechanics-plan.md` was executed end to end under
`superpowers:subagent-driven-development` against spec `docs/plans/2026-09-13-raid-analysis-design.md`
(§14 amends the unlabelled sections): 9 tasks, a fresh implementer per task, a review after
each, fix rounds where the review found something. Commits `1ca32b3..ad2e856`. Every task's
review closed clean; the offline gate stands at 1608 passed, 11 deselected.

The execution workspace is gitignored scratch and will be deleted when this plan finishes.
Everything in it that could not be re-derived from the code or from `git log` is here: sixteen
rulings with their reasoning and their cost if wrong, the places a review's own mutation-testing
found (or missed) a gap, a coupling no test enforces, and the work this plan leaves for the next
one. Per-task briefs, per-task reports and review diffs stay behind — they record how the work
was done, which the commits already carry.

Read this before touching `src/wowperf/domain/comparison/mechanics.py`,
`src/wowperf/domain/analysis/encounter_service.py`, or the `ReferenceKillRow` half of
`src/wowperf/adapters/wcl/encounter_rankings.py`. The design it argues from is
`2026-09-13-raid-analysis-design.md`.

---

## 1. What a later plan will trip over

### 1.1 A live `fightRankings` row carries no `difficulty` — the fixture invented one, and nothing offline could have said so

`ReferenceKillRow` originally carried a `difficulty` field, populated from `row["difficulty"]`,
and `select_reference_kills` filtered reference kills on `row.difficulty == our_difficulty`
before also filtering on size. Every task through Task 8 passed review with this in place,
because every fixture that exercised `build_reference_kill_rows` had hardcoded
`"difficulty": 4` into its rows. Task 9's live run against report `cW38jmwdnZfbHVL4` — 100 rows
across two encounters (fight 2, encounter 3470; fight 30, encounter 3492), both requested at
`difficulty: 4` — showed every row's keys to be exactly `server, duration, startTime, report,
damageTaken, deaths, tanks, healers, melee, ranged, guild, bracketData, size`. `difficulty` is
absent from all 100. `build_reference_kill_rows` raised `KeyError` on the first row of the first
live report this plan's mechanics comparison ever touched.

The ruling was to drop the field rather than back-fill it from the query argument. Two things
made that the only defensible choice once traced through. First, `reference_kills` already
passes `encounter.difficulty` as a GraphQL variable, so the API filters server-side and every
row returned is at our own difficulty by construction — the row-level filter this plan wrote
could never have rejected anything in production. Back-filling the field from the argument we
already sent would have let that filter keep compiling and keep passing its (synthetic) test
forever, which is the same defect one level up: a check with no path to failure. Second, nothing
else in the codebase reads `row.difficulty` except that one filter; `cli.py` writes
`encounter.difficulty` from our own fight, never a reference's. Removing the field costs
nothing downstream. The size filter is unaffected and stays, because size genuinely is in the
payload and genuinely varies — a leaderboard page spans 14 to 30 players against our own 20.

This is the repository's own documented failure shape recurring at the API boundary: a fixture
that encodes what the implementer expected the API to look like, checked by a test that can
therefore never see the API disagree. The corrected claim is dated 2026-09-14 in
`.claude/skills/wcl-api/SKILL.md`, under "`fightRankings` echoes no `difficulty` per row",
replacing a claim dated 2026-09-04 and re-asserted 2026-09-13 that was simply wrong. **Cost if
the correction itself is wrong:** none stands to be lost — the field carried no reader today,
and any future caller needing a difficulty-per-row check would have to source it from
`bracketData`, whose contents nobody has verified, which is exactly why this repository declines
to guess at it.

### 1.2 The plan contradicted itself about `scope`, and a type-correct call shipped a false sentence

Task 5's brief calls `compare_mechanics(..., scope="the raid")` in all four of its own worked
examples and tests. Task 7's brief, at its own line 107, writes
`scope=encounter.boss_name` — and the implementer, working from Task 7's brief alone with no
visibility into Task 5's, transcribed it faithfully into `encounter_service.py`. Both are
type-correct: `scope` is a plain `str` parameter, and a boss name is a `str`. Task 7's review
confirmed the call matched the signature, positionally and by keyword, and approved it.

The title template in `mechanics.py` is
`f"{scope} took {our_row.landings} of {our_row.ability_name} where the references took a median
of {their_median:.1f} a minute"`. With the boss's name filling `scope`, the sentence reads, for
example, "The Twin Fangs took 12 of Ravenous Feast where the references took a median of 0.0 a
minute" — naming the boss as the party that took its own ability's damage. `scope` names who
*took* the landings, which is exactly why Task 5's own tests use `"the raid"` throughout.

Task 7's review is not at fault for missing this by being careless; it checked the one thing a
signature check can check. A type-correct call can still say something false, and nothing short
of reading the rendered sentence catches that. The fix (commit `45d5274`) is one line —
`scope=encounter.boss_name` back to `scope="the raid"` — verified by reverting it in place and
re-running: the assertion `'...Ravenous Feast where the references took a median of 0.0 a
minute'.startswith("the raid")` failed against the boss-name version and passed against the
fixed one. **Cost if wrong:** finding titles would name the subject of the sentence rather than
the boss; the boss is already named elsewhere in the report's own context, so nothing factual
would be lost by the mistake persisting — but every mechanics finding would misstate, in its own
title, who did what.

A second, unresolved half of the same shape survives in the code: `compare_mechanics` builds one
`FindingFact(label="This raid", ...)` per finding as a hardcoded literal, never derived from
`scope`. Today the two happen to agree, because `scope` is always `"the raid"`. Nothing enforces
that agreement — a future caller passing a different `scope` (a per-player comparison, say)
would get a title that says one thing and a fact card that says another, and no test would
notice, because no test compares them to each other. See §3 below.

### 1.3 Per-subject mechanics was dropped for an arithmetic reason, not an effort one

The design's step 4.3 asks for one ability-taken table scoped per subject, using
`ABILITY_TAKEN_TABLE_BY_VICTIM_QUERY`. Task 8's implementer found that step 4.4 hands everything
to `analyse_encounter`, which accepts one `our_abilities` tuple and one `scope` for the whole
call — there was never a channel for a per-player table to travel through — and stopped rather
than inventing one.

Widening that interface would not have produced a correct per-player comparison; it would have
produced a wrong one that type-checks. The reference side of this comparison is
`MechanicsSample`, built from the `execution` leaderboard's raid-wide ability-taken tables — each
`MechanicsMember.abilities` is the whole reference raid's damage-taken table, not one player's.
Putting a single player's own landings on our side against that reference would compare one
person against roughly twenty. For a mechanic that lands on everyone in the raid, the reference
count is inflated by headcount alone, and every player would read as taking far less than "the
references" — not because they did, but because the denominator on their side of the comparison
is twenty times smaller than the sample it is measured against. A per-player mechanics
comparison needs a per-player *reference* table, which is a different, more expensive fetch (one
`AbilityTakenTableByVictim` query per reference member per subject) and a design decision about
sample cost, not an implementation gap this plan could close in passing.

`ABILITY_TAKEN_TABLE_BY_VICTIM_QUERY` stays in `queries.py`, unused, with the comment reproduced
in `1.2` above stating plainly why it is not wired and what wiring it would need. `--player` and
`--all-players` keep the real work they already do elsewhere (roster resolution,
`payload["player"]`, `comparison.players`); neither narrows the mechanics comparison, which
stays raid-wide. **Cost if wrong:** plan 2 ships a raid-wide mechanics comparison where a
per-player one might have been more useful; the alternative was shipping a per-player comparison
that structurally cannot be read as one.

The controller's own preflight scan is on record as having missed both 1.2 and 1.3. Its `T5 ->
T7` row checked that `MechanicsSample`'s default construction matched Task 7's call and stopped
there; its `T7 -> T8` row checked that `analyse_encounter(..., mechanics=, our_abilities=)`
matched the CLI's call by argument name, which it did. Neither row checked that the *values*
passed said anything true, and neither asked whether a step's prescribed output had anywhere to
go once it arrived. A conflict scan that verifies interfaces line up is necessary and is not
sufficient; both defects here are semantic, not structural, and a semantic check has to read the
rendered sentence or trace the arithmetic, not just the call site.

---

## 2. The sixteen rulings

Each was a decision made during execution, with what it costs if it turns out wrong. Numbered
in the order they were made.

**Ruling 1 (preflight).** Task 6's Interfaces prose says "the eight families the raid path can
emit" and then lists seven: deaths, mechanics, players, defensives, consumables, interrupts,
compare. Verified against the code before Task 6 ran: `analyse_encounter` already emits deaths,
interrupts, defensives, consumables; this plan adds players (Task 1) and mechanics (Task 5);
`compare` is carried forward for plan 3. `time`, `trash` and `throughput` are Mythic+-only and
are correctly absent. The count word is wrong and the list is right — `SEVERITY_BY_FAMILY` in
`src/wowperf/domain/analysis/severity.py` has seven entries, matching the parametrized test
verbatim, and no family is missing. Cost if wrong: an eighth family would rank on the
unknown-family default, `UNKNOWN_SEVERITY`, which sorts last — a visible symptom, not a silent
one.

**Ruling 2 (preflight).** Task 5's Interfaces block names `MechanicsMember` and `MechanicsSample`
but its Step 3 code block never defines either; Task 7 constructs `MechanicsSample()` with no
arguments. Ruling: Task 5's implementer writes both on the repository's `Frozen` base, the same
way `AbilityTakenRow` and `ReferenceKillRow` already are —
`MechanicsMember(row: ReferenceKillRow, abilities: tuple[AbilityTakenRow, ...])` and
`MechanicsSample(members: tuple[MechanicsMember, ...] = ())`, with the empty default mandatory
rather than optional, because Task 7's signature and Task 5's own test both depend on
`MechanicsSample()` constructing with no arguments. Cost if wrong: Task 7 fails to import or
construct the type at all, caught immediately by its own tests.

**Ruling 3 (Task 1).** The brief said `display_names` had five importers; there are seven. The
implementer's grep found and moved three the plan missed: `tests/test_cli.py` (in the default
suite), `tests/e2e/test_sampling_e2e.py`, `tests/e2e/test_report_e2e.py`. Verified independently:
no import anywhere still points at the old module. The plan's undercount came from grepping
`src/` plus one test file rather than the whole tree; the implementer was right to widen the
sweep rather than stop at the number the brief gave. Cost if wrong: none — an import left
pointing at a moved module is an `ImportError` at collection time, not a silent divergence.

**Ruling 4 (Task 2).** The brief's Step 6 told the implementer to add `hitCount`, `tickCount`,
`missCount`, `tickMissCount` and `sources` as rows of `SKILL.md`'s machine-checked field table.
That contradicts the file's own preamble (`.claude/skills/wcl-api/SKILL.md:71-76`), which
reserves the table for fields a test can assert by name in both directions and explicitly keeps
JSON-scalar response keys like `bands` and `totalUptime` in prose instead. All five names are
response keys inside `table()`'s opaque JSON scalar — the same class. Verified by grep: those
five names appear in `queries.py` only inside a comment the implementer had added at lines
385-394 purely to make the text-matching test find them — a check that would keep passing even
if the adapter stopped reading `tick_miss_count` tomorrow, because the comment and the claim
would both survive the change untouched. The plan's instruction does not outrank the convention
the file itself states, and the test the convention protects. Decision: move all five rows into
the file's existing dated prose section, and cut the part of the `queries.py` comment that
existed only to plant literal strings for the checker. `viewBy` keeps its `yes` row — it is a
literal argument in the query text, honestly checkable in both directions, so the implementer's
earlier flip of that one row stood. Cost if wrong: those four field names lose a check that was
never real to begin with; the facts themselves stay documented, dated, in prose.

**Ruling 5 (Task 2).** The brief gave `build_ability_taken_rows` a guard reading `if alias not in
report`, which only catches a missing key, not a key present with value `null` — the shape a
GraphQL response takes when a selection fails server-side. The repository's own established
idiom for the identical situation, `ingest._aura_rows` (`src/wowperf/adapters/wcl/ingest.py:602-614`),
checks `not isinstance(table, dict)` and catches both. The brief's own prose calls out the
missing-versus-empty distinction by name; its code delivers only half of it, and no test in the
task exercised the raise path at all. Decision: tighten the guard to
`not isinstance(report.get(alias), dict)`, matching `_aura_rows`, and add tests for both "alias
absent" and "alias present but null" — the spec's stated intent (a failed selection must never
read as "this fight took no damage") outranks the brief's literal code. Cost if wrong: a
slightly stricter guard on a payload shape nobody has ever observed malformed; it cannot produce
a false finding, only a loud error where there would otherwise have been a silent empty tuple.

**Ruling 6 (Task 3).** `_report_of` was duplicated byte-for-byte between
`adapters/wcl/rankings.py:57-59` and the new `adapters/wcl/encounter_rankings.py:13-15`.
Verified by grep: `rankings.py` calls it twice, `encounter_rankings.py` once, nothing else. The
implementer's stated reason for leaving it — nothing in the codebase imports a private symbol
across modules — is true, and is also the codebase's own argument for making the helper public
in the first place, exactly as `bracket_for` and `rankings_block` already are, both imported
across adapter modules. Decision: rename it public as `report_of` in `rankings.py`, update its
two call sites there, import it in `encounter_rankings.py`. A rename plus an import, no
behaviour change. Cost if wrong: one public name in an adapter module two files use; the
alternative was two copies of the rule for what counts as a loadable report, silently
divergeable the next time that rule changes.

**Ruling 7 (Task 3, round 1).** The mandated mutation on
`test_a_row_with_no_report_code_is_dropped` is the failure shape this repository already names:
the fixture dies at an earlier gate than the one the test claims to check. Its dropped row is
`{"code": None, "fightID": None}`. Weakening the truthiness guard to an `is not None` check lets
that row survive the guard, but `ReferenceKillRow(report_code=None, fight_id=None, ...)` then
fails Pydantic validation before the list-equality assertion runs — the test goes red, which
looks like the mutation was caught, but it was caught by the type system, not by the assertion
that claims to be checking the drop. Decision at the time: keep the null-code row (39 of 50 real
`progress` rows carried one — the measured shape, worth documenting) and add a second,
undroppable-looking row whose code is falsy but type-valid: `""` with a real integer `fightID`.
With the guard weakened, that row constructs cleanly, and the assertion sees `["", "abc123"]`
instead of `["abc123"]` — the list comparison itself is what fails. Cost if wrong stated at the
time: none, the fixture only gets stronger.

**Ruling 8 (Task 3, round 2 — reissuing Ruling 7).** Ruling 7 was internally contradictory, and
the re-reviewer was right to refuse it. It required the null-code row to stay in the fixture
*and* the same broad guard mutation to be re-run and fail at the assertion. Those cannot both
hold: a `code: None` row is type-invalid for `ReferenceKillRow` (`report_code: str`,
`fight_id: int`), so *any* mutation admitting it raises `ValidationError` during construction
before the loop reaches any other row, regardless of fixture order — the null-code row and an
assertion-level proof are mutually exclusive in the same test. The implementer had already found
the mutation that does prove the point, run it, gotten the assertion-level failure, and
documented the substitution candidly instead of passing it off as the original test — that part
was right; it needed a correct ruling, which the first attempt had not been. Decision: split the
one test into two. `test_a_blank_report_code_is_dropped` holds only the `""` row and a good row;
under the guard mutation it constructs cleanly and fails
`['', 'abc123'] == ['abc123']` — the assertion-level proof the round-1 ruling was actually
reaching for. `test_a_null_report_code_is_dropped` holds only the null row and a good row, keeps
the measured-shape comment, and a new comment explains that its crash under the same mutation is
not the proof — the proof lives in the sibling test. Cost if wrong: none to production code; two
narrower tests instead of one, each reaching the gate it claims to check.

**Ruling 9 (Task 4).** The Haiku implementer's commit trailer read
`Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>` — its own model name, not the fixed
literal the plan mandates. This is the exact failure a prior plan's handoff had already warned
about. Amended the tip commit in place rather than dispatching a fix round: it is one line of
metadata with no code impact and no review surface, and the commit was local, unpushed, and at
the branch tip, so exactly one SHA moved (`5caac3d` -> `b806c9c`; the old SHA survives only in a
review-package filename, nowhere that matters). Cost if wrong: a rewritten local commit SHA,
recorded here so nobody goes looking for `5caac3d` and fails to find it.

**Ruling 10 (Task 5).** The brief contradicts itself about the word "avoidable". Its Step 3
template puts the word directly into the produced `detail` string, and its own rule two
paragraphs later says no sentence the function produces may contain "missed", "avoidable",
"should have" or "failed". Verified both against the tree before the fix: the word shipped in
`detail`; the only other hit was a docstring, which the rule does not govern. Decision: the ban
wins over the template. The sentence keeps its meaning and loses the word — `mechanics.py` now
reads "whether any single landing could have been prevented is not something the log records."
The test was widened to assert the absence of all four banned words, not only "missed" as it did
before — one banned word had slipped through precisely because only one of the four was ever
checked. Cost if wrong: a slightly different disclaimer sentence; the rule exists because design
5.5 refuses claims about intent, and "avoidable" makes exactly that claim.

**Ruling 11 (Task 5).** `compare_mechanics` guarded `our_seconds <= 0` but divided by
`member.row.duration_seconds` with no equivalent check, so a reference member with a zero
duration would raise `ZeroDivisionError` and a negative one would silently invert every rate's
sign. Nothing upstream filters this out: `select_reference_kills` matches on size only, and
`ReferenceKillRow.duration_ms` is a plain `int` with no lower bound. This is explicitly **not**
the deliberate no-zero-check trade the global constraints name — that one is `rate_measures` in
`spells.py`, where the missing check is what keeps a different membership guard from becoming
dead code. There is no equivalent guard doing useful work here; this gap is a plain bug. Decision:
drop members whose `duration_seconds` is not positive before `total` is computed
(`mechanics.py:162-169`), so the denominator and every "N of M" phrase in a finding's evidence
see the same surviving set; an empty result after dropping returns `[]`, exactly like the
empty-sample case. Deliberately not fixed as a validator on `ReferenceKillRow` itself — that
would reach across an already-completed task (Task 3) for a case its own adapter has never
produced. Cost if wrong: an unusable reference is silently excluded from a comparison instead of
crashing the whole run, and the reported evidence count stays honest about how many references
were actually compared.

**Ruling 12 (Task 7).** The implementer's commit trailer landed as literal text with no blank
line before it, so `git interpret-trailers` did not recognise it as a trailer at all — the
constraint asks for a trailer, not a line that merely reads like one. Amended the tip commit in
place for the same reasons as Ruling 9: metadata only, no code impact, no review surface, local
and unpushed, at the tip. `da14824` -> `9640f22`; `git log --format="%(trailers:key=Co-Authored-By)"`
now returns it correctly. Cost if wrong: a rewritten local commit SHA, recorded here.

**Ruling 13 (Task 8).** Documented in full in §1.2 above: `scope="the raid"` restored in
`encounter_service.py`, one line, verified by revert-and-rerun rather than by inspection alone.
Cost if wrong: mechanics finding titles name the subject rather than the boss; nothing factual
is lost since the boss is already named elsewhere in the report.

**Ruling 14 (Task 8).** Documented in full in §1.3 above: per-subject mechanics tables are
dropped for plan 2; `ABILITY_TAKEN_TABLE_BY_VICTIM_QUERY` stays defined, unused, commented. Cost
if wrong: a raid-wide comparison ships instead of a per-player one; the alternative was shipping
a per-player comparison built on a mismatched sample.

**Ruling 15 (Task 9).** Documented in full in §1.1 above: `difficulty` dropped from
`ReferenceKillRow`, the adapter, the filter and every fixture, rather than back-filled from the
query argument. Task 4's difficulty-filter test is removed along with the behaviour it tested —
a sanctioned removal, since the filter itself no longer exists; it is not a test deleted for
failing. Cost if wrong: a caller drawing reference rows from a mixed-difficulty source would
lose a guard; no such caller exists today, and the query's own server-side filter makes one
impossible without a further, deliberate change.

**Ruling 16 (Task 9).** `.claude/skills/wcl-api/SKILL.md` claimed `difficulty` was a verified
field of a `fightRankings` row, dated twice, both times wrongly. Corrected with a 2026-09-14 entry
recording what the 100 real rows actually carry and stating plainly that `difficulty` is a
request argument only, never an echoed field — kept in prose, not the machine-checked table, per
Ruling 4's standing convention for JSON-scalar response keys. The section's other claims (report
code, `fightID`, `size`, `duration`, `deaths` all present in the same payload) held and stay.
Cost if wrong: none — it replaces a false dated claim with a true one, in the same place a reader
would already look.

---

## 3. Coupling no test announces

**`compare_mechanics`'s `FindingFact(label="This raid", ...)` is independent of its own `scope`
parameter.** The title is built from `scope`; the fact card beside it is a hardcoded literal that
happens to read correctly only because every caller today passes `scope="the raid"`. Nothing
checks that the two agree, because nothing treats them as a pair that must. A future
per-player mechanics comparison (the very thing §1.3 defers) would need `scope` to name the
player, and whoever writes that call will get a title correctly naming the player next to a fact
card that still, silently, says "This raid" — the same class of defect as Ruling 13, reintroduced
by the fix for Ruling 13's own gap not reaching this second copy of the same fact.

**`_find_roster_player` in `cli.py` duplicates `find_player` in `domain/comparison/service.py`
body-for-body**, differing only in taking `Sequence[Player]` where `find_player` takes a whole
`Run`. `cli.py`'s own docstring for `_find_roster_player` names `find_player` as its "narrower
sibling" and explains why a raid `Encounter` cannot supply a `Run` — so the duplication is
disclosed in the code, not hidden — but no test pins the two functions' matching behaviour
together, and the two case-folding rules could drift apart with neither test noticing, since each
is tested only against its own call site.

**`_mechanics_sample` omits the roster-overlap exclusion that the speed axis's `_samples` applies**
(a reference run sharing a player with the run under analysis). The mechanics sample has no
roster data to check a reference kill against — a `MechanicsMember` carries a raid-wide ability
table, not a roster — so there is nothing to exclude by today. If a later plan adds roster data
to `MechanicsMember`, the natural next question is whether it should also gain the same
exclusion `_samples` already has, and nothing in the code or its tests asks that question for you.

**`pyproject.toml`'s `extend-immutable-calls` list grew by one entry for `MechanicsSample` inside
Task 7**, a task whose brief named only `encounter_service.py` and its test in its file list.
`MechanicsSample = MechanicsSample()` as a default argument cannot pass `ruff check .` without
that entry, and the four pre-existing entries (`Roles`, `Externals`, `SelfResurrections`,
`ThroughputCooldowns`) are exactly the same `Frozen(BaseModel)` shape, so the addition follows the
established pattern rather than inventing a workaround. Recorded because it is a project-wide
config file touched by a task whose stated scope did not mention it, and nothing enforces that
every new `Frozen` model used as a mutable-looking default gets the same treatment automatically.

---

## 4. Gaps left open

**Deferred minors from the ledger**, each correct as shipped and each left for the next plan or a
future fix round to pick up:

- No test exercises `WclEncounterRankingRepository.reference_kills` itself, only the pure
  `build_reference_kill_rows` beneath it — the adapter's own wiring from `encounter_id` /
  `difficulty` / `partition` to GraphQL variables to cache key is unverified below the e2e level.
  Task 9's live run covers it once, but nothing pins it as a repeatable offline check.
- `select_reference_kills`'s docstring claims its result is "in leaderboard order"; the function
  only filters and slices, preserving whatever order the caller passed, and
  `ReferenceKillRow` carries no rank field a test could use to pin the claim either way. Not a
  defect — an overstatement in prose.
- No test covers an ability only our own raid took and no reference kill did at all (every
  fixture gives each sample member the same ability id). Traced by hand during Task 5's review:
  `their_median` is `0`, the ratio-against-zero skip does not fire, and the finding emits with
  `carrying=0`, which `quantifier_for` reads as "none" — correct, but the code's own comment
  calls this out as "precisely the finding" this function exists to make, and it has never been
  exercised by a test.
- No test names a finding id with no dot (`family_of("orphan")` returns the whole string and
  falls through to `UNKNOWN_SEVERITY` by the same path an unrecognised family already takes), and
  none calls `rank_raid_findings([])`. Both are correct by construction; neither was asked for.
- The e2e kill test's mechanics assertion is conditional on the leaderboard actually holding a
  size-20 reference, which it did not on the run that was used — the test degrades to
  `assert not mechanics_ids`, true whatever the comparison does. Every genuine positive-path
  assertion for the mechanics comparison rests on the wipe test alone. Not fixable by choosing a
  better fight ahead of time: leaderboard shape varies by boss and by day, and no fight can be
  guaranteed in advance to carry a same-size reference.
- `comparison.players` is built from display names where `analyze`'s Mythic+ equivalent uses
  slugs — defensible while the raid path has no report builder of its own, worth normalising once
  one exists.

**What this plan deliberately leaves undone**, named so the next plan starts from a record
instead of rediscovering the gap:

- **The external frame.** Design §6.1 to §6.7 — `damage.total`, `damage.targets`, `casts.count`,
  `casts.missing`, `talents`, `uptime.buffs`, `rank` — and §8.2's parse half, left for plan 3.
- **The `ParseMember` narrowing, and with it the `casts_in` predicate.** §8.2's amendment
  describes both; they belong with the parse axis they serve, not this one. The trap travels with
  them: `casts_in` filters on `event.pull_index not in indices`, and a raid cast's `pull_index` is
  always `None` — a raid sample handed to it today would silently return zero casts for every
  ability, and raise nothing.
- **The report.** Design §10; `raid` writes findings JSON only, no HTML.
- **`dps` versus `bossdps`.** Design §14 item 5 narrowed the choice to two candidates and left the
  decision to whichever plan builds §6.1.
- **The healing fight-wide fetch.** Measured at 8.00 points against the per-death fan-out's
  21.00, with identical data — break-even sits around eight deaths. It touches `repository.py` on
  the Mythic+ path too, which makes it its own change rather than this plan's. The obvious
  implementation is wrong in a way worth naming here: the server-side filter
  `target.id in (...)` returns zero rows for one point, silently, rather than failing loudly.
- **`CLAUDE.md`'s list of reports holding real people still owes `cW38jmwdnZfbHVL4`**, which this
  plan's e2e run touched and which holds twenty real people. Design §12 records the obligation;
  nobody has yet added the row.

---

## 5. Where the process itself failed, and was caught

Two commit trailers had to be amended after the fact: Task 4's implementer wrote its own model
name instead of the plan's fixed literal (Ruling 9), and Task 7's implementer wrote the correct
text but with no blank line before it, so git did not read it as a trailer at all (Ruling 12).
Both were one-line, tip-of-branch, unpushed fixes with no code surface, and both are the exact
mistake a prior plan's own handoff had already flagged as likely to recur — it recurred twice in
this one.

One ruling was self-contradictory and had to be reissued: Ruling 7 asked for a fixture and a
mutation result that could not both exist in the same test, and the re-reviewer who refused it
was right to (Ruling 8). The correction split one test into two, each proving one half of the
original claim against the gate it actually reaches.

The preflight conflict scan, run before any task started, missed both of the defects recorded in
§1.2 and §1.3 — not because it skipped the pair of tasks involved, but because it checked that an
interface's shape matched across a task boundary and stopped there. A shape check cannot see that
a boss's name in a `scope: str` slot makes a sentence say something false, and it cannot see that
a step's prescribed output has no channel to travel through until an implementer tries to wire
it and finds none. Both were real defects that a stricter reading of the plan's own text would
still have shipped; both were caught only by an implementer or reviewer reading what the code
would actually say, not what it would type-check as.

One further honesty note, smaller than the three above but worth keeping: Task 8's original
Step 2 RED evidence — the failing-test proof TDD calls for before the fix — is a reconstruction
(`git show HEAD~1` plus grep) rather than an executed failing run, because the sandbox refused
the revert command that would have produced one. The reviewer judged the reconstruction genuine
but weaker than an executed run, and noted that the requirement Step 7 actually mandates, the
`--no-compare` mutation, does carry real executed output. Recorded so a reader comparing the two
kinds of evidence in Task 8's history knows which is which; it is a different piece of evidence
than the revert-and-rerun that verified the `scope` fix in Ruling 13, which was executed.
