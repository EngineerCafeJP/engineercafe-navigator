"""Tests for knowledge schema (Pydantic v2 models)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from backend.knowledge.schema import KnowledgeEntry, KnowledgeSection

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML = Path(__file__).resolve().parent.parent.parent / "knowledge" / "data" / "general.yaml"


def _valid_entry_data(**overrides: object) -> dict:
    base = {
        "id": "test-entry",
        "title": "Test Title",
        "content": "Test content body.",
        "category": "general",
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# KnowledgeEntry - valid creation
# ---------------------------------------------------------------------------


class TestKnowledgeEntry:
    def test_create_with_required_fields(self) -> None:
        entry = KnowledgeEntry(**_valid_entry_data())
        assert entry.id == "test-entry"
        assert entry.priority == 50  # default
        assert entry.verified is False

    def test_create_with_all_fields(self) -> None:
        entry = KnowledgeEntry(
            **_valid_entry_data(
                title_en="English Title",
                content_en="English content.",
                subcategory="sub",
                tags=["a", "b"],
                priority=80,
                source="official",
                verified=True,
            )
        )
        assert entry.title_en == "English Title"
        assert entry.tags == ["a", "b"]
        assert entry.priority == 80
        assert entry.verified is True

    # --- validation errors ---

    def test_invalid_id_pattern(self) -> None:
        with pytest.raises(ValidationError, match="id"):
            KnowledgeEntry(**_valid_entry_data(id="INVALID ID!"))

    def test_empty_title(self) -> None:
        with pytest.raises(ValidationError, match="title"):
            KnowledgeEntry(**_valid_entry_data(title=""))

    def test_priority_out_of_range_high(self) -> None:
        with pytest.raises(ValidationError, match="priority"):
            KnowledgeEntry(**_valid_entry_data(priority=101))

    def test_priority_out_of_range_low(self) -> None:
        with pytest.raises(ValidationError, match="priority"):
            KnowledgeEntry(**_valid_entry_data(priority=-1))

    # --- immutability (frozen) ---

    def test_frozen_model(self) -> None:
        entry = KnowledgeEntry(**_valid_entry_data())
        with pytest.raises(ValidationError):
            entry.title = "New Title"

    # --- extra fields forbidden ---

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra_field"):
            KnowledgeEntry(**_valid_entry_data(extra_field="nope"))


# ---------------------------------------------------------------------------
# KnowledgeSection
# ---------------------------------------------------------------------------


class TestKnowledgeSection:
    def _make_section(self) -> KnowledgeSection:
        entries = [
            KnowledgeEntry(**_valid_entry_data(id="a", category="general")),
            KnowledgeEntry(**_valid_entry_data(id="b", category="event")),
            KnowledgeEntry(**_valid_entry_data(id="c", category="general")),
        ]
        return KnowledgeSection(entries=entries)

    def test_create_section(self) -> None:
        section = self._make_section()
        assert section.version == "1.0.0"
        assert len(section.entries) == 3

    def test_get_entry_found(self) -> None:
        section = self._make_section()
        entry = section.get_entry("b")
        assert entry is not None
        assert entry.category == "event"

    def test_get_entry_not_found(self) -> None:
        section = self._make_section()
        assert section.get_entry("missing") is None

    def test_get_by_category(self) -> None:
        section = self._make_section()
        results = section.get_by_category("general")
        assert len(results) == 2

    def test_categories_property(self) -> None:
        section = self._make_section()
        assert section.categories == ["event", "general"]

    def test_empty_entries_rejected(self) -> None:
        with pytest.raises(ValidationError, match="entries"):
            KnowledgeSection(entries=[])

    def test_invalid_version_format(self) -> None:
        with pytest.raises(ValidationError, match="version"):
            KnowledgeSection(
                version="abc",
                entries=[KnowledgeEntry(**_valid_entry_data())],
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            KnowledgeSection(
                entries=[KnowledgeEntry(**_valid_entry_data())],
                unknown="bad",
            )


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestYamlLoading:
    def test_load_general_yaml(self) -> None:
        assert SAMPLE_YAML.exists(), f"Sample YAML not found: {SAMPLE_YAML}"
        raw = yaml.safe_load(SAMPLE_YAML.read_text(encoding="utf-8"))
        section = KnowledgeSection(**raw)
        assert len(section.entries) >= 3
        assert section.version == "1.0.0"

    def test_general_yaml_first_entry(self) -> None:
        raw = yaml.safe_load(SAMPLE_YAML.read_text(encoding="utf-8"))
        section = KnowledgeSection(**raw)
        first = section.entries[0]
        assert first.id == "general-what-is-ec"
        assert first.category == "general"
        assert first.verified is True
        assert first.priority == 90
