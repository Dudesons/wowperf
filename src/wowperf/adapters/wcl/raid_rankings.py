# ABOUTME: Turns a raid characterRankings row into RaidParseRow, this axis's own shape.
# ABOUTME: Not build_parse_rows: a raid row carries no score, medal or affixes to reuse it for.

from typing import Any

from wowperf.adapters.wcl.rankings import report_of
from wowperf.domain.comparison.raid_reference import RaidParseRow


def build_raid_parse_rows(rows: list[dict[str, Any]]) -> tuple[RaidParseRow, ...]:
    built = []
    for row in rows:
        report = report_of(row)
        if report is None:
            # A row with no report cannot be fetched, so it is no use as a reference.
            continue
        built.append(
            RaidParseRow(
                report_code=report["code"],
                fight_id=report["fightID"],
                duration_ms=row["duration"],
                character_name=row["name"],
                class_name=row["class"],
                spec=row["spec"],
                amount=row["amount"],
            )
        )
    return tuple(built)
