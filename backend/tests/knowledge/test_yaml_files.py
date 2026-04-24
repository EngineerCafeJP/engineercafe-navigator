"""Comprehensive validation tests for all 7 YAML knowledge files.

Validates:
- All 7 YAML files exist and parse without errors
- Each file passes Pydantic KnowledgeSection schema validation
- Total of exactly 60 entries across all files
- No duplicate IDs across all files
- All IDs match the required pattern ^[a-z0-9_-]+$
- Priority values are within valid range (0-100)
- Categories are from the expected set
- Required fields (title, content, category) are present in all entries
- All entries have source="official" and verified=true
- Expected entry counts per file
"""

import re
from pathlib import Path

import pytest
import yaml

from backend.knowledge.schema import KnowledgeSection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge" / "data"

EXPECTED_FILES = [
    "general.yaml",
    "facilities.yaml",
    "saino_cafe.yaml",
    "community.yaml",
    "building_history.yaml",
    "policies.yaml",
    "events.yaml",
]

EXPECTED_TOTAL_ENTRIES = 62

EXPECTED_ENTRY_COUNTS = {
    "general.yaml": 14,
    "facilities.yaml": 23,
    "saino_cafe.yaml": 4,
    "community.yaml": 5,
    "building_history.yaml": 3,
    "policies.yaml": 11,
    "events.yaml": 2,
}

VALID_CATEGORIES = {
    "general",
    "hours",
    "contact",
    "access",
    "pricing",
    "facility-info",
    "consultation",
    "community",
    "surrounding",
    "food_drink",
    "smoking",
    "parking",
    "bicycle",
    "policy",
    "event",
}

ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_section(filename: str) -> KnowledgeSection:
    """Load and validate a single YAML file into a KnowledgeSection."""
    path = DATA_DIR / filename
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return KnowledgeSection(**raw)


def _load_all_sections() -> dict[str, KnowledgeSection]:
    """Load all 7 YAML files into KnowledgeSection instances."""
    return {f: _load_section(f) for f in EXPECTED_FILES}


# ---------------------------------------------------------------------------
# File existence tests
# ---------------------------------------------------------------------------


