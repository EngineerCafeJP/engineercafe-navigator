"""Tests for STTAgent - Speech-to-Text integration"""

import pytest
import json
import io
import wave
import numpy as np
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.stt_agent import (
    MAX_AUDIO_UPLOAD_BYTES,
    LocalSTTClient,
    GoogleSTTClient,
    STTAgent,
    TranscriptionResult,
    ENGINEER_CAFE_GRAMMAR,
    STAGE_GRAMMARS,
    VALID_STAGES,
)

# ==============================================================================
# Helpers: vosk mock context manager
# ==============================================================================

# vosk is an optional dependency (no macOS ARM wheels).
# These tests must work even if vosk is not installed by injecting a mock module.
_vosk_mock = MagicMock()


def _vosk_patched():
    """Context manager that injects a mock vosk module into sys.modules."""
    return patch.dict("sys.modules", {"vosk": _vosk_mock})


# ==============================================================================
# Fixtures: Test audio generation
# ==============================================================================


def generate_test_wav(sample_rate: int = 16000, duration: float = 0.5, channels: int = 1) -> bytes:
    """Generate a simple test WAV file (silence or tone)"""
    num_samples = int(sample_rate * duration)
    # Generate silence
    samples = np.zeros(num_samples, dtype=np.int16)

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

    bio.seek(0)
    return bio.read()


@pytest.fixture
def test_wav_16khz() -> bytes:
    """Test WAV: 16kHz, 16-bit, mono (ideal for Vosk)"""
    return generate_test_wav(sample_rate=16000, duration=0.5)


@pytest.fixture
def test_wav_8khz() -> bytes:
    """Test WAV: 8kHz (non-ideal for Vosk)"""
    return generate_test_wav(sample_rate=8000, duration=0.5)


# ==============================================================================
# LocalSTTClient Tests
# ==============================================================================


