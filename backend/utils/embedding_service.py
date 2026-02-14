"""
Embedding生成共通サービス

OpenRouter API経由でtext-embedding-3-small (1536d) のembeddingを生成する。
enhanced_rag.pyとseed_knowledge.pyで共通利用。
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
    """OpenRouter API経由でembeddingを生成

    Args:
        text: エンベディング対象のテキスト

    Returns:
        1536次元のembeddingベクトル。エラー時は空リスト。
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")

    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set, skipping embedding generation")
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENROUTER_EMBEDDING_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBEDDING_MODEL, "input": text},
                timeout=EMBEDDING_TIMEOUT,
            )

            if response.status_code != 200:
                logger.error(
                    f"Embedding API error: status={response.status_code}, body={response.text[:200]}"
                )
                return []

            data = response.json()
            embedding: List[float] = data["data"][0]["embedding"]
            logger.info(f"Generated embedding: {len(embedding)} dimensions")
            return embedding

    except httpx.TimeoutException:
        logger.error("Embedding API request timed out")
        return []
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return []
