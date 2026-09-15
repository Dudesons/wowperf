# Raid HTML Report — Rulings and Evidence

**Status:** Recorded 2026-09-15, after the plan was executed, every task's review came back clean,
and the whole-branch review's one fix wave closed. This is a record of judgement, not a
specification.

**Scope.** `docs/plans/2026-09-15-raid-report-plan.md` was executed end to end under
`superpowers:subagent-driven-development` against spec `docs/plans/2026-09-13-raid-analysis-design.md`
(§10 is the report): 15 tasks — Task 6b was inserted during execution — a fresh implementer per
task, a scoped review after each, fix rounds where a review found something. Commits
`195d6cd..bbdbd12`, merged to `main` as `30cd7fd` via PR #6. The baseline at the base commit
`195d6cd` stood at 1880 passed, 16 deselected, ruff clean, mypy clean over 204 source files; the
final gate stands at 1954 passed, 17 deselected, ruff clean, mypy clean over 218 source files. The
whole-branch review raised no Critical and four Important findings; one fix wave closed all four,
and its scoped re-review passed.

The execution workspace was gitignored scratch and has been deleted.
Everything in it that could not be re-derived from the code or from `git log` is here: twenty
rulings with their reasoning and their cost if wrong, the three rulings the pre-flight scan made
before any task ran, the couplings no test enforces, the work this plan leaves for the next one,
and the two page states that no task-scoped review could have seen. Per-task briefs, per-task
reports and review diffs stay behind — they record how the work was done, which the commits
already carry.

Read this before touching `src/wowperf/domain/report/raid_build.py`,
`src/wowperf/domain/report/raid_players.py`, `src/wowperf/domain/report/raid_frame.py`,
`src/wowperf/domain/report/raid_ledger.py`, `src/wowperf/domain/fight.py`, or the five raid
templates under `src/wowperf/adapters/render/`. The design it argues from is
`2026-09-13-raid-analysis-design.md`.

---

## 1. What a later plan will trip over

### 1.1 The plan claimed one domain change, and the death chain cost a task of its own

The plan states its own boundary twice — "It adds no analyser and no query. Every figure the page
draws is already computed by plans 1, 2 and 3a. The one domain change is Task 2's id minting" —
and design §6.11 backs it, calling the death chain "fully generic already". Both sentences are
false, and Task 7's implementer found out the moment it read the two functions its brief told it
to call. `build_deaths` and `tooltips_by_finding_id`, in
`src/wowperf/domain/report/deaths.py` and `src/wowperf/domain/report/finding_tooltip.py`, both
took a `LoadedRun`. `LoadedEncounter` is a sibling of `LoadedRun`, not a subclass. A raid report
could not call either one. The implementer returned NEEDS_CONTEXT with no commits and a clean
worktree; the controller verified the defect independently before believing it.

The two escapes were both worse than the third. Shipping `deaths=()` would have gutted the Deaths
tab that design §10 requires, and Task 11 would then have baked the hole into a golden file, where
a falsehood stops looking like one. Folding the refactor into Task 7 would have put a cross-cutting
change to five shared modules on the same review surface as the builder with the most control flow
in the plan. So the widening became its own task, 6b, dispatched and reviewed alone before Task 7
was re-dispatched — one more task and one more review than the plan budgeted.

Task 6b narrowed five functions to the values they read, and gave the three that genuinely read a
whole fight a protocol: `LoadedFight` in the new `src/wowperf/domain/fight.py`. No `isinstance`, no
`hasattr`, no union. `src/wowperf/domain/analysis/recap.py` now imports no aggregate at all, which
is design §5.2's stated goal, and `src/wowperf/domain/report/build.py` came out byte-identical to
its state before the task. The protocol is deliberately smaller than either aggregate:
`LoadedRun.enemy_deaths` and `LoadedEncounter.standing` have no counterpart across the pair, and
naming them would have made the protocol a lowest-common-denominator copy of two models instead of
a statement about what a death recap reads.

**What a later plan should take from this.** A plan's claim about its own blast radius is a
hypothesis, not a fact, and the pre-flight scan cannot test it: the scan compares one task's output
against another task's expectation, and a shared function's existing signature is neither. Both of
this plan's cross-task conflict rows about the death chain agreed with each other and were both
wrong about the code. The thing that caught it was an implementer reading the callee before
writing the caller. Design §6.11's "fully generic already" remains in the design; it is true of the
recap's arithmetic and false of `build_deaths` and `availability_at`, and it was the sentence the
plan trusted.

### 1.2 Two tasks were told to write the same file, one of them told to create it

