"""Bridge between ReceptionWorkflow and MainWorkflow.

Transforms a completed ReceptionSession into the state dict expected by
MainWorkflow, optionally enriched by PurposeFlowService preprocessing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from backend.domain.reception.models import ReceptionSession, VisitPurpose, VisitorIdentity
from backend.services.purpose_flow_service import PurposeFlowResult, PurposeFlowService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandoffResult:
    """Result of preparing a reception-to-main-workflow handoff.

    Attributes:
        workflow_state: Dict compatible with WorkflowStateDict for MainWorkflow.
        target_agent: The MainWorkflow agent node to route to.
        purpose_flow: The PurposeFlowResult from purpose-specific preprocessing.
        requires_staff: Whether the visitor needs staff escalation.
    """

    workflow_state: dict[str, Any]
    target_agent: str
    purpose_flow: PurposeFlowResult
    requires_staff: bool


class ReceptionHandoffService:
    """Prepare the handoff from ReceptionWorkflow to MainWorkflow.

    This service is a pure transformer: it takes a completed ReceptionSession,
    runs purpose-specific preprocessing via PurposeFlowService, and builds
    the WorkflowStateDict that MainWorkflow expects.
    """

    def __init__(
        self,
        purpose_flow_service: Optional[PurposeFlowService] = None,
    ) -> None:
        self._purpose_flow = purpose_flow_service or PurposeFlowService()

    async def prepare_handoff(
        self,
        session: ReceptionSession,
    ) -> HandoffResult:
        """Transform a completed ReceptionSession into a MainWorkflow state.

        Args:
            session: A ReceptionSession that has reached the 'routing' or
                'completed' stage with purpose and visitor_identity set.

        Returns:
            A HandoffResult containing the workflow state dict and routing info.

        Raises:
            ValueError: If the session is missing purpose or visitor_identity.
        """
        if session.purpose is None:
            raise ValueError(f"Cannot hand off session {session.id}: purpose not set")
        if session.visitor_identity is None:
            raise ValueError(f"Cannot hand off session {session.id}: visitor_identity not set")

        purpose: VisitPurpose = session.purpose
        identity: VisitorIdentity = session.visitor_identity

        # Run purpose-specific preprocessing
        purpose_flow_result = await self._purpose_flow.resolve(
            purpose=purpose,
            language=session.language,
            session_id=session.session_id,
            visitor_identity=identity,
        )

        # Use the target agent from PurposeFlowService (single source of truth)
        target_agent = purpose_flow_result.target_agent

        # Build the WorkflowStateDict-compatible state
        workflow_state = self._build_workflow_state(
            session=session,
            purpose=purpose,
            identity=identity,
            purpose_flow_result=purpose_flow_result,
            target_agent=target_agent,
        )

        logger.info(
            "Handoff prepared: session=%s purpose=%s target=%s requires_staff=%s",
            session.id,
            purpose.category,
            target_agent,
            purpose_flow_result.requires_staff,
        )

        return HandoffResult(
            workflow_state=workflow_state,
            target_agent=target_agent,
            purpose_flow=purpose_flow_result,
            requires_staff=purpose_flow_result.requires_staff,
        )

    def _build_workflow_state(
        self,
        session: ReceptionSession,
        purpose: VisitPurpose,
        identity: VisitorIdentity,
        purpose_flow_result: PurposeFlowResult,
        target_agent: str,
    ) -> dict[str, Any]:
        """Build a dict compatible with WorkflowStateDict."""
        # Construct query from purpose detail or a synthetic description
        query = purpose.detail or self._synthetic_query(purpose, session.language)

        return {
            "messages": [],
            "query": query,
            "session_id": session.session_id,
            "language": session.language,
            "routing": {
                "agent": target_agent,
                "category": purpose.category,
                "request_type": purpose_flow_result.action_type,
                "confidence": 1.0,
                "reasoning": "Routed from autonomous reception flow",
                "debug_info": {},
            },
            "answer": None,
            "emotion": None,
            "metadata": {
                "reception_session_id": session.id,
                "reception_handoff": True,
                "visitor_type": identity.visitor_type.value,
                "purpose_category": purpose.category,
                "purpose_detail": purpose.detail,
                "purpose_flow_action": purpose_flow_result.action_type,
                "purpose_flow_data": purpose_flow_result.action_data,
                "requires_staff": purpose_flow_result.requires_staff,
            },
            "context": {
                "reception_context": {
                    "visitor_name": identity.name,
                    "visitor_type": identity.visitor_type.value,
                    "visit_count": identity.visit_count,
                    "purpose_response_text": purpose_flow_result.response_text,
                },
            },
            "image_data": None,
            "ocr_result": None,
        }

    def _synthetic_query(self, purpose: VisitPurpose, language: str) -> str:
        """Generate a synthetic query when no detail text is available."""
        queries: dict[str, dict[str, str]] = {
            "facility_use": {
                "ja": "施設を利用したいです",
                "en": "I'd like to use the facility",
                "zh": "我想使用设施",
                "ko": "시설을 이용하고 싶습니다",
            },
            "event_participation": {
                "ja": "イベントに参加したいです",
                "en": "I'd like to attend an event",
                "zh": "我想参加活动",
                "ko": "이벤트에 참가하고 싶습니다",
            },
            "tour": {
                "ja": "館内ツアーをお願いします",
                "en": "I'd like a facility tour",
                "zh": "我想参观馆内",
                "ko": "투어를 부탁드립니다",
            },
            "consultation": {
                "ja": "相談したいことがあります",
                "en": "I'd like to consult about something",
                "zh": "我想咨询一些事情",
                "ko": "상담하고 싶은 것이 있습니다",
            },
            "other": {
                "ja": "用件があります",
                "en": "I have a request",
                "zh": "我有事要办",
                "ko": "용건이 있습니다",
            },
        }
        category_queries = queries.get(purpose.category, queries["other"])
        return category_queries.get(language, category_queries["ja"])
