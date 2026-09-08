# What a sample of N reference runs costs — measurement

**This document measures. It designs nothing and approves nothing.** It is the live counterpart to
`docs/plans/2026-09-08-sampling-decision-brief.md`, which states at its head that "a separate agent
is doing that live" and marks every recommendation that turns on cost as *pending the quota
measurement*. This is that measurement.

Measured 2026-09-08 against report `6Kx1P9GbNXrcLdHa` fight 36 — Den of Nalorakk +16, 1909 s
keystone time, 5 players, 12 pulls, 4 deaths — and against three real reference runs drawn from the
same speed leaderboard. Nothing under `src/` or `tests/` was touched, and the repository's own
`cache/` was left alone: the measurement scripts and their caches live in this session's scratch
directory, outside the repository. Those caches hold about 14 MB of three strangers' logs and should
be deleted — the sandbox refused the removal, so it needs a human hand or the temp directory's own
cleanup.

**Total spend: 160.74 points of 3600.** The hour opened at 38.26 already spent and closed at 199.00,
leaving 3401. The instruction to stop below 3000 remaining never came close to binding, so nothing
here is truncated.

**Correction, 2026-09-08, later the same day.** Per-query instrumentation landed after this was
written and settled how a reading relates to its query: a reading reports the spend *before* that
query is billed. Under that convention §2's cross-check had charged two quota reads to a figure
that can hold only one, so its residual is **15.30**, not the 14.30 first written, and §1's method
subtracts the *opening* read rather than the closing one. Nothing measured changes. §3's fixed
subtotal in particular stands at 23.06: the two reads really do cost the hour two points, even
though a single before/after difference can never see the second. See "Every query reports its own
cost" in `.claude/skills/wcl-api/SKILL.md`.

---

## 1. Method, and what is measured versus extrapolated

Every figure below is a difference between two `rateLimitData` readings taken either side of a
single query, with the 1.00-point cost of the opening read subtracted. **A `rateLimitData` query
costs exactly 1.00 point**: three consecutive reads gave deltas of 1.00 and 1.00 (2026-09-08),
confirming the figure the `wcl-api` skill already carries. A reading reports the spend before its
own query is billed, so the opening read's point falls inside the difference and the closing
read's falls outside: one read to subtract, never two.

Four fetches, in order, each into a cache that was cold for everything it needed:

| Step | What | Spend |
| --- | --- | --- |
| 1 | Three quota reads, to price a quota read | 3.00 |
| 2 | One cold `wowperf analyze`, end to end, into a fresh cache | 41.38 |
| 3 | Reference `71cv4MRdNCp8ZFjG` fight 28, priced query by query, into step 2's cache | 13.58 + 16 reads |
| 4 | Reference `37FzMg9pVPH6fnJT` fight 16, same | 15.70 + 15 reads |
| 5 | The analysed run, both leaderboards and our own aura table, cold, priced query by query | 23.08 + 22 reads |

Steps 3 and 4 reuse step 2's cache deliberately: the leaderboards and the affix table are already
paid for there, so what those steps price is exactly the **marginal** cost of one more reference.

**Measured:** every per-query figure, the two per-reference totals, the fixed half, the leaderboard
page sizes, and every cache size in megabytes.

**Extrapolated:** the projections for N = 3, 5 and 10 — arithmetic over the measured per-reference
figure, not observation. And the per-reference figure itself is a mean of three references that were
all +16 Den of Nalorakk runs of 1357–1399 s with 5 players and 12 pulls, which is a narrow sample:
see §8.

**The three steps' arithmetic reconciles exactly.** Step 3's start reading equals step 2's end plus
one read; step 4's equals step 3's end; step 5's equals step 4's end. One 6.00-point discrepancy
appeared later, between step 5's closing read and a read taken a few minutes afterwards with no
queries in between; a 45-second idle probe then showed no drift at all (198.00 → 199.00, exactly one
read). I cannot explain those 6 points and will not pretend to. They fall outside every figure
below, and every step reconciles internally, so the conclusions stand — but if this repeats, the
suspect is another process sharing the same client credentials.

---

## 2. What one reference run costs, query by query

