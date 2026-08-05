"""Embedding Service テスト

utils/embedding_service.py の全パスを網羅するユニットテスト。
httpx.AsyncClient をモックし、外部APIへの実際の通信は行わない。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.utils.embedding_service import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT,
    OPENROUTER_EMBEDDING_URL,
    generate_embedding,
)


# ---------------------------------------------------------------------------
# ヘルパー: httpx.AsyncClient のモックを構築
# ---------------------------------------------------------------------------
def _build_mock_client(mock_response: MagicMock) -> AsyncMock:
    """async with httpx.AsyncClient() as client: のコンテキストマネージャ用モックを構築する。"""
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ===========================================================================
# 定数値の検証
# ===========================================================================
class TestConstants:
    """モジュール定数の値が期待通りであることを検証する。"""

    def test_embedding_dimensions(self):
        """EMBEDDING_DIMENSIONS が 1536 であること。"""
        assert EMBEDDING_DIMENSIONS == 1536

    def test_embedding_model(self):
        """EMBEDDING_MODEL が openai/text-embedding-3-small であること。"""
        assert EMBEDDING_MODEL == "openai/text-embedding-3-small"

    def test_openrouter_embedding_url(self):
        """OPENROUTER_EMBEDDING_URL が OpenRouter の embeddings エンドポイントであること。"""
        assert OPENROUTER_EMBEDDING_URL == "https://openrouter.ai/api/v1/embeddings"

    def test_embedding_timeout(self):
        """EMBEDDING_TIMEOUT が 30.0 秒であること。"""
        assert EMBEDDING_TIMEOUT == 30.0


# ===========================================================================
# generate_embedding 関数のテスト
# ===========================================================================
class TestGenerateEmbedding:
    """generate_embedding() の全分岐パスを検証する。"""

    @pytest.mark.asyncio
    async def test_generate_embedding_success(self, monkeypatch):
        """正常系: 200レスポンスで 1536 次元のembeddingを返すこと。"""
        fake_embedding = [0.01 * i for i in range(EMBEDDING_DIMENSIONS)]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-abc123")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            result = await generate_embedding("Hello, world!")

        assert result == fake_embedding
        assert len(result) == EMBEDDING_DIMENSIONS

        # POST が正しいURL・ヘッダー・ボディで呼ばれたことを検証
        mock_client.post.assert_called_once_with(
            OPENROUTER_EMBEDDING_URL,
            headers={
                "Authorization": "Bearer test-key-abc123",
                "Content-Type": "application/json",
            },
            json={"model": EMBEDDING_MODEL, "input": "Hello, world!"},
            timeout=EMBEDDING_TIMEOUT,
        )

    @pytest.mark.asyncio
    async def test_generate_embedding_no_api_key(self, monkeypatch):
        """OPENROUTER_API_KEY が空文字の場合、空リストを返すこと。"""
        monkeypatch.setenv("OPENROUTER_API_KEY", "")

        result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_no_api_key_unset(self, monkeypatch):
        """OPENROUTER_API_KEY が環境変数に存在しない場合、空リストを返すこと。"""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_api_error_500(self, monkeypatch):
        """APIが 500 を返した場合、空リストを返すこと。"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _build_mock_client(mock_response)

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_api_error_401(self, monkeypatch):
        """APIが 401 (Unauthorized) を返した場合、空リストを返すこと。"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        monkeypatch.setenv("OPENROUTER_API_KEY", "invalid-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _build_mock_client(mock_response)

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_api_error_429(self, monkeypatch):
        """APIが 429 (Rate Limited) を返した場合、空リストを返すこと。"""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _build_mock_client(mock_response)

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_wrong_dimensions(self, monkeypatch):
        """embedding の次元数が 1536 でない場合、空リストを返すこと。"""
        wrong_embedding = [0.5] * 768  # 768次元 (text-embedding-3-small ではない)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": wrong_embedding}]}

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _build_mock_client(mock_response)

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_timeout(self, monkeypatch):
        """httpx.TimeoutException 発生時、空リストを返すこと。"""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_general_exception(self, monkeypatch):
        """予期しない例外発生時、空リストを返すこと。"""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = RuntimeError("Unexpected connection error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_text(self, monkeypatch):
        """空文字列でもAPIが正常応答すればembeddingを返すこと。"""
        fake_embedding = [0.0] * EMBEDDING_DIMENSIONS

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _build_mock_client(mock_response)

            result = await generate_embedding("")

        assert result == fake_embedding
        assert len(result) == EMBEDDING_DIMENSIONS

    @pytest.mark.asyncio
    async def test_generate_embedding_long_error_text_truncated(self, monkeypatch):
        """エラーレスポンスの text が長い場合でも
        クラッシュしないこと。"""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "x" * 500  # 200文字以上のエラー本文

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _build_mock_client(mock_response)

            result = await generate_embedding("test text")

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_returns_new_list_on_each_failure(self, monkeypatch):
        """複数回の失敗呼び出しで毎回新しい空リストを返すこと。"""
        monkeypatch.setenv("OPENROUTER_API_KEY", "")

        result1 = await generate_embedding("a")
        result2 = await generate_embedding("b")

        assert result1 == []
        assert result2 == []
        assert result1 is not result2  # 異なるリストオブジェクトであること


# ===========================================================================
# 環境変数オーバーライドのテスト（COSCUPデモ: Ollama等のOpenAI互換エンドポイント）
# ===========================================================================
class TestEnvOverrides:
    """EMBEDDING_API_URL / EMBEDDING_MODEL / EMBEDDING_DIMENSIONS /
    EMBEDDING_API_KEY の上書き動作を検証する。"""

    @pytest.mark.asyncio
    async def test_api_url_override(self, monkeypatch):
        """EMBEDDING_API_URL 指定時にそのURLへPOSTされること"""
        fake_embedding = [0.01 * i for i in range(EMBEDDING_DIMENSIONS)]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("EMBEDDING_API_URL", "http://localhost:11434/v1/embeddings")
        monkeypatch.setenv("EMBEDDING_API_KEY", "ollama-dummy")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            result = await generate_embedding("test")

        assert result == fake_embedding
        mock_client.post.assert_called_once_with(
            "http://localhost:11434/v1/embeddings",
            headers={
                "Authorization": "Bearer ollama-dummy",
                "Content-Type": "application/json",
            },
            json={"model": EMBEDDING_MODEL, "input": "test"},
            timeout=EMBEDDING_TIMEOUT,
        )

    @pytest.mark.asyncio
    async def test_model_override(self, monkeypatch):
        """EMBEDDING_MODEL 指定時にそのモデル名でリクエストされること"""
        fake_embedding = [0.0] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
        monkeypatch.setenv("EMBEDDING_API_KEY", "ollama-dummy")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            await generate_embedding("test")

        assert mock_client.post.call_args.kwargs["json"]["model"] == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_dimensions_override_valid(self, monkeypatch):
        """EMBEDDING_DIMENSIONS 指定時はその次元数で検証されること"""
        fake_embedding = [0.5] * 8
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "8")
        monkeypatch.setenv("EMBEDDING_API_KEY", "ollama-dummy")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            result = await generate_embedding("test")

        assert result == fake_embedding

    @pytest.mark.asyncio
    async def test_dimensions_override_mismatch(self, monkeypatch):
        """EMBEDDING_DIMENSIONS 指定時は既定次元のレスポンスが拒否されること"""
        wrong_embedding = [0.5] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": wrong_embedding}]}

        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "8")
        monkeypatch.setenv("EMBEDDING_API_KEY", "ollama-dummy")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            result = await generate_embedding("test")

        assert result == []

    @pytest.mark.asyncio
    async def test_api_key_takes_precedence(self, monkeypatch):
        """EMBEDDING_API_KEY が設定されている場合は優先されること"""
        fake_embedding = [0.0] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("EMBEDDING_API_KEY", "embed-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            await generate_embedding("test")

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer embed-key"

    @pytest.mark.asyncio
    async def test_api_key_falls_back_to_openrouter(self, monkeypatch):
        """EMBEDDING_API_KEY 未設定時は OPENROUTER_API_KEY にフォールバックすること"""
        fake_embedding = [0.0] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            await generate_embedding("test")

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer or-key"

    @pytest.mark.asyncio
    async def test_api_key_empty_string_falls_back_to_openrouter(self, monkeypatch):
        """EMBEDDING_API_KEY が空文字でも OPENROUTER_API_KEY にフォールバックすること"""
        fake_embedding = [0.0] * EMBEDDING_DIMENSIONS
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        monkeypatch.setenv("EMBEDDING_API_KEY", "")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

        with patch("backend.utils.embedding_service.httpx.AsyncClient") as mock_cls:
            mock_client = _build_mock_client(mock_response)
            mock_cls.return_value = mock_client

            await generate_embedding("test")

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer or-key"