The pre-flight scan found one genuine conflict in fifteen tasks, and it was this. Task 10 lists
`tests/adapters/render/test_raid_html_invariants.py` under **Create**, while Task 9's step 1
already writes two tests into that same file — tests that read `RAID_PANEL_ORDER`, a constant Task
10's own step 1 defines. Run in plan order, Task 9 would write a file referencing a name that does
not exist, and Task 10 would then create a file that already did.

**Ruling A** resolved it forward rather than by reordering: Task 9 creates the file, defining
`RAID_PANEL_ORDER` verbatim as Task 10 gives it, plus the minimum fixtures its own two tests need.
Task 10 then extends that file and does not redefine the constant. Task 9's tests cannot run
without both, and Task 10's text is the authority on the constant's content, so the constant is
copied forward rather than invented. **Cost if wrong:** the constant and two fixtures sit in the
file one task earlier than the plan's prose says; nothing moves between files, and no assertion
changes.

### 1.3 The bare-number scan was blind to every module this plan created

The plan's Global Constraints bind every new view-model field to `NUMBERS_THAT_ARE_NOT_TOTALS` in
`tests/adapters/render/test_html_invariants.py`. The scan that enforces that walks
`view_model_types()` (`tests/domain/report/test_model.py`), which enumerates only what
`wowperf.domain.report.model` defines. It cannot see `raid_model.py`, which did not exist when it
was written. Accepting the constraint as the plan worded it would therefore have left it
unenforced for every field this plan added — a rule that reads as binding and has no path to
failure, which is this repository's characteristic defect wearing a different hat.

**Ruling B** made Task 10 add a raid counterpart to the walk, and carried the constraint as binding
on Task 4's dispatch even though no test could see it yet. Task 10's implementer then implemented
it wider than asked, and better: the scan covers `raid_frame` as well as `raid_model`, because
`RaidReport` has no numeric field at all and a `raid_model`-only scan would have left
`(RaidHeader, "size")` exactly as unenforced as before. Two deliberate failures proved it.
**Cost if wrong:** one extra test function in the raid invariants file.

**Ruling C** declined to write `RAID_PANELS`. The plan's File Structure table names it as
`raid_frame.py`'s responsibility, and no task in the plan mentions it again; the only panel
registry any task specifies is `RAID_PANEL_ORDER`, a test constant. Writing an unused domain
constant to satisfy a table is dead code on arrival. **Cost if wrong:** nothing — a panel registry
in the domain would be purely additive if one is ever wanted.

### 1.4 The difficulty-name ruling overrode the plan's own rule, in the direction the rule anticipated

This one deserves its own record, because the final reviewer pushed back on it and the push-back
was fair.

Task 3 needed a readable difficulty for the raid header: `Encounter.difficulty` is a bare `int`,
and design §10 asks the header to print the difficulty by name. The plan pre-wrote the decision
rule rather than the answer, and the rule was sound: introspect the live schema first, and *"if one
exists: resolve the name at runtime through the adapter, add a dated row to the skill file's table,
and skip step 2. The invariant is 'no hardcoded season data' and an API source always wins."* The
task was dispatched on the standard tier rather than the cheapest the plan assigned, precisely
because a dated claim in `.claude/skills/wcl-api/SKILL.md` is the invented technical detail
`CLAUDE.md` forbids if it is not measured.

The implementer measured, and a source does exist. Neither `ReportFight` nor `worldData.encounter`
names a difficulty — `ReportFight`'s 43 fields carry `difficulty` and nothing that names it, and
the encounter type carries `id, name, characterRankings, fightRankings, zone, journalID`. But
`Zone.difficulties` returns `[Difficulty]` with fields exactly `id, name, sizes`, and a live query
through the analysed encounter's own zone named ids 5, 4, 3 and 1 as Mythic, Heroic, Normal and
LFR, on 2026-09-15. The plan's own pre-written `season.toml` comment, which asserted that the API
echoes no name at all, was false; the implementer correctly refused to commit it as written and
recorded the true, dated finding in the skill file instead.

**The ruling went the other way.** The table is hand-kept in
`src/wowperf/domain/report/raid_frame.py`, and the dead `[raid.difficulty_names]` block was deleted
from `data/season.toml`. Four arguments carried it. Nothing read that block — the only consumer,
`adapters/config/toml.py`, reads the partition — so it was two copies of one fact with nothing
keeping them in step. `build_raid_header(encounter: Encounter) -> RaidHeader` is domain code that
performs no query of its own, so reaching `Zone.difficulties` means a second `worldData` query
threaded through the adapter and passed in, which is a change to the fetch path rather than to the
header. Difficulty ids 3, 4 and 5 are stable game vocabulary rather than season data that retunes
between tiers. And a number the table does not carry prints as `Difficulty {n}` rather than a
guess, so a stale table degrades loudly.

