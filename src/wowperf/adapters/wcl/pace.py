# ABOUTME: Fetches our boss's (or council's) damage graphs and each reference kill's.
# ABOUTME: A reference is dropped with its reason recorded; nothing here is fatal to the sample.

from collections.abc import Sequence
from typing import Any

import httpx

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import RateLimitExceeded, WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_boss_damage,
    build_first_deaths,
    build_npc_actors,
    build_player_boss_damage,
    build_reference_fight,
)
from wowperf.adapters.wcl.pagination import fetch_all_events
from wowperf.adapters.wcl.queries import (
    BOSS_DAMAGE_GRAPH_QUERY,
    DEATHS_QUERY,
    NPC_ACTORS_QUERY,
    REFERENCE_FIGHT_QUERY,
)
from wowperf.domain.comparison.mechanics import ReferenceKillRow
from wowperf.domain.comparison.pace import (
    BOSS_IN_NO_REFERENCE,
    GRIDS_DIFFER,
    NO_BOSS,
    NO_BOSS_DAMAGE,
    NO_REFERENCE_KILL,
    PaceSample,
)
from wowperf.domain.comparison.pace_boss import find_bosses
from wowperf.domain.comparison.pace_curve import (
    BossDamage,
    PaceReference,
    PlayerSeries,
    sum_boss_damage,
)
from wowperf.domain.comparison.reference import REPORT_URL
from wowperf.domain.comparison.sample import SAMPLE_SIZE
from wowperf.domain.encounter import Encounter
from wowperf.domain.report.model import ReferenceRecord

FIGHT_NOT_IN_REPORT = "the reference fight is not in its report"
BOSS_NOT_AMONG_ENEMIES = "the boss is not among this fight's enemies"
BOSS_APPEARS_TWICE = "the boss appears as more than one actor"
NO_BOSS_SERIES = "the damage graph held no series for the boss"
GRIDS_DIFFER_REASON = "the bosses' damage graphs came back on different time grids"


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


def _boss_graphs(
    client: WclClient,
    cache: DiskCache,
    *,
    code: str,
    fight_id: int,
    start_ms: int,
    end_ms: int,
    target_ids: Sequence[int],
) -> tuple[BossDamage | None, bool, dict[int, BossDamage], bool]:
    """One graph per boss, summed: (total, grids differ, per-player, all from cache).

    The total is None when any graph carried no boss series, or when the
    graphs sat on different grids -- the second flag says which. A player's
    series sums their part of every graph they appear in.
    """
    totals: list[BossDamage | None] = []
    players: dict[int, list[BossDamage]] = {}
    all_hit = True
    for target_id in target_ids:
        payload, hit = _fetch(
            client, cache, BOSS_DAMAGE_GRAPH_QUERY,
            {"code": code, "fightId": fight_id, "startTime": float(start_ms),
             "endTime": float(end_ms), "targetId": target_id},
        )
        all_hit = all_hit and hit
        totals.append(build_boss_damage(payload, fight_start_ms=start_ms))
        for actor_id, series in build_player_boss_damage(payload, fight_start_ms=start_ms).items():
            players.setdefault(actor_id, []).append(series)
    if any(total is None for total in totals):
        return None, False, {}, all_hit
    summed = sum_boss_damage([total for total in totals if total is not None])
    if summed is None:
        return None, True, {}, all_hit
    per_player = {
        actor_id: combined
        for actor_id, parts in players.items()
        if (combined := sum_boss_damage(parts)) is not None
    }
    return summed, False, per_player, all_hit


