# ABOUTME: GraphQL query text for the Warcraft Logs v2 client API, one constant per query.
# ABOUTME: Every field here is verified against the published schema; do not add unverified ones.

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
# see design §2.2 for the measured table. The selection stays wired for when a
# working query is found; today `onTargets` ships inert.
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
