"""Alert state and webhook for z2g run.

State file: last_run, last_status, consecutive_failures, last_alert_at.
Alerts when: consecutive_failures >= min_failures, rate-limited, and (optionally) within alert hours.
Webhook: POST JSON to Z2G_ALERT_WEBHOOK_URL.

Timezone convention:
  - UTC: State file values (last_run, last_alert_at) are stored as ISO strings in UTC.
  - Z2G_ALERT_TIMEZONE: Alert window (Z2G_ALERT_HOURS_*), rate-limit comparison, and webhook
    payload "last_run" string use this timezone. Set it (e.g. America/Chicago) so the
    alert window and webhook times match your local time; otherwise they default to UTC.

Payload format (for docs and callers):
  Failure: event "z2g_alert"; consecutive_failures, last_error, last_run, message.
  All-clear: event "z2g_all_clear"; last_run, message. Sent when we had previously sent an alert (last_alert_at set) and current local time is inside the alert window (Z2G_ALERT_HOURS_*). Sent on (1) first success inside the window, or (2) first run inside the next window after recovery outside the window (even if that run fails), so the user knows at the start of the day that they don't need to check. Clears last_alert_at so the next failure will trigger an alert. All-clear does not use rate_hours.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import urllib.request

from .config import PROJECT_ROOT, resolve_path


DEFAULT_STATE_FILE = ".z2g-alert-state.json"
DEFAULT_STATUS_FILE = ".z2g-status.json"


def _get_state_path() -> Path:
    raw = os.environ.get("Z2G_ALERT_STATE_FILE")
    if raw:
        return Path(resolve_path(raw))
    return PROJECT_ROOT / DEFAULT_STATE_FILE


def _get_tz():
    tz_name = os.environ.get("Z2G_ALERT_TIMEZONE", "UTC").strip()
    if not tz_name:
        return timezone.utc
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def format_last_run_for_webhook(utc_dt: datetime) -> str:
    """Format UTC datetime as ISO string in Z2G_ALERT_TIMEZONE, truncated to second (for webhook payloads)."""
    tz = _get_tz()
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    local = utc_dt.astimezone(tz).replace(microsecond=0)
    return local.isoformat()


def load_state() -> dict[str, Any]:
    path = _get_state_path()
    if not path.exists():
        return {
            "last_run": None,
            "last_status": "ok",
            "consecutive_failures": 0,
            "last_alert_at": None,
            "last_success": None,
        }
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return {
            "last_run": data.get("last_run"),
            "last_status": data.get("last_status", "ok"),
            "consecutive_failures": int(data.get("consecutive_failures", 0)),
            "last_alert_at": data.get("last_alert_at"),
            "last_success": data.get("last_success"),
        }
    except Exception:
        return {
            "last_run": None,
            "last_success": None,
            "last_status": "ok",
            "consecutive_failures": 0,
            "last_alert_at": None,
        }


def save_state(state: dict[str, Any]) -> None:
    path = _get_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _get_status_path() -> Path | None:
    """Path for the status file (one-line JSON for host scripts). None if Z2G_STATUS_FILE is set to empty."""
    raw = os.environ.get("Z2G_STATUS_FILE", DEFAULT_STATUS_FILE).strip()
    if raw == "":
        return None
    state_dir = _get_state_path().parent
    if raw != DEFAULT_STATUS_FILE:
        return Path(resolve_path(raw))
    return state_dir / DEFAULT_STATUS_FILE


def write_status_file(state: dict[str, Any]) -> None:
    """Write a one-line JSON status file for host scripts/cron (same dir as state by default)."""
    path = _get_status_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_run": state.get("last_run"),
        "last_status": state.get("last_status", "ok"),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "last_alert_at": state.get("last_alert_at"),
        "last_success": state.get("last_success"),
    }
    with open(path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))


def is_inside_alert_window(now: datetime | None = None) -> bool:
    """True if current local time (Z2G_ALERT_TIMEZONE) is inside Z2G_ALERT_HOURS_* window.
    If no window is set, returns True (no restriction). Used for both failure alerts and all-clear."""
    now = now or datetime.now(timezone.utc)
    tz = _get_tz()
    if hasattr(now, "astimezone"):
        now = now.astimezone(tz)
    start_h = (os.environ.get("Z2G_ALERT_HOURS_START") or "").strip().split("#")[0].strip()
    end_h = (os.environ.get("Z2G_ALERT_HOURS_END") or "").strip().split("#")[0].strip()
    if not start_h and not end_h:
        return True
    try:
        start_hour = int(start_h) if start_h else 0
        end_hour = int(end_h) if end_h else 24
        current_hour = now.hour
        if start_hour <= end_hour:
            return start_hour <= current_hour < end_hour
        return current_hour >= start_hour or current_hour < end_hour
    except (ValueError, TypeError):
        return False


def should_alert(state: dict[str, Any], now: datetime | None = None) -> bool:
    """True if we should send an alert: failures >= min, rate limit passed, and current local time inside alert window (if set).
    Alert window: Z2G_ALERT_HOURS_START (inclusive) to Z2G_ALERT_HOURS_END (exclusive). Set both, or only one for open-ended."""
    now = now or datetime.now(timezone.utc)
    tz = _get_tz()
    if hasattr(now, "astimezone"):
        now = now.astimezone(tz)

    min_failures = int(os.environ.get("Z2G_ALERT_MIN_FAILURES", "2"))
    if state.get("consecutive_failures", 0) < min_failures:
        return False

    rate_hours = float(os.environ.get("Z2G_ALERT_RATE_HOURS", "24"))
    last_alert = state.get("last_alert_at")
    if last_alert:
        try:
            last_dt = datetime.fromisoformat(last_alert.replace("Z", "+00:00"))
            if hasattr(last_dt, "astimezone"):
                last_dt = last_dt.astimezone(tz)
            delta_hours = (now - last_dt).total_seconds() / 3600
            if delta_hours < rate_hours:
                return False
        except Exception:
            pass

    if not is_inside_alert_window(now):
        return False

    return True


def build_payload(
    *,
    consecutive_failures: int,
    last_error: str | None,
    last_run: str,
    message: str,
) -> dict[str, Any]:
    return {
        "event": "z2g_alert",
        "consecutive_failures": consecutive_failures,
        "last_error": last_error,
        "last_run": last_run,
        "message": message,
    }


def build_all_clear_payload(*, last_run: str, message: str) -> dict[str, Any]:
    """Payload for first success after failure. Caller should clear last_alert_at so the next failure will alert.
    Includes last_error and consecutive_failures so the same webhook body template works (N/A and 0)."""
    return {
        "event": "z2g_all_clear",
        "last_run": last_run,
        "message": message,
        "last_error": "N/A",
        "consecutive_failures": 0,
    }


def send_webhook(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30)
