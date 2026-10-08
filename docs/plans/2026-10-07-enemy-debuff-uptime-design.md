# Debuff uptime on bosses, per player

**Status:** approved design, 2026-10-07; planned in docs/plans/2026-10-07-enemy-debuff-uptime-plan.md, built, and exercised live on 2026-10-08.
**Area:** `wowperf analyze`, the parse axis of the Mythic+ comparison, and the player card on the
Players tab. It revives the "on target" half of `docs/plans/2026-09-03-mplus-postmortem-design.md`
§5 item 5, which has been inert since 2026-09-05, for boss pulls only.

## 1. Why

The buff uptime family compares what a player kept up on themselves against the same
specialisation's top parses. The matching figure for what a player kept up on enemies was
declared unavailable on 2026-09-05: `table(dataType: Debuffs, hostilityType: Enemies)` cannot be
narrowed to one caster by any argument.

That measurement was of the `table` endpoint only. The event stream answers differently.
`events(dataType: Debuffs, hostilityType: Enemies)` names the caster of every application, at
about one point per 10,000-row page. This was first read on 2026-10-02 and verified on 2026-10-07;
see the wcl-api skill, "The debuff event stream does name the caster". So the figure exists. It
has to be rebuilt from events rather than read from a pre-built table.

## 2. Scope

**In:**

- Mythic+ boss pulls.
- One figure per debuff across all boss pulls, with a verdict.
- The same figure per boss, descriptive only.
- Pets folded into their owner.

**Out, each deliberately:**

- **Trash.** On a trash pull, "uptime" needs each enemy's alive span. The log records a death but
  never an appearance, so the span's start would be inferred. Trash is the planned second step,
  defined as enemy coverage: debuff-seconds summed over every enemy, divided by
  enemy-alive-seconds summed. It is not designed here.
- **Per-pull figures.** They arrive with trash.
- **Raid.** The measure carries over unchanged, with the whole fight as the boss window. It is
  left out so that one path is proven live before a second is paid for. A cold
  `raid --all-players` kill draws about 95 reference kills, each of which would need its own
  stream.
- **Council pulls.** They are withheld with a stated reason (§4). A council's bosses can die
  apart, which is the alive-span inference deferred with trash.

## 3. What the reader sees

The player card gets a new table, titled **"Debuff uptime on bosses"**, directly under "Buff uptime
on boss pulls".

- **One row per qualifying debuff.** A debuff earns a row by the buff family's own rules: at
  least three parse references carry it, and their median is at least 10%. That filter, not a
  hand-written list, keeps incidental debuffs off the table. Like the buff table, the table
  itself is not capped. The cap of five (`MAX_AURAS_REPORTED`) applies to the gap findings.
  *Corrected 2026-10-07 while planning: this line first said "at most five" rows, from a misreading
  of the buff table.*
- **One verdict per row, on the figure across all boss pulls.** The figure is the total seconds
  the bosses carried the debuff, divided by the total boss-pull seconds. The states are the buff
  family's: *below* when the median exceeds ours by at least 15 points, *level*, and *not judged*
  when ours is zero.
- **Per-boss cells beside the verdict, descriptive only.** Each cell holds ours against the
  reference median for that boss, and carries no verdict. References are runs of the same
  dungeon, so their bosses line up by encounter id. There are two reasons for no per-boss
  verdict. A short boss pull makes a noisy fraction. And five debuffs over four bosses would put
  twenty verdicts on one card. The cells still show where an overall gap sits.
- **A withheld cell states its reason**: a council pull, no boss found, or a reference that never
  reached that boss.
- **Confidence: `derived`.** The intervals are rebuilt from apply and remove events. The API does
  not hand them over the way it does buff bands.
- **Finding ids mirror the buff family.** They are `compare.uptime.boss.{rank}`,
  `compare.uptime.boss.unjudged` and `compare.uptime.boss.unavailable`. Each carries the
  player-slug suffix `service.py` already appends, and each is routed to the player card through
  `report/players.py`'s `COMPARISON_PREFIXES`.

*Amended 2026-10-08:* a debuff one teammate's application replaces is marked **shared**, not
judged. The first live run's only gap finding was false. It was measured on the cached key
`LyKXYvVZm192TDr6` fight 9, over 438 s of measured boss time:

| Debuff on measured bosses | Owner | Share | Pairwise overlap |
| --- | --- | --- | --- |
| Mortal Wounds (115804) | Arms Warrior | 69.1% | Warrior / Monk: **0.0 s** |
| | Windwalker Monk | 27.1% | union of both: 96.2% |
| Rune of Lingering (1287663) | 5 players | 9-53% each | every pair overlaps: **7.9 s to 127.9 s** |

