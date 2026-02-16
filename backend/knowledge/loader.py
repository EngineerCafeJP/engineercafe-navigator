"""Hierarchical chunking engine for YAML knowledge files.

Loads YAML knowledge entries, splits them into hierarchical chunks
(document / section / chunk), generates embeddings, and upserts to Supabase.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from backend.knowledge.schema import KnowledgeEntry, KnowledgeSection
from backend.utils.embedding_service import generate_embedding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes (frozen for immutability)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkingStrategy:
    """Controls how text is split into chunks."""

    max_tokens: int = 500
    overlap_tokens: int = 50
    min_chunk_tokens: int = 50


@dataclass(frozen=True)
class KnowledgeChunk:
    """A single chunk produced by the chunking engine.

    Note: *metadata* is a dict and therefore mutable even on a frozen
    dataclass.  Callers MUST treat it as read-only; ``chunk_entry``
    creates a fresh copy for every chunk.
    """

    entry_id: str
    chunk_level: Literal["document", "section", "chunk"]
    chunk_index: int
    title: str
    content: str
    token_count: int
    category: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SeedResult:
    """Result of a full seed operation."""

    success_count: int
    error_count: int
    total_chunks: int
    skipped_count: int


# ---------------------------------------------------------------------------
# Token counting (no tiktoken dependency)
# ---------------------------------------------------------------------------

_JP_RANGES = (
    ("\u3000", "\u303f"),  # CJK punctuation
    ("\u3040", "\u309f"),  # Hiragana
    ("\u30a0", "\u30ff"),  # Katakana
    ("\u4e00", "\u9fff"),  # CJK Unified Ideographs
    ("\uff00", "\uffef"),  # Fullwidth forms
)


def _is_japanese_char(ch: str) -> bool:
    """Return True if *ch* is in a Japanese Unicode range."""
    for lo, hi in _JP_RANGES:
        if lo <= ch <= hi:
            return True
    cat = unicodedata.category(ch)
    return cat.startswith("Lo") and ord(ch) > 0x2E7F


def count_tokens(text: str) -> int:
    """Approximate token count for mixed Japanese / English text.

    Japanese characters map to ~0.6 tokens each (~1.67 chars/token).
    ASCII characters map to ~0.25 tokens each (~4 chars/token).
    """
    if not text:
        return 0

    jp_chars = sum(1 for ch in text if _is_japanese_char(ch))
    ascii_chars = len(text) - jp_chars

    tokens = jp_chars * 0.6 + ascii_chars * 0.25
    return max(1, int(tokens))


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def load_all_yaml_files(data_dir: Path) -> list[KnowledgeSection]:
    """Load and validate every ``*.yaml`` file under *data_dir*.

    Files are sorted by name for deterministic ordering.
    On failure the exception is logged with the offending file name
    before being re-raised so that callers get clear diagnostics.
    """
    yaml_files = sorted(data_dir.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No YAML files found in %s", data_dir)
        return []

    sections: list[KnowledgeSection] = []
    for path in yaml_files:
        logger.info("Loading %s", path.name)
        try:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
            section = KnowledgeSection(**raw)
            sections.append(section)
        except Exception:
            logger.exception("Failed to load %s", path.name)
            raise

    logger.info(
        "Loaded %d YAML files with %d total entries",
        len(sections),
        sum(len(s.entries) for s in sections),
    )
    return sections


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"(?<=[。．.!?！？\n])")


def _split_sentences(text: str) -> list[str]:
    """Split text at Japanese/English sentence boundaries."""
    parts = _SENTENCE_RE.split(text)
    return [p for p in parts if p.strip()]


def _apply_overlap(chunks: list[str], overlap_tokens: int) -> list[str]:
    """Prepend *overlap_tokens* worth of previous chunk text."""
    if overlap_tokens <= 0 or len(chunks) < 2:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        # Take trailing characters from prev that approximate overlap_tokens
        overlap_chars = int(overlap_tokens / 0.4)  # rough char estimate
        overlap_text = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
        result.append(overlap_text + chunks[i])
    return result


def _build_metadata(entry: KnowledgeEntry) -> dict[str, Any]:
    """Build a *fresh* metadata dict for a chunk derived from *entry*."""
    return {
        "tags": list(entry.tags),
        "priority": entry.priority,
        "verified": entry.verified,
    }


def _split_and_merge(content: str, strategy: ChunkingStrategy) -> list[str]:
    """Split *content* into paragraph/sentence parts and merge into chunks."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    raw_parts: list[str] = []
    for para in paragraphs:
        if count_tokens(para) > strategy.max_tokens:
            raw_parts.extend(_split_sentences(para))
        else:
            raw_parts.append(para)

    merged: list[str] = []
    buf = ""
    for part in raw_parts:
        candidate = (buf + "\n" + part).strip() if buf else part
        if count_tokens(candidate) > strategy.max_tokens and buf:
            merged.append(buf)
            buf = part
        else:
            buf = candidate
    if buf:
        merged.append(buf)

    return _apply_overlap(merged, strategy.overlap_tokens)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_entry(
    entry: KnowledgeEntry,
    strategy: ChunkingStrategy | None = None,
) -> list[KnowledgeChunk]:
    """Split a single *entry* into hierarchical chunks."""
    strategy = strategy or ChunkingStrategy()
    token_total = count_tokens(entry.content)

    # Small entry -> single document-level chunk
    if token_total <= strategy.max_tokens:
        return [
            KnowledgeChunk(
                entry_id=entry.id,
                chunk_level="document",
                chunk_index=0,
                title=entry.title,
                content=entry.content,
                token_count=token_total,
                category=entry.category,
                metadata=_build_metadata(entry),
            )
        ]

    # Large entry -> parent document + child chunks
    summary = entry.content[:200].rstrip() + "..."
    chunks: list[KnowledgeChunk] = [
        KnowledgeChunk(
            entry_id=entry.id,
            chunk_level="document",
            chunk_index=0,
            title=entry.title,
            content=summary,
            token_count=count_tokens(summary),
            category=entry.category,
            metadata=_build_metadata(entry),
        )
    ]

    merged = _split_and_merge(entry.content, strategy)
    child_index = 1
    for text in merged:
        tc = count_tokens(text)
        if tc < strategy.min_chunk_tokens:
            continue  # Skip too-small standalone chunks
        chunks.append(
            KnowledgeChunk(
                entry_id=entry.id,
                chunk_level="chunk",
                chunk_index=child_index,
                title=entry.title,
                content=text,
                token_count=tc,
                category=entry.category,
                metadata=_build_metadata(entry),
            )
        )
        child_index += 1

    return chunks


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


