# Comparing against a sample of references — design

Approved 2026-09-08. This design replaces the one-reference comparison with a sample of
reference runs, so a claim means what most fast runs did rather than what one stranger did.

It amends `docs/plans/2026-09-03-mplus-postmortem-design.md` §6, which remains the authority on
everything it does not touch. Two research documents are its evidence and are not restated here:

- `docs/plans/2026-09-08-sampling-decision-brief.md` — the arguments, finding by finding.
- `docs/plans/2026-09-08-sampling-quota-measurement.md` — what a reference costs, measured.

Where this design disagrees with either, this document wins and says why.

---

## 1. What changes, in one paragraph

A single reference makes a claim of the form *"the reference did X"*, which a reader is invited to
generalise and which may be one stranger's idiosyncrasy. A sample makes a claim of the form
*"4 of 5 fast runs did X"*, which generalises honestly and which filters idiosyncrasy out by
construction. That filtering is the product, not the extra precision. It matters most where a
single reference is most likely to be weird: a pet talent build, a gear proc nobody else owns, one
group's unusual route choice.

## 2. Decisions taken, and why

Four questions were settled in the brainstorm on 2026-09-08. They are recorded here so the next
session does not relitigate them.

**Five speed references and five parse references.** The measurement recommended sampling only the
speed side, reasoning that "the top parse of your specialisation" is a claim about an exemplar. The
brief contradicts it: `compare.spells.missing.*` — "k of n top parses cast this and you never did"
— is the second strongest case for the whole feature, and it lives on the parse axis. Sampling also
removes the uptime finding's worst caveat, again on the parse axis. Five is the smallest N at which
one unusual reference cannot carry a finding alone, and at which the floor in §3 leaves room to
lose a member that fails to load. The one thing that genuinely needs a single named player is the
talent import string, and that keeps pointing at the top-ranked member.

**References are linked, not tabulated.** Provenance keeps each candidate's report code, fight and
URL, plus whether it loaded and why not. Per-run durations, death counts and character names are
not written to the findings JSON or the HTML. The 24-hour reference cache was built so that other
players' runs do not accumulate; the output walked around it, because `out/` has no expiry and at
five references per axis every kept report would name ten strangers and their numbers forever. A
link still reaches everything a reader needs to audit a claim. A name written into a file is
greppable and poolable; a link is a pointer.

**The reference cache stays shared, and says so.** Keying it per analysed run was considered and
rejected: quota no longer forbids it, but the same reference fetched under several keys is several
copies, so per-run keying holds *more* of other people's logs on disk at once, not less. It buys a
posture rather than a smaller footprint. What was actually wrong was that the reuse was invisible,
in a report that otherwise discloses every candidate it considered. Provenance now records that a
reference was served from cache and when it was fetched.

**Composition is counted, not prescribed.** §6.6 of the approved design declares confounds rather
than correcting for them. Under a sample, "the two groups were not the same composition" sharpens
into "4 of 5 fast runs brought an Augmentation Evoker; your group did not". That stays in the
confounds section, carries no seconds and no suggestion. The report states what was true of the
sample and stops.

---

## 3. The sample

### Selection

A deterministic prefix of the nearest bracket's leaderboard page, in the leaderboard's own order.
The rule is fixed before the data is seen, which is the property that makes this a sample rather
than a cherry-pick: cherry-picking is choosing after looking. **If the selection rule ever grows a
knob that reads the analysed run's own numbers, that property is gone.**

One leaderboard page holds 44 speed rows and 82 parse rows (measured 2026-09-08), so filling five
never costs a second query.

The sample is the fastest N and not a cross-section, and the report says so. Five
top-of-leaderboard runs are the extreme tail; they may agree with each other for reasons that have
nothing to do with what this player should do. "4 of the 5 fastest recorded runs skipped this pack"
is honest. "Most groups skip this pack" is not, and would be the same number.

### Exclusions

Two, both applied before a candidate is loaded:

1. **Our own report and fight**, as today.
2. **Our own characters, by name.** At N=1 the odds of drawing the analysed player's own other run
   were negligible. At N=5 they are not, and "the fast runs did this" is a small lie if one of them
   is you.

### Filling, and mixed brackets

`WclRankingRepository._levels_to_try` returns `(L, L-1, L+1)` and `assert_bracket` guarantees each
returned page holds exactly one keystone level, so today's candidate pool is already homogeneous.

The new rule: fill from the first bracket that answers; if it cannot supply five members that load,
widen to the next bracket in that order and keep filling. Prefer a homogeneous sample; widen only
to reach the floor.

