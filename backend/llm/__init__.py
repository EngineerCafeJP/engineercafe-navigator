"""
LLM Provider abstraction for Engineer Cafe Navigator.

Provides unified interface for AI model access through OpenRouter,
supporting multiple providers (OpenAI, Google, Anthropic, etc.).

Example:
    >>> from llm import get_llm_provider, MODEL_CONFIGS
    >>>
    >>> # Get the singleton provider
    >>> provider = get_llm_provider()
    >>>
    >>> # Generate a response
    >>> response = await provider.generate(
    ...     messages=[HumanMessage(content="Hello!")],
    ...     config=MODEL_CONFIGS["router"]
    ... )
    >>>
    >>> # Get LangChain-compatible LLM for LangGraph
    >>> llm = provider.get_langchain_llm(MODEL_CONFIGS["qa_response"])
"""

from .models import (
    MODEL_CONFIGS,
    ModelConfig,
    SupportedModel,
    get_model_config,
)
from .openrouter import OpenRouterError, OpenRouterProvider
from .provider import LLMProvider, get_llm_provider, reset_provider

__all__ = [
    # Provider classes
    "LLMProvider",
    "OpenRouterProvider",
    # Factory functions
    "get_llm_provider",
    "reset_provider",
    "get_model_config",
    # Configuration
    "ModelConfig",
    "SupportedModel",
    "MODEL_CONFIGS",
    # Exceptions
    "OpenRouterError",
]

__version__ = "1.0.0"
