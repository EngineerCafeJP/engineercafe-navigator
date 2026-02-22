"""
構造化ログ + リクエストトレーシング

JSON形式のログフォーマッターとリクエストID伝播のためのユーティリティ。
"""

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# リクエストスコープのコンテキスト変数
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """現在のリクエストIDを取得"""
    return request_id_var.get()


def generate_request_id() -> str:
    """新しいリクエストIDを生成"""
    return uuid.uuid4().hex[:16]


class StructuredFormatter(logging.Formatter):
    """JSON構造化ログフォーマッター"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # リクエストIDをコンテキストから取得
        req_id = request_id_var.get()
        if req_id:
            log_data["request_id"] = req_id

        # ソース情報
        log_data["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # 例外情報
        if record.exc_info and record.exc_info[1]:
            import traceback as tb_module

            log_data["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(tb_module.format_exception(*record.exc_info)),
            }

        # 追加フィールド
        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__
            and k
            not in (
                "name",
                "msg",
                "args",
                "created",
                "relativeCreated",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "pathname",
                "filename",
                "module",
                "levelno",
                "levelname",
                "msecs",
                "thread",
                "threadName",
                "process",
                "processName",
                "message",
                "taskName",
            )
        }
        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """構造化ログを設定

    Args:
        level: ログレベル
    """
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
