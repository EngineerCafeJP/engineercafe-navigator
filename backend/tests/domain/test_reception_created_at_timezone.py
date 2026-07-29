"""受付セッションの created_at がタイムゾーン付き UTC であることの回帰テスト (#925)。

Bug: ``created_at`` が naive な ``datetime.now()`` で採番されると、
``TZ=Asia/Tokyo`` のコンテナ上では JST 壁時計時刻になり、
オフセットなしで ``TIMESTAMPTZ`` 列へ挿入されて +9h 未来にずれる。
その行は ``order by created_at desc`` で永久に勝ち続け、
受付 stage が最初の ``greeting`` から進まなくなる。
"""

import os
import time
from datetime import datetime, timedelta, timezone

from backend.api.reception import _serialize_session
from backend.domain.reception.models import ReceptionSession


class TestReceptionSessionCreatedAt:
    def test_created_at_is_timezone_aware(self) -> None:
        session = ReceptionSession(session_id="s-1")
        assert session.created_at.tzinfo is not None, "created_at が naive（+9h ずれの原因）"

    def test_created_at_is_utc(self) -> None:
        session = ReceptionSession(session_id="s-1")
        assert session.created_at.utcoffset() == timedelta(0)

    def test_created_at_is_close_to_real_utc_now(self) -> None:
        """JST 壁時計時刻が混入すると 9 時間ずれるため、大きな乖離を検出する。"""
        before = datetime.now(timezone.utc)
        session = ReceptionSession(session_id="s-1")
        after = datetime.now(timezone.utc)
        assert before - timedelta(seconds=5) <= session.created_at <= after + timedelta(seconds=5)

    def test_created_at_is_utc_even_under_asia_tokyo_tz(self) -> None:
        """コンテナと同じ TZ=Asia/Tokyo でも UTC で採番されること。"""
        original = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Tokyo"
        try:
            if hasattr(time, "tzset"):
                time.tzset()
            session = ReceptionSession(session_id="s-1")
            skew = abs((session.created_at - datetime.now(timezone.utc)).total_seconds())
            assert skew < 60, f"UTC から {skew}s ずれている（JST 壁時計時刻の混入）"
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            if hasattr(time, "tzset"):
                time.tzset()


class TestSerializedCreatedAtCarriesOffset:
    def test_serialized_created_at_includes_utc_offset(self) -> None:
        """DB へ渡す文字列にオフセットが含まれること。

        オフセットが無い文字列は TIMESTAMPTZ 列で UTC とみなされるため、
        JST 壁時計時刻がそのまま +9h の未来として保存されてしまう。
        """
        session = ReceptionSession(session_id="s-1")
        serialized = _serialize_session(session)
        created_at = serialized["created_at"]
        assert isinstance(created_at, str)
        assert created_at.endswith("+00:00") or created_at.endswith(
            "Z"
        ), f"オフセットなしでシリアライズされている: {created_at}"

    def test_round_trip_keeps_utc(self) -> None:
        session = ReceptionSession(session_id="s-1")
        parsed = datetime.fromisoformat(_serialize_session(session)["created_at"])
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)
