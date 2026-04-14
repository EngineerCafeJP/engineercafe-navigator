"""Tests for backend/main.py endpoint fixes (Sprint 5)"""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
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


class TestLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_prewarms_checkpointer(self):
        import backend.main as main_mod

        app = MagicMock()
        session_task_manager = AsyncMock()

        with (
            patch("backend.utils.env_validator.validate_startup"),
            patch("backend.utils.checkpoint_cleanup.CheckpointCleanup", return_value=MagicMock()),
            patch("backend.main.get_session_task_manager", return_value=session_task_manager),
            patch("backend.utils.checkpointer.prewarm_checkpointer", new=AsyncMock()) as prewarm,
            patch("backend.utils.checkpointer.close_checkpointer", new=AsyncMock()),
            patch("backend.utils.store.close_store", new=AsyncMock()),
        ):
            async with main_mod.lifespan(app):
                prewarm.assert_awaited_once()
                session_task_manager.initialize.assert_awaited_once()

        session_task_manager.shutdown.assert_awaited_once()


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

    @pytest.mark.asyncio
    async def test_chat_forwards_image_data_to_workflow(self):
        with patch(
            "backend.main._run_workflow_with_tracking",
            new_callable=AsyncMock,
            return_value={
                "answer": "OCR結果です",
                "emotion": "neutral",
                "metadata": {},
            },
        ) as mock_run:
            from backend.main import chat, ChatRequest

            body = ChatRequest(query="画像を読んで", session_id="s1", image_data="base64-image")
            response = await chat(_mock_request(), body)

            assert response.answer == "OCR結果です"
            mock_run.assert_awaited_once_with(
                payload={
                    "query": "画像を読んで",
                    "session_id": "s1",
                    "language": "ja",
                    "context": {},
                    "visitor_id": None,
                    "image_data": "base64-image",
                },
                session_id="s1",
            )

    @pytest.mark.asyncio
    async def test_chat_strips_emotion_tags_from_answer(self):
        """Emotion tags in answer text should be stripped (#350)"""
        with patch(
            "backend.main._run_workflow_with_tracking",
            new_callable=AsyncMock,
            return_value={
                "answer": "[relaxed]営業時間は9時からです[/relaxed]",
                "emotion": "relaxed",
                "metadata": {},
            },
        ):
            from backend.main import chat, ChatRequest

            body = ChatRequest(query="営業時間は？", session_id="s1")
            response = await chat(_mock_request(), body)
            assert "[relaxed]" not in response.answer
            assert "[/relaxed]" not in response.answer
            assert "営業時間は9時からです" in response.answer
            assert response.emotion == "relaxed"


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

    @pytest.mark.asyncio
    async def test_voice_invalid_tts_provider_returns_400(self):
        from backend.main import voice_api, VoiceRequest
        from fastapi import HTTPException

        body = VoiceRequest(action="text_to_speech", text="hello", ttsProvider="vocaloid")
        with pytest.raises(HTTPException) as exc_info:
            await voice_api(_mock_request(), body)
        assert exc_info.value.status_code == 400
        detail_lower = exc_info.value.detail.lower()
        assert "ttsprovider" in detail_lower and "vocaloid" in detail_lower

    @pytest.mark.asyncio
    async def test_voice_tts_provider_piper_uses_per_provider_agent(self):
        mock_agent = AsyncMock()
        mock_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "d2F2",
                "format": "audio/wav",
                "emotion": "neutral",
            }
        )
        with patch(
            "backend.main._get_voice_agent_for_provider_key", return_value=mock_agent
        ) as get_p:
            with patch("backend.main._get_voice_agent") as get_default:
                from backend.main import voice_api, VoiceRequest

                body = VoiceRequest(action="text_to_speech", text="hello", ttsProvider="piper")
                resp = await voice_api(_mock_request(), body)
                get_p.assert_called_once_with("piper")
                get_default.assert_not_called()
                assert resp.success is True
                assert resp.audioResponse == "d2F2"


class TestSlidesEndpoint:
    @pytest.mark.asyncio
    async def test_slides_error_no_leak(self):
        mock_agent = AsyncMock()
        mock_agent.handle_slide_action = AsyncMock(side_effect=Exception("Slide DB error"))
        with patch("backend.main._get_slide_agent", return_value=mock_agent):
            from backend.main import slides_api, SlidesRequest
            from fastapi import HTTPException

            body = SlidesRequest(action="narrate")
            with pytest.raises(HTTPException) as exc_info:
                await slides_api(_mock_request(), body)
            assert "Slide DB error" not in exc_info.value.detail


