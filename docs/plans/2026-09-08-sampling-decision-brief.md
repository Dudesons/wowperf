# Comparing against a sample of references — decision brief

**This document is input to a brainstorming session. It decides nothing, approves nothing, and
authorises no code.** Its only job is to put the arguments and the evidence on the table before
that session starts.

Written 2026-09-08, against `master` at `7af17b1`.

---

## Changed since this was written

The reference loader was partly trimmed on 2026-09-08, after this brief and the companion
measurement were finished. `WclRunRepository.load_reference` now stops before the four streams no
comparison reads — damage taken, enemy deaths, healing and resurrections — which the measurement
priced at 8.5 of a reference's 14.5 points and 4.5 of its 4.8 MB. The findings for the run this
project is built against are byte-identical before and after.

**One further split was identified and deliberately deferred to this design.** The two references
need different subsets, and `load_reference` currently hands both the union: a speed reference
still fetches its casts, which only `compare_spells` reads and only on the parse side, and a parse
reference still fetches deaths, enemy casts and interrupts, which only `compare_tempo` reads and
only on the speed side. Splitting is worth about four points and three megabytes per compared
analysis today, and roughly five times that once a sample of speed references each skips its own
cast stream — the largest single stream a reference carries.

It was left undone because this design decides the shape of reference loading, and doing it twice
is waste. Whatever this design settles on should settle that with it. The disk figure matters to
§7 as well as to cost: the less of another player's log that reaches disk, the smaller the
question §7 is asking.

## What I read

- `docs/plans/2026-09-03-mplus-postmortem-design.md` — §3.3 caching, §6.1–6.7 comparison.
- `src/wowperf/domain/comparison/` in full: `reference.py`, `alignment.py`, `route.py`,
  `tempo.py`, `spells.py`, `uptime.py`, `confounds.py`, `service.py`.
- `src/wowperf/domain/report/model.py` and the reference wiring in `report/build.py`.
- `src/wowperf/cli.py` (`_references`, `build_reference_repositories`, the findings JSON block),
  `src/wowperf/adapters/wcl/ranking_repository.py`, `rankings.py`, `repository.py`.
- `.claude/skills/mplus-analysis/SKILL.md`.
- The 2026-09-06 handoff, section "A sample of references instead of one".

I did not measure API cost. A separate agent is doing that live; every place cost bears on a
recommendation below says **pending the quota measurement** and states which way the answer
would push.

---

## 1. What the code does today, stated precisely

Worth having in front of you, because three of the questions below turn on details that are not
in the design document.

**Selection.** `WclRankingRepository.fastest_runs` and `top_parses` try brackets in the order
`(L, L-1, L+1)` — `_levels_to_try` — and return **the whole first page that has any rows**.
`assert_bracket` then guarantees every row on that page is at that one keystone level. So the
candidate pool is already level-homogeneous: today's "gap of at most one" is a property of which
bracket answered, not a per-row filter.

`_references` in `cli.py` then walks that page and takes **the first row that loads**, skipping
our own run and skipping any row whose report fails to load, silently:

```python
        try:
            loaded = runs.load(row.report_code, row.fight_id)
        except (IngestError, WclError):
            continue
```

**The named constant for the gap rule is dead code.** `MAX_LEVEL_GAP = 1` in
`comparison/reference.py` is imported by two tests and by nothing in `src/`. The rule is actually
enforced by the three-element tuple in `_levels_to_try`. Any sampling design will touch exactly
this seam, so it should fix or delete the constant rather than inherit the confusion.

**The gap rule itself.** `Comparability` in `src/wowperf/domain/comparison/reference.py`:

```python
    @property
    def durations_comparable(self) -> bool:
        return self.level_gap == 0

    def withheld_because(self) -> str:
        """The sentence a reader gets in place of a number we refuse to print."""
        return (
            f"The reference is a +{self.their_level} and this run is a +{self.our_level}. "
            "Enemy health scales about 10% a keystone level and compounds, so pull "
            "durations and kill times are not comparable and are not shown."
        )
```

and `MAX_LEVEL_GAP`'s docstring, which states the reasoning the constant no longer enforces:

```python
MAX_LEVEL_GAP = 1
"""A reference further than this from our keystone level is not offered at all.

Two levels of enemy health is roughly a fifth more, which changes which packs a
group can hold together, not merely how long each one takes.
"""
```

**What the rule actually gates, in code, is two findings and nothing else.** In `tempo.py`,
`compare.duration` becomes "Completion times are not compared" with `seconds_lost=None`; in
`confounds.py`, `compare.confound.keystone_level` appears. Route, downtime, deaths and interrupts
are computed unconditionally. That is not a hole: the other comparisons are built so no
reference-side duration ever reaches the page. A skipped pack is priced with **our** pull's
duration (`seconds_lost=pull.duration_seconds` on our pull, `route.py`), and an extra pack
deliberately carries no seconds at all — "we have no clock for a pull we never did."

