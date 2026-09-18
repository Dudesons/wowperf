# ABOUTME: Fetches the `execution` leaderboard for one boss, caching every response.
# ABOUTME: Satisfies EncounterRankingRepository, the raid axis sibling of the ranking port.

from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.queries import (
    ENCOUNTER_KILL_RANKINGS_QUERY,
    RAID_CHARACTER_RANKINGS_QUERY,
)
from wowperf.adapters.wcl.raid_rankings import build_raid_parse_rows
from wowperf.adapters.wcl.rankings import rankings_block, report_of
from wowperf.domain.comparison.mechanics import ReferenceKillRow
from wowperf.domain.comparison.raid_reference import RaidParseRow

ROLE_COUNTS = ("tanks", "healers", "melee", "ranged")


def _required(row: dict[str, Any], field: str) -> Any:
    """One field the row cannot be read without, named when it is absent.

    `build_ability_taken_rows` answers a malformed response the same way. A
    bare subscript here escapes the command as a `KeyError` traceback, which
    says which key was missing but not which response carried it.
    """
    try:
        return row[field]
    except KeyError:
        raise WclError(f"An execution leaderboard row carried no `{field}`") from None


def _raid_size(row: dict[str, Any]) -> int:
    """The row's own `size`, or the roster composition standing in for it.

    The board omits `size` at a difficulty whose raid size cannot vary.
    Measured 2026-09-16: present on all 50 rows of encounter 3492 at difficulty
    4, absent from all 50 of encounter 3470 at difficulty 5, where the four role
    counts summed to 20 -- Mythic's fixed size -- every time. Where both are
    present the composition sums to `size` on 50 of 50 rows with no
    disagreements, so this is a derivation of the same figure and not a guess at
    it; `size` is still preferred wherever the board states it.
    """
    if "size" in row:
        return int(row["size"])
    return sum(int(row.get(role) or 0) for role in ROLE_COUNTS)


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
                size=_raid_size(row),
                duration_ms=_required(row, "duration"),
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

    def top_parses(
        self,
        encounter_id: int,
        difficulty: int,
        partition: int,
        class_name: str,
        spec: str,
        metric: str,
    ) -> tuple[RaidParseRow, ...]:
        variables = {
            "encounterId": encounter_id,
            "difficulty": difficulty,
            "partition": partition,
            "page": 1,
            "className": class_name,
            "specName": spec,
            "metric": metric,
        }
        payload, _ = self._cache.get_or_fetch(
            cache_key(RAID_CHARACTER_RANKINGS_QUERY, variables),
            lambda: self._client.execute(RAID_CHARACTER_RANKINGS_QUERY, variables),
        )
        rows = rankings_block(payload).get("rankings") or []
        return build_raid_parse_rows(rows)
