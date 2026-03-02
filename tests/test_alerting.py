"""Unit tests for z2g.alerting."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from z2g import alerting


def test_build_payload():
    p = alerting.build_payload(
        consecutive_failures=2,
        last_error="Missing env var: X",
        last_run="2026-02-13T14:00:00+00:00",
        message="z2g run failed 2 time(s): Missing env var: X",
    )
    assert p["event"] == "z2g_alert"
    assert p["consecutive_failures"] == 2
    assert p["last_error"] == "Missing env var: X"
    assert p["last_run"] == "2026-02-13T14:00:00+00:00"
    assert p["message"] == "z2g run failed 2 time(s): Missing env var: X"


def test_build_payload_null_error():
    p = alerting.build_payload(
        consecutive_failures=1,
        last_error=None,
        last_run="2026-02-13T14:00:00+00:00",
        message="fail",
    )
    assert p["last_error"] is None


def test_build_all_clear_payload():
    p = alerting.build_all_clear_payload(
        last_run="2026-02-13T15:00:00+00:00",
        message="z2g run succeeded after previous failure(s).",
    )
    assert p["event"] == "z2g_all_clear"
    assert p["last_run"] == "2026-02-13T15:00:00+00:00"
    assert p["message"] == "z2g run succeeded after previous failure(s)."
    assert p["last_error"] == "N/A"
    assert p["consecutive_failures"] == 0
    assert "last_alert_at" not in p


def test_format_last_run_for_webhook_utc(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_TIMEZONE", "UTC")
    utc_dt = datetime(2026, 2, 13, 14, 30, 5, 123456, tzinfo=timezone.utc)
    s = alerting.format_last_run_for_webhook(utc_dt)
    assert s == "2026-02-13T14:30:05+00:00"
    assert "." not in s  # truncated to second


def test_format_last_run_for_webhook_local_tz(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_TIMEZONE", "America/Chicago")
    utc_dt = datetime(2026, 2, 13, 20, 30, 5, 999999, tzinfo=timezone.utc)
    s = alerting.format_last_run_for_webhook(utc_dt)
    assert "2026-02-13" in s
    assert "14:30:05" in s  # CST is UTC-6
    assert "." not in s


def test_should_alert_below_min_failures(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_MIN_FAILURES", "2")
    state = {"consecutive_failures": 1, "last_alert_at": None}
    assert alerting.should_alert(state) is False


def test_should_alert_at_min_no_previous_alert(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_MIN_FAILURES", "2")
    state = {"consecutive_failures": 2, "last_alert_at": None}
    assert alerting.should_alert(state) is True


def test_should_alert_rate_limited(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_MIN_FAILURES", "2")
    monkeypatch.setenv("Z2G_ALERT_RATE_HOURS", "24")
    now = datetime(2026, 2, 13, 14, 0, 0, tzinfo=timezone.utc)
    state = {"consecutive_failures": 2, "last_alert_at": "2026-02-13T12:00:00+00:00"}
    assert alerting.should_alert(state, now=now) is False


def test_should_alert_after_rate_window(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_MIN_FAILURES", "2")
    monkeypatch.setenv("Z2G_ALERT_RATE_HOURS", "24")
    monkeypatch.setenv("Z2G_ALERT_TIMEZONE", "UTC")
    now = datetime(2026, 2, 14, 15, 0, 0, tzinfo=timezone.utc)
    state = {"consecutive_failures": 2, "last_alert_at": "2026-02-13T12:00:00+00:00"}
    assert alerting.should_alert(state, now=now) is True


def test_should_alert_hours_window_outside(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_MIN_FAILURES", "2")
    monkeypatch.setenv("Z2G_ALERT_TIMEZONE", "UTC")
    monkeypatch.setenv("Z2G_ALERT_HOURS_START", "8")
    monkeypatch.setenv("Z2G_ALERT_HOURS_END", "22")
    now = datetime(2026, 2, 13, 3, 0, 0, tzinfo=timezone.utc)
    state = {"consecutive_failures": 2, "last_alert_at": None}
    assert alerting.should_alert(state, now=now) is False


def test_should_alert_hours_window_inside(monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_MIN_FAILURES", "2")
    monkeypatch.setenv("Z2G_ALERT_TIMEZONE", "UTC")
    monkeypatch.setenv("Z2G_ALERT_HOURS_START", "8")
    monkeypatch.setenv("Z2G_ALERT_HOURS_END", "22")
    now = datetime(2026, 2, 13, 14, 0, 0, tzinfo=timezone.utc)
    state = {"consecutive_failures": 2, "last_alert_at": None}
    assert alerting.should_alert(state, now=now) is True


def test_load_state_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_STATE_FILE", str(tmp_path / "nonexistent.json"))
    state = alerting.load_state()
    assert state["last_run"] is None
    assert state["last_status"] == "ok"
    assert state["consecutive_failures"] == 0
    assert state["last_alert_at"] is None
    assert state["last_success"] is None


def test_save_state_load_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_STATE_FILE", str(tmp_path / "state.json"))
    written = {
        "last_run": "2026-02-13T14:00:00+00:00",
        "last_status": "error",
        "consecutive_failures": 2,
        "last_alert_at": "2026-02-13T12:00:00+00:00",
        "last_success": "2026-02-13T10:00:00+00:00",
    }
    alerting.save_state(written)
    loaded = alerting.load_state()
    assert loaded["last_run"] == written["last_run"]
    assert loaded["last_status"] == written["last_status"]
    assert loaded["consecutive_failures"] == written["consecutive_failures"]
    assert loaded["last_alert_at"] == written["last_alert_at"]
    assert loaded["last_success"] == written["last_success"]


def test_append_run_and_get_24h_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_STATE_FILE", str(tmp_path / "state.json"))
    # No log yet
    assert alerting.get_24h_counts() == (0, 0)
    # Append a few runs (use recent-ish timestamps so they're inside 24h)
    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(hours=1)).isoformat()
    t2 = (now - timedelta(minutes=30)).isoformat()
    alerting.append_run(t1, "ok")
    alerting.append_run(t2, "error")
    alerting.append_run(now.isoformat(), "ok")
    successes, failures = alerting.get_24h_counts()
    assert successes == 2
    assert failures == 1
    # Run log exists and is pruned (only recent lines kept)
    log_path = tmp_path / ".z2g-runs.log"
    assert log_path.exists()


def test_write_status_file(tmp_path, monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_STATE_FILE", str(tmp_path / "state.json"))
    state = {
        "last_run": "2026-02-13T14:00:00+00:00",
        "last_status": "ok",
        "consecutive_failures": 0,
        "last_alert_at": None,
        "last_success": "2026-02-13T14:00:00+00:00",
    }
    alerting.save_state(state)
    alerting.write_status_file(state)
    status_path = tmp_path / ".z2g-status.txt"
    assert status_path.exists()
    text = status_path.read_text()
    assert "SYSTEM STATUS:" in text
    assert "✅" in text
    assert "HEALTHY" in text
    assert "Current Status:   OK" in text
    assert "Last Success:" in text
    assert "PAST 24 HOURS:" in text
    assert "Successes:" in text
    assert "Failures:" in text
    assert "Consecutive Fails:" in text

    # Error state: ALERT and ❌
    state["last_status"] = "error"
    state["consecutive_failures"] = 2
    alerting.write_status_file(state)
    text = status_path.read_text()
    assert "❌" in text
    assert "ALERT" in text
    assert "Current Status:   ERROR" in text
    assert "Consecutive Fails: 2" in text
