"""Tests for STTAgent - Speech-to-Text integration"""

import pytest
import json
import io
import wave
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.stt_agent import LocalSTTClient, GoogleSTTClient, STTAgent


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
        assert client.model_path_ja == "models/vosk-model-ja"
        assert client.model_path_en == "models/vosk-model-en-us"

    def test_init_custom_paths(self):
        """LocalSTTClient accepts custom model paths"""
        client = LocalSTTClient(
            model_path_ja="custom/ja",
            model_path_en="custom/en"
        )
        assert client.model_path_ja == "custom/ja"
        assert client.model_path_en == "custom/en"

    def test_load_model_not_found_raises_error(self):
        """LocalSTTClient raises RuntimeError if Vosk model not found"""
        client = LocalSTTClient(model_path_ja="/nonexistent/path")
        
        with pytest.raises(RuntimeError) as exc_info:
            client._load_model("ja")
        
        assert "not found" in str(exc_info.value).lower()
        assert "alphacephei.com" in str(exc_info.value)  # Download URL in error message

    @pytest.mark.asyncio
    async def test_transcribe_vosk_success(self, test_wav_16khz):
        """LocalSTTClient.transcribe returns text for valid WAV input"""
        client = LocalSTTClient()
        
        # Mock Vosk's KaldiRecognizer
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps({
            "result": [
                {"conf": 1.0, "word": "こんにちは"}
            ],
            "text": "こんにちは"
        })
        
        with patch("vosk.KaldiRecognizer", return_value=mock_recognizer):
            with patch("vosk.Model"):
                with patch("backend.agents.stt_agent.LocalSTTClient._load_model") as mock_load:
                    mock_load.return_value = MagicMock()
                    
                    result = await client.transcribe(test_wav_16khz, language="ja")
                    assert isinstance(result, str)
                    assert "こんにちは" in result

    @pytest.mark.asyncio
    async def test_transcribe_empty_result_raises_error(self, test_wav_16khz):
        """LocalSTTClient raises error if Vosk returns empty transcript"""
        client = LocalSTTClient()
        
        mock_recognizer = MagicMock()
        mock_recognizer.FinalResult.return_value = json.dumps({
            "result": [],
            "text": ""
        })
        
        with patch("vosk.KaldiRecognizer", return_value=mock_recognizer):
            with patch("vosk.Model"):
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
        
        with patch("vosk.KaldiRecognizer", return_value=mock_recognizer):
            with patch("vosk.Model"):
                with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                    with pytest.raises(RuntimeError):
                        await client.transcribe(test_wav_16khz, language="ja")


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
# STTAgent Tests (Provider Switching)
# ==============================================================================


class TestSTTAgent:
    """Tests for STTAgent provider switching"""

    def test_init_default_provider_vosk(self):
        """STTAgent defaults to Vosk provider"""
        with patch("backend.agents.stt_agent.LocalSTTClient"):
            agent = STTAgent()
            assert agent.stt_provider == "vosk"

    def test_init_env_var_provider(self):
        """STTAgent reads STT_PROVIDER from environment"""
        import os
        os.environ["STT_PROVIDER"] = "google"
        
        with patch("backend.agents.stt_agent.GoogleSTTClient"):
            agent = STTAgent()
            assert agent.stt_provider == "google"
        
        # Clean up
        del os.environ["STT_PROVIDER"]

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

    @pytest.mark.asyncio
    async def test_speech_to_text_success(self):
        """STTAgent.speech_to_text returns unified success response"""
        mock_client = AsyncMock()
        mock_client.transcribe.return_value = "Test transcript"
        
        agent = STTAgent(stt_provider="vosk", stt_client=mock_client)
        result = await agent.speech_to_text(b"test_audio", language="ja")
        
        assert result["success"] is True
        assert result["transcript"] == "Test transcript"
        assert result["provider"] == "vosk"
        assert result["confidence"] is None

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


# ==============================================================================
# Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_stt_agent_with_mock_vosk():
    """Integration test: STTAgent with mocked Vosk"""
    # Create mock Vosk recognizer
    mock_recognizer = MagicMock()
    mock_recognizer.FinalResult.return_value = json.dumps({
        "text": "エンジニアカフェについて教えてください"
    })
    
    # Patch Vosk components
    with patch("vosk.KaldiRecognizer", return_value=mock_recognizer):
        with patch("vosk.Model"):
            with patch("backend.agents.stt_agent.LocalSTTClient._load_model"):
                # Create agent with Vosk (default)
                agent = STTAgent(stt_provider="vosk")
                
                # Generate test audio
                test_wav = generate_test_wav(sample_rate=16000)
                
                # Transcribe
                result = await agent.speech_to_text(test_wav, language="ja")
                
                # Verify result structure
                assert result["success"] is True
                assert result["provider"] == "vosk"
                assert "カフェ" in result["transcript"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
