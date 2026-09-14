# Raid Analysis — Design

- **Date:** 2026-09-13, amended 2026-09-14
- **Status:** Approved; plan 1 merged, §14 resolved
- **Scope:** Second vertical slice of the `wow_perf` project

**Reading the amendments.** §14's nine open items were resolved on 2026-09-14 by measurement
against the live API. Four of those measurements contradicted a section written before them:
§2.1, §2.5, §6.3, §6.8, §6.9 and §8.2 each carry an inline amendment note, and the section
they amend is left standing above it so the correction is legible as a correction. §15 records
how the remaining work is cut into plans. **Where an unamended section disagrees with §14,
§14 is later and wins.**

**Authority.** `2026-09-03-mplus-postmortem-design.md` remains the authority on architecture,
badges and refusals. This document amends three of its sections by name in §9 and reopens
nothing else. `2026-09-08-sampling-design.md` remains the authority on how a sample is drawn
and when a comparison is withheld; this design draws its samples on a different axis and
changes none of those rules. `2026-09-10-per-player-parse-comparison-design.md` settled how one
command compares several players at once, and slice 2 inherits that answer whole.

---

## 1. Purpose

A raider finishes a night, sees a middling parse and a boss the guild could not kill, and
cannot say which of the two problems caused the other. Warcraft Logs shows what happened.
This tool says what was different about it.

Slice 2 answers three questions about one boss fight, from one report URL:

1. **What should I press differently?** — casts, cooldowns and talents against top parses of
   the same specialisation.
2. **Where is my damage going?** — the split across targets, against what the sample did.
3. **Which mechanics are we failing?** — the abilities that hit us and did not hit them.

The third question is the new one, and it is the reason this slice exists. Wipefest answers it
by encoding each boss by hand. This tool answers it by comparison, and therefore knows nothing
about any boss.

---

## 2. Verified context

Measured against the live API on 2026-09-13. Every claim below was run, not read. Report
`cW38jmwdnZfbHVL4` is one Heroic clear of The Venomous Abyss; report `1YW78rVzmnhPtADd` was
drawn once as a reference and not retained. The players in both are real people and are named
here by class and specialisation only.

### 2.1 Raid rankings take `difficulty` and `partition`

`Encounter.characterRankings` and `Encounter.fightRankings` each accept `bracket`, `difficulty`,
`partition`, `page`, `size`, `className`, `specName`, `metric` and more. Mythic+ passes
`bracket`; raid passes `difficulty` and `partition`. The query shape does not change.

`characterRankings(metric: dps, difficulty: 4, partition: 1, className: "Evoker",
specName: "Devastation")` on encounter 3421 returned **100 rows** at a cost of **0.0 points**.
Each row carries `amount`, `duration`, `startTime`, `bracketData`, `size`, `class`, `spec` and
`report { code, fightID }` — the same fields `build_parse_rows` already reads.

`CharacterRankingMetricType` offers `dps`, `bossdps`, `rdps`, `ndps`, `cdps`, `hps`, `tankhps`
and `playerscore`, among others. **Amended 2026-09-14 (§14 item 5): `rdps`, `ndps` and `cdps`
are not World of Warcraft metrics.** Each describes itself in the schema as "unique to FFXIV",
and `rdps` fails at the server. The choice for raid is `dps` or `bossdps`. Mythic+ uses `playerscore` from this same enum.
`FightRankingMetricType` offers `default`, `execution`, `feats`, `score`, `speed` and `progress`.

### 2.2 A report carries its own players' ranks

`Report.rankings(fightIDs: [N], playerMetric: dps)` returned **every one of the 20 players**
with `rank`, `rankPercent` and `totalParses`, grouped into `tanks`, `healers` and `dps`, for
**2.0 points**. The same row carries `difficulty`, `partition`, `bracket`, `size`, `deaths`,
`damageTakenExcludingTanks`, `execution` and `speed`.

The master design's §7 removed the parse percentile from slice 1 because "nothing this project
fetches produces our own player's rank". That is true of `characterRankings` and false of
`Report.rankings`. §9.3 amends it.

Reading `difficulty` and `partition` off this row removes any need to resolve them separately.

### 2.3 Damage done splits by target, exactly

`Report.table` accepts `viewBy: ViewType`, whose values are `Default`, `Ability`, `Source` and
`Target`. `table(dataType: DamageDone, fightIDs: [N], viewBy: Target, sourceID: A)` returns one
row per target with `name`, `id`, `guid`, `total` and `type`.

On The Twin Fangs, a Devastation Evoker's three rows summed to the exact total that
`viewBy: Source` reported for the same actor. The split is arithmetic, not an estimate, and
earns `measured`.

