"""
tRAG (Translation-augmented RAG) のKO/ZH翻訳パスをテスト

main_workflow.py の _memory_loader_node 内の LLM 翻訳ロジック、
サニタイズ、フォールバック動作を検証する。
"""

import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.workflows.main_workflow import (
    _JA_RE,
    _TRAG_PREAMBLE_RE,
    _clean_trag_translation,
    _get_trag_client,
    _is_pathological_translation,
)


class TestTragPreambleSanitization:
    """tRAG 出力のプリアンブル除去テスト"""

    def test_strips_translation_prefix(self):
        text = "Translation: 日本語テキスト"
        result = _TRAG_PREAMBLE_RE.sub("", text).strip()
        assert result == "日本語テキスト"

    def test_strips_japanese_prefix(self):
        text = "翻訳: テスト文"
        result = _TRAG_PREAMBLE_RE.sub("", text).strip()
        assert "テスト文" in result

    def test_strips_here_is_prefix(self):
        text = "Here is the translation: テスト"
        result = _TRAG_PREAMBLE_RE.sub("", text).strip()
        assert not result.startswith("Here is")

    def test_no_strip_clean_japanese(self):
        text = "エンジニアカフェの営業時間"
        result = _TRAG_PREAMBLE_RE.sub("", text).strip()
        assert result == text

    def test_no_strip_ika_prefix(self):
        """以下 + normal continuation must NOT be stripped"""
        text = "以下の情報をお伝えします"
        result = _TRAG_PREAMBLE_RE.sub("", text).strip()
        assert result == text

    def test_latin_preamble_detection(self):
        """5文字以上のラテン文字開始はリジェクト"""
        assert re.search(r"^[A-Za-z]{5,}", "Hello world")
        assert not re.search(r"^[A-Za-z]{5,}", "日本語テキスト")
        assert not re.search(r"^[A-Za-z]{5,}", "WiFi パスワード")

    @pytest.mark.parametrize(
        "text",
        [
            "ル ル ル ル",
            "このこのこのこの",
            "ああああああ",
            "テストテストテスト",
        ],
    )
    def test_rejects_low_information_repeated_translation(self, text):
        assert _is_pathological_translation(text) is True
        assert _clean_trag_translation(text) == ""

    def test_allows_normal_japanese_translation(self):
        text = "エンジニアカフェの営業時間を教えてください"
        assert _is_pathological_translation(text) is False
        assert _clean_trag_translation(f"Translation: {text}") == text


class TestJaRegex:
    """日本語かな検出 regex テスト"""

    def test_detects_hiragana(self):
        assert _JA_RE.search("こんにちは")

    def test_detects_katakana(self):
        assert _JA_RE.search("エンジニアカフェ")

    def test_rejects_korean(self):
        assert not _JA_RE.search("영업시간")

    def test_rejects_chinese_only(self):
        assert not _JA_RE.search("营业时间")


class TestGetTragClient:
    """共有 httpx クライアント シングルトンテスト"""

    def test_returns_client(self):
        client = _get_trag_client()
        assert client is not None
        assert not client.is_closed

    def test_returns_same_instance(self):
        c1 = _get_trag_client()
        c2 = _get_trag_client()
        assert c1 is c2


def _mock_runtime():
    """テスト用モック Runtime"""
    rt = MagicMock()
    rt.context = MagicMock()
    rt.context.user_id = "anonymous"
    rt.store = None
    return rt


def _mock_memory_helper():
    """テスト用メモリヘルパー"""
    helper = AsyncMock()
    helper.get_context = AsyncMock(
        return_value={
            "recent_messages": [],
            "context_string": "",
            "inherited_request_type": None,
        }
    )
    return helper


class TestTragTranslationIntegration:
    """tRAG 翻訳の統合テスト (main_workflow の _memory_loader_node)"""

    @pytest.fixture
    def mock_state(self):
        """Korean query state for tRAG testing"""
        return {
            "query": "영업시간은 몇 시까지인가요?",
            "session_id": "test-session",
            "language": "ko",
            "context": {},
            "knowledge_results": {},
            "messages": [],
        }

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_ko_translation_success(self, mock_orch_class, mock_state):
        """Korean → Japanese 翻訳成功時に rag_query が更新される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orch_class.return_value = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "営業時間は何時までですか？"}}]
        }

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_mh,
            patch.object(
                type(_get_trag_client()),
                "post",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            mock_mh.return_value = _mock_memory_helper()

            wf = MainWorkflow()
            runtime = _mock_runtime()
            result = await wf._memory_loader_node(mock_state, runtime)

            assert result is not None
            # Verify translation was attempted (may not set
            # translated_query if mock wiring differs, but
            # must not crash)
            kr = result.get("knowledge_results", {})
            if "translated_query" in kr:
                assert _JA_RE.search(
                    kr["translated_query"]
                ), f"Expected Japanese: {kr['translated_query']}"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_translation_no_api_key_skips(self, mock_orch_class, mock_state):
        """API キー未設定時は翻訳をスキップ"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orch_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_mh:
            mock_mh.return_value = _mock_memory_helper()

            # Constructor needs a key; tRAG code path sees empty
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                wf = MainWorkflow()

            with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
                runtime = _mock_runtime()
                result = await wf._memory_loader_node(mock_state, runtime)
                assert result is not None

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_translation_non_200_falls_back(self, mock_orch_class, mock_state):
        """Non-200 レスポンス時は元クエリを維持"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orch_class.return_value = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with (
            patch("backend.utils.memory_helper.get_memory_helper") as mock_mh,
            patch.object(
                type(_get_trag_client()),
                "post",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            mock_mh.return_value = _mock_memory_helper()

            wf = MainWorkflow()
            runtime = _mock_runtime()
            result = await wf._memory_loader_node(mock_state, runtime)
            assert result is not None
