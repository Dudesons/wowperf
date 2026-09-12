# ABOUTME: Translates Warcraft Logs report JSON into the domain model.
# ABOUTME: The only module that knows Warcraft Logs field names; everything downstream is clean.

from typing import Any

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.events import (
    CastEvent,
    DamageTakenEvent,
    Death,
    EnemyCastRow,
    EnemyDeath,
    HealingEvent,
    HealthSample,
    InterruptEvent,
    Resurrection,
)
from wowperf.domain.model import DamageDoneSeries, EnemyNpc, Player, Pull, Run


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


def _build_players(
    fight: dict[str, Any], actors: list[dict[str, Any]], talents: dict[int, str]
) -> tuple[Player, ...]:
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
        # Both arrays are index-aligned with `friendlyPlayers` and both carry
        # nulls in real reports. A null says exactly what a short array says —
        # this report does not know — so it reads as unknown rather than
        # dropping the player, which would shrink the roster for the same reason
        # the unmatched actor above is refused rather than skipped.
        spec = specs[position] if position < len(specs) else None
        item_level = item_levels[position] if position < len(item_levels) else None
        players.append(
            Player(
                actor_id=actor_id,
                name=actor["name"],
                class_name=actor["subType"],
                spec=spec if spec is not None else "",
                item_level=item_level if item_level is not None else 0,
                talent_import_string=talents.get(actor_id),
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


def build_run(
    report: dict[str, Any], fight: dict[str, Any], talents: dict[int, str] | None = None
) -> Run:
    actors = report.get("masterData", {}).get("actors") or []
    raw_counts = fight.get("npcCountMap") or {}

    return Run(
        report_code=report["code"],
        fight_id=fight["id"],
        dungeon_name=fight["name"],
        encounter_id=_required(fight, "encounterID"),
        keystone_level=fight["keystoneLevel"],
        affix_ids=tuple(fight.get("keystoneAffixes") or ()),
        keystone_time_ms=_required(fight, "keystoneTime"),
        keystone_bonus=fight.get("keystoneBonus") or 0,
        count_reached=_required(fight, "countReached"),
        count_required=_required(fight, "countRequired"),
        owner_name=(report.get("owner") or {}).get("name"),
        # npcCountMap arrives as a JSON object, so its keys are strings.
        npc_counts=tuple((int(game_id), count) for game_id, count in raw_counts.items()),
        players=_build_players(fight, actors, talents or {}),
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


def _target_of(event: dict[str, Any]) -> int | None:
    """The cast's target actor, or None: the API writes -1 for a cast with no target."""
    target = event.get("targetID")
    if target is None or target == -1:
        return None
    return int(target)


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
            target_id=_target_of(event),
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
    """Build deaths, measuring the real cost as time until the player next acted on another actor.

    The timer penalty understates a death. The seconds a player spent unable to
    contribute is observable, so we measure that instead of estimating a run-back.
    """
    names = {player.actor_id: player.name for player in run.players}
    # A cast aimed at another actor is the first moment the player affected the
    # fight again. A released player respawns alive at the entrance with no
    # event to say so, and presses self-only sprints and shields while running
    # back; counting those would end the death after a few seconds of a
    # twenty-second absence.
    acted_by_actor: dict[int, list[int]] = {}
    for cast in casts:
        if cast.target_id is not None and cast.target_id != cast.actor_id:
            acted_by_actor.setdefault(cast.actor_id, []).append(cast.timestamp_ms)

    deaths = []
    for event in events:
        if event.get("type") != "death":
            continue

        actor_id = event["targetID"]
        timestamp = event["timestamp"]
        later = [stamp for stamp in acted_by_actor.get(actor_id, []) if stamp > timestamp]

        deaths.append(
            Death(
                player_name=names.get(actor_id, f"Actor {actor_id}"),
                actor_id=actor_id,
                timestamp_ms=timestamp,
                killing_blow_id=event.get("killingAbilityGameID", 0),
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
    actor_game_ids: dict[int, int],
    npc_count_map: dict[int, int],
) -> tuple[EnemyDeath, ...]:
    """Attach the enemy-forces value each kill awarded.

    An enemy absent from npcCountMap awards nothing; that is normal for bosses,
    for mobs that do not count, and for a pet like Glacial Tomb — a dungeon
    mechanic that encases a player, which Warcraft Logs models as a hostile pet
    owned by that player — so it is zero rather than an error.

    An enemy absent from actor_game_ids is different: ACTORS_QUERY returns
    every actor in the report, so a report actor id missing there means our own
    fetch is wrong, not that the log is odd. Defaulting that case to game_id 0
    would silently attach the wrong forces count to a real death.
    """
    deaths = []
    for event in events:
        if event.get("type") != "death":
            continue
        actor_id = event["targetID"]
        if actor_id not in actor_game_ids:
            raise IngestError(
                f"Enemy death targets actor {actor_id}, which is absent from "
                "the report's actors"
            )
        game_id = actor_game_ids[actor_id]
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


def parse_buff_ids(raw: str | None) -> tuple[int, ...]:
    """The `buffs` field's dot-terminated id list, as game ids.

    Measured 2026-09-11 against the cached DamageTaken stream of report
    6Kx1P9GbNXrcLdHa fight 36: the field is a string of ability game ids
    separated and terminated by a period, e.g. "391395.391398.". The trailing
    separator yields an empty final part, which is why the parts are filtered
    rather than trusted.
    """
    if not raw:
        return ()
    return tuple(int(part) for part in raw.split(".") if part)


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
                health_damage=int(event.get("amount") or 0),
                absorbed=int(event.get("absorbed") or 0),
                mitigated=int(event.get("mitigated") or 0),
                overkill=int(event.get("overkill") or 0),
                source_id=event.get("sourceID"),
                is_area=bool(event.get("isAoE")),
                is_tick=bool(event.get("tick")),
                buff_ids=parse_buff_ids(event.get("buffs")),
            )
        )
    return tuple(taken)


def build_damage_done(payload: dict[str, Any]) -> tuple[DamageDoneSeries, ...]:
    """The damage graph as domain series, with its rate converted to amounts.

    The response's numbers are damage per second. Multiplying by the interval
    reproduces the series' own `total` to within 0.3% to 0.7%, the residual
    being the last bucket overhanging the window -- measured 2026-09-12 and
    recorded in the wcl-api skill. Reading them as amounts instead would
    understate every bucket by the interval in seconds, which was 6.4 on the
    run this was measured against, and the chart would look entirely plausible.

    A player's series is keyed by an integer actor id and the run-wide sum by
    the string "Total", which is what drops the latter: nothing here has a use
    for it, and a run-wide damage total sitting in the model is one import away
    from a page that ranks.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    graph = report.get("graph") or {}
    rows = (graph.get("data") or {}).get("series") or []

    built: list[DamageDoneSeries] = []
    for row in rows:
        actor_id = row.get("id")
        if not isinstance(actor_id, int):
            continue
        interval_ms = float(row.get("pointInterval") or 0.0)
        # Guards the division below rather than any observed response: a
        # zero interval would make every bucket zero seconds wide, and a
        # silent column of noughts is worse than no track.
        if interval_ms <= 0:
            continue
        built.append(
            DamageDoneSeries(
                actor_id=actor_id,
                point_start_ms=int(row.get("pointStart") or 0),
                interval_ms=interval_ms,
                amounts=tuple(
                    int(round(float(point) * interval_ms / 1000))
                    for point in row.get("data") or []
                ),
            )
        )
    return tuple(built)


def build_health_samples(events: list[dict[str, Any]]) -> tuple[HealthSample, ...]:
    """One reading per cast that carried the caster's hit points.

    `includeResources` attaches `hitPoints` and `maxHitPoints` to an event for
    its source actor. A cast carrying neither produces no sample rather than a
    zero — a zero would read as a dead player — and a `begincast` is not a cast.
    """
    samples = []
    for event in events:
        if event.get("type") != "cast" or "sourceID" not in event:
            continue
        hit_points = event.get("hitPoints")
        max_hit_points = event.get("maxHitPoints")
        if hit_points is None or max_hit_points is None or int(max_hit_points) <= 0:
            continue
        samples.append(
            HealthSample(
                actor_id=event["sourceID"],
                timestamp_ms=event["timestamp"],
                hit_points=int(hit_points),
                max_hit_points=int(max_hit_points),
            )
        )
    return tuple(samples)


def build_healing(
    events: list[dict[str, Any]], ability_names: dict[int, str]
) -> tuple[HealingEvent, ...]:
    """Heals landing on a player and hits their shields soaked, from a `Healing` stream.

    A `heal` names the healing spell in `abilityGameID`. An `absorbed` event
    names the shield that soaked it in `abilityGameID` and the hit it soaked in
    `extraAbilityGameID`; the shield is what a recap wants to show, so that is
    the ability the event keeps. The stream's `removebuff` rows are not healing.
    """
    healing = []
    for event in events:
        kind = event.get("type")
        if kind not in ("heal", "absorbed"):
            continue
        ability_id = int(event["abilityGameID"])
        source_id_value = event.get("sourceID")
        source_id = int(source_id_value) if source_id_value is not None else -1
        healing.append(
            HealingEvent(
                actor_id=event["targetID"],
                source_id=source_id,
                ability_id=ability_id,
                ability_name=_ability_name(ability_names, ability_id),
                amount=int(event.get("amount") or 0),
                timestamp_ms=event["timestamp"],
                absorbed=kind == "absorbed",
            )
        )
    return tuple(healing)


def build_resurrections(
    events: list[dict[str, Any]], ability_names: dict[int, str]
) -> tuple[Resurrection, ...]:
    """Every `resurrect` row of a stream: who was brought back, by whom, with what."""
    return tuple(
        Resurrection(
            actor_id=event["targetID"],
            caster_id=event["sourceID"],
            ability_id=event["abilityGameID"],
            ability_name=_ability_name(ability_names, event["abilityGameID"]),
            timestamp_ms=event["timestamp"],
        )
        for event in events
        if event.get("type") == "resurrect"
    )


def _aura_rows(report: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    """The aura list under one aliased table, or an error if the table is absent.

    A table that came back null and a table with no auras are different claims:
    the first is a failed query, the second is a player who carried nothing.
    """
    table = report.get(alias)
    if not isinstance(table, dict):
        raise IngestError(f"The aura response carried no {alias} table")
    data = table.get("data")
    if not isinstance(data, dict):
        raise IngestError(f"The aura response's {alias} table carried no data block")
    return list(data.get("auras") or [])


def _aura(row: dict[str, Any]) -> Aura:
    return Aura(
        ability_id=int(row["guid"]),
        name=str(row["name"]),
        total_uptime_ms=int(row.get("totalUptime") or 0),
        uses=int(row.get("totalUses") or 0),
        bands=tuple(
            AuraBand(start_ms=int(band["startTime"]), end_ms=int(band["endTime"]))
            for band in row.get("bands") or ()
        ),
    )


def build_player_auras(payload: dict[str, Any], actor_id: int) -> PlayerAuras:
    """The aliased buff table for one actor, as domain values."""
    report = payload["reportData"]["report"]
    return PlayerAuras(
        actor_id=actor_id,
        on_self=tuple(_aura(row) for row in _aura_rows(report, "onSelf")),
    )
