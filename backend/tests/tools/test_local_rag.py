"""
ローカルpgvector RAG（COSCUPデモ用）のテスト

- RAG_VECTOR_BACKEND=local-pgvector の分岐とSupabaseフォールバック
- backend.tools.local_rag の行コントラクトとパラメータ化クエリ
- seed_local_knowledge.py のYAML→行変換（DB不要・embeddingはモック）
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.tools.local_rag as local_rag_module
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.tools.enhanced_rag_constants import RPC_SIMILARITY_THRESHOLDS

SAMPLE_LOCAL_ROWS = [
    {
        "id": "uuid-1",
        "title": "営業時間",
        "content": "エンジニアカフェの営業時間は平日9:00-21:00、土日祝10:00-19:00です。",
        "category": "hours",
        "subcategory": None,
        "language": "ja",
        "source": "official",
        "metadata": {"entity": "engineer-cafe"},
        "similarity": 0.85,
    },
    {
        "id": "uuid-2",
        "title": "年末年始",
        "content": "エンジニアカフェは年末年始（12/29-1/3）は休館となります。",
        "category": "hours",
        "subcategory": None,
        "language": "ja",
        "source": "official",
        "metadata": {"entity": "engineer-cafe"},
        "similarity": 0.72,
    },
    {
        "id": "uuid-3",
        "title": "saino営業時間",
        "content": "sainoカフェの営業時間は11:00-18:00です。",
        "category": "hours",
        "subcategory": None,
        "language": "ja",
        "source": "official",
        "metadata": {"entity": "saino"},
        "similarity": 0.65,
    },
]


@pytest.fixture
def mock_supabase():
    """モックSupabaseクライアント"""
    return MagicMock()


@pytest.fixture
def rag_search(mock_supabase):
    """テスト用EnhancedRAGSearchインスタンス"""
    return EnhancedRAGSearch(supabase_client=mock_supabase)


# ==============================================================================
# local_rag モジュール（行コントラクト）
# ==============================================================================


class TestNormalizeRow:
    """DB行→RAG行コントラクトの正規化"""

    def test_normalize_row_full_contract(self):
        """フォールバック行と同じキーセットが返ること"""
        row = {
            "id": "general-hours",
            "title": "営業時間",
            "content": "9:00〜22:00",
            "category": "hours",
            "subcategory": None,
            "language": "ja",
            "metadata": {"source": "official", "entity": "engineer-cafe", "priority": 90},
            "similarity": 0.87,
        }
        normalized = local_rag_module._normalize_row(row)

        assert set(normalized.keys()) == {
            "id",
            "title",
            "content",
            "category",
            "subcategory",
            "language",
            "source",
            "metadata",
            "similarity",
        }
        assert normalized["source"] == "official"
        assert normalized["metadata"]["entity"] == "engineer-cafe"
        assert normalized["metadata"]["priority"] == 90
        assert normalized["metadata"]["tags"] == []
        assert normalized["metadata"]["verified"] is False
        assert normalized["metadata"]["local_fallback"] is True
        assert normalized["similarity"] == 0.87

    def test_normalize_row_defaults(self):
        """metadata未設定・source未設定時にデフォルトが補完されること"""
        row = {"id": "x", "title": "T", "content": "C", "language": "ja", "similarity": None}
        normalized = local_rag_module._normalize_row(row)

        assert normalized["source"] == "official-yaml"
        assert normalized["metadata"]["entity"] == "general"
        assert normalized["metadata"]["priority"] == 50
        assert normalized["similarity"] == 0.0


# ==============================================================================
# local_rag モジュール（検索実行）
# ==============================================================================


class _FakeCursor:
    """cur.execute / cur.fetchall を記録するフェイクカーソル"""

    def __init__(self):
        self.executed_sql = None
        self.params = None
        self.rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        self.executed_sql = sql
        self.params = params

    async def fetchall(self):
        return self.rows


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor


class _FakePool:
    """AsyncConnectionPool のフェイク（open/connection/closeを記録）"""

    def __init__(self, cursor, open_error=None):
        self.cursor = cursor
        self.open_error = open_error
        self.kwargs = {}
        self.opened = False
        self.closed = False

    async def open(self):
        if self.open_error is not None:
            raise self.open_error
        self.opened = True

    def connection(self):
        return _FakeConn(self.cursor)

    async def close(self):
        self.closed = True


class TestLocalPgvectorSearch:
    """local_pgvector_search() の実行パス"""

    @pytest.mark.asyncio
    async def test_no_db_uri_returns_empty(self, monkeypatch):
        """SUPABASE_DB_URI未設定時は空リストを返し、プールを作らないこと"""
        monkeypatch.delenv("SUPABASE_DB_URI", raising=False)

        def _boom(**kwargs):
            raise AssertionError("pool should not be created")

        monkeypatch.setattr(local_rag_module, "AsyncConnectionPool", _boom)

        result = await local_rag_module.local_pgvector_search(
            embedding=[0.1] * 16, similarity_threshold=0.25, match_count=30
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_executes_parameterized_query(self, monkeypatch):
        """パラメータ化SQLで検索関数を呼び、行を正規化して返すこと"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://u:p@h:5432/db")
        cursor = _FakeCursor()
        cursor.rows = [
            {
                "id": "general-hours",
                "title": "営業時間",
                "content": "9:00〜22:00",
                "category": "hours",
                "subcategory": None,
                "language": "ja",
                "metadata": {"source": "official", "entity": "engineer-cafe"},
                "similarity": 0.87,
            }
        ]
        fake_pool = _FakePool(cursor)

        def _pool_factory(**kw):
            fake_pool.kwargs = kw
            return fake_pool

        monkeypatch.setattr(local_rag_module, "AsyncConnectionPool", _pool_factory)

        result = await local_rag_module.local_pgvector_search(
            embedding=[0.1] * 16, similarity_threshold=0.25, match_count=30
        )

        assert len(result) == 1
        assert result[0]["id"] == "general-hours"
        assert result[0]["similarity"] == 0.87
        # パラメータ化クエリ（%s プレースホルダ）であること
        assert "search_knowledge_base_local(%s::vector, %s, %s)" in cursor.executed_sql
        assert cursor.params == ([0.1] * 16, 0.25, 30)
        # プール設定: 遅延オープン + 上限2接続
        assert fake_pool.kwargs["open"] is False
        assert fake_pool.kwargs["max_size"] == 2
        assert fake_pool.kwargs["min_size"] == 0
        # open/close が実行されること
        assert fake_pool.opened is True
        assert fake_pool.closed is True

    @pytest.mark.asyncio
    async def test_error_returns_empty_and_closes_pool(self, monkeypatch):
        """接続エラー時は空リストを返し、プールを閉じること"""
        monkeypatch.setenv("SUPABASE_DB_URI", "postgresql://u:p@h:5432/db")
        fake_pool = _FakePool(_FakeCursor(), open_error=RuntimeError("connection refused"))

        def _pool_factory(**kw):
            fake_pool.kwargs = kw
            return fake_pool

        monkeypatch.setattr(local_rag_module, "AsyncConnectionPool", _pool_factory)

        result = await local_rag_module.local_pgvector_search(
            embedding=[0.1] * 16, similarity_threshold=0.25, match_count=30
        )
        assert result == []
        assert fake_pool.closed is True


