---
name: wcl-api
description: Use when writing or changing any code that queries the Warcraft Logs API — the verified field names, the terms of service, and the rate-limit budget
---

# The Warcraft Logs API, as verified

This is the live reference. `docs/plans/2026-09-03-mplus-postmortem-design.md` §2 points here.

**Every claim carries how it was verified and when.** A field name with no date is a defect, not
a shortcut. This project shipped a half-feature that does nothing because a line said "verified"
and had never been run — see the debuff section below.

**Never invent a field name.** Verify it against the live schema before using it, then record it
here with the date: as a row in the table when the table covers it, in the prose section that
covers it otherwise.

## Fields

| Field | Appears on | Verified | In queries.py |
| --- | --- | --- | --- |
| `keystoneLevel` | `ReportFight` | 2026-09-03 | yes |
| `keystoneAffixes` | `ReportFight` | 2026-09-03 | yes |
| `keystoneTime` | `ReportFight` | 2026-09-03 | yes |
| `keystoneBonus` | `ReportFight` | 2026-09-03 | yes |
| `countReached` | `ReportFight` | 2026-09-03 | yes |
| `countRequired` | `ReportFight` | 2026-09-03 | yes |
| `npcCountMap` | `ReportFight` | 2026-09-03 | yes |
| `rating` | `ReportFight` | 2026-09-03 | no |
| `friendlyPlayers` | `ReportFight` | 2026-09-04 | yes |
| `friendlySpecs` | `ReportFight` | 2026-09-04 | yes |
| `friendlyItemLevels` | `ReportFight` | 2026-09-04 | yes |
| `dungeonPulls` | `ReportFight` | 2026-09-03 | yes |
| `encounterID` | `ReportDungeonPull` | 2026-09-03 | yes |
| `enemyNPCs` | `ReportDungeonPull` | 2026-09-03 | yes |
| `gameID` | `ReportDungeonPull.enemyNPCs` | 2026-09-03 | yes |
| `masterData` | `Report` | 2026-09-03 | yes |
| `icon` | `ReportAbility` | 2026-09-09 | yes |
| `allowUnlisted` | `reportData.report` argument | 2026-09-03 | yes |
| `rateLimitData` | `Query` | 2026-09-04 | yes |
| `limitPerHour` | `RateLimitData` | 2026-09-04 | yes |
| `pointsSpentThisHour` | `RateLimitData` | 2026-09-04 | yes |
| `pointsResetIn` | `RateLimitData` | 2026-09-04 | yes |
| `gameData` | `Query` | 2026-09-06 | yes |
| `affixes` | `GameData` | 2026-09-06 | yes |
| `characterRankings` | `worldData.encounter` | 2026-09-03 | yes |
| `fightRankings` | `worldData.encounter` | 2026-09-03 | yes |
| `fightIDs` | `table` argument | 2026-09-05 | yes |
| `hostilityType` | `table` argument | 2026-09-05 | yes |
| `sourceID` | `table` argument | 2026-09-05 | no |
| `targetID` | `table` argument | 2026-09-05 | yes |
| `targetID` | `events` argument | 2026-09-07 | yes |
| `includeResources` | `events` argument | 2026-09-07 | yes |
| `filterExpression` | `events` argument | 2026-09-07 | yes |
| `graph` | `Report` | 2026-09-12 | yes |
| `viewBy` | `graph` and `table` argument | 2026-09-12 | no |
| `petOwner` | `ReportActor` | 2026-09-12 | no |
| `playerDetails` | `Report` | 2026-09-14 | yes |
| `includeCombatantInfo` | `playerDetails` argument | 2026-09-14 | yes |

`tests/test_skills.py` holds this table against `src/wowperf/adapters/wcl/queries.py`. When it
rejects a row, correct the row rather than the test: the table is a claim about the code, and the
code wins.

**The table is the machine-checked subset, not the whole vocabulary.** It holds the fields a test
can assert by name in both directions, which is why it stays short. The sections below name more —
arguments, nested fields and response keys such as `kill`, `startTime`, `endTime`, `x`/`y`,
`actors`, `bands`, `totalUptime`, `totalUses` and `totalTime` — each under its own verification
date, and those dates bind exactly as the table's do. A field documented in prose is documented.
`queries.py` also uses fields this reference names nowhere: `talentImportCode`,
`abilities`, `subType`, `nextPageTimestamp` and `owner` (surveyed 2026-09-05 against `queries.py`;
in use, but not verified against the live schema here).

## The endpoint and auth

Verified 2026-09-03 against the Warcraft Logs GraphQL schema and the official OAuth
documentation.

- **Endpoint:** `https://www.warcraftlogs.com/api/v2/client` (single POST GraphQL).
- **Auth:** OAuth2 client credentials. Token URI `https://www.warcraftlogs.com/oauth/token`,
  HTTP Basic with `client_id` as user and `client_secret` as password. Clients are created
  at `https://www.warcraftlogs.com/api/clients/`.
- **Client credentials read public reports only.** Unlisted reports work through
  `reportData.report(code:, allowUnlisted: true)` when the code is known. Private reports
  require the authorization-code flow, which this project does not implement.

## Rate limit

Points per hour, per client, on fixed one-hour cycles. Live introspection on 2026-09-04 read
`limitPerHour: 3600` for the unsubscribed tier, confirming the figure that was previously known
only from an archived page. Still read the real value from
`rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }` at runtime rather than
hardcoding it, because it is per-client and can change.

**The point cost formula is undocumented.** No published table, no response headers. The
`pointsSpentThisHour` field is a Float, implying fractional per-query costs. We measure rather
than predict.

One approximation and three measurements:

- A full compared analysis costs roughly **28 points of 3600** — an order of magnitude observed
  across this project's own compared runs, not a controlled measurement. No single reading stands
  behind it and its composition is not recorded. It predates sampling and describes one reference
  per axis, not five. It is the reason not to loop, not a number to budget against.
- A roster query, four aura tables and a `rateLimitData` read together spent **12.02 points of
  3600** (2026-09-05).
- A full sampled compared analysis — five speed references and five parse references, both
  leaderboards, and an aura fetch for every parse member — spent **83.39 points of 3600**
  (2026-09-08). Conditions: one cold run, one dungeon, one keystone level; all ten candidates
  loaded, none excluded and none retried. `docs/plans/2026-09-08-sampling-design.md` projects ~111
  for that shape, so the reading came in about a quarter under.
