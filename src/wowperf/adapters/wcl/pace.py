# ABOUTME: Fetches our boss's damage graph and each reference kill's, by the boss-actor rule.
# ABOUTME: A reference is dropped with its reason recorded; nothing here is fatal to the sample.

from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_boss_damage,
    build_npc_actors,
    build_reference_fight,
)
from wowperf.adapters.wcl.queries import (
    BOSS_DAMAGE_GRAPH_QUERY,
    NPC_ACTORS_QUERY,
    REFERENCE_FIGHT_QUERY,
)
from wowperf.domain.comparison.mechanics import ReferenceKillRow
from wowperf.domain.comparison.pace import (
    BOSS_IN_NO_REFERENCE,
    NO_BOSS_DAMAGE,
    NO_REFERENCE_KILL,
    NO_SINGLE_BOSS,
    PaceSample,
)
from wowperf.domain.comparison.pace_boss import find_boss_actor
from wowperf.domain.comparison.pace_curve import PaceReference
from wowperf.domain.comparison.reference import REPORT_URL
from wowperf.domain.encounter import Encounter
from wowperf.domain.report.model import ReferenceRecord

FIGHT_NOT_IN_REPORT = "the reference fight is not in its report"
BOSS_NOT_AMONG_ENEMIES = "the boss is not among this fight's enemies"
BOSS_APPEARS_TWICE = "the boss appears as more than one actor"
NO_BOSS_SERIES = "the damage graph held no series for the boss"


def _fetch(
    client: WclClient, cache: DiskCache, query: str, variables: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Run one query through one cache, as every other repository in this adapter does.

    A plain helper rather than a lambda inlined at each call site: a lambda
    written inside a `for` loop closes over the loop variable by name, not by
    value, so it would see whichever `variables` the loop last assigned
    rather than the one it was built for.
    """
    return cache.get_or_fetch(cache_key(query, variables), lambda: client.execute(query, variables))


def _record(
    row: ReferenceKillRow, *, loaded: bool, reason: str = "", from_cache: bool = False
) -> ReferenceRecord:
    """One reference kill's outcome, in the shape `_mechanics_record` keeps for its own axis.

    `keystone_level` is written as 0 for the reason `_mechanics_record` gives:
    a boss kill has none. `player_slug` and `player_name` stay at their empty
    default: the pace axis is drawn once for the whole encounter, not per
    player.
    """
    return ReferenceRecord(
        report_code=row.report_code,
        fight_id=row.fight_id,
        keystone_level=0,
        url=REPORT_URL.format(code=row.report_code, fight=row.fight_id),
        axis="pace",
        loaded=loaded,
        reason=reason,
        from_cache=from_cache,
    )


def load_pace_sample(
    client: WclClient,
    own_cache: DiskCache,
    reference_cache: DiskCache,
    encounter: Encounter,
    references: tuple[ReferenceKillRow, ...],
) -> tuple[PaceSample, tuple[ReferenceRecord, ...]]:
    """Our boss's damage graph and each reference kill's, for one wipe.

    Our report's responses go in `own_cache`, which never expires; the
    reference kills' in `reference_cache`, which does -- other players' logs,
    kept for one comparison. `references` is the mechanics comparison's own
    members, so the page's two comparisons stand on one sample.

    A reference is dropped, with its reason recorded, when its fight is
    missing, when our boss's game id names no actor in it or more than one, or
    when its graph carries no boss series. Never fatal: a `WclError`,
    `IngestError` or `httpx.HTTPError` on one reference is recorded and the
    loop moves on.
    """
    actors_payload, _ = _fetch(
        client, own_cache, NPC_ACTORS_QUERY, {"code": encounter.report_code}
    )
    boss = find_boss_actor(build_npc_actors(actors_payload), encounter.boss_name)
    if boss is None:
        return PaceSample(unavailable=NO_SINGLE_BOSS), ()

    own_graph_variables = {
        "code": encounter.report_code,
        "fightId": encounter.fight_id,
        "startTime": float(encounter.start_ms),
        "endTime": float(encounter.end_ms),
        "targetId": boss.actor_id,
    }
    graph_payload, _ = _fetch(client, own_cache, BOSS_DAMAGE_GRAPH_QUERY, own_graph_variables)
    ours = build_boss_damage(graph_payload, fight_start_ms=encounter.start_ms)
    if ours is None:
        return PaceSample(unavailable=NO_BOSS_DAMAGE), ()

    if not references:
        return PaceSample(ours=ours, unavailable=NO_REFERENCE_KILL), ()

    members: list[PaceReference] = []
    records: list[ReferenceRecord] = []
    boss_absent_count = 0

    for row in references:
        try:
            fight_variables = {"code": row.report_code, "fightId": row.fight_id}
            fight_payload, fight_hit = _fetch(
                client, reference_cache, REFERENCE_FIGHT_QUERY, fight_variables
            )
            fight = build_reference_fight(fight_payload)
            if fight is None:
                records.append(_record(row, loaded=False, reason=FIGHT_NOT_IN_REPORT))
                continue

            matching = [
                enemy.actor_id for enemy in fight.enemies if enemy.game_id == boss.game_id
            ]
            if not matching:
                boss_absent_count += 1
                records.append(_record(row, loaded=False, reason=BOSS_NOT_AMONG_ENEMIES))
                continue
            if len(matching) > 1:
                records.append(_record(row, loaded=False, reason=BOSS_APPEARS_TWICE))
                continue

            graph_variables = {
                "code": row.report_code,
                "fightId": row.fight_id,
                "startTime": float(fight.start_ms),
                "endTime": float(fight.end_ms),
                "targetId": matching[0],
            }
            damage_payload, damage_hit = _fetch(
                client, reference_cache, BOSS_DAMAGE_GRAPH_QUERY, graph_variables
            )
            damage = build_boss_damage(damage_payload, fight_start_ms=fight.start_ms)
            if damage is None:
                records.append(_record(row, loaded=False, reason=NO_BOSS_SERIES))
                continue

            members.append(PaceReference(duration_seconds=row.duration_seconds, damage=damage))
            records.append(_record(row, loaded=True, from_cache=fight_hit and damage_hit))
        except (WclError, IngestError, httpx.HTTPError) as error:
            records.append(_record(row, loaded=False, reason=str(error)))
            continue

    if not members:
        unavailable = (
            BOSS_IN_NO_REFERENCE
            if references and boss_absent_count == len(references)
            else NO_REFERENCE_KILL
        )
        return PaceSample(ours=ours, unavailable=unavailable), tuple(records)

    return PaceSample(ours=ours, references=tuple(members)), tuple(records)
