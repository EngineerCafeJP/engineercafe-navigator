"""
HTTP層を経由するE2Eテスト

httpx.AsyncClient + ASGITransport パターンを使用して、FastAPI のルーティング、
認証、CORS、ミドルウェア、エラーハンドリングを含む全HTTPスタックを検証する。

全テストはモック使用でCI実行可能。外部サービス（LLM、Supabase等）への依存なし。
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

import backend.main as main_mod
from backend.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

TEST_API_KEY = os.getenv("API_KEY", "test-api-key")
VALID_API_HEADERS = {"X-API-Key": TEST_API_KEY}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    """
    verify_api_key() が参照するモジュールレベル変数とenv両方をパッチする。
    import時に _API_SECRET_KEY が確定済みのため、属性の直接パッチが必要。
    """
    monkeypatch.setenv("API_SECRET_KEY", TEST_API_KEY)
    monkeypatch.setattr(main_mod, "_API_SECRET_KEY", TEST_API_KEY)


@pytest_asyncio.fixture
async def client():
    """
    ASGITransport を使用した非同期HTTPクライアント。
    実際のTCPソケットを使わず、ミドルウェアスタック全体を通過する。
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 1. /health エンドポイント
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """ヘルスチェックエンドポイントの検証"""

    async def test_health_returns_200(self, client: httpx.AsyncClient):
        """GET /health は認証不要で200を返す"""
        response = await client.get("/health")
        # ステータスコードが200であること
        assert response.status_code == 200

    async def test_health_json_structure(self, client: httpx.AsyncClient):
        """GET /health のレスポンスに status, checks, service キーが含まれること"""
        response = await client.get("/health")
        body = response.json()
        # status フィールドの存在確認
        assert "status" in body, "レスポンスに 'status' キーが必要"
        # checks フィールドの存在確認
        assert "checks" in body, "レスポンスに 'checks' キーが必要"
        # service フィールドの存在確認
        assert "service" in body, "レスポンスに 'service' キーが必要"

    async def test_health_status_value(self, client: httpx.AsyncClient):
        """GET /health の status は 'ok' または 'degraded' のいずれかであること"""
        response = await client.get("/health")
        body = response.json()
        # ステータス値が許容範囲内であること
        assert body["status"] in (
            "ok",
            "degraded",
        ), f"status は 'ok' か 'degraded' のはず、実際: {body['status']}"


# ---------------------------------------------------------------------------
# 2. /api/chat エンドポイント
# ---------------------------------------------------------------------------


class TestChatEndpoint:
    """チャットエンドポイントの検証"""

    async def test_chat_without_api_key_returns_403(self, client: httpx.AsyncClient):
        """POST /api/chat に X-API-Key なしでリクエストすると403が返る"""
        response = await client.post(
            "/api/chat",
            json={"query": "こんにちは", "session_id": "test-session"},
        )
        # 認証なしは403
        assert response.status_code == 403

    async def test_chat_with_valid_key_and_mock_workflow(self, client: httpx.AsyncClient):
        """POST /api/chat に有効なAPIキーとモックワークフローで200が返る"""
        mock_result = {
            "answer": "エンジニアカフェへようこそ！",
            "emotion": "happy",
            "metadata": {"query": "こんにちは", "session_id": "test-session"},
        }

        with patch.object(
            main_mod, "_run_workflow_with_tracking", new_callable=AsyncMock
        ) as mock_wf:
            mock_wf.return_value = mock_result
            response = await client.post(
                "/api/chat",
                headers=VALID_API_HEADERS,
                json={"query": "こんにちは", "session_id": "test-session", "language": "ja"},
            )

        # ワークフローモック時に200が返ること
        assert response.status_code == 200
        body = response.json()
        # レスポンスに必須フィールドが含まれること
        assert "answer" in body, "レスポンスに 'answer' が必要"
        assert "emotion" in body, "レスポンスに 'emotion' が必要"
        assert "metadata" in body, "レスポンスに 'metadata' が必要"
        # モックの回答が返ること
        assert body["answer"] == "エンジニアカフェへようこそ！"

    async def test_chat_missing_query_field_returns_422(self, client: httpx.AsyncClient):
        """POST /api/chat で必須フィールド 'query' がないと422が返る"""
        response = await client.post(
            "/api/chat",
            headers=VALID_API_HEADERS,
            json={"language": "ja"},  # query フィールドなし
        )
        # Pydantic バリデーションエラーで422
        assert response.status_code == 422

    async def test_chat_empty_query_does_not_crash(self, client: httpx.AsyncClient):
        """POST /api/chat に空文字列の query を送ると5xxにならないこと"""
        mock_result = {
            "answer": "ご質問をお聞かせください。",
            "emotion": "neutral",
            "metadata": {},
        }

        with patch.object(
            main_mod, "_run_workflow_with_tracking", new_callable=AsyncMock
        ) as mock_wf:
            mock_wf.return_value = mock_result
            response = await client.post(
                "/api/chat",
                headers=VALID_API_HEADERS,
                json={"query": "", "session_id": "test-empty"},
            )

        # 空クエリで5xxにならないこと（200 or 422が許容範囲）
        assert response.status_code in (
            200,
            422,
        ), f"空クエリで予期しないステータス: {response.status_code}"


