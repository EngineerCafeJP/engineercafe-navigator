"""Voice API endpoint tests (/api/voice)

main.py のインポートはテスト環境のモジュールパス問題を避けるため行わず、
test_knowledge_api.py と同様にテスト用 FastAPI アプリを構成してエンドポイントを再現する。
"""

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional

# =============================================================================
# Voice API Models (main.py から複製)
# =============================================================================


class VoiceRequest(BaseModel):
    action: str
    audioData: Optional[str] = None
    sessionId: Optional[str] = None
    language: Optional[str] = "ja"
    text: Optional[str] = None
    streaming: Optional[bool] = False
    conversationStage: Optional[str] = None
    emotion: Optional[str] = None
    outputEncoding: Optional[str] = None


class VoiceResponse(BaseModel):
    success: bool
    transcript: Optional[str] = None
    response: Optional[str] = None
    audioResponse: Optional[str] = None
    audioFormat: Optional[str] = None
    emotion: Optional[str] = None
    sessionId: Optional[str] = None
    error: Optional[str] = None
    detectedLanguage: Optional[str] = None
    confidence: Optional[float] = None
    interruptStatus: Optional[str] = None


# =============================================================================
# Test app setup
# =============================================================================

# main.py の voice_api エンドポイントロジックを再現するテスト用アプリ。
# voice_agent / stt_agent はモックで注入する。

mock_voice_agent = MagicMock()
mock_stt_agent = MagicMock()
mock_session_task_manager = MagicMock()

_test_app = FastAPI()


async def _handle_stt_test(request: VoiceRequest) -> VoiceResponse:
    """Shared STT processing for speech_to_text action (test version)."""
    if not request.audioData:
        raise HTTPException(status_code=400, detail="Missing audioData")

    audio_bytes = base64.b64decode(request.audioData)

    stt_result = await mock_stt_agent.speech_to_text(
        audio_bytes,
        language=request.language,
        conversation_stage=request.conversationStage,
    )

    if not stt_result["success"]:
        return VoiceResponse(
            success=False,
            error=stt_result.get("error", "STT failed"),
            sessionId=request.sessionId,
        )

    return VoiceResponse(
        success=True,
        transcript=stt_result["transcript"],
        emotion="neutral",
        detectedLanguage=stt_result.get("language"),
        confidence=stt_result.get("confidence"),
        sessionId=request.sessionId,
    )


@_test_app.post("/api/voice", response_model=VoiceResponse)
async def voice_api(request: VoiceRequest):
    try:
        if request.action == "text_to_speech":
            if not request.text or not request.text.strip():
                raise HTTPException(status_code=400, detail="Missing text for text_to_speech")

            result = await mock_voice_agent.text_to_speech(
                text=request.text,
                language=request.language or "ja",
                emotion=request.emotion,
            )
            if not result.get("success"):
                return VoiceResponse(
                    success=False,
                    error=result.get("error", "TTS failed"),
                    emotion=result.get("emotion"),
                    audioFormat=result.get("format"),
                    sessionId=request.sessionId,
                )

            audio_b64 = result.get("audioResponse")
            audio_format = result.get("format")

            if (
                request.outputEncoding
                and request.outputEncoding.lower() == "mp3"
                and audio_format == "audio/wav"
                and audio_b64
            ):
                try:
                    from backend.utils.audio_encode import wav_base64_to_mp3_base64_async

                    audio_b64 = await wav_base64_to_mp3_base64_async(audio_b64)
                    audio_format = "audio/mpeg"
                except Exception:
                    raise HTTPException(
                        status_code=502,
                        detail="Audio encoding to MP3 failed (ensure ffmpeg is installed).",
                    )

            return VoiceResponse(
                success=True,
                audioResponse=audio_b64,
                audioFormat=audio_format,
                emotion=result.get("emotion"),
                sessionId=request.sessionId,
            )

        elif request.action == "set_language":
            return VoiceResponse(success=True, sessionId=request.sessionId)

        elif request.action == "speech_to_text":
            return await _handle_stt_test(request)

        elif request.action == "interrupt":
            if not request.sessionId:
                raise HTTPException(status_code=400, detail="Missing sessionId for interrupt")

            cancelled = await mock_session_task_manager.cancel_all_tasks(request.sessionId)
            return VoiceResponse(
                success=True,
                sessionId=request.sessionId,
                interruptStatus="cancelled" if cancelled else "no_active_task",
            )

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


client = TestClient(_test_app)


# =============================================================================
# Helpers
# =============================================================================

SAMPLE_SESSION_ID = "test-session-001"


def _fake_wav_b64() -> str:
    """最小限のダミー WAV の base64 文字列"""
    return base64.b64encode(b"\x00" * 100).decode()