That player put **11.6%** of their damage into the add and **88.4%** into the two bosses; the
raid as a whole put 6.5% into the add. Cost: **0.94 points per table**.

### 2.4 Damage taken splits by ability, and the comparison finds mechanics

`table(dataType: DamageTaken, fightIDs: [N], viewBy: Ability)` returns one row per ability.
Comparing our 374-second kill against the reference's 393-second kill of the same boss, at a
cost of **2.0 points for both tables**, produced this:

| Ability | ours, hits/min | reference, hits/min |
| --- | --- | --- |
| Ravenous Feast | 11.1 | 0.0 |
| Coiling Ichor | 116.7 | 183.5 |
| Venomous Emergence | 12.7 | 17.2 |
| Corrosive Spit | 2.7 | 4.6 |

One ability hit us repeatedly across a six-minute kill and never hit them. No rule was written
for this boss, and none was needed: the encounter is fixed, so both sides draw from the same
ability set, and the difference is what remains.

### 2.5 Three details the probe exposed

**Two of the three claims below were measured wrong. Read the amendment under each.**

- **The damage-taken table includes friendly abilities.** Paladin damage transfers appeared as
  damage taken. `hostilityType` is the argument that excludes them; a name filter is not.

  **Amended 2026-09-14.** `hostilityType` does not exclude them. Omitting the argument and
  passing `Friendlies` return byte-identical JSON; `Enemies` returns the enemy side of the
  fight, a different table of 223 rows, not a filtered one. The argument selects *whose*
  damage-taken is tabulated, not which sources are counted, so friendly-sourced rows survive
  by design — 8 of 26 rows and 1.97% of damage on one measured fight. The row's own
  `sources[].type` is what distinguishes them, and sources were homogeneous on every row
  observed.

- **The hit count is wrong for damage over time.** One ability reported 3.1 million damage and a
  zero count, so the field read was not the one that counts ticks. The correct field names are an
  open item (§14) and must reach `.claude/skills/wcl-api/SKILL.md` with a date before use.

  **Resolved 2026-09-14 (§14 item 1).** No single field counts landings. `hitCount` counts
  direct hits, `tickCount` counts damage-over-time ticks, and an ability may carry both;
  `missCount` and `tickMissCount` count attempts that did not land. All four summed over one
  fight's 26 rows came to 11,456, matching the event count exactly.

- **An unscoped table sums the whole raid.** One ability read 1068 hits per minute across twenty
  players. Per-player figures need `targetID`, which changes the claim from "we" to "you".

  **Amended 2026-09-14.** The argument is `sourceID`, not `targetID`. On a damage-taken table
  `sourceID` scopes to the victim; `targetID` selects who dealt the damage and returned zero
  rows for a tank who had taken 26 million. A scoped sum matches the unscoped table's
  per-player entry to the unit.

### 2.6 The current tier

Zone **53, The Venomous Abyss**, nine encounters, partition **1 ("12.1")**, difficulties
**5 = Mythic** (size 20), **4 = Heroic**, **3 = Normal**, **1 = LFR**. Those four difficulty ids
are identical on every raid zone back to Warlords of Draenor.

`frozen` does not identify the current tier. Zones 52, 53, 55 and 510 are all unfrozen today.

---

## 3. Scope

### 3.1 In scope

One boss fight from one report, analysed for one player, several, or the whole roster, and
compared against a sample of top parses of each subject's specialisation.

**Kills and wipes both.** A kill receives every finding. A wipe receives the internal frame of
§4 in full and states, per withheld finding, that no ranking exists for an attempt that did not
kill.

**Findings at two scopes.** The mechanics comparison runs raid-wide and per-player from the same
machinery, differing only by `targetID`.

### 3.2 What this takes from slice 3, and what slice 3 keeps

The master design gives "single-player raid analysis" to slice 2 and "raid wipe analysis" to
slice 3. Raid-wide mechanics findings cross that line, and the crossing is deliberate rather
than accidental: the per-ability table that answers "did I eat this" answers "did we eat this"
for the price of one argument, and building the second half later would mean building it twice.

**Slice 3 keeps** the wipe narrative: why an attempt ended, which phase it ended in, what the
raid was doing when it collapsed, progression across a night's attempts, and any claim about
causation between players. Slice 2 states per-ability differences and stops.

### 3.3 Out of scope

- **Healer throughput.** Slice 4. `Report.rankings` returns `hps` ranks for healers and slice 2
  prints them, which is not healer analysis and must not be described as any.
- **Attempts as a series.** A night of wipes read together belongs to slice 3.
- **Encoding any boss.** No per-encounter rules, no phase table, no mechanic list. If a finding
  cannot be derived by comparison, it is not built.
