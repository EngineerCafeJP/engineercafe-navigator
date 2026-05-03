"""
StructuredFormatter ユーティリティのユニットテスト

JSON 出力フォーマット、必須フィールド、追加フィールド、
request_id ContextVar、generate_request_id を検証する。
"""

import json
import logging
import re

from backend.utils.structured_logging import (
    StructuredFormatter,
    generate_request_id,
    request_id_var,
    setup_structured_logging,
)

# ============================================
# Helpers
# ============================================


def _make_log_record(
    message: str = "test message",
    level: int = logging.INFO,
    logger_name: str = "test.logger",
    **extra,
) -> logging.LogRecord:
    """テスト用の LogRecord を作成する"""
    record = logging.LogRecord(
        name=logger_name,
        level=level,
        pathname="test_file.py",
        lineno=42,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


# ============================================
# format() - JSON output
# ============================================


def test_format_outputs_json():
    """format() が有効な JSON 文字列を返す"""
    formatter = StructuredFormatter()
    record = _make_log_record()

    output = formatter.format(record)

    parsed = json.loads(output)  # Raises if invalid JSON
    assert isinstance(parsed, dict)


# ============================================
# Required fields
# ============================================


def test_format_includes_required_fields():
    """出力に timestamp, level, message, logger が含まれる"""
    formatter = StructuredFormatter()
    record = _make_log_record(
        message="hello world",
        level=logging.WARNING,
        logger_name="my.logger",
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "timestamp" in parsed
    assert parsed["level"] == "WARNING"
    assert parsed["message"] == "hello world"
    assert parsed["logger"] == "my.logger"


# ============================================
# Extra fields
# ============================================


def test_format_includes_extra_fields():
    """LogRecord に付加した追加データが extra に出力される"""
    formatter = StructuredFormatter()
    record = _make_log_record(custom_field="custom_value", another_field=123)

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "extra" in parsed
    assert parsed["extra"]["custom_field"] == "custom_value"
    assert parsed["extra"]["another_field"] == 123


# ============================================
# request_id context
# ============================================


def test_request_id_context():
    """request_id_var にセットした値がログ出力に含まれる"""
    formatter = StructuredFormatter()
    record = _make_log_record()

    token = request_id_var.set("req-abc-123")
    try:
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["request_id"] == "req-abc-123"
    finally:
        request_id_var.reset(token)


# ============================================
# generate_request_id()
# ============================================


def test_generate_request_id():
    """generate_request_id() が 16 文字の hex 文字列を返す"""
    rid = generate_request_id()

    assert isinstance(rid, str)
    assert len(rid) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", rid)

    # 毎回異なる値を生成する
    rid2 = generate_request_id()
    assert rid != rid2


def test_setup_structured_logging_quiets_access_and_http_client_loggers():
    original_handlers = logging.getLogger().handlers[:]
    original_level = logging.getLogger().level
    access_level = logging.getLogger("uvicorn.access").level
    httpx_level = logging.getLogger("httpx").level
    httpcore_level = logging.getLogger("httpcore").level

    try:
        setup_structured_logging()

        assert logging.getLogger("uvicorn.access").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
    finally:
        root = logging.getLogger()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
        logging.getLogger("uvicorn.access").setLevel(access_level)
        logging.getLogger("httpx").setLevel(httpx_level)
        logging.getLogger("httpcore").setLevel(httpcore_level)
