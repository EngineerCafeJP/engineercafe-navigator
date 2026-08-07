"""Tests for GeneralKnowledgeAgent adaptive web search."""

from unittest.mock import MagicMock, patch

from backend.utils.context_priority import ContextSignals


def _make_agent():
    """Create a GeneralKnowledgeAgent with mocked dependencies."""
    with (
        patch("backend.agents.general_knowledge_agent.resolve_llm_provider"),
        patch("backend.agents.general_knowledge_agent.get_model_config"),
        patch("backend.agents.general_knowledge_agent.TavilySearchTool"),
        patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch"),
    ):
        from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

        return GeneralKnowledgeAgent()


class TestAdaptiveWebSearch:
    def test_high_rag_high_specificity_no_web(self):
        """RAGスコア高い + 具体性高い → Web検索不要"""
        agent = _make_agent()
        signals = ContextSignals(
            rag_cache_top_score=0.9,
            request_specificity=0.8,
            conversation_depth=5,
        )
        result = agent._should_use_web_search_adaptive("エンジニアカフェの営業時間", signals)
        assert result is False

    def test_low_rag_shallow_conversation_requires_current_info_marker(self):
        """RAGスコア低い + 会話浅いだけでは Web検索しない"""
        agent = _make_agent()
        signals = ContextSignals(
            rag_cache_top_score=0.3,
            request_specificity=0.5,
            conversation_depth=1,
        )
        result = agent._should_use_web_search_adaptive("AIとは何ですか", signals)
        assert result is False

        current_result = agent._should_use_web_search_adaptive("最新のAIニュース", signals)
        assert current_result is True

    def test_none_signals_fallback(self):
        """context_signals=None → 静的判定にフォールバック"""
        agent = _make_agent()
        agent._should_use_web_search = MagicMock(return_value=True)

        result = agent._should_use_web_search_adaptive("some query", None)

        agent._should_use_web_search.assert_called_once_with("some query")
        assert result is True

    def test_medium_signals_static_fallback(self):
        """中間シグナル → 静的ヒューリスティックにフォールバック"""
        agent = _make_agent()
        agent._should_use_web_search = MagicMock(return_value=False)

        signals = ContextSignals(
            rag_cache_top_score=0.6,
            request_specificity=0.5,
            conversation_depth=5,
        )
        result = agent._should_use_web_search_adaptive("何かの質問", signals)

        agent._should_use_web_search.assert_called_once_with("何かの質問")
        assert result is False
