import pytest

from backend.agents.voice_agent import (
    parse_emotion_tags,
    preprocess_tts,
    clean_text_for_tts,
    truncate_by_bytes,
    map_vrm_to_tts_emotion,
    VoiceAgent,
)


def test_parse_emotion_tags_removes_tags_and_maps_alias():
    """
    - [curious] が EmotionMapping により surprised に正規化される
    - タグが除去され clean_text だけ残る
    - :0.9 が intensity として解釈される
    - primaryEmotion は intensity 最大を採用
    """
    text = "[curious:0.9]こんにちは[/curious] 今日はいい天気"
    parsed = parse_emotion_tags(text)

    # タグが除去されている（角括弧が消えていること）
    assert "[" not in parsed.clean_text
    assert "curious" not in parsed.clean_text
    assert parsed.clean_text.startswith("こんにちは")

    # curious -> surprised（正規化）
    assert parsed.primary_emotion == "surprised"
    assert parsed.emotions[0].emotion == "surprised"
    assert parsed.emotions[0].intensity == 0.9


@pytest.mark.parametrize("lang, expected", [("ja", "ミーティング"), ("en", "meeting")])
def test_preprocess_tts_mtg(lang, expected):
    """preprocessTTS（TS）仕様：MTG を置換するだけ"""
    assert preprocess_tts("MTGがあります", lang).startswith(expected)
    assert preprocess_tts("mtgがあります", lang).startswith(expected)  # 大文字小文字無視も確認


def test_clean_text_for_tts_strips_markdown_links_code():
    text = (
        "# 見出し\n"
        "**太字** と *斜体*\n"
        "[リンク](https://example.com)\n"
        "`inline_code`\n"
        "```python\n"
        'print("hello")\n'
        "```\n"
    )

    cleaned = clean_text_for_tts(text)

    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "# " not in cleaned

    # Markdown リンクは表示テキストのみ残し、URL は除去する
    assert "https://example.com" not in cleaned
    assert "リンク" in cleaned

    assert "`" not in cleaned
    assert "inline_code" in cleaned
    assert "print(" not in cleaned


def test_clean_text_for_tts_preserves_technical_symbols_and_single_pipes():
    text = """
    <p>Use vector<int> when 1 < 2.</p>
    | name | value |
    grep foo | sort
    """

    cleaned = clean_text_for_tts(text)

    assert "<p>" not in cleaned
    assert "</p>" not in cleaned
    assert "vector<int>" in cleaned
    assert "1 < 2" in cleaned
    # Table data rows are converted to plain text (pipes removed, content kept)
    assert "name" in cleaned
    assert "value" in cleaned
    assert "grep foo | sort" in cleaned


def test_truncate_by_bytes_over_limit():
    """5000 bytes 制限を超える入力が 5000 bytes 以下に収まること"""
    text = "あ" * 3000
    out = truncate_by_bytes(text, 5000)
    assert len(out.encode("utf-8")) <= 5000


def test_map_vrm_to_tts_emotion():
    """VRM(6種) -> 音声側(5種) 変換の整合性"""
    assert map_vrm_to_tts_emotion("relaxed") == "calm"
    assert map_vrm_to_tts_emotion("surprised") == "excited"
    assert map_vrm_to_tts_emotion("neutral") == "calm"
    assert map_vrm_to_tts_emotion("happy") == "happy"
    assert map_vrm_to_tts_emotion("sad") == "sad"
    assert map_vrm_to_tts_emotion("angry") == "angry"


@pytest.mark.asyncio
async def test_text_to_speech_calls_tts_with_processed_text_and_emotion(monkeypatch):
    """
    外部I/O（Google TTS）をモック化し、VoiceAgent.text_to_speech が
    - タグ除去/整形/MTG置換を行った text で synthesize を呼ぶ
    - emotion を VRM->TTS 変換して渡す
    - audioResponse を返す
    を検証する
    """
    agent = VoiceAgent(tts_provider="google")
    calls = {}

    async def fake_synth(text, lang, tts_emotion):
        calls["text"] = text
        calls["lang"] = lang
        calls["tts_emotion"] = tts_emotion
        return "BASE64_MP3_DUMMY"

    # 外部I/O（Google TTS）をモック化して単体テストにする
    monkeypatch.setattr(agent.tts_client, "synthesize_mp3_base64", fake_synth)

    result = await agent.text_to_speech(
        text="[happy]こんにちは！MTGの予定です。",
        language="ja",
        emotion=None,
    )

    assert result["success"] is True
    assert result["audioResponse"] == "BASE64_MP3_DUMMY"
    assert calls["lang"] == "ja"

    # MTGが置換されている
    assert "ミーティング" in calls["text"]

    # VRM happy -> TTS happy
    assert calls["tts_emotion"] == "happy"


@pytest.mark.asyncio
async def test_text_to_speech_fallback_on_error(monkeypatch):
    """1回目のTTSが失敗したら、フォールバック文言で再試行することを検証"""
    agent = VoiceAgent(tts_provider="google")
    state = {"n": 0}

    async def fake_synth(text, lang, tts_emotion):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("primary tts failed")
        return "FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_mp3_base64", fake_synth)

    result = await agent.text_to_speech(
        text="[happy]こんにちは",
        language="ja",
        emotion=None,
    )

    assert result["success"] is True
    assert result["audioResponse"] == "FALLBACK_BASE64"
    assert state["n"] == 2  # 1回失敗 + フォールバックで1回成功


