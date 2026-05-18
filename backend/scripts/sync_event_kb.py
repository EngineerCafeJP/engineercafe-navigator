"""CLI for the additive event-to-KB bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.utils import secrets


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync ICS events into knowledge_base rows.")
    parser.add_argument("--ics-file", type=Path, help="Local ICS fixture/feed export to parse.")
    parser.add_argument(
        "--ics-url",
        default=secrets.get("GOOGLE_CALENDAR_ICAL_URL", ""),
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
    result = await run_event_kb_sync(
        ics_file=args.ics_file,
        ics_url=args.ics_url,
        dry_run=args.dry_run,
        include_spreadsheet=args.include_spreadsheet,
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


async def run_event_kb_sync(
    *,
    ics_file: Path | None = None,
    ics_url: str | None = None,
    dry_run: bool = False,
    include_spreadsheet: bool = False,
):
    """Run the event KB sync once and return the sync result."""

    import httpx

    from backend.services.event_kb_sync import (
        parse_ics_event_records,
        sync_event_kb_records,
    )

    resolved_ics_url = secrets.get("GOOGLE_CALENDAR_ICAL_URL", "") if ics_url is None else ics_url
    events = []
    if ics_file:
        ics_content = ics_file.read_text(encoding="utf-8")
        events.extend(parse_ics_event_records(ics_content))
    elif resolved_ics_url:
        async with httpx.AsyncClient() as client:
            response = await client.get(resolved_ics_url, timeout=30.0)
            response.raise_for_status()
            ics_content = response.text
        events.extend(parse_ics_event_records(ics_content))

    if include_spreadsheet:
        _export_secret_for_legacy_env_reader("EVENT_SHEET_GAS_URL")
        _export_secret_for_legacy_env_reader("EVENT_SHEET_GAS_TOKEN")
        from backend.services.sheets_event_source import SheetsEventSource

        events.extend(await SheetsEventSource().fetch_events())

    if not events:
        raise SystemExit(
            "No events were fetched. Configure --ics-file, --ics-url/"
            "GOOGLE_CALENDAR_ICAL_URL, or --include-spreadsheet with "
            "EVENT_SHEET_GAS_URL/TOKEN."
        )

    supabase_client = None
    if not dry_run:
        from supabase import create_client

        url = secrets.get("SUPABASE_URL", "") or ""
        key = secrets.get("SUPABASE_KEY", "") or ""
        if not url or not key:
            raise SystemExit("SUPABASE_URL and SUPABASE_KEY are required unless --dry-run is used")
        supabase_client = create_client(url, key)

    result = await sync_event_kb_records(
        events,
        supabase_client=supabase_client,
        dry_run=dry_run,
    )
    return result


def _export_secret_for_legacy_env_reader(key: str) -> None:
    value = secrets.get(key)
    if value is not None:
        import os

        os.environ.setdefault(key, value)


if __name__ == "__main__":
    asyncio.run(_main())
