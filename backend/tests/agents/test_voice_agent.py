import asyncio
from unittest.mock import AsyncMock

import httpx
import time
import pytest
from cachetools import TTLCache

from backend.agents.voice_agent import (
    DEFAULT_TTS_MAX_BYTES,
    parse_emotion_tags,
    preprocess_tts,
    clean_text_for_tts,
    get_tts_timeout_seconds,
    get_tts_max_bytes,
    truncate_by_bytes,
    map_vrm_to_tts_emotion,
    PiperPlusTTSClient,
    VoiceAgent,
    VoiceVoxClient,
)


class FakeTimer:
    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


class FakeTTSHTTPResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        json_data=None,
        text: str = "",
    ):
        self.status_code = status_code
        self.content = content
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


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


def test_truncate_by_bytes_handles_sentence_ending_over_limit():
    sentence = "エンジニアカフェの施設について詳しく説明します。"
    out = truncate_by_bytes(sentence * 20, 300)
    assert len(out.encode("utf-8")) <= 300
    assert out.endswith("。")
    assert out != sentence * 20


def test_get_tts_max_bytes_defaults_and_guards_invalid_env(monkeypatch):
    monkeypatch.delenv("TTS_MAX_BYTES", raising=False)
    assert get_tts_max_bytes() == DEFAULT_TTS_MAX_BYTES

    monkeypatch.setenv("TTS_MAX_BYTES", "1200")
    assert get_tts_max_bytes() == 1200

    monkeypatch.setenv("TTS_MAX_BYTES", "100")
    assert get_tts_max_bytes() == 200

    monkeypatch.setenv("TTS_MAX_BYTES", "invalid")
    assert get_tts_max_bytes() == DEFAULT_TTS_MAX_BYTES


def test_map_vrm_to_tts_emotion():
    """VRM(6種) -> 音声側(5種) 変換の整合性"""
    assert map_vrm_to_tts_emotion("relaxed") == "calm"
    assert map_vrm_to_tts_emotion("surprised") == "excited"
    assert map_vrm_to_tts_emotion("neutral") == "calm"
    assert map_vrm_to_tts_emotion("happy") == "happy"
    assert map_vrm_to_tts_emotion("sad") == "sad"
    assert map_vrm_to_tts_emotion("angry") == "angry"


@pytest.mark.asyncio
async def test_piper_client_reuses_async_client_and_closes(monkeypatch):
    class FakeAsyncClient:
        instances = []

        def __init__(self, timeout):
            self.timeout = timeout
            self.is_closed = False
            self.posts = []
            FakeAsyncClient.instances.append(self)

        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return FakeTTSHTTPResponse(content=b"wav-data")

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr("backend.agents.voice_agent.httpx.AsyncClient", FakeAsyncClient)
    client = PiperPlusTTSClient(api_url="http://piper")

    await client.synthesize_wav_base64("こんにちは", "ja")
    await client.synthesize_wav_base64("Hello", "en", speaker_id=2)

    assert len(FakeAsyncClient.instances) == 1
    instance = FakeAsyncClient.instances[0]
    assert instance.timeout == 30
    assert len(instance.posts) == 2
    assert instance.posts[0][0] == "http://piper/synthesize"
    assert instance.posts[0][1]["json"] == {"text": "こんにちは", "language": "ja"}
    assert instance.posts[1][1]["json"] == {
        "text": "Hello",
        "language": "en",
        "speaker_id": 2,
    }

    await client.close()

    assert instance.is_closed is True
    assert client._client is None


@pytest.mark.asyncio
async def test_piper_client_sends_speed_to_synthesize(monkeypatch):
    """PiperPlusTTSClient が speed を /synthesize ペイロードに含めること。

    話速 (PIPER_SPEED / UI スライダー) はクライアント -> server.py (length_scale)
    のパイプラインで伝播する。speed 未指定時はキー自体を送らない
    （サーバー側の PIPER_SPEED env に従う）。
    """

    class FakeAsyncClient:
        instances = []

        def __init__(self, timeout):
            self.timeout = timeout
            self.is_closed = False
            self.posts = []
            FakeAsyncClient.instances.append(self)

        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return FakeTTSHTTPResponse(content=b"wav-data")

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr("backend.agents.voice_agent.httpx.AsyncClient", FakeAsyncClient)
    client = PiperPlusTTSClient(api_url="http://piper")

    await client.synthesize_wav_base64("Hello", "en", speed=0.65)
    await client.synthesize_wav_base64("Hello", "en")
    await client.synthesize_wav_base64("Hello", "en", speaker_id=1, speed=0.85)

    instance = FakeAsyncClient.instances[0]
    assert len(instance.posts) == 3
    assert instance.posts[0][1]["json"] == {
        "text": "Hello",
        "language": "en",
        "speed": 0.65,
    }
    assert instance.posts[1][1]["json"] == {"text": "Hello", "language": "en"}
    assert instance.posts[2][1]["json"] == {
        "text": "Hello",
        "language": "en",
        "speaker_id": 1,
        "speed": 0.85,
    }

    await client.close()


