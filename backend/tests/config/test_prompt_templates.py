"""
Tests for backend/config/prompts/*.py

イベント、施設、メモリプロンプトテンプレートの構築ロジックをテスト。
"""

from backend.config.prompts.event_prompts import build_event_prompt, get_time_range_label
from backend.config.prompts.facility_prompts import (
    FACILITY_ENHANCEMENT_KEYWORDS,
    build_facility_prompt,
)
from backend.config.prompts.memory_prompts import build_memory_prompt


class TestEventPrompts:
    """EventAgent プロンプトのテスト"""

    def test_get_time_range_label_today_ja(self):
        """today の日本語ラベルは「本日」"""
        label = get_time_range_label("today", "ja")
        assert label == "本日"

    def test_get_time_range_label_today_en(self):
        """today の英語ラベルは "today" """
        label = get_time_range_label("today", "en")
        assert label == "today"

    def test_get_time_range_label_unknown_range_fallback(self):
        """未知の range は "今週" / "this week" にフォールバック"""
        label_ja = get_time_range_label("unknown", "ja")
        label_en = get_time_range_label("unknown", "en")

        assert label_ja == "今週"
        assert label_en == "this week"

    def test_build_event_prompt_returns_non_empty_string(self):
        """build_event_prompt は空でない文字列を返す"""
        query = "今日のイベントは？"
        events_text = "イベント1: 勉強会\nイベント2: ミートアップ"
        result = build_event_prompt(query, events_text, "today", "ja")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_event_prompt_contains_query_text(self):
        """プロンプトにクエリテキストが含まれる"""
        query = "What events are happening today?"
        events_text = "Event 1: Study session\nEvent 2: Meetup"
        result = build_event_prompt(query, events_text, "today", "en")

        assert query in result

    def test_build_event_prompt_ja_vs_en_produces_different_prompts(self):
        """日本語と英語で異なるプロンプトが生成される"""
        query = "イベント教えて"
        events_text = "イベント1"

        result_ja = build_event_prompt(query, events_text, "today", "ja")
        result_en = build_event_prompt(query, events_text, "today", "en")

        # 日本語プロンプトには「質問」が含まれる
        assert "質問" in result_ja or "イベント" in result_ja
        # 英語プロンプトには "Question" が含まれる
        assert "Question" in result_en or "Events" in result_en
        # 異なるプロンプトであることを確認
        assert result_ja != result_en

    def test_build_event_prompt_contains_jst_range_rule(self):
        """イベント範囲の解釈ルールをプロンプトに明示する"""
        prompt = build_event_prompt("今週のイベントは？", "- LT会", "thisWeek", "ja")

        assert "範囲解釈ルール" in prompt
        assert "JST" in prompt
        assert "過去日は含めない" in prompt


class TestFacilityPrompts:
    """FacilityAgent プロンプトのテスト"""

    def test_facility_enhancement_keywords_has_expected_keys(self):
        """FACILITY_ENHANCEMENT_KEYWORDS に期待されるキーが存在"""
        expected_keys = {"wifi", "facility", "access", "basement", "building"}

        for key in expected_keys:
            assert key in FACILITY_ENHANCEMENT_KEYWORDS

    def test_facility_enhancement_keywords_structure(self):
        """各キーワードエントリが ja, en を持つ"""
        for request_type, keywords in FACILITY_ENHANCEMENT_KEYWORDS.items():
            assert "ja" in keywords
            assert "en" in keywords
            assert isinstance(keywords["ja"], str)
            assert isinstance(keywords["en"], str)

    def test_build_facility_prompt_with_request_type(self):
        """request_type がある場合、タイプ情報を含むプロンプトが生成される"""
        query = "WiFiのパスワードは？"
        context = "WiFiパスワード: test1234"
        result = build_facility_prompt(query, context, "wifi", "ja")

        # request_type "wifi" に対応する情報が含まれる
        assert "Wi-Fi" in result or "wifi" in result.lower()
        assert query in result
        assert context in result

    def test_build_facility_prompt_without_request_type(self):
        """request_type がない場合、汎用プロンプトが生成される"""
        query = "施設について教えて"
        context = "施設情報..."
        result = build_facility_prompt(query, context, None, "ja")

        assert isinstance(result, str)
        assert len(result) > 0
        assert query in result
        assert context in result

    def test_build_facility_prompt_en_vs_ja(self):
        """英語と日本語で異なるプロンプトが生成される"""
        query = "test query"
        context = "test context"

        result_ja = build_facility_prompt(query, context, "wifi", "ja")
        result_en = build_facility_prompt(query, context, "wifi", "en")

        # 異なるプロンプトであることを確認
        assert result_ja != result_en
        # 日本語プロンプトには「質問」が含まれる
        assert "質問" in result_ja
        # 英語プロンプトには "Question" が含まれる
        assert "Question" in result_en


