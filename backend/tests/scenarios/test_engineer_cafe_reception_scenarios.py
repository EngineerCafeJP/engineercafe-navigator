"""
Engineer Cafe Reception Scenario Tests
=======================================
TDD: These tests define the expected behavior BEFORE implementation.
They should FAIL on the current codebase and PASS after Wave 7 implementation.

Scenarios are derived from:
- Existing knowledge base markdown documents
- routing_constants.py keyword patterns (real user query patterns)
- RAGAS evaluation test data (e2e_scenarios.json)
- Discord logs of actual kiosk usage (2026-03-25, 2026-03-28)

Each scenario represents a real visitor interaction at Engineer Cafe Fukuoka.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.orchestrator_agent import OrchestratorDecision
from backend.config.routing_constants import extract_request_type

# Mark all tests as scenario tests (can be run with pytest -m scenario)
pytestmark = [pytest.mark.scenario, pytest.mark.slow]


# =============================================================================
# Shared test helpers (same pattern as test_multi_agent_scenarios.py)
# =============================================================================


def _make_memory_helper_mock(context_return=None):
    helper = AsyncMock()
    if context_return is None:
        context_return = {"recent_messages": [], "context_string": ""}
    helper.get_context = AsyncMock(return_value=context_return)
    helper.store_message = AsyncMock()
    return helper


def _make_rag_mock(context=""):
    rag = AsyncMock()
    rag.search = AsyncMock(
        return_value={
            "success": True,
            "data": {"results": [], "context": context},
        }
    )
    return rag


def _make_classifier_mock(category="general"):
    class _Classification:
        def __init__(self, cat):
            self.category = cat

    classification = _Classification(category)
    classifier = MagicMock()
    classifier.classify_with_details = AsyncMock(return_value=classification)
    return classifier


def _make_context_priority_mock():
    mock_engine = MagicMock()
    mock_engine.extract_signals_from_context.return_value = {
        "has_memory": False,
        "has_knowledge": False,
    }
    return mock_engine


@contextmanager
def _patch_memory_loader_deps(category="general"):
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
    return OrchestratorDecision(
        next_agent=next_agent,
        language=language,
        category=category,
        request_type=request_type,
        confidence=confidence,
        reasoning=reasoning,
        debug_info={},
    )


async def _run_workflow(query, session_id, language, mock_decision, agent_attr, agent_response):
    """Run MainWorkflow with standard mocks and return the result."""
    from backend.workflows.main_workflow import MainWorkflow

    mock_orchestrator = AsyncMock()
    mock_orchestrator.decide_next_agent = AsyncMock(return_value=mock_decision)

    mock_helper = _make_memory_helper_mock()

    with (
        patch(
            "backend.workflows.main_workflow.OrchestratorAgent",
            return_value=mock_orchestrator,
        ),
        patch("backend.utils.memory_helper.get_memory_helper", return_value=mock_helper),
    ):
        checkpointer = MemorySaver()
        category = mock_decision.category if mock_decision.category else "general"

        with _patch_memory_loader_deps(category):
            workflow = MainWorkflow(checkpointer=checkpointer)

            agent = getattr(workflow, agent_attr)
            if agent_attr == "_business_info_agent":
                agent.answer_business_query = AsyncMock(return_value=agent_response)
            elif agent_attr == "_facility_agent":
                agent.answer_facility_query = AsyncMock(return_value=agent_response)
            elif agent_attr == "_event_agent":
                agent.answer_event_query = AsyncMock(return_value=agent_response)
            elif agent_attr == "_general_knowledge_agent":
                agent.answer_general_query = AsyncMock(return_value=agent_response)
            elif agent_attr == "_slide_agent":
                agent.handle_slide_request = AsyncMock(return_value=agent_response)
            elif agent_attr == "_farewell_agent":
                agent.handle_farewell = AsyncMock(return_value=agent_response)

            result = await workflow.ainvoke(
                {"query": query, "session_id": session_id, "language": language}
            )

    return result


# =============================================================================
# A. Japanese Regular User (エンジニアカフェ利用客)
# =============================================================================


class TestJapaneseRegularUser:
    """日本語の一般利用者シナリオ。エンジニアカフェで最も頻出する質問パターン。"""

    @pytest.mark.asyncio
    async def test_a01_wifi_password(self):
        """A01: "WiFiのパスワードを教えてください" -> facility agent -> WiFi password

        Most common question at the kiosk. Visitors need WiFi immediately.
        """
        assert extract_request_type("WiFiのパスワードを教えてください") == "wifi"

        result = await _run_workflow(
            query="WiFiのパスワードを教えてください",
            session_id="scenario-a01",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facility-info",
                request_type="wifi",
                confidence=0.98,
                reasoning="WiFi keyword detected",
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "Wi-Fiは無料でご利用いただけます。SSID: EngineerCafe_WiFi",
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert "Wi-Fi" in result["answer"] or "wifi" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_a02_business_hours(self):
        """A02: "営業時間は何時までですか？" -> business_info agent -> hours

        Hours: Weekdays/Sat 9:00-22:00, Sun/Holidays 9:00-20:00.
        """
        assert extract_request_type("営業時間は何時までですか？") == "hours"

        result = await _run_workflow(
            query="営業時間は何時までですか？",
            session_id="scenario-a02",
            language="ja",
            mock_decision=_build_decision(
                next_agent="business_info",
                category="business-hours",
                request_type="hours",
                confidence=0.97,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": "平日・土曜は9:00〜22:00、日曜・祝日は9:00〜20:00です。",
                "emotion": "neutral",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert "9:00" in result["answer"]
        assert "22:00" in result["answer"] or "20:00" in result["answer"]

    @pytest.mark.asyncio
    async def test_a03_todays_events(self):
        """A03: "今日のイベントはありますか？" -> event agent -> calendar check

        Visitors checking if there's a meetup/seminar today.
        """
        assert extract_request_type("今日のイベントはありますか？") == "event"

        result = await _run_workflow(
            query="今日のイベントはありますか？",
            session_id="scenario-a03",
            language="ja",
            mock_decision=_build_decision(
                next_agent="event",
                category="events",
                request_type="event",
                confidence=0.95,
            ),
            agent_attr="_event_agent",
            agent_response={
                "answer": "本日はPython勉強会が19:00から開催されます。",
                "emotion": "happy",
                "metadata": {"agent": "EventAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_a04_basement_space(self):
        """A04: "地下のスペースを使いたいのですが" -> facility agent -> basement info

        Engineer Cafe has B1 with meeting/focus/makers spaces.
        """
        assert extract_request_type("地下のスペースを使いたいのですが") == "basement"

        result = await _run_workflow(
            query="地下のスペースを使いたいのですが",
            session_id="scenario-a04",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facility-info",
                request_type="basement",
                confidence=0.93,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "地下にはMTGスペース、集中スペース、MAKER'sスペースがあります。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_a05_meeting_room_booking(self):
        """A05: "会議室の予約方法を教えてください" -> facility agent -> meeting room"""
        assert extract_request_type("会議室の予約方法を教えてください") == "meeting-room"

        result = await _run_workflow(
            query="会議室の予約方法を教えてください",
            session_id="scenario-a05",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facility-info",
                request_type="meeting-room",
                confidence=0.92,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "会議室は事前予約で利用できます。受付でお申し込みください。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_a06_pricing_free(self):
        """A06: "料金はいくらですか？" -> business_info -> pricing (free!)

        Engineer Cafe is free to use. Visitors often don't believe it.
        """
        assert extract_request_type("料金はいくらですか？") == "price"

        result = await _run_workflow(
            query="料金はいくらですか？",
            session_id="scenario-a06",
            language="ja",
            mock_decision=_build_decision(
                next_agent="business_info",
                category="pricing",
                request_type="price",
                confidence=0.96,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": "エンジニアカフェは無料でご利用いただけます。",
                "emotion": "happy",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert "無料" in result["answer"]

    @pytest.mark.asyncio
    async def test_a07_power_outlets(self):
        """A07: "電源はどこにありますか？" -> facility agent -> power outlets

        Engineers need to charge laptops. Power outlets at most desks.
        """
        assert extract_request_type("電源はどこにありますか？") == "facility"

        result = await _run_workflow(
            query="電源はどこにありますか？",
            session_id="scenario-a07",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facilities",
                request_type="facility",
                confidence=0.90,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "各デスクに電源コンセントが設置されています。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_a08_printer_available(self):
        """A08: "プリンターは使えますか？" -> facility agent -> printing"""
        assert extract_request_type("プリンターは使えますか？") == "facility"

        result = await _run_workflow(
            query="プリンターは使えますか？",
            session_id="scenario-a08",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facilities",
                request_type="facility",
                confidence=0.90,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "プリンターをご利用いただけます。受付にお声がけください。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_a09_what_is_engineer_cafe(self):
        """A09: "エンジニアカフェって何ですか？" -> business_info -> about

        From e2e_scenarios.json scn-001: first-time visitor at kiosk.
        """
        result = await _run_workflow(
            query="エンジニアカフェって何ですか？",
            session_id="scenario-a09",
            language="ja",
            mock_decision=_build_decision(
                next_agent="business_info",
                category="general",
                request_type="general",
                confidence=0.85,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": (
                    "エンジニアカフェは、福岡市の赤煉瓦文化館にある"
                    "エンジニア向けの無料コワーキングスペースです。"
                ),
                "emotion": "happy",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert "エンジニアカフェ" in result["answer"] or "コワーキング" in result["answer"]

    @pytest.mark.asyncio
    async def test_a10_community_lab(self):
        """A10: "コミュニティラボについて教えてください" -> business_info -> community

        EC Lab is a membership community for startups. From scn-007.
        """
        assert extract_request_type("エンジニアカフェラボについて教えてください") == "community"

        result = await _run_workflow(
            query="コミュニティラボについて教えてください",
            session_id="scenario-a10",
            language="ja",
            mock_decision=_build_decision(
                next_agent="business_info",
                category="community",
                request_type="community",
                confidence=0.92,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": (
                    "Engineer Cafe Labは会員制のコミュニティです。"
                    "起業やスタートアップの支援を行っています。"
                ),
                "emotion": "happy",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None


# =============================================================================
# B. English Tourist (外国人観光客)
# =============================================================================


class TestEnglishTourist:
    """English-speaking visitor scenarios. Engineer Cafe is in a historic
    building in Fukuoka and attracts international visitors."""

    @pytest.mark.asyncio
    async def test_b11_opening_hours_english(self):
        """B11: "What are the opening hours?" -> business_info -> hours (English)

        From e2e_scenarios.json scn-004.
        """
        assert extract_request_type("What are the opening hours?") == "hours"

        result = await _run_workflow(
            query="What are the opening hours?",
            session_id="scenario-b11",
            language="en",
            mock_decision=_build_decision(
                next_agent="business_info",
                language="en",
                category="business-hours",
                request_type="hours",
                confidence=0.95,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": (
                    "We are open weekdays and Saturdays from 9:00 to 22:00, "
                    "Sundays and holidays from 9:00 to 20:00."
                ),
                "emotion": "neutral",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert "9:00" in result["answer"]

    @pytest.mark.asyncio
    async def test_b12_is_it_free_english(self):
        """B12: "Is it free to use?" -> business_info -> pricing (English)"""
        assert extract_request_type("Is it free to use?") == "price"

        result = await _run_workflow(
            query="Is it free to use?",
            session_id="scenario-b12",
            language="en",
            mock_decision=_build_decision(
                next_agent="business_info",
                language="en",
                category="pricing",
                request_type="price",
                confidence=0.95,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": "Yes, Engineer Cafe is completely free to use!",
                "emotion": "happy",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert "free" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_b13_wifi_password_english(self):
        """B13: "What's the WiFi password?" -> facility -> WiFi (English)"""
        assert extract_request_type("What's the WiFi password?") == "wifi"

        result = await _run_workflow(
            query="What's the WiFi password?",
            session_id="scenario-b13",
            language="en",
            mock_decision=_build_decision(
                next_agent="facility",
                language="en",
                category="facility-info",
                request_type="wifi",
                confidence=0.97,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "Free WiFi is available. SSID: EngineerCafe_WiFi",
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert "WiFi" in result["answer"] or "wifi" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_b14_directions_from_hakata(self):
        """B14: "How do I get here from Hakata Station?" -> facility -> access

        Hakata Station is the main JR station in Fukuoka.
        """
        assert extract_request_type("How do I get here from Hakata Station?") == "access"

        result = await _run_workflow(
            query="How do I get here from Hakata Station?",
            session_id="scenario-b14",
            language="en",
            mock_decision=_build_decision(
                next_agent="facility",
                language="en",
                category="access",
                request_type="access",
                confidence=0.92,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": (
                    "From Hakata Station, take the subway to Gion Station. "
                    "It's a 5-minute walk from there."
                ),
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_b15_tour_request(self):
        """B15: "I'd like a tour of the building" -> slide agent -> tour slides

        The building (Akarenga Cultural Hall) is a registered Important
        Cultural Property from 1909. Tourists want a tour.
        """
        result = await _run_workflow(
            query="I'd like a tour of the building",
            session_id="scenario-b15",
            language="en",
            mock_decision=_build_decision(
                next_agent="slide",
                language="en",
                category="slide",
                request_type="slide",
                confidence=0.88,
            ),
            agent_attr="_slide_agent",
            agent_response={
                "answer": "Let me show you around! This building was built in 1909.",
                "emotion": "happy",
                "metadata": {"agent": "SlideAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_b16_events_today_english(self):
        """B16: "What events are happening today?" -> event -> calendar (English)"""
        assert extract_request_type("What events are happening today?") == "event"

        result = await _run_workflow(
            query="What events are happening today?",
            session_id="scenario-b16",
            language="en",
            mock_decision=_build_decision(
                next_agent="event",
                language="en",
                category="events",
                request_type="event",
                confidence=0.93,
            ),
            agent_attr="_event_agent",
            agent_response={
                "answer": "There is a Python meetup today at 19:00.",
                "emotion": "happy",
                "metadata": {"agent": "EventAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_b17_restroom_english(self):
        """B17: "Where is the restroom?" -> facility -> restroom (English)

        From e2e_scenarios.json scn-008.
        """
        assert extract_request_type("Where is the restroom?") == "toilet"

        result = await _run_workflow(
            query="Where is the restroom?",
            session_id="scenario-b17",
            language="en",
            mock_decision=_build_decision(
                next_agent="facility",
                language="en",
                category="facility-info",
                request_type="toilet",
                confidence=0.95,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "Restrooms are located on each floor.",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None


# =============================================================================
# C. Reception Flow (受付フロー)
# =============================================================================


class TestReceptionFlow:
    """Reception workflow scenarios triggered by sensor/button at the kiosk.
    Tests the full greet -> hear_purpose -> classify -> route flow."""

    @pytest.mark.asyncio
    async def test_c18_sensor_trigger_facility_use(self):
        """C18: Sensor trigger -> greeting -> "施設を使いたい" -> facility routing

        Visitor walks up to kiosk, sensor triggers greeting,
        they say they want to use the facility.
        """
        from backend.workflows.reception_workflow import (
            get_reception_workflow,
            make_initial_state,
        )
        from langchain_core.messages import HumanMessage

        state = make_initial_state(
            session_id="scenario-c18",
            language="ja",
            trigger_type="sensor",
        )
        state["messages"] = [HumanMessage(content="施設を使いたいです")]

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(return_value=None)

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["category"] == "facility_use"
        assert result["purpose"]["target_agent"] == "facility"

    @pytest.mark.asyncio
    async def test_c19_sensor_trigger_tour(self):
        """C19: Sensor trigger -> greeting -> "I want a tour" -> slide routing

        English tourist at kiosk wants to see the building.
        """
        from backend.workflows.reception_workflow import (
            get_reception_workflow,
            make_initial_state,
        )
        from langchain_core.messages import HumanMessage

        state = make_initial_state(
            session_id="scenario-c19",
            language="en",
            trigger_type="sensor",
        )
        state["messages"] = [HumanMessage(content="I want a tour of the building")]

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(return_value=None)

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            with patch(
                "backend.utils.purpose_classifier.classify_purpose",
                new_callable=AsyncMock,
                return_value=("tour", "Building tour request", 0.90),
            ):
                graph = await get_reception_workflow()
                result = await graph.ainvoke(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["category"] == "tour"
        assert result["purpose"]["target_agent"] == "slide"

    @pytest.mark.asyncio
    async def test_c20_sensor_trigger_event(self):
        """C20: Sensor trigger -> "イベントに参加しに来ました" -> event routing

        Visitor came for a specific meetup/seminar.
        """
        from backend.workflows.reception_workflow import (
            get_reception_workflow,
            make_initial_state,
        )
        from langchain_core.messages import HumanMessage

        state = make_initial_state(
            session_id="scenario-c20",
            language="ja",
            trigger_type="sensor",
        )
        state["messages"] = [HumanMessage(content="イベントに参加しに来ました")]

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(return_value=None)

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "completed"
        assert result["purpose"]["category"] == "event_participation"
        assert result["purpose"]["target_agent"] == "event"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Wave 7: ambiguous purpose re-ask not yet implemented")
    async def test_c21_ambiguous_purpose(self):
        """C21: "ちょっと見に来ただけ" -> should re-ask purpose

        Visitor is just browsing. System should clarify intent before routing.
        """
        from backend.workflows.reception_workflow import (
            get_reception_workflow,
            make_initial_state,
        )
        from langchain_core.messages import HumanMessage

        state = make_initial_state(
            session_id="scenario-c21",
            language="ja",
            trigger_type="sensor",
        )
        state["messages"] = [HumanMessage(content="ちょっと見に来ただけです")]

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(return_value=None)

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] in ("purpose_hearing", "clarification")
        assert "purpose" not in result or result["purpose"]["confidence"] < 0.5

    @pytest.mark.asyncio
    async def test_c22_returning_visitor(self):
        """C22: Returning visitor -> personalized greeting -> purpose

        Recognized visitor gets a personalized welcome with their name.
        """
        from backend.workflows.reception_workflow import (
            get_reception_workflow,
            make_initial_state,
        )
        from langchain_core.messages import HumanMessage

        state = make_initial_state(
            session_id="scenario-c22",
            language="ja",
            trigger_type="sensor",
        )
        state["messages"] = [HumanMessage(content="作業したいです")]

        svc = MagicMock()
        svc.identify_by_visitor_id = AsyncMock(
            return_value={
                "visitor_type": "returning",
                "name": "山田太郎",
                "last_purpose": "コーディング",
                "visit_count": 5,
            }
        )

        with patch(
            "backend.workflows.reception_workflow.VisitorIdentificationService",
            return_value=svc,
        ):
            graph = await get_reception_workflow()
            result = await graph.ainvoke(state)

        assert result["stage"] == "completed"
        assert "山田太郎" in result["greeting"]
        assert result["visitor_identity"]["visitor_type"] == "returning"
        assert result["purpose"]["category"] == "facility_use"


# =============================================================================
# D. Cross-domain & Edge Cases
# =============================================================================


class TestCrossDomainAndEdgeCases:
    """Edge cases that test routing robustness and multi-intent handling."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Wave 7: multi-intent splitting not yet implemented")
    async def test_d23_multi_intent_wifi_and_hours(self):
        """D23: "WiFiパスワードと営業時間を教えて" -> both answers

        From e2e_scenarios.json scn-005. Visitors often ask multiple things.
        """
        assert extract_request_type("WiFiパスワードと営業時間を教えて") == "wifi"

        result = await _run_workflow(
            query="WiFiパスワードと営業時間を教えて",
            session_id="scenario-d23",
            language="ja",
            mock_decision=_build_decision(
                next_agent="business_info",
                category="business-hours",
                request_type="hours",
                confidence=0.85,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": (
                    "Wi-Fiパスワードは受付でお伝えしています。"
                    "営業時間は平日・土曜9:00〜22:00、日曜・祝日9:00〜20:00です。"
                ),
                "emotion": "neutral",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        answer = result["answer"]
        assert "Wi-Fi" in answer or "wifi" in answer.lower()
        assert "9:00" in answer

    @pytest.mark.asyncio
    async def test_d24_mixed_language_query(self):
        """D24: "hello, wifi password?" -> mixed language -> WiFi answer

        Non-native speakers mixing English greetings with keywords.
        """
        assert extract_request_type("hello, wifi password?") == "wifi"

        result = await _run_workflow(
            query="hello, wifi password?",
            session_id="scenario-d24",
            language="en",
            mock_decision=_build_decision(
                next_agent="facility",
                language="en",
                category="facility-info",
                request_type="wifi",
                confidence=0.95,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "WiFi is free. Please ask at the reception for the password.",
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Wave 7: anaphora resolution not yet implemented")
    async def test_d25_anaphora_needs_context(self):
        """D25: "それについてもう少し教えて" -> needs memory context

        Follow-up referencing previous context. Should NOT fast-path.
        """
        assert extract_request_type("それについてもう少し教えて") is None

        result = await _run_workflow(
            query="それについてもう少し教えて",
            session_id="scenario-d25",
            language="ja",
            mock_decision=_build_decision(
                next_agent="general_knowledge",
                category="memory",
                request_type="general",
                confidence=0.6,
                reasoning="Anaphora detected, requires memory context",
            ),
            agent_attr="_general_knowledge_agent",
            agent_response={
                "answer": "前の質問の続きですね。もう少し詳しく教えてください。",
                "emotion": "neutral",
                "metadata": {"agent": "GeneralKnowledgeAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_d26_floor_location_query(self):
        """D26: "ここは何階ですか？" -> facility with context

        Visitor disoriented in the multi-floor building.
        """
        result = await _run_workflow(
            query="ここは何階ですか？今いる場所は？",
            session_id="scenario-d26",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facility-info",
                request_type="general",
                confidence=0.85,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "こちらは1階のメインフロアです。受付と作業スペースがあります。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_d27_off_topic_weather(self):
        """D27: "明日の天気は？" -> polite rejection

        Visitor asking something unrelated to Engineer Cafe.
        """
        assert extract_request_type("明日の天気は？") is None

        result = await _run_workflow(
            query="明日の天気は？",
            session_id="scenario-d27",
            language="ja",
            mock_decision=_build_decision(
                next_agent="general_knowledge",
                category="general",
                request_type="general",
                confidence=0.3,
                reasoning="Off-topic query",
            ),
            agent_attr="_general_knowledge_agent",
            agent_response={
                "answer": (
                    "申し訳ございませんが、天気予報についてはお答えできません。"
                    "エンジニアカフェに関するご質問はいかがですか？"
                ),
                "emotion": "neutral",
                "metadata": {"agent": "GeneralKnowledgeAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_d28_emergency_fire(self):
        """D28: "火事だ！" -> emergency -> immediate guidance

        Emergency situation at the facility.
        """
        assert extract_request_type("火事だ！") == "emergency"

        result = await _run_workflow(
            query="火事だ！",
            session_id="scenario-d28",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="emergency",
                request_type="emergency",
                confidence=0.99,
                reasoning="Emergency keyword: fire",
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": (
                    "緊急事態です！すぐに119番に通報してください。"
                    "最寄りの非常口から避難してください。"
                ),
                "emotion": "urgent",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None


# =============================================================================
# E. Fast-Path Verification
# =============================================================================


class TestFastPathVerification:
    """Verify keyword-only queries are correctly classified by
    extract_request_type for fast-path routing."""

    def test_e29_wifi_fast_path_keyword(self):
        """E29: "WiFiパスワード" -> wifi (fast-path candidate)"""
        assert extract_request_type("WiFiパスワード") == "wifi"

    def test_e30_hours_fast_path_keyword(self):
        """E30: "営業時間" -> hours (fast-path candidate)"""
        assert extract_request_type("営業時間") == "hours"

    def test_e31_farewell_fast_path(self):
        """E31: "さようなら" -> farewell fast-path

        Visitor leaving. Triggers farewell with card return reminder.
        """
        assert extract_request_type("さようなら") == "farewell"

    def test_e32_wifi_complaint_still_matches_wifi(self):
        """E32: "WiFiの速度が遅いんですが" -> wifi keyword match

        Mentions WiFi but is a complaint. Keyword matcher returns "wifi"
        but orchestrator should distinguish simple vs complex queries.
        """
        assert extract_request_type("WiFiの速度が遅いんですが") == "wifi"

    def test_e33_emergency_keywords_take_priority(self):
        """Emergency keywords should take priority over other matches."""
        assert extract_request_type("地震だ！避難しないと") == "emergency"
        assert extract_request_type("AEDはどこですか？") == "emergency"

    def test_e34_farewell_variants(self):
        """Various farewell expressions should all route correctly."""
        assert extract_request_type("帰ります") == "farewell"
        assert extract_request_type("お先に失礼します") == "farewell"
        assert extract_request_type("bye") == "farewell"
        assert extract_request_type("goodbye") == "farewell"

    def test_e35_lost_and_found(self):
        """Lost item queries should route correctly."""
        assert extract_request_type("忘れ物をしました") == "lost_found"
        assert extract_request_type("I left my bag here") == "lost_found"

    def test_e36_no_match_returns_none(self):
        """Queries without keywords return None."""
        assert extract_request_type("それについてもう少し教えて") is None
        assert extract_request_type("明日の天気は？") is None
        assert extract_request_type("ありがとう") is None


# =============================================================================
# F. Multilingual (zh/ko)
# =============================================================================


class TestMultilingual:
    """Chinese and Korean visitor scenarios. Engineer Cafe Fukuoka
    attracts visitors from neighboring Asian countries."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Wave 7: zh/ko language detection not yet fully implemented")
    async def test_f33_chinese_wifi(self):
        """F33: "请问WiFi密码是什么？" (Chinese) -> WiFi answer in Chinese

        Chinese tourists visiting Fukuoka often stop by Engineer Cafe.
        """
        assert extract_request_type("请问WiFi密码是什么？") == "wifi"

        result = await _run_workflow(
            query="请问WiFi密码是什么？",
            session_id="scenario-f33",
            language="zh",
            mock_decision=_build_decision(
                next_agent="facility",
                language="zh",
                category="facility-info",
                request_type="wifi",
                confidence=0.95,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "WiFi是免费的。SSID: EngineerCafe_WiFi",
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert "WiFi" in result["answer"] or "wifi" in result["answer"].lower()

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Wave 7: zh/ko language detection not yet fully implemented")
    async def test_f34_korean_hours(self):
        """F34: "영업시간이 어떻게 되나요?" (Korean) -> hours in Korean"""
        result = await _run_workflow(
            query="영업시간이 어떻게 되나요?",
            session_id="scenario-f34",
            language="ko",
            mock_decision=_build_decision(
                next_agent="business_info",
                language="ko",
                category="business-hours",
                request_type="hours",
                confidence=0.90,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": "평일과 토요일은 9:00~22:00, 일요일과 공휴일은 9:00~20:00입니다.",
                "emotion": "neutral",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert "9:00" in result["answer"]


# =============================================================================
# G. Additional Realistic Scenarios (from routing_constants.py keywords)
# =============================================================================


class TestAdditionalRealisticScenarios:
    """Additional scenarios from routing_constants.py keyword lists
    representing real questions visitors ask at Engineer Cafe."""

    @pytest.mark.asyncio
    async def test_g35_parking(self):
        """G35: "駐車場はありますか？" -> facility -> parking

        From e2e_scenarios.json scn-008. No dedicated parking.
        """
        assert extract_request_type("駐車場はありますか？") == "parking"

        result = await _run_workflow(
            query="駐車場はありますか？",
            session_id="scenario-g35",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="parking",
                request_type="parking",
                confidence=0.95,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "専用駐車場はありません。近隣のコインパーキングをご利用ください。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g36_career_consultation(self):
        """G36: "転職を考えているのですが、相談できますか？" -> business_info -> consultation

        From e2e_scenarios.json scn-007. Community managers offer career
        counseling.
        """
        assert extract_request_type("転職を考えているのですが、相談できますか？") == "consultation"

        result = await _run_workflow(
            query="転職を考えているのですが、相談できますか？",
            session_id="scenario-g36",
            language="ja",
            mock_decision=_build_decision(
                next_agent="business_info",
                category="consultation",
                request_type="consultation",
                confidence=0.92,
            ),
            agent_attr="_business_info_agent",
            agent_response={
                "answer": (
                    "コミュニティマネージャーにキャリア相談ができます。受付でお声がけください。"
                ),
                "emotion": "happy",
                "metadata": {"agent": "BusinessInfoAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g37_food_and_drink(self):
        """G37: "飲食は持ち込めますか？" -> facility -> food_drink

        Saino Cafe is on 1F for drinks.
        """
        assert extract_request_type("飲食は持ち込めますか？") == "food_drink"

        result = await _run_workflow(
            query="飲食は持ち込めますか？",
            session_id="scenario-g37",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="food_drink",
                request_type="food_drink",
                confidence=0.93,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": (
                    "蓋つきの飲み物は持ち込み可能です。"
                    "1FのSaino Cafeでドリンクもお求めいただけます。"
                ),
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g38_smoking(self):
        """G38: "喫煙所はありますか？" -> facility -> smoking

        Building is non-smoking.
        """
        assert extract_request_type("喫煙所はありますか？") == "smoking"

        result = await _run_workflow(
            query="喫煙所はありますか？",
            session_id="scenario-g38",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="smoking",
                request_type="smoking",
                confidence=0.95,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "館内は全面禁煙です。近隣の喫煙所をご案内いたします。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g39_bicycle_parking(self):
        """G39: "自転車で来たのですが、駐輪場はありますか？" -> facility -> bicycle

        Cycling is common in Fukuoka.
        """
        assert extract_request_type("自転車で来たのですが、駐輪場はありますか？") == "bicycle"

        result = await _run_workflow(
            query="自転車で来たのですが、駐輪場はありますか？",
            session_id="scenario-g39",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="bicycle",
                request_type="bicycle",
                confidence=0.93,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "建物の近くに駐輪スペースがあります。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g40_building_history(self):
        """G40: "この建物の歴史を教えてください" -> facility -> building

        The Akarenga Cultural Hall was built in 1909 by Tatsuno Kingo.
        Registered Important Cultural Property.
        """
        assert extract_request_type("この建物の歴史を教えてください") == "building"

        result = await _run_workflow(
            query="この建物の歴史を教えてください",
            session_id="scenario-g40",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facility-info",
                request_type="building",
                confidence=0.90,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": (
                    "この建物は1909年（明治42年）に建設された赤煉瓦文化館です。"
                    "国の重要文化財に指定されています。"
                ),
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g41_nearby_lunch(self):
        """G41: "近くにランチできる場所はありますか？" -> facility -> nearby"""
        assert extract_request_type("近くにランチできる場所はありますか？") == "nearby"

        result = await _run_workflow(
            query="近くにランチできる場所はありますか？",
            session_id="scenario-g41",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="nearby",
                request_type="nearby",
                confidence=0.90,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "周辺にはレストランやカフェが多数あります。中洲エリアが近いです。",
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g42_accessibility(self):
        """G42: "車椅子で入れますか？" -> facility -> accessibility"""
        assert extract_request_type("車椅子で入れますか？") == "accessibility"

        result = await _run_workflow(
            query="車椅子で入れますか？",
            session_id="scenario-g42",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="policy",
                request_type="accessibility",
                confidence=0.92,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "エレベーターがありますので、車椅子でもご利用いただけます。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g43_lost_item(self):
        """G43: "忘れ物をしたのですが" -> facility -> lost_found"""
        assert extract_request_type("忘れ物をしたのですが") == "lost_found"

        result = await _run_workflow(
            query="忘れ物をしたのですが",
            session_id="scenario-g43",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="lost_found",
                request_type="lost_found",
                confidence=0.95,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": "忘れ物については受付スタッフにお問い合わせください。",
                "emotion": "neutral",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_g44_3d_printer(self):
        """G44: "3Dプリンターは使えますか？" -> facility -> equipment

        From e2e_scenarios.json scn-002. MAKER's space has 3D printers.
        """
        assert extract_request_type("3Dプリンターは使えますか？") == "facility"

        result = await _run_workflow(
            query="3Dプリンターは使えますか？",
            session_id="scenario-g44",
            language="ja",
            mock_decision=_build_decision(
                next_agent="facility",
                category="facilities",
                request_type="facility",
                confidence=0.92,
            ),
            agent_attr="_facility_agent",
            agent_response={
                "answer": (
                    "地下のMAKER'sスペースで3Dプリンターをご利用いただけます。"
                    "フィラメント代は実費負担となります。"
                ),
                "emotion": "happy",
                "metadata": {"agent": "FacilityAgent", "status": "success"},
            },
        )

        assert result["answer"] is not None