`WclRunRepository.load` is the whole of it. Priced against two references, with the analysed run
alongside for comparison. All three are +16 runs of the same dungeon.

| Query | Analysed run (1909 s, 4 deaths) | `71cv…` (1379 s, 0 deaths) | `37Fz…` (1399 s, 2 deaths) | Payload |
| --- | --- | --- | --- | --- |
| `Fights` | 2.01 | 2.01 | 2.01 | 0.06 MB |
| `Talents` | 2.05 | 2.05 | 2.05 | <0.01 MB |
| `Affixes` | 1.00 | — cached — | — cached — | <0.01 MB |
| `Abilities` | 1.00 | 1.00 | 1.00 | 0.13 MB |
| `Casts` | 1.00 × 2 pages | 1.00 | 1.00 | 3.16 MB |
| `Deaths` | 1.00 | 1.00 | 1.00 | <0.01 MB |
| `EnemyCasts` | 1.00 | 1.00 | 1.00 | 0.09 MB |
| `Interrupts` | 1.00 | 1.00 | 1.00 | 0.02 MB |
| `EnemyDeaths` | 1.00 | 1.00 | 1.00 | 0.03 MB |
| `DamageTaken` | 1.00 | 1.52 | 1.22 | 1.34 MB |
| `Resurrects` | 1.00 | 1.00 | 1.00 | <0.01 MB |
| `Actors` | 1.00 | 1.00 | 1.00 | 0.02 MB |
| `Healing` | 1.00 × 4 windows | — none — | 1.42 + 1.00 | <0.01 MB |
| **Total** | **19.06** (17 queries) | **13.58** (11 queries) | **15.70** (13 queries) | |
| Cache written | 6.39 MB | 4.86 MB | 4.73 MB | |

Payload sizes are from `71cv…`; they vary by a few percent between runs.

What the shape says:

- **Almost every query costs a flat 1.00.** `Casts` returns 7975 rows and 3.16 MB for 1.00. Volume
  is nearly free; **queries are what cost**. The only exceptions measured are `Fights` at 2.01,
  `Talents` at 2.05, the aura table at 2.00, and `DamageTaken`, which drifted between 1.00 and 1.52
  across three runs with no pattern I can name from three samples.
- **Deaths are the only term that scales.** Each merged run-up window is one `Healing` query at
  1.00–1.42. A reference with no deaths pays none. The speed leaderboard's first ten rows carried
  0, 1, 2, 2, 0, 0, 0, 6, 1, 0 deaths, so a fast run typically adds 0–2 points here.
- **Pagination is not a factor for references.** Our 1909-second run paged `Casts` twice
  (10000 + 716 rows, limit 10000); the 1357–1399-second references paged once at ~7400–8000 rows.
  Fast runs are short by definition, so a reference will nearly always be one page per stream.

**The marginal cost of one additional reference run, cold: 14.5 points**, taking the mean of 13.58
and 15.70, with 13.58 as the floor for a deathless reference. A reference used on the *parse* side
also needs its aura table, measured at **2.00**, so 16.5.

A third, independent check falls out of step 2. The full cold analysis cost 41.38 as the command
reports it, of which 19.06 was the analysed run, 2.02 the two leaderboards, 2.00 our aura table,
2.00 the reference's aura table and 1.00 the command's own quota reads — two reads costing a point
each, but only the opening one falling inside a before/after difference. The residual — the
reference's own load, including its one-off affix re-fetch — is **15.30**, which sits between the
two directly measured figures, though near the top of that range rather than in the middle of it.

---

## 3. The fixed half — what every analysis pays whatever N is

| Item | Points |
| --- | --- |
| The analysed run, loaded cold (17 queries) | 19.06 |
| Our own player's aura table | 2.00 |
| The two quota reads `analyze` makes itself | 2.00 |
| **Fixed subtotal** | **23.06** |
| `FightRankings`, page 1 | 1.01 |
| `CharacterRankings`, page 1 | 1.01 |
| `Affixes`, re-fetched into the references cache | 1.00 |
| **Shared-across-references subtotal** | **3.02** |

Both subtotals are points the hour actually loses, the two quota reads included at a point each.
A single before/after difference reports one less, which is why §2's cross-check divides 41.38 and
not 42.38.

