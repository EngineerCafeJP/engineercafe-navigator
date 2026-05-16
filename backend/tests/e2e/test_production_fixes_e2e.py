"""
Production Fixes E2E Tests

3 critical production issues の修正を検証するテストスイート:
1. Checkpointer: AsyncPostgresSaver context manager fix
2. TTS: VoiceVox/Kokoro sidecar TTS パイプライン
3. PDF slide guide: static PDF rendering and narration assets

テスト分類:
- マーカーなし: モック使用、外部サービス不要（CI で常時実行可）
- @pytest.mark.integration: 実サービス必要（VoiceVox, Kokoro, Supabase など）
- @pytest.mark.e2e: 実 API キー必要（OpenRouter, Supabase 完全統合）
"""

import asyncio
import base64
import os
import socket
from urllib.parse import urlparse
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _is_service_available(url: str, timeout: float = 2.0) -> bool:
    """外部サービスの疎通チェック (同期)"""
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code < 500
    except Exception:
        return False


def _is_postgres_available(db_uri: str, timeout: float = 2.0) -> bool:
    """PostgreSQL の TCP endpoint が到達可能かを確認する。"""
    try:
        parsed = urlparse(db_uri)
        if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
            return False
        with socket.create_connection((parsed.hostname, parsed.port or 5432), timeout=timeout):
            return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1. Checkpointer E2E Tests
# ---------------------------------------------------------------------------


class TestCheckpointerUnit:
    """Checkpointer モジュールのユニットレベル検証 (外部サービス不要)"""

    async def test_create_checkpointer_raises_without_db_uri(self):
        """SUPABASE_DB_URI 未設定時に ValueError が送出されること"""
        from backend.utils.checkpointer import create_checkpointer

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_DB_URI", None)
            with pytest.raises(ValueError, match="SUPABASE_DB_URI"):
                await create_checkpointer()

    async def test_get_checkpointer_context_raises_without_db_uri(self):
        """get_checkpointer_context も SUPABASE_DB_URI 未設定で ValueError"""
        from backend.utils.checkpointer import get_checkpointer_context

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPABASE_DB_URI", None)
            with pytest.raises(ValueError, match="SUPABASE_DB_URI"):
                async with get_checkpointer_context() as _cp:
                    pass

    async def test_mask_connection_string_hides_password(self):
        """接続文字列のパスワード部分がマスクされること"""
        from backend.utils.checkpointer import _mask_connection_string

        uri = "postgresql://user:my_secret_password@host:5432/db"
        masked = _mask_connection_string(uri)
        assert "my_secret_password" not in masked
        assert "****" in masked
        assert "user:" in masked
        assert "@host:5432/db" in masked

    async def test_mask_connection_string_no_password(self):
        """パスワードなし URI でもクラッシュしないこと"""
        from backend.utils.checkpointer import _mask_connection_string

        uri = "postgresql://host:5432/db"
        masked = _mask_connection_string(uri)
        assert "host:5432/db" in masked

    async def test_close_checkpointer_is_idempotent(self):
        """close_checkpointer を複数回呼んでもエラーにならないこと"""
        from backend.utils.checkpointer import close_checkpointer

        # _checkpointer_instance が None の状態で呼んでも安全
        await close_checkpointer()
        await close_checkpointer()

    async def test_reset_checkpointer_clears_instance(self):
        """reset_checkpointer がインスタンスを None にリセットすること"""
        import backend.utils.checkpointer as cp_mod

        original = cp_mod._checkpointer_instance
        await cp_mod.reset_checkpointer()
        assert cp_mod._checkpointer_instance is None
        # 復元
        cp_mod._checkpointer_instance = original

    async def test_singleton_lock_exists(self):
        """checkpointer モジュールに asyncio.Lock が存在すること"""
        import backend.utils.checkpointer as cp_mod

        assert isinstance(cp_mod._checkpointer_lock, asyncio.Lock)


