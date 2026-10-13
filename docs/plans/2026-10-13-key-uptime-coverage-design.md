# Uptime over the whole key: buffs, and debuff coverage and reach on every enemy

**Status:** approved design, 2026-10-13. Not yet planned or built.
**Area:** the Mythic+ uptime families. It builds on the boss debuff figure of
`docs/plans/2026-10-07-enemy-debuff-uptime-design.md` and its council extension
`docs/plans/2026-10-08-council-debuff-coverage-design.md`. It supersedes both wherever they say
trash is not measured or the debuff figure is boss-only, and it supersedes the buff uptime rule of
`dec758f` (2026-09-05), which measured buffs over boss pulls only. Raid is untouched.

## 1. Why

Both uptime tables read boss pulls only. A Mythic+ key is mostly trash: over the 265 cached trash
pulls measured on 2026-10-13, a trash pull ran a median 129 s, and a key holds many of them. A player can keep a buff or
a debuff up on every boss and still drop it on half the key, and today the page cannot say so.
RwlRwlRwlRwl noticed the buff side first, as "uptime used to be on the whole dungeon".

The questions the page should answer, in RwlRwlRwlRwl's words: do I have good debuff uptime, and is
the debuff spread to every mob, or to most of them? No per-mob figures.

## 2. Decisions

RwlRwlRwlRwl decided each of these on 2026-10-13.

1. **Both families.** Buffs and debuffs both gain an Overall and a non-boss figure beside the boss
   figure.
2. **Buffs are measured over the whole key clock**, from the fight's start to its end, walking
   between pulls included, rather than over combat time only.
   - Accepted consequence, stated on the page: a buff that is only up in combat reads lower over
     the whole key the more of the key was spent between pulls, so a reference that walked less
     reads higher whatever either player did.
3. **Debuffs are measured as coverage over every enemy's life**, the council rule extended to
   trash: the debuff-seconds on each enemy, over the seconds each enemy was alive, summed. The
   whole key clock cannot apply to debuffs: between pulls there is no enemy to debuff, so that time
   could only ever count as uncovered.
   - Rejected: "on any enemy" over pull time, which reads one dot on a pack of eight as full
     coverage; and pull time per enemy averaged, which needs the same inferred start without the
     consistency.
4. **Reach is added beside coverage.** The share of the enemies that carried the debuff at least
   once. Coverage alone cannot tell "on one mob all the time" from "on every mob briefly"; both read
   20% on a pack of five that lives 30 s. Reach does.
5. **Overall carries the verdict, in both families.** Every other figure is descriptive. Reach has
   no threshold and is never judged: choosing one without data would be inventing it.
6. **A trash enemy's life opens at the first debuff anyone applied to it, and closes at its death**
   (see §3.1 for the measurement that chose it).
7. **An enemy life with no death in the log is left out** of coverage and reach. Its count is shown
   as a warning on the page and kept in the findings file, so it can be tracked across runs. So is
   the count of enemies that died with no debuff from anyone.
8. **Adds spawned during a boss fight count in Overall only.** The Trash column is the mobs of trash
   pulls, and the Bosses column is the bosses themselves, exactly as today.
9. **The reach figures get their own table** below the coverage table (version C of the two shown
   on 2026-10-13), with a note under the pair explaining coverage and reached.

## 3. Measurement

### 3.1 The evidence for the trash start rule

Measured 2026-10-13, offline, over the 44 cached keystone fights that hold enemy deaths. Two of them
(our Ruby Life Pools and Temple of Sethraliss keys) hold every stream: 11 trash pulls, 269 trash
enemies that died. The other 42 are 24 parse references and 18 of our own fights without the debuff
stream.

- **The pull's start is wrong for trash.** Pulls chain packs: enemies first appear a median 79 s
  after the pull's start on our two full fights, and 64 s on the references. Ten of our 11 trash
  pulls hold an enemy first seen more than 10 s in. Starting every enemy at the pull's start would
  triple its alive-seconds (32,487 s against 10,310 s) and cut trash coverage to about a third.
- **The first debuff is close to the truth where it can be checked.** On our two full fights,
  the first debuff row on an enemy matched the earliest event of that enemy in our richer streams
  (casts, damage taken, enemy casts) to within a median 0.0 s, p90 0.9 s, max 8.5 s: about 1% of
  alive-seconds.