class TestSlidesContentEndpoint:
    @pytest.mark.asyncio
    async def test_slides_content_ja(self):
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/slides/content", json={"language": "ja"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "markdown" in data
        assert "marp: true" in data["markdown"]
        assert data["narrationData"] is not None
        assert len(data["narrationData"]["slides"]) > 0

    @pytest.mark.asyncio
    async def test_slides_content_en(self):
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/slides/content", json={"language": "en"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["markdown"] is not None

    @pytest.mark.asyncio
    async def test_slides_content_invalid_language_falls_back_to_ja(self):
        """Unsupported language falls back to Japanese content."""
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/slides/content", json={"language": "zh"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["metadata"]["language"] == "ja"
        assert "marp: true" in data["markdown"]

    @pytest.mark.asyncio
    async def test_slides_content_path_traversal_blocked(self):
        """Path traversal attempts are sanitized to default language."""
        from backend.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/slides/content", json={"language": "../../etc"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["metadata"]["language"] == "ja"


class TestCORSConfiguration:
    def test_cors_default_origins(self, monkeypatch):
        """Without ALLOWED_ORIGINS env var, production default is used"""
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        monkeypatch.delenv("FRONTEND_PRODUCTION_ORIGIN", raising=False)
        import importlib
        import backend.main

        importlib.reload(backend.main)
        assert "https://frontend-delta-six-20.vercel.app" in backend.main.ALLOWED_ORIGINS

    def test_cors_uses_frontend_origin_override(self, monkeypatch):
        """FRONTEND_PRODUCTION_ORIGIN becomes the default when ALLOWED_ORIGINS is absent."""
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        monkeypatch.setenv(
            "FRONTEND_PRODUCTION_ORIGIN",
            "https://frontend-qwbhreahe-kousukes-projects-8e2831b8.vercel.app",
        )
        import importlib
        import backend.main

        importlib.reload(backend.main)
        assert (
            "https://frontend-qwbhreahe-kousukes-projects-8e2831b8.vercel.app"
            in backend.main.ALLOWED_ORIGINS
        )

    def test_cors_custom_origins(self, monkeypatch):
        """With ALLOWED_ORIGINS set, custom origins are used"""
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.com,https://app.example.com")
        import importlib
        import backend.main

        importlib.reload(backend.main)
        assert "https://example.com" in backend.main.ALLOWED_ORIGINS
        assert "https://app.example.com" in backend.main.ALLOWED_ORIGINS
        # Restore
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        monkeypatch.delenv("FRONTEND_PRODUCTION_ORIGIN", raising=False)
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

    @pytest.mark.asyncio
    async def test_character_get_default_state(self):
        """GET /api/character returns default state (#349)"""
        from backend.main import character_get_api

        response = await character_get_api(_mock_request())
        assert response["success"] is True
        assert response["current_emotion"] == "neutral"
        assert response["current_expression"] == "neutral"

    @pytest.mark.asyncio
    async def test_character_get_supported_features(self):
        """GET /api/character?action=supported_features returns expressions list (#349)"""
        from backend.main import character_get_api

        response = await character_get_api(_mock_request(), action="supported_features")
        assert response["success"] is True
        assert "neutral" in response["expressions"]
        assert "happy" in response["expressions"]
        assert isinstance(response["animations"], list)


class TestBearerAuthSupport:
    """Tests for Authorization: Bearer support in verify_api_key (#353)"""

    @pytest.mark.asyncio
    async def test_bearer_token_accepted(self):
        """verify_api_key should accept Authorization: Bearer header"""

        with patch("backend.main._API_SECRET_KEY", "test-secret-key"):
            from backend.main import verify_api_key

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/character",
                "query_string": b"",
                "headers": [
                    (b"authorization", b"Bearer test-secret-key"),
                ],
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 12345),
            }
            request = Request(scope)
            # Should NOT raise
            await verify_api_key(request)

    @pytest.mark.asyncio
    async def test_bearer_token_rejected_when_wrong(self):
        """verify_api_key should reject incorrect Bearer token"""
        from fastapi import HTTPException

        with patch("backend.main._API_SECRET_KEY", "test-secret-key"):
            from backend.main import verify_api_key

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/character",
                "query_string": b"",
                "headers": [
                    (b"authorization", b"Bearer wrong-key"),
                ],
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 12345),
            }
            request = Request(scope)
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(request)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_x_api_key_still_works(self):
        """X-API-Key header should still be accepted"""
        with patch("backend.main._API_SECRET_KEY", "test-secret-key"):
            from backend.main import verify_api_key

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/character",
                "query_string": b"",
                "headers": [
                    (b"x-api-key", b"test-secret-key"),
                ],
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 12345),
            }
            request = Request(scope)
            # Should NOT raise
            await verify_api_key(request)