class TestLocalSTTClient:
    """Tests for Vosk-based local STT"""

    def test_init_default_paths(self):
        """LocalSTTClient initializes with default Vosk model paths"""
        client = LocalSTTClient()
        assert client.model_paths["ja"] == "models/vosk-model-ja"
        assert client.model_paths["en"] == "models/vosk-model-en-us"

    def test_init_custom_paths(self):
        """LocalSTTClient accepts custom model paths"""
        client = LocalSTTClient(model_paths={"ja": "custom/ja", "en": "custom/en"})
        assert client.model_paths["ja"] == "custom/ja"
        assert client.model_paths["en"] == "custom/en"

    def test_load_model_not_found_raises_error(self):
        """LocalSTTClient raises RuntimeError if Vosk model not found"""
        client = LocalSTTClient(model_paths={"ja": "/nonexistent/path"})

        # Mock vosk import so the "model not found" path is reached even if vosk is not installed
        with _vosk_patched():
            with pytest.raises(RuntimeError) as exc_info:
                client._load_model("ja")

        assert "not found" in str(exc_info.value).lower()
        assert "alphacephei.com" in str(exc_info.value)  # Download URL in error message

    def test_load_model_unsupported_language(self):
        """LocalSTTClient raises ValueError for unsupported language"""
        client = LocalSTTClient()
        with pytest.raises(ValueError, match="Unsupported language"):
            client._load_model("fr")

    @pytest.mark.asyncio
    async def test_transcribe_vosk_success(self, test_wav_16khz):
        """LocalSTTClient.transcribe returns TranscriptionResult for valid WAV input"""
        client = LocalSTTClient()

        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {"result": [{"conf": 0.95, "word": "こんにちは"}], "text": "こんにちは"}
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model") as mock_load:
                mock_load.return_value = MagicMock()

                result = await client.transcribe(test_wav_16khz, language="ja")
                assert isinstance(result, TranscriptionResult)
                assert result.text == "こんにちは"
                assert result.confidence == pytest.approx(0.95)
                assert result.language == "ja"
                assert len(result.word_confidences) == 1

    @pytest.mark.asyncio
    async def test_transcribe_empty_result_raises_error(self, test_wav_16khz):
        """LocalSTTClient raises error if Vosk returns empty transcript"""
        client = LocalSTTClient()

        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps({"result": [], "text": ""})

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                with pytest.raises(RuntimeError) as exc_info:
                    await client.transcribe(test_wav_16khz, language="ja")

                assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_transcribe_invalid_json_raises_error(self, test_wav_16khz):
        """LocalSTTClient raises error if Vosk returns malformed JSON"""
        client = LocalSTTClient()

        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = "invalid json {{"

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                with pytest.raises(RuntimeError):
                    await client.transcribe(test_wav_16khz, language="ja")

    @pytest.mark.asyncio
    async def test_transcribe_non_wav_data_converts_to_wav(self, test_wav_16khz):
        """LocalSTTClient converts non-WAV payloads to WAV before Vosk parsing."""
        client = LocalSTTClient()
        non_wav_audio = b"\x1a\x45\xdf\xa3" + (b"webm-opus-data" * 4)
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {"result": [{"conf": 0.88, "word": "こんにちは"}], "text": "こんにちは"}
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch.object(
                client, "_convert_audio_to_wav", return_value=test_wav_16khz
            ) as mock_convert:
                with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                    result = await client.transcribe(non_wav_audio, language="ja")

        mock_convert.assert_called_once_with(non_wav_audio)
        assert result.text == "こんにちは"
        assert result.confidence == pytest.approx(0.88)
        assert result.language == "ja"

    @pytest.mark.asyncio
    async def test_transcribe_truncated_wav_header_raises_value_error(self):
        """LocalSTTClient rejects payloads smaller than a WAV header."""
        client = LocalSTTClient()
        truncated_audio = b"RIFF123456"

        with patch("backend.agents.stt_agent.LocalSTTClient._load_model") as mock_load:
            with pytest.raises(ValueError, match="minimum 44 bytes"):
                await client.transcribe(truncated_audio, language="ja")

        mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcribe_auto_detect_non_wav_returns_error(self):
        """transcribe_auto_detect handles non-WAV data gracefully via ValueError catch."""
        client = LocalSTTClient()
        non_wav_audio = b"\x1a\x45\xdf\xa3" + (b"webm-data" * 8)  # EBML/WebM header

        with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
            with pytest.raises(RuntimeError, match="Auto-detect failed"):
                await client.transcribe_auto_detect(non_wav_audio)

    @pytest.mark.asyncio
    async def test_transcribe_non_wav_conversion_failure_raises_value_error(self):
        """LocalSTTClient surfaces WebM conversion failures with a clear message."""
        client = LocalSTTClient()
        non_wav_audio = b"\x1a\x45\xdf\xa3" + (b"webm-data" * 8)

        with patch.object(
            client,
            "_convert_audio_to_wav",
            side_effect=ValueError(
                "Failed to convert WebM audio to WAV for STT transcription: boom"
            ),
        ) as mock_convert:
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model") as mock_load:
                with pytest.raises(ValueError, match="Failed to convert WebM audio to WAV"):
                    await client.transcribe(non_wav_audio, language="ja")

        mock_convert.assert_called_once_with(non_wav_audio)
        mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcribe_wav_audio_skips_conversion(self, test_wav_16khz):
        """Existing WAV inputs should not trigger WebM conversion."""
        client = LocalSTTClient()
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {"result": [{"conf": 0.91, "word": "hello"}], "text": "hello"}
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch.object(client, "_convert_audio_to_wav") as mock_convert:
                with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                    result = await client.transcribe(test_wav_16khz, language="en")

        mock_convert.assert_not_called()
        assert result.text == "hello"
        assert result.language == "en"

    def test_convert_audio_to_wav_uses_pydub_normalization(self, test_wav_16khz):
        """WebM conversion normalizes audio to 16kHz, 16-bit, mono WAV."""
        client = LocalSTTClient()
        input_audio = b"\x1a\x45\xdf\xa3" + (b"webm" * 8)
        fake_segment = MagicMock()
        fake_segment.set_frame_rate.return_value = fake_segment
        fake_segment.set_sample_width.return_value = fake_segment
        fake_segment.set_channels.return_value = fake_segment

        def export_side_effect(buffer, format):
            assert format == "wav"
            buffer.write(test_wav_16khz)

        fake_segment.export.side_effect = export_side_effect
        fake_pydub = SimpleNamespace(AudioSegment=MagicMock())
        fake_pydub.AudioSegment.from_file.return_value = fake_segment

        with patch.dict("sys.modules", {"pydub": fake_pydub}):
            wav_bytes = client._convert_audio_to_wav(input_audio)

        fake_pydub.AudioSegment.from_file.assert_called_once()
        call_buffer = fake_pydub.AudioSegment.from_file.call_args.args[0]
        assert isinstance(call_buffer, io.BytesIO)
        assert call_buffer.getvalue() == input_audio
        assert fake_pydub.AudioSegment.from_file.call_args.kwargs["format"] is None
        fake_segment.set_frame_rate.assert_called_once_with(16000)
        fake_segment.set_sample_width.assert_called_once_with(2)
        fake_segment.set_channels.assert_called_once_with(1)
        assert wav_bytes.startswith(b"RIFF")

    def test_convert_audio_to_wav_rejects_oversized_payload(self):
        """Oversized non-WAV payloads are rejected before conversion work starts."""
        client = LocalSTTClient()
        oversized_audio = b"\x1a\x45\xdf\xa3" + (b"x" * (MAX_AUDIO_UPLOAD_BYTES + 1))

        with pytest.raises(ValueError, match="Audio payload too large"):
            client._convert_audio_to_wav(oversized_audio)

    def test_convert_audio_to_wav_failure_raises_value_error(self):
        """pydub conversion failures are wrapped with a stable STT error."""
        client = LocalSTTClient()
        fake_pydub = SimpleNamespace(AudioSegment=MagicMock())
        fake_pydub.AudioSegment.from_file.side_effect = RuntimeError("ffmpeg missing")

        with patch.dict("sys.modules", {"pydub": fake_pydub}):
            with pytest.raises(ValueError, match="Failed to convert WebM audio to WAV"):
                client._convert_audio_to_wav(b"\x1a\x45\xdf\xa3" + (b"webm" * 8))


