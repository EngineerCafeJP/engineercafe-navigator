"""Utilities for making values safe for PostgreSQL text and JSON storage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

_T = TypeVar("_T")

POSTGRES_NULL_BYTE = "\x00"


def sanitize_for_postgres(value: _T) -> _T:
    """Return ``value`` with NUL bytes removed from all nested strings.

    PostgreSQL rejects U+0000 in both text and json/jsonb values. psycopg's JSON
    adapter serializes Python NUL bytes as ``\\u0000``, which PostgreSQL then
    rejects while decoding json/jsonb. Removing only NUL bytes keeps the rest of
    the user-provided text intact.
    """
    if isinstance(value, str):
        return cast(_T, value.replace(POSTGRES_NULL_BYTE, ""))

    if isinstance(value, Mapping):
        return cast(
            _T,
            {
                sanitize_for_postgres(key): sanitize_for_postgres(item)
                for key, item in value.items()
            },
        )

    if isinstance(value, list):
        return cast(_T, [sanitize_for_postgres(item) for item in value])

    if isinstance(value, tuple):
        return cast(_T, tuple(sanitize_for_postgres(item) for item in value))

    if isinstance(value, set):
        return cast(_T, {sanitize_for_postgres(item) for item in value})

    return value


def contains_postgres_null_byte(value: Any) -> bool:
    """Return True when ``value`` contains a NUL byte in any nested string."""
    if isinstance(value, str):
        return POSTGRES_NULL_BYTE in value

    if isinstance(value, Mapping):
        return any(
            contains_postgres_null_byte(key) or contains_postgres_null_byte(item)
            for key, item in value.items()
        )

    if isinstance(value, list | tuple | set):
        return any(contains_postgres_null_byte(item) for item in value)

    return False