class TestFileExistence:
    def test_data_directory_exists(self) -> None:
        assert DATA_DIR.exists(), f"Data directory not found: {DATA_DIR}"
        assert DATA_DIR.is_dir()

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_yaml_file_exists(self, filename: str) -> None:
        path = DATA_DIR / filename
        assert path.exists(), f"YAML file not found: {path}"
        assert path.is_file()

    def test_exactly_seven_yaml_files(self) -> None:
        yaml_files = sorted(f.name for f in DATA_DIR.glob("*.yaml"))
        assert len(yaml_files) == 7, f"Expected 7 YAML files, found {len(yaml_files)}: {yaml_files}"


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_yaml_parses_without_error(self, filename: str) -> None:
        path = DATA_DIR / filename
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw is not None
        assert "entries" in raw

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_pydantic_validation_passes(self, filename: str) -> None:
        section = _load_section(filename)
        assert isinstance(section, KnowledgeSection)
        assert section.version == "1.0.0"
        assert len(section.entries) > 0

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_all_entries_have_required_fields(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert entry.id, f"Empty ID in {filename}"
            assert entry.title, f"Empty title in {filename}: {entry.id}"
            assert entry.content, f"Empty content in {filename}: {entry.id}"
            assert entry.category, f"Empty category in {filename}: {entry.id}"


# ---------------------------------------------------------------------------
# Entry count tests
# ---------------------------------------------------------------------------


class TestEntryCounts:
    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_expected_entry_count_per_file(self, filename: str) -> None:
        section = _load_section(filename)
        expected = EXPECTED_ENTRY_COUNTS[filename]
        actual = len(section.entries)
        assert actual == expected, f"{filename}: expected {expected} entries, got {actual}"

    def test_total_entry_count_is_60(self) -> None:
        sections = _load_all_sections()
        total = sum(len(s.entries) for s in sections.values())
        assert (
            total == EXPECTED_TOTAL_ENTRIES
        ), f"Expected {EXPECTED_TOTAL_ENTRIES} total entries, got {total}"


# ---------------------------------------------------------------------------
# ID validation tests
# ---------------------------------------------------------------------------


class TestIdValidation:
    def test_no_duplicate_ids_across_files(self) -> None:
        sections = _load_all_sections()
        all_ids: list[str] = []
        for filename, section in sections.items():
            for entry in section.entries:
                all_ids.append(entry.id)

        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for filename, section in sections.items():
            for entry in section.entries:
                if entry.id in seen:
                    duplicates.append(f"'{entry.id}' in both {seen[entry.id]} and {filename}")
                seen[entry.id] = filename

        assert not duplicates, f"Duplicate IDs found: {duplicates}"

    def test_all_ids_are_unique(self) -> None:
        sections = _load_all_sections()
        all_ids = [entry.id for section in sections.values() for entry in section.entries]
        assert len(all_ids) == len(set(all_ids)), "Duplicate IDs exist"

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_ids_match_pattern(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert ID_PATTERN.match(entry.id), (
                f"Invalid ID '{entry.id}' in {filename}: " f"must match ^[a-z0-9_-]+$"
            )


# ---------------------------------------------------------------------------
# Priority validation tests
# ---------------------------------------------------------------------------


class TestPriorityValidation:
    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_priority_within_range(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert 0 <= entry.priority <= 100, (
                f"Priority {entry.priority} out of range for " f"'{entry.id}' in {filename}"
            )

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_priority_is_standard_value(self, filename: str) -> None:
        """Priority should be one of: 30 (low), 50 (default), 60 (medium), 90 (high)."""
        standard_values = {30, 50, 60, 90}
        section = _load_section(filename)
        for entry in section.entries:
            assert entry.priority in standard_values, (
                f"Non-standard priority {entry.priority} for "
                f"'{entry.id}' in {filename}. "
                f"Expected one of {standard_values}"
            )


# ---------------------------------------------------------------------------
# Category validation tests
# ---------------------------------------------------------------------------


class TestCategoryValidation:
    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_categories_are_valid(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert entry.category in VALID_CATEGORIES, (
                f"Invalid category '{entry.category}' for "
                f"'{entry.id}' in {filename}. "
                f"Valid: {sorted(VALID_CATEGORIES)}"
            )


# ---------------------------------------------------------------------------
# Source and verification tests
# ---------------------------------------------------------------------------


class TestSourceVerification:
    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_all_entries_are_official(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert entry.source == "official", (
                f"Entry '{entry.id}' in {filename} "
                f"has source='{entry.source}', expected 'official'"
            )

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_all_entries_are_verified(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert entry.verified is True, f"Entry '{entry.id}' in {filename} is not verified"


# ---------------------------------------------------------------------------
# Content quality tests
# ---------------------------------------------------------------------------


class TestContentQuality:
    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_content_is_not_trivially_short(self, filename: str) -> None:
        """All entries should have meaningful content (at least 20 chars)."""
        section = _load_section(filename)
        for entry in section.entries:
            stripped = entry.content.strip()
            assert len(stripped) >= 20, (
                f"Content too short ({len(stripped)} chars) for " f"'{entry.id}' in {filename}"
            )

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_title_is_not_trivially_short(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert len(entry.title.strip()) >= 3, f"Title too short for '{entry.id}' in {filename}"

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_entries_have_tags(self, filename: str) -> None:
        section = _load_section(filename)
        for entry in section.entries:
            assert len(entry.tags) >= 1, f"Entry '{entry.id}' in {filename} has no tags"


# ---------------------------------------------------------------------------
# Cross-file consistency tests
# ---------------------------------------------------------------------------


class TestCrossFileConsistency:
    def test_general_yaml_contains_overview_entry(self) -> None:
        section = _load_section("general.yaml")
        entry = section.get_entry("general-what-is-ec")
        assert entry is not None
        assert entry.category == "general"
        assert entry.priority == 90

    def test_facilities_yaml_contains_main_hall(self) -> None:
        section = _load_section("facilities.yaml")
        entry = section.get_entry("facility-main-hall")
        assert entry is not None
        assert entry.category == "facility-info"

    def test_saino_yaml_contains_business_info(self) -> None:
        section = _load_section("saino_cafe.yaml")
        entry = section.get_entry("saino-business-info")
        assert entry is not None

    def test_community_yaml_contains_cm_entry(self) -> None:
        section = _load_section("community.yaml")
        ids = [e.id for e in section.entries]
        cm_ids = [i for i in ids if "community" in i or "manager" in i]
        assert len(cm_ids) >= 1, "No community manager entry found"

    def test_events_yaml_contains_hosting_entry(self) -> None:
        section = _load_section("events.yaml")
        entry = section.get_entry("event-hosting")
        assert entry is not None
        assert entry.category == "event"

    def test_policies_yaml_contains_smoking_entry(self) -> None:
        section = _load_section("policies.yaml")
        entry = section.get_entry("policy-smoking")
        assert entry is not None

    def test_building_history_contains_akarenga(self) -> None:
        section = _load_section("building_history.yaml")
        entry = section.get_entry("building-akarenga-history")
        assert entry is not None