# ==============================================================================
# Confidence Extraction Tests
# ==============================================================================


class TestConfidenceExtraction:
    """Tests for word-level confidence extraction"""

    @pytest.mark.asyncio
    async def test_average_confidence_multiple_words(self, test_wav_16khz):
        """Confidence is averaged across all words"""
        client = LocalSTTClient()
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {
                "result": [
                    {"conf": 0.9, "word": "エンジニア"},
                    {"conf": 0.8, "word": "カフェ"},
                ],
                "text": "エンジニア カフェ",
            }
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                result = await client.transcribe(test_wav_16khz, language="ja")
                assert result.confidence == pytest.approx(0.85)
                assert len(result.word_confidences) == 2

    @pytest.mark.asyncio
    async def test_no_word_results_confidence_none(self, test_wav_16khz):
        """When Vosk returns text but no word-level results, confidence is None"""
        client = LocalSTTClient()
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps({"text": "こんにちは"})

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                result = await client.transcribe(test_wav_16khz, language="ja")
                assert result.confidence is None
                assert result.word_confidences == []

    @pytest.mark.asyncio
    async def test_set_words_called(self, test_wav_16khz):
        """SetWords(True) is called on the recognizer"""
        client = LocalSTTClient()
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {"result": [{"conf": 1.0, "word": "test"}], "text": "test"}
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                await client.transcribe(test_wav_16khz, language="en")
                mock_recognizer.SetWords.assert_called_once_with(True)


# ==============================================================================
# Grammar Support Tests
# ==============================================================================


class TestGrammarSupport:
    """Tests for domain-specific grammar support"""

    @pytest.mark.asyncio
    async def test_grammar_passed_to_recognizer(self, test_wav_16khz):
        """When grammar is provided, KaldiRecognizer receives grammar JSON"""
        client = LocalSTTClient()
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {"result": [{"conf": 1.0, "word": "エンジニアカフェ"}], "text": "エンジニアカフェ"}
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model") as mock_load:
                mock_load.return_value = MagicMock()
                grammar = ["エンジニアカフェ", "営業時間"]
                await client.transcribe(test_wav_16khz, language="ja", grammar=grammar)

                # KaldiRecognizer called with 3 args (model, rate, grammar_json)
                call_args = _vosk_mock.KaldiRecognizer.call_args
                assert len(call_args[0]) == 3

    @pytest.mark.asyncio
    async def test_no_grammar_standard_recognizer(self, test_wav_16khz):
        """Without grammar, KaldiRecognizer is called with 2 args"""
        client = LocalSTTClient()
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps(
            {"result": [{"conf": 1.0, "word": "テスト"}], "text": "テスト"}
        )

        with _vosk_patched():
            _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                await client.transcribe(test_wav_16khz, language="ja")
                call_args = _vosk_mock.KaldiRecognizer.call_args
                assert len(call_args[0]) == 2

    def test_grammar_constants_defined(self):
        """ENGINEER_CAFE_GRAMMAR has ja and en entries"""
        assert "ja" in ENGINEER_CAFE_GRAMMAR
        assert "en" in ENGINEER_CAFE_GRAMMAR
        assert len(ENGINEER_CAFE_GRAMMAR["ja"]) > 0
        assert len(ENGINEER_CAFE_GRAMMAR["en"]) > 0


# ==============================================================================
# Auto-Detection Tests
# ==============================================================================


