# ABOUTME: Assembles a Run from Warcraft Logs, caching every response it fetches.
# ABOUTME: Satisfies the RunRepository port so services never learn where a run came from.

from typing import Any

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import WclClient
from wowperf.adapters.wcl.ingest import build_casts, build_deaths, build_run, select_keystone_fight
from wowperf.adapters.wcl.pagination import fetch_all_events
from wowperf.adapters.wcl.queries import (
    ABILITIES_QUERY,
    CASTS_QUERY,
    DEATHS_QUERY,
    FIGHTS_QUERY,
)
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.model import Run


class LoadedRun:
    """A run together with the event streams the analysers need."""

    def __init__(self, run: Run, casts: tuple[CastEvent, ...], deaths: tuple[Death, ...]) -> None:
        self.run = run
        self.casts = casts
        self.deaths = deaths


class WclRunRepository:
    def __init__(self, client: WclClient, cache: DiskCache) -> None:
        self._client = client
        self._cache = cache

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return self._cache.get_or_fetch(
            cache_key(query, variables),
            lambda: self._client.execute(query, variables),
        )

    def get(self, report_code: str, fight_id: int | None) -> Run:
        return self.load(report_code, fight_id).run

    def load(self, report_code: str, fight_id: int | None) -> LoadedRun:
        report = self._query(FIGHTS_QUERY, {"code": report_code})["reportData"]["report"]
        fight = select_keystone_fight(report["fights"], fight_id)
        run = build_run(report, fight)

        abilities = self._query(ABILITIES_QUERY, {"code": report_code})
        ability_names = {
            ability["gameID"]: ability["name"]
            for ability in abilities["reportData"]["report"]["masterData"]["abilities"]
        }

        event_variables = {
            "code": report_code,
            "fightId": run.fight_id,
            "startTime": float(fight["startTime"]),
            "endTime": float(fight["endTime"]),
        }
        cast_events = fetch_all_events(self._query, CASTS_QUERY, event_variables)
        death_events = fetch_all_events(self._query, DEATHS_QUERY, event_variables)

        casts = build_casts(cast_events, run, ability_names)
        deaths = build_deaths(death_events, run, casts, ability_names)
        return LoadedRun(run, casts, deaths)