**The argument against, stated so nobody re-decides it silently.** The plan wrote its rule before
knowing the answer, which is the right time to write a rule, and the rule said an API source always
wins. Evidence then arrived in exactly the direction the rule anticipated, and the ruling overrode
it on cost grounds. That is the shape of reasoning that lets an invariant erode one defensible
exception at a time. The final reviewer accepted the outcome and flagged the process, and it is
flagged here rather than re-decided. Whoever next touches the raid header should treat
`Zone.difficulties` as a known, live-verified source that this project has chosen not to read yet —
the full note, with its date and its queried field list, is in
`.claude/skills/wcl-api/SKILL.md` under "A difficulty's name lives on its zone, not on the fight or
the encounter". **Cost if wrong:** the table sits in domain code instead of `data/`; moving it
later is one extra argument on two functions, and wiring the query is one more.

---

## 2. The twenty rulings

Each was a decision made during execution, with what it costs if it turns out wrong. Numbered in
the order they were made. The three pre-flight rulings are in §1.2 and §1.3 above.

**Ruling 1 (Task 2).** `encounter_service._for_raider` is body-for-body identical to
`comparison/service._for_player`, and the implementer defended it with a false rationale — that the
two loops carry different subject types and a shared helper would need a protocol to describe a
`str` field. Both functions take `(findings: list[Finding], slug: str)`. The reviewer offered two
fixes and named the rationale correction as sufficient. Ruled: correct the rationale, do not
extract the helper. Extraction would edit `src/wowperf/domain/comparison/service.py`, which sits on
the `analyze` path this plan's scope excludes, and a cross-path refactor of shared comparison
plumbing deserves its own change and its own review rather than riding on the branch's
load-bearing task. **Cost if wrong:** two four-line functions stay in step by hand until somebody
extracts them; the duplication is recorded in §3.

**Ruling 2 (Task 3).** Dispatched on the standard tier rather than the cheapest the plan assigns,
because step 1 writes a dated claim into `.claude/skills/wcl-api/SKILL.md` and an unverified row
there is the invented technical detail `CLAUDE.md` forbids. **Cost if wrong:** one task costs more
than the plan budgeted.

**Ruling 3 (Task 3).** The difficulty-name table lives once, in `raid_frame.py`, and the dead
`[raid.difficulty_names]` block leaves `data/season.toml`. Argued in full in §1.4 above, both ways.
**Cost if wrong:** the table sits in domain code instead of `data/`.

**Ruling 4 (Task 3).** `build_raid_header` gains the branch the brief omits: where
`fight_percentage` is `None`, the outcome reads exactly `Wiped`, with no number. The field is
`float | None` and documented as `None` where the report itself does not say, so the brief's
formatting would have raised `TypeError` on a real wipe — and a number the log never gave must not
be invented, least of all a zero standing in for one. **Cost if wrong:** one word of header copy.

**Ruling 5 (Task 3).** The controller's own "leave the skill file untouched" instruction falsified
a sentence inside it: the note still claimed the table was hand-kept in `season.toml` after the
ruling had deleted that block. Corrected in the task's first fix round. **Cost if wrong:** none;
the correction is one line.

**Ruling 6 (Task 4).** `all_raid_ledger_rows` walks each `PlayerCard`'s own `damage_rows` and
`spell_and_talent_rows`, though the brief's Step 3 snippet omits both. The Mythic+ `all_ledger_rows`
walks exactly those two, and its docstring gives the reason — a caller cannot reach eight of the
nine and lose the ninth in silence. A row that reaches the page without reaching the icon resolver
draws nothing and reports nothing. The brief's snippet was incomplete; obeying it would have been
the defect. **Cost if wrong:** the walk yields rows Task 7 never puts there, which is inert.

**Ruling 7 (Task 5).** The brief's call shape `analyse_encounter(*a_rich_encounter())` cannot reach
the `mechanics` and `parse_subjects` keyword-only arguments, so the hand-written `RAID_FAMILIES`
list would have been held against the service only for the families three positional arguments
produce — leaving `mechanics.*` and `compare.*` checked against nothing. The file's entire claim is
that a new family cannot go silently unplaced, and those two are the families most likely to gain
members. Ruled: the fixture supplies those keywords, reusing the inputs
`tests/domain/analysis/test_encounter_service.py` already builds, and the implementer reports
BLOCKED if reuse proves impossible so the ruling can be reconsidered on evidence. The coverage test
now asserts strict equality against the 24 families the service emits. **Cost if wrong:** a heavier
fixture.