A mixed sample is allowed, and eligibility is then decided **per finding, never up front**.
Filtering the whole sample down to same-level members would discard runs that are fully valid for
route, deaths, downtime and interrupts — the comparisons §6.4 explicitly says survive a level gap.
Deleting a +15 reference from a +16 analysis would throw away good evidence to protect a rule that
was only ever about durations.

Three eligibility subsets, each computed once and carried on the sample:

| Subset | Rule | Used by |
| --- | --- | --- |
| duration-eligible | `Comparability.durations_comparable` — the member's keystone level equals ours | completion time, downtime, the timeline |
| route-eligible | the member's `Alignment.matched_share >= MIN_ALIGNED_SHARE` (0.5) | skipped packs, extra packs, route summary |
| aura-eligible | the member returned aura data | buff uptime |

`matched_share` is a property of a *pair* of routes, so it is never averaged. It gates membership
and nothing else. A member below the threshold contributes nothing to the skipped-pack counts and
still contributes to downtime, deaths and interrupts. This is the first place one section carries
different denominators on different rows, and that is intended.

### `MAX_LEVEL_GAP` becomes the rule it describes

`MAX_LEVEL_GAP = 1` in `comparison/reference.py` is imported by two tests and by nothing in `src/`.
The rule is really the three-element tuple in `_levels_to_try`, and the constant's docstring
explains reasoning the constant does not enforce. Sampling cuts straight through that seam, so
`_levels_to_try` derives its levels from the constant: our own level first, then `L - gap` and
`L + gap` for each gap from 1 up to `MAX_LEVEL_GAP`. At `MAX_LEVEL_GAP = 1` this reproduces today's
`(L, L-1, L+1)` exactly, including the order.

### Failures are disclosed, not swallowed

`_references` in `cli.py` currently takes the first row that loads and skips a failure with a bare
`except (IngestError, WclError): continue`. That is fine at N=1, where the cost of a failure is
"use the next row". Under a sample it silently changes a denominator, which turns a designed sample
into a convenience sample wearing its clothes.

Every candidate considered is recorded: report code, fight, keystone level, URL, whether it loaded,
and the reason if it did not. That record is what makes the difference between "the five fastest
runs" and "five runs that happened to load".

### The floor is three

Below three eligible references for a given finding, no aggregate is computed. The finding falls
back to today's single-reference wording, names that one run, and says the sample was too small.
A median of two is a mean of two, and "1 of 2" is noise dressed as a statistic.

This is what degrades gracefully at high keys and in unpopular dungeons — exactly where the
leaderboard will not fill a sample. With no eligible reference at all, today's `*.unavailable`
finding is unchanged.

---

## 4. What each reference fetches

`WclRunRepository.load_reference` already stops before the four streams no comparison reads —
damage taken, enemy deaths, healing and resurrections. The remaining problem is that the two axes
need different subsets and both get the union: a speed member fetches its cast stream, 3.16 MB and
the largest single stream a reference carries, which only `compare_spells` reads on the parse side;
a parse member fetches deaths, enemy casts and interrupts, which only `compare_tempo` reads on the
speed side.

**Two load profiles.** A speed member fetches what route, tempo and confounds read. A parse member
fetches what spells, talents and uptime read. The exact query set for each is pinned in the
implementation plan by reading what each comparison touches, not by arithmetic in this document;
the measurement's own tier table is the starting point, and its parse figure is known to include
kick-tier queries the parse side does not read.

Measured, a fully usable speed member costs 6.01 points and 0.30 MB, against 14.5 points and
4.80 MB today. Projected for this design:

| | Points | Disk | Cold latency |
| --- | --- | --- | --- |
| Today, one reference each side | 57.1 | 16.4 MB | ~12 s |
| Five and five, untrimmed | 181 | 48 MB | ~50 s |
| **Five and five, trimmed** | **~111** | **~19 MB** | **~40 s** |

Three percent of the hourly budget, and less of other people's data on disk than a single
untrimmed analysis holds today. Quota is not the constraint at any N this design contemplates;
latency is the number a user will notice.

### Absence must not read as fact

A skipped stream comes back as an empty tuple, which reads exactly like "this run had none".
`load_reference`'s docstring says so and asks the reader not to rely on it. With two profiles that
hazard doubles, and a comparison that began reading an unfetched stream would report absence as
fact, silently, with a `measured` badge on it.

