# Progression Analysis — Design

**Status:** Approved 2026-09-16. Slice 3 of four. This design covers **one piece** of slice 3 —
a night of attempts on one boss, read as a series. The other two pieces slice 3 owns, the
single-wipe diagnosis and the causal narrative, are named in §3.2 and are not built here.

**Spec lineage.** `docs/plans/2026-09-03-mplus-postmortem-design.md` is the master design and
remains the authority on architecture. `docs/plans/2026-09-13-raid-analysis-design.md` is slice
2, complete and merged; its §3.2 draws the line this design stands on the other side of. Where
this document and slice 2 overlap, this one governs the progression command and slice 2 governs
the single-fight command.

---

## 1. Purpose

A guild pulls a boss fifteen times in a night and wants to know one thing: **are we getting
anywhere.** The tool answers with three claims, in descending order of how well the log
supports them — where the attempts sit, what repeats across them, and what was different about
the best one.

It refuses a fourth claim it is often asked for: a trend line. §2.3 records why.

---

## 2. Verified context

Every figure here was measured on 2026-09-16 against the live API. Nothing in this section is
projected, and the two projections this document does make are labelled as such in §7.3.

### 2.1 The phase vocabulary exists, and we encode none of it

Introspected 2026-09-16. `ReportFight` carries 43 fields, among them `lastPhase`,
`lastPhaseAsAbsoluteIndex`, `lastPhaseIsIntermission`, `phaseTransitions`, `bossPercentage` and
`wipeCalledTime`. `Report.phases` returns `[EncounterPhases]`, where `EncounterPhases` is
exactly `{encounterID, separatesWipes, phases}` and `PhaseMetadata` is exactly
`{id, name, isIntermission}`. `PhaseTransition` is exactly `{id, startTime}`.

**This dissolves the tension §3.3 of the raid design created.** That section forbids "no
per-encounter rules, no phase table, no mechanic list", and a phase-aware report appears to
need one. It does not: the API names the phases and we read the names. We encode nothing, and
a boss the API says nothing about draws no phase claim at all.

`.claude/skills/wcl-api/SKILL.md` carries the full field list and the dated introspection.

### 2.2 `separatesWipes` is the API's own opinion, and it varies

Measured across one report's six phase entries: True for two encounters, False for a third.
Warcraft Logs is stating whether phase is a meaningful way to group attempts on that encounter.
**Every phase claim in this design is gated on it.** Where it is False, the report carries depth
and duration and says nothing about phases.

`phaseTransitions` is not a ladder. One encounter's transitions ran `1 -> 2 -> 1 -> 2 -> 1`, and
another ran `1 -> 2 -> 1 -> 3 -> 1`. On such an encounter neither the last phase nor the deepest
one means progress, which is the same fact `separatesWipes` reports from the other side.

### 2.3 Progression is not monotonic, and this is the finding that shapes the design

Measured on a real eight-attempt night, no kill. Boss health remaining at each attempt's end, in
the order they were pulled:

| Attempt | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Remaining | 64.81 | 85.80 | **16.49** | 85.40 | 87.65 | 53.30 | 55.65 | 100 |
| Duration (s) | 215.7 | 105.9 | **480.0** | 110.0 | 88.0 | 278.8 | 227.0 | 15.8 |

The deepest attempt was **third of eight**. Five pulls followed it without coming close, two
recovered partway, and the night ended on a 15.8-second reset.

**A raid that pushes deep and then does not repeat it is the normal shape of progression, not a
decline.** A regression line fitted to this data would report a trend, and the trend would be an
artefact. The tool therefore states where attempts cluster and what the best one reached, and
never extrapolates a slope. §5.1 carries the finding that says so out loud.

### 2.4 `fightPercentage` counts down

A kill reads `0` or `0.01`; an attempt that ended immediately reads `100`. It is health
remaining, not progress made. `Encounter.fight_percentage` already documents this correctly and
this design keeps that meaning.

`bossPercentage` is a different figure and the two diverge sharply: one attempt read
`fightPercentage` 51.12 against `bossPercentage` 3.76. **Every printed percentage names which
one it is.** Where they disagree by more than a stated margin the report shows both, because a
raid that pushed the boss to 3.76% on an encounter still reading 51.12% overall has learned
something the single figure hides.

