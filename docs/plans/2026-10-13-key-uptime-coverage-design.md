# Uptime over the whole key: buffs, and debuff coverage and reach on every enemy

**Status:** approved design, 2026-10-13; planned in `docs/plans/2026-10-13-key-uptime-coverage-plan.md`.
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

*Amended 2026-10-13, while planning:* the life start was re-measured on the cache as §3.2 states
it: the first `applydebuff` row on a copy after its previous death, against the spike's first row
of any kind. On our two full fights, over 269 died trash lives, the first application came a
median 0.0 s, p90 0.0 s and at most 3.2 s after the first row, and summed alive time moved by
-0.2%. On the references, over 3156 lives, the same figures were 0.0 s, 0.0 s and 5.2 s, and alive
time moved by -0.2%. 0 lives on ours and 0 on the references moved by more than 10 s. Lives of zero
length went from 10 to 11 on ours, and from 85 to 93 on the references. Both sides stay within the
2% of alive time this plan set as material, so the rule stands.

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

*Amended 2026-10-13, while planning:* five points the section left open were decided in the plan.
- A measured boss's game id is never cut into lives. Otherwise every wiped boss would read as an
  enemy with no death, and every boss would count twice.
- The enemies of a boss pull with no boss found count as adds, the unfound boss among them.
- A death belongs to the last pull starting at or before it, as the council's death rule reads it.
- A death row the log writes twice at one millisecond is one death.
- The lives are built in `comparison/enemy_lives.py`, and coverage and reach in
  `comparison/key_debuffs.py`. The boss figure is built by the same helpers as before, and every
  boss test reads it through `key_debuffs.boss_debuffs`, a thin reading of `key_debuffs`.

### 3.3 Buffs

