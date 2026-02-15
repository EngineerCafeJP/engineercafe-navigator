"""
EnhancedRAGSearch のユニットテスト
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock

from backend.tools.enhanced_rag import EnhancedRAGSearch


class TestEnhancedRAGSearch:
    """EnhancedRAGSearch のテストクラス"""

    @pytest.mark.asyncio
    @patch("backend.tools.enhanced_rag.create_client")
    async def test_generate_embedding_uses_openrouter(self, mock_create_client):
        """_generate_embeddingがOpenRouter APIエンドポイントを使用することを確認"""
        mock_create_client.return_value = Mock()

        rag = EnhancedRAGSearch()

        # httpxのモック
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"embedding": [0.1] * 1536}]}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            embedding = await rag._generate_embedding("テストクエリ")

            # OpenRouterエンドポイントが呼ばれることを確認
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args

            # URL確認
            assert call_args[0][0] == "https://openrouter.ai/api/v1/embeddings"

            # モデル確認
            assert call_args[1]["json"]["model"] == "openai/text-embedding-3-small"

            # 結果確認
            assert len(embedding) == 1536


class TestRAGQualityGrading:
    """RAG結果品質グレーディングのテスト"""

    def setup_method(self):
        """テスト前の初期化"""
        with patch("backend.tools.enhanced_rag.create_client") as mock_create:
            mock_create.return_value = Mock()
            self.rag = EnhancedRAGSearch()

    def test_high_score_results_kept(self):
        """priority_score >= 0.8の結果は常に保持されることを確認"""
        scored_results = [
            {
                "title": "料金情報",
                "content": "無料です",
                "priority_score": 0.9,
                "entity": "engineer-cafe",
            },
            {
                "title": "営業時間",
                "content": "9-22時",
                "priority_score": 0.85,
                "entity": "engineer-cafe",
            },
        ]

        graded = self.rag._grade_result_relevance(scored_results, "料金はいくら")

        assert len(graded) == 2
        assert all(r["grade"] == "HIGH" for r in graded)

    def test_low_score_results_filtered(self):
        """priority_score < 0.6の結果は除外されることを確認"""
        scored_results = [
            {
                "title": "高スコア",
                "content": "料金は無料",
                "priority_score": 0.9,
                "entity": "engineer-cafe",
            },
            {
                "title": "低スコア",
                "content": "関係ない情報",
                "priority_score": 0.4,
                "entity": "general",
            },
            {
                "title": "もう一つ低い",
                "content": "全く関係ない",
                "priority_score": 0.3,
                "entity": "general",
            },
        ]

        graded = self.rag._grade_result_relevance(scored_results, "料金について")

        assert len(graded) == 1
        assert graded[0]["title"] == "高スコア"
        assert graded[0]["grade"] == "HIGH"

    def test_empty_input_returns_empty(self):
        """空の入力に対して空リストが返ることを確認"""
        graded = self.rag._grade_result_relevance([], "テスト")
        assert graded == []

    def test_category_specific_thresholds_hours(self):
        """hours カテゴリでは閾値が緩和されることを確認"""
        scored_results = [
            {
                "title": "営業時間情報",
                "content": "営業時間は9時から22時です",
                "priority_score": 0.76,  # Default HIGH(0.8)未満, hours HIGH(0.75)以上
                "entity": "engineer-cafe",
            },
        ]

        # hours カテゴリではHIGHになる
        graded_hours = self.rag._grade_result_relevance(
            scored_results, "営業時間はいつですか", "hours"
        )

        # hours カテゴリでは0.76がHIGH(>=0.75)
        assert len(graded_hours) == 1
        assert graded_hours[0]["grade"] == "HIGH"

    def test_short_query_relaxed_thresholds(self):
        """短いクエリ(10文字未満)で閾値が緩和されることを確認"""
        scored_results = [
            {
                "title": "料金表",
                "content": "利用料金は無料です",
                "priority_score": 0.76,  # Default HIGH(0.8)未満
                "entity": "engineer-cafe",
            },
        ]

        # 短いクエリ "料金は?" (4文字) → 閾値 -0.05 → HIGH threshold = 0.75
        graded = self.rag._grade_result_relevance(scored_results, "料金は?")

        assert len(graded) == 1
        assert graded[0]["grade"] == "HIGH"

    def test_medium_with_term_match_category(self):
        """MEDIUM結果がカテゴリ別term_match閾値で判定されることを確認"""
        scored_results = [
            {
                "title": "場所案内",
                "content": "天神駅から徒歩5分の場所にあります",
                "priority_score": 0.55,  # Default MEDIUM(0.6)未満, location MEDIUM(0.50)以上
                "entity": "engineer-cafe",
            },
        ]

        # location カテゴリでは medium=0.50 なので MEDIUM 判定
        graded = self.rag._grade_result_relevance(scored_results, "場所はどこ", "location")

        # Content contains "場所" which matches query term
        assert len(graded) == 1
        assert graded[0]["grade"] == "MEDIUM"
