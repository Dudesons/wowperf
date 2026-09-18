# Wipe analysis: what failed on one boss fight

**Approved 2026-09-18.** Extends `2026-09-13-raid-analysis-design.md`. Supersedes nothing.

This is the first of several designs answering one batch of feedback on the raid reports. It
covers the per-fight failure analysis only. Section 2.2 names the sub-projects deliberately left
out, so an implementer reading this document does not build them by accident.

---

## 1. Purpose

A raid leader opens the report the morning after a wipe night and needs three answers:

1. **What do we drill next pull?** A short, ranked list of what cost the raid the most.
2. **Who needs to change?** Which players are taking far more of something than their raid is.
3. **Did we wipe on mistakes, or on a wall?** Execution and throughput want opposite fixes, and
   drilling mechanics wastes a night when the real problem is that the boss outlived the
   cooldowns.

A fourth question — *are we getting better night over night?* — belongs to the progression page
and its repeat detection, and this design does not touch it.

---

## 2. Scope

### 2.1 In scope

One boss fight, kill or wipe, reached through the existing `wowperf raid <url> --fight N`
command. Three analysis components, one chart, and a redistribution of what the raid page
already shows across the tabs it already has.

### 2.2 Out of scope

Each of these is its own design, plan and implementation cycle. None of them is blocked by this
one, and this one is blocked by none of them.

| Deferred | Why it is separate |
| --- | --- |
| A navigation shell indexing every fight across every night | A new artifact type, a new filename scheme, and cross-page links that nothing emits today. Scaffolding is worth building once the pages it links to are right. |
| Roster ready check — flasks, food, enchants, gems, tier | Self-contained, reads gear and auras rather than damage, and shares no code with this. |
| Booster-log exclusion from reference samples | A predicate on reference selection. `ReferenceKillRow.deaths` already carries a free first-order signal; timing needs a query per candidate. |
| Raid Players-tab parity with the Mythic+ report | A port of comparison families that already exist. `comparison_tables` is empty on the raid path because the measures need a `LoadedRun` the raid path never holds — see `raid_build.py:89-98`. |
| Hand-written per-encounter mechanic definitions | Explicitly declined for now. Section 4.2 records the ruling and the seam left for it. |

---

## 3. What already exists

An implementer must read this section before writing code. Three of the four things this design
needs are already built, and the fourth is half built.

### 3.1 The ranked list is half built

`compare_mechanics` in `src/wowperf/domain/comparison/mechanics.py` already produces
`mechanics.ability.<rank>` findings, badged `derived`. It states landings per minute on our side
and the reference side, sorts candidates by the size of the gap, caps at
`MAX_MECHANICS_REPORTED = 5`, and numbers each finding by where it landed on the page rather than
where it was built. `_worth_reporting` admits a candidate when the reference rate is zero or our
rate is at least `MECHANIC_MULTIPLE = 2.0` times theirs. Below `MIN_SAMPLE_FOR_AGGREGATE = 3`
comparable references it compares against a single reference kill and the finding says so.

**Rate-normalising by duration is what makes a wipe comparable to a kill at all**, and it is
already there. Do not reimplement it.

`mechanics.py` is already the raid module. `compare_mechanics` has exactly one caller —
`encounter_service.py:117` — and `ReferenceKillRow`'s docstring records that it carries no
keystone level, bracket or affixes because a boss fight has none. There is no Mythic+ caller to
protect and no reason to fork a raid variant.

### 3.2 The per-player comparison is already built

`src/wowperf/domain/analysis/damage_outliers.py` computes one player's total from one ability
against the median of the players who took it. Its ABOUTME says it "reads a roster and a set of
hits, never a Run, so a boss fight can reuse it", and the raid ledger already routes its
`players.damage.*` findings. It is role-aware, knowing which specialisations tank.

Constants: `MEDIAN_MULTIPLE = 2.0`, `MIN_PLAYERS_FOR_MEDIAN = 3`, `MAX_OUTLIERS_REPORTED = 5`.

**What is missing is the table, not the analysis.** The findings name the worst five; nothing
renders the full grid, and nothing slices either by phase.

### 3.3 Phases are modelled, ingested, and displayed nowhere

