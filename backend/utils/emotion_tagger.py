"""
EmotionTagger - メッセージに感情タグを付与するユーティリティ

clarification templates などで使用される、シンプルな感情タグ付与機能。
フロントエンドの EmotionTagger の Python 版。

参考:
- docs/migration/agents/clarification-agent/MIGRATION-GUIDE.md
- frontend/src/lib/emotion-tagger.ts (Mastra版)
"""


def add_emotion_tag(message: str, emotion: str) -> str:
    """
    メッセージ先頭に感情タグを付与する

    Args:
        message: 元のメッセージ
        emotion: 感情名（'surprised', 'happy', 'sad', 'angry', 'relaxed' など）

    Returns:
        感情タグ付きメッセージ（例: "[surprised]お手伝いさせていただきます！..."）

    Examples:
        >>> add_emotion_tag("こんにちは", "happy")
        '[happy]こんにちは'

        >>> add_emotion_tag("どちらについてお聞きでしょうか？", "surprised")
        '[surprised]どちらについてお聞きでしょうか？'
    """
    return f"[{emotion}]{message}"
