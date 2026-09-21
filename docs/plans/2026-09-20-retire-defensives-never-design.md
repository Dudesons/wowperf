# Retiring `defensives.never`

**Status: approved 2026-09-20.** Supersedes nothing; closes the item
`docs/plans/2026-09-20-defensives-at-a-hit-design.md` §2.2 deferred.

---

## 1. What this answers

`defensives.never` fires once per player per defensive in `data/defensives.toml` that the
player did not cast at any point in the run. It is the largest family the tool produces, and
on a twenty-player raid report it is the majority of the page.

This design retires it. Nothing replaces it, because the claim already appears — word for
word, ability for ability — on the death card of every player it could reasonably be aimed at.

---

## 2. The measurement

Taken 2026-09-20 against the fifteen `out/*.findings.json` files on the development machine
and their rendered HTML. No API quota: every figure comes from reports already built. `out/`
is not tracked, so these numbers are a dated reading rather than something a clean checkout
reproduces; the method is given below so a later reader can take their own.

### 2.1 How much of the page it is

| | findings | `defensives.never` | share |
| --- | ---: | ---: | ---: |
| fifteen reports, summed | 773 | **203** | **26.3%** |

By family, summed across the same fifteen: `defensives.never` 203, `compare` 133,
`consumables` 101, `deaths` 79, `interrupts` 79, `defensives.unused` 44, `players` 42,
`time` 36, `trash` 24, `defensives.ceiling` 15. It is the largest by half again.

The four raid reports carry it worst:

| report | findings | `never` | share |
| --- | ---: | ---: | ---: |
| `cW38jmwdnZfbHVL4` fight 8 | 87 | 52 | **59.8%** |
| `cW38jmwdnZfbHVL4` fight 26 | 79 | 42 | 53.2% |
| `DJfap6RcYKhPGHXZ` fight 7 | 80 | 31 | 38.8% |
| `cW38jmwdnZfbHVL4` fight 30 | 78 | 27 | 34.6% |

### 2.2 How much of it the Deaths tab already says

The death card places every defensive in one of six states at the moment of death, and
`unseen` — rendered as **"not seen this run"** — is the same claim as `defensives.never`. The
card's own wording is run-wide, not per-death, which matters: the surviving row is not a
narrower restatement, it is the identical sentence.

Each `defensives.never` finding was matched against the `unseen` rows on its own player's
death cards, by ability id:

| | count | share |
| --- | ---: | ---: |
| an `unseen` row for **that exact ability**, on that player's death card | **158** | 77.8% |
| player has **no death card at all** | **45** | 22.2% |
| player has a card, ability absent from every row | **0** | — |
| ability present, in some state other than `unseen` | **0** | — |

Both residual buckets are empty across all fifteen reports. The Deaths tab renders `unseen`
501 times over the same set.

The overlap is total exactly where the problem is worst. The four raid reports above resolve
52/52, 42 with 8 no-card, 31/31 and 27/27.

### 2.3 What retirement costs

The 45 findings in the no-card bucket, and nothing else. Every one of them says: *this player
survived the entire run and never pressed this defensive.* That is the weakest ground the
claim stands on — there is no death to point at, the likeliest explanation for not pressing a
defensive on a run you survived is not needing one, and §3 shows the talent ambiguity is not
resolvable either.

They concentrate on Mythic+ reports where few players died, and those files carry three to
six `never` findings each. There is no drowning problem there for the finding to be solving.

### 2.4 Method, and one correction

Counts come from `out/*.findings.json` (`findings[].id`, `findings[].ability_id`, and titles
matching `never cast`) and from the `id="tab-deaths"` section of the matching HTML, where each
`<div class="card">` carries one death, its `<div class="row-head"><h3>` names the dying
player, and each `<li class="STATE">` carries the ability's id in an `i-<id>` icon class.