`src/wowperf/domain/phases.py` models `Phase{id, name, is_intermission}` and
`PhaseTransition{id, start_ms}`. `build_phases` ingests them at `ingest.py:239`, and
`last_phase`, `last_phase_is_intermission` and `phase_transitions` land at `ingest.py:301-307`.
`FIGHTS_QUERY` already selects them, so **phases cost nothing**.

Their only consumer is `progression_repeats.py:43`. No report displays a phase.

### 3.4 Charts have a proven pattern

`src/wowperf/domain/report/progression_chart.py` builds inline SVG inside the domain layer,
tested, feeding the progression page's Attempts chart. The report's one inline script may show,
hide and highlight what is already on the page; it may not draw. Any chart this design adds is
built in Python and shipped as markup, exactly as that one is.

### 3.5 The data is already fetched

`repository.py:429` pages the full damage-taken event stream on the raid path and
`build_damage_taken` (`ingest.py:513`) keeps every event. `DamageTakenEvent` carries:

`actor_id`, `ability_id`, `ability_name`, `amount` (unmitigated), `timestamp_ms`, `pull_index`,
`health_damage`, `absorbed`, `mitigated`, `overkill`, `source_id`, `is_area`, `is_tick`,
`buff_ids`.

So per-player landings, per-ability damage, phase attribution by timestamp, and what a player had
up when a hit landed are all available **without a single new query**.

`queries.py` also defines `ABILITY_TAKEN_BY_PLAYER`, a `sourceID`-scoped damage-taken table,
deliberately unwired. Its comment explains why, and that reasoning still holds: a per-player
reference side would need one query per reference player, which is five kills times twenty
players. **Leave it unwired.** This design needs nothing from it.

---

## 4. Standing rulings this design does not overturn

### 4.1 The tool never says a mechanic was missed

`compare_mechanics`'s docstring states it, and master design §5.5 is the authority:

> Damage taken is reported as damage per ability against the group median for that same ability,
> never as "avoidable damage". Deciding whether a hit was avoidable needs per-mechanic knowledge
> this slice does not have, and guessing at it would produce exactly the confident nonsense the
> confidence badges exist to prevent. Taking three times the group median from one ability is a
> fact the reader can act on without the tool pretending to know why.

A damage-taken table cannot distinguish a player who stood in something carelessly from one who
soaked it deliberately. **The page describes damage and never assigns intent.**

Note that §5.5 already specifies this design's per-player comparison — a player against the group
median of the same ability — and `damage_outliers` already implements it. Section 7 extends the
presentation, not the ruling.

### 4.2 No per-encounter mechanic definitions

Hand-written encounter files in `data/` would let the page say "soaked" and "stood in", and would
let a red cell honestly mean a mistake. They were considered and declined: someone maintains them
per boss per tier, and a stale file mis-judges silently.

**The seam:** every finding this design adds states its ability by id and name, and its measure as
a count or an amount. An overlay adding a verb and an expected count later changes the wording
layer only. No analyser needs reworking to accept one.

### 4.3 One unambiguous exception: deaths

Nobody dies to a mechanic on purpose. Where §5.5 refuses a verdict on damage, a death carries one
without inventing intent. This is the only place the page judges rather than describes, and
section 8 confines it.

### 4.4 No percentile against a population

Warcraft Logs ranks kills, and a percentile — "better than 75% of guilds" — needs a corpus of
other players' logs that RPGLogs terms §5d forbid accumulating. Comparison stays what this project
does everywhere: five references, a median and an observed range, never a mean.

### 4.5 Our damage figure never sits beside theirs

Our events carry the unmitigated amount. The reference side is a `viewBy: Ability` table whose
figure is mitigated, and `AbilityTakenRow`'s docstring records those two measured **4.61× apart**
on a real fight. Therefore:

- **Cross-raid comparison uses landings per minute, never damage.** This is what
  `compare_mechanics` already does.
- **Damage figures appear only on our own side of the page**, in the per-player grid, where every
  number comes from the same event stream.

Section 12 requires an invariant test for this, because a rule living only in a docstring is a
rule that gets broken.

---

## 5. Data

