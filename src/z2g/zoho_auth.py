"""Zoho OAuth: refresh_token → access_token.

Caches access token until near expiry; refreshes automatically for API calls.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests


@dataclass
class AccessToken:
    token: str
    expires_at: float  # epoch seconds

class ZohoOAuth:
    """Exchanges Zoho refresh token for short-lived access tokens."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, accounts_host: str = "https://accounts.zoho.com") -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.accounts_host = accounts_host.rstrip("/")
        self._cached: AccessToken | None = None

    def get_access_token(self) -> str:
        if self._cached and time.time() < self._cached.expires_at:
            return self._cached.token

        url = f"{self.accounts_host}/oauth/v2/token"
        r = requests.post(
            url,
            data={
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in_sec", data.get("expires_in", 3600)))
        self._cached = AccessToken(token=token, expires_at=time.time() + expires_in - 60)
        return token