# ==============================================================================
# RAG_VECTOR_BACKEND 分岐
# ==============================================================================


class TestLocalBranchRouting:
    """search() のバックエンド分岐"""

    @pytest.mark.asyncio
    async def test_local_env_routes_to_local_pgvector(self, rag_search, mock_supabase, monkeypatch):
        """RAG_VECTOR_BACKEND=local-pgvector でローカル検索が使われ、RPCは呼ばれないこと"""
        monkeypatch.setenv("RAG_VECTOR_BACKEND", "local-pgvector")
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        local_mock = AsyncMock(return_value=SAMPLE_LOCAL_ROWS)
        monkeypatch.setattr(local_rag_module, "local_pgvector_search", local_mock)

        result = await rag_search.search(
            query="エンジニアカフェの営業時間は？",
            category="hours",
            language="ja",
        )

        assert result["success"] is True
        assert result["data"]["totalResults"] > 0
        assert result["data"]["topEntity"] == "engineer-cafe"
        # ローカル検索は閾値・件数を正しく渡す
        local_mock.assert_awaited_once()
        call_kwargs = local_mock.await_args.kwargs
        assert call_kwargs["similarity_threshold"] == RPC_SIMILARITY_THRESHOLDS["hours"]
        assert call_kwargs["match_count"] == 30
        # Supabase RPC は呼ばれない
        mock_supabase.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_env_unset_uses_supabase(self, rag_search, mock_supabase, monkeypatch):
        """RAG_VECTOR_BACKEND未設定時は従来どおりSupabase RPCを使うこと"""
        monkeypatch.delenv("RAG_VECTOR_BACKEND", raising=False)
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        local_mock = AsyncMock(return_value=SAMPLE_LOCAL_ROWS)
        monkeypatch.setattr(local_rag_module, "local_pgvector_search", local_mock)

        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=SAMPLE_LOCAL_ROWS)
        mock_supabase.rpc.return_value = mock_execute

        result = await rag_search.search(
            query="エンジニアカフェの営業時間は？",
            category="hours",
            language="ja",
        )

        assert result["success"] is True
        mock_supabase.rpc.assert_called_once()
        local_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_env_other_value_uses_supabase(self, rag_search, mock_supabase, monkeypatch):
        """RAG_VECTOR_BACKENDが別の値でもSupabase RPCを使うこと"""
        monkeypatch.setenv("RAG_VECTOR_BACKEND", "supabase")
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        local_mock = AsyncMock(return_value=SAMPLE_LOCAL_ROWS)
        monkeypatch.setattr(local_rag_module, "local_pgvector_search", local_mock)

        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=SAMPLE_LOCAL_ROWS)
        mock_supabase.rpc.return_value = mock_execute

        result = await rag_search.search(
            query="エンジニアカフェの営業時間は？",
            category="hours",
            language="ja",
        )

        assert result["success"] is True
        mock_supabase.rpc.assert_called_once()
        local_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_error_falls_back(self, rag_search, mock_supabase, monkeypatch):
        """ローカル検索が例外を投げた場合、_fallback_search_response に委ねること"""
        monkeypatch.setenv("RAG_VECTOR_BACKEND", "local-pgvector")
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        monkeypatch.setattr(
            local_rag_module,
            "local_pgvector_search",
            AsyncMock(side_effect=RuntimeError("connection refused")),
        )
        fallback_mock = AsyncMock(return_value={"success": False, "error": "boom"})
        rag_search._fallback_search_response = fallback_mock

        result = await rag_search.search(query="営業時間", category="hours", language="ja")

        fallback_mock.assert_awaited_once()
        assert result == {"success": False, "error": "boom"}
        mock_supabase.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_empty_falls_back(self, rag_search, mock_supabase, monkeypatch):
        """ローカル検索が空の場合も _fallback_search_response に委ねること"""
        monkeypatch.setenv("RAG_VECTOR_BACKEND", "local-pgvector")
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        monkeypatch.setattr(local_rag_module, "local_pgvector_search", AsyncMock(return_value=[]))
        fallback_mock = AsyncMock(return_value={"success": True, "data": {"results": []}})
        rag_search._fallback_search_response = fallback_mock

        result = await rag_search.search(query="営業時間", category="hours", language="ja")

        fallback_mock.assert_awaited_once()
        assert result["success"] is True
        mock_supabase.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_path_uses_existing_text_fallback_for_insufficient_results(
        self, rag_search, monkeypatch
    ):
        """ローカル検索結果が1件未満2件の場合、既存のテキストフォールバック統合が動くこと"""
        monkeypatch.setenv("RAG_VECTOR_BACKEND", "local-pgvector")
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        monkeypatch.setattr(
            local_rag_module,
            "local_pgvector_search",
            AsyncMock(return_value=[SAMPLE_LOCAL_ROWS[0]]),
        )
        rag_search._text_fallback_search = AsyncMock(return_value=[])

        result = await rag_search.search(
            query="エンジニアカフェの営業時間は？",
            category="hours",
            language="ja",
        )

        assert result["success"] is True
        rag_search._text_fallback_search.assert_awaited_once()


