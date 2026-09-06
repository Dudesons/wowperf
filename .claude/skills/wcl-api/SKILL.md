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
  soaking a hit, with `extraAbilityGameID` naming the absorbing aura) and `removebuff` events.
  Observed keys: `abilityGameID`, `amount`, `attackerID`, `buffs`, `extraAbilityGameID`, `fight`,
  `sourceID`, `targetID`, `timestamp`, `type`. No `overheal` key appeared.
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