Only one Mortal Wounds sits on a target, so a teammate's application replaces yours. The table
judged the Warrior below, 69% against a median of 91%, when the group kept it up 96% of the time.
Rune of Lingering is one per caster: copies coexist, so a per-player figure is fair there. "A
teammate also applied it" is therefore not what makes a debuff shared. **Copies that never
overlap** are.

The rule is computed on our own side only, from the same stream and measured boss windows, with
no new query. Each player of our run is one owner, their pets folded in; an enemy applying the
debuff is not an owner. A debuff is *exclusive* when at least two owners held it on the measured
bosses and every pair of them overlapped by at most `SHARED_OVERLAP_TOLERANCE_S` (1.0 s) in total.
A player's debuff is *shared* when it is exclusive and some other owner held it. That holds even
at a zero of their own, once two others took it over from each other. Beside a single other owner,
exclusivity cannot be shown and a zero stays `unjudged`. A shared debuff yields no gap finding
and is not listed in `compare.uptime.boss.unjudged`. Its row keeps its figures, and the verdict
column reads "Shared with" and the teammates' specialisation and class, counted when several share
one, in the unjudged row's tint. References
are not read for sharing: it can only lower a reference's share, which moves the median down and so
can only make ours read level, never wrongly below.

Checked offline over 26 cached keys the same day. Mortal Wounds was exclusive on all six keys
where two players held it: every pair overlapped 0.00 s, and the smaller holder had at least
84 s. Every per-caster debuff on every key read per-caster: Rune of Lingering, Venomfang, Soul
Fang Venom, Consecration, Brittle and Incite Terror. On the measurement key the rows came to
18 level, 3 unjudged and 2 shared, and no `below` and no gap finding remained.

**Known limitation.** A per-caster debuff held by exactly two players whose copies barely
overlapped would read as shared. Single Rune of Lingering pairs were measured at 0.00 s and
0.72 s of overlap, with one holder at 8 s. Those keys read per-caster only because a third holder
overlapped more. The error goes the safe way: it withholds a verdict and never accuses wrongly.
On the 26 keys it never happened, because every such key had a third holder.

## 4. Components and data flow

The order is hexagonal, matching the buff family.

1. **Query (adapter).** `ENEMY_DEBUFFS_QUERY` asks for
   `events(dataType: Debuffs, hostilityType: Enemies, fightIDs: [$fightId], startTime, endTime,
   limit: 10000)`. It is paginated on `nextPageTimestamp` like the other streams and covers the
   whole fight.
   - **Whole fight, not boss windows.** A boss pull on a key is about one page anyway, and the
     whole-fight stream is what trash will need.
   - **One stream per run, covering the whole group.** A reference run shared by several players'
     samples under `--all-players` is fetched once.
   - **Cache tiers as today.** Our own run goes in the permanent tier, references in the
     day-long one.

2. **Actors (adapter).** `ACTORS_QUERY` grows from `actors { id gameID }` to
   `actors { id gameID name subType petOwner }`. The one query then serves both needs, on our run
   and on every reference: pet owners for the folding, and the boss flags `find_bosses` reads.
   - **No new call.** Adding fields to an existing query has measured free; `enemyNPCs` on
     `Fights` did not move its 2.01.
   - **A one-time cost.** The query text is part of the cache key, so every report already cached
     pays about one point once to re-read its actors.
   - **The skill's field table changes.** `petOwner` flips to "yes", which `tests/test_skills.py`
     enforces.

3. **Ingest (adapter).** A `DebuffEvent` carries the event type, `sourceID`, `sourceInstance`,
   `targetID`, `targetInstance`, `abilityGameID` and `timestamp`.
   - **Kept types:** `applydebuff` and `removedebuff` only. `refreshdebuff`, `applydebuffstack`
     and `removedebuffstack` do not change whether a debuff is on, so they are dropped.
   - **Absent keys:** an absent instance reads as 0. This is the skill's existing rule for
     `sourceInstance`, applied to `targetInstance` as well.

4. **Pairing (domain, pure).** `debuff_bands(events, owner_of, game_id_of)` returns, for each
   owning player and ability, the intervals on each target.
   - **The source is folded to its owner** through `petOwner`. A player's own applications and
     their pets' are merged per ability and per target, never counted twice.
   - **The target is keyed on its gameID and copy number, not its actor id.** One enemy can be
     logged under two actor ids. Keyed on actor id, 13 of the Death Knight's 168 applications on
     the probe key never closed. Keyed on gameID, the same ability balanced completely.
   - **Pairing:** an apply opens an interval and a remove closes it.
   - **An interval still open at the window's end is closed there.** A boss window ends with the
     boss pull.
   - **An orphan remove is counted and dropped, never guessed at.** An orphan remove is one with
     no open application.
   - *Amended 2026-10-08:* the pairing keys on (source id, ability, target game id, target
     instance), without the source's own instance number. A pet applies a debuff under one
     instance and removes it under another: a Mirror Image pet's Frostbolt ran on to the fight's
     end, which added 1,869.7 s of uptime on measured bosses across 8 of the 26 cached keys. The
     source is folded to its owner only when an interval is written. The accepted cost is an
     under-count when two copies of one pet each hold a debuff on one target, since the first
     removal closes the interval; it moved Withering Grasp and Mind Sear, the two debuffs it was
     measured on, by no more than 6.3 points of boss time on any key (corrected 2026-10-08: this
     note first said it of every debuff, but the skill records the bound for these two only; the
     per-ability comparison over all 26 keys found only three abilities moving by 0.5 s or
     more). Orphan
     removes now mostly count a pet copy's second removal rather than a broken pairing. The
     function is `pair_debuffs(log)`, returning the intervals and the tally, where this item
     names `debuff_bands(events, owner_of, game_id_of)`.

