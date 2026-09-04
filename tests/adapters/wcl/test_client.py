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


def test_an_exhausted_point_budget_raises_a_named_error() -> None:
    client = build_client(httpx.Response(429, text="Too Many Requests"))
    with pytest.raises(RateLimitExceeded):
        client.execute("query { hello }")


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
