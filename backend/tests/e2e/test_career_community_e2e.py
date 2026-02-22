"""キャリア/コミュニティE2Eテスト"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestCareerCommunityE2E:
    async def test_career_consultation(self, invoke_workflow):
        result = await invoke_workflow("エンジニアへの転職について相談できますか？")
        assert result["answer"]
        assert_keywords(
            result["answer"],
            ["相談", "コミュニティマネージャー", "転職", "キャリア"],
            threshold=0.25,
        )

    async def test_skill_change(self, invoke_workflow):
        result = await invoke_workflow("プログラミング未経験ですが、スキルチェンジしたいです")
        assert result["answer"]
        assert len(result["answer"]) > 30

    async def test_ec_lab(self, invoke_workflow):
        result = await invoke_workflow("EC Labとは何ですか？")
        assert result["answer"]
        assert_keywords(result["answer"], ["Lab", "スタートアップ", "起業"], threshold=0.3)

    async def test_eic_program(self, invoke_workflow):
        result = await invoke_workflow("EICプログラムについて教えてください")
        assert result["answer"]
        assert len(result["answer"]) > 20
