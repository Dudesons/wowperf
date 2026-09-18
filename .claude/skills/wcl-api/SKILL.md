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
| `difficulty` | `ReportFight` | 2026-09-14 | yes |
| `size` | `ReportFight` | 2026-09-14 | yes |
| `fightPercentage` | `ReportFight` | 2026-09-14 | yes |
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
| `sourceID` | `table` argument | 2026-09-05 | yes |
| `targetID` | `table` argument | 2026-09-05 | yes |
| `targetID` | `events` argument | 2026-09-07 | yes |
| `includeResources` | `events` argument | 2026-09-07 | yes |
| `filterExpression` | `events` argument | 2026-09-07 | yes |
| `graph` | `Report` | 2026-09-12 | yes |
| `viewBy` | `graph` and `table` argument | 2026-09-12 | yes |
| `petOwner` | `ReportActor` | 2026-09-12 | no |
| `playerDetails` | `Report` | 2026-09-14 | yes |
| `includeCombatantInfo` | `playerDetails` argument | 2026-09-14 | yes |
| `bossPercentage` | `ReportFight` | 2026-09-16 | yes |
| `lastPhase` | `ReportFight` | 2026-09-16 | yes |
| `lastPhaseAsAbsoluteIndex` | `ReportFight` | 2026-09-16 | yes |
| `lastPhaseIsIntermission` | `ReportFight` | 2026-09-16 | yes |
| `phaseTransitions` | `ReportFight` | 2026-09-16 | yes |
| `wipeCalledTime` | `ReportFight` | 2026-09-16 | no |
| `phases` | `Report` | 2026-09-16 | yes |
| `separatesWipes` | `EncounterPhases` | 2026-09-16 | yes |
| `killerID` | `Deaths event` | 2026-09-16 | no |

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
- **`wowperf raid` with the parse axis, one subject, cold cache: 62.69 points of 3600**
  (2026-09-15, report `cW38jmwdnZfbHVL4` fight 2, a 20-player Heroic kill, one specialisation
  compared). Composed as the command printed it: `Talents` 6 calls for 13.62, `Fights` 5 for
  10.04, `Casts` 7 for 7.00, `Abilities` 6 for 6.00, `AuraTable` 5 for 5.00,
  `DamageDoneTargets` 5 for 5.00, `ReportRankings` 2 for 4.00, `RaidCharacterRankings` 2 for
  2.02, and the internal frame's own streams for the rest. **Both leaderboard pages together
  cost 2.02**, which is the free-board reading below holding at a second boss.
- **The same fight with `--all-players`, cold cache: 877.74 points of 3600** (2026-09-15, same
  report and fight). Twenty players held **nineteen distinct class-and-specialisation pairs**,
  so 38 `RaidCharacterRankings` calls for 38.38 and 95 reference kills drawn, over 92 distinct
  reference reports — three reports served two specialisations each and cost nothing the second
  time. Composed as the command printed it: `Talents` 94 calls for 212.77, `Fights` 93 for
  186.86, `Casts` 116 for 116.00, `DamageDoneTargets` 107 for 109.72, `AuraTable` 107 for
  107.00, `Abilities` 93 for 93.00, `RaidCharacterRankings` 38 for 38.38.
  `docs/plans/2026-09-13-raid-analysis-design.md` §14 item 6 **projected** roughly 730 for this
  shape from a 7.29-point-per-reference reading; the measurement is about 20% above that
  projection, and the difference is `Talents` and `Fights` at about 2 points each rather than
  one. One reading, of one report, against one day's leaderboards.
- **`wowperf raid` on an attempt that did not kill costs nothing for this axis at all**
  (2026-09-15, same report, fight 30, 45.25 points in total). No `RaidCharacterRankings`, no
  `AuraTable` and no `DamageDoneTargets` call appears in the breakdown: `Report.rankings`
  returns no row for a wipe, every family of the parse axis reads that row or a sample drawn to
  stand beside it, and `cli._parse_samples` therefore draws nothing. The 45.25 is the internal
  frame, of which 21.00 is one `Healing` query per death.
- **The one-subject raid shape re-run against a warm cache spent 1.00 point** — the two
  `RateLimit` reads and nothing else, within the reference cache's 24 hours.
- **This plan's own live run, cache warm from work done earlier the same day: the kill and the
  roster both re-priced to 1.00 point each** (2026-09-15, report `cW38jmwdnZfbHVL4`, fight 2, one
  subject and then `--all-players` naming all 20 raiders). Both spent only the two `RateLimit`
  reads the quota check itself makes, extending the one-subject warm reading above to the full
  twenty-player shape: once every class-and-specialisation pair's parse sample already sits on
  disk, naming all twenty costs no more than naming one. **The wipe re-priced close to cold**,
  because no fetch in this session's cache had ever touched fight 30 (`Ula'tek`, a different boss
  from fight 2's `Nek'zali the Soulcoiler`, found by listing the report's boss fights and reading
  its own already-cached `Fights` table for name and kill status, at no cost beyond the quota
  check): a `--no-compare` probe of it spent 36.20, and the recorded wipe run added 7.39 once the
  comparison axis ran, 43.59 together against the 45.25 recorded above for the same fixture. That
  1.66-point gap between two nominally-cold readings of the same fixture is unexplained: the API
  documents no per-query cost, and nothing recorded about either run points to a cause, so it is
  left as a gap rather than a guess. Total spent across every command this measurement ran, cold
  and warm together: 50.59 points of 3600, leaving 2672.33.
- **`wowperf progression` on an eight-attempt night, cold cache: 3.01 points of 3600**
  (2026-09-16, report `cW38jmwdnZfbHVL4`, encounter 3492, `Ula'tek` -- the same boss fight 30's
  wipe above names). One `Fights` query for the whole report, 2.01 points, plus the command's own
  opening `RateLimit` read; the closing read stays unpriced, as always. This is the design's own
  §7.1 cost claim -- one query answers a whole night -- measured rather than assumed: no attempt
  was deepened, so this reading is not comparable to the design's 40-to-60-point *projection* for
  a *deepened* night, which this plan's Layer 1 never approaches. **Re-run against the same,
  now-warm cache: 1.00 point** -- the two `RateLimit` reads and nothing else, no `Fights` line at
  all. `tests/e2e/test_progression_e2e.py` runs the equivalent query directly, without its own
  `RateLimit` calls, so its own marginal network cost is the `Fights` line alone: 2.01 points
  cold, every run, since it uses a fresh `tmp_path` cache each time.

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