- **Naming a mechanic as missed.** See §6.8.
- **Mythic+.** Nothing in `analyze` changes behaviour.

---

## 4. Two reference frames

Every finding is a difference against something. This slice has two, and which one is honest
depends on the question being asked.

| Frame | Compared against | Answers | Requires a kill |
| --- | --- | --- | --- |
| **External** | top parses of the subject's specialisation on this boss, at this difficulty and partition | damage, target focus, cooldown casts, buff uptime, rank | yes |
| **Internal** | the rest of the subject's own raid, and a sample of reference raids' profiles of the same boss | who took what, deaths, mechanics | no |

The internal frame is not a degraded external one. For mechanics it is the better of the two:
every player in a pull met the same mechanic, at the same moment, under the same tuning, and no
external sample controls for any of that.

A correction to an assumption made early in this design's brainstorming: the speed axis was
thought not to transfer to raid. It does. `fightRankings` supplies kills of the encounter, which
is exactly the reference raid the internal frame needs for its second comparison. What does not
transfer is the *dungeon* half — there is no route to compare.

---

## 5. Domain model

### 5.1 `Encounter` sits beside `Run` and never pretends to be one

A new frozen model carries what a raid fight has: `report_code`, `fight_id`, `encounter_id`,
`boss_name`, `difficulty`, `partition`, `size`, `kill`, `fight_percentage`, `start_ms`, `end_ms`,
`players`. It carries no pulls, no keystone level, no affixes, and no enemy forces.

`LoadedEncounter` mirrors `LoadedRun`: the aggregate plus the event streams already built.

### 5.2 Generic analysers take what they use, not a `Run`

Where an analyser needs only casts, deaths or a roster, its signature narrows to those.
`analysis/interrupts.py` already works this way — `analyse_interrupts(casts, damage_taken)` has
never seen a `Run` — and `recap.py` likewise. This design extends an existing pattern rather
than introducing one.

Narrowing is preferred to a shared base class. A base type would be speculation about what
slices 3 and 4 need, written before slice 2 has a line of code. Narrowing costs nothing and
converges on a base type later if one is ever earned.

### 5.3 Why a raid boss is not a `Run` with one `Pull`

The tempting alternative reuses everything: make `Run`'s eight Mythic+ fields optional and model
the boss as a single degenerate `Pull`. It was rejected, and the reason is measured rather than
aesthetic.

With `run.pulls` empty today:

- `analysis/players.py` computes `activity_percent = 0.0`, which falls below the 60% floor, and
  emits **"cast 0 times inside pulls" against every player in the raid**.
- `analysis/consumables.py:94` collapses `visible_from_ms` to zero, and the guard whose own
  docstring says it exists to prevent a false accusation stops guarding.
- `analysis/defensives.py:188` divides by an `alive_combat_seconds` of zero, so every
  `defensives.ceiling.*` finding disappears without a word.
- `comparison/spells.py:35` and `comparison/uptime.py:34` lose their denominators, and the parse
  axis returns `unavailable` instead of numbers.

None of these raises. All of them are quiet wrong answers, and this repository's documented
failure mode is precisely the assertion that could never have failed. Eight `Optional` fields
would also push a `None` branch into the 71 files that mention `pull`, where mypy catches only
those that dereference.

---

## 6. Analysers

Twelve findings. Seven exist already and need their denominator changed from pull time to fight
time. Each carries `measured`, `derived` or `inferred`, as every finding in this project must.

### 6.1 `damage.total` — `measured`

The subject's damage against the sample median, with the observed range. Requires the amendment
in §9.1.

### 6.2 `damage.targets` — `measured`

The subject's damage as a share per target, against the sample's shares. Reported as a
distribution, never as a total: totals confound target focus with fight length and gear.

A boss with one target produces one row and no finding. The analyser says so rather than
printing a comparison worth nothing.

### 6.3 `casts.count` — `measured`

Casts of each ability, the subject's against the sample median.

This is the cooldown finding, and it is worth stating why it is buildable here when §6.5 item 4
of the master design rejected it for Mythic+. That rejection reads: "this needed cooldown seconds
and charge counts for every rotational ability of every specialization, none of which the API
publishes, all of which go stale each patch, and the result would be wrong wherever a proc resets
a cooldown."

**The sample is the cooldown database.** Five top parses that each cast an ability five times in
this kill establish what five casts costs, procs and resets included, without the tool learning
what any cooldown is. The objection does not survive a fixed encounter.

Compared as counts while the two durations are close, and as casts per minute of fight once they
are not, with the difference stated either way. The threshold between the two is chosen, not
derived, and §14 records it as owing a measurement.

