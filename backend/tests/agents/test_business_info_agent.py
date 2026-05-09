"""
BusinessInfoAgent のユニットテスト
"""

import pytest
from unittest.mock import AsyncMock

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
        assert self.agent._map_request_type_to_category("contact") == "contact"
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
        assert "reception" in response["answer"]
        assert "5 to 10 minutes" in response["answer"]
        assert "web form" in response["answer"].lower()
        assert "staff" in response["answer"].lower()
        assert "online pre-registration is not available" in response["answer"].lower()

    def test_first_time_visitor_canonical_response(self):
        """Hyphenated first-time visitor phrasing must not fall back."""
        response = self.agent._get_canonical_response(
            "I'm a first-time visitor. What should I do?", "reception", "en"
        )

        assert response is not None
        assert response["metadata"]["confidence"] >= 0.7
        assert response["metadata"]["sources"] == ["enhanced_rag"]
        assert "reception" in response["answer"]
        assert "staff" in response["answer"].lower()
        assert "5 to 10 minutes" in response["answer"]

    @pytest.mark.parametrize(
        "query",
        [
            "How do I become a member?",
            "Tell me about membership",
            "What is the membership like?",
        ],
    )
    def test_abstract_english_membership_canonical_response(self, query):
        """#567: abstract English membership queries must not fall back."""
        response = self.agent._get_canonical_response(query, "reception", "en")

        assert response is not None
        assert response["metadata"]["sources"] == ["enhanced_rag"]
        answer = response["answer"].lower()
        assert "membership registration is free" in answer
        assert "member number" in answer
        assert "online pre-registration is not available" in answer

    def test_returning_visitor_canonical_response_japanese(self):
        """gt-082/gt-085: 再来館発話は退館・会話履歴ではなく歓迎にする"""
        response = self.agent._get_canonical_response("前にも来たことがあります", "reception", "ja")

        assert response is not None
        assert "おかえりなさい" in response["answer"]
        assert "チェックイン" in response["answer"]
        assert "受付カード" in response["answer"]
        assert "ありがとうございました" not in response["answer"]

    def test_engineer_cafe_lab_canonical_response(self):
        """gt-021: Engineer Cafe LabをEIC情報に混ぜない"""
        response = self.agent._get_canonical_response(
            "Engineer Cafe Labとは何ですか？", "community", "ja"
        )

        assert response is not None
        assert "25歳以下" in response["answer"]
        assert "事前応募" in response["answer"]
        assert "面接" in response["answer"]
        assert "EIC" not in response["answer"]

    def test_alpha_c127_engineer_friendly_city_canonical(self):
        """gt-059: EFCは中核施設と支援施策を含める"""
        response = self.agent._get_canonical_response(
            "エンジニアフレンドリーシティ福岡とは？", "community", "ja"
        )

        assert response is not None
        assert "福岡市" in response["answer"]
        assert "中核施設" in response["answer"]
        assert "EFCアワード" in response["answer"]
        assert "外国人エンジニア支援" in response["answer"]

    def test_alpha_c127_official_social_canonical(self):
        """gt-053: 公式SNSはX/Connpass/公式サイト/LINEなしを含める"""
        response = self.agent._get_canonical_response(
            "エンジニアカフェの公式SNSアカウントは？", "contact", "ja"
        )

        assert response is not None
        assert "@EngineerCafeJP" in response["answer"]
        assert "https://engineercafe.connpass.com/" in response["answer"]
        assert "https://engineercafe.jp/" in response["answer"]
        assert "LINEアカウントはありません" in response["answer"]

    def test_alpha_c127_english_support_canonical(self):
        """gt-056: 英語対応は英語版URLと限定対応を含める"""
        response = self.agent._get_canonical_response("英語対応はしていますか？", "contact", "ja")

        assert response is not None
        assert "https://engineercafe.jp/en/" in response["answer"]
        assert "英語対応は限定的" in response["answer"]
        assert "国際イベント" in response["answer"]
        assert "外国人利用者" in response["answer"]

    def test_opening_hours_canonical_response_japanese(self):
        """営業時間は開館時間と相談受付時間を分けて案内する"""
        response = self.agent._get_canonical_response(
            "エンジニアカフェの営業時間は何時から何時までですか？",
            "hours",
            "ja",
        )

        assert response is not None
        assert "朝9時から夜22時" in response["answer"]
        assert "9:00〜22:00" in response["answer"]
        assert "13:00〜21:00" in response["answer"]

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

    def test_pricing_canonical_response_japanese(self):
        """一般的な料金質問では基本無料と主要な有料例を簡潔に案内する"""
        response = self.agent._get_canonical_response(
            "料金はいくらですか？",
            "pricing",
            "ja",
        )

        assert response is not None
        assert "施設・設備の利用料は無料" in response["answer"]
        assert "cafe&bar saino" in response["answer"]
        assert "3Dプリンターのフィラメント代" in response["answer"]
        assert "2階" not in response["answer"]

    def test_reservation_canonical_response_english_includes_expected_fact(self):
        """Q-BIZ-EN-003: reservation questions must be deterministic."""
        response = self.agent._get_canonical_response(
            "Can I use Engineer Cafe without a reservation?",
            "reception",
            "en",
        )

        assert response is not None
        assert "reservation" in response["answer"].lower()
        assert "without a reservation" in response["answer"].lower()
        assert "1F reception" in response["answer"]
        assert response["metadata"]["sources"] == ["enhanced_rag"]

    def test_reservation_canonical_does_not_capture_event_room_booking(self):
        """Event-room reservation questions must stay out of generic coworking answers."""
        response = self.agent._get_canonical_response(
            "Do I need a reservation for an event room?",
            "reception",
            "en",
        )

        assert response is None

    def test_reservation_canonical_does_not_capture_meeting_room_booking(self):
        """Meeting-room reservation questions are facility-specific, not coworking use."""
        response = self.agent._get_canonical_response(
            "Do I need a reservation for a meeting room?",
            "reception",
            "en",
        )

        assert response is None

    def test_first_visit_registration_precedes_reservation_canonical(self):
        """First-visit registration questions should not become reservation-only answers."""
        response = self.agent._get_canonical_response(
            "For my first visit, do I need a reservation or should I register at reception?",
            "reception",
            "en",
        )

        assert response is not None
        assert "5 to 10 minutes" in response["answer"]
        assert "web form" in response["answer"].lower()
        assert "regular coworking space" not in response["answer"].lower()

    @pytest.mark.asyncio
    async def test_answer_business_query_reservation_canonical_skips_rag_and_llm(self):
        """Q-BIZ-EN-003: live path should not depend on RAG/LLM wording."""
        self.agent.enhanced_rag.search = AsyncMock(
            side_effect=AssertionError("reservation canonical must skip RAG")
        )
        self.agent.llm_provider.generate = AsyncMock(
            side_effect=AssertionError("reservation canonical must skip LLM")
        )

        response = await self.agent.answer_business_query(
            "Can I use Engineer Cafe without a reservation?",
            "reception",
            "en",
            "q-biz-en-003",
        )

        assert "reservation" in response["answer"].lower()
        self.agent.enhanced_rag.search.assert_not_called()
        self.agent.llm_provider.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_answer_business_query_canonical_ignores_stale_state_context(self):
        """Known alpha-gate canonical answers must not be suppressed by stale RAG cache."""
        self.agent.enhanced_rag.search = AsyncMock(
            side_effect=AssertionError("reservation canonical must skip stale cache fallback")
        )
        self.agent.llm_provider.generate = AsyncMock(
            side_effect=AssertionError("reservation canonical must skip LLM")
        )

        response = await self.agent.answer_business_query(
            "Can I use Engineer Cafe without a reservation?",
            "reception",
            "en",
            "q-biz-en-003",
            state_context={
                "success": True,
                "category": "general",
                "context_string": "stale general cache",
                "results": [],
                "query": "stale",
            },
        )

        assert "without a reservation" in response["answer"].lower()
        self.agent.enhanced_rag.search.assert_not_called()
        self.agent.llm_provider.generate.assert_not_called()

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

    def test_contact_canonical_response_english_includes_channels(self):
        """EN contact answer should not depend on RAG/LLM URL generation."""
        response = self.agent._get_canonical_response(
            "How can I contact Engineer Cafe?", None, "en"
        )

        assert response is not None
        assert "080-6742-7231" in response["answer"]
        assert "13:00-21:00" in response["answer"]
        assert "https://engineercafe.jp/" in response["answer"]
        assert "contact form" in response["answer"].lower()
        assert "official website" in response["answer"].lower()
        assert "second-floor meeting rooms" in response["answer"].lower()

    def test_contact_canonical_response_zh_ko_includes_sources_and_form(self):
        """gt-106/116: ZH/KO contact must avoid fallback and include contact form URL."""
        zh = self.agent._get_canonical_response("如何联系工程师咖啡？", "contact", "zh")
        ko = self.agent._get_canonical_response(
            "엔지니어 카페에 어떻게 연락할 수 있나요?", "contact", "ko"
        )

        assert zh is not None
        assert "080-6742-7231" in zh["answer"]
        assert "https://engineercafe.jp/" in zh["answer"]
        assert "https://engineercafe.jp/ja/contact" in zh["answer"]
        assert zh["metadata"]["sources"] == ["enhanced_rag"]

        assert ko is not None
        assert "080-6742-7231" in ko["answer"]
        assert "https://engineercafe.jp/" in ko["answer"]
        assert "https://engineercafe.jp/ja/contact" in ko["answer"]
        assert ko["metadata"]["sources"] == ["enhanced_rag"]

    def test_closed_days_canonical_precedes_hours(self):
        """休館日は営業時間の広い回答に倒さない"""
        response = self.agent._get_canonical_response(
            "エンジニアカフェの休館日はいつですか？",
            "hours",
            "ja",
        )

        assert response is not None
        assert "毎月最終月曜日" in response["answer"]
        assert "12月29日から1月3日" in response["answer"]
        assert "朝9時から夜22時" not in response["answer"]

    def test_community_program_canonical_static_devday(self):
        """DevDayはlive eventではなくEICの静的情報として回答する"""
        response = self.agent._get_canonical_response(
            "DevDayはいつ開催されますか？",
            "community",
            "ja",
        )

        assert response is not None
        assert "2026年2月23日18:00" in response["answer"]
        assert "展示形式" in response["answer"]
        assert "Fusic" in response["answer"]
        assert "ヌーラボ" in response["answer"]

    def test_alpha_c127_consultation_canonical(self):
        """gt-019/020: CM相談とスキルチェンジ相談を固定する"""
        response = self.agent._get_canonical_response(
            "コミュニティマネージャーに相談できることは？",
            "consultation",
            "ja",
        )

        assert response is not None
        assert "キャリア相談" in response["answer"]
        assert "技術相談" in response["answer"]
        assert "イベント企画サポート" in response["answer"]
        assert "13:00〜21:00" in response["answer"]
        assert "予約不要" in response["answer"]

        skill_change = self.agent._get_canonical_response(
            "エンジニアカフェでスキルチェンジ相談はできますか？",
            "consultation",
            "ja",
        )
        assert skill_change is not None
        assert "スキルチェンジ支援" in skill_change["answer"]
        assert "相談会" in skill_change["answer"]

    def test_alpha_c127_reception_welcome_canonical(self):
        """gt-081/082/085: 初回・再訪ウェルカムを固定する"""
        first_visit = self.agent._get_canonical_response("初めて来ました", "reception", "ja")
        assert first_visit is not None
        assert "エンジニアカフェへようこそ" in first_visit["answer"]
        assert "初めてのご利用" in first_visit["answer"]
        assert "1階受付" in first_visit["answer"]
        assert "利用登録手続き" in first_visit["answer"]

        returning = self.agent._get_canonical_response(
            "前にも来たことがあります", "reception", "ja"
        )
        assert returning is not None
        assert "おかえりなさい" in returning["answer"]
        assert "エンジニアカフェへようこそ" in returning["answer"]
        assert "チェックイン" in returning["answer"]
        assert "受付カード" in returning["answer"]

    def test_alpha_c127_corporate_receipt_canonical(self):
        """gt-055: 法人名義・領収書回答を固定する"""
        response = self.agent._get_canonical_response(
            "法人名義での利用や領収書は発行できますか？",
            "price",
            "ja",
        )

        assert response is not None
        assert "領収書" in response["answer"]
        assert "請求書" in response["answer"]
        assert "赤煉瓦文化館管理" in response["answer"]

    def test_eic_completion_conditions_canonical(self):
        """gt-023: EICの修了認定条件を汎用EIC説明に倒さない"""
        response = self.agent._get_canonical_response(
            "EICの修了認定条件を教えてください",
            "community",
            "ja",
        )

        assert response is not None
        assert "講義3回" in response["answer"]
        assert "LT発表" in response["answer"]
        assert "Dev & Tips 5回中3回" in response["answer"]
        assert "Boot Camp 2日間" in response["answer"]
        assert "DevDay" in response["answer"]
        assert "短期集中" not in response["answer"]

    def test_saino_hours_precedes_engineer_cafe_hours(self):
        """gt-015: sainoの営業時間をエンジニアカフェ開館時間に倒さない"""
        response = self.agent._get_canonical_response(
            "cafe&bar sainoの営業時間は？",
            "hours",
            "ja",
        )

        assert response is not None
        assert "Day Time 12:00〜17:00" in response["answer"]
        assert "Night Time 18:00〜20:00" in response["answer"]
        assert "月曜と水曜" in response["answer"]
        assert "朝9時から夜22時" not in response["answer"]
        assert response["metadata"]["category"] == "saino-cafe"
        assert response["metadata"]["cafe_entity_resolution"]["entity"] == "saino_cafe"

    def test_heisetsu_cafe_hours_resolves_to_saino(self):
        """併設のカフェ営業時間はsainoとして固定回答する"""
        response = self.agent._get_canonical_response(
            "併設のカフェの営業時間は？",
            "hours",
            "ja",
        )

        assert response is not None
        assert "Day Time 12:00〜17:00" in response["answer"]
        assert "朝9時から夜22時" not in response["answer"]
        assert response["metadata"]["cafe_entity_resolution"]["entity"] == "saino_cafe"

    def test_ambiguous_cafe_hours_returns_both_options(self):
        """Bare カフェ営業時間はEngineer Cafeだけに倒さない"""
        response = self.agent._get_canonical_response(
            "カフェの営業時間は？",
            "hours",
            "ja",
        )

        assert response is not None
        assert "エンジニアカフェなら9:00〜22:00" in response["answer"]
        assert "cafe&bar saino" in response["answer"]
        assert response["metadata"]["category"] == "cafe-clarification-needed"
        assert response["metadata"]["cafe_entity_resolution"]["entity"] == "ambiguous"

    def test_saino_coffee_price_precedes_engineer_cafe_pricing(self):
        """gt-017: 価格fast-path後もsainoのコーヒー価格を返す"""
        response = self.agent._get_canonical_response(
            "サイノカフェのコーヒーの値段は？",
            "price",
            "ja",
        )

        assert response is not None
        assert "ブレンドコーヒー380円" in response["answer"]
        assert "カフェラテ570円" in response["answer"]
        assert "施設・設備の利用料は無料" not in response["answer"]

    @pytest.mark.asyncio
    async def test_chinese_canonical_ignores_stale_state_context(self):
        """ZH canonical は stale cache があっても fallback/RAG に進まない"""
        response = await self.agent.answer_business_query(
            query="工程师咖啡是什么？",
            request_type="general",
            language="zh",
            state_context={"success": True, "category": "general", "context_string": ""},
        )

        assert "免费共享办公" in response["answer"]
        assert response["metadata"]["sources"] == ["enhanced_rag"]