- **`AuraTable` costs about 1.06 points a call, not the 2.00 recorded above** (2026-09-11).
  Thirty calls on one `--all-players` run spent 31.70 together. Every earlier reading of that
  operation — 2.00 a call on 2026-09-05 and again on 2026-09-08 — was taken while the query still
  selected a second, enemy-side table alongside the player's own buffs. `ee23732` removed that
  selection, and the operation kept its name, so a reading from before that commit prices a query
  that no longer exists. Treat the 2.00 rows below as historical.
- The same analysis widened to the whole roster with `--all-players` — one speed sample for the
  run and a parse sample for each of five players — spent **190.90 points of 3600** (2026-09-11),
  against the 83.39 above for the same report and fight with one player. Conditions: one cold run,
  report `6Kx1P9GbNXrcLdHa` fight 36, five players in five distinct specialisations and none
  skipped for want of one; all thirty candidates loaded, none excluded and none retried.
  **Eleven of the twenty-five parse candidates were served from another player's sample** — the
  parse rows carrying `from_cache` whose report and fight another player's sample also names,
  which is what `tests/e2e/test_report_e2e.py` counts. Twenty-five candidates stand on fourteen
  distinct runs: the fourteen first parse loads are not among the eleven, and each of the eleven
  repeats found its run already on disk. Those fourteen were not all paid for in full — five of
  them had already been read on the speed axis, so their first parse load paid only for `Talents`
  and `Casts`, the queries a speed profile leaves unfetched. Both halves of that definition carry
  weight — drop `from_cache` and the count is at least fourteen, because the first fetch of every
  shared run sits in a multi-player group too.
  `docs/plans/2026-09-10-per-player-parse-comparison-design.md` §7.1 derived about 250 for this
  shape, so this too came in about a quarter under. One reading, of one report, against one day's
  leaderboards: how much a roster shares depends on how much its specialisations' leaderboards
  overlap, and that is not a rate this measures.
- **The same `--all-players` shape re-run against a warm cache spent 78.21 points of 3600**
  (2026-09-11, report `6Kx1P9GbNXrcLdHa` fight 36, the first such report read by a person rather
  than by a test). Composition as the command printed it: `AuraTable` 30 calls for 31.70,
  `Talents` 9 for 18.45, `Fights` 6 for 12.06, `Casts` 9 for 9.00, `Abilities` 6 for 6.00,
  `RateLimit` 2 for 1.00. **This prices a re-run, not a cold one, and the composition says so:**
  no `CharacterRankings` or `FightRankings` call at all — both leaderboards came from the
  24-hour reference cache — and no `Deaths`, `DamageTaken`, `Healing`, `Interrupts`,
  `EnemyCasts`, `EnemyDeaths`, `Resurrects` or `Actors` call, all served from our own run's
  permanent cache. The cold figure for this shape is the 190.90 above, and that reading predates
  `ee23732`, so it over-prices every `AuraTable` in it by roughly half.

## Every query reports its own cost

Measured 2026-09-08. `rateLimitData` is a top-level `Query` field, so it can be selected
alongside the real work in one round trip, and `with_rate_limit` in
`src/wowperf/adapters/wcl/queries.py` now splices it into every named operation the project
sends.

**The block is free.** Two real queries cost **3.01 points with it and 3.01 without** — a plain
`Fights` at 2.01 and a plain `Affixes` at 1.00, then the same pair aliased. Instrumenting every
query therefore costs nothing, which is the only reason to do it at all.

**A reading reports the spend before its own query is billed.** So a query's cost is the *next*
reading minus its own, and the last query of a sequence stays unpriced until something follows
it. A probe's whole sequence reconciled to the hundredth under that reading and under no other:
an aliased `Fights` reported 8.01, exactly what the queries before it had left behind.
Attributing a reading to the query that carried it would shift every figure onto its neighbour
and still look entirely plausible.

This holds only while requests are sequential. They are — the loaders are plain loops — but
nothing enforces it, and concurrent fetches would interleave the readings and misattribute every
cost after the first.

**A full sampled compared analysis, cold cache, same report and fight, 2026-09-08: 83.39 points
of 3600**, composed as the command prints it.

| Operation | Calls | Points | Mean |
| --- | --- | --- | --- |
| `Fights` | 7 | 14.07 | 2.01 |
| `Talents` | 6 | 12.30 | 2.05 |
| `AuraTable` | 6 | 12.00 | 2.00 |
| `Abilities` | 7 | 7.00 | 1.00 |
| `Casts` | 7 | 7.00 | 1.00 |
| `Deaths` | 6 | 6.00 | 1.00 |
| `EnemyCasts` | 6 | 6.00 | 1.00 |
| `Interrupts` | 6 | 6.00 | 1.00 |
| `Healing` | 4 | 4.00 | 1.00 |
| `Affixes` | 2 | 2.00 | 1.00 |
| `CharacterRankings` | 1 | 1.01 | 1.01 |
| `FightRankings` | 1 | 1.01 | 1.01 |
| `Actors`, `DamageTaken`, `EnemyDeaths`, `Resurrects` | 1 each | 1.00 each | 1.00 |
| `RateLimit` | 2 | 1.00 | — |

`RateLimit` shows two calls against one point because the closing read has nothing after it to
price it. The mean is the column to distrust elsewhere too: only the totals were measured, and a
second cold run of the same shape came to **84.23**, differing from this one in exactly two rows
— `Deaths` at 6.39 rather than 6.00, and `DamageTaken` at 1.45 rather than 1.00. So a handful of
queries carry fractions that move between runs, and a mean is a rate rather than a price.

**That 83.39 is the same figure this file already recorded for the same shape before any
instrumentation existed.** Selecting the block is therefore free at the scale of a whole run, not
only across the two queries the controlled probe compared.

**Most queries cost 1.00 and nothing costs much above 2.** What the table adds is the
composition, not the total: the ~111 the sampling design projects can now be checked against real
per-query prices rather than argued about.

**A contradiction for a human to settle.** `CASTS_QUERY` always sends `includeResources: true`,
and all seven cast pages here cost 7.00 points together — 1.00 each, since any variation would
have to cancel exactly. The 2026-09-07 note below records 2.59 points for two such pages, about
1.30 each, against 2.00 for the same window without the flag. Both readings cannot be right.
Nothing in this project depends on which is, so it is recorded rather than resolved.

