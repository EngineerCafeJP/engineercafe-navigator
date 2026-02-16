"""Enhanced RAG search end-to-end tests."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.tools.enhanced_rag import EnhancedRAGSearch


@pytest.fixture
def rag():
    with patch("backend.tools.enhanced_rag.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        return EnhancedRAGSearch()


class TestSearchE2E:
    @pytest.mark.asyncio
    async def test_search_success_full_pipeline(self, rag):
        """Full pipeline: embedding → RPC → scoring → grading → context"""
        fake_embedding = [0.1] * 1536
        rpc_data = [
            {
                "title": "営業時間",
                "content": "9時から22時",
                "similarity": 0.85,
                "category": "hours",
                "metadata": {"entity": "engineer-cafe"},
            },
        ]

        rag.supabase.rpc.return_value.execute.return_value = MagicMock(data=rpc_data)

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=fake_embedding
        ):
            result = await rag.search("営業時間はいつ", "hours")

        assert result["success"] is True
        assert result["data"]["totalResults"] >= 1
        assert result["data"]["context"] != ""

    @pytest.mark.asyncio
    async def test_search_empty_results(self, rag):
        """Empty RPC results → empty context"""
        rag.supabase.rpc.return_value.execute.return_value = MagicMock(data=[])

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            result = await rag.search("何かのクエリ", "general")

        assert result["success"] is True
        assert result["data"]["context"] == ""
        assert result["data"]["totalResults"] == 0

    @pytest.mark.asyncio
    async def test_search_with_advice(self, rag):
        """include_advice=True adds advice to context"""
        rpc_data = [
            {
                "title": "料金",
                "content": "無料です",
                "similarity": 0.9,
                "category": "pricing",
                "metadata": {},
            }
        ]
        rag.supabase.rpc.return_value.execute.return_value = MagicMock(data=rpc_data)

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            result = await rag.search("料金は", "pricing", include_advice=True)

        assert result["success"] is True
        # pricing has advice template
        assert "💡" in result["data"]["context"]

    @pytest.mark.asyncio
    async def test_search_exception_returns_error(self, rag):
        """Embedding failure → success=False"""
        with patch.object(
            rag,
            "_generate_embedding",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await rag.search("test", "general")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_category_threshold_applied(self, rag):
        """Category-specific threshold is passed to RPC"""
        rag.supabase.rpc.return_value.execute.return_value = MagicMock(data=[])

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            await rag.search("営業時間", "hours")

        # Verify the RPC was called with hours threshold (0.30)
        call_args = rag.supabase.rpc.call_args
        # RPC is called as: supabase.rpc("name", params_dict)
        # So call_args[0] is the positional args tuple and call_args[1] is kwargs
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["similarity_threshold"] == 0.30

    @pytest.mark.asyncio
    async def test_cjk_sliding_window_matching(self, rag):
        """Japanese 2-char bigram matching works in grading"""
        scored_results = [
            {
                "title": "営業時間",
                "content": "営業時間は9時から22時",
                "priority_score": 0.65,
                "entity": "engineer-cafe",
            },
        ]
        graded = rag._grade_result_relevance(scored_results, "営業時間はいつ", "hours")
        # Should pass MEDIUM grade because CJK bigrams match
        assert len(graded) >= 1
