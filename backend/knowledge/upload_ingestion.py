"""Side-effect-free chunk planning for uploaded knowledge documents."""

from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backend.knowledge.loader import (
    ChunkingStrategy,
    KnowledgeChunk,
    _split_and_merge,
    _split_into_sections,
    count_tokens,
    get_strategy_for_category,
)
from backend.knowledge.metadata import normalize_user_metadata

EmbeddingFn = Callable[[str], Awaitable[Sequence[float]] | Sequence[float]]
ChunkLevel = Literal["document", "section", "chunk"]

_ENTRY_ID_RE = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class UploadChunkPlan:
    """Planned upload chunks plus the normalized upload context."""

    chunks: tuple[KnowledgeChunk, ...]
    strategy: ChunkingStrategy
    title: str
    category: str
    language: str
    original_filename: str
    file_type: str

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


def plan_upload_chunks(
    parsed_text: str,
    *,
    filename: str,
    category: str,
    language: str = "ja",
    title: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    strategy: ChunkingStrategy | None = None,
) -> UploadChunkPlan:
    """Plan KnowledgeChunk records for parsed upload text.

    This mirrors the YAML loader's hierarchical chunking shape without
    writing to Supabase or generating embeddings.
    """
    content = parsed_text.strip()
    if not content:
        raise ValueError("parsed_text must not be empty")

    normalized_filename = Path(filename).name
    normalized_title = _derive_title(normalized_filename, title)
    file_type = _detect_file_type(normalized_filename)
    resolved_strategy = get_strategy_for_category(category, strategy)
    entry_id = _derive_entry_id(normalized_filename, normalized_title)

    user_metadata = normalize_user_metadata(metadata, reserved_policy="drop")
    base_metadata = {
        **user_metadata,
        "language": language,
        "original_filename": normalized_filename,
        "file_type": file_type,
    }

    chunks = _chunk_upload_content(
        content=content,
        entry_id=entry_id,
        title=normalized_title,
        category=category,
        base_metadata=base_metadata,
        strategy=resolved_strategy,
    )
    chunks = _apply_total_chunk_metadata(chunks)

    return UploadChunkPlan(
        chunks=tuple(chunks),
        strategy=resolved_strategy,
        title=normalized_title,
        category=category,
        language=language,
        original_filename=normalized_filename,
        file_type=file_type,
    )


async def build_upload_chunk_records(
    plan: UploadChunkPlan,
    *,
    embedding_fn: EmbeddingFn | None = None,
) -> list[dict[str, Any]]:
    """Convert a plan into side-effect-free knowledge records.

    If *embedding_fn* is provided, it is called once per chunk and its result is
    attached as ``content_embedding``. No embedding service is imported here.
    """
    records: list[dict[str, Any]] = []
    for chunk in plan.chunks:
        record: dict[str, Any] = {
            "title": upload_chunk_record_title(chunk),
            "content": chunk.content,
            "category": chunk.category,
            "source": f"file:{plan.original_filename}",
            "metadata": {
                **chunk.metadata,
                "entry_id": chunk.entry_id,
                "document_id": chunk.entry_id,
            },
            "language": chunk.metadata.get("language", plan.language),
            "chunk_level": chunk.chunk_level,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
        }
        if embedding_fn is not None:
            embedding = embedding_fn(chunk.content)
            if inspect.isawaitable(embedding):
                embedding = await embedding
            record["content_embedding"] = list(embedding)
        records.append(record)
    return records


def _chunk_upload_content(
    *,
    content: str,
    entry_id: str,
    title: str,
    category: str,
    base_metadata: Mapping[str, Any],
    strategy: ChunkingStrategy,
) -> list[KnowledgeChunk]:
    token_total = count_tokens(content)
    if token_total <= strategy.max_tokens:
        return [
            _make_chunk(
                entry_id=entry_id,
                chunk_level="document",
                chunk_index=0,
                title=title,
                content=content,
                category=category,
                metadata=base_metadata,
            )
        ]

    sections = _split_into_sections(content)
    if sections:
        return _chunk_upload_sections(
            content=content,
            sections=sections,
            entry_id=entry_id,
            title=title,
            category=category,
            base_metadata=base_metadata,
            strategy=strategy,
        )

    chunks = [
        _make_chunk(
            entry_id=entry_id,
            chunk_level="document",
            chunk_index=0,
            title=title,
            content=_summary(content),
            category=category,
            metadata=base_metadata,
        )
    ]

    child_index = 1
    for text in _split_and_merge(content, strategy):
        if count_tokens(text) < strategy.min_chunk_tokens:
            continue
        chunks.append(
            _make_chunk(
                entry_id=entry_id,
                chunk_level="chunk",
                chunk_index=child_index,
                title=title,
                content=text,
                category=category,
                metadata=base_metadata,
            )
        )
        child_index += 1
    return chunks