# ---------------------------------------------------------------------------
# 3. /api/chat/stream エンドポイント
# ---------------------------------------------------------------------------


class TestChatStreamEndpoint:
    """SSEストリーミングチャットエンドポイントの検証"""

    async def test_stream_without_auth_returns_403(self, client: httpx.AsyncClient):
        """POST /api/chat/stream に認証なしでリクエストすると403が返る"""
        response = await client.post(
            "/api/chat/stream",
            json={"query": "hello", "session_id": "test"},
        )
        # 認証なしは403
        assert response.status_code == 403

    async def test_stream_with_auth_returns_sse(self, client: httpx.AsyncClient):
        """POST /api/chat/stream にモックワークフローでSSE形式のレスポンスが返る"""

        async def mock_astream(payload):
            """モックストリームジェネレータ"""
            yield {"type": "token", "content": "こんにちは"}
            yield {"type": "token", "content": "！"}

        mock_workflow = MagicMock()
        mock_workflow.astream = mock_astream

        # get_workflow は chat_stream 内で遅延importされるため、ソースモジュールでパッチ
        with patch(
            "backend.workflows.main_workflow.get_workflow",
            new_callable=AsyncMock,
            return_value=mock_workflow,
        ):
            response = await client.post(
                "/api/chat/stream",
                headers=VALID_API_HEADERS,
                json={"query": "テスト", "session_id": "test-stream", "language": "ja"},
            )

        # ステータスコード200
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        # Content-Type が text/event-stream であること
        assert (
            "text/event-stream" in content_type
        ), f"SSEのContent-Typeが期待と異なる: {content_type}"
        # レスポンスボディに 'data:' チャンクが含まれること
        assert "data:" in response.text, "SSEレスポンスに 'data:' が含まれるべき"


# ---------------------------------------------------------------------------
# 4. /api/voice エンドポイント
# ---------------------------------------------------------------------------


class TestVoiceEndpoint:
    """音声APIエンドポイントの検証"""

    async def test_voice_without_auth_returns_403(self, client: httpx.AsyncClient):
        """POST /api/voice に認証なしでリクエストすると403が返る"""
        response = await client.post(
            "/api/voice",
            json={"action": "text_to_speech", "text": "hello"},
        )
        # 認証なしは403
        assert response.status_code == 403

    async def test_voice_tts_missing_text_returns_400(self, client: httpx.AsyncClient):
        """POST /api/voice で text_to_speech アクションに text がないと400が返る"""
        response = await client.post(
            "/api/voice",
            headers=VALID_API_HEADERS,
            json={"action": "text_to_speech"},  # text フィールドなし
        )
        # text が必須で400エラー
        assert response.status_code == 400

    async def test_voice_tts_empty_text_returns_400(self, client: httpx.AsyncClient):
        """POST /api/voice で text_to_speech アクションに空白のみ text だと400が返る"""
        response = await client.post(
            "/api/voice",
            headers=VALID_API_HEADERS,
            json={"action": "text_to_speech", "text": "   "},  # 空白のみ
        )
        # 空白のみのtextは400エラー
        assert response.status_code == 400

    async def test_voice_tts_with_mock_returns_200(self, client: httpx.AsyncClient):
        """POST /api/voice で text_to_speech アクションがモックTTSで200が返る"""
        mock_tts_result = {
            "success": True,
            "audioResponse": "base64encodedaudio==",
            "emotion": "neutral",
        }

        mock_voice_agent = MagicMock()
        mock_voice_agent.text_to_speech = AsyncMock(return_value=mock_tts_result)

        with patch.object(main_mod, "_get_voice_agent", return_value=mock_voice_agent):
            response = await client.post(
                "/api/voice",
                headers=VALID_API_HEADERS,
                json={
                    "action": "text_to_speech",
                    "text": "こんにちは",
                    "language": "ja",
                },
            )

        # モックTTS使用時に200が返ること
        assert response.status_code == 200
        body = response.json()
        # success フラグが True であること
        assert body["success"] is True
        # audioResponse が含まれること
        assert body.get("audioResponse") is not None

    async def test_voice_unknown_action_returns_400(self, client: httpx.AsyncClient):
        """POST /api/voice で不明なアクションだと400が返る"""
        response = await client.post(
            "/api/voice",
            headers=VALID_API_HEADERS,
            json={"action": "unknown_action"},
        )
        # 不明なアクションは400
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 5. /api/slides エンドポイント
# ---------------------------------------------------------------------------


