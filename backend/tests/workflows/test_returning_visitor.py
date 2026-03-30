"""
リピーター検出ユニットテスト - returning visitor detection in main_workflow

main_workflow._orchestrator_node の reception ブロックで
long_term_memory の有無に基づいて reception_type を判定するロジックをテスト。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Helper: Build minimal workflow state
# =============================================================================


def _make_state(query="こんにちは", language="ja", long_term_memory=None, context=None):
    """テスト用の最小 WorkflowStateDict を構築"""
    ctx = context or {}
    if long_term_memory is not None:
        ctx["long_term_memory"] = long_term_memory
    return {
        "messages": [],
        "query": query,
        "session_id": str(uuid.uuid4()),
        "language": language,
        "routing": {},
        "answer": None,
        "emotion": None,
        "metadata": {},
        "context": ctx,
        "image_data": None,
        "ocr_result": None,
    }


def _make_decision(category="general", request_type="reception", language="ja"):
    """Mock RoutingDecision"""
    decision = MagicMock()
    decision.category = category
    decision.request_type = request_type
    decision.language = language
    decision.confidence = 0.9
    decision.reasoning = "test"
    decision.debug_info = {}
    decision.next_agent = "general_knowledge"
    return decision


# =============================================================================
# reception_type 判定テスト
# =============================================================================


class TestReceptionTypeDetection:
    """ReceptionDomainService での visitor type 判定ロジック"""

    @pytest.fixture
    def service(self):
        from backend.domain.reception.service import ReceptionDomainService

        return ReceptionDomainService()

    @pytest.mark.asyncio
    async def test_first_time_keyword_ja(self, service):
        """「初めて来ました」→ first_time"""
        result = service.determine_visitor_type("初めて来ました", "ja", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_first_time_keyword_en(self, service):
        """'first time' keyword → first_time"""
        result = service.determine_visitor_type("This is my first time here", "en", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_returning_with_long_term_memory(self, service):
        """long_term_memory あり → returning"""
        memories = [{"data": "前回WiFiの使い方を質問", "type": "fact"}]
        result = service.determine_visitor_type("こんにちは", "ja", memories)
        assert result.value == "returning"

    @pytest.mark.asyncio
    async def test_general_no_memory_no_keyword(self, service):
        """long_term_memory なし + キーワードなし → general"""
        result = service.determine_visitor_type("こんにちは", "ja", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_general_none_memory(self, service):
        """long_term_memory が None → general"""
        result = service.determine_visitor_type("こんにちは", "ja", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_first_time_overrides_memory(self, service):
        """first_time キーワードは long_term_memory よりも優先"""
        memories = [{"data": "過去の記録", "type": "fact"}]
        result = service.determine_visitor_type("初めて来ました", "ja", memories)
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_hajimete_keyword(self, service):
        """「はじめて」キーワード → first_time"""
        result = service.determine_visitor_type("はじめて利用します", "ja", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_first_visit_keyword_en(self, service):
        """'first visit' keyword → first_time"""
        result = service.determine_visitor_type("This is my first visit", "en", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_initial_visit_keyword_en(self, service):
        """'initial visit' keyword → first_time (case insensitive)"""
        result = service.determine_visitor_type("This is my initial visit here", "en", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_syokkai_keyword(self, service):
        """「初回」キーワード → first_time"""
        result = service.determine_visitor_type("初回訪問です", "ja", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_case_insensitive_keyword_matching(self, service):
        """キーワードマッチングは大文字小文字を区別しない"""
        result = service.determine_visitor_type("FIRST TIME visiting here", "en", [])
        assert result.value == "new"

    @pytest.mark.asyncio
    async def test_multiple_memories_triggers_returning(self, service):
        """複数の long_term_memory エントリ → returning"""
        memories = [
            {"data": "前回WiFiの質問", "type": "fact"},
            {"data": "イベント情報の質問", "type": "event"},
            {"data": "営業時間を確認", "type": "business"},
        ]
        result = service.determine_visitor_type("こんにちは", "ja", memories)
        assert result.value == "returning"

    @pytest.mark.asyncio
    async def test_empty_memory_list_is_general(self, service):
        """empty list of memories → general (same as None)"""
        result = service.determine_visitor_type("こんにちは", "ja", [])
        assert result.value == "new"


# =============================================================================
# Emergency inline block テスト
# =============================================================================


class TestEmergencyInlineBlock:
    """emergency category がインラインで処理されることを検証"""

    @pytest.fixture
    def workflow(self):
        from backend.workflows.main_workflow import MainWorkflow

        return MainWorkflow(checkpointer=None)

    @pytest.mark.asyncio
    async def test_emergency_returns_template(self, workflow):
        """emergency → テンプレート応答が返る"""
        state = _make_state(query="地震です！")
        decision = _make_decision(category="emergency", request_type="emergency")

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            with patch("backend.workflows.main_workflow.asyncio.create_task"):
                result = await workflow._orchestrator_node(state)
                assert result.update["answer"]
                assert result.update["emotion"] == "serious"
                routing = result.update["routing"]
                assert routing["category"] == "emergency"

    @pytest.mark.asyncio
    async def test_emergency_triggers_discord_task(self, workflow):
        """emergency → asyncio.create_task が呼ばれる"""
        state = _make_state(query="火事だ！")
        decision = _make_decision(category="emergency", request_type="emergency")

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            with patch("backend.workflows.main_workflow.asyncio.create_task") as mock_task:
                await workflow._orchestrator_node(state)
                mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_emergency_metadata_has_subtype(self, workflow):
        """emergency metadata に subtype が含まれる"""
        state = _make_state(query="AEDはどこ？")
        decision = _make_decision(category="emergency", request_type="emergency")

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            with patch("backend.workflows.main_workflow.asyncio.create_task"):
                result = await workflow._orchestrator_node(state)
                emergency_meta = result.update["metadata"].get("emergency", {})
                assert "subtype" in emergency_meta
                assert "confidence" in emergency_meta

    @pytest.mark.asyncio
    async def test_emergency_routing_target(self, workflow):
        """emergency → format_response に goto"""
        state = _make_state(query="緊急です")
        decision = _make_decision(category="emergency", request_type="emergency")

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            with patch("backend.workflows.main_workflow.asyncio.create_task"):
                result = await workflow._orchestrator_node(state)
                assert result.goto == "format_response"

    @pytest.mark.asyncio
    async def test_emergency_sets_serious_emotion(self, workflow):
        """emergency response は emotion を 'serious' に設定"""
        state = _make_state(query="怪我人がいます")
        decision = _make_decision(category="emergency", request_type="emergency")

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            with patch("backend.workflows.main_workflow.asyncio.create_task"):
                result = await workflow._orchestrator_node(state)
                assert result.update["emotion"] == "serious"


# =============================================================================
# Clarification inline block テスト
# =============================================================================


class TestClarificationInlineBlock:
    """clarification categories がインラインで処理されることを検証"""

    @pytest.fixture
    def workflow(self):
        from backend.workflows.main_workflow import MainWorkflow

        return MainWorkflow(checkpointer=None)

    @pytest.mark.asyncio
    async def test_cafe_clarification_inline(self, workflow):
        """cafe-clarification-needed → インラインで処理"""
        state = _make_state(query="カフェについて質問があります")
        decision = _make_decision(
            category="cafe-clarification-needed",
            request_type="clarification",
        )

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            result = await workflow._orchestrator_node(state)
            assert result.goto == "format_response"
            assert result.update["answer"]
            routing = result.update["routing"]
            assert routing["category"] == "cafe-clarification-needed"

    @pytest.mark.asyncio
    async def test_meeting_room_clarification_inline(self, workflow):
        """meeting-room-clarification-needed → インラインで処理"""
        state = _make_state(query="会議室について知りたい")
        decision = _make_decision(
            category="meeting-room-clarification-needed",
            request_type="clarification",
        )

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            result = await workflow._orchestrator_node(state)
            assert result.goto == "format_response"
            assert "clarification" in result.update["metadata"]

    @pytest.mark.asyncio
    async def test_clarification_sets_requires_followup(self, workflow):
        """clarification metadata に requires_followup フラグが立つ"""
        state = _make_state(query="イベントについて知りたい")
        decision = _make_decision(
            category="event-clarification-needed",
            request_type="clarification",
        )

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            result = await workflow._orchestrator_node(state)
            assert result.update["metadata"].get("requires_followup") is True

    @pytest.mark.asyncio
    async def test_space_clarification_inline(self, workflow):
        """space-clarification-needed → インラインで処理"""
        state = _make_state(query="スペースについて")
        decision = _make_decision(
            category="space-clarification-needed",
            request_type="clarification",
        )

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            result = await workflow._orchestrator_node(state)
            assert result.goto == "format_response"
            assert result.update["answer"]

    @pytest.mark.asyncio
    async def test_general_clarification_inline(self, workflow):
        """general-clarification-needed → インラインで処理"""
        state = _make_state(query="何か質問があります")
        decision = _make_decision(
            category="general-clarification-needed",
            request_type="clarification",
        )

        with patch.object(
            workflow.orchestrator,
            "decide_next_agent",
            new_callable=AsyncMock,
            return_value=decision,
        ):
            result = await workflow._orchestrator_node(state)
            assert result.goto == "format_response"
            assert result.update["answer"]
