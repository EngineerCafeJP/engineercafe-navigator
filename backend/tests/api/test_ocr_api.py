"""OCR API のユニットテスト。

テスト対象: backend/api/ocr.py
カバレッジ:
  - helper 関数 (_decode_image, _detect_language, _estimate_confidence)
  - 会員番号抽出用の正規表現
  - POST /api/ocr エンドポイント
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.api.ocr as ocr_module
import backend.main as main_module
from backend.main import app

client = TestClient(app)

VALID_JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3O"
    "Dk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6"
    "ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEB"
    "AQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJB"
    "UQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVV"
    "ldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6ws"
    "PExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z"
)


@pytest.fixture(autouse=True)
def reset_ocr_state(monkeypatch: pytest.MonkeyPatch):
    """OCR API のモジュール状態を各テスト前後で初期化する。"""
    ocr_module._vision_agent = None
    ocr_module._visitor_id_service = None
    monkeypatch.setattr(main_module, "_API_SECRET_KEY", None)
    yield
    ocr_module._vision_agent = None
    ocr_module._visitor_id_service = None


def _extract_member_number(text: str) -> int | None:
    """テスト用に正規表現マッチから会員番号を取り出す（context優先）。"""
    match = ocr_module._MEMBER_CONTEXT_RE.search(text)
    if not match:
        match = ocr_module._MEMBER_STANDALONE_RE.search(text)
    if match is None:
        return None
    return int(match.group(1))


class TestDecodeImage:
    """_decode_image のテスト。"""

    def test_returns_ndarray_for_valid_base64_jpeg(self):
        """有効な base64 JPEG から ndarray を返す。"""
        image = ocr_module._decode_image(VALID_JPEG_BASE64)

        assert isinstance(image, np.ndarray)
        assert image.shape == (2, 2, 3)
        assert image.dtype == np.uint8

    def test_strips_data_uri_prefix_before_decoding(self):
        """data URI prefix 付きでも正常にデコードできる。"""
        image = ocr_module._decode_image(f"data:image/jpeg;base64,{VALID_JPEG_BASE64}")

        assert isinstance(image, np.ndarray)
        assert image.shape == (2, 2, 3)

    def test_raises_400_for_invalid_base64(self):
        """不正な base64 文字列では 400 を返す。"""
        with pytest.raises(HTTPException) as exc_info:
            ocr_module._decode_image("%%%not-base64%%%")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid image data"

    def test_raises_400_for_non_image_payload(self):
        """画像ではない base64 ペイロードでは 400 を返す。"""
        non_image_payload = base64.b64encode(b"plain text").decode("utf-8")

        with pytest.raises(HTTPException) as exc_info:
            ocr_module._decode_image(non_image_payload)

        assert exc_info.value.status_code == 400
        assert "Could not decode image" in exc_info.value.detail

    def test_raises_400_for_empty_image_payload(self):
        """base64 デコード結果が空バイトの場合は 400 を返す。"""
        import base64 as _base64

        empty_payload = _base64.b64encode(b"").decode("utf-8")
        with pytest.raises(HTTPException) as exc_info:
            ocr_module._decode_image(empty_payload)
        assert exc_info.value.status_code == 400
        assert "Empty image data" in exc_info.value.detail


class TestDetectLanguage:
    """_detect_language のテスト。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("こんにちはカフェ", "ja"),
            ("안녕하세요", "ko"),
            ("Engineer Cafe reception 2025", "en"),
            ("福岡天神", "ja"),
            ("", None),
        ],
    )
    def test_detects_expected_language(self, text: str, expected: str | None):
        """文字種のヒューリスティックで言語を判定する。"""
        assert ocr_module._detect_language(text) == expected

    def test_returns_none_for_none_input(self):
        """None 入力では None を返す。"""
        assert ocr_module._detect_language(None) is None  # type: ignore[arg-type]


class TestEstimateConfidence:
    """_estimate_confidence のテスト。"""

    def test_returns_0_7_for_successful_text_with_reasonable_length(self):
        """テキスト成功かつ妥当な長さなら 0.7 を返す。"""
        confidence = ocr_module._estimate_confidence({"success": True, "text": "hello"}, {})

        assert confidence == 0.7

    def test_returns_1_0_when_member_number_is_found(self):
        """会員番号が見つかった場合は 1.0 を返す。"""
        confidence = ocr_module._estimate_confidence(
            {"success": True, "text": "会員番号123"},
            {},
            member_number_found=True,
        )

        assert confidence == 1.0

    def test_returns_0_0_when_text_recognition_failed(self):
        """テキスト認識に失敗した場合は 0.0 を返す。"""
        confidence = ocr_module._estimate_confidence({"success": False, "text": ""}, {})

        assert confidence == 0.0

    def test_returns_0_1_for_face_detection_only(self):
        """顔検出だけ成功した場合は 0.1 を返す。"""
        confidence = ocr_module._estimate_confidence(
            {"success": False, "text": ""},
            {"detected": True},
        )

        assert confidence == 0.1


