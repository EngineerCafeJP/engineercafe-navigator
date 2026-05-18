"""Pydantic schemas for the knowledge API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=50000)
    category: str
    language: str = Field(default="ja", pattern=r"^(ja|en)$")
    subcategory: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, max_length=50000)
    category: Optional[str] = None
    language: Optional[str] = Field(None, pattern=r"^(ja|en)$")
    subcategory: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeItem(BaseModel):
    id: str
    title: str
    content: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    language: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class KnowledgeListResponse(BaseModel):
    success: bool
    data: List[KnowledgeItem]
    total: int
    page: int
    limit: int


class KnowledgeResponse(BaseModel):
    success: bool
    data: Optional[KnowledgeItem] = None
    error: Optional[str] = None


class KnowledgeCategoriesStats(BaseModel):
    totalCategories: int
    totalSubcategories: int
    totalSources: int
    totalLanguages: int


class KnowledgeCategoriesResponse(BaseModel):
    categories: List[str]
    subcategories: Dict[str, List[str]]
    sources: List[str]
    languages: List[str]
    stats: KnowledgeCategoriesStats