@pytest.fixture(autouse=True)
def _reset_mocks():
    """各テスト前にモックをリセット"""
    mock_voice_agent.reset_mock()
    mock_stt_agent.reset_mock()
    mock_session_task_manager.reset_mock()
    mock_session_task_manager.cancel_all_tasks = AsyncMock(return_value=False)


# =============================================================================
# text_to_speech
# =============================================================================


class TestTextToSpeech:
    """POST /api/voice  action=text_to_speech"""

    def test_tts_success(self):
        """TTS 成功時に audioResponse を返す"""
        mock_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "base64audio==",
                "emotion": "happy",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "こんにちは",
                "language": "ja",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["audioResponse"] == "base64audio=="
        assert body["emotion"] == "happy"
        assert body["sessionId"] == SAMPLE_SESSION_ID

    def test_tts_missing_text_returns_400(self):
        """text が空の場合は 400 エラー"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )
        assert resp.status_code == 400

    def test_tts_null_text_returns_400(self):
        """text が null の場合は 400 エラー"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": None,
                "sessionId": SAMPLE_SESSION_ID,
            },
        )
        assert resp.status_code == 400

    def test_tts_whitespace_only_returns_400(self):
        """text が空白のみの場合は 400 エラー"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "   ",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )
        assert resp.status_code == 400

    def test_tts_failure_returns_error(self):
        """TTS 失敗時に success=False + error を返す"""
        mock_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": False,
                "error": "Google TTS unavailable",
                "emotion": "neutral",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "テスト",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "unavailable" in body["error"]

    def test_tts_exception_returns_500(self):
        """TTS が例外を投げた場合は 500 エラー"""
        mock_voice_agent.text_to_speech = AsyncMock(side_effect=RuntimeError("unexpected"))

        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "テスト",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 500


# =============================================================================
# outputEncoding mp3 (WAV → MP3)
# =============================================================================


class TestOutputEncodingMp3:
    """outputEncoding=mp3 で WAV を MP3 に変換する経路"""

    @pytest.mark.asyncio
    async def test_wav_to_mp3_async_uses_executor(self, monkeypatch):
        call_count = 0

        def fake_wav_to_mp3(wav_b64: str) -> str:
            nonlocal call_count
            call_count += 1
            assert wav_b64 == "input_b64"
            return "mp3_result"

        monkeypatch.setattr(
            "backend.utils.audio_encode.wav_base64_to_mp3_base64",
            fake_wav_to_mp3,
        )

        from backend.utils.audio_encode import wav_base64_to_mp3_base64_async

        result = await wav_base64_to_mp3_base64_async("input_b64")

        assert result == "mp3_result"
        assert call_count == 1

    def test_tts_output_mp3_converts_wav(self, monkeypatch):
        def fake_wav_to_mp3(wav_b64: str) -> str:
            assert wav_b64 == "d2F2LTE="
            return "bXAz"

        monkeypatch.setattr(
            "backend.utils.audio_encode.wav_base64_to_mp3_base64",
            fake_wav_to_mp3,
        )
        mock_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "d2F2LTE=",
                "format": "audio/wav",
                "emotion": "neutral",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "テスト",
                "outputEncoding": "mp3",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["audioResponse"] == "bXAz"
        assert body["audioFormat"] == "audio/mpeg"

    def test_tts_output_mp3_skips_when_already_mpeg(self, monkeypatch):
        def should_not_run(_wav_b64: str) -> str:
            raise AssertionError("wav_base64_to_mp3_base64 should not run for audio/mpeg")

        monkeypatch.setattr(
            "backend.utils.audio_encode.wav_base64_to_mp3_base64",
            should_not_run,
        )
        mock_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "Z29vZ2xl",
                "format": "audio/mpeg",
                "emotion": "neutral",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "hello",
                "outputEncoding": "mp3",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["audioResponse"] == "Z29vZ2xl"
        assert body["audioFormat"] == "audio/mpeg"

    def test_tts_output_mp3_conversion_failure_returns_502(self, monkeypatch):
        def boom(_wav_b64: str) -> str:
            raise RuntimeError("ffmpeg missing")

        monkeypatch.setattr(
            "backend.utils.audio_encode.wav_base64_to_mp3_base64",
            boom,
        )
        mock_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "d2F2",
                "format": "audio/wav",
                "emotion": "neutral",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "テスト",
                "outputEncoding": "mp3",
            },
        )

        assert resp.status_code == 502
        assert "MP3" in resp.json()["detail"]


# =============================================================================
# set_language
# =============================================================================


class TestSetLanguage:
    """POST /api/voice  action=set_language"""

    def test_set_language_returns_success(self):
        """set_language は即座に success を返す"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "set_language",
                "language": "en",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["sessionId"] == SAMPLE_SESSION_ID

    def test_set_language_without_session_id(self):
        """set_language は sessionId なしでも成功する"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "set_language",
                "language": "ja",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True


# =============================================================================
# speech_to_text
# =============================================================================


class TestSpeechToText:
    """POST /api/voice  action=speech_to_text"""

    def test_stt_success(self):
        """speech_to_text 成功時に transcript を返す"""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "hello world",
                "confidence": 0.95,
                "language": "en",
                "provider": "vosk",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "audioData": _fake_wav_b64(),
                "language": "en",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["transcript"] == "hello world"
        assert body["confidence"] == pytest.approx(0.95)
        assert body["detectedLanguage"] == "en"
        assert body["sessionId"] == SAMPLE_SESSION_ID

    def test_stt_missing_audio_returns_400(self):
        """audioData がない場合は 400 エラー"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )
        assert resp.status_code == 400

    def test_stt_failure_returns_error(self):
        """STT 失敗時に success=False + error を返す"""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": False,
                "transcript": "",
                "confidence": 0.0,
                "language": "unknown",
                "provider": "vosk",
                "error": "Recognition failed",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "audioData": _fake_wav_b64(),
                "language": "ja",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error"] is not None

    def test_stt_exception_returns_500(self):
        """STT が例外を投げた場合は 500 エラー"""
        mock_stt_agent.speech_to_text = AsyncMock(side_effect=RuntimeError("STT crashed"))

        resp = client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "audioData": _fake_wav_b64(),
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 500


