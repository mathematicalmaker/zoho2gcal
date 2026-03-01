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
RUNS_LOG_FILE = ".z2g-runs.log"
RUNS_LOG_MAX_AGE_HOURS = 48


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


def _get_runs_log_path() -> Path:
    """Path for the append-only run history (timestamp + ok/error per line) for 24h counts."""
    return _get_state_path().parent / RUNS_LOG_FILE


def _parse_iso_to_utc_ts(iso_str: str | None) -> float | None:
    """Parse ISO timestamp to UTC epoch seconds, or None if invalid."""
    if not iso_str:
        return None
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def append_run(timestamp_iso: str, status: str) -> None:
    """Append one run to the history log and prune entries older than RUNS_LOG_MAX_AGE_HOURS."""
    path = _get_runs_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{timestamp_iso}\t{status}\n"
    with open(path, "a") as f:
        f.write(line)
    # Prune old lines so the file doesn't grow unbounded
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - (RUNS_LOG_MAX_AGE_HOURS * 3600)
    try:
        with open(path, "r") as f:
            lines = f.readlines()
        kept = []
        for ln in lines:
            part = ln.strip().split("\t")
            if len(part) >= 2:
                ts = _parse_iso_to_utc_ts(part[0])
                if ts is not None and ts >= cutoff:
                    kept.append(ln)
        if len(kept) < len(lines):
            with open(path, "w") as f:
                f.writelines(kept)
    except Exception:
        pass


def get_24h_counts() -> tuple[int, int]:
    """Return (successes_24h, failures_24h) from the run history log."""
    path = _get_runs_log_path()
    if not path.exists():
        return 0, 0
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - (24 * 3600)
    successes = 0
    failures = 0
    try:
        with open(path, "r") as f:
            for ln in f:
                part = ln.strip().split("\t")
                if len(part) >= 2:
                    ts = _parse_iso_to_utc_ts(part[0])
                    if ts is not None and ts >= cutoff:
                        if part[1].strip().lower() == "ok":
                            successes += 1
                        else:
                            failures += 1
    except Exception:
        pass
    return successes, failures


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
    """Write a one-line JSON status file: current health + successes/failures in past 24h (for host scripts without docker logs jq)."""
    path = _get_status_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    successes_24h, failures_24h = get_24h_counts()
    last_success = state.get("last_success")
    now_ts = datetime.now(timezone.utc).timestamp()
    last_success_ts = _parse_iso_to_utc_ts(last_success) if last_success else None
    time_since_last_success_seconds: float | None = (now_ts - last_success_ts) if last_success_ts is not None else None
    payload = {
        "last_run": state.get("last_run"),
        "last_status": state.get("last_status", "ok"),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "last_alert_at": state.get("last_alert_at"),
        "last_success": last_success,
        "successes_24h": successes_24h,
        "failures_24h": failures_24h,
        "time_since_last_success_seconds": round(time_since_last_success_seconds, 1) if time_since_last_success_seconds is not None else None,
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