class TestAutoDetection:
    """Tests for automatic language detection (dual-model)"""

    @pytest.mark.asyncio
    async def test_auto_detect_picks_higher_confidence(self, test_wav_16khz):
        """Auto-detect selects the model with higher average confidence"""
        client = LocalSTTClient()

        ja_result = TranscriptionResult(
            text="何か",
            confidence=0.3,
            language="ja",
            word_confidences=[{"word": "何か", "conf": 0.3}],
        )
        en_result = TranscriptionResult(
            text="hello",
            confidence=0.95,
            language="en",
            word_confidences=[{"word": "hello", "conf": 0.95}],
        )

        with patch.object(client, "transcribe", new_callable=AsyncMock) as mock_transcribe:
            mock_transcribe.side_effect = [ja_result, en_result]

            result = await client.transcribe_auto_detect(test_wav_16khz)
            assert result.language == "en"
            assert result.text == "hello"
            assert result.confidence == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_auto_detect_picks_japanese(self, test_wav_16khz):
        """Auto-detect selects Japanese when it has higher confidence"""
        client = LocalSTTClient()

        ja_result = TranscriptionResult(
            text="こんにちは",
            confidence=0.92,
            language="ja",
            word_confidences=[{"word": "こんにちは", "conf": 0.92}],
        )
        en_result = TranscriptionResult(
            text="con itchy wa",
            confidence=0.4,
            language="en",
            word_confidences=[{"word": "con", "conf": 0.4}],
        )

        with patch.object(client, "transcribe", new_callable=AsyncMock) as mock_transcribe:
            mock_transcribe.side_effect = [ja_result, en_result]

            result = await client.transcribe_auto_detect(test_wav_16khz)
            assert result.language == "ja"
            assert result.text == "こんにちは"

    @pytest.mark.asyncio
    async def test_auto_detect_fallback_when_one_fails(self, test_wav_16khz):
        """If one model produces empty result, the other is used"""
        client = LocalSTTClient()

        en_result = TranscriptionResult(
            text="hello",
            confidence=0.8,
            language="en",
            word_confidences=[{"word": "hello", "conf": 0.8}],
        )

        with patch.object(client, "transcribe", new_callable=AsyncMock) as mock_transcribe:
            mock_transcribe.side_effect = [
                RuntimeError("Vosk returned empty recognition result"),
                en_result,
            ]

            result = await client.transcribe_auto_detect(test_wav_16khz)
            assert result.language == "en"

    @pytest.mark.asyncio
    async def test_auto_detect_both_fail_raises(self, test_wav_16khz):
        """If both models fail, RuntimeError is raised"""
        client = LocalSTTClient()

        with patch.object(client, "transcribe", new_callable=AsyncMock) as mock_transcribe:
            mock_transcribe.side_effect = RuntimeError("Vosk returned empty recognition result")

            with pytest.raises(RuntimeError, match="Auto-detect failed"):
                await client.transcribe_auto_detect(test_wav_16khz)

    @pytest.mark.asyncio
    async def test_auto_detect_with_grammar(self, test_wav_16khz):
        """Auto-detect passes per-language grammar to each model"""
        client = LocalSTTClient()

        ja_result = TranscriptionResult(
            text="エンジニアカフェ",
            confidence=0.99,
            language="ja",
            word_confidences=[{"word": "エンジニアカフェ", "conf": 0.99}],
        )
        en_result = TranscriptionResult(
            text="engineer cafe",
            confidence=0.7,
            language="en",
            word_confidences=[{"word": "engineer", "conf": 0.7}],
        )

        with patch.object(client, "transcribe", new_callable=AsyncMock) as mock_transcribe:
            mock_transcribe.side_effect = [ja_result, en_result]

            grammar = {"ja": ["エンジニアカフェ"], "en": ["engineer cafe"]}
            result = await client.transcribe_auto_detect(test_wav_16khz, grammar=grammar)

            assert result.language == "ja"
            # Verify grammar was passed to each call
            calls = mock_transcribe.call_args_list
            assert calls[0].kwargs.get("grammar") == ["エンジニアカフェ"]
            assert calls[1].kwargs.get("grammar") == ["engineer cafe"]


# ==============================================================================
# GoogleSTTClient Tests
# ==============================================================================


class TestGoogleSTTClient:
    """Tests for Google Cloud STT"""

    def test_init(self):
        """GoogleSTTClient initializes with env vars"""
        client = GoogleSTTClient()
        # Should initialize without error
        assert client is not None

    @pytest.mark.asyncio
    async def test_transcribe_sync_wrapper(self):
        """GoogleSTTClient.transcribe wraps synchronous Google API"""
        client = GoogleSTTClient()

        test_audio = b"\x00\x01\x02\x03"

        with patch.object(client, "_sync_transcribe", return_value="Hello world"):
            result = await client.transcribe(test_audio, language="en")
            assert result == "Hello world"


# ==============================================================================
# STTAgent Tests (Provider Switching + Auto-Detection)
# ==============================================================================


