"""Minimal Google Calendar v3 adapter with an injected HTTP transport.

The adapter owns provider syntax, not owner authority or credentials.  It is
intentionally fixed to the primary calendar and suppresses attendee updates.
The injected transport has the signature ``(method, url, body, headers)``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from urllib.parse import quote, urlencode


CALENDAR_API = "https://www.googleapis.com/calendar/v3"
CALENDAR_READ_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
CALENDAR_WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"


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
            if error.status in {401, 403}:
                raise GoogleCalendarError("scope-expired") from None
            if error.status == 412:
                raise GoogleCalendarError("stale-event") from None
            if error.status >= 500 and mutation:
                raise GoogleCalendarError("provider-error", "unknown") from None
            raise GoogleCalendarError("provider-rejected") from None
        except (TimeoutError, OSError):
            raise GoogleCalendarError("provider-timeout", "unknown" if mutation else "none") from None

    def query(self, time_min: str, time_max: str, timezone: str, max_results: int) -> list[dict]:
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
            f"{CALENDAR_API}/calendars/primary/events?{query}",
            None,
            {},
            mutation=False,
        )
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
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
            if not isinstance(start, str) or not isinstance(end, str):
                raise GoogleCalendarError("malformed-response")
            events.append(
                {
                    "id": item["id"],
                    "etag": item.get("etag", "") if isinstance(item.get("etag", ""), str) else "",
                    "summary": item.get("summary", "") if isinstance(item.get("summary", ""), str) else "",
                    "start": start,
                    "end": end,
                    "location": item.get("location", "") if isinstance(item.get("location", ""), str) else "",
                    "status": item.get("status", "") if isinstance(item.get("status", ""), str) else "",
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
