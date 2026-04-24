"""
EnhancedRAGSearch のユニットテスト

RAG検索のクエリ拡張、スコアリング、テキストフォールバック、
エンベディング生成のロジックを検証する。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.tools.enhanced_rag import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    QUERY_EXPANSION_MAP,
    RPC_SIMILARITY_THRESHOLDS,
    EnhancedRAGSearch,
)

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def mock_supabase():
    """モックSupabaseクライアント"""
    client = MagicMock()
    return client


@pytest.fixture
def rag_search(mock_supabase):
    """テスト用EnhancedRAGSearchインスタンス"""
    return EnhancedRAGSearch(supabase_client=mock_supabase)


@pytest.fixture
def sample_knowledge_results():
    """knowledge_base検索結果のサンプルデータ"""
    return [
        {
            "id": "uuid-1",
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
def sample_pricing_results():
    """料金関連の検索結果サンプル"""
    return [
        {
            "id": "uuid-p1",
            "content": "エンジニアカフェの利用は無料です。",
            "category": "pricing",
            "subcategory": None,
            "language": "ja",
            "source": "official",
            "metadata": {"entity": "engineer-cafe"},
            "similarity": 0.80,
        },
    ]


@pytest.fixture
def sample_access_results():
    """アクセス関連の検索結果サンプル"""
    return [
        {
            "id": "uuid-a1",
            "content": "エンジニアカフェは福岡市中央区天神1-15-5にあります。最寄り駅は天神駅です。",
            "category": "location",
            "subcategory": None,
            "language": "ja",
            "source": "official",
            "metadata": {"entity": "engineer-cafe"},
            "similarity": 0.78,
        },
    ]


# ==============================================================================
# Query Expansion Tests
# ==============================================================================


class TestQueryExpansion:
    """クエリ拡張のテスト"""

    def test_expand_query_hours_japanese(self, rag_search):
        """営業時間クエリが正しく拡張される"""
        result = rag_search._expand_query("エンジニアカフェの営業時間は？", "hours", "ja")

        # 元のクエリが含まれている
        assert "エンジニアカフェの営業時間は？" in result
        # 拡張キーワードが追加されている
        assert "(" in result
        # 英語キーワードが含まれている
        assert "opening hours" in result or "business hours" in result

    def test_expand_query_pricing_japanese(self, rag_search):
        """料金クエリが正しく拡張される"""
        result = rag_search._expand_query("料金を教えてください", "pricing", "ja")

        assert "料金を教えてください" in result
        assert "(" in result

    def test_expand_query_location_english(self, rag_search):
        """英語locationクエリが正しく拡張される"""
        result = rag_search._expand_query("Where is the location?", "location", "en")

        assert "Where is the location?" in result

    @pytest.mark.parametrize(
        ("query", "expected_terms"),
        [
            ("Tell me about membership", ["会員", "利用登録", "無料"]),
            ("What is the membership like?", ["会員", "利用登録", "受付"]),
            ("Can I become a member?", ["会員", "利用登録", "初回"]),
            ("Are there member benefits?", ["無料", "利用料", "会員"]),
        ],
    )
    def test_expand_query_membership_english_matches_kb_terms(
        self,
        rag_search,
        query,
        expected_terms,
    ):
        """英語のmembership系クエリがKB由来の語彙へ拡張される"""
        result = rag_search._expand_query(query, "general", "en")

        assert result.startswith(query)
        assert "(" in result
        for term in expected_terms:
            assert term in result

    def test_expand_query_register_as_member_uses_corpus_terms(self, rag_search):
        """member登録系クエリでKBにある語彙が優先される"""
        result = rag_search._expand_query("How do I register as a member?", "general", "en")

        assert "利用登録" in result
        assert "会員" in result
        assert "受付" in result
        assert "サインアップ" not in result

    def test_expand_query_parking_has_no_membership_noise(self, rag_search):
        """関係ないクエリにmembership拡張が混ざらない"""
        result = rag_search._expand_query("parking", "general", "en")

        assert result == "parking"

    def test_expand_query_business_hours_still_works_in_english(self, rag_search):
        """既存の営業時間クエリ拡張が維持される"""
        result = rag_search._expand_query("What are your business hours?", "hours", "en")

        assert result.startswith("What are your business hours?")
        assert "営業時間" in result or "開館時間" in result

    def test_expand_query_no_expansion_needed(self, rag_search):
        """拡張が不要なクエリ（generalカテゴリではアンカリングしない）"""
        result = rag_search._expand_query("こんにちは", "general", "ja")

        # generalカテゴリはアンカリング対象外
        assert result == "こんにちは"

    def test_expand_query_deduplication(self, rag_search):
        """拡張キーワードの重複が除去される（完全一致キーワード単位）"""
        # _expand_query内部では完全一致キーワード単位で重複除去される
        # 例: "opening hours" と "business hours" は別キーワードとして扱われる
        result = rag_search._expand_query("営業時間", "hours", "ja")

        assert "営業時間" in result
        # 拡張キーワードが追加されている
        assert "(" in result
        # 元クエリのキーワード自体は拡張に含まれない
        expansion_part = result.split("(")[1].rstrip(")")
        assert "営業時間" not in expansion_part.lower()

    def test_expand_query_limited_keywords(self, rag_search):
        """拡張キーワードの数が制限される（最大5キーワード）

        注意: "opening hours"のような複数語キーワードは1つとしてカウントされるが、
        スペース区切りの単語数は5を超える場合がある。
        """
        result = rag_search._expand_query("営業時間", "hours", "ja")

        assert "(" in result
        # 拡張部分が存在し、過度に長くない（5キーワード分を超えない範囲）
        expansion_part = result.split("(")[1].rstrip(")")
        # 空でないこと
        assert len(expansion_part) > 0
        # スペース区切り単語数が妥当な範囲（5キーワード x 最大2語 = 10語以下）
        words = expansion_part.split()
        assert len(words) <= 10


# ==============================================================================
# Scoring Tests
# ==============================================================================


class TestScoring:
    """スコアリングのテスト"""

    def test_score_results_sorts_by_priority(self, rag_search, sample_knowledge_results):
        """結果がpriority_scoreで正しくソートされる"""
        scored = rag_search._score_results(
            sample_knowledge_results, "エンジニアカフェの営業時間は？", "hours", "ja"
        )

        # priority_scoreが降順であることを確認
        for i in range(len(scored) - 1):
            assert scored[i]["priority_score"] >= scored[i + 1]["priority_score"]

    def test_score_results_adds_entity(self, rag_search, sample_knowledge_results):
        """スコアリング結果にentityが付与される"""
        scored = rag_search._score_results(sample_knowledge_results, "営業時間", "hours", "ja")

        for result in scored:
            assert "entity" in result
            assert "priority_score" in result
            assert "original_similarity" in result

    def test_entity_bonus_for_engineer_cafe_query(self, rag_search, sample_knowledge_results):
        """エンジニアカフェに言及するクエリでentity bonusが付く"""
        scored = rag_search._score_results(
            sample_knowledge_results, "エンジニアカフェの営業時間", "hours", "ja"
        )

        # エンジニアカフェの結果が最上位にくるはず
        assert scored[0]["entity"] == "engineer-cafe"
        # entity bonusが加算されているのでoriginal_similarityより高い
        assert scored[0]["priority_score"] > scored[0]["original_similarity"]

    def test_category_bonus_applied(self, rag_search):
        """カテゴリ一致時にボーナスが適用される"""
        result = {
            "content": "営業時間は9:00-21:00",
            "metadata": {"category": "hours"},
            "similarity": 0.5,
        }

        bonus = rag_search._calculate_category_bonus(result, "hours")
        assert bonus == 0.2

    def test_category_bonus_not_applied_for_mismatch(self, rag_search):
        """カテゴリ不一致時にボーナスが0"""
        result = {
            "content": "料金は無料です",
            "metadata": {"category": "pricing"},
            "similarity": 0.5,
        }

        bonus = rag_search._calculate_category_bonus(result, "hours")
        assert bonus == 0.0


# ==============================================================================
# Entity Detection Tests
# ==============================================================================


class TestEntityDetection:
    """エンティティ検出のテスト"""

    def test_detect_engineer_cafe_from_content(self, rag_search):
        """コンテンツからエンジニアカフェを検出"""
        result = {"content": "エンジニアカフェは福岡にあります", "metadata": {}}
        assert rag_search._detect_entity(result) == "engineer-cafe"

    def test_detect_entity_from_metadata(self, rag_search):
        """メタデータからエンティティを検出"""
        result = {"content": "営業時間は9:00-21:00", "metadata": {"entity": "saino"}}
        assert rag_search._detect_entity(result) == "saino"

    def test_detect_meeting_room(self, rag_search):
        """会議室エンティティを検出"""
        result = {"content": "会議室の予約は3時間まで", "metadata": {}}
        assert rag_search._detect_entity(result) == "meeting-room"

    def test_detect_general_entity(self, rag_search):
        """特定エンティティが見つからない場合はgeneral"""
        result = {"content": "天気は晴れです", "metadata": {}}
        assert rag_search._detect_entity(result) == "general"


# ==============================================================================
# Context Building Tests
# ==============================================================================


class TestContextBuilding:
    """コンテキスト構築のテスト"""

    def test_build_context_groups_by_entity(self, rag_search):
        """エンティティごとにグループ化されたコンテキストが構築される"""
        results = [
            {"content": "営業時間は9:00-21:00", "entity": "engineer-cafe"},
            {"content": "sainoは11:00-18:00", "entity": "saino"},
        ]

        context = rag_search._build_context_from_results(results, "hours", "ja")

        assert "エンジニアカフェ" in context
        assert "sainoカフェ" in context
        assert "営業時間は9:00-21:00" in context
        assert "sainoは11:00-18:00" in context

    def test_build_context_empty_results(self, rag_search):
        """空の結果リストでは空文字列"""
        context = rag_search._build_context_from_results([], "hours", "ja")
        assert context == ""

    def test_build_context_entity_priority_order(self, rag_search):
        """エンティティが優先順位順に並ぶ"""
        results = [
            {"content": "sainoは11:00", "entity": "saino"},
            {"content": "営業時間は9:00", "entity": "engineer-cafe"},
        ]

        context = rag_search._build_context_from_results(results, "hours", "ja")

        # engineer-cafeがsainoより先に出現すること
        ec_pos = context.index("エンジニアカフェ")
        saino_pos = context.index("sainoカフェ")
        assert ec_pos < saino_pos


# ==============================================================================
# Practical Advice Tests
# ==============================================================================


class TestPracticalAdvice:
    """アドバイス生成のテスト"""

    def test_advice_for_hours_category(self, rag_search):
        """hoursカテゴリで日本語アドバイスが生成される"""
        results = [{"content": "営業時間"}]
        advice = rag_search._generate_practical_advice(results, "営業時間", "hours", "ja")

        assert advice is not None
        assert "営業時間" in advice

    def test_advice_for_pricing_english(self, rag_search):
        """pricingカテゴリで英語アドバイスが生成される"""
        results = [{"content": "pricing"}]
        advice = rag_search._generate_practical_advice(results, "price", "pricing", "en")

        assert advice is not None
        assert "Pricing" in advice or "pricing" in advice.lower()

    def test_no_advice_for_unknown_category(self, rag_search):
        """未知カテゴリではアドバイスがNone"""
        results = [{"content": "something"}]
        advice = rag_search._generate_practical_advice(results, "query", "unknown", "ja")

        assert advice is None

    def test_no_advice_for_empty_results(self, rag_search):
        """空の結果でNone"""
        advice = rag_search._generate_practical_advice([], "query", "hours", "ja")
        assert advice is None


# ==============================================================================
# Embedding Configuration Tests
# ==============================================================================


class TestEmbeddingConfiguration:
    """エンベディング設定のテスト"""

    def test_default_model_and_dimensions(self, mock_supabase):
        """デフォルトモデルと次元数が設定される"""
        rag = EnhancedRAGSearch(supabase_client=mock_supabase)

        assert rag.embedding_model == DEFAULT_EMBEDDING_MODEL
        assert rag.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS

    def test_custom_model_via_constructor(self, mock_supabase):
        """コンストラクタでカスタムモデルを設定可能"""
        rag = EnhancedRAGSearch(
            supabase_client=mock_supabase,
            embedding_model="text-embedding-3-large",
            embedding_dimensions=3072,
        )

        assert rag.embedding_model == "text-embedding-3-large"
        assert rag.embedding_dimensions == 3072

    def test_custom_model_via_env(self, mock_supabase):
        """環境変数でカスタムモデルを設定可能"""
        with patch.dict(
            "os.environ",
            {"EMBEDDING_MODEL": "custom-model", "EMBEDDING_DIMENSIONS": "768"},
        ):
            rag = EnhancedRAGSearch(supabase_client=mock_supabase)

        assert rag.embedding_model == "custom-model"
        assert rag.embedding_dimensions == 768


# ==============================================================================
# Search Integration Tests (with mocked external calls)
# ==============================================================================


class TestSearchIntegration:
    """検索統合テスト（外部APIはモック）"""

    @pytest.mark.asyncio
    async def test_search_returns_results_on_vector_match(
        self, rag_search, mock_supabase, sample_knowledge_results
    ):
        """ベクトル検索が結果を返す場合、正常な応答が返る"""
        # Mock embedding generation
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        # Mock Supabase RPC
        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=sample_knowledge_results)
        mock_supabase.rpc.return_value = mock_execute

        result = await rag_search.search(
            query="エンジニアカフェの営業時間は？",
            category="hours",
            language="ja",
        )

        assert result["success"] is True
        assert result["data"]["totalResults"] > 0
        assert result["data"]["context"] != ""
        assert result["data"]["topEntity"] == "engineer-cafe"

    @pytest.mark.asyncio
    async def test_search_falls_back_to_text_when_vector_empty(
        self, rag_search, mock_supabase, sample_knowledge_results
    ):
        """ベクトル検索が空の場合、テキストフォールバックが使われる"""
        # Mock embedding generation
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        # Mock Supabase RPC - return empty
        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=[])
        mock_supabase.rpc.return_value = mock_execute

        # Mock text fallback - return results
        rag_search._text_fallback_search = AsyncMock(return_value=sample_knowledge_results)

        result = await rag_search.search(
            query="エンジニアカフェの営業時間は？",
            category="hours",
            language="ja",
        )

        assert result["success"] is True
        # テキストフォールバックが呼ばれた
        rag_search._text_fallback_search.assert_called_once()
        assert result["data"]["totalResults"] > 0

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_no_results(self, rag_search, mock_supabase):
        """検索結果が全くない場合の挙動"""
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=[])
        mock_supabase.rpc.return_value = mock_execute

        rag_search._text_fallback_search = AsyncMock(return_value=[])

        result = await rag_search.search(
            query="存在しない情報",
            category="general",
            language="ja",
        )

        assert result["success"] is True
        assert result["data"]["context"] == ""
        assert result["data"]["totalResults"] == 0

    @pytest.mark.asyncio
    async def test_search_handles_embedding_error(self, rag_search, mock_supabase):
        """エンベディング生成エラー時にerrorレスポンスを返す"""
        rag_search._generate_embedding = AsyncMock(side_effect=Exception("API error"))

        result = await rag_search.search(query="テスト", category="general", language="ja")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_with_pricing_query(
        self, rag_search, mock_supabase, sample_pricing_results
    ):
        """料金クエリで正しく検索される"""
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=sample_pricing_results)
        mock_supabase.rpc.return_value = mock_execute

        # テキストフォールバックもモック（結果不十分で呼ばれる可能性あり）
        rag_search._text_fallback_search = AsyncMock(return_value=[])

        result = await rag_search.search(
            query="料金を教えてください",
            category="pricing",
            language="ja",
        )

        assert result["success"] is True
        assert "無料" in result["data"]["context"] or result["data"]["totalResults"] > 0

    @pytest.mark.asyncio
    async def test_search_with_access_query(self, rag_search, mock_supabase, sample_access_results):
        """アクセスクエリで正しく検索される"""
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=sample_access_results)
        mock_supabase.rpc.return_value = mock_execute

        rag_search._text_fallback_search = AsyncMock(return_value=[])

        result = await rag_search.search(
            query="エンジニアカフェへのアクセス方法",
            category="location",
            language="ja",
        )

        assert result["success"] is True
        assert result["data"]["totalResults"] > 0

    @pytest.mark.asyncio
    async def test_search_uses_low_similarity_threshold(
        self, rag_search, mock_supabase, sample_knowledge_results
    ):
        """ベクトル検索が0.3の低い閾値を使っていることを確認"""
        rag_search._generate_embedding = AsyncMock(return_value=[0.1] * 1536)

        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=sample_knowledge_results)
        mock_supabase.rpc.return_value = mock_execute

        await rag_search.search(query="営業時間", category="hours", language="ja")

        # RPCが呼ばれた引数を検証
        call_args = mock_supabase.rpc.call_args
        assert call_args[0][0] == "search_knowledge_base"
        params = call_args[0][1]
        assert params["similarity_threshold"] == RPC_SIMILARITY_THRESHOLDS["hours"]


# ==============================================================================
# Text Fallback Search Tests
# ==============================================================================


class TestTextFallbackSearch:
    """テキストフォールバック検索のテスト"""

    @pytest.mark.asyncio
    async def test_text_fallback_with_category_match(self, rag_search, mock_supabase):
        """カテゴリ一致でテキストフォールバックが結果を返す"""
        mock_result = MagicMock()
        mock_result.data = [
            {
                "id": "uuid-fb1",
                "content": "エンジニアカフェの営業時間は平日9:00-21:00です。",
                "category": "hours",
                "subcategory": None,
                "language": "ja",
                "source": "official",
                "metadata": {},
            }
        ]

        mock_query = MagicMock()
        mock_query.limit.return_value = mock_result
        mock_eq_lang = MagicMock()
        mock_eq_lang.limit.return_value = mock_result
        mock_eq_cat = MagicMock()
        mock_eq_cat.eq.return_value = mock_eq_lang
        # PR #546 (#541): _text_fallback_search now chains
        # .filter("content_embedding", "not.is", None) after .select(...)
        # before the category/language .eq(...) calls, so the mock chain
        # must route through a filter node before reaching category eq.
        mock_filter = MagicMock()
        mock_filter.eq.return_value = mock_eq_cat
        mock_select = MagicMock()
        mock_select.filter.return_value = mock_filter
        mock_select.eq.return_value = mock_eq_cat
        mock_table = MagicMock()
        mock_table.select.return_value = mock_select

        mock_supabase.table.return_value = mock_table
        mock_result.execute = MagicMock(return_value=mock_result)
        mock_eq_lang.execute = MagicMock(return_value=mock_result)

        results = await rag_search._text_fallback_search(
            query="営業時間を教えて", category="hours", language="ja", max_results=5
        )

        # カテゴリ一致＋テキストマッチがあるので結果が返る
        assert len(results) > 0
        assert results[0]["similarity"] > 0

    @pytest.mark.asyncio
    async def test_text_fallback_handles_error(self, rag_search, mock_supabase):
        """テキストフォールバックでエラーが発生しても空リストを返す"""
        mock_supabase.table.side_effect = Exception("DB error")

        results = await rag_search._text_fallback_search(
            query="テスト", category="general", language="ja", max_results=5
        )

        assert results == []


# ==============================================================================
# Entity Priority Tests
# ==============================================================================


class TestEntityPriority:
    """エンティティ優先順位のテスト"""

    def test_hours_category_priority(self, rag_search):
        """hoursカテゴリのエンティティ優先順位"""
        priority = rag_search._get_entity_priority("hours")
        assert priority[0] == "engineer-cafe"

    def test_pricing_category_priority(self, rag_search):
        """pricingカテゴリのエンティティ優先順位"""
        priority = rag_search._get_entity_priority("pricing")
        assert priority[0] == "engineer-cafe"

    def test_unknown_category_default_priority(self, rag_search):
        """未知カテゴリではデフォルト優先順位"""
        priority = rag_search._get_entity_priority("unknown")
        assert priority[0] == "engineer-cafe"


# ==============================================================================
# QUERY_EXPANSION_MAP Tests
# ==============================================================================


class TestQueryExpansionMap:
    """クエリ拡張マッピングの整合性テスト"""

    def test_japanese_keys_have_english_synonyms(self):
        """日本語キーのエントリに英語の同義語が含まれる"""
        assert "opening hours" in QUERY_EXPANSION_MAP["営業時間"]
        assert "pricing" in QUERY_EXPANSION_MAP["料金"]
        assert "access" in QUERY_EXPANSION_MAP["アクセス"]

    def test_english_keys_have_japanese_synonyms(self):
        """英語キーのエントリに日本語の同義語が含まれる"""
        assert "営業時間" in QUERY_EXPANSION_MAP["opening hours"]
        assert "料金" in QUERY_EXPANSION_MAP["price"]
        assert "アクセス" in QUERY_EXPANSION_MAP["location"]

    def test_membership_entries_use_kb_aligned_terms(self):
        """membership系の英語キーがKB語彙に寄せられている"""
        assert "サインアップ" not in QUERY_EXPANSION_MAP["register"]
        assert "利用登録" in QUERY_EXPANSION_MAP["register"]
        assert "無料" in QUERY_EXPANSION_MAP["membership"]
        assert "無料" in QUERY_EXPANSION_MAP["member benefits"]
        assert "会員番号" in QUERY_EXPANSION_MAP["member"]


# ==============================================================================
# Entity Anchoring Tests
# ==============================================================================


class TestEntityAnchoring:
    """エンティティアンカリングのテスト"""

    def test_anchoring_applied_for_short_non_general_query(self, rag_search):
        """短い非generalクエリにアンカリングが適用される"""
        result = rag_search._expand_query("営業時間", "hours", "ja")
        assert result.startswith("エンジニアカフェ ")

    def test_anchoring_skipped_when_already_contains_anchor(self, rag_search):
        """クエリに既にエンジニアカフェが含まれている場合スキップ"""
        query = "エンジニアカフェの料金"
        result = rag_search._expand_query(query, "pricing", "ja")
        # 二重にアンカリングされていないことを確認
        assert result.count("エンジニアカフェ") == 1
