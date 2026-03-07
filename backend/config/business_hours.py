"""
営業時間設定

エンジニアカフェの営業時間、タイムゾーンなどの設定を管理する。
ハードコードを避け、設定変更に柔軟に対応できるようにする。
"""

# エンジニアカフェ営業時間設定
# weekday: 月-金, saturday: 土, sunday: 日, holiday: 祝日
# None は休館日を表す
BUSINESS_HOURS: dict[str, dict[str, str] | None] = {
    "weekday": {"open": "09:00", "close": "22:00"},
    "saturday": {"open": "09:00", "close": "22:00"},
    "sunday": None,
    "holiday": None,
}

# 閉館警告を表示する閉館前の分数
CLOSING_WARNING_MINUTES: int = 30

# タイムゾーン（IANA識別子）
TIMEZONE: str = "Asia/Tokyo"
