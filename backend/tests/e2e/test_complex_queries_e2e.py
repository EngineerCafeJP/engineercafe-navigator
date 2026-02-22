"""複合クエリE2Eテスト - 曖昧・マルチインテント・コンテキスト依存"""

import pytest


@pytest.mark.e2e
class TestComplexQueriesE2E:
    async def test_ambiguous_query_cafe(self, invoke_workflow):
        """曖昧クエリ: カフェ"""
        result = await invoke_workflow("カフェはどこですか？")
        assert result["answer"]
        assert len(result["answer"]) > 20

    async def test_multi_intent(self, invoke_workflow):
        """マルチインテント: 営業時間+WiFi"""
        result = await invoke_workflow("営業時間とWiFiのパスワードを教えてください")
        assert result["answer"]
        # At least one of the intents should be addressed
        assert len(result["answer"]) > 30

    async def test_context_dependent(self, invoke_workflow):
        """コンテキスト依存クエリ（コンテキストなしでもGKAが応答可能）"""
        result = await invoke_workflow("もっと詳しく教えてください")
        assert result["answer"]
        # GKAが応答すればOK（コンテキストなしの場合は案内的な応答になる）
        assert len(result["answer"]) > 10

    async def test_vague_question(self, invoke_workflow):
        """非常に曖昧な質問"""
        result = await invoke_workflow("ここで何ができますか？")
        assert result["answer"]
        assert len(result["answer"]) > 30