The off-by-one is **not** the explanation, so do not reach for it. The older method read the
quota before and after and subtracted the read's own 1.00, and under the reading described above
that arithmetic yields the query's true cost: the opening read's point falls inside the
difference and the closing read's does not.

**The same analysis with `--all-players`, cold cache, same report and fight, 2026-09-11: 190.90
points of 3600**, five players compared instead of one, composed as the command prints it.

| Operation | Calls | Points |
| --- | --- | --- |
| `AuraTable` | 30 | 60.08 |
| `Talents` | 15 | 30.75 |
| `Fights` | 15 | 30.15 |
| `Casts` | 16 | 16.00 |
| `Abilities` | 15 | 15.00 |
| `EnemyCasts` | 6 | 9.44 |
| `Deaths` | 6 | 6.00 |
| `Interrupts` | 6 | 6.00 |
| `CharacterRankings` | 5 | 5.05 |
| `Healing` | 4 | 4.00 |
| `Affixes` | 2 | 2.00 |
| `DamageTaken` | 1 | 1.42 |
| `FightRankings` | 1 | 1.01 |
| `Actors`, `EnemyDeaths`, `Resurrects` | 1 each | 1.00 each |
| `RateLimit` | 2 | 1.00 |

No mean column, for the reason the table above gives: only the totals were measured. Two rows
read higher here than the identical call counts did on 2026-09-08 — `EnemyCasts` at 9.44 against
6.00 over six calls, `DamageTaken` at 1.42 against 1.00 over one. `DamageTaken` is squarely the
drift the table above describes, which put that same row at 1.45 on a second cold run of the
single-player shape. `EnemyCasts` is consistent with that drift but larger than either row the
drift was measured on: 3.44 points over six calls, 57% above the 2026-09-08 figure, where the
recorded drift moved a row by under half a point. There is a second account the call count does
not distinguish it from — the five speed references were drawn from a different day's
leaderboard, so those five calls were made against a sample re-drawn three days later, not
necessarily the same fights. Neither row is a difference `--all-players` made. Which account
holds for `EnemyCasts` needs another reading to settle, and none has been taken.

**Five times the players is not five times the price, and the reason is in the call counts.**
Thirty candidates were weighed — five speed references, and five parse references for each of the
five players — and fourteen distinct runs stand behind them: eleven parse candidates were served
from another player's sample, and all five speed references were themselves top parses, so their
reports were read on both axes and fetched once. Hence `Fights` and `Abilities` at 15, which is
fourteen references plus our own run rather than thirty-one; `Talents` at 15, one per
parse-profile load and ours; `Casts` at 16, one page per parse reference plus the two our own
longer fight takes, which is what the 2026-09-07 probe below counted for this fight's friendly
cast stream with `includeResources: true` — 10716 rows over 2 pages. `EnemyCasts`, `Deaths` and
`Interrupts` stay at 6 — the speed axis is drawn once however many players are compared.

**The rows do not all count the same population, and that is what makes the two tables
comparable.** Read off `src/wowperf/adapters/wcl/repository.py` on 2026-09-11: `Fights` and
`Abilities` are fetched on every profile, so they count references on both axes, while `Casts`
and `Talents` are fetched on the parse profile and on our own run and nowhere else — a speed
reference fetches neither. So the divisor for a `Casts` count is `Talents`, never `Fights`.
`Fights` and `Abilities` are keyed on the report code alone where `Casts` and `Talents` are keyed
on report and fight, so strictly the first two count distinct reports, which in both these
samples is the same as distinct runs. On 2026-09-08, `Talents` at 6 is five parse references and
ours, and `Casts` at 7 is those five single pages plus our two. Here, `Talents` at 15 is fourteen
parse references and ours, and `Casts` at 16 is those fourteen plus our two. Both readings
therefore put our own fight at the same two pages, and neither leaves a page unaccounted for.

**The one row that scales with players rather than with references is `AuraTable`**, at 30 calls
and 60.08 points, a third of the run: one for each of the five subjects' own uptime, and one for
each of the twenty-five sample memberships. A reference shared between two samples is a different
character in each, so nothing there is shared, and nothing about it improves with a warmer cache.

The `Casts` row also speaks to the price contradiction above: sixteen pages with
`includeResources: true` for 16.00 points, 1.00 each, agreeing with the 2026-09-08 reading and not
with the 2026-09-07 one. Still recorded rather than resolved, since nothing here depends on it.

## Mythic+ in the schema

Verified 2026-09-03 against the Warcraft Logs GraphQL schema.

