# ABOUTME: Translates Warcraft Logs report JSON into the domain model.
# ABOUTME: The only module that knows Warcraft Logs field names; everything downstream is clean.

from typing import Any

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.base import Frozen
from wowperf.domain.comparison.pace_boss import NpcActor
from wowperf.domain.comparison.pace_curve import BossDamage
from wowperf.domain.encounter import Encounter
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
from wowperf.domain.loadout import Loadout
from wowperf.domain.model import DamageDoneSeries, EnemyNpc, Player, Pull, Run
from wowperf.domain.phases import Phase, PhaseTransition


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


def select_raid_fight(fights: list[dict[str, Any]], fight_id: int | None) -> dict[str, Any]:
    """Find the boss fight to analyse.

    A raid fight is one with a non-zero encounterID and no keystoneLevel. Trash
    between bosses is logged as sibling fights carrying encounterID 0, and a
    Mythic+ run carries the dungeon's own encounterID -- so the encounter id
    alone does not separate a boss from a key, and selecting on it would let
    this command analyse a keystone as a boss and never say so.

    Unlike a keystone, a boss fight is not required to be a kill: a wipe is the
    log a progression raid most wants read, and the analysers that need a kill
    withhold themselves rather than being gated here.

    With no `fight_id` and several boss fights on the report, this refuses
    rather than choosing. A night holds eight attempts on one boss; picking the
    last, or the only kill, would analyse a fight nobody asked for.
    """
    boss_fights = [
        fight
        for fight in fights
        if fight.get("encounterID") and fight.get("keystoneLevel") is None
    ]

    if fight_id is not None:
        chosen = next((fight for fight in fights if fight["id"] == fight_id), None)
        if chosen is None:
            raise IngestError(f"This report has no fight {fight_id}")
        if chosen.get("keystoneLevel") is not None:
            raise IngestError(f"Fight {fight_id} is a Mythic+ run; analyze it with `analyze`")
        if not chosen.get("encounterID"):
            raise IngestError(f"Fight {fight_id} is not a boss fight")
        return chosen

    if not boss_fights:
        # The same mistake the explicit-fight_id branch above catches for one
        # fight: a whole report that is a Mythic+ run and holds no boss fight at
        # all. Naming `analyze` here is what turns this from a dead end into a
        # signpost -- the fight the reader wanted to see is real, just not one
        # this command reads.
        if any(fight.get("keystoneLevel") is not None for fight in fights):
            raise IngestError(
                "This report contains no boss fight; it holds a Mythic+ run instead; "
                "analyze it with `analyze`"
            )
        raise IngestError("This report contains no boss fight")
    if len(boss_fights) > 1:
        ids = ", ".join(str(fight["id"]) for fight in boss_fights)
        # `--fight` first, and the alternative after it: a reader who wanted one
        # of these fights is answered before being offered another command. The
        # second clause is for the reader who pasted a bare report link meaning
        # the whole night, which is now something this tool reads rather than a
        # question it can only refuse.
        raise IngestError(
            f"This report holds several boss fights ({ids}); pass --fight, "
            "or read every one of them with `wowperf night`"
        )
    return boss_fights[0]


def _build_players(
    fight: dict[str, Any],
    actors: list[dict[str, Any]],
    talents: dict[int, str],
    loadouts: dict[int, Loadout],
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
                loadout=loadouts.get(actor_id),
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
    report: dict[str, Any],
    fight: dict[str, Any],
    talents: dict[int, str] | None = None,
    loadouts: dict[int, Loadout] | None = None,
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
        players=_build_players(fight, actors, talents or {}, loadouts or {}),
        pulls=_build_pulls(fight),
    )


def build_raid_roster(
    report: dict[str, Any],
    fight: dict[str, Any],
    talents: dict[int, str] | None = None,
) -> tuple[Player, ...]:
    """One boss fight's roster, with each player's build where the report has one.

    Public because a reference kill needs exactly this and nothing else around
    it: a leaderboard row names a fight in somebody else's report, and the only
    things read off it are who was there and what they cast. Building a whole
    `Encounter` for that would need a `partition` the reference's report never
    states, which `build_encounter` deliberately refuses to guess.

    No loadouts: the raid path does not fetch `playerDetails`, and an empty map
    is what leaves every player's `loadout` None. Withholding the gear
    comparison is the honest reading of "never fetched" -- inventing a zeroed
    `Loadout` here would have the gear analysers argue from nothing.
    """
    actors = report.get("masterData", {}).get("actors") or []
    return _build_players(fight, actors, talents or {}, {})


