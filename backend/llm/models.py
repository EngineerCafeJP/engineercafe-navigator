"""
Model configuration and supported models registry.

This module defines the available AI models through OpenRouter
and their configurations for different use cases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SupportedModel(str, Enum):
    """
    Supported AI models through OpenRouter.

    These models are available via the unified OpenRouter API.
    See https://openrouter.ai/docs#models for full list.
    """

    # Google Models
    GEMINI_2_5_FLASH = "google/gemini-2.5-flash-preview"
    GEMINI_2_0_FLASH = "google/gemini-2.0-flash-exp"
    GEMINI_PRO = "google/gemini-pro"
    GEMINI_PRO_VISION = "google/gemini-pro-vision"

    # OpenAI Models
    GPT_4O = "openai/gpt-4o"
    GPT_4O_MINI = "openai/gpt-4o-mini"
    GPT_4_TURBO = "openai/gpt-4-turbo"
    GPT_4 = "openai/gpt-4"
    GPT_3_5_TURBO = "openai/gpt-3.5-turbo"

    # Anthropic Models
    CLAUDE_3_5_SONNET = "anthropic/claude-3.5-sonnet"
    CLAUDE_3_OPUS = "anthropic/claude-3-opus"
    CLAUDE_3_HAIKU = "anthropic/claude-3-haiku"

    # Meta Models
    LLAMA_3_2_90B = "meta-llama/llama-3.2-90b-vision-instruct"
    LLAMA_3_1_70B = "meta-llama/llama-3.1-70b-instruct"
    LLAMA_3_1_8B = "meta-llama/llama-3.1-8b-instruct"

    # Mistral Models
    MISTRAL_LARGE = "mistralai/mistral-large-latest"
    MISTRAL_MEDIUM = "mistralai/mistral-medium"
    MISTRAL_SMALL = "mistralai/mistral-small"


@dataclass
class ModelConfig:
    """
    Configuration for an LLM model.

    Attributes:
        model_id: The model identifier from SupportedModel enum
        temperature: Sampling temperature (0.0-2.0), lower = more deterministic
        max_tokens: Maximum tokens to generate
        top_p: Nucleus sampling parameter
        fallback_model: Backup model if primary fails
        timeout: Request timeout in seconds
    """

    model_id: SupportedModel
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    fallback_model: Optional[SupportedModel] = None
    timeout: float = 30.0

    # Metadata for cost tracking (approximate, per 1K tokens)
    input_cost_per_1k: float = field(default=0.0, repr=False)
    output_cost_per_1k: float = field(default=0.0, repr=False)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"Temperature must be between 0.0 and 2.0, got {self.temperature}")
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if not 0.0 <= self.top_p <= 1.0:
            raise ValueError(f"top_p must be between 0.0 and 1.0, got {self.top_p}")


# Pre-configured model settings for common use cases
MODEL_CONFIGS: dict[str, ModelConfig] = {
    # Router Agent: Low temperature for consistent routing decisions
    "router": ModelConfig(
        model_id=SupportedModel.GEMINI_2_5_FLASH,
        temperature=0.3,
        max_tokens=256,
        fallback_model=SupportedModel.GPT_4O_MINI,
    ),

    # Q&A Response: Balanced settings for informative responses
    "qa_response": ModelConfig(
        model_id=SupportedModel.GEMINI_2_5_FLASH,
        temperature=0.7,
        max_tokens=1024,
        fallback_model=SupportedModel.GPT_4O,
    ),

    # Clarification: Helpful tone for disambiguation
    "clarification": ModelConfig(
        model_id=SupportedModel.GEMINI_2_5_FLASH,
        temperature=0.5,
        max_tokens=512,
        fallback_model=SupportedModel.GPT_4O_MINI,
    ),

    # General Knowledge: Higher creativity for diverse topics
    "general_knowledge": ModelConfig(
        model_id=SupportedModel.GEMINI_2_5_FLASH,
        temperature=0.8,
        max_tokens=1024,
        fallback_model=SupportedModel.GPT_4O,
    ),

    # Event Information: Factual, structured responses
    "event_info": ModelConfig(
        model_id=SupportedModel.GEMINI_2_5_FLASH,
        temperature=0.4,
        max_tokens=512,
        fallback_model=SupportedModel.GPT_4O_MINI,
    ),

    # Facility Information: Detailed, accurate responses
    "facility_info": ModelConfig(
        model_id=SupportedModel.GEMINI_2_5_FLASH,
        temperature=0.5,
        max_tokens=768,
        fallback_model=SupportedModel.GPT_4O_MINI,
    ),
}


def get_model_config(use_case: str) -> ModelConfig:
    """
    Get the model configuration for a specific use case.

    Args:
        use_case: The use case key (e.g., "router", "qa_response")

    Returns:
        ModelConfig for the specified use case

    Raises:
        KeyError: If use case is not found
    """
    if use_case not in MODEL_CONFIGS:
        available = ", ".join(MODEL_CONFIGS.keys())
        raise KeyError(f"Unknown use case: {use_case}. Available: {available}")
    return MODEL_CONFIGS[use_case]