# =============================================================================
# Unknown action
# =============================================================================


class TestUnknownAction:
    """POST /api/voice  未知の action"""

    def test_unknown_action_returns_400(self):
        """不明な action は 400 エラー"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "unknown_action",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )
        assert resp.status_code == 400
        assert "Unknown action" in resp.json()["detail"]


# =============================================================================
# Language parameter
# =============================================================================


class TestLanguageParam:
    """language パラメータの挙動"""

    def test_tts_default_language_ja(self):
        """language 未指定時はデフォルト ja"""
        mock_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "audio==",
                "emotion": "neutral",
            }
        )

        client.post(
            "/api/voice",
            json={
                "action": "text_to_speech",
                "text": "テスト",
            },
        )

        call_kwargs = mock_voice_agent.text_to_speech.call_args.kwargs
        assert call_kwargs["language"] == "ja"

    def test_stt_passes_language_to_agent(self):
        """speech_to_text は language を stt_agent に渡す"""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "hello",
                "confidence": 0.9,
                "language": "en",
                "provider": "vosk",
            }
        )

        client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "audioData": _fake_wav_b64(),
                "language": "en",
            },
        )

        call_kwargs = mock_stt_agent.speech_to_text.call_args.kwargs
        assert call_kwargs["language"] == "en"

    def test_speech_to_text_with_conversation_stage(self):
        """speech_to_text は conversationStage を stt_agent に渡す"""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "こんにちは",
                "confidence": 0.95,
                "language": "ja",
                "provider": "vosk",
            }
        )

        resp = client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "audioData": _fake_wav_b64(),
                "language": "ja",
                "sessionId": SAMPLE_SESSION_ID,
                "conversationStage": "greeting",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["transcript"] == "こんにちは"

        call_kwargs = mock_stt_agent.speech_to_text.call_args.kwargs
        assert call_kwargs["conversation_stage"] == "greeting"


# =============================================================================
# interrupt
# =============================================================================


class TestInterrupt:
    """POST /api/voice  action=interrupt"""

    def test_interrupt_cancelled(self):
        """進行中タスクがある場合は cancelled を返す"""
        mock_session_task_manager.cancel_all_tasks = AsyncMock(return_value=True)

        resp = client.post(
            "/api/voice",
            json={
                "action": "interrupt",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["sessionId"] == SAMPLE_SESSION_ID
        assert body["interruptStatus"] == "cancelled"

    def test_interrupt_no_active_task(self):
        """進行中タスクがない場合は no_active_task を返す"""
        mock_session_task_manager.cancel_all_tasks = AsyncMock(return_value=False)

        resp = client.post(
            "/api/voice",
            json={
                "action": "interrupt",
                "sessionId": SAMPLE_SESSION_ID,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["interruptStatus"] == "no_active_task"

    def test_interrupt_without_session_id_returns_400(self):
        """sessionId なしのinterruptは400"""
        resp = client.post(
            "/api/voice",
            json={
                "action": "interrupt",
            },
        )

        assert resp.status_code == 400
        assert "Missing sessionId" in resp.json()["detail"]