def build_phases(report: dict[str, Any], encounter_id: int) -> tuple[tuple[Phase, ...], bool]:
    """The phases this encounter has, and whether they separate its wipes.

    `Report.phases` lists one entry per encounter in the report. An encounter
    with no entry has no phases, which is a fact about the boss rather than an
    error: two of eight bosses measured on 2026-09-16 were like this.

    `separatesWipes` is Warcraft Logs' own opinion on whether phase is a
    meaningful way to group that encounter's attempts, and it varies between
    encounters in one report. Returning it beside the names keeps the guard and
    the thing it guards in one place.
    """
    for entry in report.get("phases") or ():
        if entry.get("encounterID") != encounter_id:
            continue
        phases = tuple(
            Phase(
                id=int(phase["id"]),
                name=str(phase["name"]),
                is_intermission=bool(phase.get("isIntermission")),
            )
            for phase in entry.get("phases") or ()
        )
        return phases, bool(entry.get("separatesWipes"))
    return (), False


def build_encounter(
    report: dict[str, Any],
    fight: dict[str, Any],
    *,
    partition: int,
    talents: dict[int, str] | None = None,
) -> Encounter:
    """One boss fight as a domain object.

    `partition` is passed rather than read off the fight: a ReportFight carries
    no partition, and the report's own rankings row is where it comes from. The
    caller that has it passes it; nothing here guesses.
    """
    players = build_raid_roster(report, fight, talents)

    difficulty = fight.get("difficulty")
    if difficulty is None:
        raise IngestError(
            f"Fight {fight.get('id')} is a boss fight but carries no difficulty"
        )

    encounter_id = _required(fight, "encounterID")
    phases, _separates_wipes = build_phases(report, encounter_id)

    return Encounter(
        report_code=report["code"],
        fight_id=fight["id"],
        encounter_id=encounter_id,
        boss_name=fight["name"],
        difficulty=int(difficulty),
        partition=partition,
        # `size` is the raid size the report recorded. Where it is absent the
        # roster is the honest answer, and it is the number every per-player
        # median is drawn over anyway.
        size=int(fight["size"]) if fight.get("size") else len(players),
        kill=bool(fight.get("kill")),
        fight_percentage=fight.get("fightPercentage"),
        boss_percentage=fight.get("bossPercentage"),
        last_phase=fight.get("lastPhase"),
        last_phase_is_intermission=bool(fight.get("lastPhaseIsIntermission")),
        phase_transitions=tuple(
            # int() truncates the API's Float rather than rounding, so a
            # transition is never reported as later than it happened.
            PhaseTransition(id=int(t["id"]), start_ms=int(t["startTime"]))
            for t in fight.get("phaseTransitions") or ()
        ),
        phases=phases,
        start_ms=int(fight["startTime"]),
        end_ms=int(fight["endTime"]),
        owner_name=(report.get("owner") or {}).get("name"),
        players=players,
    )


def pull_index_at(pulls: tuple[Pull, ...], timestamp_ms: int) -> int | None:
    """Which pull was underway at this moment, or None if the group was between pulls.

    Also None whenever `pulls` is empty, which is what every event of a boss
    fight passes: a boss fight carries no pulls at all, so there is no pull to
    be inside or outside of. That is a real answer, not a missing one -- the
    same reason `analyse_deaths` reads a death against the fight (`fight_offset`)
    rather than against a pull once there are none.
    """
    for pull in pulls:
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
    events: list[dict[str, Any]], pulls: tuple[Pull, ...], ability_names: dict[int, str]
) -> tuple[CastEvent, ...]:
    return tuple(
        CastEvent(
            actor_id=event["sourceID"],
            ability_id=event["abilityGameID"],
            ability_name=_ability_name(ability_names, event["abilityGameID"]),
            timestamp_ms=event["timestamp"],
            pull_index=pull_index_at(pulls, event["timestamp"]),
            target_id=_target_of(event),
        )
        for event in events
        if event.get("type") == "cast" and "sourceID" in event
    )


def build_deaths(
    events: list[dict[str, Any]],
    pulls: tuple[Pull, ...],
    casts: tuple[CastEvent, ...],
    player_names: dict[int, str],
    ability_names: dict[int, str],
) -> tuple[Death, ...]:
    """Build deaths, measuring the real cost as time until the player next acted on another actor.

    The timer penalty understates a death. The seconds a player spent unable to
    contribute is observable, so we measure that instead of estimating a run-back.
    """
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
                player_name=player_names.get(actor_id, f"Actor {actor_id}"),
                actor_id=actor_id,
                timestamp_ms=timestamp,
                killing_blow_id=event.get("killingAbilityGameID", 0),
                killing_blow=_ability_name(
                    ability_names, event.get("killingAbilityGameID", 0)
                ),
                pull_index=pull_index_at(pulls, timestamp),
                seconds_until_next_action=(min(later) - timestamp) / 1000 if later else None,
            )
        )
    return tuple(deaths)