**Amended 2026-09-14 (§14 item 8): the count half is not built.** Measured against real
reference durations, the top five references spread 33.9% of our own duration on one boss and
16.1% on another. No threshold a five-reference sample reliably clears, so casts per minute of
fight is the only expression, not a fallback. This also keeps `ParseMember`'s stated reason for
carrying no `comparability` true: nothing on the parse axis is shaped like a duration.

### 6.4 `casts.missing` — `measured`

Abilities the sample cast and the subject never did. Exists as `compare_spells_sample`.

### 6.5 `talents` — `measured`

The build difference, printed as an importable string. Exists.

### 6.6 `uptime.buffs` — `derived`

Buff uptime against the sample. Exists; the denominator becomes fight time. The on-target half
stays inert for the reason recorded in `.claude/skills/wcl-api/SKILL.md`.

### 6.7 `rank` — `measured`

The subject's percentile from `Report.rankings`. One line, labelled as triage. §6.7 of the master
design binds it: it indicates that something is wrong and never what, it is never a headline, and
it is never an optimisation target.

### 6.8 `mechanics.ability` — `measured`

The per-ability damage-taken profile, compared twice: the subject against the rest of their own
raid, and the subject's raid against one reference raid's kill of the same boss.

**Amended 2026-09-14: the reference is a sample, not one raid.** "One reference raid" here
contradicted §13 — "one reference is one guild on one night with one composition" — and the
sampling authority this design's header says it changes none of, `2026-09-08-sampling-design.md`.
§13 and the authority win. `SAMPLE_SIZE` reference kills are drawn from the `execution`
leaderboard, filtered to our own raid `size`, and the finding states a median with an observed
range. Below `MIN_SAMPLE_FOR_AGGREGATE` matching references it states one reference and says so,
through the existing `too_few` wording. The cost stays trivial: §8.1 measures the damage-taken
table at 1.0 point and a reference contributes exactly one, so a full sample is about five
points against the parse axis's 7.29 *per reference*.

**The finding states hits and damage. It never states that a mechanic was missed.** "You took
four hits from Ravenous Feast; eighteen of twenty players took none" is a fact the reader
interprets. "You missed the soak" is a claim about intent that no table supports, and §5.5 of the
master design refuses exactly that inference. The badge is `measured` because what is printed is
counted, not judged.

Restricted to hostile sources by `hostilityType`, for the reason in §2.5.

**Amended 2026-09-14: the finding states landings only, and both sides come from the table.**

The damage half is not buildable as written. The table's `total` is *mitigated* — it equals the
event stream's `health_damage + absorbed`, exact on 23 of 25 rows and within 0.0018% fight-wide
— and `totalReduced` equals `health_damage` exactly. The unmitigated figure is not exposed and
not reconstructible. §6.9 ranks on unmitigated, so the same ability on the same fight reads
51,059,709 from the event stream against 11,070,173 from the table, and the factor ranges 0.88
to 4.61 within one fight, so no constant corrects it. A report stating both would print two
damage figures for one ability that its own evidence cannot reconcile, which
`2026-09-13-comparison-table-rulings.md` names as a defect.

So this finding states `hitCount + tickCount` and says nothing about damage. Both sides are
drawn from the same endpoint, which makes the counts reconcile exactly and keeps either side
from joining to the event stream — necessary, because **the table and the event stream disagree
on ability ids**: one ability measured as `guid 1302265` in the table and `abilityGameID
1287955` in the stream, the same 240 occurrences under two identifiers. Joining the endpoints on
id drops rows silently. §6.9 keeps damage, unmitigated, from events. Two findings, two units,
and nothing that looks as though it should reconcile.

The friendly-source restriction comes from the row's `sources[].type`, not from
`hostilityType`, per §2.5's amendment.

### 6.9 `damage.taken.outlier` — `measured`

Damage per ability against the group median for that ability, as §5.5 specifies. Exists, is
generic. Its 2026-09-06 amendment excluded tanks because a keystone's single tank "has no honest
median to be measured against". A raid has two, so a tank median exists — drawn from one other
player. Whether two is enough to rank against is a judgement the finding must make out loud, and
§14 records it as undecided.

**Resolved 2026-09-14 (§14 item 9): tanks stay excluded.** Two is not enough, by a rule the code
already states — `MIN_PLAYERS_FOR_MEDIAN = 3` in `analysis/players.py` — and the measurements
agree. Tank against tank ran a median ratio of 1.24 and 1.28 across two real fights; a non-tank
against a real median of the other non-tanks ran 1.08 and 1.10, with a 90th percentile of 1.68
and 2.24. The distributions overlap, the tank outliers rest on between one and eight landings,
and four abilities had no non-tank observation at all. For the eighteen non-tanks of a
twenty-player raid the median is real, so this finding works on a raid with no change beyond
taking `players` instead of a `Run`.

