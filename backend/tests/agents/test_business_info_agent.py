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
        assert self.agent._map_request_type_to_category("reception") == "general"
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

    def test_first_visit_registration_canonical_response(self):
        """初回登録の実地案内を固定する"""
        response = self.agent._get_canonical_response(
            "How do I register for my first visit?", None, "en"
        )

        assert response is not None
        assert "1F reception" in response["answer"]
        assert "5 to 10 minutes" in response["answer"]
        assert "web form" in response["answer"].lower()
        assert "Online pre-registration is not available" in response["answer"]
        assert "free" in response["answer"].lower()

    def test_opening_hours_canonical_response_japanese(self):
        """営業時間は開館時間と相談受付時間を分けて案内する"""
        response = self.agent._get_canonical_response(
            "エンジニアカフェの営業時間は何時から何時までですか？",
            "hours",
            "ja",
        )

        assert response is not None
        assert "朝9:00から夜22:00" in response["answer"]
        assert "13:00から21:00" in response["answer"]
        assert "毎月最終月曜日" in response["answer"]

    def test_pricing_canonical_response_english(self):
        """料金は無料範囲と有料例を明示する"""
        response = self.agent._get_canonical_response(
            "How much does it cost to use Engineer Cafe?",
            "pricing",
            "en",
        )

        assert response is not None
        assert "free" in response["answer"].lower()
        assert "3D printer filament" in response["answer"]
        assert "second-floor meeting rooms" in response["answer"]

    def test_reception_request_type_alone_does_not_force_first_visit(self):
        """reception routingだけで初回登録回答へ倒さない"""
        response = self.agent._get_canonical_response(
            "I have registered before. Can I just check in again today?",
            "reception",
            "en",
        )

        assert response is None

    def test_korean_hours_query_matches_hours_not_what_is_engineer_cafe(self):
        """韓国語の営業時間質問を施設紹介に誤分類しない"""
        response = self.agent._get_canonical_response(
            "엔지니어 카페의 운영 시간은 어떻게 되나요?", "hours", "ko"
        )

        assert response is not None
        assert "9:00" in response["answer"]
        assert "22:00" in response["answer"]
        assert "직원" in response["answer"]
        assert "코워킹" not in response["answer"]

    def test_contact_canonical_response_japanese_phone(self):
        """電話番号の実地案内を固定する"""
        response = self.agent._get_canonical_response("電話番号を教えてください", None, "ja")

        assert response is not None
        assert "080-6742-7231" in response["answer"]
        assert "13時から21時" in response["answer"]
