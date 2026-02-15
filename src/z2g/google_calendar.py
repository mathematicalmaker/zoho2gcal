"""Google Calendar API client.

Uses token JSON from google-auth flow. Credentials auto-refresh via refresh_token.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, List, Sequence

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Must match scopes used at auth time (calendar.events + calendarlist.readonly)
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
)


class GoogleCalendarClient:
    """Thin wrapper around Google Calendar API v3 for list/find/upsert/delete events."""

    def __init__(self, token_json_path: str, scopes: Sequence[str] = DEFAULT_SCOPES) -> None:
        self.scopes = list(scopes)
        creds = Credentials.from_authorized_user_file(token_json_path, self.scopes)
        self.svc = build("calendar", "v3", credentials=creds, cache_discovery=False)

    def list_calendars(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        page_token = None
        while True:
            resp = self.svc.calendarList().list(pageToken=page_token).execute()
            items.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return items

    def find_by_icaluid(self, calendar_id: str, icaluid: str) -> Optional[Dict[str, Any]]:
        resp = self.svc.events().list(calendarId=calendar_id, iCalUID=icaluid, maxResults=5).execute()
        items: List[Dict[str, Any]] = resp.get("items", [])
        return items[0] if items else None

    def upsert(self, calendar_id: str, existing_event_id: Optional[str], body: Dict[str, Any]) -> Dict[str, Any]:
        if existing_event_id:
            return self.svc.events().patch(calendarId=calendar_id, eventId=existing_event_id, body=body).execute()
        return self.svc.events().insert(calendarId=calendar_id, body=body).execute()

    def list_events_in_range(
        self,
        calendar_id: str,
        time_min: str,
        time_max: str,
        *,
        single_events: bool = True,
    ) -> List[Dict[str, Any]]:
        """List events in the given time range (time_min/time_max in RFC3339)."""
        items: List[Dict[str, Any]] = []
        page_token = None
        while True:
            resp = (
                self.svc.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=single_events,
                    pageToken=page_token,
                )
                .execute()
            )
            items.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return items

    def delete(self, calendar_id: str, event_id: str) -> None:
        """Delete an event by ID."""
        self.svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()

