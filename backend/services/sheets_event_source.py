"""Spreadsheet-backed Engineer Cafe event source.

The source spreadsheet is exposed through a GAS Web App that already filters
public rows and strips PII. This service keeps a defensive allowlist and
normalizes the payload into the same event shape used by CalendarService and
the event KB bridge.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend.services.event_kb_sync import EventSourceRecord
from backend.tools.calendar_service import CalendarService, TimeRange
from backend.utils.input_sanitizer import sanitize_input

logger = logging.getLogger(__name__)

GAS_URL_ENV = "EVENT_SHEET_GAS_URL"
GAS_TOKEN_ENV = "EVENT_SHEET_GAS_TOKEN"
EVENT_SOURCE_NAME = "spreadsheet"
JST = ZoneInfo("Asia/Tokyo")
HTTP_TIMEOUT_SEC = 15.0

MAX_TITLE = 200
MAX_DESC = 1000
MAX_TIMETABLE = 500
MAX_VENUE = 100
MAX_ORGANIZER = 100


class SheetsEventSource:
    """Fetch public event rows from the GAS event API."""

    def __init__(self) -> None:
        self.url = os.getenv(GAS_URL_ENV, "").strip()
        self.token = os.getenv(GAS_TOKEN_ENV, "").strip()
        self._calendar = CalendarService()

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)

    async def fetch_events(self) -> list[EventSourceRecord]:
        """Fetch and normalize public spreadsheet events."""

        if not self.enabled:
            logger.info(
                "%s/%s not configured; spreadsheet event source disabled",
                GAS_URL_ENV,
                GAS_TOKEN_ENV,
            )
            return []

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_SEC,
                follow_redirects=True,
            ) as client:
                response = await client.get(self.url, params={"token": self.token})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("GAS event API fetch failed: %s", exc)
            return []

        if isinstance(payload, dict) and payload.get("error"):
            logger.warning("GAS event API returned error: %s", payload.get("error"))
            return []

        records = [
            record for item in _extract_event_items(payload) if (record := self._to_record(item))
        ]
        logger.info("Fetched %d spreadsheet event records", len(records))
        return records

    async def search_events(self, time_range: TimeRange = "thisWeek") -> dict[str, Any]:
        """Return spreadsheet events in CalendarService-compatible response shape."""

        try:
            records = await self.fetch_events()
            events = [event_source_record_to_dict(record) for record in records]
            time_min, time_max = self._calendar._calculate_time_range(time_range)
            filtered = self._calendar._filter_events_by_time(events, time_min, time_max)
            filtered.sort(key=lambda event: event.get("start") or "")
            return {
                "success": True,
                "data": {
                    "events": filtered,
                    "timeRange": time_range,
                    "eventCount": len(filtered),
                },
            }
        except Exception as exc:
            logger.warning("Spreadsheet event search failed: %s", exc)
            return {"success": False, "error": str(exc), "data": {"events": []}}

    def _to_record(self, raw: dict[str, Any]) -> EventSourceRecord | None:
        status = _clean(raw.get("status"), max_length=20)
        if status and status != "許可済":
            return None

        title = _clean(raw.get("title"), max_length=MAX_TITLE)
        date = _clean(raw.get("date"), max_length=20)
        if not title or not date:
            return None

        start_text = _normalize_time(raw.get("event_start") or raw.get("start") or "00:00")
        end_text = _normalize_time(raw.get("event_end") or raw.get("end") or start_text)
        try:
            start_dt = datetime.fromisoformat(f"{date}T{start_text}:00").replace(tzinfo=JST)
            end_dt = datetime.fromisoformat(f"{date}T{end_text}:00").replace(tzinfo=JST)
        except ValueError as exc:
            logger.debug(
                "Skipping spreadsheet event row=%s due datetime parse: %s",
                raw.get("row"),
                exc,
            )
            return None

        organizer = _clean(raw.get("organizer"), max_length=MAX_ORGANIZER)
        venue = _clean(
            raw.get("facility") or raw.get("venue") or "Engineer Cafe", max_length=MAX_VENUE
        )
        description = _build_description(raw, organizer=organizer)
        external_id = _external_id(raw, title=title, start=start_dt.isoformat())

        return EventSourceRecord(
            external_id=external_id,
            title=title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat(),
            description=description,
            location=venue or "Engineer Cafe",
            url=_clean(raw.get("url") or raw.get("registration_url"), max_length=300),
            source=EVENT_SOURCE_NAME,
        )


def event_source_record_to_dict(record: EventSourceRecord) -> dict[str, Any]:
    return {
        "id": record.external_id,
        "title": record.title,
        "start": record.start,
        "end": record.end,
        "description": record.description,
        "location": record.location,
        "htmlLink": record.url,
        "url": record.url,
        "source": record.source,
    }


def _extract_event_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _build_description(raw: dict[str, Any], *, organizer: str) -> str:
    parts: list[str] = []
    description = _clean(raw.get("description"), max_length=MAX_DESC)
    additional_info = _clean(raw.get("additional_info"), max_length=MAX_DESC)
    time_table = _clean(raw.get("time_table"), max_length=MAX_TIMETABLE)
    capacity = raw.get("capacity")
    entry_fee = _clean(raw.get("entry_fee"), max_length=80)
    entry_fee_amount = raw.get("entry_fee_amount")
    online = _clean(raw.get("online"), max_length=80)

    if description:
        parts.append(description)
    if additional_info:
        parts.append(f"[補足] {additional_info}")
    if time_table:
        parts.append(f"[タイムテーブル] {time_table}")
    if organizer:
        parts.append(f"[主催] {organizer}")
    if capacity not in (None, ""):
        parts.append(f"[定員] {_clean(capacity, max_length=20)}名")
    if entry_fee:
        fee = entry_fee
        if entry_fee_amount not in (None, "", 0):
            fee = f"{fee} ({_clean(entry_fee_amount, max_length=20)}円)"
        parts.append(f"[参加費] {fee}")
    if online:
        parts.append(f"[オンライン配信] {online}")

    hashtags = raw.get("hashtags")
    if isinstance(hashtags, list):
        tag_text = " ".join(cleaned for tag in hashtags if (cleaned := _clean(tag, max_length=60)))
        if tag_text:
            parts.append(f"[タグ] {tag_text}")

    return "\n".join(parts)


def _external_id(raw: dict[str, Any], *, title: str, start: str) -> str:
    row = raw.get("row")
    if row not in (None, ""):
        return f"sheet:event_status:row{row}"
    event_id = raw.get("event_id") or raw.get("id")
    if event_id:
        return f"sheet:event_status:{_clean(event_id, max_length=100)}"
    return f"sheet:event_status:{title}:{start}"


def _normalize_time(value: Any) -> str:
    text = _clean(value, max_length=20)
    if not text:
        return "00:00"
    parts = text.split(":")
    if len(parts) < 2:
        return "00:00"
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return "00:00"
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return "00:00"
    return f"{hour:02d}:{minute:02d}"


def _clean(value: Any, *, max_length: int) -> str:
    if value is None:
        return ""
    return sanitize_input(str(value).strip(), max_length)