- **It is measurable alike on both sides, for no new points.** A parse reference already fetches
  the debuff stream, the enemy deaths and the actors for the boss figure.
- **Its blind spot:** an enemy nobody debuffed has no start. 84 such lives on the references (almost
  all Scorchlings) and 10 on ours, 2.7 to 3.7% of the trash enemies that died, had no event in any
  stream before their death row. Only a damage-done stream would see them; none is fetched.
- **Identity.** An enemy is (game id, instance), as the debuff pairing keys it, an absent instance
  read as 0. `targetInstance` is present on 5,445 trash death rows and absent on 181, never 0, and an
  absent value means the actor had one instance. Instance numbers are reused: 387 enemy keys die
  twice in one pull. So an enemy is cut into lives at each of its deaths.
- **The pull's enemy list cannot count enemies.** It carries only `id` and `gameID` per enemy type
  (`FIGHTS_QUERY` asks for nothing else), a median 6 types against a median 27 to 29 enemies dying
  per trash pull, and it lists totems and eggs while omitting spawned adds. Lives are therefore read
  from the debuff and death streams, not from the pull list.
- **Lives with no death:** 29 of 298 on ours (Static Anomaly, Scorchling, Swarming Krolusk), 47 of
  3,203 on the references. On our fights without the debuff stream, totems, eggs and spirits
  dominate (Magma Totem, Potadpole Egg, Ritual Spirit).

The spike's full record is not committed; this section is its measured content.

### 3.2 Debuffs: coverage and reach

1. **Enemy lives.** Every hostile NPC instance of the key is keyed by (game id, instance). A
   player-owned hostile pet (Glacial Tomb, A Knot of Snakes) is filtered out by actor type and
   `petOwner`. Each instance is cut into lives at its death rows:
   - a life opens at the first debuff *application*, by anyone, on that instance after its previous
     death, so a removal logged just after a death never opens a life;
   - it closes at its death;
   - a life with no death is left out and counted (decision 7);
   - an instance that died with no application since its previous death is a zero-length life:
     it adds nothing to coverage, counts in reach's denominator, and is counted.
2. **Boss lives keep the existing rule**: a single boss over its pull, a council boss from the pull's
   start to its own death, capped at the pull's end. Their figures do not move.
3. **Stretches.** A life belongs to the pull holding its death.
   - **Bosses:** the boss targets of measured boss pulls.
   - **Trash:** every life whose death falls in a trash pull.
   - **Overall:** both, plus every other life whose death falls in a boss pull (the adds).
4. **Coverage** of a stretch: the player's debuff-seconds on each life, clipped to that life, the
   player's and their pets' copies merged per life before counting, summed over the stretch, over the
   stretch's summed life-seconds. This is the council formula; on bosses it is the existing figure.
5. **Reach** of a stretch: of its measured lives, the share that carried the player's debuff at least
   once. A zero-length life counts in the denominator and never in the numerator.
6. **Shared debuffs:** the existing rule, applied per life: two players are compared on a common
   target within one pull, and the debuff is exclusive when every such pair overlapped by at most
   `SHARED_OVERLAP_TOLERANCE_S` in total.
7. **Thresholds** are reused, never redefined: `MIN_UPTIME_FRACTION`, `UPTIME_GAP_FRACTION`,
   `MIN_SAMPLE_FOR_AGGREGATE`, `MAX_AURAS_REPORTED`.

### 3.3 Buffs

