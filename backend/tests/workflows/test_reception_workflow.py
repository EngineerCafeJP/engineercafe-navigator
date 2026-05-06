"""Tests for the ReceptionWorkflow StateGraph.

All external calls (Supabase, LLM) are mocked. Tests cover:
- New visitor greeting
- Returning visitor (personalized) greeting
- Purpose classification integration
- Agent routing based on purpose
- Full end-to-end flow
"""

from __future__ import annotations

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# =============================================================================
# Helpers
# =============================================================================


def _make_session_id() -> str:
    return str(uuid.uuid4())


def _make_initial_state(
    session_id: Optional[str] = None,
    language: str = "ja",
    trigger_type: str = "button_press",
    messages=None,
):
    """Build a minimal ReceptionState dict for testing."""
    from backend.workflows.reception_workflow import make_initial_state

    return make_initial_state(
        session_id=session_id or _make_session_id(),
        language=language,
        trigger_type=trigger_type,
        messages=messages or [],
    )


def _mock_identification_service_new_visitor():
    """Return a mock VisitorIdentificationService that reports a new visitor."""
    svc = MagicMock()
    svc.identify_by_visitor_id = AsyncMock(return_value=None)
    svc.identify_by_nfc = AsyncMock(return_value=None)
    return svc


def _mock_identification_service_returning(name: str = "田中太郎", last_purpose: str = "勉強"):
    """Return a mock VisitorIdentificationService that reports a returning visitor."""
    svc = MagicMock()
    svc.identify_by_visitor_id = AsyncMock(
        return_value={
            "visitor_type": "returning",
            "name": name,
            "last_purpose": last_purpose,
            "visit_count": 3,
        }
    )
    return svc


# =============================================================================
# greet_visitor node tests
# =============================================================================


