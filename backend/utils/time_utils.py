"""
時間帯判定・閉館警告ユーティリティ

エンジニアカフェの営業時間に基づく時間帯判定、閉館警告、
営業時間取得などの機能を提供する。
"""

import calendar
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from backend.config.business_hours import BUSINESS_HOURS, CLOSING_WARNING_MINUTES, TIMEZONE

JST = ZoneInfo(TIMEZONE)


def get_current_time_period(hour: int) -> str:
    """0-23の時刻から時間帯を判定する。

    Args:
        hour: 0-23の時刻（24時間制）。

    Returns:
        時間帯を表す文字列。"morning", "afternoon", "evening", "night" のいずれか。

    Raises:
        ValueError: hourが0-23の範囲外の場合。
    """
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be between 0 and 23, got {hour}")

    if 5 <= hour <= 11:
        return "morning"
    elif 12 <= hour <= 16:
        return "afternoon"
    elif 17 <= hour <= 20:
        return "evening"
    else:
        return "night"


def is_closing_soon(
    current_time: datetime,
    closing_hour: int,
    closing_minute: int,
    margin_minutes: int = CLOSING_WARNING_MINUTES,
) -> bool:
    """閉館時間のmargin_minutes分前以内かどうかを判定する。

    閉館時間を過ぎている場合はFalseを返す（既に閉館しているため警告不要）。

    Args:
        current_time: 現在時刻。
        closing_hour: 閉館時間の時（0-23）。
        closing_minute: 閉館時間の分（0-59）。
        margin_minutes: 警告を出す閉館前の分数。デフォルトは設定値。

    Returns:
        閉館margin_minutes分前以内であればTrue。
    """
    remaining = get_minutes_until_closing(current_time, closing_hour, closing_minute)
    return 0 < remaining <= margin_minutes


def get_minutes_until_closing(
    current_time: datetime,
    closing_hour: int,
    closing_minute: int,
) -> int:
    """閉館までの残り分数を返す。

    閉館時間を過ぎている場合は0を返す。

    Args:
        current_time: 現在時刻。
        closing_hour: 閉館時間の時（0-23）。
        closing_minute: 閉館時間の分（0-59）。

    Returns:
        閉館までの残り分数。閉館後は0。
    """
    closing_time = current_time.replace(
        hour=closing_hour, minute=closing_minute, second=0, microsecond=0
    )
    diff = closing_time - current_time
    total_minutes = int(diff.total_seconds() // 60)
    return max(0, total_minutes)


def get_today_business_hours(
    weekday: int,
    config: dict[str, dict[str, str] | None] | None = None,
) -> tuple[time, time] | None:
    """曜日に応じた営業時間を返す。

    Args:
        weekday: 曜日（0=月曜, 6=日曜）。datetime.weekday()の戻り値に対応。
        config: 営業時間設定辞書。Noneの場合はsettings.BUSINESS_HOURSを使用。

    Returns:
        (開店時間, 閉店時間) のタプル。休館日の場合はNone。

    Raises:
        ValueError: weekdayが0-6の範囲外の場合。
    """
    if not 0 <= weekday <= 6:
        raise ValueError(f"weekday must be between 0 and 6, got {weekday}")

    if config is None:
        config = BUSINESS_HOURS

    if weekday == 6:
        hours = config.get("sunday")
    elif weekday == 5:
        hours = config.get("saturday")
    else:
        hours = config.get("weekday")

    if hours is None:
        return None

    open_parts = hours["open"].split(":")
    close_parts = hours["close"].split(":")

    open_time = time(int(open_parts[0]), int(open_parts[1]))
    close_time = time(int(close_parts[0]), int(close_parts[1]))

    return (open_time, close_time)


def is_engineer_cafe_closed_date(target_date: date) -> bool:
    """エンジニアカフェの定期休館日に該当するかを返す。"""
    if (target_date.month, target_date.day) >= (12, 29) or (target_date.month, target_date.day) <= (
        1,
        3,
    ):
        return True

    if target_date.weekday() != 0:
        return False

    last_day = calendar.monthrange(target_date.year, target_date.month)[1]
    return target_date.day + 7 > last_day


def get_business_hours_for_date(target: date | datetime) -> tuple[time, time] | None:
    """日付を考慮したエンジニアカフェの営業時間を返す。"""
    target_date = target.date() if isinstance(target, datetime) else target
    if is_engineer_cafe_closed_date(target_date):
        return None
    return get_today_business_hours(target_date.weekday())


def get_now_jst() -> datetime:
    """現在のJST時刻を取得する。

    Returns:
        JSTタイムゾーンの現在時刻。
    """
    return datetime.now(tz=JST)