**In every table measured, Mythic+ and raid alike, no band falls outside the fight it was
queried for.** The Mythic+ half was measured 2026-09-14 against every cached `AuraTable` response,
offline and at no quota cost. Method: a response's `totalTime` equals its fight's wall-clock
`endTime - startTime` exactly, so the pair `(endTime - totalTime, endTime)` identifies the
fight even where two reports share an `endTime`; 22 of the 49 cached tables join that way, and
over their 49,514 bands **none starts before its fight's `startTime` and none ends after its
`endTime`**. So a buff carried into the pull is reported clipped, and uptime summed over a
whole fight cannot exceed the fight — which is what lets
`comparison/uptime.seconds_up_over_the_fight` clip to nothing and still bound its own fraction.

Note what the response's own `startTime`/`endTime` are **not**: they read 0 and the fight end,
the query window rather than the fight, so they are no use as a bound.

Why the other 27 tables did not join, so the gap reads as an identification problem and not as
a counterexample: 12 carry an `endTime` no cached `fights` payload holds at all — a reference
run whose report query was never cached — and 15 match a cached fight's `endTime` while that
fight's span is **shorter** than the table's own `totalTime`, which is impossible for the same
fight and so an `endTime` collision between two reports. Not one of the 27 is a table joined to
its own fight and found to overhang it.

**The raid half, measured 2026-09-15: the same, and tighter.** Report `cW38jmwdnZfbHVL4`
fight 2 and the five reference kills its parse sample drew produced 5 raid `AuraTable`
responses, 2326 bands over 309 auras. Every one of the five joins a cached fight's own
`startTime`/`endTime` pair, and in each the earliest band start **equals** that fight's
`startTime` and the latest band end **equals** its `endTime` — clipped exactly to the fight, not
merely inside it. All five joins are exact to the millisecond, across five fights in five
different reports of five different lengths (316.48s, 375.04s, 212.91s, 407.09s, 276.53s), so
this is the endpoint clipping rather than five raids that happened to start and end on a buff.
`comparison/uptime.seconds_up_over_the_fight` divides band seconds by the fight's own
duration and clips neither side; this is what bounds its fraction at 100% on a raid as well as
on a key. `tests/e2e/test_raid_e2e.py::test_a_real_boss_kill_is_measured_against_the_world`
re-checks it on every live run, so a change at the endpoint fails a test rather than rendering
an uptime above 100%.

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

## A damage-taken table's row counts landings, not just hits

Measured 2026-09-14 against `table(dataType: DamageTaken, viewBy: Ability)` for a real raid kill.
Each entry carries `hitCount`, `tickCount`, `missCount`, `tickMissCount` and `sources` — these are
response keys inside the table's opaque JSON, the same class of field as the aura table's
`totalUptime`/`totalUses`/`bands` above, so they are documented here rather than as rows of the
machine-checked table: nothing in `queries.py` selects them by name, because `table(...)` returns
a `JSON` scalar with no sub-selection to check against.

Landings are `hitCount + tickCount`: summed together with `missCount` and `tickMissCount` over
the kill's 26 rows, all four totalled 11,456 — the event count for the same fight, exactly,
difference zero. `missCount` and `tickMissCount` count attempts that did not land and must never
be added to the other two. `mechanics.AbilityTakenRow.landings` reads exactly
`hit_count + tick_count`.

## `hostilityType` does not exclude friendly sources

Measured 2026-09-14 against `table(dataType: DamageTaken, viewBy: Ability)` for a real raid kill.

`HostilityType` has two values, `Friendlies` and `Enemies`. Omitting `hostilityType` and passing
`Friendlies` explicitly return byte-identical JSON — `Friendlies` is this table's default.
`Enemies` is not a filtered view of the same table: it returns the other side of the fight, 223
rows against this table's 26.

The argument selects whose damage-taken is tabulated, not which sources may appear in it.
**Friendly-sourced rows survive**: 8 of this kill's 26 rows were sourced entirely by players —
1.97% of the fight's damage-taken, Blessing of Sacrifice among them. Each entry's `sources` is a
list of `{name, type}`, one per source, and a row's `sources[].type` reads `"Boss"`, `"NPC"` or
`"Pet"` for a hostile source and a class name for a player; every row measured had homogeneous
sources. It is `sources[].type` — not `hostilityType` — that separates a mechanic from a
self-inflicted or ally-sourced hit, and `AbilityTakenRow.source_types` carries it for the domain
to judge, in `src/wowperf/domain/comparison/mechanics.py`.

## A damage-taken table's damage is mitigated

Measured 2026-09-14, same table and kill. Each entry's `total` equals the event stream's health
damage plus absorbs, and `totalReduced` equals health damage alone — both are **mitigated**
figures. The unmitigated figure that a per-player damage ranking is built on is not exposed by
this table and is not reconstructible from what is: the gap between the two reached 4.61x on one
fight. `AbilityTakenRow` stores neither `total` nor `totalReduced` for this reason — see its
docstring in `src/wowperf/domain/comparison/mechanics.py`.

## Gear and the secondary stat block

Measured 2026-09-14 against report `VCGkLQtPwNRA8HhD` fight 1 and report `6Kx1P9GbNXrcLdHa`
fight 36, five players each. The whole probe cost roughly 15 points of the 3600-point hour.

**`Report.playerDetails` returns a `JSON` scalar** and accepts `difficulty`, `encounterID`,
`endTime`, `fightIDs`, `killType`, `startTime`, `translate` and `includeCombatantInfo`.

**The envelope wraps the roster in a `data` key.** The probe behind every number in this
section traversed exactly `response["reportData"]["report"]["playerDetails"]["data"]["playerDetails"]`
against the live API, measured 2026-09-14. `playerDetails` returns a `JSON` scalar, and like
`graph` and `table` elsewhere in this codebase, its payload sits one level down from the field
itself, under a `data` key.

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

