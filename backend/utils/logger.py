"""
ロギングユーティリティ
統一されたロギング設定
"""

import logging
import sys
from typing import Optional
import os


def setup_logging(level: Optional[str] = None) -> None:
    """ロギングのセットアップ"""
    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_logger(name: str) -> logging.Logger:
    """ロガーを取得"""
    return logging.getLogger(name)