**One exception, which the sampling design will have to face.** The aligned timeline is *not*
gated by comparability. `build_timeline` in `report/build.py` is gated only on
`speed is not None`, and it draws the reference's pull blocks on a shared seconds scale with a
caption reading "Reference — mm:ss from first pull to last". So across a keystone gap the report
withholds the reference's durations as numbers and draws them as a picture. Today that is one
inconsistency; with a sample it becomes a question about which of N runs gets drawn.

**Cost shape, from `WclRunRepository.load` (`adapters/wcl/repository.py:211`).** A reference is a
full run load: the report query, talents, affix names, abilities, actor game IDs, then paginated
event streams for casts, deaths, enemy casts, interrupts, enemy deaths, damage taken and
resurrects, plus a healing window per death. But `build_run(report, fight, talents)` runs
**before any event query**, and it already yields the roster, item levels, affixes, keystone
level, the pull sequence and each pull's enemy types. Which means:

| What a finding needs from a reference | Where it comes from |
| --- | --- |
| completion time, death count, medal, team | the leaderboard row itself — **already fetched, free** |
| route alignment, skipped/extra packs, downtime, composition, item level, affixes | the report + fight query — **no event stream** |
| kicked/landed casts | two event streams |
| casts per minute on bosses | one event stream |
| buff uptime | one aura table per reference player |

That decomposition is the biggest lever in this whole brief, and §5 and the cost note return to
it.

---

## 2. Question 1 — what each finding becomes when the reference is a distribution

### The general shape

Two things change, and only one of them is the number. A single reference makes a claim of the
form *"the reference did X"*, which a reader is invited to generalise and which may be one
stranger's idiosyncrasy. A sample makes a claim of the form *"k of n fast runs did X"*, which
generalises honestly and which **filters idiosyncrasy out by construction**. That filtering is
the actual product here, not the extra precision. It matters most where a single reference is
most likely to be weird: a pet talent build, a gear proc nobody else owns, one group's unusual
route choice.

Finding by finding.

### Speed axis

**`compare.route.skipped.*` — the strongest case for the whole feature.** Note what does *not*
change: the price. The seconds come from our own pull, so a sample cannot move them. What the
sample changes is the claim attached to the price: "the reference skipped this pack" (one
stranger) becomes "4 of 6 fast runs never pulled this pack" (a route consensus). Same number,
much better warrant. Aggregation is easy because the pack is keyed by **our** pull index, which
every pairwise alignment already produces. Recommend: aggregate, and make the count the headline.

**`compare.route.extra.*` — aggregates badly, and needs a key it does not have.** An extra pack is
one of *theirs*, identified by their pull index in their report. Two references' pull 7 are not
the same pack. To say "3 of 6 fast runs pulled something you skipped" you need a pack identity
stable across reference runs, and the only candidate is the set of enemy game IDs
(`alignment._types`). That is a new concept: today's alignment is strictly pairwise and never
needs a global pack key. Recommend: either introduce the signature key deliberately and accept it
as new surface, or leave the extra-pack finding pairwise against one named reference. I lean to
the latter for a first pass — it is the weaker of the two route findings and carries no seconds.

**`compare.route.summary` and `compare.route.unaligned`.** `matched_share` is a property of a
*pair* of routes, not of a run, so it must never be averaged. It becomes a per-reference
eligibility gate: any reference below `MIN_ALIGNED_SHARE` (0.5) contributes nothing to the
skipped/extra counts but still contributes to downtime, deaths and interrupts. The summary
becomes "we pulled 14 packs; the six fast runs pulled 11 to 13" plus "4 of 6 aligned well enough
to price a skipped pack". Note this is the first place where the denominator differs per finding
inside one section.

**`compare.route.order` — I would drop it or demote it.** Reordering is a pairwise diff against
one route. Against six routes you get six different diffs, and the only aggregate worth printing
is whether *the references agree with each other* — which is a new computation (do the six share
a canonical order?) and a different claim from the one the finding makes today. Its current text
already concedes it is "usually a different path through the dungeon rather than a mistake". Cost
of dropping it: near zero. Cost of keeping it naively: six sets of pull-index pairs on the page,
which no reader will read.

**`compare.downtime`.** Survives cleanly — the finding's own detail says travel time "does not
depend on how much health a mob had". Becomes ours against the sample median, with the range
stated. The `seconds_lost` anchor moves from "one fast run" to "the median fast run", which will
change the ledger ranking and the Summary pointers. That is a behaviour change worth calling out
in the design, not a bug.

