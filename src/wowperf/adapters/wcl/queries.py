# ABOUTME: GraphQL query text for the Warcraft Logs v2 client API, one constant per query.
# ABOUTME: Every field here is verified against the published schema; do not add unverified ones.

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
