"""Unit tests for z2g.time_utils."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from z2g.time_utils import compute_window, parse_when


def test_parse_when_iso():
    dt = parse_when("2026-02-11T14:00:00Z")
    assert dt.year == 2026 and dt.month == 2 and dt.day == 11


def test_parse_when_date_only():
    dt = parse_when("2026-02-11")
    assert dt.year == 2026 and dt.month == 2 and dt.day == 11


def test_parse_when_relative_positive():
    now = datetime.now(timezone.utc)
    dt = parse_when("+7d")
    delta = (dt - now).total_seconds()
    assert 6.9 * 86400 <= delta <= 7.1 * 86400


def test_parse_when_relative_negative():
    now = datetime.now(timezone.utc)
    dt = parse_when("-1d")
    delta = (now - dt).total_seconds()
    assert 0.9 * 86400 <= delta <= 1.1 * 86400


def test_parse_when_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_when("")


@patch.dict(os.environ, {"SYNC_LOOKBACK_DAYS": "3", "SYNC_LOOKAHEAD_DAYS": "14"}, clear=False)
def test_compute_window_from_env():
    start, end = compute_window(
        None,
        None,
        lookback_days_env="SYNC_LOOKBACK_DAYS",
        lookahead_days_env="SYNC_LOOKAHEAD_DAYS",
    )
    delta = end - start
    assert delta.days == 17  # 3 + 14


def test_compute_window_explicit():
    start, end = compute_window(
        "2026-02-01",
        "2026-02-15",
        lookback_days_env="X",
        lookahead_days_env="Y",
    )
    assert start.year == 2026 and start.month == 2 and start.day == 1
    assert end.year == 2026 and end.month == 2 and end.day == 15


def test_compute_window_until_before_since_raises():
    with pytest.raises(ValueError, match="--until must be after"):
        compute_window("2026-02-15", "2026-02-01", lookback_days_env="X", lookahead_days_env="Y")
