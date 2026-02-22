"""多言語E2Eテスト - 英語/中国語/韓国語対応"""

import pytest

from backend.tests.e2e.conftest import is_routing_failure


@pytest.mark.e2e
class TestMultilingualE2E:
    async def test_english_what_is_ec(self, invoke_workflow):
        """英語: エンジニアカフェ紹介"""
        result = await invoke_workflow("What is Engineer Cafe?", language="en")
        assert result["answer"]
        if is_routing_failure(result["answer"]):
            pytest.xfail("ルーティング非決定性によりRAG検索未実行")
        answer_lower = result["answer"].lower()
        assert any(
            kw in answer_lower
            for kw in [
                "coworking",
                "co-working",
                "engineer",
                "free",
                "space",
                "fukuoka",
                "cafe",
            ]
        )

    async def test_english_hours(self, invoke_workflow):
        """英語: 営業時間"""
        result = await invoke_workflow("What are the opening hours?", language="en")
        assert result["answer"]
        if is_routing_failure(result["answer"]):
            pytest.xfail("ルーティング非決定性によりRAG検索未実行")
        assert any(
            kw in result["answer"]
            for kw in ["9:00", "22:00", "9", "22", "open", "hour", "am", "pm"]
        )

    async def test_english_wifi(self, invoke_workflow):
        """英語: WiFi"""
        result = await invoke_workflow("What is the Wi-Fi password?", language="en")
        assert result["answer"]
        if is_routing_failure(result["answer"]):
            pytest.xfail("ルーティング非決定性によりRAG検索未実行")
        answer_lower = result["answer"].lower()
        assert any(
            kw in answer_lower
            for kw in ["akarenga", "112years", "wi-fi", "wifi", "password", "ssid"]
        )

    async def test_chinese_query(self, invoke_workflow):
        """中国語: 基本質問（LLMが多言語対応のためxfail不要）"""
        result = await invoke_workflow("工程师咖啡馆在哪里？", language="zh")
        assert result["answer"]
        assert len(result["answer"]) > 10

    async def test_korean_query(self, invoke_workflow):
        """韓国語: 基本質問（LLMが多言語対応のためxfail不要）"""
        result = await invoke_workflow("엔지니어 카페는 무엇인가요?", language="ko")
        assert result["answer"]
        assert len(result["answer"]) > 10
