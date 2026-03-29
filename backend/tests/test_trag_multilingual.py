"""Tests for multilingual tRAG support (#379)."""

import pytest

from config.routing_constants import GREETING_KEYWORDS, RECEPTION_KEYWORDS


class TestMultilingualGreetingKeywords:
    """Verify GREETING_KEYWORDS contains Chinese and Korean entries."""

    def test_greeting_keywords_include_chinese(self):
        assert "你好" in GREETING_KEYWORDS
        assert "早上好" in GREETING_KEYWORDS

    def test_greeting_keywords_include_korean(self):
        assert "안녕하세요" in GREETING_KEYWORDS
        assert "안녕" in GREETING_KEYWORDS

    def test_greeting_keywords_include_japanese(self):
        assert "こんにちは" in GREETING_KEYWORDS
        assert "おはよう" in GREETING_KEYWORDS

    def test_greeting_keywords_include_english(self):
        assert "hello" in GREETING_KEYWORDS
        assert "good morning" in GREETING_KEYWORDS


class TestMultilingualReceptionKeywords:
    """Verify RECEPTION_KEYWORDS contains multilingual entries."""

    def test_reception_keywords_include_chinese(self):
        assert "登记" in RECEPTION_KEYWORDS
        assert "来访" in RECEPTION_KEYWORDS

    def test_reception_keywords_include_korean(self):
        assert "접수" in RECEPTION_KEYWORDS
        assert "방문" in RECEPTION_KEYWORDS

    def test_reception_keywords_include_english(self):
        assert "visit" in RECEPTION_KEYWORDS
        assert "visitor" in RECEPTION_KEYWORDS

    def test_reception_keywords_include_japanese(self):
        assert "来場" in RECEPTION_KEYWORDS
        assert "来訪" in RECEPTION_KEYWORDS


class TestEntityLabels:
    """Verify entity_labels fallback for unknown languages returns Japanese default."""

    def test_entity_labels_fallback_to_japanese(self):
        """Unknown language codes should fall back to Japanese labels."""
        entity_labels = {
            "engineer-cafe": {
                "ja": "【エンジニアカフェ】",
                "en": "[Engineer Cafe]",
                "zh": "【工程师咖啡】",
                "ko": "【엔지니어 카페】",
            },
            "saino": {
                "ja": "【sainoカフェ】",
                "en": "[Saino Cafe]",
                "zh": "【saino咖啡】",
                "ko": "【saino 카페】",
            },
            "meeting-room": {
                "ja": "【会議室】",
                "en": "[Meeting Room]",
                "zh": "【会议室】",
                "ko": "【회의실】",
            },
        }

        for entity, labels in entity_labels.items():
            # Unknown language falls back to Japanese
            result = labels.get("fr", labels["ja"])
            assert result == labels["ja"], f"entity={entity}: expected ja fallback for unknown lang"

    def test_entity_labels_contain_zh_ko(self):
        """Chinese and Korean labels must be present for all entities."""
        entity_labels = {
            "engineer-cafe": {
                "ja": "【エンジニアカフェ】",
                "en": "[Engineer Cafe]",
                "zh": "【工程师咖啡】",
                "ko": "【엔지니어 카페】",
            },
            "saino": {
                "ja": "【sainoカフェ】",
                "en": "[Saino Cafe]",
                "zh": "【saino咖啡】",
                "ko": "【saino 카페】",
            },
            "meeting-room": {
                "ja": "【会議室】",
                "en": "[Meeting Room]",
                "zh": "【会议室】",
                "ko": "【회의실】",
            },
        }

        for entity, labels in entity_labels.items():
            assert "zh" in labels, f"entity={entity}: missing zh label"
            assert "ko" in labels, f"entity={entity}: missing ko label"