@pytest.mark.asyncio
async def test_voicevox_client_reuses_async_client_and_closes(monkeypatch):
    class FakeAsyncClient:
        instances = []

        def __init__(self, timeout):
            self.timeout = timeout
            self.is_closed = False
            self.posts = []
            FakeAsyncClient.instances.append(self)

        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            if url.endswith("/audio_query"):
                return FakeTTSHTTPResponse(json_data={"query": "ok"})
            return FakeTTSHTTPResponse(content=b"voicevox-wav")

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr("backend.agents.voice_agent.httpx.AsyncClient", FakeAsyncClient)
    client = VoiceVoxClient(api_url="http://voicevox")

    await client.synthesize_wav_base64("こんにちは", "ja")
    await client.synthesize_wav_base64("こんばんは", "ja")

    assert len(FakeAsyncClient.instances) == 1
    instance = FakeAsyncClient.instances[0]
    assert instance.timeout == 30
    assert [url for url, _kwargs in instance.posts] == [
        "http://voicevox/initialize_speaker",
        "http://voicevox/audio_query",
        "http://voicevox/synthesis",
        "http://voicevox/audio_query",
        "http://voicevox/synthesis",
    ]

    await client.aclose()

    assert instance.is_closed is True
    assert client._client is None


@pytest.mark.asyncio
async def test_piper_client_preserves_timeout_error(monkeypatch):
    monkeypatch.setenv("PIPER_PLUS_RETRY_BACKOFF_SECONDS", "0")

    class TimeoutAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout
            self.is_closed = False
            self.calls = 0

        async def post(self, url, **kwargs):
            self.calls += 1
            raise httpx.TimeoutException("request timed out")

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr("backend.agents.voice_agent.httpx.AsyncClient", TimeoutAsyncClient)
    client = PiperPlusTTSClient(api_url="http://piper")

    with pytest.raises(RuntimeError, match="PiperPlus TTS connection timeout"):
        await client.synthesize_wav_base64("こんにちは", "ja")


@pytest.mark.asyncio
async def test_piper_client_retries_transient_5xx_then_succeeds(monkeypatch):
    monkeypatch.setenv("PIPER_PLUS_RETRY_BACKOFF_SECONDS", "0")
    instances = []

    class RetryAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout
            self.is_closed = False
            self.posts = []
            instances.append(self)

        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            if len(self.posts) == 1:
                return FakeTTSHTTPResponse(status_code=503, text="warming")
            return FakeTTSHTTPResponse(status_code=200, content=b"piper-wav")

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr("backend.agents.voice_agent.httpx.AsyncClient", RetryAsyncClient)
    client = PiperPlusTTSClient(api_url="http://piper")

    result = await client.synthesize_wav_base64("こんにちは", "ja")

    assert result == "cGlwZXItd2F2"
    assert len(instances) == 1
    assert [url for url, _kwargs in instances[0].posts] == [
        "http://piper/synthesize",
        "http://piper/synthesize",
    ]


@pytest.mark.asyncio
async def test_text_to_speech_calls_tts_with_processed_text_and_emotion(monkeypatch):
    """
    外部I/O（Piper TTS）をモック化し、VoiceAgent.text_to_speech が
    - タグ除去/整形/MTG置換を行った text で synthesize を呼ぶ
    - audioResponse を返す
    を検証する
    """
    agent = VoiceAgent(tts_provider="piper")
    calls = {}

    async def fake_synth(text, lang, speed=None):
        calls["text"] = text
        calls["lang"] = lang
        return "BASE64_WAV_DUMMY"

    # 外部I/O（Piper TTS）をモック化して単体テストにする
    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    result = await agent.text_to_speech(
        text="[happy]こんにちは！MTGの予定です。",
        language="ja",
        emotion=None,
    )

    assert result["success"] is True
    assert result["audioResponse"] == "BASE64_WAV_DUMMY"
    assert calls["lang"] == "ja"

    # MTGが置換されている
    assert "ミーティング" in calls["text"]


