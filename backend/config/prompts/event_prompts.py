"""
EventAgent用プロンプトテンプレート

イベント情報クエリに対するプロンプト構築ロジックと時間範囲ラベルを集約。
"""

from typing import Dict

from backend.utils.language_types import get_language_instruction
from backend.utils.time_utils import get_now_jst

# 時間範囲ラベル
TIME_RANGE_LABELS: Dict[str, Dict[str, str]] = {
    "today": {"ja": "本日", "en": "today", "zh": "今天", "ko": "오늘"},
    "tomorrow": {"ja": "明日", "en": "tomorrow", "zh": "明天", "ko": "내일"},
    "thisWeek": {"ja": "今週", "en": "this week", "zh": "本周", "ko": "이번 주"},
    "nextWeek": {"ja": "来週", "en": "next week", "zh": "下周", "ko": "다음 주"},
    "thisMonth": {"ja": "今月", "en": "this month", "zh": "本月", "ko": "이번 달"},
}


def get_time_range_label(time_range: str, language: str) -> str:
    """時間範囲ラベルを取得"""
    labels = TIME_RANGE_LABELS.get(time_range, TIME_RANGE_LABELS["thisWeek"])
    return labels.get(language, labels.get("ja", "今週"))


def build_range_interpretation_rule(language: str) -> str:
    """Return the JST date-range rule that the LLM must preserve."""

    now = get_now_jst()
    current = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    if language == "en":
        return (
            f"Range interpretation rule (JST, current datetime: {current}): "
            "today = today 00:00 through before tomorrow 00:00; "
            "tomorrow = tomorrow 00:00 through before the day after tomorrow 00:00; "
            "this week = today through the end of the current week, excluding past days; "
            "this month = today through the end of the current month, excluding past days; "
            "next week = next Monday through next Sunday."
        )

    return (
        f"範囲解釈ルール（JST基準、現在日時: {current}）: "
        "「今日」は本日00:00から翌日00:00未満、"
        "「明日」は翌日00:00から翌々日00:00未満、"
        "「今週」は本日から今週末までで過去日は含めない、"
        "「今月」は本日から今月末までで過去日は含めない、"
        "「来週」は来週の月曜から日曜までとして扱ってください。"
    )


def build_event_prompt(query: str, events_text: str, time_range: str, language: str) -> str:
    """イベント情報のプロンプトを構築

    Args:
        query: ユーザークエリ
        events_text: 整形済みイベント情報
        time_range: 時間範囲
        language: 言語（ja or en）

    Returns:
        構築されたプロンプト

    Notes:
        Issue #509: the prompt enforces STRICT grounding — the LLM must
        only reference events in ``events_text`` and must not invent or
        predict events. When ``events_text`` is empty, the LLM must say
        there are no events (with the ``[sad]`` emotion tag) instead of
        fabricating entries.
    """
    time_range_text = get_time_range_label(time_range, language)
    has_events = bool(events_text.strip())
    range_rule = build_range_interpretation_rule(language)

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

    # STRICT grounding rules (Issue #509).
    grounding_rule_ja = (
        "【重要・厳守】以下に記載されているイベントだけを使って答えてください。"
        "リストに載っていないイベントは絶対に作り出さない・予測しないこと。"
        "具体的な日付・イベント名・講師名などをでっち上げてはいけません。"
        f"もしリストが空の場合は、『{time_range_text}には登録されているイベントはありません』"
        "と正直に答え、回答は必ず[sad]の感情タグで始めてください。"
        "イベントがある場合のみ[happy]の感情タグで始めてください。"
    )
    grounding_rule_en = (
        "[STRICT RULE] You must use ONLY the events listed below. "
        "Do not invent, predict, or fabricate events, dates, names, "
        "or speakers that are not in the list. "
        f"If the list is empty, answer honestly with "
        f"'There are no scheduled events for {time_range_text}.' "
        "and start your response with the [sad] emotion tag. "
        "Use the [happy] emotion tag only when events are present."
    )

    emotion_hint_ja = "[happy]" if has_events else "[sad]"
    emotion_hint_en = "[happy]" if has_events else "[sad]"

    # Multilingual: append language instruction for zh/ko
    lang_suffix = get_language_instruction(language)

    if language == "en":
        prompt = f"""Answer the question using the event information for {time_range_text} below.

{grounding_rule_en}

{range_rule}

Question: {query}

Events {time_range_text}:
{events_text if has_events else "(no events)"}

Provide a brief and friendly summary of the events. \
Start your response with the {emotion_hint_en} emotion tag.
Maximum 2-3 sentences.
{oral_instruction_en}"""
        if lang_suffix:
            prompt += f"\n{lang_suffix}"
        return prompt
    else:
        prompt = f"""{time_range_text}のイベント情報に基づいて、質問に答えてください。

{grounding_rule_ja}

{range_rule}

質問: {query}

{time_range_text}のイベント:
{events_text if has_events else "(イベントなし)"}

イベントについて簡潔でフレンドリーな説明を提供してください。\
{emotion_hint_ja}の感情タグで回答を始めてください。
最大2-3文。
{oral_instruction_ja}"""
        if lang_suffix:
            prompt += f"\n{lang_suffix}"
        return prompt