**Ruling 8 (Task 6).** Card ordering — subject first, then roster order — was documented in
`build_raid_players`' docstring and covered by no test. Ruled: add one before review, with a
subject that is not already first, so the assertion distinguishes subject-first from roster order.
An untested docstring claim is this repository's characteristic defect, and the visible consequence
here is the Players tab opening on the wrong raider, which is the thing `--player` exists to
control. **Cost if wrong:** one extra test.

**Ruling 9 (Task 7).** The `LoadedRun` widening becomes its own task, 6b, dispatched and reviewed
alone before Task 7 is re-dispatched. Argued in full in §1.1. **Cost if wrong:** one more task and
one more review than the plan budgeted.

**Ruling 10 (Task 7).** Task 6b must **narrow**, not branch. This project's rule, and Task 1's own
precedent, is that a shared function takes the values it reads — never an aggregate it switches on,
and never an `isinstance`. A union type with accessors would be acceptable only if narrowing proved
genuinely impossible, and then the reason would be recorded here. It did not: five functions
narrowed cleanly and three took a protocol. **Cost if wrong:** a wider refactor than a union would
have been, bought by keeping the seam the rest of the codebase already uses.

**Ruling 11 (Task 7).** `comparison_measures` is dropped from `build_raid_report`'s signature. The
raid path can never produce it — it needs a `LoadedRun` — and `build_raid_players` takes no
measures and builds no comparison tables, so the parameter would be accepted and ignored, which is
a lie in the interface. Task 12's dispatch carried the corrected signature. **Cost if wrong:** if a
later slice puts the secondary-stat tables on raid cards, both builders grow the argument then.

**Ruling 12 (Task 6b).** The trailing ", between pulls" on a boss death's `when` is Task 7's to
fix, not a deferral. `_when` (`src/wowperf/domain/report/deaths.py`) appended that phrase whenever
`pull_index is None`, which is every boss death, so every raid death card read "5:00, between
pulls". A fight with no pulls is one continuous window: there is nothing to be between, so the
`when` states the elapsed time alone and any replacement phrase would add nothing. The Mythic+
string had to come out unchanged, proven by the existing suite and by the Mythic+ golden file.
Fixed now rather than deferred because Task 11 bakes the rendered page into a golden file, and a
falsehood in a golden file stops looking like one. **Cost if wrong:** the raid card reads "5:00"
where somebody later wants "5:00 into the fight".

**Ruling 13 (Task 6b).** Of the three shared strings that read oddly on a boss fight, Task 7 fixes
only the falsehood. "Not seen acting again this run." and "either none is listed for this run" are
correct vocabulary on the Mythic+ path and merely off on a raid; parameterising them means touching
frozen Mythic+ wording. They went to Task 14's read-the-page-as-a-reader step, which confirmed them
present and left them alone. **Cost if wrong:** a raid death card says "this run" where "this
attempt" would read better — a nit, not a false claim.

**Ruling 14 (Task 7).** Suppress a per-card provenance line whose reason is the one the Damage
section already gave. On a twenty-player wipe every raider's reason is the same paragraph, so
mirroring `build_report` would put 21 identical copies in Provenance. `build_report`'s own rule is
to say it once when the reason is about the whole run and per-card when it is about that card, and
design §13 agrees; a wipe's reason is about the attempt, not about any raider. The rule was always
right — only the roster size made the divergence visible, since five copies look like emphasis and
twenty read as a bug. Each card keeps its own reason on the card. One pre-existing test asserting
the removed behaviour was renamed and narrowed, and flagged to the reviewer as a named risk.
**Cost if wrong:** a reader loses a per-card restatement of a sentence already stated once above;
the condition is three words to remove.

**Ruling 15 (Task 7).** The Mythic+ degenerate case — a run with no pulls at all — now reads
"0:05" instead of "0:05, between pulls", changing one existing assertion. Kept. Claiming "between
pulls" about a fight with no pulls is false wherever it happens, so the value-based rule is more
correct on the Mythic+ path too, and deciding otherwise would mean branching on which kind of fight
arrived. Real Mythic+ output — pulls present, and the golden file — is byte-for-byte unchanged.
**Cost if wrong:** one degenerate-fixture string.

