"""
time_utils モジュールのユニットテスト

時間帯判定、閉館警告、営業時間取得、残り分数計算をテストする。
"""

from datetime import datetime, time

import pytest

from backend.utils.time_utils import (
    JST,
    get_business_hours_for_date,
    get_current_time_period,
    get_minutes_until_closing,
    get_now_jst,
    get_today_business_hours,
    is_engineer_cafe_closed_date,
    is_closing_soon,
)


class TestGetCurrentTimePeriod:
    """get_current_time_period のテスト"""

    @pytest.mark.parametrize(
        ("hour", "expected"),
        [
            (5, "morning"),
            (6, "morning"),
            (9, "morning"),
            (11, "morning"),
            (12, "afternoon"),
            (14, "afternoon"),
            (16, "afternoon"),
            (17, "evening"),
            (19, "evening"),
            (20, "evening"),
            (21, "night"),
            (23, "night"),
            (0, "night"),
            (3, "night"),
            (4, "night"),
        ],
    )
    def test_time_period_mapping(self, hour: int, expected: str) -> None:
        """各時刻が正しい時間帯にマッピングされることを検証する。

        時間帯の境界値を含む全時間帯をテストする。
        """
        assert get_current_time_period(hour) == expected

    def test_boundary_morning_start(self) -> None:
        """morning の開始境界（5時）を検証する。"""
        assert get_current_time_period(4) == "night"
        assert get_current_time_period(5) == "morning"

    def test_boundary_morning_end(self) -> None:
        """morning の終了境界（11時）を検証する。"""
        assert get_current_time_period(11) == "morning"
        assert get_current_time_period(12) == "afternoon"

    def test_boundary_afternoon_end(self) -> None:
        """afternoon の終了境界（16時）を検証する。"""
        assert get_current_time_period(16) == "afternoon"
        assert get_current_time_period(17) == "evening"

    def test_boundary_evening_end(self) -> None:
        """evening の終了境界（20時）を検証する。"""
        assert get_current_time_period(20) == "evening"
        assert get_current_time_period(21) == "night"

    def test_invalid_hour_negative(self) -> None:
        """負の時刻でValueErrorが発生することを検証する。"""
        with pytest.raises(ValueError, match="hour must be between 0 and 23"):
            get_current_time_period(-1)

    def test_invalid_hour_over_23(self) -> None:
        """24以上の時刻でValueErrorが発生することを検証する。"""
        with pytest.raises(ValueError, match="hour must be between 0 and 23"):
            get_current_time_period(24)


class TestIsClosingSoon:
    """is_closing_soon のテスト"""

    def _make_time(self, hour: int, minute: int) -> datetime:
        """テスト用のJST datetimeを生成する。"""
        return datetime(2026, 3, 7, hour, minute, 0, tzinfo=JST)

    def test_closing_in_30_minutes(self) -> None:
        """閉館ちょうど30分前はTrue。"""
        current = self._make_time(21, 30)
        assert is_closing_soon(current, 22, 0, margin_minutes=30) is True

    def test_closing_in_29_minutes(self) -> None:
        """閉館29分前はTrue。"""
        current = self._make_time(21, 31)
        assert is_closing_soon(current, 22, 0, margin_minutes=30) is True

    def test_closing_in_1_minute(self) -> None:
        """閉館1分前はTrue。"""
        current = self._make_time(21, 59)
        assert is_closing_soon(current, 22, 0, margin_minutes=30) is True

    def test_closing_in_31_minutes(self) -> None:
        """閉館31分前はFalse（マージン外）。"""
        current = self._make_time(21, 29)
        assert is_closing_soon(current, 22, 0, margin_minutes=30) is False

    def test_already_closed(self) -> None:
        """閉館後はFalse。"""
        current = self._make_time(22, 1)
        assert is_closing_soon(current, 22, 0, margin_minutes=30) is False

    def test_exactly_at_closing(self) -> None:
        """閉館時刻ちょうどはFalse（残り0分 = 閉館済み扱い）。"""
        current = self._make_time(22, 0)
        assert is_closing_soon(current, 22, 0, margin_minutes=30) is False

    def test_custom_margin(self) -> None:
        """カスタムマージン（15分）の動作を検証する。"""
        current_inside = self._make_time(21, 46)
        current_outside = self._make_time(21, 44)
        assert is_closing_soon(current_inside, 22, 0, margin_minutes=15) is True
        assert is_closing_soon(current_outside, 22, 0, margin_minutes=15) is False

    def test_non_zero_closing_minute(self) -> None:
        """閉館時間が0分でない場合（例: 21:30閉館）を検証する。"""
        current = self._make_time(21, 5)
        assert is_closing_soon(current, 21, 30, margin_minutes=30) is True

        current_outside = self._make_time(20, 59)
        assert is_closing_soon(current_outside, 21, 30, margin_minutes=30) is False


