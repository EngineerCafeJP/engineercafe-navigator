"""STT Custom Vocabulary API Tests"""

import base64
import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.stt_vocabulary import router as stt_vocabulary_router

_test_app = FastAPI()
_test_app.include_router(stt_vocabulary_router, prefix="/api")
client = TestClient(_test_app)


# =============================================================================
# Fixtures / helpers
# =============================================================================

SAMPLE_VOCABULARY = [
    {
        "id": "a1b2c3d4-0001-0000-0000-000000000001",
        "word": "エンジニアカフェ",
        "reading": "えんじにあかふぇ",
        "category": "facility",
        "priority": 10,
        "created_at": "2026-02-19T00:00:00Z",
        "updated_at": "2026-02-19T00:00:00Z",
    },
    {
        "id": "a1b2c3d4-0001-0000-0000-000000000002",
        "word": "博多",
        "reading": "はかた",
        "category": "location",
        "priority": 8,
        "created_at": "2026-02-19T00:00:00Z",
        "updated_at": "2026-02-19T00:00:00Z",
    },
]


def _make_wav_base64() -> str:
    """テスト用のダミーWAVをbase64エンコードして返す（無音16kHz）"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)  # 0.1秒分の無音
    return base64.b64encode(buf.getvalue()).decode()


# =============================================================================
# GET /api/stt/vocabulary
# =============================================================================


@patch("api.stt_vocabulary._load_vocabulary")
def test_list_vocabulary_all(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.get("/api/stt/vocabulary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total"] == 2
    assert len(body["data"]) == 2


@patch("api.stt_vocabulary._load_vocabulary")
def test_list_vocabulary_filter_by_category(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.get("/api/stt/vocabulary?category=facility")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["word"] == "エンジニアカフェ"


@patch("api.stt_vocabulary._load_vocabulary")
def test_list_vocabulary_invalid_category(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.get("/api/stt/vocabulary?category=invalid")
    assert resp.status_code == 422


# =============================================================================
# POST /api/stt/vocabulary
# =============================================================================


@patch("api.stt_vocabulary._save_vocabulary")
@patch("api.stt_vocabulary._load_vocabulary")
def test_create_vocabulary(mock_load, mock_save):
    mock_load.return_value = []
    mock_save.return_value = None

    resp = client.post(
        "/api/stt/vocabulary",
        json={
            "word": "コワーキング",
            "reading": "こわーきんぐ",
            "category": "service",
            "priority": 7,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["word"] == "コワーキング"
    assert body["data"]["category"] == "service"
    assert "id" in body["data"]
    mock_save.assert_called_once()


@patch("api.stt_vocabulary._load_vocabulary")
def test_create_vocabulary_duplicate(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.post(
        "/api/stt/vocabulary",
        json={
            "word": "エンジニアカフェ",
            "reading": "えんじにあかふぇ",
            "category": "facility",
        },
    )
    assert resp.status_code == 409


@patch("api.stt_vocabulary._load_vocabulary")
def test_create_vocabulary_missing_fields(mock_load):
    mock_load.return_value = []
    resp = client.post(
        "/api/stt/vocabulary",
        json={"word": "テスト"},  # reading, category が欠落
    )
    assert resp.status_code == 422


# =============================================================================
# PUT /api/stt/vocabulary/{id}
# =============================================================================


@patch("api.stt_vocabulary._save_vocabulary")
@patch("api.stt_vocabulary._load_vocabulary")
def test_update_vocabulary(mock_load, mock_save):
    mock_load.return_value = [dict(SAMPLE_VOCABULARY[0])]
    mock_save.return_value = None

    target_id = SAMPLE_VOCABULARY[0]["id"]
    resp = client.put(
        f"/api/stt/vocabulary/{target_id}",
        json={"priority": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["priority"] == 5
    mock_save.assert_called_once()


@patch("api.stt_vocabulary._load_vocabulary")
def test_update_vocabulary_not_found(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.put(
        "/api/stt/vocabulary/nonexistent-id",
        json={"priority": 5},
    )
    assert resp.status_code == 404


@patch("api.stt_vocabulary._save_vocabulary")
@patch("api.stt_vocabulary._load_vocabulary")
def test_update_vocabulary_duplicate_word(mock_load, mock_save):
    mock_load.return_value = list(SAMPLE_VOCABULARY)
    target_id = SAMPLE_VOCABULARY[0]["id"]
    resp = client.put(
        f"/api/stt/vocabulary/{target_id}",
        json={"word": "博多"},  # 既存の別エントリと重複
    )
    assert resp.status_code == 409


# =============================================================================
# DELETE /api/stt/vocabulary/{id}
# =============================================================================


@patch("api.stt_vocabulary._save_vocabulary")
@patch("api.stt_vocabulary._load_vocabulary")
def test_delete_vocabulary(mock_load, mock_save):
    mock_load.return_value = [dict(SAMPLE_VOCABULARY[0])]
    mock_save.return_value = None

    target_id = SAMPLE_VOCABULARY[0]["id"]
    resp = client.delete(f"/api/stt/vocabulary/{target_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["id"] == target_id
    mock_save.assert_called_once()


@patch("api.stt_vocabulary._load_vocabulary")
def test_delete_vocabulary_not_found(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.delete("/api/stt/vocabulary/nonexistent-id")
    assert resp.status_code == 404


# =============================================================================
# POST /api/stt/vocabulary/test
# =============================================================================


@patch("api.stt_vocabulary._load_vocabulary")
def test_test_vocabulary_invalid_base64(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    resp = client.post(
        "/api/stt/vocabulary/test",
        json={"audio_base64": "!!!not-valid-base64!!!"},
    )
    assert resp.status_code == 400


@patch("api.stt_vocabulary._load_vocabulary")
def test_test_vocabulary_stt_error_returns_success_false(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    wav_b64 = _make_wav_base64()

    with patch("api.stt_vocabulary.LocalSTTClient") as MockClient:
        instance = MagicMock()
        instance.transcribe = AsyncMock(side_effect=RuntimeError("Vosk model not found"))
        MockClient.return_value = instance

        resp = client.post(
            "/api/stt/vocabulary/test",
            json={"audio_base64": wav_b64, "language": "ja"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "error" in body
    assert "[unk]" in body["grammar_words"]


@patch("api.stt_vocabulary._load_vocabulary")
def test_test_vocabulary_success(mock_load):
    mock_load.return_value = SAMPLE_VOCABULARY
    wav_b64 = _make_wav_base64()

    mock_result = MagicMock()
    mock_result.text = "エンジニアカフェ"

    with patch("api.stt_vocabulary.LocalSTTClient") as MockClient:
        instance = MagicMock()
        instance.transcribe = AsyncMock(return_value=mock_result)
        MockClient.return_value = instance

        resp = client.post(
            "/api/stt/vocabulary/test",
            json={"audio_base64": wav_b64, "language": "ja", "category": "facility"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["transcript"] == "エンジニアカフェ"
    assert "エンジニアカフェ" in body["grammar_words"]
    assert "[unk]" in body["grammar_words"]


# =============================================================================
# build_grammar_words helper
# =============================================================================


def test_build_grammar_words_all():
    from api.stt_vocabulary import build_grammar_words

    words = build_grammar_words(SAMPLE_VOCABULARY)
    assert "エンジニアカフェ" in words
    assert "博多" in words
    assert "[unk]" in words
    assert words[-1] == "[unk]"


def test_build_grammar_words_with_category():
    from api.stt_vocabulary import build_grammar_words

    words = build_grammar_words(SAMPLE_VOCABULARY, category="facility")
    assert "エンジニアカフェ" in words
    assert "博多" not in words
    assert "[unk]" in words


def test_build_grammar_words_priority_order():
    from api.stt_vocabulary import build_grammar_words

    words = build_grammar_words(SAMPLE_VOCABULARY)
    # priority=10 のエンジニアカフェが priority=8 の博多より前
    idx_ec = words.index("エンジニアカフェ")
    idx_hk = words.index("博多")
    assert idx_ec < idx_hk
