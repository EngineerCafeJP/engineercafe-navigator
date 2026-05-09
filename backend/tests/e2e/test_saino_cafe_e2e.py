"""サイノカフェE2Eテスト - 併設カフェ＆バーの情報検証"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestSainoCafeE2E:
    """サイノカフェのE2Eテスト"""

    async def test_saino_cafe_menu(self, invoke_workflow):
        """メニュー情報"""
        result = await invoke_workflow("サイノカフェのメニューを教えてください")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["メニュー", "コーヒー", "ドリンク", "ランチ"],
            threshold=0.25,
            msg="サイノカフェメニュー",
        )

    async def test_saino_cafe_hours(self, invoke_workflow):
        """営業時間"""
        result = await invoke_workflow("サイノカフェの営業時間は？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["12:00", "20:00", "12時", "20時"],
            threshold=0.25,
            msg="サイノカフェ営業時間",
        )

    async def test_saino_cafe_hours_followup_after_engineer_cafe_hours(
        self, invoke_workflow, e2e_session_id
    ):
        """エンジニアカフェ営業時間後の隣のカフェ参照"""
        sid = f"{e2e_session_id}-saino-followup"

        first = await invoke_workflow("エンジニアカフェの営業時間を教えて", session_id=sid)
        assert first["answer"]

        result = await invoke_workflow("隣のカフェは？", session_id=sid)
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["12:00", "20:00", "Day Time", "Night Time"],
            threshold=0.25,
            msg="サイノカフェフォローアップ営業時間",
        )
        assert result["metadata"].get("cafe_entity_resolution", {}).get("entity") == "saino_cafe"

    async def test_saino_cafe_closed_day(self, invoke_workflow):
        """定休日"""
        result = await invoke_workflow("サイノカフェの定休日はいつですか？")
        assert result["answer"]
        assert len(result["answer"]) > 10, "回答が短すぎます"

    async def test_saino_cafe_alcohol(self, invoke_workflow):
        """アルコール"""
        result = await invoke_workflow("サイノカフェでお酒は飲めますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["バー", "アルコール", "お酒", "ビール", "ワイン"],
            threshold=0.2,
            msg="サイノカフェアルコール",
        )

    async def test_saino_cafe_coffee_price(self, invoke_workflow):
        """コーヒー価格"""
        result = await invoke_workflow("コーヒーはいくらですか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["円", "コーヒー"],
            threshold=0.5,
            msg="コーヒー価格",
        )
