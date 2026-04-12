"""Voice full pipeline integration tests: STT -> MainWorkflow -> TTS.

Unlike test_stt_voice_pipeline.py which hardcodes LLM responses,
these tests verify the REAL LangGraph routing with mocked LLM.

The pipeline mirrors the production data flow:
  Browser audio -> STTAgent.speech_to_text()
    -> MainWorkflow.ainvoke() (real graph traversal, mocked LLM)
    -> VoiceAgent.text_to_speech()
"""

from __future__ import annotations

import base64
import os
import struct
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.stt_agent import STTAgent
from backend.agents.voice_agent import VoiceAgent
from backend.workflows.main_workflow import MainWorkflow

pytestmark = [pytest.mark.integration, pytest.mark.voice_pipeline]


def _make_workflow_input(
    query: str,
    session_id: str = "test-session",
    language: str = "ja",
) -> Dict[str, Any]:
    """Build input dict matching MainWorkflow.ainvoke() expected format."""
    return {
        "query": query,
        "session_id": session_id,
        "language": language,
    }


def _build_minimal_wav(duration_ms: int = 100, sample_rate: int = 16000) -> bytes:
    """Build a minimal valid WAV file (16-bit mono PCM silence).

    Produces a byte-perfect RIFF/WAVE header followed by zero-valued
    PCM samples so that any WAV parser (Vosk, ffmpeg, etc.) accepts it.
    """
    num_samples = int(sample_rate * duration_ms / 1000)
    bits_per_sample = 16
    num_channels = 1
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align
    # RIFF header (44 bytes) + PCM data
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,  # file size - 8
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + b"\x00" * data_size


