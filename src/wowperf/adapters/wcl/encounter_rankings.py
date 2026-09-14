# ABOUTME: Fetches the `execution` leaderboard for one boss, caching every response.
# ABOUTME: Satisfies EncounterRankingRepository, the raid axis sibling of the ranking port.

from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.queries import ENCOUNTER_KILL_RANKINGS_QUERY
from wowperf.adapters.wcl.rankings import rankings_block, report_of
from wowperf.domain.comparison.mechanics import ReferenceKillRow


def build_reference_kill_rows(rows: list[dict[str, Any]]) -> tuple[ReferenceKillRow, ...]:
    built = []
    for row in rows:
        report = report_of(row)
        if report is None:
            # A row with no report cannot be fetched, so it is no use as a reference.
            continue
        built.append(
            ReferenceKillRow(
                report_code=report["code"],
                fight_id=report["fightID"],
                size=row["size"],
                duration_ms=row["duration"],
                deaths=row.get("deaths") or 0,
            )
        )
    return tuple(built)


class WclEncounterRankingRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def reference_kills(
        self, encounter_id: int, difficulty: int, partition: int
    ) -> tuple[ReferenceKillRow, ...]:
        variables = {
            "encounterId": encounter_id,
            "difficulty": difficulty,
            "partition": partition,
            "page": 1,
        }
        payload, _ = self._cache.get_or_fetch(
            cache_key(ENCOUNTER_KILL_RANKINGS_QUERY, variables),
            lambda: self._client.execute(ENCOUNTER_KILL_RANKINGS_QUERY, variables),
        )
        rows = rankings_block(payload).get("rankings") or []
        return build_reference_kill_rows(rows)
