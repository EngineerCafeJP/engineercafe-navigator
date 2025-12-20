"""
Abstract LLM Provider interface.

This module defines the base class for LLM providers,
allowing flexible switching between different AI backends.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Optional, TYPE_CHECKING

from langchain_core.messages import BaseMessage

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI
    from .models import ModelConfig


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implementations should handle:
    - API authentication
    - Message format conversion
    - Error handling and fallback
    - Rate limiting
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[BaseMessage],
        config: Optional["ModelConfig"] = None,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            messages: List of conversation messages
            config: Optional model configuration

        Returns:
            Generated text response

        Raises:
            Exception: On API errors (after fallback attempts if configured)
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[BaseMessage],
        config: Optional["ModelConfig"] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response from the LLM.

        Args:
            messages: List of conversation messages
            config: Optional model configuration

        Yields:
            Text chunks as they are generated

        Raises:
            Exception: On API errors
        """
        pass

    @abstractmethod
    def get_langchain_llm(
        self,
        config: Optional["ModelConfig"] = None
    ) -> "ChatOpenAI":
        """
        Get a LangChain-compatible LLM instance.

        This allows integration with LangGraph workflows
        and other LangChain tooling.

        Args:
            config: Optional model configuration

        Returns:
            ChatOpenAI instance configured for this provider
        """
        pass


# Singleton instance storage
_provider_instance: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """
    Get the singleton LLM provider instance.

    This function lazily initializes the OpenRouterProvider
    and returns the same instance on subsequent calls.

    Returns:
        The LLM provider instance

    Example:
        >>> provider = get_llm_provider()
        >>> response = await provider.generate(messages)
    """
    global _provider_instance
    if _provider_instance is None:
        from .openrouter import OpenRouterProvider
        _provider_instance = OpenRouterProvider()
    return _provider_instance


def reset_provider() -> None:
    """
    Reset the singleton provider instance.

    Useful for testing or when configuration changes.
    """
    global _provider_instance
    _provider_instance = None
