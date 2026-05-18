from __future__ import annotations

from typing import Dict, Optional

from backend.agents.facility.canonical_part1 import facility_canonical_part1
from backend.agents.facility.canonical_part2 import facility_canonical_part2


class FacilityCanonicalMixin:
    def _get_canonical_response(
        self, query: str, request_type: Optional[str], language: str
    ) -> Optional[Dict]:
        """Return complete answers for common visitor-critical facility questions."""
        normalized = query.lower()
        for resolver in (facility_canonical_part1, facility_canonical_part2):
            result = resolver(self, normalized, request_type, language)
            if result:
                return result
        return None