**`compare.deaths`.** Survives, and is nearly free: `SpeedRow.deaths` comes off the leaderboard
row. A death distribution over the whole page costs nothing beyond the query already made.

**`compare.interrupts`.** Survives as a median of per-run kick *shares*. Do not pool the counts —
see §5. Costs two event streams per reference, so it is on the expensive tier.

**`compare.duration`.** Survives as ours against the median, and this is where the sample most
changes what the reader is told: "you were 90s off the fastest run in the bracket" and "you were
90s off the median of the six fastest" are different sentences and the second is far more useful.
**But it breaks a documented invariant.** `mplus-analysis/SKILL.md` and the findings file's own
`findings_are_ranked_not_additive` both state that `compare.duration` "is the total gap against
the reference run… that figure already contains every other `seconds_lost` in the file". Against a
median that containment claim is no longer exactly true: the total gap is measured against one
quantity and the component losses were priced against particular runs' routes. The warning, the
skill section, and the test that holds the label set in step with it all need rewriting. This is
the largest piece of collateral in the brief.

**`compare.confound.*`.**

- *augmentation* — becomes "k of n reference rosters contained one". It only bites where the
  report uses a reference's **per-player** numbers, which is the parse axis, not the speed axis.
  Our own roster's Aug is the case that matters most and is unaffected.
- *item_level* — becomes ours against the median of the sample's group means. Fine.
- *composition* — this one *improves into a finding*. "The two groups were not the same
  composition" (a shrug) becomes "5 of 6 fast runs brought a class your group did not" (actionable
  and, arguably, the most valuable single thing a sample can say). **Flag for the brainstorm:**
  §6.6 deliberately declares composition rather than correcting for it, and a count like that
  edges toward prescription — "bring an Augmentation Evoker". Whether that crosses the design's
  own line is a judgement call, not a technical one.
- *affixes* — becomes "k of n ran your affix set". Modest improvement, free.
- *keystone_level* — see question 3.

### Parse axis

**`compare.spells.missing.*` — the second strongest case for the feature.** "The top parse cast
Ability X and you never did" is exactly the claim a single reference is worst at: one player's
build. "5 of 6 top parses cast it" is a build consensus. Recommend: aggregate, count in the title.

**`compare.spells.rate.*`.** Median of per-run casts-per-minute, ours against it.
`MIN_CASTS_TO_COMPARE = 3` ("the reference's own sample is too small to argue from") should
probably be restated in sample terms — "appeared in at least k of n references" is a better
threshold than "3 casts in one run" once you have a sample, and it is the same idea.

**`compare.talents` — does not survive, and I recommend leaving it single-reference.** Today it is
binary on the import string and prints theirs for copy-paste. Six strings are useless to a reader,
and the only meaningful aggregate is the **mode** — which requires that two players with the same
build produce byte-identical strings. **I do not know whether that is true and I am not going to
guess it**; it is the kind of encoding detail this project's rules forbid inventing. If it is not
true, aggregating talents needs a decoder, which is a whole subsystem for one row.
Recommend: keep the talent row against the single top-ranked parse, and say in its text that it is
one player's build.

**`compare.uptime.*`.** Survives as a median of per-run fractions, and the sample **fixes its
worst caveat**. The finding today has to warn that a gap "can also mean a different item of the
same kind, or gear this player does not own", because `onSelf` carries no source filter and picks
up teammate buffs, consumables and procs. A one-off proc will not reach 5 of 6; the sample filters
exactly the noise that caveat was written for. That is a real, specific improvement, not a
generality.

**The `compare.*.unavailable` findings.** Today binary. With a sample they become partial —
"2 of 6 references had no aura data" — and the report needs a shape for that. See question 7.

### Summary table

| Finding | Under a sample |
| --- | --- |
| `compare.route.skipped.*` | **Best case.** Count of references that skipped it; price unchanged (our clock) |
| `compare.route.extra.*` | Needs a cross-run pack key it does not have. Keep pairwise, or introduce the key deliberately |
| `compare.route.summary` / `.unaligned` | Per-reference eligibility gate; `matched_share` must never be averaged |
| `compare.route.order` | Degrades. Drop, or restate as "do the references agree with each other" |
| `compare.downtime` | Median; ranking anchor moves |
| `compare.deaths` | Free from leaderboard rows |
| `compare.interrupts` | Median of per-run ratios; expensive tier |
| `compare.duration` | Median; **breaks the documented containment claim** |
| `compare.confound.composition` | Becomes a finding rather than a caveat — and edges toward prescription |
| `compare.confound.*` (others) | Counts and medians, straightforward |
| `compare.spells.missing.*` | **Second best case.** Build consensus instead of one build |
| `compare.spells.rate.*` | Median; rethink `MIN_CASTS_TO_COMPARE` as "k of n" |
| `compare.talents` | **Does not survive.** Keep single-reference |
| `compare.uptime.*` | Median, and the sample *fixes* the finding's own worst caveat |

