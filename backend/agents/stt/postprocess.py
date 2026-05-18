from __future__ import annotations

import importlib
import json
import os
import re
import time
from typing import Any, List, Optional

from .common import (
    TranscriptionResult,
    _duration_ms,
    _get_stt_postprocess_client,
    _is_real_openrouter_key,
    _qwen_postprocess_enabled,
    logger,
    log_stt_event,
)


def _public_symbol(name: str, fallback: Any) -> Any:
    try:
        return getattr(importlib.import_module("backend.agents.stt_agent"), name)
    except Exception:
        return fallback


def _postprocess_client():
    return _public_symbol("_get_stt_postprocess_client", _get_stt_postprocess_client)()


def _log_stt_event(**kwargs: Any) -> None:
    _public_symbol("log_stt_event", log_stt_event)(**kwargs)


_QWEN_VOCAB_CACHE: Optional[List[str]] = None
_JAPANESE_LANGUAGE_LABELS = {"ja", "japanese", "日本語"}
_QWEN_BOUNDARY = r"(?=(?:の|は|を|に|へ|で|と|、|。|？|\?|！|!|$))"
_SAINO_NAME_VARIANT = (
    r"(?:才能|再能|最能|採納|彩野|才納|才脳|歳納|財野|財納|"
    r"サイノウ|さいのう|サイナ|さいな|サイ\s*の|さい\s*の|才\s*の|"
    r"saino|sino|cyno)"
)
_QWEN_DETERMINISTIC_CORRECTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Observed Qwen CPU confusion for the cafe attached to Engineer Cafe.
    (re.compile(r"閉\s*接\s*の\s*カフェ"), "併設のカフェ"),
    (re.compile(r"閉\s*接\s*カフェ"), "併設カフェ"),
    # Observed ONNX/CPU proper-noun confusions for エンジニアカフェ.
    (re.compile(rf"エンジン\s*や\s*カ(?:ベ|べ){_QWEN_BOUNDARY}"), "エンジニアカフェ"),
    (re.compile(rf"エンジン\s*カフェ{_QWEN_BOUNDARY}"), "エンジニアカフェ"),
    (re.compile(rf"エンジニア\s*カ(?:ベ|べ|フ){_QWEN_BOUNDARY}"), "エンジニアカフェ"),
    (re.compile(rf"エンジニア\s*か(?:べ|ふぇ){_QWEN_BOUNDARY}"), "エンジニアカフェ"),
    # Saino variants are only corrected when cafe/cafe&bar context is explicit.
    (
        re.compile(rf"カフェ\s*(?:アンド|&|＆)\s*バー\s*{_SAINO_NAME_VARIANT}", re.IGNORECASE),
        "サイノカフェ",
    ),
    (
        re.compile(rf"{_SAINO_NAME_VARIANT}\s*(?:カフェ|cafe){_QWEN_BOUNDARY}", re.IGNORECASE),
        "サイノカフェ",
    ),
)


def _normalize_qwen_language_label(language: Optional[str]) -> str:
    if language is None:
        return ""
    return str(language).strip().lower()


def _is_japanese_qwen_language(language: Optional[str]) -> bool:
    return _normalize_qwen_language_label(language) in _JAPANESE_LANGUAGE_LABELS


def _qwen_deterministic_post_process(transcript: str, language: Optional[str]) -> str:
    """Apply narrow, deterministic Qwen STT corrections for live cafe terms."""

    if not _is_japanese_qwen_language(language) or not transcript:
        return transcript

    corrected = transcript
    for pattern, replacement in _QWEN_DETERMINISTIC_CORRECTIONS:
        corrected = pattern.sub(replacement, corrected)
    return corrected


def _load_qwen_vocab() -> List[str]:
    """Load domain vocabulary once for Qwen post-processing hints.

    Reads backend/data/stt_vocabulary.json which has structure:
    {"vocabulary": [{"word": "エンジニアカフェ", ...}, ...]}
    """
    global _QWEN_VOCAB_CACHE
    if _QWEN_VOCAB_CACHE is not None:
        return _QWEN_VOCAB_CACHE
    try:
        from pathlib import Path

        vocab_path = Path(__file__).resolve().parents[2] / "data" / "stt_vocabulary.json"
        if not vocab_path.exists():
            _QWEN_VOCAB_CACHE = []
            return _QWEN_VOCAB_CACHE
        raw = json.loads(vocab_path.read_text())
        words: List[str] = []
        # Preferred schema: {"vocabulary": [{"word": "...", ...}, ...]}
        if isinstance(raw, dict) and isinstance(raw.get("vocabulary"), list):
            for entry in raw["vocabulary"]:
                if isinstance(entry, dict):
                    word = entry.get("word")
                    if isinstance(word, str) and word.strip():
                        words.append(word.strip())
                elif isinstance(entry, str) and entry.strip():
                    words.append(entry.strip())
        # Legacy / fallback: plain list of strings
        elif isinstance(raw, list):
            words = [str(w).strip() for w in raw if isinstance(w, (str, int, float))]
        # Deduplicate while preserving order.
        seen = set()
        deduped: List[str] = []
        for w in words:
            if w and w not in seen:
                seen.add(w)
                deduped.append(w)
        _QWEN_VOCAB_CACHE = deduped
    except Exception as exc:
        logger.warning("Qwen vocab load failed: %s", exc)
        _QWEN_VOCAB_CACHE = []
    return _QWEN_VOCAB_CACHE


