"""HTTP API chain tests: /api/voice (STT) -> /api/chat -> /api/voice (TTS).

Tests the 3-step HTTP sequence that the frontend actually makes,
using the real FastAPI app with mocked agents/workflow.
"""

from __future__ import annotations

import base64
import struct

import httpx
import pytest
from httpx import ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from backend.main import app


def _minimal_wav_b64() -> str:
    """Return a small valid WAV file above the STT no-speech byte guard."""
    sample_rate = 16000
    num_samples = 256
    bits_per_sample = 16
    num_channels = 1
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return base64.b64encode(header + (b"\x00" * data_size)).decode()


def _mock_stt_success(
    transcript: str = "エンジニアカフェの営業時間は？",
    language: str = "ja",
    confidence: float = 0.95,
):
    """Build an AsyncMock that returns a successful STT result."""
    return AsyncMock(
        return_value={
            "success": True,
            "transcript": transcript,
            "language": language,
            "confidence": confidence,
        }
    )


def _mock_stt_failure(error: str = "STT failed"):
    """Build an AsyncMock that returns a failed STT result."""
    return AsyncMock(return_value={"success": False, "error": error})


def _mock_workflow_success(
    answer: str = "営業時間は10時から21時までです。",
    emotion: str = "neutral",
):
    """Build a mock workflow whose ainvoke returns a chat-like result."""
    workflow = AsyncMock()
    workflow.ainvoke = AsyncMock(
        return_value={
            "answer": answer,
            "emotion": emotion,
            "metadata": {"query": "test", "session_id": "test-session"},
        }
    )
    return workflow


def _mock_tts_success(
    audio_b64: str | None = None,
    emotion: str = "neutral",
):
    """Build an AsyncMock that returns a successful TTS result."""
    if audio_b64 is None:
        audio_b64 = base64.b64encode(b"\x00" * 100).decode()
    return AsyncMock(
        return_value={
            "success": True,
            "audioResponse": audio_b64,
            "format": "audio/wav",
            "emotion": emotion,
        }
    )


def _patch_singletons(
    *,
    stt_mock=None,
    voice_mock=None,
    workflow_mock=None,
    stm_mock=None,
):
    """Context manager that patches all singleton getters at once."""
    if stm_mock is None:
        stm_mock = MagicMock()
        stm_mock.register_session = AsyncMock()
        stm_mock.set_llm_task = AsyncMock()
        stm_mock.set_tts_task = AsyncMock()
        stm_mock.set_tts_buffer = AsyncMock()

    patches = []
    if stt_mock is not None:
        patches.append(patch("backend.main._stt_agent", stt_mock))
    if voice_mock is not None:
        patches.append(patch("backend.main._voice_agent", voice_mock))
    patches.append(patch("backend.main._session_task_manager", stm_mock))
    if workflow_mock is not None:
        patches.append(
            patch(
                "backend.workflows.main_workflow.get_workflow",
                AsyncMock(return_value=workflow_mock),
            )
        )

    from contextlib import ExitStack

    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