@pytest.mark.asyncio
async def test_text_to_speech_does_not_replace_ambiguous_source_text(monkeypatch):
    agent = VoiceAgent(tts_provider="piper")
    calls = {}
    agent.clarification_agent = AsyncMock()

    async def fake_synth(text, lang, speed=None):
        calls["text"] = text
        calls["lang"] = lang
        return "PIPER_BASE64_DUMMY"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)
    source_text = "What are good conversation topics when meeting engineers in Fukuoka?"

    result = await agent.text_to_speech(text=source_text, language="en")

    assert result["success"] is True
    assert calls["text"] == source_text
    assert calls["lang"] == "en"
    assert result["ambiguity_resolved"] is False
    agent.clarification_agent.handle_clarification.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_to_speech_fallback_on_error(monkeypatch):
    """1回目のTTSが失敗したら、フォールバック文言で再試行することを検証"""
    agent = VoiceAgent(tts_provider="voicevox")
    state = {"n": 0}

    async def fake_synth(text, lang, speaker_id=None, speed=None):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("primary tts failed")
        return "FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    result = await agent.text_to_speech(
        text="[happy]こんにちは",
        language="ja",
        emotion=None,
    )

    assert result["success"] is True
    assert result["audioResponse"] == "FALLBACK_BASE64"
    assert state["n"] == 2  # 1回失敗 + フォールバックで1回成功


@pytest.mark.asyncio
async def test_text_to_speech_piper_timeout_falls_back_quickly(monkeypatch):
    monkeypatch.setenv("TTS_PIPER_PRIMARY_TIMEOUT_SECONDS", "0.01")
    agent = VoiceAgent(tts_provider="piper")

    async def slow_piper(text, lang, speed=None):
        await asyncio.sleep(1)
        return "TOO_LATE"

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        return "VOICEVOX_FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", slow_piper)
    monkeypatch.setattr(
        agent.voicevox_fallback_client, "synthesize_wav_base64", fake_voicevox_synth
    )

    started_at = time.perf_counter()
    result = await agent.text_to_speech(text="こんにちは", language="ja")
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.25
    assert result["success"] is True
    assert result["fallback_used"] is True
    assert result["fallback_provider"] == "voicevox"
    assert result["audioResponse"] == "VOICEVOX_FALLBACK_BASE64"
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_text_to_speech_piper_primary_required_disables_fallback(monkeypatch):
    monkeypatch.setenv("TTS_REQUIRE_PRIMARY_PROVIDER", "true")
    agent = VoiceAgent(tts_provider="piper")
    calls = {"piper": 0}

    async def fake_piper_empty(text, lang, speed=None):
        del text, lang
        calls["piper"] += 1
        return ""

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_empty)

    result = await agent.text_to_speech(text="こんにちは", language="ja")
    second = await agent.text_to_speech(text="別の案内です", language="ja")

    assert agent.voicevox_fallback_client is None
    assert result["success"] is False
    assert result["fallback_used"] is False
    assert result["fallback_provider"] is None
    assert result["actual_provider"] is None
    assert "primary piper provider" in result["error"]
    assert second["success"] is False
    assert "failure cooldown" not in second["error"]
    assert calls == {"piper": 2}