**Ruling 16 (Task 7).** The Damage gate keys on whether `damage_rows` is non-empty rather than on
the unavailable finding's presence, which is a different condition from the one the plan's Ruling 3
described. Accepted after the reviewer traced it: a presence gate would have withheld the whole tab
whenever any single raider hit the no-sample branch on a kill, hiding nineteen raiders' measured
figures because of one missing sample. The plan's ruling governed the *matching*; the condition
change is better and stands. **Cost if wrong:** none identified — `compare_rank` yields a damage
row whenever the fight was ranked, so "rows empty" holds exactly on a wipe or under `--no-compare`.

**Ruling 17 (Task 8).** The raid provenance line drops the Mythic+ `+<keystone_level>` segment, and
**no** field is added to `ReferenceRecord`. That record's field set is closed on purpose — a test
asserts it has no field for a figure — so that it stays a link rather than a tabulation of other
players' runs; changing it is a decision about that rule, not a formatting fix. And the segment is
worth nothing here: the rankings query takes `difficulty` as a request argument, so every raid
reference shares the analysed fight's difficulty, which Task 3 already prints by name in the
header. A comment in the partial records why it is absent. **Cost if wrong:** a reader cannot see a
per-reference difficulty; the header states the only one there is.

**Ruling 18 (Task 8).** The header subhead uses the existing `.sub` class, not the brief's
undefined `subhead`. `.sub` is already styled and is what the Mythic+ header uses; a new
`.subhead` rule would have spent this task's one CSS allowance — reserved for what the Damage and
Mechanics tabs need — on a header. Found by the implementer reading the rendered page, which is the
only check this deliberately test-free task has. In the event `report.css.j2` finished with a zero
diff, so the allowance was never spent at all. **Cost if wrong:** one class name.

**Ruling 19 (Task 9).** The review's Important finding — that
`test_a_raid_report_renders_its_seven_panels` cannot detect a panel/tab id mismatch — is carried
into Task 10 rather than fixed in Task 9. `data-tab-for` appears only on the seven nav buttons and
never on the sections, so counting it re-counts the buttons; and counting `<section class="panel"`
counts sections whatever ids they carry. A typo in a partial's own `id="tab-x"` would pass both
assertions and click through to nothing in a browser. The test bodies came verbatim from pre-flight
Ruling A, so this was the brief's gap, not the implementer's, and Task 10's own specified items 6
and 7 are exactly the tests that close it, and writing them a task early would duplicate the next
task's work. **Cost if wrong:** if Task 10 wrote those tests weakly the gap would persist, so its
dispatch named this explicitly and its reviewer received it as a named risk. Task 10 closed it:
`test_every_panel_appears_once_in_tab_order` now reads the ids the sections actually render and
compares them as a list, and `test_every_panel_has_exactly_one_tab_button` asserts both directions
at once. Its fix round kept the section count beside the list equality after finding that a panel
written with no id at all is invisible to the regex while still changing the count.

**Ruling 20 (Task 14).** The final whole-branch review covers `195d6cd..HEAD`, not
`merge-base(main)..HEAD`. The merge base with `main` was `d555d4f`, which would have dragged in
plan 3a's entire merged work — already reviewed, out of this plan's scope, and enough diff to drown
the review. `195d6cd` is the commit that added this plan's document, so `195d6cd..HEAD` is exactly
what this plan produced. **Cost if wrong:** the final review does not re-examine already-merged
work, which is the intent.

---

## 3. Coupling no test announces

**A tab and its panel are matched by string equality, and nothing counts them.** The seven nav
buttons live in `src/wowperf/adapters/render/raid.html.j2` as
`<button type="button" class="tab" data-tab-for="tab-summary">`, and each panel lives in its own
partial as `<section class="panel" data-tab-panel="main" id="tab-summary">`. Two hand-written
halves in two files, joined by a literal string the script looks up at click time. Nothing in the
rendering loops over a registry, and nothing derives one half from the other — Ruling C declined to
write the domain registry that might have. The only registry anywhere is `RAID_PANEL_ORDER`, a
constant in the test module, and the tests Task 10 built around it are what turn a typo into a red
test rather than a dead tab. The coupling itself stays convention: adding an eighth tab means
editing two files that do not know about each other, and remembering a third that does. The same
shape governs the Mythic+ page, where it has held for six tabs.

**`encounter_service._for_raider` and `comparison/service._for_player` are body-for-body
identical.** Both take `(findings, slug)` and return the same `model_copy` comprehension. Ruling 1
kept them apart deliberately and corrected the docstring that claimed they could not be shared, so
the duplication is disclosed in the code rather than hidden — but no test pins the two behaviours
together, and the id-minting rule could drift on one path with nothing noticing.

**`raid_players._stats_line` re-derives the shape `build_players` inlines in `players.py`**, from
raw `LoadedEncounter` tuples. Two near-identical format strings in two files, with no shared helper
and no test comparing their output.

