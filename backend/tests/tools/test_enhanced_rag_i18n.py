"""Tests for multilingual content_en support in knowledge loader and RAG.

Validates:
1. YAML entries with content_en load correctly via schema
2. chunk_entry() produces separate English chunks
3. English chunks have correct metadata (language='en')
4. English and Japanese chunks have distinct entry_ids
"""

import pytest

from backend.knowledge.loader import (
    ChunkingStrategy,
    _build_metadata,
    _chunk_english_content,
    chunk_entry,
)
from backend.knowledge.schema import KnowledgeEntry


@pytest.fixture
def ja_only_entry():
    return KnowledgeEntry(
        id="test-ja-only",
        title="テストエントリ",
        content="これは日本語のコンテンツです。テスト用のエントリです。",
        category="general",
        tags=["test"],
        priority=50,
        source="test",
        verified=True,
    )


@pytest.fixture
def bilingual_entry():
    return KnowledgeEntry(
        id="test-bilingual",
        title="テストエントリ",
        title_en="Test Entry",
        content="これは日本語のコンテンツです。テスト用のエントリです。エンジニアカフェのテストです。",
        content_en="This is English content for testing. Engineer Cafe test entry.",
        category="general",
        tags=["test"],
        priority=50,
        source="test",
        verified=True,
    )


@pytest.fixture
def large_bilingual_entry():
    ja_content = "エンジニアカフェのテストです。" * 50
    en_content = "Engineer Cafe test content for chunking. " * 80
    return KnowledgeEntry(
        id="test-large-bilingual",
        title="大きなテストエントリ",
        title_en="Large Test Entry",
        content=ja_content,
        content_en=en_content,
        category="general",
        tags=["test"],
        priority=50,
        source="test",
        verified=True,
    )


class TestContentEnSchema:
    def test_entry_without_content_en(self, ja_only_entry):
        assert ja_only_entry.content_en is None

    def test_entry_with_content_en(self, bilingual_entry):
        assert bilingual_entry.content_en is not None
        assert "English" in bilingual_entry.content_en

    def test_content_en_none_by_default(self):
        entry = KnowledgeEntry(
            id="test-default", title="Test", content="Content", category="general"
        )
        assert entry.content_en is None


class TestBuildMetadata:
    def test_default_language_is_ja(self, ja_only_entry):
        meta = _build_metadata(ja_only_entry)
        assert meta["language"] == "ja"

    def test_explicit_en_language(self, bilingual_entry):
        meta = _build_metadata(bilingual_entry, language="en")
        assert meta["language"] == "en"

    def test_metadata_preserves_tags(self, bilingual_entry):
        meta = _build_metadata(bilingual_entry, language="en")
        assert meta["tags"] == ["test"]
        assert meta["priority"] == 50
        assert meta["verified"] is True


class TestChunkEnglishContent:
    def test_no_english_chunks_without_content_en(self, ja_only_entry):
        chunks = _chunk_english_content(ja_only_entry, ChunkingStrategy())
        assert len(chunks) == 0

    def test_produces_english_chunks(self, bilingual_entry):
        chunks = _chunk_english_content(bilingual_entry, ChunkingStrategy())
        assert len(chunks) >= 1
        assert all(c.metadata["language"] == "en" for c in chunks)

    def test_english_chunk_entry_id_suffix(self, bilingual_entry):
        chunks = _chunk_english_content(bilingual_entry, ChunkingStrategy())
        assert all(c.entry_id.endswith("-en") for c in chunks)

    def test_english_chunk_uses_title_en(self, bilingual_entry):
        chunks = _chunk_english_content(bilingual_entry, ChunkingStrategy())
        assert chunks[0].title == "Test Entry"

    def test_english_chunk_fallback_title(self):
        entry = KnowledgeEntry(
            id="test-no-title-en",
            title="テスト",
            content="日本語コンテンツ",
            content_en="English content here.",
            category="general",
        )
        chunks = _chunk_english_content(entry, ChunkingStrategy())
        assert chunks[0].title == "テスト (English)"

    def test_large_english_content_produces_multiple_chunks(self, large_bilingual_entry):
        chunks = _chunk_english_content(large_bilingual_entry, ChunkingStrategy())
        assert len(chunks) >= 2
        doc_chunks = [c for c in chunks if c.chunk_level == "document"]
        assert len(doc_chunks) >= 1