The fix makes it a type error rather than a warning. `SpeedReference` and `ParseReference` already
wrap `row + loaded`; each exposes only the streams its axis may read, and the comparison modules
take the member rather than the raw `LoadedRun`. mypy is in the gate, so `compare_tempo` reaching
for a parse member's interrupts stops being a code-review question. No new load types and no
runtime checks: the wrapper that already exists does the work.

---

## 5. Aggregation semantics

**The shape of the aggregate follows the shape of the claim, and every aggregate states its
denominator.**

| Claim | Statistic |
| --- | --- |
| Binary, about one of **our** packs (skipped) | Count with denominator: "4 of 5" |
| Counts per run (deaths, pull count) | Median with the observed range |
| Durations (completion time, downtime) | Median with range; `seconds_lost` = ours − median |
| Rates and shares (casts per minute, kick share, aura uptime) | Median of per-run values |
| Composition | Per-spec presence counts |
| Affixes | Count sharing our set |

Four rules carry the reasoning:

- **Never a percentage.** At N=5, "80%" invents precision the sample does not have.
- **Never the minimum.** Taking the fastest member is today's single-best-run behaviour with extra
  steps, and it maximises the number on the page — the exact bias this tool exists not to have.
- **Median of per-run values, never the pooled ratio.** Pooling weights by run length, so a long
  run dominates a rate that was supposed to describe a player. One reference, one observation.
- **Every median states its range.** A median of five with a 200-second spread and one with a
  20-second spread must not read identically.

**Five things are never averaged**, listed so nobody reaches for one later: composition (there is
no mean roster), talent build (no mean build), pull order (no mean route), keystone level (the mean
of a +15 and a +16 is not a key that exists), and `matched_share` (a property of a pair).

---

## 6. Badges, denominators, and the narrative

### The badge rule

A **count over an enumerated sample** stays `measured`, provided the denominator is on the face of
the claim. Every one of those five logs either contains the pack or does not; nothing about the
count rests on an assumption. A **central-tendency statistic** standing in for "what a fast run
does" is `derived`, because the choice of sample and statistic is a modelling choice that could be
wrong. Anything with an `inferred` component stays `inferred`.

The alternative — one rule, everything `derived` — was rejected. Sampling strictly improves the
evidence, and that rule would downgrade every comparison finding on the day it got better. A reader
who has learned that `measured` means "trust it" would watch the whole section drop a rung. That is
badge inflation running backwards, and it costs the badge its discriminating power exactly where
the reader needs it.

### The denominator goes in the title, and a test enforces it

`.claude/skills/mplus-analysis/SKILL.md` line 232 tells the narrative writer to echo a finding's
title, and the report's Summary renders pointers as titles. A denominator buried in `evidence` would
be dropped by both paths, and a `measured` badge on a count whose denominator went missing is the
exact failure the badge system exists to prevent. This is enforced by a test, not by a convention.

### The narrative quantifier

Putting digits in titles collides with an invariant: `analyze --narrative` refuses a narrative file
containing any digit, before it fetches anything. So the narrative cannot echo an aggregate
finding's title, which is the one instruction the skill gives it for pointing at a finding.

Two non-answers were rejected. Dropping the quantifier gives "the fast runs skipped that pack",
which reads as *all* of them — an overclaim built out of a rule meant to prevent overclaiming.
Letting the narrative pick "most" is the LLM reading a number and stating a conclusion from it,
with no guardrail able to catch a wrong word.

**Tested Python emits the word.** `Finding` gains `quantifier: str = ""`, populated only by
aggregate findings and written into the findings JSON. The mapping over k of n:

| Condition | Word |
| --- | --- |
| `k == n` | `every` |
| `k * 2 > n` | `most` |
| `k * 2 == n` | `about half` |
| `k * 2 < n` | `some` |

`k == 0` does not arise: a finding with no supporting reference is not emitted.

`mplus-analysis/SKILL.md` gains a rule that the narrative may use only the quantifier the findings
file supplied, for the finding it supplied it for. The invariant then holds literally: Python
computes, the narrative echoes.

The word does not change a finding's badge. It renders a count that is already on the page by a
fixed documented rule; it introduces no new claim.

---

## 7. Finding by finding

