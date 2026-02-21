"""
EventAgent用プロンプトテンプレート

イベント情報クエリに対するプロンプト構築ロジックと時間範囲ラベルを集約。
"""

from typing import Dict

# 時間範囲ラベル
TIME_RANGE_LABELS: Dict[str, Dict[str, str]] = {
    "today": {"ja": "本日", "en": "today"},
    "thisWeek": {"ja": "今週", "en": "this week"},
    "nextWeek": {"ja": "来週", "en": "next week"},
    "thisMonth": {"ja": "今月", "en": "this month"},
}


def get_time_range_label(time_range: str, language: str) -> str:
    """時間範囲ラベルを取得"""
    labels = TIME_RANGE_LABELS.get(time_range, TIME_RANGE_LABELS["thisWeek"])
    return labels.get(language, labels.get("ja", "今週"))


def build_event_prompt(query: str, events_text: str, time_range: str, language: str) -> str:
    """イベント情報のプロンプトを構築

    Args:
        query: ユーザークエリ
        events_text: 整形済みイベント情報
        time_range: 時間範囲
        language: 言語（ja or en）

    Returns:
        構築されたプロンプト
    """
    time_range_text = get_time_range_label(time_range, language)

    if language == "en":
        return f"""Based on the following event information for {time_range_text}, answer the question.

Question: {query}

Events {time_range_text}:
{events_text}

Provide a brief and friendly summary of the events. Start your response with [happy] emotion tag.
Maximum 2-3 sentences."""
    else:
        return f"""{time_range_text}のイベント情報に基づいて、質問に答えてください。

質問: {query}

{time_range_text}のイベント:
{events_text}

イベントについて簡潔でフレンドリーな説明を提供してください。[happy]の感情タグで回答を始めてください。
最大2-3文。"""
