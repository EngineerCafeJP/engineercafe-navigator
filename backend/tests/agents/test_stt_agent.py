"""Tests for STTAgent - Speech-to-Text integration"""

import logging
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
    Qwen06BCpuSTTClient,
    QwenSTTClient,
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
# Resample Tests
# ==============================================================================


class TestResampleTo16khz:
    """Tests for _resample_to_16khz static method."""

    def test_passthrough_16khz(self):
        """16kHz audio is returned unchanged."""
        samples = np.zeros(16000, dtype=np.int16)
        result_frames, result_rate = LocalSTTClient._resample_to_16khz(samples.tobytes(), 16000)
        assert result_rate == 16000
        assert result_frames == samples.tobytes()

    def test_resample_22050hz_to_16khz(self):
        """22050Hz audio (Piper output) is resampled to 16kHz."""
        orig_rate = 22050
        duration = 0.5
        num_samples = int(orig_rate * duration)
        t = np.linspace(0, duration, num_samples, endpoint=False)
        tone = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        orig_bytes = tone.tobytes()

        result_frames, result_rate = LocalSTTClient._resample_to_16khz(orig_bytes, orig_rate)
        assert result_rate == 16000

        result_samples = np.frombuffer(result_frames, dtype=np.int16)
        expected_len = int(num_samples * 16000 / orig_rate)
        assert abs(len(result_samples) - expected_len) <= 2

    def test_resample_8khz_to_16khz(self):
        """8kHz audio is upsampled to 16kHz."""
        orig_rate = 8000
        samples = np.ones(8000, dtype=np.int16) * 1000
        result_frames, result_rate = LocalSTTClient._resample_to_16khz(samples.tobytes(), orig_rate)
        assert result_rate == 16000
        result_samples = np.frombuffer(result_frames, dtype=np.int16)
        assert len(result_samples) == 16000

    def test_resample_preserves_dtype(self):
        """Resampled output is int16 (matches WAV 16-bit PCM)."""
        samples = np.ones(22050, dtype=np.int16) * 5000
        result_frames, _ = LocalSTTClient._resample_to_16khz(samples.tobytes(), 22050)
        result_samples = np.frombuffer(result_frames, dtype=np.int16)
        assert result_samples.dtype == np.int16

    def test_resample_silence(self):
        """Resampling silence produces silence."""
        silence = np.zeros(22050, dtype=np.int16)
        result_frames, _ = LocalSTTClient._resample_to_16khz(silence.tobytes(), 22050)
        result_samples = np.frombuffer(result_frames, dtype=np.int16)
        np.testing.assert_array_equal(result_samples, np.zeros_like(result_samples))


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
# QwenSTTClient Tests
# ==============================================================================


class TestQwenSTTClient:
    """Tests for Qwen-based local STT"""

    @pytest.mark.asyncio
    async def test_transcribe_non_wav_data_converts_to_wav(self, test_wav_16khz):
        """QwenSTTClient converts non-WAV payloads before transcription."""
        client = QwenSTTClient(model_variant="0.6b", device="cpu")
        client._model = MagicMock()
        client._model.transcribe.return_value = [SimpleNamespace(text="こんにちは", language="ja")]
        non_wav_audio = b"\x1a\x45\xdf\xa3" + (b"webm-opus-data" * 4)

        with patch(
            "backend.agents.stt_agent.convert_audio_to_wav_bytes", return_value=test_wav_16khz
        ) as mock_convert:
            with patch.object(client, "_load_model"):
                result = await client.transcribe(non_wav_audio, language="ja")

        mock_convert.assert_called_once_with(non_wav_audio)
        assert result.text == "こんにちは"
        assert result.language == "ja"

    @pytest.mark.asyncio
    async def test_transcribe_wav_audio_skips_conversion(self, test_wav_16khz):
        """QwenSTTClient uses WAV payloads directly without conversion."""
        client = QwenSTTClient(model_variant="0.6b", device="cpu")
        client._model = MagicMock()
        client._model.transcribe.return_value = [SimpleNamespace(text="hello", language="en")]

        with patch("backend.agents.stt_agent.convert_audio_to_wav_bytes") as mock_convert:
            with patch.object(client, "_load_model"):
                result = await client.transcribe(test_wav_16khz, language="en")

        mock_convert.assert_not_called()
        assert result.text == "hello"
        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_language_name_normalized_to_code(self, test_wav_16khz):
        """Qwen returns display names ('Japanese'); verify they map to codes ('ja')."""
        client = QwenSTTClient(model_variant="0.6b", device="cpu")
        client._model = MagicMock()
        client._model.transcribe.return_value = [
            SimpleNamespace(text="こんにちは", language="Japanese")
        ]

        with patch.object(client, "_load_model"):
            result = await client.transcribe(test_wav_16khz, language="ja")

        assert result.language == "ja"

    @pytest.mark.asyncio
    async def test_language_name_english_normalized(self, test_wav_16khz):
        """Qwen 'English' display name maps to 'en' code."""
        client = QwenSTTClient(model_variant="0.6b", device="cpu")
        client._model = MagicMock()
        client._model.transcribe.return_value = [
            SimpleNamespace(text="hello world", language="English")
        ]

        with patch.object(client, "_load_model"):
            result = await client.transcribe(test_wav_16khz, language="en")

        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_auto_detect_passes_none_to_qwen(self, test_wav_16khz):
        """When language=None, Qwen auto-detect is used (no forced default)."""
        client = QwenSTTClient(model_variant="0.6b", device="cpu")
        client._model = MagicMock()
        client._model.transcribe.return_value = [SimpleNamespace(text="hello", language="English")]

        with patch.object(client, "_load_model"):
            result = await client.transcribe(test_wav_16khz, language=None)

        assert result.text == "hello"
        assert result.language == "en"
        # Verify language kwarg was NOT passed to Qwen (auto-detect)
        call_kwargs = client._model.transcribe.call_args
        assert (
            "language" not in call_kwargs.kwargs
        ), "language should not be passed to Qwen when auto-detect is intended"


