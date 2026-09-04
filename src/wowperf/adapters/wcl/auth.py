# ABOUTME: Obtains and caches a Warcraft Logs OAuth token using the client-credentials flow.
# ABOUTME: This flow reads public reports only; private reports need the authorization-code flow.

import time
from collections.abc import Callable

import httpx

TOKEN_URI = "https://www.warcraftlogs.com/oauth/token"
REFRESH_MARGIN_SECONDS = 60


class TokenProvider:
    """Holds one token and renews it shortly before it expires."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: httpx.Client,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self._now = now
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token is not None and self._now() < self._expires_at - REFRESH_MARGIN_SECONDS:
            return self._token

        response = self._http.post(
            TOKEN_URI,
            data={"grant_type": "client_credentials"},
            auth=httpx.BasicAuth(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        payload = response.json()

        self._token = str(payload["access_token"])
        self._expires_at = self._now() + float(payload["expires_in"])
        return self._token
