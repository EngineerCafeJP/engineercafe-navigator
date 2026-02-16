"""Context-Driven Priority Engine テスト"""

import pytest

from backend.utils.context_priority import (
    MAX_ADJUSTMENT,
    ContextPriorityEngine,
    ContextSignals,
)

# =============================================================================
# ContextSignals tests
# =============================================================================


class TestContextSignals:
    """ContextSignals frozen dataclass のテスト"""

    def test_default_creation(self):
        signals = ContextSignals()
        assert signals.memory_topics == ()
        assert signals.rag_cache_top_score == 0.0
        assert signals.request_specificity == 0.5
        assert signals.conversation_depth == 0
        assert signals.previous_categories == ()

    def test_custom_creation(self):
        signals = ContextSignals(
            memory_topics=("hours", "pricing"),
            rag_cache_top_score=0.85,
            request_specificity=0.9,
            conversation_depth=5,
            previous_categories=("hours", "general"),
        )
        assert signals.memory_topics == ("hours", "pricing")
        assert signals.rag_cache_top_score == 0.85
        assert signals.request_specificity == 0.9
        assert signals.conversation_depth == 5
        assert signals.previous_categories == ("hours", "general")

    def test_frozen_immutability(self):
        signals = ContextSignals()
        with pytest.raises(AttributeError):
            signals.conversation_depth = 10  # type: ignore[misc]


# =============================================================================
# compute_adjusted_thresholds tests
# =============================================================================


class TestComputeAdjustedThresholds:
    """閾値調整ロジックのテスト"""

    @pytest.fixture()
    def engine(self):
        return ContextPriorityEngine()

    @pytest.fixture()
    def base_thresholds(self):
        return {"high": 0.75, "medium": 0.55, "term_match": 0.25}

    def test_topic_consistency_lowers_thresholds(self, engine, base_thresholds):
        """トピック一貫性が高い場合、high/mediumが-0.03される"""
        signals = ContextSignals(
            previous_categories=("hours",),
            conversation_depth=5,
        )
        result = engine.compute_adjusted_thresholds(
            category="hours",
            query="営業時間は？",
            signals=signals,
            base_thresholds=base_thresholds,
        )
        assert result["high"] == pytest.approx(0.75 - 0.03)
        assert result["medium"] == pytest.approx(0.55 - 0.03)
        assert result["term_match"] == pytest.approx(0.25)

    def test_high_rag_cache_raises_thresholds(self, engine, base_thresholds):
        """RAGキャッシュスコアが高い場合、high/mediumが+0.05される"""
        signals = ContextSignals(
            rag_cache_top_score=0.85,
            conversation_depth=5,
        )
        result = engine.compute_adjusted_thresholds(
            category="general",
            query="テスト",
            signals=signals,
            base_thresholds=base_thresholds,
        )
        assert result["high"] == pytest.approx(0.75 + 0.05)
        assert result["medium"] == pytest.approx(0.55 + 0.05)

    def test_high_specificity_raises_medium(self, engine, base_thresholds):
        """リクエスト具体性が高い場合、mediumが+0.03される"""
        signals = ContextSignals(
            request_specificity=0.9,
            conversation_depth=5,
        )
        result = engine.compute_adjusted_thresholds(
            category="general",
            query="テスト",
            signals=signals,
            base_thresholds=base_thresholds,
        )
        assert result["high"] == pytest.approx(0.75)
        assert result["medium"] == pytest.approx(0.55 + 0.03)

    def test_low_conversation_depth_no_change(self, engine, base_thresholds):
        """会話深度が浅い場合、変更なし"""
        signals = ContextSignals(
            conversation_depth=1,
        )
        result = engine.compute_adjusted_thresholds(
            category="general",
            query="テスト",
            signals=signals,
            base_thresholds=base_thresholds,
        )
        assert result["high"] == pytest.approx(0.75)
        assert result["medium"] == pytest.approx(0.55)
        assert result["term_match"] == pytest.approx(0.25)

    def test_combined_adjustments(self, engine, base_thresholds):
        """複合シグナル: topic consistency(-0.03) + high rag(+0.05)"""
        signals = ContextSignals(
            previous_categories=("hours",),
            rag_cache_top_score=0.9,
            conversation_depth=5,
        )
        result = engine.compute_adjusted_thresholds(
            category="hours",
            query="何時まで？",
            signals=signals,
            base_thresholds=base_thresholds,
        )
        # high: -0.03 + 0.05 = +0.02
        assert result["high"] == pytest.approx(0.75 + 0.02)
        # medium: -0.03 + 0.05 = +0.02
        assert result["medium"] == pytest.approx(0.55 + 0.02)

    def test_clamp_max_adjustment(self, engine):
        """調整値がMAX_ADJUSTMENTを超えないこと"""
        result = engine._clamp_adjustment(0.20)
        assert result == MAX_ADJUSTMENT

    def test_clamp_min_adjustment(self, engine):
        """調整値が-MAX_ADJUSTMENTを下回らないこと"""
        result = engine._clamp_adjustment(-0.20)
        assert result == -MAX_ADJUSTMENT

    def test_clamp_within_range(self, engine):
        """範囲内の調整値はそのまま"""
        assert engine._clamp_adjustment(0.05) == 0.05
        assert engine._clamp_adjustment(-0.03) == -0.03

    def test_does_not_mutate_base_thresholds(self, engine):
        """元のbase_thresholdsがミューテーションされないこと"""
        base = {"high": 0.75, "medium": 0.55, "term_match": 0.25}
        original_high = base["high"]
        signals = ContextSignals(rag_cache_top_score=0.9, conversation_depth=5)
        engine.compute_adjusted_thresholds(
            category="general",
            query="test",
            signals=signals,
            base_thresholds=base,
        )
        assert base["high"] == original_high

    def test_no_category_match_no_topic_adjustment(self, engine, base_thresholds):
        """カテゴリがprevious_categoriesに含まれない場合、topic調整なし"""
        signals = ContextSignals(
            previous_categories=("hours", "pricing"),
            conversation_depth=5,
        )
        result = engine.compute_adjusted_thresholds(
            category="event",
            query="イベント情報",
            signals=signals,
            base_thresholds=base_thresholds,
        )
        assert result["high"] == pytest.approx(0.75)


