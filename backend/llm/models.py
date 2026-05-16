"""
Model configuration and supported models registry.

This module defines the available AI models through OpenRouter
and their configurations for different use cases.

Runtime IDs may be overridden via env (see model_resolve.py); defaults follow the 2026-04 naming.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SupportedModel(str, Enum):
    """
    Supported AI models through OpenRouter.

    These models are available via the unified OpenRouter API.
    See https://openrouter.ai/docs#models for full list.

    Last updated: 2026-04-30
    """

    # Google — latency-optimized tier
    GEMINI_3_1_FLASH_LITE = "google/gemini-3.1-flash-lite-preview"
    GEMINI_3_FLASH = "google/gemini-3-flash-preview"  # comparison / benchmarks only
    GEMINI_2_5_FLASH_LITE = "google/gemini-2.5-flash-lite"  # stable fallback
    # Google — reasoning / multimodal
    GEMINI_3_1_PRO = "google/gemini-3.1-pro-preview"
    GEMINI_3_PRO = "google/gemini-3-pro-preview"  # legacy preview id; prefer GEMINI_3_1_PRO
    GEMINI_2_5_PRO = "google/gemini-2.5-pro"  # stable fallback

    # OpenAI Models (OpenRouter slug) — GPT-5.4/5.5 family (2026 Q1–Q2 on OpenRouter)
    GPT_5_5 = "openai/gpt-5.5"  # Released 2026-04 (frontier; fallback for deep reasoning)
    GPT_5_4 = "openai/gpt-5.4"  # 2026-03 general frontier
    GPT_5_4_MINI = "openai/gpt-5.4-mini"  # High-throughput / mid cost
    GPT_5_4_NANO = "openai/gpt-5.4-nano"  # Low-latency classification & sub-agent tasks
    GPT_5_2 = "openai/gpt-5.2"
    GPT_5_MINI = "openai/gpt-5-mini"  # Legacy; prefer GPT_5_4_NANO for fast fallbacks
    GPT_5_1 = "openai/gpt-5.1-chat"

    # Anthropic Models
    CLAUDE_SONNET_4_6 = "anthropic/claude-sonnet-4.6"
    CLAUDE_OPUS_4_5 = "anthropic/claude-opus-4.5"
    CLAUDE_HAIKU_4_5 = "anthropic/claude-haiku-4.5"
    CLAUDE_SONNET_4 = "anthropic/claude-sonnet-4"
    CLAUDE_3_5_SONNET = "anthropic/claude-3.5-sonnet"

    # Meta Models
    LLAMA_3_3_NEMOTRON = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    LLAMA_3_2_90B = "meta-llama/llama-3.2-90b-vision-instruct"
    LLAMA_3_1_70B = "meta-llama/llama-3.1-70b-instruct"

    # Mistral Models
    MISTRAL_LARGE = "mistralai/mistral-large-2512"
    MISTRAL_SMALL = "mistralai/mistral-small-creative"
    DEVSTRAL = "mistralai/devstral-2512"

    # Vision (lightweight, tool-use capable)
    GPT_4O = "openai/gpt-4o"
    GPT_4_1_NANO = "openai/gpt-4.1-nano"


@dataclass
class ModelConfig:
    """
    Configuration for an LLM model.

    Attributes:
        model_id: The model identifier from SupportedModel enum
        temperature: Sampling temperature (0.0-2.0), lower = more deterministic
        max_tokens: Maximum tokens to generate
        top_p: Nucleus sampling parameter
        fallback_model: Backup model if primary fails (same OpenRouter API)
        timeout: Request timeout in seconds
        allow_cerebras_primary: Allow direct Cerebras before OpenRouter for lightweight answers
        cerebras_primary_use_case: Stable use-case name for env allowlist checks
        primary_model_env: Optional env var that overrides the primary OpenRouter slug
        fallback_model_env: Optional env var that overrides the fallback OpenRouter slug
    """

    model_id: SupportedModel
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    fallback_model: Optional[SupportedModel] = None
    timeout: float = 30.0
    allow_cerebras_primary: bool = False
    cerebras_primary_use_case: Optional[str] = None
    primary_model_env: Optional[str] = None
    fallback_model_env: Optional[str] = None

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


# Fast tier: optional direct Cerebras first pass, then Gemini 3.1 Flash-Lite preview
# -> Gemini 2.5 Flash-Lite stable through OpenRouter.
# Deep path: Gemini 3.1 Pro preview -> Gemini 2.5 Pro stable.
# Optional Cerebras direct hop: gpt-oss-120b (model_resolve), enabled by env.
MODEL_CONFIGS: dict[str, ModelConfig] = {
    "router": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        temperature=0.3,
        max_tokens=256,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    "qa_response": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        temperature=0.7,
        max_tokens=1024,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        allow_cerebras_primary=True,
        cerebras_primary_use_case="qa_response",
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    "clarification": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        temperature=0.5,
        max_tokens=512,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    "general_knowledge": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        temperature=0.7,
        max_tokens=1024,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        allow_cerebras_primary=True,
        cerebras_primary_use_case="general_knowledge",
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    # Deep reasoning — explicit keyword-gated path for complex reasoning only.
    "deep_reasoning": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_PRO,
        temperature=0.5,
        max_tokens=1536,
        fallback_model=SupportedModel.GEMINI_2_5_PRO,
        input_cost_per_1k=0.002,
        output_cost_per_1k=0.012,
    ),
    "event_info": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        temperature=0.4,
        max_tokens=512,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        allow_cerebras_primary=True,
        cerebras_primary_use_case="event_info",
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    "facility_info": ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        temperature=0.5,
        max_tokens=768,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        allow_cerebras_primary=True,
        cerebras_primary_use_case="facility_info",
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    "vision": ModelConfig(
        model_id=SupportedModel.GPT_4_1_NANO,
        temperature=0.0,
        max_tokens=512,
        fallback_model=SupportedModel.GPT_5_4_NANO,
        primary_model_env="VISION_MODEL",
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
    ),
    "vision_handwriting": ModelConfig(
        model_id=SupportedModel.GPT_4O,
        temperature=0.0,
        max_tokens=256,
        fallback_model=SupportedModel.GPT_4_1_NANO,
        timeout=20.0,
        primary_model_env="VISION_HANDWRITING_MODEL",
        fallback_model_env="VISION_HANDWRITING_FALLBACK_MODEL",
        input_cost_per_1k=0.002,
        output_cost_per_1k=0.012,
    ),
}


def get_model_config(use_case: str) -> ModelConfig:
    """Get the model configuration for a specific use case."""
    if use_case not in MODEL_CONFIGS:
        available = ", ".join(MODEL_CONFIGS.keys())
        raise KeyError(f"Unknown use case: {use_case}. Available: {available}")
    return MODEL_CONFIGS[use_case]