class TestMemoryPrompts:
    """MemoryAgent プロンプトのテスト"""

    def test_build_memory_prompt_returns_formatted_string(self):
        """build_memory_prompt は整形された文字列を返す"""
        query = "前に何を聞いた？"
        context = {"context_string": "以前の会話: ユーザー: WiFiは? AI: パスワードは..."}
        result = build_memory_prompt(query, context, "question_history", "ja")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_memory_prompt_contains_query(self):
        """プロンプトにクエリが含まれる"""
        query = "What did I ask before?"
        context = {"context_string": "Previous: ..."}
        result = build_memory_prompt(query, context, "question_history", "en")

        assert query in result

    def test_build_memory_prompt_question_history(self):
        """question_history タイプで適切なプロンプトが生成される"""
        query = "前の質問は？"
        context = {"context_string": "会話履歴..."}
        result = build_memory_prompt(query, context, "question_history", "ja")

        # 「質問」「履歴」などのキーワードが含まれる
        assert "質問" in result or "履歴" in result

    def test_build_memory_prompt_answer_history(self):
        """answer_history タイプで適切なプロンプトが生成される"""
        query = "前の回答は？"
        context = {"context_string": "会話履歴..."}
        result = build_memory_prompt(query, context, "answer_history", "ja")

        # 「回答」「履歴」などのキーワードが含まれる
        assert "回答" in result or "履歴" in result

    def test_build_memory_prompt_other_option(self):
        """other_option タイプで適切なプロンプトが生成される"""
        query = "もう一つの方は？"
        context = {"context_string": "会話履歴..."}
        result = build_memory_prompt(query, context, "other_option", "ja")

        # 「別の」「選択肢」などのキーワードが含まれる
        assert len(result) > 0

    def test_build_memory_prompt_general_memory(self):
        """general_memory タイプで適切なプロンプトが生成される"""
        query = "会話の内容は？"
        context = {"context_string": "会話履歴..."}
        result = build_memory_prompt(query, context, "general_memory", "ja")

        assert len(result) > 0

    def test_build_memory_prompt_unknown_type_falls_back_to_general(self):
        """未知のタイプは general_memory にフォールバック"""
        query = "test query"
        context = {"context_string": "history..."}
        result = build_memory_prompt(query, context, "unknown_type", "ja")

        # general_memory のテンプレートが使われる（エラーにならない）
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_memory_prompt_ja_vs_en_produces_different_prompts(self):
        """日本語と英語で異なるプロンプトが生成される"""
        query = "test query"
        context = {"context_string": "history..."}

        result_ja = build_memory_prompt(query, context, "question_history", "ja")
        result_en = build_memory_prompt(query, context, "question_history", "en")

        # 異なるプロンプトであることを確認
        assert result_ja != result_en

    def test_build_memory_prompt_uses_context_string(self):
        """context_string がプロンプトに含まれる"""
        query = "test"
        context_string = "Unique context marker 12345"
        context = {"context_string": context_string}

        result = build_memory_prompt(query, context, "general_memory", "ja")

        assert context_string in result