**The first pass of this measurement was wrong and said 78 / 80 rather than 158 / 0.** A
regex matching `<li class="(state)">.*?class="icon i-(\d+)"` with `DOTALL` ran past the end of
any row that carries no icon and borrowed the next row's ability. 19 of 221 rows in one report
have no icon id. The fix is to match each `<li>...</li>` whole and search inside it. The tell
was a bucket nobody predicted — 80 findings whose ability was supposedly missing from a card
that should list every defensive of that spec. A surprising bucket is a bug before it is a
finding.

---

## 3. Why the obvious repair is unavailable

The finding's own detail text concedes the problem: *"it may have been unavailable, or the
talent may not be taken."* The natural repair is to gate it on the player's real build, so it
only fires on an ability they actually have.

`playerDetails(includeCombatantInfo: true)` does return talent data, and this project already
pays for that call. Read from cached response bodies on 2026-09-20:

- **`combatantInfo.talents` is an empty list on every player observed.**
- **`combatantInfo.talentTree` is populated** — 76 to 79 entries per player, each
  `{"id": int, "rank": int, "nodeID": int}`.

The `id` there is a talent-entry id, not a spell id. One Warrior's read `112121, 112122,
112123, 112125` — consecutive, which spell ids for a spec's talents are not. Mapping those to
the ability ids in `data/defensives.toml` needs a node-to-spell table with no API source
behind it: hand-maintained, per spec, re-verified every patch, roughly 76 entries apiece.
That is precisely what the **no hardcoded season data** invariant exists to prevent, at a
scale that would dwarf `data/season.toml`.

**The talent gate is unavailable.** Recorded here so it is not re-derived.

`talentImportCode` is the same wall by another route: the project fetches it, and
`compare_talents` only ever tests it for equality against another player's. Decoding it needs
the same tree definition.

---

## 4. What the page keeps

- **`data/defensives.toml` is untouched.** It still feeds the ceiling claim,
  `defensives.unused`, and all six death-card states.
- **`defensive_base_ids` stays.** `defensives.ceiling` mints its ids through it.
- **The death card is untouched.** `unseen` and its "not seen this run" detail are the
  surviving form of this claim, and they already read correctly.
- **The `("defensives.", "group_rows")` placement entry stays** in both ledgers.
  `defensives.ceiling` falls through to it.

---

## 5. What changes

| File | Change |
| --- | --- |
| `src/wowperf/domain/analysis/defensives.py` | `analyse_defensives` loses its zero-casts branch and is renamed `analyse_defensive_ceiling`; docstring drops §5.6; the references at `:109` and `:214` follow |
| `src/wowperf/domain/analysis/service.py` `:10,:65`, `encounter_service.py` `:14,:109` | the two call sites follow the rename |
| `src/wowperf/domain/analysis/deaths.py:202` | comment naming `analyse_defensives` follows the rename |
| `src/wowperf/domain/report/finding_tooltip.py` | `DEFENSIVE_FAMILIES` becomes `("defensives.ceiling.",)`; docstring stops saying "two families" |
| `src/wowperf/domain/report/ledger.py`, `raid_ledger.py` | comments stop naming `defensives.never.`; `test_raid_ledger.py:323`'s comment follows the rename |
| `tests/domain/analysis/test_defensives.py` | 16 of its 27 tests are touched — see §5.2 |
| `tests/domain/analysis/test_encounter_service.py:62` | **rewritten, not deleted** — see below |
| `tests/domain/report/test_build_observations.py`, `test_build_placement.py`, `test_ledger.py`, `test_finding_tooltip.py` | their `never` cases go |
| `tests/adapters/render/golden/*` | **unchanged** — see §5.3 |
| `docs/how-it-works.md` | the `defensives.py` row drops "never cast" |
| `.claude/skills/mplus-analysis/SKILL.md` | stops advertising the claim |

### 5.1 Two tests that must be rewritten rather than deleted

`test_a_death_with_unmeasured_cost_disables_the_ceiling_but_not_never_cast`
(`test_defensives.py:316`) asserts two independent things. The half this design removes is the
never-cast half. **The other half is a guard with nothing to do with this work**: a death whose
cost could not be measured must withhold *every* ceiling finding for that player, not only the
one for the ability they pressed. Deleting the test to be rid of its name would silently drop
that guard. It is rewritten to keep the ceiling assertion and renamed to say what is left.

`test_encounter_service.py:62` documents in its own docstring that its fixture's zero casts
are what make the never branch fire, and uses that to assert the encounter service states the
claim once. With the branch gone the fixture proves nothing, so the test is reworked onto a
claim the fixture still supports rather than removed for convenience.

**The rule for the whole task: a test may be deleted only when the behaviour it pins is the
behaviour being removed.** A test that merely mentions `never` is not evidence of that.

### 5.2 The test impact is 16 of 27, not 4

Counted while writing the implementation plan, after this section first claimed four.

`analyse_defensives` is the only entry point `tests/domain/analysis/test_defensives.py` has,
and the never-cast branch is what makes it return anything for the file's Mage fixture. That
fixture is a 100-second run, where Prismatic Barrier's ceiling is 4.0 and a single press
clears the 0.2 fraction: **it produces no ceiling finding for any input.** Four comments in
the file assert the opposite and are wrong.

So nine tests use the retired branch as a *vehicle* while pinning something else — id
slugging, actor disambiguation, ASCII safety, per-player independence — and six of those call
the analyser with no casts at all.

**Four of them would pass vacuously rather than fail** once the branch goes: `all(...)` over
an empty list is `True`, and `len([]) == len(set([]))` is `0 == 0`. They would go green while
pinning nothing.

The plan therefore re-anchors them onto `defensives.ceiling.` **before** the removal, against
a 1800-second fixture where both ceilings (72.0 and 7.5) sit far above one press. That pass is
green-to-green and changes no production code, so the re-anchored assertions are proved
against a tree where they can still fail.

Five tests are deleted, because the behaviour they pin is the behaviour being removed. Two are
rewritten because they assert the ceiling as well.

### 5.3 No golden file changes

`tests/adapters/render/golden/raid.html` carries no `defensives` content at all. Checked with
a positive control — `grep -c 'div'` returns 118 and all seven tab ids are present on the same
file — because a bare zero from `grep` is not trustworthy on this machine, and a zero that
reads as a measurement is how two false statements reached a previous branch.

Do not run `--golden-update` during this work. A failing golden test means something
unplanned happened.

`SKILL.md`'s "never cast it" at line 277 is the **comparison** finding, a different family.
It is not touched.

The rename is not optional tidying. Removing the branch makes the existing name and docstring
false, and this repository's rule is that a change cleans up the orphans it creates.

---

## 6. What would make this wrong

The falsifier, stated before the work runs:

**If retiring it removes anything a reader could not otherwise find, this design is wrong.**
The measurement in §2.2 answers that for 158 of 203 with zero exceptions, and §2.3 concedes
the remaining 45 as a deliberate loss. If a regenerated report turns out to lose a finding
outside the `defensives.never` family, or to lose a `never` claim for a player who *does* have
a death card, the premise is broken and the work stops.

A second one, softer: if a reader of the Deaths tab cannot tell what "not seen this run"
means without the retired finding's detail paragraph beside it, the claim did not survive the
move and the card's wording needs the work instead.

---

## 7. Testing and verification

**The offline gate.** `uv run pytest`, `uv run ruff check .`, `uv run mypy`, each run in the
checkout rather than relayed.

**The removal, measured on real reports.** `CLAUDE.md`'s live-run invariant asks that a new
judgement be exercised against a real log and its state distribution reported. This judgement
is being removed, so the mirror applies: regenerate every cached report and require each to
come back with **exactly `total - never` findings, every other family unchanged count for
count**. The cache is warm, so this costs no quota. A family that moves by even one is §6's
falsifier firing.

**The death card is unchanged, and a test must say so.** The `unseen` count per report must
be identical before and after. Nothing in this work touches `recap.py`, so a change there is
an accident.

### 7.1 What the regeneration measured, 2026-09-21

Eleven of the fifteen cached reports regenerate offline, and all eleven came back clean:
**532 findings before, 349 after, the difference exactly the 183 `defensives.never` claims
they carried**. Every other family held count for count — no family moved by one in either
direction.

What the eleven cover is the part of the corpus this retirement bears on hardest. **All four
raid fights are in, including the one where the family ran to 52 of 87 findings — 59.8% of
the page**, along with seven Mythic+ runs across both commands. Between them they carry
**183 of the corpus's 198 `never` findings**. Regeneration cost 1.00 point per command,
11.00 in total, and every one of those points was the quota reading itself: no report data
left the cache.

**The remaining four cannot be verified by this method at all, at any price.** They were
built with the comparison axis live, and that axis draws a fresh sample of five references
each time it runs. The reference cache expires after a day and its entries are older than
that, so regenerating would refetch and draw a *different* sample: their `compare` counts
would then differ for reasons having nothing to do with this change, and a moved family
would be uninterpretable rather than informative. Spending quota here would not buy a
verification, it would buy a noisier one. The oldest of the four also predates the current
finding-id scheme. Their 133 `compare` findings therefore sit outside the measurement.

That gap is closed by reading the code rather than by measuring it, and is recorded here as
reasoned, not measured. `compare()` is handed the run, the speed sample and the subjects,
never the findings list. `rank_findings` is a pure `sorted()` with no cap or truncation, so
removing a finding cannot admit another — which is also what the eleven show empirically,
every total landing on exactly `total - never`. The caps that do exist under
`domain/comparison/` — `MAX_PACKS_REPORTED`, `MAX_AURAS_REPORTED`, `MAX_SPELLS_REPORTED` —
each slice a comparison-internal collection of packs, auras or candidate rows before any of
it joins the findings list; none of them can see an analysis finding. And nothing under
`domain/comparison/` reads the retired analyser. The comparison family is structurally
insulated from this change.

**The `unseen` counts are identical on all eleven**, checked against a positive control that
counts all four availability states. The control earned its place: two files in the directory
matched no availability row in any state, both predating the current death-card markup, and
their zeros are not measurements. Neither was among the eleven.

**Two counts of one family, and how they reconcile.** §2.2 and §2.3 count 203; this section
counts 198. Both are right, and they measure slightly different things. 203 is the count by
title — every finding making the claim, however its id is spelled. 198 is the count by id
prefix, `defensives.never.*`. The five-finding gap is the oldest report in the corpus, whose
ids predate the family naming and take the form `defensives.<slug>.<ability>`: they make the
same claim under a spelling the prefix test does not catch. **198 + 5 = 203.** Neither figure
supersedes the other, and §2.2's "158 of 203" stands as written; a reader comparing the two
numbers is looking at two ways of counting the same family, not at a correction.

---

## 8. Recorded, not fixed

- **The 45 no-card claims are gone deliberately**, with §2.3's reasoning behind it. Restoring
  them means firing the finding only for players who never died, which keeps exactly the
  subset with the least evidence behind it.
- **The talent ambiguity is unresolved and unresolvable from this API** (§3). It applies
  equally to `defensives.unused` and to the death card's `unseen` state, both of which
  disclose it in their own wording. Neither is in this scope.
- **`defensives.ceiling` fires 15 times across the same fifteen reports** and is untouched
  here. Its `CEILING_USE_FRACTION` was measured once, on one 28-minute dungeon; whether it
  holds on a raid fight has not been asked. Its own piece of work.
- **`out/` is left in a mixed state.** Eleven reports there are post-retirement; the four of
  §7.1 are not, and their pages still render a claim the tool no longer makes. Nothing in the
  repository reads `out/`, and regenerating those four would spend live reference fetches to
  tidy a directory that is not an input to anything. Left as it is, deliberately.