class TestSTTAgent:
    """Tests for STTAgent provider switching"""

    def test_init_default_provider_vosk(self):
        """STTAgent defaults to Vosk provider"""
        with patch("backend.agents.stt_agent.LocalSTTClient"):
            agent = STTAgent()
            assert agent.stt_provider == "vosk"

    def test_init_env_var_provider(self, monkeypatch):
        """STTAgent reads STT_PROVIDER from environment"""
        monkeypatch.setenv("STT_PROVIDER", "google")

        with patch("backend.agents.stt_agent.GoogleSTTClient"):
            agent = STTAgent()
            assert agent.stt_provider == "google"

    def test_init_custom_provider(self):
        """STTAgent accepts custom provider name"""
        with patch("backend.agents.stt_agent.LocalSTTClient"):
            agent = STTAgent(stt_provider="vosk")
            assert agent.stt_provider == "vosk"

    def test_init_invalid_provider_raises_error(self):
        """STTAgent raises ValueError for unknown provider"""
        with pytest.raises(ValueError) as exc_info:
            STTAgent(stt_provider="unknown")

        assert "Unknown STT provider" in str(exc_info.value)

    def test_init_custom_client(self):
        """STTAgent accepts custom client instance"""
        mock_client = MagicMock()
        agent = STTAgent(stt_client=mock_client)
        assert agent.stt_client is mock_client

    def test_init_use_grammar_default_false(self):
        """STTAgent use_grammar defaults to False"""
        with patch("backend.agents.stt_agent.LocalSTTClient"):
            agent = STTAgent()
            assert agent.use_grammar is False

    def test_init_use_grammar_true(self):
        """STTAgent accepts use_grammar=True"""
        with patch("backend.agents.stt_agent.LocalSTTClient"):
            agent = STTAgent(use_grammar=True)
            assert agent.use_grammar is True

    @pytest.mark.asyncio
    async def test_speech_to_text_success_with_confidence(self):
        """STTAgent.speech_to_text returns confidence from TranscriptionResult"""
        mock_client = AsyncMock(spec=LocalSTTClient)
        mock_client.transcribe.return_value = TranscriptionResult(
            text="こんにちは",
            confidence=0.88,
            language="ja",
            word_confidences=[{"word": "こんにちは", "conf": 0.88}],
        )

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client)
        result = await agent.speech_to_text(b"test_audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "こんにちは"
        assert result["provider"] == "vosk"
        assert result["confidence"] == pytest.approx(0.88)
        assert result["language"] == "ja"

    @pytest.mark.asyncio
    async def test_speech_to_text_failure(self):
        """STTAgent.speech_to_text returns error dict on failure"""
        mock_client = AsyncMock()
        mock_client.transcribe.side_effect = RuntimeError("Vosk error")

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client)
        result = await agent.speech_to_text(b"test_audio", language="ja")

        assert result["success"] is False
        assert result["transcript"] == ""
        assert result["confidence"] == 0.0
        assert result["provider"] == "vosk"
        assert "Vosk error" in result["error"]
        assert result["language"] == "ja"

    @pytest.mark.asyncio
    async def test_speech_to_text_google_returns_str(self):
        """STTAgent handles GoogleSTTClient string return type"""
        mock_client = AsyncMock()
        mock_client.transcribe.return_value = "Hello world"

        agent = STTAgent(stt_provider="google", stt_client=mock_client)
        result = await agent.speech_to_text(b"test_audio", language="en")

        assert result["success"] is True
        assert result["transcript"] == "Hello world"
        assert result["confidence"] is None
        assert result["language"] == "en"


# ==============================================================================
# STTAgent Auto-Detection Tests
# ==============================================================================


