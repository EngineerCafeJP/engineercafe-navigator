"""施設情報E2Eテスト - 各フロア・設備の情報検証"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestFacilityE2E:
    """施設情報のE2Eテスト"""

    async def test_main_hall(self, invoke_workflow):
        """メインホール"""
        result = await invoke_workflow("メインホールはどこにありますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["1階", "メインホール", "コワーキング"],
            threshold=0.3,
            msg="メインホール",
        )

    async def test_makers_space(self, invoke_workflow):
        """MAKER'sスペース"""
        result = await invoke_workflow("MAKER'sスペースについて教えてください")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["地下", "B1", "3D", "プリンター", "レーザー"],
            threshold=0.2,
            msg="MAKER'sスペース",
        )

    async def test_concentration_space(self, invoke_workflow):
        """集中スペース"""
        result = await invoke_workflow("集中して作業できるスペースはありますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["集中", "静か", "2階"],
            threshold=0.3,
            msg="集中スペース",
        )

    async def test_meeting_rooms(self, invoke_workflow):
        """会議室"""
        result = await invoke_workflow("会議室はありますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["会議室", "予約", "2階"],
            threshold=0.3,
            msg="会議室",
        )

    async def test_soundproof_room(self, invoke_workflow):
        """防音室"""
        result = await invoke_workflow("防音室はありますか？")
        assert result["answer"]
        assert len(result["answer"]) > 10, "回答が短すぎます"

    async def test_3d_printer(self, invoke_workflow):
        """3Dプリンター"""
        result = await invoke_workflow("3Dプリンターを使いたいのですが")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["予約", "講習", "3D", "プリンター"],
            threshold=0.25,
            msg="3Dプリンター",
        )

    async def test_laser_cutter(self, invoke_workflow):
        """レーザー加工機"""
        result = await invoke_workflow("レーザー加工機は使えますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["レーザー", "加工", "予約"],
            threshold=0.3,
            msg="レーザー加工機",
        )

    async def test_toilet_location(self, invoke_workflow):
        """トイレの場所"""
        result = await invoke_workflow("トイレはどこですか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["テラス", "受付", "トイレ"],
            threshold=0.3,
            msg="トイレ",
        )

    async def test_building_history(self, invoke_workflow):
        """建物の歴史"""
        result = await invoke_workflow("この建物はいつ建てられましたか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["1909", "明治", "赤煉瓦", "日本生命"],
            threshold=0.25,
            msg="建物歴史",
        )

    async def test_floor_guide(self, invoke_workflow):
        """フロアガイド"""
        result = await invoke_workflow("各階に何がありますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["1階", "2階", "地下"],
            threshold=0.3,
            msg="フロアガイド",
        )
