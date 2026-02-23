"""
STT -> Voice パイプライン統合テスト

STTAgent と VoiceAgent が連携して動作し、音声入力→テキスト→音声出力の
フルパイプラインが正しく機能することを検証する。

テスト範囲:
1. TestSTTAgentPipeline: STTAgent 単体のモック統合テスト
2. TestVoiceAgentPipeline: VoiceAgent 単体のモック統合テスト（HTTP呼び出しモック）
3. TestSTTToVoicePipeline: STT→Voice のフルパイプライン統合テスト

すべての外部依存（Vosk, Google STT, VoiceVox, Kokoro）はモックで置き換え、
エージェント間のインターフェース契約が正しいことを検証する。
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.stt_agent import (
    STAGE_GRAMMARS,
    LocalSTTClient,
    STTAgent,
    TranscriptionResult,
)
from backend.agents.voice_agent import (
    VoiceAgent,
    VoiceVoxClient,
    KokoroTTSClient,
    clean_text_for_tts,
    preprocess_tts,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_local_stt_client():
    """LocalSTTClient のモック。transcribe / transcribe_auto_detect を提供。

    spec=LocalSTTClient を使用することで isinstance(client, LocalSTTClient) が
    True を返し、STTAgent 内の分岐ロジックが正しく動作する。
    """
    client = AsyncMock(spec=LocalSTTClient)
    client.transcribe = AsyncMock()
    client.transcribe_auto_detect = AsyncMock()
    return client


@pytest.fixture
def mock_google_stt_client():
    """GoogleSTTClient のモック。transcribe / is_available を提供。"""
    client = AsyncMock()
    client.transcribe = AsyncMock()
    client.is_available = MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_voicevox_client():
    """VoiceVoxClient のモック。"""
    client = AsyncMock(spec=VoiceVoxClient)
    client.synthesize_wav_base64 = AsyncMock()
    return client


@pytest.fixture
def mock_kokoro_client():
    """KokoroTTSClient のモック。"""
    client = AsyncMock(spec=KokoroTTSClient)
    client.synthesize_wav_base64 = AsyncMock()
    return client


@pytest.fixture
def mock_language_processor():
    """LanguageProcessor のモック。detect / detect_language を提供。"""
    processor = AsyncMock()
    processor.detect = AsyncMock(return_value="ja")
    processor.detect_language = MagicMock(
        return_value={
            "detected": "ja",
            "confidence": 0.9,
            "is_mixed": False,
            "languages": {"primary": "ja"},
        }
    )
    return processor


@pytest.fixture
def mock_clarification_agent():
    """ClarificationAgent のモック。"""
    agent = AsyncMock()
    agent.handle_clarification = AsyncMock()
    return agent


@pytest.fixture
def stt_agent_vosk(mock_local_stt_client, mock_google_stt_client):
    """Vosk ベースの STTAgent（モック注入済み）。"""
    return STTAgent(
        stt_provider="vosk",
        stt_client=mock_local_stt_client,
        fallback_client=mock_google_stt_client,
        language_processor=None,
        use_grammar=False,
        confidence_threshold=0.4,
    )


@pytest.fixture
def stt_agent_google(mock_google_stt_client):
    """Google STT ベースの STTAgent（モック注入済み）。"""
    return STTAgent(
        stt_provider="google",
        stt_client=mock_google_stt_client,
        fallback_client=None,
        language_processor=None,
    )


# =============================================================================
# 1. TestSTTAgentPipeline
# =============================================================================


class TestSTTAgentPipeline:
    """STTAgent のパイプラインテスト。"""

    async def test_vosk_stt_success(self, stt_agent_vosk, mock_local_stt_client):
        """Vosk STTが正常にTranscriptionResultを返し、speech_to_textが正しいdictを返す。"""
        mock_local_stt_client.transcribe.return_value = TranscriptionResult(
            text="こんにちは",
            confidence=0.92,
            language="ja",
            word_confidences=[
                {"word": "こんにちは", "conf": 0.92},
            ],
        )

        audio_data = b"fake-wav-data"
        result = await stt_agent_vosk.speech_to_text(audio_data, language="ja")

        assert result["success"] is True
        assert result["transcript"] == "こんにちは"
        assert result["confidence"] == 0.92
        assert result["language"] == "ja"
        assert result["provider"] == "vosk"
        assert "error" not in result
        mock_local_stt_client.transcribe.assert_awaited_once()

    async def test_vosk_auto_detect(self, stt_agent_vosk, mock_local_stt_client):
        """language=None のとき transcribe_auto_detect が呼ばれ、自動言語検出が動作する。"""
        mock_local_stt_client.transcribe_auto_detect.return_value = TranscriptionResult(
            text="hello world",
            confidence=0.88,
            language="en",
            word_confidences=[
                {"word": "hello", "conf": 0.90},
                {"word": "world", "conf": 0.86},
            ],
        )

        audio_data = b"fake-wav-data"
        result = await stt_agent_vosk.speech_to_text(audio_data, language=None)

        assert result["success"] is True
        assert result["transcript"] == "hello world"
        assert result["language"] == "en"
        assert result["confidence"] == 0.88
        mock_local_stt_client.transcribe_auto_detect.assert_awaited_once()
        mock_local_stt_client.transcribe.assert_not_awaited()

    async def test_vosk_low_confidence_fallback(
        self,
        mock_local_stt_client,
        mock_google_stt_client,
    ):
        """Vosk の confidence が閾値未満のとき Google STT にフォールバックする。"""
        mock_local_stt_client.transcribe.return_value = TranscriptionResult(
            text="こ に ち は",
            confidence=0.2,
            language="ja",
            word_confidences=[{"word": "こ", "conf": 0.2}],
        )
        mock_google_stt_client.is_available.return_value = True
        mock_google_stt_client.transcribe.return_value = "こんにちは"

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
            confidence_threshold=0.4,
        )

        audio_data = b"fake-wav-data"
        result = await agent.speech_to_text(audio_data, language="ja")

        assert result["success"] is True
        assert result["transcript"] == "こんにちは"
        assert result["provider"] == "google-fallback"
        assert result["fallback_used"] is True
        assert result["original_confidence"] == 0.2
        mock_google_stt_client.transcribe.assert_awaited_once_with(audio_data, "ja")

    async def test_google_stt_fallback_unavailable(
        self,
        mock_local_stt_client,
        mock_google_stt_client,
    ):
        """Google STTが利用不可(is_available=False)の場合、Vosk結果がそのまま返る。"""
        mock_local_stt_client.transcribe.return_value = TranscriptionResult(
            text="なにか",
            confidence=0.3,
            language="ja",
            word_confidences=[{"word": "なにか", "conf": 0.3}],
        )
        mock_google_stt_client.is_available.return_value = False

        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
            confidence_threshold=0.4,
        )

        audio_data = b"fake-wav-data"
        result = await agent.speech_to_text(audio_data, language="ja")

        assert result["success"] is True
        assert result["transcript"] == "なにか"
        assert result["confidence"] == 0.3
        assert result["provider"] == "vosk"
        mock_google_stt_client.transcribe.assert_not_awaited()

    async def test_stt_provider_google(self, stt_agent_google, mock_google_stt_client):
        """STTAgent を stt_provider='google' で構成した場合、GoogleSTTClient が使われる。"""
        mock_google_stt_client.transcribe.return_value = "What are the business hours?"

        audio_data = b"fake-wav-data"
        result = await stt_agent_google.speech_to_text(audio_data, language="en")

        assert result["success"] is True
        assert result["transcript"] == "What are the business hours?"
        assert result["confidence"] is None
        assert result["language"] == "en"
        assert result["provider"] == "google"
        mock_google_stt_client.transcribe.assert_awaited_once_with(audio_data, "en")

    async def test_stt_error_handling(self, stt_agent_vosk, mock_local_stt_client):
        """STTで例外発生時、errorフィールドを含むエラーdictが返る。"""
        mock_local_stt_client.transcribe.side_effect = RuntimeError("Vosk model not found")

        audio_data = b"fake-wav-data"
        result = await stt_agent_vosk.speech_to_text(audio_data, language="ja")

        assert result["success"] is False
        assert result["transcript"] == ""
        assert result["confidence"] == 0.0
        assert "Vosk model not found" in result["error"]
        assert result["provider"] == "vosk"

    async def test_grammar_resolution_with_stage(
        self, mock_local_stt_client, mock_google_stt_client
    ):
        """conversation_stage='greeting' 指定時、_resolve_grammar が greeting 用 grammar を返す。"""
        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
            use_grammar=False,
        )

        grammar = agent._resolve_grammar("greeting")

        assert grammar is not None
        assert "ja" in grammar
        assert "en" in grammar
        # greeting ステージのキーワードが含まれていることを確認
        assert "こんにちは" in grammar["ja"]
        assert "hello" in grammar["en"]
        # STAGE_GRAMMARS["greeting"] のすべてのキーワードが含まれていることを確認
        for word in STAGE_GRAMMARS["greeting"]["ja"]:
            assert word in grammar["ja"]
        for word in STAGE_GRAMMARS["greeting"]["en"]:
            assert word in grammar["en"]

    async def test_grammar_resolution_without_stage(
        self, mock_local_stt_client, mock_google_stt_client
    ):
        """use_grammar=False かつ conversation_stage=None のとき、
        _resolve_grammar は None を返す。"""
        agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
            use_grammar=False,
        )

        grammar = agent._resolve_grammar(None)

        assert grammar is None


# =============================================================================
# 2. TestVoiceAgentPipeline
# =============================================================================


class TestVoiceAgentPipeline:
    """VoiceAgent のパイプラインテスト（HTTP 呼び出しをモック）。"""

    async def test_tts_japanese_via_voicevox(
        self,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """日本語テキストが VoiceVox 経由で音声合成され、base64 WAV が返る。"""
        fake_wav = base64.b64encode(b"RIFF-fake-wav-data").decode("utf-8")
        mock_voicevox_client.synthesize_wav_base64.return_value = fake_wav

        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "voicevox"
        agent.tts_client = mock_voicevox_client
        agent.kokoro_client = mock_kokoro_client
        agent.language_processor = mock_language_processor
        agent.clarification_agent = mock_clarification_agent

        result = await agent.text_to_speech(
            text="エンジニアカフェへようこそ",
            language="ja",
        )

        assert result["success"] is True
        assert result["audioResponse"] == fake_wav
        assert result["format"] == "audio/wav"
        assert result["language"] == "ja"
        mock_voicevox_client.synthesize_wav_base64.assert_awaited_once()
        mock_kokoro_client.synthesize_wav_base64.assert_not_awaited()

    async def test_tts_english_via_kokoro(
        self,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """英語テキストが Kokoro TTS 経由で音声合成され、base64 WAV が返る。"""
        fake_wav = base64.b64encode(b"RIFF-fake-wav-en").decode("utf-8")
        mock_kokoro_client.synthesize_wav_base64.return_value = fake_wav

        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "voicevox"
        agent.tts_client = mock_voicevox_client
        agent.kokoro_client = mock_kokoro_client
        agent.language_processor = mock_language_processor
        agent.clarification_agent = mock_clarification_agent

        result = await agent.text_to_speech(
            text="Welcome to Engineer Cafe",
            language="en",
        )

        assert result["success"] is True
        assert result["audioResponse"] == fake_wav
        assert result["format"] == "audio/wav"
        assert result["language"] == "en"
        mock_kokoro_client.synthesize_wav_base64.assert_awaited_once()
        mock_voicevox_client.synthesize_wav_base64.assert_not_awaited()

    async def test_tts_with_emotion(
        self,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """emotion パラメータが VRM emotion にマッピングされて返る。"""
        fake_wav = base64.b64encode(b"wav-happy").decode("utf-8")
        mock_voicevox_client.synthesize_wav_base64.return_value = fake_wav

        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "voicevox"
        agent.tts_client = mock_voicevox_client
        agent.kokoro_client = mock_kokoro_client
        agent.language_processor = mock_language_processor
        agent.clarification_agent = mock_clarification_agent

        result = await agent.text_to_speech(
            text="ようこそ！",
            language="ja",
            emotion="happy",
        )

        assert result["success"] is True
        assert result["emotion"] == "happy"

    async def test_tts_with_emotion_tag_in_text(
        self,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """テキスト内の emotion タグ [excited] がパースされ、primary_emotion が設定される。"""
        fake_wav = base64.b64encode(b"wav-excited").decode("utf-8")
        mock_voicevox_client.synthesize_wav_base64.return_value = fake_wav

        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "voicevox"
        agent.tts_client = mock_voicevox_client
        agent.kokoro_client = mock_kokoro_client
        agent.language_processor = mock_language_processor
        agent.clarification_agent = mock_clarification_agent

        result = await agent.text_to_speech(
            text="[excited]すごいですね！",
            language="ja",
        )

        assert result["success"] is True
        # "excited" is mapped to VRM "happy"
        assert result["emotion"] == "happy"
        # emotion tag はテキストから除去される
        assert "[excited]" not in result["cleanText"]

    async def test_tts_text_cleaning(self):
        """Markdown, HTML, 特殊文字が除去され、MTG がミーティングに変換される。"""
        # clean_text_for_tts のテスト
        raw = "**重要** MTG: `会議室A`を予約"
        cleaned = clean_text_for_tts(raw)
        assert "**" not in cleaned
        assert "`" not in cleaned

        # preprocess_tts のテスト
        processed_ja = preprocess_tts("次のMTGは3時です", "ja")
        assert "MTG" not in processed_ja
        assert "ミーティング" in processed_ja

        processed_en = preprocess_tts("Next MTG at 3pm", "en")
        assert "MTG" not in processed_en
        assert "meeting" in processed_en

    async def test_tts_empty_text_returns_error(
        self,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """空テキストの場合、VoiceVox 呼び出しが失敗しエラーが返る。"""
        mock_voicevox_client.synthesize_wav_base64.side_effect = RuntimeError("Empty text")
        # フォールバックも失敗させて完全なエラーレスポンスを取得
        mock_voicevox_client.synthesize_wav_base64.side_effect = [
            RuntimeError("Empty text"),
            RuntimeError("Fallback also failed"),
        ]

        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "voicevox"
        agent.tts_client = mock_voicevox_client
        agent.kokoro_client = mock_kokoro_client
        agent.language_processor = mock_language_processor
        agent.clarification_agent = mock_clarification_agent

        result = await agent.text_to_speech(text="", language="ja")

        assert result["success"] is False
        assert "error" in result

    async def test_tts_fallback_on_voicevox_failure(
        self,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """VoiceVox が失敗した場合、フォールバックメッセージで再試行する。"""
        fallback_wav = base64.b64encode(b"fallback-wav").decode("utf-8")
        # 最初の呼び出しは失敗、フォールバックは成功
        mock_voicevox_client.synthesize_wav_base64.side_effect = [
            RuntimeError("VoiceVox connection timeout"),
            fallback_wav,
        ]

        agent = VoiceAgent.__new__(VoiceAgent)
        agent.tts_provider = "voicevox"
        agent.tts_client = mock_voicevox_client
        agent.kokoro_client = mock_kokoro_client
        agent.language_processor = mock_language_processor
        agent.clarification_agent = mock_clarification_agent

        result = await agent.text_to_speech(
            text="テスト音声",
            language="ja",
        )

        # フォールバック成功なので success=True だがエラー情報も含まれる
        assert result["success"] is True
        assert result["audioResponse"] == fallback_wav
        assert result["emotion"] == "sad"
        assert "error" in result
        assert "VoiceVox connection timeout" in result["error"]
        # synthesize_wav_base64 が2回呼ばれている（本体 + フォールバック）
        assert mock_voicevox_client.synthesize_wav_base64.await_count == 2


# =============================================================================
# 3. TestSTTToVoicePipeline
# =============================================================================


class TestSTTToVoicePipeline:
    """STT -> Voice のフルパイプライン統合テスト。"""

    async def test_full_pipeline_ja(
        self,
        mock_local_stt_client,
        mock_google_stt_client,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """日本語: 音声入力 -> STT -> テキスト -> VoiceAgent -> 音声出力。"""
        # STT モック設定
        mock_local_stt_client.transcribe.return_value = TranscriptionResult(
            text="営業時間は何時ですか",
            confidence=0.95,
            language="ja",
            word_confidences=[
                {"word": "営業時間", "conf": 0.96},
                {"word": "は", "conf": 0.99},
                {"word": "何時", "conf": 0.93},
                {"word": "です", "conf": 0.95},
                {"word": "か", "conf": 0.92},
            ],
        )

        # TTS モック設定
        fake_response_wav = base64.b64encode(b"RIFF-response-wav").decode("utf-8")
        mock_voicevox_client.synthesize_wav_base64.return_value = fake_response_wav

        # Step 1: STT (音声 -> テキスト)
        stt_agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
        )

        audio_input = base64.b64decode(base64.b64encode(b"fake-16khz-mono-wav"))
        stt_result = await stt_agent.speech_to_text(audio_input, language="ja")

        assert stt_result["success"] is True
        assert stt_result["transcript"] == "営業時間は何時ですか"
        assert stt_result["language"] == "ja"

        # Step 2: VoiceAgent (テキスト -> 音声)
        # シミュレーション: LLM応答テキストを TTS に渡す
        llm_response = "営業時間は朝9時から夜9時までです。"

        voice_agent = VoiceAgent.__new__(VoiceAgent)
        voice_agent.tts_provider = "voicevox"
        voice_agent.tts_client = mock_voicevox_client
        voice_agent.kokoro_client = mock_kokoro_client
        voice_agent.language_processor = mock_language_processor
        voice_agent.clarification_agent = mock_clarification_agent

        tts_result = await voice_agent.text_to_speech(
            text=llm_response,
            language=stt_result["language"],
        )

        assert tts_result["success"] is True
        assert tts_result["audioResponse"] == fake_response_wav
        assert tts_result["format"] == "audio/wav"
        assert tts_result["language"] == "ja"

    async def test_full_pipeline_en(
        self,
        mock_local_stt_client,
        mock_google_stt_client,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """英語: 音声入力 -> STT -> テキスト -> VoiceAgent -> 音声出力。"""
        # STT モック設定
        mock_local_stt_client.transcribe.return_value = TranscriptionResult(
            text="What are the business hours?",
            confidence=0.91,
            language="en",
            word_confidences=[
                {"word": "what", "conf": 0.92},
                {"word": "are", "conf": 0.95},
                {"word": "the", "conf": 0.98},
                {"word": "business", "conf": 0.88},
                {"word": "hours", "conf": 0.82},
            ],
        )

        # Kokoro TTS モック設定
        fake_response_wav = base64.b64encode(b"RIFF-en-response-wav").decode("utf-8")
        mock_kokoro_client.synthesize_wav_base64.return_value = fake_response_wav

        # Step 1: STT
        stt_agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
        )

        audio_input = b"fake-en-wav-data"
        stt_result = await stt_agent.speech_to_text(audio_input, language="en")

        assert stt_result["success"] is True
        assert stt_result["transcript"] == "What are the business hours?"
        assert stt_result["language"] == "en"

        # Step 2: VoiceAgent
        llm_response = "Our business hours are from 9 AM to 9 PM."

        voice_agent = VoiceAgent.__new__(VoiceAgent)
        voice_agent.tts_provider = "voicevox"
        voice_agent.tts_client = mock_voicevox_client
        voice_agent.kokoro_client = mock_kokoro_client
        voice_agent.language_processor = mock_language_processor
        voice_agent.clarification_agent = mock_clarification_agent

        tts_result = await voice_agent.text_to_speech(
            text=llm_response,
            language=stt_result["language"],
        )

        assert tts_result["success"] is True
        assert tts_result["audioResponse"] == fake_response_wav
        assert tts_result["format"] == "audio/wav"
        assert tts_result["language"] == "en"
        # 英語は Kokoro が使われる
        mock_kokoro_client.synthesize_wav_base64.assert_awaited_once()
        mock_voicevox_client.synthesize_wav_base64.assert_not_awaited()

    async def test_pipeline_with_auto_detect(
        self,
        mock_local_stt_client,
        mock_google_stt_client,
        mock_voicevox_client,
        mock_kokoro_client,
        mock_language_processor,
        mock_clarification_agent,
    ):
        """language=None で自動検出し、検出言語で TTS を実行するフルパイプライン。"""
        # STT モック: 自動検出で日本語と判定
        mock_local_stt_client.transcribe_auto_detect.return_value = TranscriptionResult(
            text="会議室を予約したいです",
            confidence=0.89,
            language="ja",
            word_confidences=[
                {"word": "会議室", "conf": 0.91},
                {"word": "を", "conf": 0.99},
                {"word": "予約", "conf": 0.88},
                {"word": "したい", "conf": 0.85},
                {"word": "です", "conf": 0.82},
            ],
        )

        # VoiceVox TTS モック設定
        fake_response_wav = base64.b64encode(b"RIFF-auto-detect-wav").decode("utf-8")
        mock_voicevox_client.synthesize_wav_base64.return_value = fake_response_wav

        # Step 1: STT (auto-detect)
        stt_agent = STTAgent(
            stt_provider="vosk",
            stt_client=mock_local_stt_client,
            fallback_client=mock_google_stt_client,
            language_processor=None,
        )

        audio_input = b"fake-audio-unknown-lang"
        stt_result = await stt_agent.speech_to_text(audio_input, language=None)

        assert stt_result["success"] is True
        assert stt_result["transcript"] == "会議室を予約したいです"
        assert stt_result["language"] == "ja"
        mock_local_stt_client.transcribe_auto_detect.assert_awaited_once()

        # Step 2: VoiceAgent (検出された言語で TTS)
        llm_response = "会議室の予約についてご案内します。"
        detected_language = stt_result["language"]

        voice_agent = VoiceAgent.__new__(VoiceAgent)
        voice_agent.tts_provider = "voicevox"
        voice_agent.tts_client = mock_voicevox_client
        voice_agent.kokoro_client = mock_kokoro_client
        voice_agent.language_processor = mock_language_processor
        voice_agent.clarification_agent = mock_clarification_agent

        tts_result = await voice_agent.text_to_speech(
            text=llm_response,
            language=detected_language,
        )

        assert tts_result["success"] is True
        assert tts_result["audioResponse"] == fake_response_wav
        assert tts_result["language"] == "ja"
        # 日本語なので VoiceVox が使われる
        mock_voicevox_client.synthesize_wav_base64.assert_awaited_once()
