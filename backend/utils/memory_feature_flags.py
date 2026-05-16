"""
Memory feature flags for gradual rollout.

段階導入用のメモリ機能フラグを一元管理する。
Settings キャッシュの影響を避けるため、都度 os.getenv を読む。
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_stm_write_disable_warning_emitted = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _agent_memory_stm_writes_enabled() -> bool:
    requested = _env_bool("ENABLE_AGENT_MEMORY_STM_WRITES", True)
    if requested:
        return True

    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    allow_production_disable = _env_bool("ALLOW_AGENT_MEMORY_STM_WRITE_DISABLE", False)
    if environment == "production" and not allow_production_disable:
        global _stm_write_disable_warning_emitted
        if not _stm_write_disable_warning_emitted:
            logger.warning(
                "Ignoring ENABLE_AGENT_MEMORY_STM_WRITES=false in production; "
                "set ALLOW_AGENT_MEMORY_STM_WRITE_DISABLE=true only after "
                "short-term memory reads no longer depend on agent_memory."
            )
            _stm_write_disable_warning_emitted = True
        return True

    return False


@dataclass(frozen=True)
class MemoryFeatureFlags:
    enable_memory_candidates: bool = False
    enable_memory_promotion: bool = False
    enable_style_profile: bool = False
    enable_long_term_memory_rerank: bool = False
    enable_agent_memory_stm_writes: bool = True


def get_memory_feature_flags() -> MemoryFeatureFlags:
    """環境変数からメモリ機能フラグを読み込む。"""
    return MemoryFeatureFlags(
        enable_memory_candidates=_env_bool("ENABLE_MEMORY_CANDIDATES", False),
        enable_memory_promotion=_env_bool("ENABLE_MEMORY_PROMOTION", False),
        enable_style_profile=_env_bool("ENABLE_STYLE_PROFILE", False),
        enable_long_term_memory_rerank=_env_bool("ENABLE_LONG_TERM_MEMORY_RERANK", False),
        enable_agent_memory_stm_writes=_agent_memory_stm_writes_enabled(),
    )
