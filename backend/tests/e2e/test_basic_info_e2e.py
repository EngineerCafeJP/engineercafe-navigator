"""基本情報E2Eテスト - エンジニアカフェの基本的な施設情報の検証"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestBasicInfoE2E:
    """エンジニアカフェ基本情報のE2Eテスト"""

    async def test_what_is_engineer_cafe(self, invoke_workflow):
        """エンジニアカフェの基本紹介"""
        result = await invoke_workflow("エンジニアカフェって何ですか？")
        assert result["answer"], "回答が空です"
        assert_keywords(
            result["answer"],
            ["コワーキング", "無料"],
            threshold=0.5,
            msg="EC基本紹介",
        )

    async def test_opening_hours_weekday(self, invoke_workflow):
        """平日の営業時間"""
        result = await invoke_workflow("平日の営業時間は何時から何時までですか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["9:00", "22:00", "9時", "22時"],
            threshold=0.25,  # 表現バリエーションがあるため低め
            msg="平日営業時間",
        )

    async def test_opening_hours_weekend(self, invoke_workflow):
        """土日祝日の営業"""
        result = await invoke_workflow("土日祝日も開いていますか？")
        assert result["answer"]
        # 土日も開いているが時間が異なる可能性
        assert_keywords(
            result["answer"],
            ["土", "日", "開館", "営業"],
            threshold=0.25,
            msg="土日営業",
        )

    async def test_holidays(self, invoke_workflow):
        """休館日"""
        result = await invoke_workflow("休館日はいつですか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["最終月曜", "月曜", "年末年始", "12月29日"],
            threshold=0.25,
            msg="休館日",
        )

    async def test_is_it_free(self, invoke_workflow):
        """利用料金（無料）"""
        result = await invoke_workflow("エンジニアカフェは無料で使えますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["無料", "料金", "0円", "タダ", "フリー"],
            threshold=0.2,
            msg="無料利用",
        )

    async def test_registration_process(self, invoke_workflow):
        """初回登録プロセス"""
        result = await invoke_workflow("初めて利用するにはどうすればいいですか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["受付", "登録", "初回", "利用"],
            threshold=0.25,
            msg="初回登録",
        )

    async def test_wifi_password(self, invoke_workflow):
        """WiFiパスワード"""
        result = await invoke_workflow("WiFiのパスワードを教えてください")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["akarenga", "112years", "Wi-Fi", "WiFi"],
            threshold=0.25,
            msg="WiFiパスワード",
        )

    async def test_contact_info(self, invoke_workflow):
        """連絡先"""
        result = await invoke_workflow("エンジニアカフェの連絡先を教えてください")
        assert result["answer"]
        # Phone number or website or some contact info
        assert len(result["answer"]) > 20, "連絡先情報が不十分です"
