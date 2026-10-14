# ABOUTME: Fetches a zone and one character's ranked runs, behind the cache it is handed.
# ABOUTME: The CLI hands it the one-day tier: the list changes with every key the character plays.

from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.character_runs import build_ranked_runs, build_zone
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.queries import ZONE_QUERY, character_runs_query
from wowperf.domain.character.model import RankedRun, Zone


class WclCharacterRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload, _ = self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._client.execute(query, variables),
        )
        return payload

    def zone(self, zone_id: int) -> Zone:
        return build_zone(self._query(ZONE_QUERY, {"zoneId": zone_id}))

    def ranked_runs(
        self, name: str, realm: str, region: str, zone: Zone
    ) -> tuple[RankedRun, ...]:
        query = character_runs_query([dungeon.encounter_id for dungeon in zone.dungeons])
        payload = self._query(query, {"name": name, "serverSlug": realm, "serverRegion": region})
        return build_ranked_runs(payload, zone.dungeons)