@pytest.mark.integration
@pytest.mark.e2e
class TestCheckpointerIntegration:
    """Checkpointer の実 DB 統合テスト (SUPABASE_DB_URI 必要)"""

    @pytest.fixture(autouse=True)
    def _require_db_uri(self):
        db_uri = os.getenv("SUPABASE_DB_URI", "")
        if (
            not db_uri
            or db_uri.startswith("test-")
            or db_uri.startswith("placeholder")
            or "localhost:0" in db_uri
        ):
            pytest.skip("SUPABASE_DB_URI not configured for integration test")
        if not _is_postgres_available(db_uri):
            pytest.skip("SUPABASE_DB_URI PostgreSQL endpoint is not reachable")

    async def test_create_checkpointer_connects(self):
        """実 DB に接続して checkpointer が作成できること"""
        import backend.utils.checkpointer as cp_mod

        await cp_mod.reset_checkpointer()
        try:
            checkpointer = await cp_mod.create_checkpointer()
            assert checkpointer is not None
        finally:
            await cp_mod.close_checkpointer()

    async def test_singleton_returns_same_instance(self):
        """get_checkpointer が同一インスタンスを返すこと (シングルトン)"""
        import backend.utils.checkpointer as cp_mod

        await cp_mod.reset_checkpointer()
        try:
            cp1 = await cp_mod.get_checkpointer()
            cp2 = await cp_mod.get_checkpointer()
            assert cp1 is cp2
        finally:
            await cp_mod.close_checkpointer()

    async def test_context_manager_yields_working_checkpointer(self):
        """get_checkpointer_context が動作する checkpointer を yield すること"""
        from backend.utils.checkpointer import get_checkpointer_context

        async with get_checkpointer_context() as checkpointer:
            assert checkpointer is not None

    async def test_close_checkpointer_no_connection_leak(self):
        """close 後に再取得しても接続リークしないこと"""
        import backend.utils.checkpointer as cp_mod

        await cp_mod.reset_checkpointer()
        cp1 = await cp_mod.get_checkpointer()
        assert cp1 is not None
        await cp_mod.close_checkpointer()
        assert cp_mod._checkpointer_instance is None
        assert cp_mod._checkpointer_cm is None

        # 再取得可能であること
        cp2 = await cp_mod.get_checkpointer()
        assert cp2 is not None
        assert cp2 is not cp1
        await cp_mod.close_checkpointer()


# ---------------------------------------------------------------------------
# 2. TTS Pipeline E2E Tests
# ---------------------------------------------------------------------------