A same-day re-run costs **2.00** — the two quota reads and nothing else — because the main cache is
permanent and the references cache holds for 24 hours. The command prints 1.00 for such a run,
measured on a fully warm cache, for the same reason. The narrative re-run the `analyzing-a-run`
skill relies on is therefore free at any N.

---

## 4. What is shared, and what only looks shared

Question 3 of the brief asked whether the dungeon's encounter data, the ability table and the affix
table are paid once. Measured, the answer splits:

**Paid once, whatever N (measured):**

- **Both leaderboard pages, 2.02 total.** One `FightRankings` page returned **44 rows, 44 distinct
  report codes**; one `CharacterRankings` page returned **82 rows, 82 distinct report codes**. So
  every N up to 44 on the speed side and 82 on the parse side is served by the page already bought.
  The dungeon's encounter identity travels on that same query. Sampling does not add a leaderboard
  query until N exceeds 44.
- **The completion time, death count, medal and team of every candidate**, which ride on the
  leaderboard row. Free at any N, already in `SpeedRow`.
- **The affix table, 1.00.** Argument-free and game-wide. Note it is paid **twice per analysis** —
  once into the main cache and once into `cache/references`, because `build_reference_repositories`
  hands the references a separate `DiskCache` directory. Once, not N times, so it does not grow with
  N; but it is a point that a shared cache directory would save.

**Not shared, contrary to the guess in the task:**

- **The ability table is per report, 1.00 each.** `ABILITIES_QUERY` takes a report code and returns
  that report's own ability names. Every reference pays it.
- So are `Fights` (2.01), `Actors` (1.00) and `Talents` (2.05). All three are keyed by report code,
  and the leaderboard gave 44 distinct report codes for 44 rows, so in practice no two references
  ever share them.

**Net effect of sharing as N grows:** the shared block is a flat 3.02 points. It is 5% of the bill
at N = 1 and 1.6% at N = 10. Sharing does not meaningfully shrink the marginal cost — the marginal
cost is dominated by per-report queries that cannot be shared. Anyone hoping N would get cheaper per
unit should let that hope go: **the curve is linear.**

---

## 5. Projected cost by N

Two shapes, because "N references" is ambiguous in the brief and the two diverge to nearly a factor
of two by N = 10.

`cost = 23.06 fixed + 3.02 shared + 14.5 per speed reference + 16.5 per parse reference`

**Shape A — N speed references, one parse reference** (the route/tempo claim becomes a
distribution; the exemplar parse stays an exemplar):

| N | Points | Share of 3600 | Analyses per hour |
| --- | --- | --- | --- |
| 1 | 57.1 | 1.6% | 63 |
| 3 | 86.1 | 2.4% | 41 |
| 5 | 115.1 | 3.2% | 31 |
| 10 | 187.6 | 5.2% | 19 |

**Shape B — N of each:**

| N | Points | Share of 3600 | Analyses per hour |
| --- | --- | --- | --- |
| 1 | 57.1 | 1.6% | 63 |
| 3 | 119.1 | 3.3% | 30 |
| 5 | 181.1 | 5.0% | 19 |
| 10 | 336.1 | 9.3% | 10 |

**Today's actual measurement was 41.38, not 57.1**, and the reason matters. The two also differ by
a point in basis: 41.38 is what the command printed, while the projections count both quota reads,
so today's run cost the hour 42.38. On this run the speed leaderboard's first loadable row and the
parse leaderboard's first loadable row named **the same report and the same fight**
(`6L2XcjtJyRZkfYFb` fight 3), so the second reference was a cache hit
and cost only its aura table. Today's N = 1 is therefore 42.38 when the two coincide and 57.1 when
they do not. Both are real; the brief should quote 57.1 as the baseline, because a sample makes the
coincidence vanishingly unlikely.

This also explains the gap against the 44.29 the `wcl-api` skill records for 2026-09-07. Re-measured
today the same command cost 41.38 — same report, same fight, cold cache, the figure as the command
reports it. The 2.91 difference is a different reference run: leaderboards move daily, and a
reference with one more death or a heavier damage stream moves the total by exactly that order. The
skill's figure was not wrong; it was a measurement of a different reference.

### The headline

