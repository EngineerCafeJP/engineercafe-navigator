"""
Discord Webhook notification service.

Sends structured embed notifications to a Discord channel via Webhook.
Supports severity levels: critical (red), warning (yellow), info (blue).

Designed as fire-and-forget: failures are logged but never raised to callers.
Use get_discord_notification_service() for singleton access.
"""

import logging
import os
from datetime import datetime
from typing import Literal, Optional

import httpx

logger = logging.getLogger(__name__)

_COLOR_MAP: dict[str, int] = {
    "critical": 0xFF0000,
    "warning": 0xFFFF00,
    "info": 0x0000FF,
}


class DiscordNotificationService:
    """
    Send notifications to Discord via Webhook embeds.

    If DISCORD_WEBHOOK_URL is not set, all send operations silently return
    False without raising. Use get_discord_notification_service() for
    singleton access.
    """

    def __init__(self) -> None:
        self._webhook_url: str | None = os.environ.get("DISCORD_WEBHOOK_URL")
        self._client: httpx.AsyncClient = httpx.AsyncClient(timeout=10.0)
        if not self._webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not set, notifications disabled")

    async def send_notification(
        self,
        title: str,
        message: str,
        severity: Literal["critical", "warning", "info"] = "info",
        metadata: dict | None = None,
    ) -> bool:
        """
        Send a notification to Discord via Webhook.

        Args:
            title: Embed title text.
            message: Embed description / body text.
            severity: One of ``"critical"``, ``"warning"``, or ``"info"``.
                      Determines the embed sidebar color.
            metadata: Optional key-value pairs rendered as inline embed fields.

        Returns:
            ``True`` if the webhook POST succeeded (2xx response), ``False``
            otherwise. Never raises.
        """
        if not self._webhook_url:
            return False

        color = _COLOR_MAP.get(severity, _COLOR_MAP["info"])

        fields = [{"name": k, "value": str(v), "inline": True} for k, v in (metadata or {}).items()]

        payload: dict = {
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": color,
                    "fields": fields,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]
        }

        try:
            response = await self._client.post(self._webhook_url, json=payload)
            response.raise_for_status()
            return True
        except httpx.RequestError as exc:
            logger.warning(
                "Discord notification failed (network error): %s",
                exc,
            )
            return False
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Discord notification failed (HTTP %s): %s",
                exc.response.status_code,
                exc,
            )
            return False
        except Exception as exc:
            logger.warning("Discord notification failed (unexpected error): %s", exc)
            return False

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()


# ======================================================================
# Singleton access
# ======================================================================

_discord_notification_service: Optional[DiscordNotificationService] = None


def get_discord_notification_service() -> DiscordNotificationService:
    """
    Return the singleton :class:`DiscordNotificationService`.

    The instance is created on first call and reused thereafter.
    """
    global _discord_notification_service  # noqa: PLW0603
    if _discord_notification_service is None:
        _discord_notification_service = DiscordNotificationService()
    return _discord_notification_service