**A full-roster analysis multiplies that call, not just its cost.** Measured 2026-09-14 on an
`analyze --all-players` run against a five-player roster: 19 `PlayerDetails` calls for 38.00
points, inside a 219.47-point total against the 3600-point hourly budget. The driver is that
each analysed player draws its own specialisation's parse sample, and each reference report
needs its own fetch. `Talents` and `Fights` issued exactly the same 19 calls on that run, so
this scaling predates the gear work rather than being introduced by it.

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

## `fightRankings` takes `difficulty` and `partition`, and `execution` is a deathless-kill board

Verified 2026-09-04 against the live schema (recorded in
`docs/plans/2026-09-04-mplus-comparison-plan.md`'s "Verified schema" table) and again 2026-09-13
against a real raid encounter (`docs/plans/2026-09-13-raid-analysis-design.md` §2.1):
`Encounter.fightRankings` and `Encounter.characterRankings` each accept `difficulty: Int` and
`partition: Int` alongside `bracket`. Mythic+ passes `bracket`; a raid boss has no keystone level
and passes `difficulty` and `partition` instead. `FightRankingMetricType` offers `default`,
`execution`, `feats`, `score`, `speed` and `progress`.

Measured 2026-09-14: querying one boss's `fightRankings` under three metrics, `default` and
`speed` return byte-identical row sets with deaths ranging 0 to 20, while `execution` is a
separate board overlapping them on 7 of 50 rows with deaths ranging 0 to 1 — the near-deathless
kills a mechanics comparison wants as its reference. `progress` carried a null `report.code` on 39
of its 50 rows; `execution` carried none, but the shape exists and `build_reference_kill_rows`
drops any row it finds.

A `fightRankings(metric: execution)` row carries `report { code, fightID }`, `size`, `duration`
and `deaths` — response keys nested inside the endpoint's opaque JSON, the same class of field
as the aura table's `totalUptime`/`totalUses`/`bands` above, so they are documented here rather
than as rows of the machine-checked table: nothing in `queries.py` selects them by name, because
`fightRankings(...)` returns a `JSON` scalar with no sub-selection to check against.
`ReferenceKillRow.duration_seconds` divides `duration` by 1000, exactly as `SpeedRow` does.

**Corrected 2026-09-14: `fightRankings` echoes no `difficulty` per row.** The paragraph above
used to list `difficulty` alongside `size`, `duration` and `deaths` as a field the row itself
carries, on the strength of an entry "verified... 2026-09-13 against a real raid encounter."
That entry was wrong. Measured live against report `cW38jmwdnZfbHVL4`, both fight 2 (encounter
3470) and fight 30 (encounter 3492), 50 rows apiece: every row's keys are exactly `server`,
`duration`, `startTime`, `report`, `damageTaken`, `deaths`, `tanks`, `healers`, `melee`, `ranged`,
`guild`, `bracketData`, `size` -- `difficulty` is absent from all 100 rows checked, on two
different encounters, both requested with `difficulty: 4`. `difficulty` is a request argument to
`fightRankings` only (see the paragraph above this one); the API never echoes it back on a row,
and no field in the response substitutes for it -- `bracketData` was observed but its meaning is
not verified, and this project does not guess at what an unverified field holds. The offline
fixture exercising `build_reference_kill_rows` had hardcoded `"difficulty": 4` into its rows,
which is why this went unnoticed until a live run: the row shape under test did not occur.
`select_reference_kills` filtered on `row.difficulty == our_difficulty` for the same reason and
has had that filter removed rather than back-filled, since `reference_kills` already passes our
own difficulty as the query argument -- every row the API returns is at that difficulty already,
so the per-row check could never have failed in production.

**A row carries `size` only where the difficulty lets raid size vary. Measured 2026-09-18.**
The key set above was taken at `difficulty: 4` on both encounters, and it does not hold at
`difficulty: 5`. On report `DJfap6RcYKhPGHXZ`, whose two raid encounters differ in little else:
encounter 3492 at difficulty 4 carried `size` on all 50 rows, and encounter 3470 at difficulty 5
carried it on none of its 50. Each board returned exactly one distinct row key set, so `size` is
absent from the Mythic board altogether rather than optional on it. The reading is consistent
with the API omitting a field that cannot vary -- Mythic raid size is fixed at 20, and every
difficulty below it is flexible -- but the mechanism is inferred and only these two difficulties
were read.

`build_reference_kill_rows` read `row["size"]` bare, so `wowperf raid` died with `KeyError` on
every Mythic boss fight ever passed to it. **The role counts are the substitute, and they are
measured rather than assumed:** on the difficulty-4 board, where both are present,
`tanks + healers + melee + ranged` equalled `size` on 50 of 50 rows with no disagreements. The
row's own `size` is still preferred wherever the board states one.

This is the second defect on this board found by a row shape that did not occur offline, and the
paragraph above names the first. Both times the fixtures were right and an argument had simply
never been passed: `difficulty: 4` hardcoded into a fixture the first time, and no live run ever
made at `difficulty: 5` the second. **The question that finds this class is which argument values
the live runs have actually taken**, not whether a live run happened.

**A row's `deaths` counts death events, not the players behind them. Measured 2026-09-18.**
Twelve rows of encounter 3492's `default` board at `difficulty: 4, partition: 1`, each joined to
its own fully paginated `events(dataType: Deaths)` stream for the report and fight the row names.
**Four of the twelve had at least one player die more than once, and those four are the only ones
that can tell the two readings apart**: on all four the row's `deaths` equalled the death-event
count and differed from the count of distinct `targetID`s -- claimed 6 against 6 events and 5
players, claimed 5 against 5 and 3, claimed 5 against 5 and 4, claimed 4 against 4 and 3. On the
remaining eight nobody died twice, so both counts agreed and neither reading is excluded by them.
Across all twelve, `claimed == events` held 12 of 12 and `claimed == distinct players` held 8 of
12. The whole probe cost 35.6 points of 3600.

So anything set beside this field has to be an event count. `attempt_shape.classify_attempt`
compared a count of distinct players against a median of it until this was measured, and
`compare_lethal_abilities` counted events correctly while wording them as players; both are
corrected.

**The board to take this reading on is not encounter 3470's.** The 2026-09-14 note above records
`default` and `speed` there "with deaths ranging 0 to 20"; measured again 2026-09-18, the same
board at the same difficulty and partition read `{0: 40, 1: 9, 2: 1}` -- a maximum of 2 over 50
rows, which cannot separate an event from a player at all. Encounter 3492's board at the same
difficulty read `{0: 7, 1: 15, 2: 9, 3: 8, 4: 6, 5: 2, 6: 3}`. Whether the 0-to-20 reading was of
a different board or the board has simply moved in four days is not established, and the older
line is left standing rather than overwritten: what is recorded here is that a range deep enough
for this measurement has to be looked for rather than assumed.

## A difficulty's name lives on its zone, not on the fight or the encounter

Introspected 2026-09-15, looking for something `raid_frame.py`'s header could print instead of
`Encounter.difficulty`'s bare int. **Neither `ReportFight` nor `worldData.encounter` carries a
difficulty name.** `ReportFight`'s full field list (introspected the same day) returned 43 names
including `difficulty`. The following twenty-four are transcribed verbatim from that response,
not recalled — `averageItemLevel`, `bossPercentage`, `completeRaid`, `countReached`,
`countRequired`, `dungeonPulls`, `encounterID`, `endTime`, `fightPercentage`, `friendlyPlayers`,
`gameZone`, `hardModeLevel`, `id`, `keystoneAffixes`, `keystoneBonus`, `keystoneLevel`,
`keystoneTime`, `kill`, `layer`, `name`, `npcCountMap`, `rating`, `size`, `startTime` — the other
nineteen are not reproduced here, and none of the forty-three fields names a difficulty.
`worldData.encounter(id:)`'s type carries exactly `id, name, characterRankings, fightRankings,
zone, journalID`; no name there either.

**A name exists one hop further out, on the zone.** `worldData.zone` (and `encounter(id:).zone`)
carries `id, name, brackets, difficulties, encounters, expansion, frozen, partitions`, and
`Zone.difficulties` returns `[Difficulty]` with fields exactly `id, name, sizes`. Queried live
against `worldData.encounter(id: 3470) { zone { id name difficulties { id name sizes } } }` —
encounter 3470 is the same one this file already names "Heroic" below, from report
`cW38jmwdnZfbHVL4` fight 2, requested with `difficulty: 4` — the zone (id 53, "The Venomous
Abyss") named its own four difficulties: id 5 "Mythic" (sizes `[20]`), id 4 "Heroic" (no size
listed), id 3 "Normal" (no size listed), id 1 "LFR" (no size listed). `difficulty: 4` naming
"Heroic" here is consistent with this file's own 2026-09-14 note below, which already described
encounter 3470 as Heroic — prior descriptive knowledge, recorded without the query that produced
it, not a second independent measurement.

**This is a real, live-verified source, and it is still not what this project reads for a raid
header.** Getting from an `Encounter` to its zone's difficulty names needs a second `worldData`
query beyond the one that already fetches the fight, threaded through the adapter and passed in
— `build_raid_header(encounter: Encounter) -> RaidHeader` in `raid_frame.py` takes a bare
`Encounter` and performs no query of its own, being domain code. Wiring that second query through
is future work, not this task's. Until then, `raid_frame.py` hand-keeps the same three names
this query returned for ids 3, 4 and 5, dated 2026-09-15 against it, and prints the bare number
for any id it does not carry.

## A report carries its own players' ranks, and their amounts

Measured 2026-09-14 against report `cW38jmwdnZfbHVL4` fight 2 (encounter 3470, Heroic, 20
players), by schema introspection and by running the queries. The whole probe -- three
introspections and three queries -- cost 12.2 points of 3600 on a cold cache.

**`Report.rankings` takes six arguments**: `compare: RankingCompareType`, `difficulty: Int`,
`encounterID: Int`, `fightIDs: [Int]`, `playerMetric: ReportRankingMetricType`,
`timeframe: RankingTimeframeType`. **There is no `partition` argument** -- partition comes back
on the row and is never sent.

**`ReportRankingMetricType`**, the enum `playerMetric` accepts, holds `bosscdps`, `bossdps`,
`bossndps`, `bossrdps`, `default`, `dps`, `hps`, `krsi`, `playerscore`, `playerspeed`, `cdps`,
`ndps`, `rdps`, `tankhps` and `wdps`. **`CharacterRankingMetricType`** holds all of those plus
sixteen `healercombined*` and `tankcombined*` variants.

This **amends, rather than contradicts, the 2026-09-03 line under "Corrections to widespread
errors"** below, which reads "WoW has `dps`, `wdps`, `playerscore`, `hps`, `tankhps`, and
`playerspeed`". That list was taken before this project sent a raid query and is incomplete:
`bossdps` is a real World of Warcraft metric and returns 100 fully populated rows. What that
correction got right and this does not disturb is that `rdps`, `ndps` and `cdps` describe
themselves in the schema as unique to FFXIV, and `rdps` fails at the server.

**The payload is a `JSON` scalar whose top level is exactly one key, `data`**, holding a list of
rows -- one row per requested fight. A row's keys, all seventeen: `bracket`, `bracketData`,
`damageTakenExcludingTanks`, `deaths`, `difficulty`, `duration`, `encounter`, `execution`,
`fightID`, `guild`, `kill`, `partition`, `reportsBlacklistForCharacters`, `roles`, `size`,
`speed`, `zone`.

**`roles` has exactly three keys** -- `tanks`, `healers`, `dps` -- each an object holding
`characters`, a list. A character entry's keys, all thirteen: `amount`, `best`, `bracket`,
`bracketData`, `bracketPercent`, `class`, `id`, `name`, `rank`, `rankPercent`, `server`, `spec`,
`totalParses`.

**The entry carries the player's own throughput as `amount`, and the two metrics differ.** One
tank read 59991.462335693 under `playerMetric: dps` and 44818.47826087 under
`playerMetric: bossdps` -- a ratio of 0.747. `rankPercent` moved 80 to 87 and `bracketPercent`
73 to 81 for the same player. So one query returns every player's own figure and their
percentile together, for 2.00 points, whatever the roster's size.

**`rank` and `best` are strings, not integers.** They read `"~5764"` and `"~3746"` -- with a
leading tilde, which `int()` rejects. `rankPercent`, `bracketPercent` and `totalParses` are
integers.

**A wipe returns an empty list.** Recorded 2026-09-14 in
`docs/plans/2026-09-13-raid-analysis-design.md` section 14 item 7: a kill returned one row and
the wipe returned none, with no field distinguishing the cases. Code tests for emptiness.

**`id` on a character entry is a Warcraft Logs character id, not a report actor id.** One read
seven digits on a report whose actor ids are small integers. Joining a rankings entry to a
`ReportFight` roster is done on the name, never on the id.

## A raid `characterRankings` row is not a Mythic+ one

Measured 2026-09-14 against encounter 3470 at `difficulty: 4, partition: 1`, one specialisation,
under both `dps` and `bossdps`. 100 rows each, **0.0 points each**.

A row's keys, all thirteen: `amount`, `bracketData`, `class`, `duration`, `faction`, `guild`,
`hardModeLevel`, `name`, `report`, `server`, `size`, `spec`, `startTime`.

**`score`, `medal` and `affixes` are absent**, and `build_parse_rows` in
`src/wowperf/adapters/wcl/rankings.py` reads all three. It also writes `row["bracketData"]` into
a field named `keystone_level`; on a raid board `bracketData` read **319 to 325**, which is not a
keystone level. **What it does mean is not verified**, and nothing in this project reads it on
this axis rather than guessing.

**`amount` is a rate, not a total.** The first four `dps` rows read 247358.16, 240273.40,
237153.76 and 236147.44 against durations of 407086, 375044, 276534 and 321355 ms: the board
descends by `amount` while `amount x duration` swings from 65.6M to 100.7M, so the ordering is by
a per-second figure. `Report.rankings`' own `amount` is the same unit. Neither side of a
throughput comparison needs dividing by a duration, and dividing one of them would be the
count-against-rate mistake that reached a user-visible sentence on 2026-09-14.

**The two metrics' boards hold different reports.** The `bossdps` board's first four durations
were 173050, 212911, 231133 and 263277 ms against the `dps` board's 407086, 375044, 276534 and
321355 -- different rows, not a reordering. Drawing reference reports from both boards doubles
the fetch.

**Raid size varies widely on a parse board.** The `dps` board's first four rows read `size` 29,
30, 29, 30 and the `bossdps` board's 29, 24, 23, 25, against an analysed raid of 20.

**`duration` on a raid board matches the fight's own wall-clock length, for every reference
checked so far.** Measured 2026-09-15 against the same `dps` board above (encounter 3470,
difficulty 4, partition 1, Evoker/Devastation): for its first five rows, each row's own
`duration` was checked against `endTime - startTime` read from `FIGHTS_QUERY` for the report and
fight that same row names. All five agreed to the millisecond -- durations 407086, 375044,
276534, 321355 and 212911 ms, the same four leading rows the paragraph above already quotes plus
a fifth, every one with a signed difference of exactly 0 ms. The whole check -- one
`RaidCharacterRankings` board plus five `Fights` calls -- cost 13.05 points of 3600,
`RaidCharacterRankings` itself billing 2.01 this time against the 0.0 recorded above for the same
board: not reconciled, and not this measurement's question.

**This says nothing about the Mythic+ board, which does not behave this way.** A cache
measurement over 113 Mythic+ `characterRankings` references found `duration` equal to
`endTime - startTime` zero times, differing from -11s to +96s in a pattern shaped like a
keystone timer -- consistent with a Mythic+ board's `duration` counting the keystone timer rather
than the fight's wall clock, though nothing here traces the mechanism. The two boards are not
shown to measure the same quantity; they are shown, on the readings taken so far, to disagree in
one case and agree in the other.

**What this does not show:** five references, one boss, one difficulty, one partition, one
specialisation, one metric (`dps` -- the `bossdps` board above draws a different set of reports
and rows, and was not checked). Whether `duration` still matches the fight's own length on a
different encounter, a different difficulty, or under `bossdps` is unmeasured, and so is every
raid board beyond this one specialisation on this one day.

**This board omits `size` at difficulty 5 too, and offers nothing to derive one from. Measured
2026-09-18** against encounter 3470 at `difficulty: 5, partition: 1`, one specialisation, `dps`,
100 rows: none carried `size`, and none carried the role counts `fightRankings` falls back on --
so unlike the execution board, no substitute exists in the response. Three distinct key sets
appeared across the 100 rows: 87 as listed above minus `size`, 12 of those without `guild`, and
one without `guild` or `server` but carrying `hidden`. **`guild` and `server` are therefore
optional on this board**, which the thirteen-key list above does not say.

`RaidParseRow` no longer carries a size at all. Nothing read one -- the parse boards are
deliberately not filtered by raid size, for the reason the paragraph above gives -- and
`build_raid_parse_rows` read `row["size"]` bare, which crashed `wowperf raid` on every Mythic
boss fight one board further along than `build_reference_kill_rows` did.

## A damage-done table split by target names the boss itself

Measured 2026-09-14, same report and fight. `table(dataType: DamageDone, fightIDs: [N],
viewBy: Target)` returned three entries whose `type` read `'NPC'`, `'Boss'` and `'NPC'`, with
`total` 144629000, 498963668 and 111365043. Entry keys: `abilities`, `activeTime`,
`activeTimeReduced`, `damageAbilities`, `given`, `guid`, `icon`, `id`, `name`, `sources`,
`taken`, `total`, `totalRDPSGiven`, `totalRDPSTaken`, `totalReduced`, `type`.

So separating a boss from its adds needs no per-encounter rule and no boss table: the row's own
`type` does it. This call was unscoped; the `sourceID`-scoped version was measured at 0.94 points
on 2026-09-13, and 1.03 over 107 calls on 2026-09-15.

**No table measured has carried more than one `Boss` row.** Measured 2026-09-15 over the five
`sourceID`-scoped tables a live parse sample fetched for report `cW38jmwdnZfbHVL4` fight 2 —
our own subject's and four references' — each of which returned three entries with exactly one
`type: 'Boss'` among them. The boss row's position varies (first, second and third all
occurred), so nothing may assume an index. `comparison/targets._boss_share` reads the first
`Boss` row and folds any others into "everything else"; on seven tables across two encounters
there has never been another, so the behaviour is unobserved rather than known to be safe. A
two-boss encounter — a council fight — is the shape that would test it, and none has been read.

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

## Phases are named by the API, so no phase table needs writing

Introspected 2026-09-16, looking for whatever a progression report could say about how far an
attempt got. **`ReportFight` carries 43 fields and six of them are about how an attempt ended**:
`bossPercentage`, `fightPercentage`, `lastPhase`, `lastPhaseAsAbsoluteIndex`,
`lastPhaseIsIntermission` and `phaseTransitions`. The full 43 were read in one introspection; the
twenty-four transcribed under "A difficulty's name lives on its zone" remain accurate and this
section adds the phase half rather than restating them.

The phase vocabulary is three types, each read verbatim from the introspection response:

- `Report.phases` returns `[EncounterPhases]`.
- `EncounterPhases` carries exactly `encounterID`, `separatesWipes`, `phases`.
- `PhaseMetadata` carries exactly `id`, `name`, `isIntermission`.
- `PhaseTransition` carries exactly `id`, `startTime`.

**So a phase's human-readable name comes from the API.** `docs/plans/2026-09-13-raid-analysis-design.md`
§3.3 forbids encoding a phase table, and nothing needs encoding: the names are fetched. Measured
against report `cW38jmwdnZfbHVL4` the same day, `Report.phases` returned six entries, one naming four phases
including an intermission flagged by `isIntermission`.

**`separatesWipes` varies by encounter and is the API's own opinion.** Of the three entries
inspected, two read `true` and one read `false`. Read it as Warcraft Logs stating whether phase is
a meaningful way to group that encounter's attempts, and gate any phase claim on it.

**`phaseTransitions` is not a ladder.** One encounter's transitions ran `1, 2, 1, 2, 1` and
another ran `1, 2, 1, 3, 1`, both within a single attempt. On such an encounter neither the last
phase nor the highest phase reached means progress. Two other encounters reported `lastPhase: 0`
with no transitions at all, which is a boss with no phases rather than an error.

**`wipeCalledTime` exists and was `null` on all nineteen fights of that report.** Present in the
schema, absent from the data. Do not build on it without measuring it somewhere it is populated;
this file's opening warning exists because of exactly this shape of field.

## Warcraft Logs does not attribute a death to another player

Measured 2026-09-16 against a fight chosen because a raider who was there reported a death caused
by another player passing a mechanic to them. **Across all 15 deaths, `killerID` was never a
friendly player.** Where it is set it names an enemy actor; it is `null` on 7 of the 15. The
killing blow on the death in question is credited to the boss.

A death event carries exactly `abilityGameID`, `fight`, `killerID`, `killingAbilityGameID`,
`sourceID`, `targetID`, `timestamp`, `type`. `sourceID` read `-1` on every one of the 15.

**So "player A killed player B" is not a fact this API reports.** It can only be reconstructed
from a player-to-player application followed by damage credited to the encounter, and every link
in that chain is an inference. `docs/plans/2026-09-16-progression-analysis-design.md` §9.1 carries
the measurement that must come before anything is built on it.

## Damage-taken events name their source, and some of it is friendly

Measured 2026-09-16 on one 20-player wipe (report `cW38jmwdnZfbHVL4` fight 30), both pages of the
stream. **Every one of 2009 damage-taken rows carried `sourceID`**, and **357 of them (17.8%) had a friendly player as the
source, across 6 distinct abilities**.

A damage-taken event carries `timestamp`, `type`, `sourceID`, `targetID`, `abilityGameID`,
`fight`, `hitType`, `amount` and `isAoE` on every row, and `unmitigatedAmount`, `buffs`,
`mitigated`, `absorbed`, `tick`, `targetMarker`, `sourceInstance`, `sourceMarker` and `blocked` on
some.

**Corrected 2026-09-16.** This paragraph ended "`DamageTakenEvent` in
`src/wowperf/domain/events.py` keeps none of the source fields today", and that was already false
when it was written. `source_id: int | None` has been a field on `DamageTakenEvent`, populated by
`build_damage_taken` from `sourceID`, since `fd90170` on 2026-09-11. The source fields the ingest
really drops are `sourceInstance` and `sourceMarker`. The same claim reached
`docs/plans/2026-09-16-progression-analysis-design.md` §2.6 and is corrected there too. This is
the shape of defect this file's opening warning exists for — a claim about our own code, written
without running it.

`EventDataType` offers exactly fourteen values, transcribed from the same introspection: `All`,
`Buffs`, `Casts`, `CombatantInfo`, `DamageDone`, `DamageTaken`, `Deaths`, `Debuffs`, `Dispels`,
`Healing`, `Interrupts`, `Resources`, `Summons`, `Threat`.

**The `Debuffs` stream carries player-to-player applications, and its composition is unmeasured.**
A *different* fight -- the one the section above measures death attribution on, not the one this
section's damage figures come from -- returned 610 events whose source and target were two
different friendly players,
split `applydebuff` 308, `removedebuff` 217, `refreshdebuff` 51, `applydebuffstack` 34. Several of
the most frequent ability ids resemble ordinary class debuffs rather than a passed raid mechanic,
so **this count is not yet evidence that a passed mechanic can be isolated**. Treat 610 as an
upper bound on the signal and nothing more until the composition is measured.

**Measured 2026-09-16. It is composed of ordinary class debuffs.** See the section below.

## The player-to-player debuff stream is class debuffs, measured

Measured 2026-09-16 over **every boss fight in report `cW38jmwdnZfbHVL4`: 19 fights across 8
encounters, 26,328 rows** of `events(dataType: Debuffs, hostilityType: Friendlies)`, fully
paginated. A row counts as player-to-player when `sourceID` and `targetID` are both in
`masterData.actors(type: "Player")` and differ. **1,900 rows qualified, across 67 distinct
abilities.**

**Two facts decide it.**

**First, 1,857 of the 1,900 (97.7%) come from two fights on one encounter.** Every other fight in
the report produced between 0 and 10. A phenomenon confined to one encounter out of eight is not a
population to build a general finding on.

**Second, 64 of the 67 abilities are applied by exactly one class**, and they are named class
debuffs: `Chaos Brand` from the one Demon Hunter, `Chilled` from a Mage, `Rend` and `Thunder Clap`
from Warriors, the Death Knight's `Famine`/`Death`/`War`/`Pestilence`, Rogue poisons,
`Mystic Touch` from a Monk. Of the three exceptions, two are shared class effects —
`Resurrecting` (160029) from the two battle-resurrection classes, already documented above, and
`Mortal Wounds` (115804) from a Monk and a Warrior. **The third, `Rune of Lingering` (1287663), is
sourced by 12 of the 13 classes present, from 18 distinct actors.** No class owns it. It is the
only ability in 1,900 applications whose source profile is not explicable as a class ability, and
the log says nothing about what it is.

**Two discriminators were tested, neither encoding any boss knowledge:**

| Discriminator | Result |
| --- | --- |
| The ability also arrives from a non-player source on the same fight | 2 of 67 — and both are class debuffs (`Mortal Wounds`, `Blood Plague`). Useless, and it produces false positives. |
| The ability is applied by more than one class | 3 of 67, of which 2 are shared class effects. Isolates one candidate, with no way to confirm what it is. |

**A positive control settles it, and the reason is stronger than the one above.** Measured
2026-09-16 against a death a raider reported as caused by another player passing them a mechanic
(report `cW38jmwdnZfbHVL4`, fight 26, the subject is actor 21, who supplied the log). The ability
is `Gloombomb`, ids 1310881, 1310882 and 1310883.

**Every Gloombomb row in either stream is sourced to an NPC.** All 18 debuff applications and
removals, and all 22 damage rows, carry `sourceID: 238`. Not one names a player. The log records
"the boss's Gloombomb hit this player", identically for every target, so **the carrier whose bomb
reached a victim is not in the event at all.**

So the player-to-player stream was never where this mechanic lived, and the composition above —
however it had come out — could not have decided it. **Searching for a passed mechanic among
player-sourced events is searching the wrong stream.**

**What the log does carry is the spread, and it needs no boss knowledge.** Three detonations on
that fight, each preceded by the debuff on exactly three players:

| Detonation | Carried it | Took the damage | Spread past its carriers |
| --- | --- | --- | --- |
| 1 | 3 | 12 | 9 |
| 2 | 3 | 3 | **0** |
| 3 | 3 | 7 | 4 |

The second detonation is the same mechanic executed cleanly, and it is the control that makes the
other two readable. **The derivable rule is generic**: a debuff removed from N actors, followed
within about a second by damage from the *same ability id* to M actors, where M > N. It encodes no
encounter, names no carrier, and distinguishes a mechanic that was contained from one that was
not. Nothing in this project reads it yet.

**So a passed raid mechanic cannot be separated from a rogue's bleed by anything measured here.**
`docs/plans/2026-09-16-progression-analysis-design.md` §9.1 says that if it cannot, the feature is
cut rather than hedged. It is cut. Reopening it needs a **positive control**: a fight where a
passed mechanic is known to have occurred, so a candidate can be confirmed rather than guessed at.

**The 610 figure above was not reproduced.** No fight in this report produced it: the two large
fights read 904 and 953, and every other fight reads 10 or fewer. Either that measurement was of a
different report, or it counted by a different rule. Recorded rather than resolved.

## Friendly-sourced damage is 90% self-damage, and the rest is one encounter

Measured 2026-09-16 over the same 19 fights, **139,891 rows** of
`events(dataType: DamageTaken, hostilityType: Friendlies)`, fully paginated, counting only rows of
`type: "damage"`.

| Population | Rows | Share |
| --- | --- | --- |
| All damage rows | 139,891 | — |
| `sourceID` is a friendly player | 22,989 | 16.4% |
| …of which `sourceID == targetID` (self-damage) | 20,663 | **89.9% of the friendly-sourced** |
| …of which one player to a *different* player | 2,326 | **1.66% of all rows** |

**This corrects the reading in the section above.** That section reports "357 of them (17.8%) had
a friendly player as the source" for fight 30 and treats it as the evidence for a player-sourced
finding. At whole-fight scope fight 30 reads **15,798 damage rows, 2,371 friendly-sourced
(15.0%), and only 34 player-to-a-different-player** — the friendly-sourced figure is dominated by
self-damage, which the design that cites it excludes by its own rule. The 17.8% and 15.0% shares
agree; the conclusion drawn from the 17.8% does not survive splitting self-damage out. The 2009
row count was not reproduced either and is consistent with a per-player scope rather than a
whole-fight one.

**2,227 of the 2,326 (95.7%) come from the same two fights on the same one encounter** as the
debuff finding above, and every ability in them is an ordinary class damage ability from the class
that owns it — `Virulent Plague`, `Rend`, `Immolation Aura`, `Frozen Orb`, `Rupture`, `Moonfire`,
`Starfall`. The shape is a raid damaging a raid member the encounter turned hostile.

**Outside that encounter the whole report yields 99 hits across 17 fights.** The design's own
eight-attempt fixture night (encounter 3492) yields **34 hits of one ability across 7 qualifying
attempts**, and that ability is `Blessing of Sacrifice` (6940) — a Paladin cooldown that redirects
damage *away* from an ally. Its recorded source classes across the report are DeathKnight, Evoker,
Rogue and Warrior, so **the "source" of that damage is the protected player, not the Paladin**.
The one ability that appears across five encounters is therefore one where "player-sourced" names
the wrong player and the correct play.

**So `source_id` on `DamageTakenEvent` earns its place by exclusion, not by attribution**: it is
how an analyser keeps a rogue's Rupture out of a list of what repeatedly hits the raid.

## `lastPhase` is a phase id; `lastPhaseAsAbsoluteIndex` is not

Measured 2026-09-16 across all 8 encounters of report `cW38jmwdnZfbHVL4`, reading one fight per
encounter against that encounter's `Report.phases` entry. Costs nothing: `FIGHTS_QUERY` already
selects every field involved.

| Encounter | `separatesWipes` | `Report.phases` ids | `lastPhase` | `lastPhaseAsAbsoluteIndex` | that fight's transition ids |
| --- | --- | --- | --- | --- | --- |
| 3470 | `true` | 1, 2, 3 | 2 | 2 | 1, 2, 3 |
| 3445 | `false` | 1, 2 | 1 | 2 | 1, 2, 1 |
| 3455 | *no entry* | — | 0 | 0 | — |
| 3497 | `false` | 1, 2, 3, 4 | 1 | 4 | 1, 2, 1, 3, 1 |
| 3420 | `false` | 1, 2 | 1 | 0 | 1 |
| 3421 | *no entry* | — | 0 | 0 | — |
| 3429 | `true` | 1, 2, 3, 4 | 1 | 0 | 1 |
| 3492 | `true` | 1, 2, 3, 4 | 2 | 1 | 1, 2 |

**`lastPhase` is a `PhaseMetadata.id`.** On all 8 it is either a value in that encounter's own
phase id list, or `0` where the encounter has no phases at all. **So a phase name can be looked up
by matching `lastPhase` against `Report.phases[].phases[].id`**, and a `lastPhase` of 0 means a
boss with no phases rather than a missing reading.

**`lastPhaseAsAbsoluteIndex` is not a phase id, and reading it as one is wrong on 5 of these 8.**
On all 8 it equals the zero-based index of the *last transition in that attempt's own
`phaseTransitions` list* — 3497's five transitions end at index 4 while its last phase is 1, and
3420's single transition sits at index 0 while its last phase is 1. It counts transitions, not
phases.

**One encounter does not fit the obvious shortcut.** `lastPhase` equals the id of the last
transition on 7 of the 8, but encounter 3470 reports `lastPhase: 2` against transitions ending in
3. Unexplained, and recorded rather than guessed at: **read `lastPhase`, never
`phaseTransitions[-1].id`.**

## No boss health curve is on offer, and `separatesWipes` is not a phase gate

Measured 2026-09-18 against report `DJfap6RcYKhPGHXZ` fight 13, a Mythic Nek'zali kill, by schema
introspection and by running each query. The whole probe spent under 5 points.

**The four enums, read verbatim from introspection.** `GraphDataType` and `TableDataType` carry
the same fourteen values: `Summary`, `Buffs`, `Casts`, `DamageDone`, `DamageTaken`, `Deaths`,
`Debuffs`, `Dispels`, `Healing`, `Interrupts`, `Resources`, `Summons`, `Survivability`, `Threat`.
They differ from `EventDataType`, recorded above, in both directions: graphs and tables add
`Summary` and `Survivability`, and lack `All` and `CombatantInfo`. `HostilityType` is exactly
`Friendlies` and `Enemies`.

**`graph(dataType: Resources, hostilityType: Enemies)` returns zero series.** One call, one fight,
`series: []` inside the usual `startTime`/`endTime` envelope. Cost 1.00 point. **So there is no
enemy health curve to read**, and a boss's health over time cannot be fetched the way a player's
resources can.

**`graph(dataType: Summary, hostilityType: Enemies)` returns three series of 42 points each** --
`Damage Done`, `Damage Taken`, `Healing Done` -- and priced at **0.00 points**. Whether those
points are per-bucket rates or running totals was not established, so nothing should read them as
a depletion curve without settling that first.

**The endpoint remains the reliable reading.** `ReportFight.fightPercentage` states the boss
health a fight ended on, is already selected by `FIGHTS_QUERY`, and costs nothing.

**`events(..., includeResources: true)` surfaced no boss-sized pool.** On a
`DamageTaken`/`Friendlies` stream, 313 of 401 events carried `hitPoints` and `maxHitPoints` across
9 distinct source ids, every maximum between 812560 and 927660 -- pools far too small for a Mythic
raid boss. Which actors those are was not identified, and is recorded as a raw reading rather than
guessed at. The 2026-09-06 note above reached the same conclusion from a smaller window.

**`separatesWipes` is false on encounters that plainly have phases.** Read off the cache the same
day across 8 encounters carrying a `Report.phases` entry: 5 true, 3 false, and **all 8 carry 2 to
4 named phases**. Encounter 3445 reads false while naming `Stage One: Entombed Sentinels` and
`Intermission: Vitriolic Stasis`. Encounters 3497, 12813 and 12859 name bosses rather than stages,
which is what a council encounter's phases are.

So the flag answers "is phase a meaningful way to group this encounter's **attempts**", which is a
progression question. **It does not answer whether a single attempt can be sliced by phase**, and
gating an in-fight phase label on it would silently drop 3 encounters in 8 that have named phases
and transitions. Gate attempt-grouping on `separatesWipes`; gate an in-fight phase label on the
encounter having phases at all.

## What a whole day of this investigation cost

**14.04 points of 3600** (2026-09-16), covering four schema introspections, a report-wide `fights`
listing, and two fully paginated event streams on a 20-player fight. Introspection is cheap: the
first probe, which read all 43 `ReportFight` fields and every type name in the schema, moved the
counter by 1.00.

**An event stream is about 1.00 points a fight, whatever its size.** Measured 2026-09-16: the
`Debuffs` sweep of all 19 boss fights spent **14.00 points**, of which `Debuffs` was 13 calls for
13.00 — one call each, 1.00 each, on fights from 15.8s to 480.0s and from 2 rows to 5,254. The
six earlier fights cost 6.03 for 6 calls. The report-wide `DamageTaken` sweep of the same 19
fights spent **18.76**, higher only because the larger fights paginate: 26,606 rows on one fight
is three pages, and a page is a call.

**So deepening a whole night is projected to be cheap — this has not itself been measured.** Two
streams a fight at ~1.00 point each projects an eight-attempt night to about 20 points of 3600,
against the design's estimate of 40 to 60 for three streams. Lower only because it drops the
debuff stream that estimate priced in, not because the estimate was wrong. The one figure actually
measured for `load_progression_attempts` is a warm-cache re-run at 8.00 points: 7 `Deaths` calls
for 7.00 and 2 `RateLimit` calls for 1.00, with `Fights`, `Abilities` and `DamageTaken` all served
from cache — a re-run price, not a cold one.