### 2.5 The log does not attribute a death to a player

Measured against a fight known in advance to contain a player-caused death, reported by a raider
who was there. Across all 15 deaths, `killerID` was a friendly player **zero** times; where it
is set it names an enemy actor, and it is `None` on 7 of the 15. The killing blow on the death in
question is credited to the boss.

The causal chain — one raider passes a mechanic to another, the damage that follows is credited
to the encounter — is **reconstructed, never read**. §9.1 carries this as the design's first
risk, with the measurement that must precede any attempt to build it.

### 2.6 Damage events name their source; our ingest discards it

Every one of 2009 damage-taken rows on one wipe carried `sourceID`. **357 rows (17.8%) came from
a friendly player, across 6 distinct abilities.** `DamageTakenEvent` in
`src/wowperf/domain/events.py` keeps the victim and drops the source, so the signal is present
in the API and absent from the domain.

Self-damage (`sourceID == targetID`) is class mechanics and is excluded wherever this design
counts player-sourced damage.

---

## 3. Scope

### 3.1 In scope

**Every attempt on one boss, at one difficulty, from one report**, read against each other.
Three layers of claim, three fetch depths (§4.1).

A kill stays in the series. Two wipes and a kill is the shape worth showing, and one encounter
in the probed report had exactly it.

### 3.2 What this takes from slice 3's other pieces, and what they keep

The raid design gives slice 3 five things: why an attempt ended, which phase it ended in, what
the raid was doing when it collapsed, progression across a night's attempts, and any claim about
causation between players.

**This design builds the fourth**, and takes the second only as a counted fact (`lastPhase`,
gated on `separatesWipes`) because the API hands it over for the price of a field.

**The single-wipe diagnosis keeps** the anatomy of one attempt: why it ended, what the raid was
doing in its last seconds, the reconstruction of the collapse. Layer 2 of this design counts what
repeats across attempts and stops. Where Layer 2 wants to explain a single attempt, it links to
`wowperf raid --fight N`, which already renders it in seven tabs.

**The causal narrative keeps** any statement that one raider's action caused another's death.
This design measures co-occurrence, badges it `inferred`, and uses no causal verb (§5.2, §9.1).

### 3.3 Out of scope

- **Encoding any boss.** No per-encounter rules, no phase table, no mechanic list. Phase names
  come from the API or the claim is not made.
- **Naming a mechanic as missed.** The raid design's §6.8 line holds here unchanged.
- **Any external reference.** The series compares attempts to each other. Drawing a parse sample
  per attempt is the one shape that would make this command expensive (§7.3).
- **Several bosses at once.** One command invocation reads one boss.
- **Several reports at once.** §9.6 records what this costs.
- **Healer throughput.** Slice 4.
- **Mythic+.** Nothing in `analyze` or `raid` changes behaviour.

---

## 4. Domain model

### 4.1 Three layers, three fetch depths

The structure of the command falls out of what each claim needs.

| Layer | Claim | Needs | Cost |
| --- | --- | --- | --- |
| 1 | Where attempts sit | Fight metadata | One `Fights` query, whole night |
| 2 | What repeats | Deaths, damage taken, debuffs per attempt | N attempts |
| 3 | What the best attempt did differently | One attempt's internal frame | 1 |

Layer 1 is effectively free: every figure in §2.3's table arrived in a single query. `Progression`
is therefore cheap to build, and `LoadedProgression` deepens only the attempts a layer asks for.

### 4.2 The aggregates

`Progression` (`src/wowperf/domain/progression.py`) holds `report_code`, `encounter_id`,
`boss_name`, `difficulty`, `size`, `phases: tuple[Phase, ...]`, `separates_wipes: bool`, and
`attempts: tuple[Encounter, ...]` ordered by start time.

`LoadedProgression` holds `progression: Progression` and
`loaded: tuple[LoadedEncounter, ...]` — the subset deepened, not necessarily all of them.