### 6.10 `deaths` — `measured`

Deaths and what killed each one. Exists. `pull_offset` and the "across N pulls" evidence line
need fight-relative replacements.

### 6.11 `death.recap` — `inferred`

The run-up, the reconstructed health curve, and every defensive, consumable and external placed
in one of four states at the moment of death. Fully generic already; `visible_from_ms` becomes
the fight's start rather than the first pull's.

### 6.12 `defensives.*` — `inferred`

Never pressed, and pressed far below what the cooldown allowed. Exists; `alive_combat_seconds`
becomes fight duration minus time dead.

---

## 7. Ranking

Slice 1 denominates every finding in seconds, and `rank_findings` sorts by `seconds_lost` with
every `None` falling to the bottom in arbitrary order. Most findings above cost no seconds. A
raid report ranked by that key would have no ranking at all.

**Raid findings rank by `severity`, then by each analyser's own magnitude.** A sibling of
`rank_findings` does this; the existing function is not touched, because slice 1 depends on its
present behaviour and nothing about Mythic+ changes here.

`seconds_lost` is populated only where it is literally true — time dead, and time spent casting
nothing. It is left `None` everywhere else rather than filled with a plausible number, which is
the same discipline the confidence badges enforce.

---

## 8. The API surface

### 8.1 Queries this slice adds

| Query | Purpose | Measured cost |
| --- | --- | --- |
| `Report.rankings(playerMetric:)` | own ranks, whole roster | 2.0 |
| `table(DamageDone, viewBy: Target, sourceID:)` | target split, one player | 0.94 |
| `table(DamageTaken, viewBy: Ability)` | mechanics profile | 1.0 |
| `characterRankings(difficulty:, partition:)` | the parse sample | 0.0 |

Every per-fight and per-actor query slice 1 already sends — casts, deaths, damage taken, healing,
health samples, auras, resurrections, talents, abilities — works on a raid fight unchanged.

### 8.2 The ranking port widens

`domain/ports.py` declares `fastest_runs(encounter_id, keystone_level)` and
`top_parses(encounter_id, keystone_level, class_name, spec)`. `keystone_level: int` becomes a
type that expresses both axes, so that a raid caller cannot pass a keystone level and a Mythic+
caller cannot pass a difficulty. Which type is an open item (§14).

**Amended 2026-09-14 (§14 item 3): siblings, not a widened parameter.** No type replaces
`keystone_level: int`, because a union of two axis types leaves the wrong axis representable —
a Mythic+ caller can construct a raid axis and mypy accepts it, leaving a runtime guard as the
only defence, which is the "merely unlikely" item 3 rules out. Instead a second Protocol,
`EncounterRankingRepository`, takes the raid axis and returns raid row types.
`RankingRepository` is untouched; one adapter class implements both. A consumer typed against
the Mythic+ protocol cannot see the raid method at all, so the wrong axis is unrepresentable by
absence. This contradicts the paragraph above and follows the one below it — "siblings rather
than conditionals" — and applies plan 1's narrowing rule at the port.

The axis distinction dies at the adapter. Above it, one `ParseMember` and one `ParseSample`
serve both axes, because a member is read for only four things: `boss_seconds`, the roster, the
casts, and the row's `character_name`. `ParseMember` therefore stops holding a `Run` and holds
those values instead. `too_few`, `SAMPLE_SIZE`, `MIN_SAMPLE_FOR_AGGREGATE` and `can_aggregate`
are already axis-blind.

**A trap on that path.** The counting rule is
`casts_in(casts, actor_id, indices: frozenset[int])`, filtering on
`event.pull_index not in indices`. A raid cast carries `pull_index=None`, which is in no
frozenset, so handed a raid sample today it returns zero casts for every ability and every
player and raises nothing. `casts_in` must take a predicate, the shape plan 1 established with
`locate: Callable[[Death], str]`.

`rankings.py`'s `bracket_for`, `assert_bracket` and the `level < 2` skip gain raid siblings
rather than conditionals. The bracket assertion's reasoning carries over intact: an undocumented
off-by-one in `difficulty` would poison every comparison as surely as one in `bracket` would, so
the returned rows' `difficulty` is checked against the requested one and the code fails loudly on
a mismatch.

### 8.3 Ingest

`select_keystone_fight` gates every load path today and rejects a raid fight outright. A sibling
selector picks a raid fight: by `--fight`, or the only boss fight, refusing ambiguity rather than
guessing. It does not require `kill`, and it reads no keystone field.

---

## 9. Amendments to the master design

