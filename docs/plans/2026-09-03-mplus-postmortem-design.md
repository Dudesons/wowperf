# Mythic+ Run Post-Mortem — Design

- **Date:** 2026-09-03
- **Status:** Approved. Plans A to F implemented; §6.5 amended 2026-09-05 (see §6.5)
- **Scope:** First vertical slice of the `wow_perf` project

---

## 1. Purpose

A player finishes a Mythic+ key, feels it went badly, and cannot say why. Warcraft Logs
shows what happened but not what it cost. This tool answers two questions from one report
URL:

1. **Where did the time go?** — a group-level accounting of the run in seconds.
2. **What should I press differently?** — an individual comparison against a top parse of
   the same specialization.

It produces one self-contained HTML report combining measured facts with a written
interpretation.

### Scope of this slice

In scope: a single completed Mythic+ run, analysed and compared against two reference runs
fetched on demand.

Out of scope, deferred to later slices: raid encounters, wipe analysis, healer-specific
analysis, personal run history, and raw combat-log ingestion.

### Where this sits

The project decomposes into four slices. Each gets its own design, plan, and implementation
cycle.

| Slice | Content |
| --- | --- |
| 1 (this one) | Mythic+ run post-mortem with speed and spell comparison |
| 2 | Single-player raid analysis |
| 3 | Raid wipe analysis |
| 4 | Healer analysis |

Slice 1 establishes the API client, cache, domain model, findings format, report renderer,
and skills layer. Later slices add analyzers and reuse everything else.

---

## 2. Verified context

The verified API reference now lives in `.claude/skills/wcl-api/SKILL.md`, where every claim
carries the date it was checked and a field table that a test holds against the code. It moved
there on 2026-09-05: two copies of a schema reference drift, and the drifted one is read as true.

### 2.6 Existing tools

`WoWAnalyzer` performs per-specialization rotational analysis, is actively maintained on a
`midnight` branch, and is AGPL-3.0. It analyses one log in isolation and exposes no API.
`WowCoach.gg` ingests raw combat logs for raid and Mythic+ and ships an LLM coach. `Healper`
covers healers. `Lorrgs` publishes cooldown timelines from top parses.

We do not rebuild per-specialization rotational rules. WoWAnalyzer encodes what good play
should be, maintained by hand, one specialization at a time. This tool derives it empirically
from what top players actually did, which requires no specialization knowledge and therefore
works on every specialization from the first day.

---

## 3. Architecture

Hexagonal layering. The domain holds the model and the analysis; everything that touches the
network, the disk, or a template sits behind a port.

The seam earns its cost: raw `WoWCombatLog.txt` ingestion, planned for a later slice, enters
as a second `RunRepository` adapter and changes no analysis code.

```
wowperf/
  domain/
    model/        Run, Pull, Player, Death, CastEvent, Finding
    analysis/     pure functions: model -> [Finding]
    ports.py      RunRepository, RankingRepository, ReportRenderer  (typing.Protocol)
  adapters/
    wcl/          auth, GraphQL transport, queries, ingest
    cache/        caching decorator over the repositories
    report/       Jinja2 renderer
  application/
    analyze_run.py    AnalyzeRunService
    compare_runs.py   CompareRunsService
  cli.py          driving adapter (typer)
```

Deliberately absent: dependency-injection container, CQRS, event bus, unit of work, factory
per entity. Ports are Protocols, adapters are classes, and `cli.py` wires them in roughly ten
lines.

### 3.1 Data flow

Report URL to HTML:

1. Parse the URL into a report code and optional fight ID.
2. `reportData.report.fights` — select the fight with a non-null `keystoneLevel`.
3. `masterData` — actor and ability names.
4. `dungeonPulls` — pull boundaries and enemy composition.
5. Targeted `events` and `table` calls (see §5 for which, and why each is narrow).
6. Ingest into the domain model.
7. Run analyzers, collect findings.
8. Fetch reference runs, ingest, align, diff.
9. Render HTML and write findings JSON.

