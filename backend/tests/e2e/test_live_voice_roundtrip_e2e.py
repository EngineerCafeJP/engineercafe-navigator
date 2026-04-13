"""Live voice round-trip tests using real STT, LangGraph, and TTS providers."""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from backend.main import app
from backend.tests.e2e.conftest import assert_keyword_groups

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]

VALID_API_HEADERS = {"X-API-Key": "test-secret-key-12345"}


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    """Stabilize auth regardless of the developer's local environment."""
    import backend.main as main_mod

    test_key = "test-secret-key-12345"
    monkeypatch.setenv("API_SECRET_KEY", test_key)
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", test_key)


@pytest_asyncio.fixture
async def live_api_client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestLiveVoiceRoundTripE2E:
    async def test_voice_round_trip_reflects_langgraph_answer(
        self,
        _check_e2e_env,
        live_api_client: httpx.AsyncClient,
        voice_sample_audio_b64: str,
    ):
        """
        実音声 fixture を STT し、その transcript で LangGraph に問い合わせ、
        返答をそのまま TTS できることを確認する。
        """
        session_id = str(uuid.uuid4())

        stt_response = await live_api_client.post(
            "/api/voice",
            headers=VALID_API_HEADERS,
            json={
                "action": "speech_to_text",
                "audioData": voice_sample_audio_b64,
                "language": "en",
                "sessionId": session_id,
            },
            timeout=90,
        )
        assert stt_response.status_code == 200, stt_response.text
        stt_data = stt_response.json()
        assert stt_data["success"] is True, stt_data
        transcript = stt_data.get("transcript", "")
        detected_language = stt_data.get("detectedLanguage") or "en"
        assert transcript, stt_data
        assert_keyword_groups(
            transcript,
            [["engineer cafe"], ["tell me about", "about engineer cafe"]],
            msg="voice:stt",
        )

        chat_response = await live_api_client.post(
            "/api/chat",
            headers=VALID_API_HEADERS,
            json={
                "query": transcript,
                "language": detected_language,
                "session_id": session_id,
            },
            timeout=90,
        )
        assert chat_response.status_code == 200, chat_response.text
        chat_data = chat_response.json()
        answer = chat_data["answer"]
        emotion = chat_data["emotion"]
        assert answer, chat_data
        assert emotion, chat_data
        assert_keyword_groups(
            answer,
            [
                ["engineer cafe", "エンジニアカフェ"],
                ["free", "無料"],
                ["coworking", "コワーキング"],
            ],
            msg="voice:chat",
        )

        tts_response = await live_api_client.post(
            "/api/voice",
            headers=VALID_API_HEADERS,
            json={
                "action": "text_to_speech",
                "text": answer,
                "language": detected_language,
                "emotion": emotion,
                "sessionId": session_id,
            },
            timeout=90,
        )
        assert tts_response.status_code == 200, tts_response.text
        tts_data = tts_response.json()
        assert tts_data["success"] is True, tts_data
        assert tts_data.get("audioResponse"), tts_data
        assert len(tts_data["audioResponse"]) > 100, "voice:tts returned unexpectedly small audio"
        assert tts_data.get("audioFormat") in {"audio/wav", "audio/mpeg"}, tts_data
        assert tts_data.get("sessionId") == session_id, tts_data
        assert (
            tts_data.get("emotion") == emotion
        ), "voice:tts did not preserve the LangGraph-selected emotion"
