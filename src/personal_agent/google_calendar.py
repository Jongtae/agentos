"""Minimal Google Calendar v3 adapter with an injected HTTP transport.

The adapter owns provider syntax, not owner authority or credentials.  Writes
are fixed to the primary calendar and suppress attendee updates.  Reads cover
every calendar the owner shows (``selected``) in Google Calendar, plus the
primary (#1225); only primary events carry an ``etag`` for later changes.
The injected transport has the signature ``(method, url, body, headers)``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from urllib.parse import quote, urlencode


CALENDAR_API = "https://www.googleapis.com/calendar/v3"
CALENDAR_READ_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
#: #1225: listing which calendars the owner has (and shows) needs this scope;
#: the events scope alone cannot discover non-primary calendar ids.
CALENDAR_LIST_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
#: Most calendars read per query (the owner's shown ones, primary first).
MAX_CALENDARS = 25
CALENDAR_WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def _instant(value: str, timezone: str):
    """A sort key that orders RFC3339 starts by instant, all-day dates at local midnight (review on #1228)."""
    from datetime import datetime, timezone as utc
    from zoneinfo import ZoneInfo
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.max.replace(tzinfo=utc.utc)
    if moment.tzinfo is None:
        try:
            moment = moment.replace(tzinfo=ZoneInfo(timezone))
        except Exception:
            moment = moment.replace(tzinfo=utc.utc)
    return moment


@dataclass(frozen=True)
class GoogleCalendarError(ValueError):
    """A provider failure with an explicit external-effect classification."""

    reason: str
    effect: str = "none"

    def __post_init__(self) -> None:
        if self.effect not in {"none", "unknown"}:
            raise ValueError("effect must be none or unknown")
        ValueError.__init__(self, "Google Calendar request failed")


class GoogleCalendarHTTPError(Exception):
    """Transport-neutral HTTP failure used by injected provider transports."""

    def __init__(self, status: int):
        super().__init__(f"Google Calendar HTTP status {status}")
        self.status = status


def _event_body(payload: dict, *, partial: bool = False) -> dict:
    body = {}
    for key in ("summary", "location", "description"):
        if key in payload:
            body[key] = payload[key]
    if any(key in payload for key in ("start", "end", "timezone")):
        if not all(key in payload for key in ("start", "end", "timezone")):
            raise GoogleCalendarError("invalid-payload")
        body["start"] = {"dateTime": payload["start"], "timeZone": payload["timezone"]}
        body["end"] = {"dateTime": payload["end"], "timeZone": payload["timezone"]}
    if not body and partial:
        raise GoogleCalendarError("invalid-payload")
    return body


class GoogleCalendar:
    """Exact GET/POST/PATCH/DELETE operations for one primary calendar."""

    def __init__(self, transport, access_token: str | None = None):
        if access_token is not None and (not isinstance(access_token, str) or not access_token):
            raise ValueError("access_token must be a non-empty string")
        self.transport = transport
        self.access_token = access_token

    def _headers(self, extra: dict | None = None) -> dict:
        headers = dict(extra or {})
        if self.access_token is not None:
            headers["Authorization"] = "Bearer " + self.access_token
        return headers

    def _call(self, method: str, url: str, body, headers: dict, *, mutation: bool):
        try:
            return self.transport(method, url, body, self._headers(headers))
        except GoogleCalendarHTTPError as error:
            if error.status == 401:
                raise GoogleCalendarError("scope-expired") from None
            if error.status == 403:
                raise GoogleCalendarError("provider-rejected") from None
            if error.status == 412:
                raise GoogleCalendarError("stale-event") from None
            if error.status == 409 and mutation:
                # Google documents 409 as "The requested identifier already
                # exists" (reason ``duplicate``) and as ``conflict``. create()
                # sends an event ID derived from the approved idempotency key,
                # so a create 409 means the event plausibly already exists; a
                # PATCH/DELETE 409 does not establish that nothing changed.
                # Neither may be reported as "no external effect".
                reason = "event-already-exists" if method == "POST" else "provider-conflict"
                raise GoogleCalendarError(reason, "unknown") from None
            if mutation and (error.status in (408, 429) or (method in ("PATCH", "DELETE") and error.status in (404, 410))):
                # #594 item 6 (#607): a timed-out/throttled mutation may still
                # have been applied, and "not found"/"gone" on PATCH/DELETE can
                # be the trace of an earlier attempt of this same action.
                # Neither proves that nothing changed; reconcile, never replay.
                raise GoogleCalendarError("provider-error", "unknown") from None
            if error.status >= 500:
                raise GoogleCalendarError("provider-error", "unknown" if mutation else "none") from None
            raise GoogleCalendarError("provider-rejected") from None
        except (TimeoutError, OSError):
            raise GoogleCalendarError("provider-timeout", "unknown" if mutation else "none") from None
        except Exception:
            # Injected transports and response decoders are an external trust
            # boundary. Never expose their exception text; after a mutation
            # attempt, conservatively preserve an unknown-effect receipt.
            raise GoogleCalendarError("provider-error", "unknown" if mutation else "none") from None

    def calendars(self) -> list[dict]:
        """The calendars to read: primary first, then each one shown in Google Calendar.

        ``[{"id", "name", "primary"}]``.  When the list cannot be read (an
        older grant, a provider error), only the primary calendar is returned,
        so a read never gets worse than before #1225.
        """
        query = urlencode({"minAccessRole": "freeBusyReader", "maxResults": 250,
                           "fields": "items(id,summary,summaryOverride,primary,selected)"})
        self.calendar_list_failed = False
        try:
            response = self._call("GET", f"{CALENDAR_API}/users/me/calendarList?{query}", None, {}, mutation=False)
        except GoogleCalendarError as error:
            if error.reason == "scope-expired":
                raise
            response = None
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            # Review on #1228: a primary-only read after a failed discovery is
            # an incomplete read, and says so.
            self.calendar_list_failed = True
        primary = {"id": "primary", "name": "", "primary": True}
        shown = []
        items = response.get("items") if isinstance(response, dict) else None
        for item in items if isinstance(items, list) else ():
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or len(item["id"]) > 1024:
                continue
            name = item.get("summaryOverride") or item.get("summary") or ""
            name = name[:200] if isinstance(name, str) else ""
            if item.get("primary") is True:
                primary["name"] = name
            elif item.get("selected") is True:
                shown.append({"id": item["id"], "name": name, "primary": False})
        return [primary, *shown][:MAX_CALENDARS]

    def query(self, time_min: str, time_max: str, timezone: str, max_results: int) -> list[dict]:
        """Events in the window from every calendar ``calendars`` names, earliest first.

        A non-primary calendar that fails is skipped (named in ``skipped``
        by the caller's evidence); the primary calendar failing fails the read.
        """
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 100:
            raise GoogleCalendarError("malformed-response")
        events, self.skipped_calendars, self.read_calendars = [], [], []
        for calendar in self.calendars():
            try:
                rows = self._query_calendar(calendar["id"], time_min, time_max, timezone, max_results)
            except GoogleCalendarError as error:
                if calendar["primary"] or error.reason == "scope-expired":
                    raise
                self.skipped_calendars.append(calendar["name"] or calendar["id"])
                continue
            self.read_calendars.append(calendar["name"] or ("primary" if calendar["primary"] else calendar["id"]))
            for row in rows:
                row["calendar"] = calendar["name"]
                row["calendar_primary"] = calendar["primary"]
                if not calendar["primary"]:
                    # Writes go to the primary calendar only: no version to draft a change against.
                    row["etag"] = ""
                events.append(row)
        events.sort(key=lambda row: _instant(row["start"], timezone))
        return events[:max_results]

    def _query_calendar(self, calendar_id: str, time_min: str, time_max: str, timezone: str, max_results: int) -> list[dict]:
        query = urlencode(
            {
                "timeMin": time_min,
                "timeMax": time_max,
                "timeZone": timezone,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": max_results,
                "fields": "items(id,etag,summary,start,end,location,status)",
            }
        )
        response = self._call(
            "GET",
            f"{CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events?{query}",
            None,
            {},
            mutation=False,
        )
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise GoogleCalendarError("malformed-response")
        if len(response["items"]) > max_results:
            raise GoogleCalendarError("malformed-response")
        events = []
        for item in response["items"]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                or not isinstance(item.get("start"), dict)
                or not isinstance(item.get("end"), dict)
            ):
                raise GoogleCalendarError("malformed-response")
            start = item["start"].get("dateTime", item["start"].get("date"))
            end = item["end"].get("dateTime", item["end"].get("date"))
            optional = {
                key: item.get(key, "")
                for key in ("etag", "summary", "location", "status")
            }
            if (
                len(item["id"]) > 1024
                or not isinstance(start, str) or not 1 <= len(start) <= 128
                or not isinstance(end, str) or not 1 <= len(end) <= 128
                or any(not isinstance(value, str) for value in optional.values())
                or len(optional["etag"]) > 1024
                or len(optional["summary"]) > 1000
                or len(optional["location"]) > 1000
                or len(optional["status"]) > 64
            ):
                raise GoogleCalendarError("malformed-response")
            events.append(
                {
                    "id": item["id"],
                    "etag": optional["etag"],
                    "summary": optional["summary"],
                    "start": start,
                    "end": end,
                    "location": optional["location"],
                    "status": optional["status"],
                }
            )
        return events

    def create(self, payload: dict, idempotency_key: str) -> dict:
        # Google Calendar has no generic Idempotency-Key contract.  A stable,
        # provider-valid event ID makes the approved create identity explicit.
        event_id = "a" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:31]
        body = {"id": event_id, **_event_body(payload)}
        response = self._call(
            "POST",
            f"{CALENDAR_API}/calendars/primary/events?sendUpdates=none",
            body,
            {"Content-Type": "application/json", "Idempotency-Key": idempotency_key},
            mutation=True,
        )
        if not isinstance(response, dict) or response.get("id") != event_id:
            raise GoogleCalendarError("malformed-response", "unknown")
        return {"id": event_id, "etag": response.get("etag", "")}

    def update(self, event_id: str, etag: str, payload: dict) -> dict:
        response = self._call(
            "PATCH",
            f"{CALENDAR_API}/calendars/primary/events/{quote(event_id, safe='')}?sendUpdates=none",
            _event_body(payload, partial=True),
            {"Content-Type": "application/json", "If-Match": etag},
            mutation=True,
        )
        if not isinstance(response, dict) or response.get("id") != event_id:
            raise GoogleCalendarError("malformed-response", "unknown")
        return {"id": event_id, "etag": response.get("etag", "")}

    def cancel(self, event_id: str, etag: str) -> dict:
        response = self._call(
            "DELETE",
            f"{CALENDAR_API}/calendars/primary/events/{quote(event_id, safe='')}?sendUpdates=none",
            None,
            {"If-Match": etag},
            mutation=True,
        )
        if response not in (None, {}):
            raise GoogleCalendarError("malformed-response", "unknown")
        return {"id": event_id, "cancelled": True}