def test_piper_primary_timeout_default_covers_live_answer_window(monkeypatch):
    monkeypatch.delenv("TTS_PIPER_PRIMARY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("TTS_PRIMARY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("TTS_PIPER_TIMEOUT_SECONDS", raising=False)

    assert get_tts_timeout_seconds("piper", "primary") == 20.0


def test_piper_voicevox_fallback_requires_url_on_cloud_run(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "engineer-cafe-backend")
    monkeypatch.delenv("VOICEVOX_API_URL", raising=False)

    agent = VoiceAgent(tts_provider="piper")

    assert agent.voicevox_fallback_client is None


@pytest.mark.asyncio
async def test_text_to_speech_caches_successful_fallback(monkeypatch):
    monkeypatch.setenv("TTS_PIPER_PRIMARY_TIMEOUT_SECONDS", "0.01")
    agent = VoiceAgent(tts_provider="piper")
    calls = {"piper": 0, "voicevox": 0}
    fallback_audio = "V" * 128

    async def slow_piper(text, lang, speed=None):
        calls["piper"] += 1
        await asyncio.sleep(1)
        return "TOO_LATE"

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        calls["voicevox"] += 1
        return fallback_audio

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", slow_piper)
    monkeypatch.setattr(
        agent.voicevox_fallback_client, "synthesize_wav_base64", fake_voicevox_synth
    )

    first = await agent.text_to_speech(text="こんにちは", language="ja")
    second = await agent.text_to_speech(text="こんにちは", language="ja")

    assert first["success"] is True
    assert first["fallback_used"] is True
    assert second["tts_cache_hit"] is True
    assert second["fallback_used"] is True
    assert second["fallback_provider"] == "voicevox"
    assert second["audioResponse"] == fallback_audio
    assert calls == {"piper": 1, "voicevox": 1}


@pytest.mark.asyncio
async def test_text_to_speech_piper_failure_cooldown_skips_next_primary_attempt(
    monkeypatch,
):
    monkeypatch.setenv("TTS_PIPER_FAILURE_COOLDOWN_SECONDS", "30")
    agent = VoiceAgent(tts_provider="piper")
    calls = {"piper": 0, "voicevox": 0}
    fallback_audio = "V" * 128

    async def broken_piper(text, lang, speed=None):
        del text, lang
        calls["piper"] += 1
        raise RuntimeError("piper transient failure")

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        del text, lang, speaker_id
        calls["voicevox"] += 1
        return fallback_audio

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", broken_piper)
    monkeypatch.setattr(
        agent.voicevox_fallback_client, "synthesize_wav_base64", fake_voicevox_synth
    )

    first = await agent.text_to_speech(text="こんにちは", language="ja")
    second = await agent.text_to_speech(text="別の案内です", language="ja")

    assert first["success"] is True
    assert first["fallback_used"] is True
    assert second["success"] is True
    assert second["fallback_used"] is True
    assert "failure cooldown" in second["error"]
    assert calls == {"piper": 1, "voicevox": 2}


@pytest.mark.asyncio
async def test_text_to_speech_empty_primary_audio_uses_fallback(monkeypatch):
    agent = VoiceAgent(tts_provider="voicevox")
    state = {"n": 0}

    async def fake_synth(text, lang, speaker_id=None, speed=None):
        state["n"] += 1
        if state["n"] == 1:
            return ""
        return "FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert result["fallback_provider"] == "voicevox"
    assert result["audioResponse"] == "FALLBACK_BASE64"
    assert "empty audio response" in result["error"]


@pytest.mark.asyncio
async def test_text_to_speech_piper_empty_primary_audio_uses_voicevox_fallback(
    monkeypatch,
):
    agent = VoiceAgent(tts_provider="piper")

    async def fake_piper_empty(text, lang, speed=None):
        return ""

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        return "VOICEVOX_FALLBACK_BASE64"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_empty)
    monkeypatch.setattr(
        agent.voicevox_fallback_client, "synthesize_wav_base64", fake_voicevox_synth
    )

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is True
    assert result["fallback_used"] is True
    assert result["fallback_provider"] == "voicevox"
    assert result["actual_provider"] == "voicevox"
    assert result["language"] == "ja"
    assert result["audioResponse"] == "VOICEVOX_FALLBACK_BASE64"
    assert "empty audio response" in result["error"]
    assert isinstance(result["tts_duration_ms"], int)


@pytest.mark.asyncio
async def test_text_to_speech_piper_local_fallback_failure_returns_error(monkeypatch):
    agent = VoiceAgent(tts_provider="piper")

    async def fake_piper_empty(text, lang, speed=None):
        return ""

    async def fake_voicevox_fail(text, lang, speaker_id=None):
        raise RuntimeError("voicevox unavailable")

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_empty)
    monkeypatch.setattr(agent.voicevox_fallback_client, "synthesize_wav_base64", fake_voicevox_fail)

    result = await agent.text_to_speech(text="こんにちは", language="ja")

    assert result["success"] is False
    assert result["fallback_used"] is True
    assert result["fallback_provider"] is None
    assert result["actual_provider"] is None
    assert result["language"] == "ja"
    assert "voicevox unavailable" in result["error"]