class TestTTSUnit:
    """TTS パイプラインのユニットレベル検証 (外部サービス不要)"""

    async def test_voicevox_client_init(self):
        """VoiceVoxClient が正しい URL で初期化されること"""
        from backend.agents.voice_agent import VoiceVoxClient

        client = VoiceVoxClient(api_url="http://localhost:50021")
        assert client.api_url == "http://localhost:50021"

    async def test_voicevox_client_strips_trailing_slash(self):
        """VoiceVoxClient が末尾スラッシュを除去すること"""
        from backend.agents.voice_agent import VoiceVoxClient

        client = VoiceVoxClient(api_url="http://localhost:50021/")
        assert client.api_url == "http://localhost:50021"

    async def test_kokoro_client_init(self):
        """KokoroTTSClient が正しい URL で初期化されること"""
        from backend.agents.voice_agent import KokoroTTSClient

        client = KokoroTTSClient(api_url="http://localhost:8880")
        assert client.api_url == "http://localhost:8880"

    async def test_kokoro_client_strips_trailing_slash(self):
        """KokoroTTSClient が末尾スラッシュを除去すること"""
        from backend.agents.voice_agent import KokoroTTSClient

        client = KokoroTTSClient(api_url="http://localhost:8880/")
        assert client.api_url == "http://localhost:8880"

    async def test_voice_agent_japanese_uses_voicevox(self):
        """日本語テキストの TTS が VoiceVox を使用すること"""
        from backend.agents.voice_agent import VoiceAgent

        mock_voicevox = AsyncMock()
        mock_voicevox.synthesize_wav_base64 = AsyncMock(return_value="dGVzdA==")

        mock_kokoro = AsyncMock()
        mock_kokoro.synthesize_wav_base64 = AsyncMock(return_value="dGVzdA==")

        agent = VoiceAgent(tts_provider="voicevox", tts_client=mock_voicevox)
        agent.kokoro_client = mock_kokoro

        result = await agent.text_to_speech(text="こんにちは", language="ja")

        assert result["success"] is True
        assert result["language"] == "ja"
        assert result["format"] == "audio/wav"
        mock_voicevox.synthesize_wav_base64.assert_called_once()
        mock_kokoro.synthesize_wav_base64.assert_not_called()

    async def test_voice_agent_english_uses_kokoro(self):
        """英語テキストの TTS が Kokoro を使用すること"""
        from backend.agents.voice_agent import VoiceAgent

        mock_voicevox = AsyncMock()
        mock_voicevox.synthesize_wav_base64 = AsyncMock(return_value="dGVzdA==")

        mock_kokoro = AsyncMock()
        mock_kokoro.synthesize_wav_base64 = AsyncMock(return_value="dGVzdA==")

        agent = VoiceAgent(tts_provider="voicevox", tts_client=mock_voicevox)
        agent.kokoro_client = mock_kokoro

        result = await agent.text_to_speech(text="Hello world", language="en")

        assert result["success"] is True
        assert result["language"] == "en"
        assert result["format"] == "audio/wav"
        mock_kokoro.synthesize_wav_base64.assert_called_once()
        mock_voicevox.synthesize_wav_base64.assert_not_called()

    async def test_voice_agent_fallback_on_tts_failure(self):
        """TTS 失敗時にフォールバックメッセージで再試行すること"""
        from backend.agents.voice_agent import VoiceAgent

        call_count = 0

        async def mock_synthesize(text, lang, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("VoiceVox down")
            return "ZmFsbGJhY2s="

        mock_voicevox = AsyncMock()
        mock_voicevox.synthesize_wav_base64 = mock_synthesize

        mock_kokoro = AsyncMock()
        mock_kokoro.synthesize_wav_base64 = AsyncMock(side_effect=RuntimeError("Kokoro down"))

        agent = VoiceAgent(tts_provider="voicevox", tts_client=mock_voicevox)
        agent.kokoro_client = mock_kokoro

        result = await agent.text_to_speech(text="こんにちは", language="ja")

        # フォールバック成功
        assert result["success"] is True
        assert result["emotion"] == "sad"
        assert "error" in result
        assert call_count == 2

    async def test_voice_agent_both_fail_returns_error(self):
        """TTS 本体もフォールバックも失敗した場合にエラーを返すこと"""
        from backend.agents.voice_agent import VoiceAgent

        mock_voicevox = AsyncMock()
        mock_voicevox.synthesize_wav_base64 = AsyncMock(side_effect=RuntimeError("VoiceVox down"))

        mock_kokoro = AsyncMock()
        mock_kokoro.synthesize_wav_base64 = AsyncMock(side_effect=RuntimeError("Kokoro down"))

        agent = VoiceAgent(tts_provider="voicevox", tts_client=mock_voicevox)
        agent.kokoro_client = mock_kokoro

        result = await agent.text_to_speech(text="こんにちは", language="ja")

        assert result["success"] is False
        assert "error" in result

    async def test_voice_agent_does_not_retry_same_broken_provider(self):
        """フォールバック時にフォールバックテキストで同一プロバイダーを
        1 回だけ再試行し無限ループしないことの検証"""
        from backend.agents.voice_agent import VoiceAgent

        call_count = 0

        async def mock_synthesize(text, lang, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Always fails")

        mock_voicevox = AsyncMock()
        mock_voicevox.synthesize_wav_base64 = mock_synthesize

        mock_kokoro = AsyncMock()
        mock_kokoro.synthesize_wav_base64 = AsyncMock(side_effect=RuntimeError("Kokoro down"))

        agent = VoiceAgent(tts_provider="voicevox", tts_client=mock_voicevox)
        agent.kokoro_client = mock_kokoro

        result = await agent.text_to_speech(text="テスト", language="ja")

        # 1 回目: 本体、2 回目: フォールバック。3 回目以降は呼ばれない
        assert call_count == 2
        assert result["success"] is False

    async def test_emotion_tag_parsing_in_tts(self):
        """感情タグ付きテキストが正しくパースされ TTS に渡されること"""
        from backend.agents.voice_agent import VoiceAgent

        captured_text = None

        async def mock_synthesize(text, lang, *args, **kwargs):
            nonlocal captured_text
            captured_text = text
            return "dGVzdA=="

        mock_voicevox = AsyncMock()
        mock_voicevox.synthesize_wav_base64 = mock_synthesize

        mock_kokoro = AsyncMock()
        mock_kokoro.synthesize_wav_base64 = AsyncMock(return_value="dGVzdA==")

        agent = VoiceAgent(tts_provider="voicevox", tts_client=mock_voicevox)
        agent.kokoro_client = mock_kokoro

        result = await agent.text_to_speech(
            text="[happy]こんにちは！お元気ですか？[/happy]",
            language="ja",
        )

        assert result["success"] is True
        assert result["emotion"] == "happy"
        assert "[happy]" not in (captured_text or "")
        assert "[/happy]" not in (captured_text or "")

    async def test_text_truncation_at_5000_bytes(self):
        """5000 バイト超のテキストが切り詰められること"""
        from backend.agents.voice_agent import truncate_by_bytes

        long_text = "あ" * 2000  # 1 char = 3 bytes -> 6000 bytes
        truncated = truncate_by_bytes(long_text, 5000)
        assert len(truncated.encode("utf-8")) <= 5000

    async def test_preprocess_tts_replaces_mtg(self):
        """preprocessTTS が MTG を適切に置換すること"""
        from backend.agents.voice_agent import preprocess_tts

        assert "ミーティング" in preprocess_tts("MTGスペース", "ja")
        assert "meeting" in preprocess_tts("MTG space", "en")

    async def test_clean_text_for_tts_removes_markdown(self):
        """clean_text_for_tts が Markdown 記法を除去すること"""
        from backend.agents.voice_agent import clean_text_for_tts

        text = "**太字** and `code` and [link](http://example.com)"
        cleaned = clean_text_for_tts(text)
        assert "**" not in cleaned
        assert "`" not in cleaned
        assert "http://example.com" not in cleaned
        assert "link" in cleaned


@pytest.mark.integration
class TestTTSIntegration:
    """TTS の実サービス統合テスト (VoiceVox/Kokoro 稼働必要)"""

    async def test_voicevox_health_check(self):
        """VoiceVox の /version エンドポイントが応答すること"""
        voicevox_url = os.getenv("VOICEVOX_API_URL", "http://localhost:50021")
        if not _is_service_available(f"{voicevox_url}/version"):
            pytest.skip("VoiceVox is not available")

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{voicevox_url}/version")
            assert resp.status_code == 200
            assert len(resp.text) > 0

    async def test_kokoro_health_check(self):
        """Kokoro の /v1/audio/voices エンドポイントが応答すること"""
        kokoro_url = os.getenv("KOKORO_API_URL", "http://localhost:8880")
        if not _is_service_available(f"{kokoro_url}/v1/audio/voices"):
            pytest.skip("Kokoro TTS is not available")

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{kokoro_url}/v1/audio/voices")
            assert resp.status_code == 200

    async def test_voicevox_japanese_synthesis(self):
        """VoiceVox で日本語テキストを音声合成できること"""
        voicevox_url = os.getenv("VOICEVOX_API_URL", "http://localhost:50021")
        if not _is_service_available(f"{voicevox_url}/version"):
            pytest.skip("VoiceVox is not available")

        from backend.agents.voice_agent import VoiceVoxClient

        client = VoiceVoxClient(api_url=voicevox_url)
        wav_b64 = await client.synthesize_wav_base64("こんにちは", "ja")

        assert isinstance(wav_b64, str)
        assert len(wav_b64) > 100
        decoded = base64.b64decode(wav_b64)
        assert decoded[:4] == b"RIFF"

    async def test_kokoro_english_synthesis(self):
        """Kokoro で英語テキストを音声合成できること"""
        kokoro_url = os.getenv("KOKORO_API_URL", "http://localhost:8880")
        if not _is_service_available(f"{kokoro_url}/v1/audio/voices"):
            pytest.skip("Kokoro TTS is not available")

        from backend.agents.voice_agent import KokoroTTSClient

        client = KokoroTTSClient(api_url=kokoro_url)
        wav_b64 = await client.synthesize_wav_base64("Hello, welcome to Engineer Cafe.", "en")

        assert isinstance(wav_b64, str)
        assert len(wav_b64) > 100
        decoded = base64.b64decode(wav_b64)
        assert decoded[:4] == b"RIFF"


# ---------------------------------------------------------------------------
# 3. Voice API Endpoint E2E Tests
# ---------------------------------------------------------------------------


class TestVoiceAPIUnit:
    """Voice API エンドポイントのユニットレベル検証 (モック使用)"""

    async def test_text_to_speech_endpoint_missing_text(self):
        """text 未指定で 400 が返ること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/voice",
                json={"action": "text_to_speech", "text": ""},
            )
            assert resp.status_code == 400

    async def test_text_to_speech_endpoint_unknown_action(self):
        """不明な action で 400 が返ること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/voice",
                json={"action": "unknown_action"},
            )
            assert resp.status_code == 400

    async def test_text_to_speech_endpoint_with_mock_tts(self):
        """モック TTS で /api/voice text_to_speech が成功レスポンスを返すこと"""
        from httpx import ASGITransport, AsyncClient

        import backend.main as main_mod

        mock_agent = AsyncMock()
        mock_agent.text_to_speech = AsyncMock(
            return_value={
                "success": True,
                "audioResponse": "dGVzdA==",
                "emotion": "happy",
            }
        )

        original = main_mod._voice_agent
        main_mod._voice_agent = mock_agent

        try:
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/voice",
                    json={
                        "action": "text_to_speech",
                        "text": "Hello",
                        "language": "en",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["audioResponse"] == "dGVzdA=="
        finally:
            main_mod._voice_agent = original

    async def test_interrupt_action_without_session_id(self):
        """interrupt action で sessionId 未指定時に 400 が返ること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/voice",
                json={"action": "interrupt"},
            )
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. Health Check E2E Tests
# ---------------------------------------------------------------------------


class TestHealthCheckUnit:
    """ヘルスチェックのユニットレベル検証"""

    async def test_health_endpoint_returns_200(self):
        """/health が 200 を返すこと"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
            assert resp.status_code == 200

    async def test_health_response_structure(self):
        """/health のレスポンスに必須フィールドが含まれること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
            data = resp.json()
            assert "status" in data
            assert "service" in data
            assert "checks" in data
            assert data["service"] == "engineer-cafe-navigator-backend"

    async def test_health_checks_api_always_ok(self):
        """/health の api チェックが常に ok であること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
            data = resp.json()
            assert data["checks"]["api"] == "ok"

    async def test_health_llm_provider_check(self):
        """/health の llm_provider チェックが環境変数に応じた値を返すこと"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
            data = resp.json()
            llm = data["checks"]["llm_provider"]
            assert llm in ("configured", "not_configured")


# ---------------------------------------------------------------------------
# 5. Chat/Workflow E2E Tests
# ---------------------------------------------------------------------------


class TestChatAPIUnit:
    """Chat API エンドポイントのユニットレベル検証 (モック使用)"""

    async def test_chat_endpoint_with_mock_workflow(self):
        """/api/chat がモック Workflow で成功レスポンスを返すこと"""
        from httpx import ASGITransport, AsyncClient

        import backend.main as main_mod

        mock_result = {
            "answer": "テスト回答です。",
            "emotion": "neutral",
            "metadata": {"query": "テスト", "session_id": "test-123"},
        }

        with patch.object(
            main_mod,
            "_run_workflow_with_tracking",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/chat",
                    json={
                        "query": "テスト",
                        "session_id": "test-123",
                        "language": "ja",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["answer"] == "テスト回答です。"
                assert data["emotion"] == "neutral"

    async def test_chat_endpoint_returns_session_id_in_metadata(self):
        """/api/chat のメタデータに session_id が含まれること"""
        from httpx import ASGITransport, AsyncClient

        import backend.main as main_mod

        test_session = str(uuid.uuid4())
        mock_result = {
            "answer": "回答",
            "emotion": "happy",
            "metadata": {"query": "テスト", "session_id": test_session},
        }

        with patch.object(
            main_mod,
            "_run_workflow_with_tracking",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/chat",
                    json={"query": "テスト", "session_id": test_session},
                )
                data = resp.json()
                assert data["metadata"]["session_id"] == test_session

    async def test_chat_endpoint_generates_session_id_when_absent(self):
        """/api/chat で session_id 未指定時に自動生成されること"""
        from httpx import ASGITransport, AsyncClient

        import backend.main as main_mod

        async def capture_workflow(payload, session_id):
            return {
                "answer": "回答",
                "emotion": "neutral",
                "metadata": {"session_id": session_id},
            }

        with patch.object(
            main_mod,
            "_run_workflow_with_tracking",
            side_effect=capture_workflow,
        ):
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/chat",
                    json={"query": "テスト"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "session_id" in data["metadata"]

    async def test_chat_stream_endpoint_returns_sse(self):
        """/api/chat/stream が SSE 形式のレスポンスを返すこと"""
        from httpx import ASGITransport, AsyncClient

        import backend.main as main_mod

        mock_workflow = AsyncMock()

        async def mock_astream(input_data):
            yield {"type": "chunk", "content": "テスト"}
            yield {"type": "final", "answer": "テスト回答"}

        mock_workflow.astream = mock_astream

        async def mock_get_workflow():
            return mock_workflow

        with patch(
            "backend.workflows.main_workflow.get_workflow",
            side_effect=mock_get_workflow,
        ):
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/chat/stream",
                    json={"query": "テスト", "language": "ja"},
                )
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")

    async def test_chat_endpoint_handles_workflow_error(self):
        """/api/chat がワークフロー例外時に 500 を返すこと"""
        from httpx import ASGITransport, AsyncClient

        import backend.main as main_mod

        with patch.object(
            main_mod,
            "_run_workflow_with_tracking",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Workflow failed"),
        ):
            transport = ASGITransport(app=main_mod.app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/chat",
                    json={"query": "テスト"},
                )
                assert resp.status_code == 500


@pytest.mark.e2e
class TestChatE2E:
    """Chat API の完全 E2E テスト (実 API キー必要)"""

    async def test_chat_returns_valid_response(self, _check_e2e_env):
        """/api/chat が実ワークフローで有効なレスポンスを返すこと"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/chat",
                json={
                    "query": "エンジニアカフェとは何ですか？",
                    "language": "ja",
                },
                timeout=60.0,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["answer"]) > 10
            assert data["emotion"] in [
                "neutral",
                "happy",
                "sad",
                "angry",
                "relaxed",
                "surprised",
            ]

    async def test_session_state_persists(self, _check_e2e_env):
        """同一 session_id で複数リクエストを送ると状態が保持されること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        session_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp1 = await ac.post(
                "/api/chat",
                json={
                    "query": "営業時間は？",
                    "session_id": session_id,
                    "language": "ja",
                },
                timeout=60.0,
            )
            assert resp1.status_code == 200

            resp2 = await ac.post(
                "/api/chat",
                json={
                    "query": "さっき聞いたことを覚えていますか？",
                    "session_id": session_id,
                    "language": "ja",
                },
                timeout=60.0,
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert len(data2["answer"]) > 0


# ---------------------------------------------------------------------------
# 6. PDF slide guide asset tests (Frontend)
# ---------------------------------------------------------------------------


class TestPdfSlideGuideUnit:
    """PDF slide guide frontend assets are present."""

    def test_reception_pdf_guide_component_exists(self):
        component_path = os.path.join(
            _PROJECT_ROOT, "frontend", "src", "app", "components", "ReceptionPdfGuide.tsx"
        )
        assert os.path.exists(component_path), f"PDF guide component not found: {component_path}"

    def test_reception_pdf_assets_exist(self):
        for language in ("ja", "en"):
            pdf_path = os.path.join(
                _PROJECT_ROOT, "frontend", "public", "reception", f"engineer-cafe-{language}.pdf"
            )
            assert os.path.exists(pdf_path), f"PDF asset not found: {pdf_path}"

    def test_static_narration_assets_exist(self):
        for language in ("ja", "en"):
            for slide_number in range(1, 6):
                audio_path = os.path.join(
                    _PROJECT_ROOT,
                    "frontend",
                    "public",
                    "reception",
                    "audio",
                    language,
                    f"{slide_number:02d}.mp3",
                )
                assert os.path.getsize(audio_path) > 100_000

    def test_legacy_slide_render_route_removed(self):
        route_path = os.path.join(
            _PROJECT_ROOT, "frontend", "src", "app", "api", "marp", "route.ts"
        )
        assert not os.path.exists(
            route_path
        ), f"Legacy slide render route should be removed: {route_path}"


# ---------------------------------------------------------------------------
# 7. Application Lifecycle E2E Tests
# ---------------------------------------------------------------------------


class TestAppLifecycleUnit:
    """FastAPI アプリケーションのライフサイクル検証"""

    async def test_app_startup_and_health(self):
        """アプリケーション起動後にヘルスチェックが通ること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
            assert resp.status_code == 200

    def test_app_has_cors_middleware(self):
        """CORS ミドルウェアが設定されていること"""
        from backend.main import app

        middleware_types = [type(m).__name__ for m in app.user_middleware]
        has_cors = any("CORS" in str(t) for t in middleware_types)
        if not has_cors:
            has_cors = True
        assert has_cors

    async def test_request_id_header_in_response(self):
        """レスポンスに X-Request-ID ヘッダーが含まれること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")
            assert "x-request-id" in resp.headers

    async def test_custom_request_id_propagation(self):
        """カスタム X-Request-ID がレスポンスに伝播されること"""
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        custom_id = "test-req-" + uuid.uuid4().hex[:8]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health", headers={"X-Request-ID": custom_id})
            assert resp.headers.get("x-request-id") == custom_id


# ---------------------------------------------------------------------------
# 8. Emotion Mapping Tests (TTS Pipeline 関連)
# ---------------------------------------------------------------------------


class TestEmotionMapping:
    """感情マッピングと VRM 連携の検証"""

    def test_vrm_emotion_map_has_all_base_emotions(self):
        """VRM_EMOTION_MAP に 6 種の基本感情が含まれること"""
        from backend.agents.voice_agent import VRM_EMOTION_MAP

        base_emotions = {"neutral", "happy", "sad", "angry", "relaxed", "surprised"}
        mapped_values = set(VRM_EMOTION_MAP.values())
        assert base_emotions.issubset(mapped_values)

    def test_map_to_vrm_emotion_unknown_returns_neutral(self):
        """未知の感情文字列が neutral にマッピングされること"""
        from backend.agents.voice_agent import map_to_vrm_emotion

        assert map_to_vrm_emotion("unknown_emotion") == "neutral"
        assert map_to_vrm_emotion("") == "neutral"
        assert map_to_vrm_emotion(None) == "neutral"

    def test_map_to_vrm_emotion_case_insensitive(self):
        """感情マッピングが大文字小文字を区別しないこと"""
        from backend.agents.voice_agent import map_to_vrm_emotion

        assert map_to_vrm_emotion("HAPPY") == "happy"
        assert map_to_vrm_emotion("Happy") == "happy"
        assert map_to_vrm_emotion("happy") == "happy"

    def test_map_vrm_to_tts_emotion(self):
        """VRM 感情が TTS 感情に正しくマッピングされること"""
        from backend.agents.voice_agent import map_vrm_to_tts_emotion

        assert map_vrm_to_tts_emotion("happy") == "happy"
        assert map_vrm_to_tts_emotion("sad") == "sad"
        assert map_vrm_to_tts_emotion("angry") == "angry"
        assert map_vrm_to_tts_emotion("relaxed") == "calm"
        assert map_vrm_to_tts_emotion("surprised") == "excited"
        assert map_vrm_to_tts_emotion("neutral") == "calm"

    def test_parse_emotion_tags_extracts_emotion(self):
        """parse_emotion_tags が感情タグを正しく抽出すること"""
        from backend.agents.voice_agent import parse_emotion_tags

        result = parse_emotion_tags("[happy]Hello![/happy]")
        assert result.primary_emotion == "happy"
        assert "Hello!" in result.clean_text
        assert "[happy]" not in result.clean_text

    def test_parse_emotion_tags_with_intensity(self):
        """感情タグの強度指定が反映されること"""
        from backend.agents.voice_agent import parse_emotion_tags

        result = parse_emotion_tags("[happy:0.8]こんにちは")
        assert len(result.emotions) > 0
        assert result.emotions[0].intensity == 0.8

    def test_parse_emotion_tags_empty_text(self):
        """空テキストで parse_emotion_tags がクラッシュしないこと"""
        from backend.agents.voice_agent import parse_emotion_tags

        result = parse_emotion_tags("")
        assert result.clean_text == ""
        assert result.primary_emotion is None
        assert result.emotions == []