**Cost of being wrong on the "does not survive" calls:** small and reversible. Dropping route-order
and keeping talents single-reference are both one-row decisions that can be revisited without
touching the sampling machinery.

---

## 3. Question 2 — what badge an aggregate carries, and how N reaches the reader

### The badge

The project's own definitions (`domain/findings.py`):

> `MEASURED` read from the log, or plain arithmetic over logged facts and dated constants,
> needing no assumption that could be wrong
> `DERIVED` reconstructed by a documented rule, or computed with a modelling choice that could be
> wrong
> `INFERRED` requires an assumption the log cannot confirm

**Option A — every aggregate is `derived`.** One rule, conservative, easy to test. Rationale: the
sample's membership is a modelling choice that could be wrong.

**Option B — it depends on the shape of the statistic.** A **count over an enumerated sample**
("4 of 6 fast runs never pulled this pack") stays `measured` provided the denominator is on the
face of the claim: every one of those six logs either contains the pack or does not, and nothing
about the count rests on an assumption. A **central-tendency statistic** standing in for "what a
fast run does" — median, mean, rate — is `derived`, because the choice of sample and statistic is
a modelling choice that can be wrong. Anything with an `inferred` component stays `inferred`.

**Recommendation: B**, on this principle — *the badge answers "how much does this claim rest on an
assumption that could be wrong", and the assumption in an aggregate lives in the generalisation,
not in the arithmetic. A count that carries its own denominator makes no generalisation. A median
does.*

**Cost of being wrong with A** is the perverse one, and it is why I would not take A despite its
simplicity: sampling strictly improves the evidence, and A would strictly downgrade the badge on
every comparison finding. A reader who has learned that `measured` means "trust it" would see the
entire comparison section drop a rung on the day it got better. That is badge inflation running
backwards, and it costs the badge its discriminating power exactly where the reader needs it.

**Cost of being wrong with B** is two rules where one would do, and a reader who does not notice
that "4 of 6" and "the median of 6" are differently warranted. Mitigated by the fact that the two
read differently on the page anyway.

**A constraint on B that must be enforced, not merely intended:** the denominator has to be *in
the title*. `mplus-analysis/SKILL.md` tells the narrative writer to echo titles, and the report's
Summary renders pointers as titles. A denominator buried in `evidence` would be dropped by both
paths, and a `measured` badge on a count whose denominator went missing is the exact failure this
badge system exists to prevent.

### How the sample size reaches the reader

Three requirements, and one sharp edge.

1. **Per finding, never per section.** The eligible sample shrinks differently for different
   findings (question 3), so a single "sample of 6" banner at the top of the comparison section
   would be a lie for any finding that used four.
2. **In the title, for the reason above.**
3. **A floor, below which you do not aggregate.** "1 of 2" is noise wearing a statistic's clothes,
   and a median of two is a mean of two. Suggested rule, for the brainstorm to argue with: with
   fewer than **three** eligible references for a given finding, fall back to today's
   single-reference wording naming that one run, and say the sample was too small. That is honest
   and it degrades gracefully at high keys and in unpopular dungeons, which is exactly where the
   leaderboard will not fill a sample.

**The sharp edge: the digit ban.** `analyze --narrative` refuses a narrative file containing any
digit. So the sample size cannot reach the reader through the narrative at all — it reaches them
only through the page and the findings JSON. The narrative will therefore reach for quantifiers:
"most of the fast runs skipped that pack". But "most" *is* a reading of 4-of-6, and a bad reading
of 3-of-6. Under the "LLM never computes a number" invariant, an unconstrained quantifier is a
computation with the digits filed off. Worth deciding in the brainstorm: either the finding titles
carry the quantifier so the narrative only ever echoes ("4 of 6" appears on the page; the narrative
says "the fast runs that skipped it"), or `mplus-analysis/SKILL.md` gets an explicit rule about
quantifier words over a sample. I lean to the first — it needs no new guardrail — but this is a
genuine new hole in an invariant the project takes seriously, and it should be closed deliberately.

---

## 4. Question 3 — the mixed sample and the gap rule

### The setup is better than it looks

Because `assert_bracket` guarantees a returned page holds exactly one keystone level, **today's
candidate pool is already homogeneous**. A mixed sample only arises if the design deliberately
unions brackets to reach N. So the first question is not "how do we handle a mixed sample" but
"do we want one at all".

**Option A — one bracket only.** Take N from whichever of `(L, L-1, L+1)` answers first. The gap
rule then applies once, to the whole sample, exactly as today: durations either compare or they do
not, and no finding has a different denominator for gap reasons. Simplest by a distance, and it
changes nothing about `Comparability`.
*Risk:* at a high key or in an unpopular dungeon one bracket may not hold N loadable rows, and you
are back to a small sample or a fallback.

