"""
Lectura de calendario: Outlook (Microsoft Graph) y Google Calendar.
Devuelve eventos normalizados {title, start, end, location, organizer, attendees}.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from mind.integrations.store import get_valid_access_token

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
GCAL = "https://www.googleapis.com/calendar/v3"


def _graph_event(e: dict) -> dict:
    start = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date")
    end = (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date")
    org = ((e.get("organizer") or {}).get("emailAddress") or {}).get("address")
    attendees = [
        ((a.get("emailAddress") or {}).get("address") or "")
        for a in (e.get("attendees") or [])
    ]
    return {
        "title": e.get("subject") or "(sin título)",
        "start": start,
        "end": end,
        "location": ((e.get("location") or {}).get("displayName") or ""),
        "organizer": org or "",
        "attendees": [a for a in attendees if a],
    }


def _google_event(e: dict) -> dict:
    start = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date")
    end = (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date")
    attendees = [a.get("email", "") for a in (e.get("attendees") or [])]
    return {
        "title": e.get("summary") or "(sin título)",
        "start": start,
        "end": end,
        "location": e.get("location") or "",
        "organizer": ((e.get("organizer") or {}).get("email") or ""),
        "attendees": [a for a in attendees if a],
    }


async def list_events(session, conn, start: datetime, end: datetime, *, limit: int = 25) -> list[dict]:
    token = await get_valid_access_token(session, conn)
    async with httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"}) as client:
        if conn.provider == "outlook":
            resp = await client.get(
                f"{GRAPH}/me/calendarView",
                params={
                    "startDateTime": start.isoformat(),
                    "endDateTime": end.isoformat(),
                    "$top": limit,
                    "$select": "subject,start,end,location,organizer,attendees",
                    "$orderby": "start/dateTime",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"Graph calendar {resp.status_code}: {resp.text[:200]}")
            return [_graph_event(e) for e in resp.json().get("value", [])]

        # Google Calendar
        resp = await client.get(
            f"{GCAL}/calendars/primary/events",
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "maxResults": limit,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Google Calendar {resp.status_code}: {resp.text[:200]}")
        return [_google_event(e) for e in resp.json().get("items", [])]