**Two private symbols are imported across module boundaries.**
`src/wowperf/domain/report/raid_build.py` imports `_check_unique_finding_ids` from
`report/build.py`, and `src/wowperf/domain/report/raid_players.py` imports `_comparison_section`
from `report/players.py`. Both are genuine reuse of exactly the right function — the duplicate-id
gate and the three-state comparison section are the two rules this plan most needed to keep
identical between the two pages — and the leading underscore now says the opposite of what the
import does. Either name them public, as `bracket_for` and `rankings_block` already are in the
adapter layer, or accept that the underscore no longer means private here. Nothing enforces either
reading today.

**`RAID_PLACEMENTS`'s `("compare.rank", "damage_rows")` entry carries no trailing dot**, unlike
every other prefix in the table. Brief-mandated, and safe only while no sibling family starts with
`compare.rank` and is not a rank finding. The ordering test that guards the table checks that no
broader prefix sits ahead of a narrower one; it does not check that a prefix ends where a family
name ends.

**`_FAMILY_PREFIXES` in the raid ledger's test module is a second hand-maintained list** that must
stay in step with `RAID_FAMILIES`. It fails safely — an unmatched id shows up as a spurious
coverage failure rather than as a silent misclassification — which is why it was left as it is.

---

## 4. Gaps left open

### 4.1 The three named in PR #6

**`_damage_unavailable` builds a finding with no evidence, at all five of its call sites.**
`src/wowperf/domain/comparison/throughput.py` defines it to return a `Finding` with `id`, `title`,
`detail`, `confidence` and `seconds_lost` and no `evidence` argument, so the tuple defaults empty.
Its five callers cover the four states the function's own docstring enumerates — no kill, a name
this report carries twice, a player absent from a row that exists, and a leaderboard that came back
empty — plus the boss-damage variant of the last. Each of those states has something concrete to
say, and neighbouring branches in the same module do say it. Task 8 fixed the two evidence bullets
it had itself added and left this, correctly: the gap predates the task and touches the `analyze`
path as well. The implementer also spawned a user-facing follow-up chip for it, was told not to
dispatch work, and the chip was withdrawn — so this record and the PR description are the only
places it lives.

**`"{n} times"` has no singular case in two shared analysers, and the correct form already exists
in two others.** `src/wowperf/domain/analysis/deaths.py:239` writes `f"{name} died {count} times"`
and `src/wowperf/domain/analysis/interrupts.py:213` writes
`f"{names[ability_id]} landed {counts[ability_id]} times"`, so a page can read "died 1 times".
`src/wowperf/domain/analysis/consumables.py:141` and
`src/wowperf/domain/analysis/defensives.py:152` both already write
`"once" if len(lines) == 1 else f"{len(lines)} times"`. The fix is four lines and the pattern to
copy is in the same directory. It was not made here because both offenders are shared analysers
that render on the Mythic+ page too: changing them changes Mythic+ wording and its golden file,
both outside this plan's bounds. Task 11's golden file now freezes the wrong forms on the raid side
as well, so the follow-up change moves two goldens.

**The two cross-module private imports**, recorded in §3 above.

### 4.2 Arithmetic deliberately preserved

**`Run.window_ms` carries a float truncation, documented and pinned by a test.** The window's end
is computed as `start + int((last_end - start) / 1000 * 1000)` rather than as `last_end` directly,
and the round trip through a float lands a millisecond short for about one integer in a hundred and
twenty — 182 of 20 000 measured. Every reader computed it that way before the property named the
arithmetic, and the only thing the window does is clip aura bands. Correcting it is a change of
behaviour and belongs to a change that says so and tests it. Task 6b's fix round added the
cross-module assertion that the equality rests on: `model.py` and `frame.py` each write their own
`max(pull.end_ms)`, in two modules that cannot import each other, and breaking only the `frame.py`
side now produces a failure rather than silence.

### 4.3 Duplication and fixture debt

Each of these is correct as shipped, and each is left for the next plan or a future fix round:

- `Encounter.outcome` already encodes the same three-way outcome logic the raid header re-derives,
  in the findings' own words rather than the header's. The two must now be kept in step by hand — a
  consolidation candidate.
- A difficulty name could be resolved from `Zone.difficulties` instead of the hand-kept table, at
  the cost of one query per run. Recorded in the skill file and argued in §1.4.
- `_family()` in the raid ledger's test module re-sorts its prefix list on every call rather than
  once at module scope. Harmless at test scale.
