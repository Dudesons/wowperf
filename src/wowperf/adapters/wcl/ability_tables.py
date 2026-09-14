# ABOUTME: Maps a viewBy-Ability damage-taken table into the domain's per-ability rows.
# ABOUTME: The only module that reads this table's shape; it decides nothing about it.

from typing import Any

from wowperf.adapters.wcl.errors import WclError
from wowperf.domain.comparison.mechanics import AbilityTakenRow


def build_ability_taken_rows(payload: dict[str, Any], alias: str) -> tuple[AbilityTakenRow, ...]:
    """The aliased `viewBy: Ability` damage-taken table, as domain rows.

    A missing selection raises, naming the alias, rather than returning an
    empty tuple that would read as "this fight had no damage taken" -- the
    same distinction `ingest._aura_rows` draws for the buff table.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    if alias not in report:
        raise WclError(f"The damage-taken table response carried no `{alias}` selection")
    entries = ((report[alias] or {}).get("data") or {}).get("entries") or []
    return tuple(
        AbilityTakenRow(
            ability_id=entry["guid"],
            ability_name=entry.get("name") or "",
            hit_count=entry.get("hitCount") or 0,
            tick_count=entry.get("tickCount") or 0,
            miss_count=entry.get("missCount") or 0,
            tick_miss_count=entry.get("tickMissCount") or 0,
            source_types=tuple(source.get("type") or "" for source in entry.get("sources") or ()),
        )
        for entry in entries
    )