# =============================================================================
# extract_signals_from_context tests
# =============================================================================


class TestExtractSignalsFromContext:
    """シグナル抽出のテスト"""

    @pytest.fixture()
    def engine(self):
        return ContextPriorityEngine()

    def test_with_full_memory_context(self, engine):
        memory_context = {
            "conversation_history": [{"role": "user"}, {"role": "assistant"}],
            "topics": ["hours", "pricing"],
            "previous_categories": ["hours"],
        }
        knowledge_results = {
            "results": [
                {"priority_score": 0.85, "title": "test"},
                {"priority_score": 0.70, "title": "test2"},
            ],
            "category": "hours",
            "query": "エンジニアカフェの営業時間を教えてください",
        }
        signals = engine.extract_signals_from_context(memory_context, knowledge_results)

        assert signals.conversation_depth == 2
        assert "hours" in signals.memory_topics
        assert signals.rag_cache_top_score == pytest.approx(0.85)
        assert "hours" in signals.previous_categories

    def test_with_none_inputs(self, engine):
        signals = engine.extract_signals_from_context(None, None)
        assert signals.conversation_depth == 0
        assert signals.memory_topics == ()
        assert signals.rag_cache_top_score == 0.0
        assert signals.request_specificity == 0.0

    def test_with_empty_dicts(self, engine):
        signals = engine.extract_signals_from_context({}, {})
        assert signals.conversation_depth == 0
        assert signals.rag_cache_top_score == 0.0

    def test_rag_category_added_to_previous(self, engine):
        """RAGカテゴリがprevious_categoriesに追加されること"""
        knowledge_results = {
            "results": [{"priority_score": 0.7}],
            "category": "pricing",
            "query": "料金",
        }
        signals = engine.extract_signals_from_context(None, knowledge_results)
        assert "pricing" in signals.previous_categories


# =============================================================================
# _compute_specificity tests
# =============================================================================


class TestComputeSpecificity:
    """クエリ具体性計算のテスト"""

    @pytest.fixture()
    def engine(self):
        return ContextPriorityEngine()

    def test_empty_query(self, engine):
        assert engine._compute_specificity("") == 0.0

    def test_short_query_low_specificity(self, engine):
        score = engine._compute_specificity("時間")
        assert score < 0.5

    def test_long_query_higher_specificity(self, engine):
        score = engine._compute_specificity(
            "エンジニアカフェの営業時間について詳しく教えてください"
        )
        assert score > 0.5

    def test_proper_noun_increases_specificity(self, engine):
        with_noun = engine._compute_specificity("エンジニアカフェの料金はいくらですか")
        without_noun = engine._compute_specificity("この施設の料金はいくらですか")
        assert with_noun > without_noun

    def test_numeric_increases_specificity(self, engine):
        with_num = engine._compute_specificity("3階の会議室の予約方法")
        without_num = engine._compute_specificity("会議室の予約方法を教えて")
        assert with_num > without_num

    def test_score_clamped_to_range(self, engine):
        score = engine._compute_specificity(
            "エンジニアカフェのsaino福岡天神で3階の会議室を12月25日に予約したい"
        )
        assert 0.0 <= score <= 1.0


# =============================================================================
# Integration: full flow
# =============================================================================


class TestIntegrationFlow:
    """シグナル抽出 -> 閾値調整の統合テスト"""

    def test_full_flow(self):
        engine = ContextPriorityEngine()

        memory_context = {
            "conversation_history": [
                {"role": "user", "content": "営業時間は？"},
                {"role": "assistant", "content": "9:00-22:00です"},
                {"role": "user", "content": "料金は？"},
                {"role": "assistant", "content": "無料です"},
            ],
            "topics": ["hours"],
            "previous_categories": ["hours"],
        }
        knowledge_results = {
            "results": [{"priority_score": 0.82}],
            "category": "hours",
            "query": "エンジニアカフェは何時まで開いてますか",
        }

        signals = engine.extract_signals_from_context(memory_context, knowledge_results)

        base_thresholds = {"high": 0.75, "medium": 0.55, "term_match": 0.25}
        adjusted = engine.compute_adjusted_thresholds(
            category="hours",
            query="何時まで開いてますか",
            signals=signals,
            base_thresholds=base_thresholds,
        )

        # topic consistency(-0.03) + high rag(+0.05) = +0.02
        assert adjusted["high"] == pytest.approx(0.75 + 0.02)
        # topic(-0.03) + rag(+0.05) + specificity depends on score
        assert adjusted["medium"] != base_thresholds["medium"]