- **Overall:** the share of the key clock, the fight's start to its end, that the buff was up.
- **Without bosses:** the key clock less the boss pulls, walking included.
- **Bosses:** the boss pulls, as today.
- The aura bands already cover the whole fight on both sides (`.claude/skills/wcl-api/SKILL.md`, "In
  every table measured"), so no new data is read. A parse reference gains its fight's start and end,
  read from the report the cache already holds.

*Amended 2026-10-13, after planning:* the Bosses figure is no longer exactly as today. It moves on a
fight where Warcraft Logs lists a boss pull twice, with one encounter, start and end (10 such pulls in
5 of 969 cached keystone fights, all wipes, measured 2026-10-08).
- **The defect.** The buff's boss windows held such a pull twice. Bands are clipped to every window
  and merged before they are summed, so the buff's seconds in that pull counted once. The boss
  seconds summed it twice. A buff up through every boss pull therefore read below 100%: exactly half
  on a fight whose only boss pull is the duplicate, and two thirds beside one other boss pull of the
  same length.
- **The fix.** The buff windows now keep one copy, on our side and on every reference's, by the rule
  the debuff figure already applies (`docs/plans/2026-10-08-council-debuff-coverage-design.md` §5). One
  helper holds the rule for both.
- **Why the move is intended.** The figure that moves was wrong, and the two families now count one
  physical pull alike.
- **What does not move.** Overall never counted the pull twice: the key clock is one span. Neither
  did Without bosses: the boss pulls are walked past in order, so a repeated one changes nothing.
- **Out of scope.** Cast rates still divide by boss seconds that count the pull twice. They are the
  separate task §10 names.

## 4. What the reader sees

**Buff uptime:** one row per buff, a verdict judged on Overall, then the cells Overall, Range,
Sample, Without bosses and Bosses. Overall and the two stretches each read "ours / the median";
Range and Sample are Overall's. The caption states the walking consequence of decision 2.

| Ability | Verdict | Overall | Range | Sample | Without bosses | Bosses |
| --- | --- | --- | --- | --- | --- | --- |

**Debuff coverage** (judged), then **Debuff reach** (descriptive), one row per admitted debuff in
each (the admission rule is the last amendment of this section):

| Ability | Verdict | Overall | Range | Sample | Trash | Bosses | per-boss cells as today |
| --- | --- | --- | --- | --- | --- | --- | --- |

| Ability | Overall | Range | Sample | Trash | Bosses |
| --- | --- | --- | --- | --- | --- |

The reach table has no per-boss columns: a boss is one target, so its reach is 100% or 0%, which the
Bosses column already says.

*Amended 2026-10-13, after planning:* the three tables keep a Range and a Sample column, for the
judged Overall figure.
- **What they state.** The spread and the count of the references behind Overall's median, which is
  what the verdict rests on. RwlRwlRwlRwl decided it on reading the plan, which had drawn neither.
- **Reach too.** Reach keeps the two columns, stating its own Overall figure's references, so the
  three tables share one shape. Those references are the parses that reached any enemy with the
  debuff, and the findings file keeps their Overall reaches beside the reach cells.
- **The other cells.** The cells for each stretch and each boss stay "ours / the median", with no
  range of their own.

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

*Amended 2026-10-13, while planning:*
- The warning states each clause only when its own count is above zero.
- In the findings file, `comparison_tables.<slug>.boss_debuffs` becomes `.debuffs`, and each
  `auras` entry nests its judged figure under `uptime`, beside `without_bosses` and `bosses`.
  Each debuff row's `reach` carries `overall_fractions`, the references' Overall reaches behind
  its median.
- The page heads the first column of every comparison table "Ability", these three included, so
  the example tables above head it so too. The template draws one shared heading and only loops.
- An empty buff Without bosses cell reads "nothing outside boss pulls", not "no trash measured":
  that stretch is the key less its boss pulls, walking included, so it is not trash alone.

*Amended 2026-10-13, after the live run:* a debuff aimed at bosses kept its row. RwlRwlRwlRwl
decided the rule on 2026-10-13.
- **What the live run showed.** Touch of the Magi on an Arcane Mage and Soul Fang Venom on a
  Restoration Shaman vanished from the Debuff coverage table, with their Bosses and per-boss cells.
  Their Overall coverage in the references is about 3.6 to 5.0% of all enemy life for the first,
  15.5 to 20.4% on bosses. The table took its rows from `uptime_measures` over the Overall shares
  alone, which drops an ability whose median sits under `MIN_UPTIME_FRACTION`. The boss-only table
  it replaced had these rows.
- **The rule.** A row appears when the references' Overall median clears the existing admission
  (at least `MIN_SAMPLE_FOR_AGGREGATE` carriers and a median of at least `MIN_UPTIME_FRACTION`),
  or when the same rule, read over the references' Bosses shares, admits it.
- **The verdict stays on Overall.** A row admitted only through Bosses is not judged: no verdict, no
  gap finding, and no mention in `compare.uptime.debuff.unjudged`. Its own state is
  `uptime.verdict` "bosses_only", distinct from `unjudged`, which means we showed none of it. The
  page reads "Not judged" for both, and the note under the coverage table says why such a row is
  kept.
- **Its figures.** Its Overall cell is ours against the references' Overall median, with Range and
  Sample over the references that carried it Overall. Trash, Bosses, each boss and reach are drawn
  as for any row.
- **Order.** Judged rows first, then these, each group in the table's usual order. The reach table
  follows the coverage table.
- **Scope.** Debuffs only, and the sample table only: the single-reference path and the buff table
  are unchanged, and so are the finding ids.

*Amended 2026-10-13, after the live run:* a stretch no reference applied the debuff in is named as
such. RwlRwlRwlRwl decided the rule on 2026-10-13.
- **What the live run showed.** On slows that bosses are immune to (Heart Strike and Grip of the
  Dead on a Blood Death Knight) the Bosses, per-boss and reach-Bosses cells read "too few
  references", though all five references measured the stretch and all five sat at 0%. The cell
  dropped the zeros before counting, so a sample that measured the stretch and never applied the
  debuff there read as too small.
- **The rule.** When no reference carried the debuff over a stretch but at least
  `MIN_SAMPLE_FOR_AGGREGATE` measured it, the cell reads "no reference applied it". Every other
  case is as it was: no reference measured it reads "no reference measured it", and fewer than
  `MIN_SAMPLE_FOR_AGGREGATE` carriers otherwise still reads "too few references".
- **Where it applies.** The one cell rule is shared, so the buff table's cells, the debuff table's
  Trash, Bosses and per-boss cells, and the reach table's cells all read it.

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
- A boss pull Warcraft Logs lists twice: measured once, by the existing rule, in the debuff figure
  and, by §3.3's amendment, in the buff Bosses figure.

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

*Amended 2026-10-13, live:* `analyze` ran on both keys twice. The first round had its references
cold. It found the two gaps that §4's two "after the live run" amendments close. The second round
ran warm, after those amendments were built.

**The keys.**
- `LyKXYvVZm192TDr6` fight 9, `--all-players`: a Blood Death Knight, an Arms Warrior, a Windwalker
  Monk, a Restoration Shaman and a Subtlety Rogue.
- `nd6Rz47Gj1ZPxFfm` fight 3: an Arcane Mage.

**States reached.** The second round's counts, Ruby Life Pools / Temple of Sethraliss.

| State | Ruby Life Pools | Temple of Sethraliss |
| --- | --- | --- |
| Buff verdict `level` | 159 | 34 |
| Buff verdict `below` | 4 | 0 |
| Buff verdict `unjudged` | 27 | 3 |
| Buff Without bosses measured | 190 | 37 |
| Buff Bosses measured | 189 | 37 |
| Buff Bosses "too few references" | 1 | 0 |
| Debuff verdict `level` | 20 | 1 |
| Debuff verdict `unjudged` | 2 | 0 |
| Debuff shared | 2 | 0 |
| Debuff verdict `bosses_only` | 1 | 1 |
| Coverage Trash measured | 25 | 2 |
| Coverage Bosses measured | 22 | 2 |
| Coverage Bosses "no reference applied it" | 3 | 0 |
| Coverage per boss measured | 66 | 6 |
| Coverage per boss "no reference applied it" | 9 | 0 |
| Coverage per boss "no boss found" | 0 | 2 |
| Reach Overall measured | 25 | 2 |
| Reach Trash measured | 25 | 2 |
| Reach Bosses measured | 22 | 2 |
| Reach Bosses "no reference applied it" | 3 | 0 |

- **Findings.**
  - Four buff gaps, all `derived`. They are the first buff `below` verdicts seen live:
    - on the Blood Death Knight, Sanguine Ground, Death and Decay and Blood-Soaked Ground, each 56%
      against 73%;
    - on the Subtlety Rogue, Momentum of Despair, 52% against 83%.
  - Five and one buff `unjudged`, and two and none debuff `unjudged`.
- **The `bosses_only` rows** are the two this design's amendment kept:
  - Touch of the Magi on the Arcane Mage: 16.0% against 16.4% on bosses, 4.5% against 4.1%
    Overall.
  - Soul Fang Venom on the Restoration Shaman: 0% against 23.2% on bosses. The player did not carry
    it.
- **"No reference applied it"** is read by the Blood Death Knight's three slows that bosses are
  immune to: two Heart Strike debuffs and Grip of the Dead. In the first round, the same cells read
  "too few references".
- **The warning.**
  - Ruby Life Pools: 1 enemy with no death and 11 undebuffed deaths, the same for every player.
  - Temple of Sethraliss: 22 and 1.
  - Together that is 23 and 12, against the spike's 29 and 10. Set beside each other as a
    comparison, not as a cause: §3.1's planning amendment re-measured the zero-length lives on
    our two full fights at 11 under this rule, against 12 here. Why 23 differs from 29 was not
    measured.

**States that never occurred, and why.**
- **The debuff verdict `below`, and so the debuff gap finding.** `below` needs the median at least
  `UPTIME_GAP_FRACTION`, 15 points, above ours. The widest judged shortfall was Grip of the Dead's
  9.5 points.
- **`unavailable`, in both families.** Every reference returned aura and debuff data. Every gap
  finding's evidence reads 0 of 5 references without aura data, and every compared player drew a
  debuff table.
- **"No trash measured".** Ours held 133 and 135 trash lives, and every surveyed reference 116 to 148.
- **"No reference measured it".** The one boss no side can find is Avatar of Sethraliss. It reads
  "no boss found" on our side first, and our reason takes the cell.
- **"Nothing outside boss pulls".** A key always walks between its pulls.
- **"Too few references" on a debuff cell.** It occurred in the first round. Every case was a
  stretch where all five references sat at zero, which now reads "no reference applied it". It still
  occurs on one buff Bosses cell.

**Coverage and reach.**
- **The four judged debuffs whose Overall gap is widest**, ours against the median:

  | Debuff | Player | Coverage | Reach |
  | --- | --- | --- | --- |
  | Insidious Chill | Blood Death Knight | 46.9% against 32.2% | 41.1% against 29.4% |
  | Grip of the Dead | Blood Death Knight | 40.6% against 50.0% | 73.5% against 86.2% |
  | Deep Wounds | Arms Warrior | 44.9% against 35.8% | 63.8% against 59.1% |
  | Heart Strike | Blood Death Knight | 35.1% against 28.2% | 58.9% against 66.8% |

- **The references' Overall medians on every row but `bosses_only`:**
  - coverage ran from 10.0% to 95.0%, with a median of 24.0%;
  - reach ran from 11.0% to 93.1%, with a median of 56.4%;
  - none reached 99%.
- **Even the widest-spread debuff stops short of every enemy.** Blood Plague, which a tank spreads to
  everything, sits about 5 points below full coverage and 7 below full reach.

**The survey of the cache, offline.**
- **Lives.** 27 fights hold both streams:
  - 3,532 trash lives and 1,827 add lives;
  - 145 undebuffed deaths, 2.7% of them, against §3.1's 2.7 to 3.7%;
  - 177 lives with no death, left out;
  - no coverage or reach above 100%.
- **The route check.** 380 keystone fights were routed.
  - The cache held 969 on 2026-10-08. Expired references have been purged since.
  - 8 boss pulls listed twice, in 7 fights, were each kept once: 27 listed boss pulls became 19
    windows.
  - The buff and debuff boss windows agreed on every fight.
- **Two changes to the plan's survey were needed to reach that.**
  - A report without a cached actor list is routed too. A window's span does not depend on the
    actors.
  - A fight `build_run` refuses is routed on its pulls alone.
- **The buff Bosses figure on a duplicated pull stays unproven live.** Every cached boss pull listed
  twice sits on an unfinished key, which `analyze` refuses because it carries no `keystoneTime`. No
  `AuraTable` response covers one, and none was bought.
- **Pairing.** Of 160,581 paired intervals, 1,699 outlive a death of their own copy. 10 of those reach
  a later death of it.

**End to end.**
- **`test_uptime_e2e` passed.**
- **`test_boss_debuffs_e2e` failed in the first round.**
  - The Restoration Shaman's Flame Shock on Kyrakka, the key's last boss, was left open to the key's
    end.
  - At Kyrakka's death the log removed every other debuff on it but wrote no removal for that one,
    0.27 s before the stream ended.
  - The figure was unaffected, since the boss's span stops at its death.
  - The test now excuses an interval on a boss that died within 1.0 s of the stream's end, and it
    passed in the second round. The wcl-api skill records the oddity.
- **`tests/e2e/test_compare_e2e.py` was not run.** It is a known gap: the rewrite of it made while
  building this design shipped without a live run. RwlRwlRwlRwl decided to skip it on 2026-10-13.

**Cost.**
- `analyze nd6Rz47Gj1ZPxFfm --fight 3`, cold, spent 98.15 points:

  | Operation | Calls | Points |
  | --- | --- | --- |
  | `Fights` | 7 | 14.07 |
  | `EnemyDebuffs` | 14 | 14.00 |
  | `Talents` | 5 | 10.25 |
  | `PlayerDetails` | 5 | 10.00 |
  | `Casts` | 8 | 8.00 |
  | `Abilities` | 7 | 7.00 |
  | `Deaths` | 5 | 5.77 |
  | `EnemyCasts` | 5 | 5.04 |
  | `Actors` | 5 | 5.00 |
  | `AuraTable` | 5 | 5.00 |
  | `EnemyDeaths` | 5 | 5.00 |
  | `Interrupts` | 5 | 5.00 |
  | `CharacterRankings` | 1 | 1.01 |
  | `FightRankings` | 1 | 1.01 |
  | `Affixes` | 1 | 1.00 |
  | `RateLimit` | 2 | 1.00 |

- `analyze LyKXYvVZm192TDr6 --fight 9 --all-players`, cold, spent 337.48:

  | Operation | Calls | Points |
  | --- | --- | --- |
  | `EnemyDebuffs` | 76 | 80.12 |
  | `Fights` | 21 | 42.21 |
  | `Talents` | 20 | 41.00 |
  | `PlayerDetails` | 20 | 40.00 |
  | `AuraTable` | 25 | 28.90 |
  | `Abilities` | 21 | 21.00 |
  | `Casts` | 21 | 21.00 |
  | `EnemyDeaths` | 20 | 20.89 |
  | `Actors` | 20 | 20.00 |
  | `Deaths` | 5 | 5.30 |
  | `CharacterRankings` | 5 | 5.05 |
  | `EnemyCasts` | 5 | 5.00 |
  | `Interrupts` | 5 | 5.00 |
  | `FightRankings` | 1 | 1.01 |
  | `RateLimit` | 2 | 1.00 |

- **Warm, each command spent 1.00**, all of it on `RateLimit`. The first round's two end-to-end tests
  spent about 29 points.
- **No operation was new.** `EnemyDebuffs` (1.00 and 1.05 a call), `EnemyDeaths` (1.00 and 1.04) and
  `Actors` (1.00) sit inside the ranges the wcl-api skill records. The skill's cost paragraphs are
  left alone.
- **One reading moved, outside the three this checks.** `AuraTable` cost 1.16 a call on the first
  key, against 1.00 on 2026-10-08.
- **So the feature's cost is 0 points**, as §8 estimated.

**Observed, not changed here.** The Blood Death Knight's Death and Decay fills three of the five buff
gap slots under three names with identical figures. That behaviour predates this design, and became
visible once `below` occurred live. It is left to a separate task.

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