# ==============================================================================
# STTAgent Tests (Provider Switching + Auto-Detection)
# ==============================================================================


class TestSTTAgent:
    """Tests for STTAgent provider switching"""

    def test_init_default_provider_qwen_06b_cpu(self):
        """STTAgent defaults to qwen0.6b-cpu provider"""
        with patch("backend.agents.stt_agent.Qwen06BCpuSTTClient"):
            agent = STTAgent()
            assert agent.stt_provider == "qwen0.6b-cpu"

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

    def test_init_qwen_provider(self, monkeypatch):
        """STTAgent accepts qwen provider and builds QwenSTTClient"""
        monkeypatch.setenv("QWEN_STT_MODEL_VARIANT", "0.6b")
        monkeypatch.setenv("QWEN_STT_DEVICE", "cpu")
        monkeypatch.setenv("QWEN_STT_LANGUAGE", "ja")

        with patch("backend.agents.stt_agent.QwenSTTClient") as mock_qwen_client:
            agent = STTAgent(stt_provider="qwen")

        assert agent.stt_provider == "qwen"
        mock_qwen_client.assert_called_once_with(
            model_variant="0.6b",
            device="cpu",
            default_language="ja",
        )

    def test_init_qwen_06b_cpu_provider(self, monkeypatch):
        """STTAgent accepts qwen0.6b-cpu provider and builds fixed CPU client"""
        monkeypatch.setenv("QWEN_STT_LANGUAGE", "ja")

        with patch("backend.agents.stt_agent.Qwen06BCpuSTTClient") as mock_qwen_client:
            agent = STTAgent(stt_provider="qwen0.6b-cpu")

        assert agent.stt_provider == "qwen0.6b-cpu"
        mock_qwen_client.assert_called_once_with(default_language="ja")

    def test_init_qwen_primary_timeout_env_guard(self, monkeypatch):
        """qwen-primary tolerates malformed QWEN_STT_TIMEOUT from prod env."""
        monkeypatch.setenv("QWEN_STT_TIMEOUT", "true")

        with (
            patch("backend.agents.stt_agent.Qwen06BCpuSTTClient"),
            patch("backend.agents.stt_agent.LocalSTTClient"),
        ):
            agent = STTAgent(stt_provider="qwen-primary")

        assert agent._qwen_timeout == pytest.approx(10.0)

    def test_init_qwen_primary_timeout_env_numeric(self, monkeypatch):
        """qwen-primary accepts numeric QWEN_STT_TIMEOUT values."""
        monkeypatch.setenv("QWEN_STT_TIMEOUT", "2.5")

        with (
            patch("backend.agents.stt_agent.Qwen06BCpuSTTClient"),
            patch("backend.agents.stt_agent.LocalSTTClient"),
        ):
            agent = STTAgent(stt_provider="qwen-primary")

        assert agent._qwen_timeout == pytest.approx(2.5)

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

    @pytest.mark.asyncio
    async def test_speech_to_text_qwen_returns_transcription_result(self):
        """STTAgent handles QwenSTTClient TranscriptionResult return type"""
        mock_client = AsyncMock(spec=QwenSTTClient)
        mock_client.default_language = "ja"
        mock_client.transcribe.return_value = TranscriptionResult(
            text="エンジニアカフェです",
            confidence=None,
            language="ja",
            word_confidences=[],
        )

        agent = STTAgent(stt_provider="qwen", stt_client=mock_client)
        result = await agent.speech_to_text(b"test_audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "エンジニアカフェです"
        assert result["confidence"] is None
        assert result["language"] == "ja"
        assert result["provider"] == "qwen"

    @pytest.mark.asyncio
    async def test_speech_to_text_qwen_06b_cpu_returns_transcription_result(self):
        """STTAgent handles Qwen06BCpuSTTClient TranscriptionResult return type"""
        mock_client = AsyncMock(spec=Qwen06BCpuSTTClient)
        mock_client.default_language = "ja"
        mock_client.transcribe.return_value = TranscriptionResult(
            text="コワーキングスペースをご案内します",
            confidence=None,
            language="ja",
            word_confidences=[],
        )

        agent = STTAgent(stt_provider="qwen0.6b-cpu", stt_client=mock_client)
        result = await agent.speech_to_text(b"test_audio", language="ja")

        assert result["success"] is True
        assert result["transcript"] == "コワーキングスペースをご案内します"
        assert result["confidence"] is None
        assert result["language"] == "ja"
        assert result["provider"] == "qwen0.6b-cpu"


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


class TestSTTLLMPostProcess:
    """STT LLM 後処理テスト"""

    @pytest.fixture
    def stt_agent(self):
        """Create STTAgent with vosk provider for testing"""
        with patch("backend.agents.stt_agent.LocalSTTClient"):
            agent = STTAgent(stt_provider="vosk")
        return agent

    @pytest.mark.asyncio
    async def test_postprocess_corrects_text(self, stt_agent):
        """LLM post-processing corrects domain terms"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "エンジニアカフェの営業時間は？"}}]
        }

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("backend.agents.stt_agent._get_stt_postprocess_client") as mock_client_fn,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client

            result = await stt_agent._llm_post_process(
                "えんじにあかふぇ の えいぎょうじかん は", "ja"
            )
            assert result == "エンジニアカフェの営業時間は？"

    @pytest.mark.asyncio
    async def test_postprocess_timeout_returns_original(self, stt_agent):
        """Timeout returns original transcript"""
        import httpx

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("backend.agents.stt_agent._get_stt_postprocess_client") as mock_client_fn,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_fn.return_value = mock_client

            result = await stt_agent._llm_post_process("テスト", "ja")
            assert result == "テスト"

    @pytest.mark.asyncio
    async def test_postprocess_disabled_via_env(self, stt_agent):
        """STT_LLM_POSTPROCESS=false skips LLM call at speech_to_text level"""
        with (
            patch.dict(
                "os.environ",
                {
                    "STT_LLM_POSTPROCESS": "false",
                    "OPENROUTER_API_KEY": "test-key",
                },
            ),
            patch.object(stt_agent, "_llm_post_process", new_callable=AsyncMock) as mock_pp,
            patch.object(
                stt_agent,
                "_try_fallback",
                new_callable=AsyncMock,
                return_value={
                    "success": True,
                    "transcript": "test",
                    "provider": "vosk",
                },
            ),
            patch.object(
                stt_agent.stt_client,
                "transcribe",
                new_callable=AsyncMock,
                return_value=TranscriptionResult(text="test", confidence=0.9, language="ja"),
            ),
        ):
            result = await stt_agent.speech_to_text(b"RIFF" + b"\x00" * 40, "ja")
            mock_pp.assert_not_called()
            assert result["transcript"] == "test"

    @pytest.mark.asyncio
    async def test_postprocess_no_api_key_returns_original(self, stt_agent):
        """No API key returns original transcript"""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            result = await stt_agent._llm_post_process("テスト", "ja")
            assert result == "テスト"

    @pytest.mark.asyncio
    async def test_postprocess_empty_transcript_returns_original(self, stt_agent):
        """Empty transcript is returned as-is"""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            result = await stt_agent._llm_post_process("", "ja")
            assert result == ""

    @pytest.mark.asyncio
    async def test_postprocess_rejects_divergent_output(self, stt_agent):
        """Output >3x input length is rejected as hallucination"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "A" * 300}}]}

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("backend.agents.stt_agent._get_stt_postprocess_client") as mock_fn,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_fn.return_value = mock_client

            result = await stt_agent._llm_post_process("短い", "ja")
            assert result == "短い"

    @pytest.mark.asyncio
    async def test_postprocess_integration_vosk_enabled(self, stt_agent):
        """Integration: Vosk + enabled → post-process runs"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "修正済み"}}]}

        with (
            patch.dict(
                "os.environ",
                {
                    "STT_LLM_POSTPROCESS": "true",
                    "OPENROUTER_API_KEY": "test-key",
                },
            ),
            patch("backend.agents.stt_agent._get_stt_postprocess_client") as mock_fn,
            patch.object(
                stt_agent,
                "_try_fallback",
                new_callable=AsyncMock,
                return_value={
                    "success": True,
                    "transcript": "元テキスト",
                    "provider": "vosk",
                },
            ),
            patch.object(
                stt_agent.stt_client,
                "transcribe",
                new_callable=AsyncMock,
                return_value=TranscriptionResult(text="元テキスト", confidence=0.9, language="ja"),
            ),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_fn.return_value = mock_client

            result = await stt_agent.speech_to_text(b"RIFF" + b"\x00" * 40, "ja")
            assert result["transcript"] == "修正済み"
            assert result["original_transcript"] == "元テキスト"
            assert result["postprocessed"] is True


# ==============================================================================
# Qwen Primary + Vosk Parallel Fallback (ADR-007)
# ==============================================================================


class TestQwenPrimaryParallel:
    """Tests for qwen-primary provider with Vosk parallel fallback."""

    def _make_agent(self, mock_qwen, mock_vosk):
        """Create STTAgent wired for qwen-primary with mock clients."""
        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_qwen,
            fallback_client=None,
            language_processor=None,
        )
        agent.stt_provider = "qwen-primary"
        agent._vosk_fallback_client = mock_vosk
        agent._qwen_timeout = 10.0
        return agent

    @pytest.mark.asyncio
    async def test_qwen_primary_success(self, caplog):
        """Qwen succeeds -> provider='qwen-primary'"""
        caplog.set_level(logging.INFO, logger="backend.observability.stt")
        mock_qwen = MagicMock()
        mock_qwen.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="こんにちは",
                confidence=0.95,
                language="ja",
            )
        )
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="こんにちわ",
                confidence=0.7,
                language="ja",
            )
        )

        agent = self._make_agent(mock_qwen, mock_vosk)
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["provider"] == "qwen-primary"
        assert result["transcript"] == "こんにちは"
        stt_records = [
            record for record in caplog.records if record.name == "backend.observability.stt"
        ]
        events = [getattr(record, "event", None) for record in stt_records]
        assert "stt_qwen_start" in events
        assert "stt_qwen_complete" in events
        assert "stt_winner" in events

        winner = next(
            record for record in stt_records if getattr(record, "event", None) == "stt_winner"
        )
        assert winner.stt_winner == "qwen"
        assert winner.provider == "qwen-primary"
        assert isinstance(winner.stt_overall_duration_ms, int)
        assert winner.stt_trace_id.startswith("stt-")

        qwen_complete = next(
            record
            for record in stt_records
            if getattr(record, "event", None) == "stt_qwen_complete"
        )
        assert qwen_complete.success is True
        assert isinstance(qwen_complete.stt_qwen_duration_ms, int)
        assert qwen_complete.stt_trace_id == winner.stt_trace_id

    @pytest.mark.asyncio
    async def test_qwen_success_does_not_wait_for_slow_vosk(self):
        """Qwen succeeds -> returns immediately without waiting for Vosk fallback."""
        import asyncio

        vosk_started = asyncio.Event()
        vosk_cancelled = asyncio.Event()

        async def slow_vosk(*args, **kwargs):
            vosk_started.set()
            try:
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                vosk_cancelled.set()
                raise
            return TranscriptionResult(
                text="slow fallback",
                confidence=0.7,
                language="ja",
            )

        mock_qwen = MagicMock()
        mock_qwen.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="qwen fast",
                confidence=0.95,
                language="ja",
            )
        )
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(side_effect=slow_vosk)

        agent = self._make_agent(mock_qwen, mock_vosk)
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        result = await agent.speech_to_text(b"audio", language="ja")
        elapsed = loop.time() - started_at

        assert result["success"] is True
        assert result["provider"] == "qwen-primary"
        assert result["transcript"] == "qwen fast"
        assert vosk_started.is_set()
        assert vosk_cancelled.is_set()
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_qwen_timeout_vosk_fallback(self):
        """Qwen times out -> Vosk fallback with provider='vosk-fallback'"""
        import asyncio

        async def slow_qwen(*args, **kwargs):
            await asyncio.sleep(20)
            return TranscriptionResult(text="late", confidence=0.9, language="ja")

        mock_qwen = MagicMock()
        mock_qwen.transcribe = slow_qwen
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="vosk result",
                confidence=0.8,
                language="ja",
            )
        )

        agent = self._make_agent(mock_qwen, mock_vosk)
        agent._qwen_timeout = 0.1
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["provider"] == "vosk-fallback"
        assert result["transcript"] == "vosk result"

    @pytest.mark.asyncio
    async def test_qwen_error_vosk_fallback(self):
        """Qwen raises exception -> Vosk fallback"""
        mock_qwen = MagicMock()
        mock_qwen.transcribe = AsyncMock(side_effect=RuntimeError("Model OOM"))
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="fallback ok",
                confidence=0.75,
                language="en",
            )
        )

        agent = self._make_agent(mock_qwen, mock_vosk)
        result = await agent.speech_to_text(b"audio", language="en")

        assert result["success"] is True
        assert result["provider"] == "vosk-fallback"
        assert result["transcript"] == "fallback ok"

    @pytest.mark.asyncio
    async def test_both_fail_raises(self):
        """Both Qwen and Vosk fail -> RuntimeError"""
        mock_qwen = MagicMock()
        mock_qwen.transcribe = AsyncMock(side_effect=RuntimeError("Qwen OOM"))
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(side_effect=RuntimeError("Vosk model missing"))

        agent = self._make_agent(mock_qwen, mock_vosk)
        with pytest.raises(RuntimeError, match="Both"):
            await agent.speech_to_text(b"audio", language="ja")

    @pytest.mark.asyncio
    async def test_vosk_ready_before_qwen(self):
        """Vosk completes first but Qwen still wins when it succeeds"""
        import asyncio

        async def slow_qwen(*args, **kwargs):
            await asyncio.sleep(0.05)
            return TranscriptionResult(
                text="qwen wins",
                confidence=0.95,
                language="ja",
            )

        mock_qwen = MagicMock()
        mock_qwen.transcribe = slow_qwen
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="vosk fast",
                confidence=0.8,
                language="ja",
            )
        )

        agent = self._make_agent(mock_qwen, mock_vosk)
        result = await agent.speech_to_text(b"audio", language="ja")

        assert result["provider"] == "qwen-primary"
        assert result["transcript"] == "qwen wins"

    @pytest.mark.asyncio
    async def test_language_auto_detect(self):
        """language=None -> Qwen called with language=None, Vosk uses auto_detect"""
        mock_qwen = MagicMock()
        mock_qwen.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="hello world",
                confidence=0.9,
                language="en",
            )
        )
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe_auto_detect = AsyncMock(
            return_value=TranscriptionResult(
                text="hello",
                confidence=0.7,
                language="en",
            )
        )

        agent = self._make_agent(mock_qwen, mock_vosk)
        result = await agent.speech_to_text(b"audio", language=None)

        assert result["provider"] == "qwen-primary"
        assert result["language"] == "en"
        mock_qwen.transcribe.assert_called_once_with(b"audio", language=None)
        mock_vosk.transcribe_auto_detect.assert_called_once_with(b"audio")

    @pytest.mark.asyncio
    async def test_vosk_fallback_with_llm_postprocess(self, monkeypatch):
        """Qwen fails, Vosk falls back, LLM post-processing runs"""
        monkeypatch.setenv("STT_LLM_POSTPROCESS", "true")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        mock_qwen = MagicMock()
        mock_qwen.transcribe = AsyncMock(side_effect=RuntimeError("Qwen OOM"))
        mock_vosk = MagicMock(spec=LocalSTTClient)
        mock_vosk.transcribe = AsyncMock(
            return_value=TranscriptionResult(
                text="えんじにあかふぇ",
                confidence=0.7,
                language="ja",
            )
        )

        agent = self._make_agent(mock_qwen, mock_vosk)
        with patch.object(
            agent,
            "_llm_post_process",
            new_callable=AsyncMock,
            return_value="エンジニアカフェ",
        ) as mock_llm:
            result = await agent.speech_to_text(b"audio", language="ja")

        assert result["success"] is True
        assert result["provider"] == "vosk-fallback"
        assert result["transcript"] == "エンジニアカフェ"
        assert result["postprocessed"] is True
        mock_llm.assert_called_once_with("えんじにあかふぇ", "ja")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