| Finding | Under a sample |
| --- | --- |
| `compare.route.skipped.*` | Count in the title; price unchanged |
| `compare.route.summary` / `.unaligned` | Our pull count against the sample's range, plus how many aligned well enough to price a skip |
| `compare.route.extra.*` | Unchanged — pairwise against one named member |
| `compare.route.order` | Removed |
| `compare.downtime` | Median; the `seconds_lost` anchor moves |
| `compare.deaths` | Median with range, from the leaderboard rows |
| `compare.interrupts` | Median of per-run kick shares |
| `compare.duration` | Median; breaks a documented invariant, see below |
| `compare.confound.item_level` | Ours against the median of the members' group means |
| `compare.confound.composition` | Per-spec presence counts, no advice |
| `compare.confound.augmentation` | Count of member rosters that contained one |
| `compare.confound.affixes` | Count sharing our set |
| `compare.confound.keystone_level` | Restated over the sample: how many were at a different level |
| `compare.spells.missing.*` | Count in the title |
| `compare.spells.rate.*` | Median of per-run rates |
| `compare.talents` | Unchanged — single reference |
| `compare.uptime.*` | Median of per-run fractions |
| `compare.*.unavailable` | Partial states land on the rows, not the section |

Six need their reasoning on the record.

**`compare.route.skipped.*` is the strongest case for the feature, and the price does not move.**
The seconds come from *our* pull (`seconds_lost=pull.duration_seconds` in `route.py`), so a sample
cannot change them. What changes is the warrant: "the reference skipped this pack" becomes "4 of 5
fast runs never pulled it". Same number, much better claim. Aggregation is easy because the pack is
keyed by **our** pull index, which every pairwise alignment already produces.

**`compare.route.extra.*` stays pairwise for a reason, not from laziness.** An extra pack is one of
*theirs*, and two references' pull 7 are not the same pack. The signature exists — `_types(pull)`
is a frozenset of enemy game IDs — but `align_pulls` deliberately matches by *containment* rather
than signature equality, documented 2026-09-06. Grouping extra packs across references therefore
needs a clustering rule, not a dict key. That is real new surface for the weaker of the two route
findings, and it carries no seconds.

**`compare.route.order` is removed.** Five pairwise reorder diffs is five sets of pull-index pairs no
reader will read. The only aggregate worth printing is whether the references agree with *each
other*, which is a different claim from the one the finding makes today, and the finding's own text
already concedes that reordering is "usually a different path through the dungeon rather than a
mistake".

**`compare.duration` breaks the containment claim, and the fix is one deliberate pass.**
`mplus-analysis/SKILL.md` and the findings file's own `findings_are_ranked_not_additive` warning
both state that this figure is the total gap against the reference run, and that it already
contains every other `seconds_lost` in the file. Against a median that is no longer exactly true:
the total gap is measured against one quantity while the component losses were priced against
particular runs' routes. The warning text, the skill section, and the test that holds the
"Already counted inside …" label set in step with it are all rewritten together. This is the
largest single piece of collateral in the change.

**`compare.spells.rate.*` restates its threshold.** `MIN_CASTS_TO_COMPARE = 3` exists because the
reference's own sample is too small to argue from. With a sample the better form of the same idea
is "the ability appeared in at least three of the eligible members", and the per-run threshold is
kept alongside it so a single member's stray cast still cannot found a rate.

**`compare.talents` stays single-reference.** The only meaningful aggregate is the mode, and that
requires two players with the same build to produce byte-identical import strings. Nobody here
knows whether that is true, and this project does not guess encodings. The row names the
top-ranked member and says in its text that it is one player's build.

**Partial availability lands on the rows.** "2 of 5 references had no aura data" is a per-finding
fact. `SectionState` keeps `PRESENT` and `WITHHELD` and gains no `PARTIAL`, because `Section.reason`
is documented as quoted verbatim from a single `compare.*.unavailable` finding and a partial
section has no single finding to quote.

---

## 8. Types and wiring

**`comparison/reference.py`.** `SpeedSample` and `ParseSample` frozen values, each holding its
members and the eligibility subsets from §3. `Comparability` is unchanged: it is a correct two-run
value, one is built per member, and the sample collects the eligible subset above it. The sample
logic does not belong inside it.

**`comparison/service.py`.** `compare(ours, our_player, speed: SpeedSample | None,
parse: ParseSample | None, our_auras)`. Everything else follows from that signature.

**`report/build.py`.** `_section_for(...)` and the `build_report` signature follow the samples.
`build_timeline` currently calls `align_pulls` a second time — already recorded as cosmetic
duplication. With five members that is five alignments computed twice, so alignments are computed
once and passed.

**The timeline keeps one track, and its gating bug is fixed here.** `build_timeline` is gated only
on a speed reference existing, not on `Comparability`, so across a keystone gap the report withholds
the reference's durations as numbers and then draws them as a picture. Today that is one
inconsistency; under a sample it becomes "which of five gets drawn". The track shows the
best-aligned duration-eligible member, `TimelineTrack.caption` names it and says it is one of N, and
no track is drawn when no member is duration-eligible.

