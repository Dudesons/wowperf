# ABOUTME: Obtains and caches a Warcraft Logs OAuth token using the client-credentials flow.
# ABOUTME: This flow reads public reports only; private reports need the authorization-code flow.

import time
from collections.abc import Callable

import httpx

from wowperf.adapters.wcl.errors import WclError

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

        missing = [field for field in ("access_token", "expires_in") if field not in payload]
        if missing:
            # Assigned only once both fields are in hand, so a malformed response
            # leaves any still-valid cached token and its expiry untouched.
            raise WclError(
                f"The Warcraft Logs token response is missing {', '.join(missing)}"
            )

        access_token = str(payload["access_token"])
        expires_at = self._now() + float(payload["expires_in"])
        self._token, self._expires_at = access_token, expires_at
        return self._token