### 9.1 §5.5's "No damage ranking" does not reach raid

The master design states, in bold, "No damage ranking", and reasons: "Warcraft Logs deliberately
exports no per-boss Mythic+ damage metric because the unit of optimization is the whole dungeon.
Ranking individual throughput in Mythic+ invites exactly the behaviour this tool exists to coach
out."

Every clause of that reasoning is about Mythic+. Warcraft Logs exports `dps`, `bossdps` and
`rdps` per raid encounter, measured in §2.1, and on a fixed encounter individual throughput is a
unit of optimisation rather than a distraction from one. **The rule stands for Mythic+ and does
not bind slice 2.** `analyze` is unchanged.

What survives the amendment is the sentence after it, which is not about Mythic+ at all: damage
taken is reported per ability against a median, never as "avoidable damage". §6.8 holds to that.

### 9.2 §6.5 item 4's rejection of cooldown analysis does not reach raid

Reopened by §6.3, and only for a fixed encounter, where the sample supplies empirically what the
API does not publish. The rejection stands for Mythic+.

### 9.3 §7's removal of the parse percentile does not reach raid

The 2026-09-05 amendment removed the percentile because "nothing this project fetches produces
our own player's rank". `Report.rankings` does, measured in §2.2. The percentile returns for raid
under §6.7's constraints, and stays absent from the Mythic+ report.

---

## 10. The report

One self-contained HTML file, under every invariant the master design sets: no network at load,
no stylesheet link, no remote `src`, one inline script that shows, hides and highlights and does
nothing else. `tests/adapters/render/test_html_invariants.py` governs the raid report as it
governs the Mythic+ one.

Seven tabs: **Summary**, **Damage**, **Mechanics**, **Deaths**, **Interrupts**, **Players**,
**Provenance**. Route & tempo has no raid meaning and is absent.

The header prints boss, difficulty by name, kill or best percentage, and the partition.

The section registry is named in four places — `Report`'s required fields, the template's nav and
includes, `PLACEMENTS` in `report/ledger.py:42`, and `all_ledger_rows` in `report/model.py:712`.
A raid report needs a model of its own rather than empty stand-ins in the Mythic+ one; the shared
vocabulary beneath it — `LedgerRow`, `Badge`, `Tooltip`, `Section`, `ledger_row`,
`collapse_repeated_details`, `build_observations`, the macros, the CSS, the icon pipeline — is
reused whole.

---

## 11. Command line

```
uv run wowperf raid <url> [--fight N] [--player NAME]... [--all-players]
                          [--no-compare] [--cache-dir DIR] [--out DIR]
```

A sibling of `analyze`, not a mode of it. `analyze`'s flags are Mythic+-shaped, its fight
selection refuses a raid fight by design, and one command that silently does two different things
is worse than two commands that each do one.

`--player`, `--all-players` and `--no-compare` behave exactly as
`2026-09-10-per-player-parse-comparison-design.md` specifies, including its default: with neither
flag, `raid` compares the report owner alone. A twenty-player roster makes that default matter
more than it did at five.

**Amended 2026-09-14.** The flags select subjects for whichever comparisons exist. Under §15's
cut they first become live in plan 2, where they scope the mechanics comparison per player with
`sourceID`, and `--no-compare` skips fetching the reference kill. Plan 3 extends the same flags
over the parse axis. Plan 1 accepts all three and ignores them, saying so on every run.

Output is `<code>-<fight>.findings.json` and `<code>-<fight>.html` under `--out`, and the command
closes by printing what it spent from the hourly budget, dearest operation first.

`fetch` gains no raid sibling until something needs one.

---

## 12. Testing

Unit, integration and end-to-end, with no exceptions, as `CLAUDE.md` requires.

This repository's failure mode is a test that could never have failed, not a wrong
implementation. Twelve plan tasks have now produced defects of that shape and none of the other.
Every assertion in this slice is therefore written to fail against a deliberate mutation of the
arithmetic it claims to check, and any test that reads a table, a set difference or a ranked list
carries a guard asserting the collection is non-empty before asserting anything about its
contents.

Three specific traps:

- **A comparison finding that is withheld must be tested for the reason it gives**, not merely
  for its absence. A withheld finding and an unbuilt one look identical to a test that checks
  only that no row was printed.
- **The mechanics comparison must be tested against a reference whose ability set differs from
  ours in both directions** — abilities only we took, and abilities only they took. A fixture
  where the sets match tests nothing.
- **No real character name reaches `tests/`.** The sanctioned set is unchanged. Report
  `cW38jmwdnZfbHVL4` holds twenty real people; they are referred to by class, specialisation or
  role in code, tests, commit messages and documents, and `CLAUDE.md`'s list of such reports
  should gain this code.