| Needed | Source | Cost |
| --- | --- | --- |
| Our per-player, per-ability landings and damage | `DamageTakenEvent` stream, already fetched | none |
| Reference kills' per-ability landings | `AbilityTakenRow` tables, already fetched, five kills | none |
| Reference kills' death counts | `ReferenceKillRow.deaths`, already on the row, **read by nothing today** | none |
| Reference kills' durations | `ReferenceKillRow.duration_ms` | none |
| Our deaths and resurrects | streams already fetched for the Deaths tab | none |
| Boss health remaining | `ReportFight.fightPercentage`, verified 2026-09-14 | none |
| Phase names and transitions | `Report.phases`, `phaseTransitions`, already in `FIGHTS_QUERY` | none |
| Continuous boss-health curve | **unverified — see section 14** | unknown |

A full `raid --fight N` with comparison measured **76.96 points** of the 3600-point hour. This
design adds nothing to that except, possibly, the boss-health curve.

---

## 6. Component one — the ranked list

**Answers:** what do we drill next pull?

**`compare_mechanics` keeps its current contract unchanged.** Its comparison stays whole-fight,
because the reference side cannot be split by time — see section 9. Everything it does well stays:
the rate normalisation, the sort, the cap, the rank numbering, the single-reference fallback.

What it gains is descriptive, on our side only: a finding may name the phase its landings
concentrated in, drawn from our own timestamped events. That is context attached to a whole-fight
comparison, never a phase-against-phase claim.

Add one new function beside it, because it reads data `compare_mechanics` has never seen:

**`mechanics.lethal.<rank>`** — abilities that killed our players, against the same ability in the
reference kills. Reads the deaths stream. States our death count from that ability and the
reference kills' total death counts. Badge `derived`.

This is the finding that carries weight under ruling 4.3: *"Caustic Waves killed 4 of ours; the
five reference kills lost 0 to 3 players in total."*

---

## 7. Component two — the per-player grid

**Answers:** who needs to change?

### 7.1 The table

One row per player, each cell a player's total from one ability against the median of the players
who took it — §5.5's measure, which `damage_outliers` already computes.

**The columns are named, not open-ended:** the abilities the ranked list reports, plus any ability
that killed someone, capped at `MAX_MECHANICS_REPORTED` columns. An ability nobody died to and
nobody took unusually much of earns no column. This keeps the grid readable at twenty rows and
ties it to the same ranking the rest of the tab uses.

The table is a **view model, not findings.** Twenty players by a dozen abilities is 240 cells; as
findings that is outstanding item #3 again, five times worse. It renders like the Mythic+ Players
tab's `comparison_tables` — a `<details>` block of `ComparisonRow`s — reusing that pattern rather
than inventing a second one.

### 7.2 The findings

`players.damage.*` already mints the worst five and caps there. Keep the cap. Section 12 requires
it to be asserted rather than assumed.

### 7.3 What a cell means

A red cell means **"this player took far more of this than their raid did"**. It does not mean a
mistake. The page must say so where a reader will see it, not only in a design document: taking a
tankbuster is correct, and taking soak damage is doing the job.

### 7.4 Defensives at the moment of a hit

`buff_ids` on each event records what the player had up when it landed. This makes "a hit landed
with nothing mitigating it" **measurable** rather than inferred, and it is the honest neighbour of
the claim §5.5 forbids.

It is also the thread back to outstanding item #3. `defensives.never` currently reports defensives
nobody pressed all fight, with no idea whether pressing one would have mattered — which is why it
reached 29 of 55 findings on a real Mythic report and drowned everything else. Tied to the moment
of a lethal hit, the same data becomes specific and rankable.

---

## 8. Component three — the verdict

**Answers:** execution or throughput?

### 8.1 The finding

**`wipe.cause`**, badge `inferred` — the only inferred finding in this design, because it is the
only judgement. It states its reasoning, never only its conclusion. It withholds on a kill.

### 8.2 Evidence

Four measured facts:

1. Players alive when the attempt ended, against raid size.
2. Boss health remaining, from `fightPercentage`.
3. Our duration against the five reference kills' median duration.
4. Our death count against theirs, from `ReferenceKillRow.deaths`.

### 8.3 The four outcomes

