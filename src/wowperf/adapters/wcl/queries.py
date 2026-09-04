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
    report(code: $code) {
      code
      title
      startTime
      endTime
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