`Phase` is `{id: int, name: str, is_intermission: bool}`, read from `Report.phases` and matched
on `encounter_id`. A boss the API lists no phases for gets an empty tuple, and every phase claim
goes silent. Two of the eight bosses in the probed report were such bosses, so this path is
exercised by real data rather than defended against in the abstract.

**`Encounter` is reused unchanged in meaning and gains four optional fields**: `boss_percentage`,
`last_phase`, `last_phase_is_intermission`, and `phase_transitions: tuple[PhaseTransition, ...]`.
Each is `None` or empty where the report is silent, which is the discipline `fight_percentage`
already follows.

`LoadedEncounter` gains nothing. What Layer 2 needs from the debuff stream is a new field on a
new event type (§4.4), not a change to the existing aggregate's meaning.

### 4.3 Which attempts are in the series

Same `encounter_id`; **same difficulty**, never mixed, because a Heroic pull is not evidence
about a Mythic one and slice 2 already refuses that comparison; above the duration floor; ordered
by start time.

**The duration floor is measured, not chosen.** Three attempts in the probed report ran 15.8s,
17.1s and 25.4s at or near 100% remaining — resets and instant disasters, not pulls a night's
shape should be read from. `MIN_PACK_SECONDS` in the keystone path was measured against 98 cached
pulls before its value was set, and this floor gets the same treatment: the plan measures a
population of real attempts and records the reading with its date before the constant exists.

An attempt below the floor is counted and reported (`progression.attempts.discarded`), never
silently dropped.

### 4.4 The player-sourced damage seam

`DamageTakenEvent` gains `source_id: int | None`, defaulting to `None`. Where it is a friendly
player and not the victim, the hit is player-sourced.

The debuff stream is new to this project. `PlayerDebuffEvent` carries
`{source_id, target_id, ability_id, ability_name, kind, timestamp_ms}` where `kind` is the event
type the API reports (`applydebuff`, `refreshdebuff`, `applydebuffstack`, `removedebuff`). It is
fetched only for attempts Layer 2 deepens, and only §9.1's measurement decides whether anything
is built on it.

---

## 5. Analysers

All progression findings cost no seconds, so they are ranked by the severity table slice 2 built
rather than by `seconds_lost`. §6 covers the vocabulary that table gains.

### 5.1 Layer 1 — where attempts sit

- **`progression.best`** — which attempt went deepest, what it reached, how long it lasted.
  `measured`.
- **`progression.cluster`** — the median depth across qualifying attempts and the observed range,
  never a mean. `measured`. This is the project's house style for every sample it reports.
- **`progression.movement`** — whether the later attempts sat deeper than the earlier ones.
  `derived`, because splitting a night into halves is a modelling choice that could be wrong,
  and the finding says so in its own words.
- **`progression.attempts.discarded`** — how many fell below the floor and why, so a reader can
  see what was excluded.

**`progression.movement` must be able to say nothing.** "No movement we can distinguish" is a
first-class result, and a tool that manufactures a slope rather than reaching it is worse than
one that stays quiet. Below a stated minimum of qualifying attempts the finding is withheld
entirely, in the same words the keystone comparison uses when its sample falls below three.

**What §2.3's night actually reports, computed rather than assumed.** Its seven qualifying
attempts split into half-medians of 64.81 and 55.65, so the later half sat **9.16 points
deeper** and the finding says so. That is not a contradiction of §2.3: the deepest attempt is
still the third of eight, and the raid never came close to it again. Stating a gap between two
halves and extrapolating a slope are different claims, and only the second is forbidden. A
reader told "later attempts sat deeper by nine points" and "the best attempt was your third"
has both facts and can hold them at once, which a trend line would not allow.

### 5.2 Layer 2 — what repeats

- **`progression.repeat.phase`** — how many attempts ended in the same phase. Gated on
  `separates_wipes`; silent where the API says phases do not separate wipes.
- **`progression.repeat.ability`** — an ability present in the run-up to the end of several
  attempts, stated as presence and a count. **Never as a mechanic failed.**
- **`progression.repeat.first_death`** — which role or specialisation died first, counted across
  attempts. A count, not an accusation.
- **`progression.collapse`** — seconds from the first death to the wipe. A slow bleed and a sudden
  detonation are different problems wanting different fixes, and the single figure that separates
  them is cheap.
