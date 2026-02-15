"""Diff/normalize logic for dry-run and patch decisions.

Compares existing Google events to desired bodies; used for sync/run dry-run output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any, Dict, List

from dateutil import parser as dtparser


@dataclass(frozen=True)
class Diff:
    field: str
    old: str
    new: str


def _norm_rfc3339_instant(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    dt = dtparser.parse(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reminders_signature(reminders: Dict[str, Any]) -> str:
    """
    Normalize a Google Calendar 'reminders' dict to a single comparable string
    so diff output shows the full picture (default vs overrides).
    """
    reminders = reminders or {}
    if reminders.get("useDefault") is True:
        return "default"
    overrides = reminders.get("overrides") or []
    if not overrides:
        return "default"
    parts = []
    for o in overrides:
        m = (o.get("method") or "").strip().lower()
        mins = o.get("minutes")
        if m and mins is not None:
            parts.append(f"{m}:{int(mins)}")
    parts.sort()
    return ",".join(parts)


def _normalize_google_event_for_compare(ev: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract/normalize the Google event fields we control.
    Keep it conservative: only compare what we set in build_google_mirror_event().
    """
    start = ev.get("start") or {}
    end = ev.get("end") or {}

    def norm_when(x: Dict[str, Any]) -> str:
        dtv = x.get("dateTime")
        if dtv:
            return _norm_rfc3339_instant(str(dtv))
        return str(x.get("date") or "")

    reminders = ev.get("reminders") or {}

    return {
        "summary": str(ev.get("summary") or ""),
        "location": str(ev.get("location") or ""),
        "description": str(ev.get("description") or ""),
        "start": norm_when(start),
        "end": norm_when(end),
        "visibility": str(ev.get("visibility") or ""),
        "transparency": str(ev.get("transparency") or "opaque"),
        "iCalUID": str(ev.get("iCalUID") or ""),
        "reminders": _reminders_signature(reminders),
    }


def diff_events(existing: Dict[str, Any], desired: Dict[str, Any]) -> List[Diff]:
    """
    Compare existing Google event vs desired body and return diffs.
    Only compares the normalized field set from _normalize_google_event_for_compare().
    """
    a = _normalize_google_event_for_compare(existing)
    b = _normalize_google_event_for_compare(desired)

    diffs: List[Diff] = []
    for k in sorted(set(a.keys()) | set(b.keys())):
        av = a.get(k, "")
        bv = b.get(k, "")
        if av != bv:
            diffs.append(Diff(field=k, old=av, new=bv))
    return diffs


def fmt_diff(d: Diff, *, maxlen: int = 160) -> str:
    def clip(x: str) -> str:
        x = x.replace("\n", "\\n")
        return x if len(x) <= maxlen else (x[: maxlen - 3] + "...")
    return f"  - {d.field}: {clip(d.old)}  ->  {clip(d.new)}"
