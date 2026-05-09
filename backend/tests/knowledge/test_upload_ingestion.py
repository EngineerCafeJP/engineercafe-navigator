"""Tests for side-effect-free upload ingestion chunk planning."""

from __future__ import annotations

from backend.knowledge.loader import ChunkingStrategy, count_tokens, get_strategy_for_category
from backend.knowledge.upload_ingestion import (
    build_upload_chunk_records,
    plan_upload_chunks,
)


def _content_with_tokens(min_tokens: int) -> str:
    sentence = "これはアップロード文書のチャンク分割テストです。"
    paragraphs: list[str] = []
    while count_tokens("\n\n".join(paragraphs)) < min_tokens:
        paragraphs.append(sentence * 8)
    return "\n\n".join(paragraphs)


def test_plan_upload_chunks_uses_category_specific_strategy():
    content = _content_with_tokens(360)

    pricing = plan_upload_chunks(
        content,
        filename="pricing.md",
        category="pricing",
        language="ja",
    )
    general = plan_upload_chunks(
        content,
        filename="general.md",
        category="general",
        language="ja",
    )

    assert pricing.strategy == get_strategy_for_category("pricing")
    assert pricing.strategy.max_tokens == 300
    assert pricing.total_chunks > 1
    assert any(chunk.chunk_level == "chunk" for chunk in pricing.chunks)

    assert general.strategy == get_strategy_for_category("general")
    assert general.strategy.max_tokens == 500
    assert general.total_chunks == 1
    assert general.chunks[0].chunk_level == "document"


def test_plan_upload_chunks_adds_language_file_and_accounting_metadata():
    plan = plan_upload_chunks(
        "Parsed PDF content",
        filename="Visitor Guide.pdf",
        category="general",
        language="en",
        title="Visitor Guide",
        metadata={
            "owner": "operations",
            "language": "ja",
            "total_chunks": 99,
        },
    )

    chunk = plan.chunks[0]
    assert chunk.metadata["owner"] == "operations"
    assert chunk.metadata["language"] == "en"
    assert chunk.metadata["original_filename"] == "Visitor Guide.pdf"
    assert chunk.metadata["file_type"] == "pdf"
    assert chunk.metadata["chunk_level"] == "document"
    assert chunk.metadata["chunk_index"] == 0
    assert chunk.metadata["total_chunks"] == 1


def test_plan_upload_chunks_preserves_section_chunk_levels_and_titles():
    content = (
        "## Access\n"
        + "アクセス方法の説明です。" * 10
        + "\n\n## Facilities\n"
        + "設備情報の説明です。" * 10
    )

    plan = plan_upload_chunks(
        content,
        filename="facility-info.md",
        category="facility-info",
        title="Facility Guide",
        strategy=ChunkingStrategy(max_tokens=90, overlap_tokens=0, min_chunk_tokens=10),
    )

    assert [chunk.chunk_level for chunk in plan.chunks] == [
        "document",
        "section",
        "section",
    ]
    assert plan.chunks[1].title == "Facility Guide - Access"
    assert plan.chunks[2].title == "Facility Guide - Facilities"
    assert plan.chunks[1].metadata["section"] == "Access"
    assert plan.chunks[2].metadata["section"] == "Facilities"


def test_plan_upload_chunks_applies_total_chunk_accounting_to_every_chunk():
    plan = plan_upload_chunks(
        _content_with_tokens(260),
        filename="long-policy.txt",
        category="general",
        title="Long Policy",
        strategy=ChunkingStrategy(max_tokens=90, overlap_tokens=0, min_chunk_tokens=10),
    )

    assert plan.total_chunks > 1
    for chunk in plan.chunks:
        assert chunk.metadata["total_chunks"] == plan.total_chunks
        assert chunk.metadata["chunk_index"] == chunk.chunk_index
        assert chunk.metadata["chunk_level"] == chunk.chunk_level


async def test_build_upload_chunk_records_uses_injected_embedding_function_only():
    plan = plan_upload_chunks(
        "Short upload content",
        filename="short.md",
        category="general",
        title="Short Upload",
        language="en",
    )
    calls: list[str] = []

    async def fake_embed(text: str) -> list[float]:
        calls.append(text)
        return [0.1, 0.2, 0.3]

    records_without_embeddings = await build_upload_chunk_records(plan)
    assert "content_embedding" not in records_without_embeddings[0]
    assert calls == []

    records = await build_upload_chunk_records(plan, embedding_fn=fake_embed)
    assert calls == ["Short upload content"]
    assert records[0]["title"] == "Short Upload"
    assert records[0]["source"] == "file:short.md"
    assert records[0]["language"] == "en"
    assert records[0]["content_embedding"] == [0.1, 0.2, 0.3]
    assert records[0]["metadata"]["entry_id"] == plan.chunks[0].entry_id
    assert records[0]["metadata"]["document_id"] == plan.chunks[0].entry_id
