from backend.utils.postgres_sanitizer import (
    contains_postgres_null_byte,
    sanitize_for_postgres,
)


def test_sanitize_for_postgres_handles_nested_values():
    value = {
        "ke\x00y": [
            "a\x00b",
            ("c\x00d", {"inner": "e\x00f"}),
            {"g\x00h"},
        ],
        "unchanged": 3,
    }

    assert sanitize_for_postgres(value) == {
        "key": [
            "ab",
            ("cd", {"inner": "ef"}),
            {"gh"},
        ],
        "unchanged": 3,
    }


def test_contains_postgres_null_byte_detects_nested_values():
    assert contains_postgres_null_byte({"nested": ["ok", "bad\x00value"]})
    assert not contains_postgres_null_byte({"nested": ["ok", "safe"]})
