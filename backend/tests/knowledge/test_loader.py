"""Tests for backend.knowledge.loader — hierarchical chunking engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from backend.knowledge.loader import (
    ChunkingStrategy,
    KnowledgeChunk,
    SeedResult,
    chunk_entry,
    count_tokens,
    generate_chunks_with_embeddings,
    load_all_yaml_files,
    seed_from_yaml,
)
from backend.knowledge.schema import KnowledgeEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str = "test-entry",
    title: str = "テストタイトル",
    content: str = "テスト内容です。",
    category: str = "general",
    **kwargs,
) -> KnowledgeEntry:
    return KnowledgeEntry(
        id=entry_id,
        title=title,
        content=content,
        category=category,
        **kwargs,
    )


def _long_content(tokens: int = 600) -> str:
    """Generate Japanese text that exceeds *tokens* approximate tokens."""
    sentence = "これはテスト用の長いコンテンツです。"
    paragraph = sentence * 10
    paragraphs = []
    while count_tokens("\n\n".join(paragraphs)) < tokens:
        paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


SAMPLE_YAML = {
    "version": "1.0.0",
    "description": "テスト用",
    "entries": [
        {
            "id": "test-1",
            "title": "テスト1",
            "content": "テスト内容1",
            "category": "general",
        },
        {
            "id": "test-2",
            "title": "テスト2",
            "content": "テスト内容2",
            "category": "facility",
        },
    ],
}

# YAML with a long entry that produces parent + child chunks
LONG_SAMPLE_YAML = {
    "version": "1.0.0",
    "description": "テスト用（長いエントリ）",
    "entries": [
        {
            "id": "test-long",
            "title": "長いテスト",
            "content": "これはテスト用の長いコンテンツです。" * 50,
            "category": "general",
        },
    ],
}


# ===================================================================
# TestCountTokens
# ===================================================================


class TestCountTokens:
    def test_japanese_text(self):
        text = "エンジニアカフェは福岡市のエンジニア向け施設です"
        tokens = count_tokens(text)
        assert tokens > 0
        # Japanese text: ~0.6 tokens per char -> ~24 chars ~ 14 tokens
        assert 5 < tokens < 30

    def test_english_text(self):
        text = "Engineer Cafe is a free coworking space."
        tokens = count_tokens(text)
        assert tokens > 0
        # English: ~0.25 tokens per char -> 40 chars ~ 10 tokens
        assert 5 < tokens < 20

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_mixed_text(self):
        text = "エンジニアカフェ is a great place for engineers"
        tokens = count_tokens(text)
        assert tokens > 0
        # Should be somewhere between pure-JP and pure-EN estimates
        assert 5 < tokens < 30


# ===================================================================
# TestChunkEntry
# ===================================================================


class TestChunkEntry:
    def test_short_entry_single_chunk(self):
        entry = _make_entry(content="短いコンテンツ。")
        chunks = chunk_entry(entry)

        assert len(chunks) == 1
        assert chunks[0].chunk_level == "document"
        assert chunks[0].chunk_index == 0
        assert chunks[0].content == entry.content

    def test_long_entry_multiple_chunks(self):
        content = _long_content(tokens=600)
        entry = _make_entry(content=content)
        strategy = ChunkingStrategy(max_tokens=200)
        chunks = chunk_entry(entry, strategy)

        assert len(chunks) > 1
        # First chunk is always the parent document summary
        assert chunks[0].chunk_level == "document"
        assert chunks[0].chunk_index == 0
        assert chunks[0].content.endswith("...")
        # Remaining chunks are children
        child_chunks = [c for c in chunks if c.chunk_level == "chunk"]
        assert len(child_chunks) >= 1

    def test_chunk_ordering(self):
        content = _long_content(tokens=600)
        entry = _make_entry(content=content)
        strategy = ChunkingStrategy(max_tokens=200)
        chunks = chunk_entry(entry, strategy)

        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices)
        # First index is 0 (document), children start at 1
        assert indices[0] == 0

    def test_min_chunk_size(self):
        """Chunks smaller than min_chunk_tokens should be skipped."""
        entry = _make_entry(content="短い。\n\n" + _long_content(tokens=400))
        strategy = ChunkingStrategy(
            max_tokens=200,
            min_chunk_tokens=50,
            overlap_tokens=0,
        )
        chunks = chunk_entry(entry, strategy)

        child_chunks = [c for c in chunks if c.chunk_level == "chunk"]
        for child in child_chunks:
            assert child.token_count >= strategy.min_chunk_tokens

    def test_paragraph_splitting(self):
        """Content with \\n\\n should split at paragraph boundaries."""
        para1 = "段落1です。" * 30
        para2 = "段落2です。" * 30
        content = para1 + "\n\n" + para2
        entry = _make_entry(content=content)
        strategy = ChunkingStrategy(max_tokens=50)
        chunks = chunk_entry(entry, strategy)

        # Should have more than 1 chunk since we have 2 large paragraphs
        assert len(chunks) > 1

    def test_custom_strategy(self):
        """Custom ChunkingStrategy parameters are respected."""
        content = _long_content(tokens=800)
        entry = _make_entry(content=content)

        small = ChunkingStrategy(max_tokens=100)
        large = ChunkingStrategy(max_tokens=400)

        chunks_small = chunk_entry(entry, small)
        chunks_large = chunk_entry(entry, large)

        # Smaller max_tokens should produce more chunks
        assert len(chunks_small) >= len(chunks_large)

    def test_metadata_is_independent_per_chunk(self):
        """Each chunk gets its own metadata dict (no shared reference)."""
        content = _long_content(tokens=600)
        entry = _make_entry(content=content)
        strategy = ChunkingStrategy(max_tokens=200)
        chunks = chunk_entry(entry, strategy)

        assert len(chunks) >= 2
        # Verify each chunk has a distinct metadata object
        ids = [id(c.metadata) for c in chunks]
        assert len(set(ids)) == len(ids), "Chunks share the same metadata dict object"


# ===================================================================
# TestLoadAllYamlFiles
# ===================================================================


class TestLoadAllYamlFiles:
    def test_load_existing_yaml(self):
        data_dir = Path(__file__).resolve().parents[2] / "knowledge" / "data"
        if not data_dir.exists():
            pytest.skip("No knowledge/data directory")

        sections = load_all_yaml_files(data_dir)
        assert len(sections) >= 1
        assert len(sections[0].entries) >= 1

    def test_empty_directory(self, tmp_path: Path):
        sections = load_all_yaml_files(tmp_path)
        assert sections == []

    def test_validation_error(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("not_a_valid: structure\n", encoding="utf-8")

        with pytest.raises(Exception):
            load_all_yaml_files(tmp_path)

    def test_invalid_schema(self, tmp_path: Path):
        bad = {
            "version": "1.0.0",
            "entries": [{"id": "!!invalid id!!", "title": "", "content": "", "category": "x"}],
        }
        path = tmp_path / "bad_schema.yaml"
        path.write_text(yaml.dump(bad), encoding="utf-8")

        with pytest.raises(Exception):
            load_all_yaml_files(tmp_path)


# ===================================================================
# TestGenerateChunksWithEmbeddings
# ===================================================================


class TestGenerateChunksWithEmbeddings:
    @pytest.mark.asyncio
    async def test_generates_embeddings(self):
        chunks = [
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="document",
                chunk_index=0,
                title="T1",
                content="コンテンツ1",
                token_count=5,
                category="general",
            ),
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="chunk",
                chunk_index=1,
                title="T1",
                content="コンテンツ2",
                token_count=5,
                category="general",
            ),
        ]
        fake_embedding = [0.1] * 1536

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ) as mock_embed:
            results = await generate_chunks_with_embeddings(chunks)

        assert len(results) == 2
        assert mock_embed.call_count == 2
        for r in results:
            assert r["content_embedding"] == fake_embedding
            assert "chunk_level" in r
            assert "token_count" in r

    @pytest.mark.asyncio
    async def test_child_chunk_title_uniqueness(self):
        """Child chunks get title suffixed with [chunk N] to avoid collisions."""
        chunks = [
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="document",
                chunk_index=0,
                title="Same Title",
                content="Parent content",
                token_count=5,
                category="general",
            ),
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="chunk",
                chunk_index=1,
                title="Same Title",
                content="Child 1",
                token_count=5,
                category="general",
            ),
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="chunk",
                chunk_index=2,
                title="Same Title",
                content="Child 2",
                token_count=5,
                category="general",
            ),
        ]
        fake_embedding = [0.1] * 1536

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ):
            results = await generate_chunks_with_embeddings(chunks)

        titles = [r["title"] for r in results]
        assert titles[0] == "Same Title"  # parent keeps original
        assert titles[1] == "Same Title [chunk 1]"
        assert titles[2] == "Same Title [chunk 2]"
        # All titles are unique
        assert len(set(titles)) == len(titles)

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        chunks = [
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="document",
                chunk_index=i,
                title="T",
                content=f"C{i}",
                token_count=3,
                category="g",
            )
            for i in range(3)
        ]
        fake_embedding = [0.1] * 1536

        with (
            patch(
                "backend.knowledge.loader.generate_embedding",
                new_callable=AsyncMock,
                return_value=fake_embedding,
            ),
            patch(
                "backend.knowledge.loader.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            await generate_chunks_with_embeddings(chunks)

        # sleep called between chunks (n-1 times)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.0)

    @pytest.mark.asyncio
    async def test_empty_embedding_handling(self):
        chunks = [
            KnowledgeChunk(
                entry_id="e1",
                chunk_level="document",
                chunk_index=0,
                title="T",
                content="C",
                token_count=1,
                category="g",
            ),
        ]

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=[],
        ):
            results = await generate_chunks_with_embeddings(chunks)

        assert len(results) == 0


# ===================================================================
# TestSeedFromYaml
# ===================================================================


class TestSeedFromYaml:
    def _mock_supabase(self) -> MagicMock:
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value = None
        return client

    def _write_yaml(self, tmp_path: Path, data: dict | None = None) -> Path:
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(data or SAMPLE_YAML), encoding="utf-8")
        return tmp_path

    @pytest.mark.asyncio
    async def test_full_pipeline(self, tmp_path: Path):
        data_dir = self._write_yaml(tmp_path)
        client = self._mock_supabase()
        fake_embedding = [0.1] * 1536

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ):
            result = await seed_from_yaml(client, data_dir)

        assert isinstance(result, SeedResult)
        assert result.success_count > 0
        assert result.error_count == 0
        client.table.assert_called_with("knowledge_base")

    @pytest.mark.asyncio
    async def test_idempotent(self, tmp_path: Path):
        data_dir = self._write_yaml(tmp_path)
        client = self._mock_supabase()
        fake_embedding = [0.1] * 1536

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ):
            result1 = await seed_from_yaml(client, data_dir)
            result2 = await seed_from_yaml(client, data_dir)

        assert result1.success_count == result2.success_count
        assert result1.total_chunks == result2.total_chunks

    @pytest.mark.asyncio
    async def test_parent_child_relationship(self, tmp_path: Path):
        """Parent documents are upserted before children."""
        data_dir = self._write_yaml(tmp_path, data=LONG_SAMPLE_YAML)
        client = self._mock_supabase()
        fake_embedding = [0.1] * 1536

        upsert_order: list[str] = []
        original_upsert = client.table.return_value.upsert

        def track_upsert(rec, **kwargs):
            upsert_order.append(rec.get("chunk_level", "unknown"))
            return original_upsert(rec, **kwargs)

        client.table.return_value.upsert = track_upsert

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ):
            result = await seed_from_yaml(
                client, data_dir, strategy=ChunkingStrategy(max_tokens=100)
            )

        # Long entry should produce both document and chunk levels
        assert "document" in upsert_order, "Expected parent document chunks"
        assert "chunk" in upsert_order, "Expected child chunks"
        # All "document" entries must come before any "chunk" entries
        last_doc_idx = max(i for i, v in enumerate(upsert_order) if v == "document")
        first_chunk_idx = min(i for i, v in enumerate(upsert_order) if v == "chunk")
        assert last_doc_idx < first_chunk_idx
        assert result.success_count > 2  # at least 1 parent + 1+ children

    @pytest.mark.asyncio
    async def test_error_handling(self, tmp_path: Path):
        """Embedding failure for one chunk does not crash the pipeline."""
        data_dir = self._write_yaml(tmp_path)
        client = self._mock_supabase()

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await seed_from_yaml(client, data_dir)

        # All embeddings failed -> skipped, but no crash
        assert isinstance(result, SeedResult)
        assert result.success_count == 0
        assert result.skipped_count > 0

    @pytest.mark.asyncio
    async def test_seed_result_counts(self, tmp_path: Path):
        data_dir = self._write_yaml(tmp_path)
        client = self._mock_supabase()
        fake_embedding = [0.1] * 1536

        with patch(
            "backend.knowledge.loader.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ):
            result = await seed_from_yaml(client, data_dir)

        assert result.total_chunks >= 2  # at least 2 entries
        # success + errors + skipped == total_chunks (exact accounting)
        assert result.success_count + result.error_count + result.skipped_count == (
            result.total_chunks
        )
        assert result.error_count == 0
