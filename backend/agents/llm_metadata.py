"""Helpers for propagating LLM observability metadata from provider returns."""

from typing import Any

LLM_METADATA_KEYS = ("provider", "model", "llm_latency_ms")


def extract_llm_metadata(response: Any) -> dict[str, Any]:
    """Extract provider/model/latency metadata carried by an LLM response object."""

    raw_metadata = getattr(response, "llm_metadata", None)
    if not isinstance(raw_metadata, dict):
        return {}
    return {
        key: raw_metadata[key] for key in LLM_METADATA_KEYS if raw_metadata.get(key) is not None
    }


def merge_llm_metadata(metadata: dict[str, Any], response: Any) -> dict[str, Any]:
    """Merge explicit LLM metadata into agent metadata without overwriting callers."""

    for key, value in extract_llm_metadata(response).items():
        metadata.setdefault(key, value)
    return metadata