async def _qwen_llm_post_process(transcript: str, language: str) -> str:
    """LLM post-process for Qwen Japanese output with domain vocabulary hints.

    Returns the original transcript on any failure (OpenRouter error, timeout,
    empty response, excessive divergence). Disabled by default — set
    STT_QWEN_POSTPROCESS_ENABLED=true to opt in. This is a defense-in-depth
    fix for Bug #439 (Qwen mangling proper nouns under noise) and adds
    OpenRouter latency to every Japanese STT request when enabled.
    """
    if not _qwen_postprocess_enabled():
        return transcript
    if not _is_japanese_qwen_language(language):
        return transcript
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not _is_real_openrouter_key(api_key) or not transcript.strip():
        return transcript
    # Skip post-processing for long transcripts to avoid OpenRouter max_tokens
    # truncation silently overwriting good STT output. Voice queries are
    # typically short (<300 chars); longer transcripts are unlikely to need
    # proper-noun correction enough to risk data loss.
    if len(transcript) > 300:
        return transcript

    vocab = _load_qwen_vocab()
    vocab_hint = ", ".join(vocab[:15]) if vocab else ""
    model = os.getenv("STT_POSTPROCESS_MODEL", "google/gemini-3.1-flash-lite-preview")

    system_prompt = (
        "You correct Japanese speech-to-text transcription errors for "
        "Engineer Cafe (エンジニアカフェ) in Fukuoka. "
        + (f"Domain terms that may appear: {vocab_hint}. " if vocab_hint else "")
        + "Only correct phonetically similar errors. Do NOT paraphrase, "
        "translate, or add commentary. Return ONLY the corrected Japanese "
        "transcript."
    )

    try:
        client = _postprocess_client()
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript},
                ],
                "max_tokens": 600,
            },
        )
        if resp.status_code != 200:
            logger.warning("Qwen post-process %d: %s", resp.status_code, resp.text[:100])
            return transcript
        data = resp.json()
        corrected = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not corrected:
            return transcript
        # Length-divergence guard: reject only when the corrected text is
        # wildly longer or shorter than the original. This permits legitimate
        # script conversions (hiragana → katakana / kanji) which look totally
        # "different" at the character level but preserve content length.
        # Hallucinations and paraphrases tend to balloon or truncate length.
        orig_len = len(transcript)
        corr_len = len(corrected)
        if orig_len == 0 or corr_len > orig_len * 2 or corr_len < orig_len * 0.5:
            logger.warning(
                "Qwen post-process rejected (length %d->%d): '%s' -> '%s'",
                orig_len,
                corr_len,
                transcript[:40],
                corrected[:40],
            )
            return transcript
        if corrected != transcript:
            logger.info("Qwen post-process: '%s' -> '%s'", transcript[:40], corrected[:40])
        return corrected
    except Exception as exc:
        logger.warning("Qwen LLM post-process failed: %s", exc)
        return transcript


async def _post_process_qwen_transcription_result(
    result: TranscriptionResult,
    *,
    stt_trace_id: Optional[str] = None,
) -> TranscriptionResult:
    """Apply deterministic Qwen fixes, then optional LLM post-processing."""

    if not _is_japanese_qwen_language(result.language) or not result.text.strip():
        return result

    postprocess_started_at = time.perf_counter()
    original_text = result.text
    deterministic_text = _qwen_deterministic_post_process(original_text, result.language)
    try:
        corrected_text = await _qwen_llm_post_process(deterministic_text, result.language)
        _log_stt_event(
            event="stt_qwen_postprocess_complete",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            language=result.language,
            success=True,
            changed=corrected_text != original_text,
            deterministic_changed=deterministic_text != original_text,
            llm_changed=corrected_text != deterministic_text,
            enabled=_qwen_postprocess_enabled(),
            transcript_chars=len(original_text),
            corrected_chars=len(corrected_text),
            stt_qwen_postprocess_duration_ms=_duration_ms(postprocess_started_at),
        )
    except Exception as exc:
        logger.warning("Qwen post-process wrapper failed: %s", exc)
        corrected_text = deterministic_text
        _log_stt_event(
            event="stt_qwen_postprocess_complete",
            stt_trace_id=stt_trace_id,
            provider="qwen-primary",
            language=result.language,
            success=False,
            error_type=type(exc).__name__,
            changed=corrected_text != original_text,
            deterministic_changed=deterministic_text != original_text,
            llm_changed=False,
            enabled=_qwen_postprocess_enabled(),
            transcript_chars=len(original_text),
            corrected_chars=len(corrected_text),
            stt_qwen_postprocess_duration_ms=_duration_ms(postprocess_started_at),
        )

    if corrected_text == result.text:
        return result

    return TranscriptionResult(
        text=corrected_text,
        confidence=result.confidence,
        language=result.language,
        word_confidences=result.word_confidences,
    )
