"""Alert state and webhook for z2g run.

State file: last_run, last_status, consecutive_failures, last_alert_at.
Alerts when: consecutive_failures >= min_failures, rate-limited, and (optionally) within alert hours.
Webhook: POST JSON to Z2G_ALERT_WEBHOOK_URL.

Payload format (for docs and callers):
  event: "z2g_alert"
  consecutive_failures: int
  last_error: str | null
  last_run: str (ISO datetime)
  message: str (human-readable)
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


def load_state() -> dict[str, Any]:
    path = _get_state_path()
    if not path.exists():
        return {
            "last_run": None,
            "last_status": "ok",
            "consecutive_failures": 0,
            "last_alert_at": None,
        }
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return {
            "last_run": data.get("last_run"),
            "last_status": data.get("last_status", "ok"),
            "consecutive_failures": int(data.get("consecutive_failures", 0)),
            "last_alert_at": data.get("last_alert_at"),
        }
    except Exception:
        return {
            "last_run": None,
            "last_status": "ok",
            "consecutive_failures": 0,
            "last_alert_at": None,
        }


def save_state(state: dict[str, Any]) -> None:
    path = _get_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def should_alert(state: dict[str, Any], now: datetime | None = None) -> bool:
    """True if we should send an alert: failures >= min, rate limit passed, and within alert hours (if set)."""
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

    start_h = os.environ.get("Z2G_ALERT_HOURS_START")
    end_h = os.environ.get("Z2G_ALERT_HOURS_END")
    if start_h is not None and start_h.strip() != "" and end_h is not None and end_h.strip() != "":
        try:
            start_hour = int(start_h.strip())
            end_hour = int(end_h.strip())
            current_hour = now.hour
            if start_hour <= end_hour:
                if current_hour < start_hour or current_hour >= end_hour:
                    return False
            else:
                if current_hour >= end_hour and current_hour < start_hour:
                    return False
        except Exception:
            pass

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


def send_webhook(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30)