| Reading | Verdict |
| --- | --- |
| The raid was dismantled before the end | **Execution** |
| The raid stood, boss health stayed high, our duration met or passed their median | **Throughput** — nobody died and it still was not enough |
| Both | **Say both, and say which came first.** A raid that loses five people early and then limps is an execution failure that caused a damage shortfall; flattening that to one word would be wrong |
| The signals conflict | **Withhold**, and record why in Provenance |

Withholding is this project's existing habit and this design does not break it for a headline.

### 8.4 The chart

A wipe is a race between two health bars. Players alive over time is a step function from the
deaths and resurrect streams — free and certain. Boss health is the unverified half.

**Build the chart on the certain series, annotating boss health at the end point.** Add the curve
only if section 13's measurement says it is available and cheap. One real series beats waiting on
a field nobody has confirmed.

---

## 9. Phases

Phases slice all three components. They are not a component themselves.

Slicing means two things. Every finding in section 10 that names a moment also names the phase it
fell in, where the encounter has phases. And one new family rolls that up:

**`mechanics.phase.<rank>`** — where in the fight the cost concentrated. States a phase by its
API-supplied name and what it cost us. Badge `derived`. Built beside `compare_mechanics`, and
withheld entirely when `separatesWipes` reads false or the encounter has no phases.

**There is no cross-raid phase comparison, and there cannot be a cheap one.** The reference side
is an `AbilityTakenRow` table — a whole-fight aggregate carrying no timestamps. Knowing when a
reference kill's phases began would not help, because its landings cannot be split by time at all.
Splitting them would need each reference kill's own event stream, which is both expensive and a
step toward the corpus RPGLogs §5d forbids. **Phase attribution therefore describes our attempt
only.** A phase finding says where our cost fell; it never says the reference kills differed.

**Gate every phase claim on `separatesWipes`.** Warcraft Logs states whether phase is a meaningful
way to group an encounter's attempts, and where it says no, the page groups by nothing.

Three properties are documented in `.claude/skills/wcl-api/SKILL.md` and each is a trap:

- **`phaseTransitions` is not a ladder.** One encounter's transitions ran `1, 2, 1, 2, 1`. Neither
  the last phase nor the highest reached means progress.
- **Read `lastPhase`, never `phaseTransitions[-1].id`.** Encounter 3470 reports `lastPhase: 2`
  against transitions ending in 3. Unexplained, and recorded rather than guessed at.
- **`lastPhase: 0` means a boss with no phases**, not a missing reading.
- **`lastPhaseAsAbsoluteIndex` is not a phase id.** It indexes `phaseTransitions`, and reading it
  as a phase id was wrong on 5 of 8 encounters measured.

Phase names come from the API. **Encode no phase table** — `phases.py`'s docstring and raid design
§3.3 both forbid it.

---

## 10. Finding families

| Family | States | Badge | Status |
| --- | --- | --- | --- |
| `mechanics.ability.<rank>` | landings per minute, ours against theirs | `derived` | exists; gains phase attribution |
| `mechanics.lethal.<rank>` | deaths caused, ours against theirs | `derived` | new |
| `players.damage.*` | a player's total against their raid's median | `derived` | exists; gains phase attribution |
| `mechanics.phase.<rank>` | where in the fight the cost concentrated | `derived` | new |
| `wipe.cause` | execution, throughput, both, or withheld | `inferred` | new |

Every finding carries a badge. A finding without one is a bug.

---

## 11. Page layout

**The tab count stays at seven.** The raid page already carries Summary, Damage, Mechanics,
Deaths, Interrupts, Players and Provenance, and part of the complaint behind this design is that
the page is hard to read. An eighth tab beside a Mechanics tab doing half the same job would make
that worse.

- **`wipe.cause` headlines Summary.** Summary is the landing tab, and outstanding item #5 is that
  a landing tab reading as a null result at first glance is bad. A verdict at the top replaces a
  list with an answer.
- **Mechanics absorbs the rest** — the ranked list it already half-builds, then the lethal
  abilities, then the per-player grid, then the phase strip.
- **The two-bar chart sits under the verdict on Summary**, where it explains it.