**`LedgerRow` needs no change, and that is the headline.** The denominator goes in `title`, which
§6 requires anyway; the per-reference breakdown goes in `evidence`, already a `tuple[str, ...]`. The
ledger, the Summary pointers, the route rows, the death rows and the player cards absorb a sample
without a type change. Rendering "4 of 5" as a visual would need integers rather than prose, but a
nullable pair of ints on a type used by five sections is not free and waits until the UI work asks.

**`Provenance` is where the real change lands.** `speed_reference_url` and `parse_reference_url`
become a sequence of a small frozen record per candidate *considered*: report code, fight, keystone
level, URL, whether it loaded, the reason if not, and whether it was served from cache and when it
was fetched. `withheld: tuple[str, ...]` keeps its present job; the per-finding exclusions would
swamp it and belong on the findings.

### One consequence of the persistence decision

Reference character names currently reach finding text — `spells.py:99` and `uptime.py:97`
interpolate them, and `cli.py:369` writes one into the findings JSON. Most vanish on their own when
those findings become medians. The exception is the talent row, which stays single-reference: it
refers to "the top-ranked parse" and carries its URL rather than naming the player. The build string
you copy is unaffected.

### Collateral

- The findings-JSON `comparison` block in `cli.py`.
- `mplus-analysis/SKILL.md`: the containment claim, the confounds section, "Reading the file", and
  the new quantifier rule. This skill is how the narrative gets written, so a stale version means
  the LLM narrates a sample as if it were one run.
- The test holding the "Already counted inside …" label set in step with the warning.
- `tests/adapters/render/golden/minimal.html`.

---

## 9. Testing

All three levels, per the repository's no-exceptions policy.

**Unit.** Each comparison module over synthetic samples: counts, medians and their ranges, the floor
at three, each eligibility subset, and the never-average list. Every new assertion is
mutation-checked, as this repository does.

Two tests carry unusual weight:

- **Every aggregate finding's title carries its denominator.** §6 made the denominator load-bearing
  for the badge, so a test pins it rather than a convention.
- **The query set per load profile.** A fake client records what was asked and the test asserts a
  speed member issues the speed profile's queries and never a cast query. The trim is where the cost
  is, and nothing else would notice it regressing: every other test runs off fixtures that do not
  care what was fetched.

**Integration.** `compare()` through `build_report()` over a sample fixture: partial availability on
the rows, the floor falling back to single-reference wording, and the timeline withheld when no
member is duration-eligible.

**End to end.** A real sampled analysis against the live API, marked `e2e`, costing about 111
points of 3600.

**And the plan ends with a live run, not a green gate.** On this project every plan's worst defects
have survived the offline suite and appeared on the first real run. The last task renders
`https://www.warcraftlogs.com/reports/6Kx1P9GbNXrcLdHa?fight=36` and reads the page.

---

## 10. Risks

- **Latency, not quota.** Roughly 40 seconds cold against 12 today. That is the number a user
  notices; the points are invisible.
- **A leaderboard that cannot fill five.** Handled by the floor in §3, and tested with a two-member
  sample rather than left to a high-key run to discover.
- **The measurement's soft spots stand.** One dungeon, one bracket, one page. No candidate was ever
  observed failing to load, so the cost of a failed candidate is a floor of 2.01 points rather than
  a measurement.
- **Two denominators on one page.** If it turns out readers cannot track them, the fallback is a
  single homogeneous sample with one denominator, which is strictly simpler than what this design
  builds. The direction is therefore low-risk to take first.

---

## 11. Out of scope, with reasons

- **Composition-matched selection.** The most interesting second iteration, and the one that attacks
  the largest declared confound directly. It needs a similarity metric with no ground truth, it may
  be unsatisfiable at five specific specs in one bracket and one dungeon, and it would *hide* the
  finding "every fast run brought a class you did not" — which §2 has just decided is worth printing.
- **A cross-run pack key** for extra packs (§7).
- **Talent aggregation**, which needs an encoding fact this project will not guess. It would be
  settled by checking the encoding against a verified source and recording a dated row in
  `.claude/skills/wcl-api/SKILL.md`, or by observing two known-identical builds in real data.
- **Sampling deeper in the leaderboard.** A cross-section answers "am I typical"; this tool asks
  "what did the fast groups do differently". Softening the reference would make the findings
  unactionable.
- **The report's UI rewrite** and the deep-link scroll defect, both documented and both waiting on
  this work.
