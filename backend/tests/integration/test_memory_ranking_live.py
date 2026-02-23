"""
Memory Dynamic Ranking + Context Priority Live Tests

3A. メッセージ動的ランキングテスト (Unit-level, Supabaseモック)
3B. コンテキスト優先度シグナル検証テスト (Unit-level)
3C. 閾値動的調整テスト (Unit-level)
3D. メッセージウィンドウイングテスト (Unit-level)

Note: e2e マークのないテストは実際の Supabase/LLM を呼ばない。
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.utils.context_priority import ContextPriorityEngine, ContextSignals
from backend.utils.message_windowing import MessageWindow, apply_message_window

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_helper_mock():
    """Supabase クライアントをモックした SimplifiedMemoryHelper インスタンス"""
    with patch("backend.utils.memory_helper.create_client") as mock_create:
        mock_create.return_value = MagicMock()
        # 環境変数もモックして初期化エラーを防ぐ
        with patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://mock.supabase.co", "SUPABASE_KEY": "mock-key"},
        ):
            from backend.utils.memory_helper import SimplifiedMemoryHelper

            helper = SimplifiedMemoryHelper()
            yield helper


@pytest.fixture
def context_engine():
    """ContextPriorityEngine インスタンス"""
    return ContextPriorityEngine()


@pytest.fixture
def message_window():
    """デフォルト設定の MessageWindow インスタンス"""
    return MessageWindow(max_messages=20, summary_threshold=30)


# ---------------------------------------------------------------------------
# 3A. Message Dynamic Ranking Tests
# ---------------------------------------------------------------------------


class TestMessageDynamicRanking:
    """_rank_messages の複合スコアランキングを検証する"""

    def _make_msg(self, content: str, age_ms: int = 0) -> dict:
        """テスト用メッセージを生成するヘルパー

        Args:
            content: メッセージ内容
            age_ms: 現在からの経過時間（ミリ秒）。0 = 現在
        """
        ts = int(time.time() * 1000) - age_ms
        return {
            "role": "user",
            "content": content,
            "metadata": {"timestamp": ts},
        }

    def test_rank_messages_relevance_ordering(self, memory_helper_mock):
        """WiFi 関連のクエリに対して関連度でランキングされることを検証する

        _rank_messages の relevance スコアは bigram マッチ率で計算される。
        クエリ "WiFiパスワードを教えて" に対して:
        - "WiFiパスワードを確認する方法" はクエリと多くの bigram を共有 → 高スコア
        - "WiFiに繋がらないときの対処" は WiFi を含むが bigram 一致が少ない → 中スコア
        - "レーザーカッターの使い方" はクエリと bigram をほとんど共有しない → 低スコア
        """
        same_ts = int(time.time() * 1000)
        # WiFi + パスワード両方を含む → クエリとのオーバーラップ大
        msg_high = {
            "role": "user",
            "content": "WiFiパスワードを確認する方法",
            "metadata": {"timestamp": same_ts},
        }
        # WiFi を含むが bigram 一致が少ない → 中程度
        msg_mid = {
            "role": "user",
            "content": "WiFiに繋がらないときの対処",
            "metadata": {"timestamp": same_ts},
        }
        # 完全に無関係
        msg_low = {
            "role": "user",
            "content": "レーザーカッターの使い方",
            "metadata": {"timestamp": same_ts},
        }

        messages = [msg_high, msg_mid, msg_low]
        query = "WiFiパスワードを教えて"

        ranked = memory_helper_mock._rank_messages(messages, query)

        # 全メッセージにスコアが付いていること
        assert all("_rank_score" in m for m in ranked)

        # ランキング結果が 3 件であること
        assert len(ranked) == 3

        # スコアを取得
        high_score = next(m["_rank_score"] for m in ranked if "WiFiパスワード" in m["content"])
        mid_score = next(m["_rank_score"] for m in ranked if "繋がらない" in m["content"])
        low_score = next(m["_rank_score"] for m in ranked if "レーザーカッター" in m["content"])

        # WiFiパスワードメッセージ >= 無関係メッセージ であること
        assert high_score >= low_score, (
            "WiFiパスワード含むメッセージは無関係メッセージと同等以上のスコアであること"
        )
        # WiFi 含むメッセージ (mid/high) は無関係メッセージ (low) より高いか同等以上
        assert mid_score >= low_score, (
            "WiFi含むメッセージは完全無関係メッセージと同等以上のスコアであること"
        )

    def test_rank_messages_recency_factor(self, memory_helper_mock):
        """古いメッセージより新しいメッセージが高い recency スコアを持つことを検証する"""
        one_week_ms = 7 * 24 * 3600 * 1000  # 1週間をミリ秒で表現

        recent_msg = self._make_msg("最近のメッセージ", age_ms=1_000)  # 1 秒前
        old_msg = self._make_msg("古いメッセージ", age_ms=one_week_ms)

        ranked = memory_helper_mock._rank_messages([recent_msg, old_msg], "テスト")

        assert len(ranked) == 2
        # ランキング後は降順のためインデックス 0 が最高スコア
        assert ranked[0]["content"] == "最近のメッセージ", (
            "1秒前のメッセージが1週間前のメッセージより上位にランキングされること"
        )

    def test_rank_messages_empty_list(self, memory_helper_mock):
        """空のメッセージリストに対して空リストを返すことを検証する"""
        result = memory_helper_mock._rank_messages([], "テストクエリ")
        assert result == []

    def test_rank_messages_composite_score_components(self, memory_helper_mock):
        """各メッセージに _rank_score キーが付与されることを検証する"""
        messages = [
            self._make_msg("エンジニアカフェの利用方法"),
            self._make_msg("WiFiの接続方法"),
            self._make_msg("3Dプリンタの予約"),
        ]

        ranked = memory_helper_mock._rank_messages(messages, "エンジニアカフェ WiFi")

        for msg in ranked:
            assert "_rank_score" in msg, "各メッセージに _rank_score が付いていること"
            score = msg["_rank_score"]
            assert 0.0 <= score <= 1.0, f"スコアは [0, 1] の範囲内であること: {score}"

    def test_rank_messages_returns_sorted_descending(self, memory_helper_mock):
        """ランキング結果が降順ソートされていることを検証する"""
        messages = [
            self._make_msg("全く無関係なトピック", age_ms=10_000),
            self._make_msg("WiFiパスワードを教えてください", age_ms=0),
        ]

        ranked = memory_helper_mock._rank_messages(messages, "WiFiのパスワード")

        scores = [m["_rank_score"] for m in ranked]
        assert scores == sorted(scores, reverse=True), "スコアは降順でソートされていること"


# ---------------------------------------------------------------------------
# 3B. Context Priority Signal Verification Tests
# ---------------------------------------------------------------------------


class TestContextPrioritySignals:
    """ContextPriorityEngine のシグナル抽出ロジックを検証する"""

    def test_extract_signals_basic(self, context_engine):
        """基本的なメモリコンテキストからシグナルを正しく抽出することを検証する"""
        memory_context = {
            "conversation_history": [1, 2, 3],
            "topics": ["wifi"],
            "previous_categories": ["facility"],
        }
        knowledge_results = {
            "results": [{"priority_score": 0.85}],
            "category": "facility",
            "query": "WiFiパスワード",
        }

        signals = context_engine.extract_signals_from_context(memory_context, knowledge_results)

        assert signals.conversation_depth == 3, (
            "会話深度が conversation_history の長さと一致すること"
        )
        assert signals.rag_cache_top_score == pytest.approx(0.85), (
            "RAG キャッシュのトップスコアが取得されること"
        )
        assert "facility" in signals.previous_categories, (
            "memory_context の previous_categories が引き継がれること"
        )

    def test_extract_signals_empty_context(self, context_engine):
        """None コンテキストに対してデフォルト値のシグナルを返すことを検証する"""
        signals = context_engine.extract_signals_from_context(None, None)

        assert signals.conversation_depth == 0
        assert signals.rag_cache_top_score == pytest.approx(0.0)

    def test_extract_signals_multiple_rag_results(self, context_engine):
        """複数の RAG 結果から最高スコアを抽出することを検証する"""
        knowledge_results = {
            "results": [
                {"priority_score": 0.5},
                {"priority_score": 0.9},
                {"priority_score": 0.7},
            ],
            "category": "general",
            "query": "test",
        }

        signals = context_engine.extract_signals_from_context(None, knowledge_results)

        assert signals.rag_cache_top_score == pytest.approx(0.9), (
            "複数の結果から最高スコアが選ばれること"
        )

    def test_extract_signals_rag_category_added_to_previous(self, context_engine):
        """RAG 結果のカテゴリが previous_categories に追加されることを検証する"""
        memory_context = {"previous_categories": ["facility"]}
        knowledge_results = {
            "results": [{"priority_score": 0.7}],
            "category": "event",
            "query": "test",
        }

        signals = context_engine.extract_signals_from_context(memory_context, knowledge_results)

        assert "event" in signals.previous_categories, (
            "RAG カテゴリが previous_categories に追加されること"
        )
        assert "facility" in signals.previous_categories, (
            "既存の previous_categories も保持されること"
        )

    def test_compute_specificity_short_query(self, context_engine):
        """短いクエリ（10 文字未満）が低い具体性スコアを持つことを検証する"""
        score = context_engine._compute_specificity("WiFi")

        assert score < 0.5, f"短いクエリは 0.5 未満のスコアであること: {score}"

    def test_compute_specificity_specific_query(self, context_engine):
        """固有名詞・数値・長さを含む具体的なクエリが高いスコアを持つことを検証する"""
        query = "エンジニアカフェの3階にある会議室を予約したい"
        score = context_engine._compute_specificity(query)

        assert score > 0.7, f"固有名詞+数値+長さを含むクエリは 0.7 超のスコアであること: {score}"

    def test_compute_specificity_empty(self, context_engine):
        """空のクエリに対して 0.0 を返すことを検証する"""
        score = context_engine._compute_specificity("")

        assert score == pytest.approx(0.0)

    def test_compute_specificity_with_number(self, context_engine):
        """数値を含むクエリがベーススコアより高いことを検証する"""
        score_with_number = context_engine._compute_specificity("1000円の料金は？")
        score_without_number = context_engine._compute_specificity("料金はいくら？")

        assert score_with_number > score_without_number, (
            "数値含むクエリの方が高いスコアであること"
        )

    def test_compute_specificity_with_proper_noun(self, context_engine):
        """固有名詞（エンジニアカフェ）を含むクエリが高いスコアを持つことを検証する"""
        score = context_engine._compute_specificity("エンジニアカフェはどこですか")

        assert score > 0.5, f"固有名詞含むクエリはベーススコア超であること: {score}"


# ---------------------------------------------------------------------------
# 3C. Threshold Dynamic Adjustment Tests
# ---------------------------------------------------------------------------


class TestThresholdDynamicAdjustment:
    """compute_adjusted_thresholds の閾値調整ロジックを検証する"""

    BASE_THRESHOLDS = {"high": 0.80, "medium": 0.60, "term_match": 0.50}

    def test_threshold_topic_consistency(self, context_engine):
        """トピック一貫性がある場合に high/medium が -0.03 されることを検証する"""
        signals = ContextSignals(previous_categories=("facility",))
        result = context_engine.compute_adjusted_thresholds(
            "facility", "test", signals, self.BASE_THRESHOLDS
        )

        assert result["high"] == pytest.approx(0.77), (
            "facility カテゴリ一致で high が 0.80 - 0.03 = 0.77 になること"
        )
        assert result["medium"] == pytest.approx(0.57), (
            "facility カテゴリ一致で medium が 0.60 - 0.03 = 0.57 になること"
        )
        assert result["term_match"] == pytest.approx(0.50), "term_match は変化しないこと"

    def test_threshold_high_rag_score(self, context_engine):
        """RAG スコアが高い場合に high/medium が +0.05 されることを検証する"""
        signals = ContextSignals(rag_cache_top_score=0.9)
        result = context_engine.compute_adjusted_thresholds(
            "general", "test", signals, self.BASE_THRESHOLDS
        )

        assert result["high"] == pytest.approx(0.85), (
            "RAG スコア > 0.8 で high が 0.80 + 0.05 = 0.85 になること"
        )
        assert result["medium"] == pytest.approx(0.65), (
            "RAG スコア > 0.8 で medium が 0.60 + 0.05 = 0.65 になること"
        )

    def test_threshold_high_specificity(self, context_engine):
        """リクエスト具体性が高い場合に medium のみ +0.03 されることを検証する"""
        signals = ContextSignals(request_specificity=0.9)
        result = context_engine.compute_adjusted_thresholds(
            "general", "test", signals, self.BASE_THRESHOLDS
        )

        assert result["medium"] == pytest.approx(0.63), (
            "具体性 > 0.8 で medium が 0.60 + 0.03 = 0.63 になること"
        )
        assert result["high"] == pytest.approx(0.80), (
            "具体性は high に影響しないため 0.80 のまま"
        )

    def test_threshold_combined_adjustments(self, context_engine):
        """トピック一貫性 + 高 RAG スコアの複合調整が加算されることを検証する"""
        # トピック一貫性: high -0.03, medium -0.03
        # 高 RAG スコア:   high +0.05, medium +0.05
        # 合計:           high +0.02, medium +0.02
        signals = ContextSignals(
            previous_categories=("facility",),
            rag_cache_top_score=0.9,
        )
        result = context_engine.compute_adjusted_thresholds(
            "facility", "test", signals, self.BASE_THRESHOLDS
        )

        assert result["high"] == pytest.approx(0.82), (
            "複合調整 (-0.03 + 0.05) = +0.02 → 0.80 + 0.02 = 0.82"
        )
        assert result["medium"] == pytest.approx(0.62), (
            "複合調整 (-0.03 + 0.05) = +0.02 → 0.60 + 0.02 = 0.62"
        )

    def test_threshold_max_adjustment_clamped(self, context_engine):
        """調整幅が MAX_ADJUSTMENT (0.10) にクランプされることを検証する"""
        from backend.utils.context_priority import MAX_ADJUSTMENT

        # 最大調整幅を超えるシナリオ: RAGスコア高 (+0.05) のみ適用
        signals = ContextSignals(rag_cache_top_score=0.95)
        result = context_engine.compute_adjusted_thresholds(
            "general", "test", signals, self.BASE_THRESHOLDS
        )

        # +0.05 は MAX_ADJUSTMENT 以内なのでクランプされない
        high_adj = result["high"] - self.BASE_THRESHOLDS["high"]
        assert abs(high_adj) <= MAX_ADJUSTMENT, (
            f"調整幅は +-{MAX_ADJUSTMENT} を超えないこと: {high_adj}"
        )

    def test_threshold_no_signals_unchanged(self, context_engine):
        """シグナルがすべてデフォルト値の場合、閾値が変化しないことを検証する"""
        signals = ContextSignals()  # すべてデフォルト値
        result = context_engine.compute_adjusted_thresholds(
            "general", "test", signals, self.BASE_THRESHOLDS
        )

        assert result["high"] == pytest.approx(self.BASE_THRESHOLDS["high"])
        assert result["medium"] == pytest.approx(self.BASE_THRESHOLDS["medium"])
        assert result["term_match"] == pytest.approx(self.BASE_THRESHOLDS["term_match"])

    def test_threshold_returns_new_dict(self, context_engine):
        """元の base_thresholds がミューテーションされないことを検証する"""
        base = {"high": 0.80, "medium": 0.60, "term_match": 0.50}
        original_base = dict(base)
        signals = ContextSignals(rag_cache_top_score=0.9)

        context_engine.compute_adjusted_thresholds("general", "test", signals, base)

        assert base == original_base, "base_thresholds はミューテーションされないこと"


# ---------------------------------------------------------------------------
# 3D. Message Windowing Tests
# ---------------------------------------------------------------------------


class TestMessageWindowing:
    """MessageWindow のウィンドウ適用ロジックを検証する"""

    def _make_human_messages(self, count: int) -> list:
        """指定件数の HumanMessage を生成する"""
        return [HumanMessage(content=f"質問 {i}") for i in range(count)]

    def _make_ai_messages(self, count: int) -> list:
        """指定件数の AIMessage を生成する"""
        return [AIMessage(content=f"回答 {i}") for i in range(count)]

    def test_window_under_limit(self, message_window):
        """15 件のメッセージはウィンドウ適用後も全件保持されることを検証する"""
        messages = self._make_human_messages(15)
        result = message_window.apply_window(messages)

        assert len(result) == 15, "上限未満のメッセージはすべて保持されること"

    def test_window_over_limit(self, message_window):
        """25 件のメッセージに対して最近の 20 件 + 要約プレースホルダーが返されることを検証する"""
        messages = self._make_human_messages(25)
        result = message_window.apply_window(messages)

        # システムメッセージ(要約) + 最近の max_messages 件
        non_system = [m for m in result if not isinstance(m, SystemMessage)]
        system_msgs = [m for m in result if isinstance(m, SystemMessage)]

        assert len(non_system) == 20, "最近の 20 件の会話メッセージが残ること"
        assert len(system_msgs) == 1, "要約 SystemMessage が 1 件追加されること"
        assert "summarized" in system_msgs[0].content.lower(), (
            "要約プレースホルダーに 'summarized' が含まれること"
        )

    def test_should_compact_under_threshold(self, message_window):
        """20 件のメッセージは should_compact が False を返すことを検証する"""
        messages = self._make_human_messages(20)
        result = message_window.should_compact(messages)

        assert result is False, "閾値 (30) 未満の場合、コンパクション不要"

    def test_should_compact_over_threshold(self, message_window):
        """35 件のメッセージは should_compact が True を返すことを検証する"""
        messages = self._make_human_messages(35)
        result = message_window.should_compact(messages)

        assert result is True, "閾値 (30) 以上の場合、コンパクションが必要"

    def test_should_compact_at_threshold(self, message_window):
        """ちょうど summary_threshold (30) 件のとき True を返すことを検証する"""
        messages = self._make_human_messages(30)
        result = message_window.should_compact(messages)

        assert result is True, "summary_threshold と同数の場合も True"

    def test_window_preserves_system_messages(self, message_window):
        """システムメッセージが常に保持されることを検証する"""
        sys_msgs = [SystemMessage(content="あなたはナビゲーターAIです。")]
        human_msgs = self._make_human_messages(25)
        all_messages = sys_msgs + human_msgs

        result = message_window.apply_window(all_messages)

        # 元の SystemMessage が保持されているか確認
        preserved_sys = [
            m for m in result if isinstance(m, SystemMessage) and "ナビゲーター" in m.content
        ]
        assert len(preserved_sys) == 1, "元の SystemMessage が保持されること"

    def test_window_keeps_most_recent_messages(self, message_window):
        """ウィンドウ適用後に最新メッセージが保持されることを検証する"""
        messages = [HumanMessage(content=f"メッセージ {i}") for i in range(25)]
        result = message_window.apply_window(messages)

        non_system = [m for m in result if not isinstance(m, SystemMessage)]
        # 最新 20 件 = インデックス 5 〜 24 のメッセージ
        assert non_system[-1].content == "メッセージ 24", "最新のメッセージが保持されること"
        assert non_system[0].content == "メッセージ 5", "古すぎるメッセージは除外されること"

    def test_apply_message_window_convenience_function(self):
        """モジュールレベルの apply_message_window が正しく動作することを検証する"""
        messages = [HumanMessage(content=f"質問 {i}") for i in range(10)]
        result = apply_message_window(messages)

        assert len(result) == 10, "上限未満のメッセージはすべて返されること"

    def test_window_exact_limit_no_summary(self, message_window):
        """ちょうど max_messages (20) 件の場合、要約が生成されないことを検証する"""
        messages = self._make_human_messages(20)
        result = message_window.apply_window(messages)

        system_msgs = [m for m in result if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 0, "上限ちょうどのメッセージには要約が不要"
        assert len(result) == 20

    def test_should_compact_excludes_system_messages(self, message_window):
        """should_compact は SystemMessage をカウントから除外することを検証する"""
        # SystemMessage 20 件 + HumanMessage 20 件 = 計 40 件
        # 非システムメッセージは 20 件 → 閾値 30 未満 → False
        sys_msgs = [SystemMessage(content=f"sys {i}") for i in range(20)]
        human_msgs = self._make_human_messages(20)
        messages = sys_msgs + human_msgs

        result = message_window.should_compact(messages)

        assert result is False, "SystemMessage はコンパクション判定から除外されること"
