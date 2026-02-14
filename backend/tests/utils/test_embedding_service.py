"""Embedding Service Tests"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.embedding_service import generate_embedding


@pytest.mark.asyncio
async def test_generate_embedding_success():
    """OpenRouter API呼出しモック + 1536d確認"""
    fake_embedding = [0.1] * 1536

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        with patch("utils.embedding_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await generate_embedding("test text")

    assert len(result) == 1536
    assert result == fake_embedding


@pytest.mark.asyncio
async def test_generate_embedding_api_error():
    """APIエラー時に空リスト返却"""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        with patch("utils.embedding_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await generate_embedding("test text")

    assert result == []


@pytest.mark.asyncio
async def test_generate_embedding_no_api_key():
    """APIキー未設定時に空リスト返却"""
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
        result = await generate_embedding("test text")

    assert result == []
