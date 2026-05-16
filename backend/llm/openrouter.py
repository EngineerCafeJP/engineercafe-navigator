"""
OpenRouter LLM Provider implementation.

Provides flexible model switching through OpenRouter API,
supporting multiple AI providers (OpenAI, Google, Anthropic, etc.)
through a unified interface.

Optional fast-path primary/fallback via Cerebras (see model_resolve.py).

See: https://openrouter.ai/docs
"""

import json
import logging
import os
import time
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI

from .models import MODEL_CONFIGS, ModelConfig
from .model_resolve import (
    cerebras_fallback_enabled,
    cerebras_model_slug,
    cerebras_primary_enabled,
    cerebras_reasoning_effort,
    cerebras_timeout_seconds,
    merge_gemini_openrouter_extra,
    openrouter_timeout_seconds,
    resolved_openrouter_model_slug,
)
from .provider import LLMProvider
from backend.utils.token_tracker import get_token_tracker, record_llm_call_metadata

logger = logging.getLogger(__name__)

CEREBRAS_CHAT_URL = os.getenv(
    "CEREBRAS_API_BASE_URL", "https://api.cerebras.ai/v1/chat/completions"
).rstrip("/")


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

    @staticmethod
    def _record_successful_llm_call(*, provider: str, model: str, started_at: float) -> None:
        """Record request-scoped provider/model metadata without shared instance state."""

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            record_llm_call_metadata(
                provider=provider,
                model=model,
                llm_latency_ms=latency_ms,
            )
        except Exception as e:
            logger.debug("LLM metadata tracking failed (non-critical): %s", e)

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

    def _build_openrouter_payload(self, messages: List[BaseMessage], config: ModelConfig) -> Dict:
        slug = resolved_openrouter_model_slug(config)
        payload: Dict = {
            "model": slug,
            "messages": self._convert_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }
        merge_gemini_openrouter_extra(payload)
        return payload

    @staticmethod
    def _build_fallback_config(config: ModelConfig) -> ModelConfig:
        """Promote fallback model settings into a single-attempt primary config."""
        if config.fallback_model is None:
            raise OpenRouterError("Fallback model is not configured")
        return ModelConfig(
            model_id=config.fallback_model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            fallback_model=None,
            timeout=config.timeout,
            primary_model_env=config.fallback_model_env,
        )

    async def _cerebras_generate(self, messages: List[BaseMessage], config: ModelConfig) -> str:
        api_key = os.getenv("CEREBRAS_API_KEY", "").strip()
        if not api_key:
            raise OpenRouterError("CEREBRAS_API_KEY missing for fallback")
        model_id = cerebras_model_slug()
        body: Dict = {
            "model": model_id,
            "messages": self._convert_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }
        effort = cerebras_reasoning_effort()
        if effort:
            body["reasoning_effort"] = effort
        async with httpx.AsyncClient(
            timeout=cerebras_timeout_seconds(config),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        ) as cerebras_http:
            response = await cerebras_http.post(CEREBRAS_CHAT_URL, json=body)
            response.raise_for_status()
            data = response.json()
        if "choices" not in data or len(data["choices"]) == 0:
            raise OpenRouterError("No choices in Cerebras response", response=data)
        if "usage" in data:
            try:
                tracker = get_token_tracker()
                tracker.record(
                    model=model_id,
                    prompt_tokens=data["usage"].get("prompt_tokens", 0),
                    completion_tokens=data["usage"].get("completion_tokens", 0),
                )
            except Exception as e:
                logger.debug("Token tracking failed (non-critical): %s", e)
        return data["choices"][0]["message"]["content"]

    async def generate(
        self,
        messages: List[BaseMessage],
        config: Optional[ModelConfig] = None,
        _fallback_count: int = 0,
        *,
        _root_config: Optional[ModelConfig] = None,
        _cerebras_tried: bool = False,
    ) -> str:
        """
        Generate a response using OpenRouter API.

        Args:
            messages: List of conversation messages
            config: Model configuration (defaults to qa_response config)
            _fallback_count: Internal counter to prevent infinite fallback loops
            _root_config: First config when recursing OpenRouter fallback (for Cerebras gate)
            _cerebras_tried: Whether Cerebras has already been attempted for this request

        Returns:
            Generated text response

        Raises:
            OpenRouterError: On API errors after fallback attempts
        """
        config = config or MODEL_CONFIGS["qa_response"]
        root_cfg = _root_config or config

        if cerebras_primary_enabled(root_cfg) and _fallback_count == 0 and not _cerebras_tried:
            logger.info("Trying Cerebras fast primary model=%s", cerebras_model_slug())
            try:
                started_at = time.perf_counter()
                response_text = await self._cerebras_generate(messages, root_cfg)
                self._record_successful_llm_call(
                    provider="cerebras",
                    model=cerebras_model_slug(),
                    started_at=started_at,
                )
                return response_text
            except Exception as ce:
                _cerebras_tried = True
                logger.warning("Cerebras primary failed; falling back to OpenRouter: %s", ce)

        payload = self._build_openrouter_payload(messages, config)
        primary_slug = payload["model"]

        try:
            started_at = time.perf_counter()
            response = await self._http_client.post(
                "/chat/completions",
                json=payload,
                timeout=openrouter_timeout_seconds(config),
            )
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or len(data["choices"]) == 0:
                raise OpenRouterError("No choices in response", response=data)

            if "usage" in data:
                try:
                    tracker = get_token_tracker()
                    tracker.record(
                        model=primary_slug,
                        prompt_tokens=data["usage"].get("prompt_tokens", 0),
                        completion_tokens=data["usage"].get("completion_tokens", 0),
                    )
                except Exception as e:
                    logger.debug("Token tracking failed (non-critical): %s", e)

            response_text = data["choices"][0]["message"]["content"]
            self._record_successful_llm_call(
                provider="openrouter",
                model=primary_slug,
                started_at=started_at,
            )
            return response_text

        except httpx.HTTPStatusError as e:
            if config.fallback_model and _fallback_count < 1:
                fallback_config = self._build_fallback_config(config)
                fb_slug = resolved_openrouter_model_slug(fallback_config)
                logger.warning(
                    "HTTP error (status %d), trying OpenRouter fallback: %s",
                    e.response.status_code,
                    fb_slug,
                )
                return await self.generate(
                    messages,
                    fallback_config,
                    _fallback_count=_fallback_count + 1,
                    _root_config=root_cfg,
                    _cerebras_tried=_cerebras_tried,
                )

            if cerebras_fallback_enabled(root_cfg) and not _cerebras_tried:
                logger.warning(
                    "OpenRouter failed (status=%s); trying Cerebras model=%s",
                    getattr(e.response, "status_code", "?"),
                    cerebras_model_slug(),
                )
                try:
                    started_at = time.perf_counter()
                    response_text = await self._cerebras_generate(messages, root_cfg)
                    self._record_successful_llm_call(
                        provider="cerebras",
                        model=cerebras_model_slug(),
                        started_at=started_at,
                    )
                    return response_text
                except Exception as ce:
                    logger.warning("Cerebras fallback failed: %s", ce, exc_info=True)

            raise OpenRouterError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            ) from e

        except httpx.RequestError as e:
            if config.fallback_model and _fallback_count < 1:
                fallback_config = self._build_fallback_config(config)
                logger.warning(
                    "Network error, trying fallback: %s",
                    resolved_openrouter_model_slug(fallback_config),
                )
                return await self.generate(
                    messages,
                    fallback_config,
                    _fallback_count=_fallback_count + 1,
                    _root_config=root_cfg,
                    _cerebras_tried=_cerebras_tried,
                )

            if cerebras_fallback_enabled(root_cfg) and not _cerebras_tried:
                logger.warning("OpenRouter transport error; trying Cerebras: %s", e)
                try:
                    started_at = time.perf_counter()
                    response_text = await self._cerebras_generate(messages, root_cfg)
                    self._record_successful_llm_call(
                        provider="cerebras",
                        model=cerebras_model_slug(),
                        started_at=started_at,
                    )
                    return response_text
                except Exception as ce:
                    logger.warning("Cerebras fallback failed: %s", ce, exc_info=True)

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

        payload = self._build_openrouter_payload(messages, config)
        payload["stream"] = True

        try:
            async with self._http_client.stream(
                "POST",
                "/chat/completions",
                json=payload,
                timeout=openrouter_timeout_seconds(config),
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

    def get_langchain_llm(self, config: Optional[ModelConfig] = None) -> ChatOpenAI:
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

        slug = resolved_openrouter_model_slug(config)

        return ChatOpenAI(
            model=slug,
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
