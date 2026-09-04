# ABOUTME: Translates Warcraft Logs report JSON into the domain model.
# ABOUTME: The only module that knows Warcraft Logs field names; everything downstream is clean.

from typing import Any

from wowperf.domain.model import EnemyNpc, Player, Pull, Run


class IngestError(ValueError):
    """The report does not contain what this tool needs."""


def select_keystone_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]:
    """Find the fight holding the Mythic+ run.

    A complete run is one fight carrying a keystoneLevel; its trash and bosses
    hang off it as dungeonPulls rather than appearing as sibling fights.
    """
    keystone_fights = [fight for fight in fights if fight.get("keystoneLevel") is not None]

    if fight_id is not None:
        for fight in keystone_fights:
            if fight["id"] == fight_id:
                return fight
        raise IngestError(f"Fight {fight_id} is not a Mythic+ run in this report")

    if not keystone_fights:
        raise IngestError("This report contains no Mythic+ run")
    if len(keystone_fights) > 1:
        ids = ", ".join(str(fight["id"]) for fight in keystone_fights)
        raise IngestError(f"This report holds several Mythic+ runs ({ids}); pass --fight")
    return keystone_fights[0]


def _build_players(fight: dict[str, Any], actors: list[dict[str, Any]]) -> tuple[Player, ...]:
    by_id = {actor["id"]: actor for actor in actors}
    ids = fight.get("friendlyPlayers") or []
    specs = fight.get("friendlySpecs") or []
    item_levels = fight.get("friendlyItemLevels") or []

    players = []
    for position, actor_id in enumerate(ids):
        actor = by_id.get(actor_id)
        if actor is None:
            continue
        players.append(
            Player(
                actor_id=actor_id,
                name=actor["name"],
                class_name=actor["subType"],
                spec=specs[position] if position < len(specs) else "",
                item_level=item_levels[position] if position < len(item_levels) else 0,
            )
        )
    return tuple(players)


def _build_pulls(fight: dict[str, Any]) -> tuple[Pull, ...]:
    pulls = []
    for index, raw in enumerate(fight.get("dungeonPulls") or []):
        pulls.append(
            Pull(
                index=index,
                pull_id=raw["id"],
                name=raw["name"],
                encounter_id=raw["encounterID"],
                start_ms=raw["startTime"],
                end_ms=raw["endTime"],
                killed=bool(raw.get("kill")),
                x=raw.get("x") or 0,
                y=raw.get("y") or 0,
                enemies=tuple(
                    EnemyNpc(actor_id=npc["id"], game_id=npc["gameID"])
                    for npc in (raw.get("enemyNPCs") or [])
                ),
            )
        )
    return tuple(pulls)


def build_run(report: dict[str, Any], fight: dict[str, Any]) -> Run:
    actors = report.get("masterData", {}).get("actors") or []
    raw_counts = fight.get("npcCountMap") or {}

    return Run(
        report_code=report["code"],
        fight_id=fight["id"],
        dungeon_name=fight["name"],
        keystone_level=fight["keystoneLevel"],
        affix_ids=tuple(fight.get("keystoneAffixes") or ()),
        keystone_time_ms=fight.get("keystoneTime") or 0,
        keystone_bonus=fight.get("keystoneBonus") or 0,
        count_reached=fight.get("countReached") or 0,
        count_required=fight.get("countRequired") or 0,
        # npcCountMap arrives as a JSON object, so its keys are strings.
        npc_count_map={int(game_id): count for game_id, count in raw_counts.items()},
        players=_build_players(fight, actors),
        pulls=_build_pulls(fight),
    )