def load_pace_sample(
    client: WclClient,
    own_cache: DiskCache,
    reference_cache: DiskCache,
    encounter: Encounter,
    references: tuple[ReferenceKillRow, ...],
) -> tuple[PaceSample, tuple[ReferenceRecord, ...]]:
    """Our boss's damage graph and each reference kill's, for one pull, kill or wipe.

    The boss is found among the fight's own enemies: one boss, or a council's
    bosses, each read through its own graph and summed onto one series, and
    `bosses_read` records how many. A reference fight must field every one of
    our bosses, found by game id.

    Our report's responses go in `own_cache`, which never expires; the
    reference kills' in `reference_cache`, which does -- other players' logs,
    kept for one comparison. `references` is the candidates in the order they
    are tried: `raid` hands its mechanics comparison's own members, so the
    page's two comparisons stand on one sample, and `night` hands the same
    members followed by every other candidate the leaderboard offers, so a
    reference that fails is refilled from the rows behind it. Either way the
    loop stops once it holds
    `SAMPLE_SIZE` references, and a candidate past that costs no request.

    Each side's boss graph is also split by player: `our_players` is our own
    roster's part of it, and each `PaceReference.players` its own kill's
    roster. A reference kill's deaths are read only when its row says someone
    died -- `ReferenceKillRow.deaths > 0` -- since a clean kill has no
    `until_seconds` to set and the query would spend quota for nothing. None
    of this is written anywhere; it lives for one comparison in memory.

    A reference is dropped, with its reason recorded, when its fight is
    missing, when one of our bosses' game ids names no actor in it or more than
    one, when its graphs carry no boss series, or when they sit on different
    time grids. Never fatal: a `WclError`, `IngestError` or `httpx.HTTPError`
    on one reference is recorded and the loop moves on. `RateLimitExceeded`
    alone is raised: the client raises it only once its own waits for the
    reset are spent, so it is every later request's failure, not one
    reference's.
    """
    actors_payload, _ = _fetch(
        client, own_cache, NPC_ACTORS_QUERY, {"code": encounter.report_code}
    )
    bosses = find_bosses(
        build_npc_actors(actors_payload),
        frozenset(enemy.actor_id for enemy in encounter.enemies),
        encounter.boss_name,
    )
    if not bosses:
        return PaceSample(unavailable=NO_BOSS), ()

    if not references:
        # No reference to compare against, so our own graph is never worth its
        # quota: this is the one withhold this function reaches before it has
        # spent anything on the fight it was actually asked to read.
        return PaceSample(unavailable=NO_REFERENCE_KILL), ()

    ours, grids_differ, our_series, _ = _boss_graphs(
        client, own_cache, code=encounter.report_code, fight_id=encounter.fight_id,
        start_ms=encounter.start_ms, end_ms=encounter.end_ms,
        target_ids=[boss.actor_id for boss in bosses],
    )
    if ours is None:
        return PaceSample(unavailable=GRIDS_DIFFER if grids_differ else NO_BOSS_DAMAGE), ()

    our_players = tuple(
        PlayerSeries(
            actor_id=player.actor_id,
            class_name=player.class_name,
            spec=player.spec,
            damage=our_series[player.actor_id],
        )
        for player in encounter.players
        if player.actor_id in our_series
    )

    members: list[PaceReference] = []
    records: list[ReferenceRecord] = []
    boss_absent_count = 0

    for row in references:
        if len(members) >= SAMPLE_SIZE:
            break
        try:
            fight_variables = {"code": row.report_code, "fightId": row.fight_id}
            fight_payload, fight_hit = _fetch(
                client, reference_cache, REFERENCE_FIGHT_QUERY, fight_variables
            )
            fight = build_reference_fight(fight_payload)
            if fight is None:
                records.append(_record(row, loaded=False, reason=FIGHT_NOT_IN_REPORT))
                continue

            target_ids: list[int] = []
            absent = duplicated = False
            for boss in bosses:
                matching = [
                    enemy.actor_id for enemy in fight.enemies if enemy.game_id == boss.game_id
                ]
                absent = absent or not matching
                duplicated = duplicated or len(matching) > 1
                if len(matching) == 1:
                    target_ids.append(matching[0])
            if absent:
                boss_absent_count += 1
                records.append(_record(row, loaded=False, reason=BOSS_NOT_AMONG_ENEMIES))
                continue
            if duplicated:
                records.append(_record(row, loaded=False, reason=BOSS_APPEARS_TWICE))
                continue

            damage, grids_differ, series, damage_hit = _boss_graphs(
                client, reference_cache, code=row.report_code, fight_id=row.fight_id,
                start_ms=fight.start_ms, end_ms=fight.end_ms, target_ids=target_ids,
            )
            if damage is None:
                records.append(
                    _record(row, loaded=False,
                            reason=GRIDS_DIFFER_REASON if grids_differ else NO_BOSS_SERIES)
                )
                continue

            deaths: dict[int, float] = {}
            if row.deaths > 0:
                events = fetch_all_events(
                    lambda one_query, variables: _fetch(
                        client, reference_cache, one_query, variables
                    )[0],
                    DEATHS_QUERY,
                    {
                        "code": row.report_code,
                        "fightId": row.fight_id,
                        "startTime": float(fight.start_ms),
                        "endTime": float(fight.end_ms),
                    },
                )
                deaths = build_first_deaths(
                    events,
                    frozenset(entry.actor_id for entry in fight.roster),
                    fight_start_ms=fight.start_ms,
                )
            players = tuple(
                PlayerSeries(
                    actor_id=entry.actor_id,
                    class_name=entry.class_name,
                    spec=entry.spec,
                    damage=series[entry.actor_id],
                    until_seconds=deaths.get(entry.actor_id),
                )
                for entry in fight.roster
                if entry.actor_id in series
            )

            members.append(
                PaceReference(
                    duration_seconds=row.duration_seconds, damage=damage, players=players
                )
            )
            records.append(_record(row, loaded=True, from_cache=fight_hit and damage_hit))
        except RateLimitExceeded:
            raise
        except (WclError, IngestError, httpx.HTTPError) as error:
            records.append(_record(row, loaded=False, reason=str(error)))
            continue

    if not members:
        unavailable = (
            BOSS_IN_NO_REFERENCE
            if references and boss_absent_count == len(references)
            else NO_REFERENCE_KILL
        )
        return (
            PaceSample(
                ours=ours, unavailable=unavailable, our_players=our_players,
                bosses_read=len(bosses),
            ),
            tuple(records),
        )

    return (
        PaceSample(
            ours=ours, references=tuple(members), our_players=our_players,
            bosses_read=len(bosses),
        ),
        tuple(records),
    )