class TestGreetVisitorNode:
    """Unit tests for the greet_visitor graph node."""

    @pytest.mark.asyncio
    async def test_new_visitor_greeting_japanese(self):
        """New visitor receives a standard first-visit greeting in Japanese."""
        from backend.workflows.reception_workflow import greet_visitor

        state = _make_initial_state(language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_new_visitor(),
        ):
            result = await greet_visitor(state)

        assert result["stage"] == "greeting"
        assert result["visitor_identity"] is None
        assert result["greeting"]
        assert isinstance(result["greeting"], str)
        # Should not be a personalized message (no name)
        assert "田中" not in result["greeting"]

    @pytest.mark.asyncio
    async def test_new_visitor_greeting_english(self):
        """New visitor receives a first-visit greeting in English."""
        from backend.workflows.reception_workflow import greet_visitor

        state = _make_initial_state(language="en")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_new_visitor(),
        ):
            result = await greet_visitor(state)

        assert result["stage"] == "greeting"
        # English greeting should contain English text
        assert "Engineer Cafe" in result["greeting"] or "Welcome" in result["greeting"]

    @pytest.mark.asyncio
    async def test_returning_visitor_personalized_greeting(self):
        """Returning visitor with a name receives a personalized greeting."""
        from backend.workflows.reception_workflow import greet_visitor

        state = _make_initial_state(language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_returning(
                name="田中太郎",
                last_purpose="勉強",
            ),
        ):
            result = await greet_visitor(state)

        assert result["stage"] == "greeting"
        assert result["visitor_identity"] is not None
        assert result["visitor_identity"]["visitor_type"] == "returning"
        # Personalized greeting includes the visitor's name
        assert "田中太郎" in result["greeting"]

    @pytest.mark.asyncio
    async def test_returning_visitor_without_name_generic_greeting(self):
        """Returning visitor without a name gets a generic returning greeting."""
        from backend.workflows.reception_workflow import greet_visitor

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(
            return_value={
                "visitor_type": "returning",
                "name": None,
                "last_purpose": None,
                "visit_count": 1,
            }
        )
        state = _make_initial_state(language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            result = await greet_visitor(state)

        assert result["stage"] == "greeting"
        assert result["visitor_identity"] is not None
        # Generic returning greeting (no name interpolation)
        greeting = result["greeting"]
        assert greeting  # not empty

    @pytest.mark.asyncio
    async def test_greet_visitor_appends_ai_message(self):
        """greet_visitor adds an AIMessage to the messages list."""
        from backend.workflows.reception_workflow import greet_visitor

        state = _make_initial_state(language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_new_visitor(),
        ):
            result = await greet_visitor(state)

        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)

    @pytest.mark.asyncio
    async def test_greet_visitor_identification_error_handled(self):
        """VisitorIdentificationService errors are handled gracefully."""
        from backend.workflows.reception_workflow import greet_visitor

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(side_effect=RuntimeError("DB unavailable"))
        state = _make_initial_state(language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            result = await greet_visitor(state)

        # Should still return a valid greeting despite the error
        assert result["stage"] == "greeting"
        assert result["greeting"]


# =============================================================================
# hear_purpose node tests
# =============================================================================


class TestHearPurposeNode:
    """Unit tests for the hear_purpose graph node."""

    @pytest.mark.asyncio
    async def test_hear_purpose_sets_stage(self):
        """hear_purpose advances stage to purpose_hearing."""
        from backend.workflows.reception_workflow import hear_purpose

        state = _make_initial_state(language="ja")
        result = await hear_purpose(state)

        assert result["stage"] == "purpose_hearing"

    @pytest.mark.asyncio
    async def test_hear_purpose_japanese_prompt(self):
        """hear_purpose returns a Japanese prompt for ja language."""
        from backend.workflows.reception_workflow import hear_purpose

        state = _make_initial_state(language="ja")
        result = await hear_purpose(state)

        assert result["response"]
        # Should contain Japanese characters or text
        assert "ご用件" in result["response"] or "ください" in result["response"]

    @pytest.mark.asyncio
    async def test_hear_purpose_english_prompt(self):
        """hear_purpose returns an English prompt for en language."""
        from backend.workflows.reception_workflow import hear_purpose

        state = _make_initial_state(language="en")
        result = await hear_purpose(state)

        assert result["response"]
        assert "today" in result["response"].lower() or "bring" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_hear_purpose_appends_ai_message(self):
        """hear_purpose adds an AIMessage to messages."""
        from backend.workflows.reception_workflow import hear_purpose

        state = _make_initial_state(language="ja")
        result = await hear_purpose(state)

        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)


# =============================================================================
# classify_purpose node tests
# =============================================================================


