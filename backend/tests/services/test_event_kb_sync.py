from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.services.event_kb_sync import (
    EventSourceRecord,
    event_record_to_kb_title,
    event_record_to_markdown,
    parse_ics_event_records,
    plan_event_kb_records,
    sync_event_kb_records,
)

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Engineer Cafe//Event KB Bridge Test//EN
BEGIN:VEVENT
UID:event-001@example.com
SUMMARY:Engineer Cafe Python Meetup
DTSTART:20260510T100000Z
DTEND:20260510T120000Z
LOCATION:Engineer Cafe Main Hall
DESCRIPTION:Bring a laptop\\, meet local engineers.\\nBeginner friendly.
URL:https://example.com/events/python
END:VEVENT
BEGIN:VEVENT
UID:noise-001@example.com
SUMMARY:Busy
DTSTART:20260511T100000Z
DTEND:20260511T110000Z
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_event_records_filters_noise_and_normalizes_fields():
    records = parse_ics_event_records(SAMPLE_ICS)

    assert records == [
        EventSourceRecord(
            external_id="event-001@example.com",
            title="Engineer Cafe Python Meetup",
            start="2026-05-10T10:00:00Z",
            end="2026-05-10T12:00:00Z",
            description="Bring a laptop, meet local engineers.\nBeginner friendly.",
            location="Engineer Cafe Main Hall",
            url="https://example.com/events/python",
            source="google_calendar",
        )
    ]


def test_event_record_adapter_builds_stable_title_and_content():
    event = EventSourceRecord(
        external_id="event-001@example.com",
        title="Engineer Cafe Python Meetup",
        start="2026-05-10T10:00:00Z",
        end="2026-05-10T12:00:00Z",
        description="Bring a laptop.",
        location="Engineer Cafe Main Hall",
        url="https://example.com/events/python",
    )

    title = event_record_to_kb_title(event)
    content = event_record_to_markdown(event)

    assert title.startswith("Event: Engineer Cafe Python Meetup (2026-05-10) [")
    assert len(title) <= 200
    assert "# Engineer Cafe Python Meetup" in content
    assert "- Start: 2026-05-10T10:00:00Z" in content
    assert "- Location: Engineer Cafe Main Hall" in content
    assert "Bring a laptop." in content


@pytest.mark.asyncio
async def test_plan_event_kb_records_uses_event_category_upload_path():
    events = parse_ics_event_records(SAMPLE_ICS)

    records = await plan_event_kb_records(events)

    assert len(records) == 1
    record = records[0]
    assert "content_embedding" not in record
    assert record["category"] == "event"
    assert record["language"] == "ja"
    assert record["source"] == "event_bridge:google_calendar:event-001@example.com"
    assert record["subcategory"] == "live_event"
    assert record["chunk_level"] == "document"
    assert record["metadata"]["bridge"] == "event_bridge"
    assert record["metadata"]["sync_source"] == "google_calendar"
    assert record["metadata"]["external_event_id"] == "event-001@example.com"
    assert record["metadata"]["file_type"] == "markdown"
    assert record["token_count"] > 0


@pytest.mark.asyncio
async def test_sync_event_kb_records_dry_run_does_not_embed_or_write():
    events = parse_ics_event_records(SAMPLE_ICS)
    supabase = MagicMock()

    async def fail_embed(text: str) -> list[float]:
        raise AssertionError("dry-run should not embed")

    result = await sync_event_kb_records(
        events,
        supabase_client=supabase,
        embedding_fn=fail_embed,
        dry_run=True,
    )

    assert result.planned_count == 1
    assert result.written_count == 0
    assert result.skipped_count == 0
    assert len(result.records) == 1
    supabase.table.assert_not_called()


@pytest.mark.asyncio
async def test_sync_event_kb_records_live_upserts_embedding_visible_rows():
    events = parse_ics_event_records(SAMPLE_ICS)
    supabase = MagicMock()
    table = supabase.table.return_value
    table.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "kb-1"}])

    async def fake_embed(text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    result = await sync_event_kb_records(
        events,
        supabase_client=supabase,
        embedding_fn=fake_embed,
        dry_run=False,
    )

    assert result.planned_count == 1
    assert result.written_count == 1
    assert result.skipped_count == 0
    supabase.table.assert_called_with("knowledge_base")
    upsert_record = table.upsert.call_args.args[0]
    assert upsert_record["content_embedding"] == [0.1, 0.2, 0.3]
    assert upsert_record["category"] == "event"
    assert table.upsert.call_args.kwargs == {"on_conflict": "title"}
