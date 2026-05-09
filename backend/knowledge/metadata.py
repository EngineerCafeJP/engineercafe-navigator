"""Metadata normalization for knowledge ingestion paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

MetadataReservedPolicy = Literal["allow", "drop", "reject"]

RESERVED_METADATA_FIELDS = frozenset(
    {
        "chunk_index",
        "chunk_level",
        "chunks_created",
        "document_id",
        "entry_id",
        "failed_chunks",
        "file_type",
        "language",
        "original_filename",
        "total_chunks",
    }
)

MAX_METADATA_KEYS = 50
MAX_METADATA_DEPTH = 4
MAX_METADATA_STRING_LENGTH = 1000
MAX_METADATA_SEQUENCE_LENGTH = 50


class MetadataValidationError(ValueError):
    """Raised when user-supplied knowledge metadata is not safe to persist."""


def normalize_user_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    reserved_policy: MetadataReservedPolicy = "reject",
) -> dict[str, Any]:
    """Validate and copy user metadata for knowledge ingestion.

    The RAG upload path owns document identity and chunk accounting fields. Text
    CRUD rejects those reserved keys to avoid retrieval-invisible or
    document-masquerading rows. File upload can drop them because generated
    metadata is applied immediately after user metadata.
    """

    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise MetadataValidationError("metadata must be a JSON object")

    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key.strip():
            raise MetadataValidationError("metadata keys must be non-empty strings")
        if key in RESERVED_METADATA_FIELDS:
            if reserved_policy == "drop":
                continue
            if reserved_policy == "reject":
                raise MetadataValidationError(f"metadata field '{key}' is reserved")
        normalized[key] = _normalize_metadata_value(value, path=key, depth=0)

    if len(normalized) > MAX_METADATA_KEYS:
        raise MetadataValidationError(f"metadata must contain at most {MAX_METADATA_KEYS} keys")
    return normalized


def _normalize_metadata_value(value: Any, *, path: str, depth: int) -> Any:
    if depth > MAX_METADATA_DEPTH:
        raise MetadataValidationError(
            f"metadata field '{path}' exceeds maximum depth of {MAX_METADATA_DEPTH}"
        )

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        if len(value) > MAX_METADATA_STRING_LENGTH:
            raise MetadataValidationError(
                f"metadata field '{path}' exceeds {MAX_METADATA_STRING_LENGTH} characters"
            )
        return value

    if isinstance(value, Mapping):
        if len(value) > MAX_METADATA_KEYS:
            raise MetadataValidationError(
                f"metadata field '{path}' must contain at most {MAX_METADATA_KEYS} keys"
            )
        normalized: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if not isinstance(child_key, str) or not child_key.strip():
                raise MetadataValidationError(f"metadata field '{path}' contains a non-string key")
            child_path = f"{path}.{child_key}"
            normalized[child_key] = _normalize_metadata_value(
                child_value,
                path=child_path,
                depth=depth + 1,
            )
        return normalized

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) > MAX_METADATA_SEQUENCE_LENGTH:
            raise MetadataValidationError(
                f"metadata field '{path}' must contain at most "
                f"{MAX_METADATA_SEQUENCE_LENGTH} items"
            )
        return [
            _normalize_metadata_value(item, path=f"{path}[]", depth=depth + 1) for item in value
        ]

    raise MetadataValidationError(
        f"metadata field '{path}' must be a JSON scalar, object, or array"
    )
