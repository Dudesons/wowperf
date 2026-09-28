# ABOUTME: Behaviour tests for the GraphQL transport: auth header, error surfacing, quota reads.
# ABOUTME: Routes on request path so the real TokenProvider participates rather than a stub.

import httpx
import pytest

from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import (
    BURST_BACKOFF_SECONDS,
    CYCLE_SECONDS,
    MAX_WAITS,
    MIN_WAIT_SECONDS,
    RESET_MARGIN_SECONDS,
    RateLimitExceeded,
    WclClient,
)
from wowperf.adapters.wcl.errors import WclError


def build_client(graphql: httpx.Response) -> WclClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        return graphql

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return WclClient(TokenProvider("id", "secret", http), http)


def test_a_query_carries_the_bearer_token_and_returns_the_data_block() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        seen["authorization"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"hello": "world"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(TokenProvider("id", "secret", http), http)

    assert client.execute("query { hello }") == {"hello": "world"}
    assert seen["authorization"] == "Bearer abc"
    assert seen["url"] == "https://www.warcraftlogs.com/api/v2/client"


def test_graphql_errors_are_raised_with_their_messages() -> None:
    client = build_client(
        httpx.Response(200, json={"errors": [{"message": "Cannot query field dungeonPulls"}]})
    )
    with pytest.raises(WclError, match="Cannot query field dungeonPulls"):
        client.execute("query { bad }")


def test_a_200_response_with_neither_data_nor_errors_raises_a_wcl_error() -> None:
    client = build_client(httpx.Response(200, json={"extensions": {}}))
    with pytest.raises(WclError, match="neither 'data' nor 'errors'"):
        client.execute("query { hello }")


def test_a_null_data_block_raises_a_named_wcl_error() -> None:
    """{"data": null} is a real response shape, not only a null nested report.

    Casting it to a dict used to hand every caller a `None` they had no reason
    to expect, since the return type is annotated `dict[str, Any]`. Two call
    sites had no guard against it at all: the rate-limit reader in this module,
    and `rankings_block` in `ranking_repository.py` — both would raise a raw
    `AttributeError`, which is not in `analyze`'s caught exception tuple, and
    crash the CLI after the run had already been fetched and analysed.
    """
    client = build_client(httpx.Response(200, json={"data": None}))
    with pytest.raises(WclError, match="null 'data' block"):
        client.execute("query AuraTable($code: String!) { hello }", {"code": "abc123"})


def test_a_null_data_block_names_the_query_and_report_it_happened_on() -> None:
    client = build_client(httpx.Response(200, json={"data": None}))
    with pytest.raises(WclError, match="AuraTable") as exc_info:
        client.execute("query AuraTable($code: String!) { hello }", {"code": "abc123"})
    assert "abc123" in str(exc_info.value)


def test_a_null_data_block_on_the_rate_limit_query_raises_a_named_error() -> None:
    """The rate-limit reader had no guard of its own against a null `data` block:
    `self.execute(RATE_LIMIT_QUERY).get("rateLimitData")` would raise a raw
    `AttributeError` on `None`. Guarding in `execute` fixes this call site too."""
    client = build_client(httpx.Response(200, json={"data": None}))
    with pytest.raises(WclError, match="null 'data' block"):
        client.rate_limit()


def test_an_exhausted_point_budget_raises_a_named_error_once_the_waits_are_spent() -> None:
    slept: list[float] = []
    client, _ = scripted_client([httpx.Response(429, text="Too Many Requests")] * 3, slept)
    with pytest.raises(RateLimitExceeded):
        client.execute("query { hello }")
    assert len(slept) == MAX_WAITS


class FakeClock:
    """A monotonic clock a test moves by hand; every sleep advances it too."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def quota(spent: float, reset_in: int, limit: int = 3600) -> httpx.Response:
    """A 200 whose only content is its own quota reading."""
    return httpx.Response(
        200,
        json={
            "data": {
                "rateLimitData": {
                    "limitPerHour": limit,
                    "pointsSpentThisHour": spent,
                    "pointsResetIn": reset_in,
                }
            }
        },
    )


HELLO = httpx.Response(200, json={"data": {"hello": "world"}})


def scripted_client(
    responses: list[httpx.Response],
    slept: list[float],
    *,
    clock: FakeClock | None = None,
    said: list[str] | None = None,
) -> tuple[WclClient, FakeClock]:
    """A client answering each GraphQL request with the next scripted response."""
    queue = list(responses)
    ticking = clock if clock is not None else FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 86400})
        return queue.pop(0)

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        ticking.now += seconds

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = WclClient(
        TokenProvider("id", "secret", http),
        http,
        sleep=sleep,
        clock=ticking,
        on_wait=said.append if said is not None else None,
    )
    return client, ticking


def test_a_retry_after_header_is_waited_out_and_the_query_retried() -> None:
    slept: list[float] = []
    said: list[str] = []
    client, _ = scripted_client(
        [httpx.Response(429, headers={"Retry-After": "7"}), HELLO], slept, said=said
    )

    assert client.execute("query Hello { hello }") == {"hello": "world"}
    assert slept == [7.0]
    assert len(said) == 1
    assert "waiting 7 s" in said[0]
    assert "Hello" in said[0]


def test_a_spent_budget_waits_until_the_reset_the_last_reading_named() -> None:
    """The reading said 600 s to the reset; 100 s have passed since it was taken."""
    slept: list[float] = []
    clock = FakeClock()
    client, _ = scripted_client(
        [quota(3600.0, 600), httpx.Response(429), HELLO], slept, clock=clock
    )
    client.rate_limit()
    clock.now += 100.0

    assert client.execute("query { hello }") == {"hello": "world"}
    assert slept == [600.0 - 100.0 + RESET_MARGIN_SECONDS]


def test_a_refusal_with_budget_left_backs_off_briefly_before_waiting_for_the_reset() -> None:
    """Points remained, so the refusal is not the hourly budget as far as the
    reading knows: a short back-off first, and the reset only if that fails."""
    slept: list[float] = []
    client, _ = scripted_client(
        [quota(100.0, 600), httpx.Response(429), httpx.Response(429), HELLO], slept
    )
    client.rate_limit()

    assert client.execute("query { hello }") == {"hello": "world"}
    assert slept == [BURST_BACKOFF_SECONDS, 600.0 - BURST_BACKOFF_SECONDS + RESET_MARGIN_SECONDS]


def test_a_reading_older_than_its_own_reset_counts_to_the_next_cycle() -> None:
    """The budget resets on a fixed hourly cycle, so a reset already past means
    the next one is a whole cycle after it."""
    slept: list[float] = []
    clock = FakeClock()
    client, _ = scripted_client(
        [quota(3600.0, 600), httpx.Response(429), HELLO], slept, clock=clock
    )
    client.rate_limit()
    clock.now += 700.0

    client.execute("query { hello }")
    assert slept == [(600.0 - 700.0) % CYCLE_SECONDS + RESET_MARGIN_SECONDS]


def test_with_no_reading_and_no_header_the_second_wait_is_one_whole_cycle() -> None:
    slept: list[float] = []
    client, _ = scripted_client([httpx.Response(429), httpx.Response(429), HELLO], slept)

    client.execute("query { hello }")
    assert slept == [BURST_BACKOFF_SECONDS, CYCLE_SECONDS + RESET_MARGIN_SECONDS]


def test_no_wait_is_longer_than_one_cycle_whatever_the_header_says() -> None:
    slept: list[float] = []
    client, _ = scripted_client(
        [httpx.Response(429, headers={"Retry-After": "999999"}), HELLO], slept
    )

    client.execute("query { hello }")
    assert slept == [CYCLE_SECONDS + RESET_MARGIN_SECONDS]


def test_a_retry_after_date_already_past_waits_the_shortest_wait() -> None:
    slept: list[float] = []
    client, _ = scripted_client(
        [httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}), HELLO],
        slept,
    )

    client.execute("query { hello }")
    assert slept == [MIN_WAIT_SECONDS]


def test_an_unreadable_retry_after_falls_back_to_the_reading() -> None:
    slept: list[float] = []
    client, _ = scripted_client(
        [quota(3600.0, 600), httpx.Response(429, headers={"Retry-After": "soon"}), HELLO], slept
    )
    client.rate_limit()

    client.execute("query { hello }")
    assert slept == [600.0 + RESET_MARGIN_SECONDS]


def test_a_rate_limit_response_missing_ratelimitdata_names_the_missing_field() -> None:
    client = build_client(httpx.Response(200, json={"data": {}}))
    with pytest.raises(WclError, match="rateLimitData"):
        client.rate_limit()


def test_the_rate_limit_is_read_from_the_api_not_assumed() -> None:
    client = build_client(
        httpx.Response(
            200,
            json={
                "data": {
                    "rateLimitData": {
                        "limitPerHour": 3600,
                        "pointsSpentThisHour": 12.5,
                        "pointsResetIn": 900,
                    }
                }
            },
        )
    )
    limit = client.rate_limit()
    assert (limit.limit_per_hour, limit.points_spent_this_hour, limit.points_reset_in) == (
        3600,
        12.5,
        900,
    )


def _capturing_client(payload: dict[str, object]) -> tuple[WclClient, dict[str, str]]:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json=payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return WclClient(TokenProvider("id", "secret", http), http), seen


QUOTA = {"limitPerHour": 3600, "pointsSpentThisHour": 8.01, "pointsResetIn": 900}


def test_a_query_goes_out_carrying_the_quota_block() -> None:
    client, seen = _capturing_client({"data": {"rateLimitData": QUOTA, "hello": "world"}})

    client.execute("query Hello { hello }")

    assert "rateLimitData" in seen["body"]


def test_the_quota_block_never_reaches_the_caller_and_so_never_reaches_the_cache() -> None:
    """`_fetch` hands this payload straight to DiskCache, which keeps it for a day
    or forever. A block left in would freeze an hour-old counter into the entry."""
    client, _ = _capturing_client({"data": {"rateLimitData": QUOTA, "hello": "world"}})

    assert client.execute("query Hello { hello }") == {"hello": "world"}


def test_the_reading_is_recorded_against_the_operation_that_carried_it() -> None:
    client, _ = _capturing_client({"data": {"rateLimitData": QUOTA, "hello": "world"}})

    client.execute("query Hello { hello }")

    assert client.costs.pending() == "Hello"


def test_a_response_without_a_quota_block_records_nothing_and_is_returned_intact() -> None:
    """Instrumentation must never be the reason a query stops working."""
    client, _ = _capturing_client({"data": {"hello": "world"}})

    assert client.execute("query Hello { hello }") == {"hello": "world"}
    assert client.costs.pending() is None


def test_reading_the_quota_directly_still_returns_it_and_also_records_it() -> None:
    client, _ = _capturing_client({"data": {"rateLimitData": QUOTA}})

    reading = client.rate_limit()

    assert reading.points_spent_this_hour == 8.01
    assert client.costs.pending() == "RateLimit"


def test_a_quota_block_we_did_not_add_is_kept_out_of_the_payload_all_the_same() -> None:
    """The response decides what is stripped, never the request.

    A query selecting the quota itself is left unspliced. If the strip were keyed
    on whether we spliced, such a query would keep its counter, and routing it
    through the cache would freeze that counter into an entry living for a day or
    forever — the one outcome this whole mechanism exists to avoid.
    """
    client, _ = _capturing_client({"data": {"rateLimitData": QUOTA, "hello": "world"}})

    payload = client.execute("query Hello { rateLimitData { limitPerHour } hello }")

    assert payload == {"hello": "world"}
    assert client.costs.pending() == "Hello"
