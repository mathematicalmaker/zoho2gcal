"""Unit tests for z2g.sync_diff."""
from z2g.sync_diff import Diff, diff_events, fmt_diff


def test_diff_events_no_diffs():
    ev = {"summary": "A", "start": {"dateTime": "2026-02-11T14:00:00Z"}, "end": {"dateTime": "2026-02-11T15:00:00Z"}}
    diffs = diff_events(ev, ev)
    assert diffs == []


def test_diff_events_summary_change():
    a = {"summary": "Old", "start": {"dateTime": "2026-02-11T14:00:00Z"}, "end": {"dateTime": "2026-02-11T15:00:00Z"}}
    b = {"summary": "New", "start": {"dateTime": "2026-02-11T14:00:00Z"}, "end": {"dateTime": "2026-02-11T15:00:00Z"}}
    diffs = diff_events(a, b)
    assert len(diffs) == 1
    assert diffs[0].field == "summary"
    assert diffs[0].old == "Old"
    assert diffs[0].new == "New"


def test_diff_events_reminders_signature():
    a = {"reminders": {"useDefault": True}, "summary": "X", "start": {}, "end": {}}
    b = {"reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}, "summary": "X", "start": {}, "end": {}}
    diffs = diff_events(a, b)
    reminder_diff = next((d for d in diffs if d.field == "reminders"), None)
    assert reminder_diff is not None
    assert reminder_diff.old == "default"
    assert reminder_diff.new == "popup:10"


def test_fmt_diff():
    d = Diff(field="summary", old="Old", new="New")
    s = fmt_diff(d)
    assert "summary" in s
    assert "Old" in s
    assert "New" in s
