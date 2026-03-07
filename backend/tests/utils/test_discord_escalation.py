"""Tests for Discord escalation webhook notifications."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.utils.discord_escalation import send_escalation_notification

WEBHOOK_URL = "https://discord.com/api/webhooks/test/token"


class TestSendEscalationNotification:
    @pytest.mark.asyncio
    async def test_sends_notification_when_webhook_is_configured(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"DISCORD_ESCALATION_WEBHOOK_URL": WEBHOOK_URL}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await send_escalation_notification(
                    session_id="session-123",
                    reason="スタッフ対応が必要",
                    visitor_name="田中",
                    language="ja",
                )

        assert result is True
        mock_post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_gracefully_when_webhook_is_missing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO):
            with patch.dict("os.environ", {}, clear=True):
                result = await send_escalation_notification(
                    session_id="session-456",
                    reason="相談対応",
                    visitor_name="John",
                    language="en",
                )

        assert result is False
        assert "Discord escalation webhook not configured" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_http_error_gracefully(self, caplog: pytest.LogCaptureFixture) -> None:
        request = httpx.Request("POST", WEBHOOK_URL)
        response = httpx.Response(status_code=500, request=request)
        error = httpx.HTTPStatusError("server error", request=request, response=response)

        with patch.dict("os.environ", {"DISCORD_ESCALATION_WEBHOOK_URL": WEBHOOK_URL}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = error

                result = await send_escalation_notification(
                    session_id="session-789",
                    reason="緊急対応",
                    visitor_name=None,
                )

        assert result is False
        assert "Discord escalation notification failed (HTTP 500)" in caplog.text

    @pytest.mark.asyncio
    async def test_embed_contains_required_fields(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.dict("os.environ", {"DISCORD_ESCALATION_WEBHOOK_URL": WEBHOOK_URL}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                await send_escalation_notification(
                    session_id="session-999",
                    reason="来訪者がスタッフ案内を希望",
                    visitor_name="Kim",
                    language="ko",
                )

        payload = mock_post.call_args.kwargs["json"]
        embed = payload["embeds"][0]
        fields = {field["name"]: field["value"] for field in embed["fields"]}

        assert embed["title"] == "スタッフエスカレーション要求"
        assert embed["color"] == 0xFF0000
        assert fields["session_id"] == "session-999"
        assert fields["reason"] == "来訪者がスタッフ案内を希望"
        assert fields["visitor_name"] == "Kim"
        assert fields["timestamp"]
