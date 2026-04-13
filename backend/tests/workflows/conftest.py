from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from unittest.mock import patch

SAFE_WORKFLOW_TIME_JST = datetime(2026, 1, 5, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.fixture(autouse=True)
def _freeze_workflow_time():
    """Keep workflow tests deterministic unless they patch time explicitly."""
    with patch("backend.utils.time_utils.get_now_jst", return_value=SAFE_WORKFLOW_TIME_JST):
        yield


@pytest.fixture(autouse=True)
def _disable_vrm_tts_duration_probe(monkeypatch):
    """Avoid real TTS calls in _format_response_node unless a test enables probing."""
    monkeypatch.setenv("VRM_TTS_DURATION_PROBE", "0")