### 3.2 Queries and typing

We write GraphQL queries by hand and validate responses with Pydantic at the ingest boundary.
We do not generate a client.

Reason: `events`, `table`, `graph`, `rankings`, and `playerDetails` all return the untyped
`JSON` scalar, and RPGLogs reserves the right to change those shapes without notice. Code
generation would type only `fights` and `masterData`, the parts that are already simple, while
adding a build step. Validating at the boundary catches shape drift where it happens.

### 3.3 Caching

The cache is load-bearing, not an optimization. Point cost per query is unknown, and iterating
on analysis code without a cache would exhaust the hourly budget blind.

Implemented as a decorating repository, so caching stays out of the client. Policy follows the
vendor's own guidance: report data for a fight whose `inProgress` is false never changes, so it
caches indefinitely; game data caches indefinitely; rankings cache for hours.

Every phase logs `rateLimitData` before and after, recording measured cost. After the first
real runs we will know the actual budget instead of guessing at it.

### 3.4 Tooling

`uv` throughout: `uv init`, `.python-version`, dependencies declared in `pyproject.toml`,
`uv add`, `uv sync`, `uv run pytest`. No pip, no poetry, no hand-managed virtualenv.

Runtime dependencies: `httpx`, `pydantic`, `jinja2`, `typer`. Development: `pytest`, `ruff`,
`mypy`.

### 3.5 No hardcoded season data

Zone IDs, encounter IDs, dungeon names, and affix names come from `worldData` and `gameData` at
runtime and cache permanently, guarded by `Zone.frozen`. Season 3 must not require a code
change.

Some constants have no API source and Blizzard retunes them between seasons. These live in
`data/season.toml`, not in code, each with the date it was last verified:

| Constant | Current value | Verified |
| --- | --- | --- |
| Death timer penalty | 5 s | 2026-09-03 |
| Death timer penalty at keystone 12 and above | 15 s | 2026-09-03 |
| Enemy health scaling per keystone level | ~10%, compounding | 2026-09-03, community source |

The scaling figure is used only to justify refusing throughput comparisons (§6.4). No
calculation depends on its precision.

### 3.6 Command-line contract

```
wowperf analyze <report-url-or-code> [options]

  --fight N            fight ID; defaults to the only keystone fight, errors if ambiguous
  --player NAME        subject of the individual comparison; defaults to the report owner
  --no-compare         skip both reference runs, analyse in isolation
  --deep               include per-player cast analysis (see §5.5)
  --narrative FILE     inject a Markdown narrative into the report (see §8)
  --out DIR            output directory; defaults to ./out
```

Two files are written: `<code>-<fight>.html` and `<code>-<fight>.findings.json`. The exit code
is non-zero when the report cannot be fetched, the fight is not a Mythic+ run, or a bracket
assertion fails (§6.2). Ordinary analysis gaps produce findings, not failures.

---

## 4. Domain model

Pydantic models, free of any Warcraft Logs vocabulary.

- **`Run`** — dungeon, keystone level, affixes, official time, bonus chests, required and
  reached counts, roster, pulls, deaths, source reference.
- **`Pull`** — index, start, end, boss flag, enemy NPCs with counts, map position,
  enemy-forces contribution.
- **`Player`** — name, class, specialization, item level, talent import string.
- **`Death`** — player, timestamp, pull, killing blow ability, seconds until the player's
  next action. No `overkill` field: a Warcraft Logs death event carries no such data
  (confirmed 2026-09-04 against a real report — see §11), and computing it would need a
  join against damage events. Deferred until a plan needs it enough to pay for that query.
- **`CastEvent`** — actor, ability, timestamp, pull, success or interrupted.
- **`Finding`** — the analysis output type: `id`, `severity`, `title`, `detail`,
  `seconds_lost`, `confidence`, `evidence[]`, `pull_ref`.

`confidence` is an enum of `measured`, `derived`, and `inferred`. Every finding carries one.

