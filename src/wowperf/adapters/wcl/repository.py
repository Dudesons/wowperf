# ABOUTME: Assembles a Run from Warcraft Logs, caching every response it fetches.
# ABOUTME: Satisfies the RunRepository port so services never learn where a run came from.

from collections.abc import Sequence
from typing import Any, cast

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import RateLimit, RateLimitExceeded, WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_casts,
    build_damage_taken,
    build_deaths,
    build_enemy_cast_rows,
    build_enemy_deaths,
    build_interrupts,
    build_player_auras,
    build_run,
    select_keystone_fight,
)
from wowperf.adapters.wcl.pagination import fetch_all_events
from wowperf.adapters.wcl.queries import (
    ABILITIES_QUERY,
    ACTORS_QUERY,
    AFFIXES_QUERY,
    AURA_TABLE_QUERY,
    CASTS_QUERY,
    DAMAGE_TAKEN_QUERY,
    DEATHS_QUERY,
    ENEMY_CASTS_QUERY,
    ENEMY_DEATHS_QUERY,
    FIGHTS_QUERY,
    INTERRUPTS_QUERY,
    talents_query,
)
from wowperf.domain.auras import PlayerAuras
from wowperf.domain.model import LoadedRun, Run


class WclRunRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    @property
    def client(self) -> WclClient:
        return self._client

    @property
    def cache(self) -> DiskCache:
        return self._cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload = self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._fetch(query, variables),
        )
        # Also checked on the way out of the cache, so an entry written by an
        # older build still reports the problem instead of subscripting None.
        self._require_report(payload, variables)
        return payload

    def _fetch(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Fetch and validate a payload, so that only a usable one reaches the cache."""
        payload = self._client.execute(query, variables)
        self._require_report(payload, variables)
        return payload

    @staticmethod
    def _require_report(payload: dict[str, Any] | None, variables: dict[str, Any]) -> None:
        """Reject a null report.

        An unlisted or unknown report usually answers HTTP 200 with
        `reportData.report` null and no GraphQL errors. Since
        `WclClient.execute` now raises on a null `data` block, only a stale
        cache entry from an older build can deliver None here. Raising before
        the payload is cached matters: an entry lives for a day or forever, so
        caching one would poison the key for that whole span.
        """
        if payload is None:
            raise IngestError(
                f"Report {variables.get('code')} was not found, or is not accessible "
                "with these credentials. Private reports need a personal login, which "
                "this tool does not support."
            )
        report_data = payload.get("reportData")
        if isinstance(report_data, dict) and report_data.get("report") is None:
            raise IngestError(
                f"Report {variables.get('code')} was not found, or is not accessible "
                "with these credentials. Private reports need a personal login, which "
                "this tool does not support."
            )

    def rate_limit(self) -> RateLimit:
        """Read the quota straight from the API; a cached reading would be worthless."""
        return self._client.rate_limit()

    def _report(self, report_code: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._query(FIGHTS_QUERY, {"code": report_code})["reportData"]["report"],
        )

    def _fetch_affixes(self) -> dict[str, Any]:
        """Fetch and validate the affix table, so only a usable payload reaches the cache."""
        payload = self._client.execute(AFFIXES_QUERY, {})
        game_data = payload.get("gameData")
        if not isinstance(game_data, dict) or not game_data.get("affixes"):
            raise WclError("The affixes response did not carry gameData.affixes as expected")
        return payload

    def _affix_names(self, affix_ids: Sequence[int]) -> tuple[str, ...]:
        """Affix names from game data, with the bare id for anything unlisted.

        Goes to the cache and the client directly rather than through `_query`:
        the affix table needs its own validation before it may be cached
        (`_fetch_affixes` does that), and unlike every other query this
        repository issues, its absence must degrade the run rather than fail
        it — an affix id the report already carries is still usable on its
        own, so a header of bare ids is preferable to no report at all. A
        spent rate limit is the one failure still allowed through: it must
        stop the run rather than be swallowed into a silent degrade.

        Cached indefinitely: the affix table is game-wide and changes only when
        Blizzard adds one, at which point the new id simply resolves to itself
        until the cache is cleared.
        """
        if not affix_ids:
            return ()
        try:
            payload = self._cache.get_or_fetch(cache_key(AFFIXES_QUERY, {}), self._fetch_affixes)
        except WclError as error:
            if isinstance(error, RateLimitExceeded):
                raise
            return tuple(str(affix_id) for affix_id in affix_ids)
        rows = payload["gameData"]["affixes"]
        names = {int(row["id"]): str(row["name"]) for row in rows}
        return tuple(names.get(affix_id, str(affix_id)) for affix_id in affix_ids)

    def get(self, report_code: str, fight_id: int | None) -> Run:
        """Build the run alone, without paying for the event streams `load` fetches."""
        report = self._report(report_code)
        run = build_run(report, select_keystone_fight(report["fights"], fight_id))
        return run.model_copy(update={"affix_names": self._affix_names(run.affix_ids)})

    def _actor_game_ids(self, report_code: str) -> dict[int, int]:
        """Map every actor in the report to its game id, so an enemy death always resolves.

        A death can target a Pet actor as well as an NPC one: a dungeon mechanic
        that encases a player is modelled as a hostile pet owned by that player.
        Fetching every actor, not only type "NPC", is what makes that resolve.
        """
        payload = self._query(ACTORS_QUERY, {"code": report_code})
        report = payload["reportData"]["report"]
        master = report.get("masterData") or {}
        actors = master.get("actors")
        if actors is None:
            raise WclError(f"Report {report_code} returned no masterData.actors block")
        return {actor["id"]: actor["gameID"] for actor in actors}

    def _talents(self, report_code: str, fight: dict[str, Any]) -> dict[int, str]:
        """The talent import string per player, keyed by actor id.

        A player with no recorded build is left out rather than given an empty
        string: absent and "took no talents" are different claims.
        """
        actor_ids = [int(actor_id) for actor_id in fight.get("friendlyPlayers") or []]
        if not actor_ids:
            return {}

        payload = self._query(
            talents_query(actor_ids), {"code": report_code, "fightId": fight["id"]}
        )
        fights = payload["reportData"]["report"]["fights"] or [{}]
        codes = fights[0]
        return {
            actor_id: codes[f"a{actor_id}"]
            for actor_id in actor_ids
            if codes.get(f"a{actor_id}")
        }

    def load(self, report_code: str, fight_id: int | None) -> LoadedRun:
        report = self._report(report_code)
        fight = select_keystone_fight(report["fights"], fight_id)
        run = build_run(report, fight, self._talents(report_code, fight))
        run = run.model_copy(update={"affix_names": self._affix_names(run.affix_ids)})

        abilities = self._query(ABILITIES_QUERY, {"code": report_code})
        try:
            ability_names = {
                ability["gameID"]: ability["name"]
                for ability in abilities["reportData"]["report"]["masterData"]["abilities"]
            }
        except (KeyError, TypeError) as error:
            raise WclError(
                "The abilities response did not carry masterData.abilities as expected"
            ) from error

        event_variables = {
            "code": report_code,
            "fightId": run.fight_id,
            "startTime": float(fight["startTime"]),
            "endTime": float(fight["endTime"]),
        }
        cast_events = fetch_all_events(self._query, CASTS_QUERY, event_variables)
        death_events = fetch_all_events(self._query, DEATHS_QUERY, event_variables)
        enemy_cast_events = fetch_all_events(self._query, ENEMY_CASTS_QUERY, event_variables)
        interrupt_events = fetch_all_events(self._query, INTERRUPTS_QUERY, event_variables)
        enemy_death_events = fetch_all_events(self._query, ENEMY_DEATHS_QUERY, event_variables)
        damage_taken_events = fetch_all_events(self._query, DAMAGE_TAKEN_QUERY, event_variables)

        casts = build_casts(cast_events, run, ability_names)
        deaths = build_deaths(death_events, run, casts, ability_names)
        player_names = {player.actor_id: player.name for player in run.players}
        enemy_cast_rows = build_enemy_cast_rows(enemy_cast_events, run, ability_names)
        interrupts = build_interrupts(interrupt_events, run, player_names)
        actor_game_ids = self._actor_game_ids(report_code)
        enemy_deaths = build_enemy_deaths(
            enemy_death_events, run, actor_game_ids, dict(run.npc_count_map)
        )
        damage_taken = build_damage_taken(damage_taken_events, run, ability_names)

        return LoadedRun(
            run=run,
            casts=casts,
            deaths=deaths,
            enemy_cast_rows=enemy_cast_rows,
            interrupts=interrupts,
            enemy_deaths=enemy_deaths,
            damage_taken=damage_taken,
        )

    def auras(self, report_code: str, fight_id: int, actor_id: int) -> PlayerAuras:
        """Buff and debuff uptime for one player of one fight.

        Scoped rather than folded into `load`: an aura table is per-actor, so
        loading them for a whole roster would pay for ten tables to answer a
        question about two players. The debuff half of what comes back is
        always empty against the live API — confirmed 2026-09-05, no query
        argument narrows the enemy-debuff table to one caster; the measured
        table is in `.claude/skills/wcl-api/SKILL.md`, "The debuff half cannot
        be scoped to one caster".
        """
        payload = self._query(
            AURA_TABLE_QUERY,
            {"code": report_code, "fightId": fight_id, "actorId": actor_id},
        )
        return build_player_auras(payload, actor_id)
