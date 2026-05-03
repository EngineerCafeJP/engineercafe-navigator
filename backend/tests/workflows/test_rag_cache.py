"""
RAG Cache in State のユニットテスト

memory_loader_node でのRAGプリフェッチと、各エージェントでのキャッシュ利用をテスト。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


def _mock_runtime():
    """テスト用モック Runtime を生成"""
    rt = MagicMock()
    rt.context = MagicMock()
    rt.context.user_id = "anonymous"
    rt.store = None
    return rt


class TestMemoryLoaderRAGCache:
    """memory_loader_node の RAGキャッシュテスト"""

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_loader_caches_rag_results(self, mock_orchestrator_class):
        """memory_loaderがknowledge_resultsをstateに格納することを確認"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={"recent_messages": [], "context_string": ""}
            )
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # QueryClassifier と EnhancedRAGSearch をモック
            mock_classification = Mock()
            mock_classification.category = "hours"

            mock_rag_result = {
                "success": True,
                "data": {
                    "context": "営業時間は9:00-22:00です",
                    "results": [{"title": "営業時間"}],
                    "totalResults": 1,
                },
            }

            with (
                patch(
                    "backend.utils.query_classifier.QueryClassifier.classify_with_details",
                    new_callable=AsyncMock,
                    return_value=mock_classification,
                ),
                patch(
                    "backend.tools.enhanced_rag.EnhancedRAGSearch.search",
                    new_callable=AsyncMock,
                    return_value=mock_rag_result,
                ),
            ):
                state = {
                    "query": "営業時間は？",
                    "session_id": "test-session",
                    "language": "ja",
                    "context": {},
                }

                result = await workflow._memory_loader_node(state, _mock_runtime())

                assert "context" in result
                assert "knowledge_results" in result["context"]
                kr = result["context"]["knowledge_results"]
                assert kr["success"] is True
                assert kr["category"] == "hours"
                assert kr["context_string"] == "営業時間は9:00-22:00です"
                assert kr["query"] == "営業時間は？"

    @pytest.mark.asyncio
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_rag_prefetch_error_graceful(self, mock_orchestrator_class):
        """RAGプリフェッチエラー時もワークフロー継続"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator_class.return_value = AsyncMock()

        with patch("backend.utils.memory_helper.get_memory_helper") as mock_get_helper:
            mock_helper = AsyncMock()
            mock_helper.get_context = AsyncMock(
                return_value={"recent_messages": [], "context_string": ""}
            )
            mock_helper.store_message = AsyncMock()
            mock_get_helper.return_value = mock_helper

            workflow = MainWorkflow()

            # QueryClassifier が例外を投げる
            with patch(
                "backend.utils.query_classifier.QueryClassifier.classify_with_details",
                new_callable=AsyncMock,
                side_effect=Exception("Classification failed"),
            ):
                state = {
                    "query": "テスト",
                    "session_id": "test-session",
                    "language": "ja",
                    "context": {},
                }

                result = await workflow._memory_loader_node(state, _mock_runtime())

                # エラーでもcontextとknowledge_resultsが返る
                assert "context" in result
                assert "knowledge_results" in result["context"]
                kr = result["context"]["knowledge_results"]
                assert kr["success"] is False
                assert kr["category"] == "general"


class TestAgentCacheUsage:
    """各エージェントのキャッシュ利用テスト"""

    @pytest.mark.asyncio
    async def test_general_agent_uses_cached_results_on_match(self):
        """GeneralKnowledgeAgentがカテゴリ一致時にキャッシュ利用"""
        with (
            patch("backend.tools.enhanced_rag.create_client"),
            patch("backend.llm.openrouter.OpenRouterProvider"),
            patch("backend.agents.general_knowledge_agent.TavilySearchTool"),
        ):
            from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

            agent = GeneralKnowledgeAgent()

            # LLM応答をモック
            agent.provider.generate = AsyncMock(
                return_value="[relaxed]キャッシュから生成した回答です"
            )

            # RAG searchをモック（呼ばれないはず）
            agent.rag_search.search = AsyncMock()

            # Web searchをモック（asyncメソッド）
            agent.web_search.search = AsyncMock(
                return_value={"success": False, "text": "", "results": [], "sources": []}
            )

            state_context = {
                "success": True,
                "category": "general",
                "context_string": "キャッシュされたコンテキスト",
                "results": [{"title": "test"}],
                "query": "テスト",
            }

            result = await agent.answer_general_query(
                query="テスト", language="ja", state_context=state_context
            )

            assert result["answer"] == "[relaxed]キャッシュから生成した回答です"
            # RAG searchは呼ばれない
            agent.rag_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_general_agent_falls_back_on_category_mismatch(self):
        """GeneralKnowledgeAgentがカテゴリ不一致時にフレッシュ検索"""
        with (
            patch("backend.tools.enhanced_rag.create_client"),
            patch("backend.llm.openrouter.OpenRouterProvider"),
            patch("backend.agents.general_knowledge_agent.TavilySearchTool"),
        ):
            from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

            agent = GeneralKnowledgeAgent()
            agent.provider.generate = AsyncMock(return_value="[relaxed]フレッシュ検索結果です")

            # Web searchをモック（asyncメソッド）
            agent.web_search.search = AsyncMock(
                return_value={"success": False, "text": "", "results": [], "sources": []}
            )

            # RAG searchをモック
            agent.rag_search.search = AsyncMock(
                return_value={
                    "success": True,
                    "data": {"context": "フレッシュコンテキスト", "results": []},
                }
            )

            # カテゴリが不一致（hoursなのにgeneralを期待）
            state_context = {
                "success": True,
                "category": "hours",
                "context_string": "営業時間データ",
                "results": [],
                "query": "テスト",
            }

            await agent.answer_general_query(
                query="テスト", language="ja", state_context=state_context
            )

            # RAG searchが呼ばれる
            agent.rag_search.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_business_agent_uses_cached_results_on_match(self):
        """BusinessInfoAgentがカテゴリ一致時にキャッシュ利用"""
        with (
            patch("backend.tools.enhanced_rag.create_client"),
            patch("backend.llm.get_llm_provider"),
        ):
            from backend.agents.business_info_agent import BusinessInfoAgent

            agent = BusinessInfoAgent()

            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value="[relaxed]営業時間は9:00-22:00です")
            agent.llm_provider = mock_provider

            # RAG searchをモック（呼ばれないはず）
            agent.enhanced_rag.search = AsyncMock()

            state_context = {
                "success": True,
                "category": "hours",
                "context_string": "営業時間キャッシュ",
                "results": [],
                "query": "営業時間は？",
            }

            result = await agent.answer_business_query(
                query="営業時間は？",
                request_type="hours",
                language="ja",
                state_context=state_context,
            )

            assert "answer" in result
            # RAG searchは呼ばれない
            agent.enhanced_rag.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_business_agent_falls_back_on_category_mismatch(self):
        """BusinessInfoAgentがカテゴリ不一致時にフレッシュ検索"""
        with (
            patch("backend.tools.enhanced_rag.create_client"),
            patch("backend.llm.get_llm_provider"),
        ):
            from backend.agents.business_info_agent import BusinessInfoAgent

            agent = BusinessInfoAgent()

            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value="[relaxed]相談できます")
            agent.llm_provider = mock_provider

            agent.enhanced_rag.search = AsyncMock(
                return_value={
                    "success": True,
                    "data": {"context": "料金情報", "results": []},
                }
            )

            # カテゴリ不一致: キャッシュはhours、実際はgeneral。
            # Known canonical questions intentionally bypass RAG regardless of cache state,
            # so this uses a non-canonical business query to test fallback mechanics.
            state_context = {
                "success": True,
                "category": "hours",
                "context_string": "営業時間データ",
                "results": [],
                "query": "テスト",
            }

            await agent.answer_business_query(
                query="テスト",
                request_type=None,
                language="ja",
                state_context=state_context,
            )

            # RAG searchが呼ばれる
            agent.enhanced_rag.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_falls_back_on_cache_failure(self):
        """キャッシュfailure時にフレッシュ検索"""
        with (
            patch("backend.tools.enhanced_rag.create_client"),
            patch("backend.llm.get_llm_provider"),
        ):
            from backend.agents.business_info_agent import BusinessInfoAgent

            agent = BusinessInfoAgent()

            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value="[relaxed]フォールバック結果")
            agent.llm_provider = mock_provider

            agent.enhanced_rag.search = AsyncMock(
                return_value={
                    "success": True,
                    "data": {"context": "フレッシュコンテキスト", "results": []},
                }
            )

            # キャッシュが失敗状態
            state_context = {
                "success": False,
                "category": "general",
                "context_string": "",
                "results": [],
                "query": "テスト",
            }

            await agent.answer_business_query(
                query="テスト",
                request_type=None,
                language="ja",
                state_context=state_context,
            )

            # キャッシュが失敗なのでRAG searchが呼ばれる
            agent.enhanced_rag.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_facility_agent_uses_cached_results(self):
        """FacilityAgentがキャッシュ利用"""
        with (
            patch("backend.tools.enhanced_rag.create_client"),
            patch("backend.llm.get_llm_provider"),
        ):
            from backend.agents.facility_agent import FacilityAgent

            agent = FacilityAgent()

            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value="[relaxed]Wi-Fiは無料です")
            agent.llm_provider = mock_provider

            agent.enhanced_rag.search = AsyncMock()

            state_context = {
                "success": True,
                "category": "facility-info",
                "context_string": "Wi-Fi情報キャッシュ",
                "results": [],
                "query": "Wi-Fiは？",
            }

            result = await agent.answer_facility_query(
                query="Wi-Fiは使えますか？",
                request_type="wifi",
                language="ja",
                state_context=state_context,
            )

            assert "answer" in result
            # RAG searchは呼ばれない
            agent.enhanced_rag.search.assert_not_called()
