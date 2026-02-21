"""Reusable mock agent factories for testing."""

from unittest.mock import AsyncMock, MagicMock
from typing import Optional, Dict, Any


def create_mock_orchestrator(
    next_agent: str = "business_info",
    category: str = "business-info",
    language: str = "ja",
    request_type: Optional[str] = "general",
    confidence: float = 0.95,
) -> MagicMock:
    """Create a mock OrchestratorAgent with configurable routing decision.

    Args:
        next_agent: Next agent to route to (e.g., "business_info", "facility")
        category: Query category
        language: Language code (ja, en, etc.)
        request_type: Request type (hours, price, wifi, etc.)
        confidence: Confidence score (0.0-1.0)

    Returns:
        Mock OrchestratorAgent with decide_next_agent method

    Examples:
        >>> mock = create_mock_orchestrator(next_agent="facility", category="wifi")
        >>> decision = await mock.decide_next_agent("Wi-Fi password?")
        >>> assert decision.next_agent == "facility"
    """
    mock = MagicMock()
    decision = MagicMock()
    decision.next_agent = next_agent
    decision.category = category
    decision.language = language
    decision.request_type = request_type
    decision.confidence = confidence
    decision.reasoning = "test routing"
    decision.debug_info = {}
    mock.decide_next_agent = AsyncMock(return_value=decision)
    mock.close = AsyncMock()
    return mock