async def generate_chunks_with_embeddings(
    chunks: list[KnowledgeChunk],
) -> list[dict[str, Any]]:
    """Generate embeddings for every chunk and return Supabase-ready dicts.

    Child chunk titles are suffixed with ``[chunk N]`` to ensure
    uniqueness for ``on_conflict="title"`` upserts.
    """
    results: list[dict[str, Any]] = []

    for idx, chunk in enumerate(chunks):
        embedding = await generate_embedding(chunk.content)

        if not embedding:
            logger.warning(
                "Empty embedding for chunk %s index=%d – skipping",
                chunk.entry_id,
                chunk.chunk_index,
            )
            continue

        # Ensure title uniqueness per chunk to avoid on_conflict collisions
        title = chunk.title
        if chunk.chunk_level != "document":
            title = f"{chunk.title} [chunk {chunk.chunk_index}]"

        results.append(
            {
                "title": title,
                "content": chunk.content,
                "category": chunk.category,
                "metadata": chunk.metadata,
                "content_embedding": embedding,
                "chunk_level": chunk.chunk_level,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "entry_id": chunk.entry_id,
            }
        )

        # Rate-limit between calls (skip after last)
        if idx < len(chunks) - 1:
            await asyncio.sleep(1.0)

    logger.info("Generated embeddings for %d / %d chunks", len(results), len(chunks))
    return results


# ---------------------------------------------------------------------------
# Full seed pipeline
# ---------------------------------------------------------------------------


def _upsert_records(
    supabase_client: Any,
    records: list[dict[str, Any]],
    label: str,
) -> tuple[int, int]:
    """Upsert *records* to ``knowledge_base``. Returns ``(success, errors)``."""
    success = 0
    errors = 0
    for rec in records:
        try:
            supabase_client.table("knowledge_base").upsert(
                rec,
                on_conflict="title",
            ).execute()
            success += 1
        except Exception:
            logger.exception("Failed to upsert %s chunk: %s", label, rec["title"])
            errors += 1
    return success, errors


async def seed_from_yaml(
    supabase_client: Any,
    data_dir: Path,
    strategy: ChunkingStrategy | None = None,
) -> SeedResult:
    """Load YAML, chunk, embed, and upsert everything to Supabase."""
    strategy = strategy or ChunkingStrategy()

    sections = load_all_yaml_files(data_dir)
    all_chunks: list[KnowledgeChunk] = []
    for section in sections:
        for entry in section.entries:
            all_chunks.extend(chunk_entry(entry, strategy))

    if not all_chunks:
        logger.warning("No chunks produced – nothing to seed")
        return SeedResult(success_count=0, error_count=0, total_chunks=0, skipped_count=0)

    embedded = await generate_chunks_with_embeddings(all_chunks)
    skipped = len(all_chunks) - len(embedded)

    parents = [r for r in embedded if r["chunk_level"] == "document"]
    children = [r for r in embedded if r["chunk_level"] != "document"]

    p_ok, p_err = _upsert_records(supabase_client, parents, "parent")
    c_ok, c_err = _upsert_records(supabase_client, children, "child")

    result = SeedResult(
        success_count=p_ok + c_ok,
        error_count=p_err + c_err,
        total_chunks=len(all_chunks),
        skipped_count=skipped,
    )
    logger.info(
        "Seed complete: success=%d errors=%d total=%d skipped=%d",
        result.success_count,
        result.error_count,
        result.total_chunks,
        result.skipped_count,
    )
    return result