class TestSlidesEndpoint:
    """スライドAPIエンドポイントの検証"""

    async def test_slides_without_auth_returns_403(self, client: httpx.AsyncClient):
        """POST /api/slides に認証なしでリクエストすると403が返る"""
        response = await client.post(
            "/api/slides",
            json={"action": "narrate"},
        )
        # 認証なしは403
        assert response.status_code == 403

    async def test_slides_narrate_with_mock_returns_200(self, client: httpx.AsyncClient):
        """POST /api/slides の narrate アクションがモックで200が返る"""
        mock_slide_result = {
            "answer": "このスライドはエンジニアカフェの紹介です。",
            "emotion": "neutral",
            "slideNumber": 1,
            "metadata": {"action": "narrate"},
        }

        mock_slide_agent = MagicMock()
        mock_slide_agent.handle_slide_action = AsyncMock(return_value=mock_slide_result)

        with patch.object(main_mod, "_get_slide_agent", return_value=mock_slide_agent):
            response = await client.post(
                "/api/slides",
                headers=VALID_API_HEADERS,
                json={"action": "narrate", "language": "ja"},
            )

        # narrate アクションで200が返ること
        assert response.status_code == 200
        body = response.json()
        # success フラグが True であること
        assert body["success"] is True

    async def test_slides_unknown_action_returns_400(self, client: httpx.AsyncClient):
        """POST /api/slides で不明なアクションだと400が返る"""
        response = await client.post(
            "/api/slides",
            headers=VALID_API_HEADERS,
            json={"action": "invalid_action"},
        )
        # 不明なアクションは400
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 6. /api/character エンドポイント
# ---------------------------------------------------------------------------


