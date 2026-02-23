"""イベントE2Eテスト"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestEventsE2E:
    async def test_today_events(self, invoke_workflow):
        result = await invoke_workflow("今日のイベントは何がありますか？")
        assert result["answer"]
        assert len(result["answer"]) > 20

    async def test_event_hosting(self, invoke_workflow):
        result = await invoke_workflow("イベントを開催したいのですが、どうすればいいですか？")
        assert result["answer"]
        assert_keywords(
            result["answer"], ["イベント", "開催", "申し込み", "connpass"], threshold=0.25
        )

    async def test_weekly_events(self, invoke_workflow):
        result = await invoke_workflow("今週末のイベント予定を教えてください")
        assert result["answer"]
        assert len(result["answer"]) > 20
