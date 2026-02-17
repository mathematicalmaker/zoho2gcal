# Secrets directory

This directory holds the Google OAuth JSON files. **Do not commit them to Git.**

| File | Description |
|------|-------------|
| **google_client_secret.json** | OAuth client credentials from Google Cloud Console (APIs & Services → Credentials → your Desktop client → Download JSON). You add this file once during setup. |
| **google_token.json** | OAuth access/refresh token written by `z2g google-auth`. Created when you complete the Google OAuth flow; do not edit by hand. |

All other configuration (Zoho credentials, calendar IDs, paths, etc.) goes in the project `.env` file.
