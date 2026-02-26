"""
Memory feature flags for gradual rollout.

段階導入用のメモリ機能フラグを一元管理する。
Settings キャッシュの影響を避けるため、都度 os.getenv を読む。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MemoryFeatureFlags:
    enable_memory_candidates: bool = False
    enable_memory_promotion: bool = False
    enable_style_profile: bool = False
    enable_long_term_memory_rerank: bool = False


def get_memory_feature_flags() -> MemoryFeatureFlags:
    """環境変数からメモリ機能フラグを読み込む。"""
    return MemoryFeatureFlags(
        enable_memory_candidates=_env_bool("ENABLE_MEMORY_CANDIDATES", False),
        enable_memory_promotion=_env_bool("ENABLE_MEMORY_PROMOTION", False),
        enable_style_profile=_env_bool("ENABLE_STYLE_PROFILE", False),
        enable_long_term_memory_rerank=_env_bool("ENABLE_LONG_TERM_MEMORY_RERANK", False),
    )

