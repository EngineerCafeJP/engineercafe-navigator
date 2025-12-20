"""
OpenRouter LLM Provider implementation.

Provides flexible model switching through OpenRouter API,
supporting multiple AI providers (OpenAI, Google, Anthropic, etc.)
through a unified interface.

See: https://openrouter.ai/docs
"""

import json
import os
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI

from .models import MODEL_CONFIGS, ModelConfig, SupportedModel
from .provider import LLMProvider


class OpenRouterError(Exception):
    """Exception raised for OpenRouter API errors."""

    def __init__(self, message: str, status_code: int = None, response: Dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter-based LLM provider.

    Supports all major LLM providers through a unified API:
    - Google (Gemini)
    - OpenAI (GPT-4, GPT-3.5)
    - Anthropic (Claude)
    - Meta (Llama)
    - Mistral

    Example:
        >>> provider = OpenRouterProvider()
        >>> response = await provider.generate([
        ...     HumanMessage(content="Hello!")
        ... ])
        >>> print(response)
        "Hello! How can I help you today?"

        >>> # For LangGraph integration
        >>> llm = provider.get_langchain_llm()
        >>> workflow.add_node("agent", llm)
    """

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenRouter provider.

        Args:
            api_key: OpenRouter API key. If not provided, reads from
                     OPENROUTER_API_KEY environment variable.

        Raises:
            ValueError: If no API key is found.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. "
                "Set OPENROUTER_API_KEY environment variable or pass api_key parameter."
            )

        self._app_url = os.getenv("APP_URL", "https://engineer-cafe.jp")
        self._app_name = "Engineer Cafe Navigator"

        self._http_client = httpx.AsyncClient(
            base_url=self.OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": self._app_url,
                "X-Title": self._app_name,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close HTTP client."""
        await self.close()

    async def close(self):
        """Close the HTTP client connection."""
        await self._http_client.aclose()

    def _convert_messages(self, messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """
        Convert LangChain messages to OpenRouter API format.

        Args:
            messages: List of LangChain message objects

        Returns:
            List of message dictionaries for the API
        """
        converted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                converted.append({"role": "system", "content": str(msg.content)})
            elif isinstance(msg, HumanMessage):
                converted.append({"role": "user", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                converted.append({"role": "assistant", "content": str(msg.content)})
            else:
                # Fallback for other message types
                converted.append({"role": "user", "content": str(msg.content)})
        return converted

    async def generate(
        self,
        messages: List[BaseMessage],
        config: Optional[ModelConfig] = None,
    ) -> str:
        """
        Generate a response using OpenRouter API.

        Args:
            messages: List of conversation messages
            config: Model configuration (defaults to qa_response config)

        Returns:
            Generated text response

        Raises:
            OpenRouterError: On API errors after fallback attempts
        """
        config = config or MODEL_CONFIGS["qa_response"]

        payload = {
            "model": config.model_id.value,
            "messages": self._convert_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }

        try:
            response = await self._http_client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or len(data["choices"]) == 0:
                raise OpenRouterError("No choices in response", response=data)

            return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            # Try fallback model if available
            if config.fallback_model:
                print(f"[OpenRouter] Primary model failed, trying fallback: {config.fallback_model.value}")
                fallback_config = ModelConfig(
                    model_id=config.fallback_model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    top_p=config.top_p,
                )
                return await self.generate(messages, fallback_config)

            raise OpenRouterError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            ) from e

        except httpx.RequestError as e:
            raise OpenRouterError(f"Network error: {str(e)}") from e

    async def stream(
        self,
        messages: List[BaseMessage],
        config: Optional[ModelConfig] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response using OpenRouter API.

        Args:
            messages: List of conversation messages
            config: Model configuration

        Yields:
            Text chunks as they are generated

        Raises:
            OpenRouterError: On API errors
        """
        config = config or MODEL_CONFIGS["qa_response"]

        payload = {
            "model": config.model_id.value,
            "messages": self._convert_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": True,
        }

        try:
            async with self._http_client.stream(
                "POST",
                "/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            if content := delta.get("content"):
                                yield content
                    except json.JSONDecodeError:
                        continue

        except httpx.HTTPStatusError as e:
            raise OpenRouterError(
                f"Streaming failed: {e.response.text}",
                status_code=e.response.status_code,
            ) from e

    def get_langchain_llm(
        self,
        config: Optional[ModelConfig] = None
    ) -> ChatOpenAI:
        """
        Get a LangChain-compatible LLM instance using OpenRouter.

        OpenRouter is compatible with OpenAI's API, so we use ChatOpenAI
        with a custom base_url pointing to OpenRouter.

        Args:
            config: Model configuration (defaults to qa_response)

        Returns:
            ChatOpenAI instance configured for OpenRouter

        Example:
            >>> provider = OpenRouterProvider()
            >>> llm = provider.get_langchain_llm(MODEL_CONFIGS["router"])
            >>> # Use in LangGraph workflow
            >>> result = await llm.ainvoke(messages)
        """
        config = config or MODEL_CONFIGS["qa_response"]

        return ChatOpenAI(
            model=config.model_id.value,
            openai_api_key=self.api_key,
            openai_api_base=self.OPENROUTER_BASE_URL,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            default_headers={
                "HTTP-Referer": self._app_url,
                "X-Title": self._app_name,
            },
        )

    async def list_models(self) -> List[Dict]:
        """
        List available models from OpenRouter.

        Returns:
            List of model information dictionaries

        Raises:
            OpenRouterError: On API errors
        """
        try:
            response = await self._http_client.get("/models")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except httpx.HTTPStatusError as e:
            raise OpenRouterError(
                f"Failed to list models: {e.response.text}",
                status_code=e.response.status_code,
            ) from e

    async def check_key_info(self) -> Dict:
        """
        Check API key information and rate limits.

        Returns:
            Dictionary with key information

        Raises:
            OpenRouterError: On API errors
        """
        try:
            response = await self._http_client.get("/auth/key")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise OpenRouterError(
                f"Failed to check key: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
