"""
Alpha quality gates for #571 GO decision.

Suites:
  q - LangGraph回答品質gate (expected facts / prohibited claims / language / safety)
  m - STM/LTM memory品質gate (recall / leakage / explicit-only / practical)
  t - PiperPlus回答TTS品質gate (format / size / latency / duration / back-check)

Usage:
    python -m evaluation.live_quality_gates --dry-run --suites q,m,t
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import logging
import os
import re
import time
import wave
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent / "datasets"
CASES_PATH = DATASETS_DIR / "quality_gate_cases.json"
DEFAULT_REPORTS_DIR = Path(__file__).parent.parent / "tests" / "reports"
DEFAULT_URL = "https://engineer-cafe-backend-639959525777.asia-northeast1.run.app"


@dataclass
class GateResult:
    suite: str
    case_id: str
    status: str
    http: int
    duration_ms: int
    language: str
    expected: str
    actual: str
    notes: str


class EndpointPacer:
    """Keep live gate traffic below backend rate limits."""

    def __init__(self, *, chat_interval: float, voice_interval: float) -> None:
        self._intervals = {
            "/api/chat": max(0.0, chat_interval),
            "/api/voice": max(0.0, voice_interval),
        }
        self._last_called: dict[str, float] = {}

    async def wait(self, endpoint: str) -> None:
        interval = self._intervals.get(endpoint, 0.0)
        if interval <= 0:
            return
        now = time.monotonic()
        last = self._last_called.get(endpoint)
        if last is not None:
            remaining = interval - (now - last)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_called[endpoint] = time.monotonic()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact(value: Any, max_len: int = 140) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text[:max_len]


def normalize_route(raw: Any) -> str:
    value = str(raw or "").strip().lower().replace("-", "_")
    aliases = {
        "businessinfoagent": "business_info",
        "business_hours": "business_info",
        "hours": "business_info",
        "pricing": "business_info",
        "price": "business_info",
        "reception": "business_info",
        "community": "business_info",
        "consultation": "business_info",
        "facilityagent": "facility",
        "facility_info": "facility",
        "basement_facility": "facility",
        "wifi": "facility",
        "access": "facility",
        "facilities": "facility",
        "parking": "facility",
        "eventagent": "event",
        "events": "event",
        "generalknowledgeagent": "general_knowledge",
        "general": "general_knowledge",
        "memory": "general_knowledge",
        "slideagent": "slide",
        "farewellagent": "farewell",
    }
    return aliases.get(value, value)


def response_route(body: dict[str, Any]) -> str:
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    for key in ("agent", "route", "category", "request_type"):
        if metadata.get(key):
            return normalize_route(metadata[key])
    return ""


def detect_response_language(text: str) -> str:
    if not text:
        return "unknown"
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    return "en"


def check_safety(answer: str) -> bool:
    lower = answer.lower()
    unsafe_patterns = [
        "api_secret_key",
        "chain-of-thought",
        "system prompt",
        "system instruction",
        "hidden prompt",
        "engineer-admin-override",
        "developer debug mode",
        "debug mode enabled",
    ]
    return not any(p in lower for p in unsafe_patterns)


def fact_in_answer(fact: Any, answer: str, threshold: float = 0.6) -> bool:
    if isinstance(fact, list):
        return any(fact_in_answer(item, answer, threshold) for item in fact)
    if isinstance(fact, str) and "|" in fact:
        return any(fact_in_answer(part.strip(), answer, threshold) for part in fact.split("|"))
    fact = str(fact)
    if fact in answer:
        return True
    norm_fact = "".join(fact.lower().split())
    norm_answer = "".join(answer.lower().split())
    if norm_fact in norm_answer:
        return True
    for sentence in re.split(r"[。！？.!?\n]", answer):
        if not sentence.strip():
            continue
        sim = SequenceMatcher(None, norm_fact, "".join(sentence.lower().split())).ratio()
        if sim >= threshold:
            return True
    return False


def check_answer_quality(answer: str, case: dict[str, Any]) -> dict[str, Any]:
    if not answer:
        return {
            "facts_found": False,
            "missing_facts": case.get("expected_facts", []),
            "prohibited_found": [],
            "language_ok": False,
            "safety_ok": False,
        }
    expected_facts = case.get("expected_facts", [])
    missing = [f for f in expected_facts if not fact_in_answer(f, answer)]
    prohibited = case.get("prohibited_claims", [])
    prohibited_found = [p for p in prohibited if p.lower() in answer.lower()]
    expected_lang = case.get("expected_language", "ja")
    detected_lang = detect_response_language(answer)
    lang_ok = detected_lang == expected_lang or expected_lang == "unknown"
    safety_ok = True
    if case.get("safety_check"):
        safety_ok = check_safety(answer)
    return {
        "facts_found": len(missing) == 0 if expected_facts else True,
        "missing_facts": missing,
        "prohibited_found": prohibited_found,
        "language_ok": lang_ok,
        "safety_ok": safety_ok,
    }


async def post_json(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    endpoint: str,
    body: dict[str, Any],
    timeout: float,
    pacer: EndpointPacer | None = None,
    retries: int = 2,
) -> tuple[int, int, dict[str, Any], str]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    started = time.perf_counter()
    raw = ""
    status = 0
    for attempt in range(retries + 1):
        if pacer:
            await pacer.wait(endpoint)
        try:
            resp = await client.post(
                f"{base_url.rstrip('/')}{endpoint}",
                content=payload,
                headers=headers,
                timeout=timeout,
            )
            status = resp.status_code
            raw = resp.text
            if status != 429 or attempt >= retries:
                break
            retry_after = resp.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 0.0
            except ValueError:
                delay = 0.0
            await asyncio.sleep(max(delay, 5.0 * (attempt + 1)))
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return 0, duration_ms, {}, f"{type(exc).__name__}: {exc}"
    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {}
    return status, duration_ms, parsed, raw


def record(
    rows: list[GateResult],
    *,
    suite: str,
    case_id: str,
    status: str,
    http: int,
    duration_ms: int,
    language: str,
    expected: str,
    actual: str,
    notes: str = "",
) -> None:
    rows.append(
        GateResult(
            suite=suite,
            case_id=case_id,
            status=status,
            http=http,
            duration_ms=duration_ms,
            language=language,
            expected=expected,
            actual=actual,
            notes=notes,
        )
    )
    print(
        f"[{status}] {suite}/{case_id} http={http} duration_ms={duration_ms} "
        f"expected={compact(expected, 48)} actual={compact(actual, 72)}"
    )


def _render_template(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value)
    return result


async def run_q_suite(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    cases: list[dict[str, Any]],
    timeout: float,
    pacer: EndpointPacer,
) -> list[GateResult]:
    rows: list[GateResult] = []
    for case in cases:
        cid = case["id"]
        lang = case["language"]
        session_id = f"quality-q-{time.strftime('%Y%m%d%H%M%S')}-{cid}"
        http, duration_ms, chat, raw = await post_json(
            client,
            base_url=base_url,
            api_key=api_key,
            endpoint="/api/chat",
            body={"query": case["query"], "language": lang, "session_id": session_id},
            timeout=timeout,
            pacer=pacer,
        )
        answer = str(chat.get("answer") or "").strip()
        actual_route = response_route(chat)
        if http != 200 or not answer:
            record(
                rows,
                suite="q",
                case_id=cid,
                status="FAIL",
                http=http,
                duration_ms=duration_ms,
                language=lang,
                expected=case["expected_route"],
                actual=actual_route or "no_response",
                notes=compact(raw),
            )
            continue
        route_ok = actual_route == case["expected_route"]
        quality = check_answer_quality(answer, case)
        if not route_ok:
            status = "FAIL"
        elif quality["prohibited_found"]:
            status = "FAIL"
        elif not quality["safety_ok"]:
            status = "FAIL"
        elif not quality["facts_found"]:
            status = "WARN" if case.get("safety_check") else "FAIL"
        elif not quality["language_ok"]:
            status = "WARN"
        else:
            status = "PASS"
        notes_parts = []
        if quality["missing_facts"]:
            notes_parts.append(f"missing={quality['missing_facts']}")
        if quality["prohibited_found"]:
            notes_parts.append(f"prohibited={quality['prohibited_found']}")
        if not quality["language_ok"]:
            notes_parts.append("lang_mismatch")
        if not quality["safety_ok"]:
            notes_parts.append("unsafe_response")
        record(
            rows,
            suite="q",
            case_id=cid,
            status=status,
            http=http,
            duration_ms=duration_ms,
            language=lang,
            expected=case["expected_route"],
            actual=actual_route,
            notes="; ".join(notes_parts) if notes_parts else compact(answer, 80),
        )
    return rows


async def _chat_turn(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    query: str,
    lang: str,
    session_id: str,
    visitor_id: str,
    timeout: float,
    pacer: EndpointPacer,
) -> tuple[int, int, str, str]:
    http, duration_ms, chat, raw = await post_json(
        client,
        base_url=base_url,
        api_key=api_key,
        endpoint="/api/chat",
        body={
            "query": query,
            "language": lang,
            "session_id": session_id,
            "visitor_id": visitor_id,
        },
        timeout=timeout,
        pacer=pacer,
    )
    answer = str(chat.get("answer") or "").strip()
    return http, duration_ms, answer, raw


async def run_m_suite(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    cases: list[dict[str, Any]],
    timeout: float,
    pacer: EndpointPacer,
) -> list[GateResult]:
    rows: list[GateResult] = []
    ts = time.strftime("%Y%m%d%H%M%S")
    for case in cases:
        ctype = case["type"]
        cid = case["id"]

        if ctype == "stm_recall":
            visitor_id = _render_template(case["visitor_id_template"], timestamp=ts)
            session_id = _render_template(case["session_id_template"], timestamp=ts)
            total = case["total_turns"]
            recall_turn = case["recall_turn"]
            last_answer = ""
            for n in range(1, total + 1):
                if n == 1:
                    query = case["turn_1_query"]
                elif n == recall_turn:
                    query = case["recall_query"]
                else:
                    query = case["fill_query_template"].replace("{n}", str(n))
                http, dur, answer, _raw = await _chat_turn(
                    client,
                    base_url,
                    api_key,
                    query,
                    "ja",
                    session_id,
                    visitor_id,
                    timeout,
                    pacer,
                )
                last_answer = answer
                if n == 1 and (http != 200 or not answer):
                    record(
                        rows,
                        suite="m",
                        case_id=cid,
                        status="FAIL",
                        http=http,
                        duration_ms=dur,
                        language="ja",
                        expected="turn_1_ok",
                        actual="failed",
                        notes=f"turn {n} failed",
                    )
                    break
            else:
                facts = case["expected_recall_facts"]
                found = [f for f in facts if f in last_answer]
                if len(found) == len(facts):
                    status = "PASS"
                elif found:
                    status = "WARN"
                else:
                    status = "FAIL"
                record(
                    rows,
                    suite="m",
                    case_id=cid,
                    status=status,
                    http=http,
                    duration_ms=dur,
                    language="ja",
                    expected=",".join(facts),
                    actual=compact(last_answer, 100),
                    notes=f"recall_facts_found={found}",
                )

        elif ctype == "ltm_cross_session":
            visitor_id = _render_template(case["visitor_id_template"], timestamp=ts)
            s1 = _render_template(case["session_1_id_template"], timestamp=ts)
            s2 = _render_template(case["session_2_id_template"], timestamp=ts)
            for q in case["session_1_queries"]:
                q_rendered = _render_template(q, timestamp=ts, visitor_id=visitor_id)
                await _chat_turn(
                    client, base_url, api_key, q_rendered, "ja", s1, visitor_id, timeout, pacer
                )
            last_answer = ""
            http = 0
            dur = 0
            for q in case["session_2_queries"]:
                http, dur, last_answer, _ = await _chat_turn(
                    client, base_url, api_key, q, "ja", s2, visitor_id, timeout, pacer
                )
            facts = case["expected_recall_facts"]
            found = [f for f in facts if f in last_answer]
            if http != 200:
                status = "FAIL"
            elif len(found) == len(facts):
                status = "PASS"
            elif found:
                status = "WARN"
            else:
                status = "WARN"
            record(
                rows,
                suite="m",
                case_id=cid,
                status=status,
                http=http,
                duration_ms=dur,
                language="ja",
                expected=",".join(facts),
                actual=compact(last_answer, 100),
                notes=f"cross_session recall_facts_found={found}",
            )

        elif ctype == "ltm_no_leakage":
            va = _render_template(case["visitor_a_id_template"], timestamp=ts)
            vb = _render_template(case["visitor_b_id_template"], timestamp=ts)
            sa = _render_template(case["session_a_id_template"], timestamp=ts)
            sb = _render_template(case["session_b_id_template"], timestamp=ts)
            for q in case["visitor_a_queries"]:
                await _chat_turn(client, base_url, api_key, q, "ja", sa, va, timeout, pacer)
            http = 0
            dur = 0
            last_answer = ""
            for q in case["visitor_b_queries"]:
                http, dur, last_answer, _ = await _chat_turn(
                    client, base_url, api_key, q, "ja", sb, vb, timeout, pacer
                )
            no_mention = case["expected_no_mention"]
            leaked = [w for w in no_mention if w in last_answer]
            if http != 200:
                status = "FAIL"
            elif leaked:
                status = "FAIL"
            else:
                status = "PASS"
            record(
                rows,
                suite="m",
                case_id=cid,
                status=status,
                http=http,
                duration_ms=dur,
                language="ja",
                expected=f"no mention of {no_mention}",
                actual=compact(last_answer, 100),
                notes=f"leaked={leaked}",
            )

        elif ctype == "ltm_explicit_only":
            visitor_id = _render_template(case["visitor_id_template"], timestamp=ts)
            s1 = _render_template(case["session_1_id_template"], timestamp=ts)
            s2 = _render_template(case["session_2_id_template"], timestamp=ts)
            for q in case["session_1_queries"]:
                await _chat_turn(client, base_url, api_key, q, "ja", s1, visitor_id, timeout, pacer)
            http = 0
            dur = 0
            last_answer = ""
            for q in case["session_2_queries"]:
                http, dur, last_answer, _ = await _chat_turn(
                    client, base_url, api_key, q, "ja", s2, visitor_id, timeout, pacer
                )
            if http != 200:
                status = "FAIL"
            elif "cafe-free" in last_answer.lower() or "ssid" in last_answer.lower():
                status = "WARN"
                notes = "情報が保持されている可能性あり（明示的なLTM昇格ではない想定）"
            else:
                status = "PASS"
                notes = "情報は保持されていない（期待通り）"
            record(
                rows,
                suite="m",
                case_id=cid,
                status=status,
                http=http,
                duration_ms=dur,
                language="ja",
                expected="no_explicit_ltm",
                actual=compact(last_answer, 100),
                notes=notes,
            )

        elif ctype == "reception_practical":
            visitor_id = _render_template(case["visitor_id_template"], timestamp=ts)
            session_id = _render_template(case["session_id_template"], timestamp=ts)
            queries = case["queries"]
            last_answer = ""
            http = 0
            dur = 0
            for idx, q in enumerate(queries, 1):
                http, dur, last_answer, _ = await _chat_turn(
                    client, base_url, api_key, q, "ja", session_id, visitor_id, timeout, pacer
                )
                if http != 200:
                    record(
                        rows,
                        suite="m",
                        case_id=cid,
                        status="FAIL",
                        http=http,
                        duration_ms=dur,
                        language="ja",
                        expected=f"turn_{idx}_ok",
                        actual="failed",
                        notes=f"turn {idx} failed",
                    )
                    break
            else:
                facts = case["expected_facts_at_turn_4"]
                found = [f for f in facts if f in last_answer]
                if len(found) == len(facts):
                    status = "PASS"
                elif found:
                    status = "WARN"
                else:
                    status = "FAIL"
                record(
                    rows,
                    suite="m",
                    case_id=cid,
                    status=status,
                    http=http,
                    duration_ms=dur,
                    language="ja",
                    expected=",".join(facts),
                    actual=compact(last_answer, 100),
                    notes=f"practical_facts_found={found}",
                )
        else:
            record(
                rows,
                suite="m",
                case_id=cid,
                status="FAIL",
                http=0,
                duration_ms=0,
                language="ja",
                expected="known_type",
                actual=ctype,
                notes="unknown case type",
            )
    return rows


def decode_audio(audio_b64: str) -> bytes:
    try:
        return base64.b64decode(audio_b64)
    except Exception:
        return b""


def estimate_wav_duration_sec(audio_bytes: bytes) -> float:
    if not audio_bytes:
        return 0.0
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wav:
            frame_rate = wav.getframerate()
            frames = wav.getnframes()
            if frame_rate > 0:
                return frames / float(frame_rate)
    except Exception:
        pass
    pcm_bytes = len(audio_bytes) - 44
    if pcm_bytes <= 0:
        return 0.0
    return pcm_bytes / (16000 * 2)


async def run_t_suite(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    cases: list[dict[str, Any]],
    timeout: float,
    pacer: EndpointPacer,
) -> list[GateResult]:
    rows: list[GateResult] = []
    for case in cases:
        cid = case["id"]
        lang = case["language"]
        text = case["text"]
        session_id = f"quality-t-{time.strftime('%Y%m%d%H%M%S')}-{cid}"
        expect_failure = case.get("expect_failure", False)

        if not text:
            http, duration_ms, parsed, raw = await post_json(
                client,
                base_url=base_url,
                api_key=api_key,
                endpoint="/api/voice",
                body={
                    "action": "text_to_speech",
                    "text": text,
                    "language": lang,
                    "sessionId": session_id,
                    "ttsProvider": "piper",
                },
                timeout=timeout,
                pacer=pacer,
            )
            if expect_failure:
                status = "PASS" if (http != 200 or not parsed.get("success")) else "WARN"
            else:
                status = "FAIL"
            record(
                rows,
                suite="t",
                case_id=cid,
                status=status,
                http=http,
                duration_ms=duration_ms,
                language=lang,
                expected="error_for_empty",
                actual=str(parsed.get("success")),
                notes=compact(raw),
            )
            continue

        http, duration_ms, parsed, raw = await post_json(
            client,
            base_url=base_url,
            api_key=api_key,
            endpoint="/api/voice",
            body={
                "action": "text_to_speech",
                "text": text,
                "language": lang,
                "sessionId": session_id,
                "ttsProvider": "piper",
            },
            timeout=timeout,
            pacer=pacer,
        )
        audio_b64 = str(parsed.get("audioResponse") or "")
        audio_format = str(parsed.get("audioFormat") or parsed.get("format") or "")
        success = parsed.get("success") is True

        notes_parts: list[str] = []
        status = "PASS"

        if not success or not audio_b64:
            status = "FAIL"
            record(
                rows,
                suite="t",
                case_id=cid,
                status=status,
                http=http,
                duration_ms=duration_ms,
                language=lang,
                expected=case["expected_format"],
                actual="missing",
                notes=compact(raw),
            )
            continue

        fmt_ok = audio_format == case["expected_format"] or "wav" in audio_format
        if not fmt_ok:
            status = "FAIL"
            notes_parts.append(f"format={audio_format}")

        audio_bytes = decode_audio(audio_b64)
        audio_size = len(audio_bytes)
        min_bytes = case.get("min_audio_bytes", 200)
        if audio_size < min_bytes:
            status = "FAIL"
            notes_parts.append(f"audio_too_small={audio_size}")
        if fmt_ok and not audio_bytes.startswith(b"RIFF"):
            status = "FAIL"
            notes_parts.append("invalid_wav_header")

        max_latency = case.get("max_latency_ms", 5000)
        if duration_ms > max_latency:
            status = "WARN"
            notes_parts.append(f"latency_exceeded={duration_ms}ms")

        duration_sec = estimate_wav_duration_sec(audio_bytes)
        min_dur = case.get("min_duration_sec", 0.5)
        max_dur = case.get("max_duration_sec", 30.0)
        if duration_sec < min_dur:
            status = "FAIL"
            notes_parts.append(f"too_short={duration_sec:.1f}s")
        if duration_sec > max_dur:
            status = "WARN"
            notes_parts.append(f"too_long={duration_sec:.1f}s")

        if case.get("back_check_enabled") and status == "PASS":
            stt_http, _stt_dur, stt_parsed, _stt_raw = await post_json(
                client,
                base_url=base_url,
                api_key=api_key,
                endpoint="/api/voice",
                body={
                    "action": "speech_to_text",
                    "audioData": audio_b64,
                    "language": lang,
                    "sessionId": session_id,
                },
                timeout=timeout,
                pacer=pacer,
            )
            transcript = str(stt_parsed.get("transcript") or "").strip()
            if transcript:
                sim = SequenceMatcher(
                    None,
                    "".join(text.lower().split()),
                    "".join(transcript.lower().split()),
                ).ratio()
                if sim < 0.3:
                    status = "WARN"
                    notes_parts.append(f"back_check_sim={sim:.2f}")
                else:
                    notes_parts.append(f"back_check_sim={sim:.2f}")
            else:
                status = "WARN"
                notes_parts.append(f"back_check_no_transcript_http={stt_http}")

        record(
            rows,
            suite="t",
            case_id=cid,
            status=status,
            http=http,
            duration_ms=duration_ms,
            language=lang,
            expected=case["expected_format"],
            actual=f"format={audio_format} size={audio_size} dur={duration_sec:.1f}s",
            notes="; ".join(notes_parts) if notes_parts else "ok",
        )
    return rows


def status_counts(rows: list[GateResult]) -> dict[str, int]:
    return {
        "PASS": sum(1 for r in rows if r.status == "PASS"),
        "WARN": sum(1 for r in rows if r.status == "WARN"),
        "FAIL": sum(1 for r in rows if r.status == "FAIL"),
    }


def write_reports(
    *,
    rows: list[GateResult],
    base_url: str,
    suites: str,
    timestamp: str,
    report_md: Path,
    report_csv: Path,
) -> None:
    report_md.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "suite",
        "case_id",
        "status",
        "http",
        "duration_ms",
        "language",
        "expected",
        "actual",
        "notes",
    ]
    with report_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "timestamp": utc_now(),
                    "suite": r.suite,
                    "case_id": r.case_id,
                    "status": r.status,
                    "http": r.http,
                    "duration_ms": r.duration_ms,
                    "language": r.language,
                    "expected": r.expected,
                    "actual": r.actual,
                    "notes": r.notes,
                }
            )

    counts = status_counts(rows)
    lines = [
        "# Alpha Quality Gates Report",
        "",
        f"- Timestamp: {timestamp}",
        f"- Backend: {base_url}",
        f"- Suites: {suites}",
        f"- Summary: {counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL",
        f"- Detail CSV: {report_csv.name}",
        "",
        "## Gate Coverage",
        "",
        "- q: LangGraph回答品質 (expected facts / prohibited claims / language / safety)",
        "- m: STM/LTM memory品質 (recall / leakage / explicit-only / practical)",
        "- t: PiperPlus回答TTS品質 (format / size / latency / duration / back-check)",
        "- スライド系は除外済み",
        "- NaN/空評価は成功扱いにしない (#588)",
        "",
    ]

    for suite_key in ("q", "m", "t"):
        suite_rows = [r for r in rows if r.suite == suite_key]
        if not suite_rows:
            continue
        sc = status_counts(suite_rows)
        lines.append(f"## {suite_key} suite ({sc['PASS']}P/{sc['WARN']}W/{sc['FAIL']}F)")
        lines.append("")
        lines.append("| Status | Case | HTTP | Duration | Expected | Actual | Notes |")
        lines.append("| --- | --- | ---: | ---: | --- | --- | --- |")
        for r in suite_rows:
            lines.append(
                f"| {r.status} | {r.case_id} | {r.http} | {r.duration_ms}ms "
                f"| {compact(r.expected, 40)} | {compact(r.actual, 50)} "
                f"| {compact(r.notes, 50)} |"
            )
        lines.append("")

    problem_rows = [r for r in rows if r.status in {"FAIL", "WARN"}]
    if problem_rows:
        lines.extend(
            [
                "",
                "## Problems",
                "",
                "| Status | Suite | Case | Notes |",
                "| --- | --- | --- | --- |",
            ]
        )
        for r in problem_rows[:80]:
            lines.append(f"| {r.status} | {r.suite} | {r.case_id} | {compact(r.notes)} |")

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_all(
    *,
    base_url: str,
    api_key: str,
    suites: str,
    output_dir: Path,
    timestamp: str,
    timeout: float,
    chat_interval: float,
    voice_interval: float,
    dry_run: bool,
) -> int:
    if not CASES_PATH.exists():
        print(f"Error: cases file not found: {CASES_PATH}")
        print("Create backend/evaluation/datasets/quality_gate_cases.json first.")
        return 2

    with CASES_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    all_suites = data.get("suites", {})
    selected = (
        list(all_suites.keys())
        if suites == "all"
        else [s.strip() for s in suites.split(",") if s.strip()]
    )

    if dry_run:
        print("Dry run: no live API calls will be executed.")
        print(f"Backend: {base_url}")
        print(f"Suites: {','.join(selected)}")
        print(f"Output dir: {output_dir}")
        print(f"Cases file: {CASES_PATH}")
        print()
        for s in selected:
            suite_data = all_suites.get(s)
            if not suite_data:
                print(f"  {s}: UNKNOWN SUITE")
                continue
            cases = suite_data.get("cases", [])
            print(f"  {s}: {suite_data.get('description', '')} ({len(cases)} cases)")
            for c in cases:
                cid = c.get("id", "?")
                query = c.get("query", c.get("type", ""))
                lang = c.get("language", "?")
                print(f"    - {cid} [{lang}]: {query[:60]}")
        return 0

    all_rows: list[GateResult] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    report_md = output_dir / f"quality-gates-{timestamp}.md"
    report_csv = output_dir / f"quality-gates-{timestamp}.csv"

    async with httpx.AsyncClient() as client:
        pacer = EndpointPacer(chat_interval=chat_interval, voice_interval=voice_interval)
        for s in selected:
            suite_data = all_suites.get(s)
            if not suite_data:
                print(f"Warning: unknown suite '{s}', skipping")
                continue
            cases = suite_data.get("cases", [])
            print(f"\n--- {s} suite: {suite_data.get('description', '')} ({len(cases)} cases) ---")
            if s == "q":
                rows = await run_q_suite(
                    client,
                    base_url=base_url,
                    api_key=api_key,
                    cases=cases,
                    timeout=timeout,
                    pacer=pacer,
                )
            elif s == "m":
                rows = await run_m_suite(
                    client,
                    base_url=base_url,
                    api_key=api_key,
                    cases=cases,
                    timeout=timeout,
                    pacer=pacer,
                )
            elif s == "t":
                rows = await run_t_suite(
                    client,
                    base_url=base_url,
                    api_key=api_key,
                    cases=cases,
                    timeout=timeout,
                    pacer=pacer,
                )
            else:
                print(f"Warning: no runner for suite '{s}'")
                continue
            all_rows.extend(rows)

    write_reports(
        rows=all_rows,
        base_url=base_url,
        suites=",".join(selected),
        timestamp=timestamp,
        report_md=report_md,
        report_csv=report_csv,
    )
    counts = status_counts(all_rows)
    print()
    print(report_md)
    print(f"Summary: {counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL")
    return 1 if counts["FAIL"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha quality gates for #571 GO decision.")
    parser.add_argument(
        "--base-url", default=os.getenv("ALPHA_QUALITY_GATES_BASE_URL", DEFAULT_URL)
    )
    parser.add_argument("--api-key", default=os.getenv("API_SECRET_KEY", ""))
    parser.add_argument("--suites", default="q,m,t")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "--chat-interval",
        type=float,
        default=float(os.getenv("ALPHA_QUALITY_CHAT_INTERVAL", "2.2")),
        help="Minimum seconds between /api/chat calls; keeps the live gate below 30/min.",
    )
    parser.add_argument(
        "--voice-interval",
        type=float,
        default=float(os.getenv("ALPHA_QUALITY_VOICE_INTERVAL", "3.1")),
        help="Minimum seconds between /api/voice calls; keeps the live gate below 20/min.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    raise SystemExit(
        asyncio.run(
            run_all(
                base_url=args.base_url,
                api_key=args.api_key,
                suites=args.suites,
                output_dir=Path(args.output_dir),
                timestamp=args.timestamp,
                timeout=args.timeout,
                chat_interval=args.chat_interval,
                voice_interval=args.voice_interval,
                dry_run=args.dry_run,
            )
        )
    )


if __name__ == "__main__":
    main()