class TestCharacterEndpoint:
    """キャラクター制御APIエンドポイントの検証"""

    async def test_character_without_auth_returns_403(self, client: httpx.AsyncClient):
        """POST /api/character に認証なしでリクエストすると403が返る"""
        response = await client.post(
            "/api/character",
            json={"action": "set_emotion", "emotion": "happy"},
        )
        # 認証なしは403
        assert response.status_code == 403

    async def test_character_with_valid_emotion_returns_200(self, client: httpx.AsyncClient):
        """POST /api/character に有効な emotion でモック使用時に200が返る"""
        mock_result = {
            "name": "idle",
            "duration": 2000,
            "keyframes": [{"time": 0, "bones": {}, "expressions": {"happy": 1.0}}],
            "text": None,
        }

        # CharacterControlAgent は character_api 内で遅延importされるため、ソースモジュールでパッチ
        with patch("backend.agents.character_control_agent.CharacterControlAgent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.process = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_instance

            response = await client.post(
                "/api/character",
                headers=VALID_API_HEADERS,
                json={"action": "set_emotion", "emotion": "happy"},
            )

        # 有効な emotion で200が返ること
        assert response.status_code == 200
        body = response.json()
        # success フラグが True であること
        assert body["success"] is True
        # message フィールドが含まれること
        assert "message" in body


# ---------------------------------------------------------------------------
# 7. ミドルウェア検証
# ---------------------------------------------------------------------------


class TestMiddleware:
    """ミドルウェアの動作検証"""

    async def test_request_id_echoed(self, client: httpx.AsyncClient):
        """クライアントから送信した X-Request-ID がレスポンスにエコーされること"""
        custom_id = "test-request-id-12345"
        response = await client.get("/health", headers={"X-Request-ID": custom_id})
        # ステータスコード200
        assert response.status_code == 200
        returned_id = response.headers.get("x-request-id", "")
        # 送信したリクエストIDがエコーされること
        assert (
            returned_id == custom_id
        ), f"X-Request-ID がエコーされていない: 期待={custom_id}, 実際={returned_id}"

    async def test_request_id_generated_when_not_provided(self, client: httpx.AsyncClient):
        """X-Request-ID を送信しない場合、サーバーが自動生成すること"""
        response = await client.get("/health")
        assert response.status_code == 200
        generated_id = response.headers.get("x-request-id", "")
        # 自動生成されたリクエストIDが空でないこと
        assert generated_id, "X-Request-ID がレスポンスに含まれていない"

    async def test_response_time_header_present(self, client: httpx.AsyncClient):
        """X-Response-Time-Ms ヘッダーがレスポンスに含まれること"""
        response = await client.get("/health")
        assert response.status_code == 200
        raw = response.headers.get("x-response-time-ms", "")
        # ヘッダーが存在すること
        assert raw, "X-Response-Time-Ms ヘッダーが見つからない"
        # 数値として解析可能であること
        duration = float(raw)
        assert duration >= 0, f"レスポンスタイムが負の値: {duration}"

    async def test_cors_headers_on_preflight(self, client: httpx.AsyncClient):
        """OPTIONS リクエストで CORS ヘッダーが設定されること"""
        production_origin = "https://engineer-cafe-navigator.company-997.workers.dev"
        response = await client.options(
            "/api/chat",
            headers={
                "Origin": production_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, X-API-Key",
            },
        )
        # CORS プリフライトが200を返すこと
        assert response.status_code == 200
        # Access-Control-Allow-Origin ヘッダーが含まれること
        assert (
            "access-control-allow-origin" in response.headers
        ), "CORS Access-Control-Allow-Origin ヘッダーが見つからない"

    async def test_cors_allows_configured_origin(self, client: httpx.AsyncClient):
        """設定済みのオリジンが CORS で許可されること"""
        production_origin = "https://engineer-cafe-navigator.company-997.workers.dev"
        response = await client.options(
            "/api/chat",
            headers={
                "Origin": production_origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        allowed_origin = response.headers.get("access-control-allow-origin", "")
        # 本番オリジンがデフォルトで許可されていること
        assert allowed_origin == production_origin, f"許可オリジンが期待と異なる: {allowed_origin}"


# ---------------------------------------------------------------------------
# 8. エラーハンドリング検証
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """エラーハンドリングの検証"""

    async def test_invalid_json_body_returns_422(self, client: httpx.AsyncClient):
        """不正なJSONボディで422が返ること"""
        response = await client.post(
            "/api/chat",
            headers={**VALID_API_HEADERS, "Content-Type": "application/json"},
            content=b"{invalid json",
        )
        # 不正なJSONは422
        assert response.status_code == 422

    async def test_wrong_content_type_returns_422(self, client: httpx.AsyncClient):
        """Content-Type が application/json でない場合に422が返ること"""
        response = await client.post(
            "/api/chat",
            headers={**VALID_API_HEADERS, "Content-Type": "text/plain"},
            content=b"plain text body",
        )
        # 不正なContent-Typeは422
        assert response.status_code == 422

    async def test_workflow_exception_returns_500(self, client: httpx.AsyncClient):
        """ワークフローが例外を投げた場合に500が返ること"""
        with patch.object(
            main_mod, "_run_workflow_with_tracking", new_callable=AsyncMock
        ) as mock_wf:
            mock_wf.side_effect = RuntimeError("Unexpected workflow error")
            response = await client.post(
                "/api/chat",
                headers=VALID_API_HEADERS,
                json={"query": "test", "session_id": "test-error"},
            )

        # 内部エラーで500が返ること
        assert response.status_code == 500
        body = response.json()
        # エラー詳細に内部情報が漏洩しないこと
        assert "Unexpected workflow error" not in body.get(
            "detail", ""
        ), "内部エラーメッセージがレスポンスに漏洩している"