class TestChunkEntryBilingual:
    def test_bilingual_produces_both_languages(self, bilingual_entry):
        chunks = chunk_entry(bilingual_entry)
        ja_chunks = [c for c in chunks if c.metadata.get("language") == "ja"]
        en_chunks = [c for c in chunks if c.metadata.get("language") == "en"]
        assert len(ja_chunks) >= 1
        assert len(en_chunks) >= 1

    def test_ja_only_produces_only_ja_chunks(self, ja_only_entry):
        chunks = chunk_entry(ja_only_entry)
        languages = {c.metadata.get("language") for c in chunks}
        assert languages == {"ja"}

    def test_ja_chunks_use_original_id(self, bilingual_entry):
        chunks = chunk_entry(bilingual_entry)
        ja_chunks = [c for c in chunks if c.metadata.get("language") == "ja"]
        assert all(c.entry_id == "test-bilingual" for c in ja_chunks)

    def test_en_chunks_use_suffixed_id(self, bilingual_entry):
        chunks = chunk_entry(bilingual_entry)
        en_chunks = [c for c in chunks if c.metadata.get("language") == "en"]
        assert all(c.entry_id == "test-bilingual-en" for c in en_chunks)

    def test_total_chunk_count_increases(self, bilingual_entry):
        ja_only = KnowledgeEntry(
            id="test-ja", title="テスト", content=bilingual_entry.content, category="general"
        )
        ja_chunks = chunk_entry(ja_only)
        bi_chunks = chunk_entry(bilingual_entry)
        assert len(bi_chunks) > len(ja_chunks)


class TestYAMLLoadingWithContentEn:
    def _load_all_entries(self):
        from pathlib import Path

        from backend.knowledge.loader import load_all_yaml_files

        data_dir = Path(__file__).parent.parent.parent / "knowledge" / "data"
        sections = load_all_yaml_files(data_dir)
        entries = []
        for section in sections:
            entries.extend(section.entries)
        return entries

    def test_at_least_10_entries_have_content_en(self):
        entries = self._load_all_entries()
        entries_with_en = [e for e in entries if e.content_en is not None]
        assert len(entries_with_en) >= 10

    def test_general_hours_has_english(self):
        for e in self._load_all_entries():
            if e.id == "general-hours":
                assert e.content_en is not None
                assert "9:00" in e.content_en or "AM" in e.content_en
                return
        pytest.fail("general-hours not found")

    def test_general_access_has_english(self):
        for e in self._load_all_entries():
            if e.id == "general-access":
                assert e.content_en is not None
                assert "Tenjin" in e.content_en
                return
        pytest.fail("general-access not found")

    def test_facility_wifi_has_english(self):
        for e in self._load_all_entries():
            if e.id == "facility-wifi-power":
                assert e.content_en is not None
                assert "engnecf-guest" in e.content_en
                return
        pytest.fail("facility-wifi-power not found")

    def test_community_manager_has_english(self):
        for e in self._load_all_entries():
            if e.id == "community-manager":
                assert e.content_en is not None
                assert "Community Manager" in e.content_en
                return
        pytest.fail("community-manager not found")

    def test_policy_parking_has_english(self):
        for e in self._load_all_entries():
            if e.id == "policy-parking":
                assert e.content_en is not None
                assert "parking" in e.content_en.lower()
                return
        pytest.fail("policy-parking not found")

    def test_event_connpass_has_english(self):
        for e in self._load_all_entries():
            if e.id == "event-connpass-howto":
                assert e.content_en is not None
                assert "connpass" in e.content_en.lower()
                return
        pytest.fail("event-connpass-howto not found")
