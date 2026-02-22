"""アクセスE2Eテスト"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestAccessE2E:
    async def test_from_tenjin_station(self, invoke_workflow):
        result = await invoke_workflow("天神駅からエンジニアカフェへの行き方を教えてください")
        assert result["answer"]
        assert_keywords(result["answer"], ["天神", "徒歩", "分"], threshold=0.3)

    async def test_nearest_station(self, invoke_workflow):
        result = await invoke_workflow("最寄り駅はどこですか？")
        assert result["answer"]
        assert_keywords(result["answer"], ["天神", "中洲川端", "駅"], threshold=0.3)

    async def test_address(self, invoke_workflow):
        result = await invoke_workflow("エンジニアカフェの住所を教えてください")
        assert result["answer"]
        assert_keywords(result["answer"], ["福岡", "中央区", "天神"], threshold=0.3)
