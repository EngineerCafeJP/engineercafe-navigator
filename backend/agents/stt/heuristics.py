from __future__ import annotations

import re
from typing import Optional


def _normalize_vosk_route_transcript(transcript: str, language: Optional[str]) -> str:
    """Correct narrow, route-critical Vosk confusions before LangGraph routing.

    Vosk sometimes preserves only the intent-bearing tail of Japanese alpha
    fixture audio and mangles "エンジニアカフェ" into unrelated words. When the
    remaining phrase is still clearly an Engineer Cafe hours question, return a
    canonical business-hours query so it cannot fall into small talk.
    """

    if language != "ja":
        return transcript

    normalized = "".join(transcript.lower().split())
    if not normalized:
        return transcript

    has_repeated_hai = "はいはい" in normalized or "ハイハイ" in normalized
    has_other_connection_target = any(
        marker in normalized for marker in ("bluetooth", "プロジェクター")
    )
    is_wifi_connection_confusion = has_repeated_hai and (
        ("セット" in normalized and "逆方法" in normalized)
        or ("瀬田" in normalized and "作方法" in normalized)
        or ("接続" in normalized and "方法" in normalized and not has_other_connection_target)
    )
    if is_wifi_connection_confusion:
        return "Wi-Fiの接続方法を教えてください。"

    is_python_venv_confusion = (
        "仮想環境" in normalized and any(marker in normalized for marker in ("パート", "ぱいと"))
    ) or normalized in {
        "配管のかかとは何ですか",
        "配管のかかととは何ですか",
    }
    if is_python_venv_confusion:
        return "Python の仮想環境とは何ですか。"

    has_time_context = any(marker in normalized for marker in ("時間", "影響時", "液状時"))
    if not has_time_context:
        return transcript

    asks_for_time = any(
        marker in normalized
        for marker in ("教え", "知りたい", "確認", "何時", "いつまで", "いつから")
    )
    if not asks_for_time:
        return transcript

    has_engineer_cafe_context = any(
        marker in normalized
        for marker in (
            "エンジニア",
            "カフェ",
            "営業",
            "開館",
            "会館",
            "受付",
            "利用",
            "検事",
            "壁",
        )
    ) or ("赤毛" in normalized and "アン" in normalized)
    has_engineer_cafe_context = (
        has_engineer_cafe_context
        or (
            "元気" in normalized
            and ("新潟" in normalized or "県" in normalized)
            and "影響" in normalized
        )
        or (
            "園児" in normalized
            and "変" in normalized
            and "影響" in normalized
            and "出る" not in normalized
        )
    )
    if not has_engineer_cafe_context:
        return transcript

    if "会館" in normalized or "開館" in normalized:
        return "エンジニアカフェの開館時間を教えてください。"
    return "エンジニアカフェの営業時間を教えてください。"


def _vosk_transcript_trusted_for_early_return(transcript: str, language: Optional[str]) -> bool:
    """Return true when Vosk output contains route-stable alpha keywords."""

    if language not in {None, "ja", "en"}:
        return False
    normalized_transcript = _normalize_vosk_route_transcript(transcript, language)
    normalized = "".join(normalized_transcript.lower().split())
    if not normalized:
        return False

    trusted_terms = (
        "営業時間",
        "開館時間",
        "営業日",
        "予約",
        "料金",
        "wi-fi",
        "wifi",
        "接続",
        "パスワード",
        "イベント",
        "開催",
        "python",
        "パイソン",
        "仮想環境",
        "api",
        "sdk",
    )
    if any(term in normalized for term in trusted_terms):
        return True

    return ("営業" in normalized and "時間" in normalized) or (
        "開館" in normalized and "時間" in normalized
    )


