"""
Conversation Flow Scenario Tests - Multi-turn conversations through MainWorkflow

LangGraph の MemorySaver (in-memory checkpointer) を使用し、
複数ターンの会話フローが正しくルーティング・コンテキスト継承されることを検証する。

全ての外部依存 (LLM, Supabase, RAG) はモックし、
グラフのルーティングとノード遷移のみを統合テストする。

Scenarios:
  Flow 1: Business -> Facility (context inheritance across turns)
  Flow 2: Slide narration -> Slide question (action switching)
  Flow 3: Ambiguous -> Clarification -> Correct routing
  Flow 4: English query -> Language detection -> English response
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from backend.agents.orchestrator_agent import OrchestratorDecision


# ---------------------------------------------------------------------------
# Shared fixtures & helpers (same pattern as test_multi_agent_scenarios.py)
# ---------------------------------------------------------------------------


def _make_memory_helper_mock(context_return=None):
    """SimplifiedMemoryHelper のモックを作成する共通ヘルパー

    Args:
        context_return: get_context の戻り値をカスタマイズする場合に指定。
                        None の場合はデフォルトの空コンテキストを返す。
    """
    helper = AsyncMock()
    if context_return is None:
        context_return = {
            "recent_messages": [],
            "context_string": "",
        }
    helper.get_context = AsyncMock(return_value=context_return)
    helper.store_message = AsyncMock()
    return helper


def _make_rag_mock():
    """EnhancedRAGSearch のモックを作成する共通ヘルパー"""
    rag = AsyncMock()
    rag.search = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "results": [],
                "context": "",
            },
        }
    )
    return rag


def _make_classifier_mock(category="general"):
    """QueryClassifier のモックを作成する共通ヘルパー

    NOTE: classify_with_details の戻り値は plain object を使う。
    MagicMock は MemorySaver の msgpack シリアライゼーションに失敗するため。
    """

    class _Classification:
        def __init__(self, cat):
            self.category = cat

    classification = _Classification(category)
    classifier = MagicMock()
    classifier.classify_with_details = AsyncMock(return_value=classification)
    return classifier


def _make_context_priority_mock():
    """ContextPriorityEngine のモックを作成する共通ヘルパー

    extract_signals_from_context() が plain dict を返すように設定する。
    MagicMock を返すと MemorySaver の msgpack serialization で失敗する。
    """
    mock_engine = MagicMock()
    mock_engine.extract_signals_from_context.return_value = {
        "has_memory": False,
        "has_knowledge": False,
    }
    return mock_engine


@contextmanager
def _patch_memory_loader_deps(category="general"):
    """memory_loader_node 内でインポートされる依存のパッチ一式

    EnhancedRAGSearch, QueryClassifier, ContextPriorityEngine を
    全て serializable な値を返すモックに差し替える。
    """
    with (
        patch(
            "backend.tools.enhanced_rag.EnhancedRAGSearch",
            return_value=_make_rag_mock(),
        ),
        patch(
            "backend.utils.query_classifier.QueryClassifier",
            return_value=_make_classifier_mock(category),
        ),
        patch(
            "backend.utils.context_priority.ContextPriorityEngine",
            return_value=_make_context_priority_mock(),
        ),
    ):
        yield


def _build_decision(
    next_agent,
    language="ja",
    category="general",
    request_type="general",
    confidence=0.9,
    reasoning="test routing",
):
    """OrchestratorDecision を簡潔に生成するヘルパー"""
    return OrchestratorDecision(
        next_agent=next_agent,
        language=language,
        category=category,
        request_type=request_type,
        confidence=confidence,
        reasoning=reasoning,
        debug_info={},
    )


# ===========================================================================
# Flow 1: Business -> Facility Context Inheritance
# ===========================================================================


class TestBusinessToFacilityContextInheritance:
    """
    会話フロー: 営業時間の質問 -> 同一セッションで施設の質問

    同一 session_id を使った2ターン会話で:
    1. "営業時間は？" -> business_info agent にルーティング
    2. "会議室借りたい" -> facility agent にルーティング
    3. 2回目の呼び出しで orchestrator が memory_context を受け取ることを検証
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_two_turn_business_then_facility_same_session(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """2ターン会話: business_info -> facility, 同一session_idで実行"""
        from backend.workflows.main_workflow import MainWorkflow

        # -- Arrange: Track orchestrator calls for per-turn routing --
        turn_count = 0
        captured_memory_contexts = []

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            nonlocal turn_count
            turn_count += 1
            captured_memory_contexts.append(memory_context)

            if turn_count == 1:
                return _build_decision(
                    next_agent="business_info",
                    category="business-hours",
                    request_type="hours",
                    reasoning="Business hours keyword detected",
                )
            return _build_decision(
                next_agent="facility",
                category="facility-meeting-room",
                request_type="meeting_room",
                reasoning="Meeting room request detected",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        # -- Arrange: Memory helper with progressive context --
        # Turn 1: empty context, Turn 2: includes previous conversation
        turn1_context = {
            "recent_messages": [],
            "context_string": "",
        }
        turn2_context = {
            "recent_messages": [
                {"role": "user", "content": "営業時間は？"},
                {"role": "assistant", "content": "営業時間は9時から22時までです。"},
            ],
            "context_string": "ユーザー: 営業時間は？\nアシスタント: 営業時間は9時から22時までです。",
        }

        call_count_ctx = {"n": 0}

        async def progressive_get_context(query, session_id, options=None):
            call_count_ctx["n"] += 1
            if call_count_ctx["n"] == 1:
                return turn1_context
            return turn2_context

        mock_helper = AsyncMock()
        mock_helper.get_context = AsyncMock(side_effect=progressive_get_context)
        mock_helper.store_message = AsyncMock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()
        session_id = "flow1-biz-to-facility"

        with _patch_memory_loader_deps(category="business-hours"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                return_value={
                    "answer": "営業時間は9時から22時までです。",
                    "emotion": "happy",
                    "metadata": {"agent": "BusinessInfoAgent"},
                }
            )
            workflow._facility_agent.answer_facility_query = AsyncMock(
                return_value={
                    "answer": "地下1階にMTGスペースがあります。予約優先です。",
                    "emotion": "neutral",
                    "metadata": {"agent": "FacilityAgent"},
                }
            )

            # -- Act: Turn 1 --
            result1 = await workflow.ainvoke(
                {
                    "query": "営業時間は？",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

            # -- Act: Turn 2 --
            result2 = await workflow.ainvoke(
                {
                    "query": "会議室借りたい",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

        # -- Assert: Turn 1 routed to business_info --
        assert result1["answer"] == "営業時間は9時から22時までです。"
        assert result1["emotion"] == "happy"
        workflow._business_info_agent.answer_business_query.assert_called_once()

        # -- Assert: Turn 2 routed to facility --
        assert result2["answer"] == "地下1階にMTGスペースがあります。予約優先です。"
        assert result2["emotion"] == "neutral"
        workflow._facility_agent.answer_facility_query.assert_called_once()

        # -- Assert: Both used same session_id --
        assert turn_count == 2
        for call in mock_orchestrator.decide_next_agent.call_args_list:
            assert call.kwargs["session_id"] == session_id

        # -- Assert: Second call received memory_context with previous conversation --
        second_memory = captured_memory_contexts[1]
        assert second_memory is not None
        assert "recent_messages" in second_memory
        assert len(second_memory["recent_messages"]) == 2
        assert second_memory["recent_messages"][0]["content"] == "営業時間は？"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_different_sessions_do_not_share_memory_context(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """異なる session_id は独立したメモリコンテキストを持つ"""
        from backend.workflows.main_workflow import MainWorkflow

        captured_sessions = []

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            captured_sessions.append(session_id)
            return _build_decision(
                next_agent="business_info",
                category="business-hours",
                request_type="hours",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps(category="business-hours"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                return_value={
                    "answer": "9時から22時です。",
                    "emotion": "neutral",
                    "metadata": {},
                }
            )

            # Two calls with different session_ids
            await workflow.ainvoke(
                {"query": "営業時間は？", "session_id": "session-A", "language": "ja"}
            )
            await workflow.ainvoke(
                {"query": "営業時間は？", "session_id": "session-B", "language": "ja"}
            )

        # Verify different session_ids were passed
        assert captured_sessions == ["session-A", "session-B"]

        # Memory helper get_context was called with respective session_ids
        ctx_calls = mock_helper.get_context.call_args_list
        assert ctx_calls[0].kwargs["session_id"] == "session-A"
        assert ctx_calls[1].kwargs["session_id"] == "session-B"


# ===========================================================================
# Flow 2: Slide Narration -> Slide Question
# ===========================================================================


class TestSlideNarrationToQuestion:
    """
    会話フロー: スライドナレーション要求 -> スライド内容への質問

    同一セッションで:
    1. "スライド見せて" -> slide agent (narrate action)
    2. "3枚目は何？" -> slide agent (question action)
    3. SlideAgent が適切な action (narrate vs question) で呼ばれることを検証
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_narrate_then_question_actions(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """スライドナレーション -> スライド質問, アクションが正しく切り替わる"""
        from backend.workflows.main_workflow import MainWorkflow

        turn_count = 0

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            nonlocal turn_count
            turn_count += 1
            if turn_count == 1:
                return _build_decision(
                    next_agent="slide",
                    category="slide-narration",
                    request_type="narrate",
                    reasoning="Slide presentation request",
                )
            return _build_decision(
                next_agent="slide",
                category="slide-question",
                request_type="question",
                reasoning="Question about slide content",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()
        session_id = "flow2-slide-narrate-question"

        captured_slide_calls = []

        async def mock_slide_action(action, query=None, language="ja", session_id="default"):
            captured_slide_calls.append(
                {"action": action, "query": query, "session_id": session_id}
            )
            if action == "narrate":
                return {
                    "answer": "エンジニアカフェへようこそ。このスライドでは...",
                    "emotion": "happy",
                    "metadata": {"slide_number": 1, "action": "narrate"},
                }
            return {
                "answer": "3枚目のスライドは施設案内についてです。",
                "emotion": "neutral",
                "metadata": {"slide_number": 3, "action": "question"},
            }

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._slide_agent.handle_slide_action = AsyncMock(side_effect=mock_slide_action)

            # Turn 1: narrate
            result1 = await workflow.ainvoke(
                {
                    "query": "スライド見せて",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

            # Turn 2: question
            result2 = await workflow.ainvoke(
                {
                    "query": "3枚目は何？",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

        # -- Assert: Turn 1 used narrate action --
        assert result1["answer"] == "エンジニアカフェへようこそ。このスライドでは..."
        assert captured_slide_calls[0]["action"] == "narrate"
        assert captured_slide_calls[0]["query"] is None  # narrate passes None

        # -- Assert: Turn 2 used question action --
        assert result2["answer"] == "3枚目のスライドは施設案内についてです。"
        assert captured_slide_calls[1]["action"] == "question"
        assert captured_slide_calls[1]["query"] == "3枚目は何？"

        # -- Assert: Both used same session_id --
        assert captured_slide_calls[0]["session_id"] == session_id
        assert captured_slide_calls[1]["session_id"] == session_id

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_slide_goto_action(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """goto request_type でスライドジャンプが実行される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(
            return_value=_build_decision(
                next_agent="slide",
                category="slide-goto",
                request_type="goto",
                reasoning="User wants specific slide",
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        captured_action = {}

        async def mock_slide_action(action, query=None, language="ja", session_id="default"):
            captured_action["action"] = action
            captured_action["query"] = query
            return {
                "answer": "5枚目のスライドに移動しました。",
                "emotion": "neutral",
                "metadata": {"slide_number": 5, "action": "goto"},
            }

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._slide_agent.handle_slide_action = AsyncMock(side_effect=mock_slide_action)

            result = await workflow.ainvoke(
                {
                    "query": "5枚目のスライドに行って",
                    "session_id": "flow2-slide-goto",
                    "language": "ja",
                }
            )

        assert result["answer"] == "5枚目のスライドに移動しました。"
        # goto action passes query as None (not question)
        assert captured_action["action"] == "goto"
        assert captured_action["query"] is None


# ===========================================================================
# Flow 3: Ambiguous -> Clarification -> Correct Routing
# ===========================================================================


class TestAmbiguousToClarificationToCorrectRouting:
    """
    会話フロー: 曖昧な質問 -> 明確化応答 -> 正しいルーティング

    同一セッションで:
    1. "ここの使い方" (曖昧) -> clarification 応答
    2. "Wi-Fiのパスワードが知りたい" (明確) -> facility agent
    3. 最初の呼び出しで clarification が発動し、
       2回目で正しいエージェントにルーティングされることを検証
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_ambiguous_triggers_clarification_then_correct_routing(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """曖昧 -> clarification -> 次の明確な質問は facility にルーティング"""
        from backend.workflows.main_workflow import MainWorkflow

        turn_count = 0

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            nonlocal turn_count
            turn_count += 1
            if turn_count == 1:
                # Ambiguous query -> clarification
                return _build_decision(
                    next_agent="general_knowledge",
                    category="general-clarification-needed",
                    request_type="clarification",
                    confidence=0.7,
                    reasoning="Ambiguous usage reference",
                )
            # Clear query -> facility
            return _build_decision(
                next_agent="facility",
                category="facility-wifi",
                request_type="wifi",
                confidence=0.95,
                reasoning="WiFi password request",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()
        session_id = "flow3-ambiguous-clarify"

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            # Facility agent should only be called on turn 2
            workflow._facility_agent.answer_facility_query = AsyncMock(
                return_value={
                    "answer": "Wi-Fiパスワードは館内掲示をご確認ください。",
                    "emotion": "neutral",
                    "metadata": {"agent": "FacilityAgent"},
                }
            )

            # Specialist agents that should NOT be called on turn 1
            workflow._business_info_agent.answer_business_query = AsyncMock(
                side_effect=AssertionError("business_info should not be called")
            )
            workflow._general_knowledge_agent.answer_query = AsyncMock(
                side_effect=AssertionError("general_knowledge should not be called")
            )

            # Turn 1: ambiguous query -> clarification
            result1 = await workflow.ainvoke(
                {
                    "query": "ここの使い方",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

            # Turn 2: clear query -> facility
            result2 = await workflow.ainvoke(
                {
                    "query": "Wi-Fiのパスワードが知りたい",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

        # -- Assert: Turn 1 returned clarification response --
        assert "もう少し詳しく" in result1["answer"] or "お手伝い" in result1["answer"]
        assert result1["emotion"] == "surprised"
        assert result1["metadata"].get("requires_followup") is True

        # -- Assert: Turn 2 routed to facility --
        assert result2["answer"] == "Wi-Fiパスワードは館内掲示をご確認ください。"
        workflow._facility_agent.answer_facility_query.assert_called_once()

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_cafe_clarification_includes_engineer_and_saino_options(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """cafe-clarification はエンジニアカフェとサイノカフェの選択肢を含む"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(
            return_value=_build_decision(
                next_agent="general_knowledge",
                category="cafe-clarification-needed",
                request_type="clarification",
                confidence=0.9,
                reasoning="Ambiguous cafe reference",
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            result = await workflow.ainvoke(
                {
                    "query": "カフェの情報教えて",
                    "session_id": "flow3-cafe-clarify",
                    "language": "ja",
                }
            )

        # Clarification template mentions both Engineer Cafe and Saino Cafe
        assert "エンジニアカフェ" in result["answer"]
        assert "サイノカフェ" in result["answer"]
        assert result["emotion"] == "surprised"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_clarification_metadata_contains_type_and_followup_flag(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """clarification の metadata に clarification_type と requires_followup が含まれる"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(
            return_value=_build_decision(
                next_agent="general_knowledge",
                category="meeting-room-clarification-needed",
                request_type="clarification",
                confidence=0.9,
                reasoning="Ambiguous meeting room",
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            result = await workflow.ainvoke(
                {
                    "query": "会議室について",
                    "session_id": "flow3-mtg-clarify",
                    "language": "ja",
                }
            )

        assert result["metadata"]["requires_followup"] is True
        assert (
            result["metadata"]["clarification"]["clarification_type"]
            == "meeting-room-clarification-needed"
        )


# ===========================================================================
# Flow 4: English Query -> Language Detection -> English Response
# ===========================================================================


class TestEnglishQueryLanguageDetectionAndResponse:
    """
    会話フロー: 英語クエリ -> 言語検出 -> 英語応答

    1. "What are the opening hours?" -> orchestrator が language="en" を検出
    2. business_info agent が英語で応答
    3. 応答言語がクエリ言語と一致することを検証
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_english_query_detected_and_routed_with_english_language(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """英語クエリは language='en' でルーティングされる"""
        from backend.workflows.main_workflow import MainWorkflow

        captured_language = {}

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            return _build_decision(
                next_agent="business_info",
                language="en",
                category="business-hours",
                request_type="hours",
                confidence=0.95,
                reasoning="English business hours query",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        async def capture_biz_query(
            query, request_type, language, session_id, state_context=None, context_signals=None
        ):
            captured_language["language"] = language
            return {
                "answer": "Opening hours are from 9:00 to 22:00.",
                "emotion": "happy",
                "metadata": {"agent": "BusinessInfoAgent", "language": "en"},
            }

        with _patch_memory_loader_deps(category="business-hours"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                side_effect=capture_biz_query
            )

            result = await workflow.ainvoke(
                {
                    "query": "What are the opening hours?",
                    "session_id": "flow4-english",
                    "language": "en",
                }
            )

        # -- Assert: English response --
        assert result["answer"] == "Opening hours are from 9:00 to 22:00."

        # -- Assert: Language passed to agent is 'en' --
        assert captured_language["language"] == "en"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_english_clarification_returns_english_template(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """英語の clarification はテンプレートも英語で返される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(
            return_value=_build_decision(
                next_agent="general_knowledge",
                language="en",
                category="cafe-clarification-needed",
                request_type="clarification",
                confidence=0.9,
                reasoning="Ambiguous cafe in English",
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            result = await workflow.ainvoke(
                {
                    "query": "Tell me about the cafe",
                    "session_id": "flow4-english-clarify",
                    "language": "en",
                }
            )

        # English template mentions "Engineer Cafe" and "Saino Cafe"
        assert "Engineer Cafe" in result["answer"]
        assert "Saino Cafe" in result["answer"]
        assert result["emotion"] == "surprised"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_language_propagated_through_entire_flow(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """language フィールドがフロー全体で保持される"""
        from backend.workflows.main_workflow import MainWorkflow

        captured_facility_language = {}

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            return _build_decision(
                next_agent="facility",
                language="en",
                category="facility-wifi",
                request_type="wifi",
                confidence=0.95,
                reasoning="English WiFi query",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        async def capture_facility_query(
            query, request_type, language, session_id, state_context=None, context_signals=None
        ):
            captured_facility_language["language"] = language
            return {
                "answer": "The WiFi password is posted on the wall near the entrance.",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "language": "en"},
            }

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._facility_agent.answer_facility_query = AsyncMock(
                side_effect=capture_facility_query
            )

            result = await workflow.ainvoke(
                {
                    "query": "What is the WiFi password?",
                    "session_id": "flow4-english-wifi",
                    "language": "en",
                }
            )

        # Response is in English
        assert "WiFi" in result["answer"]

        # Language was passed as 'en' to the facility agent
        assert captured_facility_language["language"] == "en"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_japanese_and_english_sessions_independent(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """日本語セッションと英語セッションは独立して動作する"""
        from backend.workflows.main_workflow import MainWorkflow

        turn_count = 0
        captured_languages = []

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            nonlocal turn_count
            turn_count += 1
            lang = "ja" if turn_count == 1 else "en"
            captured_languages.append(lang)
            return _build_decision(
                next_agent="business_info",
                language=lang,
                category="business-hours",
                request_type="hours",
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        biz_answers = []

        async def mock_biz_query(
            query, request_type, language, session_id, state_context=None, context_signals=None
        ):
            if language == "ja":
                answer = "9時から22時です。"
            else:
                answer = "From 9:00 to 22:00."
            biz_answers.append(answer)
            return {
                "answer": answer,
                "emotion": "neutral",
                "metadata": {},
            }

        with _patch_memory_loader_deps(category="business-hours"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                side_effect=mock_biz_query
            )

            # Japanese session
            result_ja = await workflow.ainvoke(
                {
                    "query": "営業時間は？",
                    "session_id": "flow4-ja-session",
                    "language": "ja",
                }
            )

            # English session
            result_en = await workflow.ainvoke(
                {
                    "query": "What are the opening hours?",
                    "session_id": "flow4-en-session",
                    "language": "en",
                }
            )

        # Each session gets response in its own language
        assert result_ja["answer"] == "9時から22時です。"
        assert result_en["answer"] == "From 9:00 to 22:00."
        assert captured_languages == ["ja", "en"]