def _chunk_upload_sections(
    *,
    content: str,
    sections: list[tuple[str, str]],
    entry_id: str,
    title: str,
    category: str,
    base_metadata: Mapping[str, Any],
    strategy: ChunkingStrategy,
) -> list[KnowledgeChunk]:
    chunks = [
        _make_chunk(
            entry_id=entry_id,
            chunk_level="document",
            chunk_index=0,
            title=title,
            content=_summary(content),
            category=category,
            metadata=base_metadata,
        )
    ]

    child_index = 1
    for heading, body in sections:
        section_title = f"{title} - {heading}"
        section_metadata = {**base_metadata, "section": heading}
        if count_tokens(body) <= strategy.max_tokens:
            chunks.append(
                _make_chunk(
                    entry_id=entry_id,
                    chunk_level="section",
                    chunk_index=child_index,
                    title=section_title,
                    content=body,
                    category=category,
                    metadata=section_metadata,
                )
            )
            child_index += 1
            continue

        for text in _split_and_merge(body, strategy):
            if count_tokens(text) < strategy.min_chunk_tokens:
                continue
            chunks.append(
                _make_chunk(
                    entry_id=entry_id,
                    chunk_level="chunk",
                    chunk_index=child_index,
                    title=section_title,
                    content=text,
                    category=category,
                    metadata=section_metadata,
                )
            )
            child_index += 1
    return chunks


def _make_chunk(
    *,
    entry_id: str,
    chunk_level: ChunkLevel,
    chunk_index: int,
    title: str,
    content: str,
    category: str,
    metadata: Mapping[str, Any],
) -> KnowledgeChunk:
    return KnowledgeChunk(
        entry_id=entry_id,
        chunk_level=chunk_level,
        chunk_index=chunk_index,
        title=title,
        content=content,
        token_count=count_tokens(content),
        category=category,
        metadata=dict(metadata),
    )


def _apply_total_chunk_metadata(chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
    total_chunks = len(chunks)
    return [
        KnowledgeChunk(
            entry_id=chunk.entry_id,
            chunk_level=chunk.chunk_level,
            chunk_index=chunk.chunk_index,
            title=chunk.title,
            content=chunk.content,
            token_count=chunk.token_count,
            category=chunk.category,
            metadata={
                **chunk.metadata,
                "chunk_level": chunk.chunk_level,
                "chunk_index": chunk.chunk_index,
                "total_chunks": total_chunks,
            },
        )
        for chunk in chunks
    ]


def upload_chunk_record_title(chunk: KnowledgeChunk) -> str:
    """Return the persisted title for an uploaded knowledge chunk."""

    if chunk.chunk_level == "document":
        return chunk.title
    return f"{chunk.title} [chunk {chunk.chunk_index}]"


def _derive_title(filename: str, title: str | None) -> str:
    if title and title.strip():
        return title.strip()
    stem = Path(filename).stem.strip()
    return stem or filename or "Uploaded knowledge"


def _derive_entry_id(filename: str, title: str) -> str:
    slug_source = Path(filename).stem or title
    slug = _ENTRY_ID_RE.sub("-", slug_source.lower()).strip("-_")
    digest = hashlib.sha1(f"{filename}:{title}".encode("utf-8")).hexdigest()[:8]
    if slug:
        return f"upload-{slug[:48]}-{digest}"
    return f"upload-{digest}"


def _summary(content: str) -> str:
    return content[:200].rstrip() + "..."


def _detect_file_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".md", ".markdown")):
        return "markdown"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".txt"):
        return "text"
    return "unknown"
