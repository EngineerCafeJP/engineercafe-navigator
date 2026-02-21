"""
テストフィクスチャモジュール

ゴールデンデータセットとデータセットローダーを提供します。
"""

from backend.tests.fixtures.dataset_loader import (
    DatasetLoader,
    load_routing_test_cases,
    load_answer_quality_cases,
    load_multilingual_cases,
)

# Mock agents
from backend.tests.fixtures.mock_agents import (
    create_mock_orchestrator,
    create_mock_business_info_agent,
    create_mock_facility_agent,
    create_mock_event_agent,
    create_mock_slide_agent,
    create_mock_general_knowledge_agent,
    create_mock_vision_agent,
    create_mock_stt_agent,
    create_mock_voice_agent,
)

# Mock LLM
from backend.tests.fixtures.mock_llm import (
    create_mock_llm,
    create_mock_openrouter_provider,
    create_mock_chat_response,
    create_mock_structured_llm,
    create_mock_rag_search,
    create_mock_embedding_model,
    create_mock_langchain_tool,
)

# Sample states
from backend.tests.fixtures.sample_states import (
    create_text_query_state,
    create_image_query_state,
    create_memory_context,
    create_routing_decision,
    create_agent_response,
    create_workflow_state_with_routing,
    create_workflow_state_with_answer,
    create_multilingual_query_states,
    create_error_state,
)

# Sample images
from backend.tests.fixtures.sample_images import (
    create_blank_image,
    create_white_image,
    create_wide_image,
    create_exact_640_image,
    create_qr_like_image,
    create_gradient_image,
    create_checkerboard_image,
    create_colored_image,
    create_text_like_image,
    create_small_image,
    create_portrait_image,
    create_grayscale_image,
)

__all__ = [
    # Dataset loader
    "DatasetLoader",
    "load_routing_test_cases",
    "load_answer_quality_cases",
    "load_multilingual_cases",
    # Mock agents
    "create_mock_orchestrator",
    "create_mock_business_info_agent",
    "create_mock_facility_agent",
    "create_mock_event_agent",
    "create_mock_slide_agent",
    "create_mock_general_knowledge_agent",
    "create_mock_vision_agent",
    "create_mock_stt_agent",
    "create_mock_voice_agent",
    # Mock LLM
    "create_mock_llm",
    "create_mock_openrouter_provider",
    "create_mock_chat_response",
    "create_mock_structured_llm",
    "create_mock_rag_search",
    "create_mock_embedding_model",
    "create_mock_langchain_tool",
    # Sample states
    "create_text_query_state",
    "create_image_query_state",
    "create_memory_context",
    "create_routing_decision",
    "create_agent_response",
    "create_workflow_state_with_routing",
    "create_workflow_state_with_answer",
    "create_multilingual_query_states",
    "create_error_state",
    # Sample images
    "create_blank_image",
    "create_white_image",
    "create_wide_image",
    "create_exact_640_image",
    "create_qr_like_image",
    "create_gradient_image",
    "create_checkerboard_image",
    "create_colored_image",
    "create_text_like_image",
    "create_small_image",
    "create_portrait_image",
    "create_grayscale_image",
]
