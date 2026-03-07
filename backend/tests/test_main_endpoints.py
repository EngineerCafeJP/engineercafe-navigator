"""Tests for backend/main.py endpoint fixes (Sprint 5)"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from starlette.requests import Request


def _mock_request():
    """Create a minimal Starlette Request for direct endpoint calls.

    slowapi requires isinstance(request, Request), so we build a real
    Request object backed by a minimal ASGI scope.
    """
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "query_string": b"",
        "headers": [],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


class TestHealthCheck:
    def test_health_check_returns_200(self):
        from backend.main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # CI環境ではSupabase/LLM未接続のため "degraded" になりうる
        assert data["status"] in ("ok", "degraded")
        assert data["service"] == "engineer-cafe-navigator-backend"


class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_chat_awaits_get_workflow(self):
        """get_workflow() must be awaited (it's async)"""
        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(
            return_value={
                "answer": "テスト回答",
                "emotion": "neutral",
                "metadata": {"vrm_control": {"name": "idle", "duration": 1000, "keyframes": []}},
            }
        )

        with patch(
            "backend.workflows.main_workflow.get_workflow",
            new_callable=AsyncMock,
            return_value=mock_workflow,
        ):
            from backend.main import chat, ChatRequest

            body = ChatRequest(query="テスト", session_id="s1")
            response = await chat(_mock_request(), body)
            assert response.answer == "テスト回答"
            assert response.vrm_control == {"name": "idle", "duration": 1000, "keyframes": []}

    @pytest.mark.asyncio
    async def test_chat_error_no_leak(self):
        """Exception detail should NOT contain internal error message"""
        with patch(
            "backend.workflows.main_workflow.get_workflow",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection failed: password=secret123"),
        ):
            from backend.main import chat, ChatRequest
            from fastapi import HTTPException

            body = ChatRequest(query="テスト", session_id="s1")
            with pytest.raises(HTTPException) as exc_info:
                await chat(_mock_request(), body)
            assert exc_info.value.status_code == 500
            assert "secret" not in exc_info.value.detail
            assert "internal error" in exc_info.value.detail.lower()


class TestInvokeEndpoint:
    @pytest.mark.asyncio
    async def test_invoke_success(self):
        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(
            return_value={
                "answer": "回答",
                "emotion": "neutral",
                "metadata": {},
            }
        )
        with patch(
            "backend.workflows.main_workflow.get_workflow",
            new_callable=AsyncMock,
            return_value=mock_workflow,
        ):
            from backend.main import invoke_agent, ChatRequest

            body = ChatRequest(query="テスト", session_id="s1")
            response = await invoke_agent(_mock_request(), body)
            assert response["status"] == "success"

    @pytest.mark.asyncio
    async def test_invoke_error_no_leak(self):
        with patch(
            "backend.workflows.main_workflow.get_workflow",
            new_callable=AsyncMock,
            side_effect=Exception("Internal DB error"),
        ):
            from backend.main import invoke_agent, ChatRequest
            from fastapi import HTTPException

            body = ChatRequest(query="テスト", session_id="s1")
            with pytest.raises(HTTPException) as exc_info:
                await invoke_agent(_mock_request(), body)
            assert "Internal DB error" not in exc_info.value.detail


class TestVoiceEndpoint:
    @pytest.mark.asyncio
    async def test_voice_error_no_leak(self):
        """Voice endpoint should not leak internal errors"""
        mock_agent = AsyncMock()
        mock_agent.text_to_speech = AsyncMock(side_effect=Exception("GCP credential expired"))

        with patch("backend.main._get_voice_agent", return_value=mock_agent):
            from backend.main import voice_api, VoiceRequest
            from fastapi import HTTPException

            body = VoiceRequest(action="text_to_speech", text="hello")
            with pytest.raises(HTTPException) as exc_info:
                await voice_api(_mock_request(), body)
            assert "credential" not in exc_info.value.detail.lower()


class TestSlidesEndpoint:
    @pytest.mark.asyncio
    async def test_slides_error_no_leak(self):
        with patch("backend.agents.slide_agent.SlideAgent") as mock_class:
            mock_class.return_value.handle_slide_action = AsyncMock(
                side_effect=Exception("Slide DB error")
            )
            from backend.main import slides_api, SlidesRequest
            from fastapi import HTTPException

            body = SlidesRequest(action="narrate")
            with pytest.raises(HTTPException) as exc_info:
                await slides_api(_mock_request(), body)
            assert "Slide DB error" not in exc_info.value.detail


class TestCORSConfiguration:
    def test_cors_default_origins(self, monkeypatch):
        """Without ALLOWED_ORIGINS env var, defaults are used"""
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        import importlib
        import backend.main

        importlib.reload(backend.main)
        assert "http://localhost:3000" in backend.main._allowed_origins
        assert "http://localhost:3001" in backend.main._allowed_origins

    def test_cors_custom_origins(self, monkeypatch):
        """With ALLOWED_ORIGINS set, custom origins are used"""
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.com,https://app.example.com")
        import importlib
        import backend.main

        importlib.reload(backend.main)
        assert "https://example.com" in backend.main._allowed_origins
        assert "https://app.example.com" in backend.main._allowed_origins
        # Restore
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        importlib.reload(backend.main)


class TestCharacterEndpoint:
    @pytest.mark.asyncio
    async def test_character_error_no_leak(self):
        from backend.main import character_api, CharacterRequest

        # character_api currently has a simple try/except with detail=str(e)
        # After fix, it should use generic message
        # We need to mock to force an exception
        with patch(
            "backend.main.CharacterResponse",
            side_effect=Exception("Some internal error"),
        ):
            from fastapi import HTTPException

            body = CharacterRequest(action="test")
            with pytest.raises(HTTPException) as exc_info:
                await character_api(_mock_request(), body)
            assert "Some internal error" not in exc_info.value.detail
