"""
Embedding生成共通サービス

OpenRouter API経由でtext-embedding-3-small (1536d) のembeddingを生成する。
環境変数でOllamaなどのOpenAI互換エンドポイントへ切り替え可能（COSCUPデモ用）。
enhanced_rag.pyとseed_local_knowledge.pyで共通利用。
"""

import logging
import os
from typing import List

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_TIMEOUT = 30.0


async def generate_embedding(text: str) -> List[float]:
    """embeddingを生成（環境変数で接続先を上書き可能）

    環境変数:
        EMBEDDING_API_URL: OpenAI互換embeddingsエンドポイント（デフォルト: OpenRouter）
        EMBEDDING_MODEL: embeddingモデル名（デフォルト: openai/text-embedding-3-small）
        EMBEDDING_DIMENSIONS: embedding次元数（デフォルト: 1536）
        EMBEDDING_API_KEY: APIキー（設定時は優先。未設定時はOPENROUTER_API_KEYにフォールバック。
            ローカルOllama利用時はダミーキーで可）

    Args:
        text: エンベディング対象のテキスト

    Returns:
        EMBEDDING_DIMENSIONS次元のembeddingベクトル。エラー時は空リスト。
    """
    try:
        api_url = os.getenv("EMBEDDING_API_URL", OPENROUTER_EMBEDDING_URL)
        model = os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)
        dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
        api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")

        if not api_key:
            logger.warning("API key not set, skipping embedding generation")
            return []

        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "input": text},
                timeout=EMBEDDING_TIMEOUT,
            )

            if response.status_code != 200:
                logger.error(
                    "Embedding API error: status=%s, body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return []

            data = response.json()
            embedding: List[float] = data["data"][0]["embedding"]

            # 次元数バリデーション
            if len(embedding) != dimensions:
                logger.error(
                    "Unexpected embedding dimensions: got %d, expected %d",
                    len(embedding),
                    dimensions,
                )
                return []

            logger.info("Generated embedding: %d dimensions", len(embedding))
            return embedding

    except httpx.TimeoutException:
        logger.error("Embedding API request timed out")
        return []
    except Exception as e:
        logger.error("Embedding generation failed: %s", e)
        return []
