# Raid Analysis — Design

- **Date:** 2026-09-13
- **Status:** Proposed
- **Scope:** Second vertical slice of the `wow_perf` project

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
and `playerscore`, among others. Mythic+ uses `playerscore` from this same enum.
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

- **The damage-taken table includes friendly abilities.** Paladin damage transfers appeared as
  damage taken. `hostilityType` is the argument that excludes them; a name filter is not.
- **The hit count is wrong for damage over time.** One ability reported 3.1 million damage and a
  zero count, so the field read was not the one that counts ticks. The correct field names are an
  open item (§14) and must reach `.claude/skills/wcl-api/SKILL.md` with a date before use.
- **An unscoped table sums the whole raid.** One ability read 1068 hits per minute across twenty
  players. Per-player figures need `targetID`, which changes the claim from "we" to "you".

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
| **Internal** | the rest of the subject's own raid, and one reference raid's profile of the same boss | who took what, deaths, mechanics | no |

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

**The finding states hits and damage. It never states that a mechanic was missed.** "You took
four hits from Ravenous Feast; eighteen of twenty players took none" is a fact the reader
interprets. "You missed the soak" is a claim about intent that no table supports, and §5.5 of the
master design refuses exactly that inference. The badge is `measured` because what is printed is
counted, not judged.

Restricted to hostile sources by `hostilityType`, for the reason in §2.5.

### 6.9 `damage.taken.outlier` — `measured`

Damage per ability against the group median for that ability, as §5.5 specifies. Exists, is
generic. Its 2026-09-06 amendment excluded tanks because a keystone's single tank "has no honest
median to be measured against". A raid has two, so a tank median exists — drawn from one other
player. Whether two is enough to rank against is a judgement the finding must make out loud, and
§14 records it as undecided.

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

---

## 14. Open items for the implementation plan

1. **The damage-taken table's count fields.** Which field counts hits, and which counts ticks of
   a damage-over-time effect. Verify against the live API, then add a dated row to
   `.claude/skills/wcl-api/SKILL.md` before any code reads it.
2. **`hostilityType`'s exact effect** on the damage-taken table. Measure; do not assume.
3. **The type that replaces `keystone_level: int` in the ranking port.** It must make a wrong
   axis unrepresentable rather than merely unlikely.
4. **The reference sample for a wipe.** `fightRankings(metric: speed)` gives kills; whether
   `execution` or `progress` gives something better for a wiping raid is unexplored.
5. **Which damage metric is the default.** `dps`, `bossdps` and `rdps` answer different
   questions, and the choice belongs in the report's own words.
6. **The cost of `--all-players` at twenty.** Measure once, record the figure, and state it
   nowhere until then.
7. **Whether `Report.rankings` returns ranks for a wipe.** If it does, §6.7 extends to wipes; if
   it does not, the withholding must say so.
8. **The duration gap at which `casts.count` switches from counts to rates** (§6.3). Pick it
   against real reference durations rather than by eye.
9. **Whether two tanks are enough to rank one against the other** (§6.9). If they are not, tanks
   stay excluded from the damage-taken comparison as they are in Mythic+, and the finding says
   why.
