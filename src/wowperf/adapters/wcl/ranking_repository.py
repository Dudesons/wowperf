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

    def fastest_runs(
        self, encounter_id: int, keystone_level: int, minimum: int = 1
    ) -> tuple[SpeedRow, ...]:
        """The fastest runs at this keystone level, widening a bracket at a time.

        `minimum` names how many rows are worth having, not how many to keep: a
        bracket that already meets it stops the search, but a bracket short of
        it does not have its rows discarded — the next level's rows are added
        to what is already in hand, not fetched instead of it. A short
        leaderboard still returns whatever it found; it is `_samples` in
        `cli.py`, not this method, that decides a short result is acceptable.
        """
        collected: list[SpeedRow] = []
        for level in self._levels_to_try(keystone_level):
            if level < 2:
                continue
            rows = self._rows(FIGHT_RANKINGS_QUERY, {"encounterId": encounter_id}, level)
            if rows:
                collected.extend(build_speed_rows(rows))
                if len(collected) >= minimum:
                    break
        return tuple(collected)

    def top_parses(
        self, encounter_id: int, keystone_level: int, class_name: str, spec: str, minimum: int = 1
    ) -> tuple[ParseRow, ...]:
        """The top parses for this specialisation, widening a bracket at a time.

        See `fastest_runs` for what `minimum` does and does not guarantee.
        """
        variables = {"encounterId": encounter_id, "className": class_name, "specName": spec}
        collected: list[ParseRow] = []
        for level in self._levels_to_try(keystone_level):
            if level < 2:
                continue
            rows = self._rows(CHARACTER_RANKINGS_QUERY, variables, level)
            if rows:
                collected.extend(build_parse_rows(rows))
                if len(collected) >= minimum:
                    break
        return tuple(collected)
