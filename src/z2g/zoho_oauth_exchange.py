"""One-time exchange: Zoho auth code → refresh_token.

Run during setup; output ZOHO_REFRESH_TOKEN goes into .env.
"""
from __future__ import annotations

from typing import Any, Dict

import requests


def exchange_code_for_tokens(
    *,
    accounts_host: str,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://localhost",
) -> Dict[str, Any]:
    url = accounts_host.rstrip("/") + "/oauth/v2/token"
    r = requests.post(
        url,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