- `recap_timeline` is typed on the whole of `LoadedFight` while reading four of its members.
  Splitting the protocol into four would be worse than the overstatement.
- `run_start_ms` computes a `max` it discards, so `run_seconds` walks the pulls three times instead
  of twice. Irrelevant at real pull counts.
- `card.slug in compared_slugs` has no raid-side test; it is mirrored from `build_report` and
  covered there.
- Under `--no-compare`, two provenance lines carry identical reason text for two different
  sections. Compliant with Ruling 14, which governs per-card lines; noted in case the
  once-per-distinct-reason rule should later apply across sections too.
- A raid `ReferenceRecord` sets `keystone_level=0`, a field that means nothing on that path. Plan
  3a's, already merged.
- The word `compared` means a frozenset in one raid-invariants fixture and a count in another,
  forty lines apart. Inherited from the brief's fixed signature.
- `a_ledger_row` sets `ability_id` while leaving `title_ability` and `title_after` empty, a state
  the real builder would never produce. Harmless to the icon assertion; a later task reusing the
  fixture for a title-consistency scenario should not copy it blindly.
- `a_parse_subject` in the encounter-service tests defaults `slug` and `display_name` to raider 0
  regardless of an overridden `player` — one forgotten keyword from a silently wrong fixture.
- Three `assert compared` guards prove that findings exist, not that a real comparison ran; one
  `assert any(f.id.startswith("compare.rank."))` would pin it.
- `tests/domain/report/test_build_players.py:446-455` carries a pre-existing test sharing a name
  with the new one in `tests/domain/report/test_players.py`. Redundant, not this plan's to
  consolidate.
- The raid golden page renders no icon art, so its "no remote src" check is vacuous — consistent
  with the Mythic+ golden and covered by the icon-address rules elsewhere. The golden is held only
  by byte equality; its structural invariants are not re-run over the render.
- `# type: ignore[arg-type]` on the `ParseSubject` dict splat turns off type checking on the golden
  fixture's most structured object.
- `compared_slugs` is computed in `cli.py` by a truthiness check on `parse_subjects` after the
  `if not no_compare:` block, where `analyze` sets it unconditionally inside. Proven equivalent
  today, because `_parse_samples` appends one subject per entry of `to_compare`, which is never
  empty.
- The raid end-to-end test checks that every card has a naming finding, but not the symmetric
  direction — that every finding's `player_slug` is a card. Covered transitively by the roster-size
  equality; worth a comment if the file is touched again.
- The plan document's own Task 14 header lists two files while its body also directs editing the
  `analyzing-a-run` skill. The implementer followed the body and disclosed the discrepancy.

### 4.4 What this plan deliberately leaves undone

- **`_boss_share` taking the first `Boss` row** (`src/wowperf/domain/comparison/targets.py`) stays
  as it is and stays recorded. No council fight has been read, and a change on no evidence is worse
  than a documented unknown.
- **`raid` takes no `--narrative`.** Design §11 lists the raid flags and that is not among them.
- **`--throughput-ceiling` is not a raid flag either**, so `build_raid_report` takes no throughput
  argument.

---

## 5. Where the process itself failed, and was caught

**Two page states existed that no task-scoped review could have seen, and the whole-branch review
found both.** Each was inherited faithfully from Mythic+ markup where it cannot fire, which is
exactly why every per-task reviewer read it and approved it.

The first: `_raid_mechanics.html.j2` had no empty state, so a `--no-compare` run on a clean fight
rendered a bare heading. Every other panel on either report says "Nothing to report." The second:
`_raid_summary.html.j2` rendered the heading "Figures that contain others" and its do-not-sum
caveat over nothing on a deathless kill — the best possible raid outcome, and the exact fight the
end-to-end test's own docstring describes. The Mythic+ `_summary.html.j2` places its heading and
caveat outside the `{% if %}` guard in the same way, and never shows an empty one because a
keystone run always has time decomposition; a raid's decomposition is `deaths.total` alone, so a
kill with no deaths empties it. A per-task reviewer comparing the raid partial against its Mythic+
original finds a faithful port. Only a reviewer asking what the page looks like on a fight with
nothing wrong finds the hole.

Both were fixed in the one fix wave, and the raid golden file did not move — its fixture always
carries a death and mechanics rows, so it never reaches either empty state, which is precisely why
those states needed tests of their own. Two new tests, and the Mythic+ golden confirmed unchanged.

