# The Comparison Table — Rulings and Evidence

**Status:** Recorded 2026-09-13, after the plan was executed and its final review came back
clean. This is a record of judgement, not a specification.

**Scope.** `docs/plans/2026-09-13-comparison-table-plan.md` was executed end to end under
`superpowers:subagent-driven-development`: 8 tasks, a fresh implementer per task, a review
after each, fix rounds, then a whole-branch review, one fix dispatch, a scoped re-review and
a last targeted fix. Eighteen commits, `ff2318e..1ebc1b8`. All reviews clean.

The execution workspace was gitignored scratch and has been deleted. Everything in it that
could not be re-derived from the code or from `git log` is here: the twenty-five rulings with
their reasoning and their cost if wrong, the mutations that survived the whole-branch review,
and the couplings that no test can announce. The rest of it — per-task briefs, per-task
reports, review diffs — was a record of *how the work was done*, which the commits already
carry.

Read this before touching `src/wowperf/domain/comparison/`, `src/wowperf/domain/report/players.py`,
or the comparison half of `src/wowperf/adapters/render/`. The design it argues from is
`2026-09-13-comparison-table-design.md`.

---

## 1. The four things most worth keeping in mind

These are judgement rather than fact. They live nowhere in the code except as comments that
someone could talk themselves out of.

### 1.1 Ruling 11 is a load-bearing trade, and one test is the whole collateral

Three `per_member` builders in `src/wowperf/domain/comparison/tables.py` (`_boss`, `_trash`,
`_auras`) **mirror** their counterparts in `compare_spells_sample`, `compare_trash_spells_sample`
and `_gap_findings_sample` rather than being extracted into shared code. The duplication is
deliberate: extracting it would have churned three signed-off files for no behavioural change.

What makes it safe is the anti-drift test in `tests/domain/comparison/test_tables.py`, which
catches a drift between any builder and its twin. It kills seven mutations, arithmetic and
membership, across all three.

If someone weakens, simplifies or tidies that test, the duplication stops being safe and
nothing announces it. If someone extracts the builders properly, the trade is discharged and
the test can relax — but not before.

### 1.2 The `rate_measures` zero-guard asymmetry is deliberate, and is the likeliest bad "fix"

`spells.py`'s `rate_measures` divides with no zero check. `trash_spells.py`'s
`trash_rate_measures` has one. That looks like an oversight and is not. It is the **only**
thing keeping `tables.py`'s `their_boss_seconds <= 0` membership guard from being dead code:
add `and their_boss_seconds > 0` inside `rate_measures` and that predicate loses every
observable consequence, so no mutation of it is killable by any test.

Verified in both directions during the final fix round. Dropping the seconds half of
`tables._boss`'s membership guard:

```
membership guard dropped, rate_measures unguarded: RED      -- 1 failed, 1535 passed, 9 deselected
membership guard dropped, rate_measures guarded:   SURVIVED -- 1536 passed, 9 deselected
```

There are comments saying so in `rate_measures`, at `tables._boss`'s guard, and at
`compare_spells_sample`'s own copy. **Read them before making the twins symmetric.**

### 1.3 This repository's failure mode is a test that could never have failed

Not wrong implementations — the code was right nearly every time. This plan produced ten
instances, the whole-branch review found four more, and one last one turned up after that.

The rule that came out of it, binding on every task:

> **No assertion in a test may survive deleting the arithmetic it claims to check** — proven
> by mutation, on every side of a comparison, not just the one you thought of first.

Four distinct shapes, all of which have actually occurred here:

1. **The fixture dies at an earlier gate than the one under test.** A floor on aligned trash
   seconds tested with a half-second pull: half a second is under `MIN_PACK_SECONDS`, so
   alignment dropped the pull as not-a-pack and the floor was never consulted. Deleting the
   floor entirely left the test green. Before trusting any test, list every gate its input
   passes through and name which one actually rejects it.
2. **A fixture whose arithmetic is the identity.** Every denominator in the measure tests was
   60 seconds, so `count / seconds * 60 == count`, and `their_median == 7.0` passed
   identically with the division deleted.
3. **A median flanked by equal values.** A fixture of three identical reference values is
   immune to mutating any one of them: two equal values flank the median whatever the third
   does.