**Option B — union all three brackets, filter per finding.** Biggest sample. Duration-shaped
findings use only the same-level members; everything else uses all of them. Every finding then
carries its own denominator.
*Risk:* two sample sizes live on one page and the reader must track which is which.

**Option C — fill from the same level first, widen only if short.** Mechanically A when the
leaderboard is rich and B when it is thin.

**Recommendation: C in mechanism, B in language.** Prefer a homogeneous sample; widen only to
reach the floor; and once the sample is mixed, speak per-finding denominators, because that is the
only honest description of what happened.

### Shrink per finding, do not filter up front

This one I will argue firmly. Filtering the whole sample down to same-level references discards
runs that are *fully valid* for route, deaths, interrupts and downtime — the comparisons §6.4
explicitly says survive a level gap. Deleting a +15 reference from a +16 analysis would throw away
good evidence to protect a rule that was only ever about durations. **The sample is one set; each
finding declares which subset it used.**

### What the report says about references it dropped

Three different kinds of "dropped", and merging them would be the mistake:

1. **Never offered** — more than one level away, so never in the pool. Invisible, correctly.
2. **In the sample, ineligible for this finding** — the level gap. Must be stated on the finding,
   with `withheld_because()` generalised from "The reference is a +N" to a sentence about how many
   of the sample were at a different level.
3. **Fetched and failed to load** — deleted, private, unfinished, roster gap. Today
   `_references` swallows this with a bare `continue`, and that is fine when the cost of a failure
   is "use the next row". **Under a sample it silently changes a denominator.** A statistic whose
   sample size quietly shrank because two reports were private is a convenience sample presented
   as a designed one. Recommend: provenance lists every candidate considered, whether it loaded,
   and why not. It is cheap, and it is the difference between "the six fastest runs" and "six runs
   that happened to load".

**Cost of being wrong on the per-finding shrink:** if it turns out readers cannot track varying
denominators, the fallback is A — one homogeneous sample, one denominator — and that fallback is
strictly simpler, so this is a low-risk direction to take first.

---

## 5. Question 4 — how the sample is selected, and what makes it defensible

### Options

**A. Top N by the leaderboard's own metric, at the nearest bracket.** The current rule, taking
more rows. Speed leaderboard for the group axis, playerscore for the individual axis.

**B. A band around our keystone level.** Already implemented — the bracket *is* the band, and
`_levels_to_try` is already the band's width.

**C. A cross-section rather than the top.** Sample from deeper in the leaderboard, or across
pages, to get runs "like ours".

**D. Composition-matched.** Prefer references whose roster resembles ours.

### Recommendation: A, at the nearest bracket, with disclosure

Take the leaderboard's first page in its own order, skip our own run, take the first N that load.

**And say plainly, in the report, that the sample is the fastest N and not a cross-section.**
Because that is what it is. Six top-of-leaderboard runs are the extreme tail; they may agree with
each other for reasons that have nothing to do with what our player should do (same meta
composition, same route video, same week). Sampling the tail does not make it representative — it
makes it *a consensus of the tail*, which is a perfectly good thing to compare against as long as
the sentence on the page says so. "4 of the 6 fastest recorded runs skipped this pack" is honest.
"Most groups skip this pack" is not, and would be the same number.

### What makes it defensible rather than cherry-picked

Two properties, and neither of them is representativeness:

1. **The rule is fixed before the data is seen.** A deterministic prefix of a leaderboard cannot
   cherry-pick, because cherry-picking is choosing *after* looking. If the selection rule ever
   grows a knob that reads the analysed run's own numbers, that property is gone.
2. **Every candidate is disclosed** — including the ones that failed to load, per question 3.

### Fairness to the player being analysed

Two concrete points, one of which is a small bug today.

- **C is not more fair, it is a different question.** Comparing against median-speed runs answers
  "am I typical", and this tool asks "what did the fast groups do differently". Softening the
  reference to be kind would make the findings unactionable, and it would cost real quota to fetch
  slower runs deeper in the leaderboard.
- **D is the most interesting second iteration and I would not do it first.** Composition matching
  attacks the largest declared confound directly, and "fair to the player" has real teeth there —
  being told you were slower than a group with an Augmentation Evoker you did not have is not
  useful. But it needs a similarity metric with no ground truth, it may be unsatisfiable (five
  specific specs, one dungeon, one bracket), and the fairness argument cuts both ways: matching
  composition also *hides* the finding "every fast run brought a class you did not". Worth an
  explicit "not now, and here is why" in the design.
- **Exclude our own players, not just our own report.** `_references` skips the exact
  report-and-fight. With one reference the odds of drawing the analysed character's own other run
  are negligible; with six they are not, and "the fast runs did X" is a small lie if one of them is
  the same player. Cheap to check by character name.