class TestMemberNumberRegex:
    """_MEMBER_CONTEXT_RE / _MEMBER_STANDALONE_RE のテスト。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("会員番号123", 123),
            ("No.456", 456),
            ("Member 789", 789),
            ("1234", 1234),
            ("12345", 12345),
            ("005544", 5544),
            ("会員番号123456", 123456),
        ],
    )
    def test_matches_supported_member_number_formats(self, text: str, expected: int):
        """対応フォーマットから会員番号を抽出できる。"""
        assert _extract_member_number(text) == expected

    def test_does_not_match_two_digit_standalone_number(self):
        """単独の 2 桁数字はフォールバック対象外とする。"""
        assert _extract_member_number("12") is None

    def test_does_not_match_seven_digit_standalone_number(self):
        """単独の 7 桁数字はフォールバック対象外とする。"""
        assert _extract_member_number("1234567") is None

    def test_context_match_takes_priority_over_earlier_standalone(self):
        """ラベル付き番号が standalone より後にあっても優先される。"""
        assert _extract_member_number("202503 会員番号1234") == 1234


class TestRecognizeImageEndpoint:
    """POST /api/ocr のテスト。"""

    @staticmethod
    def _post_ocr(image_data: str = "ignored", mode: str = "member_card") -> dict:
        """OCR API に対して POST を送る。"""
        response = client.post(
            "/api/ocr",
            json={"image_data": image_data, "mode": mode, "session_id": "sess-001"},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_returns_successful_response_on_happy_path(self):
        """VisionAgent の成功結果を正常レスポンスへ変換する。"""
        decoded_image = np.zeros((4, 4, 3), dtype=np.uint8)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            return_value={
                "text": {"success": True, "text": "plain text"},
                "face": {"detected": True, "expression": "happy"},
            }
        )

        with (
            patch.object(ocr_module, "_decode_image", return_value=decoded_image),
            patch.object(ocr_module, "_get_vision_agent", return_value=mock_agent),
        ):
            data = self._post_ocr(mode="member_card")

        assert data["success"] is True
        assert data["mode"] == "member_card"
        assert data["recognized_text"] == "plain text"
        assert data["expression"] == "happy"
        assert data["confidence"] == pytest.approx(0.8)
        assert data["member_number"] is None
        assert data["identity_lookup"] is None

        run_payload = mock_agent.run.await_args.args[0]
        assert run_payload["image"] is decoded_image
        assert run_payload["mode"] == "member_card"

    def test_returns_error_response_when_vision_agent_raises(self):
        """VisionAgent 例外時はエラーレスポンスを返す。"""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch.object(ocr_module, "_decode_image", return_value=np.zeros((2, 2, 3))),
            patch.object(ocr_module, "_get_vision_agent", return_value=mock_agent),
        ):
            data = self._post_ocr(mode="member_card")

        assert data["success"] is False
        assert data["mode"] == "member_card"
        assert data["error"] == "Vision processing failed"
        assert data["processing_time_ms"] >= 0

    def test_member_card_mode_extracts_member_number_without_identity_lookup(self):
        """member_card モードでは会員番号抽出のみを行う。"""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            return_value={
                "text": {"success": True, "text": "会員番号123"},
                "face": {"detected": False, "expression": {"emotion": "neutral"}},
            }
        )

        with (
            patch.object(ocr_module, "_decode_image", return_value=np.zeros((2, 2, 3))),
            patch.object(ocr_module, "_get_vision_agent", return_value=mock_agent),
        ):
            data = self._post_ocr(mode="member_card")

        assert data["success"] is True
        assert data["member_number"] == 123
        assert data["visitor_identity"] is None
        assert data["identity_lookup"] is None
        assert data["expression"] == "neutral"
        assert data["confidence"] == 1.0

    def test_handwriting_mode_detects_language(self):
        """handwriting モードでは言語推定結果を返す。"""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            return_value={
                "text": {"success": True, "text": "こんにちは"},
                "face": {"detected": False, "expression": None},
            }
        )

        with (
            patch.object(ocr_module, "_decode_image", return_value=np.zeros((2, 2, 3))),
            patch.object(ocr_module, "_get_vision_agent", return_value=mock_agent),
        ):
            data = self._post_ocr(mode="handwriting")

        assert data["success"] is True
        assert data["mode"] == "handwriting"
        assert data["recognized_text"] == "こんにちは"
        assert data["language"] == "ja"
        assert data["member_number"] is None
