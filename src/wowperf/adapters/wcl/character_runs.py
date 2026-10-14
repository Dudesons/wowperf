# ABOUTME: Reads a zone's dungeons and one character's per-dungeon rankings off the API's answer.
# ABOUTME: A rank with no public report is kept with no code, so selection can say why it skipped.

import re
from collections.abc import Sequence
from typing import Any

from wowperf.domain.character.model import Dungeon, RankedRun, Zone

REPORT_CODE = re.compile(r"[A-Za-z0-9]+")
"""A report code's alphabet, as `urls.REPORT_PATTERN` reads it from a pasted URL."""


def build_zone(payload: dict[str, Any]) -> Zone:
    zone = (payload.get("worldData") or {}).get("zone")
    if zone is None:
        raise ValueError("Warcraft Logs has no zone with that id")
    return Zone(
        zone_id=int(zone["id"]),
        name=str(zone["name"]),
        difficulty_ids=tuple(int(one["id"]) for one in zone.get("difficulties") or ()),
        dungeons=tuple(
            Dungeon(encounter_id=int(one["id"]), name=str(one["name"]))
            for one in zone.get("encounters") or ()
        ),
    )


def build_ranked_runs(
    payload: dict[str, Any], dungeons: Sequence[Dungeon]
) -> tuple[RankedRun, ...]:
    """Every rank of every dungeon, in dungeon order then the rankings' own order."""
    character = (payload.get("characterData") or {}).get("character")
    if character is None:
        raise ValueError("Warcraft Logs has no such character on that realm")
    if character.get("hidden"):
        raise ValueError("This character has hidden its rankings on Warcraft Logs")
    runs: list[RankedRun] = []
    for dungeon in dungeons:
        alias = f"e{dungeon.encounter_id}"
        where = f"{dungeon.name} ({dungeon.encounter_id})"
        # Warcraft Logs may change this field without notice, so a missing key is a
        # changed shape and refused; only a null block means a dungeon with no runs.
        if alias not in character:
            raise ValueError(f"The character's rankings carry no answer for {where}")
        block = character[alias]
        if block is None:
            continue
        if "ranks" not in block:
            raise ValueError(f"The rankings for {where} carry no ranks list")
        for rank in block["ranks"] or ():
            if "report" not in rank:
                raise ValueError(f"A rank for {where} carries no report")
            report = rank["report"] or {}
            # A run with no public log arrives with an empty code, no fight and a
            # null report start (wcl-api skill, "A character's ranked runs"), so the
            # start time is the rank's own, never the report's.
            code = report.get("code") or None
            # The code becomes part of the run's two file names, so anything but
            # a report code's own alphabet is refused before it can name a path.
            if code is not None and not REPORT_CODE.fullmatch(code):
                raise ValueError(f"A rank for {where} names {code!r}, which is not a report code")
            fight = report.get("fightID")
            runs.append(
                RankedRun(
                    encounter_id=dungeon.encounter_id,
                    keystone_level=int(rank["bracketData"]),
                    spec=str(rank["spec"]),
                    start_time_ms=int(rank["startTime"]),
                    report_code=code,
                    fight_id=int(fight) if code is not None and fight is not None else None,
                )
            )
    return tuple(runs)
