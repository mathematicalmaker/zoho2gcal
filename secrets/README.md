# Secrets directory

This directory holds credentials and tokens. **Do not commit real values to Git.**

| File | Description |
|------|-------------|
| **private.env** | Zoho and Google credentials: `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, `ZOHO_CALENDAR_UID`, `GOOGLE_CALENDAR_ID`. Loaded after the project `.env`. |
| **private.env.example** | Template for `private.env`; copy to `private.env` and fill in values. |
| **google_client_secret.json** | OAuth client credentials from Google Cloud Console (APIs & Services → Credentials → your Desktop client → Download JSON). You add this file once during setup. |
| **google_token.json** | OAuth access/refresh token written by `z2g google-auth`. Created when you complete the Google OAuth flow; do not edit by hand. |