---

## 5. Analyzers

Every Mythic+ finding is denominated in **seconds**. Not percentiles, not scores. Seconds rank
against each other, translate directly into action, and stay meaningful across keystone levels,
which percentile-shaped metrics do not.

### 5.1 Time decomposition — `measured`

`keystoneTime` minus the sum of pull durations minus death penalties leaves a residual: travel,
run-backs, and waiting on cooldowns. Death penalty constants come from `data/season.toml`
(§3.5), not from the code.

Each gap between consecutive pulls is ranked worst first and carries the map coordinates from
`ReportDungeonPull.x`/`y`, so the reader knows where the group stood still.

### 5.2 Deaths and their cost — `measured`

The timer penalty understates the real cost. We measure it instead: from the death timestamp to
that actor's next cast or damage event is the actual time spent not playing.

Deaths are ordered. In a chain, the first death usually causes the rest.

### 5.3 Missed interrupts — `derived`

The combat log carries no "interruptible" flag, so we reconstruct outcomes. For each enemy
`SPELL_CAST_START(x)`, resolve to one of three cases:

- a `SPELL_INTERRUPT` with `extraSpellId == x` — kicked;
- a `SPELL_CAST_SUCCESS(x)` from the same `sourceInstanceID` — **missed**;
- neither, because the caster died, was crowd-controlled, or cancelled — **excluded**.

The third case is where naive implementations produce garbage. `sourceInstanceID` is required to
distinguish multiple copies of the same NPC.

We vendor no curated must-kick list. Instead every completed enemy cast is ranked by the damage
that followed it, which surfaces the spells that hurt this group rather than the ones a
spreadsheet nominates. Warcraft Logs itself does not compute this.

### 5.4 Trash efficiency — `measured`

Per-pull enemy-forces contribution from `npcCountMap`, and total killed against `countRequired`.
Reaching 112% of required means roughly 12% of trash time was spent for nothing.

### 5.5 Per-player, in combat only — `derived`

Active time computed from cast events **inside pull windows**, since downtime between pulls
belongs to the route, not the player. Also interrupt participation and deaths.

Damage taken is reported as **damage per ability against the group median for that same
ability**, never as "avoidable damage". Deciding whether a hit was avoidable needs per-mechanic
knowledge this slice does not have, and guessing at it would produce exactly the confident
nonsense the confidence badges exist to prevent. Taking three times the group median from one
ability is a fact the reader can act on without the tool pretending to know why.

**No damage ranking.** Warcraft Logs deliberately exports no per-boss Mythic+ damage metric
because the unit of optimization is the whole dungeon. Ranking individual throughput in Mythic+
invites exactly the behaviour this tool exists to coach out.

Full cast events are the expensive call. If measurement shows the cost is prohibitive, this
analyzer moves behind a `--deep` flag. It does not get silently dropped.

### 5.6 Explicitly inferred

"Defensive available but unused" is **inference, not measurement**. The combat log emits no
cooldown-reset or cooldown-reduction events, so a defensive may genuinely have been unavailable.
It ships labelled `inferred` and only for the unambiguous case: never cast at any point in the
run.

### 5.7 Defensive uses against the cooldown ceiling — `inferred`

*Added 2026-09-05. This began as §6.5 item 4 and moved here; see §6.5.*

§5.6 reports a binary: pressed, or never pressed. This deepens it to a rate. The ceiling is

```
alive_combat_seconds / cooldown_seconds * charges
```

using the death spans §5.2 already computes, because a defensive cannot be pressed by a corpse
and charging a player for time they spent dead penalises the same death twice.

`cooldown_seconds` and `charges` have **no API source**. A schema-wide search for `cooldown` and
`charges` on 2026-09-05 returned nothing. They join `data/defensives.toml` beside the ability IDs
already there — roughly forty values, dated and hand-maintained, on the same terms as §3.5 allows
for constants the API does not expose.