class TestSTTAgentAutoDetect:
    """Tests for STTAgent auto-detection integration"""

    @pytest.mark.asyncio
    async def test_language_none_triggers_auto_detect(self):
        """STTAgent with language=None uses auto-detect"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe_auto_detect = AsyncMock(
            return_value=TranscriptionResult(
                text="hello",
                confidence=0.9,
                language="en",
                word_confidences=[],
            )
        )

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client)
        result = await agent.speech_to_text(b"audio", language=None)

        assert result["success"] is True
        assert result["language"] == "en"
        assert result["confidence"] == pytest.approx(0.9)
        mock_client.transcribe_auto_detect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_explicit_language_uses_single_model(self):
        """STTAgent with explicit language uses single model (no auto-detect)"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="こんにちは",
                confidence=0.85,
                language="ja",
                word_confidences=[],
            )
        )

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client)
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["language"] == "ja"
        mock_client.transcribe.assert_awaited_once()

    @pytest.mark.asyncio
    @patch.object(STTAgent, "_load_custom_vocabulary", return_value=[])
    async def test_auto_detect_with_grammar_enabled(self, _mock_vocab):
        """STTAgent with use_grammar=True passes grammar to auto-detect"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe_auto_detect = AsyncMock(
            return_value=TranscriptionResult(
                text="エンジニアカフェ",
                confidence=0.95,
                language="ja",
                word_confidences=[],
            )
        )

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client, use_grammar=True)
        await agent.speech_to_text(b"audio", language=None)

        call_kwargs = mock_client.transcribe_auto_detect.call_args.kwargs
        assert call_kwargs["grammar"] == ENGINEER_CAFE_GRAMMAR

    @pytest.mark.asyncio
    async def test_auto_detect_without_grammar(self):
        """STTAgent with use_grammar=False passes None grammar"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe_auto_detect = AsyncMock(
            return_value=TranscriptionResult(
                text="hello",
                confidence=0.9,
                language="en",
                word_confidences=[],
            )
        )

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client, use_grammar=False)
        await agent.speech_to_text(b"audio", language=None)

        call_kwargs = mock_client.transcribe_auto_detect.call_args.kwargs
        assert call_kwargs["grammar"] is None

    @pytest.mark.asyncio
    async def test_auto_detect_failure_returns_error_dict(self):
        """STTAgent auto-detect failure returns error response"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe_auto_detect = AsyncMock(
            side_effect=RuntimeError("Auto-detect failed: neither model produced a result")
        )

        agent = STTAgent(stt_provider="vosk", stt_client=mock_client)
        result = await agent.speech_to_text(b"audio", language=None)

        assert result["success"] is False
        assert "Auto-detect failed" in result["error"]
        assert result["language"] == "unknown"


# ==============================================================================
# Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_stt_agent_with_mock_vosk():
    """Integration test: STTAgent with mocked Vosk"""
    # Create mock Vosk recognizer
    mock_recognizer = MagicMock()
    mock_recognizer.FinalResult.return_value = json.dumps(
        {
            "result": [
                {"conf": 0.92, "word": "エンジニアカフェ"},
                {"conf": 0.88, "word": "について"},
                {"conf": 0.90, "word": "教えてください"},
            ],
            "text": "エンジニアカフェについて教えてください",
        }
    )

    with _vosk_patched():
        _vosk_mock.KaldiRecognizer.return_value = mock_recognizer
        with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
            agent = STTAgent(stt_provider="vosk")

            test_wav = generate_test_wav(sample_rate=16000)
            result = await agent.speech_to_text(test_wav, language="ja")

            assert result["success"] is True
            assert result["provider"] == "vosk"
            assert "カフェ" in result["transcript"]
            assert result["confidence"] is not None
            assert result["confidence"] > 0.8
            assert result["language"] == "ja"


@pytest.mark.asyncio
async def test_stt_agent_auto_detect_integration():
    """Integration test: STTAgent auto-detect with mocked Vosk"""

    call_count = 0

    def make_recognizer(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        rec = MagicMock()
        if call_count % 2 == 1:
            # Japanese model (low confidence for English audio)
            rec.FinalResult.return_value = json.dumps(
                {
                    "result": [{"conf": 0.3, "word": "はろう"}],
                    "text": "はろう",
                }
            )
        else:
            # English model (high confidence)
            rec.FinalResult.return_value = json.dumps(
                {
                    "result": [{"conf": 0.95, "word": "hello"}],
                    "text": "hello",
                }
            )
        return rec

    with _vosk_patched():
        _vosk_mock.KaldiRecognizer.side_effect = make_recognizer
        with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
            agent = STTAgent(stt_provider="vosk")

            test_wav = generate_test_wav(sample_rate=16000)
            result = await agent.speech_to_text(test_wav, language=None)

            assert result["success"] is True
            assert result["language"] == "en"
            assert result["transcript"] == "hello"
            assert result["confidence"] == pytest.approx(0.95)


# ==============================================================================
# #1: LanguageProcessor Post-Validation Tests
# ==============================================================================


class TestLanguageProcessorValidation:
    """Tests for LanguageProcessor post-validation of Vosk language detection"""

    @pytest.mark.asyncio
    async def test_language_processor_validates_language(self):
        """LP confirms Vosk's language choice — no re-transcription"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="こんにちは",
                confidence=0.9,
                language="ja",
                word_confidences=[{"word": "こんにちは", "conf": 0.9}],
            )
        )

        mock_lp = MagicMock()
        mock_lp.detect_language.return_value = {
            "detected": "ja",
            "confidence": 0.9,
            "is_mixed": False,
            "languages": {"ja": 0.9},
        }

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=mock_lp,
            fallback_client=None,
        )
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["language"] == "ja"
        assert result["language_validated"] is False  # No correction needed

    @pytest.mark.asyncio
    async def test_language_processor_corrects_language(self):
        """LP detects different language, re-transcription has higher confidence"""
        mock_client = MagicMock(spec=LocalSTTClient)

        original = TranscriptionResult(
            text="con itchy wa",
            confidence=0.4,
            language="en",
            word_confidences=[{"word": "con", "conf": 0.4}],
        )
        corrected = TranscriptionResult(
            text="こんにちは",
            confidence=0.92,
            language="ja",
            word_confidences=[{"word": "こんにちは", "conf": 0.92}],
        )
        mock_client.transcribe = AsyncMock(side_effect=[original, corrected])

        mock_lp = MagicMock()
        mock_lp.detect_language.return_value = {
            "detected": "ja",
            "confidence": 0.9,
            "is_mixed": False,
            "languages": {"ja": 0.9},
        }

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=mock_lp,
            fallback_client=None,
        )
        result = await agent.speech_to_text(b"audio", language="en")

        assert result["success"] is True
        assert result["transcript"] == "こんにちは"
        assert result["language"] == "ja"
        assert result["language_validated"] is True

    @pytest.mark.asyncio
    async def test_language_processor_low_confidence_skips(self):
        """LP confidence < 0.7 — skip language correction"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="hello",
                confidence=0.6,
                language="en",
                word_confidences=[{"word": "hello", "conf": 0.6}],
            )
        )

        mock_lp = MagicMock()
        mock_lp.detect_language.return_value = {
            "detected": "ja",
            "confidence": 0.5,  # Low LP confidence
            "is_mixed": True,
            "languages": {"ja": 0.5, "en": 0.5},
        }

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=mock_lp,
            fallback_client=None,
        )
        result = await agent.speech_to_text(b"audio", language="en")

        assert result["success"] is True
        assert result["language"] == "en"  # Original Vosk result kept
        assert result["language_validated"] is False

    @pytest.mark.asyncio
    async def test_language_processor_none_skips_validation(self):
        """When language_processor is None, no validation occurs"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="hello",
                confidence=0.8,
                language="en",
                word_confidences=[{"word": "hello", "conf": 0.8}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=None,
        )
        result = await agent.speech_to_text(b"audio", language="en")

        assert result["success"] is True
        assert result["language_validated"] is False