**Quota is not the constraint.** Shape B at N = 10 — ten fast runs and ten top parses, the most
extravagant reading of the feature — costs 9.3% of one hour's budget and still allows ten analyses
an hour. A human running this tool a few times a day will never see the ceiling. The real limits on
N are the ones the brief already names in §6 and §10: the terms-of-service posture on how many
strangers' logs one analysis pulls, the reader's ability to track a denominator, and wall-clock
latency.

**Latency, for scale:** step 2's 36 queries took 12.1 s end to end, about 0.34 s per query. Shape B
at N = 5 is roughly 145 queries, so about 50 seconds on a cold cache. That is the number likely to
annoy someone, not the point count.

---

## 6. Local cache growth

Measured on disk, one JSON file per query, as `DiskCache` writes them.

| Item | Size | Entries | Lifetime |
| --- | --- | --- | --- |
| The analysed run + its aura table | 6.57 MB | 18 | permanent |
| Both leaderboard pages | 0.09 MB | 2 | 24 hours |
| The affix table in the references cache | <0.01 MB | 1 | 24 hours |
| One reference run, full load | 4.73–4.86 MB | 11–13 | 24 hours |
| One aura table | 0.10 MB | 1 | 24 hours |

Of a reference's 4.8 MB, **3.16 MB is the cast stream and 1.34 MB the damage-taken stream** — 93%
of the bytes in two files.

Projected, using 4.80 MB per reference:

| N | Shape A | Shape B |
| --- | --- | --- |
| 1 | 16.4 MB | 16.4 MB |
| 3 | 26.0 MB | 35.8 MB |
| 5 | 35.6 MB | 55.2 MB |
| 10 | 59.6 MB | 103.7 MB |

For scale, the repository's working `cache/` directory stands at 31 MB today. The reference half
expires after 24 hours, so these are peaks within a day of work, not accumulation — which is the
distinction §5d turns on, and the number a human will want when judging where the line is: **at
shape B, N = 10, one analysis holds about 97 MB of other players' logs on disk for a day.** At
shape A, N = 5, it holds 29 MB. That is the sentence to argue about.

---

## 7. The lever: a reference load fetches five streams no comparison reads

This is the biggest finding here and it bears directly on the brief's §1 and §9 two-tier proposal,
which guessed at this decomposition from the code. Measured, the guess is right and the prize is
larger than the brief supposed.

Grepping every field of a reference's `LoadedRun` that the comparison layer actually reads:
`run`, `casts`, `deaths`, `enemy_cast_rows` and `interrupts`. **Never** `damage_taken`,
`enemy_deaths`, `healing`, `resurrections` or `health_samples` — those exist for our own run's
analysers and death cards.

Pricing the split, per reference:

| Tier | Queries | Points | Cache |
| --- | --- | --- | --- |
| **Cheap** — route, skipped/extra packs, downtime, composition, item level, affixes | `Fights` | **2.01** | 0.06 MB |
| **+ kicked/landed and death count** | `Abilities`, `Deaths`, `EnemyCasts`, `Interrupts` | **+4.00** | +0.24 MB |
| **+ casts per minute and talents** (parse side) | `Casts`, `Talents` | **+3.05** | +3.16 MB |
| **+ buff uptime** (parse side) | `AuraTable` | **+2.00** | +0.10 MB |
| **Waste on a speed reference** — fetched, never read | `Casts`, `Talents`, `DamageTaken`, `EnemyDeaths`, `Actors`, `Resurrects`, `Healing`×deaths | **8.5** (7.57 and 9.69 measured) | 4.4–4.6 MB |
| **Waste on a parse reference** | `DamageTaken`, `EnemyDeaths`, `Actors`, `Resurrects`, `Healing`×deaths | **4.5–6.6** (4.52 and 6.64 measured) | 1.39 MB |

So a speed reference the comparison can fully use costs **6.01 points and 0.30 MB**, against the
14.5 points and 4.80 MB it costs today. A parse reference costs **11.06 points and 3.56 MB**.

Rerunning the projection on a trimmed load, shape A:

| N | Points today | Points trimmed | Analyses/hour trimmed | Cache trimmed |
| --- | --- | --- | --- | --- |
| 1 | 57.1 | 43.2 | 83 | 10.5 MB |
| 3 | 86.1 | 55.2 | 65 | 11.1 MB |
| 5 | 115.1 | 67.2 | 53 | 11.7 MB |
| 10 | 187.6 | 97.2 | 37 | 13.2 MB |

**Trimmed N = 10 costs less than untrimmed N = 5, and holds under a quarter of the disk.** If the design
takes one thing from this document, take that: the reference loader, not N, is where the cost is.

Two caveats before anyone treats it as free money. `WclRunRepository.load` is one method serving
both our run and every reference; splitting it is real work with real tests, and the brief's §9
warns that a two-tier fetch makes N stop being one number. And the cheap tier's 2.01 assumes the
route comparison needs no event stream — which the code supports today (`align_pulls` and
`compare_route` read only `Run`), but which any future route finding could quietly break.

---

## 8. What I did not measure, and where the numbers are soft

- **Only one dungeon, one bracket, one page.** All three references were +16 Den of Nalorakk runs of
  1357–1399 s, 5 players, 12 pulls. A longer dungeon, or a bracket where fast runs run past 1800 s,
  would page `Casts` twice and add 1.00. Treat 14.5 as "a fast +16 run of a 20-minute dungeon", not
  as a universal constant.
- **`DamageTaken` varied 1.00 / 1.22 / 1.52 across three runs** with no pattern three samples can
  establish. It is the only query whose price I cannot predict. It is also, conveniently, one no
  reference comparison reads.
- **No candidate row failed to load.** `_references` skips a row whose report will not load, and a
  sample would have to keep drawing until it has N. A failed candidate costs at least the `Fights`
  query, 2.01, since that is the first query `load` issues — but I did not observe a failure, so I
  cannot say how often it happens or whether some failures cost more.
- **N > 44 is unmeasured.** Page 1 of the speed board holds 44 rows; a second page would be another
  ~1.01 and is untested.
- **I did not price a reference with many deaths.** Two data points (0 and 2 deaths) give
  1.00–1.42 per merged run-up window; the 6-death row on the leaderboard would have tested the
  linearity and I chose not to spend on it, since the term disappears entirely under §7's trim.
- **The 6.00-point discrepancy in §1 is unexplained.**

---

## 9. Recommendation

**Take N = 5 on the speed side and keep one parse reference — shape A, N = 5. It costs 115 points
of 3600 on a cold cache, 3.2% of the hourly budget, 31 analyses an hour, and 36 MB of local cache
that expires in a day.**

Why 5 and not 3 or 10:

- Quota does not choose it. Every N from 1 to 10 is affordable in both shapes; §5 settles the
  brief's §9 fork in favour of "N full reference loads are comfortable — take the simple path".
  The brief's own preferred shape, "one sample, N of five or six, full load for every member, one
  denominator per finding", is therefore **affordable as written**, and no two-tier machinery is
  needed to make it fit.
- Five is the smallest N at which "4 of 5 fast runs skipped this pack" reads as a distribution
  rather than as anecdote, and at which one unusual reference cannot carry a finding on its own.
  At N = 3 a single outlier is a third of the evidence.
- Ten costs 63% more than five, doubles the disk, adds half a minute of latency, and pulls ten
  strangers' logs per analysis instead of five. It buys sharper denominators than the report can
  honestly render — the brief's §5 already rejects percentages at these sample sizes.
- One parse reference, not five, because "the top parse of your specialisation" is a claim about an
  exemplar, and a sample of parses is a different claim that the brief has not yet decided it wants
  to make. Moving the parse side to a sample later costs a further 16.5 a head, which changes
  nothing about affordability — it is a design question, not a budget one.

**And trim the reference load, in the same plan or the next one.** Not because N = 5 needs it, but
because a speed-side reference currently pays 8.5 of its 14.5 points and 4.5 of its 4.8 MB for data
no route or tempo comparison reads. Trimmed, shape A at N = 5 costs 67 points and 12 MB. That is the difference
between a feature the human notices in their quota and one they do not.

Plainly, for the record: **I measured** the quota read, the analysed run, three reference runs, both
leaderboards, two aura tables, every cache size and the end-to-end total. **I extrapolated** every
row of every projection table from the measured per-reference figure, and I extrapolated the trimmed
tier from per-query prices measured inside a full load rather than by running a trimmed load, which
does not exist yet.

