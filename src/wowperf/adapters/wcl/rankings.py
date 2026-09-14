# ABOUTME: Turns Warcraft Logs leaderboard rows into this project's reference-run types.
# ABOUTME: Also asserts the undocumented bracket convention, because a wrong reference looks right.

from typing import Any

from wowperf.adapters.wcl.errors import BracketMismatch, WclError
from wowperf.domain.comparison.reference import ParseRow, SpeedRow


def bracket_for(keystone_level: int) -> int:
    """The leaderboard bracket that holds runs of this keystone level.

    Confirmed by live query on 2026-09-04: bracket 15 returns rows whose
    bracketData is 16. The convention appears in no documentation, which is why
    every call also runs `assert_bracket` over what came back.
    """
    return keystone_level - 1


def rankings_block(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the rankings object out of a response, refusing the two failure shapes.

    A rejected ranking query answers HTTP 200 with no GraphQL error at all: the
    rankings value is `{"error": "..."}` instead of the usual object. Nothing
    else in this adapter notices that, so it is caught here.
    """
    encounter = (payload.get("worldData") or {}).get("encounter")
    if not encounter:
        raise WclError("The rankings response carried no encounter")

    for key in ("fightRankings", "characterRankings"):
        block = encounter.get(key)
        if block is None:
            continue
        if "error" in block:
            raise WclError(f"Warcraft Logs rejected the rankings query: {block['error']}")
        return dict(block)

    raise WclError("The rankings response carried neither fightRankings nor characterRankings")


def assert_bracket(rows: list[dict[str, Any]], keystone_level: int) -> None:
    """Fail loudly if the leaderboard did not return the keystone level we asked for.

    Rows that carry no bracketData are ignored rather than assumed wrong: the
    assertion exists to catch a changed convention, not to reject a sparse row.
    """
    seen = {row["bracketData"] for row in rows if row.get("bracketData") is not None}
    if seen and seen != {keystone_level}:
        raise BracketMismatch(
            f"Asked for bracket {bracket_for(keystone_level)} expecting +{keystone_level} runs, "
            f"but the rows say {sorted(seen)}. The bracket convention has changed and every "
            "comparison built on it would be wrong."
        )


def report_of(row: dict[str, Any]) -> dict[str, Any] | None:
    report = row.get("report")
    return report if isinstance(report, dict) and report.get("code") else None


def build_speed_rows(rows: list[dict[str, Any]]) -> tuple[SpeedRow, ...]:
    built = []
    for row in rows:
        report = report_of(row)
        if report is None:
            # A row with no report cannot be fetched, so it is no use as a reference.
            continue
        built.append(
            SpeedRow(
                report_code=report["code"],
                fight_id=report["fightID"],
                keystone_level=row["bracketData"],
                duration_ms=row["duration"],
                deaths=row.get("deaths") or 0,
                affix_ids=tuple(row.get("affixes") or ()),
                score=row.get("score") or 0.0,
                medal=row.get("medal") or "",
                team=tuple(
                    f"{member.get('class', '?')} {member.get('spec', '?')}"
                    for member in row.get("team") or ()
                ),
            )
        )
    return tuple(built)


def build_parse_rows(rows: list[dict[str, Any]]) -> tuple[ParseRow, ...]:
    built = []
    for row in rows:
        report = report_of(row)
        if report is None:
            continue
        built.append(
            ParseRow(
                report_code=report["code"],
                fight_id=report["fightID"],
                keystone_level=row["bracketData"],
                duration_ms=row["duration"],
                character_name=row["name"],
                class_name=row["class"],
                spec=row["spec"],
                affix_ids=tuple(row.get("affixes") or ()),
                # `amount` is negative for playerscore on a real row; `score` is the figure.
                score=row.get("score") or 0.0,
                medal=row.get("medal") or "",
            )
        )
    return tuple(built)
