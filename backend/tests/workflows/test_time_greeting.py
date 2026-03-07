"""
format_response ノードの時間帯情報・閉館警告統合テスト

MainWorkflow._format_response_node() が time_period と closing_warning を
正しく metadata に設定し、閉館警告メッセージを応答に付加するかを検証する。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.workflows.main_workflow import MainWorkflow, WorkflowStateDict

JST = ZoneInfo("Asia/Tokyo")


@pytest.fixture
def workflow() -> MainWorkflow:
    """MainWorkflow インスタンスを提供するフィクスチャ。"""
    return MainWorkflow()


def _make_state(
    query: str = "テスト",
    answer: str = "テスト回答",
    language: str = "ja",
) -> WorkflowStateDict:
    """テスト用の WorkflowStateDict を生成する。"""
    return {
        "messages": [],
        "query": query,
        "session_id": "test-session",
        "language": language,
        "routing": {},
        "answer": answer,
        "emotion": "neutral",
        "metadata": {},
        "context": {},
        "image_data": None,
        "ocr_result": None,
    }


def _make_runtime() -> MagicMock:
    """テスト用モック Runtime を生成する。"""
    runtime = MagicMock()
    runtime.context = MagicMock()
    runtime.context.user_id = "anonymous"
    runtime.store = None
    return runtime


class TestFormatResponseTimePeriod:
    """format_response ノードの time_period テスト"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("hour", "expected_period"),
        [
            (9, "morning"),
            (14, "afternoon"),
            (18, "evening"),
            (22, "night"),
        ],
    )
    async def test_time_period_in_metadata(
        self, workflow: MainWorkflow, hour: int, expected_period: str
    ) -> None:
        """各時間帯が metadata.time_period に正しく設定されることを検証する。"""
        mock_now = datetime(2026, 3, 9, hour, 0, 0, tzinfo=JST)  # 月曜日
        state = _make_state()
        runtime = _make_runtime()

        with (
            patch("backend.utils.time_utils.get_now_jst", return_value=mock_now),
            patch.object(workflow, "_character_control_agent", None),
            patch("backend.utils.memory_helper.get_memory_helper") as mock_memory,
        ):
            mock_memory.return_value.store_message = AsyncMock()
            result = await workflow._format_response_node(state, runtime)

        assert result["metadata"]["time_period"] == expected_period


class TestFormatResponseClosingWarning:
    """format_response ノードの閉館警告テスト"""

    @pytest.mark.asyncio
    async def test_closing_warning_when_closing_soon(self, workflow: MainWorkflow) -> None:
        """閉館30分前に警告が metadata に設定されることを検証する。"""
        # 2026-03-09 21:35 JST（月曜 = weekday 0）
        mock_now = datetime(2026, 3, 9, 21, 35, 0, tzinfo=JST)
        state = _make_state()
        runtime = _make_runtime()

        with (
            patch("backend.utils.time_utils.get_now_jst", return_value=mock_now),
            patch.object(workflow, "_character_control_agent", None),
            patch("backend.utils.memory_helper.get_memory_helper") as mock_memory,
        ):
            mock_memory.return_value.store_message = AsyncMock()
            result = await workflow._format_response_node(state, runtime)

        closing = result["metadata"]["closing_warning"]
        assert closing["is_closing_soon"] is True
        assert closing["minutes_remaining"] == 25

    @pytest.mark.asyncio
    async def test_no_closing_warning_when_far_from_closing(self, workflow: MainWorkflow) -> None:
        """閉館まで余裕がある場合、警告が出ないことを検証する。"""
        # 2026-03-09 15:00 JST（月曜）
        mock_now = datetime(2026, 3, 9, 15, 0, 0, tzinfo=JST)
        state = _make_state()
        runtime = _make_runtime()

        with (
            patch("backend.utils.time_utils.get_now_jst", return_value=mock_now),
            patch.object(workflow, "_character_control_agent", None),
            patch("backend.utils.memory_helper.get_memory_helper") as mock_memory,
        ):
            mock_memory.return_value.store_message = AsyncMock()
            result = await workflow._format_response_node(state, runtime)

        closing = result["metadata"]["closing_warning"]
        assert closing["is_closing_soon"] is False

    @pytest.mark.asyncio
    async def test_closing_warning_appended_to_answer_ja(self, workflow: MainWorkflow) -> None:
        """閉館警告が日本語応答に付加されることを検証する。"""
        mock_now = datetime(2026, 3, 9, 21, 40, 0, tzinfo=JST)
        state = _make_state(answer="元の回答です。", language="ja")
        runtime = _make_runtime()

        with (
            patch("backend.utils.time_utils.get_now_jst", return_value=mock_now),
            patch.object(workflow, "_character_control_agent", None),
            patch("backend.utils.memory_helper.get_memory_helper") as mock_memory,
        ):
            mock_memory.return_value.store_message = AsyncMock()
            result = await workflow._format_response_node(state, runtime)

        # AIMessage の content を確認
        ai_message = result["messages"][-1]
        assert "元の回答です。" in ai_message.content
        assert "閉館まであと約20分" in ai_message.content

    @pytest.mark.asyncio
    async def test_closing_warning_appended_to_answer_en(self, workflow: MainWorkflow) -> None:
        """閉館警告が英語応答に付加されることを検証する。"""
        mock_now = datetime(2026, 3, 9, 21, 45, 0, tzinfo=JST)
        state = _make_state(answer="Original answer.", language="en")
        runtime = _make_runtime()

        with (
            patch("backend.utils.time_utils.get_now_jst", return_value=mock_now),
            patch.object(workflow, "_character_control_agent", None),
            patch("backend.utils.memory_helper.get_memory_helper") as mock_memory,
        ):
            mock_memory.return_value.store_message = AsyncMock()
            result = await workflow._format_response_node(state, runtime)

        ai_message = result["messages"][-1]
        assert "Original answer." in ai_message.content
        assert "closing in about 15 minutes" in ai_message.content

    @pytest.mark.asyncio
    async def test_no_warning_on_closed_day(self, workflow: MainWorkflow) -> None:
        """休館日には閉館警告が出ないことを検証する。"""
        # 2026-03-08 は日曜日 (weekday=6)
        mock_now = datetime(2026, 3, 8, 21, 35, 0, tzinfo=JST)
        state = _make_state()
        runtime = _make_runtime()

        with (
            patch("backend.utils.time_utils.get_now_jst", return_value=mock_now),
            patch.object(workflow, "_character_control_agent", None),
            patch("backend.utils.memory_helper.get_memory_helper") as mock_memory,
        ):
            mock_memory.return_value.store_message = AsyncMock()
            result = await workflow._format_response_node(state, runtime)

        closing = result["metadata"]["closing_warning"]
        assert closing["is_closing_soon"] is False