def create_mock_business_info_agent(
    answer: str = "営業情報です",
    emotion: str = "happy",
    confidence: float = 0.9,
    metadata: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    """Create a mock BusinessInfoAgent.

    Args:
        answer: Answer text
        emotion: Emotion tag (happy, relaxed, sad, etc.)
        confidence: Confidence score
        metadata: Additional metadata

    Returns:
        Mock BusinessInfoAgent with answer_business_query method

    Examples:
        >>> mock = create_mock_business_info_agent(answer="10:00-22:00です", emotion="informative")
        >>> result = await mock.answer_business_query("営業時間は？")
        >>> assert result["answer"] == "10:00-22:00です"
    """
    mock = MagicMock()
    default_metadata = {
        "agent": "BusinessInfoAgent",
        "confidence": confidence,
        "category": "business-info",
        "sources": [],
    }
    if metadata:
        default_metadata.update(metadata)

    response = {
        "answer": answer,
        "emotion": emotion,
        "metadata": default_metadata,
    }
    mock.answer_business_query = AsyncMock(return_value=response)
    return mock


def create_mock_facility_agent(
    answer: str = "施設情報です",
    emotion: str = "neutral",
    confidence: float = 0.9,
) -> MagicMock:
    """Create a mock FacilityAgent.

    Args:
        answer: Answer text
        emotion: Emotion tag
        confidence: Confidence score

    Returns:
        Mock FacilityAgent with answer_facility_query method
    """
    mock = MagicMock()
    response = {
        "answer": answer,
        "emotion": emotion,
        "metadata": {
            "agent": "FacilityAgent",
            "confidence": confidence,
            "category": "facility",
        },
    }
    mock.answer_facility_query = AsyncMock(return_value=response)
    return mock


def create_mock_event_agent(
    answer: str = "イベント情報です",
    emotion: str = "excited",
    confidence: float = 0.9,
) -> MagicMock:
    """Create a mock EventAgent.

    Args:
        answer: Answer text
        emotion: Emotion tag
        confidence: Confidence score

    Returns:
        Mock EventAgent with answer_event_query method
    """
    mock = MagicMock()
    response = {
        "answer": answer,
        "emotion": emotion,
        "metadata": {
            "agent": "EventAgent",
            "confidence": confidence,
            "category": "event",
        },
    }
    mock.answer_event_query = AsyncMock(return_value=response)
    return mock


def create_mock_slide_agent(
    answer: str = "スライド情報です",
    emotion: str = "neutral",
    confidence: float = 0.9,
) -> MagicMock:
    """Create a mock SlideAgent.

    Args:
        answer: Answer text
        emotion: Emotion tag
        confidence: Confidence score

    Returns:
        Mock SlideAgent with handle_slide_query method
    """
    mock = MagicMock()
    response = {
        "answer": answer,
        "emotion": emotion,
        "metadata": {
            "agent": "SlideAgent",
            "confidence": confidence,
            "category": "slide",
        },
    }
    mock.handle_slide_query = AsyncMock(return_value=response)
    return mock


def create_mock_general_knowledge_agent(
    answer: str = "一般回答です",
    emotion: str = "neutral",
    confidence: float = 0.8,
) -> MagicMock:
    """Create a mock GeneralKnowledgeAgent.

    Args:
        answer: Answer text
        emotion: Emotion tag
        confidence: Confidence score

    Returns:
        Mock GeneralKnowledgeAgent with answer_general_query method
    """
    mock = MagicMock()
    response = {
        "answer": answer,
        "emotion": emotion,
        "metadata": {
            "agent": "GeneralKnowledgeAgent",
            "confidence": confidence,
            "category": "general-knowledge",
        },
    }
    mock.answer_general_query = AsyncMock(return_value=response)
    return mock


def create_mock_vision_agent(
    text: Optional[str] = "OCR text",
    expression: Optional[str] = "happy",
) -> MagicMock:
    """Create a mock VisionAgent with configurable OCR results.

    Args:
        text: Recognized text (None if no text detected)
        expression: Detected facial expression (None if no face detected)

    Returns:
        Mock VisionAgent with recognize_image method

    Examples:
        >>> mock = create_mock_vision_agent(text="こんにちは", expression="happy")
        >>> result = await mock.recognize_image(image_data)
        >>> assert result["text"] == "こんにちは"
    """
    mock = MagicMock()
    response = {
        "text": text,
        "expression": expression,
        "metadata": {
            "agent": "VisionAgent",
            "ocr_confidence": 0.95 if text else 0.0,
            "face_confidence": 0.9 if expression else 0.0,
        },
    }
    mock.recognize_image = AsyncMock(return_value=response)
    return mock


def create_mock_stt_agent(
    transcript: str = "テスト音声",
    confidence: float = 0.9,
    language: str = "ja",
) -> MagicMock:
    """Create a mock STTAgent (Speech-to-Text).

    Args:
        transcript: Transcribed text
        confidence: Transcription confidence
        language: Detected language

    Returns:
        Mock STTAgent with transcribe method

    Examples:
        >>> mock = create_mock_stt_agent(transcript="こんにちは")
        >>> result = await mock.transcribe(audio_data)
        >>> assert result["transcript"] == "こんにちは"
    """
    mock = MagicMock()
    response = {
        "transcript": transcript,
        "confidence": confidence,
        "language": language,
        "metadata": {
            "agent": "STTAgent",
            "duration_ms": 1000,
        },
    }
    mock.transcribe = AsyncMock(return_value=response)
    return mock


def create_mock_voice_agent(
    audio_base64: str = "dGVzdA==",
    emotion: str = "neutral",
) -> MagicMock:
    """Create a mock VoiceAgent (Text-to-Speech).

    Args:
        audio_base64: Base64-encoded audio data
        emotion: Emotion tag used for synthesis

    Returns:
        Mock VoiceAgent with text_to_speech method

    Examples:
        >>> mock = create_mock_voice_agent(audio_base64="YXVkaW8=", emotion="happy")
        >>> result = await mock.text_to_speech("こんにちは", emotion="happy")
        >>> assert result["audio_base64"] == "YXVkaW8="
    """
    mock = MagicMock()
    response = {
        "audio_base64": audio_base64,
        "emotion": emotion,
        "metadata": {
            "agent": "VoiceAgent",
            "provider": "google",
            "duration_ms": 1500,
        },
    }
    mock.text_to_speech = AsyncMock(return_value=response)
    return mock
