# ABOUTME: Behaviour tests for the OAuth client-credentials token provider.
# ABOUTME: Asserts the request we build and that a valid token is reused, not refetched.

import base64

import httpx
import pytest

from wowperf.adapters.wcl.auth import TokenProvider


def test_the_token_request_uses_basic_auth_and_the_client_credentials_grant() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider("id", "secret", http)

    assert provider.token() == "abc"
    assert seen["url"] == "https://www.warcraftlogs.com/oauth/token"
    assert seen["authorization"] == "Basic " + base64.b64encode(b"id:secret").decode()
    assert "grant_type=client_credentials" in seen["body"]


def test_a_valid_token_is_reused_and_refetched_only_near_expiry() -> None:
    issued: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        issued.append(f"t{len(issued) + 1}")
        return httpx.Response(200, json={"access_token": issued[-1], "expires_in": 3600})

    clock = {"now": 0.0}
    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider("id", "secret", http, now=lambda: clock["now"])

    assert provider.token() == "t1"

    clock["now"] = 3000.0
    assert provider.token() == "t1"

    clock["now"] = 3550.0  # inside the 60-second refresh margin
    assert provider.token() == "t2"
    assert len(issued) == 2


def test_a_non_200_token_response_leaves_a_valid_cached_token_intact() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, json={"access_token": "old-token", "expires_in": 3600})
        return httpx.Response(500, json={"error": "server_error"})

    clock = {"now": 0.0}
    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider("id", "secret", http, now=lambda: clock["now"])

    assert provider.token() == "old-token"

    clock["now"] = 3550.0  # inside the refresh margin, forces a refetch attempt
    with pytest.raises(httpx.HTTPStatusError):
        provider.token()

    clock["now"] = 100.0  # back inside the original token's valid window
    assert provider.token() == "old-token"
    assert calls["count"] == 2  # the third call was served from cache, not the network


def test_a_200_response_missing_expires_in_does_not_corrupt_a_valid_cached_token() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, json={"access_token": "old-token", "expires_in": 3600})
        return httpx.Response(200, json={"access_token": "new-token"})

    clock = {"now": 0.0}
    http = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider("id", "secret", http, now=lambda: clock["now"])

    assert provider.token() == "old-token"

    clock["now"] = 3550.0  # inside the refresh margin, forces a refetch attempt
    with pytest.raises(KeyError):
        provider.token()

    clock["now"] = 100.0  # back inside the original token's valid window
    assert provider.token() == "old-token"
    assert calls["count"] == 2  # the third call was served from cache, not the network
