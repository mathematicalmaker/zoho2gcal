"""Time/date parsing and sync window computation.

Supports ISO, date-only, and relative offsets (e.g. +7d, -12h) for --since/--until.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from dateutil import parser as dtparser

_REL_UNITS = {
    "s": ("seconds", 1),
    "m": ("minutes", 1),
    "h": ("hours", 1),
    "d": ("days", 1),
    "w": ("weeks", 1),
}


def parse_when(s: str) -> datetime:
    """
    Parse a datetime from:
      - ISO strings (with or without timezone)
      - date-only "YYYY-MM-DD"
      - relative offsets: "+7d", "-12h", "+30m", "-1w"

    If parsed datetime has no tzinfo, we assume UTC.
    """
    s = (s or "").strip()
    if not s:
        raise ValueError("empty time string")

    # Relative offset
    if (s[0] in {"+", "-"}) and len(s) >= 3:
        sign = 1 if s[0] == "+" else -1
        num_part = s[1:-1]
        unit = s[-1].lower()
        if unit in _REL_UNITS and num_part.isdigit():
            n = int(num_part) * sign
            kw_name, _ = _REL_UNITS[unit]
            return datetime.now(timezone.utc) + timedelta(**{kw_name: n})

    # Absolute parse
    dt = dtparser.parse(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_window(
    since: Optional[str],
    until: Optional[str],
    *,
    lookback_days_env: str,
    lookahead_days_env: str,
) -> Tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)

    if since:
        start = parse_when(since)
    else:
        start = now - timedelta(days=int(os.environ.get(lookback_days_env, "7")))

    if until:
        end = parse_when(until)
    else:
        end = now + timedelta(days=int(os.environ.get(lookahead_days_env, "30")))

    if end <= start:
        raise ValueError(f"--until must be after --since (got {start.isoformat()} -> {end.isoformat()})")

    return start, end