---

## Rows proposed for the wcl-api skill

`.claude/skills/wcl-api/SKILL.md` is held against the code by a test, so I have not edited it. These
belong under **Rate limit**, after the existing measurements. Each is written as it should be added.

- A `rateLimitData` read costs exactly **1.00 point**, re-confirmed 2026-09-08 by three consecutive
  reads whose deltas were 1.00 and 1.00.

- **A whole compared analysis, re-measured 2026-09-08 on a cold cache for report
  `6Kx1P9GbNXrcLdHa` fight 36, cost 41.38 points of 3600** — the figure as the command reports it,
  and so including one of the two quota reads it makes itself, never both. The real spend is
  42.38. The 44.29 recorded on 2026-09-07 for the same command and fight differs because the
  leaderboard named a different reference run that day; the reference's
  own load is the term that moves. Expect a spread of a few points across days for an unchanged
  command.

- **Composition of that 41.38, priced query by query on 2026-09-08:** the analysed run's cold load
  19.06 over 17 queries; `FightRankings` 1.01 and `CharacterRankings` 1.01; two aura tables at 2.00
  each; the command's quota reads 1.00 as that difference sees them; and 15.30 for the one
  reference run, which served as both the speed and the parse reference because both leaderboards
  named the same report and fight.

- **One reference run, loaded cold, costs 13.58 to 15.70 points** (measured 2026-09-08 on
  `71cv4MRdNCp8ZFjG` fight 28 with no deaths, 11 queries, and `37FzMg9pVPH6fnJT` fight 16 with two
  deaths, 13 queries), plus 2.00 for its aura table. Per query, on a `+16` run of about 1380 s:
  `Fights` 2.01, `Talents` 2.05, `Abilities` 1.00, `Casts` 1.00, `Deaths` 1.00, `EnemyCasts` 1.00,
  `Interrupts` 1.00, `EnemyDeaths` 1.00, `DamageTaken` 1.00–1.52, `Resurrects` 1.00, `Actors` 1.00,
  and 1.00–1.42 per merged healing window.

- **Volume is nearly free; queries are what cost.** A `Casts` page returning 7975 rows and 3.16 MB
  costs 1.00, the same as a `Deaths` page returning nothing. Measured 2026-09-08. The exceptions
  are `Fights` (2.01), `Talents` (2.05), a `table` query (2.00) and `DamageTaken`, which was 1.00,
  1.22 and 1.52 on three runs of the same dungeon and bracket.

- **A cast page costs 1.00 with `includeResources: true`, re-measured 2026-09-08** on the same
  report and fight: two pages, 10000 + 716 rows, 1.00 each, 2.00 in all. This does not agree with
  the 2.59 recorded on 2026-09-07 for the same two pages and the same 10716 rows, nor with the
  "about 0.30 a page" the flag was said to cost. Both readings used a `rateLimitData` query either
  side. The disagreement is unresolved; treat a cast page as 1.00–1.30 until someone measures it a
  third time.

- **A leaderboard page is one query and holds many candidates.** Measured 2026-09-08 for Den of
  Nalorakk +16: `fightRankings(metric: speed)` page 1 returned **44 rows with 44 distinct report
  codes** for 1.01 points; `characterRankings(metric: playerscore)` page 1 returned **82 rows with
  82 distinct report codes** for 1.01. Comparing against a sample of references therefore adds no
  leaderboard query until the sample exceeds 44.

- **The affix table is fetched twice per compared analysis**, once into the main cache and once into
  `cache/references`, because `build_reference_repositories` gives the references their own
  `DiskCache` directory. 1.00 each, and once per directory however many references are loaded.
  Observed 2026-09-08.

- **Cache on disk, measured 2026-09-08:** the analysed run and its aura table occupy 6.57 MB over 18
  entries in the permanent cache; one reference run occupies 4.73–4.86 MB over 11–13 entries in the
  24-hour references cache, of which 3.16 MB is the cast stream and 1.34 MB the damage-taken
  stream; a leaderboard page is 45 KB and an aura table 95 KB.
