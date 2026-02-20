"""Unit tests for z2g.alerting."""
import os
from datetime import datetime, timezone
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
    assert "last_alert_at" not in p
    assert "consecutive_failures" not in p


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


def test_save_state_load_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("Z2G_ALERT_STATE_FILE", str(tmp_path / "state.json"))
    written = {
        "last_run": "2026-02-13T14:00:00+00:00",
        "last_status": "error",
        "consecutive_failures": 2,
        "last_alert_at": "2026-02-13T12:00:00+00:00",
    }
    alerting.save_state(written)
    loaded = alerting.load_state()
    assert loaded["last_run"] == written["last_run"]
    assert loaded["last_status"] == written["last_status"]
    assert loaded["consecutive_failures"] == written["consecutive_failures"]
    assert loaded["last_alert_at"] == written["last_alert_at"]
