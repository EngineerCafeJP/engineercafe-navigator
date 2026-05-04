"""Tests for backend.utils.memory_extractor — memory extraction from conversations."""

from backend.utils.memory_extractor import (
    extract_memories,
    extract_memory_candidates,
    _extract_name,
    _extract_affiliation,
    _extract_remember_request,
    _extract_episode_incident,
    _extract_location_preference,
)


class TestExtractMemories:
    """extract_memories() の統合テスト"""

    def test_empty_query_returns_empty(self):
        result = extract_memories("", "", "ja")
        assert result == []

    def test_name_extraction_ja(self):
        result = extract_memories("私は田中です", "こんにちは田中さん", "ja")
        assert len(result) >= 1
        names = [m for m in result if m["type"] == "visitor_name"]
        assert len(names) == 1
        # 「私は田中」パターンで「田中」が抽出される
        assert "田中" in names[0]["content"]
        assert names[0]["confidence"] == 0.9

    def test_affiliation_extraction_ja(self):
        result = extract_memories("Google から来ました", "Googleですね", "ja")
        affiliations = [m for m in result if m["type"] == "visitor_affiliation"]
        assert len(affiliations) == 1
        assert affiliations[0]["content"] == "Google"
        assert affiliations[0]["confidence"] == 0.8

    def test_remember_request_ja(self):
        result = extract_memories("覚えて: 私はPythonが好き", "承知しました", "ja")
        remembers = [m for m in result if m["type"] == "explicit_remember"]
        assert len(remembers) == 1
        assert "Pythonが好き" in remembers[0]["content"]
        assert remembers[0]["confidence"] == 1.0

    def test_remember_request_ja_tail_form_extracts_fact_not_polite_suffix(self):
        query = "私の好きな席は窓側です。visitor alpha-m-ltm-123 として覚えてください。"

        result = extract_memories(query, "承知しました", "ja")

        remembers = [m for m in result if m["type"] == "explicit_remember"]
        assert len(remembers) == 1
        assert "窓側" in remembers[0]["content"]
        assert "ください" not in remembers[0]["content"]
        assert "visitor" not in remembers[0]["content"]

    def test_remember_request_ja_bare_polite_request_is_not_memory(self):
        result = extract_memories("覚えてください。", "承知しました", "ja")

        assert [m for m in result if m["type"] == "explicit_remember"] == []

    def test_language_preference_en(self):
        result = extract_memories("Hello there", "Hi!", "en")
        lang_prefs = [m for m in result if m["type"] == "language_preference"]
        assert len(lang_prefs) == 1
        assert lang_prefs[0]["content"] == "en"
        assert lang_prefs[0]["confidence"] == 0.7

    def test_language_preference_not_added_for_ja(self):
        result = extract_memories("こんにちは", "こんにちは！", "ja")
        lang_prefs = [m for m in result if m["type"] == "language_preference"]
        assert len(lang_prefs) == 0

    def test_multiple_extractions_combined(self):
        result = extract_memories(
            "私は田中です。Googleから来ました。覚えて: 毎週火曜に来ます",
            "承知しました",
            "ja",
        )
        types = {m["type"] for m in result}
        assert "visitor_name" in types
        assert "visitor_affiliation" in types
        assert "explicit_remember" in types

    def test_no_match_returns_empty(self):
        result = extract_memories("今日の予定を教えて", "予定は特にありません", "ja")
        assert result == []

    def test_en_name_and_language(self):
        result = extract_memories("My name is John", "Hello John!", "en")
        names = [m for m in result if m["type"] == "visitor_name"]
        assert len(names) == 1
        assert names[0]["content"] == "John"
        lang_prefs = [m for m in result if m["type"] == "language_preference"]
        assert len(lang_prefs) == 1


class TestExtractMemoryCandidates:
    """extract_memory_candidates() のテスト"""

    def test_empty_returns_empty(self):
        result = extract_memory_candidates("", "", "ja", extracted_at=123.0)
        assert result == []

    def test_candidates_include_staging_metadata(self):
        result = extract_memory_candidates(
            "私は田中です。覚えて: 毎週火曜に来ます",
            "承知しました",
            "ja",
            extracted_at=1700000000.0,
        )
        assert len(result) >= 2
        first = result[0]
        assert first["status"] == "candidate"
        assert "candidate_type" in first
        assert "content" in first
        assert "confidence" in first
        assert first["source"] == "conversation_turn"
        assert first["language"] == "ja"
        assert first["extracted_at"] == 1700000000.0
        assert first["window_seconds"] == 180
        assert "volatility" in first
        assert "sensitivity" in first
        assert first["repeat_count"] == 1
        assert "evidence" in first
        assert first["evidence"]["query"].startswith("私は田中です")

    def test_type_policies_applied(self):
        result = extract_memory_candidates("私は田中です", "こんにちは", "ja", extracted_at=1.0)
        name_candidate = next(c for c in result if c["candidate_type"] == "visitor_name")
        assert name_candidate["sensitivity"] == "pii"
        assert name_candidate["volatility"] == "low"

    def test_episode_candidate_policy(self):
        result = extract_memory_candidates(
            "今日はもくもく会で来ました", "ようこそ", "ja", extracted_at=1.0
        )
        episode = [c for c in result if c["candidate_type"] == "episode_incident"]
        assert len(episode) == 1
        assert episode[0]["sensitivity"] == "non_pii"
        assert episode[0]["volatility"] == "medium"

    def test_location_candidate_policy(self):
        result = extract_memory_candidates(
            "いつも窓際席を使っています", "承知しました", "ja", extracted_at=1.0
        )
        loc = [c for c in result if c["candidate_type"] == "location_preference"]
        assert len(loc) == 1
        assert loc[0]["sensitivity"] == "non_pii"
        assert loc[0]["volatility"] == "medium"