4. **An assertion that reads its expected value off the object it is checking.** True for
   every possible value and false for none. A caption test and a verdict-label test both
   passed while asserting nothing.

A filter can also be faithfully reproduced yet never exercised, which only running the
mutation reveals.

### 1.4 Real data found what no offline test could — twice

The table's aura half carries 52 rows under 47 names (five names own two ability ids at
different figures), which broke a name-keyed lookup that had looked fine in every fixture.
And the anti-drift test's original fixtures had no boss casts at all, so it covered one
stretch while reading as though it covered two.

Both surfaced only when the tool was run against a real report. **Budget a real run before
trusting any comparison work.**

---

## 2. The twenty-five rulings

Each was a decision the controller made during execution, with what it costs if it turns out
wrong. They are reproduced as written.

**Ruling 1: work on `master` directly rather than in a worktree.** This repo has no remote;
`master` is its trunk, and every commit of this feature's two predecessor plans landed on it
directly. `mypy` fails under long paths on this machine, so a scratch-path worktree would
break the gate. — If wrong: the branch cannot be abandoned wholesale, and backing the work
out means `git revert` of a named commit range rather than deleting a branch.

**Ruling 2: `verdict_for` lives in `spells.py`, as Tasks 1 and 2 both state; the File
Structure row for `measures.py` is loose prose and is not authority.** Two task bodies agree
on the placement and one summary table disagrees with both; `measures.py` importing
`RATE_GAP_MULTIPLE` from `spells.py` to host the rule would invert nothing but buys nothing
either. — If wrong: a one-function move plus two import lines.

**Ruling 3: keep the `build_report` parameter named `comparison_measures`.** It is the name
the plan's Task 6 uses throughout, and it names the thing it carries. In `cli.py` the function
and the keyword argument coexist as `comparison_measures(...)` and `comparison_measures=`,
which is legal and reads correctly at the call site. — If wrong: rename the parameter at three
sites.

**Ruling 4: a commit's `Co-Authored-By` trailer names the model that actually wrote it.** The
plan's example says Opus 5 because Opus wrote the plan; Sonnet 5 wrote `2f890e0` and its
trailer says Sonnet 5. Honest attribution beats a uniform trailer, and this repo's first value
is that we do not lie. The history will carry both names. — If wrong: the trailers are
inconsistent across 40-odd commits and nothing else.

**Ruling 5: the plan's worked code does not license deleting a comment.** The reviewer
labelled the deletion plan-mandated, since the brief's Step 4 template simply does not contain
the three comments. CLAUDE.md states the rule as absolute — a comment goes only when it can be
proven actively false — and the plan's templates are a transcription of the new structure, not
a decision about commentary. Restore all three. **This applies to Tasks 2 and 3 as well**:
their worked code has the same shape and will have dropped the same kind of rationale, so
their dispatches must say so before the fact. — If wrong: three comments sit in the tree that
a reader did not need.

**Ruling 6: a brief's fixture values do not licence a non-discriminating assertion.** The
implementer found, by mutating past what its brief prescribed, that every fixture denominator
in both measure test files is 60.0 — so `count / seconds * 60 == count` and an assertion like
`ours == 4.0` cannot tell a rate from a raw count. It judged this unfixable without deviating
from "use verbatim". Verbatim governs what a test asserts, not a denominator that makes the
assertion vacuous, and the Global Constraint on tests that cannot fail outranks the fixture.
Sent back pre-review, extended to the three Task 1 tests carrying the same pattern. — If
wrong: four fixtures carry denominators the brief did not name, and the assertions prove more
than the brief asked them to.

**Ruling 7: a factually false comment is pulled into the fix round, not deferred as a minor.**
The review graded at Minor a new comment claiming an unadjusted count would land on level when
it actually lands on below. Elsewhere the rule is that a comment goes only when provably
false; the corollary is that a comment proven false is the one thing that must change. A
one-word fix in a file already being touched. — If wrong: one minor was fixed a round earlier
than the process would have fixed it.

