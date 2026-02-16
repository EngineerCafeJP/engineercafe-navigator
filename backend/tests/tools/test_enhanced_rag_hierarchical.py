"""
EnhancedRAGSearch Hierarchical機能のユニットテスト
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock

from backend.tools.enhanced_rag import EnhancedRAGSearch


class TestSearchHierarchical:
    """search_hierarchical メソッドのテスト"""

    def setup_method(self):
        """テスト前の初期化"""
        with patch("backend.tools.enhanced_rag.create_client") as mock_create:
            mock_create.return_value = Mock()
            self.rag = EnhancedRAGSearch()

    @pytest.mark.asyncio
    async def test_search_hierarchical_success(self):
        """RPC成功時の正常フロー"""
        # Embedding生成をモック
        self.rag._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        # RPC結果をモック
        mock_rpc_response = Mock()
        mock_rpc_response.data = [
            {
                "id": "chunk-1",
                "title": "営業時間チャンク",
                "content": "平日は9:00-22:00です",
                "similarity": 0.85,
                "category": "hours",
                "parent_id": "parent-1",
                "metadata": {},
            },
            {
                "id": "chunk-2",
                "title": "料金チャンク",
                "content": "利用料金は無料です",
                "similarity": 0.80,
                "category": "pricing",
                "parent_id": "parent-1",
                "metadata": {},
            },
        ]

        mock_rpc = Mock()
        mock_rpc.execute = Mock(return_value=mock_rpc_response)
        self.rag.supabase.rpc = Mock(return_value=mock_rpc)

        # 親ドキュメントSELECTをモック
        mock_table_response = Mock()
        mock_table_response.data = [
            {
                "id": "parent-1",
                "title": "エンジニアカフェ基本情報",
                "content": "エンジニアカフェは福岡市の施設です",
            }
        ]
        mock_select = Mock()
        mock_select.in_ = Mock(return_value=Mock(execute=Mock(return_value=mock_table_response)))
        mock_table = Mock()
        mock_table.select = Mock(return_value=mock_select)
        self.rag.supabase.table = Mock(return_value=mock_table)

        result = await self.rag.search_hierarchical(
            query="営業時間を教えて",
            category="hours",
            language="ja",
            max_results=5,
        )

        assert result["success"] is True
        assert "data" in result
        assert result["data"]["totalResults"] > 0
        # RPC呼び出し確認
        self.rag.supabase.rpc.assert_called_once_with(
            "search_knowledge_base_hierarchical",
            {
                "query_embedding": [0.1] * 1536,
                "similarity_threshold": 0.35,
                "match_count": 10,
                "filter_chunk_level": "chunk",
            },
        )

    @pytest.mark.asyncio
    async def test_search_hierarchical_fallback_on_rpc_error(self):
        """RPC失敗時にsearch()にフォールバック"""
        self.rag._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        # RPCがエラーを投げる
        self.rag.supabase.rpc = Mock(side_effect=Exception("RPC not found"))

        # search() をモック（フォールバック先）
        mock_search_result = {
            "success": True,
            "data": {
                "context": "フォールバック結果",
                "results": [{"title": "test"}],
                "totalResults": 1,
                "topEntity": "general",
            },
        }
        self.rag.search = AsyncMock(return_value=mock_search_result)

        result = await self.rag.search_hierarchical(query="テスト", category="general")

        assert result["success"] is True
        assert result["data"]["context"] == "フォールバック結果"
        self.rag.search.assert_called_once_with(
            query="テスト",
            category="general",
            language="ja",
            include_advice=True,
            max_results=10,
            context_signals=None,
        )

    @pytest.mark.asyncio
    async def test_search_hierarchical_empty_results(self):
        """RPC成功だが結果が空の場合"""
        self.rag._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_rpc_response = Mock()
        mock_rpc_response.data = []
        mock_rpc = Mock()
        mock_rpc.execute = Mock(return_value=mock_rpc_response)
        self.rag.supabase.rpc = Mock(return_value=mock_rpc)

        result = await self.rag.search_hierarchical(query="テスト", category="general")

        assert result["success"] is True
        assert result["data"]["results"] == []
        assert result["data"]["totalResults"] == 0


class TestExpandParentContext:
    """_expand_parent_context メソッドのテスト"""

    def setup_method(self):
        with patch("backend.tools.enhanced_rag.create_client") as mock_create:
            mock_create.return_value = Mock()
            self.rag = EnhancedRAGSearch()

    def test_expand_parent_context_with_parents(self):
        """親チャンク展開の正常動作"""
        chunk_results = [
            {
                "id": "c1",
                "content": "チャンク1の内容",
                "parent_id": "p1",
                "priority_score": 0.9,
            },
            {
                "id": "c2",
                "content": "チャンク2の内容",
                "parent_id": "p2",
                "priority_score": 0.8,
            },
        ]

        # 親ドキュメントSELECTをモック
        mock_table_response = Mock()
        mock_table_response.data = [
            {"id": "p1", "title": "親タイトル1", "content": "親コンテンツ1"},
            {"id": "p2", "title": "親タイトル2", "content": "親コンテンツ2"},
        ]
        mock_select = Mock()
        mock_select.in_ = Mock(return_value=Mock(execute=Mock(return_value=mock_table_response)))
        mock_table = Mock()
        mock_table.select = Mock(return_value=mock_select)
        self.rag.supabase.table = Mock(return_value=mock_table)

        result = self.rag._expand_parent_context(chunk_results)

        assert len(result) == 2
        assert result[0]["parent_title"] == "親タイトル1"
        assert result[0]["parent_content"] == "親コンテンツ1"
        assert result[1]["parent_title"] == "親タイトル2"
        assert result[1]["parent_content"] == "親コンテンツ2"

    def test_expand_parent_context_no_parent_ids(self):
        """parent_idなしの場合はそのまま返す"""
        chunk_results = [
            {"id": "c1", "content": "チャンク内容", "priority_score": 0.9},
            {"id": "c2", "content": "別のチャンク", "priority_score": 0.8},
        ]

        result = self.rag._expand_parent_context(chunk_results)

        assert result == chunk_results
        # table()は呼ばれない
        (
            self.rag.supabase.table.assert_not_called()
            if hasattr(self.rag.supabase.table, "assert_not_called")
            else None
        )

    def test_expand_parent_context_empty_input(self):
        """空リスト入力"""
        result = self.rag._expand_parent_context([])
        assert result == []

    def test_expand_parent_context_db_error(self):
        """DBエラー時のgraceful fallback"""
        chunk_results = [
            {
                "id": "c1",
                "content": "チャンク内容",
                "parent_id": "p1",
                "priority_score": 0.9,
            },
        ]

        # DB呼び出しがエラーを投げる
        mock_table = Mock()
        mock_select = Mock()
        mock_select.in_ = Mock(side_effect=Exception("DB connection error"))
        mock_table.select = Mock(return_value=mock_select)
        self.rag.supabase.table = Mock(return_value=mock_table)

        result = self.rag._expand_parent_context(chunk_results)

        # エラー時は元のchunk_resultsがそのまま返る
        assert result == chunk_results

    def test_expand_parent_context_partial_parents(self):
        """一部のチャンクだけparent_idがある場合"""
        chunk_results = [
            {
                "id": "c1",
                "content": "親ありチャンク",
                "parent_id": "p1",
                "priority_score": 0.9,
            },
            {
                "id": "c2",
                "content": "親なしチャンク",
                "priority_score": 0.8,
            },
        ]

        mock_table_response = Mock()
        mock_table_response.data = [
            {"id": "p1", "title": "親タイトル", "content": "親コンテンツ"},
        ]
        mock_select = Mock()
        mock_select.in_ = Mock(return_value=Mock(execute=Mock(return_value=mock_table_response)))
        mock_table = Mock()
        mock_table.select = Mock(return_value=mock_select)
        self.rag.supabase.table = Mock(return_value=mock_table)

        result = self.rag._expand_parent_context(chunk_results)

        assert len(result) == 2
        assert result[0].get("parent_title") == "親タイトル"
        assert "parent_title" not in result[1]


class TestBuildHierarchicalContext:
    """_build_hierarchical_context メソッドのテスト"""

    def setup_method(self):
        with patch("backend.tools.enhanced_rag.create_client") as mock_create:
            mock_create.return_value = Mock()
            self.rag = EnhancedRAGSearch()

    def test_build_hierarchical_context_with_parents(self):
        """親グループ化コンテキスト構築"""
        results = [
            {
                "content": "チャンク1内容",
                "parent_id": "p1",
                "parent_title": "エンジニアカフェ概要",
            },
            {
                "content": "チャンク2内容",
                "parent_id": "p1",
                "parent_title": "エンジニアカフェ概要",
            },
            {
                "content": "別の親のチャンク",
                "parent_id": "p2",
                "parent_title": "料金情報",
            },
        ]

        context = self.rag._build_hierarchical_context(results)

        assert "\u3010エンジニアカフェ概要\u3011" in context
        assert "チャンク1内容" in context
        assert "チャンク2内容" in context
        assert "\u3010料金情報\u3011" in context
        assert "別の親のチャンク" in context

    def test_build_hierarchical_context_no_parents(self):
        """親なしの通常コンテキスト"""
        results = [
            {"content": "通常コンテンツ1"},
            {"content": "通常コンテンツ2"},
        ]

        context = self.rag._build_hierarchical_context(results)

        assert "通常コンテンツ1" in context
        assert "通常コンテンツ2" in context
        # 【】のグループヘッダーがない
        assert "\u3010" not in context

    def test_build_hierarchical_context_empty(self):
        """空リスト"""
        context = self.rag._build_hierarchical_context([])
        assert context == ""

    def test_build_hierarchical_context_mixed(self):
        """親ありと親なしの混在"""
        results = [
            {
                "content": "親ありチャンク",
                "parent_id": "p1",
                "parent_title": "基本情報",
            },
            {
                "content": "親なしチャンク",
            },
        ]

        context = self.rag._build_hierarchical_context(results)

        assert "\u3010基本情報\u3011" in context
        assert "親ありチャンク" in context
        assert "親なしチャンク" in context