class TestExtractName:
    """_extract_name() のユニットテスト"""

    def test_watashi_wa_pattern(self):
        assert _extract_name("私は山田です", "ja") is not None

    def test_boku_wa_pattern(self):
        assert _extract_name("僕は太郎", "ja") == "太郎"

    def test_namae_wa_pattern(self):
        assert _extract_name("名前は佐藤です", "ja") is not None

    def test_desu_pattern(self):
        result = _extract_name("鈴木です", "ja")
        assert result == "鈴木"

    def test_to_moushimasu_pattern(self):
        result = _extract_name("高橋と申します", "ja")
        assert result == "高橋"

    def test_en_my_name_is(self):
        assert _extract_name("my name is Alice", "en") == "Alice"

    def test_en_i_am(self):
        assert _extract_name("I am Bob", "en") == "Bob"

    def test_en_im(self):
        assert _extract_name("I'm Charlie", "en") == "Charlie"

    def test_en_call_me(self):
        assert _extract_name("call me Dave", "en") == "Dave"

    def test_en_full_name(self):
        result = _extract_name("my name is John Smith", "en")
        assert result == "John Smith"

    def test_non_name_filtered_ja(self):
        assert _extract_name("エンジニアです", "ja") is None

    def test_wifi_ssid_statement_not_extracted_as_name(self):
        query = "Wi-FiのSSIDはcafe-freeです。接続方法を教えてください。"

        assert _extract_name(query, "ja") is None
        assert extract_memories(query, "受付で確認してください", "ja") == []

    def test_non_name_filtered_en(self):
        assert _extract_name("I'm fine", "en") is None
        assert _extract_name("I'm good", "en") is None
        assert _extract_name("I'm happy", "en") is None
        assert _extract_name("I'm new", "en") is None

    def test_student_filtered(self):
        assert _extract_name("I'm student", "en") is None

    def test_no_match_returns_none(self):
        assert _extract_name("今日は天気がいい", "ja") is None
        assert _extract_name("hello world", "en") is None

    def test_empty_string(self):
        assert _extract_name("", "ja") is None
        assert _extract_name("", "en") is None

    def test_ore_wa_pattern(self):
        result = _extract_name("俺は健太", "ja")
        assert result == "健太"


class TestExtractAffiliation:
    """_extract_affiliation() のユニットテスト"""

    def test_kara_kimashita_pattern(self):
        result = _extract_affiliation("Googleから来ました", "ja")
        assert result == "Google"

    def test_ni_shozoku_pattern(self):
        result = _extract_affiliation("東京大学に所属しています", "ja")
        assert result is not None

    def test_de_hataraite_pattern(self):
        result = _extract_affiliation("トヨタで働いています", "ja")
        assert result == "トヨタ"

    def test_shozoku_wa_pattern(self):
        result = _extract_affiliation("所属は九州大学", "ja")
        assert result == "九州大学"

    def test_en_i_work_at(self):
        result = _extract_affiliation("I work at Google", "en")
        assert result == "Google"

    def test_en_im_from(self):
        result = _extract_affiliation("I'm from Microsoft", "en")
        assert result == "Microsoft"

    def test_en_i_work_for(self):
        result = _extract_affiliation("I work for Apple", "en")
        assert result == "Apple"

    def test_en_from_company(self):
        result = _extract_affiliation("from Amazon", "en")
        assert result == "Amazon"

    def test_no_match_returns_none(self):
        assert _extract_affiliation("今日は天気がいい", "ja") is None
        assert _extract_affiliation("hello world", "en") is None

    def test_empty_string(self):
        assert _extract_affiliation("", "ja") is None
        assert _extract_affiliation("", "en") is None

    def test_single_char_filtered(self):
        # 1文字の所属は除外される
        assert _extract_affiliation("所属はA", "ja") is None

    def test_no_mono_pattern(self):
        result = _extract_affiliation("富士通の者です", "ja")
        assert result == "富士通"

    def test_no_shain_pattern(self):
        result = _extract_affiliation("ソニーの社員です", "ja")
        assert result == "ソニー"


