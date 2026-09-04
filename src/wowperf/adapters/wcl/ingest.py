# ABOUTME: Translates Warcraft Logs report JSON into the domain model.
# ABOUTME: The only module that knows Warcraft Logs field names; everything downstream is clean.

from typing import Any

from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    EnemyCastRow,
    EnemyDeath,
    InterruptEvent,
)
from wowperf.domain.model import EnemyNpc, Player, Pull, Run


class IngestError(ValueError):
    """The report does not contain what this tool needs."""


def select_keystone_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]:
    """Find the fight holding the Mythic+ run.

    A complete run is one fight carrying a keystoneLevel and kill == true; its
    trash and bosses hang off it as dungeonPulls rather than appearing as
    sibling fights. A keystone fight that was not completed (a depleted or
    abandoned key) is rejected rather than analysed as a finished run.
    """
    keystone_fights = [fight for fight in fights if fight.get("keystoneLevel") is not None]

    if fight_id is not None:
        for fight in keystone_fights:
            if fight["id"] == fight_id:
                if not fight.get("kill"):
                    raise IngestError(f"Fight {fight_id} is a Mythic+ run that was not completed")
                return fight
        raise IngestError(f"Fight {fight_id} is not a Mythic+ run in this report")

    if not keystone_fights:
        raise IngestError("This report contains no Mythic+ run")

    completed_fights = [fight for fight in keystone_fights if fight.get("kill")]
    if not completed_fights:
        raise IngestError("This report contains no completed Mythic+ run")
    if len(completed_fights) > 1:
        ids = ", ".join(str(fight["id"]) for fight in completed_fights)
        raise IngestError(f"This report holds several Mythic+ runs ({ids}); pass --fight")
    return completed_fights[0]


def _build_players(fight: dict[str, Any], actors: list[dict[str, Any]]) -> tuple[Player, ...]:
    by_id = {actor["id"]: actor for actor in actors}
    ids = fight.get("friendlyPlayers") or []
    specs = fight.get("friendlySpecs") or []
    item_levels = fight.get("friendlyItemLevels") or []

    players = []
    for position, actor_id in enumerate(ids):
        actor = by_id.get(actor_id)
        if actor is None:
            # Dropping the player silently would shrink the roster and skew every
            # per-player metric computed from it.
            raise IngestError(
                f"Fight {fight.get('id')} lists player actor {actor_id}, "
                "which is absent from the report's master data"
            )
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


def _required(fight: dict[str, Any], field: str) -> int:
    """Read a field a completed keystone fight must carry, rather than defaulting it.

    keystoneTime anchors the whole time decomposition and countRequired is a
    divisor in trash efficiency. A missing one is schema drift, and defaulting it
    to zero would turn that into a confident wrong number.
    """
    value = fight.get(field)
    if value is None:
        raise IngestError(
            f"Fight {fight.get('id')} is a completed Mythic+ run but carries no {field}"
        )
    return int(value)


def build_run(report: dict[str, Any], fight: dict[str, Any]) -> Run:
    actors = report.get("masterData", {}).get("actors") or []
    raw_counts = fight.get("npcCountMap") or {}

    return Run(
        report_code=report["code"],
        fight_id=fight["id"],
        dungeon_name=fight["name"],
        keystone_level=fight["keystoneLevel"],
        affix_ids=tuple(fight.get("keystoneAffixes") or ()),
        keystone_time_ms=_required(fight, "keystoneTime"),
        keystone_bonus=fight.get("keystoneBonus") or 0,
        count_reached=_required(fight, "countReached"),
        count_required=_required(fight, "countRequired"),
        # npcCountMap arrives as a JSON object, so its keys are strings.
        npc_counts=tuple((int(game_id), count) for game_id, count in raw_counts.items()),
        players=_build_players(fight, actors),
        pulls=_build_pulls(fight),
    )


def pull_index_at(run: Run, timestamp_ms: int) -> int | None:
    """Which pull was underway at this moment, or None if the group was between pulls."""
    for pull in run.pulls:
        if pull.start_ms <= timestamp_ms <= pull.end_ms:
            return pull.index
    return None


def _ability_name(ability_names: dict[int, str], ability_id: int) -> str:
    return ability_names.get(ability_id, f"Unknown ability {ability_id}")