### Cost bearing on this

N is the whole cost question. **Pending the quota measurement.** If N reference runs at full load
are comfortable against the hourly budget, take A at N of five or six on both axes. If they are
not, §7's two-tier fetch is the answer and N stops being one number — see the cost note.

---

## 6. Question 5 — aggregation semantics

The rule I would propose: **the shape of the aggregate follows the shape of the claim, and every
aggregate states its denominator.**

| Claim shape | Statistic | Why |
| --- | --- | --- |
| Binary per reference, about one of **our** packs (skipped) | **Count with denominator**: "4 of 6" | Keyed by our pull index; every reference either did it or did not. Never a percentage — with N=6 a percentage invents precision |
| Binary per reference, about one of **their** packs (extra) | Count — **only if** a cross-run pack key exists | Otherwise do not aggregate (question 1) |
| Counts per run (deaths, pull count) | **Median + observed range** | Leaderboard tails are skewed; one 6-death disaster drags a mean |
| Durations (completion time, downtime) | **Median + range**; `seconds_lost` = ours − median | Never the minimum: that is the old single-best-run behaviour with extra steps, and it maximises the number on the page — the exact bias the tool exists to avoid |
| Rates and shares (casts/min, kick share, aura uptime) | **Median of per-run values**, not the pooled ratio | Pooling weights by run length: a long run dominates a rate that was supposed to describe a player. One reference, one observation |
| Talent import strings | **Mode**, and only if identical builds encode identically — unverified | See question 1 |
| Composition | **Per-spec presence counts** ("5 of 6 brought a Priest") | A "median composition" has no referent |
| Affixes | **Count sharing our set** | Not an average |

**Where an average is meaningless — worth listing explicitly in the design so nobody reaches for
one:**

- **Composition.** There is no mean roster.
- **Talent build.** There is no mean build.
- **Pull order.** There is no mean route. (This is the real reason `compare.route.order` degrades.)
- **Keystone level.** The mean of a +15 and a +16 is not a key that exists.
- **`matched_share`.** It is a property of a *pair* of routes. Averaging six pairwise alignment
  qualities produces a number about nothing.

**Three cross-cutting rules:**
- Every aggregate states its denominator, in the title (question 2).
- Every median states its range. A median of 6 with a 200-second spread and a median of 6 with a
  20-second spread should not read identically.
- No median below three eligible references (question 2's floor).

**Cost of being wrong:** the median-versus-mean choice is cheap to revisit; the count-versus-median
choice per finding is the one that would be expensive to change later, because it is baked into
each finding's title text and the tests that pin those titles.

---

## 7. Question 6 — the no-corpus invariant

CLAUDE.md states the rule as:

> **Never accumulate a corpus of other players' logs.** RPGLogs terms §5d prohibit it.
> Reference runs are fetched for one comparison and cached locally, never warehoused.

I am reasoning only from that sentence and from the repo's own recorded design (§3.3 as amended
2026-09-06: leaderboard rows and reference responses go to a second cache directory whose entries
expire after twenty-four hours and are deleted on the next start). **I have not read, fetched or
interpreted the actual terms, and nothing below should be read as a claim about what they say.**
Four design choices push against the stated line, in increasing order of how much they worry me.

**1. Sample size.** The stated rule is about accumulating a corpus, not about how many runs one
comparison reads. Six runs fetched for one comparison and expired is, on the letter of the
sentence, the same kind of act as two. But the *framing* changes even when the retention does not:
a distribution is closer in spirit to a dataset than a single comparison is. The retention story is
unchanged by N; the characterisation story is not. Someone has to decide whether that distinction
matters, and CLAUDE.md does not settle it.

**2. Cache retention.** Today's 24-hour window is justified in §3.3 by one specific need: serving
the narrative re-run that `analyzing-a-run` relies on. Under a sample the same window holds N times
as many other players' reports at once. Two sub-questions: does that justification still cover a
store N times larger, and should the reference cache instead be dropped at the end of the command
with an explicit opt-in to keep it? Sampling makes the second option easier to argue for and more
expensive to adopt — a re-run would refetch N runs. That tension between quota and retention
posture did not exist at N=2.

**3. Reuse across analyses.** The sharpest of the four. The reference cache is keyed by query, not
by the analysed run, so a second analysis of a *different* run in the same dungeon within the
window is served the same references. Functionally that is a small standing reference set, even
though every entry expires. It is invisible, and today it is a feature. Under sampling it becomes
the mechanism by which something corpus-shaped could accumulate without anyone deciding to build
one. The options a human has to choose between:
   - (a) keep the shared window and accept that consecutive analyses share references;
   - (b) key the reference cache to the analysed run so it is never reused — costs quota, **pending
     the quota measurement**;
   - (c) keep reuse but make it visible: provenance says "served from cache, fetched at T".

   I recommend (c) unconditionally, because visibility is defensible on plain technical grounds. I
   am deliberately not recommending between (a) and (b) — that turns on the reading of a document
   I have not read and am not going to interpret.

