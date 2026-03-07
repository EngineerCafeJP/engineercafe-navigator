"""Discord webhook helper for staff escalation notifications."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_EMBED_COLOR_RED = 0xFF0000
_EMBED_TITLE = "スタッフエスカレーション要求"


async def send_escalation_notification(
    session_id: str,
    reason: str,
    visitor_name: Optional[str] = None,
    language: str = "ja",
) -> bool:
    """Send a staff escalation notification to Discord.

    Returns ``False`` on configuration or transport failures and never raises.
    """
    webhook_url = os.environ.get("DISCORD_ESCALATION_WEBHOOK_URL")
    timestamp = datetime.now(timezone.utc).isoformat()
    visitor_value = visitor_name or "-"

    if not webhook_url:
        logger.info(
            (
                "Discord escalation webhook not configured; "
                "session_id=%s, reason=%s, visitor_name=%s, language=%s"
            ),
            session_id,
            reason,
            visitor_value,
            language,
        )
        return False

    payload = {
        "embeds": [
            {
                "title": _EMBED_TITLE,
                "description": "スタッフによる対応が必要な受付セッションです。",
                "color": _EMBED_COLOR_RED,
                "fields": [
                    {"name": "session_id", "value": session_id, "inline": True},
                    {"name": "reason", "value": reason, "inline": False},
                    {"name": "visitor_name", "value": visitor_value, "inline": True},
                    {"name": "timestamp", "value": timestamp, "inline": True},
                ],
                "timestamp": timestamp,
                "footer": {"text": f"language: {language}"},
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        return True
    except httpx.RequestError as exc:
        logger.warning("Discord escalation notification failed (network error): %s", exc)
        return False
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Discord escalation notification failed (HTTP %s): %s",
            exc.response.status_code,
            exc,
        )
        return False