@pytest.mark.voice_pipeline
class TestVoiceApiChain:
    """HTTP-level tests for the 3-step voice pipeline chain."""

    @pytest.fixture
    def fake_audio_b64(self):
        return _minimal_wav_b64()

    @pytest.fixture
    async def client(self):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    # ------------------------------------------------------------------ helpers

    async def _call_stt(self, client: httpx.AsyncClient, audio_b64: str, language: str = "ja"):
        return await client.post(
            "/api/voice",
            json={
                "action": "speech_to_text",
                "audioData": audio_b64,
                "language": language,
            },
        )

    async def _call_chat(
        self,
        client: httpx.AsyncClient,
        query: str,
        language: str,
        session_id: str = "test-chain-session",
    ):
        return await client.post(
            "/api/chat",
            json={
                "query": query,
                "language": language,
                "session_id": session_id,
            },
        )

    async def _call_tts(
        self,
        client: httpx.AsyncClient,
        text: str,
        language: str,
        emotion: str | None = None,
    ):
        payload: dict = {
            "action": "text_to_speech",
            "text": text,
            "language": language,
        }
        if emotion is not None:
            payload["emotion"] = emotion
        return await client.post("/api/voice", json=payload)

    # ------------------------------------------------------- test scenarios

    async def test_api_chain_stt_chat_tts(self, client, fake_audio_b64):
        """Full 3-step chain: STT -> Chat -> TTS all return 200."""
        mock_stt = MagicMock()
        mock_stt.speech_to_text = _mock_stt_success()

        mock_voice = MagicMock()
        mock_voice.text_to_speech = _mock_tts_success()

        mock_wf = _mock_workflow_success()

        with _patch_singletons(stt_mock=mock_stt, voice_mock=mock_voice, workflow_mock=mock_wf):
            # Step 1: STT
            stt_resp = await self._call_stt(client, fake_audio_b64)
            assert stt_resp.status_code == 200
            stt_data = stt_resp.json()
            assert stt_data["success"] is True
            assert stt_data["transcript"]

            # Verify STT returned the expected transcript
            expected_transcript = "エンジニアカフェの営業時間は？"
            assert stt_data["transcript"] == expected_transcript

            # Step 2: Chat (use STT output directly)
            chat_resp = await self._call_chat(
                client,
                query=stt_data["transcript"],
                language=stt_data.get("detectedLanguage", "ja"),
            )
            assert chat_resp.status_code == 200
            chat_data = chat_resp.json()
            assert chat_data["answer"]
            assert "emotion" in chat_data

            # Verify workflow received the correct transcript from STT
            mock_wf.ainvoke.assert_awaited_once()
            call_args = mock_wf.ainvoke.call_args[0][0]
            assert call_args["query"] == expected_transcript

            # Step 3: TTS (use Chat output directly)
            tts_resp = await self._call_tts(
                client,
                text=chat_data["answer"],
                language=stt_data.get("detectedLanguage", "ja"),
                emotion=chat_data.get("emotion"),
            )
            assert tts_resp.status_code == 200
            tts_data = tts_resp.json()
            assert tts_data["success"] is True
            assert tts_data["audioResponse"]

    async def test_api_chain_language_consistency(self, client, fake_audio_b64):
        """Language detected by STT propagates through Chat and TTS."""
        mock_stt = MagicMock()
        mock_stt.speech_to_text = _mock_stt_success(
            transcript="What are the opening hours?",
            language="en",
        )

        mock_voice = MagicMock()
        mock_voice.text_to_speech = _mock_tts_success()

        mock_wf = _mock_workflow_success(
            answer="Opening hours are 10 AM to 9 PM.",
            emotion="neutral",
        )

        with _patch_singletons(stt_mock=mock_stt, voice_mock=mock_voice, workflow_mock=mock_wf):
            # Step 1: STT returns language="en"
            stt_resp = await self._call_stt(client, fake_audio_b64, language="en")
            stt_data = stt_resp.json()
            detected_lang = stt_data["detectedLanguage"]
            assert detected_lang == "en"

            # Step 2: Chat with detected language
            chat_resp = await self._call_chat(
                client,
                query=stt_data["transcript"],
                language=detected_lang,
            )
            assert chat_resp.status_code == 200

            chat_data = chat_resp.json()

            # Step 3: TTS with same language
            tts_resp = await self._call_tts(
                client,
                text=chat_data["answer"],
                language=detected_lang,
            )
            assert tts_resp.status_code == 200

            # Verify language passed to TTS agent matches STT detection
            tts_call = mock_voice.text_to_speech.call_args
            assert tts_call.kwargs.get("language") == "en"

    async def test_api_chain_emotion_flow(self, client, fake_audio_b64):
        """Emotion from Chat response propagates to TTS request."""
        mock_stt = MagicMock()
        mock_stt.speech_to_text = _mock_stt_success()

        mock_voice = MagicMock()
        mock_voice.text_to_speech = _mock_tts_success(emotion="happy")

        mock_wf = _mock_workflow_success(
            answer="イベント情報をお伝えします！",
            emotion="happy",
        )

        with _patch_singletons(stt_mock=mock_stt, voice_mock=mock_voice, workflow_mock=mock_wf):
            stt_resp = await self._call_stt(client, fake_audio_b64)
            stt_data = stt_resp.json()

            chat_resp = await self._call_chat(
                client,
                query=stt_data["transcript"],
                language="ja",
            )
            chat_data = chat_resp.json()
            assert chat_data["emotion"] == "happy"

            tts_resp = await self._call_tts(
                client,
                text=chat_data["answer"],
                language="ja",
                emotion=chat_data["emotion"],
            )
            assert tts_resp.status_code == 200

            # Verify emotion was forwarded to the voice agent
            tts_call = mock_voice.text_to_speech.call_args
            assert tts_call.kwargs.get("emotion") == "happy"

    async def test_api_chain_stt_failure_short_circuit(self, client, fake_audio_b64):
        """When STT fails, the chain stops -- workflow is never invoked."""
        mock_stt = MagicMock()
        mock_stt.speech_to_text = _mock_stt_failure("Audio too short")

        mock_wf = _mock_workflow_success()

        with _patch_singletons(stt_mock=mock_stt, workflow_mock=mock_wf):
            stt_resp = await self._call_stt(client, fake_audio_b64)
            stt_data = stt_resp.json()

            assert stt_data["success"] is False
            assert "error" in stt_data

            # Workflow should NOT have been called
            mock_wf.ainvoke.assert_not_called()

    async def test_api_chain_chat_failure_graceful(self, client, fake_audio_b64):
        """When Chat (workflow) raises, TTS is never reached."""
        mock_stt = MagicMock()
        mock_stt.speech_to_text = _mock_stt_success()

        mock_voice = MagicMock()
        mock_voice.text_to_speech = _mock_tts_success()

        mock_wf = AsyncMock()
        mock_wf.ainvoke = AsyncMock(side_effect=RuntimeError("LLM provider unreachable"))

        with _patch_singletons(stt_mock=mock_stt, voice_mock=mock_voice, workflow_mock=mock_wf):
            # STT succeeds
            stt_resp = await self._call_stt(client, fake_audio_b64)
            stt_data = stt_resp.json()
            assert stt_data["success"] is True

            # Chat fails with 500
            chat_resp = await self._call_chat(
                client,
                query=stt_data["transcript"],
                language="ja",
            )
            assert chat_resp.status_code == 500

            # TTS should NOT have been called
            mock_voice.text_to_speech.assert_not_called()

    async def test_api_chain_format_compatibility(self, client, fake_audio_b64):
        """VoiceResponse fields map directly to ChatRequest fields,
        and ChatResponse fields map to VoiceRequest fields.

        Catches interface drift between endpoints.
        """
        mock_stt = MagicMock()
        mock_stt.speech_to_text = _mock_stt_success(
            transcript="テスト質問",
            language="ja",
            confidence=0.9,
        )

        mock_voice = MagicMock()
        mock_voice.text_to_speech = _mock_tts_success(emotion="neutral")

        mock_wf = _mock_workflow_success(
            answer="テスト回答です。",
            emotion="neutral",
        )

        with _patch_singletons(stt_mock=mock_stt, voice_mock=mock_voice, workflow_mock=mock_wf):
            # STT response
            stt_resp = await self._call_stt(client, fake_audio_b64)
            stt_data = stt_resp.json()

            # VoiceResponse.transcript -> ChatRequest.query
            assert isinstance(stt_data["transcript"], str)
            assert len(stt_data["transcript"]) > 0

            # VoiceResponse.detectedLanguage -> ChatRequest.language
            assert stt_data["detectedLanguage"] is not None

            # Chat response
            chat_resp = await self._call_chat(
                client,
                query=stt_data["transcript"],
                language=stt_data["detectedLanguage"],
            )
            chat_data = chat_resp.json()

            # ChatResponse.answer -> VoiceRequest.text
            assert isinstance(chat_data["answer"], str)
            assert len(chat_data["answer"]) > 0

            # ChatResponse.emotion -> VoiceRequest.emotion
            assert isinstance(chat_data["emotion"], str)

            # TTS with chat output -- no transformation needed
            tts_resp = await self._call_tts(
                client,
                text=chat_data["answer"],
                language=stt_data["detectedLanguage"],
                emotion=chat_data["emotion"],
            )
            tts_data = tts_resp.json()
            assert tts_data["success"] is True
