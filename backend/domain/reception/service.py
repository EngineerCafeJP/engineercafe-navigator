"""Reception Domain Service.

Pure domain logic for the reception flow with no infrastructure dependencies.
Handles visitor type determination and purpose-to-agent mapping.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.domain.reception.models import VisitPurpose, VisitorType

logger = logging.getLogger(__name__)

# Purpose category to agent name mapping
_PURPOSE_AGENT_MAPPING: dict[str, str] = {
    "facility_use": "facility",
    "event_participation": "event",
    "tour": "slide",
    "consultation": "general_knowledge",
    "other": "general_knowledge",
}


class ReceptionDomainService:
    """Domain logic for the reception flow.

    Contains pure business rules for visitor classification and
    agent routing. Has no infrastructure dependencies.
    """

    FIRST_TIME_KEYWORDS_JA: list[str] = ["初めて", "はじめて", "初回", "初利用"]
    FIRST_TIME_KEYWORDS_EN: list[str] = ["first time", "first visit", "never been"]

    def determine_visitor_type(
        self,
        query: str,
        language: str,
        long_term_memories: list,
        user_id: Optional[int] = None,
    ) -> VisitorType:
        """Determine if a visitor is new or returning based on available signals.

        Uses a priority-based approach:
        1. Explicit "first time" keywords in the query override everything.
        2. A database user record or existing long-term memories indicate returning.
        3. Otherwise, assume new visitor.

        Args:
            query: The visitor's spoken or typed input.
            language: The interaction language ("ja" or "en").
            long_term_memories: List of long-term memory entries for this visitor.
            user_id: Database user ID if the visitor has been identified.

        Returns:
            A VisitorType value object indicating "new" or "returning".
        """
        lower_query = query.lower()

        # Explicit "first time" keywords override everything
        keywords = self.FIRST_TIME_KEYWORDS_JA if language == "ja" else self.FIRST_TIME_KEYWORDS_EN
        if any(kw in lower_query for kw in keywords):
            return VisitorType(value="new")

        # DB user record or long-term memories indicate returning
        if user_id or long_term_memories:
            return VisitorType(value="returning")

        return VisitorType(value="new")

    def map_purpose_to_agent(self, purpose: VisitPurpose) -> str:
        """Map a visit purpose to the appropriate agent for handoff.

        Args:
            purpose: The visitor's stated visit purpose.

        Returns:
            The name of the agent that should handle this purpose.
        """
        return _PURPOSE_AGENT_MAPPING.get(purpose.category, "general_knowledge")
