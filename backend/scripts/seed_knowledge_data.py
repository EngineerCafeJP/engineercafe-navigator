"""Static seed entries for the knowledge-base seeding script."""

from __future__ import annotations

try:
    from backend.scripts.seed_knowledge_data_part1 import KNOWLEDGE_BASE_DATA_PART_1
    from backend.scripts.seed_knowledge_data_part2 import KNOWLEDGE_BASE_DATA_PART_2
except ImportError:  # pragma: no cover - supports `python -m scripts...` from backend/
    from scripts.seed_knowledge_data_part1 import KNOWLEDGE_BASE_DATA_PART_1
    from scripts.seed_knowledge_data_part2 import KNOWLEDGE_BASE_DATA_PART_2

KNOWLEDGE_BASE_DATA = KNOWLEDGE_BASE_DATA_PART_1 + KNOWLEDGE_BASE_DATA_PART_2
