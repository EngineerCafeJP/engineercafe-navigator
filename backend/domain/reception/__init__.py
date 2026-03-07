"""Reception Domain Package - DDD models, events, and services for autonomous reception flow."""

from __future__ import annotations

from backend.domain.reception.events import (
    AgentHandoffRequested,
    PurposeIdentified,
    StaffEscalationRequested,
    VisitStarted,
    VisitorDetected,
    VisitorIdentified,
)
from backend.domain.reception.models import (
    ReceptionSession,
    ReceptionStage,
    VisitPurpose,
    VisitorIdentity,
    VisitorType,
)
from backend.domain.reception.repository import (
    ReceptionSessionRepository,
    VisitRepository,
)
from backend.domain.reception.service import ReceptionDomainService

__all__ = [
    # Models
    "VisitorType",
    "VisitPurpose",
    "VisitorIdentity",
    "ReceptionStage",
    "ReceptionSession",
    # Events
    "VisitorDetected",
    "VisitorIdentified",
    "PurposeIdentified",
    "AgentHandoffRequested",
    "StaffEscalationRequested",
    "VisitStarted",
    # Repository interfaces
    "ReceptionSessionRepository",
    "VisitRepository",
    # Services
    "ReceptionDomainService",
]