def build_casts(
    events: list[dict[str, Any]], run: Run, ability_names: dict[int, str]
) -> tuple[CastEvent, ...]:
    return tuple(
        CastEvent(
            actor_id=event["sourceID"],
            ability_id=event["abilityGameID"],
            ability_name=_ability_name(ability_names, event["abilityGameID"]),
            timestamp_ms=event["timestamp"],
            pull_index=pull_index_at(run, event["timestamp"]),
        )
        for event in events
        if event.get("type") == "cast" and "sourceID" in event
    )


def build_deaths(
    events: list[dict[str, Any]],
    run: Run,
    casts: tuple[CastEvent, ...],
    ability_names: dict[int, str],
) -> tuple[Death, ...]:
    """Build deaths, measuring the real cost as time until the player acted again.

    The timer penalty understates a death. The seconds a player spent unable to
    contribute is observable, so we measure that instead of estimating a run-back.
    """
    names = {player.actor_id: player.name for player in run.players}
    casts_by_actor: dict[int, list[int]] = {}
    for cast in casts:
        casts_by_actor.setdefault(cast.actor_id, []).append(cast.timestamp_ms)

    deaths = []
    for event in events:
        if event.get("type") != "death":
            continue

        actor_id = event["targetID"]
        timestamp = event["timestamp"]
        later = [stamp for stamp in casts_by_actor.get(actor_id, []) if stamp > timestamp]

        deaths.append(
            Death(
                player_name=names.get(actor_id, f"Actor {actor_id}"),
                actor_id=actor_id,
                timestamp_ms=timestamp,
                killing_blow=_ability_name(
                    ability_names, event.get("killingAbilityGameID", 0)
                ),
                pull_index=pull_index_at(run, timestamp),
                seconds_until_next_action=(min(later) - timestamp) / 1000 if later else None,
            )
        )
    return tuple(deaths)


def build_enemy_cast_rows(
    events: list[dict[str, Any]],
    run: Run,
    ability_names: dict[int, str],
) -> tuple[EnemyCastRow, ...]:
    """Translate raw enemy cast events; resolving their outcome is the analyser's job."""
    rows = []
    for event in events:
        kind = event.get("type")
        if kind not in ("begincast", "cast"):
            continue
        ability_id = event["abilityGameID"]
        rows.append(
            EnemyCastRow(
                source_id=event["sourceID"],
                source_instance=event.get("sourceInstance") or 0,
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                timestamp_ms=event["timestamp"],
                is_start=kind == "begincast",
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(rows)


def build_interrupts(
    events: list[dict[str, Any]],
    run: Run,
    players: dict[int, str],
) -> tuple[InterruptEvent, ...]:
    """Keep only real interrupts; the stream also carries debuff applications."""
    interrupts = []
    for event in events:
        if event.get("type") != "interrupt":
            continue
        actor_id = event["sourceID"]
        interrupts.append(
            InterruptEvent(
                player_name=players.get(actor_id, f"Actor {actor_id}"),
                actor_id=actor_id,
                interrupted_ability_id=event["extraAbilityGameID"],
                target_id=event["targetID"],
                target_instance=event.get("targetInstance") or 0,
                timestamp_ms=event["timestamp"],
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(interrupts)


def build_enemy_deaths(
    events: list[dict[str, Any]],
    run: Run,
    npc_game_ids: dict[int, int],
    npc_count_map: dict[int, int],
) -> tuple[EnemyDeath, ...]:
    """Attach the enemy-forces value each kill awarded.

    An enemy absent from npcCountMap awards nothing; that is normal for bosses
    and for mobs that do not count, so it is zero rather than an error.
    """
    deaths = []
    for event in events:
        if event.get("type") != "death":
            continue
        actor_id = event["targetID"]
        game_id = npc_game_ids.get(actor_id, 0)
        deaths.append(
            EnemyDeath(
                game_id=game_id,
                actor_id=actor_id,
                timestamp_ms=event["timestamp"],
                forces=npc_count_map.get(game_id, 0),
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(deaths)


def build_damage_taken(
    events: list[dict[str, Any]],
    run: Run,
    ability_names: dict[int, str],
) -> tuple[DamageTakenEvent, ...]:
    """Record the unmitigated figure: `amount` alone reads zero on an absorbed hit."""
    taken = []
    for event in events:
        if event.get("type") != "damage":
            continue
        ability_id = event["abilityGameID"]
        amount = event.get("unmitigatedAmount")
        if amount is None:
            amount = event.get("amount") or 0
        taken.append(
            DamageTakenEvent(
                actor_id=event["targetID"],
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                amount=int(amount),
                timestamp_ms=event["timestamp"],
                pull_index=pull_index_at(run, event["timestamp"]),
            )
        )
    return tuple(taken)