@pytest.mark.asyncio
async def test_text_to_speech_cache_hit_reuses_audio(monkeypatch):
    agent = VoiceAgent(tts_provider="piper")
    calls = {"count": 0}
    first_audio = "A" * 128

    async def fake_synth(text, lang, speed=None):
        del text, lang
        calls["count"] += 1
        return first_audio

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    first = await agent.text_to_speech(text="[happy]こんにちは", language="ja")
    second = await agent.text_to_speech(text="[happy]こんにちは", language="ja")

    assert calls["count"] == 1
    assert first["audioResponse"] == first_audio
    assert first["tts_cache_hit"] is False
    assert first["format"] == "audio/wav"
    assert second["audioResponse"] == first_audio
    assert second["tts_cache_hit"] is True
    assert second["format"] == "audio/wav"


@pytest.mark.asyncio
async def test_text_to_speech_cache_miss_for_different_text(monkeypatch):
    agent = VoiceAgent(tts_provider="piper")
    calls = {"count": 0}

    async def fake_synth(text, lang, speed=None):
        calls["count"] += 1
        return f"BASE64_WAV_{calls['count']}"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    first = await agent.text_to_speech(text="こんにちは", language="ja")
    second = await agent.text_to_speech(text="こんばんは", language="ja")

    assert calls["count"] == 2
    assert first["audioResponse"] == "BASE64_WAV_1"
    assert first["tts_cache_hit"] is False
    assert second["audioResponse"] == "BASE64_WAV_2"
    assert second["tts_cache_hit"] is False


@pytest.mark.asyncio
async def test_text_to_speech_cache_expires_after_ttl(monkeypatch):
    agent = VoiceAgent(tts_provider="voicevox")
    timer = FakeTimer()
    agent._tts_cache = TTLCache(maxsize=200, ttl=3600, timer=timer)
    calls = {"count": 0}

    async def fake_synth(text, lang, speaker_id=None, speed=None):
        calls["count"] += 1
        return f"VOICEVOX_BASE64_{calls['count']}"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    first = await agent.text_to_speech(text="こんにちは", language="ja")
    timer.advance(3601)
    second = await agent.text_to_speech(text="こんにちは", language="ja")

    assert calls["count"] == 2
    assert first["audioResponse"] == "VOICEVOX_BASE64_1"
    assert first["tts_cache_hit"] is False
    assert second["audioResponse"] == "VOICEVOX_BASE64_2"
    assert second["tts_cache_hit"] is False


@pytest.mark.asyncio
async def test_text_to_speech_cache_key_varies_by_language(monkeypatch):
    agent = VoiceAgent(tts_provider="piper")
    calls = {"count": 0, "languages": []}

    async def fake_synth(text, lang, speed=None):
        calls["count"] += 1
        calls["languages"].append(lang)
        return f"PIPER_BASE64_{calls['count']}"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_synth)

    first = await agent.text_to_speech(text="Hello", language="en")
    second = await agent.text_to_speech(text="Hello", language="ja")

    assert calls["count"] == 2
    assert calls["languages"] == ["en", "ja"]
    assert first["tts_cache_hit"] is False
    assert second["tts_cache_hit"] is False


@pytest.mark.asyncio
async def test_text_to_speech_routes_english_to_kokoro(monkeypatch):
    """英語テキストがKokoro TTSにルーティングされることを確認"""
    monkeypatch.setenv("KOKORO_API_URL", "http://localhost:8880")
    agent = VoiceAgent(tts_provider="voicevox")
    kokoro_called = {"called": False}

    async def fake_kokoro_synth(text, lang, voice=None, speed=None):
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
async def test_text_to_speech_voicevox_english_without_kokoro_uses_voicevox_wav(
    monkeypatch,
):
    monkeypatch.delenv("KOKORO_API_URL", raising=False)
    agent = VoiceAgent(tts_provider="voicevox")
    voicevox_called = {"called": False}

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        voicevox_called["called"] = True
        return "VOICEVOX_BASE64_WAV"

    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_voicevox_synth)

    result = await agent.text_to_speech(
        text="Hello, how are you?",
        language="en",
    )

    assert voicevox_called["called"] is True
    assert result["success"] is True
    assert result["audioResponse"] == "VOICEVOX_BASE64_WAV"
    assert result["format"] == "audio/wav"
    assert result["language"] == "en"


