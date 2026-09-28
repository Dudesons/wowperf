# ABOUTME: POSTs GraphQL to the Warcraft Logs client API and surfaces its errors as exceptions.
# ABOUTME: Point cost per query is undocumented, so quota is read from the API, never assumed.

import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast

import httpx

from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.cost import CostLedger
from wowperf.adapters.wcl.errors import WclError
from wowperf.adapters.wcl.queries import RATE_LIMIT_QUERY, operation_name, with_rate_limit
from wowperf.domain.base import Frozen

CLIENT_ENDPOINT = "https://www.warcraftlogs.com/api/v2/client"


def _operation_name(query: str) -> str:
    """Best-effort GraphQL operation name, for error messages and for cost rows."""
    return operation_name(query) or "an unnamed query"


class RateLimitExceeded(WclError):
    """The hourly point budget is spent. Points reset on a fixed one-hour cycle."""


class RateLimit(Frozen):
    limit_per_hour: int
    points_spent_this_hour: float
    points_reset_in: int


CYCLE_SECONDS = 3600.0
"""The budget resets on a fixed one-hour cycle, so no reset is further off than this."""

RESET_MARGIN_SECONDS = 5.0
"""Added to a wait for the reset, so the retry lands after it rather than on it."""

BURST_BACKOFF_SECONDS = 30.0
"""The first wait when the last reading says points remained.

A 429 with budget left is not the hourly budget as far as the reading knows.
Warcraft Logs documents no shorter limit, but a forum report describes 429s
under the hourly cap, so a short back-off comes before a wait for the reset.
"""

MIN_WAIT_SECONDS = 1.0
MAX_WAITS = 2
"""Waits per request before a 429 is raised: a back-off, then the reset at most."""


def _retry_after(response: httpx.Response) -> float | None:
    """The response's own `Retry-After`, in seconds from now, or None if absent or unreadable.

    Whether Warcraft Logs sends one is unconfirmed -- its documentation could
    not be read, and `.claude/skills/wcl-api/SKILL.md` records that -- but
    RFC 9110 defines it for a 429 and an open-source client of this API reads
    it, so it is honoured when present and never relied on.
    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (when - datetime.now(UTC)).total_seconds()


def _spoken(seconds: float) -> str:
    whole = round(seconds)
    minutes, rest = divmod(whole, 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


class WclClient:
    def __init__(
        self,
        tokens: TokenProvider,
        http: httpx.Client,
        endpoint: str = CLIENT_ENDPOINT,
        *,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        on_wait: Callable[[str], None] | None = None,
    ) -> None:
        """`sleep`, `clock` and `on_wait` default to really waiting, a monotonic
        clock, and saying nothing: the adapter never prints, so the command that
        builds it passes `on_wait` to tell its reader why it paused."""
        self._tokens = tokens
        self._http = http
        self._endpoint = endpoint
        self._costs = CostLedger()
        self._reading: dict[str, Any] | None = None
        self._sleep = sleep if sleep is not None else time.sleep
        self._clock = clock if clock is not None else time.monotonic
        self._on_wait = on_wait
        # The last usable quota reading and when it was taken, for a 429 to
        # count the reset from. Kept apart from `_reading`, which every
        # response overwrites, because a response carrying no reading says
        # nothing about when the budget resets.
        self._last_quota: tuple[float, float, float, float] | None = None

    @property
    def costs(self) -> CostLedger:
        """What every query this client sent has cost."""
        return self._costs

    def _wait_for(self, response: httpx.Response, waited: int) -> tuple[float, str]:
        """How long to wait before retrying a 429, and why, in words.

        A `Retry-After` wins when the response carries a readable one. Without
        it, the last quota reading decides: a spent budget waits for the reset
        it named, less the time since, on the fixed hourly cycle; budget left
        backs off briefly first, and waits for the reset only if refused again.
        With no reading at all, a whole cycle is the one wait sure to cross a
        reset. No wait is longer than a cycle.
        """
        header = _retry_after(response)
        if header is not None:
            seconds, why = header, "the response asked for that wait"
        else:
            spent = self._last_quota is not None and self._last_quota[0] >= self._last_quota[1]
            if waited == 0 and not spent:
                seconds, why = BURST_BACKOFF_SECONDS, "points remained, so a short back-off first"
            elif self._last_quota is None:
                seconds = CYCLE_SECONDS + RESET_MARGIN_SECONDS
                why = "no quota reading names the reset, so one whole cycle"
            else:
                _, _, reset_in, taken_at = self._last_quota
                age = self._clock() - taken_at
                seconds = (reset_in - age) % CYCLE_SECONDS + RESET_MARGIN_SECONDS
                why = "the hourly point budget is spent until the next reset"
        return min(max(seconds, MIN_WAIT_SECONDS), CYCLE_SECONDS + RESET_MARGIN_SECONDS), why

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        instrumented = with_rate_limit(query)
        waited = 0
        while True:
            response = self._http.post(
                self._endpoint,
                json={"query": instrumented, "variables": variables or {}},
                headers={"Authorization": f"Bearer {self._tokens.token()}"},
            )
            if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                break
            if waited >= MAX_WAITS:
                raise RateLimitExceeded(
                    "Warcraft Logs hourly point budget is spent, and waiting for the reset "
                    "did not lift the refusal. Run again later: everything fetched so far is "
                    "cached."
                )
            seconds, why = self._wait_for(response, waited)
            if self._on_wait is not None:
                self._on_wait(
                    f"Warcraft Logs refused {_operation_name(query)} with 429 Too Many "
                    f"Requests ({why}); waiting {_spoken(seconds)} before retrying."
                )
            self._sleep(seconds)
            waited += 1
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

        payload_data = cast(dict[str, Any], data)
        # Always taken out, whoever asked for it. `_fetch` hands this payload
        # straight to the cache, where an entry lives for a day or forever, and a
        # counter stored there would be served back as though it were current.
        # Keying the removal on whether we spliced would leave a query that
        # selects the quota itself carrying one.
        block = payload_data.pop("rateLimitData", None)
        self._reading = block if isinstance(block, dict) else None
        self._record_quota(query, block)
        self._remember_quota(block)
        return payload_data

    def _remember_quota(self, block: Any) -> None:
        """Keep a complete reading, with when it arrived, for a later 429 to count from."""
        if not isinstance(block, dict):
            return
        fields = ("pointsSpentThisHour", "limitPerHour", "pointsResetIn")
        if all(isinstance(block.get(field), int | float) for field in fields):
            self._last_quota = (
                float(block["pointsSpentThisHour"]),
                float(block["limitPerHour"]),
                float(block["pointsResetIn"]),
                self._clock(),
            )

    def _record_quota(self, query: str, block: Any) -> None:
        """Note what this query's own quota reading said, if it carried a usable one.

        A missing or malformed block is passed over in silence rather than
        raised: instrumentation must never be the reason a query stops working.
        `rate_limit`, whose whole purpose is the reading, still fails loudly.
        """
        if isinstance(block, dict) and isinstance(block.get("pointsSpentThisHour"), int | float):
            self._costs.record(_operation_name(query), float(block["pointsSpentThisHour"]))

    def rate_limit(self) -> RateLimit:
        # `execute` strips the block out of every payload, so the reading it set
        # aside for this call is where the answer is.
        self.execute(RATE_LIMIT_QUERY)
        data = self._reading
        if data is None:
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
