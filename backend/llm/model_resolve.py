"""
Resolve OpenRouter / Cerebras model identifiers from env (no hardcoded production IDs).

Fast path: Cerebras can be used as the native first pass, with Gemini 3.1 Flash-Lite
preview on OpenRouter and Gemini 2.5 Flash-Lite as fallbacks.
Deep reasoning: override via DEEP_REASONING_MODEL (OpenRouter slug).
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.llm.models import ModelConfig

from backend.llm.models import SupportedModel

logger = logging.getLogger(__name__)

_DEFAULT_FAST_PRIMARY = SupportedModel.GEMINI_3_1_FLASH_LITE.value


def resolved_openrouter_model_slug(config: "ModelConfig", *, branch: str = "primary") -> str:
    """
    Return the effective OpenRouter model id for logging and API calls.

    branch:
      - "primary": config.model_id (plus env overrides)
      - "fallback": config.fallback_model (OpenRouter slug only)
    """
    if branch == "fallback":
        if not config.fallback_model:
            return _DEFAULT_FAST_PRIMARY
        return resolved_slug_for_supported(config.fallback_model)

    mid = config.model_id
    if mid == SupportedModel.GEMINI_3_1_FLASH_LITE:
        return os.getenv("FAST_LLM_PRIMARY_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GEMINI_2_5_FLASH_LITE:
        return os.getenv("FAST_LLM_FALLBACK_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GEMINI_3_1_PRO:
        return os.getenv("DEEP_REASONING_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GEMINI_2_5_PRO:
        return os.getenv("DEEP_REASONING_FALLBACK_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GPT_4_1_NANO:
        return os.getenv("VISION_MODEL", mid.value).strip() or mid.value
    return mid.value


def resolved_slug_for_supported(mid: SupportedModel) -> str:
    """Stable slug for SupportedModel respecting the same overrides as primaries."""
    if mid == SupportedModel.GEMINI_3_1_FLASH_LITE:
        return os.getenv("FAST_LLM_PRIMARY_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GEMINI_2_5_FLASH_LITE:
        return os.getenv("FAST_LLM_FALLBACK_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GEMINI_3_1_PRO:
        return os.getenv("DEEP_REASONING_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GEMINI_2_5_PRO:
        return os.getenv("DEEP_REASONING_FALLBACK_MODEL", mid.value).strip() or mid.value
    if mid == SupportedModel.GPT_4_1_NANO:
        return os.getenv("VISION_MODEL", mid.value).strip() or mid.value
    return mid.value


def is_fast_primary_config(config: "ModelConfig") -> bool:
    """Whether this config is the latency-optimized Gemini Flash-Lite tier."""
    return config.model_id == SupportedModel.GEMINI_3_1_FLASH_LITE


def fast_llm_enabled() -> bool:
    """Feature flag for fast LLM provider routing."""
    raw = os.getenv("FAST_LLM_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def cerebras_primary_enabled(config: "ModelConfig") -> bool:
    """Whether direct Cerebras should be attempted before OpenRouter for fast configs."""
    provider = os.getenv("FAST_LLM_PRIMARY_PROVIDER", "").strip().lower()
    key = os.getenv("CEREBRAS_API_KEY", "").strip()
    return (
        fast_llm_enabled()
        and provider == "cerebras"
        and bool(key)
        and bool(getattr(config, "allow_cerebras_primary", False))
        and is_fast_primary_config(config)
    )


def cerebras_fallback_enabled(config: "ModelConfig") -> bool:
    """After OpenRouter primary+fallback exhaustion, optionally call Cerebras."""
    provider = os.getenv("FAST_LLM_TERTIARY_PROVIDER", "").strip().lower()
    enabled = os.getenv("CEREBRAS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    key = os.getenv("CEREBRAS_API_KEY", "").strip()
    return (
        fast_llm_enabled()
        and (enabled or provider == "cerebras")
        and bool(key)
        and is_fast_primary_config(config)
    )


def cerebras_model_slug() -> str:
    """Cerebras model id (hosted id, not an OpenRouter slug)."""
    return os.getenv("CEREBRAS_FAST_MODEL", "gpt-oss-120b").strip() or "gpt-oss-120b"


def cerebras_reasoning_effort() -> str | None:
    raw = os.getenv("CEREBRAS_REASONING_EFFORT", "low").strip()
    return raw if raw else None


def merge_gemini_openrouter_extra(payload: dict) -> None:
    """Merge JSON from GEMINI_OPENROUTER_EXTRA_JSON into the completion payload (optional)."""
    extra = os.getenv("GEMINI_OPENROUTER_EXTRA_JSON", "").strip()
    if not extra:
        return
    try:
        data = json.loads(extra)
        if isinstance(data, dict):
            payload.update(data)
        else:
            logger.warning("GEMINI_OPENROUTER_EXTRA_JSON must be a JSON object; ignoring")
    except json.JSONDecodeError as e:
        logger.warning("Invalid GEMINI_OPENROUTER_EXTRA_JSON: %s", e)
