"""Unit tests for z2g.transform."""
from datetime import date, datetime, timezone

import pytest

from z2g.transform import (
    MIRROR_MARKER,
    build_google_mirror_event,
    is_zoho_allday,
    iso_z,
    parse_google_reminders,
    zoho_times,
    zoho_uid,
)


def test_iso_z():
    dt = datetime(2026, 2, 11, 20, 36, 57, tzinfo=timezone.utc)
    assert iso_z(dt) == "2026-02-11T20:36:57Z"


def test_zoho_uid_from_uid():
    assert zoho_uid({"uid": "abc123"}) == "abc123"


def test_zoho_uid_from_event_uid():
    assert zoho_uid({"event_uid": "xyz"}) == "xyz"


def test_zoho_uid_fallback_order():
    ev = {"eventId": "a", "id": "b", "uid": "c"}
    assert zoho_uid(ev) == "c"  # uid has priority


def test_zoho_uid_missing_raises():
    with pytest.raises(KeyError, match="No Zoho UID"):
        zoho_uid({"title": "foo"})


def test_zoho_times_from_dateandtime():
    ev = {
        "dateandtime": {"start": "20260211T140000-0600", "end": "20260211T141500-0600"},
    }
    s, e = zoho_times(ev)
    assert s.year == 2026 and s.month == 2 and s.day == 11
    assert e.year == 2026 and e.month == 2 and e.day == 11


def test_zoho_times_missing_raises():
    with pytest.raises(KeyError, match="Missing start/end"):
        zoho_times({"uid": "x"})


def test_is_zoho_allday_from_flag():
    assert is_zoho_allday({"isallday": True}) is True
    assert is_zoho_allday({"isallday": False}) is False


def test_is_zoho_allday_from_date_only_start():
    ev = {"dateandtime": {"start": "20260211"}}
    assert is_zoho_allday(ev) is True


def test_is_zoho_allday_timed_event():
    ev = {"dateandtime": {"start": "20260211T140000-0600", "end": "20260211T141500-0600"}}
    assert is_zoho_allday(ev) is False


def test_parse_google_reminders_default():
    assert parse_google_reminders("") == {"useDefault": True}
    assert parse_google_reminders("default") == {"useDefault": True}


def test_parse_google_reminders_popup():
    r = parse_google_reminders("popup:10")
    assert r == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}


def test_parse_google_reminders_multiple():
    r = parse_google_reminders("popup:10,email:30")
    assert r["useDefault"] is False
    assert len(r["overrides"]) == 2


def test_build_google_mirror_event_no_attendees():
    ev = {
        "uid": "test@example.com",
        "title": "Meeting",
        "dateandtime": {"start": "20260211T140000Z", "end": "20260211T141500Z"},
    }
    body = build_google_mirror_event(ev, title_mode="original", icaluid_suffix="zoho.test")
    assert "attendees" not in body
    assert body["summary"] == "Meeting"
    assert body["iCalUID"] == "test@example.com"
    assert MIRROR_MARKER in body["description"]


def test_build_google_mirror_event_allday():
    ev = {
        "uid": "abc",
        "title": "Holiday",
        "isallday": True,
        "dateandtime": {"start": "20260211", "end": "20260211"},
    }
    body = build_google_mirror_event(ev, title_mode="original", icaluid_suffix="zoho.test")
    assert body["start"]["date"] == "2026-02-11"
    assert body["end"]["date"] == "2026-02-12"  # exclusive

