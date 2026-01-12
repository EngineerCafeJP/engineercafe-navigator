"""
テストヘルパー関数

エージェントテストで使用する共通のヘルパー関数を提供します。
"""

from typing import Dict, Any, Optional


def create_mock_agent_response(
    answer: str = "テスト回答", emotion: str = "neutral", metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    モックエージェントレスポンスを作成

    Args:
        answer: 回答テキスト
        emotion: 感情タグ
        metadata: メタデータ

    Returns:
        Dict[str, Any]: エージェントレスポンス
    """
    if metadata is None:
        metadata = {}

    return {"answer": answer, "emotion": emotion, "metadata": {**metadata, "test": True}}


def create_mock_route_result(
    agent: str = "business_info", confidence: float = 0.95, reasoning: str = "テストルーティング"
) -> Dict[str, Any]:
    """
    モックルーティング結果を作成

    Args:
        agent: ルーティング先エージェント名
        confidence: 信頼度スコア
        reasoning: ルーティング理由

    Returns:
        Dict[str, Any]: ルーティング結果
    """
    return {"agent": agent, "confidence": confidence, "reasoning": reasoning}


def create_mock_memory_context(
    recent_messages: Optional[list] = None, context_string: str = ""
) -> Dict[str, Any]:
    """
    モックメモリコンテキストを作成

    Args:
        recent_messages: 最近のメッセージリスト
        context_string: コンテキスト文字列

    Returns:
        Dict[str, Any]: メモリコンテキスト
    """
    if recent_messages is None:
        recent_messages = []

    return {
        "recent_messages": recent_messages,
        "context_string": context_string,
        "total_messages": len(recent_messages),
    }


def assert_agent_response(response: Dict[str, Any], expected_keys: Optional[list] = None):
    """
    エージェントレスポンスの基本構造をアサート

    Args:
        response: エージェントレスポンス
        expected_keys: 期待されるキーのリスト（デフォルト: ["answer", "emotion", "metadata"]）
    """
    if expected_keys is None:
        expected_keys = ["answer", "emotion", "metadata"]

    for key in expected_keys:
        assert key in response, f"Response should contain '{key}'"


def assert_route_result(
    result: Dict[str, Any], expected_agent: Optional[str] = None, min_confidence: float = 0.0
):
    """
    ルーティング結果をアサート

    Args:
        result: ルーティング結果
        expected_agent: 期待されるエージェント名（Noneの場合はチェックスキップ）
        min_confidence: 最小信頼度スコア
    """
    # 基本構造の確認
    assert "agent" in result, "Route result should contain 'agent'"
    assert "confidence" in result, "Route result should contain 'confidence'"

    # エージェント名の確認
    if expected_agent is not None:
        assert (
            result["agent"] == expected_agent
        ), f"Expected agent '{expected_agent}' but got '{result['agent']}'"

    # 信頼度の確認
    assert (
        result["confidence"] >= min_confidence
    ), f"Confidence {result['confidence']} is below minimum {min_confidence}"


def create_test_query(query_type: str = "hours", language: str = "ja") -> str:
    """
    テスト用のクエリを生成

    Args:
        query_type: クエリタイプ（hours, price, location, etc.）
        language: 言語（ja or en）

    Returns:
        str: テスト用クエリ
    """
    queries = {
        "hours": {"ja": "営業時間を教えてください", "en": "What are your business hours?"},
        "price": {"ja": "料金はいくらですか？", "en": "How much does it cost?"},
        "location": {"ja": "場所はどこですか？", "en": "Where is it located?"},
        "facility": {"ja": "Wi-Fiはありますか？", "en": "Do you have Wi-Fi?"},
        "memory": {"ja": "さっき何を聞いた？", "en": "What did I ask before?"},
    }

    return queries.get(query_type, {}).get(language, "テストクエリ")