class TestClassifyPurposeNode:
    """Unit tests for the classify_purpose graph node."""

    @pytest.mark.asyncio
    async def test_classify_facility_use_by_keywords(self):
        """Keyword-heavy message is classified as facility_use without LLM call."""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        state["messages"] = [HumanMessage(content="作業したいです。コーディングをするつもりです")]

        result = await classify_purpose(state)

        assert result["stage"] == "routing"
        assert result["purpose"]["category"] == "facility_use"
        assert result["purpose"]["confidence"] > 0.5

    @pytest.mark.asyncio
    async def test_classify_event_participation(self):
        """Event-related message is classified as event_participation."""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        state["messages"] = [HumanMessage(content="イベントに参加したい。勉強会に申し込みました")]

        result = await classify_purpose(state)

        assert result["stage"] == "routing"
        assert result["purpose"]["category"] == "event_participation"

    @pytest.mark.asyncio
    async def test_classify_purpose_with_llm_fallback(self):
        """When keywords don't match, LLM classification is invoked."""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        state["messages"] = [HumanMessage(content="ちょっと見学してみたいです")]

        # Mock LLM-based classification
        with patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new_callable=AsyncMock,
            return_value=("tour", "施設見学", 0.85),
        ):
            result = await classify_purpose(state)

        assert result["stage"] == "routing"
        assert result["purpose"]["category"] == "tour"

    @pytest.mark.asyncio
    async def test_assistant_profile_question_detours_without_classification(self):
        """Assistant identity questions are answered without advancing reception."""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        state["stage"] = "purpose_hearing"
        state["messages"] = [HumanMessage(content="あなたの名前は？")]

        with patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new_callable=AsyncMock,
            side_effect=AssertionError("purpose classifier must not be called"),
        ):
            result = await classify_purpose(state)

        assert result["stage"] == "purpose_hearing"
        assert result["reception_action"] == "answer_assistant_profile"
        assert "エンナビ" in result["response"]

    @pytest.mark.asyncio
    async def test_information_question_bypasses_purpose_classification(self):
        """明確な施設情報質問は目的不明として聞き返さず、通常QAへ渡す。"""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        state["stage"] = "purpose_hearing"
        state["messages"] = [HumanMessage(content="エンジニアカフェの営業時間を教えてください")]

        with patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new_callable=AsyncMock,
            side_effect=AssertionError("purpose classifier must not be called"),
        ):
            result = await classify_purpose(state)

        assert result["stage"] == "completed"
        assert result["target_agent"] == "business_info"
        assert result["reception_action"] == "bypass_for_information_query"
        assert result["purpose"]["request_type"] == "hours"

    @pytest.mark.asyncio
    async def test_classify_purpose_no_human_message_defaults_other(self):
        """When no human message is present, stay in purpose_hearing and re-prompt."""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        # Only AI messages in history, no human message
        state["messages"] = [AIMessage(content="いらっしゃいませ")]

        result = await classify_purpose(state)

        assert result["stage"] == "purpose_hearing"
        assert result["purpose"]["category"] == "other"
        assert result["response"]

    @pytest.mark.asyncio
    async def test_classify_purpose_classification_error_handled(self):
        """Classification errors fall back to 'other' and re-prompt gracefully."""
        from backend.workflows.reception_workflow import classify_purpose

        state = _make_initial_state(language="ja")
        state["messages"] = [HumanMessage(content="なんか特殊な用件です")]

        with patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = await classify_purpose(state)

        assert result["stage"] == "purpose_hearing"
        assert result["purpose"]["category"] == "other"
        assert result["response"]


# =============================================================================
# route_to_agent node tests
# =============================================================================