# ==============================================================================
# #7: Stage Grammar Tests
# ==============================================================================


class TestStageGrammar:
    """Tests for conversation stage-based grammar switching"""

    def test_stage_grammars_constant_defined(self):
        """STAGE_GRAMMARS has greeting, service_selection, confirmation"""
        assert "greeting" in STAGE_GRAMMARS
        assert "service_selection" in STAGE_GRAMMARS
        assert "confirmation" in STAGE_GRAMMARS

    def test_valid_stages_tuple(self):
        """VALID_STAGES contains all stage keys"""
        for stage in ("greeting", "service_selection", "confirmation"):
            assert stage in VALID_STAGES

    @pytest.mark.asyncio
    @patch.object(STTAgent, "_load_custom_vocabulary", return_value=[])
    async def test_stage_grammar_greeting(self, _mock_vocab):
        """greeting stage uses STAGE_GRAMMARS['greeting']"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="こんにちは",
                confidence=0.95,
                language="ja",
                word_confidences=[{"word": "こんにちは", "conf": 0.95}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=None,
        )
        await agent.speech_to_text(b"audio", language="ja", conversation_stage="greeting")

        call_kwargs = mock_client.transcribe.call_args
        grammar_arg = call_kwargs.kwargs.get("grammar") or call_kwargs[1].get("grammar")
        assert grammar_arg == STAGE_GRAMMARS["greeting"]["ja"]

    @pytest.mark.asyncio
    @patch.object(STTAgent, "_load_custom_vocabulary", return_value=[])
    async def test_stage_grammar_service_selection(self, _mock_vocab):
        """service_selection stage uses STAGE_GRAMMARS['service_selection']"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="meeting room",
                confidence=0.9,
                language="en",
                word_confidences=[{"word": "meeting", "conf": 0.9}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=None,
        )
        await agent.speech_to_text(b"audio", language="en", conversation_stage="service_selection")

        call_kwargs = mock_client.transcribe.call_args
        grammar_arg = call_kwargs.kwargs.get("grammar") or call_kwargs[1].get("grammar")
        assert grammar_arg == STAGE_GRAMMARS["service_selection"]["en"]

    @pytest.mark.asyncio
    @patch.object(STTAgent, "_load_custom_vocabulary", return_value=[])
    async def test_stage_grammar_confirmation(self, _mock_vocab):
        """confirmation stage uses STAGE_GRAMMARS['confirmation']"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="はい",
                confidence=0.99,
                language="ja",
                word_confidences=[{"word": "はい", "conf": 0.99}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=None,
        )
        await agent.speech_to_text(b"audio", language="ja", conversation_stage="confirmation")

        call_kwargs = mock_client.transcribe.call_args
        grammar_arg = call_kwargs.kwargs.get("grammar") or call_kwargs[1].get("grammar")
        assert grammar_arg == STAGE_GRAMMARS["confirmation"]["ja"]

    @pytest.mark.asyncio
    async def test_stage_grammar_unknown_falls_back(self):
        """Unknown stage falls back to ENGINEER_CAFE_GRAMMAR"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="テスト",
                confidence=0.8,
                language="ja",
                word_confidences=[{"word": "テスト", "conf": 0.8}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=None,
        )
        await agent.speech_to_text(b"audio", language="ja", conversation_stage="unknown_stage")

        call_kwargs = mock_client.transcribe.call_args
        grammar_arg = call_kwargs.kwargs.get("grammar") or call_kwargs[1].get("grammar")
        assert grammar_arg == ENGINEER_CAFE_GRAMMAR["ja"]

    @pytest.mark.asyncio
    async def test_stage_grammar_none_uses_default(self):
        """No stage + use_grammar=True → ENGINEER_CAFE_GRAMMAR"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="エンジニアカフェ",
                confidence=0.95,
                language="ja",
                word_confidences=[{"word": "エンジニアカフェ", "conf": 0.95}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            use_grammar=True,
            language_processor=None,
            fallback_client=None,
        )
        await agent.speech_to_text(b"audio", language="ja")

        call_kwargs = mock_client.transcribe.call_args
        grammar_arg = call_kwargs.kwargs.get("grammar") or call_kwargs[1].get("grammar")
        assert grammar_arg == ENGINEER_CAFE_GRAMMAR["ja"]

    @pytest.mark.asyncio
    async def test_stage_grammar_none_no_grammar(self):
        """No stage + use_grammar=False → no grammar"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="テスト",
                confidence=0.8,
                language="ja",
                word_confidences=[{"word": "テスト", "conf": 0.8}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            use_grammar=False,
            language_processor=None,
            fallback_client=None,
        )
        await agent.speech_to_text(b"audio", language="ja")

        call_kwargs = mock_client.transcribe.call_args
        grammar_arg = call_kwargs.kwargs.get("grammar") or call_kwargs[1].get("grammar")
        assert grammar_arg is None


