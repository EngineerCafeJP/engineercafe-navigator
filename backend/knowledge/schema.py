"""YAML-based knowledge entry schema (Pydantic v2)."""

from typing import List, Optional

from pydantic import BaseModel, Field


class KnowledgeEntry(BaseModel):
    """Single knowledge entry."""

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$", description="Unique entry ID")
    title: str = Field(..., min_length=1, max_length=200)
    title_en: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    content_en: Optional[str] = Field(None, max_length=5000)
    category: str = Field(..., min_length=1)
    subcategory: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=100)
    source: Optional[str] = None
    verified: bool = False

    model_config = {"frozen": True, "extra": "forbid"}


class KnowledgeSection(BaseModel):
    """A section of knowledge entries (maps to a single YAML file)."""

    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    description: Optional[str] = None
    entries: List[KnowledgeEntry] = Field(..., min_length=1)

    model_config = {"frozen": True, "extra": "forbid"}

    def get_entry(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """Get entry by ID."""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def get_by_category(self, category: str) -> List[KnowledgeEntry]:
        """Get entries by category."""
        return [e for e in self.entries if e.category == category]

    @property
    def categories(self) -> List[str]:
        """Get unique categories."""
        return sorted(set(e.category for e in self.entries))