@pytest.mark.asyncio
async def test_text_to_speech_routes_english_to_kokoro(monkeypatch):
    """英語テキストがKokoro TTSにルーティングされることを確認"""
    agent = VoiceAgent(tts_provider="voicevox")
    kokoro_called = {"called": False}

    async def fake_kokoro_synth(text, lang, voice=None):
        kokoro_called["called"] = True
        return "KOKORO_BASE64_WAV"

    monkeypatch.setattr(agent.kokoro_client, "synthesize_wav_base64", fake_kokoro_synth)

    result = await agent.text_to_speech(
        text="Hello, how are you?",
        language="en",
    )

    assert kokoro_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "KOKORO_BASE64_WAV"
    assert result["format"] == "audio/wav"
    assert result["language"] == "en"


@pytest.mark.asyncio
async def test_text_to_speech_routes_japanese_to_voicevox(monkeypatch):
    """日本語テキストがVoiceVoxにルーティングされることを確認"""
    agent = VoiceAgent(tts_provider="voicevox")
    voicevox_called = {"called": False}

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        voicevox_called["called"] = True
        return "VOICEVOX_BASE64_WAV"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_voicevox_synth)

    result = await agent.text_to_speech(
        text="こんにちは、元気ですか？",
        language="ja",
    )

    assert voicevox_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "VOICEVOX_BASE64_WAV"
    assert result["format"] == "audio/wav"
    assert result["language"] == "ja"


@pytest.mark.asyncio
async def test_text_to_speech_auto_detects_language_and_routes(monkeypatch):
    """言語自動検出が正しく動作し、適切なTTSエンジンにルーティングされることを確認"""
    agent = VoiceAgent(tts_provider="voicevox")
    kokoro_called = {"called": False}
    voicevox_called = {"called": False}

    async def fake_kokoro_synth(text, lang, voice=None):
        kokoro_called["called"] = True
        return "KOKORO_BASE64_WAV"

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        voicevox_called["called"] = True
        return "VOICEVOX_BASE64_WAV"

    monkeypatch.setattr(agent.kokoro_client, "synthesize_wav_base64", fake_kokoro_synth)
    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_voicevox_synth)

    # 英語テキスト（言語未指定）
    result_en = await agent.text_to_speech(
        text="Hello, welcome to Engineer Cafe!",
        language=None,  # 自動検出
    )

    assert kokoro_called["called"] is True
    assert result_en["success"] is True
    assert result_en["language"] == "en"

    # リセット
    kokoro_called["called"] = False

    # 日本語テキスト（言語未指定）
    result_ja = await agent.text_to_speech(
        text="こんにちは、エンジニアカフェへようこそ！",
        language=None,  # 自動検出
    )

    assert voicevox_called["called"] is True
    assert result_ja["success"] is True
    assert result_ja["language"] == "ja"


# ---------------------------------------------------------------------------
# piper-plus プロバイダーのルーティング・フォールバックテスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_to_speech_piper_routes_japanese(monkeypatch):
    """TTS_PROVIDER=piper のとき、日本語テキストが piper-plus にルーティングされること"""
    agent = VoiceAgent(tts_provider="piper")
    piper_called = {"called": False}

    async def fake_piper_synth(text, lang):
        piper_called["called"] = True
        return "PIPER_BASE64_JA"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_synth)

    result = await agent.text_to_speech(
        text="こんにちは、エンジニアカフェへようこそ！",
        language="ja",
    )

    assert piper_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "PIPER_BASE64_JA"
    assert result["format"] == "audio/wav"
    assert result["language"] == "ja"


@pytest.mark.asyncio
async def test_text_to_speech_piper_routes_english(monkeypatch):
    """TTS_PROVIDER=piper のとき、英語テキストが piper-plus にルーティングされること"""
    agent = VoiceAgent(tts_provider="piper")
    piper_called = {"called": False}

    async def fake_piper_synth(text, lang):
        piper_called["called"] = True
        return "PIPER_BASE64_EN"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_synth)

    result = await agent.text_to_speech(
        text="Welcome to Engineer Cafe!",
        language="en",
    )

    assert piper_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "PIPER_BASE64_EN"
    assert result["format"] == "audio/wav"
    assert result["language"] == "en"


@pytest.mark.asyncio
async def test_text_to_speech_piper_fallback_japanese_to_voicevox(monkeypatch):
    """piper が日本語合成に失敗したとき、VoiceVox にフォールバックすること"""
    agent = VoiceAgent(tts_provider="piper")

    async def fake_piper_fail(text, lang):
        raise RuntimeError("piper connection error")

    voicevox_called = {"called": False}

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        voicevox_called["called"] = True
        return "VOICEVOX_FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_fail)
    monkeypatch.setattr(
        agent.voicevox_fallback_client, "synthesize_wav_base64", fake_voicevox_synth
    )

    result = await agent.text_to_speech(
        text="こんにちは",
        language="ja",
    )

    assert voicevox_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "VOICEVOX_FALLBACK_BASE64"
    assert result["format"] == "audio/wav"


@pytest.mark.asyncio
async def test_text_to_speech_piper_fallback_english_to_kokoro(monkeypatch):
    """piper が英語合成に失敗したとき、Kokoro にフォールバックすること"""
    agent = VoiceAgent(tts_provider="piper")

    async def fake_piper_fail(text, lang):
        raise RuntimeError("piper connection error")

    kokoro_called = {"called": False}

    async def fake_kokoro_synth(text, lang, voice=None):
        kokoro_called["called"] = True
        return "KOKORO_FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_fail)
    monkeypatch.setattr(agent.kokoro_client, "synthesize_wav_base64", fake_kokoro_synth)

    result = await agent.text_to_speech(
        text="Hello, how can I help you?",
        language="en",
    )

    assert kokoro_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "KOKORO_FALLBACK_BASE64"
    assert result["format"] == "audio/wav"