The badge is `inferred`, and the reason is not the arithmetic. **A defensive is pressed into
incoming damage, not on cooldown.** A tank who used Icebound Fortitude twice in a clean run did
nothing wrong, and "the cooldown allowed eight" is true and useless. Two constraints keep the
finding honest: it fires only far below the ceiling rather than at any shortfall, and the detail
states the situational caveat outright rather than leaving the reader to supply it.

This needs no reference run and appears under `--no-compare`. It measures a player against the
game's rules, which is why it is an analyzer and not a comparison.

---

## 6. Comparison

### 6.1 Two reference runs

Two questions need two references.

- **Group axis:** `fightRankings(metric: speed)` — a fast completion of the same dungeon,
  compared on route, timing, and deaths.
- **Individual axis:** `characterRankings(metric: playerscore, className, specName)` — a top
  parse of the analysed player's specialization, compared on spells and talents.

One report may satisfy both. We do not optimize for that; two queries are simpler and the cache
absorbs the cost.

### 6.2 Matching rules

Dungeon must match exactly. Partition must match, or the comparison crosses a tuning change.
Keystone level targets the same bracket and accepts a difference of at most one level, stated in
words at the top of the report. Affixes are displayed as a difference rather than filtered on, since requiring
an exact match would usually return nothing. Reference runs must have `kill: true` and a non-null
`keystoneLevel`.

**The bracket convention is asserted, not assumed.** On the first ranking call the implementation
checks the returned rows' `bracketData` against the requested keystone level and fails loudly on
mismatch. An undocumented off-by-one would silently poison every comparison the tool makes.

### 6.3 Pull alignment

A pull's canonical signature is the multiset of `enemyNPCs[].gameID`. The two pull sequences are
aligned with `difflib.SequenceMatcher` over those signatures, yielding matched pulls, pulls only
we killed, pulls only they killed, and pulls matched out of order.

That produces the findings that matter: which packs the faster group skipped and what they were
worth, and which packs we killed for nothing. Standard library suffices; a bespoke alignment
algorithm would be architecture for its own sake.

### 6.4 What we compare, and what we refuse to

Enemy health scales roughly 10% per keystone level, compounding.

**Comparable across a keystone-level gap:** pull composition, pull order, packs skipped, death
count, missed interrupts, between-pull downtime.

**Not comparable:** pull duration, boss kill time, anything throughput-shaped.

When keystone levels differ, the report greys out the invalidated metrics and states the reason
inline. It does not print a number the reader will misuse.

### 6.5 Spell comparison runs on boss pulls only

Across trash, ability ratios are dominated by pull size and route. Comparing an area-of-effect
pull against a single-target pull says nothing about play. Boss pulls are a fixed, comparable
encounter. Restricting to them costs coverage and buys validity.

Compared, in descending order of signal:

1. **Abilities they cast that we never cast.** A set difference. No modelling, no assumptions,
   highest value.
2. **Talent build difference.** `ReportFight.talentImportCode(actorID)` returns the import
   string. We diff and print an importable result.
3. **Casts per minute of active time**, ability by ability. Integer gaps are unarguable.
4. ~~**Cooldown uses against theoretical maximum**~~ — **moved to §5.7 and narrowed, 2026-09-05.**
   As written this needed cooldown seconds and charge counts for every rotational ability of
   every specialization, none of which the API publishes, all of which go stale each patch, and
   the result would be wrong wherever a proc resets a cooldown — which in current WoW is most
   specializations. Narrowed to the defensives already listed in `data/defensives.toml`, whose
   cooldowns rarely reset, it survives every one of those objections. It also stopped being a
   spell *comparison*: a cooldown ceiling is the game's own limit, so it needs no reference run
   and belongs beside §5.6.
