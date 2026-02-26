"""Tests for backend.utils.memory_feature_flags."""

import os
from unittest.mock import patch

from backend.utils.memory_feature_flags import get_memory_feature_flags


class TestMemoryFeatureFlags:
    def test_defaults_are_all_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            flags = get_memory_feature_flags()
            assert flags.enable_memory_candidates is False
            assert flags.enable_memory_promotion is False
            assert flags.enable_style_profile is False
            assert flags.enable_long_term_memory_rerank is False

    def test_truthy_values_enable_flags(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_MEMORY_CANDIDATES": "true",
                "ENABLE_MEMORY_PROMOTION": "1",
                "ENABLE_STYLE_PROFILE": "on",
                "ENABLE_LONG_TERM_MEMORY_RERANK": "YES",
            },
            clear=True,
        ):
            flags = get_memory_feature_flags()
            assert flags.enable_memory_candidates is True
            assert flags.enable_memory_promotion is True
            assert flags.enable_style_profile is True
            assert flags.enable_long_term_memory_rerank is True
