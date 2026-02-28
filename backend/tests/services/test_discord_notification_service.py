"""Tests for backend.services.discord_notification_service."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services.discord_notification_service import (
    DiscordNotificationService,
)

WEBHOOK_URL = "https://discord.com/api/webhooks/test/token"


class TestSendNotificationSuccess:
    """test_send_notification_success: 204 response returns True."""

    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": WEBHOOK_URL}):
            service = DiscordNotificationService()

            with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await service.send_notification(
                    title="Test Title",
                    message="Test message body",
                    severity="info",
                )

        assert result is True
        mock_post.assert_awaited_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == WEBHOOK_URL
        payload = call_kwargs[1]["json"]
        assert payload["embeds"][0]["title"] == "Test Title"
        assert payload["embeds"][0]["description"] == "Test message body"


class TestSendNotificationWebhookNotSet:
    """test_send_notification_webhook_not_set: missing env var returns False gracefully."""

    @pytest.mark.asyncio
    async def test_send_notification_webhook_not_set(self):
        with patch.dict("os.environ", {}, clear=False):
            # Ensure DISCORD_WEBHOOK_URL is absent
            import os

            os.environ.pop("DISCORD_WEBHOOK_URL", None)

            service = DiscordNotificationService()

            with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
                result = await service.send_notification(
                    title="Should Not Send",
                    message="This notification must not be sent",
                )

        assert result is False
        mock_post.assert_not_awaited()


class TestSendNotificationNetworkError:
    """test_send_notification_network_error: httpx.RequestError returns False without raising."""

    @pytest.mark.asyncio
    async def test_send_notification_network_error(self):
        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": WEBHOOK_URL}):
            service = DiscordNotificationService()

            with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = httpx.RequestError("connection refused")

                # Must not raise — should return False
                result = await service.send_notification(
                    title="Network Failure",
                    message="This call should swallow the exception",
                    severity="critical",
                )

        assert result is False


class TestSendNotificationSeverityColors:
    """test_send_notification_severity_colors: verify embed color codes per severity."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "severity, expected_color",
        [
            ("critical", 0xFF0000),
            ("warning", 0xFFFF00),
            ("info", 0x0000FF),
        ],
    )
    async def test_send_notification_severity_colors(self, severity, expected_color):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": WEBHOOK_URL}):
            service = DiscordNotificationService()

            with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                await service.send_notification(
                    title="Color Test",
                    message="Checking color",
                    severity=severity,
                )

                call_kwargs = mock_post.call_args
                payload = call_kwargs[1]["json"]
                assert payload["embeds"][0]["color"] == expected_color, (
                    f"Expected color {hex(expected_color)} for severity '{severity}', "
                    f"got {hex(payload['embeds'][0]['color'])}"
                )


class TestSendNotificationWithMetadata:
    """test_send_notification_with_metadata: metadata dict is included as embed fields."""

    @pytest.mark.asyncio
    async def test_send_notification_with_metadata(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        metadata = {"session_id": "abc123", "user_count": 42, "region": "jp-west"}

        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": WEBHOOK_URL}):
            service = DiscordNotificationService()

            with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await service.send_notification(
                    title="Metadata Test",
                    message="Should include fields",
                    severity="warning",
                    metadata=metadata,
                )

        assert result is True

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        fields = payload["embeds"][0]["fields"]

        field_map = {f["name"]: f["value"] for f in fields}
        assert field_map["session_id"] == "abc123"
        assert field_map["user_count"] == "42"
        assert field_map["region"] == "jp-west"

        # All fields must be marked inline=True
        for field in fields:
            assert field["inline"] is True
