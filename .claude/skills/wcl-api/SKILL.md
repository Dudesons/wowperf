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
| `allowUnlisted` | `reportData.report` argument | 2026-09-03 | yes |
| `rateLimitData` | `Query` | 2026-09-04 | yes |
| `limitPerHour` | `RateLimitData` | 2026-09-04 | yes |
| `pointsSpentThisHour` | `RateLimitData` | 2026-09-04 | yes |
| `pointsResetIn` | `RateLimitData` | 2026-09-04 | yes |
| `characterRankings` | `worldData.encounter` | 2026-09-03 | yes |
| `fightRankings` | `worldData.encounter` | 2026-09-03 | yes |
| `fightIDs` | `table` argument | 2026-09-05 | yes |
| `hostilityType` | `table` argument | 2026-09-05 | yes |
| `sourceID` | `table` argument | 2026-09-05 | yes |
| `targetID` | `table` argument | 2026-09-05 | yes |

`tests/test_skills.py` holds this table against `src/wowperf/adapters/wcl/queries.py`. When it
rejects a row, correct the row rather than the test: the table is a claim about the code, and the
code wins.

**The table is the machine-checked subset, not the whole vocabulary.** It holds the fields a test
can assert by name in both directions, which is why it stays short. The sections below name more —
arguments, nested fields and response keys such as `kill`, `startTime`, `endTime`, `x`/`y`,
`actors`, `bands`, `totalUptime`, `totalUses` and `totalTime` — each under its own verification
date, and those dates bind exactly as the table's do. A field documented in prose is documented.
`queries.py` also uses fields this reference names nowhere: `talents`, `talentImportCode`,
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

One approximation and one measurement:

- A full compared analysis costs roughly **28 points of 3600** — an order of magnitude observed
  across this project's own compared runs, not a controlled measurement. No single reading stands
  behind it and its composition is not recorded. It is the reason not to loop, not a number to
  budget against.
- A roster query, four aura tables and a `rateLimitData` read together spent **12.02 points of
  3600** (2026-09-05).

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

## Aura tables

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

## Leaderboards return report codes

Verified 2026-09-03. Both `worldData.encounter.characterRankings` and
`worldData.encounter.fightRankings` return rows containing `report { code, fightID, startTime }`.
The pipeline "find a top run, then fetch its log" works end to end.

`FightRankingMetricType` includes `speed` and `score`. `CharacterRankingMetricType` includes
`playerscore`, documented as "used by WoW Mythic dungeons".

**Unverified convention:** community code current as of August 2026 uses
`bracket = keystoneLevel - 1` and passes `className` and `specName` together. Neither
appears in the documentation. The implementation must assert this rather than assume it.

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