5. **Boss windows (domain).** For each boss pull, `find_bosses` (`comparison/pace_boss.py`) picks
   the boss from the pull's own enemies, their boss flags and the pull's `name`.
   - **One boss:** the debuff's seconds on that boss, clipped to the pull, over the pull's
     seconds.
   - **A council, or no boss found:** a withheld cell, with that reason. Withheld pulls also drop
     out of the overall figure, on both sides of the comparison.
   - **Unmeasured on dungeons.** `find_bosses` was measured on raids only, so the first live run
     must confirm it on dungeon bosses (§6).
   - *Amended 2026-10-08:* the first live run did not confirm it. Warcraft Logs types some
     dungeon bosses as plain `NPC` (Galvazzt is its pull's only enemy, and has no flag), so
     `find_bosses` found no boss there. Where an encounter is named for two bosses it read one:
     "Adderis and Aspix" begins with "Adderis ", so Adderis alone was measured, and "Kyrakka and
     Erkhart Stormvein" held no flagged enemy at all. The dungeon boss is now read by name first
     and by flag second (`boss_game_id_of`, `comparison/boss_debuffs.py`). The pull's name is
     split on " and " (never on a comma, which marks a title); each part is matched against the
     pull's own enemies by the opening-words rule, counted by game id because one enemy can be
     logged under two actor ids. A part matching two game ids is no boss. Several parts with at
     least one matched is a council. One part matching one game id is that boss. A name that
     matches no enemy falls back to `find_bosses`, counted by game id. `find_bosses` itself is
     unchanged, since raid pacing reads it.

6. **Comparison (domain).** The pairing's output takes the existing `Aura`-with-bands shape. It
   goes through the same machinery as buffs: the sample median, the observed range, the floor of
   three, the pairwise fallback below it, and "N of M references had no debuff data". Only the
   wording and the finding ids differ. Every parse member gets the same treatment against its own
   stream. The per-boss cells are a thin descriptive layer beside it.
   - *Noted 2026-10-08, not fixed:* a reference that is eligible but whose every boss was
     withheld, which leaves it zero measured seconds, still counts as having debuff data. And
     below the floor the debuff pairwise comparison returns nothing where the buff pairwise
     comparison says unavailable.

7. **Report.** A view-model row type in the builder, and a Jinja table that loops. As everywhere
   else, the builder decides and the template does not.

**Provenance, recorded and not judged.** For every run read, the findings record how many orphan
removes and how many end-closed intervals the pairing met. These counts are the evidence for the
live distribution check in §6, and the starting data for the trash design.

*Amended 2026-10-08:* the tally is recorded for our own run only
(`comparison_tables.<slug>.boss_debuffs.tally`), not for each reference run read. It is `null`
when our own stream was not read, so a findings file tells that apart from a log that paired
cleanly.

## 5. Failures

These mirror the buff family.

- **Our own stream fails:** the result is `compare.uptime.boss.unavailable`, `measured`.
- **A reference's stream fails:** that member keeps no debuff data, and the finding counts it.
- **A spent budget:** `RateLimitExceeded` is re-raised and stops the loop. It never silently drops
  a member.

## 6. Testing and proof

Tests come first, and use only the sanctioned fixture names.

- **Unit, pairing:**
  - a pet folded into its owner;
  - two actor ids of one gameID re-keyed into one interval;
  - an open interval closed at the window's end;
  - an orphan remove counted and dropped;
  - refresh and stack events ignored;
  - overlapping player and pet intervals merged.
- **Unit, boss windows:**
  - one boss;
  - a boss under a shorter name;
  - a council withheld;
  - no boss found withheld.
- **Unit, comparison and report:** every verdict state renders, and no per-boss cell carries a
  verdict.
- **Integration:** ingest from fixture pages shaped like the real rows, including absent keys.
- **End to end:** one live `analyze` on a key, asserting the table and its finding ids.
  - *Amended 2026-10-08:* no live `analyze` test was added. The live proof ran `analyze` on both
    keys and read the table, the finding ids and the state distribution from the findings files
    (corrected 2026-10-08: the state distribution is recorded in the amendment to the live proof
    below; the wcl-api skill's 2026-10-08 paragraphs hold the cost, the pairing and the tally,
    and not the distribution). The committed end-to-end test is a
    repository-level check that no debuff on a measured boss outlives the key; it is not an
    `analyze` run.

**Live proof,** per the CLAUDE.md invariant. Run `analyze` on two keys already in the cache, and
report how often each reachable state occurred:

- below;
- level;
- not judged;
- unavailable;
- the pairwise fallback;
- each withheld-cell reason;
- the orphan and end-closed counts.

The keys:

- `LyKXYvVZm192TDr6` fight 9, a +18 Ruby Life Pools with a Death Knight and its Rune Weapon.
- `nd6Rz47Gj1ZPxFfm` fight 3, a +18 Temple of Sethraliss, whose first boss is a council.

A state that never occurs is a defect to chase, not a quiet success.

*Amended 2026-10-08:* the live distribution, read from the findings files of the final pairing
(the one that drops the source instance). It spans six subjects: five players on the first key
and one on the second. Players are named by class only.

- **Row verdicts, 25 rows:** `level` 21, `unjudged` 3, `below` 1.
  - The one `below` is a Warrior's Mortal Wounds on the first key: ours 69%, median 91%, range
    40% to 95%, over 5 top parses.
  - The 3 `unjudged` are Venomfang twice and Soul Fang Venom, all on the first key.
- **Per-boss cells, 77 cells:** `measured` 49, `council` 25, `no boss found` 2, `too few
  references` 1. The council cells are 23 on the first key and 2 on the second.
- **Findings:** `gap` 1 (`compare.uptime.boss.0.<slug>`, on the Mortal Wounds row, `derived`) and
  `unjudged` 3 (`derived`).
- **Pairing tally, our own run:** first key 284 orphan removes and 4 end-closed intervals; second
  key 454 and 62. Most orphan removes are a pet copy's second removal on an interval already
  closed, not a broken pairing.
- **Never reached, three states:** `compare.uptime.boss.unavailable`, the pairwise fallback and
  `no reference reached this boss`.
  - `compare.uptime.boss.unavailable` fires when no reference in the sample returned debuff data,
    or when our own side has no figure (our stream unread, or no single-boss pull). It did not
    occur because every player's parse sample held 5 references, all 30 parse references loaded
    and returned debuff data (every gap finding read "0 of 5 references had no debuff data"),
    and both keys had measured single-boss pulls.
  - The pairwise fallback fires only when fewer than three references are eligible. It did not
    occur because every sample held 5.
  - `no reference reached this boss` needs a reference whose log misses a boss pull. It did not
    occur because every parse reference was a key of the same dungeon and read every boss
    exactly as ours did.
  - All three were left unexercised because no cached key offered a thin sample or a
    reference missing a boss, and a search on a fresh key was not paid for. They were optional.
- **Where the figures were read:** the task-8 report, section "Final reread after 132ef70" of
  `.superpowers/sdd/2026-10-07-enemy-debuff-uptime-plan/`. Those figures supersede the earlier
  ones in that report, which read the pairing before it dropped the source instance (a second
  `below` row and gap finding, both from a Mage's Frostbolt over-count, are gone).

**Budget about 400 points of 3600 for both runs, cold.** That covers `--all-players` on the first
key, which gives five subjects' worth of states, and one player on the second. *Corrected
2026-10-07 while planning: the first figure here, about 50, left out that a cold `--all-players`
compared run already costs about 190 points before any debuff stream (wcl-api skill,
2026-09-11).*

## 7. Cost

The figures below are estimates from the 2026-10-07 probe, not measurements of this feature.

| Item | Estimate |
| --- | --- |
| Our own key, 27 minutes | about 3 points |
| Each parse reference of similar length | about 3 points |
| A compared `analyze` | about 15 to 20 points more |
| `--all-players`, about 14 distinct reference runs | about 45 points more |

The first live run records the real figures in the wcl-api skill.

## 8. Documentation, when it ships

These edits land in the last implementation task, not before, because each describes the feature
as built.

- **CLAUDE.md.** The sentence "Uptime covers buffs only..." becomes:
  > Uptime covers buffs everywhere and debuffs on Mythic+ bosses. The enemy-debuff *table*
  > cannot be scoped to one caster (measured 2026-09-05), but the `Debuffs` event stream names
  > each application's caster (measured 2026-10-07). The boss figure is rebuilt from it.
- **`docs/plans/2026-09-03-mplus-postmortem-design.md` §5 item 5.** An amendment note: the on-target
  half is revived for boss pulls by this design. Trash and raid remain open.
- **The wcl-api skill.** The live cost reading, and the `petOwner` row of the field table.
