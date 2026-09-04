# ABOUTME: Assembles a Run from Warcraft Logs, caching every response it fetches.
# ABOUTME: Satisfies the RunRepository port so services never learn where a run came from.

from typing import Any, cast

from wowperf.adapters.cache.disk import DiskCache, cache_key
from wowperf.adapters.wcl.client import RateLimit, WclClient
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.ingest import (
    IngestError,
    build_casts,
    build_deaths,
    build_run,
    select_keystone_fight,
)
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
    def _require_report(payload: dict[str, Any], variables: dict[str, Any]) -> None:
        """Reject a null report.

        An unlisted or unknown report answers HTTP 200 with `reportData.report`
        null and no GraphQL errors. Raising before the payload is cached matters:
        entries never expire, so caching one would poison the key for good.
        """
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

    def get(self, report_code: str, fight_id: int | None) -> Run:
        """Build the run alone, without paying for the event streams `load` fetches."""
        report = self._report(report_code)
        return build_run(report, select_keystone_fight(report["fights"], fight_id))

    def load(self, report_code: str, fight_id: int | None) -> LoadedRun:
        report = self._report(report_code)
        fight = select_keystone_fight(report["fights"], fight_id)
        run = build_run(report, fight)

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

        casts = build_casts(cast_events, run, ability_names)
        deaths = build_deaths(death_events, run, casts, ability_names)
        return LoadedRun(run, casts, deaths)
