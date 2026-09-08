# ABOUTME: GraphQL query text for the Warcraft Logs v2 client API, and the quota-block splice.
# ABOUTME: Every field here is verified against the published schema; do not add unverified ones.

import re
from collections.abc import Sequence

RATE_LIMIT_QUERY = """
query RateLimit {
  rateLimitData {
    limitPerHour
    pointsSpentThisHour
    pointsResetIn
  }
}
"""

QUOTA_BLOCK = "rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }"

# A named operation, with or without a variable list, up to the brace opening its
# top-level selection set. Every query here is named; an anonymous one is left
# alone rather than guessed at. The header must open its own line, so that a
# comment reading `# query Foo {` is not mistaken for the operation itself.
_OPERATION_HEADER = re.compile(r"^[ \t]*query\s+(\w+)\s*(?:\([^)]*\))?\s*\{", re.MULTILINE)


def operation_name(query: str) -> str | None:
    """The name of the operation, or None where this is not a shape we recognise.

    One pattern names the operation and finds where the quota block goes, so a
    recorded cost can never be filed under a different name from the one whose
    query carried the block.
    """
    header = _OPERATION_HEADER.search(query)
    return header.group(1) if header else None


def with_rate_limit(query: str) -> str:
    """The same query, selecting the quota block first, so it reports its own cost.

    `rateLimitData` is a top-level `Query` field, and asking for it alongside the
    real work is free: two queries cost 3.01 points with the block and 3.01
    without, measured 2026-09-08. A query that already selects it, or whose shape
    this does not recognise, goes out unchanged — instrumentation must never be
    the reason a query stops working.
    """
    if "rateLimitData" in query:
        return query
    header = _OPERATION_HEADER.search(query)
    if header is None:
        return query
    return f"{query[: header.end()]}\n  {QUOTA_BLOCK}{query[header.end() :]}"


# Argument-free and game-wide, so one cached response serves every run.
AFFIXES_QUERY = """
query Affixes {
  gameData {
    affixes { id name }
  }
}
"""

FIGHTS_QUERY = """
query Fights($code: String!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      code
      title
      startTime
      endTime
      owner { name }
      fights(translate: true) {
        id
        name
        encounterID
        startTime
        endTime
        kill
        keystoneLevel
        keystoneAffixes
        keystoneTime
        keystoneBonus
        countReached
        countRequired
        npcCountMap
        friendlyPlayers
        friendlySpecs
        friendlyItemLevels
        dungeonPulls {
          id
          name
          encounterID
          startTime
          endTime
          kill
          x
          y
          enemyNPCs { id gameID }
        }
      }
      masterData(translate: true) {
        actors(type: "Player") { id name subType server }
      }
    }
  }
}
"""

DEATHS_QUERY = """
query Deaths($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Deaths
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

# `includeResources` attaches the caster's own hitPoints and maxHitPoints to each
# cast, the only health reading the log offers for a player; the hits they take
# carry none for the target. See the wcl-api skill, "The event stream, probed
# for a death recap".
CASTS_QUERY = """
query Casts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Casts
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        includeResources: true
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

ABILITIES_QUERY = """
query Abilities($code: String!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      masterData(translate: true) {
        abilities { gameID name }
      }
    }
  }
}
"""

ENEMY_CASTS_QUERY = """
query EnemyCasts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Casts
        hostilityType: Enemies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

INTERRUPTS_QUERY = """
query Interrupts($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Interrupts
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

ENEMY_DEATHS_QUERY = """
query EnemyDeaths($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Deaths
        hostilityType: Enemies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

DAMAGE_TAKEN_QUERY = """
query DamageTaken($code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: DamageTaken
        hostilityType: Friendlies
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

# Issued once per death, bounded to one actor and a few seconds, so it returns
# a handful of rows. Scoping by `targetID` is what keeps a ten-death run from
# paying for ten full streams; the healing stream honours that scoping.
HEALING_QUERY = """
query Healing(
  $code: String!, $fightId: Int!, $actorId: Int!, $startTime: Float!, $endTime: Float!
) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: Healing
        fightIDs: [$fightId]
        targetID: $actorId
        startTime: $startTime
        endTime: $endTime
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

# `resurrect` events live only in the All stream: there is no Resurrects data
# type. That stream ignores `targetID`, so it is narrowed by a server-side
# filter on the event type instead, and asked once for the whole fight rather
# than once per death.
RESURRECTS_QUERY = """
query Resurrects(
  $code: String!, $fightId: Int!, $startTime: Float!, $endTime: Float!
) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      events(
        dataType: All
        fightIDs: [$fightId]
        startTime: $startTime
        endTime: $endTime
        filterExpression: "type = 'resurrect'"
        limit: 10000
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""

ACTORS_QUERY = """
query Actors($code: String!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      masterData(translate: true) {
        actors { id gameID }
      }
    }
  }
}
"""

# Rankings take `bracket`, not a keystone level: bracket 15 returns +16 runs.
# `size` is the group size and not a page size — only 5 is valid for a dungeon,
# and omitting it returns the same rows — so neither query passes it.
FIGHT_RANKINGS_QUERY = """
query FightRankings($encounterId: Int!, $bracket: Int!, $page: Int!) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      fightRankings(metric: speed, bracket: $bracket, page: $page)
    }
  }
}
"""

CHARACTER_RANKINGS_QUERY = """
query CharacterRankings(
  $encounterId: Int!, $bracket: Int!, $page: Int!, $className: String!, $specName: String!
) {
  worldData {
    encounter(id: $encounterId) {
      id
      name
      characterRankings(
        metric: playerscore
        bracket: $bracket
        page: $page
        className: $className
        specName: $specName
      )
    }
  }
}
"""


# Two aliased selections of `table`, so one cached query covers both halves of
# "on self and on target". `Buffs` with targetID is what the player carried.
# `Debuffs` with sourceID and Enemies does not work against the live API: confirmed
# 2026-09-05, that combination returns zero auras, and no argument (sourceID,
# filterExpression, sourceClass) narrows the enemy-debuff table to one caster —
# see `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot be scoped to one
# caster", for the measured table. The selection stays wired for when a working
# query is found; today `onTargets` ships inert.
AURA_TABLE_QUERY = """
query AuraTable($code: String!, $fightId: Int!, $actorId: Int!) {
  reportData {
    report(code: $code, allowUnlisted: true) {
      onSelf: table(fightIDs: [$fightId], dataType: Buffs, targetID: $actorId)
      onTargets: table(
        fightIDs: [$fightId]
        dataType: Debuffs
        sourceID: $actorId
        hostilityType: Enemies
      )
    }
  }
}
"""


def talents_query(actor_ids: Sequence[int]) -> str:
    """One aliased `talentImportCode` per player.

    `ReportFight.talentImportCode(actorID: Int!)` takes a single actor, so a
    roster needs an alias each. This is the only generated query here; the ids
    are coerced to `int` so nothing but a number ever reaches the string, and
    sorted so the document is byte-identical for a given set of ids regardless
    of the order the caller happened to hold them in — the cache key is
    derived from the query text, so an unstable order would miss the cache.
    """
    fields = "\n".join(
        f"        a{actor_id}: talentImportCode(actorID: {actor_id})"
        for actor_id in sorted(int(actor_id) for actor_id in actor_ids)
    )
    return f"""
query Talents($code: String!, $fightId: Int!) {{
  reportData {{
    report(code: $code, allowUnlisted: true) {{
      fights(fightIDs: [$fightId]) {{
        id
{fields}
      }}
    }}
  }}
}}
"""