- **`progression.player_sourced.<ability>`** — damage taken from a friendly player, counted per
  ability across attempts. `measured`, because the log states the source (§2.6). Subject to §9.1.

**The discriminator is the night itself, never boss knowledge.** An ability whose player-sourced
damage appears in the attempts that ended early and not in the deepest attempt is a real
within-night difference and may be named. An ability that appears in every attempt including the
best one is the encounter working as designed — a soak, a link, a controlled detonation — and the
tool stays quiet. The best attempt is the control, so no per-encounter rule is required.

**The confound is declared, not corrected**, in the house style of every comparison this project
ships: on some encounters player-sourced damage is correct play, and a raid soaking properly will
show a great deal of it.

### 5.3 Layer 3 — what the best attempt did differently

The deepest attempt's internal frame against the cluster's: deaths that did not happen before the
phase that usually ends the night, damage that did not arrive, a role still alive that usually is
not. Internal comparison only.

This layer names differences and does not explain them. Where a reader wants the anatomy, the
finding carries the `wowperf raid --fight N` invocation that renders it.

---

## 6. Ranking

Slice 2's severity ranker is reused and its table gains the `progression.*` families, guarded by
the test that enumerates every family the progression path can emit — the same guard the raid
path already carries.

**No `severity` field is added to `Finding`.** A required one touches every slice-1 analyser; an
optional one defaults quietly, which is this repository's documented failure mode. The raid design
settled this and nothing here reopens it.

---

## 7. The API surface

### 7.1 What is fetched

One query for the night: `Report.phases` and `fights` with `id, encounterID, name, difficulty,
size, kill, fightPercentage, bossPercentage, lastPhase, lastPhaseAsAbsoluteIndex,
lastPhaseIsIntermission, phaseTransitions { id startTime }, startTime, endTime, friendlyPlayers`.

Per attempt deepened: `events(dataType: Deaths)`, `events(dataType: DamageTaken)` keeping
`sourceID`, and `events(dataType: Debuffs)`. `EventDataType` offers fourteen values (introspected
2026-09-16 and recorded in the skill file); these are the three that earn their place.

### 7.2 One field this design refuses to use

**`wipeCalledTime` was `null` on all nineteen fights of the probed report.** It exists in the
schema and carries nothing in this data. Recorded here so that nobody rediscovers it and builds
the half-feature the skill file's opening warning describes.

### 7.3 Cost

**Measured 2026-09-16:** the whole day's investigation — four schema introspections, two fully
paginated event streams on a 20-player fight, and a report-wide fight listing — spent **14.04
points of 3600**.

**Projected, and labelled as a projection:** one `Fights` query for the night, then roughly 3 to
4 points per attempt deepened, putting an eight-attempt night near **40 to 60 points**. Against
slice 2's **measured** 877.74 for a cold `--all-players` raid, the progression command is an
order of magnitude cheaper, because it draws no external sample at all.

**The projection must not be stated as a measurement anywhere.** The raid design projected ~730
for a shape that measured 877.74, and recorded both; this design inherits that discipline.

---

## 8. The report

One page, five tabs — **Summary, Attempts, Repeats, Best attempt, Provenance** — built as slice
2's is: a frozen view model, a pure builder under `src/wowperf/domain/report/progression_*.py`,
and Jinja templates that loop and decide nothing.

**The Attempts tab is the spine and the reason to render a page at all.** One row per attempt in
pull order: depth reached, duration, phase ended in, deaths. A night's shape — the cluster, the
one attempt that went deep, the resets — is a visual fact and a poor paragraph.

**Its geometry is computed by the builder and emitted as SVG.** CLAUDE.md allows exactly one
inline script, which "may show, hide and highlight what is already on the page; it may not fetch,
write text". No charting library, no axes drawn in JavaScript. The keystone route timeline already
works this way.

**Phase colouring is gated on `separates_wipes`**, like every other phase claim.

**The page never redraws one fight's anatomy.** That is `wowperf raid --fight N`'s work and it
already does it. Keeping the two pages from becoming duplicate templates is a CLAUDE.md
prohibition, not a preference.

