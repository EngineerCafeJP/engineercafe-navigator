"""Enhanced RAG + Context Priority 統合テスト"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.utils.context_priority import ContextSignals

# =============================================================================
# _grade_result_relevance with context_signals
# =============================================================================


class TestGradeResultRelevanceWithContext:
    """_grade_result_relevance の context_signals パラメータテスト"""

    @pytest.fixture()
    def rag_instance(self):
        with patch("backend.tools.enhanced_rag.create_client") as mock_client:
            mock_client.return_value = MagicMock()
            from backend.tools.enhanced_rag import EnhancedRAGSearch

            return EnhancedRAGSearch()

    @pytest.fixture()
    def sample_results(self):
        return [
            {
                "title": "営業時間",
                "content": "エンジニアカフェの営業時間は9:00-22:00",
                "priority_score": 0.80,
                "similarity": 0.75,
            },
            {
                "title": "料金情報",
                "content": "利用料金は無料です",
                "priority_score": 0.60,
                "similarity": 0.55,
            },
            {
                "title": "関連なし",
                "content": "天気予報",
                "priority_score": 0.30,
                "similarity": 0.25,
            },
        ]

    def test_backward_compatible_none_signals(self, rag_instance, sample_results):
        """context_signals=None で既存の静的閾値が使用されること"""
        result = rag_instance._grade_result_relevance(
            scored_results=sample_results,
            query="営業時間は？",
            category="hours",
            context_signals=None,
        )
        # 少なくともHIGHスコア結果は含まれる
        assert len(result) >= 1
        assert result[0]["title"] == "営業時間"

    def test_with_context_signals_adjusts_thresholds(self, rag_instance, sample_results):
        """context_signalsが閾値を調整すること"""
        signals = ContextSignals(
            previous_categories=("hours",),
            rag_cache_top_score=0.85,
            conversation_depth=5,
        )
        result = rag_instance._grade_result_relevance(
            scored_results=sample_results,
            query="営業時間は何時まで",
            category="hours",
            context_signals=signals,
        )
        # 調整後もフィルタリングが正しく動作すること
        assert all(isinstance(r, dict) for r in result)
        # LOWスコア(0.30)の結果は除外されているはず
        titles = [r["title"] for r in result]
        assert "関連なし" not in titles

    def test_context_signals_exception_falls_back(self, rag_instance, sample_results):
        """context_signals処理が失敗した場合、静的閾値にフォールバック"""
        # ContextPriorityEngine が例外を投げるモック
        with patch(
            "backend.utils.context_priority.ContextPriorityEngine.compute_adjusted_thresholds",
            side_effect=RuntimeError("test error"),
        ):
            signals = ContextSignals()
            result = rag_instance._grade_result_relevance(
                scored_results=sample_results,
                query="テスト",
                category="general",
                context_signals=signals,
            )
            # フォールバックで結果が返ること
            assert isinstance(result, list)


# =============================================================================
# search() and search_hierarchical() accept context_signals
# =============================================================================


class TestSearchMethodsAcceptContextSignals:
    """search/search_hierarchical の context_signals パラメータ受け入れテスト"""

    @pytest.fixture()
    def rag_instance(self):
        with patch("backend.tools.enhanced_rag.create_client") as mock_client:
            mock_client.return_value = MagicMock()
            from backend.tools.enhanced_rag import EnhancedRAGSearch

            instance = EnhancedRAGSearch()
            return instance

    @pytest.mark.asyncio()
    async def test_search_accepts_context_signals(self, rag_instance):
        """search() が context_signals パラメータを受け付けること"""
        with (
            patch.object(
                rag_instance,
                "_generate_embedding",
                new_callable=AsyncMock,
                return_value=[0.1] * 1536,
            ),
            patch.object(rag_instance, "supabase") as mock_sb,
        ):
            mock_rpc = MagicMock()
            mock_rpc.execute.return_value = MagicMock(data=[])
            mock_sb.rpc.return_value = mock_rpc

            signals = ContextSignals(conversation_depth=3)
            result = await rag_instance.search(
                query="test",
                category="general",
                context_signals=signals,
            )
            assert result["success"] is True

    @pytest.mark.asyncio()
    async def test_search_hierarchical_accepts_context_signals(self, rag_instance):
        """search_hierarchical() が context_signals パラメータを受け付けること"""
        with (
            patch.object(
                rag_instance,
                "_generate_embedding",
                new_callable=AsyncMock,
                return_value=[0.1] * 1536,
            ),
            patch.object(rag_instance, "supabase") as mock_sb,
        ):
            mock_rpc = MagicMock()
            mock_rpc.execute.return_value = MagicMock(data=[])
            mock_sb.rpc.return_value = mock_rpc

            signals = ContextSignals(conversation_depth=3)
            result = await rag_instance.search_hierarchical(
                query="test",
                category="general",
                context_signals=signals,
            )
            assert result["success"] is True
