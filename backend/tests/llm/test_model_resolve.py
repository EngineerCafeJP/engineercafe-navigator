"""
Tests for LLM model/provider routing resolution.
"""

import pytest

from backend.llm.model_resolve import (
    cerebras_primary_enabled,
    cerebras_primary_use_cases,
    openrouter_timeout_seconds,
    resolved_openrouter_model_slug,
)
from backend.llm.models import MODEL_CONFIGS
from backend.llm.models import ModelConfig, SupportedModel


def _enable_cerebras_primary_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAST_LLM_ENABLED", "true")
    monkeypatch.setenv("FAST_LLM_PRIMARY_PROVIDER", "cerebras")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test_cerebras_key")


@pytest.mark.parametrize(
    "use_case",
    ["qa_response", "general_knowledge", "event_info", "facility_info"],
)
def test_default_cerebras_primary_use_cases_include_lightweight_responses(
    monkeypatch: pytest.MonkeyPatch, use_case: str
):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.delenv("CEREBRAS_PRIMARY_USE_CASES", raising=False)

    assert cerebras_primary_enabled(MODEL_CONFIGS[use_case]) is True


@pytest.mark.parametrize(
    "use_case",
    ["router", "clarification", "deep_reasoning", "vision", "vision_handwriting"],
)
def test_cerebras_primary_does_not_apply_to_non_response_configs(
    monkeypatch: pytest.MonkeyPatch, use_case: str
):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.delenv("CEREBRAS_PRIMARY_USE_CASES", raising=False)

    assert cerebras_primary_enabled(MODEL_CONFIGS[use_case]) is False


def test_cerebras_primary_use_cases_can_narrow_response_surface(
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.setenv("CEREBRAS_PRIMARY_USE_CASES", "qa_response,general_knowledge")

    assert cerebras_primary_enabled(MODEL_CONFIGS["qa_response"]) is True
    assert cerebras_primary_enabled(MODEL_CONFIGS["general_knowledge"]) is True
    assert cerebras_primary_enabled(MODEL_CONFIGS["event_info"]) is False
    assert cerebras_primary_enabled(MODEL_CONFIGS["facility_info"]) is False


@pytest.mark.parametrize("raw_value", ["none", "off", "false", ""])
def test_cerebras_primary_use_cases_can_disable_primary(
    monkeypatch: pytest.MonkeyPatch, raw_value: str
):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.setenv("CEREBRAS_PRIMARY_USE_CASES", raw_value)

    assert cerebras_primary_use_cases() == frozenset()
    assert cerebras_primary_enabled(MODEL_CONFIGS["qa_response"]) is False


def test_cerebras_primary_requires_fast_llm_flag(monkeypatch: pytest.MonkeyPatch):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.setenv("FAST_LLM_ENABLED", "false")

    assert cerebras_primary_enabled(MODEL_CONFIGS["facility_info"]) is False


def test_cerebras_primary_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.setenv("CEREBRAS_API_KEY", "")

    assert cerebras_primary_enabled(MODEL_CONFIGS["event_info"]) is False


def test_cerebras_primary_requires_named_use_case_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_cerebras_primary_env(monkeypatch)
    config = ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        allow_cerebras_primary=True,
    )

    assert cerebras_primary_enabled(config) is False


def test_cerebras_primary_allows_explicit_all_for_opted_in_configs(
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_cerebras_primary_env(monkeypatch)
    monkeypatch.setenv("CEREBRAS_PRIMARY_USE_CASES", "all")

    assert cerebras_primary_use_cases() is None
    assert cerebras_primary_enabled(MODEL_CONFIGS["facility_info"]) is True
    assert cerebras_primary_enabled(MODEL_CONFIGS["router"]) is False


def test_openrouter_fast_timeout_default_is_bounded(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("FAST_LLM_TIMEOUT_SECONDS", raising=False)

    config = ModelConfig(
        model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
        fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
        timeout=30.0,
    )

    assert openrouter_timeout_seconds(config) == 8.0


def test_openrouter_timeout_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "2.25")

    assert openrouter_timeout_seconds(MODEL_CONFIGS["qa_response"]) == 2.25


def test_openrouter_model_slug_honors_config_specific_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("VISION_HANDWRITING_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("VISION_HANDWRITING_FALLBACK_MODEL", "openai/gpt-4.1-mini")

    config = MODEL_CONFIGS["vision_handwriting"]

    assert resolved_openrouter_model_slug(config) == "openai/gpt-4o"
    assert resolved_openrouter_model_slug(config, branch="fallback") == "openai/gpt-4.1-mini"