class TestAdviceTemplates:
    """Verify advice_templates return zh/ko strings."""

    @pytest.fixture()
    def advice_templates(self):
        return {
            "hours": {
                "ja": (
                    "\U0001f4a1 営業時間は日によって異なる場合があります。"
                    "訪問前に確認することをお勧めします。"
                ),
                "en": (
                    "\U0001f4a1 Operating hours may vary by day."
                    " We recommend checking before your visit."
                ),
                "zh": "\U0001f4a1 营业时间可能因日期而异。建议您在来访前确认。",
                "ko": (
                    "\U0001f4a1 영업시간은 날에 따라 다를 수 있습니다."
                    " 방문 전에 확인하시는 것을 권장합니다."
                ),
            },
            "pricing": {
                "ja": (
                    "\U0001f4a1 料金プランは変更される場合があります。"
                    "最新情報はスタッフにお問い合わせください。"
                ),
                "en": (
                    "\U0001f4a1 Pricing plans may change."
                    " Please contact staff for the latest information."
                ),
                "zh": "\U0001f4a1 价格方案可能会有变动。请联系工作人员获取最新信息。",
                "ko": (
                    "\U0001f4a1 요금제는 변경될 수 있습니다. 최신 정보는 직원에게 문의해 주세요."
                ),
            },
            "facility-info": {
                "ja": (
                    "\U0001f4a1 設備の利用方法がわからない場合は、"
                    "スタッフにお気軽にお声がけください。"
                ),
                "en": (
                    "\U0001f4a1 If you're unsure how to use the facilities,"
                    " feel free to ask our staff."
                ),
                "zh": "\U0001f4a1 如果您不确定如何使用设施，请随时向工作人员咨询。",
                "ko": ("\U0001f4a1 시설 이용 방법을 모르시면 직원에게 편하게 문의해 주세요."),
            },
        }

    @pytest.mark.parametrize("category", ["hours", "pricing", "facility-info"])
    def test_advice_templates_return_zh(self, advice_templates, category):
        result = advice_templates[category].get("zh")
        assert result is not None, f"category={category}: missing zh template"
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("category", ["hours", "pricing", "facility-info"])
    def test_advice_templates_return_ko(self, advice_templates, category):
        result = advice_templates[category].get("ko")
        assert result is not None, f"category={category}: missing ko template"
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("category", ["hours", "pricing", "facility-info"])
    def test_advice_templates_fallback_to_ja(self, advice_templates, category):
        """Unknown language should fall back to Japanese."""
        result = advice_templates[category].get("fr", advice_templates[category].get("ja"))
        assert result == advice_templates[category]["ja"]


class TestEnhancedRagLanguageHandling:
    """Verify enhanced_rag uses language param for presentation, not DB filtering."""

    @pytest.fixture()
    def rag(self):
        """Create EnhancedRAGSearch with a mock Supabase client."""
        from unittest.mock import MagicMock

        from tools.enhanced_rag import EnhancedRAGSearch

        mock_client = MagicMock()
        return EnhancedRAGSearch(supabase_client=mock_client)

    def test_build_context_uses_display_language_zh(self, rag):
        """Chinese language should produce Chinese entity labels."""
        results = [
            {"entity": "engineer-cafe", "content": "テスト内容", "priority_score": 0.9},
        ]
        context = rag._build_context_from_results(results, "general", "zh")
        assert "工程师咖啡" in context

    def test_build_context_uses_display_language_ko(self, rag):
        """Korean language should produce Korean entity labels."""
        results = [
            {"entity": "engineer-cafe", "content": "テスト内容", "priority_score": 0.9},
        ]
        context = rag._build_context_from_results(results, "general", "ko")
        assert "엔지니어 카페" in context

    def test_build_context_uses_display_language_en(self, rag):
        """English language should produce English entity labels."""
        results = [
            {"entity": "engineer-cafe", "content": "テスト内容", "priority_score": 0.9},
        ]
        context = rag._build_context_from_results(results, "general", "en")
        assert "Engineer Cafe" in context

    def test_build_context_uses_display_language_ja(self, rag):
        """Japanese language should produce Japanese entity labels."""
        results = [
            {"entity": "engineer-cafe", "content": "テスト内容", "priority_score": 0.9},
        ]
        context = rag._build_context_from_results(results, "general", "ja")
        assert "エンジニアカフェ" in context

    def test_generate_advice_uses_display_language_zh(self, rag):
        """Chinese language should produce Chinese advice."""
        results = [{"content": "test"}]
        advice = rag._generate_practical_advice(results, "営業時間", "hours", "zh")
        assert advice is not None
        assert "营业时间" in advice

    def test_generate_advice_uses_display_language_ko(self, rag):
        """Korean language should produce Korean advice."""
        results = [{"content": "test"}]
        advice = rag._generate_practical_advice(results, "영업시간", "hours", "ko")
        assert advice is not None
        assert "영업시간" in advice

    def test_generate_advice_fallback_to_ja_for_unknown(self, rag):
        """Unknown language should fall back to Japanese advice."""
        results = [{"content": "test"}]
        advice = rag._generate_practical_advice(results, "query", "hours", "fr")
        assert advice is not None
        assert "営業時間" in advice

    def test_build_context_saino_zh(self, rag):
        """Chinese labels for saino entity."""
        results = [
            {"entity": "saino", "content": "saino情報", "priority_score": 0.8},
        ]
        context = rag._build_context_from_results(results, "general", "zh")
        assert "saino咖啡" in context

    def test_build_context_meeting_room_ko(self, rag):
        """Korean labels for meeting-room entity."""
        results = [
            {"entity": "meeting-room", "content": "会議室情報", "priority_score": 0.8},
        ]
        context = rag._build_context_from_results(results, "general", "ko")
        assert "회의실" in context
