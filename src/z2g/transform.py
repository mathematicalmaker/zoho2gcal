"""Transform Zoho Calendar events into Google Calendar event bodies.

Maps Zoho API payloads to Google Calendar API format. No attendees (avoids RSVP).
Supports timed and all-day events. Uses extendedProperties for mirror identification.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Tuple, List

from dateutil import parser as dtparser

# Human-visible marker so you can eyeball mirrored events and bulk-cleanup if needed.
MIRROR_MARKER = "X-ZOHO-MIRROR:1"


def iso_z(dt: datetime) -> str:
    """UTC ISO-8601 like 2026-02-11T20:36:57Z (no microseconds)."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def zoho_uid(ev: Dict[str, Any]) -> str:
    """
    Return the best available stable UID for the event.

    For Zoho list-events/byinstance payload, 'uid' is typically the iCalendar UID
    (often something like ...@google.com for externally-created events).
    """
    for k in ("uid", "event_uid", "eventUid", "icaluid", "iCalUID", "id", "event_id", "eventId"):
        v = ev.get(k)
        if v:
            return str(v)
    raise KeyError(f"No Zoho UID field found. Keys: {sorted(ev.keys())}")


def zoho_times(ev: Dict[str, Any]) -> Tuple[datetime, datetime]:
    """
    Extract start/end datetimes from Zoho event payloads.

    Common Zoho list-events/byinstance payload:
      ev["dateandtime"]["start"] = "20260211T140000-0600"
      ev["dateandtime"]["end"]   = "20260211T141500-0600"
    """
    dt = ev.get("dateandtime") or {}
    start_raw = dt.get("start")
    end_raw = dt.get("end")

    # Fallbacks (other Zoho payload variants)
    if not start_raw:
        start_raw = ev.get("start_datetime") or ev.get("start") or ev.get("from") or ev.get("startTime")
    if not end_raw:
        end_raw = ev.get("end_datetime") or ev.get("end") or ev.get("to") or ev.get("endTime")

    if not start_raw or not end_raw:
        raise KeyError(f"Missing start/end. Keys: {sorted(ev.keys())}")

    s = dtparser.parse(str(start_raw))
    e = dtparser.parse(str(end_raw))
    if s.tzinfo is None:
        s = s.replace(tzinfo=timezone.utc)
    if e.tzinfo is None:
        e = e.replace(tzinfo=timezone.utc)
    return s, e


def is_zoho_allday(ev: Dict[str, Any]) -> bool:
    """
    Return True if the Zoho event is all-day.

    Zoho API uses "isallday": true in the event object. We also check
    is_all_day / allDay and infer from date-only start/end (yyyyMMdd, no "T").
    """
    for k in ("isallday", "is_all_day", "allDay", "isAllDay"):
        v = ev.get(k)
        if v is True or (isinstance(v, str) and str(v).strip().lower() in ("true", "1", "yes")):
            return True
    dt = ev.get("dateandtime") or {}
    start_raw = dt.get("start") or ev.get("start") or ev.get("start_datetime") or ""
    start_s = str(start_raw).strip()
    # Date-only format yyyyMMdd (8 chars, no "T") implies all-day
    if len(start_s) == 8 and start_s.isdigit() and "T" not in start_s:
        return True
    return False


def _date_iso(d: date) -> str:
    """Format date as YYYY-MM-DD for Google Calendar API."""
    return d.isoformat()


def parse_google_reminders(spec: str) -> Dict[str, Any]:
    """
    Parse reminder spec like:
      "default"
      "popup:10"
      "popup:10,email:30"
    Returns a Google Calendar API 'reminders' object.
    """
    s = (spec or "").strip().lower()
    if not s or s == "default":
        return {"useDefault": True}

    overrides: List[Dict[str, Any]] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            method, minutes_s = part.split(":", 1)
            method = method.strip()
            minutes = int(minutes_s.strip())
        except ValueError:
            raise ValueError(f"Bad GOOGLE_REMINDERS entry: {part!r} (expected method:minutes)")

        if method not in {"popup", "email"}:
            raise ValueError(f"Bad reminder method: {method!r} (use popup or email)")

        overrides.append({"method": method, "minutes": minutes})

    if not overrides:
        return {"useDefault": True}

    return {"useDefault": False, "overrides": overrides}

def build_google_mirror_event(
        ev: Dict[str, Any],
        *, 
        title_mode: str,
        icaluid_suffix: str,
        reminders: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build a Google Calendar event body that is informational-only:
      - no attendees field (avoids RSVP workflow)
      - stable iCalUID for idempotent upserts
      - includes a human-visible MIRROR_MARKER and Zoho UID breadcrumb
      - duplicates join URL into description for usability
    """
    uid = zoho_uid(ev)
    s, e = zoho_times(ev)
    allday = is_zoho_allday(ev)

    # Title
    raw_title = str(ev.get("title") or ev.get("name") or "Busy").strip()
    title = "Busy" if title_mode.lower() == "busy" else (raw_title or "Busy")

    # Location / join link
    location = str(ev.get("location") or ev.get("venue") or "").strip()

    # Base description from whatever Zoho gives (often blank in instance lists)
    desc = str(ev.get("description") or ev.get("desc") or ev.get("notes") or "").strip()

    # Suggestion: put the join link up top for quick access in Google UI/mobile
    if location and "Join:" not in desc:
        desc = (f"Join: {location}\n\n" + desc) if desc else f"Join: {location}"

    # Keep the marker concept (human-visible + simple filtering)
    if MIRROR_MARKER not in desc:
        desc = (desc + "\n\n" if desc else "") + MIRROR_MARKER

    # Add a breadcrumb back to the source UID
    desc = desc + f"\nX-ZOHO-UID:{uid}"

    # iCalUID strategy:
    # - If Zoho's UID already includes a domain (e.g. ...@google.com), keep it verbatim.
    # - Otherwise append a suffix to make it look like a proper RFC5545 UID.
    icaluid = uid if "@" in uid else f"{uid}@{icaluid_suffix}"

    # Google: timed events use start/end.dateTime (RFC3339); all-day use start/end.date (YYYY-MM-DD), end exclusive
    if allday:
        start_date = s.date()
        end_date = e.date() + timedelta(days=1)  # Google end is exclusive
        start_payload: Dict[str, str] = {"date": _date_iso(start_date)}
        end_payload: Dict[str, str] = {"date": _date_iso(end_date)}
    else:
        start_payload = {"dateTime": iso_z(s)}
        end_payload = {"dateTime": iso_z(e)}

    body: Dict[str, Any] = {
        "summary": title,
        "location": location,
        "description": desc,
        "start": start_payload,
        "end": end_payload,
        "visibility": "private",
        "transparency": "opaque",
        # IMPORTANT: omit 'attendees' entirely to avoid RSVP behavior
        "iCalUID": icaluid,
        "reminders": reminders or {"useDefault": True},
        "extendedProperties": {
            "private": {
                "zoho_uid": uid,
                "zoho_mirror": "1",
            }
        },
    }
    return body