**Ruling 8: the fourth instance is the same finding, not a new round.** The finding was the
masked reference-side denominator; the three assertions I listed were the review's examples of
it, not its boundary. Sending the enumeration to re-review while a confirmed fourth instance
of the same defect sits in the tree would spend a round to learn what is already known. Sent
back within round 1, with standing authority to fix any further instance mutation turns up in
these two files. — If wrong: round 1 did more work than a strict reading of the round boundary
allows, and the re-review sees one extra hunk.

**Ruling 9: Task 4 dispatched while Task 3's review is still in flight.** Normally the review
gate closes before the next task opens. Two things make it safe here and RwlRwlRwl asked to
continue: Task 4 only *creates* `comparison/tables.py` and `test_tables.py`, so it cannot
collide with any Task 3 fix round, which would touch `uptime.py` and `test_uptime.py`; and
Task 4 consumes `uptime_measures` by its settled signature, not by its internals. If Task 3's
review forces an interface change, I carry it into Task 4 as a finding. — If wrong: Task 4
rebases onto a changed `uptime_measures` signature, costing one fix round.

*(Discharged: Task 3's review forced no interface change.)*

**Ruling 10: add the `can_aggregate` guard to `_boss`, overruling the implementer's conclusion
while accepting its facts.** It found that `compare_spells_sample` returns pairwise below
`MIN_SAMPLE_FOR_AGGREGATE` and never calls `rate_measures`, while `_boss` always does —
equivalent only because that floor and `MIN_MEMBERS_WITH_ABILITY` are both 3. It declined to
add the guard as untestable code. The design's §8 claims the table "structurally cannot" state
a figure a finding does not, and that claim is the reason the table needs no per-row badge; a
coincidence between two unrelated constants is not a structure, so the design currently claims
more than the code supports. `can_aggregate` is a `ParseSample` method, so gating on it shares
the one definition rather than copying a rule. And nothing downstream catches this: Task 8
runs finding to row, and the table legitimately holds rows no finding covers (every level
row), so the reverse direction is unassertable. Guard added with a comment stating plainly
that it cannot fire while the two floors are equal, and explicitly no test pretending to
exercise it. — If wrong: three lines and a comment documenting a coupling that never bites.

**Ruling 11: do not extract the three `per_member` builders; defer it.** The reviewer's one
Important finding, labelled plan-mandated: the design's "structurally cannot disagree" holds
for the measures, each of which has one definition, but not for their inputs, which now have
two apiece and are kept in step by discipline. That is the same argument I used for Ruling 10,
so it deserves the same answer unless something distinguishes it — and something does. Ruling
10's gap had nothing downstream to catch it. This one does: any drift in a `per_member`
builder moves a median, and Task 8's anti-drift test fails the moment a rate finding's two
figures stop matching its row. The uncovered residue is drift that touches only level-verdict
abilities, which carry no competing claim for a reader to be misled by. Against that:
extracting three builders churns three files already refactored and signed off, for no
behavioural change, with four tasks left. **Task 8's dispatch must carry this**: its anti-drift
test is the structural net under Task 4's mirroring and must not be weakened. — If wrong: a
future edit to one `per_member` builder and not its twin disagrees only on level rows,
silently, until someone reads both.

**Ruling 12: Task 6's brief prescribes a test that cannot fail; require a discriminating one
instead.** Step 6's second assertion is
`all(not f["id"].startswith("compare.spells.table") for f in payload["findings"])`. No code
path in this tree emits an id beginning `compare.spells.table` — the table is not a finding and
has no id at all — so the assertion passes identically if the tables were written straight into
the ranked array. That is the seventh instance of this plan's failure mode, and the first found
in a brief before an implementer reached it. The replacement must prove the sibling placement by
what the payload actually holds: the key present and carrying a compared player's measured
figures, and every entry in `findings` still finding-shaped. Proven by mutation, not by
inspection. — If wrong: the test costs a few minutes to write and catches nothing the shape test
would not; the brief's version costs nothing and catches nothing at all.

**Ruling 13: do not implement the design's icon fallback in Task 7; measure anyway.** Design
§12 question 1 says that if the page grows a lot, the template should draw an icon only where
`row.ability_id in icons_by_id`. Two things make that inapplicable here. `_macros.html.j2:56`
already performs exactly that test, so there is nothing to add. And `report.html.j2` emits
every entry of `icons_by_id` as a data URI **twice** — once as a CSS `background-image` rule
and once as an SVG `symbol` — for the whole dictionary, whether or not any row references it.
`build_icons` fills that dictionary from the run's abilities and every parse sample's, which
this plan does not touch. So a table row can only ever reference an icon the page already
carries: suppressing the reference would save a span, not a data URI. Task 7 adds markup and
nothing else, and the commit message must attribute the growth to markup rather than repeating
a premise that does not hold in this tree. — If wrong: the recorded figure misattributes a
page's weight, and a later reader optimises the wrong thing.

**Ruling 14: Task 7 measures both figures itself, from one command at one commit.** The brief
says to compare against "the same run before this task" and the previous handoff records
1,023,518 bytes, but nothing records which command produced that number, and the brief's own
suggested command carries `--all-players`, which changes the page's population and draws a
parse leaderboard per player rather than being served from the cache. So the implementer
renders the report once before touching the templates and once after, with the same command
both times and no `--all-players` — same commit, no checkout, the second run served from the
cache at about a point. A self-consistent pair, rather than a comparison against a figure whose
provenance nobody can state. — If wrong: a cheap measurement is repeated; the alternative is an
after-figure compared against a before-figure of a different page.

**Ruling 15: Task 8's Step 2 prescribes the wrong mutation, and it is the step the task rests
on.** The brief says to multiply `our_rate` by 2 inside `trash_rate_measures` and expect the
anti-drift test to FAIL while the trash finding tests still pass. It is the other way round.
After Task 2's refactor `_rate_rows` consumes `trash_rate_measures` and builds its title
straight from the measure's own `m.ours` and `m.their_median`, so mutating that function moves
the finding and the measure together: the anti-drift test stays green and the trash finding
suite, which asserts literal titles, goes red. The brief describes a world where the two were
computed twice — the world before Tasks 1 to 3.

The drift that test actually catches is the one Ruling 11 left uncovered: between
`tables.py::_trash`'s `per_member` and `compare_trash_spells_sample`'s, the mirrored pair.
Mutating `_trash`'s copy alone — its `their_seconds`, or its `MIN_CASTS_TO_COMPARE` filter —
moves `their_median` in the measure and nowhere else, so the anti-drift test goes red while
`trash_spells.py`'s suite stays green. — If wrong: the implementer follows Step 2 literally,
sees the trash suite fail as if it had broken something, and either weakens the test or burns a
fix round discovering this.

**Ruling 16: Task 8's anti-drift test covers the third mirrored builder too, not only the two
rate ones.** The brief's test reads `measures.boss + measures.trash` and never touches
`measures.auras`. Ruling 11 deferred extracting all three `per_member` builders on the argument
that this test is the net under them; with auras left out, that argument only holds for two of
the three. A drift between `_auras` and `_gap_findings_sample` would move an aura table's
median with no finding to contradict it and nothing to catch it. So the test asserts the uptime
findings' figures against `measures.auras` as well, proven by the same kind of mutation against
`_auras`'s own `per_member`. — If wrong: a third of Ruling 11's justification stays unbacked,
which is the thing Ruling 11 traded the extraction away for.

**Ruling 17: Task 7's Step 1 fixture instruction is wrong three times over; replace it.** The
brief says to give `a_player_card()` "in that file" a `comparison_tables` argument "so
`rich_html()` renders it". Checked against the tree:

- `a_player_card()` is not in `test_html_invariants.py` at all — it lives in
  `tests/adapters/render/test_html_sections.py` and is imported;
- `rich_html()` never calls it. It builds the page through `build_report(rich_loaded(),
  rich_findings(), ...)`, so changing that fixture would put no table on that page. Only
  `rich_html_with_icon()` uses `a_player_card()`;
- the brief's second test iterates the cards of a *separately built* report and asserts their
  text appears in `rich_html()`'s HTML — two different pages, so it would pass only by
  coincidence.

The replacement uses the parameter Task 6 just added: pass `comparison_measures=` to the
`build_report` call inside `rich_html()`, keyed by a slug `rich_loaded()` actually produces, so
the table reaches the page through the real path — measures, `build_players`, card, template —
rather than by injecting a view model behind it. The assertions must then be about that same
page, and `test_the_richer_fixture_actually_exercises_what_it_claims_to` must gain a line
proving a table really is on it: without that, a loop over zero tables passes and this becomes
the eighth instance of the failure mode. — If wrong: the fixture work is done at the
`build_report` seam rather than the card seam, which is where the production path runs anyway.

**Ruling 18: the anti-drift test keys by `(stretch, ability_id)`, not by name.** The real run
found the aura table carrying 52 rows under 47 names — five names own two ability ids with
genuinely different figures (one at 1.0000 against 0.9826). The brief's
`by_name[finding.ability_name]` keeps the last of a colliding pair, so it could check a row
against a different ability's measure and pass. Two abilities are each measured on both
stretches, so the stretch half of the key is load-bearing too. The implementer found this from
real data and changed all three tests, re-verifying every mutation after. Ratified. — If wrong:
nothing; a tighter key cannot match less than a looser one that was already ambiguous.

**Ruling 19: the brief's fixtures for the anti-drift test are replaced.**
`a_run_sharing_a_pack` / `a_shared_pack_member` carry no boss casts, so `measures.boss` is
always empty under them: the brief's test would have exercised the trash builder alone while
reading as though it covered both stretches — the tenth instance of this plan's failure mode,
and one that would have hidden inside the very test meant to be the net. The replacement
reaches both stretches, pins that with a `{BOSS, TRASH}` assertion, and uses no denominator
equal to 60s. Ratified. — If wrong: a fixture larger than the brief's, in a test whose whole
purpose is coverage.

**Ruling 20: the e2e importing three helpers from `test_tables.py` stands, and goes to the
final review to triage.** It is the first import across the domain/e2e test boundary. The
alternative is a second definition of the same property, which could drift from the first — and
drift is the exact thing this task exists to catch, so duplicating here would be
self-defeating. Moving the helpers somewhere neutral is the tidier end state but is churn in
the last task of a plan. — If wrong: a test-only coupling that a later reorganisation of
`tests/` has to notice.

**Ruling 21: fold Task 8's round-2 verification into the final whole-branch review rather than
spend a separate reviewer seat on it.** The round-2 argument is subtle — equivalent mutants,
and a kill signalled by a crash rather than a mismatch — so it deserves fresh eyes, but the
whole-branch review is dispatched immediately after, runs on the most capable model, and reads
this diff anyway. It carries the verification as a named must-check instead. — If wrong: the
final review's attention is spread over one more named question.

*(Discharged: the final review verified all three round-2 claims in full.)*

**Ruling 22: render the verdict column rather than retract the claim.** The review found no
verdict column and two places in the tree claiming there is one — commit `9604648`'s body ("a
reader who cannot separate the colours still has the column") and `report.css.j2` ("a word in
the markup and a tint here, never a colour alone"). Both were false as rendered: the verdict
reached the page only as a `class` attribute, which a screen reader does not announce and a
printout does not show. Two ways out — render the column, or delete the claims. Design §5 asked
for the column and wants the two directions to read as a pair in one; the accessibility claim
was already written into the tree twice; and a colour-blind reader got nothing at all. Making a
true claim true is better than retracting it. — If wrong: a sixth column of narrow text, and a
past commit body that described an intention the branch only later delivered.

**Ruling 23: one fix dispatch for all seven findings plus four minors, not a triage.** The
skill allows one fix dispatch after the final review. Every Important here is a one-line
assertion or a comment except I1 and I2; M1 is a comment that does not describe its own code,
which is a hard rule in this repository; and M2, M3, M4 land in the same tests being edited for
C1. Splitting them across rounds costs more in dispatches than the work itself. — If wrong: one
long fix round instead of two short ones.

**Ruling 24: the `Co-Authored-By` trailers naming Sonnet 5 stand.** Ruling 4 settled this: the
trailer is an attribution, so it names the model that wrote the commit. The plan's example
trailer was an example, not a specification. No change.

**Ruling 25: fix it, rather than adjudicate it as a residual.** The skill allows one fix
dispatch after the final review and I have spent it, so the default here is to record and
leave. Not this one. It is reader-visible on the page — a row tinted as above reading "Below" —
and it is the precise disagreement between two projections of one measurement that this entire
branch exists to make impossible. Recording it would leave the branch shipping a hole in its own
central claim to save one small test. — If wrong: one more round on a branch that was otherwise
ready, and one test more than the plan called for.

---

## 3. What the whole-branch review found

The review of `ff2318e..bc351a3` verified the anti-drift net and signed off
`domain/comparison/` as it stood. Every issue was in `report/` or `adapters/render/`, where the
design's page-facing promises live. Each mutation below was actually run against the full suite
and left it green.

**C1 (Critical) — no test asserted any part of a comparison table's caption.**

```
players.py  caption -> "Some rate over some pulls."       SURVIVED
players.py  caption -> "Some rate over some packs."       SURVIVED
players.py  caption -> "Some share of some pulls."        SURVIVED
players.py  {measures.boss_seconds} -> {trash_seconds}    SURVIVED
players.py  {measures.trash_seconds} -> {boss_seconds}    SURVIVED
players.py  pack_count dropped from the caption           SURVIVED
players.py  the word "Derived." deleted                   SURVIVED
```

The only assertion touching a caption was `assert escape(table.caption) in html`, which reads
the caption off the object it is checking: true for every possible caption, false for none. The
aura table could therefore state the trash denominator for a share of boss time — the exact
failure design §6 splits three tables to prevent — and the page could carry a table of derived
divisions with no confidence badge at all.

**I1 — the template's data cells were unasserted.**

```
Median column prints ours       SURVIVED
Range column deleted            SURVIVED
Sample column deleted           SURVIVED
verdict class hardcoded         SURVIVED
ability macro -> bare name      SURVIVED
```

The page could show our own rate under the "Median" heading — the reader-visible failure §8
says structurally cannot happen — and the suite said nothing. §8 is a statement about the page,
and the page is where enforcement stops.

**I2 — there was no verdict column, and two comments claimed there was.** See Ruling 22.

**I3 — `_aura_rows` was the unguarded twin of `_rate_rows`.**

```
verdict="level"   SURVIVED   (the rate equivalent is killed)
spread="n/a"      SURVIVED
sample=""         SURVIVED
```

The verdict one is the worst: an aura the comparison explicitly refused to judge
(`Verdict.UNJUDGED`, whose whole point is that `onSelf` cannot tell a player's own buff from a
teammate's) would render styled as level, with a sample beside it — a claim the project forbids.

**I4 — `ComparisonRow.ability_id` was never pinned in either builder.** Both survived
`ability_id=0`. The id was pinned at the measure level and then dropped. This is the icon key: a
zeroed or swapped id draws the wrong art beside a name, the one failure a name-only assertion
cannot see.

**I5 — `rate_measures`'s missing zero guard is load-bearing and undocumented.** See §1.2 above.

**I6 — `_icon_uris` does not walk `comparison_tables`, and nothing said so.** A table row's
`ability_id` resolves to an icon only if that ability already appears in a death card, a ledger
row or a player timeline. That outcome matches design §12's own named fallback and was measured
honestly, but it arrived by omission rather than decision. A comment naming §12 closes it.

---

## 4. Known gaps, recorded and left

- **Aura anti-drift has never been exercised on real data.** The report used produced zero
  uptime gap rows, so the real run confirmed the aura table exists but not that it agrees with
  an uptime finding. Unit-covered only.
- **Design §11 specifies the anti-drift test as covering "every rate and uptime finding on the
  page".** What shipped compares `Finding` objects to `AbilityRate` objects. The plan narrowed
  it in its own Task 8 Step 1, so the narrowing predates implementation. The page-level
  equivalent exists separately, as the rendered-cell test.
- **Commit `9604648`'s body describes an intention the branch only later delivered.** It says a
  reader who cannot separate the colours "still has the column". That was false when written —
  the verdict reached the page only as a `class` attribute — and became true at `2157e5b`, which
  added the column under Ruling 22. History was not rewritten. Recorded so nobody reads
  `9604648` alone and concludes the claim was a lie.
- **A zero-duration boss pull is synthetic.** The repository documents degenerate pulls of a few
  milliseconds (`MIN_PACK_SECONDS` exists for them) but exactly zero has not been seen in a real
  response.
- **`test_tables.py` imports six names from four comparison modules**, to ask the guards
  directly rather than restate their numbers. The right trade, but the module is no longer cheap
  to read.
