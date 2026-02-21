"""Validation tests for fixture modules.

This file ensures all fixture factories work correctly and return expected structures.
"""

import pytest
import numpy as np
from langchain_core.messages import AIMessage

from backend.tests.fixtures import (
    # Mock agents
    create_mock_orchestrator,
    create_mock_business_info_agent,
    create_mock_vision_agent,
    create_mock_stt_agent,
    create_mock_voice_agent,
    # Mock LLM
    create_mock_llm,
    create_mock_openrouter_provider,
    create_mock_chat_response,
    create_mock_structured_llm,
    # Sample states
    create_text_query_state,
    create_image_query_state,
    create_memory_context,
    create_routing_decision,
    create_multilingual_query_states,
    # Sample images
    create_blank_image,
    create_white_image,
    create_wide_image,
    create_qr_like_image,
    create_text_like_image,
)


# =====================================================
# Mock Agents Tests
# =====================================================
@pytest.mark.asyncio
async def test_create_mock_orchestrator():
    """Test mock orchestrator returns correct routing decision."""
    mock = create_mock_orchestrator(
        next_agent="business_info", category="business-info", confidence=0.95
    )

    decision = await mock.decide_next_agent("test query")

    assert decision.next_agent == "business_info"
    assert decision.category == "business-info"
    assert decision.confidence == 0.95
    assert decision.language == "ja"
    await mock.close()


@pytest.mark.asyncio
async def test_create_mock_business_info_agent():
    """Test mock business info agent returns correct response."""
    mock = create_mock_business_info_agent(
        answer="営業時間は10:00-22:00です", emotion="informative"
    )

    result = await mock.answer_business_query("営業時間は？")

    assert result["answer"] == "営業時間は10:00-22:00です"
    assert result["emotion"] == "informative"
    assert result["metadata"]["agent"] == "BusinessInfoAgent"
    assert result["metadata"]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_create_mock_vision_agent():
    """Test mock vision agent returns OCR results."""
    mock = create_mock_vision_agent(text="こんにちは", expression="happy")

    result = await mock.recognize_image(np.zeros((100, 100, 3)))

    assert result["text"] == "こんにちは"
    assert result["expression"] == "happy"
    assert result["metadata"]["agent"] == "VisionAgent"


@pytest.mark.asyncio
async def test_create_mock_stt_agent():
    """Test mock STT agent returns transcript."""
    mock = create_mock_stt_agent(transcript="こんにちは", confidence=0.95)

    result = await mock.transcribe(b"fake audio data")

    assert result["transcript"] == "こんにちは"
    assert result["confidence"] == 0.95
    assert result["language"] == "ja"


@pytest.mark.asyncio
async def test_create_mock_voice_agent():
    """Test mock voice agent returns audio."""
    mock = create_mock_voice_agent(audio_base64="YXVkaW8=", emotion="happy")

    result = await mock.text_to_speech("こんにちは", emotion="happy")

    assert result["audio_base64"] == "YXVkaW8="
    assert result["emotion"] == "happy"
    assert result["metadata"]["provider"] == "google"


# =====================================================
# Mock LLM Tests
# =====================================================
@pytest.mark.asyncio
async def test_create_mock_llm():
    """Test mock LLM returns predictable response."""
    mock_llm = create_mock_llm(content="Test response")

    response = await mock_llm.ainvoke([])

    assert isinstance(response, AIMessage)
    assert response.content == "Test response"


def test_create_mock_openrouter_provider():
    """Test mock OpenRouter provider returns LLM."""
    provider = create_mock_openrouter_provider()

    llm = provider.get_langchain_llm()

    assert llm is not None
    assert hasattr(llm, "ainvoke")


def test_create_mock_chat_response():
    """Test mock chat response has correct structure."""
    response = create_mock_chat_response(content="営業時間は10:00-22:00です", emotion="informative")

    assert response["answer"] == "営業時間は10:00-22:00です"
    assert response["emotion"] == "informative"
    assert "metadata" in response
    assert response["metadata"]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_create_mock_structured_llm():
    """Test mock structured LLM returns JSON."""
    import json

    mock_llm = create_mock_structured_llm({"next_agent": "business_info"})

    response = await mock_llm.ainvoke([])
    data = json.loads(response.content)

    assert data["next_agent"] == "business_info"


# =====================================================
# Sample States Tests
# =====================================================
def test_create_text_query_state():
    """Test text query state has required fields."""
    state = create_text_query_state(query="営業時間は？", language="ja")

    assert state["query"] == "営業時間は？"
    assert state["language"] == "ja"
    assert state["session_id"] == "test-session"
    assert state["image_data"] is None
    assert state["answer"] is None


def test_create_image_query_state():
    """Test image query state includes image data."""
    state = create_image_query_state(query="What's in this image?")

    assert state["query"] == "What's in this image?"
    assert state["image_data"] is not None
    assert isinstance(state["image_data"], np.ndarray)
    assert state["image_data"].shape == (100, 100, 3)


def test_create_memory_context():
    """Test memory context structure."""
    context = create_memory_context(
        conversation_history=[
            {"role": "user", "content": "営業時間は？"},
            {"role": "assistant", "content": "10:00-22:00です"},
        ]
    )

    assert len(context["conversation_history"]) == 2
    assert context["conversation_history"][0]["role"] == "user"
    assert "session_metadata" in context


def test_create_routing_decision():
    """Test routing decision structure."""
    routing = create_routing_decision(agent="facility", category="facility", request_type="wifi")

    assert routing["agent"] == "facility"
    assert routing["category"] == "facility"
    assert routing["request_type"] == "wifi"
    assert routing["confidence"] == 0.95


def test_create_multilingual_query_states():
    """Test multilingual states include all languages."""
    states = create_multilingual_query_states()

    assert "ja" in states
    assert "en" in states
    assert "zh" in states
    assert "ko" in states
    assert states["ja"]["language"] == "ja"
    assert states["en"]["language"] == "en"


# =====================================================
# Sample Images Tests
# =====================================================
def test_create_blank_image():
    """Test blank image creation."""
    img = create_blank_image(100, 100, 3)

    assert img.shape == (100, 100, 3)
    assert img.dtype == np.uint8
    assert img.max() == 0  # All black


def test_create_white_image():
    """Test white image creation."""
    img = create_white_image(100, 100)

    assert img.shape == (100, 100, 3)
    assert img.min() == 255  # All white


def test_create_wide_image():
    """Test wide image creation."""
    img = create_wide_image(1920, 1080)

    assert img.shape == (1080, 1920, 3)
    assert img.shape[1] > 640  # Wider than 640px


def test_create_qr_like_image():
    """Test QR-like image has pattern."""
    img = create_qr_like_image()

    assert img.shape == (200, 200, 3)
    assert img.min() == 0  # Has black
    assert img.max() == 255  # Has white


def test_create_text_like_image():
    """Test text-like image creation."""
    img = create_text_like_image()

    assert img.shape == (200, 300, 3)
    # Should have both white background and black lines
    assert img.min() == 0
    assert img.max() == 255
