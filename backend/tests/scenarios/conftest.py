"""Scenario テスト用 conftest — 時刻依存テストの安定化.

Issue #434: test_conversation_flows の 6 テストが 21:40 JST 以降に
閉館警告 ("閉館まであと約20分") が自動追加されて失敗する問題を防止。
backend/tests/workflows/conftest.py と同じパターンを適用。
"""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

# 平日 15:00 JST = 閉館警告が出ない安全な時刻
SAFE_SCENARIO_TIME_JST = datetime(2026, 4, 1, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.fixture(autouse=True)
def _freeze_scenario_time():
    """全 scenario テストで get_now_jst() を固定し、時刻依存の flaky を防止."""
    with patch(
        "backend.utils.time_utils.get_now_jst",
        return_value=SAFE_SCENARIO_TIME_JST,
    ):
        yield
