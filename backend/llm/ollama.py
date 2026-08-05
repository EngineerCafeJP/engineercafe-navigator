"""
Ollama (OpenAI互換API) LLM Provider 実装

ローカルの Ollama サーバー（Metal GPU）と OpenAI互換の HTTP API で通信する
軽量プロバイダ。COSCUP デモ用のホットパスであり、フォールバックや
Cerebras 連携などの複雑なチェーンは一切持たない。

OpenRouter プロバイダと同じメッセージ変換・ペイロード形状を用いるが、
Ollama 固有のヘッダー（HTTP-Referer / X-Title 等）や余分なペイロードは送らない。

参考: https://github.com/ollama/ollama/blob/main/docs/openai.md
"""

import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI

from .models import MODEL_CONFIGS, ModelConfig
from .openrouter import LLMResponseText
from .provider import LLMProvider
from backend.utils.token_tracker import record_llm_call_metadata

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Ollama API エラー用の例外。"""

    def __init__(self, message: str, status_code: int = None, response: Dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class OllamaProvider(LLMProvider):
    """
    Ollama（ローカルLLM）プロバイダ。

    Docker 内のバックエンドからホストマシン上の Ollama (Metal GPU) に
    OpenAI互換の /v1/chat/completions エンドポイント経由で接続する。

    Example:
        >>> provider = OllamaProvider()
        >>> response = await provider.generate([
        ...     HumanMessage(content="Hello!")
        ... ])
        >>> print(response)
        "Hello! How can I help you today?"

        >>> # LangGraph 連携用
        >>> llm = provider.get_langchain_llm()
        >>> workflow.add_node("agent", llm)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        プロバイダを初期化する。

        Ollama は API キーを検証しないが、OpenAI互換クライアントが
        Authorization ヘッダーを要求するためダミーキーを設定する。

        Args:
            api_key: Ollama API キー。未指定時は OLLAMA_API_KEY
                     環境変数（デフォルト "dummy"）を使用。
        """
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY", "dummy")
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "qwen3:8b")

        self._http_client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def __aenter__(self):
        """非同期コンテキストマネージャのエントリ。"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャの終了 - HTTP クライアントを閉じる。"""
        await self.close()

    async def close(self):
        """HTTP クライアントの接続を閉じる。"""
        await self._http_client.aclose()

    @staticmethod
    def _convert_messages(messages: List[BaseMessage]) -> List[Dict[str, str]]:
        """
        LangChain メッセージを OpenAI互換の API 形式に変換する。

        Args:
            messages: LangChain メッセージオブジェクトのリスト

        Returns:
            API 用のメッセージディクショナリのリスト
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
                # その他のメッセージ型は user として扱う
                converted.append({"role": "user", "content": str(msg.content)})
        return converted

    def _build_payload(self, messages: List[BaseMessage], config: ModelConfig) -> Dict:
        """OpenAI互換の chat completions ペイロードを構築する。

        COSCUP デモでは応答速度が最優先のため、Qwen3 系の thinking モードを
        ``reasoning_effort=none`` で無効化する（gemma4 等では無視される）。
        ``keep_alive`` でモデルをメモリ上に保持し、ターン間のアンロードを防ぐ。
        """
        return {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "reasoning_effort": "none",
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "1h"),
        }

    @staticmethod
    def _record_successful_llm_call(
        *, provider: str, model: str, started_at: float
    ) -> dict[str, Any]:
        """明示的な provider/model メタデータを返し、トークントラッキングにも記録する。"""

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        metadata = {
            "provider": provider,
            "model": model,
            "llm_latency_ms": max(0, latency_ms),
        }
        try:
            record_llm_call_metadata(
                provider=provider,
                model=model,
                llm_latency_ms=latency_ms,
            )
        except Exception as e:
            logger.debug("LLM metadata tracking failed (non-critical): %s", e)
        return metadata

    async def generate(
        self,
        messages: List[BaseMessage],
        config: Optional[ModelConfig] = None,
    ) -> str:
        """
        Ollama の chat completions API で応答を生成する。

        Args:
            messages: 会話メッセージのリスト
            config: モデル設定（デフォルトは qa_response）

        Returns:
            生成されたテキスト（LLMResponseText。llm_metadata 付き）

        Raises:
            OllamaError: API エラー、またはレスポンスのパース失敗時
        """
        config = config or MODEL_CONFIGS["qa_response"]
        payload = self._build_payload(messages, config)

        try:
            started_at = time.perf_counter()
            response = await self._http_client.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise OllamaError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise OllamaError(f"Network error: {str(e)}") from e

        try:
            data = response.json()
            if "choices" not in data or len(data["choices"]) == 0:
                raise OllamaError("No choices in response", response=data)
            response_text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as e:
            raise OllamaError(f"Failed to parse Ollama response: {e}") from e

        metadata = self._record_successful_llm_call(
            provider="ollama",
            model=self.model,
            started_at=started_at,
        )
        return LLMResponseText(response_text, metadata)

    async def stream(
        self,
        messages: List[BaseMessage],
        config: Optional[ModelConfig] = None,
    ) -> AsyncGenerator[str, None]:
        """
        SSE（Server-Sent Events）で応答をストリーミングする。

        OpenAI互換のワイヤフォーマットをそのまま処理し、
        ``data: [DONE]`` で終了する。

        Args:
            messages: 会話メッセージのリスト
            config: モデル設定

        Yields:
            生成されたテキストチャンク

        Raises:
            OllamaError: API エラー時
        """
        config = config or MODEL_CONFIGS["qa_response"]
        payload = self._build_payload(messages, config)
        payload["stream"] = True

        try:
            async with self._http_client.stream(
                "POST", "/chat/completions", json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # "data: " プレフィックスを除去
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
            raise OllamaError(
                f"Streaming failed: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise OllamaError(f"Network error: {str(e)}") from e

    def get_langchain_llm(self, config: Optional[ModelConfig] = None) -> ChatOpenAI:
        """
        LangChain / LangGraph 用の ChatOpenAI インスタンスを返す。

        Ollama は OpenAI互換 API のため、base_url を Ollama に向けた
        ChatOpenAI をそのまま利用できる。

        Args:
            config: モデル設定（デフォルトは qa_response）

        Returns:
            ChatOpenAI インスタンス（Ollama に接続済み）

        Example:
            >>> provider = OllamaProvider()
            >>> llm = provider.get_langchain_llm()
            >>> result = await llm.ainvoke(messages)
        """
        config = config or MODEL_CONFIGS["qa_response"]

        return ChatOpenAI(
            model=self.model,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