**4. What outlives the cache — and this is the one that is easiest to miss, because it is not the
cache.** The findings JSON already names both references by report code, keystone level, duration
and character name (`cli.py`, the `comparison` block). That file is written to `out/` and the user
keeps it forever. With a sample, six other players' runs — their codes, their times, their death
counts, their per-run numbers — persist in a file with no expiry at all, long after the cached
responses are gone. The whole 24-hour cache tier was built for exactly this concern and this path
walks around it. Three options: name the references but not their per-run figures; name nothing and
keep only the aggregate; keep everything as today. **The HTML report has the same property**, via
`Provenance.speed_reference_url` and `parse_reference_url`.

**What a human needs to read and decide.** Read §5d, and record the decision the way this repo
already records verified API facts — in the design, with a date and the reasoning, so the next
session does not relitigate it. The four questions above are the ones whose answers depend on that
reading. My own line: I can argue the engineering of every one of them, and I can make none of
them for you.

---

## 8. Question 7 — what changes in the view model

Naming the actual types in `src/wowperf/domain/report/model.py`. This is a sketch of structural
consequences, not a UI design — a separate brief covers the UI.

**`LedgerRow` needs no change, and that is the headline.** It carries
`finding_id, title, detail, badge, seconds, nests_inside, evidence`. Every aggregate claim fits:
the denominator goes in `title` (which question 2 requires anyway), the per-reference breakdown
goes in `evidence`, which is already a `tuple[str, ...]`. So the ledger, the Summary pointers, the
route rows, the death rows and the player cards all absorb a sample without a type change. The
sampling feature does not have to touch most of the report.

*The exception, if the UI brief asks for it:* rendering "4 of 6" as a visual (a dot strip, a
fraction bar) needs numbers, not prose. That would mean either two fields on `LedgerRow`
(`sample_size: int | None`, `sample_matches: int | None`) or a small `SampleShare` frozen value
hung off it. Recommend adding nothing until the UI brief asks — a nullable pair of ints on a type
used by five sections is not free.

**`Provenance` is where the real change lands.**

```python
class Provenance(Frozen):
    report_code: str
    fight_id: int
    fetched_at: str
    speed_reference_url: str | None = None
    parse_reference_url: str | None = None
    withheld: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
```

Two scalar URLs become sequences. Question 3 wants more than URLs: a small frozen
`ReferenceRef`-style value per candidate carrying the report code, fight, keystone level, URL,
whether it loaded, and — if not — why. That is the record that turns a convenience sample into a
disclosed one. `withheld: tuple[str, ...]` could carry the per-finding exclusions as strings, but
it would swamp a field currently holding three lines; better a separate structured list.

**`Section` — I recommend *not* adding a state.**

```python
class SectionState(StrEnum):
    PRESENT = "present"
    WITHHELD = "withheld"
```

The tempting move is a third `PARTIAL`. I would resist it: eligibility is per finding, so a
section-level "partial" would summarise something that varies row by row, and `Section.reason` is
documented as being quoted verbatim from the `compare.*.unavailable` finding — there is no single
finding to quote for a partial section. The denominator belongs on the rows. `SectionState` stays
as it is.

**`Timeline` is the one place the model genuinely cannot absorb a sample.**

```python
class Timeline(Frozen):
    section: Section
    ours: TimelineTrack | None = None
    theirs: TimelineTrack | None = None
```

`build_timeline(ours: Run, theirs: Run | None, section: Section)` takes exactly one reference run.
N references means either `theirs: tuple[TimelineTrack, ...]` — cheap to type, unreadable past
three tracks — or one chosen reference. Recommend: **one reference track, the best-aligned member
of the sample**, with `TimelineTrack.caption` (already free text) saying which run it is and that
it is one of N. Costs nothing structurally. And it forces the decision noted in §1: the timeline is
not gated by `Comparability`, so if the chosen track can be at a different keystone level, the
picture is showing durations the findings refuse to print.

**Domain types upstream of the report** — this is where the interface change actually starts:

- `comparison/reference.py`: `SpeedReference` and `ParseReference` become collections, or gain a
  `SpeedSample` / `ParseSample` wrapper holding the members plus the per-finding eligibility.
- `comparison/service.py`: `compare(ours, our_player, speed, parse, our_auras)` takes samples.
  Everything else follows from this signature.
