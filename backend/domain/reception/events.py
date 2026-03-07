"""Reception Domain Events.

Domain events emitted during the autonomous reception flow.
These events represent significant state changes that other parts
of the system may need to react to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass(frozen=True)
class VisitorDetected:
    """Event emitted when a visitor is detected at the entrance.

    Attributes:
        trigger_type: The detection mechanism that identified the visitor.
        timestamp: When the detection occurred.
        nfc_id: Optional NFC card identifier if detected via NFC.
    """

    trigger_type: Literal["face_detection", "button_press", "wake_word", "nfc"]
    timestamp: datetime
    nfc_id: Optional[str] = None


@dataclass(frozen=True)
class VisitorIdentified:
    """Event emitted when a visitor's identity has been determined.

    Attributes:
        reception_session_id: The reception session this event belongs to.
        visitor_identity: The resolved visitor identity (VisitorIdentity value object).
    """

    reception_session_id: str
    visitor_identity: object  # VisitorIdentity (avoid circular import)


@dataclass(frozen=True)
class PurposeIdentified:
    """Event emitted when a visitor's purpose has been determined.

    Attributes:
        reception_session_id: The reception session this event belongs to.
        purpose: The resolved visit purpose (VisitPurpose value object).
    """

    reception_session_id: str
    purpose: object  # VisitPurpose


@dataclass(frozen=True)
class AgentHandoffRequested:
    """Event emitted when the reception flow hands off to a specialized agent.

    Attributes:
        reception_session_id: The reception session this event belongs to.
        target_agent: The name of the agent to hand off to.
        context: Contextual information for the target agent.
    """

    reception_session_id: str
    target_agent: str
    context: dict


@dataclass(frozen=True)
class StaffEscalationRequested:
    """Event emitted when human staff intervention is needed.

    Attributes:
        reception_session_id: The reception session this event belongs to.
        reason: Why escalation is needed.
        visitor_name: The visitor's name if known.
    """

    reception_session_id: str
    reason: str
    visitor_name: Optional[str] = None


@dataclass(frozen=True)
class VisitStarted:
    """Event emitted when a visit has been officially recorded.

    Attributes:
        visit_id: The unique identifier for this visit record.
        user_id: The visitor's user ID if known.
        purpose: The visit purpose (VisitPurpose value object).
    """

    visit_id: str
    user_id: Optional[int]
    purpose: object  # VisitPurpose
