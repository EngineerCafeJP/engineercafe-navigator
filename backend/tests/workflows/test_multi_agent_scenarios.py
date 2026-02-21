"""
Multi-Agent Scenario Tests - MainWorkflow end-to-end with mocked LLMs

LangGraph の MemorySaver (in-memory checkpointer) を使用し、
実際のグラフ実行フローを通してマルチエージェントシナリオを検証する。

全ての外部依存 (LLM, Supabase, RAG) はモックし、
グラフのルーティングとノード遷移のみを統合テストする。
"""

from contextlib import contextmanager

import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from backend.agents.orchestrator_agent import OrchestratorDecision


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_memory_helper_mock():
    """SimplifiedMemoryHelper のモックを作成する共通ヘルパー"""
    helper = AsyncMock()
    helper.get_context = AsyncMock(
        return_value={
            "recent_messages": [],
            "context_string": "",
        }
    )
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

    NOTE: classify_with_details の戻り値は MagicMock ではなく
    plain object を使う。MagicMock は MemorySaver の msgpack
    シリアライゼーションに失敗するため。
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

    extract_signals_from_context() が MagicMock を返すと
    MemorySaver の msgpack serialization で TypeError になるため、
    plain dict を返すように設定する。
    """
    mock_engine = MagicMock()
    mock_engine.extract_signals_from_context.return_value = {
        "has_memory": False,
        "has_knowledge": False,
    }
    return mock_engine


@contextmanager
def _patch_memory_loader_deps():
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
            return_value=_make_classifier_mock(),
        ),
        patch(
            "backend.utils.context_priority.ContextPriorityEngine",
            return_value=_make_context_priority_mock(),
        ),
    ):
        yield


@contextmanager
def _patch_memory_loader_deps_with_category(category):
    """memory_loader_node 内の依存パッチ（カテゴリ指定版）"""
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


# ===========================================================================
# Scenario 1: Text -> BusinessInfo
# ===========================================================================


class TestTextToBusinessInfoScenario:
    """
    テキストクエリ -> orchestrator -> business_info -> format_response

    営業時間に関するテキスト質問が、OrchestratorAgent による routing を経て
    BusinessInfoAgent で処理され、format_response で最終応答になるフローを検証。
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_text_query_routes_to_business_info_and_returns_answer(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """テキスト入力 -> memory_loader -> orchestrator -> business_info -> format_response -> END"""
        from backend.workflows.main_workflow import MainWorkflow

        # -- Arrange: OrchestratorAgent mock --
        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="business-hours",
            request_type="hours",
            confidence=0.95,
            reasoning="Business hours keyword detected",
            debug_info={"fast_path": True},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        # -- Arrange: Memory helper mock --
        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        # -- Arrange: Build workflow with MemorySaver --
        checkpointer = MemorySaver()

        with _patch_memory_loader_deps_with_category("business-hours"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            # Mock BusinessInfoAgent after workflow is constructed
            workflow._business_info_agent.answer_business_query = AsyncMock(
                return_value={
                    "answer": "営業時間は9時から22時までです。",
                    "emotion": "happy",
                    "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
                }
            )

            # -- Act --
            result = await workflow.ainvoke(
                {
                    "query": "営業時間は？",
                    "session_id": "test-biz-1",
                    "language": "ja",
                }
            )

        # -- Assert --
        assert result["answer"] == "営業時間は9時から22時までです。"
        assert result["emotion"] == "happy"

        # Orchestrator was called
        mock_orchestrator.decide_next_agent.assert_called_once()
        call_kwargs = mock_orchestrator.decide_next_agent.call_args
        assert call_kwargs.kwargs["query"] == "営業時間は？"
        assert call_kwargs.kwargs["session_id"] == "test-biz-1"

        # BusinessInfoAgent was called
        workflow._business_info_agent.answer_business_query.assert_called_once()
        biz_call = workflow._business_info_agent.answer_business_query.call_args
        assert biz_call[0][0] == "営業時間は？"  # query positional arg

        # Memory helper stored user message and assistant response
        store_calls = mock_helper.store_message.call_args_list
        assert len(store_calls) >= 2  # user + assistant
        # First call: user message
        assert store_calls[0].kwargs["role"] == "user"
        assert store_calls[0].kwargs["content"] == "営業時間は？"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_text_query_without_image_skips_vision(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """image_data が None の場合、vision ノードをスキップして memory_loader に直行する"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="business-hours",
            request_type="hours",
            confidence=0.9,
            reasoning="Business hours",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            # VisionAgent should NOT be called
            if workflow._vision_agent is not None:
                workflow._vision_agent.run = AsyncMock(
                    side_effect=AssertionError("Vision should not be called for text input")
                )

            workflow._business_info_agent.answer_business_query = AsyncMock(
                return_value={
                    "answer": "9時開店です。",
                    "emotion": "neutral",
                    "metadata": {},
                }
            )

            result = await workflow.ainvoke(
                {
                    "query": "何時に開きますか？",
                    "session_id": "test-biz-2",
                    "language": "ja",
                }
            )

        assert result["answer"] == "9時開店です。"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_routing_metadata_is_populated(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """routing dict が正しく state に格納されることを検証"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="pricing",
            request_type="price",
            confidence=0.85,
            reasoning="Pricing keyword",
            debug_info={"fast_path": True},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps_with_category("pricing"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                return_value={
                    "answer": "利用は無料です。",
                    "emotion": "happy",
                    "metadata": {},
                }
            )

            result = await workflow.ainvoke(
                {
                    "query": "料金はいくらですか？",
                    "session_id": "test-biz-3",
                    "language": "ja",
                }
            )

        assert result["answer"] == "利用は無料です。"
        # BusinessInfoAgent should receive request_type from routing
        biz_call = workflow._business_info_agent.answer_business_query.call_args
        assert biz_call[0][1] == "price"  # request_type


# ===========================================================================
# Scenario 2: Text -> Clarification (inline)
# ===========================================================================


class TestTextToClarificationScenario:
    """
    テキストクエリ -> orchestrator (clarification inline) -> format_response

    曖昧なカフェ関連クエリに対して、orchestrator_node が clarification カテゴリを
    検出し、get_clarification_response() でインラインテンプレート応答を生成して
    format_response に直接ルーティングするフローを検証。
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_cafe_clarification_returns_template_response(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """cafe-clarification-needed カテゴリでテンプレート応答が返される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="ja",
            category="cafe-clarification-needed",
            request_type="clarification",
            confidence=0.9,
            reasoning="Ambiguous cafe reference",
            debug_info={"fast_path": True},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            result = await workflow.ainvoke(
                {
                    "query": "カフェはどっちですか？",
                    "session_id": "test-clarify-1",
                    "language": "ja",
                }
            )

        # Clarification template includes Engineer Cafe and Saino Cafe references
        assert "エンジニアカフェ" in result["answer"] or "サイノカフェ" in result["answer"]
        assert result["emotion"] == "surprised"

        # Verify orchestrator was called
        mock_orchestrator.decide_next_agent.assert_called_once()

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_meeting_room_clarification(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """meeting-room-clarification-needed カテゴリでテンプレート応答が返される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="ja",
            category="meeting-room-clarification-needed",
            request_type="clarification",
            confidence=0.9,
            reasoning="Ambiguous meeting room reference",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            result = await workflow.ainvoke(
                {
                    "query": "会議室はどこですか？",
                    "session_id": "test-clarify-2",
                    "language": "ja",
                }
            )

        # Meeting room clarification mentions both 2F and B1
        assert "会議" in result["answer"] or "MTG" in result["answer"]
        assert result["emotion"] == "surprised"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_clarification_metadata_has_requires_followup(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """clarification 応答の metadata に requires_followup が含まれる"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="en",
            category="general-clarification-needed",
            request_type="clarification",
            confidence=0.7,
            reasoning="General clarification needed",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            result = await workflow.ainvoke(
                {
                    "query": "Tell me about that thing",
                    "session_id": "test-clarify-3",
                    "language": "en",
                }
            )

        assert result["metadata"].get("requires_followup") is True
        assert (
            result["metadata"]["clarification"]["clarification_type"]
            == "general-clarification-needed"
        )

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_clarification_does_not_call_specialist_agents(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """clarification フローでは specialist agent (business_info 等) は呼ばれない"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="ja",
            category="cafe-clarification-needed",
            request_type="clarification",
            confidence=0.9,
            reasoning="Ambiguous cafe",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            # Replace all specialist agents with mocks that should not be called
            workflow._business_info_agent.answer_business_query = AsyncMock(
                side_effect=AssertionError("business_info should not be called")
            )
            workflow._facility_agent.answer_facility_query = AsyncMock(
                side_effect=AssertionError("facility should not be called")
            )
            workflow._general_knowledge_agent.answer_query = AsyncMock(
                side_effect=AssertionError("general_knowledge should not be called")
            )

            result = await workflow.ainvoke(
                {
                    "query": "カフェはどっち？",
                    "session_id": "test-clarify-4",
                    "language": "ja",
                }
            )

        # Flow completed without hitting any specialist agent
        assert result["answer"] is not None
        assert result["emotion"] == "surprised"


# ===========================================================================
# Scenario 3: Image -> Vision -> GeneralKnowledge
# ===========================================================================


class TestImageToVisionToGKScenario:
    """
    画像入力 -> vision -> memory_loader -> orchestrator -> general_knowledge

    カメラからの画像入力がまず VisionAgent (OCR/表情認識) で処理され、
    OCR テキストが query に変換された後、通常のフローで orchestrator ->
    general_knowledge -> format_response に到達するフローを検証。
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_image_input_goes_through_vision_then_gka(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """画像入力 -> vision -> memory_loader -> orchestrator -> general_knowledge -> format_response"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="ja",
            category="general",
            request_type="general",
            confidence=0.8,
            reasoning="General knowledge question from OCR text",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with (
            _patch_memory_loader_deps(),
            patch("backend.utils.language_processor.LanguageProcessor") as mock_lp_class,
        ):
            # LanguageProcessor mock for vision node
            mock_lp_instance = MagicMock()
            mock_lp_instance.detect_language.return_value = {
                "detected": "ja",
                "confidence": 0.95,
            }
            mock_lp_class.return_value = mock_lp_instance

            workflow = MainWorkflow(checkpointer=checkpointer)

            # Mock VisionAgent.run
            mock_vision_result = {
                "text": {"success": True, "text": "Pythonとは何ですか"},
                "face": {
                    "success": True,
                    "detected": True,
                    "expression": {"emotion": "neutral"},
                    "error": None,
                },
            }
            workflow._vision_agent = AsyncMock()
            workflow._vision_agent.run = AsyncMock(return_value=mock_vision_result)

            # Mock GKA
            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "Pythonは汎用プログラミング言語です。",
                    "emotion": "neutral",
                    "metadata": {"agent": "GeneralKnowledgeAgent"},
                }
            )

            # Create a small dummy image
            dummy_image = np.zeros((100, 100, 3), dtype=np.uint8)

            result = await workflow.ainvoke(
                {
                    "query": "",
                    "session_id": "test-vision-1",
                    "language": "ja",
                    "image_data": dummy_image,
                }
            )

        # Verify answer comes from GKA
        assert result["answer"] == "Pythonは汎用プログラミング言語です。"
        assert result["emotion"] == "neutral"

        # Vision agent was called with the image
        workflow._vision_agent.run.assert_called_once()
        vision_call_input = workflow._vision_agent.run.call_args[0][0]
        assert np.array_equal(vision_call_input["image"], dummy_image)

        # GKA was called
        workflow._general_knowledge_agent.answer_query.assert_called_once()

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_vision_ocr_text_becomes_query(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """VisionAgent の OCR テキストが orchestrator の query として渡される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="en",
            category="general",
            request_type="general",
            confidence=0.8,
            reasoning="General",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with (
            _patch_memory_loader_deps(),
            patch("backend.utils.language_processor.LanguageProcessor") as mock_lp_class,
        ):
            mock_lp_instance = MagicMock()
            mock_lp_instance.detect_language.return_value = {
                "detected": "en",
                "confidence": 0.9,
            }
            mock_lp_class.return_value = mock_lp_instance

            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._vision_agent = AsyncMock()
            workflow._vision_agent.run = AsyncMock(
                return_value={
                    "text": {"success": True, "text": "What is WiFi password?"},
                    "face": {"success": False, "detected": False, "expression": {}, "error": None},
                }
            )

            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "The WiFi password is posted on the wall.",
                    "emotion": "neutral",
                    "metadata": {},
                }
            )

            dummy_image = np.zeros((50, 50, 3), dtype=np.uint8)

            await workflow.ainvoke(
                {
                    "query": "",
                    "session_id": "test-vision-2",
                    "language": "ja",
                    "image_data": dummy_image,
                }
            )

        # The OCR text should have been used as the query for orchestrator
        orch_call = mock_orchestrator.decide_next_agent.call_args
        assert orch_call.kwargs["query"] == "What is WiFi password?"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_vision_detected_expression_in_metadata(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """VisionAgent で検出された表情が metadata に格納される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="ja",
            category="general",
            request_type="general",
            confidence=0.8,
            reasoning="General",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with (
            _patch_memory_loader_deps(),
            patch("backend.utils.language_processor.LanguageProcessor") as mock_lp_class,
        ):
            mock_lp_instance = MagicMock()
            mock_lp_instance.detect_language.return_value = {
                "detected": "ja",
                "confidence": 1.0,
            }
            mock_lp_class.return_value = mock_lp_instance

            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._vision_agent = AsyncMock()
            workflow._vision_agent.run = AsyncMock(
                return_value={
                    "text": {"success": True, "text": "こんにちは"},
                    "face": {
                        "success": True,
                        "detected": True,
                        "expression": {"emotion": "happy"},
                        "error": None,
                    },
                }
            )

            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "こんにちは！",
                    "emotion": "happy",
                    "metadata": {},
                }
            )

            dummy_image = np.zeros((50, 50, 3), dtype=np.uint8)

            result = await workflow.ainvoke(
                {
                    "query": "",
                    "session_id": "test-vision-3",
                    "language": "ja",
                    "image_data": dummy_image,
                }
            )

        # metadata should include detected_expression from vision
        assert result["metadata"].get("detected_expression") == "happy"


# ===========================================================================
# Scenario 4: Memory Context Influence
# ===========================================================================


class TestMemoryContextScenario:
    """
    メモリコンテキスト -> orchestrator が前回コンテキストで判断

    事前にメモリコンテキストを設定し、orchestrator が memory_context を
    受け取ってルーティング判断に利用することを検証。
    """

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_orchestrator_receives_memory_context(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """orchestrator の decide_next_agent に memory_context が渡される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="business-hours",
            request_type="hours",
            confidence=0.95,
            reasoning="Context-aware routing",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        # Memory helper returns rich context
        mock_helper = AsyncMock()
        mock_helper.get_context = AsyncMock(
            return_value={
                "recent_messages": [
                    {"role": "user", "content": "営業時間は？"},
                    {"role": "assistant", "content": "9時から22時です。"},
                ],
                "context_string": "ユーザー: 営業時間は？\nアシスタント: 9時から22時です。",
                "summary": "ユーザーは営業時間について質問しました。",
                "inherited_request_type": "hours",
            }
        )
        mock_helper.store_message = AsyncMock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps_with_category("business-hours"):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                return_value={
                    "answer": "土日も9時から22時まで営業しています。",
                    "emotion": "neutral",
                    "metadata": {},
                }
            )

            await workflow.ainvoke(
                {
                    "query": "土日はどうですか？",
                    "session_id": "test-mem-1",
                    "language": "ja",
                }
            )

        # Verify orchestrator received the memory context
        orch_call = mock_orchestrator.decide_next_agent.call_args
        memory_context = orch_call.kwargs["memory_context"]
        assert memory_context is not None
        assert "recent_messages" in memory_context
        assert len(memory_context["recent_messages"]) == 2
        assert memory_context["summary"] == "ユーザーは営業時間について質問しました。"

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_memory_failure_does_not_break_flow(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """メモリ取得が失敗してもワークフロー全体は正常に完了する"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="general_knowledge",
            language="ja",
            category="general",
            request_type="general",
            confidence=0.7,
            reasoning="Fallback routing",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        # Memory helper raises an exception
        mock_helper = AsyncMock()
        mock_helper.get_context = AsyncMock(side_effect=Exception("Supabase connection failed"))
        mock_helper.store_message = AsyncMock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "何かお手伝いできますか？",
                    "emotion": "neutral",
                    "metadata": {},
                }
            )

            result = await workflow.ainvoke(
                {
                    "query": "こんにちは",
                    "session_id": "test-mem-2",
                    "language": "ja",
                }
            )

        # Workflow completes even with memory failure
        assert result["answer"] == "何かお手伝いできますか？"

        # Orchestrator receives None or empty memory_context
        orch_call = mock_orchestrator.decide_next_agent.call_args
        memory_context = orch_call.kwargs["memory_context"]
        # When memory fails, context["memory"] = {} so memory_context is {}
        assert memory_context is None or memory_context == {}

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_checkpointer_enables_thread_continuity(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """MemorySaver checkpointer により同一 thread_id で会話が継続できる"""
        from backend.workflows.main_workflow import MainWorkflow

        call_count = 0

        async def mock_decide(query, session_id, memory_context=None, previous_agent_response=None):
            nonlocal call_count
            call_count += 1
            return OrchestratorDecision(
                next_agent="general_knowledge",
                language="ja",
                category="general",
                request_type="general",
                confidence=0.8,
                reasoning=f"Call #{call_count}",
                debug_info={},
            )

        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(side_effect=mock_decide)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        checkpointer = MemorySaver()

        with _patch_memory_loader_deps():
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._general_knowledge_agent.answer_query = AsyncMock(
                return_value={
                    "answer": "回答です。",
                    "emotion": "neutral",
                    "metadata": {},
                }
            )

            session_id = "test-mem-continuity"

            # First invocation
            result1 = await workflow.ainvoke(
                {
                    "query": "最初の質問",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

            # Second invocation with same session_id
            result2 = await workflow.ainvoke(
                {
                    "query": "2番目の質問",
                    "session_id": session_id,
                    "language": "ja",
                }
            )

        # Both invocations completed successfully
        assert result1["answer"] == "回答です。"
        assert result2["answer"] == "回答です。"

        # Orchestrator was called twice (once per invocation)
        assert call_count == 2

    @patch("backend.utils.memory_helper.get_memory_helper")
    @patch("backend.workflows.main_workflow.OrchestratorAgent")
    async def test_knowledge_results_cached_in_state(
        self,
        mock_orchestrator_class,
        mock_get_helper,
    ):
        """RAG pre-fetch 結果が state.context.knowledge_results に格納される"""
        from backend.workflows.main_workflow import MainWorkflow

        mock_decision = OrchestratorDecision(
            next_agent="business_info",
            language="ja",
            category="business-hours",
            request_type="hours",
            confidence=0.9,
            reasoning="Business hours",
            debug_info={},
        )
        mock_orchestrator = AsyncMock()
        mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_helper = _make_memory_helper_mock()
        mock_get_helper.return_value = mock_helper

        mock_rag = _make_rag_mock()
        mock_rag.search = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "results": [{"title": "営業時間", "content": "9-22時"}],
                    "context": "営業時間は9時から22時です",
                },
            }
        )

        checkpointer = MemorySaver()

        captured_state_context = {}

        async def capture_biz_query(
            query, request_type, language, session_id, state_context=None, context_signals=None
        ):
            captured_state_context["knowledge_results"] = state_context
            return {
                "answer": "9時から22時です。",
                "emotion": "neutral",
                "metadata": {},
            }

        with (
            patch(
                "backend.tools.enhanced_rag.EnhancedRAGSearch",
                return_value=mock_rag,
            ),
            patch(
                "backend.utils.query_classifier.QueryClassifier",
                return_value=_make_classifier_mock("business-hours"),
            ),
            patch(
                "backend.utils.context_priority.ContextPriorityEngine",
                return_value=_make_context_priority_mock(),
            ),
        ):
            workflow = MainWorkflow(checkpointer=checkpointer)

            workflow._business_info_agent.answer_business_query = AsyncMock(
                side_effect=capture_biz_query
            )

            result = await workflow.ainvoke(
                {
                    "query": "営業時間は？",
                    "session_id": "test-mem-rag",
                    "language": "ja",
                }
            )

        assert result["answer"] == "9時から22時です。"

        # Verify knowledge_results were passed to the agent
        kr = captured_state_context.get("knowledge_results")
        assert kr is not None
        assert kr["success"] is True
        assert len(kr["results"]) == 1
        assert kr["context_string"] == "営業時間は9時から22時です"
