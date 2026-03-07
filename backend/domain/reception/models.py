"""Reception Domain Models - DDD Value Objects and Aggregate Root.

This module defines the core domain model for the autonomous reception flow,
following Domain-Driven Design principles with immutable value objects and
an aggregate root that enforces business invariants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from backend.domain.reception.events import (
    AgentHandoffRequested,
    PurposeIdentified,
    StaffEscalationRequested,
    VisitorIdentified,
)

# =============================================================================
# Value Objects (frozen=True for immutability)
# =============================================================================


@dataclass(frozen=True)
class VisitorType:
    """Classifies a visitor as new or returning.

    Attributes:
        value: Whether the visitor is new or returning.
    """

    value: Literal["new", "returning"]


@dataclass(frozen=True)
class VisitPurpose:
    """Represents a visitor's stated purpose for visiting.

    Attributes:
        category: The broad category of the visit purpose.
        detail: Optional free-text detail about the purpose.
    """

    category: Literal["facility_use", "event_participation", "tour", "consultation", "other"]
    detail: Optional[str] = None


@dataclass(frozen=True)
class VisitorIdentity:
    """Result of visitor identification, combining detection signals.

    Attributes:
        visitor_type: Whether the visitor is new or returning.
        user_id: Database user ID if the visitor is registered.
        name: The visitor's name if known.
        last_visit_date: When the visitor last visited, if returning.
        last_purpose: The purpose of the visitor's last visit.
        visit_count: Total number of previous visits.
    """

    visitor_type: VisitorType
    user_id: Optional[int] = None
    name: Optional[str] = None
    last_visit_date: Optional[datetime] = None
    last_purpose: Optional[VisitPurpose] = None
    visit_count: int = 0


# =============================================================================
# Reception Stage Type
# =============================================================================

ReceptionStage = Literal[
    "initiated",
    "greeting",
    "identifying",
    "purpose_hearing",
    "routing",
    "completed",
    "escalated",
]

# =============================================================================
# Aggregate Root
# =============================================================================

# Valid stage transitions for the reception flow state machine
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "initiated": {"greeting", "identifying", "escalated"},
    "greeting": {"identifying", "purpose_hearing", "escalated"},
    "identifying": {"greeting", "purpose_hearing", "escalated"},
    "purpose_hearing": {"routing", "escalated"},
    "routing": {"completed", "escalated"},
}


@dataclass
class ReceptionSession:
    """Aggregate root for the autonomous reception flow.

    Manages the lifecycle of a single reception interaction, enforcing
    valid stage transitions and collecting domain events.

    Attributes:
        id: Unique identifier for this reception session.
        session_id: Associated conversation session ID.
        visitor_identity: Resolved visitor identity, if identified.
        purpose: The visitor's stated purpose, if determined.
        stage: Current stage in the reception flow.
        language: Language for the interaction.
        trigger_type: How the reception was initiated.
        created_at: When this session was created.
        metadata: Arbitrary key-value metadata.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    visitor_identity: Optional[VisitorIdentity] = None
    purpose: Optional[VisitPurpose] = None
    stage: ReceptionStage = "initiated"
    language: Literal["ja", "en", "zh", "ko"] = "ja"
    trigger_type: Literal["face_detection", "button_press", "wake_word", "nfc"] = "button_press"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    _events: list = field(default_factory=list, repr=False)

    def advance_to(self, stage: ReceptionStage) -> None:
        """Advance the reception flow to a new stage.

        Validates that the transition is allowed by the state machine
        before applying it.

        Args:
            stage: The target stage to transition to.

        Raises:
            ValueError: If the transition from the current stage to the
                target stage is not allowed.
        """
        allowed = _VALID_TRANSITIONS.get(self.stage, set())
        if stage not in allowed:
            raise ValueError(f"Invalid transition: {self.stage} -> {stage}")
        self.stage = stage

    def identify_visitor(self, identity: VisitorIdentity) -> None:
        """Record the result of visitor identification.

        Args:
            identity: The resolved visitor identity.
        """
        self.visitor_identity = identity
        self._events.append(
            VisitorIdentified(
                reception_session_id=self.id,
                visitor_identity=identity,
            )
        )

    def set_purpose(self, purpose: VisitPurpose) -> None:
        """Record the visitor's stated purpose.

        Args:
            purpose: The resolved visit purpose.
        """
        self.purpose = purpose
        self._events.append(
            PurposeIdentified(
                reception_session_id=self.id,
                purpose=purpose,
            )
        )

    def request_handoff(self, target_agent: str, context: dict) -> None:
        """Request handoff to a specialized agent.

        Args:
            target_agent: The name of the agent to hand off to.
            context: Contextual information for the target agent.
        """
        self._events.append(
            AgentHandoffRequested(
                reception_session_id=self.id,
                target_agent=target_agent,
                context=context,
            )
        )

    def request_escalation(self, reason: str) -> None:
        """Escalate to human staff.

        Sets the stage to 'escalated' and emits a StaffEscalationRequested event.

        Args:
            reason: Why escalation is needed.
        """
        self.advance_to("escalated")
        self._events.append(
            StaffEscalationRequested(
                reception_session_id=self.id,
                reason=reason,
                visitor_name=self.visitor_identity.name if self.visitor_identity else None,
            )
        )

    def collect_events(self) -> list:
        """Collect and clear all pending domain events.

        Returns:
            A list of domain events that have been emitted since the last
            call to collect_events.
        """
        events = list(self._events)
        self._events.clear()
        return events
