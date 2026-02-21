"""Knowledge management package for Engineer Cafe Navigator."""

from backend.knowledge.classifier import (
    ClassificationResult,
    DuplicatePair,
    classify_entry,
    detect_duplicates,
)
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
from backend.knowledge.schema import KnowledgeEntry, KnowledgeSection

__all__ = [
    "ChunkingStrategy",
    "ClassificationResult",
    "DuplicatePair",
    "KnowledgeChunk",
    "KnowledgeEntry",
    "KnowledgeSection",
    "SeedResult",
    "chunk_entry",
    "classify_entry",
    "count_tokens",
    "detect_duplicates",
    "generate_chunks_with_embeddings",
    "load_all_yaml_files",
    "seed_from_yaml",
]