End-to-end tests spend quota and stay behind `-m e2e`.

---

## 13. Risks

- **A wipe has no external reference, and readers will expect one.** The report must say why each
  external finding is withheld, in words, on the page. An empty section teaches nothing.
- **The mechanics comparison is only as good as its reference raid.** One reference is one guild
  on one night with one composition. The sampling design's rules apply: draw several, report a
  median with a range, and withhold below the floor rather than print a comparison worth nothing.
- **Difficulty is a confound the tool must declare.** A Heroic pull compared against Mythic
  parses is meaningless. Difficulty is matched exactly, never approximated, and a mismatch is
  refused rather than annotated.
- **Scope pressure from slice 3.** Raid-wide mechanics findings sit one short step from a wipe
  narrative. §3.2 draws the line; the implementation plan should quote it.
- **Twenty players cost more than five.** One cold `--all-players` run at five players spent
  190.90 points of 3600. The raid figure is unmeasured and must be measured before any claim
  about it is written down.

  **Amended 2026-09-14 (§14 item 6).** Projected, not measured, at roughly 730 points of 3600
  for the parse axis — 19 distinct specialisations, 5 references each, 7.29 points a reference.
  The mechanics comparison is not part of that figure: it scopes per player with `sourceID` at
  roughly a point each. The projection remains a projection and must not be stated as a
  measurement.

---

## 14. Open items, resolved

All nine were measured or decided on 2026-09-14, at a cost of 155 points against the
3600-an-hour budget. Every figure below was run, not read. Where a resolution contradicts an
earlier section, that section carries an inline amendment note pointing here.

1. **The damage-taken table's count fields — resolved.** `hitCount` counts direct hits,
   `tickCount` counts damage-over-time ticks, `missCount` and `tickMissCount` count attempts
   that did not land. No single field counts landings; an ability may carry both hit and tick
   counts. All four summed over one fight's 26 rows equalled the event count exactly, 11,456,
   difference zero. Landings are `hitCount + tickCount`. Dated rows reach
   `.claude/skills/wcl-api/SKILL.md` with the code that first selects them.

2. **`hostilityType`'s effect — resolved, and §2.5 was wrong.** It selects whose damage-taken is
   tabulated, not which sources are counted. Omitting it and passing `Friendlies` return
   byte-identical JSON; `Enemies` returns the enemy side of the fight. Friendly-sourced rows
   survive either way. Exclude them by the row's `sources[].type`.

3. **The ranking port — resolved as siblings.** See §8.2's amendment. No type replaces
   `keystone_level: int`; a second Protocol exists beside the first, and the wrong axis is
   unrepresentable because the method is absent rather than guarded.

4. **The reference sample for a wipe — resolved: there is none.** `Encounter.fightRankings` is a
   kill leaderboard under every metric it accepts. `default` and `speed` returned byte-identical
   row sets; `execution` is a deathless-kill board overlapping `default` on 7 of 50 rows;
   `progress` carries no loadable report code on 39 of 50 and is guild-progression bookkeeping.
   No row on any metric carries a `kill` field, a `fightPercentage`, or any percentage at all.
   **A wiping raid therefore has no external reference of a wipe, and the whole external frame
   is withheld for an attempt that did not kill.** The wipe is answered by the internal frame of
   §4 — §6.8 and §6.9 — which needs no external sample.

   The reference kills for §6.8 are drawn from `execution`, filtered to our own raid `size`,
   and there are `SAMPLE_SIZE` of them rather than one — see §6.8's amendment, which resolves a
   contradiction between §4 and §6.8 on one side and §13 on the other. Deathless kills are the
   better teacher for what a raid handling the boss cleanly actually ate, and `execution`'s
   longer durations — 60 to 100 seconds above `default`'s — normalise away under a per-minute
   rate.

5. **The default damage metric — narrowed to two, still open.** `rdps`, `ndps` and `cdps` are
   not World of Warcraft metrics: each describes itself in the schema as "unique to FFXIV", and
   `rdps` fails at the server. §2.1 is amended. `dps` and `bossdps` both return 100 fully
   populated rows; `bossdps` is 0.634 to 0.743 of `dps` for the same run, median 0.676, and
   reorders the board by a median of 21 positions, while the subject's own percentile moved only
   97 to 96. The choice belongs with the plan that builds §6.1, and it belongs in the report's
   own words.