5. **Buff and debuff uptime**, on self and on target. *Specified 2026-09-05.* Two `table` calls
   per side, which "on self and on target" resolves to exactly:

   - **on self** — `dataType: Buffs, targetID: <subject>`, the auras the player carried;
   - **on target** — ~~`dataType: Debuffs, sourceID: <subject>, hostilityType: Enemies`, the
     debuffs the player kept up on enemies.~~ **This does not work.** Corrected 2026-09-05:
     that argument combination returns zero auras against the live API, and no other argument
     narrows the enemy-debuff table to one caster — the measured table is in
     `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to one caster".
     Plan D ships the plumbing, which is correct code for a query that returns nothing, so the
     on-target half is inert. Reviving it means either comparing the two groups' debuff uptime
     rather than the two players' — a different claim, which the finding would have to state —
     or finding a per-source filter this project has not found. Neither is decided.

   Both are restricted to boss pulls by intersecting each aura's `bands` with the boss windows
   (`.claude/skills/wcl-api/SKILL.md`, "Aura tables"), and compared against the same
   specialization's top parse. Badge `derived`: the arithmetic over bands is exact, but comparing
   two players in two different fights rests on an assumption that can be wrong. The reference player is found by name in their own roster,
   and their absence from it is a finding, not a failure — as in §6.1.

   Plan C deferred this on the grounds that it "doubles the event fetch on both sides". That
   reasoning does not survive measurement — the table endpoint is pre-aggregated and needs no
   event stream at all, and ~~four aura tables cost about four points of an hourly
   3600 (§2.2)~~. *Amended 2026-09-05:* the four-point figure was never measured on its own.
   What was measured is 12.02 points of 3600 for a roster query, four aura tables and a
   `rateLimitData` read together, recorded in `.claude/skills/wcl-api/SKILL.md`, "Rate limit".
   The conclusion is unchanged: the cost is a rounding error against the hourly budget.

### 6.6 Confounds we declare rather than correct

- **Group composition.** Large, uncorrectable.
- **Gear beyond item level.** Tier count, trinkets, and embellishments are uncorrected, and patch
  12.1's Matrix Catalyst preserves original secondary stats, so equal item level no longer implies
  a similar stat profile.
- **Augmentation Evoker.** Blizzard's support-attribution hooks are documented as faulty:
  throughput debuffs go unaccounted, reattribution can subtract damage, and shared health pools
  generate duplicate events. When either roster contains an Augmentation Evoker, the report shows
  a banner stating that per-player damage attribution is unreliable.

### 6.7 The parse percentile

One line in the report header, labelled as triage. It indicates that something is wrong and never
what. Bracket percentiles interpolate between cached sample points, so a true 99.8 can display as
99.1. It is never a headline and never an optimization target.

---

## 7. The report

One self-contained HTML file. No content delivery network, no network access at load. It must
open from disk, survive being posted to Discord, and work offline.

Jinja2 template, inline CSS, and charts as **server-side-generated inline SVG** rather than a
JavaScript charting library. The output is therefore deterministic, which makes it
snapshot-testable.

Sections, in order:

1. **Header** — dungeon, keystone level, affixes, timed or depleted ~~and by how much~~, ~~parse
   percentile as triage,~~ warning banners. *Amended 2026-09-05:* the percentile is not built.
   Nothing this project fetches produces our own player's rank — `top_parses` returns the leading
   rows for a specialisation, not our position among them — so a percentile here would be an
   invented number. Reviving it needs a leaderboard query scoped to our own character, verified
   live and dated first. See the report design, §5.1. *Amended 2026-09-05:* the header states the
   run's own completion time, not a margin. `keystoneTime` is Blizzard's penalty-inclusive
   completion time, not the key's time limit (`.claude/skills/wcl-api/SKILL.md`, "Mythic+ in the
   schema"), so "by how much" would need a par time no Warcraft Logs field this project fetches
   carries — inventing one is exactly what this design forbids.
2. **Narrative** — the written interpretation (see §8), visually distinct and marked as
   interpretation.
3. **Seconds ledger** — where the run's time went, and losses ranked, each with a confidence
   badge.
4. **Aligned timeline** — our pulls beside the reference run's, with skipped and extra packs
   marked.
5. **Deaths** — ordered, expanding into the last ten seconds of damage taken.
6. **Interrupts** — missed casts grouped by spell, ranked by the damage that followed.
7. **Per-player cards** — ~~in-pull active time~~, deaths, kicks, ~~avoidable damage~~, and the
   spell and talent difference. *Amended 2026-09-05:* not "avoidable damage" — the log does not
   record whether a hit could have been dodged, and §5.5's analyser already refuses that framing,
   stating damage against the group median instead. The card follows the analyser. See the report
   design, §3.1. *Amended 2026-09-05:* not "active time" either. `active_seconds` is
   `casts_in_pulls` at one modelled second per cast — a deliberately coarse floor — so a fast
   caster exceeds both the pull time and 100% activity on the reference run, and a percentage
   that is meaningful below 100 and nonsense above it is worse than no percentage. The card states
   the cast count over the pull time instead, and drops the derived share. See the report design,
   §4.
8. **Provenance** — report code, fetch time, reference run links, and the confidence legend.

Dark by default. Class colours identify players but never carry meaning alone, since several are
hard to distinguish and reports get screenshotted.

---

## 8. The inference layer

Two layers, with a hard line between them.

**Python produces facts.** Deterministic, tested, opinion-free. "The gap after pull 7 was 41
seconds." "Nobody cast Ability X." "Three casts of Spell Y completed uninterrupted, followed by
340k damage."

**Claude produces meaning.** "Both of your largest losses are travel, not combat, so routing is
the problem, not damage. Separately, you never pressed Ability X, and your build is missing the
talent every top parse of your specialization takes."

The command-line tool emits **two artifacts**: HTML for people, and a structured findings JSON for
Claude. Claude never parses the HTML.

**The guardrail:** the skill instructs Claude to reason only over findings present in the JSON and
to reference them by ID. ~~A number absent from the findings file may not appear in the
narrative.~~ **Amended 2026-09-05:** the narrative states **no** numbers. Every figure already
sits in a badged section directly below it, so a number repeated in the narrative is a second,
unbadged claim competing with the first. `analyze --narrative` enforces it by refusing any digit,
before fetching. The check is a tripwire rather than a proof — spelled-out quantities pass, and
the instruction that forbids them lives in `analyzing-a-run`. See
`docs/plans/2026-09-05-mplus-inference-layer-design.md` §3. Confidence badges let Claude hedge
where the underlying claim is inferred instead of asserting everything with equal force.

The narrative returns to the report through `--narrative notes.md`, which renders it as section 2
(§7), directly below the header. Determinism survives, because the narrative is an input to
rendering rather than something the template invents.

### 8.1 Skills

Three, each earning its place in `.claude/skills/`.

*Built 2026-09-05.* All three exist as `.claude/skills/<name>/SKILL.md`, and `wcl-api` holds the
verified API reference that was §2 — §2 is now a pointer to it, because two copies of a schema
reference drift and the drifted one is read as true.

- **`wcl-api`** — the verified API reference: exact field names, enum values, conventions that
  remain unverified, terms-of-service limits, rate-limit etiquette. It exists so that future
  sessions cannot invent field names.
- **`mplus-analysis`** — domain knowledge: the seconds framing, why damage goes unranked in
  Mythic+, the comparison confounds.
- **`analyzing-a-run`** — the workflow: take a URL, run the tool, read the JSON, interpret,
  converse, inject the narrative.

---

## 9. Testing

Unit, integration, and end-to-end, developed test-first.

- **Unit.** Analyzers are pure functions over the domain model and test against hand-built
  fixtures. This is the bulk of the suite.
- **Integration.** The ingest layer against recorded real API responses committed as fixtures.
  Replaying a captured payload is a golden fixture, not a mock of behaviour. These catch
  relative-timestamp handling, absent fields, and shape drift.
- **End-to-end.** Real API, real report, no mocks. Marked `@pytest.mark.e2e`, requiring
  credentials, excluded from the default run so the ordinary suite stays fast and offline.
- **Report snapshots.** Golden-file comparison on rendered HTML, which the deterministic SVG
  choice makes possible.

Test output must be clean. Expected error logs are captured and asserted on.

**Fixture policy.** RPGLogs §5d prohibits permanent copies. Test fixtures stay minimal, player and
guild names are anonymized, and large event dumps are never committed.

---

## 10. Risks

| Risk | Response |
| --- | --- |
| Point cost per query is undocumented | Instrument every phase with `rateLimitData` and measure. Cache aggressively from the first commit. |
| `bracket = keystoneLevel - 1` is unverified | Assert `bracketData` on the first ranking call and fail loudly on mismatch. |
| Full cast events may be too expensive | Move §5.5 behind `--deep` if measurement shows it. Never drop it silently. |
| Untyped JSON shapes may change without notice | Pydantic validation at the ingest boundary, with clear errors naming the field. |
| Augmentation Evoker corrupts damage attribution | Detect and warn in the report. It cannot be corrected. |
| Season rotation breaks hardcoded IDs | Resolve all IDs from `worldData` and `gameData` at runtime. |

---

## 11. Open items for the implementation plan

- ~~Confirm the real hourly point limit from a live `rateLimitData` call.~~ Confirmed on
  2026-09-04 by live introspection: `limitPerHour` reads **3600**.
- ~~Measure the point cost of a full run analysis, and decide from the measurement whether
  §5.5 ships enabled or behind `--deep`.~~ Measured on 2026-09-04 against report
  `6Kx1P9GbNXrcLdHa` fight 36, a +16 Den of Nalorakk of 31.8 minutes with 5 players, 12
  pulls, 9,259 casts and 4 deaths. Every figure below includes the two `rateLimitData` reads
  the CLI makes, which cost about 0.5 each:

  | Operation | Cold | Warm |
  | --- | --- | --- |
  | `get` — fights query only, enough to build a `Run` | 3.00 | 1.00 |
  | `load` — fights, abilities, casts (2 pages), deaths | 7.04 | — |
  | `load` with fights and abilities already cached | — | 5.00 |

  So a fights query costs about 2 points and a complete event fetch about 6. Against 3,600
  per hour that is roughly **600 full run analyses an hour**, which settles the question:
  **§5.5 ships enabled, not behind `--deep`.** The budget is not the constraint the design
  feared. The disk cache stays load-bearing anyway — it makes iterating on analysis code free
  rather than merely cheap, and a warm `get` costs only the quota reads themselves.

  Caveat: one dungeon, one key level, one group. A longer key or a cast-heavier composition
  pages more; the shape of the cost, not its exact value, is what this measures.
- Confirm whether Warcraft Logs exposes a CSV export worth using, or whether JSON is the only
  practical surface.
- Confirmed on 2026-09-04 against a real death event (report `6Kx1P9GbNXrcLdHa`, fight 36): a
  Warcraft Logs death event's complete key set is `abilityGameID` (always `0`), `fight`,
  `killerID`, `killerInstance`, `killingAbilityGameID`, `sourceID` (always `-1`), `targetID`,
  `timestamp`, `type`. There is no `killingBlow` object and no `overkill` field — both were
  invented in the original design and have been corrected (§4): the killing blow resolves
  from `killingAbilityGameID`, and `overkill` is dropped from `Death` until a plan pays for
  the damage-event join it would need.
- ~~Decide the fate of §6.5 items 4 and 5, deferred by Plan C.~~ Settled 2026-09-05. Item 4
  moved to §5.7 and narrowed to defensives, because the API publishes neither cooldown
  durations nor charge counts and the unnarrowed version would be wrong for most
  specializations. Item 5 is specified in §6.5 and built on the `table` endpoint verified in
  `.claude/skills/wcl-api/SKILL.md`, "Aura tables", which is cheaper than the event stream Plan C
  priced it against. Both are Plan D's.
