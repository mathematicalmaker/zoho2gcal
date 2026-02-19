"""CLI for z2g: one-way Zoho Calendar → Google Calendar sync.

Commands: sync (one-off), run (scheduled + state + optional alerts),
zoho-events, google-auth, zoho-exchange-code,
list-zoho-calendars, list-google-calendars, zoho-token.

Exit codes: 0 success, 1 error, 2 usage.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

from .config import env, resolve_path, verbose_enabled
from .zoho_auth import ZohoOAuth
from .zoho_calendar import ZohoCalendarClient
from .google_calendar import GoogleCalendarClient
from .transform import iso_z, build_google_mirror_event, zoho_uid, parse_google_reminders, format_default_reminders
from .time_utils import compute_window
from .sync_diff import Diff, diff_events, fmt_diff
from . import alerting


# ----------------------------
# Commands
# ----------------------------

def _zoho_client() -> ZohoCalendarClient:
    oauth = ZohoOAuth(
        client_id=env("ZOHO_CLIENT_ID"),
        client_secret=env("ZOHO_CLIENT_SECRET"),
        refresh_token=env("ZOHO_REFRESH_TOKEN"),
        accounts_host=os.environ.get("ZOHO_ACCOUNTS_HOST", "https://accounts.zoho.com"),
    )
    return ZohoCalendarClient(oauth)


def cmd_zoho_token() -> None:
    z = _zoho_client()
    # token is fetched via ZohoOAuth; expose it for debugging
    print(z.oauth.get_access_token())  # type: ignore[attr-defined]

def cmd_zoho_exchange_code(code: str, redirect_uri: str) -> None:
    from .zoho_oauth_exchange import exchange_code_for_tokens

    data = exchange_code_for_tokens(
        accounts_host=os.environ.get("ZOHO_ACCOUNTS_HOST", "https://accounts.zoho.com"),
        code=code,
        client_id=env("ZOHO_CLIENT_ID"),
        client_secret=env("ZOHO_CLIENT_SECRET"),
        redirect_uri=redirect_uri,
    )

    refresh = data.get("refresh_token")
    if refresh:
        print("Add this line to .env:")
        print("")
        print("ZOHO_REFRESH_TOKEN=" + refresh)
    else:
        print("No refresh_token returned (did you request offline access / correct grant?)", file=sys.stderr)


def cmd_google_auth(*, manual: bool = False) -> None:
    from .google_auth import authorize

    client_secret = resolve_path(env("GOOGLE_CLIENT_SECRET_JSON"))
    token_out = resolve_path(env("GOOGLE_TOKEN_JSON"))
    token_path = authorize(client_secret, token_out, manual=manual)
    print(f"Wrote Google token to: {token_path}")


def cmd_list_zoho_calendars() -> None:
    z = _zoho_client()
    for c in z.list_calendars():
        print(f"{c.get('calendar_uid') or c.get('uid')}\t{c.get('calendar_name') or c.get('name')}")


def _sanitize_tsv(s: str) -> str:
    """Replace tab/newline with space so piped output stays column-aligned (e.g. column -t, awk)."""
    return (s or "").replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()


def cmd_list_google_calendars() -> None:
    g = GoogleCalendarClient(resolve_path(env("GOOGLE_TOKEN_JSON")))
    print("Name\tCalendar_ID\tDefault_Reminders")
    for cal in g.list_calendars():
        reminders_str = format_default_reminders(cal.get("defaultReminders") or [])
        name = _sanitize_tsv(str(cal.get("summary") or ""))
        cid = _sanitize_tsv(str(cal.get("id") or ""))
        print(f"{name}\t{cid}\t{reminders_str}")


def cmd_verify() -> None:
    """Check config and test connections to Zoho and Google (validates scopes). Exit 0 if OK."""
    errors: List[str] = []
    required_env = [
        "ZOHO_CLIENT_ID",
        "ZOHO_CLIENT_SECRET",
        "ZOHO_REFRESH_TOKEN",
        "GOOGLE_CLIENT_SECRET_JSON",
        "GOOGLE_TOKEN_JSON",
    ]
    for name in required_env:
        if not (os.environ.get(name) or "").strip():
            errors.append(f"Missing env: {name}")

    if not errors:
        from pathlib import Path
        for path_var in ("GOOGLE_CLIENT_SECRET_JSON", "GOOGLE_TOKEN_JSON"):
            try:
                p = Path(resolve_path(env(path_var)))
                if not p.exists():
                    errors.append(f"File not found: {path_var} -> {p}")
            except Exception as e:
                errors.append(str(e))

    if errors:
        for e in errors:
            print(f"z2g verify: {e}", file=sys.stderr)
        sys.exit(1)

    # Test Zoho
    try:
        z = _zoho_client()
        z.list_calendars()
    except Exception as e:
        print(f"z2g verify: Zoho: {e}", file=sys.stderr)
        sys.exit(1)

    # Test Google
    try:
        g = GoogleCalendarClient(resolve_path(env("GOOGLE_TOKEN_JSON")))
        g.list_calendars()
    except Exception as e:
        print(f"z2g verify: Google: {e}", file=sys.stderr)
        sys.exit(1)

    print("Config OK. Zoho and Google connections and scopes verified.")
    missing_cal = [n for n in ("ZOHO_CALENDAR_UID", "GOOGLE_CALENDAR_ID") if not (os.environ.get(n) or "").strip()]
    if missing_cal:
        print(f"z2g verify: {', '.join(missing_cal)} not set; sync/run will fail until you set them.", file=sys.stderr)


def cmd_zoho_events(*, since: Optional[str], until: Optional[str]) -> None:
    z = _zoho_client()

    start, end = compute_window(
        since,
        until,
        lookback_days_env="SYNC_LOOKBACK_DAYS",
        lookahead_days_env="SYNC_LOOKAHEAD_DAYS",
    )

    cal_uid = env("ZOHO_CALENDAR_UID")

    events = z.list_events_range(
        cal_uid,
        start,
        end,
        byinstance=True,
        verbose=verbose_enabled(),
    )

    print(f"Fetched {len(events)} events from {iso_z(start)} to {iso_z(end)}")
    for ev in events[:50]:
        uid = zoho_uid(ev)
        title = ev.get("title") or ev.get("name") or "(no title)"
        dt = ev.get("dateandtime") or {}
        start_raw = (
            dt.get("start")
            or ev.get("start_datetime")
            or ev.get("start")
            or ev.get("from")
            or ev.get("startTime")
        )
        end_raw = (
            dt.get("end")
            or ev.get("end_datetime")
            or ev.get("end")
            or ev.get("to")
            or ev.get("endTime")
        )
        print(f"{uid}\t{title}\t{start_raw} -> {end_raw}")


def cmd_sync(
    *,
    since: Optional[str],
    until: Optional[str],
    dry_run: bool,
    delete_missing: bool = False,
) -> None:
    z = _zoho_client()

    start, end = compute_window(
        since,
        until,
        lookback_days_env="SYNC_LOOKBACK_DAYS",
        lookahead_days_env="SYNC_LOOKAHEAD_DAYS",
    )

    g = GoogleCalendarClient(resolve_path(env("GOOGLE_TOKEN_JSON")))
    gcal_id = env("GOOGLE_CALENDAR_ID")

    cal_uid = env("ZOHO_CALENDAR_UID")
    events = z.list_events_range(
        cal_uid,
        start,
        end,
        byinstance=True,
        verbose=verbose_enabled(),
    )

    title_mode = os.environ.get("TITLE_MODE", "busy")
    suffix = os.environ.get("ICALUID_SUFFIX", "zoho-mirror")
    reminders = parse_google_reminders(os.environ.get("GOOGLE_REMINDERS", ""))
    delete_missing = delete_missing or (os.environ.get("Z2G_DELETE_MISSING", "").strip().lower() in ("1", "true", "yes"))

    desired_icaluids: set[str] = set()
    inserts = patches = skips = 0

    for ev in events:
        uid = zoho_uid(ev)
        desired = build_google_mirror_event(
            ev,
            title_mode=title_mode,
            icaluid_suffix=suffix,
            reminders=reminders,
        )
        desired_icaluids.add(desired["iCalUID"])

        existing = g.find_by_icaluid(gcal_id, desired["iCalUID"])
        if not existing:
            action = "INSERT"
            diffs: List[Diff] = []
            if dry_run:
                inserts += 1
                print(f"[DRY] {action} {uid} -> {desired['iCalUID']}  {desired.get('summary','')}")
                continue
            g.upsert(gcal_id, None, desired)
            print(f"inserted {uid} -> {desired['iCalUID']}")
            continue

        # Phase B: diff compare existing vs desired
        diffs = diff_events(existing, desired)
        if not diffs:
            action = "SKIP"
            if dry_run:
                skips += 1
                print(f"[DRY] {action}  {uid} -> {desired['iCalUID']}  (already in sync)")
                continue
            # Real run: skip patch to reduce churn
            print(f"skipped  {uid} -> {desired['iCalUID']}  (already in sync)")
            continue

        action = "PATCH"
        if dry_run:
            patches += 1
            print(f"[DRY] {action} {uid} -> {desired['iCalUID']}  {desired.get('summary','')}")
            for d in diffs:
                print(fmt_diff(d))
            continue

        existing_id = existing.get("id")
        g.upsert(gcal_id, existing_id, desired)
        print(f"patched  {uid} -> {desired['iCalUID']}")

    # Optional: delete from Google any mirrored events in range that are no longer in Zoho.
    # In dry-run we always run this check so the report shows would-deletes; only actually delete when delete_missing.
    deletes = 0
    if delete_missing or dry_run:
        time_min = iso_z(start)
        time_max = iso_z(end)
        g_events = g.list_events_in_range(gcal_id, time_min, time_max)
        for event in g_events:
            private = (event.get("extendedProperties") or {}).get("private") or {}
            if private.get("zoho_mirror") != "1":
                continue
            icaluid = event.get("iCalUID")
            if icaluid and icaluid not in desired_icaluids:
                deletes += 1
                if dry_run:
                    print(f"[DRY] would delete (no longer in Zoho)  {icaluid}  {event.get('summary', '')}")
                else:
                    g.delete(gcal_id, event["id"])
                    print(f"deleted (no longer in Zoho)  {icaluid}")

    if dry_run:
        print(f"[DRY] summary: inserts={inserts} patches={patches} skips={skips} deletes={deletes} total={len(events)}")
        if deletes and not delete_missing:
            print("[DRY] (pass --delete-missing to remove those events from Google)")


def cmd_run(
    *,
    since: Optional[str],
    until: Optional[str],
    dry_run: bool,
    delete_missing: bool = False,
) -> None:
    """Run sync, update alert state, and optionally POST to webhook on repeated failures."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    last_error: Optional[str] = None
    try:
        cmd_sync(since=since, until=until, dry_run=dry_run, delete_missing=delete_missing)
    except Exception as e:
        success = False
        last_error = str(e)
        state = alerting.load_state()
        state["last_run"] = now_iso
        state["last_status"] = "error"
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        alerting.save_state(state)
        url = os.environ.get("Z2G_ALERT_WEBHOOK_URL", "").strip()
        if url and alerting.should_alert(state, now):
            payload = alerting.build_payload(
                consecutive_failures=state["consecutive_failures"],
                last_error=last_error,
                last_run=now_iso,
                message=f"z2g run failed {state['consecutive_failures']} time(s): {last_error}",
            )
            try:
                alerting.send_webhook(url, payload)
                state["last_alert_at"] = now_iso
                alerting.save_state(state)
            except Exception as webhook_err:
                print(f"z2g: webhook failed: {webhook_err}", file=sys.stderr)
        raise
    # Success: clear consecutive failures and persist state
    state = alerting.load_state()
    state["last_run"] = now_iso
    state["last_status"] = "ok"
    state["consecutive_failures"] = 0
    alerting.save_state(state)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        prog="z2g",
        description="One-way sync Zoho Calendar events into a Google Calendar (mirror).",
        epilog=(
            "sync: one-off sync (interactive/debug). No state file or alerting.\n"
            "run:  scheduled entry point; updates state file and can POST to a webhook on repeated failures.\n"
            "\n"
            "By default, events removed or cancelled in Zoho are not deleted from Google.\n"
            "Use sync/run --delete-missing (or Z2G_DELETE_MISSING=1) to remove them.\n"
            "\n"
            "Time range examples:\n"
            "  --since 2026-02-01 --until 2026-03-01\n"
            "  --since 2026-02-01T12:00:00-06:00 --until 2026-02-02T12:00:00-06:00\n"
            "  --since=-7d --until=+90d\n"
            "\n"
            "NOTE: Relative negatives like -7d must be passed as --since=-7d (or after --).\n"
            "      Example: z2g sync --since=-7d --until=+90d\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global flags (optional but nice)
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (same as Z2G_VERBOSE=1).",
    )

    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    # Put the most common operational commands first
    p_sync = sub.add_parser(
        "sync",
        help="One-off sync from Zoho to Google (interactive/debug). No state file or alerting.",
    )
    p_sync.add_argument(
        "--since",
        default=None,
        help='Start of range. Date/ISO or relative. Env: SYNC_SINCE. Defaults: SYNC_LOOKBACK_DAYS.',
    )
    p_sync.add_argument(
        "--until",
        default=None,
        help='End of range. Date/ISO or relative. Env: SYNC_UNTIL. Defaults: SYNC_LOOKAHEAD_DAYS.',
    )
    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to Google; show INSERT/PATCH/SKIP with diffs.",
    )
    p_sync.add_argument(
        "--delete-missing",
        action="store_true",
        help="Delete from Google any mirrored events in the range that are no longer in Zoho (cancelled/removed). Default: off; also settable via Z2G_DELETE_MISSING=1.",
    )

    p_run = sub.add_parser(
        "run",
        help="Scheduled entry point: run sync, update state file, optionally alert via webhook on repeated failures.",
    )
    p_run.add_argument(
        "--since",
        default=None,
        help='Start of range. Date/ISO or relative. Env: SYNC_SINCE. Defaults: SYNC_LOOKBACK_DAYS.',
    )
    p_run.add_argument(
        "--until",
        default=None,
        help='End of range. Date/ISO or relative. Env: SYNC_UNTIL. Defaults: SYNC_LOOKAHEAD_DAYS.',
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to Google; show INSERT/PATCH/SKIP with diffs.",
    )
    p_run.add_argument(
        "--delete-missing",
        action="store_true",
        help="Delete from Google any mirrored events in the range that are no longer in Zoho. Default: off; also Z2G_DELETE_MISSING=1.",
    )

    p_events = sub.add_parser(
        "zoho-events",
        help="Fetch and list Zoho events for a time range (debug aid).",
    )
    p_events.add_argument(
        "--since",
        default=None,
        help='Start of range. Date/ISO or relative (e.g. "2026-02-01" or "--since=-7d").',
    )
    p_events.add_argument(
        "--until",
        default=None,
        help='End of range. Date/ISO or relative (e.g. "2026-03-01" or "--until=+30d").',
    )

    # Auth / discovery
    p_google_auth = sub.add_parser("google-auth", help="Run Google OAuth flow and write token JSON.")
    p_google_auth.add_argument(
        "--manual",
        action="store_true",
        help="No local server; paste redirect URL back. Env: Z2G_GOOGLE_AUTH_MANUAL=1.",
    )
    sub.add_parser("list-google-calendars", help="List Google calendars (id and name).")

    sub.add_parser("zoho-token", help="Print a Zoho access token (debug).")
    sub.add_parser("list-zoho-calendars", help="List Zoho calendars (uid and name).")
    sub.add_parser(
        "verify",
        help="Check config and test Zoho + Google connections and scopes (for Docker or after setup).",
    )

    p_ex = sub.add_parser(
        "zoho-exchange-code",
        help="Exchange a Zoho authorization code for tokens (prints ZOHO_REFRESH_TOKEN=...).",
    )
    p_ex.add_argument(
        "--code",
        required=True,
        help="Authorization code obtained from Zoho OAuth consent redirect.",
    )
    p_ex.add_argument(
        "--redirect-uri",
        default="http://localhost",
        help='Must match the redirect URI configured in Zoho (default: http://localhost).',
    )

    args = p.parse_args()

    # Let CLI override env-based verbosity cleanly
    if args.verbose:
        os.environ["Z2G_VERBOSE"] = "1"

    try:
        if args.cmd == "sync":
            cmd_sync(
                since=args.since or os.environ.get("SYNC_SINCE"),
                until=args.until or os.environ.get("SYNC_UNTIL"),
                dry_run=args.dry_run,
                delete_missing=getattr(args, "delete_missing", False),
            )
        elif args.cmd == "run":
            cmd_run(
                since=args.since or os.environ.get("SYNC_SINCE"),
                until=args.until or os.environ.get("SYNC_UNTIL"),
                dry_run=args.dry_run,
                delete_missing=getattr(args, "delete_missing", False),
            )
        elif args.cmd == "zoho-events":
            cmd_zoho_events(
                since=args.since or os.environ.get("SYNC_SINCE"),
                until=args.until or os.environ.get("SYNC_UNTIL"),
            )
        elif args.cmd == "google-auth":
            manual = getattr(args, "manual", False) or (
                os.environ.get("Z2G_GOOGLE_AUTH_MANUAL", "").strip().lower() in ("1", "true", "yes")
            )
            cmd_google_auth(manual=manual)
        elif args.cmd == "list-google-calendars":
            cmd_list_google_calendars()
        elif args.cmd == "zoho-token":
            cmd_zoho_token()
        elif args.cmd == "list-zoho-calendars":
            cmd_list_zoho_calendars()
        elif args.cmd == "zoho-exchange-code":
            cmd_zoho_exchange_code(args.code, args.redirect_uri)
        elif args.cmd == "verify":
            cmd_verify()
        else:
            raise SystemExit(2)
        sys.exit(0)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"z2g: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

