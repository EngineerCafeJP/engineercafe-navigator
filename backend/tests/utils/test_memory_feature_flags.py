"""Tests for backend.utils.memory_feature_flags."""

import os
from unittest.mock import patch

from backend.utils.memory_feature_flags import get_memory_feature_flags


class TestMemoryFeatureFlags:
    def test_rollout_defaults_are_disabled_but_stm_writes_remain_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            flags = get_memory_feature_flags()
            assert flags.enable_memory_candidates is False
            assert flags.enable_memory_promotion is False
            assert flags.enable_style_profile is False
            assert flags.enable_long_term_memory_rerank is False
            assert flags.enable_agent_memory_stm_writes is True

    def test_truthy_values_enable_flags(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_MEMORY_CANDIDATES": "true",
                "ENABLE_MEMORY_PROMOTION": "1",
                "ENABLE_STYLE_PROFILE": "on",
                "ENABLE_LONG_TERM_MEMORY_RERANK": "YES",
                "ENABLE_AGENT_MEMORY_STM_WRITES": "false",
            },
            clear=True,
        ):
            flags = get_memory_feature_flags()
            assert flags.enable_memory_candidates is True
            assert flags.enable_memory_promotion is True
            assert flags.enable_style_profile is True
            assert flags.enable_long_term_memory_rerank is True
            assert flags.enable_agent_memory_stm_writes is False

    def test_production_keeps_stm_writes_enabled_without_explicit_override(self):
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "ENABLE_AGENT_MEMORY_STM_WRITES": "false",
            },
            clear=True,
        ):
            flags = get_memory_feature_flags()
            assert flags.enable_agent_memory_stm_writes is True

    def test_production_stm_write_disable_requires_explicit_override(self):
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "ENABLE_AGENT_MEMORY_STM_WRITES": "false",
                "ALLOW_AGENT_MEMORY_STM_WRITE_DISABLE": "true",
            },
            clear=True,
        ):
            flags = get_memory_feature_flags()
            assert flags.enable_agent_memory_stm_writes is False