# ==============================================================================
# #9: Low-Confidence Fallback Tests
# ==============================================================================


class TestLowConfidenceFallback:
    """Tests for low-confidence fallback to Google STT"""

    @pytest.mark.asyncio
    async def test_fallback_triggered_on_low_confidence(self):
        """Low Vosk confidence triggers Google STT fallback"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="あ",
                confidence=0.2,
                language="ja",
                word_confidences=[{"word": "あ", "conf": 0.2}],
            )
        )

        mock_fallback = MagicMock()
        mock_fallback.is_available.return_value = True
        mock_fallback.transcribe = AsyncMock(return_value="こんにちは")

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=mock_fallback,
            confidence_threshold=0.4,
        )
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "こんにちは"
        assert result["provider"] == "google-fallback"
        assert result["fallback_used"] is True
        assert result["original_confidence"] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_fallback_skipped_on_high_confidence(self):
        """High Vosk confidence skips fallback"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="こんにちは",
                confidence=0.9,
                language="ja",
                word_confidences=[{"word": "こんにちは", "conf": 0.9}],
            )
        )

        mock_fallback = MagicMock()
        mock_fallback.is_available.return_value = True
        mock_fallback.transcribe = AsyncMock(return_value="should not be called")

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=mock_fallback,
            confidence_threshold=0.4,
        )
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "こんにちは"
        assert result["provider"] == "vosk"
        assert result.get("fallback_used") is None
        mock_fallback.transcribe.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_google_failure_returns_vosk_result(self):
        """Google STT fails → Vosk result returned"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="あ",
                confidence=0.2,
                language="ja",
                word_confidences=[{"word": "あ", "conf": 0.2}],
            )
        )

        mock_fallback = MagicMock()
        mock_fallback.is_available.return_value = True
        mock_fallback.transcribe = AsyncMock(side_effect=RuntimeError("Google API error"))

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=mock_fallback,
            confidence_threshold=0.4,
        )
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "あ"
        assert result["provider"] == "vosk"

    @pytest.mark.asyncio
    async def test_fallback_no_credentials_skips(self):
        """No Google credentials → fallback skipped"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="あ",
                confidence=0.2,
                language="ja",
                word_confidences=[{"word": "あ", "conf": 0.2}],
            )
        )

        mock_fallback = MagicMock()
        mock_fallback.is_available.return_value = False

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=mock_fallback,
            confidence_threshold=0.4,
        )
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "あ"
        assert result["provider"] == "vosk"

    @pytest.mark.asyncio
    async def test_fallback_none_client_skips(self):
        """fallback_client=None → no fallback attempted"""
        mock_client = MagicMock(spec=LocalSTTClient)
        mock_client.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="あ",
                confidence=0.2,
                language="ja",
                word_confidences=[{"word": "あ", "conf": 0.2}],
            )
        )

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_client,
            language_processor=None,
            fallback_client=None,
            confidence_threshold=0.4,
        )
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "あ"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