- **Overall:** the share of the key clock, the fight's start to its end, that the buff was up.
- **Without bosses:** the key clock less the boss pulls, walking included.
- **Bosses:** the boss pulls, as today.
- The aura bands already cover the whole fight on both sides (`.claude/skills/wcl-api/SKILL.md`, "In
  every table measured"), so no new data is read. A parse reference gains its fight's start and end,
  read from the report the cache already holds.

## 4. What the reader sees

**Buff uptime:** one row per buff, a verdict judged on Overall, then the cells Overall, Without
bosses and Bosses, each "ours / the median". The caption states the walking consequence of
decision 2.

**Debuff coverage** (judged), then **Debuff reach** (descriptive), one row per debuff in each:

| Debuff | Verdict | Overall | Trash | Bosses | per-boss cells as today |
| --- | --- | --- | --- | --- | --- |

| Debuff | Overall | Trash | Bosses |
| --- | --- | --- | --- |

The reach table has no per-boss columns: a boss is one target, so its reach is 100% or 0%, which the
Bosses column already says.

**The note under the pair**, in this spirit: *Coverage*: the share of the enemies' alive time your
debuff was on them, summed over every enemy, so a long-lived mob weighs more than one that dies in
seconds. *Reached*: the share of the enemies that carried your debuff at least once. Low coverage
with high reach means it was spread but not kept up; low coverage with low reach means it stayed on
too few mobs. A trash mob's life runs from the first debuff anyone put on it to its death; adds that
spawn during a boss fight count in Overall only.

**The warning**, only when a count is above zero: "N enemies had no death in the log and were not
measured; M died without anyone debuffing them and count only toward reached."

The shared label, the pairing tally and the council-deathless sentence stay. "No boss found" stays
for the boss column; a key with no measurable trash life reads "no trash measured" in the Trash cell.

**Findings.**

- **Buff ids keep their names**: `compare.uptime.self.<rank>`, `compare.uptime.unjudged` and
  `compare.uptime.unavailable`. They now judge Overall.
- **Debuff ids are renamed** from `compare.uptime.boss.*` to `compare.uptime.debuff.*`, judging
  Overall coverage, because the old name would describe the wrong figure.
- **Confidence stays as it is:** gaps and unjudged are `derived`, unavailable is `measured`.
- **The findings file** carries, per table, the Overall, Trash and Bosses figures, coverage and reach,
  ours and the median, plus `unmeasured_no_death` and `undebuffed_deaths`.

## 5. Components

- **Domain, `comparison/`:**
  - The enemy lives and the coverage and reach per stretch, beside `boss_debuffs.py`. They reuse
    `pair_debuffs`, the boss targets, and the per-target merge and length helpers.
  - The buff windows: the whole key, and the key less the boss pulls.
  - The tables gain the stretches and the counts.
- **Domain, `report/players.py`:** the two debuff tables, the note, the warning and the buff
  columns.
- **Adapter:** nothing new is fetched. The parse reference's fight start and end come from the
  cached report.
- **CLI:** no wiring change beyond the reference's span.

## 6. Edge cases

- A key with no trash debuffs at all: Trash reads "no trash measured"; Overall is the bosses and the
  adds.
- One creature logged under two actor ids (Infused Whelp, Scorchling, Snake: 631 cases): keyed by
  game id, as the pairing does.
- A debuff applied before the key's first death of that instance and removed after it: clipped to the
  life's end.
- A boss pull Warcraft Logs lists twice: measured once, by the existing rule.

## 7. Testing and proof

Tests come first, with invented names only. They cover:

- lives cut at each death;
- an instance reused within one pull;
- one creature under two actor ids;
- a removal just after a death not opening a life;
- a life with no death left out and counted;
- a dead, undebuffed enemy counted in reach only;
- player-owned pets filtered out;
- the Trash, Bosses and Overall stretches, adds in Overall only;
- coverage and reach arithmetic;
- the boss figures unchanged;
- the buff whole-key and without-bosses windows on both sides;
- the renamed ids;
- both tables, the note and the warning on the page;
- the counts in the findings file.

**The plan's first step** re-measures, on the cache, that the first-*application* start matches the
first-row start the spike measured.

**Live proof**, per CLAUDE.md:

- Re-run `LyKXYvVZm192TDr6` fight 9 (`--all-players`) and `nd6Rz47Gj1ZPxFfm` fight 3.
- Report every state's count: verdicts, withheld cells and both warning counts.
- Report coverage and reach on both sides, and how far the references sit below 100%.
- Survey the cached keys offline for the blind spot and for coverage above 100%, which would be a
  defect.

## 8. Cost

An estimate, not a measurement: about 0 points more per run, since every stream read is already
fetched for the boss figure. The live run records the real figure.

## 9. Documentation, when it ships

- **This design**, with a live amendment.
- **Dated amendments to the parent and council designs.**
- **The mplus-analysis skill:** the renamed ids, coverage against reach, and the two counts.
- **The wcl-api skill**, if a cost reading changes.
- **CLAUDE.md, README and `docs/how-it-works.md`:** "Trash and raid pulls are not measured yet"
  becomes "Raid pulls are not measured yet".

## 10. Out of scope

- Raid debuffs.
- Per-pull figures.
- A reach threshold.
- A damage stream to see enemies nobody debuffed.
- Duplicated pulls in the other analysers, which is a separate task.
