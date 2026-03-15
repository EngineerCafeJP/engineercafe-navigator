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