class TestExtractRememberRequest:
    """_extract_remember_request() のユニットテスト"""

    def test_oboete_pattern(self):
        result = _extract_remember_request("覚えて: 明日10時に来ます", "ja")
        assert result is not None
        assert "明日10時に来ます" in result

    def test_kioku_shite_pattern(self):
        result = _extract_remember_request("記憶して: Pythonが得意です", "ja")
        assert result is not None

    def test_wasurenaide_pattern(self):
        result = _extract_remember_request("忘れないで: 水曜日は休みです", "ja")
        assert result is not None

    def test_wo_oboete_pattern(self):
        result = _extract_remember_request("私の名前は田中を覚えて", "ja")
        assert result is not None

    def test_to_particle_oboete_pattern(self):
        result = _extract_remember_request("窓側の席が好きだと覚えて", "ja")
        assert result == "窓側の席が好きだ"

    def test_oboetoite_pattern(self):
        result = _extract_remember_request("窓側の席が好きだと覚えといてね", "ja")
        assert result == "窓側の席が好きだ"

    def test_en_remember_pattern(self):
        result = _extract_remember_request("remember: I like Python", "en")
        assert result is not None
        assert "I like Python" in result

    def test_en_dont_forget_pattern(self):
        result = _extract_remember_request("don't forget I come on Tuesdays", "en")
        assert result is not None

    def test_en_keep_in_mind_pattern(self):
        result = _extract_remember_request("keep in mind: I prefer English", "en")
        assert result is not None

    def test_en_please_remember_pattern(self):
        result = _extract_remember_request("please remember that I am a student", "en")
        assert result is not None

    def test_en_note_that_pattern(self):
        result = _extract_remember_request("please note that I need help with React", "en")
        assert result is not None

    def test_no_match_returns_none(self):
        assert _extract_remember_request("今日は天気がいい", "ja") is None
        assert _extract_remember_request("hello world", "en") is None

    def test_empty_string(self):
        assert _extract_remember_request("", "ja") is None
        assert _extract_remember_request("", "en") is None

    def test_too_short_content_filtered(self):
        # 2文字以下の内容は除外
        assert _extract_remember_request("覚えて: あ", "ja") is None

    def test_trailing_punctuation_stripped(self):
        result = _extract_remember_request("覚えて: 明日来ます。", "ja")
        assert result is not None
        assert not result.endswith("。")

        result_en = _extract_remember_request("remember: I will come tomorrow.", "en")
        assert result_en is not None
        assert not result_en.endswith(".")


class TestExtractEpisodeIncident:
    """_extract_episode_incident() のユニットテスト"""

    def test_mokumokukai_ja(self):
        result = _extract_episode_incident("今日はもくもく会で来ました", "ja")
        assert result is not None
        assert "もくもく会" in result

    def test_shini_kimashita_ja(self):
        result = _extract_episode_incident("アプリ開発をしに来ました", "ja")
        assert result is not None

    def test_tameni_kimashita_ja(self):
        result = _extract_episode_incident("本日はハッカソンのために来ました", "ja")
        assert result is not None

    def test_en_here_to(self):
        result = _extract_episode_incident("I'm here to develop my app", "en")
        assert result is not None
        assert "develop" in result.lower()

    def test_en_attending(self):
        result = _extract_episode_incident("I'm attending the hackathon", "en")
        assert result is not None

    def test_en_here_for(self):
        result = _extract_episode_incident("here for the study group", "en")
        assert result is not None

    def test_no_match_ja(self):
        assert _extract_episode_incident("今日は天気がいい", "ja") is None

    def test_no_match_en(self):
        assert _extract_episode_incident("hello world", "en") is None

    def test_empty_string(self):
        assert _extract_episode_incident("", "ja") is None
        assert _extract_episode_incident("", "en") is None


class TestExtractLocationPreference:
    """_extract_location_preference() のユニットテスト"""

    def test_itsumo_pattern_ja(self):
        result = _extract_location_preference("いつも窓際席を使っています", "ja")
        assert result is not None

    def test_fudan_pattern_ja(self):
        result = _extract_location_preference("普段は奥のエリアに座っています", "ja")
        assert result is not None

    def test_keyword_match_ja(self):
        result = _extract_location_preference("メインエリアスペース", "ja")
        assert result is not None

    def test_en_usually_use(self):
        result = _extract_location_preference("I usually use the main area", "en")
        assert result is not None
        assert "main area" in result.lower()

    def test_en_prefer(self):
        result = _extract_location_preference("I prefer the window seat", "en")
        assert result is not None

    def test_en_usual_spot(self):
        result = _extract_location_preference("my usual spot is the back corner", "en")
        assert result is not None

    def test_no_match_ja(self):
        assert _extract_location_preference("今日は天気がいい", "ja") is None

    def test_no_match_en(self):
        assert _extract_location_preference("hello world", "en") is None

    def test_empty_string(self):
        assert _extract_location_preference("", "ja") is None
        assert _extract_location_preference("", "en") is None
