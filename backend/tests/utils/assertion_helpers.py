"""
カスタムアサート関数

テストで使用するカスタムアサート関数を提供します。
"""

from typing import Dict, Any, Optional, List


def assert_emotion_tag(emotion: str, valid_emotions: Optional[List[str]] = None):
    """
    感情タグの妥当性をアサート

    Args:
        emotion: 感情タグ
        valid_emotions: 有効な感情タグのリスト
    """
    if valid_emotions is None:
        valid_emotions = ["neutral", "happy", "sad", "surprised", "relaxed", "angry"]

    assert (
        emotion in valid_emotions
    ), f"Invalid emotion '{emotion}'. Must be one of {valid_emotions}"


def assert_response_structure(
    response: Dict[str, Any],
    required_keys: Optional[List[str]] = None,
    optional_keys: Optional[List[str]] = None,
):
    """
    レスポンス構造の妥当性をアサート

    Args:
        response: レスポンス辞書
        required_keys: 必須キーのリスト
        optional_keys: オプショナルキーのリスト
    """
    if required_keys is None:
        required_keys = ["answer", "emotion", "metadata"]

    # 必須キーのチェック
    for key in required_keys:
        assert key in response, f"Response must contain '{key}'"

    # 型チェック
    assert isinstance(response["answer"], str), "answer must be a string"
    assert isinstance(response["emotion"], str), "emotion must be a string"
    assert isinstance(response["metadata"], dict), "metadata must be a dict"

    # 感情タグの妥当性チェック
    assert_emotion_tag(response["emotion"])

    # オプショナルキーのチェック
    if optional_keys:
        for key in optional_keys:
            if key in response:
                # オプショナルキーが存在する場合、型を確認
                pass  # 型チェックは必要に応じて追加


def assert_confidence_score(confidence: float, min_score: float = 0.0, max_score: float = 1.0):
    """
    信頼度スコアの妥当性をアサート

    Args:
        confidence: 信頼度スコア
        min_score: 最小スコア
        max_score: 最大スコア
    """
    assert isinstance(confidence, (int, float)), "confidence must be a number"
    assert (
        min_score <= confidence <= max_score
    ), f"confidence {confidence} must be between {min_score} and {max_score}"


def assert_routing_result(
    result: Dict[str, Any], expected_agent: Optional[str] = None, min_confidence: float = 0.0
):
    """
    ルーティング結果の妥当性をアサート

    Args:
        result: ルーティング結果
        expected_agent: 期待されるエージェント名
        min_confidence: 最小信頼度
    """
    # 基本構造
    assert "agent" in result, "Routing result must contain 'agent'"
    assert "confidence" in result, "Routing result must contain 'confidence'"

    # エージェント名
    if expected_agent:
        assert (
            result["agent"] == expected_agent
        ), f"Expected agent '{expected_agent}' but got '{result['agent']}'"

    # 信頼度
    assert_confidence_score(result["confidence"], min_confidence)


def assert_memory_context(
    context: Dict[str, Any], min_messages: int = 0, max_messages: Optional[int] = None
):
    """
    メモリコンテキストの妥当性をアサート

    Args:
        context: メモリコンテキスト
        min_messages: 最小メッセージ数
        max_messages: 最大メッセージ数
    """
    # 基本構造
    assert "recent_messages" in context, "Context must contain 'recent_messages'"
    assert isinstance(context["recent_messages"], list), "recent_messages must be a list"

    # メッセージ数
    message_count = len(context["recent_messages"])
    assert (
        message_count >= min_messages
    ), f"Message count {message_count} is below minimum {min_messages}"

    if max_messages is not None:
        assert (
            message_count <= max_messages
        ), f"Message count {message_count} exceeds maximum {max_messages}"


def assert_metadata_contains(metadata: Dict[str, Any], required_fields: List[str]):
    """
    メタデータに必要なフィールドが含まれることをアサート

    Args:
        metadata: メタデータ辞書
        required_fields: 必須フィールドのリスト
    """
    assert isinstance(metadata, dict), "metadata must be a dict"

    for field in required_fields:
        assert field in metadata, f"metadata must contain '{field}'"


def assert_error_response(response: Dict[str, Any], expected_error_status: Optional[str] = None):
    """
    エラーレスポンスの妥当性をアサート

    Args:
        response: エラーレスポンス
        expected_error_status: 期待されるエラーステータス
    """
    # 基本構造
    assert "metadata" in response, "Error response must contain 'metadata'"
    assert (
        "status" in response["metadata"] or "error" in response["metadata"]
    ), "Error response metadata must contain 'status' or 'error'"

    # エラーステータス
    if expected_error_status:
        actual_status = response["metadata"].get("status") or response["metadata"].get("error")
        assert (
            actual_status == expected_error_status
        ), f"Expected error status '{expected_error_status}' but got '{actual_status}'"


def assert_no_pii(text: str):
    """
    テキストに個人情報（PII）が含まれていないことをアサート

    Args:
        text: チェックするテキスト
    """
    # 簡易的なPIIチェック（実際の実装ではより厳密なチェックが必要）
    pii_patterns = [
        r"\d{3}-\d{4}-\d{4}",  # 電話番号
        r"\d{7}",  # 郵便番号
        r"test-key",  # テストキー
    ]

    import re

    for pattern in pii_patterns:
        assert not re.search(
            pattern, text
        ), f"Text should not contain PII matching pattern '{pattern}'"
