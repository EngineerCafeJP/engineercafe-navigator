"""Tests for the Reception Domain Layer.

Covers value object immutability, aggregate root stage transitions,
domain event emission, and domain service logic.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from backend.domain.reception.events import (
    AgentHandoffRequested,
    PurposeIdentified,
    StaffEscalationRequested,
    VisitorIdentified,
)
from backend.domain.reception.models import (
    ReceptionSession,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.domain.reception.service import ReceptionDomainService

# =============================================================================
# Value Object Immutability Tests
# =============================================================================


class TestVisitorType:
    """Tests for VisitorType value object."""

    def test_create_new_visitor_type(self) -> None:
        vt = VisitorType(value="new")
        assert vt.value == "new"

    def test_create_returning_visitor_type(self) -> None:
        vt = VisitorType(value="returning")
        assert vt.value == "returning"

    def test_immutability(self) -> None:
        vt = VisitorType(value="new")
        with pytest.raises(FrozenInstanceError):
            vt.value = "returning"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert VisitorType(value="new") == VisitorType(value="new")
        assert VisitorType(value="new") != VisitorType(value="returning")


class TestVisitPurpose:
    """Tests for VisitPurpose value object."""

    def test_create_with_category_only(self) -> None:
        purpose = VisitPurpose(category="facility_use")
        assert purpose.category == "facility_use"
        assert purpose.detail is None

    def test_create_with_detail(self) -> None:
        purpose = VisitPurpose(category="event_participation", detail="Python meetup")
        assert purpose.category == "event_participation"
        assert purpose.detail == "Python meetup"

    def test_immutability(self) -> None:
        purpose = VisitPurpose(category="tour")
        with pytest.raises(FrozenInstanceError):
            purpose.category = "other"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = VisitPurpose(category="tour", detail="facility tour")
        b = VisitPurpose(category="tour", detail="facility tour")
        c = VisitPurpose(category="tour", detail="different")
        assert a == b
        assert a != c


class TestVisitorIdentity:
    """Tests for VisitorIdentity value object."""

    def test_create_minimal(self) -> None:
        identity = VisitorIdentity(visitor_type=VisitorType(value="new"))
        assert identity.visitor_type.value == "new"
        assert identity.user_id is None
        assert identity.name is None
        assert identity.visit_count == 0

    def test_create_full(self) -> None:
        now = datetime.now()
        purpose = VisitPurpose(category="facility_use")
        identity = VisitorIdentity(
            visitor_type=VisitorType(value="returning"),
            user_id=42,
            name="Tanaka",
            last_visit_date=now,
            last_purpose=purpose,
            visit_count=5,
        )
        assert identity.user_id == 42
        assert identity.name == "Tanaka"
        assert identity.last_visit_date == now
        assert identity.last_purpose == purpose
        assert identity.visit_count == 5

    def test_immutability(self) -> None:
        identity = VisitorIdentity(visitor_type=VisitorType(value="new"))
        with pytest.raises(FrozenInstanceError):
            identity.name = "Modified"  # type: ignore[misc]


# =============================================================================
# Aggregate Root Tests
# =============================================================================


class TestReceptionSession:
    """Tests for ReceptionSession aggregate root."""

    def test_default_creation(self) -> None:
        session = ReceptionSession()
        assert session.stage == "initiated"
        assert session.language == "ja"
        assert session.trigger_type == "button_press"
        assert session.visitor_identity is None
        assert session.purpose is None
        assert len(session.id) > 0

    def test_custom_creation(self) -> None:
        session = ReceptionSession(
            session_id="conv-123",
            language="en",
            trigger_type="face_detection",
        )
        assert session.session_id == "conv-123"
        assert session.language == "en"
        assert session.trigger_type == "face_detection"

    # -------------------------------------------------------------------------
    # Stage Transition Tests
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "from_stage,to_stage",
        [
            ("initiated", "greeting"),
            ("initiated", "identifying"),
            ("greeting", "identifying"),
            ("greeting", "purpose_hearing"),
            ("identifying", "greeting"),
            ("identifying", "purpose_hearing"),
            ("purpose_hearing", "routing"),
            ("routing", "completed"),
            ("routing", "escalated"),
        ],
    )
    def test_valid_transitions(self, from_stage: str, to_stage: str) -> None:
        session = ReceptionSession()
        session.stage = from_stage  # Set starting stage directly for test
        session.advance_to(to_stage)
        assert session.stage == to_stage

    @pytest.mark.parametrize(
        "from_stage,to_stage",
        [
            ("initiated", "completed"),
            ("initiated", "routing"),
            ("initiated", "purpose_hearing"),
            ("greeting", "completed"),
            ("greeting", "routing"),
            ("identifying", "completed"),
            ("identifying", "routing"),
            ("purpose_hearing", "completed"),
            ("purpose_hearing", "greeting"),
            ("routing", "greeting"),
            ("routing", "identifying"),
            ("completed", "initiated"),
            ("escalated", "initiated"),
        ],
    )
    def test_invalid_transitions(self, from_stage: str, to_stage: str) -> None:
        session = ReceptionSession()
        session.stage = from_stage
        with pytest.raises(ValueError, match="Invalid transition"):
            session.advance_to(to_stage)

    def test_transition_sequence_full_flow(self) -> None:
        """Test a complete happy-path reception flow."""
        session = ReceptionSession()
        assert session.stage == "initiated"

        session.advance_to("greeting")
        assert session.stage == "greeting"

        session.advance_to("identifying")
        assert session.stage == "identifying"

        session.advance_to("purpose_hearing")
        assert session.stage == "purpose_hearing"

        session.advance_to("routing")
        assert session.stage == "routing"

        session.advance_to("completed")
        assert session.stage == "completed"

    # -------------------------------------------------------------------------
    # Domain Event Tests
    # -------------------------------------------------------------------------

    def test_identify_visitor_emits_event(self) -> None:
        session = ReceptionSession()
        identity = VisitorIdentity(visitor_type=VisitorType(value="new"))

        session.identify_visitor(identity)

        assert session.visitor_identity == identity
        events = session.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], VisitorIdentified)
        assert events[0].reception_session_id == session.id
        assert events[0].visitor_identity == identity

    def test_set_purpose_emits_event(self) -> None:
        session = ReceptionSession()
        purpose = VisitPurpose(category="tour", detail="facility tour")

        session.set_purpose(purpose)

        assert session.purpose == purpose
        events = session.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PurposeIdentified)
        assert events[0].reception_session_id == session.id
        assert events[0].purpose == purpose

    def test_request_handoff_emits_event(self) -> None:
        session = ReceptionSession()
        context = {"purpose": "tour", "language": "ja"}

        session.request_handoff("slide", context)

        events = session.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], AgentHandoffRequested)
        assert events[0].target_agent == "slide"
        assert events[0].context == context

    def test_request_escalation_emits_event_and_sets_stage(self) -> None:
        session = ReceptionSession()
        identity = VisitorIdentity(
            visitor_type=VisitorType(value="returning"),
            name="Tanaka",
        )
        session.visitor_identity = identity

        session.request_escalation("Visitor requested human staff")

        assert session.stage == "escalated"
        events = session.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], StaffEscalationRequested)
        assert events[0].reason == "Visitor requested human staff"
        assert events[0].visitor_name == "Tanaka"

    def test_request_escalation_without_identity(self) -> None:
        session = ReceptionSession()
        session.request_escalation("Unknown issue")

        events = session.collect_events()
        assert len(events) == 1
        assert events[0].visitor_name is None

    def test_collect_events_clears_pending(self) -> None:
        session = ReceptionSession()
        session.set_purpose(VisitPurpose(category="tour"))

        first = session.collect_events()
        assert len(first) == 1

        second = session.collect_events()
        assert len(second) == 0

    def test_multiple_events_accumulate(self) -> None:
        session = ReceptionSession()
        identity = VisitorIdentity(visitor_type=VisitorType(value="new"))
        purpose = VisitPurpose(category="facility_use")

        session.identify_visitor(identity)
        session.set_purpose(purpose)
        session.request_handoff("facility", {"language": "ja"})

        events = session.collect_events()
        assert len(events) == 3
        assert isinstance(events[0], VisitorIdentified)
        assert isinstance(events[1], PurposeIdentified)
        assert isinstance(events[2], AgentHandoffRequested)


# =============================================================================
# Domain Service Tests
# =============================================================================


class TestReceptionDomainService:
    """Tests for ReceptionDomainService."""

    @pytest.fixture()
    def service(self) -> ReceptionDomainService:
        return ReceptionDomainService()

    # -------------------------------------------------------------------------
    # determine_visitor_type
    # -------------------------------------------------------------------------

    def test_first_time_keyword_ja(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="初めて来ました",
            language="ja",
            long_term_memories=[],
        )
        assert result.value == "new"

    def test_first_time_keyword_ja_hajimete(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="はじめて来ました",
            language="ja",
            long_term_memories=[],
        )
        assert result.value == "new"

    def test_first_time_keyword_en(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="This is my first time here",
            language="en",
            long_term_memories=[],
        )
        assert result.value == "new"

    def test_first_time_keyword_overrides_user_id(self, service: ReceptionDomainService) -> None:
        """First-time keywords should override even if user_id exists."""
        result = service.determine_visitor_type(
            query="初めて来ました",
            language="ja",
            long_term_memories=[{"some": "memory"}],
            user_id=42,
        )
        assert result.value == "new"

    def test_returning_by_user_id(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="こんにちは",
            language="ja",
            long_term_memories=[],
            user_id=42,
        )
        assert result.value == "returning"

    def test_returning_by_memories(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="hello",
            language="en",
            long_term_memories=[{"previous_visit": "2024-01-01"}],
        )
        assert result.value == "returning"

    def test_default_new_visitor(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="こんにちは",
            language="ja",
            long_term_memories=[],
        )
        assert result.value == "new"

    def test_case_insensitive_en(self, service: ReceptionDomainService) -> None:
        result = service.determine_visitor_type(
            query="FIRST TIME visiting",
            language="en",
            long_term_memories=[],
        )
        assert result.value == "new"

    # -------------------------------------------------------------------------
    # map_purpose_to_agent
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "category,expected_agent",
        [
            ("facility_use", "facility"),
            ("event_participation", "event"),
            ("tour", "slide"),
            ("consultation", "general_knowledge"),
            ("other", "general_knowledge"),
        ],
    )
    def test_map_purpose_to_agent(
        self,
        service: ReceptionDomainService,
        category: str,
        expected_agent: str,
    ) -> None:
        purpose = VisitPurpose(category=category)
        assert service.map_purpose_to_agent(purpose) == expected_agent
