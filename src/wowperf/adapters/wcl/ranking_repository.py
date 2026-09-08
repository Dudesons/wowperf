# ABOUTME: Fetches the two leaderboards a comparison needs, caching every response.
# ABOUTME: Satisfies the RankingRepository port so the domain never learns where a row came from.

from collections.abc import Sequence
from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.queries import CHARACTER_RANKINGS_QUERY, FIGHT_RANKINGS_QUERY
from wowperf.adapters.wcl.rankings import (
    assert_bracket,
    bracket_for,
    build_parse_rows,
    build_speed_rows,
    rankings_block,
)
from wowperf.domain.comparison.reference import MAX_LEVEL_GAP, ParseRow, SpeedRow


class WclRankingRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload, _ = self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._client.execute(query, variables),
        )
        return payload

    @staticmethod
    def _levels_to_try(keystone_level: int) -> Sequence[int]:
        """Our level first, then outwards a gap at a time, to `MAX_LEVEL_GAP`."""
        levels = [keystone_level]
        for gap in range(1, MAX_LEVEL_GAP + 1):
            levels += [keystone_level - gap, keystone_level + gap]
        return tuple(levels)

    def _rows(self, query: str, variables: dict[str, Any], level: int) -> list[dict[str, Any]]:
        payload = self._query(query, {**variables, "bracket": bracket_for(level), "page": 1})
        rows = rankings_block(payload).get("rankings") or []
        # The assertion runs before anything reads a row, so a changed convention
        # stops the run rather than quietly supplying the wrong reference.
        assert_bracket(rows, level)
        return list(rows)

    def fastest_runs(self, encounter_id: int, keystone_level: int) -> tuple[SpeedRow, ...]:
        for level in self._levels_to_try(keystone_level):
            if level < 2:
                continue
            rows = self._rows(FIGHT_RANKINGS_QUERY, {"encounterId": encounter_id}, level)
            if rows:
                return build_speed_rows(rows)
        return ()

    def top_parses(
        self, encounter_id: int, keystone_level: int, class_name: str, spec: str
    ) -> tuple[ParseRow, ...]:
        variables = {"encounterId": encounter_id, "className": class_name, "specName": spec}
        for level in self._levels_to_try(keystone_level):
            if level < 2:
                continue
            rows = self._rows(CHARACTER_RANKINGS_QUERY, variables, level)
            if rows:
                return build_parse_rows(rows)
        return ()