6. **The cost of `--all-players` at twenty — projected, not measured.** A 20-player roster held
   19 distinct class and specialisation pairs, so a full-roster parse comparison draws 19
   samples. One reference fight cost 7.29 points measured across two real references, and a
   sample is five of them, so one sample is 37.46 and the roster is roughly **730 points of
   3600** — an upper bound assuming no two samples share a report. How much they overlap is
   unmeasured and would bring it down. **This cost belongs to the parse axis, not the
   mechanics comparison**, which scopes per player with `sourceID` at roughly one point each.

   Sizing note for whoever builds it: per-player *totals* for twenty players cost one query and
   1.00 point at `viewBy: Default`, but per-player *per-ability* costs twenty queries and about
   twenty points, because `abilities`, `sources` and `targets` are each capped at five rows.
   Aliasing twenty tables into one operation cost 20.05 — points are billed per table, not per
   request.

7. **`Report.rankings` for a wipe — resolved: zero rows.** A kill returned one row carrying
   `kill`, `difficulty`, `partition`, `size`, `bracket`, `duration`, `deaths`,
   `damageTakenExcludingTanks`, `execution`, `speed`, `roles`, `guild`, `encounter` and `zone`.
   The wipe returned an empty list. No field distinguishes the cases, so the code tests for
   emptiness and §6.7 states that no percentile exists rather than printing one.

8. **The duration gap for `casts.count` — resolved by removing the question.** Top five
   reference durations spread 33.9% of our own on one boss and 16.1% on another. No threshold a
   five-reference sample reliably clears, so the count half of §6.3 is not built and casts per
   minute is the only expression.

9. **Two tanks — resolved: not enough, tanks stay excluded.** See §6.9's amendment. The rule
   already existed as `MIN_PLAYERS_FOR_MEDIAN = 3`, and the measured spreads agree.

### 14.1 Facts measured on 2026-09-14 that no section above owns

- **The damage-taken table reports mitigated damage.** `total` equals the event stream's
  `health_damage + absorbed`; `totalReduced` equals `health_damage`. The unmitigated figure is
  not exposed and not reconstructible from the table. §6.8's amendment turns on this.
- **The table and the event stream can disagree on an ability's id.** One ability appeared as
  `guid 1302265` in the table and `abilityGameID 1287955` in the stream, the same 240
  occurrences. Joining the two endpoints on id drops rows silently — 1 of 26 on the fight
  measured.
- **A raid `size` confound the design did not record.** Ours is 20; the top five parse
  references were 22 to 30, the full parse board 11 to 30, and a single page of kill rankings
  spanned 14 to 30. Heroic is flexible-size and scales. Both ranking rows carry `size`, so
  matching it is free, and `compare.confound.raid_size` exists only for when no same-size
  reference is found.
- **The per-death healing fan-out can be replaced.** One fight-wide fetch cost 8.00 points over
  8 pages against the 21 per-death windows' 21.00, and the data was identical — symmetric
  difference zero against 1384 in-window events. Break-even is about eight deaths. **The obvious
  implementation is wrong:** the server-side filter `target.id in (...)` returns zero rows for
  one point, silently. This is a change to `repository.py` shared with the Mythic+ path and does
  not belong to any plan here.

---

## 15. How this slice is cut into plans

Plan 1, `2026-09-14-raid-foundation-plan.md`, is merged: `Encounter` beside `Run`, the shared
analysers narrowed, and `wowperf raid <url>` writing ranked findings for one boss fight.

**The remaining two plans were re-cut on 2026-09-14**, after §14 item 4 established that a
wiping raid has no external reference. The original order gave the external parse axis to plan 2
and the mechanics comparison to plan 3, which would have produced a tool good at kills and
silent on wipes — the opposite of what this slice is for. The wipe diagnosis lives entirely in
the internal frame of §4.

**Plan 2 — the internal frame.** §6.8 and §6.9, and §7's ranking. The damage-taken table scoped
raid-wide and per player; the per-ability profile against a sample of `execution` references of
matching size; the damage-outlier half split out of `analyse_players` and narrowed to take
`players`; the severity ranker. Works identically on a kill and on a wipe, and needs no parse sample.
Output stays findings JSON; §10's report is whole in plan 3.

§7's ranking is built here because this plan creates the need for it: these findings cost no
seconds, and `rank_findings` sorts by `seconds_lost` with every `None` falling to the bottom in
arbitrary order. The sibling ranker holds a severity table keyed by finding-id family, guarded
by a test that enumerates every family the raid path can emit. **No `severity` field is added to
`Finding`** — a required one touches every slice-1 analyser, which §7 says not to disturb, and
an optional one defaults quietly, which is this repository's documented failure mode.

**Plan 3 — the external frame and the report.** §6.1 to §6.7, §8.1, §8.2's parse half, and §10.
The `ParseMember` narrowing and the `casts_in` predicate described in §8.2's amendment belong
here, with the axis they serve. §14 items 5 and 6 are resolved by this plan.