# ==============================================================================
# seed_local_knowledge.py
# ==============================================================================


class TestSeedLocalKnowledge:
    """シードスクリプトのYAML→行変換（DB不要・embeddingはモック）"""

    @pytest.mark.asyncio
    async def test_build_rows_transforms_entries(self, monkeypatch):
        """ja/en両方の行が生成され、メタデータが補完されること"""
        from backend.scripts import seed_local_knowledge as seed

        fake_embedding = [0.5] * 1536
        monkeypatch.setattr(seed, "generate_embedding", AsyncMock(return_value=fake_embedding))

        entries = [
            {
                "id": "e1",
                "title": "タイトル",
                "title_en": "Title",
                "content": "日本語本文",
                "content_en": "English body",
                "category": "hours",
                "tags": ["hours"],
                "priority": 80,
                "verified": True,
                "source": "official",
            },
            {"id": "e2", "title": "T2", "content": "日本語のみ", "category": "general"},
            {"id": "e3", "title": "T3", "content_en": "English only"},
        ]

        rows = await seed.build_rows(entries, 1536)

        # e3 は content が無いためエントリごとスキップ
        assert [r["id"] for r in rows] == ["e1", "e1", "e2"]
        lang_by_id = {r["language"] for r in rows if r["id"] == "e1"}
        assert lang_by_id == {"ja", "en"}

        ja_row = next(r for r in rows if r["id"] == "e1" and r["language"] == "ja")
        en_row = next(r for r in rows if r["id"] == "e1" and r["language"] == "en")
        assert ja_row["title"] == "タイトル"
        assert en_row["title"] == "Title"
        assert ja_row["content"] == "日本語本文"
        assert en_row["content"] == "English body"
        assert ja_row["category"] == "hours"
        assert ja_row["subcategory"] is None
        assert ja_row["embedding"] == fake_embedding
        assert ja_row["metadata"] == {
            "entity": "general",
            "tags": ["hours"],
            "priority": 80,
            "verified": True,
            "source": "official",
        }

    @pytest.mark.asyncio
    async def test_build_rows_skips_embedding_failure(self, monkeypatch):
        """embedding生成失敗（空リスト）の行はスキップされること"""
        from backend.scripts import seed_local_knowledge as seed

        monkeypatch.setattr(seed, "generate_embedding", AsyncMock(return_value=[]))

        rows = await seed.build_rows([{"id": "x", "title": "T", "content": "本文"}], 1536)
        assert rows == []

    @pytest.mark.asyncio
    async def test_build_rows_skips_dimension_mismatch(self, monkeypatch):
        """次元数不一致のembeddingはスキップされること"""
        from backend.scripts import seed_local_knowledge as seed

        monkeypatch.setattr(seed, "generate_embedding", AsyncMock(return_value=[0.5] * 768))

        rows = await seed.build_rows([{"id": "x", "title": "T", "content": "本文"}], 1536)
        assert rows == []

    def test_load_yaml_entries(self, tmp_path):
        """YAMLファイルから entries が読み込めること"""
        from backend.scripts import seed_local_knowledge as seed

        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(
            "entries:\n  - id: x\n    title: T\n    content: C\n", encoding="utf-8"
        )
        entries = seed.load_yaml_entries(yaml_file)
        assert entries == [{"id": "x", "title": "T", "content": "C"}]

    def test_load_yaml_entries_empty(self, tmp_path):
        """entries が無いYAMLは空リストを返すこと"""
        from backend.scripts import seed_local_knowledge as seed

        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("version: 1.0\n", encoding="utf-8")
        assert seed.load_yaml_entries(yaml_file) == []

    def test_load_schema_sql_default_dimensions(self):
        """デフォルト次元数では vector(1536) のままであること"""
        from backend.scripts import seed_local_knowledge as seed

        sql = seed.load_schema_sql(1536)
        assert "vector(1536)" in sql
        assert "search_knowledge_base_local" in sql

    def test_load_schema_sql_substitutes_dimensions(self):
        """別次元数指定時は vector(N) へ差し替えられること"""
        from backend.scripts import seed_local_knowledge as seed

        sql = seed.load_schema_sql(768)
        assert "vector(768)" in sql
        assert "vector(1536)" not in sql
