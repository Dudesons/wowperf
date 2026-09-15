# ABOUTME: Maps a viewBy-Target damage-done table into the domain's per-target rows.
# ABOUTME: The only module that reads this table's shape; it decides nothing about it.

from typing import Any

from wowperf.adapters.wcl.errors import WclError
from wowperf.domain.comparison.targets import TargetRow


def build_target_rows(payload: dict[str, Any], alias: str) -> tuple[TargetRow, ...]:
    """The aliased `viewBy: Target` damage-done table, scoped to one subject, as domain rows.

    A missing selection and a `null` one both raise, naming the alias, rather than returning
    an empty tuple that would read as "this subject dealt no damage at all" -- the same
    distinction `build_ability_taken_rows` draws for the damage-taken table.

    `target_id` reads the entry's `id`, the report-local id of the actor this row is about --
    not `guid`, which the same table carries for a different purpose on the analogous
    per-player table (see `.claude/skills/wcl-api/SKILL.md`, "the actor id" vs `guid` on a
    `DamageDoneGraph` series). Nothing in this module reads `guid` at all: `is_boss` is decided
    from `type`, per F12.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    table = report.get(alias)
    if not isinstance(table, dict):
        raise WclError(f"The damage-done-by-target table response carried no `{alias}` selection")
    entries = (table.get("data") or {}).get("entries") or []
    return tuple(
        TargetRow(
            target_id=entry["id"],
            name=entry.get("name") or "",
            kind=entry.get("type") or "",
            total=entry.get("total") or 0,
        )
        for entry in entries
    )
