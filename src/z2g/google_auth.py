"""Google OAuth 2.0 flow for Calendar API.

Supports two modes:
- Local server: run_local_server() starts a callback server (needs port access).
- Manual: prints auth URL, waits for user to paste redirect URL back (no server).
  Use --manual for SSH, Docker, or headless. Add http://localhost to GCP redirect URIs.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from google_auth_oauthlib.flow import InstalledAppFlow

# Least privilege: event read/write + calendar list (for list-google-calendars / GOOGLE_CALENDAR_ID)
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
)

# Fixed redirect for manual flow: user pastes http://localhost/?code=... back. No server needed.
MANUAL_REDIRECT_URI = "http://localhost"


def authorize(
    client_secret_json: str,
    token_json_out: str,
    scopes: Sequence[str] = DEFAULT_SCOPES,
    *,
    manual: bool = False,
) -> str:
    """
    OAuth flow for Google Calendar.

    If manual=True: prints the auth URL, waits for the user to paste the redirect
    URL in this same terminal. No local server, no port mapping. For SSH, Docker, headless.

    If manual=False: uses a local server (run_local_server). Requires port access for the callback.
    """
    out = Path(token_json_out)
    out.parent.mkdir(parents=True, exist_ok=True)

    flow_kwargs: dict = {}
    if manual:
        flow_kwargs["redirect_uri"] = MANUAL_REDIRECT_URI

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret_json,
        scopes=list(scopes),
        **flow_kwargs,
    )

    if manual:
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
        print("Visit this URL in any browser (phone, another PC, etc.):")
        print()
        print(auth_url)
        print()
        print(
            "After authorizing, you'll be redirected to localhost. Copy the *entire* URL "
            "from the address bar (it may show an error page—that's OK) and paste it below."
        )
        response = input("\nPaste the redirect URL here: ").strip()
        if not response:
            raise SystemExit("No URL pasted. Exiting.")
        # oauthlib blocks http:// redirects by default; allow for localhost paste-back
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        flow.fetch_token(authorization_response=response)
        creds = flow.credentials
    else:
        creds = flow.run_local_server(
            host="localhost",
            port=0,
            open_browser=False,
            authorization_prompt_message="Please visit this URL to authorize: {url}",
            success_message="Authorization complete. You may close this window.",
        )

    out.write_text(creds.to_json(), encoding="utf-8")
    return str(out)