**The tab mechanism is inherited, and so is its obligation.** `data-tab-for="tab-X"` and
`data-tab-panel="main" id="tab-X"` are two hand-written halves matched only by string equality,
with nothing looping or counting them. The invariant tests that pin the id set are what make this
safe, and the progression page needs its own.

---

## 9. Risks

1. **The log does not attribute deaths to players (§2.5), and the reconstruction may not be
   separable from noise.** The debuff stream carried 610 player-to-another-player applications on
   one fight, and several of the most frequent ability ids resemble ordinary class debuffs rather
   than a passed mechanic. **The plan measures that composition across several fights and several
   encounters before building anything on it.** If a passed mechanic cannot be separated from a
   rogue's bleed without encoding boss knowledge, the feature is cut. It is not fudged, and it is
   not shipped behind a hedge.
2. **Small n.** Eight attempts is a small sample and a four-against-four split is smaller. State
   the count, and withhold `progression.movement` below a floor, exactly as the keystone
   comparison falls back below three comparable members.
3. **The duration floor is a magic number until it is measured.** §4.3 sets the obligation.
4. **`lastPhase` is a trap on a cycling boss.** Gated by `separates_wipes`, but anyone reading the
   raw field will be misled, which is why §2.2 records the two measured cycles.
5. **The two percentages disagree (§2.4).** Every printed figure names which one it is.
6. **One report is not always one night.** A guild logging two sessions into one report gets both
   in one series, and "did we improve" then spans a sleep. Detectable from gaps between attempt
   start times; the report declares it rather than guessing a session boundary.
7. **Scope pressure from the two pieces slice 3 keeps.** Layer 2 sits one step from the
   single-wipe diagnosis. §3.2 draws the line and the implementation plan quotes it, which is
   what slice 2's plan was told to do with the line drawn against it.

---

## 10. Testing

Unit, integration and end-to-end. No test type is ever "not applicable".

**The rule that decides quality here is the repository's own: no assertion may survive deleting
the arithmetic or the string it claims to check.** Every real defect slice 2 shipped into review
was a test that could not have failed, so the fixtures carry the burden.

- **The fixture's shape is the real shape.** Deepest attempt in the middle, per §2.3. A monotonic
  fixture never exercises the one behaviour this tool must get right.
- **A mutation flipping `fight_percentage`'s direction must fail a test.** It counts down, and
  reversing it inverts the report while leaving every page plausible.
- **Both guard states are present:** a boss with phases and one without, `separates_wipes` True
  and False, at least one sub-floor attempt, at least one kill in the series.
- **The golden page carries a night that varies.** Slice 2's Mythic+ golden held no reference run,
  so comparison wording could be mutated freely and the golden stayed green. The progression
  golden carries several attempts, a discarded one, and a phase-gated section in both states.
- **End-to-end against the real API**, on the eight-attempt night §2.3 measures.
- **No real character name reaches `tests/`.** The sanctioned set only.

---

## 11. Open items

1. **The composition of player-to-player debuff applications** (§9.1). Blocks Layer 2's
   player-sourced findings and nothing else.
2. **The duration floor** (§4.3). Blocks attempt selection.
3. **The margin at which `fightPercentage` and `bossPercentage` are reported separately** (§2.4).
4. **Whether a session gap should split a series or merely be declared** (§9.6). The design's
   position is declare; a measurement of real multi-session reports could change it.

Each is a measurement, not a debate. None may be settled by assumption.

---

## 12. How this slice is cut into plans

**Plan 1 — the series and Layer 1.** §4's aggregates, §4.3's measured floor, §7.1's single query,
§5.1's four findings, and the `Encounter` fields of §4.2. Ends at findings JSON. Needs no new
event stream and no report.

**Plan 2 — Layer 2, and the seam of §4.4.** The deaths, damage-taken and debuff streams per
attempt; §5.2's findings; §6's severity vocabulary. **Opens with §9.1's measurement**, and its
first task is to settle open item 1 before any code depends on the answer.

**Plan 3 — Layer 3 and the report.** §5.3 and all of §8.

Plan 1 is the only one that can start today. Plans 2 and 3 each begin with an open item this
design deliberately leaves unmeasured, because measuring them needs the fetch path plan 1 builds.