@pytest.mark.asyncio
async def test_text_to_speech_english_kokoro_failure_falls_back_to_voicevox(
    monkeypatch,
):
    monkeypatch.setenv("KOKORO_API_URL", "http://localhost:8880")
    agent = VoiceAgent(tts_provider="voicevox")

    async def fake_kokoro_fail(text, lang, voice=None, speed=None):
        raise RuntimeError("kokoro down")

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        return "VOICEVOX_FALLBACK_WAV"

    monkeypatch.setattr(agent.kokoro_client, "synthesize_wav_base64", fake_kokoro_fail)
    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_voicevox_synth)

    result = await agent.text_to_speech(
        text="Hello, how are you?",
        language="en",
    )

    assert result["success"] is True
    assert result["audioResponse"] == "VOICEVOX_FALLBACK_WAV"
    assert result["format"] == "audio/wav"
    assert result["fallback_used"] is True
    assert result["fallback_provider"] == "voicevox"
    assert "kokoro down" in result["error"]


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
    monkeypatch.setenv("KOKORO_API_URL", "http://localhost:8880")
    agent = VoiceAgent(tts_provider="voicevox")
    kokoro_called = {"called": False}
    voicevox_called = {"called": False}

    async def fake_kokoro_synth(text, lang, voice=None, speed=None):
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

    async def fake_piper_synth(text, lang, speed=None):
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
async def test_text_to_speech_truncates_long_spoken_text(monkeypatch):
    agent = VoiceAgent(tts_provider="piper")
    calls = {}

    async def fake_piper_synth(text, lang, speed=None):
        calls["text"] = text
        calls["lang"] = lang
        return "PIPER_BASE64_JA"

    monkeypatch.setenv("TTS_MAX_BYTES", "300")
    monkeypatch.setattr(agent.tts_client, "synthesize_wav_base64", fake_piper_synth)

    result = await agent.text_to_speech(
        text="。".join(["エンジニアカフェの施設について詳しく説明します"] * 30),
        language="ja",
    )

    assert result["success"] is True
    assert len(calls["text"].encode("utf-8")) <= 300
    assert calls["text"].endswith("。")


@pytest.mark.asyncio
async def test_text_to_speech_piper_routes_english(monkeypatch):
    """TTS_PROVIDER=piper のとき、英語テキストが piper-plus にルーティングされること"""
    agent = VoiceAgent(tts_provider="piper")
    piper_called = {"called": False}

    async def fake_piper_synth(text, lang, speed=None):
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

    async def fake_piper_fail(text, lang, speed=None):
        raise RuntimeError("piper connection error")

    voicevox_called = {"called": False}

    fallback_text = {"value": None}

    async def fake_voicevox_synth(text, lang, speaker_id=None):
        voicevox_called["called"] = True
        fallback_text["value"] = text
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
    assert result["fallback_used"] is True
    assert result["fallback_provider"] == "voicevox"
    assert result["cleanText"] == "こんにちは"
    assert fallback_text["value"] == "こんにちは"
    assert "piper connection error" in result["error"]


@pytest.mark.asyncio
async def test_text_to_speech_piper_fallback_english_to_kokoro(monkeypatch):
    """piper が英語合成に失敗したとき、Kokoro にフォールバックすること"""
    monkeypatch.setenv("KOKORO_API_URL", "http://localhost:8880")
    agent = VoiceAgent(tts_provider="piper")

    async def fake_piper_fail(text, lang, speed=None):
        raise RuntimeError("piper connection error")

    kokoro_called = {"called": False}

    fallback_text = {"value": None}

    async def fake_kokoro_synth(text, lang, voice=None, speed=None):
        kokoro_called["called"] = True
        fallback_text["value"] = text
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
    assert result["fallback_used"] is True
    assert result["fallback_provider"] == "kokoro"
    assert result["cleanText"] == "Hello, how can I help you?"
    assert fallback_text["value"] == "Hello, how can I help you?"
    assert "piper connection error" in result["error"]
