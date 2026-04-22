"""
BusinessInfoAgent のユニットテスト
"""

from backend.agents.business_info_agent import BusinessInfoAgent


class TestBusinessInfoAgent:
    """BusinessInfoAgent のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.agent = BusinessInfoAgent()

    def test_map_request_type_to_category(self):
        """requestTypeからcategoryへのマッピングをテスト"""
        assert self.agent._map_request_type_to_category("hours") == "hours"
        assert self.agent._map_request_type_to_category("price") == "pricing"
        assert self.agent._map_request_type_to_category("location") == "location"
        assert self.agent._map_request_type_to_category("access") == "location"
        assert self.agent._map_request_type_to_category("unknown") == "general"

    def test_get_request_type_prompt_japanese(self):
        """日本語のrequestTypeプロンプトをテスト"""
        assert self.agent._get_request_type_prompt("hours", "ja") == "営業時間"
        assert self.agent._get_request_type_prompt("price", "ja") == "料金情報"
        assert self.agent._get_request_type_prompt("location", "ja") == "場所情報"

    def test_get_request_type_prompt_english(self):
        """英語のrequestTypeプロンプトをテスト"""
        assert self.agent._get_request_type_prompt("hours", "en") == "operating hours"
        assert self.agent._get_request_type_prompt("price", "en") == "pricing information"
        assert self.agent._get_request_type_prompt("location", "en") == "location information"

    def test_determine_emotion(self):
        """感情タグ決定をテスト"""
        # レスポンステキストから感情タグを抽出
        assert self.agent._determine_emotion("hours", "[relaxed]営業時間は...") == "relaxed"
        assert self.agent._determine_emotion("price", "[happy]料金は...") == "happy"
        assert self.agent._determine_emotion("location", "[sad]場所は...") == "sad"

        # request_typeに基づくデフォルト感情
        assert self.agent._determine_emotion("hours", "営業時間は...") == "informative"
        assert self.agent._determine_emotion("price", "料金は...") == "informative"
        assert self.agent._determine_emotion("location", "場所は...") == "guiding"

    def test_get_default_response_japanese(self):
        """日本語のデフォルト応答をテスト"""
        response = self.agent._get_default_response("ja", "hours")

        assert response["answer"].startswith("[sad]")
        assert "申し訳ございません" in response["answer"]
        assert response["emotion"] == "apologetic"
        assert response["metadata"]["agent"] == "BusinessInfoAgent"
        assert response["metadata"]["confidence"] == 0.3

    def test_get_default_response_english(self):
        """英語のデフォルト応答をテスト"""
        response = self.agent._get_default_response("en", "price")

        assert response["answer"].startswith("[sad]")
        assert any(
            keyword in response["answer"].lower()
            for keyword in ("sorry", "couldn't", "apologize", "unable")
        ), f"Expected apology keyword in: {response['answer']}"
        assert response["emotion"] == "apologetic"
        assert response["metadata"]["agent"] == "BusinessInfoAgent"