class TestRouteToAgentNode:
    """Unit tests for the route_to_agent graph node."""

    @pytest.mark.asyncio
    async def test_facility_use_routes_to_facility_agent(self):
        """facility_use purpose routes visitor to the facility agent."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {"category": "facility_use", "detail": None, "confidence": 0.9}

        result = await route_to_agent(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["target_agent"] == "facility"

    @pytest.mark.asyncio
    async def test_event_participation_routes_to_event_agent(self):
        """event_participation purpose routes visitor to the event agent."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {
            "category": "event_participation",
            "detail": None,
            "confidence": 0.9,
        }

        result = await route_to_agent(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["target_agent"] == "event"

    @pytest.mark.asyncio
    async def test_tour_routes_to_slide_agent(self):
        """tour purpose routes visitor to the slide agent."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {"category": "tour", "detail": None, "confidence": 0.8}

        result = await route_to_agent(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["target_agent"] == "slide"

    @pytest.mark.asyncio
    async def test_consultation_routes_to_general_knowledge_agent(self):
        """consultation purpose routes to general_knowledge agent."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {"category": "consultation", "detail": None, "confidence": 0.75}

        result = await route_to_agent(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["target_agent"] == "general_knowledge"

    @pytest.mark.asyncio
    async def test_other_routes_to_general_knowledge_agent(self):
        """other purpose routes to general_knowledge agent."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {"category": "other", "detail": None, "confidence": 0.3}

        result = await route_to_agent(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["target_agent"] == "general_knowledge"

    @pytest.mark.asyncio
    async def test_route_generates_followup_response(self):
        """route_to_agent emits the downstream target agent."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {"category": "facility_use", "detail": None, "confidence": 0.9}

        result = await route_to_agent(state)

        assert result["stage"] == "completed"
        assert result["target_agent"] == "facility"

    @pytest.mark.asyncio
    async def test_route_preserves_existing_purpose_fields(self):
        """route_to_agent preserves existing purpose fields (immutable update)."""
        from backend.workflows.reception_workflow import route_to_agent

        state = _make_initial_state(language="ja")
        state["purpose"] = {
            "category": "event_participation",
            "detail": "Python勉強会",
            "confidence": 0.92,
        }

        result = await route_to_agent(state)

        assert result["purpose"]["category"] == "event_participation"
        assert result["purpose"]["detail"] == "Python勉強会"
        assert result["purpose"]["confidence"] == 0.92
        assert result["purpose"]["target_agent"] == "event"


# =============================================================================
# Full end-to-end flow tests
# =============================================================================


class TestReceptionWorkflowEndToEnd:
    """Turn-by-turn tests running the compiled reception subgraph."""

    @pytest.mark.asyncio
    async def test_initiated_stage_advances_to_greeting(self):
        """An initiated session returns a greeting and remains in greeting stage."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_new_visitor(),
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "greeting"
        assert result["greeting"] is not None
        assert result["response"] == result["greeting"]
        assert result["target_agent"] is None

    @pytest.mark.asyncio
    async def test_initiated_stage_returning_visitor_personalized(self):
        """Returning visitor with a name receives personalized greeting."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="ja")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_returning(
                name="鈴木花子", last_purpose="コーディング"
            ),
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "greeting"
        assert "鈴木花子" in result["greeting"]

    @pytest.mark.asyncio
    async def test_greeting_stage_advances_to_purpose_hearing(self):
        """A greeting-stage session asks for the visitor's purpose."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="ja")
        state["stage"] = "greeting"

        graph = await get_reception_workflow()
        result = await graph.ainvoke(state)

        assert result["stage"] == "purpose_hearing"
        assert result["response"]
        assert result["visitor_identity"] == {"visitor_type": "new"}

    @pytest.mark.asyncio
    async def test_purpose_hearing_stage_advances_to_routing(self):
        """Purpose hearing classifies the user message and moves to routing."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="ja")
        state["stage"] = "purpose_hearing"
        state["messages"] = [HumanMessage(content="ちょっと施設を見学させてください")]

        with patch(
            "backend.utils.purpose_classifier.classify_purpose",
            new_callable=AsyncMock,
            return_value=("tour", "施設見学希望", 0.88),
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "routing"
        assert result["purpose"]["category"] == "tour"
        assert result["target_agent"] is None

    @pytest.mark.asyncio
    async def test_routing_stage_completes_and_returns_target_agent(self):
        """Routing stage completes reception and returns a downstream agent."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="ja")
        state["stage"] = "routing"
        state["purpose"] = {"category": "consultation", "detail": None, "confidence": 0.75}

        graph = await get_reception_workflow()
        result = await graph.ainvoke(state)

        assert result["stage"] == "completed"
        assert result["target_agent"] == "general_knowledge"
        assert result["purpose"]["target_agent"] == "general_knowledge"

    @pytest.mark.asyncio
    async def test_initiated_stage_english(self):
        """Initiated stage works correctly for English language sessions."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="en")

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=_mock_identification_service_new_visitor(),
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "greeting"
        assert result["greeting"] is not None
        assert result["language"] == "en"

    @pytest.mark.asyncio
    async def test_initiated_stage_supabase_unavailable(self):
        """Greeting still works even when visitor lookup is unavailable."""
        from backend.workflows.reception_workflow import get_reception_workflow, make_initial_state

        state = make_initial_state(session_id=_make_session_id(), language="ja")

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(return_value=None)

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "greeting"
        assert result["visitor_identity"] is None
        assert result["greeting"]
