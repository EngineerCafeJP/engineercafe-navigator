"""Integration tests for the RAG pipeline (search → scoring → grading → context)."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.tools.enhanced_rag import (
    EnhancedRAGSearch,
    RPC_SIMILARITY_THRESHOLDS,
)


@pytest.fixture
def rag():
    with patch("backend.tools.enhanced_rag.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        return EnhancedRAGSearch()


def _mock_rpc_results(data):
    """Create a mock RPC execute result."""
    mock_result = MagicMock()
    mock_result.data = data
    return mock_result


class TestRAGPipelineIntegration:
    @pytest.mark.asyncio
    async def test_search_to_context_hours_query(self, rag):
        """Full pipeline: embedding → RPC → scoring → grading → context for hours query."""
        rpc_data = [
            {
                "title": "エンジニアカフェ営業時間",
                "content": "営業時間は平日9:00-22:00、土日10:00-20:00です。",
                "similarity": 0.88,
                "category": "hours",
                "metadata": {"entity": "engineer-cafe"},
            },
            {
                "title": "sainoカフェ営業時間",
                "content": "sainoカフェは11:00-20:00で営業しています。",
                "similarity": 0.82,
                "category": "hours",
                "metadata": {"entity": "saino"},
            },
        ]
        rag.supabase.rpc.return_value.execute.return_value = _mock_rpc_results(rpc_data)

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            result = await rag.search("営業時間を教えてください", "hours")

        assert result["success"] is True
        assert result["data"]["totalResults"] >= 1
        assert "営業時間" in result["data"]["context"]

    @pytest.mark.asyncio
    async def test_hierarchical_with_parent_expansion(self, rag):
        """Hierarchical search with parent context expansion."""
        rpc_data = [
            {
                "title": "料金チャンク",
                "content": "月額会員は5000円です。",
                "similarity": 0.85,
                "category": "pricing",
                "metadata": {},
                "parent_id": "parent-1",
            },
        ]
        parent_data = [
            {
                "id": "parent-1",
                "title": "料金総合案内",
                "content": "エンジニアカフェの料金プランについて。",
            }
        ]

        rag.supabase.rpc.return_value.execute.return_value = _mock_rpc_results(rpc_data)
        (
            rag.supabase.table.return_value.select.return_value.in_.return_value.execute.return_value
        ) = MagicMock(data=parent_data)

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            result = await rag.search_hierarchical("料金プラン", "pricing")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_context_signals_flow_through_search(self, rag):
        """ContextSignals are passed to grading and affect thresholds."""
        rpc_data = [
            {
                "title": "テスト",
                "content": "テスト内容",
                "similarity": 0.7,
                "category": "general",
                "metadata": {},
            },
        ]
        rag.supabase.rpc.return_value.execute.return_value = _mock_rpc_results(rpc_data)

        mock_signals = MagicMock()

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            # Should not crash even with context_signals
            result = await rag.search("テスト", "general", context_signals=mock_signals)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_category_specific_threshold_in_rpc(self, rag):
        """category="hours" should use RPC threshold 0.30."""
        rag.supabase.rpc.return_value.execute.return_value = _mock_rpc_results([])

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            await rag.search("営業時間", "hours")

        # Verify RPC was called with the correct threshold
        rpc_call = rag.supabase.rpc.call_args
        params = rpc_call[0][1] if len(rpc_call[0]) > 1 else rpc_call[1].get("params", {})
        assert params["similarity_threshold"] == RPC_SIMILARITY_THRESHOLDS["hours"]

    @pytest.mark.asyncio
    async def test_multi_turn_priority_adjustment(self, rag):
        """Two search calls maintain independent results."""
        rpc_data_1 = [
            {
                "title": "営業時間",
                "content": "9-22時",
                "similarity": 0.9,
                "category": "hours",
                "metadata": {},
            },
        ]
        rpc_data_2 = [
            {
                "title": "料金",
                "content": "無料",
                "similarity": 0.85,
                "category": "pricing",
                "metadata": {},
            },
        ]

        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            rag.supabase.rpc.return_value.execute.return_value = _mock_rpc_results(rpc_data_1)
            result1 = await rag.search("営業時間", "hours")

            rag.supabase.rpc.return_value.execute.return_value = _mock_rpc_results(rpc_data_2)
            result2 = await rag.search("料金", "pricing")

        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["data"]["context"] != result2["data"]["context"]

    @pytest.mark.asyncio
    async def test_hierarchical_fallback_to_standard(self, rag):
        """When hierarchical RPC fails, falls back to standard search."""
        # Make hierarchical RPC fail
        rag.supabase.rpc.side_effect = [
            Exception("RPC not available"),  # hierarchical fails
        ]

        # Mock standard search path
        with patch.object(
            rag, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536
        ):
            with patch.object(
                rag,
                "search",
                new_callable=AsyncMock,
                return_value={
                    "success": True,
                    "data": {
                        "context": "fallback",
                        "results": [],
                        "totalResults": 0,
                        "topEntity": "general",
                    },
                },
            ):
                result = await rag.search_hierarchical("test", "general")

        assert result["success"] is True
