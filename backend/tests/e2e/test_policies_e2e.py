"""ポリシーE2Eテスト - 利用規約・ルールの検証"""

import pytest

from backend.tests.e2e.conftest import assert_keywords


@pytest.mark.e2e
class TestPoliciesE2E:
    async def test_food_drink_policy(self, invoke_workflow):
        result = await invoke_workflow("飲食の持ち込みは可能ですか？")
        assert result["answer"]
        assert len(result["answer"]) > 20

    async def test_smoking_policy(self, invoke_workflow):
        result = await invoke_workflow("館内で喫煙はできますか？")
        assert result["answer"]
        assert_keywords(result["answer"], ["禁煙", "喫煙", "不可"], threshold=0.3)

    async def test_parking(self, invoke_workflow):
        result = await invoke_workflow("駐車場はありますか？")
        assert result["answer"]
        assert_keywords(result["answer"], ["駐車場", "駐車"], threshold=0.5)

    async def test_bicycle_parking(self, invoke_workflow):
        result = await invoke_workflow("自転車で行きたいのですが、駐輪場はありますか？")
        assert result["answer"]
        assert_keywords(result["answer"], ["駐輪", "自転車"], threshold=0.5)

    async def test_photography_policy(self, invoke_workflow):
        result = await invoke_workflow("館内で写真撮影はできますか？")
        assert result["answer"]
        assert_keywords(result["answer"], ["撮影", "写真", "可能"], threshold=0.3)

    async def test_children_policy(self, invoke_workflow):
        result = await invoke_workflow("子連れで利用できますか？")
        assert result["answer"]
        assert len(result["answer"]) > 20