class TestGetMinutesUntilClosing:
    """get_minutes_until_closing のテスト"""

    def _make_time(self, hour: int, minute: int) -> datetime:
        """テスト用のJST datetimeを生成する。"""
        return datetime(2026, 3, 7, hour, minute, 0, tzinfo=JST)

    def test_two_hours_before(self) -> None:
        """閉館2時間前は120分。"""
        current = self._make_time(20, 0)
        assert get_minutes_until_closing(current, 22, 0) == 120

    def test_30_minutes_before(self) -> None:
        """閉館30分前は30分。"""
        current = self._make_time(21, 30)
        assert get_minutes_until_closing(current, 22, 0) == 30

    def test_1_minute_before(self) -> None:
        """閉館1分前は1分。"""
        current = self._make_time(21, 59)
        assert get_minutes_until_closing(current, 22, 0) == 1

    def test_at_closing(self) -> None:
        """閉館時刻ちょうどは0分。"""
        current = self._make_time(22, 0)
        assert get_minutes_until_closing(current, 22, 0) == 0

    def test_after_closing(self) -> None:
        """閉館後は0分（負にならない）。"""
        current = self._make_time(22, 30)
        assert get_minutes_until_closing(current, 22, 0) == 0

    def test_with_seconds(self) -> None:
        """秒を含む時刻での計算を検証する。"""
        current = datetime(2026, 3, 7, 21, 30, 45, tzinfo=JST)
        # 21:30:45 -> 22:00:00 = 29分15秒 -> int(29*60+15 / 60) = 29
        result = get_minutes_until_closing(current, 22, 0)
        assert result == 29


class TestGetTodayBusinessHours:
    """get_today_business_hours のテスト"""

    def test_weekday_monday(self) -> None:
        """月曜日（weekday=0）の営業時間を検証する。"""
        result = get_today_business_hours(0)
        assert result is not None
        open_time, close_time = result
        assert open_time == time(9, 0)
        assert close_time == time(22, 0)

    def test_weekday_friday(self) -> None:
        """金曜日（weekday=4）の営業時間を検証する。"""
        result = get_today_business_hours(4)
        assert result is not None
        open_time, close_time = result
        assert open_time == time(9, 0)
        assert close_time == time(22, 0)

    def test_saturday(self) -> None:
        """土曜日（weekday=5）の営業時間を検証する。"""
        result = get_today_business_hours(5)
        assert result is not None
        open_time, close_time = result
        assert open_time == time(9, 0)
        assert close_time == time(22, 0)

    def test_sunday(self) -> None:
        """日曜日（weekday=6）の営業時間を検証する。"""
        result = get_today_business_hours(6)
        assert result is not None
        open_time, close_time = result
        assert open_time == time(9, 0)
        assert close_time == time(22, 0)

    def test_regular_closed_day_last_monday(self) -> None:
        """毎月最終月曜日は休館日として扱う。"""
        target = datetime(2026, 3, 30, 21, 30, tzinfo=JST).date()

        assert is_engineer_cafe_closed_date(target) is True
        assert get_business_hours_for_date(target) is None

    def test_regular_open_day_sunday(self) -> None:
        """最終月曜・年末年始以外の日曜は9:00-22:00で扱う。"""
        target = datetime(2026, 3, 8, 21, 30, tzinfo=JST)

        assert is_engineer_cafe_closed_date(target.date()) is False
        assert get_business_hours_for_date(target) == (time(9, 0), time(22, 0))

    def test_year_end_closed_day(self) -> None:
        """年末年始は休館日として扱う。"""
        target = datetime(2026, 12, 30, 12, 0, tzinfo=JST).date()

        assert is_engineer_cafe_closed_date(target) is True
        assert get_business_hours_for_date(target) is None

    def test_custom_config(self) -> None:
        """カスタム設定での営業時間取得を検証する。"""
        custom_config: dict[str, dict[str, str] | None] = {
            "weekday": {"open": "10:00", "close": "18:00"},
            "saturday": {"open": "10:00", "close": "17:00"},
            "sunday": {"open": "12:00", "close": "16:00"},
        }
        # 平日
        result = get_today_business_hours(0, config=custom_config)
        assert result is not None
        assert result[0] == time(10, 0)
        assert result[1] == time(18, 0)

        # 土曜
        result = get_today_business_hours(5, config=custom_config)
        assert result is not None
        assert result[1] == time(17, 0)

        # 日曜（カスタムで営業）
        result = get_today_business_hours(6, config=custom_config)
        assert result is not None
        assert result[0] == time(12, 0)

    def test_invalid_weekday_negative(self) -> None:
        """負のweekdayでValueErrorが発生することを検証する。"""
        with pytest.raises(ValueError, match="weekday must be between 0 and 6"):
            get_today_business_hours(-1)

    def test_invalid_weekday_over_6(self) -> None:
        """7以上のweekdayでValueErrorが発生することを検証する。"""
        with pytest.raises(ValueError, match="weekday must be between 0 and 6"):
            get_today_business_hours(7)


class TestGetNowJst:
    """get_now_jst のテスト"""

    def test_returns_jst_timezone(self) -> None:
        """返却される時刻がJSTタイムゾーンであることを検証する。"""
        now = get_now_jst()
        assert now.tzinfo is not None
        # ZoneInfoのタイムゾーン名を確認
        assert str(now.tzinfo) == "Asia/Tokyo"

    def test_returns_datetime(self) -> None:
        """datetimeオブジェクトが返却されることを検証する。"""
        now = get_now_jst()
        assert isinstance(now, datetime)
