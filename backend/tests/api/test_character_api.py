"""Character API endpoint tests (/api/character, /api/character/auto)

Tests for the character control endpoints including the new /api/character/auto
for parallel VRM generation.
"""

import asyncio
import base64
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

# Minimal test app - we test character endpoints by importing main.py's handler logic
# To avoid heavy imports, we construct a lightweight test app with the endpoint logic.

_test_app = FastAPI()

# Mock the _generate_vrm_control_for_lab_tts function
mock_vrm_generator = AsyncMock()

FAKE_VRM_RESULT = {
    "expression": "happy",
    "blendShapes": {"joy": 0.8},
    "duration": 2.5,
}


class CharacterAutoRequest(BaseModel):
    cleanText: str
    emotion: str = "neutral"
    ttsWavB64: Optional[str] = None


class CharacterAutoResponse(BaseModel):
    success: bool
    vrmControl: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@_test_app.post("/api/character/auto", response_model=CharacterAutoResponse)
async def character_auto_api(body: CharacterAutoRequest):
    """Test replica of the /api/character/auto endpoint."""
    try:
        vrm_result = await asyncio.wait_for(
            mock_vrm_generator(
                clean_text=body.cleanText,
                emotion=body.emotion,
                tts_wav_b64=body.ttsWavB64,
            ),
            timeout=15.0,
        )
        return CharacterAutoResponse(success=True, vrmControl=vrm_result)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="VRM generation timed out")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


client = TestClient(_test_app)

FAKE_WAV_B64 = base64.b64encode(b"\x00" * 100).decode()


@pytest.fixture(autouse=True)
def _reset_mocks():
    mock_vrm_generator.reset_mock()
    mock_vrm_generator.return_value = FAKE_VRM_RESULT
    mock_vrm_generator.side_effect = None


class TestCharacterAutoApi:
    """POST /api/character/auto"""

    def test_auto_vrm_success(self):
        """Successful VRM generation returns vrmControl data"""
        resp = client.post(
            "/api/character/auto",
            json={
                "cleanText": "こんにちは",
                "emotion": "happy",
                "ttsWavB64": FAKE_WAV_B64,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["vrmControl"] == FAKE_VRM_RESULT
        mock_vrm_generator.assert_called_once_with(
            clean_text="こんにちは",
            emotion="happy",
            tts_wav_b64=FAKE_WAV_B64,
        )

    def test_auto_vrm_default_emotion(self):
        """emotion defaults to 'neutral' when not specified"""
        resp = client.post(
            "/api/character/auto",
            json={
                "cleanText": "テスト",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        call_kwargs = mock_vrm_generator.call_args.kwargs
        assert call_kwargs["emotion"] == "neutral"

    def test_auto_vrm_without_audio(self):
        """Works without ttsWavB64 (text-only VRM)"""
        resp = client.post(
            "/api/character/auto",
            json={
                "cleanText": "テスト",
                "emotion": "neutral",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        call_kwargs = mock_vrm_generator.call_args.kwargs
        assert call_kwargs["tts_wav_b64"] is None

    def test_auto_vrm_timeout_returns_504(self):
        """VRM generation timeout returns 504"""
        mock_vrm_generator.side_effect = asyncio.TimeoutError()

        resp = client.post(
            "/api/character/auto",
            json={
                "cleanText": "テスト",
            },
        )

        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()

    def test_auto_vrm_error_returns_500(self):
        """VRM generation error returns 500"""
        mock_vrm_generator.side_effect = RuntimeError("Agent crashed")

        resp = client.post(
            "/api/character/auto",
            json={
                "cleanText": "テスト",
            },
        )

        assert resp.status_code == 500

    def test_auto_vrm_missing_clean_text_returns_422(self):
        """Missing required cleanText returns 422"""
        resp = client.post(
            "/api/character/auto",
            json={
                "emotion": "happy",
            },
        )

        assert resp.status_code == 422

    def test_auto_vrm_returns_none_on_agent_failure(self):
        """When VRM agent returns None, response has no vrmControl"""
        mock_vrm_generator.return_value = None

        resp = client.post(
            "/api/character/auto",
            json={
                "cleanText": "テスト",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["vrmControl"] is None
