"""Event-to-knowledge-base bridge.

This module is intentionally additive and side-effect-free by default. It
normalizes event source records, adapts them to event-category knowledge
documents, then reuses the existing upload chunk planning path before optional
embedding/upsert.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.knowledge.upload_ingestion import (
    build_upload_chunk_records,
    plan_upload_chunks,
)
from backend.tools.calendar_service import CalendarService
from backend.utils.embedding_service import generate_embedding

logger = logging.getLogger(__name__)

EmbeddingFn = Callable[[str], Awaitable[Sequence[float]] | Sequence[float]]

EVENT_KB_CATEGORY = "event"
EVENT_KB_LANGUAGE = "ja"
EVENT_KB_SOURCE_PREFIX = "event_bridge"


@dataclass(frozen=True)
class EventSourceRecord:
    """Normalized event source representation used by the KB bridge."""

    external_id: str
    title: str
    start: str
    end: str = ""
    description: str = ""
    location: str = ""
    url: str = ""
    source: str = "google_calendar"


@dataclass(frozen=True)
class EventKbSyncResult:
    """Summary of an event KB sync run."""

    planned_count: int
    written_count: int
    skipped_count: int
    records: tuple[dict[str, Any], ...]


def parse_ics_event_records(
    ics_content: str,
    *,
    source: str = "google_calendar",
) -> list[EventSourceRecord]:
    """Parse ICS text into deterministic event source records.

    The existing calendar parser already handles folded lines, date formats,
    unescaping, and low-value placeholder filtering. This bridge wraps it in a
    stable normalized type instead of creating another event parser branch.
    """

    parsed_events = CalendarService()._parse_ics_content(ics_content)
    return [normalize_event_record(event, default_source=source) for event in parsed_events]


def normalize_event_record(
    event: dict[str, Any],
    *,
    default_source: str = "google_calendar",
) -> EventSourceRecord:
    """Normalize a calendar/Connpass-style event dict."""

    title = str(event.get("title") or event.get("summary") or "").strip()
    start = str(event.get("start") or event.get("starts_at") or event.get("start_at") or "").strip()
    if not title:
        raise ValueError("event title is required")
    if not start:
        raise ValueError(f"event start is required for title={title!r}")

    raw_id = event.get("id") or event.get("uid") or event.get("event_id")
    if raw_id:
        external_id = str(raw_id).strip()
    else:
        external_id = _event_digest(default_source, title, start)

    return EventSourceRecord(
        external_id=external_id,
        title=title,
        start=start,
        end=str(event.get("end") or event.get("ends_at") or event.get("end_at") or "").strip(),
        description=str(event.get("description") or "").strip(),
        location=str(event.get("location") or event.get("venue") or "").strip(),
        url=str(event.get("htmlLink") or event.get("url") or event.get("event_url") or "").strip(),
        source=str(event.get("source") or default_source).strip() or default_source,
    )


def event_record_to_markdown(event: EventSourceRecord) -> str:
    """Render one normalized event as a KB document body."""

    lines = [
        f"# {event.title}",
        "",
        f"- Start: {event.start}",
    ]
    if event.end:
        lines.append(f"- End: {event.end}")
    if event.location:
        lines.append(f"- Location: {event.location}")
    if event.url:
        lines.append(f"- URL: {event.url}")
    lines.extend(["", "## Description"])
    lines.append(event.description or "No description provided by the event source.")
    return "\n".join(lines).strip()


def event_record_to_metadata(event: EventSourceRecord) -> dict[str, Any]:
    """Build metadata used for sync accounting and future rollback."""

    return {
        "bridge": EVENT_KB_SOURCE_PREFIX,
        "sync_source": event.source,
        "external_event_id": event.external_id,
        "start": event.start,
        "end": event.end,
        "location": event.location,
        "url": event.url,
    }


def event_record_to_kb_title(event: EventSourceRecord) -> str:
    """Build a stable title that fits the knowledge title limit."""

    date_label = _date_label(event.start)
    digest = _event_digest(event.source, event.external_id, event.start)[:8]
    suffix = f" ({date_label}) [{digest}]"
    prefix = "Event: "
    max_title_chars = 200
    max_event_title_chars = max_title_chars - len(prefix) - len(suffix)
    event_title = event.title
    if len(event_title) > max_event_title_chars:
        event_title = event_title[: max(0, max_event_title_chars - 3)].rstrip() + "..."
    return f"{prefix}{event_title}{suffix}"


async def plan_event_kb_records(
    events: Sequence[EventSourceRecord],
    *,
    embedding_fn: EmbeddingFn | None = None,
) -> list[dict[str, Any]]:
    """Plan KB rows for events without writing to storage."""

    records: list[dict[str, Any]] = []
    for event in events:
        content = event_record_to_markdown(event)
        title = event_record_to_kb_title(event)
        plan = plan_upload_chunks(
            content,
            filename=f"{_safe_filename_stem(event)}.md",
            category=EVENT_KB_CATEGORY,
            language=EVENT_KB_LANGUAGE,
            title=title,
            metadata=event_record_to_metadata(event),
        )
        chunk_records = await build_upload_chunk_records(plan, embedding_fn=embedding_fn)
        for record in chunk_records:
            record["source"] = _kb_source(event)
            record["subcategory"] = "live_event"
        records.extend(chunk_records)
    return records


async def sync_event_kb_records(
    events: Sequence[EventSourceRecord],
    *,
    supabase_client: Any | None = None,
    embedding_fn: EmbeddingFn | None = None,
    dry_run: bool = True,
) -> EventKbSyncResult:
    """Plan and optionally upsert event KB records.

    Dry runs do not generate embeddings and never touch Supabase. Live writes
    require both a Supabase client and successful embeddings for every planned
    row; rows without embeddings are skipped to preserve RAG visibility.
    """

    if dry_run:
        records = await plan_event_kb_records(events)
        return EventKbSyncResult(
            planned_count=len(records),
            written_count=0,
            skipped_count=0,
            records=tuple(records),
        )

    if supabase_client is None:
        raise ValueError("supabase_client is required when dry_run is false")

    resolved_embedding_fn = embedding_fn or _event_record_embedding
    records = await plan_event_kb_records(events, embedding_fn=resolved_embedding_fn)

    written_count = 0
    skipped_count = 0
    written_records: list[dict[str, Any]] = []
    for record in records:
        if not record.get("content_embedding"):
            skipped_count += 1
            logger.warning("Skipping event KB record without embedding: %s", record.get("title"))
            continue
        supabase_client.table("knowledge_base").upsert(
            record,
            on_conflict="title",
        ).execute()
        written_count += 1
        written_records.append(record)

    return EventKbSyncResult(
        planned_count=len(records),
        written_count=written_count,
        skipped_count=skipped_count,
        records=tuple(written_records),
    )


async def _event_record_embedding(text: str) -> Sequence[float]:
    embedding = generate_embedding(text)
    if inspect.isawaitable(embedding):
        embedding = await embedding
    return embedding or []


def _kb_source(event: EventSourceRecord) -> str:
    return f"{EVENT_KB_SOURCE_PREFIX}:{event.source}:{event.external_id}"


def _safe_filename_stem(event: EventSourceRecord) -> str:
    return _event_digest(event.source, event.external_id, event.start)


def _event_digest(*parts: str) -> str:
    return hashlib.sha1(":".join(parts).encode("utf-8")).hexdigest()


def _date_label(value: str) -> str:
    if not value:
        return "date-unknown"
    candidate = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else value