**A test that names real people on failure survived its own task's review, and a comment defended
it by citing an instruction that does not exist.** The raid end-to-end test's duplicate-id
assertions printed real character slugs in their failure messages. Each assertion now reports a
count and the families that collided, and the page's own cards are the only place a slug is read at
all. `CLAUDE.md` names this obligation for both real reports, and the defence a reader would have
met — a comment pointing at a docstring instruction — pointed at nothing. A per-task review reads
the assertion; only a review reading the repository's standing rules against the diff asks what the
assertion prints when it fires.

**Two docstrings miscounted or misdescribed what sat beside them, and both survived to the final
review.** `src/wowperf/domain/fight.py` said its protocol carried five event streams and seven
members where it declares ten, and `parse_axis.py` said `ComparisonSubject` "carries a whole
`LoadedRun`" where the `LoadedRun` is a separate argument. The first was raised inside Task 6b,
deferred there as out of scope for a fix round, carried into Task 7's dispatch so nobody was misled
by the count — and then two agents disagreed about the true number, which is itself the argument
for correcting a count somewhere it gets its own review. Both were fixed in the final wave. A
docstring is the one artefact in this repository that no test can hold to the code, so it fails
silently and accumulates.

**A re-reviewer verdicting "does this sentence say X" will not notice that X contains a wrong
number.** Task 3's first fix round introduced, into the ground-truth skill file, a clause with
wrong arithmetic — "the other 42" where 24 of 43 items are listed, so 19 — and an unparseable
ending. The scoped re-review quoted the clause approvingly without checking its numbers. The
controller caught it on reading the file, and a second fix round corrected it with an independent
count. A review scoped to a claim will verify the claim and not the figures inside it.

**The commit trailer came back wrong three times, and the cause is structural rather than careless.**
A subagent's own harness instructs it to sign as its acting model, and that instruction beats a
plan's fixed literal. It happened on Task 1, was diagnosed there, and every later dispatch stated
the fixed `Claude Opus 5` literal and said the harness was overridden — and it still regressed on
Task 12. Twice on the cheapest tier and never on the two above it: the cheap tier's own attribution
instruction reliably wins. A later plan should assume the trailer is wrong on any cheap-tier
dispatch and check it rather than instruct against it.

**One fix round was verified by the controller rather than re-reviewed, and the deviation is
recorded openly.** Task 12's second round fixed a commit message and nothing else. The two commands
a re-reviewer would have run — `git diff` against the prior commit, and reading the full message —
were run in the controller's own transcript with their output visible. That is weaker evidence than
a scoped re-review and is named as such.

**The plan's own defect-catching task caught the plan's own defect.** Task 10's brief specified a
step 3 fixture and a step 4.2 mutation, and the fixture would not have failed the mutation:
`player_slug("Emberkin 1")` is already `emberkin-1`, and `display_names` disambiguates shared names
before slugging, so the collision the mutation was meant to expose could not occur. Corrected to
eighteen indexed names plus the sanctioned `Bríala`/`Briala` pair, which is the only route to a real
slug collision. The task built to catch a test that could not fail caught one written into its own
brief.

**The load-bearing task was proven on real data, which is where this project's defects have always
appeared.** On the real twenty-player roster the report produced 266 findings under 266 distinct
ids, 415 element ids all distinct, 20 player cards and 20 distinct `player_slug` values. The same
report produced those same 266 findings under 79 distinct ids before Task 2. That reading is the
whole justification for Task 2 reversing plan 3a's recorded decision.

**The live readings are cold, and are recorded as cold.** The plan's Ruling 5 assumed the warm
caches from plan 3a and anticipated this: the reference entries were 27.2 hours old against a
24-hour expiry when Task 13 ran, so the leaderboard and reference half had gone. The permanent run
cache was unaffected. Task 13 spent 876.08 points of 3600, leaving 2722.92, with the dearest
operations Talents 212.83, Fights 186.86, Casts 117.00, AuraTable 107.00, DamageDoneTargets 107.00,
Abilities 93.00 and RaidCharacterRankings 38.38. Task 14's three reader-pass runs then cost 50.59
points in total, the kill and the `--all-players` run fully warm at 1.00 each and the wipe close to
cold because its fight had never been fetched — a different boss, because the analysed kill's own
boss had no wipe logged in that report, which the skill file discloses at the point of use. Anyone
comparing these figures against plan 3a's must read the cache condition alongside the number. Two
nominally-cold readings of the same fixture differed by 1.66 points with no explanation; the
whole-branch review promoted that from a deferred minor to a fix-before-merge item, and the note
now says so.

**The reader pass found no new raid-specific defect**, and confirmed one thing worth keeping: the
wipe page's withheld notice is correctly scoped. It does not claim to withhold the Mechanics tab's
separate reference-kill comparison, which still runs on a wipe.
