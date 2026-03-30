"""
EventAgent用プロンプトテンプレート

イベント情報クエリに対するプロンプト構築ロジックと時間範囲ラベルを集約。
"""

from typing import Dict

from backend.utils.language_types import LANGUAGE_INSTRUCTION

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

    oral_instruction_ja = (
        "回答は口語（話し言葉）で返してください。"
        "Markdownの見出し・箇条書き・太字・表などは使わないでください。"
        "音声で読み上げた時に自然に聞こえるような文章にしてください。"
    )
    oral_instruction_en = (
        "Respond in natural spoken language. "
        "Do NOT use Markdown formatting such as "
        "headers, bullet points, bold, or tables. "
        "Write as if speaking aloud to someone."
    )

    # Multilingual: append language instruction for zh/ko
    lang_suffix = LANGUAGE_INSTRUCTION.get(language, "")

    if language == "en":
        prompt = f"""Based on the following event information \
for {time_range_text}, answer the question.

Question: {query}

Events {time_range_text}:
{events_text}

Provide a brief and friendly summary of the events. Start your response with [happy] emotion tag.
Maximum 2-3 sentences.
{oral_instruction_en}"""
        if lang_suffix:
            prompt += f"\n{lang_suffix}"
        return prompt
    else:
        prompt = f"""{time_range_text}のイベント情報に基づいて、質問に答えてください。

質問: {query}

{time_range_text}のイベント:
{events_text}

イベントについて簡潔でフレンドリーな説明を提供してください。[happy]の感情タグで回答を始めてください。
最大2-3文。
{oral_instruction_ja}"""
        if lang_suffix:
            prompt += f"\n{lang_suffix}"
        return prompt
