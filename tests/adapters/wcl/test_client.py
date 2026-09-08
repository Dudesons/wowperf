# ABOUTME: Behaviour tests for the GraphQL transport: auth header, error surfacing, quota reads.
# ABOUTME: Routes on request path so the real TokenProvider participates rather than a stub.

import httpx
import pytest

from wowperf.adapters.wcl.auth import TokenProvider
from wowperf.adapters.wcl.client import RateLimitExceeded, WclClient
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


def test_an_exhausted_point_budget_raises_a_named_error() -> None:
    client = build_client(httpx.Response(429, text="Too Many Requests"))
    with pytest.raises(RateLimitExceeded):
        client.execute("query { hello }")


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