def build_enemy_cast_rows(
    events: list[dict[str, Any]],
    pulls: tuple[Pull, ...],
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
                pull_index=pull_index_at(pulls, event["timestamp"]),
            )
        )
    return tuple(rows)


def build_interrupts(
    events: list[dict[str, Any]],
    pulls: tuple[Pull, ...],
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
                pull_index=pull_index_at(pulls, event["timestamp"]),
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
                pull_index=pull_index_at(run.pulls, event["timestamp"]),
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
    pulls: tuple[Pull, ...],
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
                pull_index=pull_index_at(pulls, event["timestamp"]),
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
    reproduces the series' own `total` to within 0.3% to 0.7%, always short and
    for a reason nobody has established -- measured 2026-09-12, and the wcl-api
    skill records why the overhang it was once blamed on cannot be it. Reading
    them as amounts instead would
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


def _boss_damage_row(row: dict[str, Any], fight_start_ms: int) -> BossDamage | None:
    """One boss-scoped damage graph row, converted from its rate.

    Shared by `build_boss_damage` (the `Total` row) and `build_player_boss_damage`
    (every per-player row), so the rate conversion lives once. `None` when the
    row's interval is zero or negative -- the same guard `build_damage_done`
    applies, for the same reason: a zero interval would make every bucket zero
    seconds wide.
    """
    interval_ms = float(row.get("pointInterval") or 0.0)
    if interval_ms <= 0:
        return None
    return BossDamage(
        interval_ms=interval_ms,
        amounts=tuple(
            int(round(float(point) * interval_ms / 1000)) for point in row.get("data") or []
        ),
        lead_ms=int(row.get("pointStart") or 0) - fight_start_ms,
    )


def build_boss_damage(payload: dict[str, Any], *, fight_start_ms: int) -> BossDamage | None:
    """The `Total` series of a boss-scoped damage graph, converted from its rate.

    `build_damage_done` drops the `"Total"` row deliberately -- a run-wide sum
    sitting in the model is one import away from a page that ranks players.
    This graph is different: `targetID` already scopes it to one enemy actor,
    so there is no per-player ranking to protect, and `Total` is the only row
    this function reads. The per-player rows this same graph carries are read
    by `build_player_boss_damage`.

    `None` when the response holds no `Total` row, or when its interval is
    zero or negative.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    graph = report.get("graph") or {}
    rows = (graph.get("data") or {}).get("series") or []

    for row in rows:
        if row.get("id") != "Total":
            continue
        return _boss_damage_row(row, fight_start_ms)
    return None


def build_player_boss_damage(
    payload: dict[str, Any], *, fight_start_ms: int
) -> dict[int, BossDamage]:
    """Every per-player row of a boss-scoped damage graph, keyed by actor id.

    The same graph `build_boss_damage` reads its `Total` row from, split by
    player: every row whose `id` is an `int` (never `bool`, which Python's
    `isinstance` would otherwise let through as a numeric type). A row with a
    non-positive interval is skipped rather than raising, the same guard
    `_boss_damage_row` applies to the `Total` row.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    graph = report.get("graph") or {}
    rows = (graph.get("data") or {}).get("series") or []

    built: dict[int, BossDamage] = {}
    for row in rows:
        actor_id = row.get("id")
        if not isinstance(actor_id, int) or isinstance(actor_id, bool):
            continue
        damage = _boss_damage_row(row, fight_start_ms)
        if damage is not None:
            built[actor_id] = damage
    return built


def build_npc_actors(payload: dict[str, Any]) -> tuple[NpcActor, ...]:
    """Every enemy actor of a report, with its boss flag.

    A row missing `id` or `gameID` is skipped: it names nothing `find_boss_actor`
    or a reference fight's enemy list could ever match against.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    rows = (report.get("masterData") or {}).get("actors") or []
    built = []
    for row in rows:
        actor_id, game_id = row.get("id"), row.get("gameID")
        if actor_id is None or game_id is None:
            continue
        built.append(
            NpcActor(
                actor_id=int(actor_id),
                game_id=int(game_id),
                name=str(row.get("name") or ""),
                sub_type=str(row.get("subType") or ""),
            )
        )
    return tuple(built)


class RosterEntry(Frozen):
    """One reference kill's player, by class and spec -- never by name.

    `PlayerSeries` carries the same two fields for the same reason: a
    per-player comparison groups by class and spec, and nothing here needs a
    name to do it.
    """

    actor_id: int
    class_name: str
    spec: str


class ReferenceFight(Frozen):
    """One reference kill's own fight window, enemy roster and player roster.

    Read to find the boss actor of a report we did not fetch `masterData`
    for: our own boss's game id, looked up in this fight's own `enemies`.

    `roster` is this fight's own player roster, for the per-player
    comparison; empty when the fight carries no roster fields. It is built
    from `friendlyPlayers` and `friendlySpecs`, which name the roster of this
    fight alone, never from the report's player actors -- those span every
    fight in the report, so filtering them by id alone would silently include
    a player who was never in this fight.
    """

    start_ms: int
    end_ms: int
    enemies: tuple[EnemyNpc, ...]
    roster: tuple[RosterEntry, ...] = ()


def _reference_int(value: Any, description: str) -> int:
    """A field `build_reference_fight` cannot build a reference from without.

    A reference fight lives in a report we do not own, so a missing or
    non-numeric field is schema drift rather than something to default away.
    Raising `IngestError` here is what keeps it inside `load_pace_sample`'s own
    `except` tuple -- a bare `KeyError` or `TypeError` would fall through that
    tuple uncaught and take the whole command down with it.
    """
    if not isinstance(value, (int, float)):
        raise IngestError(f"A reference fight carries no usable {description}")
    return int(value)


def _reference_roster(
    fight: dict[str, Any], actors: list[dict[str, Any]]
) -> tuple[RosterEntry, ...]:
    """`friendlyPlayers` paired with `friendlySpecs`, classed from the actor lookup.

    Index-aligned, as `_build_players` reads the same two arrays. An entry
    whose spec is null or missing, or whose id names no player actor, is
    skipped -- a player not pooled rather than a guess, since neither array
    is filled in for every reference kill's report.
    """
    ids = fight.get("friendlyPlayers") or []
    specs = fight.get("friendlySpecs") or []
    class_by_id = {actor["id"]: actor.get("subType") for actor in actors if "id" in actor}

    roster = []
    for position, actor_id in enumerate(ids):
        spec = specs[position] if position < len(specs) else None
        if spec is None:
            continue
        class_name = class_by_id.get(actor_id)
        if class_name is None:
            continue
        roster.append(
            RosterEntry(
                actor_id=_reference_int(actor_id, "roster actor id"),
                class_name=str(class_name),
                spec=str(spec),
            )
        )
    return tuple(roster)


def build_reference_fight(payload: dict[str, Any]) -> ReferenceFight | None:
    """The one fight `REFERENCE_FIGHT_QUERY` asked for, or `None` when it is missing.

    The player actors `masterData` carries are an id-to-class lookup only,
    never the roster: they span the whole report, across every fight in it,
    so filtering them by id alone would silently include a player who was
    never in this fight. The roster comes from `friendlyPlayers` and
    `friendlySpecs`, which name this fight's own roster.
    """
    report = (payload.get("reportData") or {}).get("report") or {}
    fights = report.get("fights") or []
    if not fights:
        return None
    fight = fights[0]
    actors = (report.get("masterData") or {}).get("actors") or []
    return ReferenceFight(
        start_ms=_reference_int(fight.get("startTime"), "startTime"),
        end_ms=_reference_int(fight.get("endTime"), "endTime"),
        enemies=tuple(
            EnemyNpc(
                actor_id=_reference_int(npc.get("id"), "enemy id"),
                game_id=_reference_int(npc.get("gameID"), "enemy gameID"),
            )
            for npc in (fight.get("enemyNPCs") or [])
        ),
        roster=_reference_roster(fight, actors),
    )


def build_first_deaths(
    events: list[dict[str, Any]], actor_ids: frozenset[int], *, fight_start_ms: int
) -> dict[int, float]:
    """The first `death` event of each listed player, in seconds from the pull.

    Only the first: a reference player's `until_seconds` marks where their
    part in the kill ended, and a second death after being resurrected is not
    that moment. An event whose `targetID` or `timestamp` is not an `int` is
    skipped, the same guard `build_deaths` applies to the same keys.
    """
    first: dict[int, float] = {}
    for event in events:
        if event.get("type") != "death":
            continue
        actor_id = event.get("targetID")
        timestamp = event.get("timestamp")
        if not isinstance(actor_id, int) or isinstance(actor_id, bool):
            continue
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            continue
        if actor_id not in actor_ids or actor_id in first:
            continue
        first[actor_id] = (timestamp - fight_start_ms) / 1000
    return first


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
        icon=str(row.get("abilityIcon") or ""),
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