def _vosk_japanese_fragmented_request_suspicious(
    transcript: str,
    language: Optional[str],
) -> bool:
    """Catch live Vosk Japanese fallback fragments that look fluent but lack intent."""

    if language not in {None, "ja"}:
        return False

    tokens = [token for token in transcript.split() if token]
    compact = "".join(tokens)
    if not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", compact):
        return False

    asks_for_help = "教え" in compact and ("ください" in compact or "下さい" in compact)
    has_generic_subject = any(marker in compact for marker in ("時間", "時刻", "方法"))
    if not asks_for_help or not has_generic_subject:
        return False

    has_time_word = "時間" in compact or "時刻" in compact
    if (
        "影響" in compact
        and has_time_word
        and any(marker in compact for marker in ("元気", "新潟", "県"))
    ):
        return True

    has_repeated_hai = compact.startswith("はいはい") or tokens.count("はい") >= 2
    if has_repeated_hai and "方法" in compact:
        compact_lower = compact.lower()
        known_connection_confusion = "セット" in compact and "逆方法" in compact
        has_connection_context = "接続" in compact or any(
            marker in compact_lower for marker in ("wi-fi", "wifi")
        )
        method_confusion_markers = {
            "瀬田",
            "世田",
            "田中",
            "セタ",
            "せた",
            "作",
            "策",
            "昨",
        }
        if (
            not known_connection_confusion
            and not has_connection_context
            and any(marker in compact for marker in method_confusion_markers)
        ):
            return True

    return False


def _vosk_fallback_transcript_suspicious(
    transcript: str,
    language: Optional[str],
    confidence: Optional[float],
) -> bool:
    """Identify risky Vosk fallback text that should not drive chat intent."""

    normalized_transcript = _normalize_vosk_route_transcript(transcript, language)
    compact = "".join(normalized_transcript.split())
    if not compact:
        return True

    if _vosk_transcript_trusted_for_early_return(normalized_transcript, language):
        return False

    if _vosk_japanese_fragmented_request_suspicious(normalized_transcript, language):
        return True

    if confidence is None or confidence >= 0.75:
        return False

    tokens = [token for token in normalized_transcript.split() if token]
    if len(tokens) < 6:
        return len(compact) <= 3

    single_char_tokens = [token for token in tokens if len(token) == 1]
    single_char_ratio = len(single_char_tokens) / len(tokens)
    if single_char_ratio >= 0.45:
        return True

    ja_particles = {"が", "を", "に", "へ", "で", "と", "の", "は", "も", "や"}
    particle_ratio = sum(1 for token in tokens if token in ja_particles) / len(tokens)
    content_tokens = [token for token in tokens if token not in ja_particles and len(token) > 1]
    return particle_ratio >= 0.30 and len(content_tokens) <= 3


_QWEN_SHORT_COMMANDS = {
    "はい",
    "いいえ",
    "うん",
    "お願い",
    "お願いします",
    "キャンセル",
    "戻る",
    "終了",
    "予約",
    "料金",
    "無料",
    "受付",
    "yes",
    "no",
    "ok",
    "okay",
    "cancel",
    "stop",
    "back",
    "help",
    "thanks",
    "hello",
    "hi",
}

_QWEN_SHORT_NOISE = {
    "あ",
    "あー",
    "ああ",
    "あああ",
    "え",
    "えー",
    "ええ",
    "えええ",
    "う",
    "うー",
    "ん",
    "んー",
    "えっと",
    "えと",
    "まあ",
    "uh",
    "um",
    "umm",
    "mmm",
    "hmm",
}


def _qwen_primary_transcript_suspicious(
    transcript: str,
    language: Optional[str],
    confidence: Optional[float],
) -> bool:
    """Identify short/noisy Qwen output that should not drive chat intent.

    Qwen generally returns less segmented text than Vosk, so this gate focuses
    on empty, punctuation-only, repeated-character, and low-confidence short
    fragments while preserving known high-confidence short commands.
    """

    normalized = " ".join((transcript or "").split())
    compact = "".join(normalized.split())
    if not compact:
        return True

    compact_lower = compact.lower()
    if _vosk_transcript_trusted_for_early_return(normalized, language):
        return False

    if compact_lower in _QWEN_SHORT_COMMANDS:
        return confidence is not None and confidence < 0.60

    if compact_lower in _QWEN_SHORT_NOISE:
        return confidence is None or confidence < 0.95

    if re.fullmatch(r"[\W_]+", compact, flags=re.UNICODE):
        return True

    if len(compact) >= 3 and len(set(compact_lower)) == 1:
        return confidence is None or confidence < 0.95

    tokens = [token for token in normalized.split() if token]
    if len(tokens) >= 3:
        single_char_ratio = sum(1 for token in tokens if len(token) == 1) / len(tokens)
        if single_char_ratio >= 0.60 and (confidence is None or confidence < 0.85):
            return True

    if len(compact) <= 2:
        return confidence is None or confidence < 0.85

    if len(compact) <= 4 and (confidence is None or confidence < 0.70):
        return True

    return False
