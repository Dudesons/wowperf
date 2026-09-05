# ABOUTME: POSTs GraphQL to the Warcraft Logs client API and surfaces its errors as exceptions.
# ABOUTME: Point cost per query is undocumented, so quota is read from the API, never assumed.

import re
from typing import Any, cast

import httpx

from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.queries import RATE_LIMIT_QUERY
from wowperf.domain.base import Frozen

CLIENT_ENDPOINT = "https://www.warcraftlogs.com/api/v2/client"


def _operation_name(query: str) -> str:
    """Best-effort GraphQL operation name, for naming a query in an error message."""
    match = re.search(r"query\s+(\w+)", query)
    return match.group(1) if match else "an unnamed query"


class RateLimitExceeded(WclError):
    """The hourly point budget is spent. Points reset on a fixed one-hour cycle."""


class RateLimit(Frozen):
    limit_per_hour: int
    points_spent_this_hour: float
    points_reset_in: int


class WclClient:
    def __init__(
        self,
        tokens: TokenProvider,
        http: httpx.Client,
        endpoint: str = CLIENT_ENDPOINT,
    ) -> None:
        self._tokens = tokens
        self._http = http
        self._endpoint = endpoint

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._http.post(
            self._endpoint,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {self._tokens.token()}"},
        )
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise RateLimitExceeded(
                "Warcraft Logs hourly point budget is spent. Wait for the reset."
            )
        response.raise_for_status()

        payload = response.json()
        if "errors" in payload:
            messages = "; ".join(
                str(error.get("message", "unknown error")) for error in payload["errors"]
            )
            raise WclError(messages)
        if "data" not in payload:
            raise WclError(
                "Warcraft Logs returned a 200 response carrying neither 'data' nor 'errors'"
            )
        data = payload["data"]
        if data is None:
            # A real response shape, not only a null nested report: casting this to
            # a dict would hand every caller a `None` the return annotation says
            # cannot happen. Raising here, once, fixes every caller at once instead
            # of requiring each one to guard against a type its annotation denies.
            on_report = (
                f" on report {variables['code']}" if variables and "code" in variables else ""
            )
            raise WclError(
                f"Warcraft Logs returned a 200 response with a null 'data' block "
                f"for {_operation_name(query)}{on_report}"
            )
        return cast(dict[str, Any], data)

    def rate_limit(self) -> RateLimit:
        data = self.execute(RATE_LIMIT_QUERY).get("rateLimitData")
        if not isinstance(data, dict):
            raise WclError("The rate limit response is missing rateLimitData")

        missing = [
            field
            for field in ("limitPerHour", "pointsSpentThisHour", "pointsResetIn")
            if field not in data
        ]
        if missing:
            raise WclError(f"The rate limit response is missing {', '.join(missing)}")

        return RateLimit(
            limit_per_hour=data["limitPerHour"],
            points_spent_this_hour=data["pointsSpentThisHour"],
            points_reset_in=data["pointsResetIn"],
        )
