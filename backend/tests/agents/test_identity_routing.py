"""
Tests for the identity-intent fast-path that prevents the GeneralKnowledgeAgent
from leaking LLM-provider self-disclosure (e.g. "I am trained by Google...")
when visitors ask "what's your name" / "who are you" in any supported language.

See issue #615.

Coverage:
- Fast-path detection in ja/en/ko/zh (multilingual identity + capability queries)
- _assistant_profile_response returns hardcoded "エンナビ" text
  in all four languages, never calls web_search or any LLM provider
- Visitor self-introduction ("私の名前は田中です") is NOT misrouted
- Returned metadata has web_search_used=False and provider_called=False
- No supported language returns a response containing any LLM-provider name
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
from backend.utils.intent_classifier import (
    classify_fast_intent,
    is_assistant_profile_question,
)

# Identity-style queries that MUST route to the assistant_profile fast-path.
IDENTITY_QUERIES = {
    "ja": [
        "あなたの名前は？",
        "お名前を教えてください",
        "あなたは誰ですか",
        "何者ですか",
        "自己紹介してください",
        "あなたに相談できることは？",
        "どんなAIなの？",
        "どのモデルを使ってる？",
    ],
    "en": [
        "what's your name?",
        "what is your name",
        "who are you?",
        "what model are you?",
        "are you trained by openai?",
        "introduce yourself",
        "which AI is this",
    ],
    "ko": [
        "당신의 이름은 무엇입니까",
        "너 이름이 뭐야",
        "누구세요?",
        "자기소개 해주세요",
    ],
    "zh": [
        "你叫什么名字",
        "你是谁",
        "你的名字是什么",
        "请自我介绍",
        "您是谁",
    ],
}

# These must NOT trigger the identity fast-path — they're visitor self-intros.
VISITOR_NAME_QUERIES = [
    "私の名前は田中です。覚えて",
    "my name is alice",
    "call me Bob",
    "내 이름은 김철수입니다",
    "我的名字叫小明",
    "我叫李华",
]

# These must NOT trigger the identity fast-path — they're domain queries that
# happen to contain ambiguous tokens (貴方 as 2nd-person pronoun, "AI" as a
# topic label, Chinese 能帮我 as a generic capability ask).
# Per Codex CLI 経路A review on PR #648 (#615 follow-up).
NON_IDENTITY_AMBIGUOUS_QUERIES = [
    # 貴方 used as 2nd-person pronoun in a Wi-Fi question (not asking about bot)
    "貴方にWi-Fiの設定を聞きたい",
    # "できること" as a consultation domain phrase, not assistant capability.
    "コミュニティマネージャーに相談できることは？",
    # "AI" as topic of an event lookup, not asking which AI the bot is
    "which AI events are held here?",
    # Chinese capability marker without self-referential identity token
    "能帮我连接 Wi-Fi 吗",
]

# LLM-provider tokens that must NEVER appear in a hardcoded identity response.
FORBIDDEN_PROVIDER_TOKENS = (
    "google",
    "gemini",
    "openai",
    "gpt",
    "anthropic",
    "claude",
    "trained by",
)


class TestIdentityIntentDetection:
    """is_assistant_profile_question must catch identity queries in ja/en/ko/zh."""

    @pytest.mark.parametrize("language", ["ja", "en", "ko", "zh"])
    def test_identity_queries_detected(self, language: str) -> None:
        for query in IDENTITY_QUERIES[language]:
            assert is_assistant_profile_question(
                query.lower()
            ), f"[{language}] identity query not detected: {query!r}"

    @pytest.mark.parametrize("query", VISITOR_NAME_QUERIES)
    def test_visitor_self_introduction_not_misrouted(self, query: str) -> None:
        assert not is_assistant_profile_question(
            query.lower()
        ), f"visitor self-intro misrouted to assistant_profile: {query!r}"

    @pytest.mark.parametrize("query", NON_IDENTITY_AMBIGUOUS_QUERIES)
    def test_ambiguous_tokens_do_not_misroute(self, query: str) -> None:
        """Regression: PR #648 false positives from Codex CLI 経路A review.

        - 貴方 alone (used as 2nd-person pronoun, not identity subject)
        - bare 'AI' substring inside an event query
        - bare Chinese 能 capability marker inside a Wi-Fi help request

        These must NOT route to the assistant_profile fast-path.
        """
        assert not is_assistant_profile_question(
            query.lower()
        ), f"ambiguous-token query misrouted to assistant_profile: {query!r}"

        # Also verify they don't get a fast assistant_profile route from the
        # higher-level classifier (defense in depth — the orchestrator path).
        route = classify_fast_intent(query)
        if route is not None:
            assert route.request_type != "assistant_profile", (
                f"classify_fast_intent misrouted ambiguous query to "
                f"assistant_profile: {query!r}"
            )


class TestIdentityFastRoute:
    """classify_fast_intent must return an assistant_profile route, not None."""

    @pytest.mark.parametrize("language", ["ja", "en", "ko", "zh"])
    def test_fast_intent_routes_assistant_profile(self, language: str) -> None:
        for query in IDENTITY_QUERIES[language]:
            route = classify_fast_intent(query)
            assert route is not None, f"[{language}] no fast route for {query!r}"
            assert route.agent == "general_knowledge", (
                f"[{language}] expected general_knowledge agent, got {route.agent!r} "
                f"for query {query!r}"
            )
            assert route.request_type == "assistant_profile", (
                f"[{language}] expected request_type=assistant_profile, "
                f"got {route.request_type!r} for query {query!r}"
            )
            assert route.category == "assistant_profile"


class TestAssistantProfileResponse:
    """_assistant_profile_response must NOT call web_search/LLM in any language."""

    @pytest.fixture
    def gka(self) -> GeneralKnowledgeAgent:
        # Patch heavyweight constructors so we don't hit external services.
        with (
            patch("backend.agents.general_knowledge_agent.OpenRouterProvider") as mock_provider,
            patch("backend.agents.general_knowledge_agent.TavilySearchTool") as mock_tavily,
            patch("backend.agents.general_knowledge_agent.EnhancedRAGSearch") as mock_rag,
            patch("backend.agents.general_knowledge_agent.get_model_config"),
        ):
            mock_provider.return_value.generate = AsyncMock(
                side_effect=AssertionError("LLM must not be called for identity")
            )
            mock_tavily.return_value.search = AsyncMock(
                side_effect=AssertionError("web_search must not be called for identity")
            )
            mock_rag.return_value.search = AsyncMock(
                side_effect=AssertionError("RAG must not be called for identity")
            )
            agent = GeneralKnowledgeAgent(memory_system=MagicMock())
            # Re-attach the mocks to the agent instance for assertion access.
            agent.provider = mock_provider.return_value
            agent.web_search = mock_tavily.return_value
            agent.rag_search = mock_rag.return_value
            return agent

    @pytest.mark.parametrize("language", ["ja", "en", "ko", "zh"])
    @pytest.mark.asyncio
    async def test_answer_query_assistant_profile_never_invokes_llm_or_web(
        self, gka: GeneralKnowledgeAgent, language: str
    ) -> None:
        result = await gka.answer_query(
            query=IDENTITY_QUERIES[language][0],
            language=language,
            session_id="test-session",
            query_type="assistant_profile",
        )

        # Hardcoded name string MUST appear, localized by language.
        assert any(
            name in result["answer"] for name in ("エンナビ", "EnNavi", "엔나비")
        ), f"[{language}] response missing fixed name: {result['answer']!r}"

        # Provider/web_search must not have been touched.
        gka.provider.generate.assert_not_called()
        gka.web_search.search.assert_not_called()
        gka.rag_search.search.assert_not_called()

        meta = result["metadata"]
        assert meta["query_type"] == "assistant_profile"
        assert meta["web_search_used"] is False
        assert meta["provider_called"] is False
        assert meta["sources"] == []

    @pytest.mark.parametrize("language", ["ja", "en", "ko", "zh"])
    def test_response_contains_no_llm_provider_disclosure(
        self, gka: GeneralKnowledgeAgent, language: str
    ) -> None:
        result = gka._assistant_profile_response(language)  # type: ignore[arg-type]
        answer_lower = result["answer"].lower()
        for token in FORBIDDEN_PROVIDER_TOKENS:
            assert token not in answer_lower, (
                f"[{language}] forbidden provider token {token!r} leaked in "
                f"response: {result['answer']!r}"
            )

    def test_unknown_language_falls_back_to_japanese(self, gka: GeneralKnowledgeAgent) -> None:
        # SupportedLanguage is Literal["ja","en","zh","ko"]; passing an unknown
        # value is a defensive guard. We expect the ja fallback string.
        result = gka._assistant_profile_response("xx")  # type: ignore[arg-type]
        assert "エンナビ" in result["answer"]
        assert result["metadata"]["web_search_used"] is False