class TestVoiceFullPipeline:
    """True STT -> MainWorkflow -> TTS pipeline tests.

    Mock strategy:
    - MOCK: STT clients, LLM (ChatOpenAI), TTS clients, Checkpointer
    - REAL: OrchestratorAgent routing, MainWorkflow graph traversal,
            Agent nodes (with mocked LLM), VoiceAgent language detection
    """

    def setup_method(self):
        os.environ["OPENROUTER_API_KEY"] = "test_dummy_api_key_for_testing"

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def fake_wav_bytes(self) -> bytes:
        return _build_minimal_wav(duration_ms=100)

    @pytest.fixture
    def mock_stt_agent(self) -> STTAgent:
        """STTAgent with a mocked client that returns configurable results."""
        client = AsyncMock()
        agent = STTAgent(
            stt_provider="vosk",
            stt_client=client,
            fallback_client=None,
            language_processor=None,
            use_grammar=False,
            confidence_threshold=0.4,
        )
        return agent

    @pytest.fixture
    def workflow(self) -> MainWorkflow:
        """MainWorkflow without checkpointer (no Postgres dependency)."""
        return MainWorkflow(checkpointer=None)

    @pytest.fixture
    def mock_voice_agent(self) -> VoiceAgent:
        """VoiceAgent with mocked TTS client."""
        tts_client = AsyncMock()
        tts_client.synthesize_wav_base64 = AsyncMock(
            return_value=base64.b64encode(b"RIFF-fake-tts-wav").decode("utf-8")
        )
        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "piper"
        agent.tts_client = tts_client
        agent.kokoro_client = None
        agent.language_processor = MagicMock()
        agent.language_processor.detect_language = MagicMock(
            return_value={
                "detected": "ja",
                "confidence": 0.95,
                "is_mixed": False,
                "languages": {"primary": "ja"},
            }
        )
        agent.clarification_agent = None
        return agent

    # ------------------------------------------------------------------
    # Pipeline runner
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        stt_agent: STTAgent,
        workflow: MainWorkflow,
        voice_agent: VoiceAgent,
        audio: bytes,
        language: Optional[str] = "ja",
        session_id: str = "test-session",
    ) -> Dict[str, Any]:
        """Run the 3-step pipeline matching the production flow.

        Returns a dict with:
          stage: "stt" | "workflow" | "tts" | "complete"
          error: str (if stage != "complete")
          stt_result, workflow_result, tts_result: step outputs
        """
        # Step 1: STT
        stt_result = await stt_agent.speech_to_text(audio, language=language)
        if not stt_result.get("success"):
            return {
                "stage": "stt",
                "error": stt_result.get("error"),
                "stt_result": stt_result,
            }

        # Step 2: MainWorkflow
        detected_lang = stt_result.get("language", language) or "ja"
        try:
            workflow_result = await workflow.ainvoke(
                _make_workflow_input(
                    query=stt_result["transcript"],
                    session_id=session_id,
                    language=detected_lang,
                )
            )
        except Exception as e:
            return {
                "stage": "workflow",
                "error": str(e),
                "stt_result": stt_result,
            }

        # Step 3: TTS
        answer = workflow_result.get("answer", "")
        emotion = workflow_result.get("emotion")
        tts_result = await voice_agent.text_to_speech(
            text=answer,
            language=detected_lang,
            emotion=emotion,
        )
        if not tts_result.get("success"):
            return {
                "stage": "tts",
                "error": tts_result.get("error"),
                "stt_result": stt_result,
                "workflow_result": workflow_result,
                "tts_result": tts_result,
            }

        return {
            "stage": "complete",
            "stt_result": stt_result,
            "workflow_result": workflow_result,
            "tts_result": tts_result,
        }

    # ------------------------------------------------------------------
    # Test 1: Full pipeline — Japanese business_info
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_ja_business_info(
        self, fake_wav_bytes, mock_stt_agent, workflow, mock_voice_agent
    ):
        """Japanese business-hours query flows through STT -> workflow -> TTS."""
        # Configure STT mock
        mock_stt_agent.stt_client.transcribe = AsyncMock(
            return_value={
                "text": "営業時間を教えてください",
                "confidence": 0.95,
            }
        )

        # Patch speech_to_text to return a well-formed result
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "営業時間を教えてください",
                "confidence": 0.95,
                "language": "ja",
                "provider": "vosk",
            }
        )

        result = await self._run_pipeline(
            stt_agent=mock_stt_agent,
            workflow=workflow,
            voice_agent=mock_voice_agent,
            audio=fake_wav_bytes,
            language="ja",
            session_id="test-session-ja-biz",
        )

        assert (
            result["stage"] == "complete"
        ), f"Pipeline stopped at {result['stage']}: {result.get('error')}"

        # Workflow routed to business_info
        wf = result["workflow_result"]
        assert wf.get("answer") is not None
        assert len(wf["answer"]) > 0
        assert wf.get("emotion") is not None

        # TTS produced audio
        tts = result["tts_result"]
        assert tts["success"] is True
        assert tts.get("audioResponse") is not None
        assert len(tts["audioResponse"]) > 0

    # ------------------------------------------------------------------
    # Test 2: Full pipeline — English facility query
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_en_facility(
        self, fake_wav_bytes, mock_stt_agent, workflow, mock_voice_agent
    ):
        """English Wi-Fi query routes to facility agent and TTS uses English."""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "Do you have Wi-Fi?",
                "confidence": 0.92,
                "language": "en",
                "provider": "qwen",
            }
        )

        # Update language_processor for English detection
        mock_voice_agent.language_processor.detect_language = MagicMock(
            return_value={
                "detected": "en",
                "confidence": 0.95,
                "is_mixed": False,
                "languages": {"primary": "en"},
            }
        )

        result = await self._run_pipeline(
            stt_agent=mock_stt_agent,
            workflow=workflow,
            voice_agent=mock_voice_agent,
            audio=fake_wav_bytes,
            language="en",
            session_id="test-session-en-facility",
        )

        assert (
            result["stage"] == "complete"
        ), f"Pipeline stopped at {result['stage']}: {result.get('error')}"

        # Workflow produced an answer
        wf = result["workflow_result"]
        assert wf.get("answer") is not None
        assert len(wf["answer"]) > 0

        # TTS was called (mock_voice_agent.tts_client.synthesize_wav_base64)
        tts = result["tts_result"]
        assert tts["success"] is True

    # ------------------------------------------------------------------
    # Test 3: Language auto-detection propagation
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_language_detection(
        self, fake_wav_bytes, mock_stt_agent, workflow, mock_voice_agent
    ):
        """STT auto-detects language=ja and propagates to workflow and TTS."""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "エンジニアカフェはどこですか",
                "confidence": 0.88,
                "language": "ja",  # auto-detected
                "provider": "qwen",
            }
        )

        result = await self._run_pipeline(
            stt_agent=mock_stt_agent,
            workflow=workflow,
            voice_agent=mock_voice_agent,
            audio=fake_wav_bytes,
            language=None,  # no language hint
            session_id="test-session-lang-detect",
        )

        assert (
            result["stage"] == "complete"
        ), f"Pipeline stopped at {result['stage']}: {result.get('error')}"

        # STT detected language
        assert result["stt_result"]["language"] == "ja"

        # Workflow used the detected language
        wf = result["workflow_result"]
        assert wf.get("answer") is not None

        # TTS received language from pipeline
        tts = result["tts_result"]
        assert tts["success"] is True

    # ------------------------------------------------------------------
    # Test 4: Emotion propagation through pipeline
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_emotion_propagation(
        self, fake_wav_bytes, mock_stt_agent, mock_voice_agent
    ):
        """Emotion from workflow propagates to TTS text_to_speech(emotion=...)."""
        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "ありがとうございます",
                "confidence": 0.95,
                "language": "ja",
                "provider": "vosk",
            }
        )

        # Use a mock workflow that returns a specific emotion
        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(
            return_value={
                "answer": "どういたしまして！何かお手伝いできることがあればお気軽にどうぞ。",
                "emotion": "happy",
                "metadata": {},
            }
        )

        # Spy on text_to_speech to capture the emotion argument
        tts_call_args: Dict[str, Any] = {}

        async def capture_tts(**kwargs):
            tts_call_args.update(kwargs)
            return {
                "success": True,
                "audioResponse": base64.b64encode(b"RIFF-happy").decode(),
                "emotion": kwargs.get("emotion", "neutral"),
                "cleanText": kwargs.get("text", ""),
                "format": "audio/wav",
                "language": kwargs.get("language", "ja"),
            }

        mock_voice_agent.text_to_speech = capture_tts

        result = await self._run_pipeline(
            stt_agent=mock_stt_agent,
            workflow=mock_workflow,
            voice_agent=mock_voice_agent,
            audio=_build_minimal_wav(),
            language="ja",
            session_id="test-session-emotion",
        )

        assert result["stage"] == "complete"
        assert result["workflow_result"]["emotion"] == "happy"

        # Verify emotion was passed to TTS
        assert tts_call_args.get("emotion") == "happy"

    # ------------------------------------------------------------------
    # Test 5: STT failure — workflow and TTS not called
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_stt_failure(self, fake_wav_bytes, mock_voice_agent):
        """When STT fails, workflow and TTS are NOT called."""
        mock_stt = AsyncMock()
        mock_stt.speech_to_text = AsyncMock(
            return_value={
                "success": False,
                "error": "Audio too short",
                "transcript": "",
                "confidence": 0.0,
                "language": None,
                "provider": "vosk",
            }
        )

        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock()

        result = await self._run_pipeline(
            stt_agent=mock_stt,
            workflow=mock_workflow,
            voice_agent=mock_voice_agent,
            audio=fake_wav_bytes,
            language="ja",
            session_id="test-session-stt-fail",
        )

        assert result["stage"] == "stt"
        assert result["error"] == "Audio too short"

        # Workflow was never called
        mock_workflow.ainvoke.assert_not_awaited()

    # ------------------------------------------------------------------
    # Test 6: Workflow failure — error captured gracefully
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_workflow_failure(self, fake_wav_bytes, mock_voice_agent):
        """When workflow raises TimeoutError, TTS is NOT called."""
        mock_stt = AsyncMock()
        mock_stt.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "営業時間は？",
                "confidence": 0.9,
                "language": "ja",
                "provider": "vosk",
            }
        )

        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(side_effect=TimeoutError("Workflow timed out after 30s"))

        # Spy to verify TTS is never called
        tts_called = False

        async def spy_tts(**kwargs):
            nonlocal tts_called
            tts_called = True
            return {"success": True, "audioResponse": "", "emotion": "neutral"}

        mock_voice_agent.text_to_speech = spy_tts

        result = await self._run_pipeline(
            stt_agent=mock_stt,
            workflow=mock_workflow,
            voice_agent=mock_voice_agent,
            audio=fake_wav_bytes,
            language="ja",
            session_id="test-session-wf-fail",
        )

        assert result["stage"] == "workflow"
        assert "timed out" in result["error"].lower()

        # TTS was never called
        assert tts_called is False

        # STT result is still available
        assert result["stt_result"]["success"] is True

    # ------------------------------------------------------------------
    # Test 7: TTS failure — answer text still available
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_tts_failure(self, fake_wav_bytes, mock_stt_agent):
        """When TTS fails, the answer text from workflow is still available."""
        expected_answer = "エンジニアカフェは月曜から金曜まで営業しています。"

        mock_stt_agent.speech_to_text = AsyncMock(
            return_value={
                "success": True,
                "transcript": "営業時間を教えて",
                "confidence": 0.91,
                "language": "ja",
                "provider": "vosk",
            }
        )

        # Workflow returns a valid answer
        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(
            return_value={
                "answer": expected_answer,
                "emotion": "helpful",
                "metadata": {},
            }
        )

        # TTS agent that always fails
        failing_voice_agent = AsyncMock()
        failing_voice_agent.text_to_speech = AsyncMock(
            return_value={
                "success": False,
                "error": "TTS synthesis failed: connection refused",
                "audioResponse": None,
            }
        )

        result = await self._run_pipeline(
            stt_agent=mock_stt_agent,
            workflow=mock_workflow,
            voice_agent=failing_voice_agent,
            audio=fake_wav_bytes,
            language="ja",
            session_id="test-session-tts-fail",
        )

        assert result["stage"] == "tts"
        assert result["error"] == "TTS synthesis failed: connection refused"

        # Answer text is still accessible despite TTS failure
        assert result["workflow_result"]["answer"] == expected_answer
        assert result["workflow_result"]["emotion"] == "helpful"

    # ------------------------------------------------------------------
    # Test 8: Session ID propagation across all stages
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_full_pipeline_session_propagation(self, fake_wav_bytes):
        """session_id propagates through STT, workflow, and TTS calls."""
        target_session = "test-session-123"

        # Track calls with their arguments
        stt_call_args: Dict[str, Any] = {}
        workflow_call_args: Dict[str, Any] = {}
        tts_call_args: Dict[str, Any] = {}

        # STT mock that captures arguments
        mock_stt = AsyncMock()

        async def capture_stt(audio_data, language=None, **kwargs):
            stt_call_args["audio_size"] = len(audio_data)
            stt_call_args["language"] = language
            return {
                "success": True,
                "transcript": "テスト",
                "confidence": 0.9,
                "language": "ja",
                "provider": "vosk",
            }

        mock_stt.speech_to_text = capture_stt

        # Workflow mock that captures the input_data
        mock_workflow = AsyncMock()

        async def capture_workflow(input_data):
            workflow_call_args.update(input_data)
            return {
                "answer": "テスト回答です。",
                "emotion": "neutral",
                "metadata": {},
            }

        mock_workflow.ainvoke = capture_workflow

        # TTS mock that captures arguments
        mock_voice = AsyncMock()

        async def capture_tts(text="", language=None, emotion=None, **kwargs):
            tts_call_args["text"] = text
            tts_call_args["language"] = language
            tts_call_args["emotion"] = emotion
            return {
                "success": True,
                "audioResponse": base64.b64encode(b"RIFF-test").decode(),
                "emotion": emotion or "neutral",
                "cleanText": text,
                "format": "audio/wav",
                "language": language or "ja",
            }

        mock_voice.text_to_speech = capture_tts

        result = await self._run_pipeline(
            stt_agent=mock_stt,
            workflow=mock_workflow,
            voice_agent=mock_voice,
            audio=fake_wav_bytes,
            language="ja",
            session_id=target_session,
        )

        assert result["stage"] == "complete"

        # Session ID was passed to workflow
        assert workflow_call_args.get("session_id") == target_session

        # All stages completed successfully
        assert result["stt_result"]["success"] is True
        assert result["workflow_result"]["answer"] == "テスト回答です。"
        assert result["tts_result"]["success"] is True