A complete Mythic+ run is one `ReportFight` with `keystoneLevel != null` and `kill == true`.
It carries `keystoneAffixes`, `keystoneTime` (Blizzard's official penalty-inclusive time),
`keystoneBonus` (1, 2, or 3 chests), `rating`, `countReached`, `countRequired`, and
`npcCountMap`.

The roster comes from three index-aligned arrays on the same fight: `friendlyPlayers` (actor
IDs, joined against `masterData.actors`), `friendlySpecs`, and `friendlyItemLevels`. All
three were confirmed present on `ReportFight` by live schema introspection on 2026-09-04.

`ReportFight.friendlyPlayers` is the roster of **that fight**. `masterData.actors` lists every
actor in the **report**, across all its fights, so filtering a fight's roster from `masterData`
alone silently includes players who were never there.

Segmentation hangs off `dungeonPulls: [ReportDungeonPull]`, each with `startTime`,
`endTime`, `encounterID` (0 means trash), `enemyNPCs[].gameID`, and `x`/`y` giving the map
position of the first mob damaged.

`npcCountMap` maps NPC IDs to the enemy-forces count each kill awards. Joined against deaths and
divided by `countRequired`, it yields per-pull trash percentage without any external data source,
and this project reads those deaths from the API rather than from a raw combat log it never
reads: `events(dataType: Deaths)`, keeping the events whose `type` is `"death"`. Checked
2026-09-05 against `src/wowperf/adapters/wcl/queries.py` and
`src/wowperf/adapters/wcl/ingest.py`. `UNIT_DIED` is the client-side combat-log line for the same
moment; it is not in this schema and nothing here queries it.

Timestamps on fights and pulls are relative to report start. `Report.startTime` is absolute
epoch milliseconds.

## Event streams `ingest.py` reads

Four rows here — enemy casts, interrupts, enemy deaths, damage taken — were verified
2026-09-04 against report `6Kx1P9GbNXrcLdHa` fight 36 by live query, first recorded in Plan B's
implementation plan (`docs/plans/2026-09-04-mplus-analysers-plan.md:34-46`) and carried here on
2026-09-06 because this file is the authority. The player-deaths row comes from the design
document, `docs/plans/2026-09-03-mplus-postmortem-design.md` §11, verified 2026-09-04 against a
real death event on the same report and fight. The player-casts row was verified separately, on
2026-09-06, against the cached `dataType: Casts, hostilityType: Friendlies` stream of the same
report and fight — see the row's own date below. The design's §5.3 prose uses combat-log names
(`SPELL_CAST_START`, `extraSpellId`, `sourceInstanceID`) that do **not** exist in the API; the
table below supersedes them.

| Stream | Verified | Query arguments | `type` values | Fields |
| --- | --- | --- | --- | --- |
| Player casts | 2026-09-06 | `dataType: Casts, hostilityType: Friendlies` | `begincast`, `cast` | `cast`: `abilityGameID`, `fight`, `sourceID`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type`. `begincast`: `abilityGameID`, `fight`, `sourceID`, `targetID`, `timestamp`, `type` (no `targetInstance`, no `targetMarker`). `targetID` is `-1` for a cast with no target. No `sourceInstance` was observed on a player cast. |
| Enemy casts | 2026-09-04 | `dataType: Casts, hostilityType: Enemies` | `begincast`, `cast` | `abilityGameID`, `fight`, `sourceID`, `sourceInstance`, `sourceMarker`, `targetID`, `timestamp`, `type` |
| Interrupts | 2026-09-04 | `dataType: Interrupts, hostilityType: Friendlies` | `interrupt`, `applydebuff` | `abilityGameID`, `extraAbilityGameID`, `fight`, `sourceID`, `sourceInstance`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type` |
| Player deaths | 2026-09-04 | `dataType: Deaths` (default hostility) | `death` | `abilityGameID` (always 0), `fight`, `killerID`, `killerInstance`, `killingAbilityGameID`, `sourceID` (always -1), `targetID`, `timestamp`, `type` |
| Enemy deaths | 2026-09-04 | `dataType: Deaths, hostilityType: Enemies` | `death` | `abilityGameID`, `fight`, `killerID`, `killerInstance`, `killingAbilityGameID`, `sourceID`, `targetID`, `targetInstance`, `targetMarker`, `timestamp`, `type` |
| Damage taken | 2026-09-04 | `dataType: DamageTaken, hostilityType: Friendlies` | `damage` | `abilityGameID`, `absorbed`, `amount`, `blocked`, `buffs`, `fight`, `hitType`, `isAoE`, `mitigated`, `sourceID`, `sourceInstance`, `sourceMarker`, `targetID`, `tick`, `timestamp`, `type`, `unmitigatedAmount` |
| Healing received | 2026-09-07 | `dataType: Healing, targetID: <actor>`, per death over the run-up | `heal`, `absorbed`, `removebuff` | `heal`: `abilityGameID`, `amount`, `sourceID`, `targetID`, `timestamp`. `absorbed`: as `heal`, plus `extraAbilityGameID` (the hit that was soaked) and `attackerID`. `removebuff` is dropped. |
| Resurrections | 2026-09-07 | `dataType: All, filterExpression: "type = 'resurrect'"`, once for the whole fight | `resurrect` only | `abilityGameID` (the spell), `sourceID` (the caster), `targetID` (the revived player), `timestamp`. |

- `sourceInstance` is absent when the instance is the first one; treat a missing value as `0`
  on both sides of any comparison. Two copies of one NPC are `(sourceID, sourceInstance)`.
- On an `interrupt` event, `abilityGameID` is the kick and `extraAbilityGameID` the spell
  interrupted; `targetID`/`targetInstance` is the enemy, `sourceID` the player.
- On a damage event `amount` excludes what was absorbed — a real row read `amount: 0,
  absorbed: 123570` — so "how hard did this hit" is `unmitigatedAmount`.
- `npcCountMap` keys are strings holding NPC game IDs; the join is enemy death `targetID` →
  `masterData.actors` → `gameID` → `npcCountMap[str(gameID)]`. `masterData.actors` accepts
  `type: "NPC"`, and `ReportActor` carries `gameID, icon, id, name, petOwner, server, subType,
  type`.
- **`ReportAbility` carries exactly `gameID`, `icon`, `name` and `type`** — introspected
  against the live schema 2026-09-09. There is no description, no cooldown and no tooltip
  text on it. `icon` is a bare lower-case file name ending `.jpg`, e.g.
  `spell_holy_magicalsentry.jpg`; all 2511 rows of one report carried one, and three carried
  a literal `?cachebust` suffix naming a file the other rows also named.
- **On a damage event, `overkill` appears only on a lethal blow, and `buffs` is a
  dot-terminated list of ability game ids.** Measured 2026-09-11 against the cached
  `DamageTaken` responses for report `6Kx1P9GbNXrcLdHa` fight 36 — 11,368 damage events. Key
  frequencies: `timestamp`, `type`, `sourceID`, `targetID`, `abilityGameID`, `fight`,
  `hitType`, `amount`, `unmitigatedAmount` and `isAoE` on all 11,368; `mitigated` on 10,177;
  `buffs` on 10,138; `sourceInstance` on 5,930; `absorbed` on 5,785; `tick` on 3,766;
  `sourceMarker` on 1,335; `overkill` on 18; `blocked` on 2. An absent key means the log said
  nothing, so each reads as zero or false. `buffs` looks like `"391395.391398.391571."` — ids
  separated *and* terminated by a period. **`hitType` is an integer (1, 2 and 4 observed) and
  nothing here documents what those integers mean**, so no code may translate one.

## The event stream, probed for a death recap

Verified 2026-09-06 against report `6Kx1P9GbNXrcLdHa` fight 36, by schema introspection and by
running the queries. The whole probe — two introspections, three event queries, one table —
spent 9.45 points. Nothing in `queries.py` uses these yet; they are recorded so the death-recap
work can start from facts.

- **`EventDataType` has no `Resurrects` value.** Its values are `All`, `Buffs`, `Casts`,
  `CombatantInfo`, `DamageDone`, `DamageTaken`, `Deaths`, `Debuffs`, `Dispels`, `Healing`,
  `Interrupts`, `Resources`, `Summons`, `Threat`. A resurrection has to be read from the
  resurrecting spell's own `cast` event, or from the `All` stream.
- **`events` accepts `includeResources: Boolean`.** With it, an event carries `hitPoints` and
  `maxHitPoints` for the event's **source** actor. On a player's `DamageTaken` stream that means
  almost nothing: 21 of 22 hits in a twelve-second window carried no hit points, and the one that
  did was a hit the player dealt to themselves. A dying player's health curve therefore comes from
  the events they are the source of — their `cast` and `resourcechange` events, which did carry
  `hitPoints` — not from the hits they took.
- **`dataType: Healing` scoped by `targetID`** returns `heal` events, `absorbed` events (a shield
  soaking a hit) and `removebuff` events. Observed keys: `abilityGameID`, `amount`, `attackerID`,
  `buffs`, `extraAbilityGameID`, `fight`, `sourceID`, `targetID`, `timestamp`, `type`. No
  `overheal` key appeared. **On an `absorbed` row, `abilityGameID` is the shield and
  `extraAbilityGameID` is the hit it soaked** — corrected 2026-09-07 against 43 rows over four
  deaths, where `abilityGameID` resolved to Prismatic Barrier, Refractive Images, Soulcoil Barrier
  and Beacon of the Savior while `extraAbilityGameID` resolved to Searing Magma, Frozen Tempest,
  Primal Echo and Seriously Sharp Seashell. The 2026-09-06 note here had the two the other way
  round.
- **`table(dataType: Deaths, fightIDs: [Int])`** returns `{entries: [...]}`, one entry per death,
  with `name`, `id`, `guid`, `type`, `icon`, `timestamp`, `fight`, `deathWindow`, `overkill`,
  `killingBlow {name, guid, type, abilityIcon}`, `damage {total, totalReduced, activeTime,
  activeTimeReduced, overheal, abilities, damageAbilities, sources}`, `healing`, and `events`.
  Each event carries `ability {name, guid, type, abilityIcon}`, `amount`, `mitigated`,
  `unmitigatedAmount`, `overkill`, `hitType`, `isAoE`, `tick`, `sourceIsFriendly`,
  `targetIsFriendly`. The `events` list is short — three events on the first entry — so it is a
  death recap, not a run-up; the run-up still comes from the `DamageTaken` stream.
- **A resurrection is a `resurrect` event in the `All` stream**, carrying the resurrecting
  spell as `abilityGameID`, the caster as `sourceID` and the dead player as `targetID` (observed:
  `Raise Ally`, with a `Resurrecting` debuff applied on the cast and removed when accepted). A
  self-resurrection is an ordinary `cast` by the dead player (observed: `Reincarnation`). **A
  player who releases and respawns produces no event at all**: on fight 36 two players were
  casting again 3 and 6 seconds after their death, at about 80% health and with their raid
  buffs gone, then dealt no damage for a further 20 seconds. Their first casts were self-only
  movement and shield spells with `targetID: -1`. "Playing again" therefore means a cast aimed at
  another actor, never merely the next cast.
- **`gameData.affixes` returns `[GameAffix {id, name, icon}]`**, 51 rows and no arguments, in
  one query (`gameData.affix(id:)` also exists). Verified 2026-09-06: ids 9, 10 and 147 resolved
  to Tyrannical, Fortified and Xal'atath's Guile.
- **`ReportDungeonPullNPC` has no `instanceCount` and no `groupCount`** (both rejected by the
  schema on 2026-09-06). `dungeonPulls[].enemyNPCs` lists NPC *types*, so multiplying a pull's
  types by `npcCountMap` under-prices a pack with several copies of one mob. Forces a pull
  actually awarded come from the enemy death events in its window, which is what
  `analysis/trash.py` already does.

**Measured 2026-09-07 for the recap**, same report and fight, into a fresh cache. Every figure is
net of the `rateLimitData` query used to read it, which costs 1.00 point of its own.

- **Casts with `includeResources: true`, whole fight, `hostilityType: Friendlies`:** 2.59 points
  over 2 pages and 10716 rows, against 2.00 points for the same window without it. The flag costs
  about 0.30 a page. **Disputed** — per-query instrumentation priced seven such pages at 1.00 each
  on 2026-09-08; see "Every query reports its own cost" above. 9259 of the rows carry both
  `hitPoints` and `maxHitPoints`; 1457 carry
  neither. A carrying row also holds `absorb`, `itemLevel`, `classResources` and the player's
  secondary stats.
- **`dataType: Healing` scoped by `targetID`, one ten-second window:** 1.00 point, 7 to 46 rows
  per death, never paginated. **The scoping works**: across all four deaths, no returned row
  targeted another actor.
- **`dataType: All` scoped by `targetID` does *not* filter.** A sixty-second window asked for one
  player returned 7087 rows, of which 428 targeted them and 6355 touched neither them nor their
  target. It is the whole group's stream with the argument ignored, and it paginates.
- **`filterExpression: "type = 'resurrect'"` on `dataType: All` does filter**, server-side and
  cheaply: over the whole 31-minute fight it returned the one `resurrect` row for 1.00 point and
  no next page. Unfiltered, the same stream costs 29 points over 29 pages. One filtered query per
  fight replaces a scoped query per death.
- **A self-resurrection, on this run.** Player 694 died at 1121.0 s into the fight and returned
  1.5 s later. The stream shows `225080` applied as a debuff at the moment of death and removed
  1.5 s after, and at that same moment a `cast` of `21169` by player 694 with `targetID: -1` —
  no `resurrect` row accompanies any of it. The report's ability table names both `225080` and
  `21169` and never `20608`, the spell database's Shaman ability. A self-resurrection is
  therefore recognised from the cast of a listed spell, not from a `resurrect` row with
  `sourceID == targetID`.
- **A whole compared analysis with the recap costs 44.29 points of 3600**, measured 2026-09-07
  on a cold cache for this report and fight, the figure as the command reports it and so
  including one of the two quota reads it makes itself, never both — see "Every query reports its
  own cost" above. About thirty-five of those points predate the recap. The rest is one healing
  window per death, one resurrections query for the fight, and the resource flag on the casts.

## Aura tables

**The buff table already carries consumable buffs.** Measured 2026-09-14 offline over the 2217
aura-table rows in this project's response cache; no query was issued. 32 match a
consumable-shaped name: five distinct flasks, `Well Fed` under **six** ability ids
(451920, 1219182, 1219185, 1232490, 1232585, 1294727) plus `Hearty Well Fed` under two more,
several `Rune of …` augment runes, `Vantus Rune: …` per-boss runes, and `Potion of Recklessness`.

**A name rule cannot identify them.** `Rune Mastery` (374585) and `Rune of Sanguination` (326808)
are Death Knight abilities. Any consumable list must be curated by id, with a verified date.

**Aura uptime comes from the table endpoint, not the event stream.** Verified 2026-09-05 against
report `6Kx1P9GbNXrcLdHa` fight 36:

```
table(fightIDs: [Int], dataType: Buffs | Debuffs, targetID: Int, sourceID: Int,
      hostilityType: HostilityType, startTime: Float, endTime: Float)
```

returns `{data: {auras: [...], totalTime, useTargets, startTime, endTime, logVersion,
gameVersion}}`, where each aura carries `name`, `guid`, `type`, `abilityIcon`, `totalUptime`
in milliseconds, `totalUses`, and `bands: [{startTime, endTime}]`. `totalTime` is the queried
window in milliseconds.

Two consequences. The uptime is pre-aggregated, so no event pagination is needed. And `bands`
carry the exact intervals, so uptime over an arbitrary sub-window — boss pulls, say — is an
intersection rather than a second query. Confirmed by recomputing one aura's uptime over
fight 36's three boss pulls and matching the boss window the analyzers already derive.

**A buff band's `startTime` coincides with the cast that applied it, closely enough to trust
`start <= press <= end`.** Measured 2026-09-11 against the cached responses for report
`6Kx1P9GbNXrcLdHa`: of 1241 band-starts paired to a cast of the same ability within five
seconds, 842 were exactly equal. The pairing is by ability id across the whole cache rather
than per actor, because a cached `AuraTable` response carries no actor id — the actor lives in
the query variables, which are not cached — so this figure is an approximation, and the 41
later and 358 earlier pairings are as likely to be mispairings as real offsets. Same cache,
same date: 1189 pairs of bands on one aura touch or overlap, which is why drawing what one
press covered clips its own band rather than reusing the merged total `clipped_bands` computes
for `uptime_seconds_in`.

**An aura row's `guid` is the id of the buff, not of the spell cast to apply it.** Measured
2026-09-11 against the cached responses for report `6Kx1P9GbNXrcLdHa`: of 139 entries in
`data/defensives.toml`, 33 matched an aura guid directly and 2 distinct abilities matched only
by name — Alter Time, cast `108978` against aura `342246`, and Greater Invisibility, cast
`110959` against aura `110960` — while 100 did not appear because they were never cast in that
run.

## A name does not identify an ability, and an id does not identify a button

Measured 2026-09-11 against the cached responses under `cache/`, offline and at no quota cost.
Method: every cached page of a report joined, cast events de-duplicated on
`(sourceID, abilityGameID, timestamp)` because overlapping pages repeat them.

Of **1755 ability names** in `masterData.abilities`, **475 own more than one `gameID`**. Of the
**73 report-and-actor pairs that cast anything** (66 distinct actor ids, some recurring across
cached reports), **22 cast some name under two ids** — **28 such collisions** once every page of
a report is joined.

The tempting question is whether the two ids are one button logged twice or two real abilities,
and **the log does not answer it.** Applying the most obvious test — do casts of the two ids fall
within a second of each other — to all 28:

| Casts of the two ids pair within 1s | Collisions |
| --- | --- |
| Never | 18 |
| Always | 5 |
| Sometimes | 5 |

Five collisions sit in neither camp, and **Alter Time is one of them**: `342245`/`342247`, two
presses by one actor, one pair 159 ms apart and the other 4323 ms apart. Greater Invisibility
`110959`/`110960` pairs 3 of 3; Demonic Gateway `1214675`/`1214740` and Overwhelming Onslaught
`1243569`/`1297792` pair 0 of 4 and 0 of 6. The exemplar the reporting code was written for is
the ambiguous case, not a clean one.

**So never sum casts across ids that share a name.** Where one press does emit both ids, summing
reports two presses where the player made one, and no test tells you when that is happening.
Counting each id separately is right, because one press does emit one cast of that id. What needs
handling instead is a report printing the same sentence twice, which
`src/wowperf/domain/comparison/spells.py` does by collapsing on the rendered sentence rather than
on the name.

## The damage graph is pre-aggregated, and its points are a rate

Verified 2026-09-12 against report `G7MBJZfNakrcPvAx` fight 3, by schema introspection and by
running the queries. `Report` carries **`graph`** beside `events` and `table`: it takes the same
arguments as `table` plus `viewBy`, and returns `JSON`.

```
graph(dataType: DamageDone, hostilityType: Friendlies, fightIDs: [Int],
      startTime: Float, endTime: Float)
```

returns `{data: {series: [...], startTime, endTime}}`, where each series carries `name`, `id` (the
actor id), `guid`, `type` (the class), `pointStart`, `pointInterval`, `total`, and `data` — a plain
list of numbers whose times are implied by `pointStart + i * pointInterval`. **One call, no
pagination.** On this fight it returned six series for five players: one each, plus one whose `id`
is the string `"Total"` and whose `guid` and `total` are null.

- **The numbers in `data` are damage per second, not damage in the bucket.** Verified on all five
  series independently: `sum(points) * pointInterval/1000` reproduces that series' own `total` to
  within 0.3% to 0.7%. Reading them as amounts understates every bucket by `pointInterval` in
  seconds, which was 6.4 here. The residual's cause is not established -- see the reconciliation
  note below, which corrects an earlier claim recorded here.
- **The interval is the API's choice and there is no argument to set it.** 241 points across the
  window on this fight, so it appears to target about 240 buckets.
- **The five player series sum to the `Total` series** — largest gap at any bucket, 0.2.
- **`graph` folds a pet's damage into its owner.** The Death Knight's series total of 213,303,506
  equals that actor's `table(dataType: DamageDone)` entry total **with** its three pets, and not
  the 173,621,604 without them. 39,681,902 of that player's damage — 18.6% — came from pets. Four
  of the five players owned pets; only the Paladin owned none.
- **`table(dataType: DamageDone, hostilityType: Friendlies, fightIDs: [Int])`** returns
  `{data: {entries: [...]}}`, one entry per player, carrying `abilities`, `activeTime`,
  `activeTimeReduced`, `damageAbilities`, `gear`, `guid`, `icon`, `id`, `itemLevel`, `name`,
  `pets`, `talents`, `targets`, `total`, `totalReduced` and `type`. Each `pets` element carries its
  own `total`, and the entry's `total` already includes them.
- **`petOwner` on `masterData.actors` returns the owning actor's id**, and is absent on an actor
  that is not a pet. 39 of this report's 221 actors carried one.
- **`events(dataType: DamageDone)` is the wrong endpoint for a time series.** `queries.py` asks for
  `limit: 10000` and gets it: measured offline across 31 cached event pages, exactly one came back
  at 10000 rows carrying a `nextPageTimestamp` and every other came back short with none. This
  fight logs 8804 damage-taken events and 8423 friendly casts in one page each, so the damage
  **done** stream is a multiple of that and paginates. `graph` replaces those pages with one call.

The whole probe — one introspection and six queries — was taken inside one quota window that read
`pointsSpentThisHour: 8.44` at the end, so it cost at most that, of 3600.

**`DamageDoneGraph` costs 1.00 point**, measured 2026-09-12 on the first run that issued it from
`repository.py`: an otherwise warm-cache `--all-players` analysis of the same report and fight
spent 2.00 in total, composed as the command printed it — `DamageDoneGraph` 1 call for 1.00, and
`RateLimit` 2 calls for 1.00 with its last read unpriced. So one call at the same price as most of
this API's queries serves a whole roster, however many players are analysed.

**The rebuilt amounts reconcile with the API's own `total` to within 0.66%**, measured the same
day across all five series of that fight: −0.26%, −0.26%, −0.34%, −0.35% and −0.66%, every one of
them short rather than over.

**The cause of that shortfall is not established, and the explanation recorded here until
2026-09-12 was wrong.** It said the residual was the last bucket overhanging the fight: 241 buckets
of 6411.679 ms span 1545.2 s of a 1538.8 s window, 0.4% more than the window holds. That mechanism
predicts the wrong sign. Summing `rate x interval` over a stream that spans *more* time than the
window can only come out equal, if the extra bucket is empty, or **long** if it is not — never
short, and all five readings are short. Per-bucket rounding cannot account for it either: 0.26% of
a series totalling in the hundreds of millions is hundreds of thousands of damage, and rounding to
the nearest whole number over 241 buckets is bounded by a few hundred.

So the figures above stand as measurements and the mechanism does not. Re-measuring costs one
`DamageDoneGraph` call. What the reading is still good for is the diagnostic it was taken for: a
gap near a factor of 6.4 means the rate conversion was dropped somewhere after ingest, and a gap
under a percent means it was not.

**That reading was taken by summing the rendered page's bar hovers, and since 2026-09-12 it can no
longer be reproduced that way.** The figures above are about what `ingest.py` rebuilds, which is
unchanged and still every bucket the response carried. The player timeline now draws only the
buckets starting inside its own axis — first pull to last — and `graph` covers the whole fight, so
the page omits the bucket or two before the first pull, which on that report held over a million
damage for one player. Sum the ingested series to check this claim, never the hovers: the hovers
are now short by whatever fell outside the drawn window, and reading a shortfall there as a broken
conversion is the false alarm this note exists to prevent.

## The debuff half cannot be scoped to one caster

Corrected 2026-09-05 after Plan D's first run against the live API, which found this endpoint's
per-source filter does not work the way this project's original design assumed. Measured, against
the same report and fight:

| Arguments | Returns |
| --- | --- |
| `dataType: Debuffs, hostilityType: Enemies` | 42 auras — every debuff the whole group put on enemies, `Blood Plague` and `Vampiric Touch` and `Immolate` side by side |
| `dataType: Debuffs, hostilityType: Enemies, sourceID: <player>` | **0 auras** |
| `dataType: Debuffs, hostilityType: Enemies, filterExpression: "source.id = <player>"` | **0 auras** |
| `dataType: Debuffs, hostilityType: Enemies, sourceClass: "DeathKnight"` | **0 auras** |
| `dataType: Debuffs, sourceID: <player>` (no `hostilityType`) | 21 auras, but these are debuffs *on friendlies* — the default hostility — not the player's own |

So a per-player "debuffs I kept on the enemy" figure is not available from `table`. A group-wide
one is. Anything built on the per-player reading returns nothing, silently.

`AURA_TABLE_QUERY` no longer asks for the debuff table at all — removed 2026-09-11, after the
selection had shipped inert since 2026-09-05. `tests/adapters/wcl/test_ingest_auras.py` holds it
out. Removing it drops one of that query's two `table` selections, which plausibly lowers what
`AuraTable` costs; that is a prediction and nothing here has measured it.

## Gear and the secondary stat block

Measured 2026-09-14 against report `VCGkLQtPwNRA8HhD` fight 1 and report `6Kx1P9GbNXrcLdHa`
fight 36, five players each. The whole probe cost roughly 15 points of the 3600-point hour.

**`Report.playerDetails` returns a `JSON` scalar** and accepts `difficulty`, `encounterID`,
`endTime`, `fightIDs`, `killType`, `startTime`, `translate` and `includeCombatantInfo`.

**`combatantInfo` is `[]` unless `includeCombatantInfo: true` is passed** — an empty list, not an
object, which makes the field look empty on a first read. With the flag it is an object carrying
`artifact`, `factionID`, `gear`, `heartOfAzeroth`, `specIDs`, `stats`, `talentTree` and `talents`.

Each player entry carries `combatantInfo`, `guid`, `healthstoneUse`, `icon`, `id`,
`maxItemLevel`, `minItemLevel`, `name`, `potionUse`, `region`, `server`, `specs` and `type`,
grouped under `tanks`, `healers` and `dps`.

**`stats` holds ratings, not percentages**, each as `{min, max}`: `Crit`, `Haste`, `Mastery`,
`Versatility`, `Leech`, `Avoidance`, `Speed`, `Strength`, `Stamina`, `Item Level`. One player read
`Crit 904`, `Haste 865`, `Mastery 1196`, `Versatility 0`. Converting a rating to a percentage
needs a per-level coefficient that has no API source here. `min` equalled `max` for every stat of
every player observed.

**Cost: `playerDetails` with `includeCombatantInfo: true` priced at 2.00 points** from its own
`rateLimitData`.

**`talents` is empty on both routes.** `combatantInfo.talents` and the `talents` field on a
`DamageDone` table entry both returned `[]` for all ten players. Talents come from
`talentImportCode` and nowhere else.

**`table(dataType: DamageDone, hostilityType: Friendlies, fightIDs: [N])` priced at 0.00
points** and carries the same `gear` array, so it is the cheaper route when gear is wanted
without stats. Its entries carried `abilities`, `activeTime`, `activeTimeReduced`,
`damageAbilities`, `gear`, `guid`, `icon`, `id`, `itemLevel`, `name`, `talents`, `targets`,
`total` and `type` — **not `pets`**, which the 2026-09-12 note above records on the same entry.
The discrepancy is unexplained and nothing depends on it. Called without `fightIDs` the query
fails: *"You must either provide fightIDs, or provide startTime and endTime."*

**Each `gear` element** carries `id`, `slot`, `quality`, `icon`, `name`, `itemLevel`,
`permanentEnchant`, `permanentEnchantName`, `bonusIDs` and `setID`, plus `gems` where the item has
any. All eighteen slots, 0 to 17, appear for every player.

**Slot indices, read off icon filenames** rather than assumed: 0 head, 1 neck, 2 shoulder,
4 chest, 5 waist, 6 legs, 7 feet, 8 wrist, 9 hands, 10 and 11 rings, **12 and 13 trinkets**,
14 back, 15 main hand, 16 off hand. Slots 3 and 17 were not identified.

**An item-sourced cast joins to its item by name.** Warcraft Logs names an on-use trinket's spell
after the item. Against the 81 items equipped by the five players of `VCGkLQtPwNRA8HhD`, joined to
the 2834 distinct ability names in this project's cache: 5 item names are also ability names, 4 of
them trinkets, out of 10 trinkets equipped. The other six are passive and fire no named spell.
**This shows a name match indicates an item source; it does not show every item-sourced ability
matches by name.** A non-match means unknown, never "this is a class spell".

**`setID` needs a slot rule.** The tier set is class-specific and sits in slots `{0, 2, 4, 6, 9}` —
observed 2055 Death Knight, 2060 Mage, 2062 Paladin, 2063 Priest, 2064 Rogue, 2065 Shaman, 2067
Warrior, at 4 or 5 pieces. **Set 2070 spans classes**, appearing for four different ones in slots
12 and 15, and is not tier. Counting equal `setID`s without the slot rule over-counts.

**Enchantable slots do not need hardcoding.** Across ten players, slots 0, 2, 4, 6, 7, 10, 11 and
15 were enchanted 10/10; slots 1, 3, 5, 8, 9, 12, 13, 14 and 17 were 0/10; slot 16, the off hand,
was 1/10. The sample defines the rule: a slot is enchantable when every comparable member
enchanted it.

## Leaderboards return report codes

Verified 2026-09-03. Both `worldData.encounter.characterRankings` and
`worldData.encounter.fightRankings` return rows containing `report { code, fightID, startTime }`.
The pipeline "find a top run, then fetch its log" works end to end.

`FightRankingMetricType` includes `speed` and `score`. `CharacterRankingMetricType` includes
`playerscore`, documented as "used by WoW Mythic dungeons".

**Unverified convention:** community code current as of August 2026 uses
`bracket = keystoneLevel - 1` and passes `className` and `specName` together. Neither
appears in the documentation. The implementation must assert this rather than assume it.

**`playerscore` returns rows for tank and healer specialisations, not only damage.** Measured
2026-09-10 against encounter 12825 at keystone level 16, one query per specialisation on a real
five-player roster: Priest/Shadow 72 rows, DeathKnight/Blood 81, Shaman/Elemental 82,
Paladin/Holy 75, Mage/Arcane 82. The tank and the healer sit inside the same range as the three
damage specialisations, so a per-player parse comparison is not silently unavailable for two of
five players. Five queries spent 5.04 points, about 1.01 each, matching the `CharacterRankings`
price recorded above. This settles the first of the three things
`docs/plans/2026-09-10-per-player-page-design.md` §13 records as blocking J2.

**`worldData.encounter(id:)` takes the dungeon's encounter id, not a boss pull's.** Measured
2026-09-10, same run: `Run.encounter_id` is 12825 and returns rows, while the `encounterID` of a
boss `ReportDungeonPull` on that same run is 3209 and returns `encounter: null` — which this
project surfaces as `WclError: The rankings response carried no encounter`. Both numbers are
called an encounter id and only one addresses a leaderboard. A query with the wrong one still
costs its point.

## Terms of service

Read 2026-09-03 from the RPGLogs API Terms of Service. §5d prohibits scraping, building
databases, and creating permanent copies of content. §2c prohibits using multiple credentials to
multiply quota. On-demand fetching with local caching is normal use; a crawler that builds a
standing corpus of other players' logs is not.

Consequence: we never accumulate a dataset. Every reference run is fetched for one comparison and
cached only as long as it stays useful locally.

## Corrections to widespread errors

Two mistakes appear in current blog posts and would corrupt the design if inherited. Both
corrected 2026-09-03 against the schema.

- **rDPS, aDPS, nDPS and cDPS do not exist in World of Warcraft.** The schema annotates them
  as unique to Final Fantasy XIV. WoW has `dps`, `wdps`, `playerscore`, `hps`, `tankhps`, and
  `playerspeed`.
- **Warcraft Logs computes "Activity" from damage events, not cast events.** Damage-over-time
  ticks therefore mask real downtime. Honest cast-based uptime has to be counted from successful
  casts instead, and this project counts them from the API's own cast events rather than from a
  raw combat log it never reads: `events(dataType: Casts)`, keeping the events whose `type` is
  `"cast"`. Checked 2026-09-05 against `src/wowperf/adapters/wcl/queries.py` and
  `src/wowperf/adapters/wcl/ingest.py`. Whether those correspond exactly to the client's
  `SPELL_CAST_SUCCESS` lines is the community reading, unverified here; nothing in this project
  depends on it.