Adding nothing to the shell keeps the tab machinery untouched: it is pure `data-tab-group` /
`data-tab-for` / `data-tab-panel` attributes driven by `report.js.j2`, and no JavaScript changes.

---

## 12. Testing

Every plan in this repository has failed the same way: tests that could not fail, while the code
was right. The traps below are specific to this feature and each one needs an assertion that dies
if the behaviour it names regresses.

**The mutation rule applies throughout: no assertion may survive deleting the arithmetic or the
string it claims to check.**

### 12.1 The verdict has four branches

A `wipe.cause` that always withholds passes any test that only checks a finding was produced.
Each branch needs a fixture producing **that branch and provably not the others**, and the
withheld case needs a test that fails if the verdict starts firing on conflicting signals.

### 12.2 Phases are not a ladder

Required fixtures: non-monotonic transitions (`1, 2, 1, 2, 1`); `lastPhase: 0`;
`separatesWipes: false`; and an encounter whose `lastPhase` disagrees with its last transition, so
a test fails if someone reaches for `phaseTransitions[-1].id`.

### 12.3 The enum axis

Every fixture in this repository to date used difficulty 4, and that is exactly what took `raid`
down on every Mythic fight. Reference-kill fixtures in **both shapes** — carrying `size` and
omitting it — and the end-to-end test exercised at **both difficulties**.

Report `DJfap6RcYKhPGHXZ` holds one encounter at difficulty 4 and one at difficulty 5, which makes
it the right end-to-end subject. **Its roster are real people.** If its data reaches the
repository, add its code to `CLAUDE.md`'s real-people list alongside `6Kx1P9GbNXrcLdHa` and
`cW38jmwdnZfbHVL4`, and refer to its players by class, spec, role or index everywhere.

### 12.4 A fixture constraint that bites at task one

Tests may carry no real character name, and the sanctioned set is four: `Emberkin`, `Stonewake`,
`Bríala`, `Кириллица`. **A twenty-player grid cannot be built from four names.** Grid fixtures
refer to players by role and index throughout.

### 12.5 The mitigated/unmitigated invariant

An invariant test, in the shape of `test_raid_html_invariants.py`: no finding carries our
unmitigated figure and a reference table's figure together.

The same test guards the other comparison that cannot honestly be made: **no finding may state a
phase and a reference figure together.** Section 9 forbids it because their table carries no
timestamps, and a phase-scoped finding that grew a reference side would be wrong in a way no
reader could detect.

### 12.6 A bound on the grid's findings

Outstanding item #3 is a family reaching 29 of 55 findings because nothing capped it. Assert the
cap, with a fixture that would blow past it.

### 12.7 Coverage

Unit, integration and end-to-end, with no exceptions. No test asserts mocked behaviour, and no
end-to-end test mocks anything. Golden files for the raid page will churn; that churn is the
regression net, not a nuisance.

---

## 13. Open measurements

Both are cheap, and both are taken before the plan is written rather than during implementation.

1. **Is a continuous boss-health series available, and what does it cost?** The end point is
   certain from `fightPercentage`. If the curve costs a query per fight, weigh it against drawing
   the certain series alone. Record the reading in `.claude/skills/wcl-api/SKILL.md` with its date
   and population, whichever way it goes.
2. **Does `separatesWipes` vary across the current tier's encounters?** Section 9 gates every
   phase claim on it, and if it reads `false` widely the phase strip serves fewer bosses than this
   design assumes.

---

## 14. What this design refuses to do

Stated plainly, so nobody implements them by accident:

- **Say a mechanic was missed, or that a player made a mistake.** Ruling 4.1.
- **Score a mechanic against a population of other guilds.** Ruling 4.4.
- **Encode a phase table or a per-encounter mechanic table.** Rulings 4.2 and section 9.
- **Put our damage figure beside a reference's.** Ruling 4.5.
- **Compare one of our phases against a reference kill's same phase.** Section 9: their table
  carries no timestamps, so their landings cannot be split by time at any price worth paying.
- **Fetch per-player tables for reference kills.** One hundred queries, and the reason
  `ABILITY_TAKEN_BY_PLAYER` stays unwired.
- **Compute anything in the report's inline script.** It shows, hides and highlights. It does not
  draw, fetch, or calculate.
