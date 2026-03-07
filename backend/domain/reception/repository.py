"""Reception Repository Interfaces.

Abstract base classes defining the persistence contracts for the reception domain.
Concrete implementations are provided by the infrastructure layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.domain.reception.models import ReceptionSession


class ReceptionSessionRepository(ABC):
    """Repository interface for ReceptionSession aggregate persistence.

    Implementations must handle saving and retrieving ReceptionSession
    aggregates from the chosen storage backend.
    """

    @abstractmethod
    async def save(self, session: ReceptionSession) -> None:
        """Persist a reception session.

        Args:
            session: The reception session to save.
        """
        ...

    @abstractmethod
    async def find_by_id(self, session_id: str) -> Optional[ReceptionSession]:
        """Find a reception session by its unique ID.

        Args:
            session_id: The reception session's unique identifier.

        Returns:
            The reception session if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_by_conversation_session(
        self, conversation_session_id: str
    ) -> Optional[ReceptionSession]:
        """Find a reception session by its associated conversation session ID.

        Args:
            conversation_session_id: The conversation session identifier.

        Returns:
            The reception session if found, None otherwise.
        """
        ...


class VisitRepository(ABC):
    """Repository interface for visit record persistence.

    Implementations handle recording completed visits and querying
    visit history for returning visitors.
    """

    @abstractmethod
    async def record_visit(self, session: ReceptionSession) -> str:
        """Record a completed visit from a reception session.

        Args:
            session: The completed reception session.

        Returns:
            The unique identifier of the created visit record.
        """
        ...

    @abstractmethod
    async def get_recent_visits(self, user_id: int, limit: int = 5) -> list:
        """Get recent visits for a registered user.

        Args:
            user_id: The user's database ID.
            limit: Maximum number of visits to return.

        Returns:
            A list of recent visit records, most recent first.
        """
        ...
