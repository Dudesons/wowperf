# ABOUTME: Turns a `Report.rankings` payload into domain rows; maps, decides nothing.
# ABOUTME: A wipe returns no row at all, so the absence is returned rather than a zeroed row.

from typing import Any

from wowperf.domain.comparison.raid_reference import RankedPlayer, ReportRankings

ROLES = ("tanks", "healers", "dps")


def build_report_rankings(payload: dict[str, Any], fight_id: int) -> ReportRankings | None:
    """The rankings row for this fight, or `None` where the API returned none.

    The payload's top level is exactly one key, `data`, holding one row per
    requested fight -- measured 2026-09-14. A wipe's list is empty, and no field
    on a row distinguishes a wipe from a kill, so emptiness is the test.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    block = report.get("rankings")
    rows = (block or {}).get("data") or []
    row = next((one for one in rows if one.get("fightID") == fight_id), None)
    if row is None:
        return None

    players: list[RankedPlayer] = []
    for role in ROLES:
        for entry in ((row.get("roles") or {}).get(role) or {}).get("characters") or ():
            players.append(
                RankedPlayer(
                    character_name=entry["name"],
                    class_name=entry.get("class") or "",
                    spec=entry.get("spec") or "",
                    role=role,
                    amount=float(entry.get("amount") or 0.0),
                    # Strings, not integers: the API writes "~5764".
                    rank=str(entry.get("rank") or ""),
                    best=str(entry.get("best") or ""),
                    rank_percent=int(entry.get("rankPercent") or 0),
                    bracket_percent=int(entry.get("bracketPercent") or 0),
                    total_parses=int(entry.get("totalParses") or 0),
                )
            )

    return ReportRankings(
        fight_id=row["fightID"],
        difficulty=int(row["difficulty"]),
        partition=int(row["partition"]),
        size=int(row["size"]),
        kill=bool(row["kill"]),
        players=tuple(players),
    )
