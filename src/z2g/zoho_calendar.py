"""Zoho Calendar API client.

Fetches events with chunking (Zoho limit: 31 days per request).
Uses OAuth bearer token from ZohoOAuth.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Iterable, Tuple, Optional

import json
import requests

from .zoho_auth import ZohoOAuth


class ZohoCalendarClient:
    def __init__(self, oauth: ZohoOAuth) -> None:
        self.oauth = oauth

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Zoho-oauthtoken {self.oauth.get_access_token()}"}

    def list_calendars(self) -> List[Dict[str, Any]]:
        url = "https://calendar.zoho.com/api/v1/calendars"
        r = requests.get(url, headers=self._headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        cals = data.get("calendars") or data.get("data") or []
        return cals if isinstance(cals, list) else [cals]

    def list_events(
        self,
        calendar_uid: str,
        start_iso: str,
        end_iso: str,
        *,
        byinstance: bool = False,
        verbose: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Low-level Zoho API call.
        Zoho requires a JSON 'range' param and rejects extra params.
        Range cannot exceed 31 days.
        """
        url = f"https://calendar.zoho.com/api/v1/calendars/{calendar_uid}/events"

        # Zoho expects range.start/range.end formatted YYYYMMDD (date-only is fine for list).
        range_obj = {
            "start": start_iso[:10].replace("-", ""),  # YYYYMMDD
            "end": end_iso[:10].replace("-", ""),      # YYYYMMDD
        }

        params: Dict[str, str] = {
            "range": json.dumps(range_obj, separators=(",", ":")),
        }
        if byinstance:
            params["byinstance"] = "true"

        r = requests.get(url, headers=self._headers(), params=params, timeout=45)
        if not r.ok:
            raise RuntimeError(f"Zoho list_events failed: {r.status_code} {r.text}")

        data = r.json()
        evs = data.get("events") or []
        if not isinstance(evs, list):
            evs = [evs]

        clean: List[Dict[str, Any]] = []
        for item in evs:
            # Zoho sometimes includes non-event records like {"message": "No events found."}
            if isinstance(item, dict) and item.keys() == {"message"}:
                if verbose:
                    print(f"[zoho] message: {item['message']}")
                continue
        
            if isinstance(item, dict) and ("uid" in item or "dateandtime" in item or "title" in item):
                clean.append(item)
            else:
                if verbose:
                    print(f"[zoho] skipping non-event item: {item!r}")

        return clean

    @staticmethod
    def _chunk_range(
        start: datetime,
        end: datetime,
        *,
        chunk_days: int = 28,
        overlap_days: int = 1,
    ) -> Iterable[Tuple[datetime, datetime]]:
        """
        Yield chunks covering [start, end] with fixed chunk length and overlap,
        GUARANTEEING forward progress (no infinite loops).
    
        We treat 'end' as an exclusive upper bound for iteration.
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    
        if end <= start:
            return
    
        step = timedelta(days=chunk_days)
        overlap = timedelta(days=overlap_days)
        if overlap >= step:
            raise ValueError("overlap_days must be smaller than chunk_days")
    
        cur = start
        while True:
            nxt = cur + step
            if nxt >= end:
                # final chunk and stop
                yield cur, end
                break
    
            yield cur, nxt
    
            # advance with overlap, but ALWAYS move forward at least 1 second
            new_cur = nxt - overlap
            if new_cur <= cur:
                new_cur = cur + timedelta(seconds=1)
    
            cur = new_cur


    def list_events_range(
        self,
        calendar_uid: str,
        start: datetime,
        end: datetime,
        *,
        byinstance: bool = False,
        chunk_days: int = 28,
        overlap_days: int = 1,
        dedupe_key: str = "uid",
        verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """
        High-level safe range fetch:
          - chunks to satisfy Zoho's <=31 day constraint
          - overlaps by 1 day to avoid boundary misses
          - de-dupes across chunks using the event 'uid' by default
        """
        events: List[Dict[str, Any]] = []
        for a, b in self._chunk_range(start, end, chunk_days=chunk_days, overlap_days=overlap_days):
            if verbose:
                print(f"[zoho] chunk {a.isoformat()} -> {b.isoformat()}")
        
            chunk_events = self.list_events(
                calendar_uid,
                a.isoformat(),
                b.isoformat(),
                byinstance=byinstance,
                verbose=verbose,
            )

            if verbose and len(chunk_events) > 0:
                print(f"[zoho] chunk events: {len(chunk_events)}")

            events.extend(chunk_events)

        # De-dupe across chunks
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for ev in events:
            k = ev.get(dedupe_key)
            if not k:
                # keep weird events, but don't let them crash the run
                deduped.append(ev)
                continue
            ks = str(k)
            if ks in seen:
                continue
            seen.add(ks)
            deduped.append(ev)
        if verbose:
            print(f"[zoho] total fetched: {len(events)} (pre-dedupe)")
            print(f"[zoho] total unique : {len(deduped)} (post-dedupe)")

        return deduped