- `Comparability(our_level, their_level)` **stays pairwise** — one per member — with something
  above it collecting the eligible subset. Do not generalise `Comparability` itself; it is correct
  as a two-run value and the sample logic does not belong inside it.
- `report/build.py`: `_section_for(findings, SPEED_UNAVAILABLE_ID, speed is not None)` and the
  `build_report` signature. Note also that `build_timeline` calls `align_pulls` a **second** time
  (the handoff already lists this duplication as a known minor); with N references that becomes N
  alignments computed twice, so the duplication stops being cosmetic.

**Collateral outside the view model**, so the brainstorm can price it:

- `cli.py`'s findings-JSON `comparison` block: `speed_reference` / `parse_reference` singular
  objects, plus the question-6 decision about what persists there.
- `mplus-analysis/SKILL.md`: "Findings are ranked, never summed" (the `compare.duration`
  containment claim), the whole "confounds the comparison declares" section, and "Reading the
  file". This skill is how the narrative gets written, so a stale version means the LLM narrates a
  sample as if it were one run.
- The test that holds the "Already counted inside …" label set in step with the
  `findings_are_ranked_not_additive` warning.

---

## 9. Cost — what is pending, and how it swings the recommendations

A separate agent is measuring N reference runs live. I have not measured and will not guess.

What I can state without measuring, from `WclRunRepository.load`, is the **cost shape**: a full
reference load issues the report query, talents, affix names, abilities and actor IDs, then seven
paginated event streams plus a healing window per death. But `build_run` runs before any event
query, so the roster, item levels, affixes, pull sequence and each pull's enemy types are available
from the report and fight queries alone. That yields two tiers:

- **Cheap tier** (leaderboard row + report/fight query, no event stream): completion time, death
  count, composition, item level, affixes, **the full route alignment and the skipped-pack
  counts**, and downtime.
- **Expensive tier** (event streams / aura tables): kicked-and-landed casts, casts per minute,
  buff uptime.

The two highest-value aggregates in this whole brief — "k of n fast runs skipped this pack" and
the group-shape confounds — are on the cheap tier. That is a fortunate arrangement and it should
shape the design regardless of what the measurement says.

**How the measurement swings things:**

- **If N full reference loads are comfortable** against the hourly budget: take the simple path —
  one sample, N of five or six, full load for every member, one denominator per finding. No
  two-tier machinery, no extra concepts.
- **If they are expensive**: go two-tier. Take a large N on the cheap tier (the leaderboard page is
  already fetched, so deaths and completion times are free at any N) and a small N — one or two —
  on the expensive tier, with the report stating different denominators for different findings.
  Question 3 already requires per-finding denominators, so this costs no new concept; it costs the
  reader some attention.
- **If they are expensive *and* the reference cache is keyed per analysed run** (question 6's
  option b): the two paths compound and N on the expensive tier probably has to be one — which is
  today's behaviour, and the honest conclusion would be that sampling lands on the cheap tier only.

---

## 10. What I could not call, and what would settle it

1. **Whether talent builds can be aggregated at all.** Turns on whether two players with the same
   build produce byte-identical import strings. *Settled by:* checking the encoding against a
   verified source and recording a dated row in `wcl-api/SKILL.md`, or by observing two known-
   identical builds in real data. Until then, keep the talent row single-reference.
2. **Whether "5 of 6 fast runs brought a class you did not" crosses §6.6's own line** between
   declaring a confound and prescribing a fix. *Settled by:* your judgement about what this tool is
   for. It is a values question wearing a statistics costume.
3. **Cache reuse across analyses — (a) shared window versus (b) per-run keying.** *Settled by:* a
   human reading §5d, plus the pending quota measurement. My recommendation of (c), disclosure, is
   independent of that and can be adopted either way.
4. **N.** *Settled by:* the quota measurement, then a judgement about question 6's framing concern.
5. **Whether the timeline should show one reference or several.** I recommend one, but that is a
   readability judgement and the separate UI brief owns it. The model consequence is stated above
   either way.

---

## 11. If I had to name the shape I would argue for

Not a recommendation to adopt — a starting position for the brainstorm to attack:

- One sample per axis, drawn as a deterministic prefix of the nearest bracket's leaderboard page,
  our own run and our own characters excluded, every candidate disclosed in provenance including
  the ones that failed to load.
- The sample is one set; each finding names the subset it used and why the rest were excluded.
- Counts with visible denominators where the claim is binary; medians with ranges where it is not;
  nothing aggregated below three eligible references.
- Counts stay `measured` when the denominator is in the title; medians are `derived`.
- Skipped packs, deaths, downtime, completion time, composition and the missing-spell finding get
  the sample. Talents stay single-reference. Route order goes away.
- The timeline keeps one reference track and says which.
- The `compare.duration` containment claim gets rewritten everywhere it appears, deliberately and
  in one pass.
