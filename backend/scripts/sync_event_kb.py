"""CLI for the additive event-to-KB bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from supabase import create_client

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.event_kb_sync import parse_ics_event_records, sync_event_kb_records
from backend.services.sheets_event_source import SheetsEventSource


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync ICS events into knowledge_base rows.")
    parser.add_argument("--ics-file", type=Path, help="Local ICS fixture/feed export to parse.")
    parser.add_argument(
        "--ics-url",
        default=os.getenv("GOOGLE_CALENDAR_ICAL_URL", ""),
        help="ICS URL to fetch. Defaults to GOOGLE_CALENDAR_ICAL_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Plan records without embeddings or Supabase writes.",
    )
    parser.add_argument(
        "--include-spreadsheet",
        action="store_true",
        default=False,
        help="Also fetch public Cafe events from EVENT_SHEET_GAS_URL/TOKEN.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    events = []
    if args.ics_file:
        ics_content = args.ics_file.read_text(encoding="utf-8")
        events.extend(parse_ics_event_records(ics_content))
    elif args.ics_url:
        async with httpx.AsyncClient() as client:
            response = await client.get(args.ics_url, timeout=30.0)
            response.raise_for_status()
            ics_content = response.text
        events.extend(parse_ics_event_records(ics_content))

    if args.include_spreadsheet:
        events.extend(await SheetsEventSource().fetch_events())

    if not events:
        raise SystemExit(
            "No events were fetched. Configure --ics-file, --ics-url/"
            "GOOGLE_CALENDAR_ICAL_URL, or --include-spreadsheet with "
            "EVENT_SHEET_GAS_URL/TOKEN."
        )

    supabase_client = None
    if not args.dry_run:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise SystemExit("SUPABASE_URL and SUPABASE_KEY are required unless --dry-run is used")
        supabase_client = create_client(url, key)

    result = await sync_event_kb_records(
        events,
        supabase_client=supabase_client,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "planned_count": result.planned_count,
                "written_count": result.written_count,
                "skipped_count": result.skipped_count,
                "titles": [record["title"] for record in result.records],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
